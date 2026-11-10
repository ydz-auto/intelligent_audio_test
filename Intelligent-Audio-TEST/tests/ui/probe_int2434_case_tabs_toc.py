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
// 评估维度 / 设备·API 目标两个轴：Tab 存在时，点击后同组面板必须只剩 1 个可见
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
  var panels = card.querySelectorAll('[data-export-show^="' + group + '"]');
  var visible = Array.prototype.filter.call(panels, function (el) {
    return el.style.display !== 'none';
  }).length;
  var allTargets = panelVisibleAll(same[0].closest('[data-export-case]'), group);
  return {
    count: same.length,
    panels: panels.length,
    visible: visible,
    ok: panels.length > 0 && visible >= 1 && visible < panels.length
  };
}
function panelVisibleAll(card, group) {
  return card.querySelectorAll('[data-export-show^="' + group + '"]').length;
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
            log('report %s ok=%s toc=%s toc_fixed=%s tabs=%s detail=%s' % (
                rid, rec['ok'],
                (rec.get('toc') or {}).get('ok'),
                (rec.get('toc_fixed') or {}).get('ok'),
                (rec.get('tabs') or {}).get('ok'),
                (rec.get('detail') or {}).get('ok')))
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
