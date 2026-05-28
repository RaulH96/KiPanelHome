"""
Composición de la hoja final a partir del PackResult.

Genera SVG (siempre, como formato intermedio), y opcionalmente convierte
a PDF y PNG.

Coordenadas: rectpack usa origen en esquina inferior-izquierda (y hacia arriba).
SVG usa origen en esquina superior-izquierda (y hacia abajo). El flip Y se
aplica en _write_composed_svg con: svg_y = sheet_h - rectpack_y - item_h.

Rotación: rotate(90) en SVG es CW visual (eje y apunta abajo).
  Transform para item rotado 90° CW:
    translate(dest_x + pcb_h, dest_y)  rotate(90)  scale(sx,sy)  translate(-bx,-by)
  Resultado: x ∈ [dest_x, dest_x+pcb_h], y ∈ [dest_y, dest_y+pcb_w]. ✓
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import json
import re
import copy
import shutil
import subprocess

from .packer import PackResult, PlacedItem
from .models import SheetConfig, OutputConfig, OutputFormat, TransferMethod

XLINK_NS = "http://www.w3.org/1999/xlink"


@dataclass
class CompositionResult:
    page_files: dict[int, dict[OutputFormat, Path]]  # page_num -> formato -> archivo
    manifest_path: Path


def compose_pages(
    pack_result: PackResult,
    sheet: SheetConfig,
    output: OutputConfig,
    method: TransferMethod,
    layer_name: str,
) -> CompositionResult:
    """
    Compone las hojas finales con los plots ya empacados.
    Genera un archivo por página y por formato solicitado.
    """
    output.output_dir.mkdir(parents=True, exist_ok=True)
    sheet_w, sheet_h = sheet.dimensions_mm()

    by_page: dict[int, list[PlacedItem]] = {}
    for item in pack_result.items:
        by_page.setdefault(item.page, []).append(item)

    page_files: dict[int, dict[OutputFormat, Path]] = {}
    safe_layer = layer_name.replace(".", "_")
    safe_method = method.value.replace("-", "")

    for page_num, items in sorted(by_page.items()):
        page_files[page_num] = {}

        svg_path = output.output_dir / (
            f"panel_{safe_layer}_{safe_method}_p{page_num}.svg"
        )
        _write_composed_svg(svg_path, items, sheet_w, sheet_h, output.negative_colors)
        if OutputFormat.SVG in output.formats:
            page_files[page_num][OutputFormat.SVG] = svg_path

        if OutputFormat.PDF in output.formats:
            pdf_path = svg_path.with_suffix(".pdf")
            try:
                _svg_to_pdf(svg_path, pdf_path)
                page_files[page_num][OutputFormat.PDF] = pdf_path
            except Exception as e:
                import warnings
                warnings.warn(f"PDF no generado: {e}")

        if OutputFormat.PNG in output.formats:
            png_path = svg_path.with_suffix(".png")
            try:
                _svg_to_png(svg_path, png_path, dpi=output.png_dpi)
                page_files[page_num][OutputFormat.PNG] = png_path
            except Exception as e:
                import warnings
                warnings.warn(f"PNG no generado: {e}")

        if OutputFormat.SVG not in output.formats and svg_path.exists():
            svg_path.unlink()

    manifest_path = output.output_dir / f"panel_manifest_{safe_layer}_{safe_method}.json"
    _write_manifest(manifest_path, pack_result, sheet, method, layer_name)

    return CompositionResult(page_files=page_files, manifest_path=manifest_path)


def _write_composed_svg(
    out_path: Path,
    items: list[PlacedItem],
    sheet_w_mm: float,
    sheet_h_mm: float,
    negative_colors: bool = False,
) -> None:
    """
    Compone el SVG de una hoja ensamblando los plots individuales.

    Cada plot se embebe en un <g> con transform que lo posiciona en la hoja.
    Para negative_colors, cada item se envuelve en clip+filter individuales
    (no fondo negro global) para no desperdiciar tinta fuera de las PCBs.
    """
    try:
        from lxml import etree  # type: ignore
    except ImportError:
        raise RuntimeError("lxml no instalado. `pip install lxml`")

    SVG_NS = "http://www.w3.org/2000/svg"

    root = etree.Element(
        f"{{{SVG_NS}}}svg",
        nsmap={None: SVG_NS, "xlink": XLINK_NS},
        attrib={
            "width": f"{sheet_w_mm}mm",
            "height": f"{sheet_h_mm}mm",
            "viewBox": f"0 0 {sheet_w_mm} {sheet_h_mm}",
        },
    )

    composite_defs = etree.SubElement(root, f"{{{SVG_NS}}}defs")

    # Fondo blanco de hoja (siempre blanco; el negro va solo dentro de cada PCB)
    etree.SubElement(
        root, f"{{{SVG_NS}}}rect",
        attrib={"x": "0", "y": "0",
                "width": str(sheet_w_mm), "height": str(sheet_h_mm),
                "fill": "white"},
    )

    for item_idx, item in enumerate(items):
        svg_file = item.plot.svg_path
        if not svg_file.exists():
            continue

        _parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
        src_tree = etree.parse(str(svg_file), _parser)
        src_root = src_tree.getroot()

        local_tag = src_root.tag.split("}")[-1] if "}" in src_root.tag else src_root.tag
        if local_tag != "svg":
            continue

        # --- viewBox y escala del SVG fuente ---
        vb_str = src_root.get("viewBox", "")
        if vb_str:
            vx, vy, vw, vh = [float(v) for v in vb_str.split()]
        else:
            vx, vy, vw, vh = 0.0, 0.0, item.width_mm, item.height_mm

        src_w = _parse_svg_dim(src_root.get("width"), vw)
        src_h = _parse_svg_dim(src_root.get("height"), vh)
        sx = src_w / vw if vw != 0.0 else 1.0
        sy = src_h / vh if vh != 0.0 else 1.0

        # --- Remapeo de IDs para evitar colisiones entre items ---
        id_prefix = f"ki{item_idx}_"
        id_remap: dict[str, str] = {
            node.get("id"): id_prefix + node.get("id")
            for node in src_root.iter()
            if node.get("id")
        }

        # --- Transform de posicionamiento ---
        #
        # Flip Y: rectpack y-up → SVG y-down: dest_y = sheet_h - y_rect - h_item
        #
        # No rotado:
        #   translate(dest_x, dest_y) scale(sx,sy) translate(-bx,-by)
        #   → content x ∈ [dest_x, dest_x+pcb_w], y ∈ [dest_y, dest_y+pcb_h]  ✓
        #
        # Rotado 90° CW visual (rotate(90) en SVG y-down):
        #   (x,y) → (-y, x)   ⟹   translate(dest_x+pcb_h, dest_y) rotate(90) scale(sx,sy) translate(-bx,-by)
        #   → content x ∈ [dest_x, dest_x+pcb_h], y ∈ [dest_y, dest_y+pcb_w]  ✓
        #
        # NOTA: rotate(-90) sería CCW visual y desplazaría el contenido fuera
        # de su slot. El bug de items "fuera de la hoja" era exactamente ese.

        pcb_w = item.plot.bbox_width_mm
        pcb_h = item.plot.bbox_height_mm

        # Cuando KiCad plotea con mirror=True, el contenido SVG aparece
        # reflejado en X respecto al centro de la página KiCad. La posición
        # física del board (board_x_mm) ya no coincide con la posición en el SVG.
        # Posición SVG de board mirrored = page_width_svg - board_x_mm - pcb_w
        # donde page_width_svg = vw (viewBox width, en unidades SVG = mm).
        if item.plot.mirrored:
            bx = vw - item.plot.board_x_mm - pcb_w
        else:
            bx = item.plot.board_x_mm
        by = item.plot.board_y_mm

        dest_x = item.x_mm
        if item.rotated:
            dest_y = sheet_h_mm - item.y_mm - item.width_mm
            tf = (
                f"translate({dest_x + pcb_h * sy:.6f},{dest_y:.6f}) "
                f"rotate(90) "
                f"scale({sx:.8f},{sy:.8f}) "
                f"translate({-bx:.6f},{-by:.6f})"
            )
            clip_w, clip_h = item.height_mm, item.width_mm   # dimensiones en output
        else:
            dest_y = sheet_h_mm - item.y_mm - item.height_mm
            tf = (
                f"translate({dest_x:.6f},{dest_y:.6f}) "
                f"scale({sx:.8f},{sy:.8f}) "
                f"translate({-bx:.6f},{-by:.6f})"
            )
            clip_w, clip_h = item.width_mm, item.height_mm

        # --- Fusionar defs del fuente en el composite ---
        src_defs_el = src_root.find(f"{{{SVG_NS}}}defs")
        if src_defs_el is not None:
            for def_child in src_defs_el:
                cloned = copy.deepcopy(def_child)
                _remap_ids_in_subtree(cloned, id_remap)
                composite_defs.append(cloned)

        # --- Añadir item al SVG ---
        # clipPath siempre activo: evita que el fondo de la página KiCad
        # se dibuje fuera del bounding box de la PCB y tape otras copias.
        clip_id = f"ki_clip_{item_idx}"
        clip_el = etree.SubElement(
            composite_defs, f"{{{SVG_NS}}}clipPath", attrib={"id": clip_id}
        )
        etree.SubElement(clip_el, f"{{{SVG_NS}}}rect", attrib={
            "x": f"{dest_x:.4f}", "y": f"{dest_y:.4f}",
            "width": f"{clip_w:.4f}", "height": f"{clip_h:.4f}",
        })
        outer = etree.SubElement(
            root, f"{{{SVG_NS}}}g",
            attrib={"clip-path": f"url(#{clip_id})"},
        )
        if negative_colors:
            # Black background rect so negative works even when KiCad SVG
            # has no explicit white page background within the PCB area.
            etree.SubElement(outer, f"{{{SVG_NS}}}rect", attrib={
                "x": f"{dest_x:.4f}", "y": f"{dest_y:.4f}",
                "width": f"{clip_w:.4f}", "height": f"{clip_h:.4f}",
                "fill": "#000000",
            })
        g = etree.SubElement(outer, f"{{{SVG_NS}}}g", attrib={"transform": tf})

        for child in src_root:
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local == "defs":
                continue
            cloned = copy.deepcopy(child)
            _remap_ids_in_subtree(cloned, id_remap)
            if negative_colors:
                _invert_svg_colors(cloned)
            g.append(cloned)

    out_path.write_bytes(
        etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    )


def _invert_svg_colors(elem) -> None:
    """Physically swap #000000↔#ffffff in all SVG color attributes (for negative mode)."""
    _BLACK = {"#000000", "#000", "black"}
    _WHITE = {"#ffffff", "#fff", "white"}
    for node in elem.iter():
        for attr in ("fill", "stroke", "color", "stop-color"):
            v = (node.get(attr) or "").strip()
            if v.lower() in _BLACK:
                node.set(attr, "#ffffff")
            elif v.lower() in _WHITE:
                node.set(attr, "#000000")
        style = node.get("style")
        if style:
            _S = "\x01"
            s = (style
                 .replace("#000000", _S).replace("#000", _S)
                 .replace("#ffffff", "#000000").replace("#fff", "#000000")
                 .replace(_S, "#ffffff"))
            node.set("style", s)


def _parse_svg_dim(val: str | None, fallback: float) -> float:
    if not val:
        return fallback
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", val.strip())
    return float(m.group(1)) if m else fallback


def _remap_ids_in_subtree(elem, id_remap: dict[str, str]) -> None:
    for node in elem.iter():
        node_id = node.get("id")
        if node_id and node_id in id_remap:
            node.set("id", id_remap[node_id])
        for attr in list(node.attrib):
            val = node.get(attr)
            if val and "url(#" in val:
                for old, new in id_remap.items():
                    val = val.replace(f"url(#{old})", f"url(#{new})")
                node.set(attr, val)
        for href_attr in ("href", f"{{{XLINK_NS}}}href"):
            href = node.get(href_attr)
            if href and href.startswith("#") and href[1:] in id_remap:
                node.set(href_attr, f"#{id_remap[href[1:]]}")


def _find_inkscape() -> str | None:
    """Busca Inkscape en PATH y en rutas comunes de Windows/Linux."""
    if (p := shutil.which("inkscape")):
        return p
    for candidate in [
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
        "/usr/bin/inkscape",
        "/usr/local/bin/inkscape",
        "/Applications/Inkscape.app/Contents/MacOS/inkscape",
    ]:
        if Path(candidate).exists():
            return candidate
    return None


def _find_browser() -> str | None:
    """Busca Edge o Chrome (para conversión headless SVG→PDF/PNG)."""
    for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if (p := shutil.which(name)):
            return p
    for candidate in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]:
        if Path(candidate).exists():
            return candidate
    return None


def _svg_to_pdf_via_browser(svg_path: Path, pdf_path: Path, browser: str) -> None:
    """Convierte SVG→PDF usando Edge/Chrome en modo headless."""
    import tempfile

    svg_text = svg_path.read_text(encoding="utf-8")

    # Extraer dimensiones del SVG para el @page CSS
    w_m = re.search(r'<svg[^>]+\bwidth="([^"]+)"', svg_text)
    h_m = re.search(r'<svg[^>]+\bheight="([^"]+)"', svg_text)
    page_w = w_m.group(1) if w_m else "210mm"
    page_h = h_m.group(1) if h_m else "297mm"

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        f"*{{margin:0;padding:0}}@page{{size:{page_w} {page_h};margin:0}}"
        f"html,body{{width:{page_w};height:{page_h};overflow:hidden}}"
        "svg{display:block;width:100%;height:100%}"
        f"</style></head><body>{svg_text}</body></html>"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = Path(f.name)

    try:
        r = subprocess.run(
            [
                browser,
                "--headless", "--disable-gpu",
                f"--print-to-pdf={pdf_path.resolve()}",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                html_path.resolve().as_uri(),
            ],
            capture_output=True,
            timeout=60,
        )
        if not pdf_path.exists():
            raise RuntimeError(
                f"El browser no generó PDF (rc={r.returncode}): "
                f"{r.stderr.decode(errors='replace')[:300]}"
            )
    finally:
        html_path.unlink(missing_ok=True)


def _svg_to_pdf(svg_path: Path, pdf_path: Path) -> None:
    """Convierte SVG→PDF. Intenta cairosvg → Inkscape → Edge/Chrome headless."""
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return
    except Exception:
        pass

    inkscape = _find_inkscape()
    if inkscape:
        r = subprocess.run(
            [inkscape, "--export-type=pdf", f"--export-filename={pdf_path}", str(svg_path)],
            capture_output=True, timeout=120,
        )
        if r.returncode == 0 and pdf_path.exists():
            return

    browser = _find_browser()
    if browser:
        _svg_to_pdf_via_browser(svg_path, pdf_path, browser)
        return

    raise RuntimeError(
        "No se pudo convertir SVG→PDF.\n"
        "Instala Inkscape (inkscape.org) o cairosvg:\n"
        "  pip install cairosvg"
    )


def _svg_to_png(svg_path: Path, png_path: Path, dpi: int) -> None:
    """Convierte SVG→PNG. Intenta cairosvg → Inkscape."""
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), dpi=dpi)
        return
    except Exception:
        pass

    inkscape = _find_inkscape()
    if inkscape:
        r = subprocess.run(
            [inkscape, "--export-type=png", f"--export-dpi={dpi}",
             f"--export-filename={png_path}", str(svg_path)],
            capture_output=True, timeout=120,
        )
        if r.returncode == 0 and png_path.exists():
            return

    raise RuntimeError(
        "No se pudo convertir SVG→PNG.\n"
        "Instala Inkscape (inkscape.org) o cairosvg:\n"
        "  pip install cairosvg"
    )


def _write_manifest(
    path: Path,
    pack_result: PackResult,
    sheet: SheetConfig,
    method: TransferMethod,
    layer_name: str,
) -> None:
    data = {
        "layer": layer_name,
        "method": method.value,
        "sheet": {
            "size": sheet.size.value,
            "dimensions_mm": list(sheet.dimensions_mm()),
            "margin_mm": sheet.margin_mm,
            "spacing_mm": sheet.spacing_mm,
        },
        "pages": pack_result.pages,
        "items": [
            {
                "page": it.page,
                "pcb": it.plot.pcb_path.name,
                "layer": it.plot.layer_name,
                "mirrored": it.plot.mirrored,
                "x_mm": round(it.x_mm, 3),
                "y_mm": round(it.y_mm, 3),
                "width_mm": round(it.width_mm, 3),
                "height_mm": round(it.height_mm, 3),
                "rotated": it.rotated,
            }
            for it in pack_result.items
        ],
        "overflow": [
            {"pcb": o.pcb_path.name, "layer": o.layer_name}
            for o in pack_result.overflow
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
