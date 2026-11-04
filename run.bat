@echo off
rem Double-click to run Sketchmaker on Windows. Same as: uv run run.py
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
uv run "%~dp0run.py" %*
if errorlevel 1 pause
