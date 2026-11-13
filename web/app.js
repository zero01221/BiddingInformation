/* 铁塔招标信息 · 离线页面逻辑
 * 原生 ES2015，零框架、零 CDN、零外部请求；数据来自页面内联的 JSON。
 * 渲染一律使用 createElement + textContent，不拼接 HTML 字符串（防 XSS）。
 * 三类筛选（地区 / 日期区间 / 文件名）取交集；公告类型只作标签，不设筛选控件。
 */
(function () {
  'use strict';

  var PLACEHOLDER = '—';
  var LEVELS = ['L1', 'L2', 'L3', 'L4'];

  // ------------------------------------------------------------------
  // 数据装载
  // ------------------------------------------------------------------
  function loadPayload() {
    var node = document.getElementById('DATA');
    if (!node) {
      return { meta: { load_error: '缺少内联数据节点' }, items: [], source_health: [], run_status: [] };
    }
    try {
      return JSON.parse(node.textContent || '');
    } catch (err) {
      return { meta: { load_error: String(err) }, items: [], source_health: [], run_status: [] };
    }
  }

  var PAYLOAD = loadPayload();
  var META = PAYLOAD.meta || {};
  var ITEMS = Array.isArray(PAYLOAD.items) ? PAYLOAD.items : [];
  var HEALTH = Array.isArray(PAYLOAD.source_health) ? PAYLOAD.source_health : [];
  var RUN_STATUS = Array.isArray(PAYLOAD.run_status) ? PAYLOAD.run_status : [];
  var REGIONS = META.regions || {};
  var PROVINCES = Array.isArray(REGIONS.provinces) ? REGIONS.provinces : [];
  var CITY_MAP = REGIONS.city_to_province || {};
  var TIERS = META.tiers || {};
  var PREFIX = META.asset_prefix || '';
  var STALE_DAYS = Number(META.stale_days || 2);
  var DEFAULT_VIEW = META.default_view || '云南';
  // 已选地区（OR 语义）。空数组 = 全部（全国）；默认云南优先。
  var SELECTED_REGIONS = [];

  // ------------------------------------------------------------------
  // DOM / 安全工具
  // ------------------------------------------------------------------
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (arguments.length >= 3) { node.textContent = String(text); }
    return node;
  }

  function safeValue(value, fallback) {
    if (value === null || value === undefined || value === '') {
      return fallback || PLACEHOLDER;
    }
    return String(value);
  }

  function fieldSpan(label, value) {
    var span = el('span', 'field');
    span.appendChild(el('span', 'field-label', label + '：'));
    span.appendChild(el('span', 'field-value', String(value)));
    return span;
  }

  function pair(container, label, value) {
    var box = el('span', 'pair');
    box.appendChild(el('span', 'pair-label', label));
    box.appendChild(el('span', 'pair-value', String(value)));
    container.appendChild(box);
  }

  /** URL 白名单：仅 http/https，非法链接按钮禁用。 */
  function isSafeHttp(url) {
    if (!url) { return false; }
    try {
      var parsed = new URL(String(url), window.location.href);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch (err) {
      return false;
    }
  }

  /** 本地产物路径白名单：只允许 attachments/ 与 snapshots/ 下的相对路径。 */
  function isSafeAsset(rel) {
    if (!rel) { return false; }
    var value = String(rel);
    if (value.indexOf('..') !== -1) { return false; }
    var lower = value.toLowerCase();
    if (lower.indexOf('javascript:') === 0 || lower.indexOf('data:') === 0 || lower.indexOf('file:') === 0) {
      return false;
    }
    return (
      lower.indexOf('attachments/') === 0 || lower.indexOf('snapshots/') === 0 ||
      lower.indexOf('./attachments/') === 0 || lower.indexOf('./snapshots/') === 0
    );
  }

  /** 加上产物相对前缀：output/ 根目录为 ""，win/ mac/ 子目录为 "../"。 */
  function assetUrl(rel) {
    return PREFIX + String(rel).replace(/^\.\//, '');
  }

  function isMac() {
    return /Mac|iPhone|iPad|iPod/i.test(String(navigator.platform || navigator.userAgent || ''));
  }

  /** RFC 5987 编码，供在线部署的 Content-Disposition 与另存为提示使用。 */
  function encodeRFC5987(name) {
    return "UTF-8''" + encodeURIComponent(String(name));
  }

  function safeFilename(name, fallback) {
    var cleaned = String(name || '')
      .replace(/[\\/:*?"<>|\r\n\t]/g, '_')
      .slice(0, 120)
      .trim();
    return cleaned || String(fallback || 'bidding-document');
  }

  function appendHint(wrap, message) {
    var old = wrap.querySelector('.dl-feedback');
    if (old && old.parentNode) { old.parentNode.removeChild(old); }
    wrap.appendChild(el('span', 'hint dl-feedback', message));
  }

  function showNotice(message, kind) {
    var notice = document.getElementById('notice');
    notice.textContent = String(message);
    notice.className = 'notice notice-' + (kind || 'info');
    notice.hidden = false;
  }

  function todayString() {
    var d = new Date();
    function pad(n) { return n < 10 ? '0' + n : String(n); }
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function daysSince(dateText) {
    var parts = String(dateText || '').slice(0, 10).split('-');
    if (parts.length !== 3) { return 0; }
    var target = Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var nowParts = todayString().split('-');
    var now = Date.UTC(Number(nowParts[0]), Number(nowParts[1]) - 1, Number(nowParts[2]));
    return Math.floor((now - target) / 86400000);
  }

  // ------------------------------------------------------------------
  // 筛选（三类取交集）
  // ------------------------------------------------------------------
  function matchRegion(item, province) {
    if (!province) { return true; }
    if (item.province === province) { return true; }
    var regions = Array.isArray(item.regions) ? item.regions : [];
    for (var i = 0; i < regions.length; i++) {
      if (regions[i] === province) { return true; }
      if (CITY_MAP[regions[i]] === province) { return true; }
    }
    return false;
  }

  /** 多地区 OR：命中任一已选地区即通过；空数组表示不过滤（全国）。 */
  function matchAnyRegion(item, provinces) {
    if (!provinces || !provinces.length) { return true; }
    for (var i = 0; i < provinces.length; i++) {
      if (matchRegion(item, provinces[i])) { return true; }
    }
    return false;
  }

  /** 规范化地区选择：接受数组或单值，去空、去重、保持顺序。 */
  function normalizeProvinces(value) {
    var raw = Array.isArray(value) ? value : (value ? [value] : []);
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var name = String(raw[i] || '').trim();
      if (name && name !== '全部（全国）' && out.indexOf(name) === -1) { out.push(name); }
    }
    return out;
  }

  /**
   * 按 state = {keyword, provinces | province, dateFrom, dateTo} 过滤，返回交集结果。
   * ``provinces`` 为数组时按 OR 匹配；保留 ``province`` 单值以兼容既有调用。
   */
  function applyFilters(state) {
    var s = state || {};
    var keyword = String(s.keyword || '').trim().toLowerCase();
    var provinces = normalizeProvinces(
      s.provinces !== undefined ? s.provinces : s.province
    );
    var from = s.dateFrom || '';
    var to = s.dateTo || '';
    return ITEMS.filter(function (item) {
      if (keyword && String(item.title || '').toLowerCase().indexOf(keyword) === -1) { return false; }
      if (!matchAnyRegion(item, provinces)) { return false; }
      if (from || to) {
        var date = String(item.date || '');
        if (!date) { return false; }
        if (from && date < from) { return false; }
        if (to && date > to) { return false; }
      }
      if (!dateFilterValid(from, to)) { return false; }
      return true;
    });
  }

  function dateFilterValid(from, to) {
    return !(from && to && from > to);
  }

  /** 起始 / 结束日期互斥约束：用 min/max 让原生日期控件直接禁止非法选择。 */
  function syncDateBounds() {
    var fromEl = document.getElementById('fDateFrom');
    var toEl = document.getElementById('fDateTo');
    var from = fromEl.value || '';
    var to = toEl.value || '';
    toEl.min = from;
    fromEl.max = to;
  }

  /**
   * 修正非法区间：起始晚于结束时，把结束日期对齐到起始日期并给出明确提示。
   * 返回 true 表示区间合法；false 表示已自动纠正（调用方仍可继续渲染）。
   */
  function normalizeDateRange(announce) {
    var fromEl = document.getElementById('fDateFrom');
    var toEl = document.getElementById('fDateTo');
    var from = fromEl.value || '';
    var to = toEl.value || '';
    if (from && to && from > to) {
      toEl.value = from;
      syncDateBounds();
      if (announce !== false) {
        showNotice('起始日期不能晚于结束日期，已自动将结束日期调整为 ' + from, 'error');
      }
      return false;
    }
    syncDateBounds();
    return true;
  }

  // ------------------------------------------------------------------
  // 下载降级 L1~L4
  // ------------------------------------------------------------------
  function triggerDownload(url, filename, level, wrap) {
    var target;
    if (isSafeHttp(url)) {
      target = String(url);
    } else if (isSafeAsset(url)) {
      target = assetUrl(url);
    } else {
      appendHint(wrap, '下载链接不可用，请点击「跳转出处」查看原文');
      return;
    }

    if (isMac()) {
      // Safari 对 download 属性支持有差异：降级为新标签打开 + 明确另存为引导。
      // 中文名用 UTF-8 原文，并附 RFC 5987 编码供「存储为」时参考，避免乱码。
      var opened = window.open(target, '_blank', 'noopener,noreferrer');
      if (!opened) {
        appendHint(wrap, '浏览器阻止了新标签，请允许弹出窗口后重试，或点击「跳转出处」');
        return;
      }
      appendHint(wrap, '已在新标签打开。请在菜单「文件 → 存储为」保存，建议文件名：' + filename +
        '（UTF-8 filename*: ' + encodeRFC5987(filename) + '）');
      return;
    }

    // Windows Chrome/Edge：download 属性带中文名，现代浏览器按 UTF-8 处理不乱码。
    // 说明：file:// 下 fetch 本地相对路径会被 CORS 拦截，故不采用 fetch+Blob 重命名，
    // 直接用 download 属性，行为确定、无静默失败。
    var link = document.createElement('a');
    link.href = target;
    link.download = filename;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    appendHint(wrap, '已开始下载：' + filename + (level === 'L3' ? '（详情页快照）' : ''));
  }

  /** 返回该条公告的下载区 DOM 节点（L4 时按钮禁用且明确提示）。 */
  function renderDownload(item) {
    var wrap = el('div', 'download');
    var dl = item.download || {};
    var level = dl.level || item.download_level || 'L4';
    if (LEVELS.indexOf(level) === -1) { level = 'L4'; }
    var note = dl.note || TIERS[level] || '';

    wrap.appendChild(el('span', 'tier tier-' + level, level + ' · ' + safeValue(note, '未标注')));

    var button = el('button', 'btn btn-download', level === 'L4' ? '无法下载' : '下载源招标文件');
    button.type = 'button';
    var url = dl.url || (level === 'L3' ? item.snapshot_url : item.attachment_url) || '';
    var filename = safeFilename(dl.filename || item.title, item.dedup_key);
    var enabled = !!dl.enabled && level !== 'L4' && !!url;

    if (!enabled) {
      // L4：不得伪造文件、不得给出 404 链接，按钮禁用并引导出处
      button.disabled = true;
      button.title = note || TIERS.L4 || '该来源不提供下载';
      wrap.appendChild(button);
      wrap.appendChild(el('span', 'hint', note || TIERS.L4 || '该来源不提供下载，请前往出处查看'));
      return wrap;
    }

    button.addEventListener('click', function () {
      triggerDownload(url, filename, level, wrap);
    });
    wrap.appendChild(button);
    if (level === 'L3') {
      wrap.appendChild(el('span', 'hint', note));
    }
    return wrap;
  }

  function renderOrigin(item) {
    var url = item.url || item.original_url || '';
    if (!isSafeHttp(url)) {
      var disabled = el('button', 'btn btn-origin', '出处不可用');
      disabled.type = 'button';
      disabled.disabled = true;
      disabled.title = '原文链接缺失或不安全';
      return disabled;
    }
    var link = el('a', 'btn btn-origin', '跳转出处');
    link.href = String(url);
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }

  // ------------------------------------------------------------------
  // 列表渲染
  // ------------------------------------------------------------------
  function renderItem(item) {
    var card = el('article', 'item');
    card.appendChild(el('h3', 'item-title', safeValue(item.title, '（无标题）')));

    var meta = el('div', 'item-meta');
    meta.appendChild(fieldSpan('日期', item.date || '暂无日期'));
    meta.appendChild(fieldSpan('来源', item.source || '暂无来源'));
    if (item.bid_type) { meta.appendChild(el('span', 'tag tag-type', String(item.bid_type))); }
    var regions = Array.isArray(item.regions) ? item.regions : [];
    regions.forEach(function (region) {
      meta.appendChild(el('span', 'tag tag-region', String(region)));
    });
    if (item.date_valid === 0) { meta.appendChild(el('span', 'tag tag-warn', '日期待核实')); }
    card.appendChild(meta);

    // 四字段中的摘要：缺失时显示明确占位
    card.appendChild(el('p', 'item-desc', safeValue(item.description, '暂无摘要')));

    var actions = el('div', 'item-actions');
    actions.appendChild(renderOrigin(item));
    actions.appendChild(renderDownload(item));
    card.appendChild(actions);
    return card;
  }

  function render(items) {
    var container = document.getElementById('list');
    container.textContent = '';
    if (!items.length) {
      container.appendChild(el('div', 'empty', '没有匹配的招标信息，试试放宽筛选条件'));
      return;
    }
    var groups = {};
    items.forEach(function (item) {
      var date = String(item.date || '未知日期');
      if (!groups[date]) { groups[date] = []; }
      groups[date].push(item);
    });
    Object.keys(groups).sort().reverse().forEach(function (date) {
      var section = el('section', 'date-group');
      var head = el('div', 'date-head');
      head.appendChild(el('span', 'date-label', date));
      head.appendChild(el('span', 'date-count', groups[date].length + ' 条'));
      section.appendChild(head);
      groups[date].forEach(function (item) { section.appendChild(renderItem(item)); });
      container.appendChild(section);
    });
  }

  function renderStats(filtered) {
    var bar = document.getElementById('statsBar');
    bar.textContent = '';
    pair(bar, '当前结果', filtered.length + ' 条');
    pair(bar, '全部数据', ITEMS.length + ' 条');
    var counts = { L1: 0, L2: 0, L3: 0, L4: 0 };
    ITEMS.forEach(function (item) {
      var level = (item.download && item.download.level) || item.download_level || 'L4';
      if (counts[level] !== undefined) { counts[level] += 1; }
    });
    LEVELS.forEach(function (level) { pair(bar, level, counts[level] + ' 条'); });
  }

  function renderMeta() {
    var bar = document.getElementById('metaBar');
    bar.textContent = '';
    pair(bar, '数据更新时间', safeValue(META.generated_at, '未知'));
    pair(bar, '数据截至', safeValue(META.data_as_of, '暂无'));
    pair(bar, '总条数', ITEMS.length + ' 条');
    pair(bar, '当前平台', isMac() ? 'macOS' : 'Windows');
  }

  function renderHealth() {
    var bar = document.getElementById('healthBar');
    bar.textContent = '';
    bar.appendChild(el('strong', 'health-title', '数据源状态'));
    if (RUN_STATUS.length) {
      RUN_STATUS.forEach(function (status) {
        var ok = !!status.healthy && !status.last_error;
        bar.appendChild(el('span', 'health ' + (ok ? 'health-ok' : 'health-bad'),
          (ok ? '✓ ' : '✗ ') + safeValue(status.name, '未知源') + '：' +
          (status.total_items || 0) + ' 条' +
          (status.last_error ? ' / ' + status.last_error : '')));
      });
    } else if (HEALTH.length) {
      HEALTH.forEach(function (health) {
        bar.appendChild(el('span', 'health',
          safeValue(health.source, '未知源') + '：' + (health.item_count || 0) +
          ' 条，最晚 ' + safeValue(health.latest_date, '—')));
      });
    } else {
      bar.appendChild(el('span', 'health', '暂无数据源信息'));
    }
  }

  function renderNotices() {
    if (META.load_error) {
      showNotice('内联数据解析失败：' + META.load_error, 'error');
      return;
    }
    if (META.degraded) {
      showNotice(safeValue(META.degraded_reason, '本次采集失败，以下为历史数据'), 'warn');
      return;
    }
    var asOf = String(META.data_as_of || '');
    var age = asOf ? daysSince(asOf) : 0;
    if (age > STALE_DAYS) {
      showNotice('数据截至 ' + asOf + '，已超过 ' + STALE_DAYS +
        ' 天未更新。请双击「更新数据」后刷新本页。', 'warn');
    }
  }

  // ------------------------------------------------------------------
  // 初始化与事件绑定
  // ------------------------------------------------------------------
  function currentState() {
    return {
      keyword: document.getElementById('fTitle').value,
      provinces: SELECTED_REGIONS.slice(),
      dateFrom: document.getElementById('fDateFrom').value,
      dateTo: document.getElementById('fDateTo').value
    };
  }

  function refresh() {
    var filtered = applyFilters(currentState());
    renderStats(filtered);
    render(filtered);
  }

  /** 地区多选：折叠面板 + 复选框，空选择 = 全部（全国）。 */
  function regionToggleLabel() {
    if (!SELECTED_REGIONS.length) { return '全部（全国）'; }
    if (SELECTED_REGIONS.length === 1) { return SELECTED_REGIONS[0]; }
    return SELECTED_REGIONS[0] + ' 等 ' + SELECTED_REGIONS.length + ' 个地区';
  }

  function renderRegionToggle() {
    document.getElementById('fRegionToggle').textContent = regionToggleLabel();
  }

  /** 同步面板内所有复选框的勾选态（含「全部（全国）」互斥项）。 */
  function syncRegionBoxes() {
    var optionsBox = document.getElementById('fRegionOptions');
    var labels = optionsBox.children || [];
    for (var i = 0; i < labels.length; i++) {
      var kids = labels[i].children || [];
      for (var j = 0; j < kids.length; j++) {
        var box = kids[j];
        if (box.tag !== 'input') { continue; }
        box.checked = box.value === ''
          ? SELECTED_REGIONS.length === 0
          : SELECTED_REGIONS.indexOf(box.value) !== -1;
      }
    }
  }

  function setRegions(next) {
    SELECTED_REGIONS = normalizeProvinces(next);
    renderRegionToggle();
    syncRegionBoxes();
    refresh();
  }

  function initRegionPicker() {
    var optionsBox = document.getElementById('fRegionOptions');
    optionsBox.textContent = '';

    function addOption(name) {
      var label = el('label', 'region-option');
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = String(name);
      box.checked = SELECTED_REGIONS.indexOf(name) !== -1;
      box.addEventListener('change', function () {
        var next = SELECTED_REGIONS.slice();
        var at = next.indexOf(name);
        if (box.checked && at === -1) { next.push(name); }
        if (!box.checked && at !== -1) { next.splice(at, 1); }
        setRegions(next);
      });
      label.appendChild(box);
      label.appendChild(el('span', '', String(name)));
      optionsBox.appendChild(label);
    }

    // 「全部（全国）」作为第一项：勾选即清空选择，语义等价于不过滤。
    var allLabel = el('label', 'region-option region-option-all');
    var allBox = document.createElement('input');
    allBox.type = 'checkbox';
    allBox.value = '';
    allBox.checked = SELECTED_REGIONS.length === 0;
    allBox.addEventListener('change', function () {
      // 勾选 = 全国（空选择）；取消勾选 = 回到默认云南视图，避免出现「无选择但显示为全国」。
      setRegions(allBox.checked ? [] : (PROVINCES.indexOf(DEFAULT_VIEW) >= 0 ? [DEFAULT_VIEW] : []));
    });
    allLabel.appendChild(allBox);
    allLabel.appendChild(el('span', '', '全部（全国）'));
    optionsBox.appendChild(allLabel);

    PROVINCES.forEach(addOption);
    renderRegionToggle();
  }

  function bindEvents() {
    ['fDateFrom', 'fDateTo', 'fTitle'].forEach(function (id) {
      var node = document.getElementById(id);
      node.addEventListener('change', function () {
        normalizeDateRange();
        refresh();
      });
      node.addEventListener('input', refresh);
    });
    document.getElementById('fRegionToggle').addEventListener('click', function () {
      var panel = document.getElementById('fRegionPanel');
      panel.hidden = !panel.hidden;
    });
    document.getElementById('fRegionAll').addEventListener('click', function () {
      setRegions([]);
    });
    document.getElementById('fRegionYunnan').addEventListener('click', function () {
      setRegions(PROVINCES.indexOf(DEFAULT_VIEW) >= 0 ? [DEFAULT_VIEW] : []);
    });
    document.getElementById('fReset').addEventListener('click', function () {
      document.getElementById('fTitle').value = '';
      document.getElementById('fDateFrom').value = '';
      document.getElementById('fDateTo').value = '';
      syncDateBounds();
      setRegions(PROVINCES.indexOf(DEFAULT_VIEW) >= 0 ? [DEFAULT_VIEW] : []);
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { return; }
      var notice = document.getElementById('notice');
      if (notice.hidden) {
        showNotice('页面已恢复显示 · 数据截至 ' + safeValue(META.data_as_of, '未知') +
          '。离线文件不会自动更新，如需最新数据请双击「更新数据」后刷新本页。', 'info');
      }
    });
  }

  function init() {
    SELECTED_REGIONS = PROVINCES.indexOf(DEFAULT_VIEW) >= 0 ? [DEFAULT_VIEW] : [];
    renderMeta();
    renderNotices();
    renderHealth();
    initRegionPicker();
    bindEvents();
    syncDateBounds();
    refresh();
  }

  // 暴露给调试与自动化测试（QA 阶段可直接在页面上下文调用）
  window.applyFilters = applyFilters;
  window.renderDownload = renderDownload;
  window.BiddingApp = {
    applyFilters: applyFilters,
    renderDownload: renderDownload,
    matchRegion: matchRegion,
    matchAnyRegion: matchAnyRegion,
    normalizeProvinces: normalizeProvinces,
    normalizeDateRange: normalizeDateRange,
    syncDateBounds: syncDateBounds,
    dateFilterValid: dateFilterValid,
    setRegions: setRegions,
    isSafeHttp: isSafeHttp,
    isSafeAsset: isSafeAsset,
    encodeRFC5987: encodeRFC5987,
    refresh: refresh,
    items: ITEMS,
    meta: META,
    selectedRegions: function () { return SELECTED_REGIONS.slice(); }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
