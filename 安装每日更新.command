#!/bin/bash
# 铁塔招标信息 · macOS「安装每日更新」（可选增强，默认不启用）
# ---------------------------------------------------------------------------
# 只有主动双击本脚本时才会安装 launchd 定时任务；不双击就完全不会自动运行。
# 任务每天 08:00 在本机执行「更新数据.command」，依旧只在这一台 mac 上完成。
# 模板 mac/每日自动更新.plist 中的 {{PROJECT_DIR}} 由本脚本替换为真实绝对路径，
# 不硬编码任何机器上的盘符路径。
#
# 首次使用若提示没有权限：在「终端」执行 chmod +x 安装每日更新.command
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
echo "  铁塔招标信息 · 安装每日自动更新（可选）"
echo "========================================"

PROJECT_DIR=$(pwd -P) || exit 1
TEMPLATE="$PROJECT_DIR/mac/每日自动更新.plist"
LABEL="com.biddinginformation.dailyupdate"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
ENTRY="$PROJECT_DIR/更新数据.command"

if [ ! -f "$TEMPLATE" ]; then
    echo "[错误] 缺少模板文件：$TEMPLATE"
    pause_if_interactive
    exit 1
fi

if [ ! -f "$ENTRY" ]; then
    echo "[错误] 缺少更新入口：$ENTRY"
    echo "        请先确认仓库完整，再双击「安装环境.command」与「更新数据.command」。"
    pause_if_interactive
    exit 1
fi

if ! mkdir -p "$HOME/Library/LaunchAgents"; then
    echo "[错误] 无法创建目录：$HOME/Library/LaunchAgents"
    pause_if_interactive
    exit 1
fi

# 转义 sed 替换串中的特殊字符，保证含空格 / 反斜杠的路径也能正确替换。
ESCAPED_DIR=$(printf '%s' "$PROJECT_DIR" | sed -e 's/[\\&|]/\\&/g')
if ! sed -e "s|{{PROJECT_DIR}}|${ESCAPED_DIR}|g" "$TEMPLATE" > "$TARGET"; then
    echo "[错误] 生成 launchd 配置失败：$TARGET"
    pause_if_interactive
    exit 1
fi

if ! plutil -lint "$TARGET" >/dev/null 2>&1; then
    echo "[错误] 生成的 plist 校验失败：$TARGET"
    echo "        请检查模板 mac/每日自动更新.plist 是否完整。"
    pause_if_interactive
    exit 1
fi

echo "已生成：$TARGET"
echo "执行入口：$ENTRY"
echo ""

# 卸载旧任务再加载，保证重复运行本脚本不会叠加多个定时任务。
launchctl unload "$TARGET" >/dev/null 2>&1 || true
if launchctl load -w "$TARGET" >/dev/null 2>&1; then
    echo "[完成] 已启用每天 08:00 的本地自动更新（默认不启用，是你主动安装的）。"
else
    echo "[提示] launchctl load 未自动生效，可在「终端」手动执行："
    echo "       launchctl load -w $TARGET"
fi

echo ""
echo "查看状态：launchctl list | grep biddinginformation"
echo "关闭自动更新：launchctl unload -w $TARGET"
echo "卸载配置：rm $TARGET"
echo "日志：output/launchd.out.log 与 output/launchd.err.log"
pause_if_interactive
exit 0
