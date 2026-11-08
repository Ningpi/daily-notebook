@echo off
chcp 65001 >nul
title 每日记事本 - 打包为 EXE
cd /d "%~dp0"

echo ============================================
echo   每日记事本 - 一键打包为 Windows EXE
echo ============================================
echo.
echo 需要：Python 3.10+（安装时勾选 Add to PATH）、联网
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python。
    echo 请安装 Python 3.10+ 并勾选 "Add python.exe to PATH"：
    echo     https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

python -c "import tkinter" 2>nul
if errorlevel 1 (
    echo [错误] 当前 Python 缺少 tkinter，请到 python.org 重装完整版。
    echo.
    pause
    exit /b 1
)

echo [1/2] 安装 / 更新 PyInstaller（首次需要联网，请稍等）...
python -m pip install --upgrade pyinstaller -q
if errorlevel 1 (
    echo.
    echo [错误] PyInstaller 安装失败，请检查网络后重试。
    echo 如果公司网络有限制，可先执行：
    echo     python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    pause
    exit /b 1
)

echo [2/2] 正在打包，约需 1~3 分钟...
python -m PyInstaller --noconfirm --clean "每日记事本.spec"
if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上方报错截图反馈。
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   打包完成！
echo   EXE 位置：dist\DailyNotebook.exe
echo   双击即可运行；右键可发送到桌面快捷方式。
echo ============================================
echo.
explorer dist
pause
