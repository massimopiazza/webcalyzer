@echo off
setlocal

set "REPO_ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%scripts\launch_webcalyzer.ps1"
set "STATUS=%ERRORLEVEL%"

if not "%STATUS%"=="0" (
  echo.
  echo Launch failed.
  pause
)

exit /b %STATUS%
