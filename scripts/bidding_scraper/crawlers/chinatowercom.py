"""中国铁塔电子采购平台爬虫

注意: 原API地址 /tcpms/tenderee/tendererBiddingInfoController/getTendererBiddingInfoList 不存在(404)。
正确API为 ES全文检索接口: /inteligentsearch/rest/esinteligentsearch/getFullTextDataNew
"""

import json
from datetime import datetime
from typing import List, Optional
from ..models import BidItem
from ..base_crawler import BaseCrawler
from ..utils import fetch_page, logger


class ChinaTowerComCrawler(BaseCrawler):
    """中国铁塔电子采购平台 (ebid.chinatowercom.cn)"""

    name = "中国铁塔电子采购平台"
    base_url = "https://ebid.chinatowercom.cn"
    # 正确的API接口（通过逆向 fullsearch.js 获取）
    api_url = "https://ebid.chinatowercom.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew"

    # 分类号：003001=采购公告, 003002=变更公告, 003003=候选人公示, 003004=结果公示
    DEFAULT_CATEGORIES = "003001;003002;003004"

    def __init__(self, source_config: dict):
        """初始化"""
        super().__init__("chinatowercom", source_config)
        self.keywords = self.config.get("keywords", ["铁塔"])
        # 允许配置文件覆盖API URL
        if self.config.get("api_url"):
            self.api_url = self.config["api_url"]
        self._categories = self.config.get("categories", self.DEFAULT_CATEGORIES)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://ebid.chinatowercom.cn/zgtt/search/fullsearch.html",
            "Origin": "https://ebid.chinatowercom.cn",
        }

    def fetch(self) -> List[BidItem]:
        """获取招标信息"""
        all_items = []

        for keyword in self.keywords:
            logger.info(f"[{self.display_name}] 搜索关键词: {keyword}")
            items = self._fetch_keyword(keyword)
            all_items.extend(items)
            self.delay()

        return all_items

    def _fetch_keyword(self, keyword: str) -> List[BidItem]:
        """获取指定关键词的招标信息"""
        items = []

        try:
            # 构建ES全文检索参数（参照 fullsearch.js）
            data = {
                "pn": 0,
                "rn": 50,
                "sdt": "",
                "edt": "",
                "wd": keyword,
                "inc_wd": "",
                "exc_wd": "",
                "fields": "title;content",
                "cnum": self._categories,
                "sort": '{"infodate":"0"}',
                "ssort": "",
                "cl": 500,
                "terminal": "0",
                "condition": "",
                "time": "",
                "highlights": "title;content",
                "statistics": "",
                "unionCondition": "",
                "accuracy": "",
                "noParticiple": "0",
                "searchRange": "",
                "token": "",
            }

            html = fetch_page(
                self.api_url,
                method="POST",
                headers=self._get_headers(),
                data=data,
                proxies=self.proxies,
                timeout=self.timeout,
                raw=True,
            )

            if not html:
                logger.warning(f"[{self.name}] API请求返回空")
                return items

            # 解析JSON响应
            try:
                resp_data = json.loads(html)
                records = self._extract_records(resp_data)
                for record in records:
                    item = self._parse_record(record)
                    if item:
                        items.append(item)
                logger.info(f"  找到 {len(items)} 个结果")
            except json.JSONDecodeError:
                logger.warning(f"[{self.name}] JSON解析失败，响应前200字符: {html[:200]}")

        except Exception as e:
            logger.error(f"[{self.name}] 请求失败: {e}")

        return items

    def _extract_records(self, resp_data: dict) -> list:
        """从ES响应中提取记录列表"""
        if not resp_data:
            return []
        # ES fulltext data 可能的响应结构
        # 通常 data.records 或 data.list 或直接 list
        data = resp_data.get("data", resp_data)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("records", data.get("list", data.get("result", [])))
        return []

    def _parse_record(self, record: dict) -> Optional[BidItem]:
        """解析单条记录"""
        try:
            # ES返回的字段可能是小写
            title = record.get("title", "") or record.get("TITLE", "")
            if not title:
                return None

            # 从高亮字段取标题（如果有）
            highlights = record.get("highlights", {}) or record.get("HIGHLIGHTS", {})
            if highlights and highlights.get("title"):
                title = highlights["title"]

            url = record.get("url", "") or record.get("URL", "") or record.get("detailUrl", "")
            if not url:
                # 尝试拼接详情页URL
                infoid = record.get("infoid", "") or record.get("INFOID", "")
                if infoid:
                    url = f"https://ebid.chinatowercom.cn/zgtt/gggs/003001/{infoid}.html"

            pub_date = record.get("infodate", "") or record.get("INFODATE", "") or record.get("webdate", "")
            if not pub_date:
                pub_date = record.get("publishDate", "") or record.get("createTime", "")

            # 解析日期
            date_obj = None
            if pub_date:
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
                    try:
                        date_obj = datetime.strptime(str(pub_date)[:19], fmt)
                        break
                    except ValueError:
                        continue

            if not date_obj:
                date_obj = datetime.now()

            # 摘要
            description = record.get("content", "") or record.get("CONTENT", "")
            if not description and highlights:
                description = highlights.get("content", "")

            return BidItem(
                title=title.strip(),
                url=url if url.startswith("http") else f"{self.base_url}{url}",
                date=date_obj.strftime("%Y-%m-%d"),
                source=self.name,
                description=description[:500] if description else "",
            )
        except Exception as e:
            logger.error(f"[{self.name}] 解析记录失败: {e}")
            return None
