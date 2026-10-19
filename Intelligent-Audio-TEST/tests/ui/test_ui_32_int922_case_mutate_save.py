# -*- coding: utf-8 -*-
"""INT-922 用例编辑抽屉「保存」生效 + 字段回填复测（真实 Chrome headless + 常驻 5000 后端）。

卡内验收标准：用例编辑「字段回填真实数据、保存生效」。逐条核对：
- P2-1 编辑回填：打开真实用例「测试用例_2026144019.wav_185552」（group INT321_E2E /
  algorithm voice_llm / 3 轮）编辑抽屉，断言所属分组 Select 显示分组名、关联算法 Select
  显示算法名、轮次导航显示真实 3 轮（每轮「1 音频·1 维度」）、描述回填。
- P1-1 保存生效：改名 → 点「保存」→ Network 捕获 PUT /api/v1/testcases/{id} 真实请求 →
  后端查得改名落库 → 再改回原名保存恢复（共享库测试数据卫生）。

失败落 tests/ui/artifacts/int922_case_mutate_save/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int922_case_mutate_save')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

CASE_ID = 'b3ed43fc-ed03-4e54-aa47-55ea9125f3e3'
CASE_NAME = '测试用例_2026144019.wav_185552'
CASE_GROUP = 'INT321_E2E'
CASE_ALGO_NAME = '小艺语音大模型'
MARK = '【INT-922接线测试】'
RENAMED = CASE_NAME + MARK

PASSED = []
FAILED = []


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


def _backend_get(path):
    with urllib.request.urlopen('http://localhost:5000' + path, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _backend_case_name():
    return (_backend_get('/api/v1/testcases/' + CASE_ID).get('data') or {}).get('name')


def _backend_restore_name():
    """预检恢复：共享用例名若非原名（前序 run 残留），PUT 恢复，保证 rerun 幂等。"""
    data = (_backend_get('/api/v1/testcases/' + CASE_ID) or {}).get('data') or {}
    if (data.get('name') or '') == CASE_NAME:
        return
    update = {k: v for k, v in data.items()
              if k in ('name', 'description', 'group_id', 'tags', 'algorithm_type',
                       'config', 'algorithm_params', 'reference_params')}
    update['name'] = CASE_NAME
    req = urllib.request.Request('http://localhost:5000/api/v1/testcases/' + CASE_ID,
                                 method='PUT',
                                 data=json.dumps(update).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def _setup(drv, theme):
    drv.get(BASE + '/')
    time.sleep(2)
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "localStorage.setItem('iatp:algorithm:v1',"
        " JSON.stringify({state:{algorithmId:''},version:0}));",
        theme)
    drv.get(BASE + '/testcases/by-group')
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))


def _find_edit_button(drv, name):
    """找名称含 name 的用例卡的行内「编辑用例」按钮。"""
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


def _wait_toast_gone(drv, timeout=8):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'))
    except Exception:
        pass


def _set_input(drv, el, value):
    drv.execute_script(
        "const el=arguments[0],s=arguments[1];"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,s); el.dispatchEvent(new Event('input',{bubbles:true}));",
        el, value)


def main():
    drv = _driver()
    try:
        _backend_restore_name()  # 幂等：前序残留改名先恢复
        print('== 准备：浅色 / 清全局算法筛选 ==')
        _setup(drv, 'light')

        print('== P2-1 编辑回填 ==')
        target_btn = _find_edit_button(drv, CASE_NAME)
        check('找到目标用例「编辑用例」按钮', target_btn is not None)
        if target_btn is None:
            _save_evidence('01_case_not_found', drv)
            raise RuntimeError('未找到目标用例卡')
        drv.execute_script('arguments[0].click()', target_btn)
        time.sleep(1.5)
        _save_evidence('02_edit_drawer_open_light', drv)

        # 所属分组回填
        try:
            gl = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.XPATH, "//label[contains(.,'所属分组')]"))
            sec_text = gl.find_element(By.XPATH, 'ancestor::section').text
            check('P2-1a 所属分组回填显示 INT321_E2E',
                  CASE_GROUP in sec_text and '请选择分组' not in sec_text,
                  f'section="{sec_text[:60]}"')
        except Exception as e:
            check('P2-1a 所属分组回填显示 INT321_E2E', False, str(e)[:100])

        # 关联算法回填
        try:
            al = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.XPATH, "//label[contains(.,'关联算法')]"))
            sec_text = al.find_element(By.XPATH, 'ancestor::section').text
            check('P2-1b 关联算法回填显示 小艺语音大模型',
                  CASE_ALGO_NAME in sec_text and '请选择算法' not in sec_text,
                  f'section="{sec_text[:60]}"')
        except Exception as e:
            check('P2-1b 关联算法回填显示 小艺语音大模型', False, str(e)[:100])

        # 描述回填
        try:
            desc = drv.find_element(By.CSS_SELECTOR, '#case-desc')
            dv = desc.get_attribute('value') or ''
            check('P2-1c 描述回填', '自动从音频' in dv or '测试用例' in dv, f'value="{dv[:50]}"')
        except Exception as e:
            check('P2-1c 描述回填', False, str(e)[:100])

        # 轮次回填
        try:
            r1 = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.XPATH, "//button[contains(.,'第 1 轮')]"))
            nav = r1.find_element(By.XPATH,
                'ancestor::div[contains(@class,"flex shrink-0")] | ancestor::div[contains(@class,"space-y-1.5")]')
            nav_text = nav.text
            check('P2-1d 轮次回填真实 3 轮（每轮 1 音频·1 维度）',
                  all(f'第 {n} 轮' in nav_text for n in (1, 2, 3))
                  and nav_text.count('音频') >= 3 and '维度' in nav_text,
                  f'nav="{nav_text[:100]}"')
        except Exception as e:
            check('P2-1d 轮次回填真实 3 轮（每轮 1 音频·1 维度）', False, str(e)[:100])

        _save_evidence('03_backfill_light', drv)

        print('== P1-1 保存走真实写接口 ==')
        name_input = drv.find_element(By.CSS_SELECTOR, '#case-name')
        _set_input(drv, name_input, RENAMED)
        time.sleep(0.3)

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
        check('P1-1a 保存 toast「更新测试用例成功」', toast_ok)

        reqs = _perf_requests(drv)
        puts = [r for r in reqs if r['method'] == 'PUT'
                and '/api/v1/testcases/' + CASE_ID in r['url']]
        check('P1-1b Network 捕获 PUT /testcases/{id}', len(puts) > 0,
              f'puts={[r["url"] for r in puts][:2]}')

        time.sleep(1.5)
        bn = _backend_case_name()
        check('P1-1c 后端改名落库', bn == RENAMED, f'backend="{bn}"')
        _save_evidence('04_saved_light', drv)

        print('== 测试数据卫生：恢复原名 ==')
        _wait_toast_gone(drv)
        time.sleep(1.5)
        WebDriverWait(drv, 15).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))
        btn2 = _find_edit_button(drv, RENAMED)
        check('恢复：找到已改名用例的编辑按钮', btn2 is not None)
        if btn2 is None:
            _save_evidence('05_restore_open_fail', drv)
            raise RuntimeError('恢复：未找到已改名用例')
        drv.execute_script('arguments[0].click()', btn2)  # toast 可能悬浮遮挡，JS 点击
        time.sleep(1.5)
        name_input2 = drv.find_element(By.CSS_SELECTOR, '#case-name')
        _set_input(drv, name_input2, CASE_NAME)
        time.sleep(0.3)
        drv.execute_script('arguments[0].click()', drv.find_element(By.XPATH, "//button[contains(.,'保存')]"))
        time.sleep(2)
        bn2 = _backend_case_name()
        check('恢复原名落库（无残留）', bn2 == CASE_NAME, f'backend="{bn2}"')

        print('== 深色截图 ==')
        try:
            _setup(drv, 'dark')
            btn3 = _find_edit_button(drv, CASE_NAME)
            if btn3:
                drv.execute_script('arguments[0].click()', btn3)
                time.sleep(1.5)
                _save_evidence('06_backfill_dark', drv)
                check('深色编辑抽屉截图', True)
            else:
                _save_evidence('06_dark_list', drv)
                check('深色编辑抽屉截图', False, '未找到目标卡')

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
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
