# -*- coding: utf-8 -*-
"""INT-2640 设备类型三值归一 · 浏览器实测（React，docker 真实库栈）。

环境铁律（负责人 2026-10-23）：后端网关 http://localhost:15000（database=intelligent_audio_test），
不启动本地后端栈。本卡改的是前端分支 agent/react-b/int-2640（sha 2259479，尚未合入 V10.11.2），
15173 镜像不含该提交，因此前端跑本 run 的 frontend-react dev server（--base，代理到 15000）。

核对卡面三处现象：
  1. 设备管理 → 行操作「编辑」→ 设备类型：关闭态不外露 phone；下拉含「未知」项；
  2. 报告中心 → 报告 426 → 设备与API统计：副标题「型号 · 类型」为中文，「phone」不外露；
  3. 开始测试 → 下一步（选择设备/API）：设备卡类型徽章与 /test-devices 的 type 一一对应
     （physical→真机，三值外→未知）。

模式：
  read  —— 只读核对三处界面 + 浅/深色截图（不写库）；
  write —— 用 API 建「接线测试_」设备（type=phone）验证编辑保存不改写未知原值、
           下拉归一后可改三值；finally 删除自身测试数据。

跑法（系统 python，playwright 装在 user site，禁 -I）：
  python tests/ui/probe_int2640_device_type.py read  --base http://localhost:5381
  python tests/ui/probe_int2640_device_type.py write --base http://localhost:5381
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient, ApiError  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2640')
REPORT_ID = 426
REPORT_NAME = '全类型覆盖报告_task460_20261031-100112'
THREE = ('physical', 'http_api', 'websocket_api')
KNOWN_LABELS = ('真机', 'HTTP API', 'Realtime WS', '未知')
RAW_ENUM = re.compile(r'\b(phone|tablet|physical|http_api|websocket_api)\b')


def label_of(api_type):
    """卡面口径：三值取中文，三值外（历史 phone / 扫描脏值）统一「未知」。"""
    return {'physical': '真机', 'http_api': 'HTTP API',
            'websocket_api': 'Realtime WS'}.get(api_type or '', '未知')


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []

    # ── 断言 / 证据 ────────────────────────────────────────
    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-46s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path)
        print('SHOT=%s' % path, flush=True)
        return path

    # ── 浏览器基础 ─────────────────────────────────────────
    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    def dark(self, on):
        self._page.emulate_media(color_scheme='dark' if on else 'light')

    # ── 页面取数（可见状态，不只看 DOM 存在）──────────────
    def type_trigger(self, page):
        """抽屉里「设备类型」字段的 base-ui Select 触发器。"""
        idx = page.evaluate("""() => {
          const ts = Array.from(document.querySelectorAll('[data-slot=select-trigger]'));
          return ts.findIndex(t => {
            const f = t.closest('div.flex.flex-col');
            const l = f ? f.querySelector('label') : null;
            return l && (l.textContent || '').replace(/\\s+/g, '').startsWith('设备类型');
          });
        }""")
        if idx is None or idx < 0:
            return None
        return page.locator('[data-slot=select-trigger]').nth(idx)

    def devices_drawer_state(self, page):
        """返回 (关闭态文案, 下拉项文案列表)；下拉打开后按 Escape 关闭。"""
        trig = self.type_trigger(page)
        if trig is None:
            return None, []
        closed = (trig.inner_text() or '').strip()
        trig.click()
        page.wait_for_timeout(500)
        items = page.locator('[data-slot=select-item]')
        options = [items.nth(i).inner_text().strip() for i in range(items.count())]
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)
        return closed, options

    def save_drawer(self, page):
        btn = page.locator("button[type='submit']").filter(has_text='保存').first
        btn.click()
        page.wait_for_timeout(3000)
        errs = page.evaluate("""() => Array.from(document.querySelectorAll('.text-destructive'))
            .map(e => (e.textContent || '').trim()).filter(Boolean).slice(0, 12)""")
        toasts = page.evaluate("""() => Array.from(document.querySelectorAll('[data-sonner-toast]'))
            .map(e => (e.textContent || '').trim())""")
        return {'errors': errs, 'toasts': toasts,
                'saving': page.locator("button[type='submit']").filter(has_text='保存中').count()}

    def open_edit_drawer(self, page, device_name):
        page.locator("[aria-label='操作 %s']" % device_name).first.click()
        page.wait_for_timeout(500)
        page.get_by_role('menuitem', name='编辑').first.click()
        page.wait_for_timeout(1500)
        # 抽屉里等「设备类型」字段
        page.wait_for_selector('[data-slot=select-trigger]', timeout=15000)

    def close_drawer(self, page):
        """下拉开着时第一次 Escape 只收下拉，循环到抽屉真正卸载。"""
        for _ in range(4):
            if page.locator("[data-slot=sheet-portal]").count() == 0:
                return
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
        page.wait_for_timeout(500)

    def report_device_cards(self, page):
        return page.evaluate("""() => {
          const cards = Array.from(document.querySelectorAll('div.bg-background.rounded-lg.border.p-3'));
          return cards.map(c => {
            const n = c.querySelector('.text-sm.font-medium');
            const s = c.querySelector('.text-xs.truncate');
            return {name: n ? n.textContent.trim() : '', subtitle: s ? s.textContent.trim() : ''};
          }).filter(c => c.name);
        }""")

    def start_test_cards(self, page):
        return page.evaluate("""() => {
          const cards = Array.from(document.querySelectorAll('div.rounded-xl.border.p-4'));
          return cards.map(c => {
            const name = c.querySelector('.truncate.text-sm.font-medium');
            const lines = (c.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
            const badge = lines.find(l => ['真机','HTTP API','Realtime WS','未知'].includes(l)) || '';
            return {name: name ? name.textContent.trim() : '', badge: badge, lines: lines};
          }).filter(c => c.name);
        }""")

    # ── API 侧 ─────────────────────────────────────────────
    def api_devices(self, client):
        data = client.request('GET', '/test-devices?page=1&per_page=100')
        body = data.get('data')
        items = body.get('items') if isinstance(body, dict) else body
        return items or []

    def api_device(self, client, device_id):
        data = client.request('GET', '/test-devices/%d' % device_id)
        return data.get('data') or data


def prelude(p, client):
    health = client.health()
    print('HEALTH=' + json.dumps(health, ensure_ascii=False), flush=True)
    p.check('health_db_main', health.get('database') == 'intelligent_audio_test',
            'database=%s' % health.get('database'))
    devices = p.api_devices(client)
    by_name = {d['name']: d for d in devices}
    print('DEVICES=' + json.dumps(
        [{'id': d['id'], 'name': d['name'], 'type': d.get('type')} for d in devices],
        ensure_ascii=False), flush=True)
    return devices, by_name


# ── read：三处界面只读核对 ───────────────────────────────
def mode_read(p, args, client):
    devices, by_name = prelude(p, client)
    phone_devs = [d for d in devices if (d.get('type') or '') not in THREE]
    physical_devs = [d for d in devices if d.get('type') == 'physical']
    p.check('api_has_unknown_type_rows', len(phone_devs) > 0,
            'unknown=%s' % [(d['id'], d['name'], d['type']) for d in phone_devs])
    target = phone_devs[0] if phone_devs else None
    physical = physical_devs[0] if physical_devs else None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p._page = page
        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text)
                if m.type == 'error' else None)
        p.login(page)

        # 1) 设备管理 → 编辑抽屉 -------------------------------------
        page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
        page.wait_for_selector('tbody tr', timeout=30000)
        page.wait_for_timeout(1500)
        if target:
            p.open_edit_drawer(page, target['name'])
            closed, options = p.devices_drawer_state(page)
            p.check('drawer_closed_label_unknown', closed == '未知',
                    'device=%s(type=%s) closed=%r' % (target['name'], target['type'], closed))
            p.check('drawer_options_three_plus_unknown',
                    options == ['真机', 'HTTP API', 'Realtime WS', '未知'],
                    'options=%s' % options)
            body = page.inner_text('body')
            p.check('drawer_no_raw_enum', not RAW_ENUM.search(body),
                    'raw=%s' % RAW_ENUM.findall(body))
            p.shot(page, 'devices_edit_closed_light')
            p.type_trigger(page).click()
            page.wait_for_timeout(600)
            p.shot(page, 'devices_edit_open_light')
            p.close_drawer(page)
            # 深色：真刷新后重开抽屉
            p.dark(True)
            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('tbody tr', timeout=30000)
            page.wait_for_timeout(1500)
            p.open_edit_drawer(page, target['name'])
            closed_d, options_d = p.devices_drawer_state(page)
            p.check('drawer_dark_closed_label', closed_d == '未知', 'closed=%r' % closed_d)
            p.shot(page, 'devices_edit_closed_dark')
            p.type_trigger(page).click()
            page.wait_for_timeout(600)
            p.shot(page, 'devices_edit_open_dark')
            p.close_drawer(page)
        if physical:
            p.open_edit_drawer(page, physical['name'])
            closed_p, _ = p.devices_drawer_state(page)
            p.check('drawer_physical_label', closed_p == '真机',
                    'device=%s closed=%r' % (physical['name'], closed_p))
            p.close_drawer(page)
        if target:
            p.open_edit_drawer(page, target['name'])
            # 关闭下拉（不选中）后再读一次：base-ui 补发 null 不得清空回填值（本卡顺带修的）
            trig = p.type_trigger(page)
            trig.click(); page.wait_for_timeout(400)
            page.keyboard.press('Escape'); page.wait_for_timeout(600)
            p.check('drawer_value_survives_escape', (trig.inner_text() or '').strip() == '未知',
                    'after_escape=%r' % (trig.inner_text() or '').strip())
            p.close_drawer(page)

        # 2) 报告中心 → 报告 426 设备与API统计 ------------------------
        report = client.request('GET', '/reports/%d' % REPORT_ID)
        rdata = report.get('data') or report
        stats = ((rdata.get('summary') or {}).get('device_stats')) or []
        expected = {}
        for d in stats:
            t = d.get('type')
            sub = [d.get('model'), label_of(t) if t else None]
            expected[d.get('name')] = ' · '.join([x for x in sub if x]) or '设备'
        print('REPORT_API_DEVICE_STATS=' + json.dumps(
            [{'name': d.get('name'), 'model': d.get('model'), 'type': d.get('type')}
             for d in stats], ensure_ascii=False), flush=True)
        p.dark(False)
        page.goto(p.base + '/report/%d' % REPORT_ID, wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        cards = p.report_device_cards(page)
        subs = [c['subtitle'] for c in cards]
        print('REPORT_DEVICE_CARDS=' + json.dumps(cards, ensure_ascii=False), flush=True)
        bad = [s for s in subs if RAW_ENUM.search(s)]
        p.check('report_subtitle_no_raw_enum', not bad, 'subtitles=%s' % subs)
        mismatch = [(c['name'], c['subtitle'], expected[c['name']])
                    for c in cards if c['name'] in expected
                    and c['subtitle'] != expected[c['name']]]
        p.check('report_subtitle_matches_api', not mismatch,
                'mismatch=%s expected=%s' % (mismatch, expected))
        unknown_rows = [n for n, sub in expected.items() if sub.split(' · ')[-1] == '未知']
        p.check('report_unknown_device_present', len(unknown_rows) > 0,
                'unknown_rows=%s' % unknown_rows)
        p.check('report_has_device_stats', len(cards) > 0, 'cards=%d' % len(cards))
        p.shot(page, 'report_426_device_stats_light')
        p.dark(True)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        cards_dark = p.report_device_cards(page)
        p.check('report_dark_device_stats', len(cards_dark) == len(cards),
                'dark_cards=%d light_cards=%d' % (len(cards_dark), len(cards)))
        p.shot(page, 'report_426_device_stats_dark')

        # 3) 开始测试 → 下一步（选择设备/API）--------------------------
        p.dark(False)
        page.goto(p.base + '/start-test?step=1&view=card', wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        body = page.inner_text('body')
        if '设备' not in body:
            page.get_by_role('button', name='下一步').first.click()
            page.wait_for_timeout(4000)
            body = page.inner_text('body')
        cards2 = p.start_test_cards(page)
        print('START_TEST_CARDS=' + json.dumps(
            [{'name': c['name'], 'badge': c['badge']} for c in cards2], ensure_ascii=False),
            flush=True)
        p.check('start_test_cards_present', len(cards2) > 0, 'cards=%d' % len(cards2))
        mismatched = []
        for c in cards2:
            api_type = (by_name.get(c['name']) or {}).get('type')
            if c['name'] in by_name and c['badge'] != label_of(api_type):
                mismatched.append((c['name'], api_type, c['badge']))
        p.check('start_test_badge_matches_api', not mismatched, 'mismatched=%s' % mismatched)
        raw_in_cards = [(c['name'], RAW_ENUM.findall(' '.join(c['lines'])))
                        for c in cards2 if RAW_ENUM.search(' '.join(c['lines']))]
        p.check('start_test_no_raw_enum', not raw_in_cards, 'raw=%s' % raw_in_cards)
        unknown_n = sum(1 for c in cards2 if c['badge'] == '未知')
        p.check('start_test_unknown_count', unknown_n == len([d for d in devices if (d.get('type') or '') not in THREE]),
                'unknown_badges=%d api_unknown=%d' % (
                    unknown_n, len([d for d in devices if (d.get('type') or '') not in THREE])))
        p.shot(page, 'start_test_resources_light')
        p.dark(True)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        p.shot(page, 'start_test_resources_dark')

        print('CONSOLE_ERRORS=' + json.dumps(console_errors[:10], ensure_ascii=False), flush=True)
        browser.close()


# ── write：编辑保存不改写未知原值 / 三值可写 ────────────────
def mode_write(p, args, client):
    suffix = str(int(time.time()))
    name = '接线测试_INT2640_%s' % suffix
    created_id = None
    try:
        body = {
            'deviceName': name, 'model': 'INT2640_P1', 'deviceType': 'phone',
            'system': 'Android', 'systemVersion': '14', 'appName': 'probe',
            'appVersion': '1.0', 'description': 'INT-2640 探针自建，跑完删除',
            # 前端表单必填项（缺了保存会被 zod 拦在本地，测不到写路径）
            'serialNumber': 'SN_INT2640_%s' % suffix,
        }
        resp = client.request('POST', '/test-devices', body)
        created_id = (resp.get('data') or resp).get('id')
        created = p.api_device(client, created_id)
        p.check('create_phone_device', created.get('type') == 'phone',
                'id=%s type=%s' % (created_id, created.get('type')))

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
            page = ctx.new_page()
            p._page = page
            writes = []
            page.on('request', lambda r: writes.append(
                {'dir': 'REQ', 'method': r.method, 'url': r.url, 'body': r.post_data})
                if r.method in ('PUT', 'POST') and '/api/v1/test-devices' in r.url else None)
            page.on('response', lambda r: writes.append(
                {'dir': 'RESP', 'method': r.request.method, 'url': r.url, 'status': r.status})
                if r.request.method in ('PUT', 'POST') and '/api/v1/test-devices' in r.url else None)
            p.login(page)
            page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
            page.wait_for_selector('tbody tr', timeout=30000)
            page.wait_for_timeout(1200)
            search = page.locator("input[placeholder='搜索设备名称或型号']")
            search.fill(name)
            page.wait_for_timeout(2500)
            p.open_edit_drawer(page, name)
            closed, options = p.devices_drawer_state(page)
            p.check('write_drawer_unknown_label', closed == '未知', 'closed=%r' % closed)
            p.check('write_drawer_options', options == ['真机', 'HTTP API', 'Realtime WS', '未知'],
                    'options=%s' % options)
            p.shot(page, 'write_drawer_unknown_light')
            # 不改类型直接保存：后端原值应保留（数据不丢）
            dbg1 = p.save_drawer(page)
            print('SAVE1=' + json.dumps(dbg1, ensure_ascii=False), flush=True)
            after = p.api_device(client, created_id)
            p.check('save_without_change_keeps_raw_type', after.get('type') == 'phone',
                    'type=%s name=%s' % (after.get('type'), after.get('name')))
            p.check('save_without_change_keeps_name', after.get('name') == name,
                    'name=%r' % after.get('name'))
            # 改成三值之一：应写入 physical
            page.wait_for_timeout(800)
            dialogs = page.locator('[role=dialog]').count()
            print('AFTER_SAVE_DIALOGS=%d' % dialogs, flush=True)
            if dialogs == 0:
                p.open_edit_drawer(page, name)
            trig = p.type_trigger(page)
            print('BEFORE_PICK=%r' % (trig.inner_text() or '').strip(), flush=True)
            trig.click()
            page.wait_for_timeout(600)
            items = page.locator('[data-slot=select-item]')
            print('OPEN_ITEMS=%s' % [items.nth(i).inner_text().strip()
                                     for i in range(items.count())], flush=True)
            items.filter(has_text='真机').first.click()
            page.wait_for_timeout(700)
            print('AFTER_PICK=%r' % (p.type_trigger(page).inner_text() or '').strip(), flush=True)
            dbg2 = p.save_drawer(page)
            print('SAVE2=' + json.dumps(dbg2, ensure_ascii=False), flush=True)
            print('WRITES=' + json.dumps(writes, ensure_ascii=False), flush=True)
            after2 = p.api_device(client, created_id)
            p.check('save_picked_value_writes_three_value', after2.get('type') == 'physical',
                    'type=%s' % after2.get('type'))
            browser.close()
    finally:
        if created_id:
            try:
                client.request('DELETE', '/test-devices/%d' % created_id)
            except ApiError as exc:
                print('CLEANUP_FAIL=%s' % exc, flush=True)
            try:
                try:
                    gone = p.api_device(client, created_id)
                    gone = 'GET ok id=%s' % gone.get('id')
                except ApiError as exc:
                    gone = 'HTTP %s %s' % (exc.status, str(exc.body)[:80])
                names = [d['name'] for d in p.api_devices(client)]
                p.check('cleanup_removed', name not in names,
                        'list_has_name=%s get=%s' % (name in names, gone))
            except Exception as exc:  # noqa: BLE001
                print('CLEANUP_VERIFY_SKIP=%s' % exc, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['read', 'write'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    client = ApiClient(args.api)
    client.login(args.username, args.password)
    health = client.health()
    print('HEALTH_START=' + json.dumps(health, ensure_ascii=False), flush=True)
    if args.mode == 'read':
        mode_read(p, args, client)
    else:
        mode_write(p, args, client)
    health2 = client.health()
    print('HEALTH_END=' + json.dumps(health2, ensure_ascii=False), flush=True)
    p.check('health_stable', health2.get('database') == 'intelligent_audio_test',
            'database=%s' % health2.get('database'))
    fails = [c for c in p.checks if not c['ok']]
    print('CHECKS=%d FAIL=%d' % (len(p.checks), len(fails)), flush=True)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
