@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYEXE=python"
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo.
echo ============================================================
echo   启动在线标注 + 公网隧道
echo   等 15 秒左右，下面会出现一个 https://xxx.trycloudflare.com
echo   把这个地址发给队友，他们在任何网络都能打开
echo ============================================================
echo.

start "streamlit-8504" /min "%PYEXE%" -m streamlit run ui\label_multi.py --server.port 8504 --server.address 0.0.0.0 --browser.gatherUsageStats false
timeout /t 12 /nobreak >nul

echo 正在建立隧道，请稍候...
echo.
tools\cloudflared.exe tunnel --no-autoupdate --url http://localhost:8504

echo.
echo 隧道已断开。按任意键关闭。
pause
