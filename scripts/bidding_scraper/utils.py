# coding=utf-8
"""工具函数模块"""

import random
import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import Config
from .logger import get_logger

logger = get_logger(__name__)


def get_random_user_agent() -> str:
    """获取随机User-Agent"""
    config = Config.get_instance()
    user_agents = config.get_user_agents()
    if not user_agents:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ]
    return random.choice(user_agents)


def make_headers(referer: str = "") -> dict:
    """生成请求头"""
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    return headers


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
    reraise=True
)
def fetch_page(
    url: str,
    params: Optional[dict] = None,
    data: Optional[dict] = None,
    method: str = "GET",
    headers: Optional[dict] = None,
    referer: str = "",
    timeout: int = 30,
    encoding: Optional[str] = None,
    proxies: Optional[dict] = None,
    raw: bool = False,
):
    """
    获取页面内容，支持自动重试

    Args:
        url: 请求URL
        params: GET参数
        data: POST数据
        method: 请求方法（GET/POST）
        headers: 自定义请求头，会与默认请求头合并
        referer: Referer头
        timeout: 超时时间
        encoding: 强制编码
        proxies: 代理配置，None或空字典则禁用代理
        raw: 是否返回原始文本（True返回str，False返回BeautifulSoup）

    Returns:
        BeautifulSoup对象或原始文本字符串，失败返回None
    """
    config = Config.get_instance()
    timeout = timeout or config.get_int("request.timeout", 30)

    # 构建请求头：默认头 + 自定义头（自定义头优先）
    req_headers = make_headers(referer)
    if headers:
        req_headers.update(headers)

    # 处理代理：None或空字典则禁用代理
    req_proxies = proxies if proxies else {'http': None, 'https': None}

    try:
        if method.upper() == "POST":
            resp = requests.post(url, data=data, headers=req_headers, timeout=timeout, proxies=req_proxies)
        else:
            resp = requests.get(url, params=params, headers=req_headers, timeout=timeout, proxies=req_proxies)

        resp.raise_for_status()

        if encoding:
            resp.encoding = encoding
        elif resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding

        if raw:
            return resp.text

        return BeautifulSoup(resp.text, "html.parser")

    except requests.exceptions.Timeout:
        logger.warning(f"请求超时: {url}")
        raise
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP错误 {e.response.status_code}: {url}")
        raise
    except Exception as e:
        logger.error(f"请求失败 {url}: {e}")
        raise


def random_delay(min_seconds: float = 1, max_seconds: float = 3):
    """随机延迟"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def extract_date(text: str) -> Optional[str]:
    """从文本中提取日期（YYYY-MM-DD格式）"""
    # 匹配 YYYY-MM-DD 格式
    patterns = [
        r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)",
        r"(\d{4}\.\d{1,2}\.\d{1,2})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            # 标准化日期格式
            date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
            # 补零
            parts = date_str.split("-")
            if len(parts) == 3:
                try:
                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    continue
    
    return None


def clean_text(text: str) -> str:
    """清理文本内容"""
    if not text:
        return ""
    # 移除多余空白
    text = re.sub(r"\s+", " ", text)
    # 移除特殊字符
    text = text.replace("\u3000", " ")  # 全角空格
    return text.strip()


def contains_any(text: str, keywords: List[str]) -> bool:
    """检查文本是否包含任一关键词"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def extract_region(text: str, region_keywords: List[str]) -> Optional[str]:
    """从文本中提取地区信息"""
    if not text:
        return None
    
    for kw in region_keywords:
        if kw in text:
            return kw
    
    return None


def truncate_text(text: str, max_length: int = 200) -> str:
    """截断文本"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + "..."
