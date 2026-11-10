# coding=utf-8
"""FR-04 / AC-03：铁塔相关性过滤，且必须真正接入 BaseCrawler.run()。

重点不是只测 ``is_relevant`` 纯函数，而是用离线爬虫桩证明
``run() → fetch() → filter_by_date() → _process_items()`` 真的执行了
相关性 → 打标 → 去重键 → 下载档位这条链。
"""

from __future__ import annotations

import json
from typing import List

import pytest

from scripts.bidding_scraper import base_crawler as bc
from scripts.bidding_scraper.base_crawler import BaseCrawler
from scripts.bidding_scraper.models import BidItem
from scripts.bidding_scraper.relevance import is_relevant


class _StubCrawler(BaseCrawler):
    """离线爬虫桩：fetch() 直接返回预置条目，不联网、不 sleep。

    ``days_limit`` 设得足够大，使 ``filter_by_date`` 不依赖系统当前日期。
    """

    def __init__(self, items: List[BidItem]) -> None:
        super().__init__(
            "测试源", {"enabled": True, "name": "测试源", "days_limit": 36500}
        )
        self._items = list(items)

    def fetch(self) -> List[BidItem]:
        return list(self._items)


class TestRelevanceFunction:
    """keywords.core + industry 命中放行；非铁塔剔除；不要求云南。"""

    @pytest.mark.parametrize(
        "title",
        [
            "中国铁塔昆明基站维护项目",
            "通信铁塔塔桅检测招标公告",
            "山东青岛5G基站建设项目",
            "中国移动云南曲靖信号覆盖工程",
        ],
    )
    def test_core_or_industry_keyword_passes(self, title):
        assert is_relevant(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "城市园林绿化养护项目招标公告",
            "市政道路沥青铺设工程",
            "办公家具采购询价公告",
            "食堂餐饮服务承包项目",
        ],
    )
    def test_non_tower_title_rejected(self, title):
        assert is_relevant(title) is False

    def test_description_also_counts(self):
        assert is_relevant("综合服务项目", "本项目含中国铁塔基站维护") is True

    def test_shandong_qingdao_tower_passes_without_yunnan(self):
        # 关键口径：不要求云南，全国数据全量入库
        assert is_relevant("山东青岛铁塔采购公告") is True
        assert is_relevant("青岛5G基站建设") is True

    def test_require_core_false_keeps_everything(self):
        assert is_relevant("市政道路工程", require_core=False) is True

    def test_bid_type_label_does_not_affect_relevance(self):
        # 公告类型仅作标签，全类型收录、不参与过滤
        for label in ("[招标公告]", "[中标公告]", "[评标公示]", "[开标结果文件]"):
            assert is_relevant(f"{label} 中国铁塔基站项目") is True


class TestFilterChainWiredIntoRun:
    """过滤链必须真正接进 run()，不能只测纯函数。"""

    def test_subclass_does_not_override_run(self):
        # 保证下面的行为断言测的是基类 run()，而非测试自己重写的实现
        assert _StubCrawler.run is BaseCrawler.run

    def test_run_invokes_relevance_gate(self, monkeypatch, make_item):
        calls: List[str] = []
        original = bc.is_relevant

        def spy(title, description=""):
            calls.append(title)
            return original(title, description)

        monkeypatch.setattr(bc, "is_relevant", spy)
        crawler = _StubCrawler([make_item(title="中国铁塔昆明基站项目")])
        crawler.run()

        assert calls, "run() 未调用相关性校验，过滤链未真正接入抓取链"

    def test_run_drops_non_tower_and_keeps_nationwide_items(self, make_item):
        good = make_item(
            title="中国铁塔曲靖基站维护", url="https://a.com/x/1", native_id="N1"
        )
        shandong = make_item(
            title="山东青岛5G基站建设", url="https://a.com/x/2", native_id="N2"
        )
        bad = make_item(
            title="城市园林绿化养护项目招标公告",
            # 显式覆盖默认摘要：默认摘要含「铁塔」，按契约标题或摘要命中即放行
            description="城市园林绿化养护服务采购",
            url="https://a.com/x/3",
            native_id="N3",
        )

        result = _StubCrawler([good, shandong, bad]).run()

        titles = [item.title for item in result]
        assert bad.title not in titles, "非铁塔标题未被 run() 剔除"
        assert len(result) == 2
        by_id = {item.native_id: item for item in result}
        assert by_id["N1"].province == "云南" and by_id["N1"].city == "曲靖"
        assert by_id["N2"].province == "山东" and by_id["N2"].city == "青岛", (
            "山东/青岛被误当云南过滤：地区必须只打标不过滤"
        )

    def test_run_populates_dedup_native_id_and_download_tier(self, make_item):
        item = make_item(title="中国铁塔北京基站检修", url="https://a.com/detail/9")

        (result,) = _StubCrawler([item]).run()

        assert len(result.dedup_key) == 32
        assert result.item_id == result.dedup_key
        assert result.native_id
        assert result.download_level in {"L1", "L2", "L3", "L4"}
        assert result.download_note
        assert isinstance(json.loads(result.regions), list)
