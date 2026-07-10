# coding=utf-8
"""爬虫模块"""

from .yfbzb import YfbzbCrawler
from .ccgp import CcgpCrawler
from .ynggzy import YnggzyCrawler
from .chinabidding import ChinabiddingCrawler

__all__ = [
    "YfbzbCrawler",
    "CcgpCrawler",
    "YnggzyCrawler",
    "ChinabiddingCrawler",
]
