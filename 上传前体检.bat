@echo off
chcp 65001 >nul
title 每日记事本 - 上传前体检
cd /d "%~dp0"

echo ============================================
echo   上传 GitHub 前的体检
echo ============================================
echo.

if not exist ".git" (
    echo [提示] 还没有初始化 git。首次上传请先执行：
    echo     git init
    echo     git branch -M main
    echo.
)

where git >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 git，请先安装：https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

echo [检查 1] 隐私文件是否被正确排除...
git add -A >nul 2>nul
git status --porcelain > "%TEMP%\dn_status.txt"
findstr /C:"data/" "%TEMP%\dn_status.txt" >nul 2>nul
if not errorlevel 1 (
    echo   [危险] data/ 出现在待上传列表里！
    echo   说明 .gitignore 没有生效，请勿继续上传。
    echo   请确认项目根目录有 .gitignore 且包含一行： data/
    echo.
    pause
    exit /b 1
)
echo   [通过] data/ 已被排除（不会上传你的真实任务数据）
echo.

echo [检查 2] dist / build / 缓存 是否被排除...
findstr /C:"__pycache__" /C:"dist/" /C:"build/" "%TEMP%\dn_status.txt" >nul 2>nul
if not errorlevel 1 (
    echo   [警告] 发现缓存或打包产物，建议检查 .gitignore
) else (
    echo   [通过]
)
echo.

echo [检查 3] 关键文件是否齐全...
for %%f in ("main.py" "parser.py" "i18n.py" "README.md" ".gitignore") do (
    if exist "%%~f" (
        echo   [有] %%~f
    ) else (
        echo   [缺失] %%~f  ^<-- 请补齐后再上传
    )
)
echo.

echo [检查 4] 本次将上传的文件数量...
for /f %%c in ('git status --porcelain ^| find /c /v ""') do set CNT=%%c
echo   待提交变更：%CNT% 项
echo.
echo ============================================
echo   体检完成。全部 [通过] 即可继续上传。
echo   下一步（首次上传）：
echo     git commit -m "feat: 首次提交"
echo     git remote add origin https://github.com/你的用户名/daily-notebook.git
echo     git push -u origin main
echo ============================================
echo.
pause
