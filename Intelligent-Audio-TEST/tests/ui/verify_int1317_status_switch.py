# -*- coding: utf-8 -*-
"""INT-1317 新建算法状态开关 浏览器验收（真实 Chrome headless，连 docker 15000 真实库后端）。

验证修复：新建算法选「下线」→ 发布后列表徽章显示「下线」（修复前恒显「上线」）。
后端 create 落 draft（INT-1253 证据），前端 workaround：POST create 后如返回 status 与
表单所选不一致，立即补一次 PUT 应用所选 status。断言：
1. 新建表单状态开关切「下线」→ 表单显示「下线」
2. 发布 → toast「算法已创建」→ 列表新行徽章「下线」（修复前「上线」）
3. Network 证据：POST /algorithm/definitions + 补 PUT /algorithm/definitions/{type}
4. GET detail status=offline；再建一个「上线」→ detail status=online
5. 浅/深色截图
清理：删除两个测试算法。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1317_status_switch')

BASE = 'http://127.0.0.1:5330'
API = 'http://127.0.0.1:15000/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

RUN_TAG = time.strftime('%H%M%S')
OFF_TYPE = f'jxcs_off_int1317_{RUN_TAG}'
OFF_NAME = f'接线测试_INT1317_下线_{RUN_TAG}'
ON_TYPE = f'jxcs_on_int1317_{RUN_TAG}'
ON_NAME = f'接线测试_INT1317_上线_{RUN_TAG}'


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
    drv.set_page_load_timeout(45)
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
    WebDriverWait(drv, 15).until(
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


def _wait_list_ready(drv):
    """列表已加载：等待 voice_llm 行操作钮出现（含刷新兜底，总时长 ~70s 防后端聚合慢）。"""
    def rows(d):
        return d.find_elements(By.XPATH, "//button[@aria-label='算法 小艺语音大模型 的操作']")
    for _ in range(3):
        try:
            WebDriverWait(drv, 30).until(lambda d: rows(d))
            return
        except Exception:
            drv.refresh()
            time.sleep(2.0)
    raise AssertionError('列表未在 70s 内加载出 voice_llm 行')


def _search(drv, keyword):
    _edit_field(drv, "//input[@aria-label='搜索算法']", keyword)
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='算法 {keyword} 的操作']"))


def _clear_search(drv):
    try:
        _edit_field(drv, "//input[@aria-label='搜索算法']", '')
        time.sleep(0.8)
    except Exception:
        pass


def _api_get(path):
    with urllib.request.urlopen(API + path, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _api_delete(type_):
    req = urllib.request.Request(
        f'{API}/algorithm/definitions/{urllib.parse.quote(type_)}', method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        if e.code == 400 and ('不存在' in body or 'not found' in body.lower() or '未知' in body):
            return {'already_absent': True}
        raise


def _create_in_browser(drv, type_, name, want_offline):
    """在已加载的列表上新建算法 → 状态开关切目标 → 发布 → 搜索新行返回徽章文本。"""
    _js_click(drv, "//button[normalize-space()='新建算法']")
    WebDriverWait(drv, 8).until(lambda d: '新建算法' in _body_text(d))
    time.sleep(0.8)
    _edit_field(drv, "//input[@id='algo-type']", type_)
    _edit_field(drv, "//input[@id='algo-name']", name)
    if want_offline:
        _js_click(drv, "//*[@id='algo-status']")
        time.sleep(0.5)
        assert '下线' in _body_text(drv), f'切下线后表单应显示下线：{_body_text(drv)[:300]}'
    else:
        assert '上线' in _body_text(drv), f'默认应显示上线：{_body_text(drv)[:300]}'
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 20).until(lambda d: '算法已创建' in _body_text(d))
    # Sheet 关闭 + 列表刷新
    WebDriverWait(drv, 12).until(
        lambda d: '管理算法定义、参数与映射关系' not in _body_text(d))
    time.sleep(1.5)
    _clear_search(drv)
    _search(drv, name)
    row = drv.find_element(By.XPATH, f"//tr[contains(., '{name}')]")
    return row.text


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    api_calls = []
    created = []
    try:
        # 会话引导（AUTH_MODE=off → dev_user 放行）+ 列表就绪
        _goto(drv, '/AlgorithmConfig')
        _wait_list_ready(drv)
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, '00_list_light.png'))

        # ── 下线路径 ──
        row_text = _create_in_browser(drv, OFF_TYPE, OFF_NAME, want_offline=True)
        created += [OFF_TYPE]
        print('--- 下线 新建后列表行文本 ---')
        print(row_text)
        assert '下线' in row_text, f'选下线发布后列表徽章应显示「下线」：{row_text}'
        assert '上线' not in row_text, f'选下线发布后列表徽章不应显示「上线」：{row_text}'
        detail = _api_get(f'/algorithm/definitions/{urllib.parse.quote(OFF_TYPE)}')
        assert detail['data']['status'] == 'offline', f'GET detail status 应为 offline：{detail}'
        print('GET detail status =', detail['data']['status'])
        drv.save_screenshot(os.path.join(ARTIFACTS, '01_offline_badge.png'))
        _clear_search(drv)

        # ── 上线路径 ──
        row_text_on = _create_in_browser(drv, ON_TYPE, ON_NAME, want_offline=False)
        created += [ON_TYPE]
        print('--- 上线 新建后列表行文本 ---')
        print(row_text_on)
        assert '上线' in row_text_on, f'选上线发布后列表徽章应显示「上线」：{row_text_on}'
        detail_on = _api_get(f'/algorithm/definitions/{urllib.parse.quote(ON_TYPE)}')
        assert detail_on['data']['status'] == 'online', f'GET detail status 应为 online：{detail_on}'
        print('GET detail status =', detail_on['data']['status'])
        drv.save_screenshot(os.path.join(ARTIFACTS, '02_online_badge.png'))

        # ── Network 证据：收集本会话 /algorithm/definitions 非 draft 请求 ──
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
                if '/algorithm/definitions' in url and 'draft' not in url:
                    api_calls.append(f"{req.get('method')} {url}")
        print('--- Network 请求（/algorithm/definitions 非 draft）---')
        for c in api_calls:
            print(c)
        post_hits = [c for c in api_calls if c.startswith('POST ') and '/algorithm/definitions' in c]
        put_hits = [c for c in api_calls if c.startswith('PUT ') and OFF_TYPE in c]
        assert post_hits, '应捕获 POST /algorithm/definitions'
        assert put_hits, f'选下线发布后应捕获补 PUT /algorithm/definitions/{OFF_TYPE}'

        # ── 深色截图 ──
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", JSON.stringify("dark"))')
        drv.get(BASE + '/AlgorithmConfig')
        time.sleep(3)
        _wait_list_ready(drv)
        _search(drv, OFF_NAME)
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, '03_offline_dark.png'))

        evidence_lines = [
            'INT-1317 新建算法状态开关 浏览器验收（docker 15000 真实库后端，dev server 5330）',
            '',
            '下线路径：新建 status=offline → 发布 toast「算法已创建」→ 列表徽章「下线」',
            f'  GET detail {OFF_TYPE} → status=offline',
            '上线路径：新建 status=online → 发布 → 列表徽章「上线」',
            f'  GET detail {ON_TYPE} → status=online',
            '',
            'Network（本会话 /algorithm/definitions）:',
        ]
        for c in api_calls:
            evidence_lines.append('  ' + c)
        evidence_lines.append('')
        evidence_lines.append('验证：选下线不再显示「上线」；workaround POST→PUT 已生效。')
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
                _api_delete(t)
                print('deleted', t)
            except Exception as e:
                print('delete', t, 'failed', e)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
