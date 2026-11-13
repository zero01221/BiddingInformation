@echo off
chcp 65001 >nul
REM 铁塔招标信息 · Windows「更新数据」（唯一会联网、会写数据的入口）
REM 职责分离：本脚本只抓取 + 处理 + 落库 + 生成本地产物；
REM 不推送仓库、不复制到同步盘、不打开页面、不依赖 mac 或第二台机器。
setlocal
cd /d "%~dp0"

echo ========================================
echo   铁塔招标信息 · 更新数据（仅本机 Windows）
echo ========================================
echo 说明：只在本机采集并生成产物，不上传、不同步、不跨系统。
echo.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -c "import requests, yaml, bs4, lxml, tenacity" >nul 2>&1
if errorlevel 1 (
    echo [错误] 缺少运行依赖，请先双击「安装环境.bat」。
    echo        也可在终端执行：pip install -r requirements.txt
    pause
    exit /b 1
)

echo 使用解释器：%PY%
echo [1/1] 正在采集并生成离线页面，请稍候（视网络可能需要几分钟）...
echo.
"%PY%" -m scripts.bidding_scraper.main
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo [失败] 本次采集失败，已保留上一版产物（产物采用原子写，上一版未被破坏）。
    echo        常见原因：网络临时不通 / 数据源站点维护 / 依赖异常；请稍后重试。
) else (
    echo [完成] 已在本机生成：
    echo        output\index.html（数据已内联，双击即用）
    echo        output\data.json、output\bidding_feed.xml
    echo        output\win\ 与 output\mac\ 平台离线包
    echo        现在双击「查询.bat」查看；页面顶部「数据截至」会同步更新。
)
echo.
pause
exit /b 0
