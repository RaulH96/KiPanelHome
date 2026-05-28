"""
Bin-packing 2D para acomodar las PCBs ploteadas en la hoja.

Usa rectpack. Si los PCBs no caben en una hoja, genera múltiples páginas.
NUNCA reescala los PCBs - escala 1:1 es regla dura del proyecto.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

try:
    from rectpack import newPacker, MaxRectsBssf, GuillotineBssfSas  # type: ignore
    _RECTPACK_AVAILABLE = True
except ImportError:
    _RECTPACK_AVAILABLE = False

from .plotter import PlottedLayer
from .models import SheetConfig


@dataclass
class PlacedItem:
    """Una PCB ya colocada en una hoja."""
    plot: PlottedLayer
    page: int          # número de hoja (1-indexed)
    x_mm: float        # esquina inferior izquierda en mm
    y_mm: float
    width_mm: float
    height_mm: float
    rotated: bool


@dataclass
class PackResult:
    pages: int
    items: list[PlacedItem]
    overflow: list[PlottedLayer]  # los que no cupieron en ninguna hoja


def pack(
    plots: list[PlottedLayer],
    sheet: SheetConfig,
) -> PackResult:
    """
    Empaca los plots en una o más hojas.

    Args:
        plots: lista de plots ya generados (cada uno tiene bbox conocido).
               Si una PCB se quiere imprimir N veces, debe aparecer N veces
               en esta lista.
        sheet: configuración de la hoja.

    Returns:
        PackResult con la disposición.
    """
    if not _RECTPACK_AVAILABLE:
        raise RuntimeError("rectpack no instalado. `pip install rectpack`")

    sheet_w, sheet_h = sheet.dimensions_mm()
    usable_w = sheet_w - 2 * sheet.margin_mm
    usable_h = sheet_h - 2 * sheet.margin_mm

    # Validación: ningún plot individual puede exceder la hoja
    for p in plots:
        w = p.bbox_width_mm + sheet.spacing_mm
        h = p.bbox_height_mm + sheet.spacing_mm
        fits_normal = w <= usable_w and h <= usable_h
        fits_rotated = sheet.allow_rotation and (h <= usable_w and w <= usable_h)
        if not (fits_normal or fits_rotated):
            raise ValueError(
                f"La PCB {p.pcb_path.name} (capa {p.layer_name}) "
                f"mide {p.bbox_width_mm:.1f}x{p.bbox_height_mm:.1f} mm "
                f"y no cabe en una hoja {sheet.size.value} con márgenes."
            )

    rotation_allowed = sheet.allow_rotation
    packer = newPacker(
        rotation=rotation_allowed,
        pack_algo=MaxRectsBssf,
    )

    # Agregar rectángulos (con spacing aplicado)
    for idx, p in enumerate(plots):
        w = p.bbox_width_mm + sheet.spacing_mm
        h = p.bbox_height_mm + sheet.spacing_mm
        packer.add_rect(width=w, height=h, rid=idx)

    # Agregar varias hojas como bins (hasta un máximo razonable)
    MAX_PAGES = 50
    for _ in range(MAX_PAGES):
        packer.add_bin(usable_w, usable_h)

    packer.pack()

    placed: list[PlacedItem] = []
    placed_ids: set[int] = set()

    for page_idx, abin in enumerate(packer):
        for rect in abin:
            x, y, w, h, rid = rect.x, rect.y, rect.width, rect.height, rect.rid
            original = plots[rid]
            # Detectar rotación: si el width empacado != bbox_width original (con spacing)
            original_w = original.bbox_width_mm + sheet.spacing_mm
            rotated = abs(w - original_w) > 0.01

            placed.append(PlacedItem(
                plot=original,
                page=page_idx + 1,
                x_mm=x + sheet.margin_mm,
                y_mm=y + sheet.margin_mm,
                width_mm=original.bbox_width_mm,
                height_mm=original.bbox_height_mm,
                rotated=rotated,
            ))
            placed_ids.add(rid)

    overflow = [plots[i] for i in range(len(plots)) if i not in placed_ids]
    pages_used = max((it.page for it in placed), default=0)

    return PackResult(pages=pages_used, items=placed, overflow=overflow)
