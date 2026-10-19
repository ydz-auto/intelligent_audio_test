# -*- coding: utf-8 -*-
"""INT-922 返工复测（P1 保存不删存量评估配置 + P3 新增/背景噪声覆盖）。

真实 Chrome headless + 常驻 5000 后端（AUTH_MODE=off）+ dev server（默认 5321）。
- P1 复测：带 config.background_noise 的用例编辑抽屉「保存」→ 未触碰评估策略节时
  存量 config.background_noise 不得被删（PUT 载荷含 background_noise + 后端 GET 仍在）。
- P3-①：UI 新增用例 → Network 捕获 POST /api/v1/testcases → 后端可查到新用例。
- 数据卫生：探针用例（API 预建 + UI 新建）结束前 DELETE + purge 清库。
失败落 tests/ui/artifacts/int922_bgnoise_preserve_post/<阶段>/。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int922_bgnoise_preserve_post')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

GROUP_ID = '3ea20043-888d-4749-b7ed-905fbcc99ce2'   # rg_g_reg1（回归测试分组，探针容器）
GROUP_NAME = 'rg_g_reg1'
PROBE_PREFIX = 'int922_bgnoise_probe_'
CREATE_PREFIX = 'int922_create_probe_'
BG_NOISE = {"audio_id": None, "spl": 60.0, "device_ids": [], "loop": True}

PASSED = []
FAILED = []
PROBES = []  # 待清理用例 id


def check(name, cond, extra=''):
    if cond:
        PASSED.append(name)
        print(f'  PASS {name}')
    else:
        FAILED.append(name)
        print(f'  FAIL {name}  {extra}')


def _driver():
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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _perf_requests(drv):
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                outer = json.loads(entry['message'])
                inner = outer.get('message', {})
                if inner.get('method') == 'Network.requestWillBeSent':
                    r = inner['params']['request']
                    reqs.append({'method': r.get('method'), 'url': r.get('url'),
                                 'postData': r.get('postData', '')})
            except Exception:
                pass
    except Exception:
        pass
    return reqs


def _api(path, method='GET', body=None):
    req = urllib.request.Request('http://localhost:5000' + path, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _setup(drv, theme):
    drv.get(BASE + '/')
    time.sleep(2)
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "localStorage.setItem('iatp:algorithm:v1',"
        " JSON.stringify({state:{algorithmId:''},version:0}));",
        theme)
    drv.get(BASE + '/testcases/by-group')
    WebDriverWait(drv, 25).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))


def _find_edit_button(drv, name):
    buttons = drv.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]')
    for btn in buttons:
        node = btn
        html = ''
        for _ in range(6):
            node = node.find_element(By.XPATH, '..')
            html = node.get_attribute('innerHTML') or ''
            if name in html:
                return btn
    return None


def _set_input(drv, el, value):
    drv.execute_script(
        "const el=arguments[0],s=arguments[1];"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,s); el.dispatchEvent(new Event('input',{bubbles:true}));",
        el, value)


def _create_probe_with_bgnoise(name):
    body = {
        'name': name,
        'description': 'INT-922 背景噪声保留探针',
        'group_id': GROUP_ID,
        'tags': [],
        'config': {
            'rounds': [{'round_number': 1, 'audios': [],
                        'evaluation': {'enabled': True, 'dimensions': []}}],
            'background_noise': BG_NOISE,
            'dimensions': [],
        },
    }
    resp = _api('/api/v1/testcases', method='POST', body=body)
    cid = (resp.get('data') or {}).get('id')
    if cid:
        PROBES.append(cid)
    return cid


def _cleanup():
    for cid in PROBES:
        try:
            _api(f'/api/v1/testcases/{cid}', method='DELETE')
        except Exception:
            pass
    for cid in PROBES:
        try:
            _api(f'/api/v1/testcases/{cid}/purge', method='DELETE')
        except Exception:
            pass
    PROBES.clear()


def main():
    drv = _driver()
    try:
        probe_name = PROBE_PREFIX + str(int(time.time() * 1000))
        print('== P1：编辑带 background_noise 探针用例，未触碰评估节保存 ==')
        cid = _create_probe_with_bgnoise(probe_name)
        check('API 预建带 background_noise 探针', cid is not None, f'id={cid}')
        if cid is None:
            raise RuntimeError('探针创建失败')

        _setup(drv, 'light')  # 探针已建，页面加载即含该卡
        btn = None
        for _ in range(20):
            btn = _find_edit_button(drv, probe_name)
            if btn:
                break
            time.sleep(1)
        check('找到探针用例「编辑用例」按钮', btn is not None)
        if btn is None:
            _save_evidence('01_probe_not_found', drv)
            raise RuntimeError('未找到探针用例卡')
        drv.execute_script('arguments[0].click()', btn)
        time.sleep(1.5)
        _save_evidence('02_edit_open_light', drv)

        # 保存（不改名不改任何字段；评估策略节未触碰）
        _perf_requests(drv)  # drain 基线
        save_btn = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(.,'保存')]"))
        drv.execute_script('arguments[0].click()', save_btn)

        toast_ok = False
        try:
            WebDriverWait(drv, 12).until(
                lambda d: any('更新测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            toast_ok = True
        except Exception:
            pass
        check('P1-1 保存 toast「更新测试用例成功」', toast_ok)

        reqs = _perf_requests(drv)
        puts = [r for r in reqs if r['method'] == 'PUT'
                and '/api/v1/testcases/' + cid in r['url']]
        check('P1-2 Network 捕获 PUT /testcases/{id}', len(puts) > 0,
              f'puts={len(puts)}')
        if puts:
            body = puts[-1].get('postData') or ''
            has_bn = 'background_noise' in body and 'spl' in body
            check('P1-3 PUT 载荷含 config.background_noise', has_bn,
                  f'body={body[:300]}')
        time.sleep(1.5)
        saved = (_api('/api/v1/testcases/' + cid).get('data') or {})
        cfg = saved.get('config') or {}
        bn = cfg.get('background_noise')
        check('P1-4 后端保存后 config.background_noise 仍在',
              bn is not None and bn.get('spl') == 60.0,
              f'bn={json.dumps(bn, ensure_ascii=False)[:200]}')

        print('== P3-①：UI 新增用例 → POST 落库 ==')
        create_name = CREATE_PREFIX + str(int(time.time() * 1000))
        add_btn = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(.,'新增用例')]"))
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(1.5)
        name_input = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.CSS_SELECTOR, '#case-name'))
        _set_input(drv, name_input, create_name)
        time.sleep(0.3)
        # 后端要求 group_id 或 group：UI 内选现有分组
        try:
            gl = drv.find_element(By.XPATH, "//label[contains(.,'所属分组')]")
            trigger = gl.find_element(By.XPATH,
                'ancestor::section').find_element(By.CSS_SELECTOR, '[role="combobox"]')
            drv.execute_script('arguments[0].click()', trigger)
            time.sleep(0.8)
            opt = WebDriverWait(drv, 5).until(
                lambda d: next((e for e in d.find_elements(
                    By.CSS_SELECTOR, '[data-slot="select-item"]')
                    if GROUP_NAME in (e.text or '')), None))
            drv.execute_script('arguments[0].click()', opt)
            check('P3-0 新增抽屉选择分组 rg_g_reg1', opt is not None)
        except Exception as e:
            check('P3-0 新增抽屉选择分组 rg_g_reg1', False, str(e)[:160])

        _save_evidence('03_create_open_light', drv)
        _perf_requests(drv)  # drain
        drv.execute_script('arguments[0].click()', drv.find_element(
            By.XPATH, "//button[contains(.,'保存')]"))
        c_toast = False
        try:
            WebDriverWait(drv, 12).until(
                lambda d: any('添加测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            c_toast = True
        except Exception:
            pass
        check('P3-1 新增 toast「添加测试用例成功」', c_toast)
        reqs2 = _perf_requests(drv)
        posts = [r for r in reqs2 if r['method'] == 'POST'
                 and r['url'].endswith('/api/v1/testcases')]
        check('P3-2 Network 捕获 POST /api/v1/testcases', len(posts) > 0,
              f'posts={len(posts)}')
        time.sleep(1.5)
        found = None
        for page in range(1, 3):
            lst = _api(f'/api/v1/testcases?page={page}&per_page=100').get('data', {}).get('items', [])
            found = next((it for it in lst if it.get('name') == create_name), None)
            if found:
                break
        check('P3-3 后端可查到新用例', found is not None,
              f'found={found.get("id") if found else None}')
        if found:
            PROBES.append(found['id'])

        print('== 深色截图 ==')
        try:
            _setup(drv, 'dark')
            btn3 = _find_edit_button(drv, probe_name)
            if btn3:
                drv.execute_script('arguments[0].click()', btn3)
                time.sleep(1.5)
                _save_evidence('04_backfill_dark', drv)
                check('深色编辑抽屉截图', True)
            else:
                _save_evidence('04_dark_list', drv)
                check('深色编辑抽屉截图', False, '未找到探针卡')

            fatal = [e for e in drv.get_log('browser')
                     if e.get('level') in ('SEVERE', 'ERROR')
                     and 'Failed to load resource' not in str(e.get('message', ''))]
            check('无 console 严重错误', len(fatal) == 0, f'fatal={len(fatal)}')
        except Exception as e:
            check('深色截图阶段', False, str(e)[:120])

        print(f'\n=== 结果：PASS {len(PASSED)} / FAIL {len(FAILED)} ===')
        for f in FAILED:
            print('  FAILED:', f)
        if FAILED:
            sys.exit(2)
    finally:
        try:
            _cleanup()
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
