# coding=utf-8
"""安全内联渲染 ``output/index.html``（替代旧 serve_web.build_html）。

安全要点（ARCHITECTURE §9 / AC-10）：
- :func:`_json_for_script` 把 ``< > &`` 与 U+2028/2029 转义为 ``\\uXXXX``；
- 数据放在 ``<script type="application/json" id="DATA">`` 中，前端用
  ``JSON.parse(textContent)`` 读取，不拼 JS 字面量；
- 前端渲染一律使用 ``textContent`` / ``createElement``，不拼 innerHTML；
- CSS/JS 全部内联，``file://`` 双击打开零外部请求。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import PROJECT_ROOT
from .region_tagger import load_regions_config

_TEMPLATE_PATH = PROJECT_ROOT / "web" / "index.template.html"
_APP_JS_PATH = PROJECT_ROOT / "web" / "app.js"
_STYLES_PATH = PROJECT_ROOT / "web" / "styles.css"

_INLINE_DATA_RE = re.compile(
    r'<script type="application/json" id="DATA">(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _json_for_script(data: Any) -> str:
    """把数据序列化为可安全放进 ``<script>`` 的 JSON 文本。

    转义 ``<`` / ``>`` / ``&`` 使 ``</script>`` 无法闭合标签；转义 U+2028/U+2029
    避免早期 JS 引擎把它们当作行终止符。``JSON.parse`` 会还原为原始字符。
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def validate_html(html: str, payload: Dict[str, Any]) -> None:
    """原子写之前的产物校验：占位符已替换、内联 JSON 可解析、无脚本逃逸、条数一致。

    Raises:
        ValueError: 任一校验不通过。
    """
    if "__INLINE_PAYLOAD__" in html or "/*__APP_JS__*/" in html or "/*__STYLES__*/" in html:
        raise ValueError("模板占位符未全部替换")

    match = _INLINE_DATA_RE.search(html)
    if not match:
        raise ValueError("未找到内联数据块 DATA")

    inline = match.group(1)
    if "</script" in inline.lower():
        raise ValueError("内联数据块存在 </script 逃逸风险")

    parsed = json.loads(inline)
    expected = len(payload.get("items", []))
    actual = len(parsed.get("items", []))
    if actual != expected:
        raise ValueError(f"内联条数不一致: 期望 {expected}，实际 {actual}")
    if not isinstance(parsed.get("meta"), dict):
        raise ValueError("内联数据缺少 meta")


class StaticBuilder:
    """静态页面构建器（零构建、零 CDN、零框架）。"""

    def __init__(
        self,
        template_path: Optional[Path] = None,
        app_js_path: Optional[Path] = None,
        styles_path: Optional[Path] = None,
    ) -> None:
        self.template_path = template_path or _TEMPLATE_PATH
        self.app_js_path = app_js_path or _APP_JS_PATH
        self.styles_path = styles_path or _STYLES_PATH

    def build(self, items: List[dict], meta: Dict[str, Any]) -> str:
        """渲染完整 HTML 字符串。

        Args:
            items: 导出的条目字典列表。
            meta: 元信息（generated_at/data_as_of/regions/asset_prefix/tiers...）。

        Returns:
            完整 HTML；数据已安全内联，``file://`` 可直接打开。
        """
        template = self.template_path.read_text(encoding="utf-8")
        styles = self.styles_path.read_text(encoding="utf-8")
        app_js = self.app_js_path.read_text(encoding="utf-8")

        enriched_meta = dict(meta)
        enriched_meta.setdefault("regions", load_regions_config())
        enriched_meta.setdefault("default_view", "云南")
        enriched_meta.setdefault("stale_days", 2)
        enriched_meta.setdefault("asset_prefix", "")
        enriched_meta.setdefault("total", len(items))
        enriched_meta.setdefault("tiers", {})
        enriched_meta.setdefault("generated_at", "")
        enriched_meta.setdefault("data_as_of", "")
        enriched_meta.setdefault("source_health", [])
        enriched_meta.setdefault("run_status", [])

        payload = {
            "meta": enriched_meta,
            "items": items,
            "source_health": enriched_meta["source_health"],
            "run_status": enriched_meta["run_status"],
        }
        inline = _json_for_script(payload)

        html = template.replace("/*__STYLES__*/", styles)
        html = html.replace("/*__APP_JS__*/", app_js)
        html = html.replace("__INLINE_PAYLOAD__", inline)
        return html


def build(items: List[dict], meta: Dict[str, Any]) -> str:
    """模块级便捷函数（架构 §5 契约签名）。"""
    return StaticBuilder().build(items, meta)
