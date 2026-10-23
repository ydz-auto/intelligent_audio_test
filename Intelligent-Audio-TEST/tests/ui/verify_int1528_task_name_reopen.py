# -*- coding: utf-8 -*-
"""INT-1528 任务命名弹窗取消后重开不恢复默认名称 —— 浏览器复验（React 接线）。

环境：
- dev server: http://127.0.0.1:5328（本 run 起，rsbuild.verify.tmp.ts，/api 代理 → docker 栈 15000）
- 后端：docker 网关 http://127.0.0.1:15000，主库 intelligent_audio_test，AUTH_MODE=off
- 页面：/start-test?step=1（选设备/API）→ 底部「开始测试」打开任务名称弹窗

验收：
① 首次打开默认名「测试任务_YYYY-MM-DD HH:mm」
② Ctrl+A+Delete 清空 → 主钮「开始测试」禁用
③ 取消后从底部「开始测试」重开 → 恢复默认名（修复前为空）
④ 输入自定义名后取消重开 → 恢复默认名（不残留上次输入）
⑤ 浅色 + 深色截图 + 请求证据
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5328')
GATEWAY = 'http://127.0.0.1:15000'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1528_task_name_reopen')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

os.makedirs(ARTIFACTS, exist_ok=True)
RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok, detail))
    print(('PASS ' if ok else 'FAIL ') + label + (' :: ' + detail if detail else ''))


def _health():
    with urllib.request.urlopen(GATEWAY + '/health', timeout=15) as r:
        body = r.read().decode('utf-8', 'replace')
    print('GATEWAY /health:', body[:200])
    assert '"database":"intelligent_audio_test"' in body, '不是主库 intelligent_audio_test！'


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
    drv.set_page_load_timeout(90)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)


def _shot(drv, name):
    path = os.path.join(ARTIFACTS, name + '.png')
    drv.save_screenshot(path)
    print('screenshot ->', path)
    return path


def _set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def _dialog(drv):
    return WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[role='dialog']"))


def _dialog_gone(drv):
    WebDriverWait(drv, 20).until(
        lambda d: len([e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                       if e.is_displayed()]) == 0)
    time.sleep(0.4)


def _input_value(drv):
    el = _dialog(drv).find_element(By.ID, 'task-name')
    return el.get_attribute('value')


def _footer_start(drv):
    """底部动作条「开始测试」按钮（Rocket 图标 + 文案；Dialog 内主钮同样文案，故按容器区分）。"""
    btns = drv.find_elements(
        By.XPATH,
        "//div[contains(@class,'border-t')]//button[normalize-space(.)='开始测试' or contains(., '开始测试')]")
    btns = [b for b in btns if b.is_displayed()]
    assert btns, '底部「开始测试」按钮未找到'
    return btns[0]


def _dialog_primary(drv):
    btns = _dialog(drv).find_elements(By.XPATH, ".//button[normalize-space(.)='开始测试']")
    assert btns, '弹窗主钮「开始测试」未找到'
    return btns[0]


def _open_from_footer(drv):
    btn = _footer_start(drv)
    drv.execute_script('arguments[0].click();', btn)
    try:
        _dialog(drv)
    except Exception:
        _shot(drv, 'debug_open_fail')
        toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]') if t.is_displayed()]
        print('DEBUG open fail; toasts=', toasts)
        print('DEBUG body:', drv.find_element(By.TAG_NAME, 'body').text[:500])
        raise
    time.sleep(0.6)


def _cancel(drv):
    btn = _dialog(drv).find_element(By.XPATH, ".//button[normalize-space(.)='取消']")
    drv.execute_script('arguments[0].click();', btn)
    _dialog_gone(drv)


def _online_device_names():
    with urllib.request.urlopen(GATEWAY + '/api/v1/test-devices?page=1&per_page=100', timeout=40) as r:
        data = json.loads(r.read().decode('utf-8', 'replace'))
    items = (data.get('data') or {}).get('items') or []
    return [i['name'] for i in items if i.get('status') == 'online']


def _select_device(drv):
    """选一台在线设备（base-ui Checkbox 渲染 span[role=checkbox]；按接口在线名单挑，避开离线校验）。"""
    names = _online_device_names()
    print('online devices:', names)
    boxes = WebDriverWait(drv, 60).until(
        lambda d: [b for b in d.find_elements(
            By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择设备']") if b.is_displayed()])
    chosen = None
    for b in boxes:
        label = b.get_attribute('aria-label') or ''
        if any(n in label for n in names):
            chosen = b
            break
    if chosen is None:
        chosen = boxes[0]
        print('WARN: 未匹配到在线设备，回退首个 checkbox')
    drv.execute_script('arguments[0].click();', chosen)
    time.sleep(1)
    return chosen.get_attribute('aria-label')


def _perf(drv):
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        m = msg.get('message', {})
        kind = m.get('method')
        if kind == 'Network.responseReceived':
            resp = m.get('params', {}).get('response', {})
            url = resp.get('url', '')
            if '/api/v1/' in url:
                out.append('%s %s' % (resp.get('status'), url))
    return out


def _exercise(drv, theme):
    """一条完整的复验链：选中设备 → 打开弹窗 → 读默认名 → 清空 → 取消 → 重开 → 自定义名 → 取消 → 重开。"""
    _goto(drv, '/start-test?step=1')
    _set_theme(drv, theme)
    if theme == 'dark':
        drv.refresh()  # 主题读 localStorage，整页重载才生效（bfcache 用 refresh 打断）
        WebDriverWait(drv, 60).until(
            lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)

    label = _select_device(drv)
    print('[%s] 选中设备：%s' % (theme, label))

    # ① 首次打开
    _open_from_footer(drv)
    first = _input_value(drv)
    check('%s 首次打开默认名非空且为「测试任务_日期时间」' % theme,
          bool(first) and first.startswith('测试任务_') and len(first) > len('测试任务_'),
          repr(first))
    if theme == 'light':
        _shot(drv, 'A_first_open_light')

    # ② 清空 → 主钮禁用
    inp = _dialog(drv).find_element(By.ID, 'task-name')
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    time.sleep(0.4)
    cleared = _input_value(drv)
    primary = _dialog_primary(drv)
    disabled = primary.get_attribute('disabled') is not None or primary.get_attribute('aria-disabled') == 'true'
    check('%s 清空后输入为空且主钮禁用' % theme, cleared == '' and disabled,
          'value=%r disabled=%s' % (cleared, disabled))
    if theme == 'light':
        _shot(drv, 'B_cleared_disabled_light')

    # ③ 取消 → 底部重开 → 恢复默认名（缺陷项）
    _cancel(drv)
    time.sleep(0.5)
    _open_from_footer(drv)
    reopened = _input_value(drv)
    reopened_disabled = _dialog_primary(drv).get_attribute('disabled') is not None
    check('%s 清空取消后重开恢复默认名（非空、主钮可用）' % theme,
          bool(reopened) and reopened.startswith('测试任务_') and not reopened_disabled,
          'value=%r disabled=%s' % (reopened, reopened_disabled))
    if theme == 'light':
        _shot(drv, 'C_reopened_after_clear_light')
    else:
        _shot(drv, 'D_reopened_after_clear_dark')

    # ④ 自定义名 → 取消 → 重开 → 不残留上次输入
    inp = _dialog(drv).find_element(By.ID, 'task-name')
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys('接线测试_残留名')
    custom = _input_value(drv)
    _cancel(drv)
    time.sleep(0.5)
    _open_from_footer(drv)
    reset = _input_value(drv)
    check('%s 自定义名取消后重开不残留上次输入' % theme,
          custom == '接线测试_残留名' and reset != custom and reset.startswith('测试任务_'),
          'custom=%r reset=%r' % (custom, reset))

    _cancel(drv)
    return first, reopened, reset


def main():
    _health()
    drv = _driver()
    try:
        _exercise(drv, 'light')
        reqs = _perf(drv)
        with open(os.path.join(ARTIFACTS, 'network_light.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(reqs) or '(no /api/v1 responses)')
        check('浅色 /api/v1 请求有 200 响应', any(' 200 ' in (' ' + r + ' ') for r in reqs),
              '；'.join(reqs[:6]))

        _health()
        _exercise(drv, 'dark')
        reqs2 = _perf(drv)
        with open(os.path.join(ARTIFACTS, 'network_all.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(reqs + reqs2))
    finally:
        drv.quit()

    failed = [r for r in RESULTS if not r[1]]
    print('\n==== 结果 %d/%d 通过 ====' % (len(RESULTS) - len(failed), len(RESULTS)))
    for label, ok, detail in RESULTS:
        print(('✅' if ok else '❌'), label, detail)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
