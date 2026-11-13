@echo off
chcp 65001 >nul
REM 铁塔招标信息 · Windows「环境自检」（只读，不写库、不写产物）
REM 双击 = 检查 Python / 依赖 / 配置 / 数据库 / 产物 / 各源站点连通性。
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ========================================
echo   铁塔招标信息 · 环境与抓取自检
echo ========================================
echo 本检查只读，不会改动数据库与页面产物。
echo 想逐源真实试抓（仍不写库），请双击「试抓测试.bat」。
echo.
"%PY%" -m scripts.bidding_scraper.doctor
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%
