# coding=utf-8
"""中国政府采购网爬虫"""

from typing import List, Optional

from bs4 import BeautifulSoup

from ..base_crawler import BaseCrawler
from ..logger import get_logger
from ..models import BidItem
from ..utils import fetch_page, extract_date, clean_text

logger = get_logger(__name__)


class CcgpCrawler(BaseCrawler):
    """中国政府采购网爬虫"""
    
    def __init__(self, source_config: dict):
        """初始化"""
        super().__init__("ccgp", source_config)
        self.search_url = self.config.get("search_url", "http://search.ccgp.gov.cn/bxsearch")
        self.display_zone = self.config.get("display_zone", "云南")
        self.zone_id = self.config.get("zone_id", "53")
        self.keywords = self.config.get("keywords", ["铁塔"])
    
    def fetch(self) -> List[BidItem]:
        """抓取招标信息"""
        all_items = []
        
        for keyword in self.keywords:
            logger.info(f"[{self.display_name}] 搜索关键词: {keyword}, 地区: {self.display_zone}(zoneId={self.zone_id})")
            items = self._search_keyword(keyword)
            all_items.extend(items)
            self.delay()
        
        # 去重
        seen_ids = set()
        unique_items = []
        for item in all_items:
            if item.item_id not in seen_ids:
                seen_ids.add(item.item_id)
                unique_items.append(item)
        
        return unique_items
    
    def _search_keyword(self, keyword: str) -> List[BidItem]:
        """搜索单个关键词"""
        params = {
            "searchtype": 1,
            "page_index": 1,
            "bidSort": 0,
            "buyerName": "",
            "projectId": "",
            "pinMu": 0,
            "bidType": 1,
            "dbselect": "bidx",
            "kw": keyword,
            "timeType": 2,
            "displayZone": self.display_zone,
            "zoneId": self.zone_id,
            "pppStatus": 0,
            "agentName": "",
        }
        
        try:
            soup = fetch_page(
                self.search_url,
                params=params,
                referer="http://www.ccgp.gov.cn/",
                timeout=self.timeout,
            )
            
            if not soup:
                logger.info(f"  找到 0 个搜索结果")
                return []
            
            items = self._parse_page(soup)
            logger.info(f"  找到 {len(items)} 个搜索结果")
            return items
        
        except Exception as e:
            logger.error(f"[{self.display_name}] 搜索失败: {e}")
            return []
    
    def _parse_page(self, soup: BeautifulSoup) -> List[BidItem]:
        """解析页面"""
        items = []
        
        # 查找搜索结果列表
        results = soup.select("ul.vT-srch-result-list-bid li")
        if not results:
            results = soup.select("ul.vT-srch-result-list li")
        
        for result in results:
            item = self._parse_result(result)
            if item:
                items.append(item)
        
        return items
    
    def _parse_result(self, result) -> Optional[BidItem]:
        """解析单个结果"""
        try:
            a_tag = result.find("a")
            if not a_tag:
                return None
            
            title = a_tag.get_text(strip=True)
            url = a_tag.get("href", "")
            
            # 提取日期
            date_str = ""
            span = result.find("span")
            if span:
                date_str = span.get_text(strip=True)
            date = extract_date(date_str) or extract_date(result.get_text()) or ""
            
            # 提取摘要
            desc = ""
            desc_p = result.find("p")
            if desc_p:
                desc = clean_text(desc_p.get_text(strip=True))
            
            return BidItem(
                title=title,
                url=url,
                original_url=url,
                date=date,
                source=self.display_name,
                description=desc,
            )
        
        except Exception as e:
            logger.debug(f"解析结果失败: {e}")
            return None
