# -*- coding: utf-8 -*-
"""INT-2664 已发布任务「发布时间」墙钟口径实测（React dev server + docker 真实库栈，只读）。

缺陷：task_service 的 published_tasks.published_at 用 utc8now（东八区）落
`timestamp without time zone`，接口下发无时区后缀的 +08 墙钟裸串
（如 `2026-11-20T10:01:51.313234`）；前端误走 formatDateTime（按裸 UTC 解析再转本地），
页面恒晚 8 小时（10:01 显示成 18:01）。

修复后本探针核对（同一时刻对照接口原值）：
  1. 任务管理 → 已发布：列表行「发布人/发布时间」= 接口 published_at 原样；
  2. 展开「版本详情」→ 版本历史「发布时间」= 接口 versions[].published_at 原样；
  3. 同屏不再出现 +8 展示值；
  4. 浅色 / 深色截图 + 全程网络证据（UI 自身请求 URL / 状态码，落 HAR）。

只读：不提交任何写请求，不改库。
跑法（环境铁律：连 docker 栈 15000，不启动本地栈）：
  API_PROXY_TARGET=http://localhost:15000 pnpm dev --port 5330
  python tests/ui/probe_int2664_published_wall_clock.py \
      --base http://localhost:5330 --api http://127.0.0.1:15000
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

ART = os.path.join(HERE, 'artifacts', 'int2664')


def wall(value):
    """后端 +08 墙钟裸串 → 期望展示「YYYY-MM-DD HH:mm」（与 formatLocalWallClock 同口径）。"""
    if not value:
        return '—'
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})', value)
    return f'{m.group(1)} {m.group(2)}' if m else '—'


def wall_add8(value):
    """错误口径下的展示值（裸串当 UTC 再 +8），用于断言不再出现。"""
    if not value:
        return None
    dt = datetime.strptime(value[:19], '%Y-%m-%dT%H:%M:%S') + timedelta(hours=8)
    return dt.strftime('%Y-%m-%d %H:%M')


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api = ApiClient(api_root)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []
        self.raw = {}

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name + ' | ' + str(detail), flush=True)

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, name)
        page.screenshot(path=path, full_page=True)
        print('SHOT=' + path, flush=True)
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

    def goto_published(self, page):
        page.goto(self.base + '/tasks/published', wait_until='domcontentloaded')
        page.wait_for_selector('table', timeout=30000)
        page.wait_for_timeout(1500)

    def run(self):
        self.api.login(self.username, self.password)
        resp = self.api.request('GET', '/published-tasks',
                                params={'page': 1, 'per_page': 100})
        items = ((resp.get('data') or {}).get('items')) or []
        assert items, '已发布任务列表为空，无法核对'
        details = {}
        for item in items:
            d = self.api.request('GET', '/published-tasks/%d' % item['id'])
            details[item['id']] = d.get('data', d)
        self.raw = {
            'items': [{k: it.get(k) for k in ('id', 'name', 'status', 'published_at')}
                      for it in items],
            'version_times': {
                it['id']: [v.get('published_at')
                           for v in (details[it['id']].get('versions') or [])]
                for it in items
            },
        }
        with open(os.path.join(ART, 'raw.json'), 'w', encoding='utf-8') as f:
            json.dump(self.raw, f, ensure_ascii=False, indent=1)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            har_path = os.path.join(ART, 'network.har')
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050},
                                      record_har_path=har_path,
                                      record_har_content='omit')
            page = ctx.new_page()

            def on_response(r):
                if '/api/v1/published-tasks' in r.url:
                    self.net.append({'method': r.request.method, 'url': r.url,
                                     'status': r.status})

            page.on('response', on_response)
            self.login(page)

            # 1) 列表「发布人/发布时间」
            self.goto_published(page)
            table_text = page.locator('table').first.inner_text()
            for item in items:
                expect = wall(item.get('published_at'))
                self.check(
                    '列表行 #%d「发布时间」= 接口原值' % item['id'],
                    expect in table_text,
                    '期望含 %s；接口原值=%s' % (expect, item.get('published_at')))
                bad = wall_add8(item.get('published_at'))
                if bad:
                    self.check('列表行 #%d 不出现 +8 值' % item['id'], bad not in table_text,
                               '+8 值 %s 不应出现' % bad)
            light = self.shot(page, 'published-light.png')

            # 2) 展开版本历史
            target = items[0]
            row = page.locator('tr', has_text=target['name']).first
            row.wait_for(timeout=20000)
            row.get_by_role('button', name='展开版本详情').click()
            page.wait_for_selector('text=版本历史', timeout=30000)
            page.wait_for_timeout(800)
            expand = row.locator('xpath=following-sibling::tr[1]')
            expand_text = expand.inner_text()
            for vt in details[target['id']].get('versions') or []:
                expect = wall(vt.get('published_at'))
                self.check(
                    '版本历史 v%s「发布时间」= 接口原值' % vt.get('version'),
                    expect in expand_text,
                    '期望含 %s；接口原值=%s' % (expect, vt.get('published_at')))
                bad = wall_add8(vt.get('published_at'))
                if bad:
                    self.check('版本历史 v%s 不出现 +8 值' % vt.get('version'),
                               bad not in expand_text, '+8 值 %s 不应出现' % bad)
            expanded = self.shot(page, 'published-expanded-light.png')

            # 3) 空态（搜索不存在的关键字）：页面空态文案正常
            search = page.get_by_placeholder('搜索任务名称、描述或标签')
            search.fill('INT2664_不存在的关键字')
            page.get_by_role('button', name='查询').click()
            page.wait_for_timeout(1500)
            self.check('无结果搜索 → 空态', page.locator('text=暂无已发布任务').count() > 0,
                       '空态文案「暂无已发布任务」')
            empty = self.shot(page, 'published-empty-light.png')
            search.fill('')
            page.get_by_role('button', name='查询').click()
            page.wait_for_timeout(1200)

            # 4) 深色
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','dark')")
            self.goto_published(page)
            is_dark = page.evaluate(
                "document.documentElement.classList.contains('dark')")
            self.check('深色模式已生效', is_dark, 'dark class=%s' % is_dark)
            dark = self.shot(page, 'published-dark.png')
            page.evaluate("localStorage.setItem('iatp:theme:v1:mode','light')")

            ctx.close()  # 关闭上下文时落盘 network.har
            browser.close()

        self.shots = {'list_light': light, 'expanded_light': expanded,
                      'empty_light': empty, 'list_dark': dark}

    def passed(self):
        return all(c['ok'] for c in self.checks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5330')
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
    print('checks: %d/%d passed' % (sum(1 for c in probe.checks if c['ok']),
                                    len(probe.checks)))
    print('network: %d responses' % len(probe.net))
    return 0 if probe.passed() else 1


if __name__ == '__main__':
    raise SystemExit(main())
