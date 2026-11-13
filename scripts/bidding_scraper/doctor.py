"""环境与抓取自检（doctor）——只读，不写数据库、不写产物。

两个模式，mac 与 Windows 通用：::

    python -m scripts.bidding_scraper.doctor           # 环境 + 站点连通性
    python -m scripts.bidding_scraper.doctor --probe    # 追加逐源真实试抓

设计目的：在真实机器上（尤其是 mac）一行命令判断「能否正常抓取」，
把结论落到可复现的检查项上，而不是凭开发环境推测。
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

REQUIRED_MODULES = ("requests", "yaml", "bs4", "lxml", "tenacity")
URL_KEYS = ("base_url", "api_url", "search_url", "detail_page_url")

OK, FAIL, WARN = "[通过]", "[失败]", "[注意]"


def _line(status: str, label: str, detail: str = "") -> bool:
    """打印一条检查结论，返回是否通过。"""
    print(f"{status} {label}" + (f" — {detail}" if detail else ""))
    return status == OK


def check_python() -> bool:
    version = sys.version_info
    ok = version >= (3, 9)
    return _line(
        OK if ok else FAIL,
        f"Python 版本 {version.major}.{version.minor}.{version.micro}",
        "满足 3.9+ 要求" if ok else "需要 3.9 及以上，请安装新版 Python 3",
    )


def check_dependencies() -> bool:
    missing = []
    versions = []
    for name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(name)
            versions.append(f"{name}={getattr(module, '__version__', 'ok')}")
        except ImportError as exc:
            missing.append(f"{name}({exc.name})")
    if missing:
        _line(FAIL, "运行依赖", "缺少 " + ", ".join(missing) +
              "；请双击「安装环境」或执行 pip install -r requirements.txt")
        return False
    return _line(OK, "运行依赖", " ".join(versions))


def load_config() -> tuple[Any, dict]:
    """加载配置，返回 (Config 实例, 启用源字典)。失败时返回 (None, {})。"""
    try:
        from .config import Config

        config = Config.load()
        sources = config.get_enabled_sources()
        return config, sources
    except Exception as exc:  # noqa: BLE001 - 自检要给出可操作结论
        _line(FAIL, "配置文件", f"{type(exc).__name__}: {exc}")
        return None, {}


def check_config(sources: dict) -> bool:
    if not sources:
        return _line(FAIL, "启用数据源", "配置中没有 enabled: true 的源")
    names = ", ".join(str(v.get("name") or k) for k, v in sources.items())
    return _line(OK, f"启用数据源 {len(sources)} 个", names)


def check_database(config: Any) -> bool:
    try:
        from .config import resolve_project_path
        from .database import Database

        db_path = resolve_project_path(config.get("database.path", "output/bidding_history.db"))
        if not db_path.exists():
            return _line(FAIL, "历史数据库", f"不存在：{db_path}")
        db = Database()
        stats = db.get_stats()
        return _line(
            OK, "历史数据库",
            f"{stats['total']} 条，最近 7 天新增 {stats['recent_week']} 条，路径 {db_path}",
        )
    except Exception as exc:  # noqa: BLE001
        return _line(FAIL, "历史数据库", f"{type(exc).__name__}: {exc}")


def check_artifact() -> bool:
    path = Path(__file__).resolve().parent.parent.parent / "output" / "index.html"
    if not path.exists():
        return _line(FAIL, "离线页面产物", f"不存在：{path}（请先跑一次「更新数据」）")
    try:
        html = io.open(path, encoding="utf-8").read()
        match = re.search(
            r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S
        )
        if not match:
            return _line(FAIL, "离线页面产物", "内联数据块缺失")
        payload = json.loads(match.group(1))
        return _line(OK, "离线页面产物", f"内联 {len(payload.get('items', []))} 条，可解析")
    except Exception as exc:  # noqa: BLE001
        return _line(FAIL, "离线页面产物", f"{type(exc).__name__}: {exc}")


def _source_url(config: dict) -> str:
    for key in URL_KEYS:
        value = str(config.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    return ""


def check_network(sources: dict) -> bool:
    """对每个启用源做一次轻量 GET，判断站点是否可达。"""
    import requests

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    if proxy:
        _line(WARN, "网络代理", f"检测到 HTTPS_PROXY={proxy}；mac 直连通常无需代理，"
              "若结果异常可尝试 unset HTTPS_PROXY HTTP_PROXY 后重跑")
    else:
        _line(OK, "网络代理", "未设置代理，走本机直连")

    results = []
    for key, cfg in sources.items():
        name = str(cfg.get("name") or key)
        url = _source_url(cfg)
        if not url:
            _line(WARN, f"{name} 连通性", "配置中无可用 URL，跳过（以试抓结果为准）")
            continue
        started = time.monotonic()
        try:
            response = requests.get(url, timeout=12, stream=True)
            elapsed = time.monotonic() - started
            good = response.status_code < 500
            _line(OK if good else FAIL, f"{name} 连通性",
                  f"HTTP {response.status_code}，{elapsed:.2f}s，{url}")
            results.append(good)
            response.close()
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            _line(FAIL, f"{name} 连通性",
                  f"{type(exc).__name__}（{elapsed:.2f}s）：{str(exc)[:90]}，{url}")
            results.append(False)
    return all(results) if results else False


def probe_crawl(sources: dict) -> bool:
    """逐源真实试抓（不写库、不写产物），报告每源条数与错误。"""
    from .main import create_crawler_manager

    print("\n--- 逐源真实试抓（不写数据库、不写产物） ---")
    manager = create_crawler_manager()
    if not manager.crawlers:
        _line(FAIL, "试抓", "没有可运行的爬虫")
        return False

    total = 0
    healthy = 0
    for crawler in manager.crawlers:
        started = time.monotonic()
        try:
            items = crawler.run()
            elapsed = time.monotonic() - started
            total += len(items)
            healthy += 1 if items else 0
            _line(OK, f"{crawler.display_name} 试抓",
                  f"取回 {len(items)} 条，{elapsed:.1f}s")
            for item in items[:3]:
                print(f"        样例：{item.date}  {item.title[:48]}")
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其它源
            elapsed = time.monotonic() - started
            _line(FAIL, f"{getattr(crawler, 'display_name', '?')} 试抓",
                  f"{type(exc).__name__}（{elapsed:.1f}s）：{str(exc)[:120]}")

    _line(OK if total else WARN, "试抓合计",
          f"{total} 条，{healthy}/{len(manager.crawlers)} 个源有数据")
    return total > 0


def main() -> int:
    parser = argparse.ArgumentParser(description="铁塔招标信息 · 环境与抓取自检")
    parser.add_argument("--probe", action="store_true",
                        help="逐源真实试抓（不写库、不写产物）")
    parser.add_argument("--timeout", type=int, default=12,
                        help="站点连通性探测超时秒数（默认 12）")
    args = parser.parse_args()

    print("=" * 60)
    print("  铁塔招标信息 · 环境与抓取自检（只读）")
    print("=" * 60)

    checks = [check_python(), check_dependencies()]
    config, sources = load_config()
    checks.append(check_config(sources))
    if config is not None:
        checks.append(check_database(config))
    checks.append(check_artifact())
    checks.append(check_network(sources) if sources else False)

    can_crawl = all(checks)
    if args.probe and sources:
        can_crawl = probe_crawl(sources) and can_crawl

    print("\n" + "=" * 60)
    if can_crawl:
        print("  结论：环境与站点就绪，可以正常抓取。")
    else:
        print("  结论：存在未通过项，抓取可能不完整或失败；请按上方 [失败] 项处理。")
    print("  提示：本自检只读，不会改动数据库与产物；正式更新请用「更新数据」。")
    print("=" * 60)
    return 0 if can_crawl else 1


if __name__ == "__main__":
    sys.exit(main())
