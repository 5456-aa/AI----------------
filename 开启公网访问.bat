@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

REM public demo mode: hide the API-key settings panel
set "PUBLIC_DEMO=1"

echo.
echo  ============================================================
echo   PUBLIC DEMO MODE
echo.
echo   This starts the local services in read-only mode and
echo   opens two Cloudflare quick tunnels (no account needed).
echo.
echo   Requirements: internet + this computer stays on.
echo  ============================================================
echo.

echo [1/3] Starting services (public mode) ...
start "AI-Opp Home 8500" cmd /c "set PUBLIC_DEMO=1&&"%PYEXE%" -m streamlit run ui\home.py --server.port 8500 --server.address 0.0.0.0 --browser.gatherUsageStats false"
timeout /t 4 >nul
start "AI-Opp Dashboard 8501" cmd /c "set PUBLIC_DEMO=1&&"%PYEXE%" -m streamlit run ui\app.py --server.port 8501 --server.address 0.0.0.0 --browser.gatherUsageStats false"
timeout /t 6 >nul

echo [2/3] Opening tunnels ...
echo [3/3] Waiting for public URLs ...
echo.

"%PYEXE%" scripts\serve_public.py

echo.
echo Public demo stopped.
pause
