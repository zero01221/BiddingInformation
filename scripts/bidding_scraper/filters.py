# coding=utf-8
"""过滤器模块 - 负责筛选云南地区铁塔相关招标信息"""

from typing import List, Optional

from .config import Config
from .logger import get_logger
from .models import BidItem
from .utils import contains_any

logger = get_logger(__name__)


class BidFilter:
    """招标信息过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        config = Config.get_instance()
        self.core_keywords = config.get_core_keywords()
        self.yunnan_keywords = config.get_yunnan_keywords()
        self.industry_keywords = config.get_industry_keywords()
    
    def should_include(
        self,
        title: str,
        description: str = "",
        require_yunnan: bool = True,
    ) -> bool:
        """
        判断是否应该包含该招标信息
        
        Args:
            title: 标题
            description: 描述/摘要
            require_yunnan: 是否要求包含云南地区信息
        
        Returns:
            是否应该包含
        """
        text = f"{title} {description}".lower()
        
        # 检查核心关键词
        has_core = contains_any(text, self.core_keywords)
        
        if not has_core:
            # 检查地区+行业组合
            has_yunnan = contains_any(text, self.yunnan_keywords)
            has_industry = contains_any(text, self.industry_keywords)
            if not (has_yunnan and has_industry):
                return False
        
        # 检查地区
        if require_yunnan:
            if not contains_any(text, self.yunnan_keywords):
                return False
        
        return True
    
    def filter_items(
        self,
        items: List[BidItem],
        require_yunnan: bool = True,
    ) -> List[BidItem]:
        """
        过滤招标信息列表
        
        Args:
            items: 招标信息列表
            require_yunnan: 是否要求包含云南地区信息
        
        Returns:
            过滤后的列表
        """
        filtered = []
        for item in items:
            if self.should_include(item.title, item.description, require_yunnan):
                filtered.append(item)
        
        logger.debug(f"过滤: {len(items)} -> {len(filtered)} 条")
        return filtered
    
    def extract_region(self, text: str) -> Optional[str]:
        """从文本中提取云南地区信息"""
        return self._extract_region(text, self.yunnan_keywords)
    
    def _extract_region(self, text: str, keywords: List[str]) -> Optional[str]:
        """从文本中提取地区信息"""
        if not text:
            return None
        
        # 优先匹配州市名称
        for kw in keywords:
            if kw in text:
                return kw
        
        return None


class RegionFilter:
    """地区过滤器 - 用于全国性网站的数据过滤"""
    
    def __init__(self):
        """初始化地区过滤器"""
        config = Config.get_instance()
        self.yunnan_keywords = config.get_yunnan_keywords()
    
    def is_yunnan(self, text: str) -> bool:
        """检查文本是否包含云南地区信息"""
        return contains_any(text, self.yunnan_keywords)
    
    def filter_items(self, items: List[BidItem]) -> List[BidItem]:
        """过滤出云南地区的招标信息"""
        filtered = []
        for item in items:
            # 检查标题、描述、地区信息
            text = f"{item.title} {item.description}"
            if self.is_yunnan(text):
                filtered.append(item)
        
        logger.debug(f"地区过滤: {len(items)} -> {len(filtered)} 条")
        return filtered
