# -*- coding: utf-8 -*-
"""INT-2654 前端回归日巡补充实测（React docker 栈 15173，只读）。

补本轮重点复验项（其余核心页 / 链路沿用 smoke_react_nav_walk_int2136、
smoke_frontend_int1919、probe_int2441/2445/2628/2638/2640/2648/2650）：

  1. `int2649`：设备管理「详情」弹窗的系统列走归一映射（API system='harmony'
     的设备显示 HarmonyOS，不外露小写原始值）；开始测试设备区标题计数为
     「N 台设备 · 在线 M」，M 与 API 在线台数一致（本栈 6 台全离线 → 在线 0）。
  2. `p50`：报告详情统计卡「中位数」标注补 P50（INT-2650 之外的 0910101af）。
  3. `exportzip`：报告详情 HTML 导出快照里标题 / 表格结构齐全（6b15b3b4f 的
     前端导出链路不回退）。

只读语义：打开弹窗 / 切图表视图 / 读已导出的 zip，不提交任何写请求、不写库。
跑法：
  python tests/ui/probe_int2654_daily.py int2649 --base http://localhost:15173 --api http://localhost:15000
  python tests/ui/probe_int2654_daily.py p50     --base http://localhost:15173
  python tests/ui/probe_int2654_daily.py exportzip
  python tests/ui/probe_int2654_daily.py all
"""
import argparse
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2654')
EXPORT_ZIP = os.path.join(HERE, 'artifacts', 'int1919', 'react', 'downloads',
                          '全类型覆盖报告_task460_20261031-100112.zip')

DEV_SECTION_JS = """
() => {
  const secs = Array.from(document.querySelectorAll('section.space-y-2'));
  const sec = secs.find(s => {
    const h = s.querySelector('h3');
    return h && (h.textContent || '').trim().startsWith('设备');
  });
  if (!sec) return null;
  const h = sec.querySelector('h3');
  const countText = h && h.querySelector('span') ? h.querySelector('span').textContent.trim() : '';
  const cards = Array.from(sec.querySelectorAll('div.rounded-xl.border.p-4')).map(c => {
    const name = c.querySelector('.truncate.text-sm.font-medium');
    let system = '';
    const dts = Array.from(c.querySelectorAll('dt'));
    const sysDt = dts.find(d => (d.textContent || '').trim() === '系统');
    if (sysDt && sysDt.nextElementSibling) system = (sysDt.nextElementSibling.textContent || '').trim();
    return {name: name ? name.textContent.trim() : '', system: system};
  }).filter(c => c.name);
  return {countText: countText, cards: cards};
}
"""


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []
        self._page = None

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-44s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        self._page.screenshot(path=path)
        print('SHOT=%s' % path, flush=True)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)


def _dialog_system(dlg):
    """弹窗内「系统」行的值（dt 后紧跟的 dd 或兄弟节点文本）。"""
    return dlg.evaluate("""(d) => {
      const rows = Array.from(d.querySelectorAll('dt'));
      for (const dt of rows) {
        if ((dt.textContent || '').trim() !== '系统') continue;
        const sib = dt.nextElementSibling;
        return sib ? (sib.textContent || '').trim() : '';
      }
      return null;
    }""")


def mode_int2649(p, args):
    from tests.ui.utils.api_client import ApiClient
    api = ApiClient(p.api)
    api.login(p.username, p.password)
    body = api.request('GET', '/test-devices?page=1&per_page=1000').get('data') or {}
    items = body.get('items') if isinstance(body, dict) else body
    items = items or []
    lower = [d for d in items if d.get('system') == 'harmony']
    online = [d for d in items if d.get('status') == 'online']
    print('API_DEVICES=%s' % json.dumps(
        [(d.get('name'), d.get('system'), d.get('status')) for d in items],
        ensure_ascii=False), flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p._page = page
        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text)
                if m.type == 'error' else None)
        p.login(page)

        # ── 1) 设备管理列表 → 详情弹窗系统列归一 ─────────────
        page.goto(p.base + '/devices', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        rows = page.locator('tbody tr').count()
        p.check('devices_list_rows_match_api', rows == len(items),
                'rows=%d api=%d' % (rows, len(items)))
        target = lower[0]['name'] if lower else None
        sys_val = None
        if target:
            row = page.locator('tbody tr').filter(has_text=target).first
            opened = row.count() > 0
            if opened:
                row.locator('button[aria-label^="操作 "]').first.click()
                page.wait_for_timeout(800)
                page.get_by_role('menuitem', name='详情', exact=True).first.click()
                page.wait_for_timeout(1600)
                dlg = page.locator('[role=dialog]').first
                sys_val = _dialog_system(dlg) if dlg.is_visible() else None
                p.shot('int2649_device_detail_harmony')
                page.keyboard.press('Escape')
                page.wait_for_timeout(600)
            p.check('device_detail_dialog_opened', opened, 'target=%r' % target)
        raw_lower = bool(sys_val) and 'harmony' in (sys_val or '')
        p.check('device_detail_system_normalized',
                bool(sys_val) and sys_val.startswith('HarmonyOS') and not raw_lower,
                'device=%r system_row=%r' % (target, sys_val))

        # ── 2) 开始测试设备区：计数格式 + 在线数与 API 一致 ──
        page.goto(p.base + '/start-test?step=1&view=card', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        st = page.evaluate(DEV_SECTION_JS)
        if st is None:
            nxt = page.get_by_role('button', name='下一步')
            if nxt.count():
                nxt.first.click()
                page.wait_for_timeout(4000)
                st = page.evaluate(DEV_SECTION_JS)
        p.check('start_test_device_section', st is not None, 'state=%r' % (st is not None))
        if st:
            expected = '%d 台设备 · 在线 %d' % (len(items), len(online))
            p.check('start_test_count_matches_online', st['countText'] == expected,
                    'shown=%r expected=%r' % (st['countText'], expected))
            cards = st['cards']
            systems = sorted(set(c['system'] for c in cards))
            p.check('start_test_cards_system_normalized',
                    len(cards) == len(items) and systems == ['HarmonyOS'],
                    'cards=%d systems=%s' % (len(cards), systems))
            p.shot('int2649_start_test_devices_light')
            page.emulate_media(color_scheme='dark')
            page.reload(wait_until='domcontentloaded')
            page.wait_for_timeout(5000)
            st_d = page.evaluate(DEV_SECTION_JS)
            if st_d is None:
                nxt = page.get_by_role('button', name='下一步')
                if nxt.count():
                    nxt.first.click()
                    page.wait_for_timeout(4000)
                    st_d = page.evaluate(DEV_SECTION_JS)
            p.check('start_test_dark_devices',
                    st_d is not None and len(st_d['cards']) == len(items),
                    'cards=%s' % (len(st_d['cards']) if st_d else None))
            p.shot('int2649_start_test_devices', dark=True)
            page.emulate_media(color_scheme='light')
        print('CONSOLE_ERRORS=' + json.dumps(console_errors[:10], ensure_ascii=False), flush=True)
        browser.close()


def mode_p50(p, args):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p._page = page
        p.login(page)
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        rows = page.locator('tbody tr').count()
        p.check('report_center_rows', rows > 0, 'rows=%d' % rows)
        page.locator('tbody tr').first.click()
        page.wait_for_timeout(5000)
        dist_btn = page.locator('button').filter(has_text='正态分布图')
        if dist_btn.count():
            dist_btn.first.click()
            page.wait_for_timeout(2500)
        for _ in range(3):
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(400)
        stats = page.evaluate("""() => {
          const out = [];
          const nodes = Array.from(document.querySelectorAll('div.rounded-xl.border.p-3'));
          for (const n of nodes) {
            const txt = n.innerText || '';
            if (!txt.includes('统计信息')) continue;
            out.push({
              p50_label: txt.includes('中位数 (Q2 / P50)'),
              old_label: txt.includes('中位数 (Q2)') && !txt.includes('P50'),
              p90: /P90\\s*[-\\d.]+/.test(txt),
              p95: /P95\\s*[-\\d.]+/.test(txt),
              sample: txt.slice(0, 200)
            });
          }
          return out;
        }""")
        p.check('report_stats_cards_present', len(stats) > 0, 'cards=%d' % len(stats))
        p.check('report_stats_p50_label',
                len(stats) > 0 and all(s['p50_label'] for s in stats),
                'cards=%d p50=%s sample=%s' % (
                    len(stats), [s['p50_label'] for s in stats],
                    stats[0]['sample'] if stats else ''))
        p.check('report_stats_p90_p95_kept',
                len(stats) > 0 and all(s['p90'] and s['p95'] for s in stats),
                'p90_95=%s' % [(s['p90'], s['p95']) for s in stats])
        p.shot('int2654_report_stats_p50_light')
        page.emulate_media(color_scheme='dark')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        dist_btn = page.locator('button').filter(has_text='正态分布图')
        if dist_btn.count():
            dist_btn.first.click()
            page.wait_for_timeout(2500)
        for _ in range(3):
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(400)
        dark_txt = page.inner_text('body')
        p.check('report_stats_p50_dark',
                '中位数 (Q2 / P50)' in dark_txt
                and page.evaluate("document.documentElement.classList.contains('dark')"),
                'has_p50=%s dark=%s' % (
                    '中位数 (Q2 / P50)' in dark_txt,
                    page.evaluate("document.documentElement.classList.contains('dark')")))
        p.shot('int2654_report_stats_p50', dark=True)
        page.emulate_media(color_scheme='light')
        browser.close()


def mode_exportzip(p, args):
    """6b15b3b4f 前端导出链路：读取 1919 链路已产出的 HTML 导出快照。"""
    exists = os.path.isfile(EXPORT_ZIP)
    p.check('export_zip_present', exists, 'path=%s' % EXPORT_ZIP)
    if not exists:
        return
    with zipfile.ZipFile(EXPORT_ZIP) as z:
        names = z.namelist()
        html = ''
        for n in names:
            if n.endswith('report.html'):
                html = z.read(n).decode('utf-8', 'replace')
                break
        css = ''
        for n in names:
            if n.endswith('.css'):
                css += z.read(n).decode('utf-8', 'replace')
    head = html[:800]
    p.check('export_html_has_h1_title',
            bool(html) and ('<h1' in html or '<h2' in html),
            'names=%s head=%r' % (names[:6], head[:120]))
    p.check('export_html_has_table_styles',
            '<table' in html or 'table' in css,
            'table_in_html=%s table_in_css=%s' % ('<table' in html, 'table' in css))
    p.check('export_html_css_title_table_rules',
            any(k in css for k in ('h1', '.report-title', 'th')) and 'td' in css,
            'css_len=%d' % len(css))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['int2649', 'p50', 'exportzip', 'all'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    modes = ['int2649', 'p50', 'exportzip'] if args.mode == 'all' else [args.mode]
    for m in modes:
        print('=== MODE %s ===' % m, flush=True)
        globals()['mode_%s' % m](p, args)
    os.makedirs(ART, exist_ok=True)
    summary = os.path.join(ART, 'summary.json')
    with open(summary, 'w', encoding='utf-8') as f:
        json.dump(p.checks, f, ensure_ascii=False, indent=2)
    total = len(p.checks)
    passed = len([c for c in p.checks if c['ok']])
    print('PASSED=%d FAILED=%d' % (passed, total - passed), flush=True)
    print('SUMMARY_JSON=%s' % summary, flush=True)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
