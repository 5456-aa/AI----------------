@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo.
echo  ============================================================
echo   AI opportunity system - single app
echo.
echo   Open:  http://localhost:8500
echo          (left sidebar: Home / Dashboard / QA)
echo.
echo   LAN:   http://%COMPUTERNAME%:8500
echo   Public: run  开启公网访问.bat
echo  ============================================================
echo.

start "" http://localhost:8500
"%PYEXE%" -m streamlit run ui\main.py --server.port 8500 --server.address 0.0.0.0 --browser.gatherUsageStats false
pause
