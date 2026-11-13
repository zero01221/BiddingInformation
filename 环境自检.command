#!/bin/bash
# 铁塔招标信息 · macOS「环境自检」（只读，不写库、不写产物）
# 检查 Python / 依赖 / 配置 / 数据库 / 产物 / 各源站点连通性，
# 用一行命令判断这台 mac 能否正常抓取。
# 首次使用若提示没有权限：终端执行 chmod +x 环境自检.command
# 若被 Gatekeeper 拦截：Finder 右键 → 打开 → 再点「打开」。
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
    echo "[错误] 没有找到 Python 3。请先双击「安装环境.command」，"
    echo "        或到 python.org 下载 macOS 安装包（.pkg）双击安装。"
    pause_if_interactive
    exit 1
fi

echo "========================================"
echo "  铁塔招标信息 · 环境与抓取自检（只读）"
echo "========================================"
echo "本检查只读，不会改动数据库与页面产物。"
echo "想逐源真实试抓（仍不写库），请双击「试抓测试.command」。"
echo ""
"$PY" -m scripts.bidding_scraper.doctor
RC=$?
pause_if_interactive
exit "$RC"
