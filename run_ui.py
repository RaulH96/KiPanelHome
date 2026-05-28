"""Script standalone para lanzar KiPanelHome con el Python de KiCad."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import wx
from kipanelh.ui.main_dialog import KiPanelHomeDialog


def main() -> None:
    app = wx.App()
    dlg = KiPanelHomeDialog(parent=None)

    if dlg.show_modal() != wx.ID_OK:
        print("Cancelado.")
        return

    try:
        request = dlg.build_request()
    except Exception as exc:
        wx.MessageBox(str(exc), "Error en configuración", wx.OK | wx.ICON_ERROR)
        return

    if not request.pcbs:
        wx.MessageBox("No hay PCBs seleccionadas.", "Sin PCBs", wx.OK | wx.ICON_WARNING)
        return

    # Mostrar progreso
    progress = wx.ProgressDialog(
        "Generando panel…",
        "Iniciando pipeline…",
        maximum=100,
        style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT,
    )

    results = {}
    error = None

    def run_pipeline() -> None:
        nonlocal results, error
        try:
            from kipanelh.core.orchestrator import run
            wx.CallAfter(progress.Update, 10, "Ploteando capas con pcbnew…")
            results = run(request)
            wx.CallAfter(progress.Update, 100, "Listo.")
        except Exception as exc:
            error = exc
            wx.CallAfter(progress.Update, 100, f"Error: {exc}")

    import threading
    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()

    while t.is_alive():
        wx.Yield()
        if not progress.WasCancelled():
            app.Yield()
        t.join(timeout=0.05)

    progress.Destroy()

    if error:
        wx.MessageBox(
            f"Error al generar el panel:\n\n{error}",
            "Error", wx.OK | wx.ICON_ERROR,
        )
        print(f"Error: {error}")
        return

    # Resumen de archivos generados
    generated = []
    for layer_name, comp in results.items():
        for page, files in comp.page_files.items():
            for fmt, path in files.items():
                generated.append(path)
                print(f"  [{layer_name} p{page}] {path}")

    if not generated:
        wx.MessageBox("No se generó ningún archivo.", "Sin salida", wx.OK | wx.ICON_WARNING)
        return

    # Preguntar si abrir la carpeta de salida
    answer = wx.MessageBox(
        f"Se generaron {len(generated)} archivo(s) en:\n{request.output.output_dir}\n\n"
        "¿Abrir la carpeta?",
        "Panel generado",
        wx.YES_NO | wx.ICON_INFORMATION,
    )
    if answer == wx.YES:
        from kipanelh.ui.main_dialog import _open_file
        _open_file(request.output.output_dir)


if __name__ == "__main__":
    main()
