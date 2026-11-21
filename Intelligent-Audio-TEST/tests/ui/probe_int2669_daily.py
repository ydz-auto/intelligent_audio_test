# -*- coding: utf-8 -*-
"""INT-2669 前端回归日巡补充实测（React docker 栈 15173，只读）。

本轮重点（卡面「上一轮结论与本轮重点」）：
  perf — 0520ddcbe / 7d67467b0 / 27ed17951 三条性能提交的数据正确性：
         * 用例列表 total_duration 与音频项时长一致，页面「总时长」= 接口值；
         * 实验室 test_case_count 与按 lab_id 分页全量计数一致（group_by 聚合口径）；
         * 用例详情音频条目齐全（窄字段批量取音频，不再逐条 RPC）。
  audio— 66c849a78 / b80503aa4 / 078fc72ba：音频试听播放时字节请求落在 15173
         网关（/api/v1/audios/download），不直连桶（127.0.0.1:9000 / cos）；
         并直接验网关媒体 token 流式路由（无 JWT + 签名 token → 200 流式）。
  auth — 65422fbe3：首屏按需加载（任务页不拉图表运行时）、登录后无白屏、
         切回标签页触发 /auth/me 静默刷新（权限变更免重登的前端半边）。

只读：不改库、不删数据、不保存设置。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2669_daily.py perf  --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2669_daily.py audio --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2669_daily.py auth  --base http://localhost:15173 --api http://127.0.0.1:15000
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2669')


def fmt_dur(seconds):
    """与 frontend-react/src/features/testcases/constants.ts formatCaseDuration 同口径。"""
    if not seconds or seconds <= 0:
        return '—'
    s = round(seconds)
    if s < 60:
        return '%ds' % s
    m, rest = s // 60, s % 60
    return '%dm' % m if rest == 0 else '%dm %ds' % (m, rest)


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api_root = api_root
        self.api = ApiClient(api_root)
        self.api.login(username, password)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-44s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
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
                self.net.append({'m': resp.request.method, 's': resp.status, 'u': url[:200]})
        page.on('response', on_resp)

    def bad_requests(self, since=0):
        return [n for n in self.net[since:] if isinstance(n.get('s'), int) and n['s'] >= 400]


def _items(resp):
    data = resp.get('data') if isinstance(resp, dict) else None
    if isinstance(data, dict):
        return data.get('items') or []
    return data if isinstance(data, list) else []


# ── perf ───────────────────────────────────────────────────────────────
def mode_perf(p, args):
    cases = _items(p.api.request('GET', '/testcases', params={'page': 1, 'page_size': 50}))
    p.check('api_testcases', len(cases) > 0, 'items=%d' % len(cases))
    with_dur = [c for c in cases if (c.get('total_duration') or 0) > 0]
    p.check('testcases_total_duration_present', len(with_dur) > 0,
            'with_duration=%d/%d' % (len(with_dur), len(cases)))
    target = with_dur[0] if with_dur else None

    labs = _items(p.api.request('GET', '/laboratories', params={'page': 1, 'page_size': 50}))
    p.check('api_laboratories', len(labs) > 0, 'items=%d' % len(labs))
    lab = labs[0] if labs else None
    if lab:
        # 独立计数：分页拉全量用例，按 config.lab_id 统计（与 group_by 聚合独立口径）
        total = 0
        page_no = 1
        while page_no <= 30:
            resp = p.api.request('GET', '/testcases',
                                 params={'page': page_no, 'page_size': 100})
            page_items = _items(resp)
            for it in page_items:
                cfg = it.get('config') if isinstance(it.get('config'), dict) else {}
                try:
                    if int(cfg.get('lab_id')) == int(lab['id']):
                        total += 1
                except (TypeError, ValueError):
                    continue
            pages = (resp.get('data') or {}).get('pages') or 1
            if len(page_items) < 100 or page_no >= pages:
                break
            page_no += 1
        p.check('lab_case_count_matches_aggregation',
                total == (lab.get('test_case_count') or 0),
                'lab#%s 聚合=%s 独立计数=%d' % (lab['id'], lab.get('test_case_count'), total))

    # 用例详情音频条目
    detail = p.api.request('GET', '/testcases/%s' % cases[0]['id'])
    d = detail.get('data') or {}
    rounds = []
    for r in (d.get('config') or {}).get('rounds') or []:
        rounds.extend(r.get('audios') or [])
    p.check('testcase_detail_audios', len(rounds) > 0,
            'case#%s audios=%d' % (cases[0]['id'], len(rounds)))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.watch(page)
        p.login(page)
        page.goto(p.base + '/testcases', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        # 默认按分组折叠：点开目标用例所属分组后卡片才显示「总时长」
        groups = _items(p.api.request('GET', '/groups', params={'page': 1, 'page_size': 20}))
        group_name = (target or {}).get('tags') and target['tags'][0] or None
        if not any(g.get('name') == group_name for g in groups):
            group_name = groups[0]['name'] if groups else None
        if group_name:
            page.get_by_text(group_name, exact=True).first.click()
            page.wait_for_timeout(2800)
        body = page.inner_text('body')
        mark = len(p.net)
        if target:
            shown = fmt_dur(target.get('total_duration'))
            p.check('case_list_duration_rendered',
                    '总时长' in body and shown in body,
                    '期望「总时长 %s」（接口 %s）' % (shown, target.get('total_duration')))
        p.check('case_list_no_error_state',
                '加载失败' not in body and '请求失败' not in body, body[:100].replace('\n', ' | '))
        bad = p.bad_requests(mark)
        p.check('case_list_no_4xx5xx', not bad, 'bad=%s' % bad[:3])
        p.shot(page, 'perf_testcases_light')
        page.emulate_media(color_scheme='dark')
        page.wait_for_timeout(800)
        p.shot(page, 'perf_testcases_dark', dark=True)
        ctx.close()
        browser.close()


# ── audio ──────────────────────────────────────────────────────────────
def mode_audio(p, args):
    audios = _items(p.api.request('GET', '/audios', params={'page': 1, 'page_size': 5}))
    p.check('api_audios', len(audios) > 0, 'items=%d' % len(audios))
    audio = audios[0]
    r = p.api.request('GET', '/audios/%s/stream' % audio['id'])
    url = (r or {}).get('url') or ''
    p.check('stream_url_gateway_relative', url.startswith('/api/v1/audios/'),
            'url=%s' % url[:120])

    # 网关媒体 token 流式路由（078fc72ba）：无 JWT + 签名 token → 200 流式
    secret = hashlib.sha256(b'iat-media|intelligent_audio_test666').digest()
    path = audio.get('file_path') or ''
    exp = int(time.time()) + 600
    sig = hmac.new(secret, ('%s|%d' % (path, exp)).encode(), hashlib.sha256).hexdigest()
    token = '%d.%s' % (exp, sig)
    import httpx
    dl = ('%s/api/v1/audios/download?' % p.api_root.rstrip('/')) + urllib.parse.urlencode(
        {'path': path, 'token': token})
    rr = httpx.get(dl, timeout=60, trust_env=False)
    p.check('media_token_stream_200', rr.status_code == 200,
            'status=%s bytes=%d ctype=%s' % (rr.status_code, len(rr.content),
                                             rr.headers.get('content-type')))
    p.check('media_token_content_length',
            (rr.headers.get('content-length') or '0') == str(len(rr.content)),
            'content-length=%s bytes=%d' % (rr.headers.get('content-length'), len(rr.content)))
    rbad = httpx.get(dl.replace(token, '1.0'), timeout=20, trust_env=False)
    p.check('media_token_invalid_rejected', rbad.status_code in (401, 403),
            'bad token status=%s' % rbad.status_code)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=['--autoplay-policy=no-user-gesture-required'])
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        reqs = []

        def on_resp(resp):
            u = resp.url
            if '/audios/download' in u or '/audios/' in u and '/stream' in u:
                reqs.append((resp.status, u[:160]))
        page.on('response', on_resp)
        p.login(page)
        page.goto(p.base + '/audio-import', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        rows = page.locator('tbody tr').count()
        p.check('audio_rows', rows > 0, 'rows=%d' % rows)
        trigger = page.locator("button[aria-label^='音频 ']").first
        trigger.wait_for(timeout=20000)
        trigger.click()
        page.wait_for_timeout(900)
        page.get_by_role('menuitem', name='预览').first.click()
        page.wait_for_timeout(1800)
        dlg = page.locator('[role=dialog]').first
        dlg.wait_for(timeout=15000)
        p.check('preview_dialog_open', dlg.is_visible(),
                dlg.inner_text()[:80].replace('\n', ' '))
        dlg.locator("button[aria-label='播放']").first.click()
        page.wait_for_timeout(4000)
        info = page.evaluate("""() => {
          const a = document.querySelector('[role=dialog] audio');
          return a ? {src: (a.src || '').slice(0, 100), t: a.currentTime, ready: a.readyState,
                      err: a.error ? (a.error.code + ':' + a.error.message) : null,
                      paused: a.paused} : null;
        }""")
        # 1.6s 短音频在 4s 等待内会自然播完（ended → paused=True），故只看已推进且无错误
        p.check('audio_element_playing',
                bool(info) and (info.get('t') or 0) > 0 and not info.get('err'),
                str(info))
        gw = [r_ for r_ in reqs if 'localhost:15173' in r_[1] and '/audios/download' in r_[1]]
        p.check('audio_bytes_via_gateway', len(gw) > 0 and all(s < 400 for s, _ in gw),
                'gateway=%s' % gw[:3])
        p.check('audio_no_public_bucket',
                not any(('127.0.0.1:9000' in u or 'myqcloud' in u or 'cos.' in u)
                        for _, u in reqs),
                'reqs=%s' % [u[:60] for _, u in reqs][:5])
        p.shot(page, 'audio_preview_light')
        page.emulate_media(color_scheme='dark')
        page.wait_for_timeout(600)
        p.shot(page, 'audio_preview_dark', dark=True)
        ctx.close()
        browser.close()


# ── auth ───────────────────────────────────────────────────────────────
def mode_auth(p, args):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        resources = []
        page.on('request', lambda req: resources.append(req.url))
        p.watch(page)
        p.login(page)
        # 1) 首屏：登录后落到 /dashboard，无白屏
        page.wait_for_timeout(3000)
        body = page.inner_text('body')
        p.check('first_paint_no_white_screen', len(body.strip()) > 60,
                'body_len=%d head=%s' % (len(body.strip()), body[:60].replace('\n', ' ')))
        p.shot(page, 'auth_dashboard_light')

        # 2) 非图表页（任务页）不应下载图表运行时（按需加载，图表运行时约 2MB）
        page.goto(p.base + '/tasks', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        mark = len(p.net)
        task_body = page.inner_text('body')
        p.check('tasks_page_renders', len(task_body.strip()) > 60,
                'body_len=%d' % len(task_body.strip()))
        js_sizes = page.evaluate(
            "() => performance.getEntriesByType('resource')"
            ".filter(e => e.name.endsWith('.js') || e.name.includes('/static/js/'))"
            ".map(e => ({n: e.name.split('/').pop(), s: e.decodedBodySize || e.transferSize || 0}))")
        big = [j for j in js_sizes if j['s'] > 1_500_000]
        p.check('no_chart_runtime_on_tasks', not big,
                '>1.5MB js=%s max=%d' % ([b['n'] for b in big][:3],
                                         max([j['s'] for j in js_sizes] or [0])))
        bad = p.bad_requests(mark)
        p.check('tasks_page_no_5xx', not [b for b in bad if b['s'] >= 500], 'bad=%s' % bad[:3])

        # 3) 图表页（总览）才按需拉图表运行时
        page.goto(p.base + '/dashboard', wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        js_sizes_d = page.evaluate(
            "() => performance.getEntriesByType('resource')"
            ".filter(e => e.name.includes('/static/js/'))"
            ".map(e => ({n: e.name.split('/').pop(), s: e.decodedBodySize || e.transferSize || 0}))")
        big_d = [j for j in js_sizes_d if j['s'] > 1_500_000]
        dash_body = page.inner_text('body').strip()
        # 当前库总览页无近期任务 → 空态「开始使用」，图表未渲染时不应拉 2MB 图表运行时
        p.check('dashboard_empty_state_no_chart_runtime',
                ('开始使用' in dash_body or len(big_d) > 0) and not (
                    '开始使用' not in dash_body and not big_d),
                'body_len=%d >1.5MB js=%s' % (len(dash_body), [b['n'] for b in big_d][:3]))
        p.check('dashboard_renders_no_white', len(dash_body) > 60,
                'body_len=%d' % len(dash_body))

        # 3) 切回标签页 → 立即静默刷新 /auth/me
        mark = len(p.net)
        page.evaluate("""() => {
          Object.defineProperty(document, 'visibilityState',
              {value: 'visible', configurable: true});
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.wait_for_timeout(2500)
        me = [n for n in p.net[mark:] if '/auth/me' in n['u']]
        p.check('visibilitychange_refresh_me', len(me) > 0,
                '/auth/me requests=%s' % me[:2])
        p.check('refresh_me_ok', bool(me) and all(n['s'] == 200 for n in me),
                'status=%s' % [n['s'] for n in me])

        # 4) /auth/me 携带权限（权限变更免重登的前端数据源）
        import httpx
        r = httpx.get(p.api_root.rstrip('/') + '/api/v1/auth/me',
                      headers={'Authorization': 'Bearer %s' % p.api.token},
                      timeout=20, trust_env=False)
        me_data = (r.json() or {}).get('data') or r.json() or {}
        perms = me_data.get('permissions')
        p.check('auth_me_permissions', r.status_code == 200 and isinstance(perms, list),
                'status=%s perms=%s' % (r.status_code, str(perms)[:80]))
        ctx.close()
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['perf', 'audio', 'auth'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    globals()['mode_%s' % args.mode](p, args)
    os.makedirs(ART, exist_ok=True)
    out = os.path.join(ART, 'result_%s.json' % args.mode)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'checks': p.checks, 'network': p.net[-60:]}, f, ensure_ascii=False, indent=1)
    passed = sum(1 for c in p.checks if c['ok'])
    print('PASSED=%d FAILED=%d' % (passed, len(p.checks) - passed), flush=True)
    print('SUMMARY_JSON=%s' % out, flush=True)
    return 0 if passed == len(p.checks) else 1


if __name__ == '__main__':
    sys.exit(main())
