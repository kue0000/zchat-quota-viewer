@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON=python"
) else (
  set "PYTHON=C:\Users\Fagu_y\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

"%PYTHON%" -m pip install -r requirements-build.txt
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name ZchatQuotaViewer ^
  outputs\zchat_quota_viewer.py

echo.
echo Build finished: dist\ZchatQuotaViewer.exe
pause
