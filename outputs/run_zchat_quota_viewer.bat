@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  python zchat_quota_viewer.py
  exit /b %errorlevel%
)

set "CODEX_PY=C:\Users\Fagu_y\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" (
  "%CODEX_PY%" zchat_quota_viewer.py
  exit /b %errorlevel%
)

echo Python was not found. Please install Python or run this script inside Codex's bundled runtime.
pause
