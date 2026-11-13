@echo off
REM ==================================================================
REM 【可选：Windows 备用入口】
REM 本项目主方案已改为「一台 mac 本地闭环」，全部运行时动作只在同一台 mac 上完成：
REM   安装环境.command（一次性）→ 更新数据.command（抓取并生成）→ 查询.command（查看）
REM mac 本地方案请用 更新数据.command / 查询.command，不需要本脚本、
REM 不需要同步盘，也不需要第二台机器。
REM 本脚本仅为 Windows 备用入口保留，行为不变；不运行它不影响任何功能。
REM ==================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo    铁塔招标信息 · 每日更新（Windows 生产端）
echo ========================================
echo.

REM 可选的国内同步目录：设环境变量 BIDDING_SYNC_DIR，或在配置 publish.sync_dir 中指定。
REM 例如：set BIDDING_SYNC_DIR=D:\Nutstore\BiddingInformation\output
set "SYNC_DIR=%BIDDING_SYNC_DIR%"

REM 选择 Python 解释器：优先项目内虚拟环境，否则用系统 Python。
set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo 使用解释器: %PY%

REM 若未设环境变量，则回退读取配置 publish.sync_dir（消费 Config.get_publish_config）。
REM 用 usebackq 反引号执行，避免与 Python -c 内部引号冲突。
if "%SYNC_DIR%"=="" (
    for /f "usebackq delims=" %%i in (`%PY% -c "from scripts.bidding_scraper.config import Config; print(Config.load().get_publish_config()['sync_dir'])" 2^>nul`) do set "SYNC_DIR=%%i"
)
if not "%SYNC_DIR%"=="" echo 同步目录: %SYNC_DIR%
echo.

REM ------------------------------------------------------------------
REM 1. 采集 + 处理 + 落库 + 导出 + 构建（一步完成，原子写产物）
REM ------------------------------------------------------------------
echo [1/4] 正在采集并生成离线页面...
"%PY%" -m scripts.bidding_scraper.main
if errorlevel 1 (
    echo [告警] 采集/构建返回非零。产物采用原子写，上一版文件已保留，本地仍可使用。
) else (
    echo [完成] output\index.html、data.json、RSS 与各平台快照包已生成。
)

if not exist "output\index.html" (
    echo [错误] output\index.html 不存在且无上一版可保留，请检查 Python 环境与日志。
    pause
    exit /b 1
)
echo.

REM ------------------------------------------------------------------
REM 2. 研发侧版本托管：失败仅告警，绝不阻断离线产物
REM ------------------------------------------------------------------
echo [2/4] 提交并推送到研发侧仓库（失败仅告警）...
git add output/ >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "自动更新招标数据 (%date% %time%)" >nul 2>&1
    echo 已创建本地提交。
) else (
    echo 没有新数据需要提交，跳过 commit。
)
git push origin master
if errorlevel 1 (
    echo [告警] Git 推送失败（网络或权限）。离线产物与同步目录照常可用，不阻断。
) else (
    echo 推送成功。
)
echo.

REM ------------------------------------------------------------------
REM 3. 复制到国内零成本文件通道（同步盘 / 文件传输 / 局域网 / U 盘）
REM ------------------------------------------------------------------
echo [3/4] 复制到同步目录...
if "%SYNC_DIR%"=="" (
    echo 未设置 BIDDING_SYNC_DIR，跳过复制。
    echo 如需自动同步，请先设置该环境变量指向同步盘中的 output 目录。
) else (
    if not exist "%SYNC_DIR%" mkdir "%SYNC_DIR%" >nul 2>&1
    xcopy /Y /E /I "output\*" "%SYNC_DIR%\" >nul
    if errorlevel 1 (
        echo [告警] 同步目录复制失败，请检查路径：%SYNC_DIR%
    ) else (
        echo 已复制到 %SYNC_DIR%
    )
)
echo.

REM ------------------------------------------------------------------
REM 4. 完成提示
REM ------------------------------------------------------------------
echo [4/4] 完成。
echo ========================================
echo  产物：output\index.html（数据已内联，双击即用）
echo  提示：Windows 备用入口可独立使用；mac 本地方案请用「更新数据」与「查询」两条命令。
echo  数据截至时间见页面顶部；终端访问全程不需要在线托管。
echo ========================================
echo.
echo 按任意键退出...
pause >nul
endlocal
