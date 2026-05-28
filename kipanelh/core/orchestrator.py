"""
Orquestador principal. Punto de entrada del core que recibe un
PanelizeRequest y produce las hojas.

Los wrappers (CLI y plugin) solo arman el PanelizeRequest y llaman a `run`.
"""
from __future__ import annotations
from pathlib import Path
import tempfile

from .models import PanelizeRequest
from .methods import should_mirror
from .plotter import plot_layer_to_svg, PlottedLayer
from .packer import pack
from .composer import compose_pages, CompositionResult


def run(request: PanelizeRequest) -> dict[str, CompositionResult]:
    """
    Ejecuta el flujo completo: plot → pack → compose.

    Returns:
        dict de layer_name → CompositionResult.
        Si combine_layers=True, la clave es "combined".
    """
    all_layers = list(request.layers.cu_layers) + list(request.layers.tech_layers)
    if not all_layers:
        raise ValueError("Debes seleccionar al menos una capa.")

    results: dict[str, CompositionResult] = {}
    default_copies = sum(job.copies for job in request.pcbs)

    with tempfile.TemporaryDirectory() as tmpdir:
        plot_dir = Path(tmpdir) / "plots"

        # --- Plotear todas las capas de todas las PCBs ---
        # plotted_cache[pcb_path][layer_name] = PlottedLayer
        plotted_cache: dict[Path, dict[str, PlottedLayer]] = {}
        for layer_name in all_layers:
            mirror = should_mirror(layer_name, request.method, request.layers)
            for job in request.pcbs:
                cache = plotted_cache.setdefault(job.path, {})
                if layer_name not in cache:
                    cache[layer_name] = plot_layer_to_svg(
                        pcb_path=job.path,
                        layer_name=layer_name,
                        mirror=mirror,
                        include_edge_cuts=request.layers.edge_cuts_overlay,
                        output_dir=plot_dir,
                    )

        if request.layers.combine_layers:
            # Empacar todas las capas juntas en la misma hoja
            combined_plots: list[PlottedLayer] = []
            for layer_name in all_layers:
                n_copies = request.layers.layer_copies_override.get(layer_name, default_copies)
                plots_for_layer = _expand_plots(request, layer_name, plotted_cache, n_copies)
                combined_plots.extend(plots_for_layer)

            pack_result = pack(combined_plots, request.sheet)
            _check_overflow(pack_result)

            comp = compose_pages(
                pack_result=pack_result,
                sheet=request.sheet,
                output=request.output,
                method=request.method,
                layer_name="combined",
            )
            results["combined"] = comp

        else:
            # Una hoja por capa (comportamiento original)
            for layer_name in all_layers:
                n_copies = request.layers.layer_copies_override.get(layer_name, default_copies)
                expanded = _expand_plots(request, layer_name, plotted_cache, n_copies)

                pack_result = pack(expanded, request.sheet)
                _check_overflow(pack_result)

                comp = compose_pages(
                    pack_result=pack_result,
                    sheet=request.sheet,
                    output=request.output,
                    method=request.method,
                    layer_name=layer_name,
                )
                results[layer_name] = comp

    return results


def _expand_plots(
    request: PanelizeRequest,
    layer_name: str,
    plotted_cache: dict[Path, dict[str, PlottedLayer]],
    n_copies: int,
) -> list[PlottedLayer]:
    """Expande los plots de una capa según el número de copias."""
    if n_copies <= 0:
        n_copies = sum(job.copies for job in request.pcbs)

    # Con layer_copies_override se ignoran los job.copies individuales y
    # se reparte equitativamente entre las PCBs (round-robin).
    override_active = layer_name in request.layers.layer_copies_override
    if override_active:
        expanded: list[PlottedLayer] = []
        pcb_list = [job.path for job in request.pcbs]
        for i in range(n_copies):
            pcb_path = pcb_list[i % len(pcb_list)]
            expanded.append(plotted_cache[pcb_path][layer_name])
        return expanded

    # Sin override: respetar job.copies por PCB
    expanded = []
    for job in request.pcbs:
        for _ in range(job.copies):
            expanded.append(plotted_cache[job.path][layer_name])
    return expanded


def _check_overflow(pack_result) -> None:
    if pack_result.overflow:
        names = ", ".join(o.pcb_path.name for o in pack_result.overflow)
        raise RuntimeError(
            f"No cupieron todas las PCBs en {pack_result.pages} hojas "
            f"(faltaron: {names}). Aumenta el número de hojas o reduce copias."
        )
