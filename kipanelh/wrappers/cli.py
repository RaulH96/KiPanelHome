"""
CLI standalone para KiPanelHome.

Uso:
    python -m kipanelh.wrappers.cli \\
        --pcb proyecto1.kicad_pcb:2 \\
        --pcb proyecto2.kicad_pcb:1 \\
        --layers F.Cu,B.Cu \\
        --method toner-transfer \\
        --sheet A4 \\
        --formats pdf,svg,png \\
        --dpi 1200 \\
        --output ./output/

Si se pasa --gui, abre el diálogo wxPython en lugar de leer argumentos.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from ..core.models import (
    PanelizeRequest, PcbJob, LayerSelection, SheetConfig, OutputConfig,
    TransferMethod, SheetSize, OutputFormat,
)
from ..core.orchestrator import run


def _parse_pcb_arg(value: str) -> PcbJob:
    """Acepta 'path/to/file.kicad_pcb' o 'path/to/file.kicad_pcb:N' donde N=copias."""
    if ":" in value and not value[1:3] == ":\\":  # cuidado con paths Windows tipo C:\
        path_str, copies_str = value.rsplit(":", 1)
        try:
            copies = int(copies_str)
        except ValueError:
            path_str, copies = value, 1
    else:
        path_str, copies = value, 1
    return PcbJob(path=Path(path_str), copies=copies)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kipanelh",
        description="KiPanelHome: panelizar múltiples PCBs de KiCad en una sola hoja para fabricación casera.",
    )
    p.add_argument("--pcb", action="append", default=[],
                   help="PCB a incluir. Formato: path[:copias]. Repetir para varias.")
    p.add_argument("--layers", default="F.Cu",
                   help="Capas separadas por coma (F.Cu,B.Cu,F.SilkS,...)")
    p.add_argument("--no-edge-cuts-overlay", action="store_true",
                   help="No sobreponer Edge.Cuts en cada capa.")
    p.add_argument("--method", choices=[m.value for m in TransferMethod],
                   default=TransferMethod.TONER_TRANSFER.value)
    p.add_argument("--sheet", choices=[s.value for s in SheetSize],
                   default=SheetSize.A4.value)
    p.add_argument("--sheet-width", type=float, help="Ancho hoja custom (mm)")
    p.add_argument("--sheet-height", type=float, help="Alto hoja custom (mm)")
    p.add_argument("--margin", type=float, default=5.0, help="Margen de hoja (mm)")
    p.add_argument("--spacing", type=float, default=3.0, help="Separación entre PCBs (mm)")
    p.add_argument("--no-rotation", action="store_true",
                   help="No permitir rotación al empacar.")
    p.add_argument("--formats", default="pdf",
                   help="Formatos separados por coma: pdf,svg,png")
    p.add_argument("--dpi", type=int, default=1200, help="DPI para PNG.")
    p.add_argument("--negative-colors", action="store_true",
                   help="Invertir colores: fondo negro, trazas blancas (fotolito negativo).")
    p.add_argument("--combine-layers", action="store_true",
                   help="Empacar todas las capas en la misma hoja en lugar de hojas separadas.")
    p.add_argument("--output", default="./output", help="Carpeta de salida.")
    p.add_argument("--gui", action="store_true",
                   help="Abrir UI wxPython en lugar de usar argumentos.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.gui:
        return _run_gui()

    if not args.pcb:
        print("ERROR: debes pasar al menos un --pcb", file=sys.stderr)
        return 2

    pcbs = [_parse_pcb_arg(v) for v in args.pcb]
    cu_layers, tech_layers = [], []
    for lay in [l.strip() for l in args.layers.split(",") if l.strip()]:
        if lay.endswith(".Cu"):
            cu_layers.append(lay)
        else:
            tech_layers.append(lay)

    request = PanelizeRequest(
        pcbs=pcbs,
        layers=LayerSelection(
            cu_layers=cu_layers,
            tech_layers=tech_layers,
            edge_cuts_overlay=not args.no_edge_cuts_overlay,
            combine_layers=args.combine_layers,
        ),
        method=TransferMethod(args.method),
        sheet=SheetConfig(
            size=SheetSize(args.sheet),
            custom_width_mm=args.sheet_width,
            custom_height_mm=args.sheet_height,
            margin_mm=args.margin,
            spacing_mm=args.spacing,
            allow_rotation=not args.no_rotation,
        ),
        output=OutputConfig(
            formats=[OutputFormat(f.strip()) for f in args.formats.split(",")],
            output_dir=Path(args.output),
            png_dpi=args.dpi,
            negative_colors=args.negative_colors,
        ),
    )

    results = run(request)
    print(f"\n✓ Generado correctamente. Capas procesadas: {len(results)}")
    for layer, comp in results.items():
        print(f"  - {layer}: {len(comp.page_files)} página(s)")
        print(f"    Manifest: {comp.manifest_path}")
    return 0


def _run_gui() -> int:
    try:
        import wx  # type: ignore
    except ImportError:
        print("ERROR: --gui requiere wxPython (`pip install wxPython`)", file=sys.stderr)
        return 2

    from ..ui.main_dialog import KiPanelHomeDialog

    app = wx.App(False)
    dlg = KiPanelHomeDialog(parent=None)
    if dlg.show_modal() == wx.ID_OK:
        request = dlg.build_request()
        results = run(request)
        wx.MessageBox(
            f"Generado: {len(results)} capa(s).\n"
            f"Salida en: {request.output.output_dir}",
            "Listo", wx.OK | wx.ICON_INFORMATION,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
