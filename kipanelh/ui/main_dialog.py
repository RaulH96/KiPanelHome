"""
Diálogo wxPython principal de la herramienta.

Diseñado para ser usado tanto desde el CLI (standalone) como desde
el plugin de KiCad. La diferencia entre ambos es solo el parent window
y la pre-carga de la PCB actual cuando se llama desde el plugin.
"""
from __future__ import annotations
from pathlib import Path
import os
import platform
import subprocess
import tempfile
import threading

try:
    import wx  # type: ignore
    _WX_AVAILABLE = True
except ImportError:
    _WX_AVAILABLE = False


def _open_file(path: Path) -> None:
    """Abre un archivo con la aplicación predeterminada del sistema (multiplataforma)."""
    try:
        sys_name = platform.system()
        if sys_name == "Windows":
            # cmd /c start es más confiable que os.startfile dentro del proceso de KiCad
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(path.resolve())],
                shell=False,
                creationflags=0x08000000,  # CREATE_NO_WINDOW: sin ventana cmd parpadeante
            )
        elif sys_name == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass

from ..core.models import (
    PanelizeRequest, PcbJob, LayerSelection, SheetConfig, OutputConfig,
    TransferMethod, SheetSize, OutputFormat,
)
from ..core.methods import should_mirror, describe_method


# (nombre_capa, activa_por_defecto)
_LAYER_DEFS: list[tuple[str, bool]] = [
    ("F.Cu",    True),
    ("B.Cu",    True),
    ("In1.Cu",  False),
    ("In2.Cu",  False),
    ("F.SilkS", False),
    ("B.SilkS", False),
    ("F.Mask",  False),
    ("B.Mask",  False),
]

_METHODS: list[tuple[TransferMethod, str]] = [
    (TransferMethod.TONER_TRANSFER, "Toner Transfer (planchado)"),
    (TransferMethod.FILM_UV,        "Film UV"),
    (TransferMethod.CUSTOM,         "Custom"),
]

_SHEET_SIZES: list[tuple[SheetSize, str]] = [
    (SheetSize.A4,     "A4"),
    (SheetSize.LETTER, "Carta (Letter)"),
    (SheetSize.A3,     "A3"),
    (SheetSize.CUSTOM, "Personalizada"),
]


class KiPanelHomeDialog:
    """
    Diálogo principal.

    Uso:
        dlg = KiPanelHomeDialog(parent=None, preloaded_pcb=Path(...))
        if dlg.show_modal() == wx.ID_OK:
            request = dlg.build_request()
    """

    def __init__(
        self,
        parent: "wx.Window | None" = None,
        preloaded_pcb: Path | None = None,
    ) -> None:
        if not _WX_AVAILABLE:
            raise RuntimeError("wxPython no instalado. `pip install wxPython`")
        self.parent = parent
        self.preloaded_pcb = preloaded_pcb
        self._dialog: "wx.Dialog | None" = None
        self._scroll: "wx.ScrolledWindow | None" = None

        self.pcb_jobs: list[PcbJob] = []
        if preloaded_pcb is not None:
            self.pcb_jobs.append(PcbJob(path=preloaded_pcb, copies=1))

        # Valor "auto" de copias: suma total de todas las PCBs.
        self._auto_total: int = sum(j.copies for j in self.pcb_jobs) or 1

        # Carpeta de salida por defecto: junto a la PCB cargada, o Documentos
        if preloaded_pcb is not None:
            self._default_out = str(preloaded_pcb.parent / "kipanel_output")
        else:
            self._default_out = str(Path.home() / "Documents" / "kipanel_output")

        # ── Widget refs ──────────────────────────────────────────────────────
        self._pcb_list: "wx.ListCtrl | None" = None

        # Capas: checkbox activo, checkbox espejado, spinbox copias, label auto
        self._layer_checks: dict[str, "wx.CheckBox"] = {}
        self._layer_mirror_checks: dict[str, "wx.CheckBox"] = {}
        self._layer_copies_spins: dict[str, "wx.SpinCtrl"] = {}
        self._layer_auto_labels: dict[str, "wx.StaticText"] = {}

        self._edge_cuts_check: "wx.CheckBox | None" = None
        self._combine_layers_check: "wx.CheckBox | None" = None

        # Método
        self._method_radios: list["wx.RadioButton"] = []
        self._method_desc: "wx.StaticText | None" = None
        self._negative_check: "wx.CheckBox | None" = None
        # Sub-panel Film UV (convención A/B)
        self._film_uv_panel: "wx.Panel | None" = None
        self._film_uv_conv_radios: list["wx.RadioButton"] = []  # [0]=A, [1]=B

        # Hoja
        self._sheet_choice: "wx.Choice | None" = None
        self._custom_size_panel: "wx.Panel | None" = None
        self._custom_w: "wx.SpinCtrlDouble | None" = None
        self._custom_h: "wx.SpinCtrlDouble | None" = None
        self._margin_spin: "wx.SpinCtrlDouble | None" = None
        self._spacing_spin: "wx.SpinCtrlDouble | None" = None
        self._rotation_check: "wx.CheckBox | None" = None

        # Salida
        self._fmt_pdf: "wx.CheckBox | None" = None
        self._fmt_svg: "wx.CheckBox | None" = None
        self._fmt_png: "wx.CheckBox | None" = None
        self._dpi_spin: "wx.SpinCtrl | None" = None
        self._out_dir: "wx.DirPickerCtrl | None" = None

        # Vista previa inline
        self._btn_prev_svg: "wx.Button | None" = None
        self._btn_prev_pdf: "wx.Button | None" = None
        self._preview_status: "wx.StaticText | None" = None

    # ─────────────────────────────────────────────────────────────────────────
    # Interfaz pública
    # ─────────────────────────────────────────────────────────────────────────

    def show_modal(self) -> int:
        self._dialog = self._build_dialog()
        return self._dialog.ShowModal()

    def build_request(self) -> PanelizeRequest:
        """Construye el PanelizeRequest leyendo el estado actual de los widgets."""
        # Capas activas
        cu_layers: list[str] = []
        tech_layers: list[str] = []
        for name, _ in _LAYER_DEFS:
            cb = self._layer_checks.get(name)
            if cb and cb.IsChecked():
                if ".Cu" in name:
                    cu_layers.append(name)
                else:
                    tech_layers.append(name)

        edge_cuts = self._edge_cuts_check.IsChecked() if self._edge_cuts_check else True
        combine_layers = self._combine_layers_check.IsChecked() if self._combine_layers_check else False

        # Espejado por capa: siempre desde los checkboxes de la UI
        all_active = cu_layers + tech_layers
        mirror_override: dict[str, bool] = {
            name: self._layer_mirror_checks[name].IsChecked()
            for name in all_active
            if name in self._layer_mirror_checks
        }

        # Copias por capa: igual al auto_total → sin override; otro → override
        layer_copies_override: dict[str, int] = {}
        for name, spin in self._layer_copies_spins.items():
            val = spin.GetValue()
            if val > 0 and val != self._auto_total:
                layer_copies_override[name] = val

        # Método efectivo (incluye convención Film UV A/B)
        method = self._effective_method()

        # Hoja
        sheet_idx = self._sheet_choice.GetSelection() if self._sheet_choice else 0
        sheet_size = _SHEET_SIZES[sheet_idx][0]
        is_custom_sheet = sheet_size == SheetSize.CUSTOM

        # Formatos
        formats: list[OutputFormat] = []
        if self._fmt_pdf and self._fmt_pdf.IsChecked():
            formats.append(OutputFormat.PDF)
        if self._fmt_svg and self._fmt_svg.IsChecked():
            formats.append(OutputFormat.SVG)
        if self._fmt_png and self._fmt_png.IsChecked():
            formats.append(OutputFormat.PNG)
        if not formats:
            formats = [OutputFormat.SVG]

        out_path = Path(self._out_dir.GetPath()) if self._out_dir else Path(self._default_out)

        return PanelizeRequest(
            pcbs=list(self.pcb_jobs),
            layers=LayerSelection(
                cu_layers=cu_layers,
                tech_layers=tech_layers,
                edge_cuts_overlay=edge_cuts,
                mirror_override=mirror_override,
                combine_layers=combine_layers,
                layer_copies_override=layer_copies_override,
            ),
            method=method,
            sheet=SheetConfig(
                size=sheet_size,
                custom_width_mm=self._custom_w.GetValue() if is_custom_sheet and self._custom_w else None,
                custom_height_mm=self._custom_h.GetValue() if is_custom_sheet and self._custom_h else None,
                margin_mm=self._margin_spin.GetValue() if self._margin_spin else 5.0,
                spacing_mm=self._spacing_spin.GetValue() if self._spacing_spin else 3.0,
                allow_rotation=self._rotation_check.IsChecked() if self._rotation_check else True,
            ),
            output=OutputConfig(
                formats=formats,
                output_dir=out_path,
                png_dpi=self._dpi_spin.GetValue() if self._dpi_spin else 1200,
                negative_colors=self._negative_check.IsChecked() if self._negative_check else False,
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Construcción del diálogo
    # ─────────────────────────────────────────────────────────────────────────

    def _build_dialog(self) -> "wx.Dialog":
        dlg = wx.Dialog(
            self.parent,
            title="KiPanelHome",
            size=(800, 720),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        dlg.SetMinSize(wx.Size(640, 540))

        self._scroll = wx.ScrolledWindow(dlg, style=wx.VSCROLL)
        self._scroll.SetScrollRate(0, 20)

        p = self._scroll
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        # Orden: PCBs → Método → Capas → Hoja → Salida
        main_sizer.Add(self._build_pcb_section(p),    1, wx.EXPAND | wx.ALL, 6)
        main_sizer.Add(self._build_method_section(p),  0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        main_sizer.Add(self._build_layers_section(p),  0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        main_sizer.Add(self._build_sheet_section(p),   0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        main_sizer.Add(self._build_output_section(p),  0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self._scroll.SetSizer(main_sizer)
        self._scroll.FitInside()

        # Botones: Vista previa inline + Generar + Cancelar
        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_prev_svg = wx.Button(dlg, label="Ver SVG ↗")
        self._btn_prev_svg.Bind(wx.EVT_BUTTON, lambda _e: self._run_preview(OutputFormat.SVG))

        self._btn_prev_pdf = wx.Button(dlg, label="Ver PDF ↗")
        self._btn_prev_pdf.Bind(wx.EVT_BUTTON, lambda _e: self._run_preview(OutputFormat.PDF))

        self._preview_status = wx.StaticText(dlg, label="")
        self._preview_status.SetForegroundColour(wx.Colour(100, 100, 100))

        btn_ok = wx.Button(dlg, wx.ID_OK, label="Generar")
        btn_ok.SetDefault()
        btn_cancel = wx.Button(dlg, wx.ID_CANCEL, label="Cancelar")

        btn_row.Add(self._btn_prev_svg, 0, wx.RIGHT, 4)
        btn_row.Add(self._btn_prev_pdf, 0, wx.RIGHT, 10)
        btn_row.Add(self._preview_status, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_row.AddStretchSpacer()
        btn_row.Add(btn_ok, 0, wx.RIGHT, 4)
        btn_row.Add(btn_cancel, 0)

        dlg_sizer = wx.BoxSizer(wx.VERTICAL)
        dlg_sizer.Add(self._scroll, 1, wx.EXPAND)
        dlg_sizer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 8)
        dlg.SetSizer(dlg_sizer)

        self._refresh_pcb_list()
        self._update_mirror_checks_for_method(self._effective_method())
        return dlg

    def _relayout(self) -> None:
        if self._scroll:
            self._scroll.Layout()
            self._scroll.FitInside()

    # ─────────────────────────────────────────────────────────────────────────
    # Sección 1: PCBs
    # ─────────────────────────────────────────────────────────────────────────

    def _build_pcb_section(self, p: "wx.Window") -> "wx.Sizer":
        box = wx.StaticBox(p, label="PCBs a panelizar")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        self._pcb_list = wx.ListCtrl(
            p, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            size=(-1, 120),
        )
        self._pcb_list.InsertColumn(0, "Archivo",  width=320)
        self._pcb_list.InsertColumn(1, "Copias",   width=55)
        self._pcb_list.InsertColumn(2, "Etiqueta", width=160)
        self._pcb_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_pcb_edit)
        sizer.Add(self._pcb_list, 1, wx.EXPAND | wx.ALL, 4)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in [
            ("Agregar…",       self._on_pcb_add),
            ("Eliminar",       self._on_pcb_remove),
            ("Editar copias…", self._on_pcb_edit),
        ]:
            btn = wx.Button(p, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            btn_row.Add(btn, 0, wx.RIGHT, 4)
        sizer.Add(btn_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        return sizer

    def _refresh_pcb_list(self) -> None:
        if not self._pcb_list:
            return
        self._pcb_list.DeleteAllItems()
        for i, job in enumerate(self.pcb_jobs):
            self._pcb_list.InsertItem(i, job.path.name)
            self._pcb_list.SetItem(i, 1, str(job.copies))
            self._pcb_list.SetItem(i, 2, job.label or "")

        new_total = max(sum(j.copies for j in self.pcb_jobs), 1)
        # Actualizar spinboxes que aún estén en el valor auto anterior
        for name, spin in self._layer_copies_spins.items():
            if spin.GetValue() == self._auto_total or spin.GetValue() == 0:
                spin.SetValue(new_total)
        for lbl in self._layer_auto_labels.values():
            lbl.SetLabel(f"(total: {new_total})")
        self._auto_total = new_total

    def _on_pcb_add(self, _event) -> None:
        with wx.FileDialog(
            self._dialog, "Seleccionar PCB",
            wildcard="KiCad PCB (*.kicad_pcb)|*.kicad_pcb",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
        ) as fd:
            if fd.ShowModal() == wx.ID_OK:
                for raw in fd.GetPaths():
                    path = Path(raw)
                    if not any(j.path == path for j in self.pcb_jobs):
                        self.pcb_jobs.append(PcbJob(path=path, copies=1))
        self._refresh_pcb_list()

    def _on_pcb_remove(self, _event) -> None:
        idx = self._pcb_list.GetFirstSelected() if self._pcb_list else -1
        if 0 <= idx < len(self.pcb_jobs):
            del self.pcb_jobs[idx]
            self._refresh_pcb_list()

    def _on_pcb_edit(self, event) -> None:
        lc = self._pcb_list
        idx = lc.GetFirstSelected() if lc else -1
        if idx < 0 and hasattr(event, "GetIndex"):
            idx = event.GetIndex()
        if not (0 <= idx < len(self.pcb_jobs)):
            return
        job = self.pcb_jobs[idx]

        with wx.Dialog(self._dialog, title=f"Editar: {job.path.name}", size=(310, 170)) as ed:
            vs = wx.BoxSizer(wx.VERTICAL)
            gs = wx.FlexGridSizer(2, 2, 6, 8)
            gs.AddGrowableCol(1)
            gs.Add(wx.StaticText(ed, label="Copias:"), 0, wx.ALIGN_CENTER_VERTICAL)
            spin = wx.SpinCtrl(ed, value=str(job.copies), min=1, max=99)
            gs.Add(spin, 0)
            gs.Add(wx.StaticText(ed, label="Etiqueta:"), 0, wx.ALIGN_CENTER_VERTICAL)
            tc = wx.TextCtrl(ed, value=job.label or "")
            gs.Add(tc, 1, wx.EXPAND)
            vs.Add(gs, 0, wx.EXPAND | wx.ALL, 10)
            vs.Add(ed.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
            ed.SetSizer(vs)
            if ed.ShowModal() == wx.ID_OK:
                self.pcb_jobs[idx] = PcbJob(
                    path=job.path,
                    copies=spin.GetValue(),
                    label=tc.GetValue() or None,
                )
                self._refresh_pcb_list()

    # ─────────────────────────────────────────────────────────────────────────
    # Sección 2: Método (antes que Capas — el método define los defaults de espejado)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_method_section(self, p: "wx.Window") -> "wx.Sizer":
        box = wx.StaticBox(p, label="Método de fabricación")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        # Radios: Toner Transfer | Film UV | Custom
        radio_row = wx.BoxSizer(wx.HORIZONTAL)
        for i, (_, label) in enumerate(_METHODS):
            rb = wx.RadioButton(p, label=label, style=wx.RB_GROUP if i == 0 else 0)
            rb.SetValue(i == 0)
            rb.Bind(wx.EVT_RADIOBUTTON, self._on_method_changed)
            self._method_radios.append(rb)
            radio_row.Add(rb, 0, wx.RIGHT, 16)
        sizer.Add(radio_row, 0, wx.ALL, 6)

        # Descripción del método
        self._method_desc = wx.StaticText(p, label=describe_method(TransferMethod.TONER_TRANSFER))
        self._method_desc.SetForegroundColour(wx.Colour(90, 90, 90))
        sizer.Add(self._method_desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)

        # ── Sub-panel Film UV (convención de contacto) ──────────────────────
        self._film_uv_panel = wx.Panel(p)
        fv_sizer = wx.StaticBoxSizer(
            wx.StaticBox(self._film_uv_panel, label="Convención de contacto (Film UV)"),
            wx.VERTICAL,
        )

        _FILM_UV_CONVS = [
            (
                TransferMethod.FILM_UV,
                "Convención A — emulsión/tinta hacia el cobre  (recomendado)",
                "El acetato se voltea boca-abajo: la tinta toca directamente la placa.\n"
                "Mejor contacto, sin difracción. Espejado igual que Toner Transfer.",
            ),
            (
                TransferMethod.FILM_UV_B,
                "Convención B — emulsión/tinta hacia arriba",
                "La cara limpia del acetato toca la placa; la tinta queda arriba.\n"
                "Mayor difracción. Espejado opuesto: F.Cu normal, B.Cu espejada.",
            ),
        ]
        for i, (conv_method, conv_label, conv_desc) in enumerate(_FILM_UV_CONVS):
            rb = wx.RadioButton(
                self._film_uv_panel, label=conv_label,
                style=wx.RB_GROUP if i == 0 else 0,
            )
            rb.SetValue(i == 0)
            rb.Bind(wx.EVT_RADIOBUTTON, self._on_film_uv_conv_changed)
            self._film_uv_conv_radios.append(rb)
            fv_sizer.Add(rb, 0, wx.LEFT | wx.TOP, 6)
            desc = wx.StaticText(self._film_uv_panel, label=conv_desc)
            desc.SetForegroundColour(wx.Colour(100, 100, 100))
            fv_sizer.Add(desc, 0, wx.LEFT | wx.BOTTOM, 20)

        # Opción negativo dentro del sub-panel Film UV
        neg_box = wx.BoxSizer(wx.HORIZONTAL)
        self._negative_check = wx.CheckBox(
            self._film_uv_panel,
            label="Negativo (invertir colores: trazas blancas, fondo negro)",
        )
        self._negative_check.SetValue(False)
        self._negative_check.SetToolTip(
            "Activa solo si usas fotorresist NEGATIVO (poco común en casa).\n"
            "Con fotorresist POSITIVO (el más común) deja esta opción desmarcada."
        )
        neg_box.Add(self._negative_check, 0, wx.ALIGN_CENTER_VERTICAL)
        neg_note = wx.StaticText(self._film_uv_panel, label="  ← para fotorresist negativo")
        neg_note.SetForegroundColour(wx.Colour(140, 100, 30))
        neg_box.Add(neg_note, 0, wx.ALIGN_CENTER_VERTICAL)
        fv_sizer.Add(neg_box, 0, wx.LEFT | wx.BOTTOM, 6)

        self._film_uv_panel.SetSizer(fv_sizer)
        self._film_uv_panel.Hide()
        sizer.Add(self._film_uv_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        return sizer

    def _on_method_changed(self, _event) -> None:
        idx = next((i for i, r in enumerate(self._method_radios) if r.GetValue()), 0)
        method = _METHODS[idx][0]
        is_film_uv = method == TransferMethod.FILM_UV

        if self._method_desc:
            self._method_desc.SetLabel(describe_method(method))

        # Mostrar/ocultar sub-panel Film UV
        if self._film_uv_panel:
            self._film_uv_panel.Show(is_film_uv)

        # Actualizar checkboxes de espejado según método efectivo
        effective = self._effective_method()
        self._update_mirror_checks_for_method(effective)

        # Auto-check negative for Film UV (usuario usa fotorresist negativo)
        if self._negative_check and is_film_uv:
            self._negative_check.SetValue(True)
        self._relayout()

    def _on_film_uv_conv_changed(self, _event) -> None:
        """Cambia la convención dentro de Film UV y actualiza el espejado."""
        effective = self._effective_method()
        self._update_mirror_checks_for_method(effective)

    def _effective_method(self) -> TransferMethod:
        """Devuelve el TransferMethod real, incluyendo la convención Film UV."""
        idx = next((i for i, r in enumerate(self._method_radios) if r.GetValue()), 0)
        method = _METHODS[idx][0]
        if method == TransferMethod.FILM_UV and self._film_uv_conv_radios:
            # Radio 0 = Convención A (FILM_UV), Radio 1 = Convención B (FILM_UV_B)
            if len(self._film_uv_conv_radios) > 1 and self._film_uv_conv_radios[1].GetValue():
                return TransferMethod.FILM_UV_B
        return method

    def _update_mirror_checks_for_method(self, method: TransferMethod) -> None:
        """Actualiza los checkboxes de espejado con los defaults del método elegido."""
        dummy_sel = LayerSelection()
        for name, mir_cb in self._layer_mirror_checks.items():
            mirror = should_mirror(name, method, dummy_sel)
            mir_cb.SetValue(mirror)

    # ─────────────────────────────────────────────────────────────────────────
    # Sección 3: Capas
    # ─────────────────────────────────────────────────────────────────────────

    def _build_layers_section(self, p: "wx.Window") -> "wx.Sizer":
        box = wx.StaticBox(p, label="Capas a procesar")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        # Grid: encabezado en la primera fila del mismo FlexGridSizer
        # para garantizar alineación perfecta con las columnas de datos.
        grid = wx.FlexGridSizer(cols=4, vgap=3, hgap=8)
        grid.AddGrowableCol(0)

        def _hdr(text: str) -> "wx.StaticText":
            st = wx.StaticText(p, label=text)
            font = st.GetFont()
            font.MakeBold()
            st.SetFont(font)
            st.SetForegroundColour(wx.Colour(80, 80, 80))
            return st

        # Fila de encabezados (misma estructura que las filas de datos)
        grid.Add(_hdr("Capa"),     0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(_hdr("Espejado"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(_hdr("Copias"),   0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(wx.StaticText(p, label=""), 0)  # columna de etiqueta, sin header

        for name, default in _LAYER_DEFS:
            # Col 1: checkbox activo/inactivo
            cb = wx.CheckBox(p, label=name)
            cb.SetValue(default)
            self._layer_checks[name] = cb
            grid.Add(cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

            # Col 2: checkbox de espejado
            mir = wx.CheckBox(p, label="")
            mir.SetValue(False)
            self._layer_mirror_checks[name] = mir
            grid.Add(mir, 0, wx.ALIGN_CENTER_VERTICAL)

            # Col 3: spinbox de copias
            spin = wx.SpinCtrl(p, value=str(self._auto_total), min=1, max=999, size=(60, -1))
            spin.SetToolTip("Copias de esta capa. Se sincroniza con el total de PCBs.")
            self._layer_copies_spins[name] = spin
            grid.Add(spin, 0, wx.ALIGN_CENTER_VERTICAL)

            # Col 4: etiqueta de referencia
            lbl = wx.StaticText(p, label=f"(total: {self._auto_total})")
            lbl.SetForegroundColour(wx.Colour(130, 130, 130))
            self._layer_auto_labels[name] = lbl
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 2)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 4)

        self._edge_cuts_check = wx.CheckBox(p, label="Sobreponer Edge.Cuts en todas las capas (guía de corte)")
        self._edge_cuts_check.SetValue(True)
        sizer.Add(self._edge_cuts_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self._combine_layers_check = wx.CheckBox(p, label="Combinar todas las capas en la misma hoja")
        self._combine_layers_check.SetValue(False)
        self._combine_layers_check.SetToolTip(
            "F.Cu, B.Cu, etc. se empacan juntas en una sola hoja "
            "en lugar de generar una hoja separada por capa."
        )
        sizer.Add(self._combine_layers_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        return sizer

    # ─────────────────────────────────────────────────────────────────────────
    # Sección 4: Hoja
    # ─────────────────────────────────────────────────────────────────────────

    def _build_sheet_section(self, p: "wx.Window") -> "wx.Sizer":
        box = wx.StaticBox(p, label="Hoja")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)

        row.Add(wx.StaticText(p, label="Tamaño:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self._sheet_choice = wx.Choice(p, choices=[lbl for _, lbl in _SHEET_SIZES])
        self._sheet_choice.SetSelection(0)
        self._sheet_choice.Bind(wx.EVT_CHOICE, self._on_sheet_changed)
        row.Add(self._sheet_choice, 0, wx.RIGHT, 20)

        row.Add(wx.StaticText(p, label="Margen:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self._margin_spin = wx.SpinCtrlDouble(p, value="5.0", min=0.0, max=50.0, inc=0.5)
        self._margin_spin.SetDigits(1)
        self._margin_spin.SetMinSize(wx.Size(72, -1))
        row.Add(self._margin_spin, 0, wx.RIGHT, 2)
        row.Add(wx.StaticText(p, label="mm"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

        row.Add(wx.StaticText(p, label="Separación:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self._spacing_spin = wx.SpinCtrlDouble(p, value="3.0", min=0.0, max=30.0, inc=0.5)
        self._spacing_spin.SetDigits(1)
        self._spacing_spin.SetMinSize(wx.Size(72, -1))
        row.Add(self._spacing_spin, 0, wx.RIGHT, 2)
        row.Add(wx.StaticText(p, label="mm"), 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(row, 0, wx.ALL, 6)

        self._custom_size_panel = wx.Panel(p)
        cs = wx.BoxSizer(wx.HORIZONTAL)
        cs.Add(wx.StaticText(self._custom_size_panel, label="Ancho:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self._custom_w = wx.SpinCtrlDouble(self._custom_size_panel, value="210.0", min=50.0, max=1200.0, inc=1.0)
        self._custom_w.SetDigits(1)
        cs.Add(self._custom_w, 0, wx.RIGHT, 2)
        cs.Add(wx.StaticText(self._custom_size_panel, label="mm"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)
        cs.Add(wx.StaticText(self._custom_size_panel, label="Alto:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self._custom_h = wx.SpinCtrlDouble(self._custom_size_panel, value="297.0", min=50.0, max=1200.0, inc=1.0)
        self._custom_h.SetDigits(1)
        cs.Add(self._custom_h, 0, wx.RIGHT, 2)
        cs.Add(wx.StaticText(self._custom_size_panel, label="mm"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._custom_size_panel.SetSizer(cs)
        self._custom_size_panel.Hide()
        sizer.Add(self._custom_size_panel, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self._rotation_check = wx.CheckBox(p, label="Permitir rotación de PCBs para mejor aprovechamiento")
        self._rotation_check.SetValue(True)
        sizer.Add(self._rotation_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        return sizer

    def _on_sheet_changed(self, _event) -> None:
        if not self._sheet_choice or not self._custom_size_panel:
            return
        is_custom = _SHEET_SIZES[self._sheet_choice.GetSelection()][0] == SheetSize.CUSTOM
        self._custom_size_panel.Show(is_custom)
        self._relayout()

    # ─────────────────────────────────────────────────────────────────────────
    # Sección 5: Salida
    # ─────────────────────────────────────────────────────────────────────────

    def _build_output_section(self, p: "wx.Window") -> "wx.Sizer":
        box = wx.StaticBox(p, label="Salida")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        fmt_row = wx.BoxSizer(wx.HORIZONTAL)
        self._fmt_pdf = wx.CheckBox(p, label="PDF")
        self._fmt_pdf.SetValue(True)
        self._fmt_svg = wx.CheckBox(p, label="SVG")
        self._fmt_svg.SetValue(True)
        self._fmt_png = wx.CheckBox(p, label="PNG")
        self._fmt_png.SetValue(False)
        self._fmt_png.Bind(wx.EVT_CHECKBOX, self._on_png_toggled)

        self._dpi_spin = wx.SpinCtrl(p, value="1200", min=300, max=2400)
        self._dpi_spin.SetMinSize(wx.Size(80, -1))
        self._dpi_spin.Enable(False)

        fmt_row.Add(self._fmt_pdf, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        fmt_row.Add(self._fmt_svg, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        fmt_row.Add(self._fmt_png, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        fmt_row.Add(self._dpi_spin, 0, wx.RIGHT, 4)
        fmt_row.Add(wx.StaticText(p, label="DPI"), 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(fmt_row, 0, wx.ALL, 6)

        dir_row = wx.BoxSizer(wx.HORIZONTAL)
        dir_row.Add(wx.StaticText(p, label="Carpeta:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self._out_dir = wx.DirPickerCtrl(
            p,
            path=self._default_out,
            message="Seleccionar carpeta de salida",
            style=wx.DIRP_USE_TEXTCTRL | wx.DIRP_SMALL,
        )
        dir_row.Add(self._out_dir, 1, wx.EXPAND)
        sizer.Add(dir_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        return sizer

    def _on_png_toggled(self, _event) -> None:
        if self._dpi_spin and self._fmt_png:
            self._dpi_spin.Enable(self._fmt_png.IsChecked())

    # ─────────────────────────────────────────────────────────────────────────
    # Vista previa inline
    # ─────────────────────────────────────────────────────────────────────────

    def _run_preview(self, fmt: "OutputFormat") -> None:
        """Genera en carpeta temporal y abre el archivo con el visor del sistema."""
        try:
            req = self.build_request()
        except Exception as exc:
            wx.MessageBox(str(exc), "Error en configuración", wx.OK | wx.ICON_ERROR, self._dialog)
            return

        if not req.pcbs:
            wx.MessageBox("Agrega al menos una PCB.", "Sin PCBs", wx.OK | wx.ICON_WARNING, self._dialog)
            return

        is_svg = fmt == OutputFormat.SVG
        btn = self._btn_prev_svg if is_svg else self._btn_prev_pdf
        orig_label = "Ver SVG ↗" if is_svg else "Ver PDF ↗"

        if btn:
            btn.SetLabel("Generando…")
            btn.Enable(False)
        if self._preview_status:
            self._preview_status.SetLabel("Generando vista previa…")

        def run_thread() -> None:
            try:
                import pcbnew  # noqa: F401 — falla rápido si no está disponible
            except ImportError:
                def _err():
                    if btn: btn.SetLabel(orig_label); btn.Enable(True)
                    if self._preview_status: self._preview_status.SetLabel("")
                    wx.MessageBox(
                        "pcbnew no disponible.\nEjecuta desde el plugin de KiCad.",
                        "Error", wx.OK | wx.ICON_ERROR, self._dialog,
                    )
                wx.CallAfter(_err)
                return

            try:
                from ..core.orchestrator import run

                tmp = tempfile.mkdtemp(prefix="kipanel_preview_")
                preview_req = PanelizeRequest(
                    pcbs=req.pcbs,
                    layers=req.layers,
                    method=req.method,
                    sheet=req.sheet,
                    output=OutputConfig(
                        formats=[fmt],
                        output_dir=Path(tmp),
                        png_dpi=req.output.png_dpi,
                        negative_colors=req.output.negative_colors,
                    ),
                )
                results = run(preview_req)

                paths: list[Path] = []
                for layer_res in results.values():
                    for page_files in layer_res.page_files.values():
                        for _f, fpath in page_files.items():
                            if fpath.exists():
                                paths.append(fpath)

                def _done() -> None:
                    if btn: btn.SetLabel(orig_label); btn.Enable(True)
                    if self._preview_status:
                        self._preview_status.SetLabel(
                            f"Listo: {len(paths)} archivo(s)." if paths else "Sin archivos generados."
                        )
                    for fp in paths:
                        _open_file(fp)

                wx.CallAfter(_done)

            except Exception as exc:
                def _err2() -> None:
                    if btn: btn.SetLabel(orig_label); btn.Enable(True)
                    if self._preview_status: self._preview_status.SetLabel("Error.")
                    wx.MessageBox(str(exc), "Error en vista previa", wx.OK | wx.ICON_ERROR, self._dialog)
                wx.CallAfter(_err2)

        threading.Thread(target=run_thread, daemon=True).start()
