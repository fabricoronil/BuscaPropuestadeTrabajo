@echo off
REM ── Botón local: doble clic = extraer + subir a GitHub ──
cd /d "%~dp0"
python deploy.py
echo.
pause
