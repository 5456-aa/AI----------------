@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

start "" http://localhost:8501
"%PYEXE%" -m streamlit run ui\app.py --server.port 8501 --browser.gatherUsageStats false
pause
