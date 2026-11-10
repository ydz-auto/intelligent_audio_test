# -*- coding: utf-8 -*-
"""INT-2434 验收探针：报告 HTML 快照产物必须保留「本页目录」+ 轮次/维度/目标 Tab + 可展开的用例详情。

背景（负责人 2026-11-10 实测）：INT-2418 的 DOM 快照管线把 `aside`（本页目录容器）与所有
`<button>`（含 `<button role="tab">`）整块剪掉 → 产物里目录和轮次/维度/目标切换全丢，用例详情
默认折叠且展开入口只有图标。

本探针在 `file://` 打开的产物上断言（无任何 http(s) 请求）：
  1) `nav[aria-label="本页目录"]` 存在，锚点与产物内分区 id 一一对应；且是与报告页同形的
     **右栏视口固定**导航（`position: sticky`、在正文右栏、滚动后仍在视口内、高亮跟随）；
  2) `[role="tab"]` 数量 > 0，点击轮次 Tab 后对应用例卡内容区文本变化（纯 DOM 切换真实生效）；
  3) `[data-export-case-detail]` 数量 = 用例卡数，点击展开入口后可见（高度 > 0）；
  4) 产物仍满足 INT-2418 口径（zip 内 report.html + css/report.css、无操作按钮残留、浅色固定）。

跑法：
  python tests/ui/probe_int2434_case_tabs_toc.py --base http://localhost:5373 --reports 383,395
  （登录账号走 UI_TEST_USERNAME / UI_TEST_PASSWORD，docker 栈用 dev_user / dev_password）
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2434')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'reports': [], 'notes': []}


def log(msg):
    print('[int2434] %s' % msg, flush=True)


# ---- 产物页断言（在 file:// 页面上执行） ----
JS_TOC = """
var nav = document.querySelector('nav[aria-label="本页目录"]');
if (!nav) return {ok: false, reason: 'no toc nav'};
var links = Array.prototype.map.call(nav.querySelectorAll('a'), function (a) {
  return a.getAttribute('href') || '';
});
var missing = links.filter(function (href) {
  if (!href || href.charAt(0) !== '#' || href.length < 2) return true;
  return !document.getElementById(href.slice(1));
});
var sections = Array.prototype.map.call(document.querySelectorAll('section[id]'), function (s) {
  return '#' + s.id;
});
return {
  ok: links.length > 0 && missing.length === 0 && links.length === sections.length,
  link_count: links.length,
  section_count: sections.length,
  links: links,
  missing: missing
};
"""

JS_TOC_FIXED = """
// 负责人 2026-11-10 补充：要的是「视口固定显示」的右导航（报告页 ReportReadingNav 同形），
// 不是页顶横条 —— 断言 sticky 生效、在正文右栏、滚动后仍在视口内、高亮与进度条跟随。
var nav = document.querySelector('nav[aria-label="本页目录"]');
if (!nav) return {ok: false, reason: 'no toc nav'};
var aside = nav.closest('[data-export-toc-aside]');
var main = document.querySelector('[data-export-layout] > main');
var style = window.getComputedStyle(nav);
var links = Array.prototype.slice.call(nav.querySelectorAll('[data-export-toc-link]'));
function activeIndex() {
  var cur = nav.querySelector('[data-export-toc-link][aria-current="location"]');
  return cur ? links.indexOf(cur) : -1;
}
function progressWidth() {
  var prog = nav.querySelector('[data-export-toc-progress]');
  return prog ? prog.style.width : null;
}
window.scrollTo(0, 0);
window.dispatchEvent(new Event('scroll'));
var rect0 = nav.getBoundingClientRect();
var mainRect = main ? main.getBoundingClientRect() : null;
var res = {
  position: style.position,
  has_aside: !!aside,
  right_of_main: mainRect ? rect0.left >= mainRect.right - 2 : null,
  top_before: Math.round(rect0.top),
  labels: links.map(function (a) { return a.textContent; }),
  active_top: activeIndex(),
  progress_top: progressWidth()
};
window.scrollTo(0, Math.max(0, document.documentElement.scrollHeight - window.innerHeight - 40));
window.dispatchEvent(new Event('scroll'));
var rect1 = nav.getBoundingClientRect();
res.scroll_y = Math.round(window.scrollY || 0);
res.top_after_scroll = Math.round(rect1.top);
res.visible_after_scroll = rect1.height > 0 && rect1.bottom > 0 && rect1.top < window.innerHeight;
res.active_bottom = activeIndex();
res.progress_bottom = progressWidth();
res.ok = res.position === 'sticky' && res.has_aside && res.right_of_main !== false
  && res.visible_after_scroll && res.active_top === 0
  && res.active_bottom > res.active_top
  && res.progress_top !== res.progress_bottom;
return res;
"""

JS_TOC_CLICK_JUMP = """
// 点目录第一条锚点：平滑滚动后该分区进入视口（file:// 下纯 DOM 跳转）
var nav = document.querySelector('nav[aria-label="本页目录"]');
if (!nav) return {ok: false, reason: 'no toc nav'};
var link = nav.querySelector('[data-export-toc-link]');
var id = link ? (link.getAttribute('data-export-toc-link') || '') : '';
var target = id ? document.getElementById(id) : null;
if (!target) return {ok: false, reason: 'no target', id: id};
var rect = target.getBoundingClientRect();
var active = nav.querySelector('[data-export-toc-link][aria-current="location"]');
return {
  ok: rect.top >= -8 && rect.top <= 200 && active === link,
  id: id,
  target_top: Math.round(rect.top),
  scroll_y: Math.round(window.scrollY || 0),
  active: active ? active.textContent : null
};
"""

JS_TABS = """
var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
if (tabs.length === 0) return {ok: false, reason: 'no tab buttons'};
var roundBtns = tabs.filter(function (b) {
  return (b.getAttribute('data-export-tab') || '').indexOf('-round:') >= 0;
});
var result = {
  ok: roundBtns.length > 0,
  tab_count: tabs.length,
  tablists: document.querySelectorAll('[role="tablist"]').length,
  round_tabs: roundBtns.length
};
if (roundBtns.length < 2) {
  result.ok = tabs.length > 0;
  result.change = 'skipped: 本报告该用例卡无多轮 Tab';
  return result;
}
var group = (roundBtns[0].getAttribute('data-export-tab') || '').split(':')[0];
var same = roundBtns.filter(function (b) {
  return (b.getAttribute('data-export-tab') || '').split(':')[0] === group;
});
if (same.length < 2) { result.ok = false; result.change = 'group tabs < 2'; return result; }
var card = same[0].closest('[data-export-case]');

// 可见内容指纹：只取未被导出脚本隐藏的轮次行 / tbody 的文本（textContent 会带上隐藏行，不能用来判变化）
function visibleRoundText(root) {
  return Array.prototype.filter.call(root.querySelectorAll('[data-export-round]'), function (el) {
    return el.style.display !== 'none';
  }).map(function (el) { return el.textContent; }).join('');
}

var before = visibleRoundText(card);
var target = same.filter(function (b) {
  return b.getAttribute('aria-selected') !== 'true';
})[0] || same[1];
target.click();
var after = visibleRoundText(card);
result.selected_after = target.getAttribute('aria-selected');
result.content_changed = before !== after;
result.before_len = before.length;
result.after_len = after.length;
result.visible_round_rows = Array.prototype.filter.call(
  card.querySelectorAll('[data-export-round]'),
  function (el) { return el.style.display !== 'none'; }).length;
result.ok = tabs.length > 0 && result.content_changed;
return result;
"""

JS_CLICK_FIRST_ROUND_BACK = """
var btn = document.querySelector('[data-export-tab*="-round:"]');
return btn ? true : false;
"""

JS_DETAIL = """
var cards = document.querySelectorAll('[data-export-case]');
var details = document.querySelectorAll('[data-export-case-detail]');
var first = cards[0];
if (!first || !details.length) return {ok: false, cards: cards.length, details: details.length};
var detail = first.querySelector('[data-export-case-detail]');
var toggle = first.querySelector('[data-export-case-toggle]');
if (!toggle) return {ok: false, reason: 'no toggle', cards: cards.length, details: details.length};
var label = toggle.querySelector('[data-export-case-toggle-label]');
var before = detail.getBoundingClientRect().height;
toggle.click();
var after = detail.getBoundingClientRect().height;
return {
  ok: cards.length === details.length && after > 0,
  cards: cards.length,
  details: details.length,
  toggle_text: toggle.textContent.trim(),
  toggle_label: label ? label.textContent.trim() : null,
  height_before: before,
  height_after: after
};
"""

JS_AXES = """
// 评估维度 / 设备·API 目标两个轴：Tab 存在时，点击后同组面板必须只剩 1 个可见。
// INT-2434 四轮：`data-export-show` 改存 JSON 字符串数组（展示名可能带空格，不能用空格切分，
// 也不能再用属性的 ^= 前缀匹配），这里 JSON.parse 后按「组:」前缀找同组面板。
function showSpecs(el) {
  var raw = el.getAttribute('data-export-show') || '';
  if (!raw) return [];
  try {
    var parsed = JSON.parse(raw);
    if (Object.prototype.toString.call(parsed) === '[object Array]') return parsed.map(String);
  } catch (err) {}
  return [raw];
}
function panelsOf(root, group) {
  return Array.prototype.filter.call(root.querySelectorAll('[data-export-show]'), function (el) {
    return showSpecs(el).some(function (spec) {
      return spec.indexOf(group + ':') === 0;
    });
  });
}
function axisCheck(suffix) {
  var tabs = Array.prototype.slice.call(
    document.querySelectorAll('[data-export-tab*="' + suffix + '"]'));
  if (tabs.length < 2) return {skipped: true, count: tabs.length};
  var group = (tabs[0].getAttribute('data-export-tab') || '').split(':')[0];
  var same = tabs.filter(function (b) {
    return (b.getAttribute('data-export-tab') || '').split(':')[0] === group;
  });
  if (same.length < 2) return {skipped: true, count: same.length};
  var card = same[0].closest('[data-export-case]');
  var target = same.filter(function (b) {
    return b.getAttribute('aria-selected') !== 'true';
  })[0] || same[1];
  target.click();
  var panels = panelsOf(card, group);
  var visible = panels.filter(function (el) {
    return el.style.display !== 'none';
  }).length;
  return {
    group: group,
    count: same.length,
    panels: panels.length,
    visible: visible,
    ok: panels.length > 0 && visible >= 1 && visible < panels.length
  };
}
var dim = axisCheck('-dim:');
var target = axisCheck('-target:');
return {ok: (dim.skipped || dim.ok) && (target.skipped || target.ok), dim: dim, target: target};
"""

JS_ACTION_BUTTONS = """
var texts = ['保存', '发布', '取消发布', '删除', '彻底删除', '下载日志', '人工复核', '导出'];
var bad = [];
Array.prototype.forEach.call(document.querySelectorAll('button'), function (b) {
  var t = (b.textContent || '').trim();
  if (t && texts.indexOf(t) >= 0) bad.push(t);
});
return bad;
"""

JS_FILTERS = """
// 负责人 2026-11-10 二轮反馈「具体用例卡片功能不完整，筛选功能不完整」：
// 产物内必须带与页面同口径的筛选（关键词 / 分组 / 标签 / 维度 / 排序）与卡片操作
// （全部展开、复制用例 ID），且是真实生效的纯 DOM 过滤，不是摆设。
var panel = document.querySelector('[data-export-filter-panel]');
if (!panel) return {ok: false, reason: 'no filter panel'};
var groups = panel.querySelectorAll('[data-export-filter-group]');
var tags = panel.querySelectorAll('[data-export-filter-tag]');
var metrics = panel.querySelectorAll('[data-export-filter-metric]');
var kw = document.getElementById('export-case-search');
var sort = panel.querySelector('[data-export-filter-sort]');
var reset = document.querySelector('[data-export-filter-reset]');
var cards = Array.prototype.slice.call(document.querySelectorAll('[data-export-case]'));
function visible() {
  return cards.filter(function (c) { return c.style.display !== 'none'; });
}
var res = {
  ok: false,
  groups: groups.length,
  tags: tags.length,
  metrics: metrics.length,
  keyword: !!kw,
  sort: !!sort,
  reset: !!reset,
  base_visible: visible().length
};
if (!kw || !sort || !reset) return res;
// 单卡报告（多目标 API 报告 421/422 只有 1 张卡）：没有「部分命中」可言，
// 关键词/按选项过滤的「命中数 > 0」断言对它恒不成立 → 记为 skipped，多卡报告仍严格。
var singleCard = cards.length <= 1;

// 1) 关键词过滤：取第二张卡名称片段，命中数应 < 总卡片数
var probe = String((cards[1] || cards[0]).getAttribute('data-export-case-name') || '').slice(0, 6);
kw.value = probe;
kw.dispatchEvent(new Event('input', {bubbles: true}));
res.keyword_hits = visible().length;
res.keyword_ok = singleCard
  ? 'skipped: 单卡报告'
  : (res.keyword_hits > 0 && res.keyword_hits < cards.length);
reset.click();
res.reset_visible = visible().length;

// 2) 分组多选：勾第一个分组后，可见卡片必须全部属于该分组
if (groups.length > 0) {
  var g = groups[0];
  var gname = g.getAttribute('data-export-filter-group');
  g.checked = true;
  g.dispatchEvent(new Event('change', {bubbles: true}));
  var vis = visible();
  res.group_name = gname;
  res.group_visible = vis.length;
  res.group_all_match = vis.length > 0 && vis.every(function (c) {
    return c.getAttribute('data-export-case-category') === gname;
  });
  var headerCount = document.querySelector('[data-export-group-count]');
  res.group_count_text = headerCount ? headerCount.textContent.trim() : null;
  reset.click();
} else {
  res.group_all_match = true;
  res.group_count_text = 'skipped: 报告无分组';
}

// 3) 标签 / 维度：过滤后可见数应 ≤ 全部
function axisFilter(el, attr, name) {
  if (!el) return {skipped: true};
  el.checked = true;
  el.dispatchEvent(new Event('change', {bubbles: true}));
  var hit = visible().length;
  reset.click();
  if (singleCard) return {value: name, hits: hit, skipped: '单卡报告'};
  return {value: name, hits: hit, ok: hit > 0 && hit <= cards.length};
}
res.tag_filter = axisFilter(tags[0], 'data-export-filter-tag',
  tags[0] ? tags[0].getAttribute('data-export-filter-tag') : null);
res.metric_filter = axisFilter(metrics[0], 'data-export-filter-metric',
  metrics[0] ? metrics[0].getAttribute('data-export-filter-metric') : null);

// 4) 排序：按名称升序后，同一分组容器内的卡片名非降序
sort.value = 'name';
sort.dispatchEvent(new Event('change', {bubbles: true}));
var parents = [];
Array.prototype.forEach.call(document.querySelectorAll('[data-export-case]'), function (c) {
  if (parents.indexOf(c.parentElement) < 0) parents.push(c.parentElement);
});
var sorted = true;
var sample = null;
parents.forEach(function (p) {
  var names = Array.prototype.filter.call(p.children, function (c) {
    return c.getAttribute && c.getAttribute('data-export-case') !== null;
  }).map(function (c) { return c.getAttribute('data-export-case-name') || ''; });
  if (names.length > 1 && !sample) sample = names.slice(0, 3);
  for (var i = 1; i < names.length; i += 1) {
    if (names[i - 1] > names[i]) sorted = false;
  }
});
res.sorted = sorted;
res.sort_sample = sample;
sort.value = '';
sort.dispatchEvent(new Event('change', {bubbles: true}));

// 5) 卡片操作：全部展开 / 收起、用例 ID 徽章（可点击复制）
var expandAll = document.getElementById('export-case-expand-all');
if (expandAll) {
  expandAll.click();
  var details = Array.prototype.slice.call(document.querySelectorAll('[data-export-case-detail]'));
  res.expand_all = details.length > 0 && details.every(function (d) { return !d.hasAttribute('hidden'); });
  var collapseAll = document.getElementById('export-case-collapse-all');
  if (collapseAll) collapseAll.click();
}
var copyEl = document.querySelector('[data-export-copy-id]');
res.copy_id = copyEl ? copyEl.textContent.trim() : null;
res.ok = res.keyword_ok && res.group_all_match !== false
  && res.tag_filter.ok !== false && res.metric_filter.ok !== false
  && res.sorted === true && res.expand_all === true && !!res.copy_id;
return res;
"""


JS_CASE_IDS = """
// UX 审计 2026-11-10 P2：产物每张卡必须带可见的用例 ID 文本
// （页面上 ID 是「点击复制」按钮，克隆时被整体剪掉，产物里整块丢失）
var cards = Array.prototype.slice.call(document.querySelectorAll('[data-export-case]'));
var missing = [];
cards.forEach(function (card) {
  var id = card.getAttribute('data-export-case-id') || '';
  var badge = card.querySelector('[data-export-copy-id]');
  if (!badge || !id || badge.textContent.trim() !== id) missing.push(id || '(no id)');
});
var first = cards.length ? cards[0].querySelector('[data-export-copy-id]') : null;
return {
  ok: cards.length > 0 && missing.length === 0,
  cards: cards.length,
  missing_count: missing.length,
  missing_sample: missing.slice(0, 5),
  sample_id: first ? first.textContent.trim() : null
};
"""

JS_GROUPS = """
// UX 审计 2026-11-10 P1：分组头必须可点开 / 收起，且点开后本组卡片可见
// （旧产物：组头是死 DIV，全局分页把第一组以外的组全藏起来 → 只剩标题、0 卡）
var wrappers = Array.prototype.slice.call(document.querySelectorAll('[data-export-group]'));
if (!wrappers.length) return {ok: false, reason: 'no group wrapper'};
var toggles = Array.prototype.slice.call(document.querySelectorAll('[data-export-group-toggle]'));
if (!toggles.length) return {ok: false, reason: 'no group toggle'};
function cardsOf(w) { return Array.prototype.slice.call(w.querySelectorAll('[data-export-case]')); }
function visibleOf(w) {
  return cardsOf(w).filter(function (c) {
    if (c.style.display === 'none') return false;
    var rect = c.getBoundingClientRect();
    return rect.height > 0 && rect.width > 0;
  });
}
var emptyGroups = [];
var withCards = 0;
wrappers.forEach(function (w) {
  if (cardsOf(w).length === 0) return;
  withCards += 1;
  if (visibleOf(w).length === 0) emptyGroups.push((w.textContent || '').trim().slice(0, 24));
});
var result = {
  ok: false,
  groups: wrappers.length,
  toggles: toggles.length,
  groups_with_cards: withCards,
  groups_empty_on_page1: emptyGroups,
  first_toggle_tag: toggles[0].tagName.toLowerCase()
};
// 优先「打断与恢复」（负责人 08:44 问的那一组），没有就取最后一个有卡的分组。
// 注意：按组头按钮的 aria-label 取组名——组容器 textContent 里还有卡片正文（用例标签里
// 也可能出现「打断与恢复」），按整块 textContent 匹配会错认成第一组。
function groupNameOf(w) {
  var btn = w.querySelector('[data-export-group-toggle]');
  if (!btn) return (w.textContent || '').trim().slice(0, 16);
  var label = btn.getAttribute('aria-label') || '';
  if (label.indexOf('展开或收起分组 ') === 0) return label.slice('展开或收起分组 '.length);
  return (btn.textContent || '').trim().slice(0, 16);
}
var target = null;
wrappers.forEach(function (w) {
  if (target) return;
  if (groupNameOf(w).indexOf('打断与恢复') >= 0) target = w;
});
if (!target) {
  for (var i = wrappers.length - 1; i >= 0; i -= 1) {
    if (cardsOf(wrappers[i]).length > 0) { target = wrappers[i]; break; }
  }
}
if (!target) return result;
var btn = target.querySelector('[data-export-group-toggle]');
var body = target.querySelector('[data-export-group-body]');
if (!btn || !body) { result.reason = 'group missing toggle/body'; return result; }
result.target_name = groupNameOf(target);
result.target_toggle_tag = btn.tagName.toLowerCase();
result.cards_in_target = cardsOf(target).length;
result.visible_before = visibleOf(target).length;
btn.click();
result.expanded_after_collapse = btn.getAttribute('aria-expanded');
result.body_hidden_after_collapse = body.style.display === 'none';
result.visible_collapsed = visibleOf(target).length;
btn.click();
result.expanded_after_expand = btn.getAttribute('aria-expanded');
result.visible_after_expand = visibleOf(target).length;
result.ok = result.target_toggle_tag === 'button'
  && result.expanded_after_collapse === 'false'
  && result.body_hidden_after_collapse === true
  && result.visible_collapsed === 0
  && result.expanded_after_expand === 'true'
  && result.visible_after_expand > 0
  && emptyGroups.length === 0;
return result;
"""

JS_SCROLL_TO_CASES = """
var sec = document.getElementById('report-specific-cases');
if (!sec) return {ok: false};
var top = sec.getBoundingClientRect().top + (window.scrollY || 0);
window.scrollTo(0, Math.max(0, top - 8));
return {ok: true, scroll_y: Math.round(window.scrollY || 0)};
"""

JS_OPEN_TARGET_GROUP = """
// 折叠再展开「打断与恢复」并滚到组头：产物里组头可点、组内卡片可见
var wrappers = Array.prototype.slice.call(document.querySelectorAll('[data-export-group]'));
function groupNameOf(w) {
  var b = w.querySelector('[data-export-group-toggle]');
  if (!b) return (w.textContent || '').trim().slice(0, 16);
  var label = b.getAttribute('aria-label') || '';
  if (label.indexOf('展开或收起分组 ') === 0) return label.slice('展开或收起分组 '.length);
  return (b.textContent || '').trim().slice(0, 16);
}
var target = null;
wrappers.forEach(function (w) {
  if (target) return;
  if (groupNameOf(w).indexOf('打断与恢复') >= 0) target = w;
});
if (!target) {
  for (var i = wrappers.length - 1; i >= 0; i -= 1) {
    if (wrappers[i].querySelector('[data-export-case]')) { target = wrappers[i]; break; }
  }
}
if (!target) return {ok: false};
var btn = target.querySelector('[data-export-group-toggle]');
if (!btn) return {ok: false};
btn.click();
btn.click();
var rect = btn.getBoundingClientRect();
window.scrollTo(0, Math.max(0, rect.top + (window.scrollY || 0) - 90));
var visible = Array.prototype.filter.call(target.querySelectorAll('[data-export-case]'), function (c) {
  var r = c.getBoundingClientRect();
  return c.style.display !== 'none' && r.height > 0;
}).length;
return {
  ok: visible > 0,
  name: groupNameOf(target),
  expanded: btn.getAttribute('aria-expanded'),
  visible_cards: visible
};
"""


def run_report(smoke, base, report_id):
    d = smoke.drv
    rec = {'report_id': report_id}
    d.get('%s/report/%d' % (base, report_id))
    time.sleep(8)
    sm.wait_quiet(d, 45)
    body = sm.body_text(d)
    rec['title_head'] = body[:160]
    rec['app_case_cards'] = d.execute_script(
        "return document.querySelectorAll('[data-export-case]').length")
    export = smoke.export_html(d)
    rec['export'] = {k: export.get(k) for k in (
        'ok', 'zip', 'zip_size', 'zip_entries', 'exported_case_cards', 'case_detail_blocks',
        'residual_action_buttons', 'has_dialog_markup', 'offline_http_requests',
        'no_backend_export_request', 'exported_html_size') if k in export}
    rec['export']['offline_http_requests_count'] = len(export.get('offline_http_requests') or [])

    # export_html 自检里会做搜索过滤 / 折叠分区，页内状态已被改动；重新打开产物再断言
    file_url = 'file:///' + os.path.join(ART, 'exported_html', 'report.html').replace('\\', '/')
    d.get(file_url)
    time.sleep(2.5)

    # 产物已由 export_html 解到 <art>/exported_html/ 并在 driver 里 file:// 打开
    toc = d.execute_script(JS_TOC)
    rec['toc'] = toc
    rec['tabs'] = d.execute_script(JS_TABS)
    rec['axes'] = d.execute_script(JS_AXES)
    rec['detail'] = d.execute_script(JS_DETAIL)
    rec['action_buttons'] = d.execute_script(JS_ACTION_BUTTONS)
    # 产物内筛选 / 排序 / 卡片操作（INT-2434 二轮）
    rec['filters'] = d.execute_script(JS_FILTERS)
    # 用例 ID 文本 / 分组头可点开（UX 审计 2026-11-10 P1·P2）
    rec['case_ids'] = d.execute_script(JS_CASE_IDS)
    rec['groups'] = d.execute_script(JS_GROUPS)
    # 「具体用例」区截图：筛选面板 + 卡片（含用例 ID）
    d.execute_script(JS_SCROLL_TO_CASES)
    time.sleep(0.8)
    rec['shot_specific_cases'] = sm.shot(d, '2434_%s_specific_cases' % report_id)
    # 点开「打断与恢复」分组后截图：组头 + 本组卡片
    rec['open_group'] = d.execute_script(JS_OPEN_TARGET_GROUP)
    time.sleep(0.8)
    rec['shot_group_open'] = sm.shot(d, '2434_%s_group_open' % report_id)
    # 视口固定的右导航（sticky）——放在最后跑，会滚动页面
    rec['toc_fixed'] = d.execute_script(JS_TOC_FIXED)
    # 滚到页底时截一张：右栏目录仍在视口内（留证「视口固定」）
    rec['shot_exported_scrolled'] = sm.shot(d, '2434_%s_exported_rail' % report_id)
    # 点目录第一条：平滑滚动后该分区进入视口（给平滑滚动留时间，最多重试 ~4s）
    d.execute_script("var l=document.querySelector('[data-export-toc-link]'); if(l) l.click(); return !!l;")
    jump = None
    for _ in range(5):
        time.sleep(0.8)
        jump = d.execute_script(JS_TOC_CLICK_JUMP)
        if jump and jump.get('ok'):
            break
    rec['toc_jump'] = jump
    d.execute_script("window.scrollTo(0, 0)")
    time.sleep(0.4)
    rec['shot_exported'] = sm.shot(d, '2434_%s_exported' % report_id)

    # 产物按报告号留档（export_html 每次复用同一目录）
    src = os.path.join(ART, 'exported_html')
    dst = os.path.join(ART, 'report_%s' % report_id)
    if os.path.isdir(src):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    rec['ok'] = all([
        bool(export.get('ok')),
        bool(toc and toc.get('ok')),
        bool(rec['tabs'] and rec['tabs'].get('ok')),
        bool(rec['axes'] and rec['axes'].get('ok')),
        bool(rec['detail'] and rec['detail'].get('ok')),
        bool(rec['filters'] and rec['filters'].get('ok')),
        bool(rec['case_ids'] and rec['case_ids'].get('ok')),
        bool(rec['groups'] and rec['groups'].get('ok')),
        bool(rec['open_group'] and rec['open_group'].get('ok')),
        bool(rec['toc_fixed'] and rec['toc_fixed'].get('ok')),
        bool(rec['toc_jump'] and rec['toc_jump'].get('ok')),
        not rec['action_buttons'],
        not (export.get('offline_http_requests') or []),
    ])
    return rec


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--reports', default='383,395', help='逗号分隔的报告 id')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    ids = [int(x) for x in args.reports.split(',') if x.strip()]
    os.makedirs(ART, exist_ok=True)

    sm.env_check('probe_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    download_dir = os.path.join(ART, 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    driver = sm.make_driver(download_dir)
    RESULT['driver'] = 'chrome-headless'
    try:
        smoke.drv = driver
        login = smoke.login()
        RESULT['checks']['login'] = {'ok': login.get('ok'), 'url': login.get('url_after')}
        assert login.get('ok'), '登录失败: %s' % login
        RESULT['checks']['stack'] = sm.env_check('probe_stack')
        for rid in ids:
            rec = run_report(smoke, base, rid)
            RESULT['reports'].append(rec)
            log('report %s ok=%s toc=%s toc_fixed=%s tabs=%s detail=%s filters=%s ids=%s groups=%s' % (
                rid, rec['ok'],
                (rec.get('toc') or {}).get('ok'),
                (rec.get('toc_fixed') or {}).get('ok'),
                (rec.get('tabs') or {}).get('ok'),
                (rec.get('detail') or {}).get('ok'),
                (rec.get('filters') or {}).get('ok'),
                (rec.get('case_ids') or {}).get('ok'),
                (rec.get('groups') or {}).get('ok')))
        RESULT['ok'] = bool(RESULT['reports']) and all(r['ok'] for r in RESULT['reports'])
        RESULT['console_errors'] = sm.console_errors(driver)
        sm.env_check('probe_end')
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('SUMMARY_JSON=%s' % out_path)
    print('OK=%s' % RESULT.get('ok'))


if __name__ == '__main__':
    main()
