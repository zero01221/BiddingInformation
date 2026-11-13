# coding=utf-8
"""AC-10 / ARCHITECTURE §9：XSS 双注入、安全内联、安全渲染、URL 白名单。"""

from __future__ import annotations

import json
import re

import pytest

from scripts.bidding_scraper.builder import StaticBuilder, _json_for_script, validate_html
from scripts.bidding_scraper.download_resolver import is_safe_url
from scripts.bidding_scraper.exporter import _safe_asset, _safe_external

XSS_SIMPLE = "<script>alert(1)</script>"
XSS_BREAKOUT = "</script><script>alert(2)</script>"
WEIRD_TEXT = "A\u2028B\u2029C & <b>粗体</b>"


@pytest.fixture(scope="module")
def injected_html():
    """用真实模板渲染含两种注入标题的页面（只在内存，不写盘）。"""
    items = [
        {
            "title": XSS_SIMPLE,
            "date": "2026-08-01",
            "source": "注入源A",
            "url": "javascript:alert(1)",
            "description": WEIRD_TEXT,
            "download": {
                "level": "L4", "url": "", "enabled": False, "filename": "",
                "note": "该来源不提供下载，请前往出处查看",
            },
        },
        {
            "title": XSS_BREAKOUT,
            "date": "2026-08-02",
            "source": "注入源B",
            "url": "https://example.com/ok",
            "description": "普通摘要",
            "download": {
                "level": "L1", "url": "https://example.com/a.pdf",
                "enabled": True, "filename": "a.pdf", "note": "原始文件",
            },
        },
    ]
    meta = {
        "generated_at": "2026-11-10T08:00:00+08:00",
        "data_as_of": "2026-08-02",
        "stale_days": 2,
    }
    return StaticBuilder().build(items, meta), items


class TestXssInjection:
    def test_inline_block_has_no_executable_script_closing(self, injected_html, inline_block_of):
        inline = inline_block_of(injected_html[0])
        assert "</script" not in inline.lower()
        assert "<script" not in inline.lower()

    def test_angle_brackets_and_ampersand_are_unicode_escaped(
        self, injected_html, inline_block_of
    ):
        inline = inline_block_of(injected_html[0])
        assert "\\u003c" in inline
        assert "\\u003e" in inline
        assert "\\u0026" in inline

    def test_u2028_u2029_are_escaped(self, injected_html, inline_block_of):
        inline = inline_block_of(injected_html[0])
        assert "\u2028" not in inline and "\u2029" not in inline
        assert "\\u2028" in inline and "\\u2029" in inline

    def test_json_parse_roundtrip_restores_injections_as_plain_text(
        self, injected_html, inline_block_of
    ):
        html, _original_items = injected_html
        parsed = json.loads(inline_block_of(html))
        titles = [item["title"] for item in parsed["items"]]
        assert titles == [XSS_SIMPLE, XSS_BREAKOUT]
        assert parsed["items"][0]["description"] == WEIRD_TEXT

    def test_validate_html_accepts_the_safe_payload(self, injected_html):
        html, items = injected_html
        validate_html(html, {"items": items})  # 不抛异常即通过

    def test_json_for_script_escapes_all_dangerous_chars(self):
        text = _json_for_script({"x": "<>&\u2028\u2029"})
        for token in ("\\u003c", "\\u003e", "\\u0026", "\\u2028", "\\u2029"):
            assert token in text
        assert json.loads(text)["x"] == "<>&\u2028\u2029"


class TestSafeRendering:
    def test_renderer_uses_textcontent_not_innerhtml(self, injected_html, web_dir):
        html, _ = injected_html
        app_js = (web_dir / "app.js").read_text(encoding="utf-8")
        assert "innerHTML" not in app_js
        assert "innerHTML" not in html
        assert "createElement" in app_js and "textContent" in app_js

    def test_external_links_carry_noopener(self, injected_html, web_dir):
        html, _ = injected_html
        app_js = (web_dir / "app.js").read_text(encoding="utf-8")
        assert "noopener" in html
        assert "noopener noreferrer" in app_js
        assert "target = '_blank'" in app_js

    def test_template_has_inline_json_block_and_no_external_script(self, web_dir):
        template = (web_dir / "index.template.html").read_text(encoding="utf-8")
        assert 'type="application/json" id="DATA"' in template
        assert "<script src" not in template
        assert "fetch(" not in template


class TestUrlSchemeWhitelist:
    @pytest.mark.parametrize("url", ["http://a.com/x", "https://a.com/x"])
    def test_http_and_https_allowed(self, url):
        assert is_safe_url(url) is True

    @pytest.mark.parametrize(
        "url", ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", ""]
    )
    def test_unsafe_schemes_rejected(self, url):
        assert is_safe_url(url) is False

    def test_exporter_blanks_unsafe_external_and_asset_urls(self):
        assert _safe_external("javascript:alert(1)") == ""
        assert _safe_external("https://a.com/x") == "https://a.com/x"
        assert _safe_asset("javascript:alert(1)") == ""
        assert _safe_asset("../etc/passwd") == ""
        assert _safe_asset("snapshots/a.html") == "snapshots/a.html"


class TestRealArtifactIsSafe:
    def test_real_index_html_inline_json_parses_without_breakout(
        self, built_index_html, inline_block_of
    ):
        inline = inline_block_of(built_index_html)
        assert "</script" not in inline.lower()
        payload = json.loads(inline)
        assert len(payload["items"]) >= 843  # 数据会每日增长，只保证历史无损
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["meta"]["data_as_of"] or "")

    def test_build_does_not_touch_real_artifact(self, index_html_path):
        # StaticBuilder.build 只返回字符串，绝不写盘（零改动约束）
        before = (index_html_path.stat().st_size, index_html_path.stat().st_mtime_ns)
        StaticBuilder().build([], {"data_as_of": ""})
        after = (index_html_path.stat().st_size, index_html_path.stat().st_mtime_ns)
        assert before == after
