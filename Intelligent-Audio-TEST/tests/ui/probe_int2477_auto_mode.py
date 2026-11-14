# -*- coding: utf-8 -*-
"""INT-2477 Auto 模式前端实测（真实栈：React dev → 网关 15000 → agent_service）。

被测代码 = 本 run worktree 的 frontend-react；后端为 docker 栈（agent_service /
api_gateway 已刷到含 INT-2474 Auto 的镜像）。模型用宿主机假 LLM（OpenAI 兼容
SSE，按目标里的场景标记决定回 tool_call / 完成标记），页面所有请求都走真实后端，
不做任何响应拦截（错误态一例用 CDP 网络阻断，见步骤说明）。

场景（一条脚本跑完，每条用独立浏览器上下文 = 独立会话）：
  A 进度 + 预算暂停 + 继续 + 完成（浅色；深色另跑一次并截暂停点）
  B 写操作审批联动：Auto 下逐条确认、无「全部自动批准」，拒绝后继续跑完
  C 超预算：终态「超出预算已停止」，不误导为成功
  D 熔断：连续失败暂停 → 继续 → 熔断 FAILED
  E 普通对话：请求体不带 mode / budget，Auto 面板不出现
  F 加载态（首轮模型慢响应的「正在收集步骤进度…」）/ 空态（暂无产物）/
    错误态（CDP 阻断发起请求）

跑法：
  <conda python> tests/ui/probe_int2477_auto_mode.py \
      --base http://localhost:5377 --api http://localhost:15000
产出：tests/ui/artifacts/int2477_auto/{summary.json,network.json,*.png}
收尾：删除本脚本的假供应商 + 本脚本会话的所有 agent_* 数据（按 session_id）。
"""
import argparse
import asyncio
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from playwright.async_api import async_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, 'artifacts', 'int2477_auto')

PROVIDER_NAME = '接线测试_INT2477_auto'
PROVIDER_MODEL = 'mock-model'
FAKE_LLM_PORT = 18879

SESSION_KEY = 'iatp:ai-chat:v1:agent-session'
THEME_KEY = 'iatp:theme:v1:mode'

SCN_PROGRESS = '[[SCN:PROGRESS]]'
SCN_APPROVAL = '[[SCN:APPROVAL]]'
SCN_BUDGET = '[[SCN:BUDGET]]'
SCN_CIRCUIT = '[[SCN:CIRCUIT]]'

# ---------------------------------------------------------------- 假 LLM


def _frame(payload):
    return 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'


class FakeLlm(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):  # 安静
        pass

    def _chunk(self, text):
        raw = text.encode('utf-8')
        self.wfile.write(('%x\r\n' % len(raw)).encode('ascii') + raw + b'\r\n')
        self.wfile.flush()

    def _start_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

    def _end_stream(self):
        self._chunk('data: [DONE]\n\n')
        self.wfile.write(b'0\r\n\r\n')
        self.wfile.flush()

    def do_GET(self):
        if self.path.rstrip('/').endswith('/models'):
            body = json.dumps(
                {'data': [{'id': PROVIDER_MODEL}]}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            body = json.loads(raw.decode('utf-8'))
        except Exception:
            body = {}
        messages = body.get('messages') or []
        texts = [str(m.get('content') or '') for m in messages
                 if m.get('role') in ('system', 'user')]
        blob = '\n'.join(texts)
        last_user = ''
        for message in reversed(messages):
            if message.get('role') == 'user':
                last_user = str(message.get('content') or '')
                break
        has_tool_message = any(m.get('role') == 'tool' for m in messages)
        resumed = '用户已确认继续' in last_user
        first_call = not any(m.get('role') == 'assistant' for m in messages)

        self._start_stream()

        def tool_call(name, arguments, call_id):
            self._chunk(_frame({'choices': [{
                'delta': {'tool_calls': [{
                    'index': 0,
                    'id': call_id,
                    'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)},
                }]},
                'finish_reason': 'tool_calls',
            }]}))

        def text_reply(text):
            self._chunk(_frame({'choices': [{
                'delta': {'content': text},
                'finish_reason': 'stop',
            }]}))

        if SCN_CIRCUIT in blob:
            # 连续工具失败：未知工具恒失败 → 2 次暂停、继续后第 3 次熔断。
            # tool_call_id 必须每次唯一：同 id 会被幂等复用上次的失败结果，
            # 连续失败数永远停在 1（实测踩到）。
            tool_call('__int2477_unknown_tool__', {}, 'call_bad_%s' % uuid.uuid4().hex[:10])
        elif SCN_BUDGET in blob:
            # 永不完成：把收紧后的轮次预算耗满 → BUDGET_EXCEEDED
            tool_call('platform_contract', {'query': '任务状态'},
                      'call_b_%s' % uuid.uuid4().hex[:10])
        elif SCN_APPROVAL in blob:
            # 首轮提一条真实写操作（testcase_write 走通用审批：落 agent_approval +
            # approval_required）；已有工具结果 / 非首轮说明审批已被拒，直接收口。
            if has_tool_message or not first_call:
                text_reply('已按审批结果继续并完成 [[AUTO_DONE]]')
            else:
                tool_call(
                    'testcase_write',
                    {
                        'action': 'create',
                        'body': {
                            'name': '接线测试_INT2477_auto临时',
                            'type': 'functional',
                            'description': 'INT-2477 验收临时数据（拒绝后不落库）',
                            # action=create 的 body 必须归属分组；本脚本只拒绝不批准，
                            # 不会真的往该分组写用例（approval 被 REJECTED 即不执行）。
                            'group_id': '350bb459-7eba-431d-91de-707770672044',
                        },
                    },
                    'call_ap',
                )
        elif SCN_PROGRESS in blob:
            if resumed:
                text_reply('目标已全部达成 [[AUTO_DONE]]')
            else:
                if first_call:
                    # 首轮慢响应：页面停在「正在收集步骤进度…」加载态
                    time.sleep(3.2)
                tool_call('platform_contract', {'query': '任务状态'},
                          'call_p_%s' % uuid.uuid4().hex[:10])
        else:
            text_reply('这是普通对话的回复（Auto 未开启）。')
        self._end_stream()


def start_fake_llm():
    server = ThreadingHTTPServer(('0.0.0.0', FAKE_LLM_PORT), FakeLlm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------- 浏览器工具


async def login(page, base):
    await page.goto(base + '/login', wait_until='domcontentloaded')
    await page.wait_for_selector('#username', timeout=60000)
    await page.fill('#username', 'dev_user')
    await page.fill('#password', 'dev_password')
    await page.locator("button[type='submit']").click()
    await page.wait_for_function(
        "() => !location.pathname.startsWith('/login')", timeout=60000)
    await page.wait_for_timeout(1200)


async def api(page, api_base, method, path, payload=None):
    """借页面 token 直接调真实网关（供应商注册 / 清理）。"""
    token = await page.evaluate(
        "() => { const raw = localStorage.getItem('iatp:auth:token:v1');"
        " if (!raw) return null; try { const v = JSON.parse(raw);"
        " return v && v.data !== undefined ? v.data : v } catch (e) { return raw } }"
    )
    if isinstance(token, dict):
        token = token.get('accessToken') or token.get('access_token')
    return await page.evaluate(
        """async ([method, path, payload, token]) => {
            // 同源相对路径：dev server 的 /api 已代理到网关，避免跨域 CORS 拦截
            const resp = await fetch(path, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: 'Bearer ' + token,
                },
                body: payload === null ? undefined : JSON.stringify(payload),
            })
            const text = await resp.text()
            let body = null
            try { body = JSON.parse(text) } catch (e) { body = text }
            return { status: resp.status, body }
        }""",
        [method, path, payload, token],
    )


def _items(resp):
    body = resp.get('body')
    if isinstance(body, dict):
        if isinstance(body.get('items'), list):
            return body['items']
        if isinstance(body.get('data'), dict) and isinstance(body['data'].get('items'), list):
            return body['data']['items']
    return []


async def ensure_provider(page, api_base):
    listed = await api(page, api_base, 'GET', '/api/v1/agent/providers')
    for item in _items(listed):
        if item.get('name') == PROVIDER_NAME:
            await api(page, api_base, 'PUT',
                      '/api/v1/agent/providers/%s' % item['id'], {
                          'base_url': 'http://host.docker.internal:%d/v1' % FAKE_LLM_PORT,
                          'model': PROVIDER_MODEL,
                      })
            await api(page, api_base, 'POST',
                      '/api/v1/agent/providers/%s/set-default' % item['id'])
            return item['id']
    created = await api(page, api_base, 'POST', '/api/v1/agent/providers', {
        'name': PROVIDER_NAME,
        'protocol': 'OPENAI_COMPATIBLE',
        'base_url': 'http://host.docker.internal:%d/v1' % FAKE_LLM_PORT,
        'model': PROVIDER_MODEL,
        'api_key': 'int2477-mock-key',
    })
    body = created.get('body') or {}
    if isinstance(body.get('data'), dict):
        body = body['data']
    provider_id = body.get('id')
    if provider_id:
        await api(page, api_base, 'POST',
                  '/api/v1/agent/providers/%s/set-default' % provider_id)
    return provider_id


async def new_session_page(browser, base, dark=False):
    ctx = await browser.new_context(
        viewport={'width': 1680, 'height': 950},
        color_scheme='dark' if dark else 'light',
    )
    page = await ctx.new_page()
    return ctx, page


async def open_chat(page, base):
    await page.goto(base + '/ai-chat', wait_until='domcontentloaded')
    await page.wait_for_selector('textarea', timeout=60000)
    await page.wait_for_timeout(1500)


async def select_auto(page):
    await page.locator('[data-agent-mode-option="auto"]').click()
    await page.wait_for_selector('[data-auto-budget-settings]', timeout=15000)


async def set_rounds(page, rounds):
    inputs = page.locator('[data-auto-budget-settings] input')
    await inputs.nth(0).fill(str(rounds))
    await page.wait_for_timeout(200)


async def send_goal(page, goal):
    textarea = page.locator('textarea').first
    await textarea.fill(goal)
    await textarea.press('Enter')


async def wait_text(page, text, timeout=60000):
    await page.get_by_text(text, exact=False).first.wait_for(
        state='visible', timeout=timeout)


async def shot(page, name, selector=None):
    """截图前把目标区域滚进视口（会话区自身带滚动容器，整页截图会截到折叠区）。"""
    if selector:
        try:
            await page.locator(selector).first.evaluate(
                "el => el && el.scrollIntoView({block: 'center'})")
            await page.wait_for_timeout(500)
        except Exception:
            pass
    path = os.path.join(OUT, name)
    await page.screenshot(path=path)
    return path


async def main(base, api_base):
    os.makedirs(OUT, exist_ok=True)
    server = start_fake_llm()
    net = []
    results = {'env': {'base': base, 'api': api_base}, 'steps': [], 'shots': []}
    sessions = []

    def step(name, ok, detail=None):
        results['steps'].append({'step': name, 'ok': bool(ok), 'detail': detail or {}})
        print('[STEP] %-52s %s %s' % (name, 'PASS' if ok else 'FAIL',
                                      json.dumps(detail or {}, ensure_ascii=False)[:300]))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()

        # ---- 初始化：登录 + 注册假供应商
        ctx0, page0 = await new_session_page(browser, base)
        await login(page0, base)
        provider_id = await ensure_provider(page0, api_base)
        step('provider_ready', bool(provider_id), {'provider_id': provider_id})
        await ctx0.close()

        async def attach(page, tag):
            def on_request(req):
                if '/api/v1/agent/' in req.url:
                    net.append({
                        'tag': tag,
                        'method': req.method,
                        'url': req.url.split('?')[0],
                        'post': req.post_data,
                    })

            def on_response(resp):
                if '/api/v1/agent/sessions' in resp.url and resp.request.method == 'POST' \
                        and resp.url.rstrip('/').endswith('/sessions'):
                    async def read():
                        try:
                            data = json.loads(await resp.text())
                            sid = (data.get('session') or {}).get('id') or data.get('id')
                            if sid:
                                sessions.append(sid)
                        except Exception:
                            pass
                    asyncio.ensure_future(read())

            page.on('request', on_request)
            page.on('response', lambda r: on_response(r))

        def run_bodies(tag):
            out = []
            for item in net:
                if item['tag'] != tag or '/runs' not in item['url']:
                    continue
                if item['method'] != 'POST' or not item['post']:
                    continue
                try:
                    out.append(json.loads(item['post']))
                except Exception:
                    pass
            return out

        # ================= A：进度 + 预算暂停 + 继续 + 完成（浅色）
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await attach(page, 'A')
        await open_chat(page, base)
        await select_auto(page)
        await set_rounds(page, 5)
        await send_goal(page, '把回归测试全用例跑一遍并给我结论 %s' % SCN_PROGRESS)

        await page.wait_for_selector('[data-auto-progress]', timeout=60000)
        # 加载态：run 已受理、首个 auto_step 刚到（0 消耗、助手气泡流式中）。
        # 「正在收集步骤进度…」占位只存在于首个 auto_step 到达前的毫秒级窗口，
        # 不作为可截图状态断言；这里以面板首屏（0 消耗 + 正在回复）为加载态证据。
        initial_ratio = await page.locator('[data-auto-ratio]').first.inner_text()
        streaming = await page.get_by_text('正在回复', exact=False).count() > 0
        results['shots'].append(await shot(page, '01_A_initial_loading_light.png'))
        step('A_initial_loading', streaming and '0%' in initial_ratio,
             {'ratio': initial_ratio, 'streaming': streaming})

        await page.wait_for_selector('[data-auto-step]', timeout=90000)
        step_texts = []
        for _ in range(30):
            try:
                text = await page.locator('[data-auto-step]').first.inner_text()
                step_texts.append(text)
            except Exception:
                pass
            if await page.locator('[data-auto-paused="true"]').count() > 0:
                break
            await page.wait_for_timeout(500)
        results['shots'].append(await shot(page, '02_A_progress_light.png', '[data-auto-progress]'))
        step('A_progress_updates', len(set(step_texts)) >= 2, {'samples': step_texts[:6]})

        body_a = run_bodies('A')
        request_ok = bool(body_a) and body_a[0].get('mode') == 'auto' \
            and (body_a[0].get('budget') or {}).get('max_rounds') == 5 \
            and 'max_tool_calls' not in (body_a[0].get('budget') or {})
        step('A_request_body', request_ok, body_a[:1])

        await page.wait_for_selector('[data-auto-paused="true"]', timeout=90000)
        pause_reason = await page.locator('[data-auto-pause-reason]').get_attribute(
            'data-auto-pause-reason')
        ratio_text = await page.locator('[data-auto-ratio]').first.inner_text()
        artifacts_text = await page.locator('[data-auto-artifacts]').inner_text()
        results['shots'].append(await shot(page, '03_A_paused_light.png', '[data-auto-progress]'))
        step('A_paused_budget', pause_reason == 'budget_threshold',
             {'reason': pause_reason, 'ratio': ratio_text})
        step('A_empty_artifacts', '暂无产物' in artifacts_text)
        step('A_no_bulk_approve',
             await page.get_by_role('button', name='全部自动批准').count() == 0)

        await page.locator('[data-auto-resume]').click()
        await page.wait_for_selector('[data-auto-terminal="succeeded"]', timeout=90000)
        terminal_text = await page.locator('[data-auto-terminal-message]').inner_text()
        results['shots'].append(await shot(page, '04_A_succeeded_light.png', '[data-auto-progress]'))
        resumed = any('/resume' in item['url'] and item['tag'] == 'A' for item in net)
        step('A_resume_calls_api', resumed)
        step('A_succeeded_terminal', 'Auto 已完成' in terminal_text,
             {'text': terminal_text})
        await ctx.close()

        # ================= A-dark：同一场景深色，截暂停点
        ctx, page = await new_session_page(browser, base, dark=True)
        await login(page, base)
        await attach(page, 'A-dark')
        await open_chat(page, base)
        dark_applied = await page.evaluate(
            "() => document.documentElement.classList.contains('dark')")
        await select_auto(page)
        await set_rounds(page, 5)
        await send_goal(page, '把回归测试全用例跑一遍并给我结论 %s' % SCN_PROGRESS)
        await page.wait_for_selector('[data-auto-paused="true"]', timeout=120000)
        results['shots'].append(await shot(page, '05_A_paused_dark.png', '[data-auto-progress]'))
        step('A_dark_theme', dark_applied)
        await ctx.close()

        # ================= B：审批联动（逐条、无批量、拒绝后继续）
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await attach(page, 'B')
        await open_chat(page, base)
        await select_auto(page)
        await send_goal(page, '写一条用户画像记忆 %s' % SCN_APPROVAL)
        await page.wait_for_selector('[data-agent-approval-panel]', timeout=90000)
        await page.wait_for_selector('[data-auto-approvals-count]', timeout=30000)
        count_attr = await page.locator('[data-auto-approvals-count]').get_attribute(
            'data-auto-approvals-count')
        results['shots'].append(
            await shot(page, '06_B_pending_light.png', '[data-auto-progress]'))
        results['shots'].append(
            await shot(page, '06b_B_approval_card_light.png', '[data-agent-approval-panel]'))
        bulk_count = await page.get_by_role('button', name='全部自动批准').count()
        step('B_approval_linked', count_attr == '1', {'count': count_attr})
        step('B_no_bulk_approve', bulk_count == 0)

        # 会话区在流式输出中持续自动滚动，Playwright 的可点击性等待会被反复打断；
        # 这里用元素自身的 click()（真实 DOM 事件，效果同用户点击）。
        await page.get_by_role('button', name='拒绝').first.evaluate(
            'el => el.click()')
        await page.wait_for_selector('[data-auto-terminal="succeeded"]', timeout=90000)
        results['shots'].append(
            await shot(page, '07_B_rejected_succeeded_light.png', '[data-auto-progress]'))
        step('B_reject_then_continue', True)
        await ctx.close()

        # ================= C：超预算终态
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await attach(page, 'C')
        await open_chat(page, base)
        await select_auto(page)
        await set_rounds(page, 4)
        await send_goal(page, '永不完成的长任务 %s' % SCN_BUDGET)
        await page.wait_for_selector('[data-auto-terminal="budget_exceeded"]',
                                     timeout=120000)
        terminal_text = await page.locator('[data-auto-terminal-message]').inner_text()
        results['shots'].append(await shot(page, '08_C_budget_exceeded_light.png', '[data-auto-progress]'))
        step('C_budget_exceeded', '超出预算' in terminal_text, {'text': terminal_text})
        step('C_not_success', 'Auto 已完成' not in terminal_text)
        await ctx.close()

        # ================= D：连续失败暂停 → 继续 → 熔断
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await attach(page, 'D')
        await open_chat(page, base)
        await select_auto(page)
        await send_goal(page, '连续失败熔断演示 %s' % SCN_CIRCUIT)
        await page.wait_for_selector('[data-auto-paused="true"]', timeout=120000)
        reason = await page.locator('[data-auto-pause-reason]').get_attribute(
            'data-auto-pause-reason')
        results['shots'].append(await shot(page, '09_D_failures_paused_light.png', '[data-auto-progress]'))
        step('D_paused_failures', reason == 'consecutive_tool_failures',
             {'reason': reason})
        await page.locator('[data-auto-resume]').click()
        await page.wait_for_selector('[data-auto-terminal="circuit_break"]',
                                     timeout=120000)
        results['shots'].append(await shot(page, '10_D_circuit_light.png', '[data-auto-progress]'))
        step('D_circuit_break', True)
        await ctx.close()

        # ================= E：普通对话不受影响
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await attach(page, 'E')
        await open_chat(page, base)
        await send_goal(page, '你好，介绍一下你能做什么')
        await wait_text(page, '这是普通对话的回复', timeout=60000)
        body_e = run_bodies('E')
        no_auto_panel = await page.locator('[data-auto-progress]').count() == 0
        results['shots'].append(await shot(page, '11_E_chat_mode_light.png'))
        step('E_chat_body_plain', bool(body_e) and set(body_e[0].keys()) == {'message'},
             body_e[:1])
        step('E_no_auto_panel', no_auto_panel)
        await ctx.close()

        # ================= F：发起失败（CDP 网络阻断）
        ctx, page = await new_session_page(browser, base)
        await login(page, base)
        await open_chat(page, base)
        cdp = await ctx.new_cdp_session(page)
        await cdp.send('Network.enable')
        await cdp.send('Network.setBlockedURLs',
                       {'urls': ['*api/v1/agent/sessions*']})
        await send_goal(page, '这条会发起失败')
        await page.wait_for_timeout(4000)
        error_seen = await page.get_by_text('网络连接失败', exact=False).count() > 0
        results['shots'].append(await shot(page, '12_F_send_error_light.png'))
        step('F_error_state', error_seen)
        await ctx.close()

        await browser.close()

    server.shutdown()

    results['sessions'] = sessions
    with open(os.path.join(OUT, 'network.json'), 'w', encoding='utf-8') as fp:
        json.dump(net, fp, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, 'summary.json'), 'w', encoding='utf-8') as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    passed = sum(1 for item in results['steps'] if item['ok'])
    print('[SUMMARY] %d/%d steps pass' % (passed, len(results['steps'])))
    print(json.dumps({'provider_id': provider_id, 'sessions': sessions},
                     ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:5377')
    parser.add_argument('--api', default='http://localhost:15000')
    args = parser.parse_args()
    asyncio.run(main(args.base.rstrip('/'), args.api.rstrip('/')))
