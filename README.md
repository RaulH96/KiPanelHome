# KiPanelHome

KiCad plugin + herramienta standalone para imprimir múltiples PCBs en una sola hoja a escala 1:1, optimizando el aprovechamiento de papel/acetato para fabricación casera de PCBs.

> **¿Qué tiene de diferente vs KiKit?**
> KiKit es paneling profesional (tabs, mouse bites, V-cuts) para enviar a un fab. KiPanelHome es para imprimir en casa: apila varias PCBs en una hoja A4/Carta/A3 con el espejado correcto según el método de transferencia. Ambas herramientas coexisten sin conflicto.

## Características

- **Bin-packing 2D automático** — coloca el mayor número de copias posible en cada hoja
- **Escala 1:1 garantizada** — nunca reescala, el SVG/PDF sale listo para imprimir
- **Espejado correcto por método**:
  - *Toner transfer (planchado)*: F.Cu espejada, B.Cu normal
  - *Film UV Convención A* (emulsión hacia el cobre, recomendado): igual que planchado
  - *Film UV Convención B* (emulsión hacia arriba): F.Cu normal, B.Cu espejada
  - *Custom*: override manual por capa
- **Modo negativo** para fotorresist negativo (inversión física de colores en SVG)
- **Salida**: PDF, SVG y PNG por capa, una hoja por página si no caben todas
- **Funciona como plugin de KiCad o como herramienta standalone**

## Instalación

### 1. Dependencias Python

```bash
pip install rectpack lxml wxPython
```

> `pcbnew` viene con KiCad, no se instala con pip.
> `cairosvg` es opcional: en Linux/Mac simplifica la conversión a PDF/PNG (`pip install cairosvg`). En Windows se usa Edge/Chrome headless automáticamente.

### 2a. Como plugin de KiCad (recomendado)

```bash
git clone https://github.com/raulmaster/KiPanelHome
cd KiPanelHome
python install_plugin.py
```

El script detecta la versión de KiCad instalada y copia el paquete a la carpeta correcta.

Rutas manuales si prefieres copiar a mano:
- **Windows**: `%APPDATA%\kicad\<version>\scripting\plugins\`
- **Linux**: `~/.config/kicad/<version>/scripting/plugins/`
- **macOS**: `~/Library/Preferences/kicad/<version>/scripting/plugins/`

Luego en KiCad: **Tools → External Plugins → Refresh → KiPanelHome**

### 2b. Standalone en Windows (sin abrir KiCad)

```batch
run_kicad.bat
```

Detecta el Python de KiCad y abre la interfaz gráfica directamente.

### 2c. CLI

```bash
python -m kipanelh.wrappers.cli \
    --pcb mi_placa.kicad_pcb:4 \
    --layers F.Cu,B.Cu \
    --method toner-transfer \
    --sheet A4 --margin 5 --spacing 3 \
    --formats pdf,svg \
    --output ./output/
```

Sintaxis `archivo.kicad_pcb:N` indica N copias de esa PCB.

## Uso desde el plugin

1. Abre una PCB en KiCad
2. **Tools → External Plugins → KiPanelHome**
3. Configura:
   - PCBs a panelizar y número de copias
   - Método de fabricación (toner / film UV / custom)
   - Capas a procesar (F.Cu, B.Cu, SilkS, Mask…)
   - Tamaño de hoja, márgenes y separación entre placas
   - Formato de salida (PDF / SVG / PNG)
4. **Ver SVG ↗** o **Ver PDF ↗** para previsualizar
5. **Generar** para guardar los archivos finales

## Conversión PDF/PNG — por plataforma

| Plataforma | Opción automática | Alternativa |
|---|---|---|
| **Windows** | Edge headless | Instalar Inkscape |
| **Linux** | `pip install cairosvg` | Chromium headless / Inkscape |
| **macOS** | `pip install cairosvg` | Chrome/Edge headless / Inkscape |

## Reglas de espejado (resumen técnico)

KiCad plotea B.Cu desde la vista superior (ya espejada en X). Por eso:

| Método | F.Cu | B.Cu |
|---|---|---|
| Toner Transfer | **espejada** | normal |
| Film UV Conv. A | **espejada** | normal |
| Film UV Conv. B | normal | **espejada** |

Las reglas están validadas con tests unitarios en `tests/test_methods.py`. Si modificas `methods.py`, corre los tests primero — un espejado incorrecto arruina las PCBs.

```bash
python -m pytest tests/
```

## Estructura del proyecto

```
kipanelh/
├── core/
│   ├── models.py       — dataclasses de configuración
│   ├── methods.py      — reglas de espejado por método
│   ├── plotter.py      — generación SVG via pcbnew
│   ├── packer.py       — bin-packing 2D (rectpack)
│   ├── composer.py     — composición SVG/PDF/PNG final
│   └── orchestrator.py — pipeline completo
├── ui/
│   └── main_dialog.py  — interfaz wxPython
└── wrappers/
    ├── cli.py              — CLI (argparse)
    └── kicad_plugin.py     — ActionPlugin de KiCad
install_plugin.py           — instalador automático
run_kicad.bat               — lanzador standalone Windows
run_ui.py                   — entry point UI standalone
```

## Licencia

GPL v3 — Copyright (C) 2026 Luis Raúl Heredia de la Cruz

Libre para usar, modificar y distribuir. Cualquier distribución del código
(modificado o no) debe mantener el código fuente abierto bajo la misma licencia.
Ver [LICENSE](LICENSE) para el texto completo.
