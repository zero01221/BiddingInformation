# coding=utf-8
"""输出格式化模块（控制台摘要 + RSS）。

RSS 从 Exporter 的全量载荷生成，``output.max_items: 0`` 表示不截断；
``escape`` 负责 XML 转义。地区与公告类型不参与输出过滤。
"""

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from .config import Config, resolve_project_path
from .logger import get_logger
from .models import BidItem

logger = get_logger(__name__)


class OutputFormatter:
    """输出格式化类。"""

    def __init__(self) -> None:
        self.config = Config.get_instance()

    # ------------------------------------------------------------------
    # 控制台
    # ------------------------------------------------------------------

    @staticmethod
    def format_console(items: List[BidItem]) -> str:
        """格式化为控制台输出（按日期分组）。"""
        if not items:
            return "未找到招标信息"

        lines = ["", "=" * 50, f"共收集到 {len(items)} 条招标信息", "=" * 50, ""]
        items_by_date: Dict[str, List[BidItem]] = defaultdict(list)
        for item in items:
            items_by_date[item.date or "未知日期"].append(item)

        for date in sorted(items_by_date.keys(), reverse=True):
            date_items = items_by_date[date]
            lines.append(f"【{date}】共 {len(date_items)} 条")
            for item in date_items:
                lines.append(f"  {item.title}")
                lines.append(f"    {item.original_url or item.url}")
                lines.append(f"    [来源: {item.source}]")
            lines.append("")
        return "\n".join(lines)

    def print_summary(self, items: List[BidItem]) -> None:
        """打印摘要到控制台。"""
        print(self.format_console(items))

    # ------------------------------------------------------------------
    # RSS
    # ------------------------------------------------------------------

    def _rss_header(self) -> List[str]:
        """构造 RSS 头部行。"""
        return [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            '<channel>',
            f'<title>{escape(str(self.config.get("output.rss_title", "招标信息")))}</title>',
            f'<description>{escape(str(self.config.get("output.rss_description", "招标信息聚合")))}</description>',
            f'<link>{escape(str(self.config.get("output.rss_link", "")))}</link>',
            f'<lastBuildDate>{self._format_rss_date(datetime.now())}</lastBuildDate>',
        ]

    def format_rss(self, items: List[BidItem]) -> str:
        """把 BidItem 列表格式化为 RSS XML（默认全量，不截断）。"""
        limit = self.config.get_int("output.max_items", 0)
        selected = items[:limit] if limit > 0 else items

        lines = self._rss_header()
        for item in selected:
            lines.append('<item>')
            lines.append(f'<title>{escape(item.title or "")}</title>')
            lines.append(f'<link>{escape(item.original_url or item.url or "")}</link>')
            lines.append(f'<description>{escape(item.description or "")}</description>')
            lines.append(f'<pubDate>{self._format_rss_date(self._parse_date(item.date))}</pubDate>')
            lines.append(f'<guid>{escape(item.dedup_key or item.item_id or "")}</guid>')
            lines.append('</item>')
        lines.extend(['</channel>', '</rss>'])
        return "\n".join(lines)

    def format_rss_from_payload(self, payload: Dict[str, Any]) -> str:
        """从 Exporter 的全量载荷生成 RSS（推荐入口）。"""
        items: List[Dict[str, Any]] = list(payload.get("items", []))
        limit = self.config.get_int("output.max_items", 0)
        if limit > 0:
            items = items[:limit]

        lines = self._rss_header()
        for item in items:
            link = item.get("original_url") or item.get("url") or ""
            lines.append('<item>')
            lines.append(f'<title>{escape(str(item.get("title", "") or ""))}</title>')
            lines.append(f'<link>{escape(str(link))}</link>')
            lines.append(f'<description>{escape(str(item.get("description", "") or ""))}</description>')
            lines.append(
                f'<pubDate>{self._format_rss_date(self._parse_date(str(item.get("date", "") or "")))}</pubDate>'
            )
            lines.append(f'<guid>{escape(str(item.get("dedup_key") or item.get("item_id") or ""))}</guid>')
            bid_type = str(item.get("bid_type", "") or "")
            if bid_type:
                lines.append(f'<category>{escape(bid_type)}</category>')
            lines.append(f'<source>{escape(str(item.get("source", "") or ""))}</source>')
            lines.append('</item>')
        lines.extend(['</channel>', '</rss>'])
        return "\n".join(lines)

    def save_rss(self, items: List[BidItem], output_path: Optional[str] = None) -> None:
        """保存 RSS（BidItem 列表入口，兼容旧调用）。"""
        self._write_rss(self.format_rss(items), output_path)

    def save_rss_from_payload(
        self, payload: Dict[str, Any], output_path: Optional[str] = None
    ) -> None:
        """保存 RSS（Exporter 全量载荷入口）。"""
        self._write_rss(self.format_rss_from_payload(payload), output_path)

    def _write_rss(self, content: str, output_path: Optional[str]) -> None:
        """原子写入 RSS 文件。"""
        raw = output_path or self.config.get("output.rss_file", "output/bidding_feed.xml")
        target = resolve_project_path(str(raw))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(target))
        logger.info(f"RSS 已写入: {target}")

    @staticmethod
    def _format_rss_date(dt: datetime) -> str:
        """格式化 RSS 日期（RFC 822）。"""
        from email.utils import formatdate
        import time
        return formatdate(time.mktime(dt.timetuple()))

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """解析 YYYY-MM-DD；失败回退当前时间。"""
        if not date_str:
            return datetime.now()
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return datetime.now()
