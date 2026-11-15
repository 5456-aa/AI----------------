@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo.
echo  Local:   http://localhost:8504
echo  LAN:     http://%COMPUTERNAME%:8504  (teammates use this)
echo.
start "" http://localhost:8504
"%PYEXE%" -m streamlit run ui\label_multi.py --server.port 8504 --server.address 0.0.0.0 --browser.gatherUsageStats false
pause
