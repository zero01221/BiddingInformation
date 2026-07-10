# coding=utf-8
"""中国采购与招标网爬虫"""

from typing import List, Optional

from bs4 import BeautifulSoup

from ..base_crawler import BaseCrawler
from ..logger import get_logger
from ..models import BidItem
from ..utils import fetch_page, extract_date, clean_text

logger = get_logger(__name__)


class ChinabiddingCrawler(BaseCrawler):
    """中国采购与招标网爬虫"""
    
    def __init__(self, source_config: dict):
        """初始化"""
        super().__init__("chinabidding", source_config)
        self.search_url = self.config.get("search_url", "https://www.chinabidding.com/search/proj.htm")
        self.keyword = self.config.get("keyword", "铁塔")
        self.max_pages = self.config.get("max_pages", 1)
    
    def fetch(self) -> List[BidItem]:
        """抓取招标信息"""
        all_items = []
        
        logger.info(f"[{self.display_name}] 开始抓取: {self.search_url}")
        
        for page in range(1, self.max_pages + 1):
            items = self._fetch_page(page)
            if not items:
                break
            all_items.extend(items)
            self.delay()
        
        logger.info(f"  找到 {len(all_items)} 个原始条目")
        
        # 过滤云南地区
        filtered_items = self.filter_by_region(all_items)
        logger.info(f"  过滤后保留 {len(filtered_items)} 条招标信息")
        
        return filtered_items
    
    def _fetch_page(self, page: int) -> List[BidItem]:
        """获取单页数据"""
        post_data = {
            "fullText": self.keyword,
            "poClass": "BidNotice",
        }
        
        try:
            soup = fetch_page(
                self.search_url,
                data=post_data,
                method="POST",
                referer="https://www.chinabidding.com/",
                timeout=self.timeout,
            )
            
            if not soup:
                return []
            
            return self._parse_page(soup)
        
        except Exception as e:
            logger.error(f"[{self.display_name}] 获取页面失败: {e}")
            return []
    
    def _parse_page(self, soup: BeautifulSoup) -> List[BidItem]:
        """解析页面"""
        items = []
        
        # 查找搜索结果列表
        result_list = soup.select_one("ul.as-pager-body")
        if not result_list:
            return items
        
        for item in result_list.select("li"):
            bid_item = self._parse_item(item)
            if bid_item:
                items.append(bid_item)
        
        return items
    
    def _parse_item(self, item) -> Optional[BidItem]:
        """解析单个条目"""
        try:
            # 标题和链接
            title_el = item.select_one("h5 span.txt")
            if not title_el:
                return None
            
            title = title_el.get_text(strip=True)
            
            a_tag = item.select_one('a[href*="/project/"]')
            if not a_tag:
                return None
            
            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.chinabidding.com{href}"
            
            # 日期
            date_str = ""
            date_el = item.select_one("h5 span.fr")
            if date_el:
                date_str = date_el.get_text(strip=True)
            date = extract_date(date_str) or ""
            
            # 摘要
            desc = ""
            desc_p = item.select_one("p.txt")
            if desc_p:
                desc = clean_text(desc_p.get_text(strip=True))
            
            return BidItem(
                title=title,
                url=href,
                original_url=href,
                date=date,
                source=self.display_name,
                description=desc,
            )
        
        except Exception as e:
            logger.debug(f"解析条目失败: {e}")
            return None
