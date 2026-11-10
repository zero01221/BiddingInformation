# coding=utf-8
"""铁塔相关性校验（入库前强制过滤）。

设计要点（docs/ARCHITECTURE.md §2/§9）：
- ``require_core=true`` 时标题或摘要须命中 ``keywords.core`` 或 ``keywords.industry``；
- **不要求云南**——地区只打标不过滤，全国数据全量入库；
- 公告类型一律不过滤，``bid_type`` 仅作标签。
"""

from typing import Iterable, Optional

from .config import Config


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    """判断文本是否命中任一关键词（大小写不敏感）。"""
    if not text:
        return False
    lowered = text.lower()
    return any(kw and str(kw).lower() in lowered for kw in keywords)


def is_relevant(title: str, description: str = "", require_core: Optional[bool] = None) -> bool:
    """判断一条公告是否与铁塔相关。

    Args:
        title: 公告标题。
        description: 摘要（可为空）。
        require_core: 是否强制校验；None 时读取 ``relevance.require_core`` 配置。

    Returns:
        True 表示应入库；配置为不强制时恒为 True（不丢弃任何条目）。
    """
    config = Config.get_instance()
    if require_core is None:
        require_core = config.get_relevance_config()["require_core"]
    if not require_core:
        return True

    text = f"{title or ''} {description or ''}"
    return _contains_any(text, config.get_core_keywords()) or _contains_any(
        text, config.get_industry_keywords()
    )


class RelevanceFilter:
    """铁塔相关性过滤器（类式包装，供处理链注入）。"""

    def __init__(self, require_core: Optional[bool] = None) -> None:
        self.require_core = require_core

    def is_relevant(self, title: str, description: str = "") -> bool:
        """判断标题/摘要是否命中核心或行业关键词。"""
        return is_relevant(title, description, self.require_core)
