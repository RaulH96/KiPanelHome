"""
Modelos de datos del proyecto. Sin lógica, solo estructuras.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TransferMethod(str, Enum):
    """Método de fabricación casera al que se orienta la impresión."""
    TONER_TRANSFER = "toner-transfer"   # planchado
    FILM_UV = "film-uv"                 # acetato emulsión-abajo (Convención A, recomendada)
    FILM_UV_B = "film-uv-b"             # acetato emulsión-arriba (Convención B)
    CUSTOM = "custom"                   # el usuario define espejado por capa


class SheetSize(str, Enum):
    A4 = "A4"
    LETTER = "Letter"
    A3 = "A3"
    CUSTOM = "Custom"


class OutputFormat(str, Enum):
    PDF = "pdf"
    SVG = "svg"
    PNG = "png"


@dataclass
class PcbJob:
    """Una PCB a panelizar, con cuántas copias se quieren."""
    path: Path
    copies: int = 1
    label: str | None = None  # opcional, para identificar en la hoja

    def __post_init__(self) -> None:
        if self.copies < 1:
            raise ValueError(f"copies debe ser >= 1, recibido {self.copies}")
        if not self.path.exists():
            raise FileNotFoundError(f"PCB no encontrada: {self.path}")


@dataclass
class LayerSelection:
    """Capas seleccionadas para el panel.

    `cu_layers` y `tech_layers` son nombres tal como los maneja KiCad
    (ej: "F.Cu", "B.Cu", "F.SilkS"). El espejado por capa se calcula
    en methods.py a partir del método elegido y este campo.
    """
    cu_layers: list[str] = field(default_factory=lambda: ["F.Cu"])
    tech_layers: list[str] = field(default_factory=list)  # SilkS, Mask, etc.
    edge_cuts_overlay: bool = True
    # Override manual de espejado, solo si method == CUSTOM
    mirror_override: dict[str, bool] = field(default_factory=dict)
    # Si True, todas las capas se empacan juntas en la misma hoja
    combine_layers: bool = False
    # Número de copias por capa (0 = usar el total de copias de los PcbJobs)
    layer_copies_override: dict[str, int] = field(default_factory=dict)


@dataclass
class SheetConfig:
    """Configuración de la hoja física donde se imprimirá."""
    size: SheetSize = SheetSize.A4
    custom_width_mm: float | None = None
    custom_height_mm: float | None = None
    margin_mm: float = 5.0
    spacing_mm: float = 3.0
    allow_rotation: bool = True

    # Dimensiones físicas estándar (mm)
    STANDARD_SIZES: dict[SheetSize, tuple[float, float]] = field(
        default_factory=lambda: {
            SheetSize.A4: (210.0, 297.0),
            SheetSize.LETTER: (215.9, 279.4),
            SheetSize.A3: (297.0, 420.0),
        },
        init=False,
        repr=False,
    )

    def dimensions_mm(self) -> tuple[float, float]:
        if self.size == SheetSize.CUSTOM:
            if self.custom_width_mm is None or self.custom_height_mm is None:
                raise ValueError("Hoja custom requiere width y height en mm")
            return (self.custom_width_mm, self.custom_height_mm)
        return self.STANDARD_SIZES[self.size]


@dataclass
class OutputConfig:
    formats: list[OutputFormat] = field(default_factory=lambda: [OutputFormat.PDF])
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    png_dpi: int = 1200
    # Invierte colores en el SVG: fondo negro, trazas blancas (para fotolito negativo)
    negative_colors: bool = False

    def __post_init__(self) -> None:
        if self.png_dpi < 300:
            raise ValueError(
                f"DPI demasiado bajo para fabricación de PCB ({self.png_dpi}). "
                "Mínimo recomendado: 600, preferible 1200."
            )


@dataclass
class PanelizeRequest:
    """Solicitud completa que recibe el core para generar las hojas."""
    pcbs: list[PcbJob]
    layers: LayerSelection
    method: TransferMethod
    sheet: SheetConfig
    output: OutputConfig

    def total_pcb_instances(self) -> int:
        return sum(job.copies for job in self.pcbs)
