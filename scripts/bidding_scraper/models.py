# coding=utf-8
"""数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BidItem:
    """招标信息数据模型"""
    title: str
    url: str
    date: str  # YYYY-MM-DD 格式
    source: str  # 数据来源名称
    description: str = ""  # 描述/摘要
    original_url: str = ""  # 原始发布平台链接
    item_id: str = ""  # 唯一标识（用于去重）
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """生成唯一ID"""
        if not self.item_id:
            import hashlib
            # 使用标题和URL生成唯一ID
            content = f"{self.title}_{self.url}"
            self.item_id = hashlib.md5(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "url": self.url,
            "original_url": self.original_url,
            "date": self.date,
            "source": self.source,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BidItem":
        """从字典创建"""
        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                created_at = datetime.now()
        
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            date=data.get("date", ""),
            source=data.get("source", ""),
            description=data.get("description", ""),
            original_url=data.get("original_url", ""),
            item_id=data.get("item_id", ""),
            created_at=created_at,
        )


@dataclass
class SourceStatus:
    """数据源状态"""
    name: str
    enabled: bool = True
    healthy: bool = True
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    total_items: int = 0
    last_success: Optional[datetime] = None
    
    def record_success(self, item_count: int):
        """记录成功"""
        self.healthy = True
        self.consecutive_failures = 0
        self.total_items = item_count
        self.last_success = datetime.now()
        self.last_check = datetime.now()
    
    def record_failure(self):
        """记录失败"""
        self.consecutive_failures += 1
        self.last_check = datetime.now()
        if self.consecutive_failures >= 3:
            self.healthy = False
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "consecutive_failures": self.consecutive_failures,
            "total_items": self.total_items,
            "last_success": self.last_success.isoformat() if self.last_success else None,
        }
