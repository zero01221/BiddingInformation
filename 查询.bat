@echo off
chcp 65001 >nul
REM 铁塔招标信息 · Windows「查询」（只读，零依赖）
REM 只打开本机 output\index.html；不抓取、不联网、不调用 Python、不改数据。
setlocal
cd /d "%~dp0"

if not exist "output\index.html" (
    echo [错误] 未找到 output\index.html。
    echo        请在同一台 Windows 上双击「更新数据.bat」生成产物。
    pause
    exit /b 1
)

start "" "output\index.html"
echo 已用默认浏览器打开 output\index.html（离线页面，数据已内联，file:// 零外部请求）。
exit /b 0
