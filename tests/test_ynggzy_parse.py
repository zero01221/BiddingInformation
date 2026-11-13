"""云南源字段解析回归（离线，不联网）。

2026-11-13 实测云南省公共资源交易中心接口后补齐字段回退链：
主键 guid、公告时间 bulletinissuetime、地区 areaName。
"""

from scripts.bidding_scraper.crawlers.ynggzy import YnggzyCrawler


def _crawler(app_config) -> YnggzyCrawler:
    return YnggzyCrawler({
        "api_url": "https://ggzy.yn.gov.cn/ynggfwpt-home-api/jyzyCenter/jyInfo/gcjs/getZbggList",
        "name": "云南省公共资源交易中心",
    })


def test_real_api_fields_are_parsed(app_config):
    """实测返回结构：guid / bulletinissuetime / areaName。"""
    row = {
        "bulletinname": "中国铁塔股份有限公司云南分公司基站施工招标公告",
        "guid": "1d2dae7f-d3b1-40ef-a7b4-38aa90e31899",
        "bulletinissuetime": "2026-11-13",
        "areaName": "昆明市",
        "jyptid": "昆明市",
        "url": None,
    }
    item = _crawler(app_config)._parse_row(row, "gcjs")
    assert item is not None
    assert item.date == "2026-11-13"
    assert item.native_id == row["guid"]
    assert f"id={row['guid']}" in item.url
    assert item.description == "昆明市"
    assert item.bid_type == "招标公告"


def test_legacy_fields_still_work(app_config):
    """旧字段 releasetime / publishdate / bulletinid 仍可回退。"""
    row = {
        "bulletinname": "中国铁塔塔桅采购公告",
        "bulletinid": "legacy-001",
        "releasetime": "2026-11-10",
        "areaname": "曲靖市",
    }
    item = _crawler(app_config)._parse_row(row, "gcjs")
    assert item.date == "2026-11-10"
    assert item.native_id == "legacy-001"
    assert "id=legacy-001" in item.url
    assert item.description == "曲靖市"


def test_source_url_takes_priority(app_config):
    """源站给出真实详情 URL 时优先使用，避免出现空的 id= 链接。"""
    row = {
        "bulletinname": "中国铁塔维护项目招标公告",
        "guid": "abc",
        "bulletinissuetime": "2026-11-12",
        "url": "https://ggzy.yn.gov.cn/detail/abc",
    }
    item = _crawler(app_config)._parse_row(row, "gcjs")
    assert item.url == "https://ggzy.yn.gov.cn/detail/abc"
    assert item.original_url == item.url


def test_missing_title_returns_none(app_config):
    assert _crawler(app_config)._parse_row({"guid": "x"}, "gcjs") is None
