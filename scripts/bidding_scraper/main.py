# coding=utf-8
"""招标信息聚合应用主入口（CLI 薄层）。

用法::

    python -m scripts.bidding_scraper.main                 # 抓取 → 处理 → 落库 → 导出 → 构建
    python -m scripts.bidding_scraper.main --no-crawl      # 离线重建：只用现有 DB 重建产物
    python -m scripts.bidding_scraper.main --stats         # 数据库统计
    python -m scripts.bidding_scraper.main --list --days 7
    python -m scripts.bidding_scraper.main --dry-run       # 只打印，不写产物

本期不做消息推送，所有信息只在页面呈现。
"""

import argparse
import sys
from pathlib import Path

# 修复 Windows GBK 终端 print 乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from .base_crawler import CrawlerManager
from .config import Config
from .crawlers import (
    CcgpCrawler,
    CebpubserviceCrawler,
    ChinaTowerComCrawler,
    MiitTxzbqyCrawler,
    TowerComCnCrawler,
    YfbzbCrawler,
    YnggzyCrawler,
)
from .database import Database
from .logger import get_logger
from .output import OutputFormatter
from .pipeline import BuildResult, Pipeline

logger = get_logger(__name__)

# 配置键 → 爬虫类；新增数据源时只需在此登记并在配置中启用。
_CRAWLER_CLASSES = {
    "ccgp": CcgpCrawler,
    "cebpubservice": CebpubserviceCrawler,
    "chinatowercom": ChinaTowerComCrawler,
    "tower_com_cn": TowerComCnCrawler,
    "miit_txzbqy": MiitTxzbqyCrawler,
    "yfbzb": YfbzbCrawler,
    "ynggzy": YnggzyCrawler,
}


def create_crawler_manager() -> CrawlerManager:
    """按配置装配所有已启用的数据源爬虫（含云南源 ynggzy）。"""
    config = Config.get_instance()
    manager = CrawlerManager()
    sources = config.get_enabled_sources()

    for source_name, crawler_class in _CRAWLER_CLASSES.items():
        source_config = sources.get(source_name)
        if source_config:
            manager.register(crawler_class(source_config))

    logger.info(f"已注册 {len(manager.crawlers)} 个数据源: {', '.join(sources.keys())}")
    return manager


def _print_stats() -> None:
    """打印数据库统计信息。"""
    stats = Database().get_stats()
    print("\n数据库统计:")
    print(f"  总记录数: {stats['total']}")
    print(f"  最近7天新增: {stats['recent_week']}")
    print("  按来源统计:")
    for source, count in stats["by_source"].items():
        print(f"    {source}: {count}")
    print(f"  数据库路径: {stats['db_path']}")


def _print_list(days: int) -> None:
    """打印最近 N 天记录（只读，不触发爬虫）。"""
    items = Database().get_recent_items(days)
    formatter = OutputFormatter()
    if not items:
        print(f"\n数据库中没有最近 {days} 天的记录")
    else:
        formatter.print_summary(items)


def _print_result(result: BuildResult) -> None:
    """打印一次构建的摘要。"""
    print("\n" + "=" * 56)
    print("  构建结果")
    print("=" * 56)
    print(f"  状态: {'成功' if result.success else '失败（已保留上一版产物）'}")
    print(f"  导出条数: {result.items_count}")
    print(f"  本次新增: {result.new_count}")
    print(f"  数据截至: {result.data_as_of or '（无）'}")
    print(f"  生成时间: {result.generated_at}")
    print(f"  首页产物: {result.index_path}")
    print(f"  数据产物: {result.data_path}")
    print(f"  数据源健康: {len(result.source_health)} 个源")
    for health in result.source_health:
        print(f"    - {health.get('source', health.get('name', '?'))}: {health.get('item_count', 0)} 条")
    for error in result.errors:
        print(f"  [告警] {error}")
    print("=" * 56 + "\n")


def main() -> None:
    """CLI 主函数。"""
    parser = argparse.ArgumentParser(
        description="铁塔招标信息聚合 - 生成离线优先的纯静态 HTML 产物"
    )
    parser.add_argument("--output", "-o", help="RSS 输出文件路径（覆盖配置）")
    parser.add_argument("--dry-run", "-n", action="store_true", help="只打印结果，不写产物")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--stats", action="store_true", help="显示数据库统计信息")
    parser.add_argument("--list", action="store_true", help="列出最近记录（不触发爬虫）")
    parser.add_argument("--days", "-d", type=int, default=30, help="--list 时的天数（默认 30）")
    parser.add_argument(
        "--no-crawl", action="store_true",
        help="跳过联网抓取，仅用现有数据库重建产物（离线验证用）",
    )
    args = parser.parse_args()

    Config.load(args.config)

    if args.stats:
        _print_stats()
        return
    if args.list:
        _print_list(args.days)
        return

    pipeline = Pipeline()
    result = pipeline.run(
        crawl=not args.no_crawl,
        write_artifacts=not args.dry_run,
        rss=not args.dry_run,
        rss_path=args.output,
    )
    _print_result(result)

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
