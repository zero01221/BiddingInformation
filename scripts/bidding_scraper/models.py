# coding=utf-8
"""数据模型定义。

字段与 ``bid_items`` 表、``data.json`` 完全一致，统一 snake_case；
前端直接消费，不做 camelCase 转换（见 docs/ARCHITECTURE.md §8）。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _iso(value: Any) -> str:
    """把 datetime 或任意值规范为 ISO 8601 字符串。"""
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _parse_dt(value: Any) -> datetime:
    """把 ISO 字符串解析为 datetime；失败时回退到当前本地时间。"""
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            pass
    return datetime.now()


def _as_region_list(value: Any) -> List[str]:
    """把 regions 字段统一成字符串列表（DB 存 JSON 文本，内存/前端用列表）。"""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (ValueError, TypeError):
            return [value]
    return []


@dataclass
class BidItem:
    """招标信息数据模型（一条公告）。

    注意：``item_id`` 与 ``dedup_key`` 恒等，均由 :func:`dedup.compute` 在
    采集处理链中计算；本类不再使用旧的 ``md5(title_url)``，也不承担任何 IO。
    """

    title: str
    url: str
    date: str  # 公告日期 YYYY-MM-DD
    source: str  # 来源名称
    description: str = ""  # 摘要
    original_url: str = ""  # 原始发布平台链接
    item_id: str = ""  # = dedup_key（32 hex）
    dedup_key: str = ""  # 去重键，sha256(source|native_id|canonical_url|date)[:32]
    native_id: str = ""  # 源站业务主键：businessId / infoid / bulletinid
    date_valid: int = 1  # 公告日期是否可解析，0 表示脏数据但不丢弃
    province: str = ""  # 省（只打标不过滤）
    city: str = ""  # 州市（只打标不过滤）
    regions: str = "[]"  # 地区标签 JSON 数组字符串（DB 存储形式）
    bid_type: str = ""  # 公告类型：仅作标签，绝不参与过滤
    download_level: str = "L4"  # L1|L2|L3|L4
    attachment_url: str = ""  # L1 直链 / L2 预存相对路径
    snapshot_url: str = ""  # L3 快照相对路径
    download_note: str = ""  # 档位文案
    created_at: datetime = field(default_factory=datetime.now)  # 首次采集时间（清理唯一口径）
    collected_at: datetime = field(default_factory=datetime.now)  # 最近一次采集时间

    def __post_init__(self) -> None:
        """保持 item_id 与 dedup_key 恒等，并规范化 regions 存储形式。"""
        if self.item_id and not self.dedup_key:
            self.dedup_key = self.item_id
        if self.dedup_key and not self.item_id:
            self.item_id = self.dedup_key
        if not self.regions:
            self.regions = "[]"
        if isinstance(self.regions, (list, tuple)):
            self.regions = json.dumps(list(self.regions), ensure_ascii=False)

    @property
    def region_list(self) -> List[str]:
        """返回地区标签列表（供导出与构建使用）。"""
        return _as_region_list(self.regions)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（snake_case，regions 输出为列表供前端直接消费）。"""
        return {
            "item_id": self.item_id,
            "dedup_key": self.dedup_key,
            "native_id": self.native_id,
            "title": self.title,
            "date": self.date,
            "date_valid": int(self.date_valid),
            "source": self.source,
            "url": self.url,
            "original_url": self.original_url,
            "description": self.description,
            "province": self.province,
            "city": self.city,
            "regions": self.region_list,
            "bid_type": self.bid_type,
            "download_level": self.download_level,
            "attachment_url": self.attachment_url,
            "snapshot_url": self.snapshot_url,
            "download_note": self.download_note,
            "created_at": _iso(self.created_at),
            "collected_at": _iso(self.collected_at),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BidItem":
        """从字典创建（兼容 regions 为列表或 JSON 字符串）。"""
        regions = data.get("regions", "[]")
        if isinstance(regions, (list, tuple)):
            regions = json.dumps(list(regions), ensure_ascii=False)
        return cls(
            title=data.get("title", "") or "",
            url=data.get("url", "") or "",
            date=data.get("date", "") or "",
            source=data.get("source", "") or "",
            description=data.get("description", "") or "",
            original_url=data.get("original_url", "") or "",
            item_id=data.get("item_id", "") or "",
            dedup_key=data.get("dedup_key", "") or "",
            native_id=data.get("native_id", "") or "",
            date_valid=int(data.get("date_valid", 1) or 0),
            province=data.get("province", "") or "",
            city=data.get("city", "") or "",
            regions=regions or "[]",
            bid_type=data.get("bid_type", "") or "",
            download_level=data.get("download_level", "L4") or "L4",
            attachment_url=data.get("attachment_url", "") or "",
            snapshot_url=data.get("snapshot_url", "") or "",
            download_note=data.get("download_note", "") or "",
            created_at=_parse_dt(data.get("created_at")),
            collected_at=_parse_dt(data.get("collected_at")),
        )


@dataclass
class SourceStatus:
    """数据源运行状态（用于 source_health 可见单源异常）。"""

    name: str
    enabled: bool = True
    healthy: bool = True
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    total_items: int = 0
    last_success: Optional[datetime] = None
    last_error: str = ""

    def record_success(self, item_count: int) -> None:
        """记录一次成功采集。"""
        self.healthy = True
        self.consecutive_failures = 0
        self.total_items = item_count
        self.last_success = datetime.now()
        self.last_check = datetime.now()
        self.last_error = ""

    def record_failure(self, error: str = "") -> None:
        """记录一次失败；连续 3 次失败标记为不健康。"""
        self.consecutive_failures += 1
        self.last_check = datetime.now()
        self.last_error = error or "未知错误"
        if self.consecutive_failures >= 3:
            self.healthy = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "last_check": _iso(self.last_check),
            "consecutive_failures": self.consecutive_failures,
            "total_items": self.total_items,
            "last_success": _iso(self.last_success),
            "last_error": self.last_error,
        }
