# -*- coding: utf-8 -*-
"""INT-2584 真事件探针：「沉淀为 Skill」建议卡（真栈真事件，不用 SSE 桩）。

背景：`skill_draft_suggested` 由 agent_service 在「run 正常结束且本轮 ≥2 个工具
COMPLETED」时下发。库里 dev_user 没有可用模型供应商，直接发消息 run 会秒
FAILED(LLM_PROVIDER_NOT_CONFIGURED)，因此本探针在宿主机起一个 OpenAI-compatible
假 LLM（只替代模型供应商，不替代 agent_service / 网关 / 前端），让真实 run 真实
执行平台工具（platform_contract / tool_search 都是只读意图工具），从而由后端
**自己**产出这条事件。

两个阶段：
① api（无浏览器，验事件本身）：
   python tests/ui/probe_int2584_skill_suggestion_real.py --phase api
   - two-tools：≥2 工具 COMPLETED → 收到 skill_draft_suggested，载荷 created=false /
     requires_confirmation=true / tools_used 两个工具；且事件先于 run_finished
   - one-tool / no-tool：不出现该事件（不伪造）

② ui（真前端 dev server 连 docker 网关 15000，验卡片 + 忽略）：
   API_PROXY_TARGET=http://127.0.0.1:15000 pnpm dev --port 5384   # frontend-react
   python tests/ui/probe_int2584_skill_suggestion_real.py --phase ui \
       --base http://localhost:5384
   - 真 run 结束 → 卡片出现（建议名 = 后端按工具名生成的 platform-contract-tool-search）
   - 点「忽略」→ 卡片消失、正文与其他内容不动、Network 无新增请求
   - 刷新 → 该消息仍无卡片（随既有消息持久化，不新增持久化口径）
   - 「去创建草稿」→ /agent-skills?name=&description= 且编辑器已预填
   - one-tool / no-tool → 不出卡片
   - 浅色 / 深色截图

产物：tests/ui/artifacts/int2584/{api,ui}/summary.json + *.png
清理：供应商 DELETE（软删）+ agent_* 行按 session 硬删；假 LLM 进程退出。
"""
import argparse
import io
import json
import os
import subprocess
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART_ROOT = os.path.join(HERE, 'artifacts', 'int2584')
USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')
PROVIDER_NAME = 'probe-int2584-llm'
MODEL = 'mock-model'
LLM_PORT = 18877
PG = ['docker', 'exec', 'intelligent-audio-test-postgres-1',
      'psql', '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test',
      '-t', '-A', '-c']

SUGGESTED_TOOLS = ['platform_contract', 'tool_search']
EXPECTED_NAME = 'platform-contract-tool-search'

RESULT = {'phase': '', 'checks': {}, 'steps': [], 'screenshots': [],
          'requests': [], 'notes': [], 'events': {}}


def log(msg):
    print('[int2584] %s' % msg, flush=True)


def record(step, status, detail=''):
    RESULT['steps'].append({'step': step, 'status': status, 'detail': detail})
    log('%s: %s %s' % (step, status, detail))


def ok(check, **payload):
    RESULT['checks'][check] = {'ok': True, **payload}
    record(check, 'PASS', json.dumps(payload, ensure_ascii=False)[:400])


def fail(check, reason, **payload):
    RESULT['checks'][check] = {'ok': False, 'reason': reason, **payload}
    record(check, 'FAIL', reason)
    raise AssertionError('%s: %s' % (check, reason))


# ─────────────────────────────────────────── 假 LLM（只替代模型供应商）
def _sse(delta, finish=None):
    body = {'choices': [{'index': 0, 'delta': delta,
                         'finish_reason': finish}]}
    return 'data: %s\n\n' % json.dumps(body, ensure_ascii=False)


def _tool_call_frame(index, call_id, name, arguments):
    return _sse({'role': 'assistant', 'tool_calls': [{
        'index': index, 'id': call_id, 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments,
                                                           ensure_ascii=False)},
    }]})


FINAL_TEXT = ('已整理本次导出流程，可以把这套步骤沉淀为可复用的 Skill。')
HITS = {'chat': 0, 'scenarios': {}}


class FakeLlm(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # noqa: ANN001 - 静音
        pass

    def _send_json(self, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def _send_sse(self, body: str):
        raw = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        if self.path.split('?')[0].rstrip('/').endswith('/models'):
            self._send_json({'object': 'list',
                             'data': [{'id': MODEL, 'object': 'model'}]})
            return
        self._send_json({'error': {'message': 'not found'}})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b'{}')
        except ValueError:
            payload = {}
        if not self.path.split('?')[0].rstrip('/').endswith('/chat/completions'):
            self._send_json({'error': {'message': 'not found'}})
            return

        messages = payload.get('messages') or []
        user_text = ''
        last_role = (messages[-1] or {}).get('role') if messages else ''
        for message in messages:
            if message.get('role') == 'user':
                content = message.get('content') or ''
                if isinstance(content, list):
                    content = ' '.join(
                        str(part.get('text') or '') for part in content
                        if isinstance(part, dict))
                user_text = str(content)

        HITS['chat'] += 1
        # 只看「最后一条」是不是工具结果：同一会话里跨 run 的历史也会带 role=tool，
        # 用「任意历史有 tool」判断会把新 run 的第一轮误当 followup（不再调工具）。
        if last_role == 'tool':
            # 第二轮：工具结果已回填，给正文 + stop，让 run 正常收口
            scenario = 'followup'
            body = _sse({'role': 'assistant', 'content': FINAL_TEXT})
            body += _sse({}, 'stop') + 'data: [DONE]\n\n'
        elif 'one-tool' in user_text:
            scenario = 'one-tool'
            body = _tool_call_frame(0, 'call_%d_one' % HITS['chat'],
                                    'platform_contract', {})
            body += _sse({}, 'tool_calls') + 'data: [DONE]\n\n'
        elif 'no-tool' in user_text:
            scenario = 'no-tool'
            body = _sse({'role': 'assistant', 'content': FINAL_TEXT})
            body += _sse({}, 'stop') + 'data: [DONE]\n\n'
        else:
            # two-tools（默认）：两个只读意图工具都走真实平台执行
            scenario = 'two-tools'
            body = _tool_call_frame(0, 'call_%d_a' % HITS['chat'],
                                    'platform_contract', {})
            body += _tool_call_frame(1, 'call_%d_b' % HITS['chat'],
                                     'tool_search', {'query': '报告导出'})
            body += _sse({}, 'tool_calls') + 'data: [DONE]\n\n'
        HITS['scenarios'][scenario] = HITS['scenarios'].get(scenario, 0) + 1
        log('fake-llm chat #%d scenario=%s' % (HITS['chat'], scenario))
        self._send_sse(body)


def start_fake_llm():
    server = ThreadingHTTPServer(('0.0.0.0', LLM_PORT), FakeLlm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log('fake LLM listening 0.0.0.0:%d' % LLM_PORT)
    return server


# ─────────────────────────────────────────── API 侧真事件
def ensure_provider(api: ApiClient):
    items = api.request('GET', '/agent/providers').get('items') or []
    for item in items:
        if item.get('name') == PROVIDER_NAME and item.get('status') != 'DELETED':
            api.request('POST', '/agent/providers/%s/set-default' % item['id'])
            record('provider', 'PASS', 'reuse %s' % item['id'])
            return item['id']
    created = api.request('POST', '/agent/providers', {
        'name': PROVIDER_NAME,
        'protocol': 'OPENAI_COMPATIBLE',
        'base_url': 'http://host.docker.internal:%d/v1' % LLM_PORT,
        'model': MODEL,
        'api_key': 'probe-key',
    })
    api.request('POST', '/agent/providers/%s/set-default' % created['id'])
    record('provider', 'PASS', 'created %s' % created['id'])
    return created['id']


def run_and_collect(api: ApiClient, message: str, timeout: float = 120.0):
    session = api.request('POST', '/agent/sessions', {
        'title': 'INT-2584 probe ' + message[:20],
    })
    created = api.request('POST', '/agent/sessions/%s/runs' % session['id'],
                          {'message': message, 'mode': 'chat'})
    run_id = created['run']['id']
    events = []
    url = ('http://127.0.0.1:15000/api/v1/agent/runs/%s/events' % run_id)
    deadline = time.time() + timeout
    with httpx.stream('GET', url, timeout=timeout, trust_env=False,
                      headers={'Authorization': 'Bearer ' + api.token}) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if time.time() > deadline:
                break
            if not line.startswith('data:'):
                continue
            try:
                event = json.loads(line[5:].strip())
            except ValueError:
                continue
            events.append(event)
            if event.get('type') == 'run_finished':
                break
    return session['id'], run_id, events


def summarize(events):
    types = [event.get('type') for event in events]
    suggestion = next((event for event in events
                       if event.get('type') == 'skill_draft_suggested'), None)
    return types, suggestion


def phase_api(api: ApiClient):
    sessions = []

    # ① ≥2 工具：事件必须真实下发
    sid, rid, events = run_and_collect(
        api, 'two-tools 请整理导出报告流程（INT-2584 真事件探针）')
    sessions.append(sid)
    types, suggestion = summarize(events)
    RESULT['events']['two_tools'] = types
    record('two_tools_events', 'PASS', ','.join(types))
    if suggestion is None:
        fail('two_tools_suggested', '真 run 未收到 skill_draft_suggested：%s'
             % types)
    payload = suggestion
    if payload.get('created') is not False:
        fail('two_tools_suggested', 'created 非 false：%r' % payload.get('created'))
    if payload.get('requires_confirmation') is not True:
        fail('two_tools_suggested', 'requires_confirmation 非 true：%r'
             % payload.get('requires_confirmation'))
    tools = payload.get('tools_used') or []
    if sorted(tools) != SUGGESTED_TOOLS:
        fail('two_tools_suggested', 'tools_used 不符：%r' % tools)
    if payload.get('suggested_name') != EXPECTED_NAME:
        fail('two_tools_suggested', 'suggested_name 不符：%r'
             % payload.get('suggested_name'))
    # 事件到达顺序：建议先于 run_finished（前端先渲染卡片再收口）
    if types.index('skill_draft_suggested') > types.index('run_finished'):
        fail('two_tools_order', '建议事件晚于 run_finished：%s' % types)
    ok('two_tools_suggested',
       suggested_name=payload.get('suggested_name'),
       description=payload.get('description'),
       tools_used=tools, created=payload.get('created'),
       requires_confirmation=payload.get('requires_confirmation'),
       order_before_finish=True)

    # run 正常结束 + 工具都 COMPLETED
    if 'run_finished' not in types or not any(
            event.get('type') == 'run_finished'
            and event.get('status') == 'SUCCEEDED' for event in events):
        fail('two_tools_succeeded', 'run 未以 SUCCEEDED 收口：%s'
             % [e for e in events if e.get('type') == 'run_finished'])
    completed = {event.get('tool') for event in events
                 if event.get('type') == 'tool_result' and event.get('ok')}
    RESULT['events']['tools_completed'] = sorted(completed)
    if sorted(completed) != SUGGESTED_TOOLS:
        fail('two_tools_succeeded', '工具未全部 COMPLETED：%r' % sorted(completed))
    ok('two_tools_succeeded', tools=sorted(completed), status='SUCCEEDED')

    # ② 单工具：不出现建议（≥2 的门槛）
    sid, rid, events = run_and_collect(
        api, 'one-tool 请查询一次平台口径（INT-2584 负例）')
    sessions.append(sid)
    types, suggestion = summarize(events)
    RESULT['events']['one_tool'] = types
    if suggestion is not None:
        fail('one_tool_absent', '单工具 run 也下发了建议：%r' % suggestion)
    ok('one_tool_absent', event_types=types)

    # ③ 不用工具：不出现建议
    sid, rid, events = run_and_collect(
        api, 'no-tool 随便聊一句（INT-2584 负例）')
    sessions.append(sid)
    types, suggestion = summarize(events)
    RESULT['events']['no_tool'] = types
    if suggestion is not None:
        fail('no_tool_absent', '无工具 run 也下发了建议：%r' % suggestion)
    ok('no_tool_absent', event_types=types)

    return sessions


# ─────────────────────────────────────────── DB 清理
def psql(sql: str):
    proc = subprocess.run(PG + [sql], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def discover_probe_sessions():
    """UI 阶段会话是页面自己建的：按消息标记（INT-2584）与时间窗反查，避免误删他人会话。"""
    code, out = psql(
        "select distinct r.session_id from agent_run r "
        "join agent_run_event e on e.run_id = r.id "
        "where r.created_at > (now() at time zone 'utc') - interval '1 hour' "
        "and e.payload::text like '%INT-2584%';")
    found = [line.strip() for line in (out or '').splitlines() if line.strip()]
    log('discover probe sessions: %s' % found)
    return found


def cleanup_db(sessions, provider_id=None):
    sessions = sessions or []
    touched = []
    for session_id in sessions:
        code, out = psql(
            "select id from agent_run where session_id = '%s';" % session_id)
        run_ids = [line.strip() for line in out.splitlines() if line.strip()]
        for run_id in run_ids:
            psql("delete from agent_run_event where run_id = '%s';" % run_id)
            psql("delete from agent_step where run_id = '%s';" % run_id)
            psql("delete from agent_tool_call where run_id = '%s';" % run_id)
            psql("delete from agent_approval where run_id = '%s';" % run_id)
            psql("delete from agent_run_skill where run_id = '%s';" % run_id)
            psql("delete from agent_context_snapshot where run_id = '%s';"
                 % run_id)
            psql("delete from agent_artifact where run_id = '%s';" % run_id)
            psql("delete from agent_run where id = '%s';" % run_id)
        psql("delete from agent_session where id = '%s';" % session_id)
        touched.append(session_id)
    if provider_id:
        psql("delete from agent_llm_provider where id = '%s';" % provider_id)
    left = psql("select count(*) from agent_run where session_id in (%s);"
                % (','.join("'%s'" % s for s in sessions) if sessions else "''"))
    residue = (left[1] or '').strip().splitlines()
    if residue and residue[-1].strip() not in ('', '0'):
        record('cleanup', 'WARN', '残留 %s' % residue[-1])
    else:
        ok('cleanup', sessions=len(sessions), provider_removed=bool(provider_id))


# ─────────────────────────────────────────── UI 侧（Selenium）
def make_driver():
    from selenium import webdriver
    opts = webdriver.ChromeOptions()
    for arg in ('--headless=new', '--window-size=1680,1050', '--disable-gpu',
                '--no-sandbox', '--lang=zh-CN', '--disable-dev-shm-usage'):
        opts.add_argument(arg)
    opts.set_capability('goog:loggingPrefs',
                        {'performance': 'ALL', 'browser': 'ALL'})
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(90)
    return drv


def shot(drv, key):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, key + '.png')
    drv.save_screenshot(path)
    RESULT['screenshots'].append({'name': key, 'size': os.path.getsize(path)})
    log('SHOT %s (%d bytes)' % (key, os.path.getsize(path)))


def body_text(drv):
    return drv.execute_script(
        'return document.body ? document.body.innerText : ""') or ''


def wait_text(drv, text, timeout=40):
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def wait_card(drv, timeout=90):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(By.CSS_SELECTOR,
                                  '[data-testid="skill-suggestion-card"]'))
    return drv.find_element(By.CSS_SELECTOR,
                            '[data-testid="skill-suggestion-card"]')


def click(drv, element):
    drv.execute_script('arguments[0].click()', element)
    time.sleep(0.4)


def type_into(drv, selector, value):
    from selenium.webdriver.common.by import By
    el = drv.find_element(By.CSS_SELECTOR, selector)
    el.click()
    el.send_keys(value)
    time.sleep(0.3)
    current = drv.execute_script(
        'return document.querySelector(arguments[0]).value', selector)
    if current != value:
        drv.execute_script(
            'const el=document.querySelector(arguments[0]);'
            'const proto=(el instanceof HTMLTextAreaElement)'
            '?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;'
            "Object.getOwnPropertyDescriptor(proto,'value').set.call(el,arguments[1]);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));",
            selector, value)
    return el


def login_ui(drv, base):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
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
    submits = [b for b in drv.find_elements(By.TAG_NAME, 'button')
               if (b.text or '').strip() in ('登录', '登 录')]
    click(drv, submits[-1] if submits else
          drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
    WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2)


def set_theme(drv, base, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light')
    drv.get(base + '/ai-chat')
    time.sleep(2.5)


def install_request_counter(drv):
    """页面内 fetch/XHR 计数（Selenium performance 日志读取即清空，不适合前后比数）。"""
    drv.execute_script(
        "window.__probeReqs = [];"
        "if (!window.__probeHooked) {"
        "  window.__probeHooked = true;"
        "  const __f = window.fetch;"
        "  window.fetch = function(input, init) {"
        "    try { window.__probeReqs.push((typeof input === 'string' ? input"
        "      : (input && input.url)) || ''); } catch (e) {}"
        "    return __f.apply(this, arguments);"
        "  };"
        "  const __o = XMLHttpRequest.prototype.open;"
        "  XMLHttpRequest.prototype.open = function(method, url) {"
        "    try { window.__probeReqs.push(String(url)); } catch (e) {}"
        "    return __o.apply(this, arguments);"
        "  };"
        "}")


def counted_requests(drv):
    return list(drv.execute_script(
        'return (window.__probeReqs || []).slice()') or [])


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


def api_requests(drv):
    return [item for item in request_log(drv)
            if '/api/' in (item.get('url') or '')]


def send_chat(drv, message):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'textarea')))
    time.sleep(1.2)
    type_into(drv, 'textarea', message)
    time.sleep(0.5)
    submits = [b for b in drv.find_elements(By.CSS_SELECTOR,
                                            'button[type=submit]')
               if b.is_displayed()]
    if not submits:
        fail('ui_send', '/ai-chat 没有可用的发送按钮')
    click(drv, submits[-1])


def phase_ui(drv, base: str, api: ApiClient):
    from selenium.webdriver.common.by import By

    login_ui(drv, base)
    drv.execute_cdp_cmd('Network.enable', {})
    set_theme(drv, base, False)

    # ① 真 run → 真卡片
    send_chat(drv, 'two-tools 请整理导出报告流程（INT-2584 真事件探针）')
    card = wait_card(drv, 120)
    card_text = card.text
    suggested = card.get_attribute('data-suggested-name')
    if suggested != EXPECTED_NAME:
        fail('ui_card', '建议名不符：%r' % suggested)
    for needle in ('沉淀为 Skill', EXPECTED_NAME, '不自动落库'):
        if needle not in card_text:
            fail('ui_card', '卡片缺少文案「%s」：%s' % (needle, card_text))
    if 'platform_contract' not in card_text or 'tool_search' not in card_text:
        fail('ui_card', '工具清单不符：%s' % card_text)
    shot(drv, 'light_card')
    ok('ui_card', suggested_name=suggested,
       text=card_text.replace('\n', ' | ')[:300])

    # ② 忽略：卡片消失、其余内容不动、无新增请求
    install_request_counter(drv)
    before = len(counted_requests(drv))
    request_log(drv)  # 先读一次清空 performance 缓冲：之后读到的就是「点击窗口内」的请求
    click(drv, drv.find_element(
        By.CSS_SELECTOR, '[data-testid="skill-suggestion-dismiss"]'))
    time.sleep(2.0)
    if drv.find_elements(By.CSS_SELECTOR,
                         '[data-testid="skill-suggestion-card"]'):
        fail('ui_dismiss', '点「忽略」后卡片仍在')
    all_requests = counted_requests(drv)
    new_requests = all_requests[before:]
    cdp_window = request_log(drv)
    RESULT.setdefault('request_windows', {})['dismiss_window'] = new_requests
    RESULT['request_windows']['dismiss_window_cdp'] = cdp_window
    if new_requests:
        fail('ui_dismiss', '忽略触发了请求：%s' % new_requests)
    api_window = [item for item in cdp_window
                  if '/api/' in (item.get('url') or '')]
    if api_window:
        fail('ui_dismiss', '忽略触发了接口请求（CDP）：%s' % api_window)
    if FINAL_TEXT not in body_text(drv):
        fail('ui_dismiss', '忽略后该轮正文消失（页面其他内容被改动）')
    if not drv.find_elements(By.CSS_SELECTOR, 'textarea'):
        fail('ui_dismiss', '忽略后输入区消失（页面其他内容被改动）')
    shot(drv, 'light_dismissed')
    ok('ui_dismiss', requests_delta=0, message_kept=True, composer_kept=True)

    # ③ 刷新：该消息仍无卡片（随既有消息持久化，不新增持久化口径）
    drv.get(base + '/ai-chat')
    time.sleep(3.0)
    if FINAL_TEXT in body_text(drv):
        if drv.find_elements(By.CSS_SELECTOR,
                             '[data-testid="skill-suggestion-card"]'):
            fail('ui_refresh', '刷新后建议卡又出现了（忽略没有随消息持久化）')
        ok('ui_refresh', card_absent=True, message_restored=True)
    else:
        RESULT['notes'].append('刷新后本地消息未恢复：仅断言无卡片')
        if drv.find_elements(By.CSS_SELECTOR,
                             '[data-testid="skill-suggestion-card"]'):
            fail('ui_refresh', '刷新后建议卡又出现了')
        ok('ui_refresh', card_absent=True, message_restored=False)

    # ④ 去创建草稿：真事件关键词跳转 + 预填
    send_chat(drv, 'two-tools 再来一轮用于验证跳转（INT-2584）')
    wait_card(drv, 120)
    click(drv, drv.find_element(
        By.CSS_SELECTOR, '[data-testid="skill-suggestion-create"]'))
    time.sleep(3.0)
    url = drv.current_url
    if '/agent-skills' not in url or ('name=' + EXPECTED_NAME) not in url:
        fail('ui_prefill', '跳转 URL 不符：%s' % url)
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-name')))
    name_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-name').get_attribute('value')
    desc_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-description').get_attribute('value')
    if name_value != EXPECTED_NAME:
        fail('ui_prefill', '名称未预填：%r' % name_value)
    if '沉淀' not in (desc_value or ''):
        fail('ui_prefill', '描述未预填：%r' % desc_value)
    shot(drv, 'light_prefill')
    ok('ui_prefill', url=url, name=name_value, description=desc_value)

    # ⑤ 深色：再来一轮真 run，卡片 + 忽略
    set_theme(drv, base, True)
    send_chat(drv, 'two-tools 深色复核（INT-2584）')
    wait_card(drv, 120)
    cards = drv.find_elements(By.CSS_SELECTOR,
                              '[data-testid="skill-suggestion-card"]')
    # 会话有滚动容器：把本轮卡片滚到视口中央再截图（否则截到的是会话顶部）
    drv.execute_script('arguments[0].scrollIntoView({block: "center"})',
                       cards[-1])
    time.sleep(0.8)
    shot(drv, 'dark_card')
    cards_before = len(drv.find_elements(
        By.CSS_SELECTOR, '[data-testid="skill-suggestion-card"]'))
    # 页面上可能残留前一步未忽略的卡片（同一会话多条消息各一张）：逐张点掉
    for _ in range(cards_before + 2):
        buttons = drv.find_elements(
            By.CSS_SELECTOR, '[data-testid="skill-suggestion-dismiss"]')
        if not buttons:
            break
        click(drv, buttons[-1])
        time.sleep(0.8)
    time.sleep(1.2)
    if drv.find_elements(By.CSS_SELECTOR,
                         '[data-testid="skill-suggestion-card"]'):
        fail('ui_dark_dismiss', '深色下点「忽略」后卡片仍在')
    anchors = drv.find_elements(
        By.XPATH, "//*[contains(text(), 'two-tools 深色复核')]")
    if anchors:
        drv.execute_script('arguments[0].scrollIntoView({block: "center"})',
                           anchors[-1])
        time.sleep(0.6)
    shot(drv, 'dark_dismissed')
    ok('ui_dark_dismiss', cards_before=cards_before, cards_after=0)

    # ⑥ 负例：单工具 / 无工具不出卡片（同一页面连发两条）
    set_theme(drv, base, False)
    for message, key in (
            ('one-tool 请查询一次平台口径（INT-2584 负例）', 'ui_one_tool'),
            ('no-tool 随便聊一句（INT-2584 负例）', 'ui_no_tool')):
        send_chat(drv, message)
        wait_text(drv, '可以把这套步骤沉淀', 90)  # 等本轮正文落地
        time.sleep(1.5)
        if drv.find_elements(By.CSS_SELECTOR,
                             '[data-testid="skill-suggestion-card"]'):
            fail(key, '不该出卡片却出现了：%s' % message)
        if FINAL_TEXT not in body_text(drv):
            fail(key, '本轮正文未出现（判据异常）')
        ok(key, card_absent=True)

    RESULT['net'] = request_log(drv)[-40:]


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with io.open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['api', 'ui'], required=True)
    parser.add_argument('--base', default='http://localhost:5384')
    parser.add_argument('--api', default='http://127.0.0.1:15000')
    args = parser.parse_args()

    global ART
    ART = os.path.join(ART_ROOT, args.phase)
    RESULT['phase'] = args.phase
    RESULT['base'] = args.base
    RESULT['api'] = args.api

    server = start_fake_llm()
    client = ApiClient(args.api)
    client.login(USERNAME, PASSWORD)
    provider_id = None
    sessions = []
    drv = None
    exit_code = 0
    try:
        provider_id = ensure_provider(client)
        if args.phase == 'api':
            sessions = phase_api(client)
        else:
            drv = make_driver()
            phase_ui(drv, args.base, client)
            sessions = discover_probe_sessions()
    except Exception as exc:  # noqa: BLE001
        RESULT['error'] = '%s: %s' % (type(exc).__name__, exc)
        RESULT['trace'] = traceback.format_exc()[-3000:]
        log('FAIL %s' % RESULT['error'])
        exit_code = 1
    finally:
        try:
            write_artifacts()
        except Exception:  # noqa: BLE001
            pass
        if drv is not None:
            try:
                drv.quit()
            except Exception:  # noqa: BLE001
                pass
        try:
            if provider_id:
                client.request('DELETE', '/agent/providers/%s' % provider_id)
        except Exception:  # noqa: BLE001
            pass
        try:
            # 失败中途退出时 sessions 可能没返回：按消息标记反查，确保自建自清
            cleanup_db(sessions or discover_probe_sessions(), provider_id)
        except Exception:  # noqa: BLE001
            log('cleanup error %s' % traceback.format_exc()[-500:])
        server.shutdown()
        write_artifacts()
    print(json.dumps({'phase': args.phase, 'exit': exit_code,
                      'checks': RESULT['checks']}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
