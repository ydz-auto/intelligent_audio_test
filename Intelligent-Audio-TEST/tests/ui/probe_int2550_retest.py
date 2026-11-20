# -*- coding: utf-8 -*-
"""INT-2550 打回修复的独立复测探针（测试工程师 / devloop §2.3）。

只覆盖上一轮打回项与本次修复相关部分：

P2-1 对话沉淀入口（卡面「做」第 10 项）
  - run 流里没有 skill_draft_suggested → 会话页不得出现建议卡（不伪造）
  - 收到该事件 → 气泡出现建议卡（名称 / 工具 / 边界说明），主按钮直达
    `/agent-skills?name=&description=`，编辑器预填；不自动落库
  - 事件缺 suggested_name（畸形帧）→ 按未知事件丢弃，不出现建议卡

P2-2 编辑器「重新加载」死按钮
  - CDP 屏蔽 export → 错误态 → 点「重新加载」必须重新发请求（计数 +1）
  - 解屏蔽再点 → 正文载入

P3-2 保存成功文案 / P3-3 错误码→文案映射（随修复一起收）
  - 保存成功：绿色「保存成功，版本已 +1」，不出现「未保存」
  - 改名撞平台 Skill：409 SKILL_NAME_CONFLICT → 显示「与已有 Skill 重名…」

环境：docker 网关 15000（真实库）；前端用分支代码 dev server 指向本进程内置
的 SSE 反向代理桩（只接管 `GET /api/v1/agent/runs/{id}/events`，其余请求原样
转发 15000）。桩帧格式取自部署容器内 `agent_service/interfaces/api/routes.py`
的 `_sse_frame()` 与 `run_orchestrator._emit_skill_suggestion()`。

用法：
  python tests/ui/probe_int2550_retest.py --base http://localhost:5340
产物：tests/ui/artifacts/int2550_retest/{summary.json,*.png}
"""
import argparse
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402

API_ROOT = 'http://127.0.0.1:15000'
STUB_PORT = 18792
SSE_RE = re.compile(r'^/api/v1/agent/runs/([^/]+)/events')
HOP_HEADERS = {
    'host', 'content-length', 'connection', 'transfer-encoding',
    'content-encoding', 'accept-encoding',
}

SUGGESTED_NAME = 'probe-retest-export-flow'
SUGGESTED_DESCRIPTION = '基于本次 run 的执行流程沉淀的 Skill 草案'
SUGGESTED_TOOLS = ['report_get_facts', 'studio_request_export']
USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')
PREFIX = 'probe-retest-'

ART = os.path.join(os.path.dirname(sm.ART_ROOT), 'int2550_retest')
RESULT = {'checks': {}, 'steps': [], 'screenshots': [], 'requests': [],
          'notes': []}

# 桩的当前模式：no_event / valid / malformed
MODE = {'value': 'valid'}


def log(msg):
    print('[int2550-retest] %s' % msg, flush=True)


def record(step, status, detail=''):
    RESULT['steps'].append({'step': step, 'status': status, 'detail': detail})
    log('%s: %s %s' % (step, status, detail))


def ok(check, **payload):
    RESULT['checks'][check] = {'ok': True, **payload}
    record(check, 'PASS', json.dumps(payload, ensure_ascii=False)[:300])


def fail(check, reason, **payload):
    RESULT['checks'][check] = {'ok': False, 'reason': reason, **payload}
    record(check, 'FAIL', reason)
    raise AssertionError('%s: %s' % (check, reason))


def shot(drv, key):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, key + '.png')
    drv.save_screenshot(path)
    RESULT['screenshots'].append({'name': key, 'path': path,
                                  'size': os.path.getsize(path)})
    log('SHOT %s (%d bytes)' % (key, os.path.getsize(path)))


# ── SSE 反向代理桩（本进程内） ─────────────────────────────────
def _sse_body(run_id, mode):
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def frame(seq, event_type, payload):
        data = {'run_id': run_id, 'sequence': seq, 'type': event_type,
                'timestamp': now, **payload}
        return 'id: %d\nevent: %s\ndata: %s\n\n' % (
            seq, event_type, json.dumps(data, ensure_ascii=False))

    frames = [
        frame(1, 'run_started', {'status': 'RUNNING', 'session_id': ''}),
        frame(2, 'message_delta', {
            'message_id': 'm-retest-1',
            'delta': '已整理本次导出流程，可以把这套步骤沉淀为可复用的 Skill。',
        }),
    ]
    if mode == 'valid':
        frames.append(frame(3, 'skill_draft_suggested', {
            'suggested_name': SUGGESTED_NAME,
            'description': SUGGESTED_DESCRIPTION,
            'tools_used': SUGGESTED_TOOLS,
            'source_skill': 'platform-reference',
            'created': False,
            'requires_confirmation': True,
        }))
    elif mode == 'malformed':
        # 缺 suggested_name：DTO 应丢弃，界面不得出现半截建议卡
        frames.append(frame(3, 'skill_draft_suggested', {
            'description': '畸形帧（无建议名称）',
            'tools_used': SUGGESTED_TOOLS,
            'created': False,
            'requires_confirmation': True,
        }))
    frames.append(frame(4, 'run_finished', {'status': 'SUCCEEDED'}))
    return ''.join(frames).encode('utf-8')


class StubHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _write(self, status, headers, body):
        self.send_response(status)
        for key, value in headers:
            if key.lower() in HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def _handle(self):
        matched = SSE_RE.match(self.path.split('?')[0])
        if self.command == 'GET' and matched:
            mode = MODE['value']
            body = _sse_body(matched.group(1), mode)
            log('stub SSE mode=%s run=%s (%d bytes)'
                % (mode, matched.group(1), len(body)))
            self._write(200, [
                ('Content-Type', 'text/event-stream; charset=utf-8'),
                ('Cache-Control', 'no-cache'),
                ('X-Accel-Buffering', 'no'),
            ], body)
            return

        length = int(self.headers.get('Content-Length') or 0)
        payload = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in HOP_HEADERS}
        try:
            with httpx.Client(timeout=90, trust_env=False) as client:
                resp = client.request(self.command, API_ROOT + self.path,
                                      headers=headers, content=payload)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({'detail': 'stub upstream error: %s' % exc},
                              ensure_ascii=False).encode('utf-8')
            self._write(502, [('Content-Type', 'application/json')], body)
            return
        RESULT['requests'].append({'method': self.command,
                                   'path': self.path.split('?')[0],
                                   'status': resp.status_code})
        self._write(resp.status_code, list(resp.headers.items()), resp.content)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle


def start_stub():
    server = ThreadingHTTPServer(('127.0.0.1', STUB_PORT), StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log('stub listening 127.0.0.1:%d -> %s' % (STUB_PORT, API_ROOT))
    return server


# ── 浏览器小工具 ────────────────────────────────────────────────
def set_theme(drv, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light')
    drv.refresh()
    time.sleep(2.5)


def click(drv, elem):
    drv.execute_script('arguments[0].click()', elem)
    time.sleep(0.4)


def type_into(drv, selector, value):
    """React 受控输入：原生 setter + input 事件，避免 send_keys 丢键。"""
    drv.execute_script(
        "const el=document.querySelector(arguments[0]);"
        "const proto=(el instanceof HTMLTextAreaElement)"
        "?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "Object.getOwnPropertyDescriptor(proto,'value').set.call(el,arguments[1]);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));",
        selector, value)
    time.sleep(0.3)


def body_text(drv):
    return drv.execute_script(
        'return document.body ? document.body.innerText : ""') or ''


def wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))
    return True


def has_element(drv, css):
    return bool(drv.find_elements(By.CSS_SELECTOR, css))


def install_export_counter(drv):
    drv.execute_script(
        "window.__exportCalls = [];"
        "const __f = window.fetch;"
        "window.fetch = function(input, init) {"
        "  try { const u = (typeof input === 'string' ? input : (input && input.url)) || '';"
        "        if (u.indexOf('/export') >= 0) window.__exportCalls.push(u); }"
        "  catch (e) {}"
        "  return __f.apply(this, arguments);"
        "};")


def export_calls(drv):
    return drv.execute_script('return (window.__exportCalls || []).length')


def request_log(drv):
    out = []
    try:
        raw = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for entry in raw:
        try:
            inner = json.loads(entry.get('message', '{}')).get('message', {})
            if inner.get('method') != 'Network.requestWillBeSent':
                continue
            req = inner.get('params', {}).get('request', {})
            out.append({'method': req.get('method'), 'url': req.get('url')})
        except Exception:  # noqa: BLE001
            continue
    return out


def login_ui(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                   if e.get_attribute('type') in (None, 'text', 'email')
                   and e.is_displayed()]
    (user_inputs[0] if user_inputs else
     drv.find_element(By.CSS_SELECTOR, '#username')).send_keys(USERNAME)
    pwd = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
           if e.is_displayed()]
    pwd[0].send_keys(PASSWORD)
    submit = [b for b in drv.find_elements(By.TAG_NAME, 'button')
              if (b.text or '').strip() in ('登录', '登 录')]
    click(drv, submit[-1] if submit else
          drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
    WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2)


# ── Skill 接口（自建自清） ──────────────────────────────────────
class SkillApi:
    def __init__(self, client):
        self.client = client

    def _headers(self):
        return {'Authorization': 'Bearer ' + self.client.token}

    def create(self, name, body=None):
        payload = {
            'name': name,
            'description': 'INT-2550 打回复测探针',
            'body': body or ('## 适用场景\n\n探针。\n\n## Gotchas\n\n-\n\n'
                             '## 验收\n\n- 通过\n'),
            'frontmatter': {'allowed-tools': [], 'permissions': []},
        }
        r = httpx.post(API_ROOT + '/api/v1/agent/skills', json=payload,
                       headers=self._headers(), trust_env=False, timeout=30)
        if r.status_code not in (200, 201):
            raise RuntimeError('create skill %s: %s %s'
                               % (name, r.status_code, r.text[:300]))
        return r.json()

    def delete(self, skill_id):
        if not skill_id:
            return
        httpx.request('DELETE', API_ROOT + '/api/v1/agent/skills/' + skill_id,
                      headers=self._headers(), trust_env=False, timeout=30)

    def list_all(self):
        r = httpx.get(API_ROOT + '/api/v1/agent/skills',
                      headers=self._headers(), trust_env=False, timeout=30)
        r.raise_for_status()
        return r.json().get('items') or []

    def cleanup(self):
        left = []
        for item in self.list_all():
            name = item.get('name') or ''
            if name.startswith(PREFIX):
                self.delete(item.get('id'))
                left.append(name)
        return left


# ── 会话页：发消息 ──────────────────────────────────────────────
def send_message(drv):
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea')))
    time.sleep(1.5)
    type_into(drv, 'textarea', '帮我把导出报告的流程沉淀成 Skill')
    time.sleep(0.5)
    submits = [b for b in drv.find_elements(By.CSS_SELECTOR,
                                            'button[type=submit]')
               if b.is_displayed()]
    if not submits:
        fail('suggestion_flow', '/ai-chat 没有可用的发送按钮')
    click(drv, submits[-1])
    wait_text(drv, '已整理本次导出流程', 40)


# ── 阶段 A/B/C：对话沉淀入口 ───────────────────────────────────
def phase_no_event(drv, base):
    MODE['value'] = 'no_event'
    drv.get(base + '/ai-chat')
    send_message(drv)
    time.sleep(3)
    if has_element(drv, '[data-testid="skill-suggestion-card"]'):
        fail('suggestion_absent_without_event',
             'run 流没有 skill_draft_suggested，页面却渲染了建议卡（伪造）')
    if '沉淀为 Skill' in body_text(drv):
        fail('suggestion_absent_without_event', '无事件时页面出现「沉淀为 Skill」文案')
    ok('suggestion_absent_without_event', cards=0)
    shot(drv, 'no_event_no_card')


def phase_malformed(drv, base):
    MODE['value'] = 'malformed'
    drv.get(base + '/ai-chat')
    send_message(drv)
    time.sleep(3)
    if has_element(drv, '[data-testid="skill-suggestion-card"]'):
        fail('suggestion_malformed_dropped',
             '畸形帧（缺 suggested_name）仍渲染建议卡，应丢弃')
    ok('suggestion_malformed_dropped', cards=0)


def phase_suggestion(drv, base, api):
    MODE['value'] = 'valid'
    drv.get(base + '/ai-chat')
    send_message(drv)
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-suggestion-card"]')))
    card = drv.find_element(By.CSS_SELECTOR,
                            '[data-testid="skill-suggestion-card"]')
    text = card.text
    suggested = card.get_attribute('data-suggested-name')
    if suggested != SUGGESTED_NAME:
        fail('suggestion_card', '建议名称不符：%r' % suggested)
    for needle in ('沉淀为 Skill', SUGGESTED_NAME, '本次 run 调用了 2 个工具',
                   '确认后才创建草稿，不自动落库', 'report_get_facts',
                   'studio_request_export'):
        if needle not in text:
            fail('suggestion_card', '建议卡缺少文案「%s」：%s'
                 % (needle, text.replace('\n', ' | ')))
    ok('suggestion_card', suggested_name=suggested,
       text=text.replace('\n', ' | ')[:400])
    shot(drv, 'suggestion_card_light')

    # 深色同卡
    set_theme(drv, True)
    drv.get(base + '/ai-chat')
    send_message(drv)
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-suggestion-card"]')))
    shot(drv, 'suggestion_card_dark')

    # 主按钮直达并预填
    before = [s.get('name') for s in api.list_all()]
    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-suggestion-create"]'))
    WebDriverWait(drv, 40).until(lambda d: '/agent-skills' in d.current_url)
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-name')))
    name_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-name').get_attribute('value')
    desc_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-description').get_attribute('value')
    if name_value != SUGGESTED_NAME:
        fail('suggestion_prefill', '名称未预填：%r' % name_value)
    if desc_value != SUGGESTED_DESCRIPTION:
        fail('suggestion_prefill', '描述未预填：%r' % desc_value)
    ok('suggestion_prefill', name=name_value, description=desc_value,
       url=drv.current_url)
    shot(drv, 'suggestion_prefill')

    after = [s.get('name') for s in api.list_all()]
    if SUGGESTED_NAME in after:
        fail('suggestion_no_autocreate', '建议名已自动落库（不应自动创建）')
    ok('suggestion_no_autocreate',
       own_before=[n for n in before if n and n.startswith(PREFIX)],
       own_after=[n for n in after if n and n.startswith(PREFIX)])


# ── 阶段 D：编辑器重试 + 文案 ──────────────────────────────────
def find_row_button(drv, name, label):
    row = drv.find_element(By.CSS_SELECTOR, '[data-skill-name="%s"]' % name)
    buttons = [b for b in row.find_elements(By.TAG_NAME, 'button')
               if (b.text or '').strip() == label]
    if not buttons:
        fail('editor_retry', '行内没有「%s」按钮' % label)
    return buttons[0]


def phase_editor(drv, base, api):
    name = PREFIX + 'retry-' + str(int(time.time()))
    skill = api.create(name)
    sid = skill['id']
    record('prepare_skill', 'PASS', 'name=%s id=%s' % (name, sid))

    drv.execute_cdp_cmd('Network.enable', {})
    drv.get(base + '/agent-skills')
    wait_text(drv, name, 40)
    time.sleep(1.5)

    drv.execute_cdp_cmd('Network.setBlockedURLs',
                        {'urls': ['*/agent/skills/*/export*']})
    install_export_counter(drv)
    click(drv, find_row_button(drv, name, '编辑'))
    wait_text(drv, '读取 SKILL.md 失败', 30)
    time.sleep(0.8)
    shot(drv, 'doc_error')
    before = export_calls(drv)
    if before < 1:
        fail('doc_retry_refetch', '屏蔽后未观察到 export 请求，判据不成立')

    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-doc-retry"]'))
    time.sleep(3)
    after = export_calls(drv)
    if after <= before:
        fail('doc_retry_refetch',
             '点「重新加载」后 export 请求数没有增加：%d → %d' % (before, after))
    if '读取 SKILL.md 失败' not in body_text(drv):
        fail('doc_retry_refetch', '仍被屏蔽却离开错误态（判据异常）')
    ok('doc_retry_refetch', before=before, after=after)

    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-doc-retry"]'))
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-body')))
    WebDriverWait(drv, 20).until(
        lambda d: '## Gotchas' in d.find_element(
            By.CSS_SELECTOR, '#agent-skill-body').get_attribute('value'))
    ok('doc_retry_recovered', body_has_gotchas=True)
    shot(drv, 'doc_recovered')

    # P3-3：409 SKILL_NAME_CONFLICT → 错误码文案
    type_into(drv, '#agent-skill-name', 'platform-reference')
    save = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if (b.text or '').strip() == '保存']
    if not save:
        fail('error_code_copy', '编辑器没有「保存」按钮')
    click(drv, save[-1])
    wait_text(drv, '与已有 Skill 重名', 30)
    if 'SKILL_NAME_CONFLICT' in body_text(drv):
        fail('error_code_copy', '界面直接显示原始错误码而不是映射文案')
    ok('error_code_copy', text='与已有 Skill 重名，请改名或 fork 后修改')
    shot(drv, 'name_conflict_code_copy')

    # P3-2：恢复名称保存成功 → 成功态文案不含「未保存」
    type_into(drv, '#agent-skill-name', name)
    save = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if (b.text or '').strip() == '保存']
    click(drv, save[-1])
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR,
                                        '[data-testid="skill-editor-saved"]')))
    hint = drv.find_element(By.CSS_SELECTOR,
                            '[data-testid="skill-editor-saved"]').text
    if '保存成功' not in hint:
        fail('save_success_hint', '成功态文案不符：%s' % hint)
    if '未保存' in body_text(drv):
        fail('save_success_hint', '保存成功后页面仍出现「未保存」')
    ok('save_success_hint', text=hint)
    shot(drv, 'save_success_state')

    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    api.delete(sid)


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with io.open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:5340')
    parser.add_argument('--api', default=API_ROOT)
    parser.add_argument('--only', choices=['all', 'suggestion', 'editor'],
                        default='all')
    args = parser.parse_args()
    RESULT['base'] = args.base
    RESULT['api'] = args.api

    global ART
    os.makedirs(ART, exist_ok=True)
    stub = start_stub()
    client = ApiClient(args.api)
    client.login(USERNAME, PASSWORD)
    api = SkillApi(client)

    drv = sm.make_driver(ART)
    code = 0
    try:
        login_ui(drv, args.base)
        if args.only in ('all', 'suggestion'):
            phase_no_event(drv, args.base)
            phase_malformed(drv, args.base)
            phase_suggestion(drv, args.base, api)
        if args.only in ('all', 'editor'):
            phase_editor(drv, args.base, api)
    except Exception as exc:  # noqa: BLE001
        RESULT['error'] = '%s: %s' % (type(exc).__name__, exc)
        RESULT['traceback'] = traceback.format_exc()[-3000:]
        record('run', 'FAIL', RESULT['error'])
        code = 1
    finally:
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            cleaned = api.cleanup()
            if cleaned:
                record('cleanup', 'PASS', 'deleted=%s' % cleaned)
        except Exception:  # noqa: BLE001
            log('清理探针数据失败（人工核对前缀 %s）' % PREFIX)
        try:
            stub.shutdown()
        except Exception:  # noqa: BLE001
            pass
        RESULT['net'] = [r for r in RESULT['requests']
                         if '/agent/skills' in r['path']
                         or '/agent/runs' in r['path']][-40:]

    write_artifacts()
    failed = [k for k, v in RESULT['checks'].items() if v.get('ok') is False]
    log('完成：%d 项，失败 %d 项' % (len(RESULT['checks']), len(failed)))
    return 1 if failed else code


if __name__ == '__main__':
    sys.exit(main())
