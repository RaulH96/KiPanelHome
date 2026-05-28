"""
Instala KiPanelHome como plugin de KiCad (Tools -> External Plugins).

Uso:
    python install_plugin.py          # instala para la version de KiCad detectada
    python install_plugin.py --list   # muestra rutas encontradas sin instalar
"""
import sys
import shutil
import argparse
from pathlib import Path

APPDATA = Path.home() / "AppData" / "Roaming"
VERSIONS = ["10.0", "9.0", "8.0", "7.0"]

PLUGIN_ENTRY = '''\
"""KiPanelHome plugin entry point — generado por install_plugin.py"""
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
from kipanelh.wrappers.kicad_plugin import KiPanelHomePlugin
KiPanelHomePlugin().register()
'''


def find_plugin_dirs() -> list[Path]:
    dirs = []
    for ver in VERSIONS:
        # Buscar si existe la carpeta de configuracion de esa version de KiCad
        kicad_ver_dir = APPDATA / "kicad" / ver
        if kicad_ver_dir.exists():
            dirs.append(kicad_ver_dir / "scripting" / "plugins")
    return dirs


def install(plugin_src: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    pkg_dst = target_dir / "kipanelh"

    if pkg_dst.exists():
        shutil.rmtree(pkg_dst)
    shutil.copytree(plugin_src / "kipanelh", pkg_dst)

    entry = target_dir / "kipanelhome_plugin.py"
    entry.write_text(PLUGIN_ENTRY, encoding="utf-8")

    print(f"Plugin instalado en: {target_dir}")
    print(f"  Paquete : {pkg_dst}")
    print(f"  Entrada : {entry}")
    print()
    print("Reinicia KiCad y ve a:")
    print("  Tools -> External Plugins -> Refresh   (o simplemente abrelo)")
    print("  Luego: Tools -> External Plugins -> KiPanelHome")


def main() -> None:
    parser = argparse.ArgumentParser(description="Instala KiPanelHome en KiCad")
    parser.add_argument("--list", action="store_true", help="Solo listar rutas sin instalar")
    args = parser.parse_args()

    plugin_src = Path(__file__).parent

    dirs = find_plugin_dirs()
    if not dirs:
        print("No se encontro ninguna instalacion de KiCad en:")
        for ver in VERSIONS:
            print(f"  {APPDATA / 'kicad' / ver / 'scripting' / 'plugins'}")
        sys.exit(1)

    if args.list:
        print("Directorios de plugins encontrados:")
        for d in dirs:
            print(f"  {d}  {'(existe)' if d.exists() else '(se creara)'}")
        return

    print(f"Encontradas {len(dirs)} instalacion(es) de KiCad:")
    for i, d in enumerate(dirs):
        ver = d.parts[-3]
        print(f"  [{i}] KiCad {ver}  ->  {d}")

    if len(dirs) == 1:
        choice = 0
    else:
        raw = input("Elige numero (Enter = primera): ").strip()
        choice = int(raw) if raw else 0

    install(plugin_src, dirs[choice])


if __name__ == "__main__":
    main()
