# coding=utf-8
"""招标信息爬虫模块"""

from .main import main
from .config import Config
from .models import BidItem
from .database import Database
from .base_crawler import BaseCrawler, CrawlerManager

__version__ = "2.0.0"
__all__ = [
    "main",
    "Config",
    "BidItem",
    "Database",
    "BaseCrawler",
    "CrawlerManager",
]
