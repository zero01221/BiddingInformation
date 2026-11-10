# coding=utf-8
"""招标信息聚合应用包。

采用 PEP 562 延迟导出：导入任一子模块（如 ``config`` / ``dedup``）不会连带
加载爬虫主流程及其网络依赖，便于离线单测与模块化复用。
"""

import importlib

__version__ = "2.0.0"

_LAZY_EXPORTS = {
    "main": ("scripts.bidding_scraper.main", "main"),
    "Config": ("scripts.bidding_scraper.config", "Config"),
    "BidItem": ("scripts.bidding_scraper.models", "BidItem"),
    "SourceStatus": ("scripts.bidding_scraper.models", "SourceStatus"),
    "Database": ("scripts.bidding_scraper.database", "Database"),
    "BaseCrawler": ("scripts.bidding_scraper.base_crawler", "BaseCrawler"),
    "CrawlerManager": ("scripts.bidding_scraper.base_crawler", "CrawlerManager"),
    "Pipeline": ("scripts.bidding_scraper.pipeline", "Pipeline"),
    "BuildResult": ("scripts.bidding_scraper.pipeline", "BuildResult"),
    "Exporter": ("scripts.bidding_scraper.exporter", "Exporter"),
    "StaticBuilder": ("scripts.bidding_scraper.builder", "StaticBuilder"),
}

__all__ = ["__version__"] + list(_LAZY_EXPORTS.keys())


def __getattr__(name: str):
    """按需加载子模块属性，避免包初始化时的循环依赖与重依赖。"""
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """让 dir() 也能看到延迟导出的名字。"""
    return sorted(set(globals()) | set(__all__))
