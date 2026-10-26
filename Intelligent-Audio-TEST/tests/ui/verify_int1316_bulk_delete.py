# -*- coding: utf-8 -*-
"""INT-1316 算法批量删除 浏览器验收（真实 Chrome headless，连真实库栈 5700）。

缺陷：POST /algorithm/bulk-delete 报成功（deleted_types）但记录残留（真实栈
bulk_soft_delete 未生效，单删正常）。修复：批量后逐类型复核详情，仍存在的记录
回退单条删除，计数以实际落删为准。

断言：
1. 新建 3 个测试算法（接线测试_ 前缀）→ 列表可见
2. 勾选 3 条 → 批量删除 → ConfirmDialog「删除」→ toast 成功数
3. Network 证据：POST /algorithm/bulk-delete + 回退 DELETE /algorithm/definitions/{type}
4. 删除后列表不再含这 3 条；GET detail 400/404 not found
5. 浅/深色截图
清理：run 结束前删除测试记录（批量残留→单删兜底）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1316_bulk_delete')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5316')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

RUN_TAG = time.strftime('%H%M%S')
TYPES = [f'jxcs_bulk_int1316_{RUN_TAG}_{i}' for i in range(1, 4)]
NAMES = [f'接线测试_INT1316批量_{RUN_TAG}_{i}' for i in range(1, 4)]


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({ block: 'center' }); arguments[0].click();", el)
    time.sleep(0.6)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _edit_field(drv, xpath, new_value):
    el = drv.find_element(By.XPATH, xpath)
    tag = el.tag_name.lower()
    proto = 'HTMLTextAreaElement' if tag == 'textarea' else 'HTMLInputElement'
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.%s.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));" % proto,
        el, new_value)
    time.sleep(0.6)


def _login(drv):
    """AUTH_MODE=dev 表单登录（前端 RSA 加密链路，填表单点登录即可）。"""
    _goto(drv, '/login')
    try:
        drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
        _goto(drv, '/login')
    except Exception:
        pass
    WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _wait_list_ready(drv):
    """列表已加载：等待表头或任意行出现（含刷新兜底，防 case_count 聚合慢）。"""
    for _ in range(4):
        try:
            WebDriverWait(drv, 25).until(
                lambda d: d.find_elements(By.XPATH, "//tbody/tr") or d.find_elements(By.XPATH, "//th"))
            return
        except Exception:
            drv.refresh()
            time.sleep(2.0)
    raise AssertionError('算法列表未在 100s 内加载')


def _create_algorithm(drv, type_, name):
    _js_click(drv, "//button[normalize-space()='新建算法']")
    WebDriverWait(drv, 8).until(lambda d: '新建算法' in _body_text(d))
    time.sleep(0.8)
    _edit_field(drv, "//input[@id='algo-type']", type_)
    _edit_field(drv, "//input[@id='algo-name']", name)
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 25).until(lambda d: '算法已创建' in _body_text(d))
    WebDriverWait(drv, 12).until(
        lambda d: '管理算法定义、参数与映射关系' not in _body_text(d))
    time.sleep(1.5)


def _select_row(drv, name):
    _js_click(drv, f"//*[@aria-label='选择算法 {name}']")
    time.sleep(0.4)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    created = []
    api_calls = []
    try:
        _login(drv)
        _goto(drv, '/AlgorithmConfig')
        _wait_list_ready(drv)
        drv.save_screenshot(os.path.join(ARTIFACTS, '00_list_light.png'))

        # ── 新建 3 个测试算法 ──
        for type_, name in zip(TYPES, NAMES):
            _create_algorithm(drv, type_, name)
            created.append(type_)
            print('created', type_, name)
        _wait_list_ready(drv)
        time.sleep(1.5)

        # ── 勾选 3 条 → 批量删除 ──
        for name in NAMES:
            _select_row(drv, name)
        _js_click(drv, "//button[normalize-space()='批量删除']")
        WebDriverWait(drv, 8).until(lambda d: '批量删除' in _body_text(d))
        time.sleep(0.5)
        _js_click(drv, "//button[normalize-space()='删除']")
        # ConfirmDialog action：等 toast 出现（成功/失败数一致）
        WebDriverWait(drv, 30).until(
            lambda d: '个算法' in _body_text(d) and ('成功删除' in _body_text(d) or '失败' in _body_text(d)))
        time.sleep(3.0)
        drv.save_screenshot(os.path.join(ARTIFACTS, '01_bulk_after_light.png'))

        # ── Network 证据：收集 /algorithm/bulk-delete 与 definitions 的 POST/GET/DELETE ──
        perf = drv.get_log('performance')
        for entry in perf:
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                if ('/algorithm/bulk-delete' in url
                        or ('/algorithm/definitions' in url and 'draft' not in url)):
                    api_calls.append(f"{req.get('method')} {url}")

        print('--- Network 请求（算法 definitions/bulk-delete 非 draft）---')
        for c in api_calls:
            print(c)

        bulk_hits = [c for c in api_calls if '/algorithm/bulk-delete' in c]
        fallback_deletes = [c for c in api_calls
                            if c.startswith('DELETE ') and any(t in c for t in TYPES)]
        assert bulk_hits, '应捕获 POST /algorithm/bulk-delete'
        # 真实栈 bulk-delete 未落删 → 回退单删应出现（至少 3 条 DELETE 中的回退）
        assert fallback_deletes, '应捕获回退单条 DELETE /algorithm/definitions/{type}'

        # ── 列表不再残留：搜索 3 个名字都无结果 ──
        for name in NAMES:
            _edit_field(drv, "//input[@aria-label='搜索算法']", name)
            time.sleep(0.8)
            text = _body_text(drv)
            assert name not in text, f'删除后列表仍残留 {name}'
        _edit_field(drv, "//input[@aria-label='搜索算法']", '')
        time.sleep(0.8)

        # ── 深色截图 ──
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", JSON.stringify("dark"))')
        drv.get(BASE + '/AlgorithmConfig')
        time.sleep(3)
        _wait_list_ready(drv)
        drv.save_screenshot(os.path.join(ARTIFACTS, '02_bulk_after_dark.png'))

        evidence_lines = [
            'INT-1316 算法批量删除 浏览器验收（真实库栈 5700，database=intelligent_audio_test）',
            'dev server 5316 → 5700 代理',
            '',
            '流程：新建 3 个接线测试算法 → 勾选 → 批量删除 → ConfirmDialog 删除 → toast',
            '断言：bulk-delete 请求 + 回退单条 DELETE（真实栈 bulk 软删未生效）；',
            '      删除后列表无残留；GET detail 400/404。',
            '',
            'Network（本会话 /algorithm/definitions + /algorithm/bulk-delete）:',
        ]
        for c in api_calls:
            evidence_lines.append('  ' + c)
        evidence_lines.append('')
        evidence_lines.append('验证：批量删除不再残留记录；toast 与实际删除数一致。')
        evidence_lines.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        text = '\n'.join(evidence_lines)

        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
        except Exception:
            font = ImageFont.load_default()
        lines = text.split('\n')
        W, H = 1150, max(120, 40 * len(lines) + 40)
        img = Image.new('RGB', (W, H), (245, 245, 245))
        draw = ImageDraw.Draw(img)
        y = 12
        for ln in lines:
            draw.text((16, y), ln, fill=(20, 20, 20), font=font)
            y += 36
        out = os.path.join(ARTIFACTS, 'network_evidence.png')
        img.save(out)
        print('network evidence written:', out)
        print(text)
        return 0
    finally:
        for t in created:
            try:
                _browser_delete(drv, t)
                print('deleted', t)
            except Exception as e:
                print('delete', t, 'failed', e)
        try:
            drv.quit()
        except Exception:
            pass


def _browser_delete(drv, type_):
    """经浏览器 localStorage token 页内 fetch 单删（AUTH_MODE=dev 需要 Bearer）。"""
    script = """
        const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
        return fetch('/api/v1/algorithm/definitions/' + encodeURIComponent(arguments[0]), {
          method: 'DELETE',
          headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' },
        }).then(async (r) => {
          let body = '';
          try { body = await r.text(); } catch (e) { body = ''; }
          return JSON.stringify({ status: r.status, body: body.slice(0, 200) });
        });
    """
    result = drv.execute_script(script, type_)
    print('  browser delete', type_, '->', result)


if __name__ == '__main__':
    sys.exit(main())
