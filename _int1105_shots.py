# -*- coding: utf-8 -*-
"""INT-1105 设备扫描回填 + 每API代理 截图与 Network 证据（Playwright）。

流程：
  1. /#/devices 浅色页截图
  2. 打开「添加测试设备」→ 扫描选择器出现 → 点选扫描设备回填（含 IP）→ 切远程连接显 IP → 截图
     → 填名称后保存，捕获 POST /test-devices 载荷（验证 ip 字段达后端）→ 清理
  3. 深色：同一模态窗截图
  4. API 页签「添加测试API」→ 代理字段 → 填代理类型+地址 → 截图
     → 保存捕获 POST /apis 载荷（验证 proxy_type/proxy_url）→ 清理
  5. 渲染 Network 载荷截图
"""
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5525'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1105_shots')
os.makedirs(OUT, exist_ok=True)

captured_posts = []  # [(url, method, post_data_json)]


def shot(page, name):
    page.screenshot(path=os.path.join(OUT, name), full_page=False)
    print('saved', name)


def wait_selector(page, sel, timeout=20000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def click_by_text(page, tag, text, timeout=8000):
    loc = page.locator(f'{tag}:has-text("{text}")').first
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if loc.is_visible():
                loc.click()
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def setup_net_listener(page):
    def on_request(req):
        try:
            if req.method in ('POST', 'PUT') and ('/test-devices' in req.url or '/apis' in req.url):
                body = req.post_data or ''
                try:
                    parsed = json.loads(body) if body else {}
                except Exception:
                    parsed = body
                captured_posts.append({'url': req.url, 'method': req.method, 'body': parsed})
        except Exception:
            pass
    page.on('request', on_request)


def render_network_screenshot():
    """把捕获的 POST 载荷渲染成 HTML 并截图（Network 证据）。"""
    html = [
        '<html><head><meta charset="utf-8"/><style>',
        'body{font-family:Consolas,monospace;background:#0f172a;color:#e2e8f0;padding:24px;}',
        'h2{color:#fbbf24;font-size:18px;} .req{margin:16px 0;}',
        '.url{color:#93c5fd;font-size:14px;} .method{color:#fbbf24;font-weight:700;}',
        'pre{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px;overflow:auto;',
        'font-size:13px;white-space:pre-wrap;word-break:break-all;color:#a7f3d0;}',
        '</style></head><body>',
        '<h2>INT-1105 Network 捕获（真实请求载荷）</h2>',
    ]
    if not captured_posts:
        html.append('<p style="color:#f87171">未捕获到 POST/PUT /test-devices 或 /apis 请求</p>')
    for i, cap in enumerate(captured_posts, 1):
        html.append(f'<div class="req"><span class="method">[{i}] {cap["method"]}</span> '
                    f'<span class="url">{cap["url"]}</span>')
        body = cap['body']
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False, indent=2)
        html.append(f'<pre>{body}</pre></div>')
    html.append('</body></html>')
    net_path = os.path.join(OUT, '_network_log.html')
    with open(net_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={'width': 1100, 'height': 900})
        pg.goto('file:///' + net_path.replace('\\', '/'))
        pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(OUT, 'int1105_network_requests.png'), full_page=True)
        print('saved int1105_network_requests.png')
        b.close()


def cleanup_devices(names):
    """通过后端 DELETE 清理测试创建的设备/API（接线测试 前缀）。"""
    import urllib.request
    BACKEND = 'http://localhost:5000/api/v1'
    for name in names:
        try:
            if name.startswith('接线测试-INT1105'):
                for path in ('/test-devices', '/apis'):
                    try:
                        req = urllib.request.Request(f'{BACKEND}{path}', method='GET')
                        with urllib.request.urlopen(req, timeout=5) as r:
                            items = json.loads(r.read())
                        coll = items.get('items', items) if isinstance(items, dict) else items
                        if not isinstance(coll, list):
                            coll = []
                        for it in coll:
                            if it.get('name') == name:
                                dreq = urllib.request.Request(f'{BACKEND}{path}/{it["id"]}', method='DELETE')
                                urllib.request.urlopen(dreq, timeout=5)
                                print('cleaned', path, it['id'], name)
                    except Exception as e:
                        print('cleanup skip', path, name, str(e)[:80])
        except Exception as e:
            print('cleanup outer', str(e)[:80])


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        setup_net_listener(page)
        created_names = []

        # ---- 1. 浅色设备页 ----
        page.goto(BASE + '/#/devices', wait_until='networkidle', timeout=30000)
        time.sleep(2)
        if wait_selector(page, '.device-view .card, .device-view .stats-grid'):
            shot(page, 'int1105_devices_light.png')

        # ---- 2. 测试设备添加模态窗：扫描选择器 + 回填 ----
        click_by_text(page, 'button', '添加测试设备', timeout=8000)
        if not wait_selector(page, '.crud-form-modal'):
            print('!! CRUDFormModal 未打开')
        else:
            if not wait_selector(page, '.device-selector-section'):
                print('!! DeviceSelector 未出现')
            else:
                time.sleep(1)
                # 点选扫描到的第一台设备（回填表单）
                if wait_selector(page, '.device-selector-section .device-item', timeout=15000):
                    page.locator('.device-selector-section .device-item').first.click()
                    time.sleep(0.6)
                    # 切远程连接使 IP 字段可见（扫描回填的 IP 显示在 IP 输入框）
                    try:
                        radio = page.locator('input[type="radio"][value="remote"]').first
                        if radio.is_visible():
                            radio.click(force=True)
                            time.sleep(0.3)
                    except Exception:
                        print('!! remote radio not found')
                    shot(page, 'int1105_test_modal_scan_fill_light.png')

                    # 覆盖名称为测试数据，保存并捕获 POST /test-devices（验证 ip 字段）
                    name_val = f'接线测试-INT1105-扫描回填-{int(time.time())}'
                    name_input = page.locator('.crud-form-modal input[type="text"]').first
                    try:
                        name_input.fill(name_val)
                        created_names.append(name_val)
                    except Exception as e:
                        print('!! fill name failed', str(e)[:60])
                    click_by_text(page, 'button', '添加', timeout=8000)
                    time.sleep(1.5)
                else:
                    print('!! 扫描设备列表为空')

        # ---- 3. 深色：打开测试添加模态窗截图 ----
        page.goto(BASE + '/#/devices', wait_until='networkidle', timeout=30000)
        time.sleep(1.5)
        page.evaluate("document.documentElement.classList.add('dark')")
        time.sleep(0.5)
        click_by_text(page, 'button', '添加测试设备', timeout=8000)
        if wait_selector(page, '.device-selector-section .device-item', timeout=15000):
            time.sleep(0.8)
            shot(page, 'int1105_test_modal_dark.png')
        # 关闭模态（ESC）
        page.keyboard.press('Escape')
        time.sleep(0.5)

        # ---- 4. API 页签：代理字段 ----
        page.evaluate("document.documentElement.classList.remove('dark')")
        time.sleep(0.3)
        if click_by_text(page, 'button', '测试API管理', timeout=8000):
            time.sleep(1.2)
        if click_by_text(page, 'button', '添加测试API', timeout=8000):
            if wait_selector(page, '.crud-form-modal', timeout=15000):
                # 填代理字段：名称 + 代理类型 select + 代理地址
                api_name = f'接线测试-INT1105-代理-{int(time.time())}'
                created_names.append(api_name)
                name_input = page.locator('.crud-form-modal input[type="text"]').first
                try:
                    name_input.fill(api_name)
                except Exception as e:
                    print('!! api name fill failed', str(e)[:60])
                # 代理类型 select（按 placeholder 无；直接选 http）
                proxy_select = page.locator('.crud-form-modal select').nth(0)
                try:
                    opts = proxy_select.locator('option')
                    for i in range(opts.count()):
                        v = opts.nth(i).get_attribute('value')
                        if v == 'http':
                            proxy_select.select_option('http')
                            break
                except Exception as e:
                    print('!! proxy select failed', str(e)[:80])
                # 代理地址（找 placeholder=user:pass@host:port 的输入框）
                proxy_url_input = page.locator('input[placeholder="user:pass@host:port"]').first
                try:
                    proxy_url_input.fill('user:pass@127.0.0.1:7890')
                except Exception as e:
                    print('!! proxy url fill failed', str(e)[:80])
                time.sleep(0.5)
                shot(page, 'int1105_api_modal_proxy_light.png')
                # 保存（捕获 POST /apis）
                click_by_text(page, 'button', '添加', timeout=8000)
                time.sleep(1.5)

        page.wait_for_timeout(500)
        browser.close()

    render_network_screenshot()

    # 清理测试数据
    cleanup_devices(created_names)


if __name__ == '__main__':
    main()
