@echo off
chcp 65001 >nul
title 每日记事本 - 修复快捷方式图标
cd /d "%~dp0"

echo ============================================
echo   修复「每日记事本」快捷方式图标
echo ============================================
echo.
echo 作用：把桌面和本目录的快捷方式重建，图标指向
echo       assets\icon.ico（最新版），并刷新 Windows 图标缓存。
echo.

if not exist "%~dp0assets\icon.ico" (
    echo [错误] 找不到 assets\icon.ico
    echo 请确认本脚本与 main.py、assets 文件夹在同一目录。
    echo.
    pause
    exit /b 1
)

set "ICO=%~dp0assets\icon.ico"
set "APP=%~dp0main.py"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
    for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYW set "PYW=%%i"
)

echo [1/3] 重建桌面快捷方式...
set "DESK=%USERPROFILE%\Desktop"
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$lnk = '%DESK%\每日记事本.lnk';" ^
  "$s = $ws.CreateShortcut($lnk);" ^
  "$s.TargetPath = '%PYW%';" ^
  "$s.Arguments = '\"%APP%\"';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%ICO%,0';" ^
  "$s.Description = '每日记事本';" ^
  "$s.Save();" ^
  "Write-Host '  已写入：' $lnk"

echo [2/3] 重建本目录快捷方式...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$lnk = '%~dp0每日记事本.lnk';" ^
  "$s = $ws.CreateShortcut($lnk);" ^
  "$s.TargetPath = '%PYW%';" ^
  "$s.Arguments = '\"%APP%\"';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%ICO%,0';" ^
  "$s.Save();" ^
  "Write-Host '  已写入：' $lnk"

echo [3/3] 刷新 Windows 图标缓存...
ie4uinit.exe -show >nul 2>nul

echo.
echo ============================================
echo   完成！
echo   如果桌面图标仍是旧的，按以下任一方式刷新：
echo     1. 在桌面按 F5
echo     2. 任务管理器 - 找到「Windows 资源管理器」- 右键「重新启动」
echo     3. 注销后重新登录
echo ============================================
echo.
pause
