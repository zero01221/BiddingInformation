# coding=utf-8
"""AC-01/02/05/11：前端契约。

单文件内联 / file:// 零外部请求 / 无类型筛选控件 / 三类筛选交集 /
默认云南优先可切全国 / 四字段占位 / 数据更新时间与数据截至 / 超 2 天标黄。

通过 subprocess 调用 Node（本机提供时）用最小 DOM stub **真实执行** web/app.js；
Node 不可用时该组跳过，静态文本断言始终执行。全程不联网、不需要真实浏览器。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_HARNESS = Path(__file__).with_name("frontend_harness.js")

SAMPLE_ITEMS = [
    {"id": "A", "title": "中国铁塔昆明5G基站项目", "date": "2026-07-20", "source": "S1",
     "description": "摘要A", "province": "云南", "regions": ["云南", "昆明"],
     "download": {"level": "L4", "url": "", "enabled": False, "note": "不可用"}},
    {"id": "B", "title": "中国铁塔曲靖基站维护", "date": "2026-07-25", "source": "S1",
     "description": "摘要B", "province": "云南", "regions": ["云南", "曲靖"],
     "download": {"level": "L1", "url": "https://a.com/b.pdf", "enabled": True, "note": "原始文件"}},
    {"id": "C", "title": "青岛铁塔采购公告", "date": "2026-08-01", "source": "S2",
     "description": "摘要C", "province": "山东", "regions": ["山东", "青岛"],
     "download": {"level": "L2", "url": "attachments/c.pdf", "enabled": True, "note": "源文件副本"}},
    {"id": "D", "title": "山东青岛5G信号覆盖工程", "date": "2026-08-02", "source": "S2",
     "description": "摘要D", "province": "山东", "regions": ["山东", "青岛"],
     "download": {"level": "L3", "url": "snapshots/d.html", "enabled": True, "note": "快照"}},
    {"id": "E", "title": "中国铁塔北京办公楼", "date": "2026-07-10", "source": "S1",
     "description": "摘要E", "province": "北京", "regions": ["北京"],
     "download": {"level": "L4", "url": "", "enabled": False, "note": "不可用"}},
    {"id": "F", "title": "中国铁塔昆明塔桅检修", "date": "2026-08-03", "source": "S1",
     "description": "摘要F", "province": "云南", "regions": ["云南", "昆明"],
     "download": {"level": "L4", "url": "", "enabled": False, "note": "不可用"}},
]

SAMPLE_PAYLOAD = {
    "meta": {
        "generated_at": "2026-11-10T08:00:00+08:00",
        "data_as_of": "2000-01-01",  # 极旧日期，稳定触发「超 2 天标黄」，不依赖运行日
        "stale_days": 2,
        "default_view": "云南",
        "degraded": False,
        "degraded_reason": "",
        "asset_prefix": "",
        "regions": {
            "provinces": ["云南", "山东", "北京"],
            "city_to_province": {"昆明": "云南", "曲靖": "云南", "青岛": "山东"},
            "yunnan_cities": ["昆明", "曲靖"],
            "default_view": "云南",
        },
        "tiers": {"L1": "原始文件", "L2": "源文件副本", "L3": "快照", "L4": "不可用"},
    },
    "items": SAMPLE_ITEMS,
    "source_health": [],
    "run_status": [],
}


@pytest.fixture(scope="module")
def js_contract(tmp_path_factory, web_dir):
    """在 Node stub 中执行一次真实 app.js，返回可断言的观测结果。"""
    if shutil.which("node") is None:
        pytest.skip("本机无 Node，跳过 JS 运行时契约断言（静态断言仍执行）")
    work = tmp_path_factory.mktemp("qa_frontend")
    payload_path = work / "qa_payload.json"
    payload_path.write_text(
        json.dumps(SAMPLE_PAYLOAD, ensure_ascii=False), encoding="utf-8"
    )
    proc = subprocess.run(
        ["node", str(_HARNESS), str(web_dir / "app.js"), str(payload_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, f"Node harness 执行失败: {proc.stderr}"
    return json.loads(proc.stdout)


class TestSingleFileOffline:
    def test_index_html_embeds_inline_data_block(self, built_index_html):
        assert 'type="application/json" id="DATA"' in built_index_html
        for placeholder in ("__INLINE_PAYLOAD__", "/*__APP_JS__*/", "/*__STYLES__*/"):
            assert placeholder not in built_index_html

    def test_file_protocol_has_zero_external_requests(self, built_index_html):
        lowered = built_index_html.lower()
        for forbidden in (
            "fetch(", "xmlhttprequest", "<script src", 'src="http',
            "@import", "url(http", "data.json",
        ):
            assert forbidden not in lowered, f"file:// 下存在外部请求: {forbidden}"

    def test_inline_payload_is_valid_json_with_843_items(
        self, built_index_html, inline_block_of
    ):
        payload = json.loads(inline_block_of(built_index_html))
        assert len(payload["items"]) == 843
        assert payload["meta"]["data_as_of"]

    def test_no_bid_type_filter_control(self, web_dir):
        template = (web_dir / "index.template.html").read_text(encoding="utf-8")
        app_js = (web_dir / "app.js").read_text(encoding="utf-8")
        assert "公告类型" not in template
        assert 'id="fBidType"' not in template and 'id="fBidType"' not in app_js
        for fid in ("fRegion", "fDateFrom", "fDateTo", "fTitle"):
            assert f'id="{fid}"' in template
        assert "tag-type" in app_js  # bid_type 仅作标签渲染


class TestThreeFiltersIntersection:
    """三类筛选可叠加为交集（真实 JS 运行时结果）。"""

    def test_all_items_loaded(self, js_contract):
        assert js_contract["total"] == 6
        assert js_contract["filters"]["all"] == ["A", "B", "C", "D", "E", "F"]

    def test_region_filter(self, js_contract):
        assert js_contract["filters"]["yunnan"] == ["A", "B", "F"]
        assert js_contract["filters"]["shandong"] == ["C", "D"]

    def test_keyword_filter(self, js_contract):
        assert js_contract["filters"]["keywordTower"] == ["A", "B", "C", "E", "F"]
        assert js_contract["filters"]["keywordKunming"] == ["A", "F"]

    def test_date_range_filter(self, js_contract):
        assert js_contract["filters"]["dateRange"] == ["B", "C", "D"]

    def test_three_filters_intersect(self, js_contract):
        assert js_contract["filters"]["intersection"] == ["B"]
        assert js_contract["filters"]["partialIntersection"] == ["B"]

    def test_invalid_date_range_returns_empty(self, js_contract):
        assert js_contract["filters"]["invalidRange"] == []


class TestDefaultViewAndMeta:
    def test_default_view_is_yunnan_and_switchable_to_nationwide(self, js_contract):
        assert js_contract["regionValue"] == "云南"
        options = js_contract["regionOptions"]
        assert options[0]["text"] == "全部（全国）" and options[0]["value"] == ""
        assert any(o["value"] == "云南" for o in options)

    def test_update_time_and_data_as_of_are_visible(self, js_contract):
        text = js_contract["metaBarText"]
        assert "数据更新时间" in text and "数据截至" in text
        assert "2000-01-01" in text

    def test_stale_data_shows_warning(self, js_contract):
        assert "warn" in js_contract["noticeClass"]
        assert "数据截至" in js_contract["noticeText"]
        assert js_contract["noticeHidden"] is False

    def test_four_fields_have_placeholders(self, web_dir):
        app_js = (web_dir / "app.js").read_text(encoding="utf-8")
        for token in ("（无标题）", "暂无日期", "暂无来源", "暂无摘要"):
            assert token in app_js, f"四字段缺失明确占位: {token}"


class TestDownloadButtonsAndUrlWhitelist:
    def test_l4_button_disabled_with_explicit_hint(self, js_contract):
        data = js_contract["download"]["L4"]
        assert data["disabled"] is True and data["buttonText"] == "无法下载"
        assert data["hints"] and "不提供下载" in data["hints"][0]

    @pytest.mark.parametrize("level", ["L1", "L2", "L3"])
    def test_other_levels_enabled_with_visible_tier(self, js_contract, level):
        data = js_contract["download"][level]
        assert data["disabled"] is False
        assert data["buttonText"] == "下载源招标文件"
        assert data["tier"].startswith(level)

    def test_javascript_and_other_schemes_rejected(self, js_contract):
        safe = js_contract["safeHttp"]
        assert safe["http"] and safe["https"]
        assert not safe["javascript"] and not safe["data"]
        assert not safe["file"] and not safe["empty"]

    def test_asset_path_whitelist(self, js_contract):
        assets = js_contract["safeAsset"]
        assert assets["snapshot"] and assets["attachment"]
        assert not assets["traversal"] and not assets["javascript"]

    def test_chinese_filename_rfc5987_encoded(self, js_contract):
        assert js_contract["rfc5987"].startswith("UTF-8''")
        assert "%" in js_contract["rfc5987"]
