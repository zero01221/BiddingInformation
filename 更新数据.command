#!/bin/bash
# 铁塔招标信息 · macOS「更新数据」（职责：抓取 → 处理 → 落库 → 生成产物）
# ---------------------------------------------------------------------------
# 本方案完全在同一台 mac 上运行，不需要第二台机器、不需要同步盘、不需要 VPN。
# 本脚本不上传产物到远端、不复制到任何同步目录、不改动版本库。
# 依赖由「安装环境.command」一次性装到项目内 .venv；依赖缺失时给出可操作的中文指引。
#
# 首次使用若提示没有权限：在「终端」执行 chmod +x 更新数据.command
# 若被 Gatekeeper 拦截：Finder 中右键本文件 → 打开 → 再点「打开」。
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

# 双击 .command 时终端窗口会有 tty；被 launchd 调用时没有，跳过等待以免挂住。
pause_if_interactive() {
    echo ""
    if [ -t 0 ]; then
        read -n 1 -s -r -p "按任意键关闭窗口…" || true
        echo ""
    fi
}

echo "========================================"
echo "  铁塔招标信息 · 更新数据（仅本机 mac）"
echo "========================================"
echo "工作目录：$(pwd)"
echo ""

# 1. 选择 Python：优先项目内 .venv，其次 python3，最后 python。
PY=""
if [ -x "./.venv/bin/python" ]; then
    PY="./.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

if [ -z "$PY" ]; then
    echo "[错误] 没有找到 Python 3，无法更新数据。"
    echo "请先安装 Python 3（任选一种，一次性即可）："
    echo "  方式一：到 Python 官网 python.org 下载 macOS 安装包（.pkg），双击安装。"
    echo "  方式二：已装 Homebrew 时，在终端执行：brew install python3"
    echo "装好后依次双击「安装环境.command」和「更新数据.command」。"
    echo "（只想查看现有数据：直接双击「查询.command」，零依赖、不需要 Python。）"
    pause_if_interactive
    exit 1
fi

echo "使用解释器：$PY ($("$PY" --version 2>&1))"

# 2. 版本校验：requirements.txt 中的依赖需要 Python 3.9 及以上。
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    echo "[错误] Python 版本过低，需要 3.9 及以上（推荐 3.13）。"
    echo "请到 python.org 下载新版 macOS 安装包，或执行 brew upgrade python3。"
    pause_if_interactive
    exit 1
fi

# 3. 依赖校验：五个运行时库必须齐全，缺任意一个都明确提示，绝不静默失败。
if ! "$PY" -c "import requests, yaml, bs4, lxml, tenacity" >/dev/null 2>&1; then
    echo "[错误] 缺少运行依赖（requests / PyYAML / beautifulsoup4 / lxml / tenacity）。"
    if [ ! -d "./.venv" ]; then
        echo "首次运行请先执行「安装环境.command」，它会自动创建 .venv 并安装全部依赖。"
    fi
    echo "也可在「终端」里手动执行："
    echo "    pip3 install -r requirements.txt"
    echo "或创建虚拟环境后执行："
    echo "    python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt"
    pause_if_interactive
    exit 1
fi

# 4. 真实抓取并生成全部产物（国内站点 mac 直连可达，不需要 VPN）。
echo "[1/1] 正在采集并生成离线页面，请稍候（视网络可能需要几分钟）…"
echo ""
"$PY" -m scripts.bidding_scraper.main
STATUS=$?
echo ""

if [ "$STATUS" -ne 0 ]; then
    echo "[失败] 本次采集失败，已保留上一版产物。"
    echo "       产物采用原子写，上一版 output/index.html 未被破坏，仍可正常查询。"
    echo "       常见原因：网络临时不通 / 数据源站点维护 / 依赖异常；请稍后重试。"
else
    echo "[完成] 已在本机生成："
    echo "       output/index.html（数据已内联，双击即用）"
    echo "       output/data.json、output/bidding_feed.xml"
    echo "       output/win/ 与 output/mac/ 平台离线包"
    echo "现在双击「查询.command」查看最新数据；页面顶部「数据截至」会同步更新。"
fi

pause_if_interactive
exit "$STATUS"
