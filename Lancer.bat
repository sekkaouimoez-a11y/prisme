@echo off
cd /d "%~dp0"
uv run prisme.py
if errorlevel 1 pause
