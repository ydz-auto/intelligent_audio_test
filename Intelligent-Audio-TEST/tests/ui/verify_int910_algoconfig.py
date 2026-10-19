# -*- coding: utf-8 -*-
"""INT-910 算法配置页真实数据走查（新Vue wiring/ux-vue + 常驻 5000 后端，AUTH_MODE=off）。

验收清单（INT-910）：
1. 算法配置真实数据：INT-901（N4 gRPC 起）done 后 Network `/algorithm/*` 200，算法列表真实渲染
2. 参数配置 + 自动保存真实接口（Vue 版为 blur 防抖自动保存，POST/PUT /algorithm/params）
3. gRPC 未起时友好错误态（INT-899 修复生效），无原始 <_InactiveRpcError...> toast
4. 加载态 / 空态 / 错误态正常
5. 浅色 + 深色 + Network 截图

后端数据源：GET /api/v1/algorithm/definitions → voice_llm「小艺语音大模型」
(device_params 7 / api_params 3 / case_params 0 / reference_params 5)。

写操作（自动保存）用探针算法 int910_probe_*：API 建探针 → 打开编辑 → 参数页签添加参数 →
blur 自动保存 POST /algorithm/params → 后端确认 → 清理参数与探针（测试数据卫生）。

错误态用 CDP Network.setBlockedURLs 阻断 /algorithm/*（模拟 gRPC 未起），断言友好文案
出现且页面无原始 InactiveRpcError 文本；解除阻断后重试恢复。
"""
import json
import os
import re
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('VUE_DEV_BASE', 'http://127.0.0.1:5640')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int910_algoconfig')

PROBE_TYPE = None
JS_ERRORS = []


def _setup_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
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
    try:
        drv.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass
    # Vite dev 模块图占满默认 250 条 resource timing 缓冲 → API fetch 条目被丢弃；
    # 注入扩缓冲后整页重载（INT-909 实证）。
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                        {'source': 'performance.setResourceTimingBufferSize(4000);'})
    return drv


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _drain_console(drv, ignore_net=False):
    global JS_ERRORS
    try:
        for entry in drv.get_log('browser'):
            msg = entry.get('message', '')
            if 'Failed to load resource' in msg and 'Uncaught' not in msg:
                continue
            if entry.get('level') == 'SEVERE':
                JS_ERRORS.append(msg)
    except Exception:
        pass


def _goto(drv, path, wait=1.5):
    # 新 Vue 前端 hash 路由：#/AlgorithmConfig
    drv.get(BASE + '/#' + path)
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)
    _drain_console(drv)


def _shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path + '.png')
    with open(path + '.html', 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    print('shot:', path + '.png')


def _wait_text(drv, text, timeout=12):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(d))


def _net(drv, url_sub):
    """从 performance log 提取与 url_sub 匹配的请求；返回 [(method, url, status, body_json)]。"""
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = entry.get('message', '')
            try:
                data = json.loads(msg)
            except Exception:
                continue
            inner = data.get('message', data)
            if not isinstance(inner, dict):
                continue
            method_name = inner.get('method', '')
            if 'Network.' not in method_name:
                continue
            params = inner.get('params', {}) or {}
            url = ''
            method = ''
            status = None
            body = None
            req_id = params.get('requestId')
            if method_name == 'Network.requestWillBeSent':
                rq = params.get('request', {}) or {}
                url = rq.get('url', '')
                method = rq.get('method', '')
            elif method_name == 'Network.responseReceived':
                rs = params.get('response', {}) or {}
                url = rs.get('url', '')
                method = (rs.get('requestHeaders', {}) or {}).get(':method', '')
                status = rs.get('status')
            if url_sub not in url:
                continue
            if req_id:
                try:
                    r = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                    body = r.get('body')
                except Exception:
                    pass
            out.append((method or '?', url, status, body))
    except Exception:
        pass
    seen, dedup = set(), []
    for m, u, s, b in out:
        key = (m, u, s, (b[:200] if b else ''))
        if key in seen:
            continue
        seen.add(key)
        dedup.append((m, u, s, b))
    return dedup


def _net_req_bodies(drv, url_sub):
    """从 performance log 提取与 url_sub 匹配的请求体（Network.requestWillBeSent postData）。

    返回 [(method, url, post_data)]；用于断言自动保存请求体 wire 契约
    （param_type_source / direction，INT-910 P2-1）。
    """
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = entry.get('message', '')
            try:
                data = json.loads(msg)
            except Exception:
                continue
            inner = data.get('message', data)
            if not isinstance(inner, dict):
                continue
            if inner.get('method', '') != 'Network.requestWillBeSent':
                continue
            params = inner.get('params', {}) or {}
            rq = params.get('request', {}) or {}
            url = rq.get('url', '')
            method = rq.get('method', '')
            if url_sub not in url:
                continue
            post = rq.get('postData')
            out.append((method or '?', url, post))
    except Exception:
        pass
    seen, dedup = set(), []
    for m, u, b in out:
        key = (m, u, (b[:300] if b else ''))
        if key in seen:
            continue
        seen.add(key)
        dedup.append((m, u, b))
    return dedup


def _api(method, path, body=None):
    """小工具：直接调用后端 API（无鉴权，AUTH_MODE=off）。"""
    req = urllib.request.Request(f'{API}/api/v1{path}', method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            try:
                return json.loads(raw)
            except Exception:
                return raw
    except urllib.error.HTTPError as e:
        return {'__http_error__': e.code, 'body': e.read().decode()[:500]}


def _api_definitions():
    d = _api('GET', '/algorithm/definitions')
    return d.get('data', d) if isinstance(d, dict) else d


def _wait_rows(drv, n, timeout=15):
    WebDriverWait(drv, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR,
                                      '.algorithm-config-page .data-table tbody tr')) == n)


def _row_by_type(drv, algo_type):
    for tr in drv.find_elements(By.CSS_SELECTOR, '.algorithm-config-page .data-table tbody tr'):
        cells = tr.find_elements(By.CSS_SELECTOR, 'td')
        if cells and algo_type in (cells[0].text or ''):
            return tr
    return None


def _open_edit(drv, algo_type):
    """找到算法行并点「编辑」打开模态窗。"""
    row = WebDriverWait(drv, 15).until(lambda d: _row_by_type(d, algo_type))
    btns = row.find_elements(By.CSS_SELECTOR, '.table-actions button')
    for b in btns:
        if '编辑' in (b.text or ''):
            drv.execute_script('arguments[0].click();', b)
            break
    else:
        raise AssertionError(f'算法 {algo_type} 行未见编辑按钮')
    WebDriverWait(drv, 12).until(
        lambda d: any('编辑算法' in (t.text or '') for t in d.find_elements(By.CSS_SELECTOR, '.modal-title')))
    time.sleep(1.0)
    _drain_console(drv)


def _click_modal_tab(drv, label):
    for t in drv.find_elements(By.CSS_SELECTOR, '.algorithm-config-modal .tabs-nav .tab-btn'):
        if label in (t.text or ''):
            drv.execute_script('arguments[0].click();', t)
            return
    raise AssertionError(f'模态窗页签「{label}」未找到')


def _set_blocked(drv, patterns):
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': patterns})


def _set_theme(drv, mode):
    """经 ThemeSwitcher 切主题（浅色/深色），localStorage iatp:theme:v1 持久化。"""
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1', arguments[0]);", mode)
    drv.refresh()
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    _drain_console(drv)


def main():
    global PROBE_TYPE, JS_ERRORS
    # 后端隔离库守卫（与 tests/ui conftest 同口径）
    with urllib.request.urlopen(f'{API}/health', timeout=10) as r:
        health = json.loads(r.read().decode())
    assert health.get('database') == 'intelligent_audio_test_test', \
        f'非隔离库: {health.get("database")}'

    drv = _setup_driver()
    ok = True
    try:
        # ── 1. 列表真实数据渲染 + Network ──
        _goto(drv, '/AlgorithmConfig', wait=2.0)
        txt = _body(drv)
        assert '算法配置管理' in txt, f'页面未渲染: {txt[:200]}'
        assert '小艺语音大模型' in txt, f'真实算法行缺失: {txt[:400]}'
        assert 'voice_llm' in txt, f'算法类型缺失: {txt[:400]}'
        assert '上线' in txt, f'状态徽章缺失: {txt[:400]}'
        assert '7' in txt, f'参数数缺失: {txt[:400]}'
        _wait_rows(drv, 1)
        print('PASS 1a: 列表渲染 voice_llm 小艺语音大模型 / 上线 / 7 参数')
        _shot(drv, '01_list_light')

        nets = _net(drv, '/algorithm/definitions')
        found = False
        for m, u, s, b in nets:
            if 'definitions' in u and s == 200:
                found = True
                print(f'NET {m} {u} -> {s}')
                if b:
                    try:
                        parsed = json.loads(b)
                        keys = list(parsed.get('data', {}).get('items', [{}])[0].keys())
                        print('NET response keys (snake_case):', keys[:14])
                        with open(os.path.join(ARTIFACTS, 'net_definitions.json'), 'w', encoding='utf-8') as f:
                            f.write(b)
                    except Exception:
                        pass
                break
        assert found, 'Network 未见 /algorithm/definitions 200 请求'
        print('PASS 1b: Network 真实请求 /algorithm/definitions 200 (snake_case 返回)')

        # ── 2. 编辑模态窗：基本信息回填 + 参数配置真实数据 ──
        _open_edit(drv, 'voice_llm')
        txt = _body(drv)
        assert '编辑算法' in txt, f'编辑模态窗标题缺失: {txt[:300]}'
        assert '基本信息' in txt and '参数配置' in txt and '参考参数' in txt and '参数映射' in txt and '关联维度' in txt, \
            f'模态窗页签缺失: {txt[300:800]}'
        # 基本信息回填（编辑态算法代码只读）
        inputs = drv.find_elements(By.CSS_SELECTOR, '.algorithm-config-modal input.form-input')
        vals = [i.get_attribute('value') for i in inputs]
        assert 'voice_llm' in vals, f'算法代码回填缺失: {vals}'
        assert any('小艺语音大模型' in (v or '') for v in vals), f'名称回填缺失: {vals}'
        print('PASS 2a: 编辑模态窗基本信息真实回填 (voice_llm / 小艺语音大模型)')
        _shot(drv, '02_edit_modal_basic_light')

        # 参数配置页签：设备参数 7 行真实渲染
        _click_modal_tab(drv, '参数配置')
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, '.param-type-tab'))
        # 默认设备参数页签（v-show 多表并存 → 只取可见行）
        def _visible_param_rows():
            return [r for r in drv.find_elements(By.CSS_SELECTOR, '.algorithm-config-modal .data-table tbody tr')
                    if r.is_displayed()]
        rows = WebDriverWait(drv, 10).until(lambda d: _visible_param_rows())
        assert len(rows) >= 7, f'设备参数应 >=7 行, 实际 {len(rows)}'
        codes = []
        for r in rows:
            tds = r.find_elements(By.CSS_SELECTOR, 'td')
            if not tds:
                continue
            inputs = tds[0].find_elements(By.CSS_SELECTOR, 'input')
            codes.append(inputs[0].get_attribute('value') if inputs else '')
        assert 'wav_path' in codes, f'真实设备参数 wav_path 缺失: {codes}'
        print(f'PASS 2b: 参数配置页签设备参数真实渲染 {len(rows)} 行（含 wav_path）')
        _shot(drv, '03_params_device_light')

        # API 参数页签 3 行
        for t in drv.find_elements(By.CSS_SELECTOR, '.param-type-tab'):
            if 'API' in (t.text or ''):
                drv.execute_script('arguments[0].click();', t)
                break
        time.sleep(0.8)
        rows = _visible_param_rows()
        assert len(rows) >= 3, f'API 参数应 >=3 行, 实际 {len(rows)}'
        print(f'PASS 2c: API 参数页签真实渲染 {len(rows)} 行')
        _shot(drv, '04_params_api_light')

        # 关闭模态窗（取消）
        for b in drv.find_elements(By.CSS_SELECTOR, '.modal-footer .btn'):
            if '取消' in (b.text or ''):
                drv.execute_script('arguments[0].click();', b)
                break
        WebDriverWait(drv, 8).until(
            lambda d: not any('编辑算法' in (t.text or '') for t in d.find_elements(By.CSS_SELECTOR, '.modal-title')))
        print('PASS 2d: 取消关闭模态窗')

        # ── 3. 参数配置自动保存真实接口（探针算法，blur 防抖 POST /algorithm/params）──
        suffix = str(int(time.time()))
        PROBE_TYPE = 'int910_probe_' + suffix
        probe_name = 'INT910验收探针'
        resp = _api('POST', '/algorithm/definitions', {
            'type': PROBE_TYPE, 'name': probe_name, 'status': 'online',
            'description': 'INT-910 acceptance probe (deleted after run)',
        })
        assert '__http_error__' not in resp, f'探针创建失败: {str(resp)[:300]}'
        print('PASS 3a: API 建探针算法', PROBE_TYPE)

        drv.refresh()
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        _wait_rows(drv, 2, timeout=15)
        time.sleep(1.0)
        _drain_console(drv)

        _open_edit(drv, PROBE_TYPE)
        _click_modal_tab(drv, '参数配置')
        time.sleep(0.8)
        # 添加参数 → 新行 param-code 输入框
        add_btns = [b for b in drv.find_elements(By.CSS_SELECTOR,
                     '.algorithm-config-modal .params-toolbar button.btn') if '添加参数' in (b.text or '')]
        assert add_btns, '未找到添加参数按钮'
        drv.execute_script('arguments[0].click();', add_btns[0])
        time.sleep(0.8)
        # 新行 param-code 输入框（.param-code-input）填入参数代码并触发 blur → 1.5s 防抖自动保存
        code_inputs = [i for i in drv.find_elements(By.CSS_SELECTOR,
                       '.algorithm-config-modal .param-code-input') if i.is_displayed()]
        assert code_inputs, '添加参数后未见参数代码输入框'
        last_input = code_inputs[-1]
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            last_input, 'int910_probe_param')
        # 填 paramName 列（同行的第 2 个输入框）
        row_tds = last_input.find_element(By.XPATH, 'ancestor::tr').find_elements(By.CSS_SELECTOR, 'td')
        name_input = row_tds[1].find_element(By.CSS_SELECTOR, 'input')
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            name_input, '探针参数')
        # blur 触发 handleParamBlur → 1500ms 防抖 → POST /algorithm/params
        drv.execute_script("arguments[0].blur();", last_input)
        # 等待自动保存请求（1.5s 防抖 + 请求往返）
        time.sleep(3.0)
        _drain_console(drv)
        nets = _net(drv, '/algorithm/params')
        posts = [(m, u, s, b) for m, u, s, b in nets if m in ('POST', 'PUT') and 'params' in u]
        assert posts, f'自动保存未产生 POST/PUT /algorithm/params: {nets[-5:]}'
        for m, u, s, b in posts:
            print(f'NET {m} {u} -> {s}')
            if b:
                try:
                    parsed = json.loads(b)
                    if parsed.get('data') and isinstance(parsed['data'], dict):
                        print('NET 自动保存响应 data keys:', list(parsed['data'].keys()))
                except Exception:
                    pass
        print('PASS 3b: blur 自动保存真实 POST/PUT /algorithm/params')

        # 后端确认探针参数已落库
        time.sleep(0.5)
        detail = _api('GET', f'/algorithm/definitions/{PROBE_TYPE}')
        params = detail.get('data', {}).get('device_params') or []
        codes2 = [p.get('param_code') for p in params]
        assert 'int910_probe_param' in codes2, f'后端未落库探针参数: {codes2}'
        print('PASS 3c: 探针参数已真实落库 (POST /algorithm/params 生效)')
        _shot(drv, '05_probe_param_autosaved')

        # ── 3d. API 参数页签自动保存（param_type_source=api + direction 原值，INT-910 P2-1 回归）──
        for t in drv.find_elements(By.CSS_SELECTOR, '.param-type-tab'):
            if 'API' in (t.text or ''):
                drv.execute_script('arguments[0].click();', t)
                break
        time.sleep(0.8)
        api_add_btns = [b for b in drv.find_elements(By.CSS_SELECTOR,
                        '.algorithm-config-modal .params-toolbar button.btn') if '添加参数' in (b.text or '')]
        assert api_add_btns, 'API 参数页签未找到添加参数按钮'
        drv.execute_script('arguments[0].click();', api_add_btns[0])
        time.sleep(0.8)
        api_code_inputs = [i for i in drv.find_elements(By.CSS_SELECTOR,
                           '.algorithm-config-modal .param-code-input') if i.is_displayed()]
        assert api_code_inputs, 'API 页签添加参数后未见参数代码输入框'
        api_last = api_code_inputs[-1]
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            api_last, 'int910_probe_api_param')
        # 同行第 2 列 paramName、第 3 列方向 select → output
        api_row_tds = api_last.find_element(By.XPATH, 'ancestor::tr').find_elements(By.CSS_SELECTOR, 'td')
        api_name_input = api_row_tds[1].find_element(By.CSS_SELECTOR, 'input')
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            api_name_input, 'API探针参数')
        api_dir_sel = api_row_tds[2].find_element(By.CSS_SELECTOR, 'select')
        drv.execute_script(
            "arguments[0].value = 'output';"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            api_dir_sel)
        drv.execute_script("arguments[0].blur();", api_last)
        # 等待 1.5s 防抖自动保存 POST /algorithm/params
        time.sleep(3.0)
        _drain_console(drv)
        api_reqs = _net_req_bodies(drv, '/algorithm/params')
        api_posts = [(m, u, b) for m, u, b in api_reqs if m == 'POST' and 'params' in u]
        assert api_posts, f'API 页签自动保存未产生 POST /algorithm/params: {api_reqs[-5:]}'
        wire_api = False
        for m, u, b in api_posts:
            if not b:
                continue
            try:
                parsed = json.loads(b)
                if parsed.get('param_type_source') == 'api' and parsed.get('direction') == 'output':
                    wire_api = True
                    print('NET API 自动保存请求体: param_type_source=api, direction=output')
                    break
            except Exception:
                continue
        assert wire_api, 'API 页签自动保存请求体缺 param_type_source=api 或 direction=output（P2-1 未修复）'
        print('PASS 3d: API 参数页签自动保存请求体透传 param_type_source=api + direction=output')
        _shot(drv, '05b_api_param_autosaved')
        # 后端落点核查（信息性：wire 契约已断言；落点反映后端 gateway 是否按
        # param_type_source 路由 device/api 表，INT-910 P2-1 数据完整性侧证）
        api_detail = _api('GET', f'/algorithm/definitions/{PROBE_TYPE}')
        api_landed = [p.get('param_code') for p in (api_detail.get('data', {}).get('api_params') or [])]
        dev_landed = [p.get('param_code') for p in (api_detail.get('data', {}).get('device_params') or [])]
        print(f'INFO API 参数落点: api_params={api_landed} device_params={dev_landed}')

        # ── 3e. 设备参数 direction 改 output 后自动保存（PUT body direction=output，INT-910 P2-1）──
        for t in drv.find_elements(By.CSS_SELECTOR, '.param-type-tab'):
            if '设备' in (t.text or ''):
                drv.execute_script('arguments[0].click();', t)
                break
        time.sleep(0.8)
        target_row = None
        for r in _visible_param_rows():
            tds = r.find_elements(By.CSS_SELECTOR, 'td')
            if not tds:
                continue
            ci = tds[0].find_elements(By.CSS_SELECTOR, 'input')
            if ci and (ci[0].get_attribute('value') or '') == 'int910_probe_param':
                target_row = r
                break
        assert target_row, '未找到探针参数行 int910_probe_param'
        dir_sel = target_row.find_elements(By.CSS_SELECTOR, 'td')[2].find_element(By.CSS_SELECTOR, 'select')
        drv.execute_script(
            "arguments[0].value = 'output';"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            dir_sel)
        time.sleep(3.0)
        _drain_console(drv)
        dev_reqs = _net_req_bodies(drv, '/algorithm/params')
        dev_puts = [(m, u, b) for m, u, b in dev_reqs if m == 'PUT' and 'params' in u]
        wire_dir = False
        for m, u, b in dev_puts:
            if not b:
                continue
            try:
                parsed = json.loads(b)
                if parsed.get('direction') == 'output':
                    wire_dir = True
                    print('NET 设备参数 direction 自动保存请求体: direction=output')
                    break
            except Exception:
                continue
        assert wire_dir, '设备参数 direction 改 output 后自动保存请求体缺 direction=output（P2-1 未修复）'
        print('PASS 3e: 设备参数 direction=output 自动保存请求体透传 direction')
        _shot(drv, '05c_device_param_direction_output')

        # 关闭模态窗（取消）
        for b in drv.find_elements(By.CSS_SELECTOR, '.modal-footer .btn'):
            if '取消' in (b.text or ''):
                drv.execute_script('arguments[0].click();', b)
                break
        WebDriverWait(drv, 8).until(
            lambda d: not any('编辑算法' in (t.text or '') for t in d.find_elements(By.CSS_SELECTOR, '.modal-title')))

        # ── 4. 空态（搜索无结果）──
        search = drv.find_element(By.CSS_SELECTOR, '.algorithm-config-page .search-input')
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            search, 'zzz_no_match_alg')
        _wait_text(drv, '暂无数据', timeout=8)
        _shot(drv, '06_empty_search')
        print('PASS 4: 空态（搜索无结果 → 暂无数据）')
        drv.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            search, '')
        _wait_rows(drv, 2, timeout=10)

        # ── 4b. 加载态（fetch 延迟注入，捕获「加载中...」spinner）──
        # 仅延迟 /api/ 路径 3s，展示加载态；用后移除脚本（INT-905 实测法）
        delay_script_id = drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
              (function(){
                var orig = window.fetch;
                window.fetch = function(url, opts){
                  if (typeof url === 'string' && url.indexOf('/api/') !== -1) {
                    return new Promise(function(resolve, reject){
                      setTimeout(function(){
                        orig.apply(window, [url, opts]).then(resolve, reject);
                      }, 3000);
                    });
                  }
                  return orig.apply(window, [url, opts]);
                };
              })();
            '''})['identifier']
        drv.refresh()
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        # 3s 延迟内应见「加载中...」
        time.sleep(1.2)
        _drain_console(drv)
        body = _body(drv)
        assert '加载中' in body, f'加载态 spinner 缺失: {body[-200:]}'
        _shot(drv, '06b_loading_state')
        print('PASS 4b: 加载态（fetch 延迟 3s → 加载中... 可见）')
        # 等加载完成（延迟结束后）
        _wait_rows(drv, 2, timeout=15)
        _drain_console(drv)
        # 移除延迟脚本，恢复即时加载
        drv.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument',
                            {'identifier': delay_script_id})
        # 重启页面确保无残留 fetch 覆盖
        drv.refresh()
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        _wait_rows(drv, 2, timeout=15)
        print('PASS 4c: 加载完成后列表恢复')

        # ── 5. 错误态（gRPC 未起模拟：CDP 阻断 /algorithm/*，INT-899 友好文案）──
        _set_blocked(drv, ['*algorithm/definitions*'])
        drv.refresh()
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.0)
        _wait_text(drv, '加载算法列表失败', timeout=15)
        body = _body(drv)
        assert '算法服务暂不可用' in body or '加载算法列表失败' in body, \
            f'友好错误文案缺失: {body[-300:]}'
        assert 'InactiveRpcError' not in body, \
            '页面直出原始 gRPC 异常文本（INT-899 修复未生效）'
        assert '<_InactiveRpcError' not in body, \
            '页面直出 <_InactiveRpcError...> 原始文本'
        _shot(drv, '07_error_state_friendly')
        print('PASS 5a: gRPC 未起 → 友好错误态（无 InactiveRpcError 直出）')
        _set_blocked(drv, [])
        drv.refresh()
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        _wait_rows(drv, 2, timeout=15)
        assert '小艺语音大模型' in _body(drv), '解除阻断后列表未恢复'
        print('PASS 5b: 解除阻断后列表恢复')

        # ── 6. 深色主题 ──
        _set_theme(drv, 'dark')
        _goto(drv, '/AlgorithmConfig', wait=1.5)
        _wait_rows(drv, 2, timeout=15)
        _shot(drv, '08_list_dark')
        _open_edit(drv, 'voice_llm')
        _shot(drv, '09_edit_modal_dark')
        # 关闭模态窗
        for b in drv.find_elements(By.CSS_SELECTOR, '.modal-footer .btn'):
            if '取消' in (b.text or ''):
                drv.execute_script('arguments[0].click();', b)
                break
        WebDriverWait(drv, 8).until(
            lambda d: not any('编辑算法' in (t.text or '') for t in d.find_elements(By.CSS_SELECTOR, '.modal-title')))
        _set_theme(drv, 'light')
        print('PASS 6: 深色主题截图')

        # ── 7. 全会话无 JS 运行时严重错误 ──
        _drain_console(drv)
        # 阻断测试预期产生 app 级错误日志（API Fetch Error / 加载算法列表失败），
        # 属 INT-899 已处理路径（友好 Toast），非未捕获运行时错误；真实崩溃为 Uncaught。
        real = [e for e in JS_ERRORS
                if 'ERR_BLOCKED_BY_CLIENT' not in e
                and 'API Fetch Error' not in e
                and '加载算法列表失败' not in e
                and 'Failed to fetch' not in e
                and 'Uncaught' in e]
        assert not real, 'JS 运行时严重错误:\n' + '\n'.join(real[-10:])
        print('PASS 7: 无 JS 未捕获运行时错误（阻断测试的已处理错误日志除外）')

        print('\nALL INT-910 验收走查用例通过')
    except Exception as e:
        ok = False
        print('\nFAIL:', e)
        import traceback
        traceback.print_exc()
    finally:
        # 清理探针数据（测试数据卫生）
        if PROBE_TYPE:
            try:
                detail = _api('GET', f'/algorithm/definitions/{PROBE_TYPE}')
                for p in (detail.get('data', {}).get('device_params') or []) + (detail.get('data', {}).get('api_params') or []):
                    _api('DELETE', f'/algorithm/params/{p.get("id")}')
                _api('DELETE', f'/algorithm/definitions/{PROBE_TYPE}')
                print('CLEAN: 探针参数(device+api)+算法已删除')
            except Exception as e2:
                print('CLEAN FAIL:', e2)
        _drain_console(drv)
        drv.quit()

    if ok:
        print('DONE ->', ARTIFACTS)
    else:
        print('FAILED ->', ARTIFACTS)
        sys.exit(1)


if __name__ == '__main__':
    main()
