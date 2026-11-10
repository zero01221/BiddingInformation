# coding=utf-8
"""去重键计算与 URL 归一化（纯函数，无 IO、无配置依赖）。

规则（docs/ARCHITECTURE.md §4）::

    dedup_key = sha256( normalize(source) + "|" + (native_id or canonical_url) + "|" + date )[:32]

``canonical_url`` 由 :func:`normalize_url` 产出：小写 host、去默认端口、
去尾斜杠、去跟踪参数（utm_*/timestamp 等）、保留 SPA fragment 中的业务 ID
（如 ``#/bulletinDetail?uuid=...``），从而让「同文不同 URL 变体」得到同一个键。
"""

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 需要剔除的跟踪参数（避免同一公告因追踪参数不同而重复入库）
_TRACKING_EXACT = {
    "timestamp", "timestamps", "_t", "t", "ts", "random", "rand", "_",
    "cachebust", "cachebuster", "nonce", "time_stamp", "from", "spm",
}

_HTML_TAG_RE = re.compile(r"<[^>]*>")
_TYPE_PREFIX_RE = re.compile(r"^\s*\[[^\]]{1,16}\]\s*")
_WHITESPACE_RE = re.compile(r"\s+")


def _is_tracking_param(key: str) -> bool:
    """判断查询参数是否为跟踪参数。"""
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_EXACT


def _clean_query(raw_query: str) -> str:
    """清理查询串：剔除跟踪参数、按键排序，保证参数顺序与来源无关。"""
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=True)
    except ValueError:
        pairs = []
    kept = [(k, v) for k, v in pairs if not _is_tracking_param(k)]
    kept.sort(key=lambda kv: (kv[0], kv[1]))
    return urlencode(kept, doseq=True)


def normalize_source(source: str) -> str:
    """来源名称归一：去空白 + 小写。"""
    return (source or "").strip().lower()


def normalize_title(title: str) -> str:
    """标题归一：去 HTML 高亮标签、去 ``[公告类型]`` 前缀、折叠空白、小写。"""
    if not title:
        return ""
    text = _HTML_TAG_RE.sub("", str(title))
    text = _TYPE_PREFIX_RE.sub("", text)
    text = text.replace("\u3000", " ")
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def normalize_url(url: str) -> str:
    """把 URL 归一为 canonical 形式，保留 SPA fragment 中的业务 ID。

    Args:
        url: 原始 URL（可含 fragment、跟踪参数、尾斜杠）。

    Returns:
        归一化后的 URL 字符串；输入为空时返回空字符串。
    """
    if not url:
        return ""
    raw = str(url).strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    # 去掉默认端口，避免 http://a.com:80/ 与 http://a.com/ 产生不同键
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parts.path or ""
    if len(path) > 1:
        path = path.rstrip("/")

    # 主查询参数与 SPA fragment 内的查询参数使用同一套清理规则
    query = _clean_query(parts.query)

    # SPA fragment：保留业务 ID（如 #/bulletinDetail?uuid=xxx），但剔除
    # utm_*/timestamp 等跟踪参数，否则同一公告会因追踪参数产生不同去重键。
    fragment = parts.fragment or ""
    if "?" in fragment:
        frag_path, frag_raw_query = fragment.split("?", 1)
        frag_query = _clean_query(frag_raw_query)
        fragment = frag_path + ("?" + frag_query if frag_query else "")

    if not scheme and not netloc:
        # 相对路径（L2/L3 本地产物），只做路径归一
        result = path
        if query:
            result += "?" + query
        if fragment:
            result += "#" + fragment
        return result

    return urlunsplit((scheme, netloc, path, query, fragment))


def compute(item: Any) -> str:
    """计算一条 :class:`BidItem` 的去重键。

    优先使用源站业务主键 ``native_id``；缺失时回退 canonical_url；
    两者皆空时用归一化标题，保证任何条目都能得到稳定键。

    Args:
        item: 具备 source / native_id / url / title / date 属性的对象。

    Returns:
        32 位十六进制字符串。
    """
    source = normalize_source(str(getattr(item, "source", "") or ""))
    native_id = str(getattr(item, "native_id", "") or "").strip()
    url = str(getattr(item, "url", "") or "")
    title = str(getattr(item, "title", "") or "")
    date = str(getattr(item, "date", "") or "").strip()

    identity = native_id or normalize_url(url) or normalize_title(title)
    payload = f"{source}|{identity}|{date}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def legacy_key(
    source: str,
    url: str,
    title: str,
    date: str,
    salt: str = "",
) -> str:
    """为历史数据计算去重键；与新数据公式一致，仅无 native_id。

    Args:
        source: 来源名称。
        url: 原文 URL。
        title: 标题（URL 为空时作为回退身份）。
        date: 公告日期。
        salt: 冲突消解盐；仅当基础键撞车时传入旧 item_id。

    Returns:
        32 位十六进制字符串。
    """
    identity = normalize_url(url) or normalize_title(title)
    payload = f"{normalize_source(source)}|{identity}|{(date or '').strip()}"
    if salt:
        payload += "|" + salt
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class DedupKey:
    """去重键计算的面向对象包装（便于在 Pipeline 中注入）。"""

    @staticmethod
    def normalize_url(url: str) -> str:
        """URL 归一化。"""
        return normalize_url(url)

    @staticmethod
    def compute(item: Any) -> str:
        """计算去重键。"""
        return compute(item)
