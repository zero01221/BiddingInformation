# coding=utf-8
"""地区打标器（只打标，绝对不过滤）。

词表单一事实源为 ``config/regions.json``（与前端下拉共用）。
策略：标题优先，正文回退；命中州市自动补对应省份；无匹配返回空标签。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, PROJECT_ROOT

__all__ = ["Region", "RegionTagger", "tag"]

_DEFAULT_TAGGER: Optional["RegionTagger"] = None


@dataclass
class Region:
    """地区打标结果。"""

    province: str = ""
    city: str = ""
    regions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {"province": self.province, "city": self.city, "regions": list(self.regions)}


def load_regions_config() -> Dict[str, Any]:
    """读取 ``config/regions.json``；失败时返回空词表（不抛异常）。"""
    path = PROJECT_ROOT / "config" / "regions.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"provinces": [], "city_to_province": {}, "yunnan_cities": [], "default_view": "云南"}


class RegionTagger:
    """省 + 州市打标器。"""

    def __init__(self, regions_config: Optional[Dict[str, Any]] = None) -> None:
        config = regions_config if regions_config is not None else Config.get_instance().get_regions()
        self.default_view: str = str(config.get("default_view", "云南"))
        self.provinces: List[str] = [str(p) for p in config.get("provinces", []) if p]
        raw_map = config.get("city_to_province", {})
        self.city_to_province: Dict[str, str] = (
            {str(k): str(v) for k, v in raw_map.items()} if isinstance(raw_map, dict) else {}
        )
        self.yunnan_cities: List[str] = [str(c) for c in config.get("yunnan_cities", []) if c]
        # 长词优先，避免「吉林」抢先命中「吉林市」这类歧义（同时补齐省份）
        self._city_pairs: List[Tuple[str, str]] = sorted(
            self.city_to_province.items(), key=lambda kv: -len(kv[0])
        )

    def tag(self, title: str, description: str = "") -> Region:
        """对标题（回退正文）打标，返回 ``{province, city, regions[]}``。

        Args:
            title: 公告标题。
            description: 摘要；仅当标题完全无地区信息时使用。

        Returns:
            :class:`Region`；无任何地区线索时返回空标签（调用方不得据此丢弃条目）。
        """
        hits = self._find_hits(title or "")
        if not hits:
            hits = self._find_hits(description or "")

        if not hits:
            return Region()

        # 按在文本中出现的位置排序，取最先出现的省/州市
        hits.sort(key=lambda h: (h[0], -h[1]))
        province_hits = [(pos, name) for pos, length, name, kind in hits if kind == "province"]
        city_hits = [(pos, name) for pos, length, name, kind in hits if kind == "city"]

        matched_provinces: List[str] = []
        matched_cities: List[str] = []
        for _, name in province_hits:
            if name not in matched_provinces:
                matched_provinces.append(name)
        for _, name in city_hits:
            if name not in matched_cities:
                matched_cities.append(name)
            parent = self.city_to_province.get(name, "")
            if parent and parent not in matched_provinces:
                matched_provinces.append(parent)

        labels = sorted(set(matched_provinces + matched_cities))
        return Region(
            province=matched_provinces[0] if matched_provinces else "",
            city=matched_cities[0] if matched_cities else "",
            regions=labels,
        )

    def _find_hits(self, text: str) -> List[Tuple[int, int, str, str]]:
        """在文本中查找所有地区词，返回 ``(位置, 词长, 词, 类型)`` 列表。"""
        if not text:
            return []
        hits: List[Tuple[int, int, str, str]] = []
        for province in self.provinces:
            pos = text.find(province)
            if pos >= 0:
                hits.append((pos, len(province), province, "province"))
        for city, _parent in self._city_pairs:
            pos = text.find(city)
            if pos >= 0:
                hits.append((pos, len(city), city, "city"))
        return hits


def tag(title: str, description: str = "") -> Region:
    """模块级便捷函数：使用进程内共享的打标器实例。"""
    global _DEFAULT_TAGGER
    if _DEFAULT_TAGGER is None:
        _DEFAULT_TAGGER = RegionTagger()
    return _DEFAULT_TAGGER.tag(title, description)
