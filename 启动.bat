@echo off
chcp 65001 >nul
title 每日记事本 - 启动
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 系统里找不到 python。
    echo.
    echo 请先安装 Python 3.10 或更高版本：
    echo     https://www.python.org/downloads/windows/
    echo 安装时务必勾选  "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import tkinter" 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 当前 Python 缺少 tkinter 图形组件。
    echo 请不要用 Microsoft Store 版本，改用官网安装包重装。
    echo.
    pause
    exit /b 1
)

echo 正在启动 每日记事本 ...
python main.py
if errorlevel 1 (
    echo.
    echo [提示] 程序异常退出，请把上面的报错内容截图反馈。
    pause
)
