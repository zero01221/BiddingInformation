# coding=utf-8
"""AC-12 / ARCHITECTURE §4：去重键与 URL 归一化回归（纯函数，无 IO）。"""

from __future__ import annotations

import re

import pytest

from scripts.bidding_scraper.dedup import (
    compute,
    legacy_key,
    normalize_source,
    normalize_title,
    normalize_url,
)
from scripts.bidding_scraper.models import BidItem


def _item(
    url: str = "",
    native_id: str = "",
    title: str = "中国铁塔项目",
    date: str = "2026-08-01",
    source: str = "测试源",
) -> BidItem:
    return BidItem(title=title, url=url, date=date, source=source, native_id=native_id)


class TestNormalizeUrl:
    """小写 host / 去尾斜杠 / 去 utm_* 与 timestamp / 保留 fragment 业务 ID。"""

    def test_lowercases_scheme_host_and_drops_default_http_port(self):
        assert normalize_url("HTTP://WWW.CEBPubService.COM:80/detail/123") == (
            "http://www.cebpubservice.com/detail/123"
        )

    def test_strips_trailing_slash(self):
        assert normalize_url("http://a.com/detail/123/") == normalize_url(
            "http://a.com/detail/123"
        )

    def test_removes_utm_and_timestamp_query_params(self):
        dirty = (
            "http://a.com/detail/123/?utm_source=weibo&timestamp=1690000000"
            "&id=42&utm_medium=x"
        )
        assert normalize_url(dirty) == "http://a.com/detail/123?id=42"

    def test_preserves_fragment_uuid_but_drops_fragment_tracking(self):
        dirty = (
            "https://EBID.CHINATOWERCOM.CN:443/zgtt/detailpage.html"
            "?businessId=ABC123&utm_medium=x#/bulletinDetail?uuid=U-999&timestamp=1"
        )
        clean = (
            "https://ebid.chinatowercom.cn/zgtt/detailpage.html"
            "?businessId=ABC123#/bulletinDetail?uuid=U-999"
        )
        assert normalize_url(dirty) == clean
        assert "uuid=U-999" in normalize_url(dirty)

    def test_query_param_order_does_not_matter(self):
        assert normalize_url("http://a.com/x?b=2&a=1") == normalize_url(
            "http://a.com/x?a=1&b=2"
        )

    @pytest.mark.parametrize("raw", ["", None, "   "])
    def test_empty_input_returns_empty_string(self, raw):
        assert normalize_url(raw) == ""


class TestDedupKey:
    """native_id 优先、同语义同键、不同语义不同键。"""

    def test_same_semantics_same_key(self):
        variant_a = _item(url="HTTP://A.COM/detail/1/?utm_source=x&timestamp=9")
        variant_b = _item(url="http://a.com/detail/1")
        assert compute(variant_a) == compute(variant_b)

    def test_native_id_takes_priority_over_url_variants(self):
        with_id_a = _item(
            url="https://a.com/one", native_id="BIZ-001", title="标题A"
        )
        with_id_b = _item(
            url="https://b.com/totally-different",
            native_id="BIZ-001",
            title="完全不同的标题",
        )
        assert compute(with_id_a) == compute(with_id_b)

    @pytest.mark.parametrize(
        "changed_fields",
        [
            {"url": "https://a.com/detail/2"},
            {"native_id": "BIZ-002"},
            {"date": "2026-08-02"},
            {"source": "另一个来源"},
        ],
    )
    def test_different_semantics_different_key(self, changed_fields):
        base_kwargs = {"url": "https://a.com/detail/1"}
        base = _item(**base_kwargs)
        changed = _item(**{**base_kwargs, **changed_fields})
        assert compute(base) != compute(changed)

    def test_key_is_32_lowercase_hex(self):
        assert re.fullmatch(r"[0-9a-f]{32}", compute(_item(url="https://a.com/x")))

    def test_legacy_key_matches_compute_when_no_native_id(self):
        item = _item(url="http://a.com/x/")
        assert legacy_key(item.source, item.url, item.title, item.date) == compute(item)

    def test_normalize_title_strips_html_and_type_prefix(self):
        assert normalize_title("<em>[招标公告]</em> 中国铁塔  昆明项目") == (
            "中国铁塔 昆明项目"
        )

    def test_normalize_source_lowercases_and_strips(self):
        assert normalize_source("  ChinaTower  ") == "chinatower"
