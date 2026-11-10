# coding=utf-8
"""数据源爬虫模块（配置键 → 爬虫类的注册见 main.py）。"""

from .ccgp import CcgpCrawler
from .cebpubservice import CebpubserviceCrawler
from .chinatowercom import ChinaTowerComCrawler
from .tower_com_cn import TowerComCnCrawler
from .miit_txzbqy import MiitTxzbqyCrawler
from .yfbzb import YfbzbCrawler
from .ynggzy import YnggzyCrawler

__all__ = [
    "CcgpCrawler",
    "CebpubserviceCrawler",
    "ChinaTowerComCrawler",
    "TowerComCnCrawler",
    "MiitTxzbqyCrawler",
    "YfbzbCrawler",
    "YnggzyCrawler",
]
