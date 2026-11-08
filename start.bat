@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  DocuMind could not be started. See the error above.
  echo ============================================================
  echo.
  pause
)
endlocal
