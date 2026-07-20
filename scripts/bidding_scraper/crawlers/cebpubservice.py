"""中国招标投标公共服务平台爬虫

API 接口: http://www.cebpubservice.com/ctpsp_iiss/searchbusinesstypebeforedooraction/getStringMethod.do
搜索页: https://ctbpsp.com/#/bulletinList (WAF 保护，直接 API 不可用)

注意:
- ctbpsp.com 新站有网易易盾 WAF，API 路径 /cutominfoapi/ 无法直接调用
- 老站 cebpubservice.com 的 getStringMethod.do 接口仍然可用，返回 JSON
- 4 种公告类型: 招标公告、开标记录、评标公示、中标公告
"""

import json
import re
from datetime import datetime
from typing import List, Optional

import requests

from ..models import BidItem
from ..base_crawler import BaseCrawler
from ..utils import random_delay, logger


class CebpubserviceCrawler(BaseCrawler):
    """中国招标投标公共服务平台 (cebpubservice.com → ctbpsp.com)"""

    name = "中国招标投标公共服务平台"
    base_url = "https://ctbpsp.com"

    # 老站 JSON API（无 WAF 保护）
    _api_url = (
        "http://www.cebpubservice.com/ctpsp_iiss"
        "/searchbusinesstypebeforedooraction/getStringMethod.do"
    )

    # 4 种公告类型（中文值直接 POST）
    _BUSINESS_TYPES = [
        "招标公告",
        "开标记录",
        "评标公示",
        "中标公告",
    ]

    def __init__(self, source_config: dict):
        """初始化"""
        super().__init__("cebpubservice", source_config)
        self.keywords = self.config.get("keywords", ["铁塔"])
        self._max_pages = self.config.get("max_pages", 3)
        # 每页条数（老站默认 15）
        self._page_size = self.config.get("page_size", 20)
        self._session = None

    # ------------------------------------------------------------------
    # 主抓取逻辑
    # ------------------------------------------------------------------

    def fetch(self) -> List[BidItem]:
        """获取招标信息"""
        all_items = []

        # 创建 session（获取 JSESSIONID cookie）
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "http://www.cebpubservice.com/ctpsp_iiss/"
                       "searchbusinesstypebeforedooraction/getSearch.do",
        })
        if self.proxies:
            self._session.proxies = self.proxies

        # 访问搜索页获取 cookie
        try:
            self._session.get(
                "http://www.cebpubservice.com/ctpsp_iiss/"
                "searchbusinesstypebeforedooraction/getSearch.do",
                timeout=self.timeout,
            )
        except Exception:
            pass  # cookie 非必须，失败也继续

        for keyword in self.keywords:
            logger.info(f"[{self.display_name}] 搜索关键词: {keyword}")

            for bt in self._BUSINESS_TYPES:
                try:
                    items = self._fetch_business_type(keyword, bt)
                    if items:
                        logger.info(
                            f"[{self.display_name}] {keyword} / {bt}: {len(items)} 条"
                        )
                    all_items.extend(items)
                except Exception as e:
                    logger.error(
                        f"[{self.display_name}] {keyword}/{bt} 失败: {e}"
                    )

                # 类型间短暂延迟
                random_delay(1, 3)

            # 关键词间延迟
            if keyword != self.keywords[-1]:
                self.delay()

        # 应用日期过滤（本地过滤）
        all_items = self.filter_by_date(all_items)

        return all_items

    def _fetch_business_type(
        self, keyword: str, business_type: str
    ) -> List[BidItem]:
        """查询单个公告类型，支持翻页"""
        items = []

        for page_num in range(1, self._max_pages + 1):
            data = self._request_api(keyword, business_type, page_num)
            if data is None:
                break

            page_items = self._parse_response(data, business_type)
            if not page_items:
                break

            items.extend(page_items)

            # 检查是否还有下一页
            page_info = data.get("object", {}).get("page", {})
            total_page = page_info.get("totalPage", 1)
            if page_num >= total_page:
                break

            # 页间延迟
            random_delay(2, 4)

        return items

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------

    def _request_api(
        self, keyword: str, business_type: str, page_num: int
    ) -> Optional[dict]:
        """调用 getStringMethod.do API

        注意：招标公告 需要 bulletinIssnTimeStart/Stop 时间范围参数，
        否则始终返回 0 条。其他类型不需要。
        """
        from datetime import datetime, timedelta

        data = {
            "searchName": keyword,
            "businessType": business_type,
            "pageNo": str(page_num),
            "row": str(self._page_size),
        }

        # 注意：searchArea 参数在老 API 中不生效（始终返回全国数据）
        # 地区过滤由 fetch() 中调用 self.filter_by_region() 在本地完成

        # 日期过滤（最近 N 天）
        end = datetime.now() + timedelta(days=1)
        start = end - timedelta(days=self.days_limit)
        data["searchTimeStart"] = start.strftime("%Y-%m-%d")
        data["searchTimeStop"] = end.strftime("%Y-%m-%d")

        # 招标公告额外需要 bulletinIssnTime 时间范围，否则始终为 0
        if business_type == "招标公告":
            # 用更宽的时间范围确保覆盖
            wide_start = end - timedelta(days=self.days_limit + 30)
            data["bulletinIssnTimeStart"] = wide_start.strftime("%Y-%m-%d")
            data["bulletinIssnTimeStop"] = end.strftime("%Y-%m-%d")

        try:
            resp = self._session.post(
                self._api_url,
                data=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("success") and data.get("object"):
                return data
            else:
                logger.debug(
                    f"[{self.display_name}] API 返回 success=False "
                    f"for {keyword}/{business_type}"
                )
                return None

        except requests.RequestException as e:
            logger.error(f"[{self.display_name}] 请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"[{self.display_name}] JSON 解析失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 数据解析
    # ------------------------------------------------------------------

    def _parse_response(self, data: dict, business_type: str = "") -> List[BidItem]:
        """解析 API JSON 响应"""
        records = data.get("object", {}).get("returnlist", [])
        if not records:
            return []

        items = []
        for rec in records:
            item = self._record_to_bid_item(rec, business_type)
            if item:
                items.append(item)

        return items

    def _record_to_bid_item(self, rec: dict, business_type: str = "") -> Optional[BidItem]:
        """将 API 记录转换为 BidItem"""
        title = (rec.get("businessObjectName") or "").strip()
        if not title:
            return None

        # 业务 ID
        business_id = rec.get("businessId", "")

        # 构建详情页 URL（使用新站 ctbpsp.com）
        url = (
            f"https://ctbpsp.com/#/bulletinDetail"
            f"?uuid={business_id}"
            if business_id
            else ""
        )

        # 日期
        receive_time = rec.get("receiveTime", "")
        date_str = self._normalize_date(receive_time)

        # 描述：[公告类型] 来源平台 | 地区 | 行业
        parts = [f"[{business_type}]"] if business_type else []
        for field in ["transactionPlatfName", "regionName", "industriesType"]:
            v = (rec.get(field) or "").strip()
            if v:
                parts.append(v)
        description = " | ".join(parts) if parts else ""

        return BidItem(
            title=title,
            url=url,
            date=date_str,
            source=self.name,
            description=description,
            original_url="",
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_date(text: str) -> str:
        """日期标准化为 YYYY-MM-DD"""
        if not text:
            return datetime.now().strftime("%Y-%m-%d")

        text = text.strip()

        # 常见格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y年%m月%d日",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        # 正则兜底
        m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if m:
            try:
                return (
                    f"{int(m.group(1)):04d}-"
                    f"{int(m.group(2)):02d}-"
                    f"{int(m.group(3)):02d}"
                )
            except ValueError:
                pass

        return datetime.now().strftime("%Y-%m-%d")
