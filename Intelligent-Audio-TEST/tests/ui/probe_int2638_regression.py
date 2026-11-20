# -*- coding: utf-8 -*-
"""INT-2638 前端回归日巡补充实测（React，docker 真实库栈，只读）。

本探针补两件事：

  1. `center`：复现 / 报告中心在整链顺序下「页面加载中…」迟迟不出行的口径，
     判定是页面卡死（缺陷）还是慢加载（冒烟超时），并记录首个数据响应耗时。
  2. `int2636`：复核 INT-2636（c66784c68，React typecheck 清零）带来的前端增量：
     - 评估维度页（/Evaluation）筛选栏按「去算法(全局化)」不再有算法 facet；
     - 日志页（/logs）筛选栏不再有算法 Select；
     - 全局算法切换器仍可用（顶栏「算法 全部算法」）。
     可用 --base 指向 docker 15173（部署镜像）或本地 dev server（V10.11.2 代码），
     两侧对比即可看出镜像是否含该提交。

只读语义：不提交任何写请求、不写库、无 teardown。
跑法：
  python tests/ui/probe_int2638_regression.py center --base http://localhost:15173 \
      --api http://localhost:15000
  python tests/ui/probe_int2638_regression.py int2636 --base http://localhost:15173
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2638')


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-40s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        tag = '%s%s' % (name, '_dark' if dark else '')
        path = os.path.join(ART, tag + '.png')
        page.screenshot(path=path)
        return path

    def set_dark(self, page, on):
        page.evaluate("on => document.documentElement.classList.toggle('dark', on)", on)
        page.wait_for_timeout(600)

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)


def mode_center(p, args):
    """复现报告中心慢加载：记录从 goto 到首行出现的时间与首包耗时。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        req_start = {}
        done = []

        def on_req(req):
            if '/api/v1/' in req.url:
                req_start[req.url] = time.time()

        def on_resp(resp):
            if '/api/v1/' in resp.url:
                t0 = req_start.get(resp.url, time.time())
                done.append({'url': resp.url, 'status': resp.status,
                             'ms': int((time.time() - t0) * 1000)})

        page.on('request', on_req)
        page.on('response', on_resp)
        p.login(page)
        # 先走一遍用例详情（对齐 int1919 链 3 → 4 的顺序）
        page.goto(p.base + '/testcases', wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        try:
            row = page.locator('tbody tr').first
            if row.count():
                row.click()
                page.wait_for_timeout(2500)
                page.keyboard.press('Escape')
                page.wait_for_timeout(800)
        except Exception as exc:
            print('case-detail prelude skipped:', exc, flush=True)

        t0 = time.time()
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        loading = True
        rows = 0
        elapsed = 0.0
        for _ in range(120):  # ≤60s
            page.wait_for_timeout(500)
            elapsed = time.time() - t0
            try:
                rows = page.locator('tbody tr').count()
            except Exception:
                rows = 0
            body = page.inner_text('body')
            if rows > 0 and '页面加载中' not in body:
                loading = False
                break
            if '页面加载中' not in body and ('报告列表加载失败' in body or '加载失败' in body):
                loading = False
                break
        body = page.inner_text('body')
        p.check('center_rows_loaded', (not loading) and rows > 0,
                'rows=%d elapsed=%.1fs loading=%s' % (rows, elapsed, loading))
        p.shot(page, 'center_loaded')
        slow = sorted(done, key=lambda d: -d['ms'])[:6]
        relevant = [d for d in done if 'report' in d['url']]
        print('TOP_SLOW=' + json.dumps(slow, ensure_ascii=False), flush=True)
        print('REPORT_APIS=' + json.dumps(relevant[:12], ensure_ascii=False), flush=True)
        browser.close()


def _toolbar_buttons(page):
    """页面主内容区按钮/可点控件文本（排除侧栏与顶栏）。"""
    return page.evaluate("""() => {
      const root = document.querySelector('main') || document.body;
      return Array.from(root.querySelectorAll('button, [role=combobox]'))
        .map(e => (e.innerText || e.getAttribute('aria-label') || '').trim())
        .filter(Boolean);
    }""")


def mode_int2636(p, args):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text)
                if m.type == 'error' else None)
        p.login(page)

        # 1) 评估维度页：筛选栏不得再有算法 facet
        page.goto(p.base + '/Evaluation', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        labels = _toolbar_buttons(page)
        has_algo_facet = any('算法' in t for t in labels)
        p.check('evaluation_no_algo_facet', not has_algo_facet,
                'controls=%s' % labels[:24])
        p.shot(page, 'int2636_evaluation_light')
        p.set_dark(page, True)
        p.shot(page, 'int2636_evaluation_dark')
        p.set_dark(page, False)

        # 2) 日志页：筛选栏不得再有算法 Select
        page.goto(p.base + '/logs', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        labels = _toolbar_buttons(page)
        has_algo_sel = any(t.strip() == '算法' or t.startswith('全部算法')
                           for t in labels)
        p.check('logs_no_algo_select', not has_algo_sel,
                'controls=%s' % labels[:24])
        p.shot(page, 'int2636_logs_light')
        p.set_dark(page, True)
        p.shot(page, 'int2636_logs_dark')
        p.set_dark(page, False)

        # 3) 全局算法切换器仍可用（顶栏）
        sw = page.locator("[aria-label*='算法'], button:has-text('全部算法')").first
        ok_sw = sw.count() > 0
        p.check('global_algorithm_switcher_present', ok_sw,
                'switcher_count=%d' % sw.count())

        print('CONSOLE_ERRORS=' + json.dumps(console_errors[:10], ensure_ascii=False),
              flush=True)
        browser.close()


def mode_reportdark(p, args):
    """报告详情独立页：显式切深色后核 body 背景与截图（int1854 的 set_theme 只写
    localStorage，深色常被拍成浅色，需自己复核）。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        row = page.locator('tbody tr').first
        row.click()
        page.wait_for_timeout(5000)
        # 浅色：强制 prefers-color-scheme=light 后重载
        page.emulate_media(color_scheme='light')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        bg_light = page.evaluate("getComputedStyle(document.body).backgroundColor")
        p.shot(page, 'reportdetail_light')
        # 深色
        page.emulate_media(color_scheme='dark')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        bg_dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
        cls = page.evaluate("document.documentElement.className")
        p.check('report_detail_dark_applied',
                bg_dark != bg_light and 'dark' in cls,
                'light=%s dark=%s class=%s' % (bg_light, bg_dark, cls))
        p.shot(page, 'reportdetail_dark')
        browser.close()


def mode_api(p, args):
    """接口抽样：核对 /health 库名与各域 total（与页面计数交叉核对用）。"""
    import httpx
    from tests.ui.utils.api_client import ApiClient
    health = httpx.get(p.api + '/health', timeout=20, trust_env=False).json()
    print('HEALTH=' + json.dumps(health, ensure_ascii=False), flush=True)
    api = ApiClient(p.api)
    api.login(p.username, p.password)
    h = {'Authorization': 'Bearer %s' % api.token}
    paths = {
        'tasks': '/api/v1/tasks?page=1&per_page=1',
        'testcases': '/api/v1/testcases?page=1&per_page=1',
        'audios': '/api/v1/audios?page=1&per_page=1',
        'reports': '/api/v1/reports?page=1&per_page=1&deleted=false',
        'test-devices': '/api/v1/test-devices?page=1&per_page=1',
        'groups': '/api/v1/groups',
        'evaluation-dimensions': '/api/v1/evaluation/dimensions?per_page=1',
        'agent-skills': '/api/v1/agent/skills',
        'agent-providers': '/api/v1/agent/providers',
        'algorithm-options': '/api/v1/algorithm/options',
    }
    out = {}
    for name, path in paths.items():
        t0 = time.time()
        r = httpx.get(p.api + path, headers=h, timeout=60, trust_env=False)
        ms = int((time.time() - t0) * 1000)
        try:
            body = r.json()
        except Exception:
            body = {}
        if isinstance(body.get('data'), dict):
            total = body['data'].get('total')
        elif isinstance(body.get('data'), list):
            total = len(body['data'])
        elif isinstance(body.get('items'), list):
            total = len(body['items'])
        elif isinstance(body.get('algorithms'), list):
            total = len(body['algorithms'])
        else:
            total = None
        out[name] = {'status': r.status_code, 'total': total, 'ms': ms}
    p.check('api_sampling_ok', all(v['status'] == 200 for v in out.values()),
            json.dumps(out, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['center', 'int2636', 'reportdark', 'api'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    if args.mode == 'center':
        mode_center(p, args)
    elif args.mode == 'reportdark':
        mode_reportdark(p, args)
    elif args.mode == 'api':
        mode_api(p, args)
    else:
        mode_int2636(p, args)
    fails = [c for c in p.checks if not c['ok']]
    print('CHECKS=%d FAIL=%d' % (len(p.checks), len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
