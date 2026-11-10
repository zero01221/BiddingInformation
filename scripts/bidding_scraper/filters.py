# coding=utf-8
"""过滤器兼容层。

历史缺陷：本模块原把 ``require_yunnan`` 默认设为 True，会砍掉全部全国数据，且活跃源
零调用。新实现把「相关性」委托给 :mod:`relevance`、「地区」委托给
:mod:`region_tagger`——**相关性强制校验、地区只打标不过滤**。
处理链真正串接发生在 :meth:`base_crawler.BaseCrawler.run`，本模块保留旧类名
仅为兼容既有导入，不再承担默认过滤职责。
"""

from typing import List, Optional

from .config import Config
from .logger import get_logger
from .models import BidItem
from .region_tagger import RegionTagger
from .relevance import RelevanceFilter
from .utils import contains_any

logger = get_logger(__name__)


class BidFilter:
    """铁塔相关性过滤器（薄适配层）。"""

    def __init__(self) -> None:
        config = Config.get_instance()
        self.core_keywords = config.get_core_keywords()
        self.yunnan_keywords = config.get_yunnan_keywords()
        self.industry_keywords = config.get_industry_keywords()
        self._relevance = RelevanceFilter()

    def should_include(
        self,
        title: str,
        description: str = "",
        require_core: bool = True,
        require_yunnan: bool = False,
    ) -> bool:
        """判断是否应入库。

        Args:
            title: 标题。
            description: 摘要。
            require_core: 是否强制校验 core/industry（默认 True）。
            require_yunnan: **已废弃**，保留仅为兼容旧签名；地区只打标不过滤，
                传入 True 也不会据此丢弃条目（避免砍掉全国数据）。

        Returns:
            True 表示通过相关性校验。
        """
        if require_yunnan:
            logger.debug("require_yunnan 已废弃：地区只打标不过滤，参数被忽略")
        return self._relevance.is_relevant(title, description) if require_core else True

    def filter_items(
        self,
        items: List[BidItem],
        require_core: bool = True,
        require_yunnan: bool = False,
    ) -> List[BidItem]:
        """按相关性过滤列表（地区不过滤）。"""
        filtered = [
            item for item in items
            if self.should_include(
                item.title, item.description, require_core, require_yunnan
            )
        ]
        logger.debug(f"相关性过滤: {len(items)} -> {len(filtered)} 条")
        return filtered

    def extract_region(self, text: str) -> Optional[str]:
        """从文本中提取云南地区词（仅打标用）。"""
        return self._extract_region(text, self.yunnan_keywords)

    @staticmethod
    def _extract_region(text: str, keywords: List[str]) -> Optional[str]:
        """返回文本中首个命中的地区词。"""
        if not text:
            return None
        for kw in keywords:
            if kw and kw in text:
                return kw
        return None


class RegionFilter:
    """地区打标器（原「地区过滤器」，已改为只打标不丢弃）。"""

    def __init__(self) -> None:
        self._tagger = RegionTagger()
        self.yunnan_keywords = Config.get_instance().get_yunnan_keywords()

    def is_yunnan(self, text: str) -> bool:
        """仅判断文本是否含云南地区词，不改变结果集。"""
        return contains_any(text or "", self.yunnan_keywords)

    def tag(self, title: str, description: str = ""):
        """返回地区打标结果（``Region``，含 province/city/regions）。"""
        return self._tagger.tag(title, description)

    def tag_items(self, items: List[BidItem]) -> List[BidItem]:
        """给每条打标并**原样返回全部**条目，绝不过滤。"""
        import json

        for item in items:
            region = self._tagger.tag(item.title, item.description)
            item.province = region.province
            item.city = region.city
            item.regions = json.dumps(region.regions, ensure_ascii=False)
        logger.debug(f"地区打标: {len(items)} 条（0 条被丢弃）")
        return items

    def filter_items(self, items: List[BidItem]) -> List[BidItem]:
        """兼容旧签名：实际执行打标，返回全部条目（不丢弃任何数据）。"""
        logger.debug("RegionFilter.filter_items 已改语义：只打标不过滤")
        return self.tag_items(items)
