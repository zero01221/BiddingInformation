#!/bin/bash
# 铁塔招标信息 · macOS「试抓测试」（逐源真实联网试抓，只读）
# 真实请求各启用数据源并报告每源取回条数；不写数据库、不写任何产物。
# 用于在新 mac 上验证国内站点直连可达、抓取链路完整。
cd "$(dirname "$0")" || exit 1

pause_if_interactive() {
    echo ""
    if [ -t 0 ]; then
        read -n 1 -s -r -p "按任意键关闭窗口…" || true
        echo ""
    fi
}

PY=""
if [ -x "./.venv/bin/python" ]; then
    PY="./.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

if [ -z "$PY" ]; then
    echo "[错误] 没有找到 Python 3。请先双击「安装环境.command」。"
    pause_if_interactive
    exit 1
fi

echo "========================================"
echo "  铁塔招标信息 · 逐源真实试抓（只读）"
echo "========================================"
echo "会真实联网请求各数据源，可能需要几分钟；不会写入数据库或产物。"
echo "若某个源返回 0 条或报错，页面仍可用历史数据，不影响其它源。"
echo ""
"$PY" -m scripts.bidding_scraper.doctor --probe
RC=$?
pause_if_interactive
exit "$RC"
