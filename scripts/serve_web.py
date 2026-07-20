#!/usr/bin/env python
# coding=utf-8
"""
铁塔招标信息 Web 前端

用法:
    python scripts/serve_web.py
    浏览器打开 http://localhost:8080

功能:
    - 展示最近 7 天全国铁塔招标信息
    - 支持标题关键字搜索、公告类型筛选、省份筛选
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "output" / "bidding_history.db"
PORT = 8080

# ---------------------------------------------------------------------------
# 地区映射
# ---------------------------------------------------------------------------

# 省份/直辖市/自治区
PROVINCES = [
    "北京", "上海", "天津", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西", "海南",
    "四川", "贵州", "云南", "西藏",
    "陕西", "甘肃", "青海", "宁夏", "新疆",
    "内蒙古",
]

# 云南地州市 → 云南
YUNNAN_CITIES = [
    "昆明", "曲靖", "玉溪", "保山", "昭通", "丽江",
    "普洱", "临沧", "楚雄", "红河", "文山", "西双版纳",
    "大理", "德宏", "怒江", "迪庆",
]
# ... 其他城市也映射到各自的省份（先只做云南）
CITY_TO_PROVINCE = {c: "云南" for c in YUNNAN_CITIES}

ALL_REGION_KEYWORDS = PROVINCES + YUNNAN_CITIES


def extract_regions(title: str, description: str = "") -> list:
    """从标题和描述中提取所有地区（省份 + 地州市）"""
    text = f"{title} {description}"
    return sorted(set(k for k in ALL_REGION_KEYWORDS if k in text))


def extract_bid_type(description: str, source: str = "") -> str:
    """从描述或来源推断公告类型"""
    m = re.search(r'\[(招标公告|开标记录|评标公示|中标公告|采购公告)\]', description)
    if m:
        return m.group(1)
    if "铁塔电子采购" in source:
        return "采购公告"
    if "乙方宝" in source:
        return "招标公告"
    return ""


# ---------------------------------------------------------------------------
# 数据查询
# ---------------------------------------------------------------------------

def get_items(days: int = 7) -> list:
    """从 SQLite 读取最近 N 天的数据"""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = conn.execute(
        """
        SELECT item_id, title, url, date, source, description
        FROM bid_items
        WHERE date >= ?
        ORDER BY date DESC, created_at DESC
        LIMIT 500
        """,
        (cutoff,)
    ).fetchall()

    items = []
    for r in rows:
        desc = r["description"] or ""
        items.append({
            "id": r["item_id"],
            "title": r["title"],
            "url": r["url"],
            "date": r["date"],
            "source": r["source"],
            "description": desc,
            "bidType": extract_bid_type(desc, r["source"]),
            "regions": extract_regions(r["title"], desc),
        })

    conn.close()
    return items


# ---------------------------------------------------------------------------
# HTML 模板
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>铁塔招标信息</title>
<style>
  :root {
    --bg: #f5f6fa; --card: #fff; --text: #2d3436; --muted: #636e72;
    --border: #dfe6e9; --accent: #0984e3; --shadow: 0 2px 8px rgba(0,0,0,.06);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
  .container { max-width: 960px; margin: 0 auto; padding: 16px; }

  .header { background: linear-gradient(135deg, #0984e3, #6c5ce7); color: #fff; padding: 24px 20px; border-radius: 12px; margin-bottom: 20px; }
  .header h1 { font-size: 22px; margin-bottom: 4px; }
  .header .sub { font-size: 13px; opacity: .85; }

  .stats { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .stat { background: var(--card); border-radius: 10px; padding: 14px 20px; flex: 1; min-width: 130px; box-shadow: var(--shadow); text-align: center; }
  .stat .num { font-size: 28px; font-weight: 700; color: var(--accent); }
  .stat .label { font-size: 12px; color: var(--muted); margin-top: 2px; }

  .search-bar { background: var(--card); border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; box-shadow: var(--shadow); display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .search-bar input, .search-bar select { padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; outline: none; transition: border .2s; }
  .search-bar input:focus, .search-bar select:focus { border-color: var(--accent); }
  .search-bar input { flex: 1; min-width: 180px; }
  .search-bar select { min-width: 120px; }
  .search-bar .count { font-size: 13px; color: var(--muted); margin-left: auto; }

  .date-group { margin-bottom: 20px; }
  .date-header { font-size: 15px; font-weight: 700; color: var(--accent); padding: 8px 0; border-bottom: 2px solid var(--accent); margin-bottom: 8px; display: flex; justify-content: space-between; }
  .date-header .cnt { font-size: 13px; font-weight: 400; color: var(--muted); }

  .item { background: var(--card); border-radius: 10px; padding: 14px 18px; margin-bottom: 8px; box-shadow: var(--shadow); transition: transform .15s; }
  .item:hover { transform: translateX(4px); }
  .item .title { font-size: 15px; font-weight: 600; line-height: 1.5; margin-bottom: 6px; }
  .item .title a { color: var(--text); text-decoration: none; }
  .item .title a:hover { color: var(--accent); }
  .item .meta { display: flex; gap: 10px; flex-wrap: wrap; font-size: 12px; color: var(--muted); align-items: center; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .tag-source { background: #dfe6e9; color: #2d3436; }
  .tag-region { background: #ffeaa7; color: #d63031; }
  .tag-type { background: #81ecec; color: #006266; }

  .empty { text-align: center; padding: 40px; color: var(--muted); font-size: 15px; }

  @media (max-width: 600px) {
    .container { padding: 10px; }
    .header { padding: 16px; }
    .header h1 { font-size: 18px; }
    .search-bar { flex-direction: column; }
    .search-bar input, .search-bar select { width: 100%; }
  }
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>📡 铁塔招标信息</h1>
    <div class="sub">数据来源：中国招标投标公共服务平台 · 中国铁塔电子采购平台 · 乙方宝 ｜ 全国范围 · 最近 7 天</div>
  </div>

  <div class="stats">
    <div class="stat"><div class="num" id="statTotal">-</div><div class="label">总条数</div></div>
    <div class="stat"><div class="num" id="statToday">-</div><div class="label">今日新增</div></div>
    <div class="stat"><div class="num" id="statSources">3</div><div class="label">数据源</div></div>
  </div>

  <div class="search-bar">
    <input type="text" id="searchKeyword" placeholder="🔍 搜索标题关键字..." oninput="doFilter()">
    <select id="searchRegion" onchange="doFilter()">
      <option value="">全部省份</option>
    </select>
    <select id="searchBidType" onchange="doFilter()">
      <option value="">全部类型</option>
      <option value="招标公告">招标公告</option>
      <option value="开标记录">开标记录</option>
      <option value="评标公示">评标公示</option>
      <option value="中标公告">中标公告</option>
      <option value="采购公告">采购公告</option>
    </select>
    <span class="count" id="resultCount"></span>
  </div>

  <div id="list"></div>

</div>

<script>
// 省份列表和城市映射
var PROVINCE_LIST = __PROVINCES__;
var CITY_MAP = __CITY_MAP__;
var ALL_ITEMS = __DATA__;

// 初始化
(function() {
  // 地区下拉：只显示省份
  const sel = document.getElementById('searchRegion');
  PROVINCE_LIST.forEach(function(p) {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p; sel.appendChild(opt);
  });

  // 统计
  document.getElementById('statTotal').textContent = ALL_ITEMS.length;
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('statToday').textContent = ALL_ITEMS.filter(function(i) { return i.date === today; }).length;

  doFilter();
})();

// 检查 item 的地区是否匹配选中的省份
function matchProvince(item, province) {
  var regions = item.regions || [];
  for (var i = 0; i < regions.length; i++) {
    var r = regions[i];
    if (r === province) return true;
    // 如果该地区是选中省份的下属城市
    if (CITY_MAP[r] === province) return true;
  }
  return false;
}

function doFilter() {
  var kw = (document.getElementById('searchKeyword').value || '').trim().toLowerCase();
  var province = document.getElementById('searchRegion').value;
  var bidType = document.getElementById('searchBidType').value;

  var filtered = ALL_ITEMS;
  if (kw) filtered = filtered.filter(function(i) { return i.title.toLowerCase().indexOf(kw) !== -1; });
  if (province) filtered = filtered.filter(function(i) { return matchProvince(i, province); });
  if (bidType) filtered = filtered.filter(function(i) { return i.bidType === bidType; });

  document.getElementById('resultCount').textContent = '共 ' + filtered.length + ' 条';
  render(filtered);
}

function render(items) {
  var container = document.getElementById('list');
  if (!items.length) {
    container.innerHTML = '<div class="empty">😕 没有匹配的招标信息</div>';
    return;
  }

  var groups = {};
  items.forEach(function(i) {
    (groups[i.date] = groups[i.date] || []).push(i);
  });
  var dates = Object.keys(groups).sort().reverse();

  var html = '';
  dates.forEach(function(date) {
    var dayItems = groups[date];
    html += '<div class="date-group">';
    html += '<div class="date-header"><span>📅 ' + date + '</span><span class="cnt">' + dayItems.length + ' 条</span></div>';
    dayItems.forEach(function(item) {
      var regionTags = (item.regions||[]).map(function(r) { return '<span class="tag tag-region">' + esc(r) + '</span>'; }).join(' ');
      var typeTag = item.bidType ? '<span class="tag tag-type">' + esc(item.bidType) + '</span>' : '';
      html += '<div class="item">';
      html += '<div class="title"><a href="' + esc(item.url) + '" target="_blank" rel="noopener">' + esc(item.title) + '</a></div>';
      html += '<div class="meta">' + typeTag + '<span class="tag tag-source">' + esc(item.source) + '</span>' + regionTags;
      if (item.description) html += '<span>' + esc(item.description) + '</span>';
      html += '</div></div>';
    });
    html += '</div>';
  });

  container.innerHTML = html;
}

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# HTTP 服务器
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/items":
            days = int(qs.get("days", [7])[0])
            items = get_items(days)
            body = json.dumps(items, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        items = get_items(7)
        html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False))
        html = html.replace("__PROVINCES__", json.dumps(PROVINCES, ensure_ascii=False))
        html = html.replace("__CITY_MAP__", json.dumps(CITY_TO_PROVINCE, ensure_ascii=False))
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_html(output_path: str = "", days: int = 7) -> str:
    """生成静态 HTML 文件（数据嵌入，无需服务器）"""
    items = get_items(days)
    html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False))
    html = html.replace("__PROVINCES__", json.dumps(PROVINCES, ensure_ascii=False))
    html = html.replace("__CITY_MAP__", json.dumps(CITY_TO_PROVINCE, ensure_ascii=False))

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        print(f"  静态 HTML 已生成: {path} ({len(items)} 条数据)")

    return html


def main():
    import sys

    if "--output" in sys.argv or "-o" in sys.argv:
        # 静态输出模式
        idx = sys.argv.index("--output") if "--output" in sys.argv else sys.argv.index("-o")
        path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "output/index.html"
        days = 7
        if "--days" in sys.argv:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        build_html(path, days)
        return

    print(f"\n  铁塔招标信息 Web 前端")
    print(f"  数据库: {DB_PATH}")
    print(f"  访问地址: http://localhost:{PORT}\n")
    print(f"  按 Ctrl+C 停止\n")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务器已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
