#!/bin/bash
# 铁塔招标信息 · macOS「查询」（兼容别名，只读，零依赖）
# ---------------------------------------------------------------------------
# 与「查询.command」内容等价，保留本文件名以兼容旧书签 / 旧说明。
# 职责：只用系统自带的 open 打开本机 output/index.html。
# 不抓取、不联网、不调用 python、不安装任何东西、不修改任何数据。
# 数据由同一台 mac 上的「更新数据.command」生成，两个命令职责完全分离。
#
# 首次使用若提示没有权限，请在「终端」执行：chmod +x 打开_mac.command
# 若被 Gatekeeper 拦截：在 Finder 中右键本文件 → 打开 → 再点「打开」。
# 最稳妥的方式仍是直接双击 output/index.html。
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

pause_if_interactive() {
    echo ""
    if [ -t 0 ]; then
        read -n 1 -s -r -p "按任意键关闭窗口…" || true
        echo ""
    fi
}

if [ -f "./output/index.html" ]; then
    open "./output/index.html"
    echo "已用默认浏览器打开 output/index.html（离线页面，数据已内联，file:// 零外部请求）。"
    echo "页面顶部显示「数据更新时间 / 数据截至」；如提示数据过期，请双击「更新数据」后刷新本页。"
else
    echo "[错误] 未找到 ./output/index.html。"
    echo "       请在同一台 mac 上依次双击「安装环境.command」和「更新数据.command」生成产物。"
    pause_if_interactive
    exit 1
fi

pause_if_interactive
