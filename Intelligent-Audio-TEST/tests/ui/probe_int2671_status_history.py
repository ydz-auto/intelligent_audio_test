# -*- coding: utf-8 -*-
"""INT-2671 设备「历史监控」列表可用性实测（React dev server + docker 真实库栈，只读）。

缺陷（P2）：
  1. 状态/操作历史恒「暂无历史记录」——前端只取 status-history 最新 200 条（实测全是
     health_check）再按分类前端过滤，状态类事件被挤出窗口；
  2. 历史行「设备」列恒「—」（前端取后端不存在的 device_name）；
  3. 「结果」列恒「—」（前端读 result，后端只给布尔 success）。

修复后本探针核对：
  1. 历史监控的 status-history 请求带 event_type（分类=多类型时按类型分别请求），
     不再出现「只取最新 200 条再前端过滤」的裸请求；
  2. 状态历史（默认近 7 天）行数 = 接口同窗口内状态类事件数，且不落空态；
  3. 操作历史（近 30 天）有行；
  4. 性能历史「设备」列显示设备名 + #id（不再是「—」），「结果」列按 success 出成功/失败图标；
  5. 浅色 / 深色截图 + 网络证据（URL / 状态码）。

只读：不提交任何写请求，不改库。
跑法（环境铁律：连 docker 栈 15000，不启动本地后端栈）：
  API_PROXY_TARGET=http://localhost:15000 node node_modules/@rsbuild/core/bin/rsbuild.js dev --port 5367
  python tests/ui/probe_int2671_status_history.py \
      --base http://localhost:5367 --api http://127.0.0.1:15000
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2671')

STATUS_TYPES = ['online', 'offline', 'connecting', 'disconnecting', 'error']
OPERATION_TYPES = ['operation']
PERFORMANCE_TYPES = ['health_check']
PER_PAGE = 200


def items_of(resp):
    data = resp.get('data') if isinstance(resp, dict) else None
    if isinstance(data, dict):
        return data.get('items') or []
    return data if isinstance(data, list) else []


def parse_wall(value):
    """后端 +08 墙钟裸串 → naive datetime（与前端 new Date(裸串) 同口径）。"""
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


def in_window(event, days):
    created = parse_wall(event.get('created_at'))
    return created is not None and created >= datetime.now() - timedelta(days=days)


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api = ApiClient(api_root)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []
        self.raw = {}

    def check(self, name, ok, detail, shot=None):
        rec = {'name': name, 'ok': bool(ok), 'detail': detail}
        if shot:
            rec['shot'] = shot
        self.checks.append(rec)
        print(('PASS ' if ok else 'FAIL ') + name + ' | ' + str(detail))

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, name)
        page.screenshot(path=path, full_page=True)
        return path

    def fetch(self, event_type, per_page=PER_PAGE):
        return items_of(self.api.request(
            'GET', '/test-devices/status-history',
            params={'page': 1, 'per_page': per_page, 'event_type': event_type}))

    # ── 页面 ──────────────────────────────────────────────
    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click('button[type=submit]')
        page.wait_for_url(lambda url: '/login' not in url, timeout=30000)
        page.wait_for_timeout(1500)

    def open_history(self, page):
        page.goto(self.base + '/devices', wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        page.get_by_role('switch', name='监控告警面板').click()
        page.wait_for_timeout(1200)
        page.get_by_role('tab', name='历史监控').click()
        page.wait_for_timeout(2000)
        self.hist_table = page.locator('table').filter(
            has=page.locator('th', has_text='事件类型')).first

    def history_rows(self, page, wait_ms=2500):
        page.wait_for_timeout(wait_ms)
        rows = self.hist_table.locator('tbody tr')
        out = []
        for i in range(rows.count()):
            cells = [c.strip() for c in rows.nth(i).locator('td').all_inner_texts()]
            ok_icons = rows.nth(i).locator('[aria-label="成功"]').count()
            fail_icons = rows.nth(i).locator('[aria-label="失败"]').count()
            out.append({'cells': cells, 'success': ok_icons, 'failed': fail_icons})
        return out

    def select_time_range(self, page, current, target):
        page.locator('button[role="combobox"]', has_text=current).first.click()
        page.wait_for_timeout(500)
        page.get_by_role('option', name=target).click()
        page.wait_for_timeout(2000)

    def run(self):
        self.api.login(self.username, self.password)

        devices = items_of(self.api.request(
            'GET', '/test-devices', params={'page': 1, 'per_page': 1000}))
        name_by_id = {d['id']: d.get('name') for d in devices}

        status_events = []
        for event_type in STATUS_TYPES:
            status_events += self.fetch(event_type)
        status_7d = [e for e in status_events if in_window(e, 7)]
        operation_30d = [e for e in self.fetch(OPERATION_TYPES[0]) if in_window(e, 30)]
        performance_200 = self.fetch(PERFORMANCE_TYPES[0])
        performance_7d = [e for e in performance_200 if in_window(e, 7)]
        self.raw = {
            'status_7d': len(status_7d),
            'status_by_type': {t: len(self.fetch(t)) for t in STATUS_TYPES},
            'operation_30d': len(operation_30d),
            'performance_7d': len(performance_7d),
        }

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050},
                                      record_har_path=os.path.join(ART, 'network.har'),
                                      record_har_content='omit')
            page = ctx.new_page()

            def on_request(req):
                if '/api/v1/test-devices/status-history' not in req.url:
                    return
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(req.url).query)
                self.net.append({
                    'url': req.url,
                    'event_type': (q.get('event_type') or [None])[0],
                    'page': (q.get('page') or [None])[0],
                    'per_page': (q.get('per_page') or [None])[0],
                })

            page.on('request', on_request)
            self.login(page)

            # ── 1) 状态历史（默认近 7 天）──
            self.open_history(page)
            rows = self.history_rows(page)
            self.check('状态历史有真实事件（不再恒「暂无历史记录」）',
                       len(rows) > 0 and len(rows) == len(status_7d),
                       f'界面行数={len(rows)}；接口近 7 天状态类事件={len(status_7d)}'
                       f'（按类型 {self.raw["status_by_type"]}）')
            legacy_empty = page.get_by_text('暂无历史记录').count()
            self.check('有数据时不出现「暂无历史记录」空态', legacy_empty == 0,
                       f'空态节点数={legacy_empty}')
            types_shown = {r['cells'][1] for r in rows if len(r['cells']) > 1}
            status_labels = {'上线', '离线', '连接中', '断开中', '错误'}
            self.check('状态历史页签只显示状态类事件',
                       bool(types_shown) and types_shown.issubset(status_labels),
                       f'出现的事件类型={sorted(types_shown)}')
            status_shot = self.shot(page, 'history-status-light.png')

            # ── 2) 操作历史（近 30 天）──
            page.get_by_role('tab', name='操作历史').click()
            self.select_time_range(page, '近7天', '近30天')
            op_rows = self.history_rows(page)
            self.check('操作历史有真实事件（近 30 天）',
                       len(op_rows) > 0 and len(op_rows) == len(operation_30d),
                       f'界面行数={len(op_rows)}；接口近 30 天操作事件={len(operation_30d)}')
            op_shot = self.shot(page, 'history-operation-light.png')

            # ── 3) 性能历史：设备 / 结果列 ──
            page.get_by_role('tab', name='性能历史').click()
            perf_rows = self.history_rows(page, wait_ms=3000)
            device_cells = [r['cells'][0] for r in perf_rows if r['cells']]
            named = [c for c in device_cells if '#' in c and '—' not in c]
            self.check('性能历史「设备」列显示设备名（不再是「—」）',
                       len(perf_rows) > 0 and len(named) == len(device_cells),
                       f'行数={len(perf_rows)}；展示名样本={device_cells[:3]}')
            id_ok = 0
            for cell in device_cells:
                m = re.search(r'#(\d+)', cell)
                if m and name_by_id.get(int(m.group(1))) and name_by_id[int(m.group(1))] in cell:
                    id_ok += 1
            self.check('设备名与 device_id 关联正确', id_ok == len(device_cells),
                       f'命中 {id_ok}/{len(device_cells)}')
            result_icon = sum(1 for r in perf_rows if r['success'] or r['failed'])
            self.check('性能历史「结果」列按 success 出成功/失败图标（不再是「—」）',
                       len(perf_rows) > 0 and result_icon == len(perf_rows),
                       f'有图标行={result_icon}/{len(perf_rows)}；'
                       f'成功 {sum(1 for r in perf_rows if r["success"])}，'
                       f'失败 {sum(1 for r in perf_rows if r["failed"])}')
            perf_shot = self.shot(page, 'history-performance-light.png')

            # ── 4) 网络证据：每个 status-history 请求都带 event_type ──
            self.check('status-history 请求全部按分类下推 event_type',
                       bool(self.net) and all(n['event_type'] for n in self.net),
                       f'{len(self.net)} 个请求；样本={[n["event_type"] for n in self.net][:8]}')
            self.check('分类=多类型时分别请求（状态页签出现多个 event_type）',
                       len({n['event_type'] for n in self.net if n['event_type'] in STATUS_TYPES})
                       >= 2,
                       f'请求过的类型={sorted({n["event_type"] for n in self.net})}')

            # ── 5) 深色 ──
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','dark')")
            self.open_history(page)
            is_dark = page.evaluate(
                "document.documentElement.classList.contains('dark')")
            self.check('深色模式已生效', is_dark, f'dark class={is_dark}')
            dark_rows = self.history_rows(page)
            self.check('深色下状态历史同样有行', len(dark_rows) > 0,
                       f'行数={len(dark_rows)}')
            dark_shot = self.shot(page, 'history-status-dark.png')
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','light')")

            ctx.close()
            browser.close()

        self.shots = {
            'status_light': status_shot,
            'operation_light': op_shot,
            'performance_light': perf_shot,
            'status_dark': dark_shot,
        }

    def passed(self):
        return all(c['ok'] for c in self.checks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5367')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    args = ap.parse_args()

    os.makedirs(ART, exist_ok=True)
    probe = Probe(args.base, args.api, args.username, args.password)
    probe.run()
    out = {'raw': probe.raw, 'checks': probe.checks, 'network': probe.net,
           'shots': probe.shots, 'passed': probe.passed()}
    with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('---')
    print('checks: %d/%d passed' % (sum(1 for c in probe.checks if c['ok']), len(probe.checks)))
    print('network:', len(probe.net), 'status-history requests')
    return 0 if probe.passed() else 1


if __name__ == '__main__':
    raise SystemExit(main())
