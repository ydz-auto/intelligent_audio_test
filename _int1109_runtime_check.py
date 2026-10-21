# -*- coding: utf-8 -*-
"""INT-1109 运行时核对：/ai-chat 发送/停止按钮图标化 + 配置即可对话（自动选模型）+ 每页 agent 浮窗。

流程：
1. 打开 /#/ai-chat，配置 mock LLM 供应商（http://127.0.0.1:7799，int1068_mock_chat.cjs），
   自动获取模型 → 校验「配置即可对话」（无需手动选模型，发送钮可点）。
2. 发送一条消息 → 捕获 /chat/completions 真实请求（CDP response 事件）→ 校验回复渲染。
3. 浅色截图 + 深色截图（localStorage iatp:theme:v1=dark + reload）。
4. 打开全局 Agent 工作台浮窗（右上角魔法按钮）→ 校验「本页 Agent 能力」条随路由变化。
5. 生成 Network 证据（HTML 面板截图 + evidence.json）。
"""
import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5522'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1109_shots')
os.makedirs(OUT, exist_ok=True)

EVIDENCE = {}


def wait_for(condition, timeout=20, interval=0.3, label='condition'):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(interval)
    raise TimeoutError(f'等待超时: {label}')


def main():
    captured = []  # /chat/completions 请求记录

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        )
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()

        def on_response(resp):
            if '/chat/completions' in resp.url:
                try:
                    body = resp.text()[:800]
                except Exception:
                    body = ''
                captured.append({
                    'url': resp.url,
                    'status': resp.status,
                    'method': resp.request.method,
                    'requestBody': resp.request.post_data,
                    'responseBody': body,
                })

        page.on('response', on_response)

        # ===== 1. 打开 /ai-chat =====
        page.goto(f'{BASE}/#/ai-chat', wait_until='networkidle')
        page.wait_for_selector('.ai-chat-page')
        page.wait_for_selector('.ai-chat-empty, .ai-chat-message', timeout=15000)
        # 发送/停止按钮形态：发送钮无可见文字（sr-only 隐藏）、仅图标
        send_btn = page.locator('.send-btn')
        send_btn.wait_for()
        send_label_visible = send_btn.locator('.send-label').count()
        sr_only_count = send_btn.locator('.sr-only').count()
        EVIDENCE['sendButton'] = {
            'hasVisibleSendLabel': send_label_visible > 0,
            'hasSrOnlyLabel': sr_only_count > 0,
            'iconClass': 'fa-paper-plane' in send_btn.evaluate("el => el.innerHTML"),
        }

        # ===== 2. 配置 mock 供应商（管理供应商 → 添加 → 自动获取模型 → 保存） =====
        page.click('.provider-switcher-trigger')
        page.click('.manage-link')
        page.wait_for_selector('.provider-manager .pm-list')
        page.click('.pm-list .btn-primary')  # 添加供应商
        page.wait_for_selector('.pm-form')
        inputs = page.locator('.pm-form .pm-input')
        inputs.nth(0).fill('MockChat')
        inputs.nth(1).fill('http://127.0.0.1:7799')
        inputs.nth(2).fill('sk-int1109')
        page.click('.pm-fetch-models')
        # 自动获取模型 → 表单出现 mock-model
        wait_for(
            lambda: page.locator('.pm-model-row input').first.input_value() == 'mock-model',
            label='自动获取模型 mock-model',
        )
        EVIDENCE['fetchModels'] = {
            'ok': True,
            'models': [page.locator('.pm-model-row input').nth(i).input_value() for i in range(page.locator('.pm-model-row').count())],
        }
        page.click('.pm-form-actions .btn-primary')  # 保存
        page.wait_for_selector('.pm-provider-row')
        # 关闭弹窗
        page.click('.modal-close')
        page.wait_for_selector('.provider-manager', state='detached')

        # ===== 3. 校验「配置即可对话」：自动选首个模型，发送钮可点 =====
        wait_for(
            lambda: page.locator('.trigger-model').count() > 0 and 'mock-model' in page.locator('.trigger-model').first.text_content(),
            label='自动选中 mock-model',
        )
        EVIDENCE['configReady'] = {
            'selectedModel': page.locator('.trigger-model').first.text_content(),
            'sendDisabled': page.locator('.send-btn').is_disabled(),
        }

        # ===== 4. 发送消息 → 捕获 /chat/completions =====
        page.fill('.ai-chat-textarea', '生成一份测试报告并说明关键指标')
        page.click('.send-btn')
        wait_for(
            lambda: any('/chat/completions' in c['url'] for c in captured),
            label='捕获 /chat/completions 请求',
        )
        wait_for(
            lambda: page.locator('.message-doc').count() > 0
            and page.locator('.message-doc').last.inner_text().strip() != '',
            label='assistant 回复渲染',
        )
        reply_text = page.locator('.message-doc').last.inner_text()
        EVIDENCE['conversation'] = {
            'userMessage': page.locator('.user-bubble').last.inner_text(),
            'assistantReply': reply_text[:200],
            'networkRequests': captured,
        }

        # ===== 5. 浅色整页截图 =====
        page.wait_for_timeout(800)
        page.screenshot(path=os.path.join(OUT, 'ai-chat_light.png'), full_page=False)

        # ===== 6. 深色：localStorage 主题 + reload =====
        page.evaluate("localStorage.setItem('iatp:theme:v1', 'dark')")
        page.goto(f'{BASE}/#/ai-chat', wait_until='networkidle')
        page.wait_for_selector('.ai-chat-page')
        wait_for(
            lambda: page.evaluate("document.documentElement.classList.contains('dark')"),
            label='dark class 挂载',
        )
        page.wait_for_selector('.ai-chat-message, .ai-chat-empty', timeout=15000)
        page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(OUT, 'ai-chat_dark.png'), full_page=False)

        # ===== 7. 每页 agent 浮窗（/dashboard 工作台能力条） =====
        page.evaluate("localStorage.setItem('iatp:theme:v1', 'light')")
        page.goto(f'{BASE}/#/dashboard', wait_until='networkidle')
        page.wait_for_selector('.dashboard-page, .authenticated-layout', timeout=15000)
        page.click('.agent-button[data-layout-btn]')
        page.wait_for_selector('.agent-workbench')
        wait_for(
            lambda: page.locator('.awb-page-capability').count() > 0,
            label='浮窗本页能力条渲染',
        )
        page.wait_for_timeout(500)
        capability_text = page.locator('.awb-page-capability-title').inner_text()
        prompts = page.locator('.awb-capability-prompt').all_inner_texts()
        EVIDENCE['perPageAgent_dashboard'] = {
            'capabilityTitle': capability_text,
            'quickPrompts': prompts,
        }
        page.screenshot(path=os.path.join(OUT, 'workbench_dashboard_light.png'), full_page=False)

        # 关闭浮窗 → 到 /testcases → 再开浮窗（能力条随路由变化 = 每页 agent 行为）
        page.click('.awb-action-btn[title="关闭"]')
        page.wait_for_selector('.agent-workbench', state='detached')
        page.goto(f'{BASE}/#/testcases', wait_until='networkidle')
        page.wait_for_selector('.authenticated-layout', timeout=15000)
        page.click('.agent-button[data-layout-btn]')
        page.wait_for_selector('.awb-page-capability')
        capability_text2 = page.locator('.awb-page-capability-title').inner_text()
        EVIDENCE['perPageAgent_testcases'] = {'capabilityTitle': capability_text2}
        page.screenshot(path=os.path.join(OUT, 'workbench_testcases_light.png'), full_page=False)

        browser.close()

    # ===== 8. Network 证据面板（DevTools Network 风格） =====
    with sync_playwright() as p2:
        browser2 = p2.chromium.launch(
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        )
        page2 = browser2.new_page(viewport={'width': 1200, 'height': 720})
        req = captured[-1] if captured else {}
        rows = ''
        for c in captured:
            req_body = (c.get('requestBody') or '')[:600]
            rows += (
                f"<tr><td>POST</td><td>{c['url']}</td><td>{c['status']}</td>"
                f"<td>fetch</td></tr>"
            )
        req_body_html = ''
        if req:
            req_body_html = (
                f"<h3>请求体（POST /chat/completions）</h3><pre>{req.get('requestBody','')}</pre>"
                f"<h3>响应体</h3><pre>{req.get('responseBody','')}</pre>"
            )
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', sans-serif; background: #1e1e1e; color: #d4d4d4; margin: 0; padding: 16px; }}
h2 {{ margin: 0 0 8px; font-size: 15px; color: #fff; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid #333; }}
th {{ color: #9cdcfe; font-weight: 600; }}
td {{ font-family: Consolas, monospace; }}
.url {{ color: #ce9178; word-break: break-all; }}
.status {{ color: #4ec9b0; }}
pre {{ background: #252526; padding: 10px; border-radius: 4px; font-size: 11px; white-space: pre-wrap; word-break: break-all; color: #d4d4d4; max-height: 220px; overflow: auto; }}
</style></head><body>
<h2>Network — 灵犀Agent 对话请求（/ai-chat → 用户自配 LLM 供应商直连）</h2>
<table>
<tr><th>Method</th><th>URL</th><th>Status</th><th>Type</th></tr>
{rows}
</table>
{req_body_html}
</body></html>"""
        net_html = os.path.join(OUT, 'network_panel.html')
        with open(net_html, 'w', encoding='utf-8') as f:
            f.write(html)
        page2.goto(f'file:///{net_html.replace(chr(92), "/")}', wait_until='networkidle')
        page2.screenshot(path=os.path.join(OUT, 'network_panel.png'), full_page=False)
        browser2.close()

    with open(os.path.join(OUT, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(EVIDENCE, f, ensure_ascii=False, indent=2)
    print(json.dumps(EVIDENCE, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
