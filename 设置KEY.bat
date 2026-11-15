@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

rem 自动打开申请页，省一步
start "" "https://platform.deepseek.com/api_keys"

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

"%PYEXE%" scripts\setup_key.py
echo.
pause
