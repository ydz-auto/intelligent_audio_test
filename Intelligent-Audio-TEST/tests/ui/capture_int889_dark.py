# -*- coding: utf-8 -*-
"""INT-889 深色模式模态窗截图（真实 Chrome headless，连常驻后端）。

本脚本驱动 frontend-react dev server（5320），AUTH_MODE=off 登录后：
1) localStorage 注入 dark 主题（iatp:theme:v1:mode=dark）
2) 逐窗打开 → 截图：音频选择子弹窗 / 评估策略折叠节 / 批量操作四弹窗
截图落 tests/ui/artifacts/int889_testcases_modals/dark/<名称>/screenshot.png
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int889_testcases_modals', 'dark')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5320')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROBE_PREFIX = '接线测试_INT889_batchops'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    print('saved', name)


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _login_dark(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    # 注入 dark 主题
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', 'dark');"
        "document.documentElement.classList.add('dark');"
    )
    time.sleep(0.5)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
        time.sleep(2)
    drv.get(BASE + '/testcases/by-group')
    time.sleep(2.5)
    assert '用例管理' in _body(drv), '用例管理页未打开'


def _open_drawer(drv):
    btns = drv.find_elements(By.XPATH, "//button[contains(., '新增用例')]")
    target = None
    for b in btns:
        if b.text.strip() == '新增用例':
            target = b
            break
    if target is None:
        target = btns[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
    time.sleep(0.4)
    target.click()
    WebDriverWait(drv, 8).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.0)


def _load_more(drv, rounds=10):
    for _ in range(rounds):
        more = drv.find_elements(By.XPATH, "//button[contains(., '加载更多')]")
        if not more:
            return
        try:
            more[0].click()
            time.sleep(1.0)
        except Exception:
            return


def _select_probe(drv):
    boxes = drv.find_elements(
        By.CSS_SELECTOR, f"[role='checkbox'][aria-label^='选择 {PROBE_PREFIX}']")
    if not boxes:
        _load_more(drv)
        boxes = drv.find_elements(
            By.CSS_SELECTOR, f"[role='checkbox'][aria-label^='选择 {PROBE_PREFIX}']")
    if boxes:
        drv.execute_script("arguments[0].click()", boxes[0])
        time.sleep(0.6)
    return boxes


def _bulk_button(drv, label):
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0)
    bar = drv.find_element(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")
    return bar.find_element(By.XPATH, f".//button[contains(., '{label}')]")


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def main():
    drv = _driver()
    try:
        _login_dark(drv)

        # ① 音频选择子弹窗（深色）
        _open_drawer(drv)
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        tabs[0].click()
        time.sleep(1.0)
        lib = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        lib[0].click()
        time.sleep(2.5)
        _shot(drv, '01_audio_select_dark')
        dlg = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
        rows = dlg.find_elements(By.XPATH, ".//button[.//*[@role='checkbox']]")
        if rows:
            drv.execute_script("arguments[0].click()", rows[0])
            time.sleep(0.8)
            _shot(drv, '01_audio_select_selected_dark')
        # 关闭弹窗 + 抽屉（ESC）
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)

        # ② 评估策略折叠节（深色）
        _open_drawer(drv)
        strat = drv.find_element(By.XPATH, "//button[contains(., '评估策略')]")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", strat)
        time.sleep(0.4)
        strat.click()
        time.sleep(0.8)
        _shot(drv, '02_strategy_section_dark')
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)

        # ③ 批量操作四弹窗（深色）
        drv.get(BASE + '/testcases/by-group')
        time.sleep(2.5)
        boxes = _select_probe(drv)
        if boxes:
            for label, title in [
                ('批量设置专属参数', '批量设置用例专属参数'),
                ('批量设置播放设备', '批量设置播放设备'),
                ('批量设置声压', '批量设置声压级'),
                ('批量设置噪声', '批量设置噪声'),
            ]:
                _bulk_button(drv, label).click()
                time.sleep(1.0)
                dlg = _dialog_by_title(drv, title)
                _shot(drv, f'03_{title}_dark')
                dlg.find_element(
                    By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]"
                ).click()
                time.sleep(0.6)
        else:
            print('WARN: 未找到探针用例，跳过批量弹窗深色截图')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
