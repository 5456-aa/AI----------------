@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用 DSH 自带的 Python 运行时（自带 numpy/pandas/sklearn/jieba），
rem 系统 python 版本太老会缺库。
set "PYEXE="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
    set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
if not defined PYEXE set "PYEXE=python"

"%PYEXE%" %*
