@echo off
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul && goto lancer
echo Premier lancement : installation de uv, qui installera Python et pywebview...
powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
:lancer
uv run prisme.py
if errorlevel 1 pause
