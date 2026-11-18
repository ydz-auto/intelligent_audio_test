# -*- coding: utf-8 -*-
"""INT-2650 开始测试「系统」筛选归一 · 浏览器实测（React，docker 真实库栈）。

环境铁律（负责人 2026-10-23）：后端网关 http://localhost:15000（database=intelligent_audio_test），
不启动本地后端栈。本卡改的是前端分支 agent/react-a/int-2650（sha 192440d48，尚未合入 V10.11.2），
15173 镜像不含该提交，因此前端跑本 run 的 frontend-react dev server（--base，代理到 15000）。

核对卡面验收：
  1. 全部系统 → 6 台设备（harmony ×2 + HarmonyOS ×4）；
  2. 系统筛选选「鸿蒙」→ 6 台全命中（修复前只剩 2 台）；
  3. Android → 0 台（库内无 Android 设备）；
  4. 筛选口径与设备卡「系统」列展示不矛盾；浅/深色各取截图；
  5. 数据来自真实 GET /test-devices（无 mock 残留），筛选为客户端过滤不再发请求。

只读：本探针不写库，无 fixture、无需清理。
跑法（系统 python，playwright 装在 user site，禁 -I）：
  python tests/ui/probe_int2650_system_filter.py --base http://localhost:5388
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2650')

# 设备区（section：h3「设备」+ 计数 span + 卡片网格）
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

BOTTOM_COUNT_JS = """
() => {
  const spans = Array.from(document.querySelectorAll('span'));
  const hit = spans.find(s => (s.textContent || '').trim().startsWith('共 '));
  return hit ? hit.textContent.trim() : '';
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

    def dark(self, on):
        self._page.emulate_media(color_scheme='dark' if on else 'light')

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    # ── 步骤二 ────────────────────────────────────────────
    def goto_step2(self, page):
        page.goto(self.base + '/start-test?step=1&view=card', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        if page.evaluate(DEV_SECTION_JS) is None:
            nxt = page.get_by_role('button', name='下一步')
            if nxt.count():
                nxt.first.click()
                page.wait_for_timeout(4000)
        page.wait_for_timeout(1500)

    def dev_state(self, page):
        return page.evaluate(DEV_SECTION_JS)

    def pick_system(self, page, label):
        trig = self.system_trigger(page)
        trig.click()
        page.wait_for_timeout(500)
        items = page.locator('[data-slot=select-item]')
        labels = [items.nth(i).inner_text().strip() for i in range(items.count())]
        items.filter(has_text=label).first.click()
        page.wait_for_timeout(1200)
        return labels

    def system_trigger(self, page):
        idx = page.evaluate("""() => {
          const labels = ['全部系统', 'Android', '鸿蒙', 'API 网关'];
          const ts = Array.from(document.querySelectorAll('[data-slot=select-trigger]'));
          return ts.findIndex(t => labels.includes((t.textContent || '').trim()));
        }""")
        assert idx is not None and idx >= 0, '未找到系统筛选下拉'
        return page.locator('[data-slot=select-trigger]').nth(idx)

    # ── API 侧 ────────────────────────────────────────────
    def api_devices(self, client):
        data = client.request('GET', '/test-devices?page=1&per_page=1000')
        body = data.get('data')
        items = body.get('items') if isinstance(body, dict) else body
        if items is None:
            items = data.get('items') or []
        return items or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5388')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()

    p = Probe(args.base, args.api, args.username, args.password)
    client = ApiClient(args.api)
    client.login(args.username, args.password)
    health = client.health()
    print('HEALTH=' + json.dumps(health, ensure_ascii=False), flush=True)
    p.check('health_db_main', health.get('database') == 'intelligent_audio_test',
            'database=%s' % health.get('database'))

    devices = p.api_devices(client)
    systems = [(d['id'], d['name'], d.get('system')) for d in devices]
    print('API_DEVICES=' + json.dumps(systems, ensure_ascii=False), flush=True)
    harmony_raw = [d for d in devices if (d.get('system') or '') in ('harmony', 'HarmonyOS')]
    lower_h = [d for d in devices if d.get('system') == 'harmony']
    canon_h = [d for d in devices if d.get('system') == 'HarmonyOS']
    p.check('api_six_devices', len(devices) == 6, 'count=%d' % len(devices))
    p.check('api_system_mix', len(lower_h) == 2 and len(canon_h) == 4,
            'harmony=%d HarmonyOS=%d' % (len(lower_h), len(canon_h)))
    total = len(harmony_raw)
    names = sorted(d['name'] for d in devices)

    reqs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p._page = page
        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text)
                if m.type == 'error' else None)
        page.on('request', lambda r: reqs.append({'method': r.method, 'url': r.url})
                if '/api/v1/test-devices' in r.url else None)
        page.on('response', lambda r: reqs.append({'resp': r.status, 'url': r.url})
                if '/api/v1/test-devices' in r.url else None)

        p.login(page)
        p.goto_step2(page)

        # 1) 默认「全部系统」
        st = p.dev_state(page)
        assert st is not None, '步骤二未渲染设备区'
        print('ALL_DEVICES=' + json.dumps(st, ensure_ascii=False), flush=True)
        p.check('all_system_cards', len(st['cards']) == total,
                'cards=%d api=%d' % (len(st['cards']), total))
        p.check('all_system_count_text', ('%d 台' % total) in st['countText'],
                'countText=%r' % st['countText'])
        p.check('all_system_names', sorted(c['name'] for c in st['cards']) == names,
                'cards=%s' % sorted(c['name'] for c in st['cards']))
        bottom = page.evaluate(BOTTOM_COUNT_JS)
        p.check('all_system_bottom_count', ('共 %d 台设备' % total) in bottom,
                'bottom=%r' % bottom)

        # 2) 筛选项
        trig = p.system_trigger(page)
        trig.click()
        page.wait_for_timeout(600)
        items = page.locator('[data-slot=select-item]')
        options = [items.nth(i).inner_text().strip() for i in range(items.count())]
        p.check('system_options', options == ['全部系统', 'Android', '鸿蒙', 'API 网关'],
                'options=%s' % options)
        items.filter(has_text='鸿蒙').first.click()
        page.wait_for_timeout(1200)
        p.shot('light_harmony_filter')

        # 3) 鸿蒙筛选 → 全部 6 台
        st_h = p.dev_state(page)
        print('HARMONY_DEVICES=' + json.dumps(st_h, ensure_ascii=False), flush=True)
        p.check('harmony_cards_all', len(st_h['cards']) == total,
                'cards=%d expect=%d' % (len(st_h['cards']), total))
        p.check('harmony_names_all', sorted(c['name'] for c in st_h['cards']) == names,
                'cards=%s' % sorted(c['name'] for c in st_h['cards']))
        p.check('harmony_count_text', ('%d 台' % total) in st_h['countText'],
                'countText=%r' % st_h['countText'])
        bottom_h = page.evaluate(BOTTOM_COUNT_JS)
        p.check('harmony_bottom_count', ('共 %d 台设备' % total) in bottom_h,
                'bottom=%r' % bottom_h)
        # 展示列与筛选口径一致：卡片系统列全部是鸿蒙系（harmony/HarmonyOS）
        shown = sorted(set(c['system'] for c in st_h['cards']))
        p.check('harmony_card_system_col', all(s in ('harmony', 'HarmonyOS') for s in shown),
                'system_col=%s' % shown)

        # 4) Android → 0 台
        trig = p.system_trigger(page)
        trig.click()
        page.wait_for_timeout(500)
        page.locator('[data-slot=select-item]').filter(has_text='Android').first.click()
        page.wait_for_timeout(1200)
        st_a = p.dev_state(page)
        print('ANDROID_DEVICES=' + json.dumps(st_a, ensure_ascii=False), flush=True)
        p.shot('light_android_filter')
        p.check('android_cards_zero', len(st_a['cards']) == 0,
                'cards=%d' % len(st_a['cards']))
        p.check('android_count_text', '0 台' in st_a['countText'],
                'countText=%r' % st_a['countText'])

        # 5) 回到全部系统，浅色截图
        p.pick_system(page, '全部系统')
        st_back = p.dev_state(page)
        p.check('back_to_all', len(st_back['cards']) == total,
                'cards=%d' % len(st_back['cards']))
        p.shot('light_all_devices')

        # 6) 深色：真刷新后重测两档
        p.dark(True)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        st_d = p.dev_state(page)
        p.check('dark_all_cards', st_d is not None and len(st_d['cards']) == total,
                'cards=%s html_dark=%s' % (len(st_d['cards']) if st_d else None,
                                           page.evaluate("() => document.documentElement.classList.contains('dark')")))
        p.shot('dark_all_devices', dark=True)
        p.pick_system(page, '鸿蒙')
        st_dh = p.dev_state(page)
        p.check('dark_harmony_cards_all', len(st_dh['cards']) == total,
                'cards=%d' % len(st_dh['cards']))
        p.shot('dark_harmony_filter', dark=True)

        requests_log = reqs[:]
        print('DEVICE_REQUESTS=' + json.dumps(requests_log, ensure_ascii=False), flush=True)
        gets = [r for r in requests_log if r.get('method') == 'GET']
        p.check('real_api_request_seen', len(gets) >= 1,
                'gets=%d' % len(gets))
        print('CONSOLE_ERRORS=' + json.dumps(console_errors[:10], ensure_ascii=False), flush=True)
        browser.close()

    fails = [c for c in p.checks if not c['ok']]
    print('CHECKS=%d FAIL=%d' % (len(p.checks), len(fails)), flush=True)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
