# -*- coding: utf-8 -*-
"""INT-2669 返工补测：设备页闭环（React docker 栈 15173，只读）。

审计打回项 1（P2 范围缺口）：卡面要求「设备（含列表 / 详情 / 弹窗 / 空态 / 错误态）」，
上一轮只有列表截图。本脚本按闭环逐项取证，全部只读、不写库：

  列表    — 测试设备 / 播放设备 / 测试 API 三页签，渲染行数与接口返回逐页对齐；
  详情    — 测试设备 / 播放设备行「详情」弹窗，名称 / 型号 / 序列号 / 实验室 / 状态与接口一致；
  弹窗    — 编辑抽屉（回显核对，取消不保存）/ 删除确认（取消不删）/ 关联声压映射（取消不关联）；
  监控    — 监控告警 → 历史监控 → 统计分析区现状（演示数据 + 是否请求真实端点）；
  空态    — 搜索不存在的关键词 → 「未找到匹配的设备」，清空恢复；
  错误态  — CDP Network.setBlockedURLs 拦截 test-devices 接口 → 错误态 + 重试恢复；
  浅/深色 — 列表、详情弹窗、监控统计区各一张深色。

跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2669_devices.py \
      --base http://localhost:15173 --api http://127.0.0.1:15000
"""
import argparse
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

import httpx  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2669')
EMPTY_KEYWORD = '接线测试_不存在_INT2669'


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api_root = api_root.rstrip('/')
        self.api = ApiClient(api_root)
        self.api.login(username, password)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-44s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def skip(self, name, detail):
        self.checks.append({'name': name, 'ok': True, 'skipped': True, 'detail': detail})
        print('[SKIP] %-44s %s' % (name, detail), flush=True)

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s.png' % name)
        page.screenshot(path=path, full_page=False)
        print('SHOT=%s' % path, flush=True)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1500)

    def watch(self, page):
        def on_resp(resp):
            url = resp.url
            if '/api/v1/' in url:
                self.net.append({'m': resp.request.method, 's': resp.status, 'u': url[:300]})
        page.on('response', on_resp)

    def bad_requests(self, since=0):
        return [n for n in self.net[since:] if isinstance(n.get('s'), int) and n['s'] >= 400]

    def api_get_url(self, url):
        """带登录态直接重放页面发出的 GET，用于「接口 vs 渲染」对齐。"""
        r = httpx.get(url, headers={'Authorization': 'Bearer %s' % self.api.token},
                      timeout=30, trust_env=False)
        return r.status_code, r.json()

    def visible_text(self, page):
        return page.locator('body').inner_text()

    def last_api_call(self, path, since=0):
        """按 URL 路径精确匹配最后一次 GET（避免 /test-devices 命中 status-history 等子路径）。"""
        hits = [n for n in self.net[since:]
                if n['m'] == 'GET'
                and urllib.parse.urlparse(n['u']).path.rstrip('/') == path.rstrip('/')]
        return hits[-1] if hits else None

    def visible_dialog_text(self, page):
        # 注意：fixed 定位元素的 offsetParent 恒为 null，不能用它判可见
        return page.evaluate("""() => {
          const ds = [...document.querySelectorAll('[role=dialog],[role=alertdialog]')]
            .filter(d => d.getClientRects().length > 0
                         && getComputedStyle(d).visibility !== 'hidden');
          const d = ds[ds.length - 1];
          return d ? d.innerText : '';
        }""")

    def close_top_dialog(self, page, button_text='取消'):
        dlg = page.locator('[role=dialog]:visible, [role=alertdialog]:visible').last
        try:
            dlg.get_by_role('button', name=button_text, exact=True).click(timeout=5000)
        except Exception:
            page.keyboard.press('Escape')
        page.wait_for_timeout(600)

    def open_row_menu(self, page, idx=0):
        triggers = page.locator("button[aria-label^='操作 ']")
        triggers.nth(idx).click()
        page.wait_for_timeout(600)

    def click_menu_item(self, page, label):
        page.get_by_role('menuitem', name=label, exact=True).first.click()
        page.wait_for_timeout(1200)


def _items(payload):
    data = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return data.get('items') or []
    return data if isinstance(data, list) else []


def _total(payload):
    data = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return data.get('total')
    return None


def list_alignment(p, page, label, api_path, since=0):
    """渲染行数与页面自己发出的列表接口对齐。

    设备页是「全量拉取（per_page=1000）+ 前端分页」，所以首屏渲染行数 =
    min(接口 items, 当前 pageSize)，页脚「共 N 条」= 接口 total。
    """
    full_path = '/api/v1' + api_path
    call = p.last_api_call(full_path, since)
    if not call:
        p.check('%s_list_api' % label, False, '页面未发出列表请求（path=%s）' % full_path)
        return None
    status, payload = p.api_get_url(call['u'])
    items = _items(payload)
    total = _total(payload)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(call['u']).query)
    page_size = int((query.get('pageSize') or [20])[0])
    rows = page.locator('table tbody tr').count()
    body = p.visible_text(page)
    count_txt = (re.findall(r'共\s*\d+\s*条', body) or [''])[0]
    expected_rows = min(len(items), page_size) if isinstance(total, int) else len(items)
    p.check('%s_list_api_ok' % label, status == 200 and isinstance(total, int),
            'GET %s status=%s total=%s items=%d 页脚=%s' % (
                urllib.parse.urlparse(call['u']).path, status, total, len(items), count_txt))
    p.check('%s_list_render_matches_api' % label,
            rows == expected_rows
            and (total is None or count_txt.replace(' ', '') == '共%d条' % total),
            'rows=%d 期望=%d（min(items %d,pageSize %d)） total=%s 页脚=%s' % (
                rows, expected_rows, len(items), page_size, total, count_txt))
    return {'items': items, 'total': total, 'rows': rows, 'status': status}


def detail_closure(p, page, items, kind_label):
    """行「详情」弹窗：按弹窗里的 #id 找到对应接口记录，逐字段核对渲染。"""
    p.open_row_menu(page, 0)
    p.click_menu_item(page, '详情')
    txt = p.visible_dialog_text(page)
    page.wait_for_timeout(400)
    m = re.search(r'#(\d+)', txt)
    dev_id = int(m.group(1)) if m else None
    device = next((it for it in items if it.get('id') == dev_id), None)
    if device is None:  # 兜底：按名称匹配
        device = next((it for it in items
                       if it.get('name') and str(it['name']) in txt), None)
    device = device or {}
    ok_title = ('%s详情' % kind_label) in txt
    ok_id = device.get('id') == dev_id
    ok_name = str(device.get('name') or '') in txt
    serial = device.get('serial_number') or device.get('device_unique_id') or ''
    ok_serial = (not serial) or (str(serial) in txt)
    lab = device.get('lab_name') or ''
    ok_lab = (not lab) or (lab in txt)
    p.check('%s_detail_rendered' % kind_label,
            ok_title and ok_id and ok_name and ok_serial and ok_lab,
            'id=%s 接口#%s title=%s name=%s serial=%s lab=%s | %s' % (
                dev_id, device.get('id'), ok_title, ok_name, ok_serial, ok_lab,
                txt[:150].replace('\n', ' ')))
    slug = 'test' if kind_label == '测试设备' else 'playback'
    p.shot(page, 'devices_detail_%s_light' % slug)
    page.emulate_media(color_scheme='dark')
    page.wait_for_timeout(700)
    p.shot(page, 'devices_detail_%s_dark' % slug)
    page.emulate_media(color_scheme='light')
    page.wait_for_timeout(400)
    p.close_top_dialog(page, '关闭')
    return device


def edit_echo(p, page, device):
    p.open_row_menu(page, 0)
    p.click_menu_item(page, '编辑')
    page.wait_for_timeout(800)
    txt = p.visible_dialog_text(page)
    inputs = page.locator('[role=dialog]:visible input')
    vals = [inputs.nth(i).input_value() for i in range(min(inputs.count(), 5))]
    p.check('devices_edit_echo', ('编辑设备' in txt) and (str(device.get('name')) in vals),
            'title=%s 前5个输入=%s' % ('编辑设备' in txt, [v[:40] for v in vals]))
    p.shot(page, 'devices_edit_light')
    p.close_top_dialog(page, '取消')


def delete_cancel(p, page, device):
    p.open_row_menu(page, 0)
    p.click_menu_item(page, '删除')
    page.wait_for_timeout(800)
    txt = p.visible_dialog_text(page)
    name = str(device.get('name') or '')
    p.check('devices_delete_confirm', ('删除设备' in txt) and (name in txt) and ('不可撤销' in txt),
            txt[:160].replace('\n', ' '))
    p.shot(page, 'devices_delete_light')
    p.close_top_dialog(page, '取消')
    # 取消后列表仍在（没有误删）
    page.wait_for_timeout(800)
    rows = page.locator('table tbody tr').count()
    p.check('devices_delete_cancelled_kept_rows', rows > 0, 'rows=%d' % rows)


def assoc_spl(p, page, playback_device):
    p.open_row_menu(page, 0)
    p.click_menu_item(page, '关联声压映射')
    page.wait_for_timeout(900)
    txt = p.visible_dialog_text(page)
    has_select = page.locator("[role=dialog]:visible [aria-label='选择声压映射']").count() > 0
    name = str(playback_device.get('name') or '')
    p.check('devices_assoc_spl_dialog', ('关联声压映射' in txt) and (name in txt) and has_select,
            'title=%s name=%s select=%s | %s' % (
                '关联声压映射' in txt, name in txt, has_select, txt[:140].replace('\n', ' ')))
    p.shot(page, 'devices_assoc_spl_light')
    p.close_top_dialog(page, '取消')


def monitor_stats(p, page):
    """监控告警 → 历史监控 → 统计分析（P3 缺陷现场取证）。"""
    mark = len(p.net)
    page.get_by_role('button', name=re.compile('监控告警')).first.click()
    page.wait_for_timeout(1500)
    page.get_by_role('tab', name='历史监控', exact=True).click()
    page.wait_for_timeout(2500)
    body = p.visible_text(page)
    demo = '演示数据' in body
    stats = '统计分析' in body
    stale = '后端暂无历史监控指标端点' in body
    calls = [n for n in p.net[mark:] if 'monitor-stats' in n['u']]
    p.check('monitor_stats_rendered', stats and demo,
            '统计分析=%s 演示数据=%s 过期文案=%s calls=%d' % (stats, demo, stale, len(calls)))
    p.check('monitor_stats_no_real_endpoint_call', len(calls) == 0,
            '页面调用 monitor-stats 次数=%d（期望 0 = 仍在用 mock）' % len(calls))
    p.shot(page, 'devices_monitor_stats_light')
    page.emulate_media(color_scheme='dark')
    page.wait_for_timeout(800)
    p.shot(page, 'devices_monitor_stats_dark')
    page.emulate_media(color_scheme='light')
    page.wait_for_timeout(400)


def empty_state(p, page):
    box = page.locator("input[aria-label='搜索设备名称或型号']").first
    box.fill(EMPTY_KEYWORD)
    page.wait_for_timeout(2200)
    body = p.visible_text(page)
    p.check('devices_empty_state', '未找到匹配的设备' in body,
            '空态文案命中=%s | %s' % ('未找到匹配的设备' in body, body[:120].replace('\n', ' ')))
    p.shot(page, 'devices_empty_light')
    box.fill('')
    page.wait_for_timeout(2200)
    rows = page.locator('table tbody tr').count()
    p.check('devices_empty_restored', rows > 0 and '未找到匹配的设备' not in p.visible_text(page),
            '恢复后 rows=%d' % rows)


def error_state(p, page, ctx):
    cdp = ctx.new_cdp_session(page)
    cdp.send('Network.enable')
    cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/test-devices*']})
    page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
    page.wait_for_timeout(4500)
    body = p.visible_text(page)
    err = ('设备列表加载失败' in body) or ('获取失败' in body)
    retry = ('重试' in body)
    p.check('devices_error_state', err and retry, 'error=%s retry=%s | %s' % (
        err, retry, body[:160].replace('\n', ' ')))
    p.shot(page, 'devices_error_light')
    cdp.send('Network.setBlockedURLs', {'urls': []})
    clicked = False
    btns = page.get_by_role('button', name='重试')
    if btns.count() > 0:
        btns.first.click()
        clicked = True
    else:
        page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    body2 = p.visible_text(page)
    rows = page.locator('table tbody tr').count()
    p.check('devices_error_recovered', rows > 0 and '设备列表加载失败' not in body2,
            'retried=%s rows=%d' % (clicked, rows))
    p.shot(page, 'devices_error_recovered_light')


def run(p, args):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.watch(page)
        p.login(page)

        # ── 测试设备列表 ────────────────────────────────
        mark = len(p.net)
        page.goto(p.base + '/devices', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        body = p.visible_text(page)
        p.check('devices_page_renders',
                '设备管理' in body and '测试设备' in body
                and page.locator("input[aria-label='搜索设备名称或型号']").count() > 0,
                '设备管理=%s 测试设备=%s 搜索框=%s' % (
                    '设备管理' in body, '测试设备' in body,
                    page.locator("input[aria-label='搜索设备名称或型号']").count()))
        aligned = list_alignment(p, page, 'devices_test', '/test-devices', since=mark)
        bad = p.bad_requests(mark)
        p.check('devices_list_no_4xx5xx', not bad, 'bad=%s' % bad[:3])
        page.emulate_media(color_scheme='dark')
        page.wait_for_timeout(700)
        p.shot(page, 'devices_list_dark')
        page.emulate_media(color_scheme='light')
        page.wait_for_timeout(500)
        p.shot(page, 'devices_list_light')

        items = (aligned or {}).get('items') or []
        if items:
            dev = detail_closure(p, page, items, '测试设备')
            if dev:
                edit_echo(p, page, dev)
                delete_cancel(p, page, dev)
        monitor_stats(p, page)
        empty_state(p, page)

        # ── 播放设备页签 ────────────────────────────────
        mark = len(p.net)
        page.goto(p.base + '/devices/playback', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        play = list_alignment(p, page, 'devices_playback', '/playback-devices', since=mark)
        p.shot(page, 'devices_playback_list_light')
        play_items = (play or {}).get('items') or []
        if play_items:
            pdev = detail_closure(p, page, play_items, '播放设备')
            if pdev:
                assoc_spl(p, page, pdev)

        # ── 测试 API 页签（列表） ───────────────────────
        mark = len(p.net)
        page.goto(p.base + '/devices/api', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        list_alignment(p, page, 'devices_api', '/apis', since=mark)
        p.shot(page, 'devices_api_list_light')

        # ── 错误态（放在最后：会整页重载） ──────────────
        error_state(p, page, ctx)

        ctx.close()
        browser.close()


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    run(p, args)
    os.makedirs(ART, exist_ok=True)
    out = os.path.join(ART, 'result_devices.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'checks': p.checks, 'network': p.net[-120:]}, fh, ensure_ascii=False, indent=1)
    passed = sum(1 for c in p.checks if c['ok'])
    print('PASSED=%d FAILED=%d' % (passed, len(p.checks) - passed), flush=True)
    print('SUMMARY_JSON=%s' % out, flush=True)
    return 0 if passed == len(p.checks) else 1


if __name__ == '__main__':
    sys.exit(main())
