# -*- coding: utf-8 -*-
"""INT-2661 前端回归日巡补充实测（React docker 栈 15173，只读）。

上一轮（INT-2654）之后合入 V10.11.2 的界面增量按卡面重点复验：

  1. `time`    — INT-2655 之后设备域改墙钟，任务 / 音频 / 报告域必须仍走
                 formatDateTime（naive UTC +8 转本地），不复归为墙钟；
  2. `audio`   — f21786f09 浏览器播放改走网关代理：/audios/{id}/stream 回网关
                 相对地址时，前端 <audio> 以 blob 播放且字节请求落在 15173 网关；
  3. `settings`— 74a4f9e50 评估服务设置前端接线：/system-settings/eval/llm 渲染
                 真实 option KV 值、密钥入口可见；
  4. `agent`   — fb0ebb926 会话消息删除：/ai-chat 用户气泡有删除入口，
                 DELETE 契约存在（用随机 message id 验幂等，不动真实消息）。

只读语义：不保存任何设置、不删除真实消息、不写库，无 teardown。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2661_daily.py time     --base http://localhost:15173 --api http://localhost:15000
  python tests/ui/probe_int2661_daily.py audio    --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2661_daily.py settings --base http://localhost:15173
  python tests/ui/probe_int2661_daily.py agent    --base http://localhost:15173 --api http://127.0.0.1:15000
"""
import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2661')


def local_from_utc(value):
    """naive UTC 串 → 东八区本地「YYYY-MM-DD HH:mm」（formatDateTime 同口径）。"""
    if not value:
        return '—'
    raw = value.replace('T', ' ')[:19]
    try:
        dt = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return '—'
    return (dt + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')


def items_of(resp):
    data = resp.get('data') if isinstance(resp, dict) else None
    if isinstance(data, dict):
        return data.get('items') or []
    return data if isinstance(data, list) else []


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
        print('[%s] %-46s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

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
        page.wait_for_timeout(1200)


def mode_time(p, args):
    """任务 / 报告域时间仍走 formatDateTime（UTC+8），不能一起改坏。"""
    tasks = items_of(p.api.request('GET', '/tasks?page=1&page_size=5'))
    p.check('api_tasks', len(tasks) > 0, 'items=%d' % len(tasks))
    reports = items_of(p.api.request('GET', '/reports?page=1&page_size=5'))
    p.check('api_reports', len(reports) > 0, 'items=%d' % len(reports))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.login(page)

        # 任务页：列表行里的创建时间应为 UTC+8
        task = next((t for t in tasks if t.get('created_at')), None)
        expect = local_from_utc(task.get('created_at')) if task else '—'
        raw = (task or {}).get('created_at') or ''
        page.goto(p.base + '/tasks', wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        body = page.inner_text('body')
        p.check('task_list_has_local_time', expect in body, '期望 %s（接口 %s）' % (expect, raw[:19]))
        p.check('task_list_not_raw_utc',
                raw[:16].replace('T', ' ') not in body,
                '原始 UTC %s 不应直接出现' % raw[:16])
        p.shot(page, 'time_tasks_light')

        # 报告中心：列表时间同样 +8
        rep = next((r for r in reports if r.get('created_at')), None)
        exp_r = local_from_utc(rep.get('created_at')) if rep else '—'
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        body2 = page.inner_text('body')
        rows = page.locator('tbody tr').count()
        p.check('report_center_rows', rows > 0 or exp_r in body2, 'rows=%d 期望时间 %s' % (rows, exp_r))
        p.check('report_center_has_local_time', exp_r in body2, '期望 %s（接口 %s）' % (
            exp_r, (rep or {}).get('created_at', '')[:19]))
        p.shot(page, 'time_report_center_light')
        ctx.close()
        browser.close()


def mode_audio(p, args):
    """f21786f09：/stream 回网关相对地址 → 前端取 blob 播放，字节走网关。"""
    audios = items_of(p.api.request('GET', '/audios?page=1&page_size=5'))
    p.check('api_audios', len(audios) > 0, 'items=%d' % len(audios))
    target = None
    for a in audios:
        try:
            r = p.api.request('GET', '/audios/%s/stream' % a['id'])
            url = (r or {}).get('url') or ''
        except Exception as exc:  # noqa: BLE001
            url = 'ERR:%s' % str(exc)[:80]
        print('stream api', a['id'], url[:120], flush=True)
        if url.startswith('/api/v1/'):
            target = (a, url)
            break
        if url and url.startswith('http') and target is None:
            target = (a, url)
    p.check('stream_api_url', target is not None, 'target=%s' % (target[1][:100] if target else None))
    if not target:
        return
    audio, stream_url = target
    p.check('stream_url_form', True, '相对（网关代理）' if stream_url.startswith('/api/v1/') else '绝对（预签名直连）')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--autoplay-policy=no-user-gesture-required'])
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        reqs = []

        def on_resp(resp):
            u = resp.url
            if 'audios/download' in u or 'audios/stream' in u or re.search(r'\.wav(\?|$)', u, re.I):
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
        dlg = page.locator('[role=dialog]')
        dlg.first.wait_for(timeout=15000)
        p.check('preview_dialog_open', dlg.first.is_visible(), dlg.first.inner_text()[:80].replace('\n', ' '))
        play = dlg.locator("button[aria-label='播放']").first
        play.click()
        page.wait_for_timeout(4000)
        info = page.evaluate("""() => {
          const a = document.querySelector('[role=dialog] audio');
          return a ? {src: (a.src || '').slice(0, 80), t: a.currentTime, ready: a.readyState,
                      err: a.error ? (a.error.code + ':' + a.error.message) : null,
                      paused: a.paused} : null;
        }""")
        p.check('audio_element_present', info is not None, str(info))
        p.check('audio_blob_playing',
                bool(info) and str(info.get('src', '')).startswith('blob:') and (info.get('t') or 0) > 0,
                'src=%s t=%s ready=%s paused=%s' % (
                    (info or {}).get('src'), (info or {}).get('t'),
                    (info or {}).get('ready'), (info or {}).get('paused')))
        gw = [r for r in reqs if 'localhost:15173' in r[1] and 'audios/download' in r[1]]
        p.check('audio_bytes_via_gateway', len(gw) > 0 and all(s < 400 for s, _ in gw),
                'requests=%s' % gw[:3])
        p.check('audio_no_bucket_public_hop',
                not any(('myqcloud' in u or 'cos.' in u) for _, u in reqs),
                'reqs=%s' % [u[:60] for _, u in reqs][:4])
        p.net = reqs[:10]
        p.shot(page, 'audio_preview_light')
        page.emulate_media(color_scheme='dark')
        page.wait_for_timeout(600)
        p.shot(page, 'audio_preview_dark')
        ctx.close()
        browser.close()


def mode_settings(p, args):
    """74a4f9e50：评估服务设置落系统设置页（展示真实 KV 值）。"""
    import httpx
    headers = {'Authorization': 'Bearer %s' % p.api.token}
    r = httpx.get(p.api_root.rstrip('/') + '/api/option/', headers=headers, timeout=15,
                  trust_env=False)
    p.check('option_api_200', r.status_code == 200, 'status=%s' % r.status_code)
    opts = (r.json() or {}).get('data') or {}
    eval_keys = {k: v for k, v in opts.items() if str(k).startswith('eval')}
    p.check('option_eval_keys_present', len(eval_keys) > 0,
            'keys=%d sample=%s' % (len(eval_keys), list(eval_keys)[:6]))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/system-settings/eval/llm', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        body = page.inner_text('body')
        p.check('eval_llm_page_rendered',
                ('评估服务' in body and ('模型' in body or 'LLM' in body)),
                body[:160].replace('\n', ' | '))
        p.check('eval_no_error_state',
                '加载失败' not in body and '无权' not in body,
                'has_error_title=%s' % ('加载失败' in body))
        # 真实 KV 值回显（api_base / 默认模型 至少命中一项）
        hit = [k for k, v in eval_keys.items() if str(v) and str(v) in body]
        p.check('eval_values_from_api', len(hit) > 0, 'hit_keys=%s' % hit[:5])
        p.shot(page, 'settings_eval_llm_light')
        page.goto(p.base + '/system-settings/eval/asr', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        p.shot(page, 'settings_eval_asr_light')
        page.emulate_media(color_scheme='dark')
        page.goto(p.base + '/system-settings/eval/llm', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        p.check('settings_dark_applied',
                page.evaluate("document.documentElement.classList.contains('dark')"),
                'dark=%s' % page.evaluate("document.documentElement.classList.contains('dark')"))
        p.shot(page, 'settings_eval_llm_dark')
        ctx.close()
        browser.close()


def mode_agent(p, args):
    """fb0ebb926：会话消息删除入口 + DELETE 契约（随机 id 幂等，不动真实消息）。"""
    sessions = p.api.request('GET', '/agent/sessions')
    p.check('api_sessions', isinstance(sessions, list) and len(sessions) > 0, 'n=%s' % (
        len(sessions) if isinstance(sessions, list) else type(sessions)))
    sid = sessions[0]['id'] if sessions else None
    if sid:
        detail = p.api.request('GET', '/agent/sessions/%s' % sid)
        msgs = (detail or {}).get('messages') or []
        users = [m for m in msgs if m.get('role') == 'user']
        p.check('session_messages', len(msgs) > 0 and len(users) > 0,
                'msgs=%d users=%d' % (len(msgs), len(users)))
        # 契约存在性：随机 message id 删除应为 200（幂等）或 404，不得 5xx
        try:
            rr = p.api.request('DELETE', '/agent/sessions/%s/messages/%s' % (sid, uuid.uuid4()))
            status = 200
            body = rr
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            m = re.search(r'HTTP (\d+)', text)
            status = int(m.group(1)) if m else 0
            body = text[:120]
        p.check('delete_message_contract', status in (200, 404),
                'status=%s body=%s' % (status, str(body)[:100]))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        page.screenshot(path=os.path.join(ART, 'agent_chat_light.png')) if os.path.isdir(ART) else None
        p.shot(page, 'agent_chat_light')
        # 打开历史会话（第一条）
        opened = False
        try:
            hist = page.locator('button, [role=button]').filter(has_text=re.compile('历史|会话'))
            if hist.count():
                hist.first.click()
                page.wait_for_timeout(1500)
            item = page.locator('[data-slot=dropdown-menu-item], [role=menuitem]').first
            if item.count():
                item.click()
                page.wait_for_timeout(3000)
                opened = True
        except Exception:  # noqa: BLE001
            pass
        body = page.inner_text('body')
        p.check('chat_page_loaded', '灵犀' in body or '对话' in body, body[:120].replace('\n', ' | '))
        del_btn = page.locator("button[aria-label='删除']")
        p.check('message_delete_affordance', del_btn.count() > 0,
                '删除按钮=%d（会话已打开=%s）' % (del_btn.count(), opened))
        ctx.close()
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['time', 'audio', 'settings', 'agent'])
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
        json.dump({'checks': p.checks, 'network': p.net}, f, ensure_ascii=False, indent=1)
    passed = sum(1 for c in p.checks if c['ok'])
    print('PASSED=%d FAILED=%d' % (passed, len(p.checks) - passed), flush=True)
    print('SUMMARY_JSON=%s' % out, flush=True)
    return 0 if passed == len(p.checks) else 1


if __name__ == '__main__':
    sys.exit(main())
