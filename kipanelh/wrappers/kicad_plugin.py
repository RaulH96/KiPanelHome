"""
Plugin de KiCad. Se registra como ActionPlugin y aparece en el menú
Tools → External Plugins → Panel Print.

INSTALACIÓN:
  Linux:   copiar/symlink el paquete completo (kipanelh/) a
           ~/.config/kicad/<version>/scripting/plugins/
  Windows: %APPDATA%\\kicad\\<version>\\scripting\\plugins\\
  macOS:   ~/Library/Preferences/kicad/<version>/scripting/plugins/

Después abrir el PCB Editor → Tools → External Plugins → Refresh.
"""
from __future__ import annotations
from pathlib import Path

try:
    import pcbnew  # type: ignore[import-not-found]
    _PCBNEW_AVAILABLE = True
except ImportError:
    _PCBNEW_AVAILABLE = False


if _PCBNEW_AVAILABLE:

    class KiPanelHomePlugin(pcbnew.ActionPlugin):
        def defaults(self) -> None:
            self.name = "KiPanelHome"
            self.category = "Manufacturing"
            self.description = (
                "Panelizar múltiples PCBs en una sola hoja para fabricación "
                "casera (planchado / film UV)."
            )
            self.show_toolbar_button = True
            # self.icon_file_name = str(Path(__file__).parent / "icon.png")

        def Run(self) -> None:
            # Importar wxPython y la UI solo en runtime para que el módulo
            # cargue aunque wx no esté disponible al importar
            from ..ui.main_dialog import KiPanelHomeDialog
            from ..core.orchestrator import run as run_pipeline
            import wx  # type: ignore

            board = pcbnew.GetBoard()
            preloaded = Path(board.GetFileName()) if board and board.GetFileName() else None

            dlg = KiPanelHomeDialog(parent=None, preloaded_pcb=preloaded)
            if dlg.show_modal() == wx.ID_OK:
                request = dlg.build_request()
                try:
                    results = run_pipeline(request)
                    wx.MessageBox(
                        f"✓ Generado: {len(results)} capa(s).\n"
                        f"Carpeta: {request.output.output_dir}",
                        "KiPanelHome - Listo",
                        wx.OK | wx.ICON_INFORMATION,
                    )
                except Exception as e:
                    wx.MessageBox(
                        f"Error: {e}",
                        "KiPanelHome - Error",
                        wx.OK | wx.ICON_ERROR,
                    )

    # Registrar la instancia
    KiPanelHomePlugin().register()
