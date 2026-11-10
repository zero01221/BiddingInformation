/* QA 前端契约测试辅助（不是 pytest 用例，供 Python 通过 subprocess 调用）。
 *
 * 在 Node 的 vm 里用最小 DOM stub 真实执行 web/app.js：不启动浏览器、不联网。
 * 用于验证 applyFilters 三类交集、renderDownload L1~L4、URL 白名单、
 * 默认云南优先视图、以及「数据截至超 2 天标黄」等真实前端逻辑。
 *
 * 用法: node frontend_harness.js <app.js 绝对路径> <payload.json 绝对路径>
 * 输出: 单行 JSON。
 */
'use strict';
const fs = require('fs');
const vm = require('vm');

const appJs = fs.readFileSync(process.argv[2], 'utf8');
const payloadText = fs.readFileSync(process.argv[3], 'utf8');

function FakeNode(tag) {
  this.tag = tag;
  this.className = '';
  this.textContent = '';
  this.children = [];
  this.type = '';
  this.title = '';
  this.disabled = false;
  this.hidden = true;   // 初始隐藏：notice 被 showNotice 才会置 false
  this.value = '';
}
FakeNode.prototype.appendChild = function (n) { this.children.push(n); return n; };
FakeNode.prototype.addEventListener = function () {};
FakeNode.prototype.querySelector = function () { return null; };

const nodeCache = {};
const dataNode = new FakeNode('script');
dataNode.textContent = payloadText;
nodeCache.DATA = dataNode;

const listeners = {};
const documentStub = {
  readyState: 'loading',
  hidden: false,
  getElementById: function (id) {
    if (!nodeCache[id]) { nodeCache[id] = new FakeNode('div'); }
    return nodeCache[id];
  },
  createElement: function (tag) { return new FakeNode(tag); },
  addEventListener: function (evt, cb) { listeners[evt] = cb; }
};
const windowStub = {
  location: { href: 'file:///D:/qa/output/index.html' },
  open: function () { return {}; }
};
const navigatorStub = { platform: 'Win32', userAgent: 'QA-Harness' };

const sandbox = {
  document: documentStub,
  window: windowStub,
  navigator: navigatorStub,
  URL: URL,
  console: console,
  encodeURIComponent: encodeURIComponent
};
vm.createContext(sandbox);
vm.runInContext(appJs, sandbox, { filename: 'app.js' });

// app.js 在 readyState=loading 时只注册回调；手动触发以执行完整初始化渲染
if (typeof listeners.DOMContentLoaded === 'function') {
  listeners.DOMContentLoaded();
}

const api = sandbox.window.BiddingApp;
if (!api) { throw new Error('window.BiddingApp 未暴露，无法做前端契约断言'); }

function ids(items) { return items.map(function (i) { return i.id; }); }
function flattenText(node) {
  let s = node && node.textContent ? String(node.textContent) : '';
  const kids = node && node.children ? node.children : [];
  kids.forEach(function (c) { s += flattenText(c); });
  return s;
}
function inspectDownload(item) {
  const wrap = api.renderDownload(item);
  const btn = wrap.children.find(function (c) { return c.tag === 'button'; });
  const hints = wrap.children.filter(function (c) {
    return c.className && String(c.className).indexOf('hint') >= 0;
  }).map(function (c) { return c.textContent; });
  const tier = wrap.children.find(function (c) {
    return c.className && String(c.className).indexOf('tier') === 0;
  });
  return {
    buttonText: btn ? btn.textContent : null,
    disabled: btn ? btn.disabled : null,
    title: btn ? btn.title : null,
    tier: tier ? tier.textContent : null,
    hints: hints
  };
}

const F = api.applyFilters;
const out = {
  total: api.items.length,
  filters: {
    all: ids(F({})),
    yunnan: ids(F({ province: '云南' })),
    shandong: ids(F({ province: '山东' })),
    keywordTower: ids(F({ keyword: '铁塔' })),
    keywordKunming: ids(F({ keyword: '昆明' })),
    dateRange: ids(F({ dateFrom: '2026-07-25', dateTo: '2026-08-02' })),
    intersection: ids(F({ province: '云南', keyword: '铁塔',
                           dateFrom: '2026-07-25', dateTo: '2026-08-02' })),
    partialIntersection: ids(F({ province: '云南',
                                 dateFrom: '2026-07-25', dateTo: '2026-08-02' })),
    invalidRange: ids(F({ dateFrom: '2026-08-02', dateTo: '2026-07-25' }))
  },
  download: {
    L4: inspectDownload({ id: 'DL4', title: '无附件公告', download_level: 'L4',
      download: { level: 'L4', url: '', enabled: false, filename: '',
                  note: '该来源不提供下载，请前往出处查看' } }),
    L1: inspectDownload({ id: 'DL1', title: '原始文件公告',
      download: { level: 'L1', url: 'https://example.com/a.pdf', enabled: true,
                  filename: 'a.pdf', note: '原始文件' } }),
    L2: inspectDownload({ id: 'DL2', title: '副本公告',
      download: { level: 'L2', url: 'attachments/a.pdf', enabled: true,
                  filename: 'a.pdf', note: '源文件副本' } }),
    L3: inspectDownload({ id: 'DL3', title: '快照公告',
      download: { level: 'L3', url: 'snapshots/a.html', enabled: true,
                  filename: 'a.html', note: '原站未提供文件下载，以下为详情页快照' } })
  },
  safeHttp: {
    http: api.isSafeHttp('http://a.com/x'),
    https: api.isSafeHttp('https://a.com/x'),
    javascript: api.isSafeHttp('javascript:alert(1)'),
    data: api.isSafeHttp('data:text/html,x'),
    file: api.isSafeHttp('file:///etc/passwd'),
    empty: api.isSafeHttp('')
  },
  safeAsset: {
    snapshot: api.isSafeAsset('snapshots/a.html'),
    attachment: api.isSafeAsset('attachments/a.pdf'),
    traversal: api.isSafeAsset('../etc/passwd'),
    javascript: api.isSafeAsset('javascript:alert(1)')
  },
  rfc5987: api.encodeRFC5987('招标文件.pdf'),
  metaBarText: flattenText(nodeCache.metaBar || new FakeNode('div')),
  noticeText: (nodeCache.notice || {}).textContent || '',
  noticeClass: (nodeCache.notice || {}).className || '',
  noticeHidden: (nodeCache.notice || {}).hidden,
  regionValue: (nodeCache.fRegion || {}).value || '',
  regionOptions: nodeCache.fRegion
    ? nodeCache.fRegion.children.map(function (o) { return { text: o.textContent, value: o.value }; })
    : [],
  healthBarText: flattenText(nodeCache.healthBar || new FakeNode('div'))
};
process.stdout.write(JSON.stringify(out));
