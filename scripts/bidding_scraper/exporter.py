# coding=utf-8
"""产物导出层：SQLite（唯一事实源）→ 序列化载荷。

``data.json`` 只是 DB 的序列化快照，不另定义 JSON schema，避免两套模型漂移。
导出时做三件事：全量读取（无截断）、URL 白名单生成期校验、逐条下载档位判定。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import Config
from .database import Database
from .download_resolver import DownloadResolver, is_safe_url
from .logger import get_logger

logger = get_logger(__name__)

# 中国标准时间 UTC+8（无夏令时）；用固定偏移避免 Windows 缺少 tzdata 时报错
_TZ_SHANGHAI = timezone(timedelta(hours=8))


def now_iso() -> str:
    """返回 Asia/Shanghai 的 ISO 8601 时间字符串。"""
    return datetime.now(_TZ_SHANGHAI).isoformat(timespec="seconds")


def _valid_date(text: str) -> bool:
    """公告日期是否为合法 YYYY-MM-DD。"""
    if not text:
        return False
    try:
        datetime.strptime(str(text)[:10], "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _safe_external(url: str) -> str:
    """生成期 URL 白名单：仅 http/https；非法链接置空（前端按钮禁用）。"""
    value = (url or "").strip()
    return value if is_safe_url(value) else ""


def _safe_asset(url: str) -> str:
    """附件/快照 URL：允许 http(s) 直链与本地相对产物路径，其余置空。"""
    value = (url or "").strip()
    if not value:
        return ""
    if is_safe_url(value):
        return value
    # 本地产物只允许 attachments/ 与 snapshots/ 下的相对路径，禁止 .. 穿越
    lowered = value.lower()
    if ".." in value or lowered.startswith(("javascript:", "data:", "file:")):
        return ""
    if lowered.startswith(("attachments/", "snapshots/", "./attachments/", "./snapshots/")):
        return value
    return ""


class Exporter:
    """把 Database 导出为构建所需的完整载荷。"""

    def export(
        self,
        db: Database,
        source_health: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """导出全量数据。

        Args:
            db: 数据库实例。
            source_health: 可选的本次运行数据源状态；为空时使用 DB 聚合健康信息。

        Returns:
            ``{generated_at, data_as_of, meta, items[], source_health[]}``。
        """
        items = db.get_all_items_for_export()
        resolver = DownloadResolver()
        dict_items = [self._item_dict(item, resolver) for item in items]

        dates = [d["date"] for d in dict_items if _valid_date(d["date"])]
        data_as_of = max(dates) if dates else ""
        generated_at = now_iso()

        config = Config.get_instance()
        regions = config.get_regions()
        meta: Dict[str, Any] = {
            "generated_at": generated_at,
            "data_as_of": data_as_of,
            "total": len(dict_items),
            "regions": regions,
            "default_view": regions.get("default_view", "云南"),
            "stale_days": config.get_offline_config()["stale_days"],
            "tiers": config.get_download_config()["tiers"],
            "asset_prefix": "",  # 由 Pipeline 按产物位置覆盖（output/ 为 ""，win/ mac/ 为 "../"）
            "app_version": "2.0.0",
        }

        health = source_health if source_health is not None else db.get_source_health()
        logger.info(
            f"导出完成: {len(dict_items)} 条，数据截至 {data_as_of or '（无）'}，"
            f"数据源 {len(health)} 个"
        )
        return {
            "generated_at": generated_at,
            "data_as_of": data_as_of,
            "meta": meta,
            "items": dict_items,
            "source_health": health,
        }

    @staticmethod
    def _item_dict(item: Any, resolver: DownloadResolver) -> Dict[str, Any]:
        """把 BidItem 转为前端可直接消费的字典。"""
        data = item.to_dict()
        data["url"] = _safe_external(data.get("url", ""))
        data["original_url"] = _safe_external(data.get("original_url", ""))
        data["attachment_url"] = _safe_asset(data.get("attachment_url", ""))
        data["snapshot_url"] = _safe_asset(data.get("snapshot_url", ""))

        # 每条持久化档位与 URL；L4 时 enabled=false，前端按钮禁用
        tier = resolver.resolve(item)
        data["download"] = tier.to_dict()
        data["download_level"] = tier.level
        data["download_note"] = tier.note
        return data


def export(db: Database, source_health: Optional[List[dict]] = None) -> Dict[str, Any]:
    """模块级便捷函数。"""
    return Exporter().export(db, source_health)
