"""
Sistema de internacionalización simple basado en diccionario.
Sin dependencias externas. Idioma por defecto: español.
"""
from __future__ import annotations
import json
from pathlib import Path

_LANG: str = "es"

_CONFIG_PATH: Path = (
    Path.home() / "AppData" / "Roaming" / "kipanelh" / "config.json"
    if __import__("platform").system() == "Windows"
    else Path.home() / ".config" / "kipanelh" / "config.json"
)

STRINGS: dict[str, dict[str, str]] = {
    "es": {
        # Diálogo principal
        "dlg_title": "KiPanelHome",

        # Secciones
        "sec_pcbs":   "PCBs a panelizar",
        "sec_method": "Método de fabricación",
        "sec_layers": "Capas a procesar",
        "sec_sheet":  "Hoja",
        "sec_output": "Salida",

        # Sección PCBs
        "col_file":   "Archivo",
        "col_copies": "Copias",
        "col_label":  "Etiqueta",
        "btn_add":    "Agregar…",
        "btn_remove": "Eliminar",
        "btn_edit":   "Editar copias…",

        # Diálogo editar PCB
        "edit_copies": "Copias:",
        "edit_label":  "Etiqueta:",

        # Sección capas
        "hdr_layer":  "Capa",
        "hdr_mirror": "Espejado",
        "hdr_copies": "Copias",
        "total_label":         "(total: {})",
        "layer_copies_tip":    "Copias de esta capa. Se sincroniza con el total de PCBs.",
        "edge_cuts_overlay":   "Sobreponer Edge.Cuts en todas las capas (guía de corte)",
        "combine_layers":      "Combinar todas las capas en la misma hoja",
        "combine_layers_tip":  "F.Cu, B.Cu, etc. se empacan juntas en una sola hoja en lugar de generar una hoja separada por capa.",

        # Métodos
        "method_toner":  "Toner Transfer (planchado)",
        "method_film":   "Film UV",
        "method_custom": "Custom",
        "method_toner_desc": (
            "Planchado: imprime en papel couché/fotográfico, plancha boca-abajo. "
            "F.Cu espejada, B.Cu normal."
        ),
        "method_film_desc": (
            "Film UV — Convención A (emulsión hacia el cobre): acetato boca-abajo "
            "tocando la placa. Mejor contacto, sin difracción. "
            "F.Cu espejada, B.Cu normal (igual que planchado)."
        ),
        "method_film_b_desc": (
            "Film UV — Convención B (emulsión hacia arriba): cara limpia del acetato "
            "toca la placa. Mayor difracción. F.Cu normal, B.Cu espejada."
        ),
        "method_custom_desc": "Custom: el usuario define espejado por capa manualmente.",

        # Film UV
        "film_uv_box":   "Convención de contacto (Film UV)",
        "film_a_label":  "Convención A — emulsión/tinta hacia el cobre  (recomendado)",
        "film_a_desc":   "El acetato se voltea boca-abajo: la tinta toca directamente la placa.\nMejor contacto, sin difracción. Espejado igual que Toner Transfer.",
        "film_b_label":  "Convención B — emulsión/tinta hacia arriba",
        "film_b_desc":   "La cara limpia del acetato toca la placa; la tinta queda arriba.\nMayor difracción. Espejado opuesto: F.Cu normal, B.Cu espejada.",
        "negative_label": "Negativo (invertir colores: trazas blancas, fondo negro)",
        "negative_note":  "  ← para fotorresist negativo",
        "negative_tip":   "Activa solo si usas fotorresist NEGATIVO (poco común en casa).\nCon fotorresist POSITIVO (el más común) deja esta opción desmarcada.",

        # Hoja
        "sheet_size":     "Tamaño:",
        "sheet_margin":   "Margen:",
        "sheet_spacing":  "Separación:",
        "sheet_width":    "Ancho:",
        "sheet_height":   "Alto:",
        "sheet_rotation": "Permitir rotación de PCBs para mejor aprovechamiento",
        "sheet_mm":       "mm",
        "sheet_letter":   "Carta (Letter)",
        "sheet_custom":   "Personalizada",
        "folder_picker_msg": "Seleccionar carpeta de salida",

        # Salida
        "out_folder": "Carpeta:",
        "out_dpi":    "DPI",

        # Botones principales
        "btn_preview_svg": "Ver SVG ↗",
        "btn_preview_pdf": "Ver PDF ↗",
        "btn_generate":    "Generar",
        "btn_cancel":      "Cancelar",
        "btn_about":       "Acerca de…",

        # Estados de vista previa
        "prev_generating": "Generando vista previa…",
        "prev_ready":      "Listo: {} archivo(s).",
        "prev_none":       "Sin archivos generados.",
        "prev_error":      "Error.",

        # Mensajes de error / aviso
        "err_config":        "Error en configuración",
        "err_preview":       "Error en vista previa",
        "warn_no_pcbs":      "Agrega al menos una PCB.",
        "warn_no_pcbs_title":"Sin PCBs",
        "err_no_pcbnew":     "pcbnew no disponible.\nEjecuta desde el plugin de KiCad.",
        "err_title":         "Error",

        # About
        "about_title":   "Acerca de KiPanelHome",
        "about_version": "Versión 0.1",
        "about_desc":    "Herramienta para panelizar múltiples PCBs\nen una sola hoja para fabricación casera.",
        "about_author":  "Autor:",
        "about_license": "Licencia:",
        "about_github":  "GitHub:",
        "about_lang":    "Idioma / Language:",
        "btn_close":     "Cerrar",
    },

    "en": {
        # Main dialog
        "dlg_title": "KiPanelHome",

        # Sections
        "sec_pcbs":   "PCBs to panelize",
        "sec_method": "Manufacturing method",
        "sec_layers": "Layers to process",
        "sec_sheet":  "Sheet",
        "sec_output": "Output",

        # PCB section
        "col_file":   "File",
        "col_copies": "Copies",
        "col_label":  "Label",
        "btn_add":    "Add…",
        "btn_remove": "Remove",
        "btn_edit":   "Edit copies…",

        # Edit PCB dialog
        "edit_copies": "Copies:",
        "edit_label":  "Label:",

        # Layer section
        "hdr_layer":  "Layer",
        "hdr_mirror": "Mirrored",
        "hdr_copies": "Copies",
        "total_label":        "(total: {})",
        "layer_copies_tip":   "Copies of this layer. Synced with total PCB count.",
        "edge_cuts_overlay":  "Overlay Edge.Cuts on all layers (cut guide)",
        "combine_layers":     "Combine all layers on the same sheet",
        "combine_layers_tip": "F.Cu, B.Cu, etc. are packed together on one sheet instead of a separate sheet per layer.",

        # Methods
        "method_toner":  "Toner Transfer (ironing)",
        "method_film":   "UV Film",
        "method_custom": "Custom",
        "method_toner_desc": (
            "Ironing: print on coated/photo paper, iron face-down. "
            "F.Cu mirrored, B.Cu normal."
        ),
        "method_film_desc": (
            "UV Film — Convention A (emulsion toward copper): acetate face-down "
            "touching the board. Better contact, no diffraction. "
            "F.Cu mirrored, B.Cu normal (same as toner transfer)."
        ),
        "method_film_b_desc": (
            "UV Film — Convention B (emulsion facing up): clean side of acetate "
            "touches the board. More diffraction. F.Cu normal, B.Cu mirrored."
        ),
        "method_custom_desc": "Custom: user defines mirroring per layer manually.",

        # UV Film
        "film_uv_box":   "Contact convention (UV Film)",
        "film_a_label":  "Convention A — emulsion/ink toward copper  (recommended)",
        "film_a_desc":   "Acetate is flipped face-down: ink touches the board directly.\nBetter contact, no diffraction. Same mirroring as Toner Transfer.",
        "film_b_label":  "Convention B — emulsion/ink facing up",
        "film_b_desc":   "The clean side of the acetate touches the board; ink faces up.\nMore diffraction. Opposite mirroring: F.Cu normal, B.Cu mirrored.",
        "negative_label": "Negative (invert colors: white traces, black background)",
        "negative_note":  "  ← for negative photoresist",
        "negative_tip":   "Enable only if using NEGATIVE photoresist (uncommon for home use).\nWith POSITIVE photoresist (most common) leave this unchecked.",

        # Sheet
        "sheet_size":     "Size:",
        "sheet_margin":   "Margin:",
        "sheet_spacing":  "Spacing:",
        "sheet_width":    "Width:",
        "sheet_height":   "Height:",
        "sheet_rotation": "Allow PCB rotation for better packing",
        "sheet_mm":       "mm",
        "sheet_letter":   "Letter",
        "sheet_custom":   "Custom",
        "folder_picker_msg": "Select output folder",

        # Output
        "out_folder": "Folder:",
        "out_dpi":    "DPI",

        # Main buttons
        "btn_preview_svg": "Preview SVG ↗",
        "btn_preview_pdf": "Preview PDF ↗",
        "btn_generate":    "Generate",
        "btn_cancel":      "Cancel",
        "btn_about":       "About…",

        # Preview status
        "prev_generating": "Generating preview…",
        "prev_ready":      "Done: {} file(s).",
        "prev_none":       "No files generated.",
        "prev_error":      "Error.",

        # Error / warning messages
        "err_config":         "Configuration error",
        "err_preview":        "Preview error",
        "warn_no_pcbs":       "Add at least one PCB.",
        "warn_no_pcbs_title": "No PCBs",
        "err_no_pcbnew":      "pcbnew not available.\nRun from the KiCad plugin.",
        "err_title":          "Error",

        # About
        "about_title":   "About KiPanelHome",
        "about_version": "Version 0.1",
        "about_desc":    "Tool to panelize multiple PCBs\nonto a single sheet for home manufacturing.",
        "about_author":  "Author:",
        "about_license": "License:",
        "about_github":  "GitHub:",
        "about_lang":    "Language / Idioma:",
        "btn_close":     "Close",
    },
}


def t(key: str) -> str:
    """Devuelve el string traducido al idioma activo."""
    return STRINGS.get(_LANG, STRINGS["es"]).get(key, key)


def current_lang() -> str:
    return _LANG


def set_lang(lang: str) -> None:
    global _LANG
    if lang in STRINGS:
        _LANG = lang
        _save_config()


def load_config() -> None:
    """Carga el idioma guardado al inicio."""
    global _LANG
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            lang = data.get("lang", "es")
            if lang in STRINGS:
                _LANG = lang
    except Exception:
        pass


def _save_config() -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(
            json.dumps({"lang": _LANG}, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# Cargar preferencia guardada al importar el módulo
load_config()
