@echo off
rem MobiWeave 上位机 · 一键启动
rem 双击本文件即可；也可以把日志路径拖到本文件上（会直接打开）。
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [失败] 没找到 python。请先装 Python 3.10+ 并勾选 "Add python.exe to PATH"。
    echo        官网：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 正在启动 MobiWeave 上位机……
python app.py %*
if errorlevel 1 (
    echo.
    echo [失败] 启动出错，把上面的红字发给我。
    pause
)
