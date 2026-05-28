"""
Wrapper de la API pcbnew de KiCad para generar SVG por capa.

Este módulo es el único que importa pcbnew. Para pruebas sin KiCad usa
mock_plotter.py en su lugar.

Compatibilidad verificada: KiCad 10.0 (pcbnew 10.0.1).
  - DRILL_MARKS_NO_DRILL_SHAPE   (KiCad 8+, antes: PCB_PLOT_PARAMS.NO_DRILL_SHAPE)
  - SetBlackAndWhite(True)        para negro sólido
  - SetSvgPrecision(4)            coordenadas limpias
  - Filename generado: {pcb_stem}-{base}.svg  (prefijo del board, KiCad 9+)

Notas sobre coordenadas:
  KiCad genera el SVG con viewBox = página completa de KiCad (ej. A3 = 419×297mm),
  NO la PCB sola. El contenido de la PCB está desplazado al interior de esa página.
  board_origin_x_mm / board_origin_y_mm guardan ese desplazamiento para que el
  compositor lo use como translate(-origin_x, -origin_y).
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field

try:
    import pcbnew  # type: ignore[import-not-found]
    _PCBNEW_AVAILABLE = True
except ImportError:
    _PCBNEW_AVAILABLE = False


@dataclass
class PlottedLayer:
    """Resultado de plotear una capa: SVG + bounding box en mm + origen en página."""
    layer_name: str
    pcb_path: Path
    svg_path: Path
    bbox_width_mm: float
    bbox_height_mm: float
    mirrored: bool
    # Posición del bbox dentro del SVG (origen de la página de KiCad).
    # El compositor necesita translate(-board_x, -board_y) para alinear al origen.
    board_x_mm: float = field(default=0.0)
    board_y_mm: float = field(default=0.0)


def _ensure_pcbnew() -> None:
    if not _PCBNEW_AVAILABLE:
        raise RuntimeError(
            "El módulo `pcbnew` no está disponible. Ejecuta con el Python de KiCad.\n"
            "Usa run_kicad.bat o busca el python.exe dentro de tu instalación de KiCad."
        )


def _layer_id(layer_name: str) -> int:
    """Convierte nombre de capa KiCad a su ID numérico interno."""
    _ensure_pcbnew()
    name_map = {
        "F.Cu":    pcbnew.F_Cu,
        "B.Cu":    pcbnew.B_Cu,
        "F.SilkS": pcbnew.F_SilkS,
        "B.SilkS": pcbnew.B_SilkS,
        "F.Mask":  pcbnew.F_Mask,
        "B.Mask":  pcbnew.B_Mask,
        "F.Paste": pcbnew.F_Paste,
        "B.Paste": pcbnew.B_Paste,
        "Edge.Cuts": pcbnew.Edge_Cuts,
    }
    if layer_name in name_map:
        return name_map[layer_name]
    if layer_name.startswith("In") and layer_name.endswith(".Cu"):
        idx = int(layer_name[2:].split(".")[0])
        return pcbnew.In1_Cu + (idx - 1)
    raise ValueError(f"Capa no reconocida: {layer_name}")


def plot_layer_to_svg(
    pcb_path: Path,
    layer_name: str,
    mirror: bool,
    include_edge_cuts: bool,
    output_dir: Path,
) -> PlottedLayer:
    """
    Plotea una capa de la PCB a SVG: escala 1:1, negro puro, sin marcos de hoja.

    El SVG resultante tiene viewBox igual a la página KiCad completa; el board
    está desplazado dentro de ella. PlottedLayer.board_{x,y}_mm registra ese
    desplazamiento para que el compositor lo cancele con translate(-x,-y).
    """
    _ensure_pcbnew()
    output_dir.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(pcb_path))
    pc = pcbnew.PLOT_CONTROLLER(board)
    po = pc.GetPlotOptions()

    po.SetOutputDirectory(str(output_dir))
    po.SetPlotFrameRef(False)
    po.SetAutoScale(False)
    po.SetScale(1.0)
    po.SetMirror(mirror)
    po.SetUseAuxOrigin(False)
    po.SetNegative(False)
    po.SetBlackAndWhite(True)        # negro sólido (crítico para toner/UV)
    po.SetSvgPrecision(4)
    po.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)

    layer_id = _layer_id(layer_name)
    suffix = "_mirror" if mirror else ""
    filename_base = f"{pcb_path.stem}_{layer_name.replace('.', '_')}{suffix}"

    pc.SetLayer(layer_id)
    pc.OpenPlotfile(filename_base, pcbnew.PLOT_FORMAT_SVG, layer_name)
    pc.PlotLayer()

    # Superponer Edge.Cuts en la misma trama SVG llamando PlotLayer por segunda vez.
    # SetLayerSelection no funciona para SVG; hay que llamar PlotLayer una vez por capa.
    if include_edge_cuts and layer_name != "Edge.Cuts":
        pc.SetLayer(pcbnew.Edge_Cuts)
        pc.PlotLayer()

    # GetPlotFileName() da la ruta exacta del archivo generado (KiCad 9+)
    generated_path = Path(pc.GetPlotFileName())
    pc.ClosePlot()

    svg_path = generated_path if generated_path.exists() else _find_svg(output_dir, pcb_path.stem)

    if not svg_path.exists():
        raise FileNotFoundError(
            f"El plotter no generó SVG en {output_dir}. "
            f"Archivos presentes: {list(output_dir.glob('*.svg'))}"
        )

    # Bounding box de la PCB (Edge.Cuts)
    bbox = board.GetBoardEdgesBoundingBox()
    width_mm  = pcbnew.ToMM(bbox.GetWidth())
    height_mm = pcbnew.ToMM(bbox.GetHeight())
    # Origen del bbox dentro del SVG (posición en la página de KiCad)
    board_x_mm = pcbnew.ToMM(bbox.GetX())
    board_y_mm = pcbnew.ToMM(bbox.GetY())

    return PlottedLayer(
        layer_name=layer_name,
        pcb_path=pcb_path,
        svg_path=svg_path,
        bbox_width_mm=width_mm,
        bbox_height_mm=height_mm,
        mirrored=mirror,
        board_x_mm=board_x_mm,
        board_y_mm=board_y_mm,
    )


def _find_svg(output_dir: Path, pcb_stem: str) -> Path:
    """Fallback: busca el SVG más reciente que contenga el nombre del board."""
    candidates = sorted(
        output_dir.glob(f"{pcb_stem}*.svg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else output_dir / f"{pcb_stem}.svg"
