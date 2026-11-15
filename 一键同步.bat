@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo.
echo  ============================================================
echo   Sync local changes to GitHub (cloud app rebuilds itself)
echo.
echo   1. shows what changed
echo   2. smoke-tests the real cloud entry (streamlit_app.py)
echo   3. checks for leaked keys
echo   4. commits and pushes if everything is fine
echo  ============================================================
echo.

set "MSG=%~1"
if "%MSG%"=="" set "MSG=同步更新"

"%PYEXE%" scripts\sync_check.py --commit "%MSG%" --push

echo.
echo  Done. Streamlit Cloud rebuilds in 1-2 minutes.
echo  Open https://adr123456.streamlit.app and click Reboot if needed.
echo.
pause
