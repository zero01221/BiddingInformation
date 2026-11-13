@echo off
chcp 65001 >nul
REM 铁塔招标信息 · Windows「试抓测试」（逐源真实联网试抓，只读）
REM 真实请求各启用数据源并报告每源取回条数；不写数据库、不写任何产物。
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ========================================
echo   铁塔招标信息 · 逐源真实试抓（只读）
echo ========================================
echo 会真实联网请求各数据源，可能需要几分钟；不会写入数据库或产物。
echo 若某个源返回 0 条或报错，页面仍可用历史数据，不影响其它源。
echo.
"%PY%" -m scripts.bidding_scraper.doctor --probe
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%
