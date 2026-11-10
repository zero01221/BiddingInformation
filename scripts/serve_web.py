#!/usr/bin/env python
# coding=utf-8
"""本地预览服务（仅 Windows 调试用）+ 静态 HTML 构建薄封装。

生成职责已整体移交 ``scripts/bidding_scraper/builder.py``：
- 删除旧版动态模板、``:315-322`` 公告类型筛选控件；
- 删除 ``:447,461`` 不安全的未转义直接内联（XSS）；
- 本文件不再读取 DB 拼 HTML，只转调安全构建器。

用法::

    python scripts/serve_web.py --output output/index.html   # 生成静态页
    python scripts/serve_web.py                              # 本地预览 output/ 目录
"""

import argparse
import os
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bidding_scraper.builder import build as builder_build  # noqa: E402
from scripts.bidding_scraper.builder import validate_html  # noqa: E402
from scripts.bidding_scraper.config import Config, resolve_project_path  # noqa: E402
from scripts.bidding_scraper.database import Database  # noqa: E402
from scripts.bidding_scraper.exporter import Exporter  # noqa: E402

PORT = 8080


class QuietHandler(SimpleHTTPRequestHandler):
    """安静的静态文件处理器（避免每次请求刷屏）。"""

    def log_message(self, fmt: str, *args) -> None:
        """仅记录错误，不打印正常访问日志。"""
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            super().log_message(fmt, *args)


def build_html(output_path: str = "", days: int = 7) -> str:
    """生成静态 HTML 文件（数据已安全内联，无需服务器）。

    Args:
        output_path: 输出路径；为空时只返回 HTML 字符串。
        days: 兼容旧签名保留；**不再截断**，始终导出数据库全量历史。

    Returns:
        完整 HTML 字符串。
    """
    Config.load()
    db = Database()
    export = Exporter().export(db)
    meta = dict(export["meta"])
    meta["source_health"] = export["source_health"]
    # days 仅保留参数兼容，历史全量入库后一律全量导出（旧版 limit=100 已修）
    html = builder_build(export["items"], meta)
    validate_html(html, {"items": export["items"]})

    if output_path:
        target = resolve_project_path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(html, encoding="utf-8")
        os.replace(str(tmp), str(target))
        print(f"  静态 HTML 已生成: {target} ({len(export['items'])} 条数据)")
    return html


def main() -> None:
    """CLI 入口：生成静态页或启动本地预览服务。"""
    parser = argparse.ArgumentParser(description="铁塔招标信息本地预览 / 静态构建薄封装")
    parser.add_argument("--output", "-o", help="生成静态 HTML 到指定路径")
    parser.add_argument("--days", type=int, default=7, help="兼容参数，已不再截断数据")
    parser.add_argument("--port", type=int, default=PORT, help="本地预览端口（默认 8080）")
    args = parser.parse_args()

    if args.output:
        build_html(args.output, args.days)
        return

    output_dir = ROOT / "output"
    index = output_dir / "index.html"
    print("\n  铁塔招标信息 · 本地预览（仅 Windows 调试）")
    print(f"  产物目录: {output_dir}")
    print(f"  访问地址: http://127.0.0.1:{args.port}/index.html")
    if not index.exists():
        print("  [提示] 尚无 index.html，请先运行: python scripts/serve_web.py --output output/index.html")
    print("  按 Ctrl+C 停止\n")

    handler = partial(QuietHandler, directory=str(output_dir))
    server = HTTPServer(("127.0.0.1", args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务器已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
