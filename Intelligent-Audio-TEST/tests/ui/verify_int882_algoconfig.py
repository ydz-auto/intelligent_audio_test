# -*- coding: utf-8 -*-
"""INT-882 算法配置页真实数据走查（React wiring/react + 常驻 5000 后端，AUTH_MODE=off）。

验收清单（INT-882）：
1. 算法/参数表真实数据渲染 + 作用域 chips
2. 高级配置折叠节、草稿/发布操作可走（写操作用测试数据，run 结束前删）
3. 空态/错误态正常
4. 浅色 + 深色 + Network 截图

- 后端数据源：GET /api/v1/algorithm/definitions → voice_llm「小艺语音大模型」(device 7 / api 3 /
  case 0 / ref 5 / 维度 3，case_count 由前端按用例引用聚合兜底 = 2)。
- 草稿保存为前端本地 mock（后端 RPC 未落定，INT-647 交付注明）；发布走真实 create/update。
- 写操作用测试数据 int882_probe_*，发布后即删（测试数据卫生）。
- 失败即打印当前 body 摘要，收尾尝试删除探针数据。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5341')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int882_algoconfig')

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
    drv.get(BASE + path)
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
    """从 performance log 提取与 url_sub 匹配的请求；返回 [(method, url, status, body_json)]。

    Selenium performance log 的 message 是转义过的 JSON 字符串，需先解析再取 URL 匹配。
    """
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = entry.get('message', '')
            try:
                data = json.loads(msg)
            except Exception:
                continue
            # Selenium 包装形如 {"message": {"method":..., "params":...}}
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
    # 去重保序
    seen, dedup = set(), []
    for m, u, s, b in out:
        key = (m, u, s, (b[:200] if b else ''))
        if key in seen:
            continue
        seen.add(key)
        dedup.append((m, u, s, b))
    return dedup


def _wait_rows(drv, n, timeout=12):
    WebDriverWait(drv, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def _row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='算法 {name} 的操作']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _menu_click(drv, label):
    for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'菜单项「{label}」未找到')


def _open_edit(drv, name='小艺语音大模型'):
    _goto(drv, '/AlgorithmConfig', wait=1.0)
    _wait_rows(drv, 1)
    _row_menu(drv, name)
    _menu_click(drv, '编辑')
    _wait_text(drv, '编辑算法')
    time.sleep(1.0)
    _drain_console(drv)


def _edit_field(drv, xpath, value):
    el = drv.find_element(By.XPATH, xpath)
    proto = 'HTMLTextAreaElement' if el.tag_name.lower() == 'textarea' else 'HTMLInputElement'
    js = (
        "const s = Object.getOwnPropertyDescriptor(window." + proto + ".prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
    )
    drv.execute_script(js, el, value)
    time.sleep(0.5)


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(0.6)


def _click_chip(drv, label):
    btn = drv.find_element(By.XPATH, f"//button[starts-with(normalize-space(.), '{label} (')]")
    btn.click()
    time.sleep(0.8)


def _table_headers(drv):
    ths = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead th')
    cells = ths or drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead td')
    return [c.text.strip() for c in cells if c.text.strip()]


def _close_sheet(drv):
    _js_click(drv, "//button[normalize-space()='取消']")
    time.sleep(0.6)
    # 脏态守卫
    if drv.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '有未保存的更改')]"):
        _js_click(drv, "//*[@role='alertdialog']//button[contains(., '离开并丢弃')]")
    try:
        WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body(d) and '新建算法' not in _body(d))
    except Exception:
        pass


def _delete_algo(drv, name):
    """行菜单删除指定算法并等待列表刷新。"""
    _row_menu(drv, name)
    _menu_click(drv, '删除')
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '确认删除')]"))
    _js_click(drv, "//*[@role='alertdialog']//button[contains(., '删除')]")
    WebDriverWait(drv, 10).until(lambda d: '算法已删除' in _body(d))
    time.sleep(1.0)


def _api_definitions():
    with urllib.request.urlopen('http://localhost:5000/api/v1/algorithm/definitions', timeout=10) as r:
        return json.loads(r.read().decode())


def _set_dark(drv):
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '深色')]")
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _set_light(drv):
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '浅色')]")
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def main():
    global PROBE_TYPE, JS_ERRORS
    drv = _setup_driver()
    ok = True
    try:
        # ── 0. 首页暖场 + 认证（AUTH_MODE=off 直达） ──
        _goto(drv, '/login', wait=2.0)
        _goto(drv, '/AlgorithmConfig', wait=2.0)

        # ── 1. 列表真实数据渲染 ──
        txt = _body(drv)
        assert '算法配置' in txt, f'页面未渲染: {txt[:200]}'
        assert '共 1 个算法' in txt, f'标题徽标缺失: {txt[:400]}'
        assert '小艺语音大模型' in txt, f'真实算法行缺失: {txt[:400]}'
        assert '上线' in txt, f'状态徽章缺失: {txt[:400]}'
        # 作用域 chips 属编辑 Sheet；列表侧先核对列与关联用例计数
        assert '关联用例' in txt, f'关联用例列缺失: {txt[:400]}'
        _wait_rows(drv, 1)
        print('PASS 1a: 列表渲染 voice_llm 小艺语音大模型 / 共 1 个算法')
        _shot(drv, '01_list_light')

        # Network 证据：definitions 请求 URL + 状态 + snake_case 返回
        nets = _net(drv, '/api/v1/algorithm/definitions')
        found = False
        for m, u, s, b in nets:
            if 'definitions' in u and s == 200:
                found = True
                print(f'NET {m} {u} -> {s}')
                if b:
                    try:
                        parsed = json.loads(b)
                        keys = list(parsed.get('data', {}).get('items', [{}])[0].keys())
                        print('NET response keys (snake_case):', keys[:12])
                        with open(os.path.join(ARTIFACTS, 'net_definitions.json'), 'w', encoding='utf-8') as f:
                            f.write(b)
                    except Exception:
                        pass
                break
        assert found, 'Network 未见 /algorithm/definitions 200 请求'
        print('PASS 1b: Network 真实请求 /algorithm/definitions 200 (snake_case 返回)')

        # ── 2. 编辑 Sheet：基本信息 + 参数表真实数据 + 作用域 chips ──
        _open_edit(drv)
        txt = _body(drv)
        assert '编辑算法' in txt and '管理算法定义、参数与映射关系' in txt, f'Sheet 标题缺失: {txt[:300]}'
        assert '算法代码' in txt and '显示名称' in txt and '所属分组' in txt, f'基本信息区缺失: {txt[:400]}'
        type_val = drv.find_element(By.XPATH, "//input[@id='algo-type']").get_attribute('value')
        name_val = drv.find_element(By.XPATH, "//input[@id='algo-name']").get_attribute('value')
        assert type_val == 'voice_llm', f'算法代码回填错误: {type_val}'
        assert name_val == '小艺语音大模型', f'显示名称回填错误: {name_val}'
        # 作用域 chips 计数（真实参数表 7 设备 + 3 API + 0 用例）
        for chip in ['全部 (10)', '设备 (7)', 'API (3)', '用例 (0)']:
            assert chip in _body(drv), f'作用域 chip「{chip}」缺失'
        rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
        assert len(rows) == 10, f'参数表应 10 行, 实际 {len(rows)}'
        # 高级配置折叠头计数徽章（默认收起，展开内容不可见）
        assert '参考参数 5' in _body(drv), f'参考参数计数徽章缺失'
        assert '维度 3' in _body(drv), f'维度计数徽章缺失'
        assert '添加参考字段' not in _body(drv), '高级配置应默认收起'
        # footer 双态保存
        assert '保存草稿' in _body(drv) and '发布' in _body(drv) and '取消' in _body(drv), 'footer 按钮缺失'
        print('PASS 2: 编辑 Sheet 基本信息/参数表/作用域 chips/高级配置徽章')
        _shot(drv, '02_edit_sheet_all_light')

        # ── 3. 作用域 chips 切换过滤 + 列动态显隐 ──
        _click_chip(drv, '设备')
        rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
        assert len(rows) == 7, f'设备 chip 应 7 行, 实际 {len(rows)}'
        headers = _table_headers(drv)
        assert '方向' in headers, f'设备态应保留方向列: {headers}'
        assert '适用范围' not in headers and '范围约束' not in headers and '字段路径' not in headers, \
            f'设备态应隐藏用例专属列: {headers}'
        _shot(drv, '03_scope_device')
        _click_chip(drv, 'API')
        rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
        assert len(rows) == 3, f'API chip 应 3 行, 实际 {len(rows)}'
        _click_chip(drv, '用例')
        rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
        # 用例 0 参数 → 空态行（colspan 单行）渲染
        assert len(rows) == 1, f'用例 chip 应为空态行(1), 实际 {len(rows)}'
        assert '未找到匹配参数' in _body(drv), '用例空态提示缺失'
        _shot(drv, '04_scope_case_empty')
        _click_chip(drv, '全部')
        rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
        assert len(rows) == 10, f'全部 chip 应恢复 10 行, 实际 {len(rows)}'
        print('PASS 3: 作用域 chips 过滤 + 列显隐 + 用例空态')

        # ── 4. 高级配置折叠节展开 ──
        _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
        WebDriverWait(drv, 5).until(lambda d: '添加参考字段' in _body(d))
        txt = _body(drv)
        assert '设备参数映射' in txt, f'展开后参数映射缺失: {txt[600:1400]}'
        assert '添加关联维度' in txt, f'展开后评估维度缺失: {txt[600:1400]}'
        _shot(drv, '05_advanced_config_expanded')
        _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
        time.sleep(0.5)
        print('PASS 4: 高级配置折叠节展开/收起')

        # ── 5. 草稿保存（mock 本地）──
        _edit_field(drv, "//input[@id='algo-name']", '小艺语音大模型·INT882草稿')
        _wait_text(drv, '将在 30 秒后自动保存草稿')
        _js_click(drv, "//button[normalize-space()='保存草稿']")
        WebDriverWait(drv, 8).until(lambda d: '上次保存' in _body(d))
        assert '保存草稿' in _body(drv), '草稿保存后 footer 应保留双态按钮'
        _shot(drv, '06_draft_saved')
        print('PASS 5: 草稿保存（上次保存时间戳）')

        # ── 6. 发布（真实 create，测试数据）──
        _close_sheet(drv)
        _goto(drv, '/AlgorithmConfig', wait=1.0)
        _wait_rows(drv, 1)
        _js_click(drv, "//button[normalize-space()='新建算法']")
        _wait_text(drv, '新建算法')
        PROBE_TYPE = 'int882_probe_' + str(int(time.time()))
        _edit_field(drv, "//input[@id='algo-type']", PROBE_TYPE)
        _edit_field(drv, "//input[@id='algo-name']", 'INT882验收探针')
        _edit_field(drv, "//textarea[@id='algo-desc']", 'INT882 acceptance probe (deleted after run)')
        _js_click(drv, "//button[normalize-space()='发布']")
        # 新建态发布成功 toast 为「算法已创建」（瞬态）；成功判据以 Sheet 关闭 + 列表刷新 + 后端落库为准
        WebDriverWait(drv, 15).until(
            lambda d: '管理算法定义、参数与映射关系' not in _body(d))
        _wait_text(drv, PROBE_TYPE, timeout=15)
        _wait_text(drv, '共 2 个算法', timeout=15)
        assert 'INT882验收探针' in _body(drv), '发布后列表未见探针行'
        print('PASS 6a: 发布成功（新建算法真实落库，列表共 2 个算法）')
        _shot(drv, '07_published_probe')
        lst = _api_definitions()
        types = [i['type'] for i in lst['data']['items']]
        assert PROBE_TYPE in types, f'后端未见探针: {types}'
        print('PASS 6b: 后端确认探针已落库')

        # 探针关联用例计数兜底（case_count 聚合）不阻塞断言；直接清理
        _delete_algo(drv, 'INT882验收探针')
        _wait_text(drv, '共 1 个算法', timeout=12)
        assert PROBE_TYPE not in _body(drv), '删除后探针行仍残留'
        lst = _api_definitions()
        types = [i['type'] for i in lst['data']['items']]
        assert PROBE_TYPE not in types, f'后端探针未清理干净: {types}'
        PROBE_TYPE = None
        print('PASS 6c: 探针已删除，库内无残留')

        # ── 7. 空态（搜索无结果）──
        search = drv.find_element(By.XPATH, "//input[@aria-label='搜索算法']")
        _edit_field(drv, "//input[@aria-label='搜索算法']", 'zzz_no_match_alg')
        _wait_text(drv, '未找到匹配的算法', timeout=8)
        _shot(drv, '08_empty_search')
        print('PASS 7: 空态（搜索无结果）')
        _edit_field(drv, "//input[@aria-label='搜索算法']", '')
        _wait_text(drv, '共 1 个算法', timeout=8)

        # ── 8. 错误态（CDP 拦截 definitions）──
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*algorithm/definitions*']})
        drv.refresh()
        WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.0)
        _wait_text(drv, '加载失败', timeout=15)
        assert '算法配置加载失败，请重试' in _body(drv), '错误态描述缺失'
        _shot(drv, '09_error_state')
        print('PASS 8a: 错误态（拦截接口 → 加载失败 + 重试）')
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
        _js_click(drv, "//button[contains(., '请重试')]")
        _wait_text(drv, '共 1 个算法', timeout=15)
        assert '小艺语音大模型' in _body(drv), '重试后列表未恢复'
        print('PASS 8b: 重试恢复')

        # ── 9. 深色主题 ──
        _set_dark(drv)
        _goto(drv, '/AlgorithmConfig', wait=1.5)
        _wait_text(drv, '共 1 个算法', timeout=12)
        _wait_text(drv, '小艺语音大模型', timeout=12)
        _shot(drv, '10_list_dark')
        _open_edit(drv)
        _shot(drv, '11_edit_sheet_dark')
        _close_sheet(drv)
        _set_light(drv)
        print('PASS 9: 深色主题截图')

        # ── 10. 全会话无 JS 运行时严重错误 ──
        _drain_console(drv)
        real = [e for e in JS_ERRORS if 'ERR_BLOCKED_BY_CLIENT' not in e]
        assert not real, 'JS 运行时严重错误:\n' + '\n'.join(real[-10:])
        print('PASS 10: 无 JS 运行时严重错误')

        print('\nALL INT-882 验收走查用例通过')
    except Exception as e:
        ok = False
        print('\nFAIL:', e)
        print('body:', _body(drv)[:800])
        _shot(drv, '99_failure')
    finally:
        # 测试数据卫生：无论成败清理探针
        if PROBE_TYPE:
            try:
                req = urllib.request.Request(
                    f'http://localhost:5000/api/v1/algorithm/definitions/{PROBE_TYPE}',
                    method='DELETE')
                urllib.request.urlopen(req, timeout=10)
                print(f'cleanup: deleted {PROBE_TYPE}')
            except Exception as ce:
                print('cleanup failed:', ce)
        try:
            drv.quit()
        except Exception:
            pass
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
