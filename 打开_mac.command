#!/bin/bash
# 铁塔招标信息 · macOS 一键打开
# 零依赖：只调用系统自带的 open，不调用 python、不联网、不修改任何数据。
# 首次使用若提示没有权限，请在「终端」执行：chmod +x 打开_mac.command
# 若被 Gatekeeper 拦截：在 Finder 中右键本文件 → 打开 → 再点「打开」。
# 最稳妥的方式仍是直接双击 output/index.html。

cd "$(dirname "$0")" || exit 1

if [ -f "./output/index.html" ]; then
    open "./output/index.html"
    echo "已用默认浏览器打开 output/index.html（离线页面，数据已内联）。"
    echo "页面顶部显示「数据更新时间 / 数据截至」；如提示数据过期，请从 Windows 端或同步盘覆盖本文件后刷新。"
else
    echo "[错误] 未找到 ./output/index.html，请确认 output 目录完整。"
    exit 1
fi
