# -*- coding: utf-8 -*-
"""INT-1319 浏览器实测（连真实库栈 5700，dev server :5399）。

验证：
- P3-1：算法列表首屏先渲染（definitions 先到，骨架态不再等逐算法聚合 8-15s）；
  关联用例列初始 —，经异步 /testcases 聚合补齐后有值。
- P3-2：create 态填 type + 保存草稿 → PUT /algorithm/definitions/draft 200 +
  footer「上次保存 HH:mm:ss」；create 态 type 留空 → 保存草稿按钮 disabled（不发 400）。

证据：light/dark 截图 + Network 请求/响应 + 文案断言。只写本 run 自建的
「接线测试_int1319_draft」草稿快照，验收后清理该行。
"""
import argparse
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1319')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
BASE = 'http://localhost:5399'
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
TEST_TYPE = 'int1319_draft_test'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def net_reqs(drv, targets):
    """从 performance log 提取目标请求的 (method, url, status, requestId, time)。"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            inner = msg.get('message') or {}
            method = inner.get('method') or ''
            params = inner.get('params') or {}
        except Exception:
            continue
        url = ''
        req_method = ''
        rid = None
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            req_method = req.get('method') or ''
            rid = params.get('requestId')
        elif method == 'Network.responseReceived':
            resp = params.get('response') or {}
            url = resp.get('url') or ''
            rid = params.get('requestId')
            req_method = 'GET'
        if not url or not any(t in url for t in targets):
            continue
        status = None
        if method == 'Network.responseReceived':
            status = (params.get('response') or {}).get('status')
        out.append({'method': req_method, 'url': url, 'status': status,
                    'rid': rid, 'event': method})
    return out


def get_body(drv, rid):
    try:
        r = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
        if r.get('base64Encoded'):
            import base64
            return base64.b64decode(r.get('body', '')).decode('utf-8', 'replace')
        return r.get('body', '')
    except Exception:
        return '(unavailable)'


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    # 若已自动重定向（dev 模式）则跳过
    if '/login' not in drv.current_url:
        return
    drv.find_element(By.ID, 'username').clear()
    drv.find_element(By.ID, 'username').send_keys(USERNAME)
    drv.find_element(By.ID, 'password').clear()
    drv.find_element(By.ID, 'password').send_keys(PASSWORD)
    for btn in drv.find_elements(By.XPATH, "//button[contains(., '登')]"):
        if '录' in btn.text:
            js_click(drv, btn)
            break
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url,
        message='login did not redirect',
    )
    time.sleep(2)


def wait_table(drv, timeout=60):
    """等待算法表格 tbody 出现首行，返回耗时（秒）。"""
    t0 = time.time()
    wait = WebDriverWait(drv, timeout)
    wait.until(lambda d: len(d.find_elements(By.XPATH, '//table/tbody/tr')) > 0,
               message='algorithm table rows did not render')
    return time.time() - t0


def cell_value(drv, row_idx, col_idx):
    cells = drv.find_elements(By.XPATH, f'//table/tbody/tr[{row_idx}]/td')
    if len(cells) <= col_idx:
        return ''
    return (cells[col_idx].text or '').strip()


def open_edit_sheet(drv, alg_name):
    # 行操作钮 aria-label=算法 {name} 的操作
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='算法 {alg_name} 的操作']")
    js_click(drv, btn)
    time.sleep(0.5)
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem' and contains(., '编辑')]")
    if not items:
        items = drv.find_elements(By.XPATH, "//li[contains(., '编辑')]")
    js_click(drv, items[-1])
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.ID, 'algo-name')) > 0,
        message='mutate sheet did not open')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    evidence = []
    try:
        login(drv)

        # ---------- P3-1：列表首屏 + 关联用例异步补齐 ----------
        drain_perf(drv)
        nav_t0 = time.time()
        drv.get(base + '/AlgorithmConfig')
        wait = WebDriverWait(drv, 60)
        wait.until(lambda d: '/AlgorithmConfig' in d.current_url or '/403' not in d.current_url)
        list_sec = wait_table(drv, timeout=60)
        evidence.append(f'P3-1 列表首屏渲染耗时: {list_sec:.2f}s (nav+load total {time.time()-nav_t0:.2f}s)')

        # 用 performance log 的事件时间戳算 definitions→渲染 间隔（首屏是否等聚合）
        # 一次读完 log（get_log 会消费缓冲区），同时做时间戳与请求过滤
        perf_entries = drv.get_log('performance')
        t_render_ms = int(time.time() * 1000) - int(list_sec * 1000)
        defs_resp_ms = None
        tc_req_ms = None
        net_log = []
        for entry in perf_entries:
            try:
                msg = json.loads(entry.get('message', '') or '')
                inner = msg.get('message') or {}
                method = inner.get('method') or ''
                params = inner.get('params') or {}
                ts = inner.get('timestamp') or 0
            except Exception:
                continue
            url = ''
            req_method = ''
            rid = None
            status = None
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                req_method = req.get('method') or ''
                rid = params.get('requestId')
                if '/testcases' in url and tc_req_ms is None:
                    tc_req_ms = ts
            elif method == 'Network.responseReceived':
                resp = params.get('response') or {}
                url = resp.get('url') or ''
                rid = params.get('requestId')
                req_method = 'GET'
                status = resp.get('status')
                if '/algorithm/definitions' in url and defs_resp_ms is None:
                    defs_resp_ms = ts
            if url and ('/algorithm/definitions' in url or '/testcases' in url):
                net_log.append({'method': req_method, 'url': url.split('?')[0], 'status': status})
        if defs_resp_ms:
            gap = (t_render_ms - defs_resp_ms) / 1000.0
            evidence.append(f'P3-1 definitions 响应→表格渲染 间隔: {gap:.2f}s（<1s = 首屏不等待聚合）')
        else:
            evidence.append('P3-1 未捕获 definitions 响应时间戳')
        if tc_req_ms and defs_resp_ms:
            evidence.append(f'P3-1 testcases(聚合)请求 晚于 definitions 响应: {(tc_req_ms-defs_resp_ms)/1000.0:.2f}s（异步补齐）')
        evidence.append('Network: ' + json.dumps(net_log, ensure_ascii=False))

        # 关联用例列：立即读首行第 7 列，再等数值出现（聚合若快则初始即数值）
        first_type = ''
        cell_start = ''
        for _ in range(60):
            rows = drv.find_elements(By.XPATH, '//table/tbody/tr')
            if rows:
                first_type = cell_value(drv, 1, 2)  # 算法类型列
                cell_start = cell_value(drv, 1, 6)  # 关联用例列
                break
            time.sleep(0.5)
        backfill_sec = 0.0
        t_b = time.time()
        for _ in range(60):
            v = cell_value(drv, 1, 6)
            if v and v not in ('—', ''):
                backfill_sec = time.time() - t_b
                evidence.append(f'P3-1 关联用例列: 初始「{cell_start}」→ 补齐「{v}」(聚合 {backfill_sec:.2f}s)')
                break
            time.sleep(0.5)
        else:
            evidence.append(f'P3-1 关联用例列 60s 未补齐（初始「{cell_start}」）')

        # 表格截图（浅色）
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p3_1_list_light.png'))
        evidence.append('截图: p3_1_list_light.png')

        # ---------- 深色截图 ----------
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get('about:blank')
        time.sleep(1)
        drv.get(base + '/AlgorithmConfig')
        wait_table(drv, timeout=60)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p3_1_list_dark.png'))
        evidence.append('截图: p3_1_list_dark.png')

        # ---------- P3-2：create 态 草稿保存成功 ----------
        # 回到浅色（避免影响后续断言截图）
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        drv.get('about:blank')
        time.sleep(1)
        drv.get(base + '/AlgorithmConfig')
        wait_table(drv, timeout=60)

        # 打开新建 Sheet
        for btn in drv.find_elements(By.XPATH, "//button[contains(., '新建算法')]"):
            js_click(drv, btn)
            break
        WebDriverWait(drv, 10).until(lambda d: len(d.find_elements(By.ID, 'algo-type')) > 0)
        time.sleep(0.5)

        # 断言：type 留空时「保存草稿」disabled（P3-2 空 type 守卫，不再发 400）
        empty_disabled = False
        for btn in drv.find_elements(By.XPATH, "//button[contains(., '保存草稿')]"):
            if '保存草稿' in btn.text:
                empty_disabled = bool(btn.get_attribute('disabled'))
                break
        evidence.append(f'P3-2 新建态 type 留空 → 保存草稿按钮 disabled: {empty_disabled}')
        if not empty_disabled:
            evidence.append('WARN: type 留空时保存草稿未 disabled（守卫失效）')

        # 填 type + name → 保存草稿 → 200 + footer 时间戳
        type_input = drv.find_element(By.ID, 'algo-type')
        js_click(drv, type_input)
        type_input.send_keys(TEST_TYPE)
        name_input = drv.find_element(By.ID, 'algo-name')
        js_click(drv, name_input)
        name_input.send_keys('接线测试_INT1319 草稿验证')
        time.sleep(0.8)
        drain_perf(drv)
        for btn in drv.find_elements(By.XPATH, "//button[contains(., '保存草稿')]"):
            if '保存草稿' in btn.text:
                js_click(drv, btn)
                break
        # 等 footer「上次保存 HH:mm:ss」
        footer_text = ''
        for _ in range(30):
            body = drv.execute_script('return document.body.textContent || ""')
            if '上次保存' in body:
                # 取 sheet footer 区域文本
                footer_text = body
                break
            time.sleep(0.5)
        evidence.append(f'P3-2 footer 出现「上次保存」: {bool(footer_text)}')
        draft_net = net_reqs(drv, ['/algorithm/definitions/draft'])
        draft_resp = [n for n in draft_net if n['event'] == 'Network.responseReceived']
        draft_status = None
        draft_body = ''
        if draft_resp:
            draft_status = draft_resp[-1]['status']
            draft_body = get_body(drv, draft_resp[-1]['rid'])
        evidence.append(f'P3-2 PUT /algorithm/definitions/draft → {draft_status}')
        evidence.append(f'P3-2 draft 响应: {draft_body[:200]}')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p3_2_draft_saved.png'))
        evidence.append('截图: p3_2_draft_saved.png')

        # ---------- 结果汇总 ----------
        ok = (
            (list_sec < 5.0 or any('间隔: ' in e and 's（<1s' in e and float(e.split('间隔: ')[1].split('s')[0]) < 1.0 for e in evidence))
            and any('→ 补齐' in e for e in evidence)
            and empty_disabled
            and draft_status == 200
            and bool(footer_text)
        )
        evidence.append(f'RESULT: {"PASS" if ok else "FAIL"}')

    finally:
        try:
            drv.quit()
        except Exception:
            pass

    text = '\n'.join(evidence)
    print(text)
    # 渲染证据 PNG（纯 ASCII）
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    lines = text.split('\n')
    W, H = 1300, max(160, 34 * len(lines) + 60)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 14
    for ln in lines:
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 30
    out = os.path.join(ARTIFACTS, 'evidence.png')
    img.save(out)
    print('evidence written:', out)


if __name__ == '__main__':
    sys.exit(main())
