#!/bin/bash
# 铁塔招标信息 · macOS「安装环境」（一次性，仅首次使用需要）
# ---------------------------------------------------------------------------
# 用户许可的「一点简单环境」：Python 3 + pip install -r requirements.txt。
# 依赖装在项目内 .venv/（已被 .gitignore 忽略），不污染系统 Python。
# 全程只在本机 mac 上执行，不需要第二台机器、不需要同步盘、不需要 VPN。
#
# 首次使用若提示没有权限：在「终端」执行 chmod +x 安装环境.command
# 若被 Gatekeeper 拦截：Finder 中右键本文件 → 打开 → 再点「打开」。
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

pause_if_interactive() {
    echo ""
    if [ -t 0 ]; then
        read -n 1 -s -r -p "按任意键关闭窗口…" || true
        echo ""
    fi
}

echo "========================================"
echo "  铁塔招标信息 · 一次性安装运行环境"
echo "========================================"
echo "工作目录：$(pwd)"
echo ""

# 1. 找 python3。
if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未找到 python3，请先安装 Python 3："
    echo "  方式一：到 Python 官网 python.org 下载 macOS 安装包（.pkg），双击安装。"
    echo "  方式二：已装 Homebrew 时，在终端执行：brew install python3"
    echo "装好后重新双击本脚本。"
    pause_if_interactive
    exit 1
fi

PY3=$(command -v python3)
if ! "$PY3" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    echo "[错误] Python 版本过低，需要 3.9 及以上（推荐 3.13）。"
    echo "当前版本：$("$PY3" --version 2>&1)"
    echo "请到 python.org 下载新版 macOS 安装包，或执行 brew upgrade python3 后重试。"
    pause_if_interactive
    exit 1
fi
echo "已找到 Python：$PY3 ($("$PY3" --version 2>&1))"
echo ""

# 2. 创建项目内虚拟环境。
if [ -d "./.venv" ]; then
    echo "[1/3] 已存在 .venv，跳过创建。"
else
    echo "[1/3] 正在创建虚拟环境 .venv …"
    if ! "$PY3" -m venv .venv; then
        echo "[错误] 创建虚拟环境失败。常见原因：Python 安装不完整（缺 venv 模块）。"
        echo "        建议从 python.org 安装官方 pkg 后重试。"
        pause_if_interactive
        exit 1
    fi
fi

VENV_PY="./.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "[错误] .venv 不完整（缺少 .venv/bin/python）。"
    echo "        请在「终端」执行 rm -rf .venv 后重新双击本脚本。"
    pause_if_interactive
    exit 1
fi

# 3. 安装 requirements.txt 中的全部运行时依赖。
echo "[2/3] 正在安装运行依赖 …"
if ! "$VENV_PY" -m pip install --disable-pip-version-check --upgrade pip >/dev/null 2>&1; then
    echo "[提示] pip 升级跳过（不影响依赖安装），继续。"
fi

if ! "$VENV_PY" -m pip install --disable-pip-version-check -r requirements.txt; then
    echo ""
    echo "[错误] 依赖安装失败。常见原因：网络不可达 / 公司代理拦截。"
    echo "        可在终端里先 cd 到本目录，再手动重试："
    echo "        ./.venv/bin/python -m pip install -r requirements.txt"
    echo "        国内网络可加镜像源，例如："
    echo "        ./.venv/bin/python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
    pause_if_interactive
    exit 1
fi

# 4. 安装后自检，确保五个库都能导入。
echo "[3/3] 校验依赖是否可导入 …"
if ! "$VENV_PY" -c "import requests, yaml, bs4, lxml, tenacity" >/dev/null 2>&1; then
    echo "[错误] 依赖安装后仍无法导入，请查看上方 pip 输出并重试。"
    pause_if_interactive
    exit 1
fi

echo ""
echo "========================================"
echo "  安装完成（只需做这一次）"
echo "========================================"
echo "以后每天只用两条命令，都在这一台 mac 上完成："
echo "  1) 双击「更新数据.command」→ 抓取并生成 output/index.html"
echo "  2) 双击「查询.command」→ 用浏览器打开页面看数据（零依赖）"
echo "可选：双击「安装每日更新.command」启用每天 08:00 自动更新（默认不开）。"
echo "只想看现有数据？直接双击「查询.command」，完全不需要本脚本。"
pause_if_interactive
exit 0
