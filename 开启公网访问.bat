@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "CF=tools\cloudflared.exe"

if not exist "%CF%" (
  echo [ERROR] tools\cloudflared.exe not found.
  echo Download from https://github.com/cloudflare/cloudflared/releases
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   PUBLIC DEMO - single link
echo.
echo   Step 1: start the app in another window (run 启动系统.bat)
echo   Step 2: this window opens a tunnel and prints ONE url
echo.
echo   Requirements: internet + this computer stays on.
echo  ============================================================
echo.

echo [1/2] Checking local service on port 8500 ...
curl -s -o nul -w "" http://127.0.0.1:8500/_stcore/health
if errorlevel 1 (
  echo [ERROR] port 8500 not responding. Run 启动系统.bat first.
  pause
  exit /b 1
)
echo       OK

echo [2/2] Opening tunnel ...
echo.
"%PYEXE%" scripts\serve_public.py

pause
