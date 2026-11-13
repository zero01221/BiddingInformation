@echo off
chcp 65001 >nul
REM 铁塔招标信息 · Windows「安装环境」（一次性，仅首次使用需要）
REM 依赖装在项目内 .venv\，不污染系统 Python；全程只在本机运行，不依赖 mac。
setlocal
cd /d "%~dp0"

echo ========================================
echo   铁塔招标信息 · 一次性安装运行环境
echo ========================================
echo 工作目录：%CD%
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.9+：https://www.python.org/downloads/
    echo        安装时务必勾选 "Add Python to PATH"，装好后重新双击本脚本。
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 版本过低，需要 3.9 及以上（推荐 3.13）。
    pause
    exit /b 1
)
for /f "delims=" %%i in ('python --version') do echo 已找到 %%i
echo.

if exist ".venv\Scripts\python.exe" (
    echo [1/3] 已存在 .venv，跳过创建。
) else (
    echo [1/3] 正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确认 Python 安装完整（含 venv 模块）。
        pause
        exit /b 1
    )
)

echo [2/3] 正在安装运行依赖 ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败。国内网络可换镜像后重试：
    echo        .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo [3/3] 校验依赖是否可导入 ...
".venv\Scripts\python.exe" -c "import requests, yaml, bs4, lxml, tenacity" >nul 2>&1
if errorlevel 1 (
    echo [错误] 依赖安装后仍无法导入，请查看上方 pip 输出。
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成（只需做这一次）
echo ========================================
echo 以后每天只用两条命令，都在这一台 Windows 上完成：
echo   1) 双击「更新数据.bat」→ 抓取并生成 output\index.html
echo   2) 双击「查询.bat」→ 用浏览器打开页面看数据（零依赖）
echo 可选：双击「环境自检.bat」检查环境，或「试抓测试.bat」逐源试抓。
echo 只想看现有数据？直接双击「查询.bat」，不需要 Python、不需要联网。
pause
exit /b 0
