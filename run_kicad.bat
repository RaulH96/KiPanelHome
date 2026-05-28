
@echo off
setlocal enabledelayedexpansion

:: Buscar python.exe de KiCad en ubicaciones estándar
set KICAD_PY=

for %%V in (10.0 9.0 8.0 7.0) do (
    for %%B in (
        "%LOCALAPPDATA%\Programs\KiCad\%%V\bin\python.exe"
        "%PROGRAMFILES%\KiCad\%%V\bin\python.exe"
        "%PROGRAMFILES(X86)%\KiCad\%%V\bin\python.exe"
    ) do (
        if exist %%B (
            if "!KICAD_PY!"=="" set KICAD_PY=%%B
        )
    )
)

if "!KICAD_PY!"=="" (
    echo No se encontro el Python de KiCad.
    echo Instala KiCad o edita este archivo para poner la ruta correcta.
    echo Rutas buscadas:
    echo   %%LOCALAPPDATA%%\Programs\KiCad\{version}\bin\python.exe
    echo   %%PROGRAMFILES%%\KiCad\{version}\bin\python.exe
    pause
    exit /b 1
)

echo Usando: !KICAD_PY!
!KICAD_PY! "%~dp0run_ui.py"
if errorlevel 1 pause
endlocal
