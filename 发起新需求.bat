@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

start "" http://localhost:8503
"%PYEXE%" -m streamlit run ui\new_batch.py --server.port 8503 --browser.gatherUsageStats false
pause
