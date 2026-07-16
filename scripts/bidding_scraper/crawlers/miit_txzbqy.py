"""通信工程建设项目招标投标管理信息平台爬虫

注意: 该网站为Vue.js SPA应用，API接口需要通过认证(OAuth/SSO)。
公开访问的API端点与原猜测的 /api/bidding/search 不同。
实际base URL为 https://txzbqy.miit.gov.cn/zbtb (从 static/config.js 确认)。

当前状态: 由于网站API需要认证令牌，暂时使用状态标记。当API可公开访问时，
需进一步逆向Vue.js应用获取正确的API端点路径。
"""

from datetime import datetime
from typing import List, Optional
from ..models import BidItem
from ..base_crawler import BaseCrawler
from ..utils import fetch_page, logger


class MiitTxzbqyCrawler(BaseCrawler):
    """通信工程建设项目招标投标管理信息平台 (txzbqy.miit.gov.cn)

    原API地址 /api/bidding/search 不存在(404)。
    正确base URL为 https://txzbqy.miit.gov.cn/zbtb（来自static/config.js）。
    REST API路径需要在Vue.js应用中进一步逆向获取。
    """

    name = "通信工程招标投标平台"
    base_url = "https://txzbqy.miit.gov.cn"
    # 已知正确的API base URL（来自 static/config.js）
    api_base = "https://txzbqy.miit.gov.cn/zbtb"

    def __init__(self, source_config: dict):
        """初始化"""
        super().__init__("miit_txzbqy", source_config)
        self.keywords = self.config.get("keywords", ["铁塔", "塔桅", "通信塔"])
        # 允许配置文件覆盖
        if self.config.get("search_url"):
            self._search_url = self.config["search_url"]
        else:
            self._search_url = None

    def _get_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Referer": "https://txzbqy.miit.gov.cn/",
        }

    def fetch(self) -> List[BidItem]:
        """获取招标信息

        由于该网站API需要认证，当前通过健康检查机制标记状态。
        如果配置中提供了有效的 search_url，则尝试调用。
        """
        if not self._search_url:
            logger.warning(
                f"[{self.display_name}] 未配置有效的API端点。"
                f"该网站为Vue.js SPA，API base为 {self.api_base}。"
                f"需要配置 search_url 指向正确的REST端点。"
                f"当前已跳过该数据源。"
            )
            # 标记为不健康，避免每次运行都尝试
            self.status.record_failure()
            return []

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
            import json
            payload = {
                "keyword": keyword,
                "pageNo": 1,
                "pageSize": 20,
                "type": "bidding",
            }

            html = fetch_page(
                self._search_url,
                method="POST",
                headers=self._get_headers(),
                data=json.dumps(payload),
                proxies=self.proxies,
                timeout=self.timeout,
                raw=True,
            )

            if not html:
                return items

            # 检查401/403
            if "Unauthorized" in html or "Forbidden" in html or "授权" in html:
                logger.warning(f"[{self.name}] API需要认证授权，跳过")
                return items

            try:
                resp_data = json.loads(html)
                records = resp_data.get("data", {}).get("list", resp_data.get("data", {}).get("records", []))
                if isinstance(resp_data.get("data"), list):
                    records = resp_data["data"]
                for record in records:
                    item = self._parse_record(record)
                    if item:
                        items.append(item)
                logger.info(f"  找到 {len(items)} 个结果")
            except json.JSONDecodeError:
                logger.warning(f"[{self.name}] JSON解析失败，响应: {html[:200]}")

        except Exception as e:
            logger.error(f"[{self.name}] 请求失败: {e}")

        return items

    def _parse_record(self, record: dict) -> Optional[BidItem]:
        """解析单条记录"""
        try:
            title = record.get("title", "") or record.get("projectName", "")
            if not title:
                return None

            url = record.get("url", "") or record.get("detailUrl", "")
            pub_date = record.get("publishDate", "") or record.get("createTime", "")

            date_obj = None
            if pub_date:
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        date_obj = datetime.strptime(str(pub_date)[:19], fmt)
                        break
                    except ValueError:
                        continue
            if not date_obj:
                date_obj = datetime.now()

            return BidItem(
                title=title.strip(),
                url=url if url.startswith("http") else f"{self.base_url}{url}",
                date=date_obj.strftime("%Y-%m-%d"),
                source=self.name,
                description=record.get("content", "") or record.get("description", ""),
            )
        except Exception as e:
            logger.error(f"[{self.name}] 解析记录失败: {e}")
            return None
