# coding=utf-8
"""FR-11 / AC-02：云南 16 州市打标、外省打标，且只打标不过滤。"""

from __future__ import annotations

import json
from typing import List

import pytest

from scripts.bidding_scraper.base_crawler import BaseCrawler
from scripts.bidding_scraper.models import BidItem
from scripts.bidding_scraper.region_tagger import RegionTagger, tag

# 与 config/regions.json 的 yunnan_cities 对齐的 16 个州市
YUNNAN_CITIES = [
    "昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧",
    "楚雄", "红河", "文山", "西双版纳", "大理", "德宏", "怒江", "迪庆",
]


class _TaggingCrawler(BaseCrawler):
    """离线爬虫桩：只调用真实处理链，不联网、不 sleep。"""

    def __init__(self):
        super().__init__(
            "测试源", {"enabled": True, "name": "测试源", "days_limit": 36500}
        )

    def fetch(self) -> List[BidItem]:
        return []


class TestRegionTagger:
    @pytest.mark.parametrize("city", YUNNAN_CITIES)
    def test_all_16_yunnan_cities_tagged(self, city):
        region = tag(f"{city}铁塔基站维护项目")
        assert region.province == "云南"
        assert region.city == city
        assert {"云南", city}.issubset(set(region.regions))

    def test_yunnan_province_word(self):
        region = tag("云南省通信基站采购公告")
        assert region.province == "云南"
        assert "云南" in region.regions

    def test_other_province_qingdao(self):
        region = tag("山东青岛铁塔项目")
        assert region.province == "山东"
        assert region.city == "青岛"
        assert set(region.regions) == {"山东", "青岛"}

    def test_no_region_hint_returns_empty_labels(self):
        region = tag("ABC-123 综合服务类项目")
        assert region.to_dict() == {"province": "", "city": "", "regions": []}

    def test_title_takes_priority_over_description(self):
        region = tag("山东青岛铁塔项目", "云南曲靖基站维护")
        assert region.province == "山东" and region.city == "青岛"

    def test_description_fallback(self):
        region = tag("综合服务项目", "项目地点：云南曲靖")
        assert region.province == "云南" and region.city == "曲靖"

    def test_explicit_regions_config_is_honoured(self):
        tagger = RegionTagger(
            regions_config={
                "provinces": ["广东"],
                "city_to_province": {"深圳": "广东"},
                "yunnan_cities": [],
                "default_view": "广东",
            }
        )
        region = tagger.tag("深圳铁塔项目")
        assert region.province == "广东" and region.city == "深圳"


class TestTaggingNeverFilters:
    """地区只打标，绝不改变结果集（全国数据全量入库）。"""

    def test_process_items_tags_all_relevant_items(self, make_item):
        items = [
            make_item(title="中国铁塔昆明基站维护项目", url="https://a.com/x/1", native_id="N1"),
            make_item(title="山东青岛铁塔项目", url="https://a.com/x/2", native_id="N2"),
            make_item(title="中国铁塔无地区信息综合服务", url="https://a.com/x/3", native_id="N3"),
        ]

        result = _TaggingCrawler()._process_items(items)

        assert len(result) == 3, "地区打标丢弃了条目"
        by_id = {item.native_id: item for item in result}
        assert by_id["N1"].province == "云南"
        assert by_id["N2"].province == "山东"
        assert by_id["N3"].province == ""
        assert isinstance(json.loads(by_id["N2"].regions), list)

    def test_unmatched_region_keeps_item(self, make_item):
        items = [make_item(title="中国铁塔综合服务项目", url="https://a.com/x/9")]
        result = _TaggingCrawler()._process_items(items)
        assert len(result) == 1
        assert result[0].province == ""
