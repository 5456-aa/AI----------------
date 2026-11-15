@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo.
echo  ============================================================
echo   Starting all services (3 windows will open)
echo.
echo     Home        http://localhost:8500
echo     Dashboard   http://localhost:8501
echo     QA          http://localhost:8505
echo.
echo   LAN access:   http://%COMPUTERNAME%:8500
echo   Public demo:  run  开启公网访问.bat  (needs internet)
echo  ============================================================
echo.

start "AI-Opp Home 8500" cmd /c ""%PYEXE%" -m streamlit run ui\home.py --server.port 8500 --server.address 0.0.0.0 --browser.gatherUsageStats false"
timeout /t 3 >nul
start "AI-Opp Dashboard 8501" cmd /c ""%PYEXE%" -m streamlit run ui\app.py --server.port 8501 --server.address 0.0.0.0 --browser.gatherUsageStats false"
timeout /t 3 >nul
start "AI-Opp QA 8505" cmd /c ""%PYEXE%" -m streamlit run ui\qa.py --server.port 8505 --server.address 0.0.0.0 --browser.gatherUsageStats false"
timeout /t 5 >nul

start "" http://localhost:8500

echo.
echo  All three services started in separate windows.
echo  Close those windows to stop them.
echo.
pause
