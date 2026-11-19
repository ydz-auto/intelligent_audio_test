# -*- coding: utf-8 -*-
"""INT-2655 设备域时间墙钟口径实测（React dev server + docker 真实库栈，只读）。

缺陷：device_service 的 created_at/updated_at/last_online_at 用 utc8now（东八区 aware）
落 `timestamp without time zone`，接口下发无时区后缀的 +08 墙钟裸串；前端按裸 UTC
解析（parseApiDateTime 补 Z）再转本地，页面恒晚/早 8 小时。

修复后本探针核对（同一时刻对照接口原值）：
  1. 设备管理 → 测试设备列表「最后在线」= 接口 last_online_at 原样（不再 +8）；
  2. 该行「操作 → 详情」弹窗「最后在线 / 更新时间」同上；
  3. 播放设备 / 测试 API 页签「更新时间」= 接口 updated_at 原样；
  4. 监控告警面板 → 历史监控「时间」= 接口 status-history created_at 原样；
  5. SPL 映射列表「更新时间」= 接口 /spl updated_at 原样；
  6. 浅色 / 深色截图 + 全程网络证据（URL / 状态码 / 关键字段）。

只读：不提交任何写请求，不改库。
跑法（环境铁律：连 docker 栈 15000/15173，不启动本地栈）：
  API_PROXY_TARGET=http://localhost:15000 pnpm dev --port 5362
  python tests/ui/probe_int2655_device_wall_clock.py \
      --base http://localhost:5362 --api http://127.0.0.1:15000
"""
import argparse
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2655')


def wall(value):
    """后端 +08 墙钟裸串 → 期望展示「YYYY-MM-DD HH:mm」（与 formatLocalWallClock 同口径）。"""
    if not value:
        return '—'
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})', value)
    return f'{m.group(1)} {m.group(2)}' if m else '—'


def items_of(resp):
    data = resp.get('data') if isinstance(resp, dict) else None
    if isinstance(data, dict):
        return data.get('items') or []
    return data if isinstance(data, list) else []


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api = ApiClient(api_root)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

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

    # ── 页面 ──────────────────────────────────────────────
    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click('button[type=submit]')
        page.wait_for_url(lambda url: '/login' not in url, timeout=30000)
        page.wait_for_timeout(1500)

    def goto(self, page, path):
        page.goto(self.base + path, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)

    def row_text(self, page, keyword):
        row = page.locator('tr', has_text=keyword).first
        row.wait_for(timeout=20000)
        return row.inner_text()

    def run(self):
        self.api.login(self.username, self.password)

        devices = items_of(self.api.request('GET', '/test-devices',
                                            params={'page': 1, 'per_page': 1000}))
        playback = items_of(self.api.request('GET', '/playback-devices',
                                            params={'page': 1, 'per_page': 1000}))
        apis = items_of(self.api.request('GET', '/apis',
                                         params={'page': 1, 'per_page': 1000}))
        history = items_of(self.api.request('GET', '/test-devices/status-history',
                                            params={'page': 1, 'per_page': 200}))
        spls = items_of(self.api.request('GET', '/spl',
                                         params={'page': 1, 'per_page': 1000}))

        dev = next(d for d in devices if d.get('name') == 'pura90gpt')
        pb = playback[0]
        api_dev = apis[0]
        hist = history[0]
        spl = spls[0]
        self.raw = {
            'device': {k: dev.get(k) for k in ('id', 'name', 'last_online_at', 'updated_at')},
            'playback': {k: pb.get(k) for k in ('id', 'name', 'updated_at')},
            'api': {k: api_dev.get(k) for k in ('id', 'name', 'updated_at')},
            'history': {k: hist.get(k) for k in ('id', 'device_id', 'created_at')},
            'spl': {k: spl.get(k) for k in ('id', 'name', 'updated_at')},
        }

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            har_path = os.path.join(ART, 'network.har')
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050},
                                      record_har_path=har_path,
                                      record_har_content='omit')
            page = ctx.new_page()

            def on_response(resp):
                url = resp.url
                if '/api/v1/' not in url:
                    return
                if any(k in url for k in ('test-devices', 'playback-devices', 'apis',
                                          'status-history', 'alarms', '/spl')):
                    self.net.append({'method': resp.request.method, 'url': url,
                                     'status': resp.status})

            page.on('response', on_response)
            self.login(page)

            # 1) 列表「最后在线」
            self.goto(page, '/devices')
            expected_last = wall(dev.get('last_online_at'))
            row = self.row_text(page, 'pura90gpt')
            self.check('设备列表 pura90gpt「最后在线」= 接口原值', expected_last in row,
                       f'期望含 {expected_last}；行文本={row[:200]}')
            bad = wall_add8(dev.get('last_online_at'))
            self.check('设备列表不再出现 +8 值', bad not in row, f'+8 值 {bad} 不应出现')
            light = self.shot(page, 'devices-light.png')

            # 1b) P3 同页：updated_at 同值时排序稳定（次级键 id），两次加载顺序一致
            def id_order(pg):
                tbl = pg.locator('table').first
                ids = []
                for i in range(tbl.locator('tbody tr').count()):
                    cells = [c.strip() for c in tbl.locator('tbody tr').nth(i).locator('td').all_inner_texts()]
                    ids += [c for c in cells if re.match(r'^#\d+$', c)]
                return ids

            order_a = id_order(page)
            self.goto(page, '/devices')
            order_b = id_order(page)
            self.check('设备列表排序稳定（两次加载 ID 顺序一致）',
                       bool(order_a) and order_a == order_b,
                       f'第一次={order_a}；第二次={order_b}')

            # 2) 详情弹窗
            page.get_by_role('button', name='操作 pura90gpt').click()
            page.get_by_role('menuitem', name='详情').click()
            dialog = page.get_by_role('dialog').last
            dialog.wait_for(timeout=15000)
            text = dialog.inner_text()
            expected_upd = wall(dev.get('updated_at'))
            self.check('详情「最后在线」= 接口原值', expected_last in text,
                       f'期望 {expected_last}')
            self.check('详情「更新时间」= 接口原值', expected_upd in text,
                       f'期望 {expected_upd}')
            self.check('详情不出现 +8 值', wall_add8(dev.get('updated_at')) not in text,
                       f'+8 值 {wall_add8(dev.get("updated_at"))} 不应出现')
            dialog_shot = self.shot(page, 'device-detail-light.png')
            dialog.get_by_role('button', name='关闭').click()
            page.wait_for_timeout(600)

            # 3) 播放设备 / 测试 API 页签「更新时间」
            page.get_by_role('tab', name='播放设备').click()
            page.wait_for_timeout(1500)
            pb_text = self.row_text(page, pb.get('name'))
            self.check('播放设备「更新时间」= 接口原值', wall(pb.get('updated_at')) in pb_text,
                       f'期望含 {wall(pb.get("updated_at"))}')
            page.get_by_role('tab', name='测试 API').click()
            page.wait_for_timeout(1500)
            api_text = self.row_text(page, api_dev.get('name'))
            self.check('测试 API「更新时间」= 接口原值', wall(api_dev.get('updated_at')) in api_text,
                       f'期望含 {wall(api_dev.get("updated_at"))}')
            page.get_by_role('tab', name='测试设备').click()
            page.wait_for_timeout(1000)

            # 4) 监控告警面板 → 历史监控「时间」
            page.get_by_role('switch', name='监控告警面板').click()
            page.wait_for_timeout(1500)
            page.get_by_role('tab', name='历史监控').click()
            page.wait_for_timeout(1500)
            # 默认「状态历史」只含 online/offline 事件（近期库里都是 health_check，
            # 落在性能历史），切到「性能历史」才能拿到近期真实事件做时间断言。
            page.get_by_role('tab', name='性能历史').click()
            page.wait_for_timeout(2500)
            # 事件持续写入（健康检查）；按「事件类型」表头锁定历史表，取当前页展示的时间，
            # 与同期接口前 200 条的 created_at 墙钟集合对照（避免「最新一条已换行」竞态）。
            hist_table = page.locator('table').filter(has=page.locator('th', has_text='事件类型')).first
            hist_table.wait_for(timeout=15000)
            shown_times = []
            rows = hist_table.locator('tbody tr')
            for i in range(min(rows.count(), 10)):
                cells = [c.strip() for c in rows.nth(i).locator('td').all_inner_texts()]
                shown_times += [c for c in cells if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$', c)]
            fresh = items_of(self.api.request('GET', '/test-devices/status-history',
                                              params={'page': 1, 'per_page': 200}))
            raw_wall = {wall(e.get('created_at')) for e in fresh}
            hit = [t for t in shown_times if t in raw_wall]
            self.check('历史监控「时间」= 接口 created_at 墙钟口径',
                       bool(shown_times) and len(hit) == len(shown_times),
                       f'界面时间样本={shown_times[:3]}；命中 {len(hit)}/{len(shown_times)}')
            monitor_shot = self.shot(page, 'devices-monitor-light.png')

            # 5) SPL 映射列表「更新时间」
            self.goto(page, '/SPLMapping')
            spl_name = spl.get('name')
            spl_row = page.locator('tr', has_text=spl_name).first
            spl_row.wait_for(timeout=20000)
            spl_text = spl_row.inner_text()
            self.check('SPL 映射「更新时间」= 接口原值', wall(spl.get('updated_at')) in spl_text,
                       f'期望含 {wall(spl.get("updated_at"))}；行={spl_text[:200]}')
            spl_shot = self.shot(page, 'spl-mapping-light.png')

            # 6) 深色
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','dark')")
            self.goto(page, '/devices')
            is_dark = page.evaluate("document.documentElement.classList.contains('dark')")
            self.check('深色模式已生效', is_dark, f'dark class={is_dark}')
            dark_dev = self.shot(page, 'devices-dark.png')
            self.goto(page, '/SPLMapping')
            dark_spl = self.shot(page, 'spl-mapping-dark.png')
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','light')")

            ctx.close()  # 关闭上下文时落盘 network.har（网络证据）
            browser.close()

        self.shots = {
            'devices_light': light, 'detail_light': dialog_shot,
            'monitor_light': monitor_shot, 'spl_light': spl_shot,
            'devices_dark': dark_dev, 'spl_dark': dark_spl,
        }

    def passed(self):
        return all(c['ok'] for c in self.checks)


def wall_add8(value):
    """错误口径下的展示值（裸串当 UTC 再 +8），用于断言不再出现。"""
    from datetime import datetime, timedelta
    dt = datetime.strptime(value[:19], '%Y-%m-%dT%H:%M:%S') + timedelta(hours=8)
    return dt.strftime('%Y-%m-%d %H:%M')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5362')
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
    print('network:', len(probe.net), 'responses')
    return 0 if probe.passed() else 1


if __name__ == '__main__':
    raise SystemExit(main())
