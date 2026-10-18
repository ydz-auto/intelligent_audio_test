# -*- coding: utf-8 -*-
"""INT-695 补充截图：深色模式关键交互态（浅色由 pytest 走查存档）。

复用 test_ui_31 的驱动/进入逻辑，打开用例抽屉后在深色主题下逐态截图：
① 音频选择子弹窗（多选态 + 底部计数）
② 评估策略折叠节展开态（引用已有策略 + 摘要卡 + 覆盖 Switch）
③ 新建策略内联表单
④ 保存回读 evaluationStrategy 契约（toast）

截图落 tests/ui/artifacts/int695_dark/。
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int695_dark')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


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


def _shot(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    print('saved', os.path.join(d, 'screenshot.png'))


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _enter_workbench(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
        time.sleep(2)
    drv.get(BASE + '/testcases/by-group')
    time.sleep(2.5)


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


def _expand_strategy(drv):
    strat = drv.find_element(By.XPATH, "//button[contains(., '评估策略')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", strat)
    time.sleep(0.4)
    strat.click()
    time.sleep(0.8)


def main():
    drv = _driver()
    try:
        _enter_workbench(drv)
        # 深色主题（localStorage + reload）
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get(BASE + '/testcases/by-group')
        time.sleep(2.5)
        html_cls = drv.execute_script("return document.documentElement.className")
        print('theme classes after dark set:', html_cls)
        assert 'dark' in html_cls, 'dark class 未生效'

        _open_drawer(drv)

        # ① 音频选择子弹窗（多选态）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        tabs[0].click()
        time.sleep(1.0)
        lib_btns = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        lib_btns[0].click()
        time.sleep(2.5)
        rows = drv.find_elements(By.XPATH, "//div[@data-slot='dialog-content']//button[.//*[@role='checkbox']]")
        drv.execute_script("arguments[0].click()", rows[0])
        time.sleep(0.8)
        _shot('01_audio_select_multi_dark', drv)
        # 重开抽屉（音频弹窗「取消」与抽屉「取消」同文案，直接整页重进）
        drv.get(BASE + '/testcases/by-group')
        time.sleep(2.5)
        _open_drawer(drv)

        # ② 评估策略折叠节展开态（引用已有策略 + 摘要卡）
        _expand_strategy(drv)
        labels = drv.find_elements(By.XPATH, "//label[contains(., '引用已有策略')]")
        labels[0].click()
        time.sleep(1.0)
        sel = drv.find_elements(By.XPATH, "//button[contains(., '请选择要引用的评估策略')]")
        drv.execute_script("arguments[0].click()", sel[0])
        time.sleep(1.0)
        opts = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' or contains(@class,'select-item')]")
        drv.execute_script("arguments[0].click()", opts[0])
        time.sleep(1.0)
        _shot('02_strategy_reference_summary_dark', drv)

        # ③ 新建策略内联表单
        create_labels = drv.find_elements(By.XPATH, "//label[contains(., '新建策略')]")
        create_labels[0].click()
        time.sleep(1.0)
        _shot('03_strategy_create_form_dark', drv)

        # ④ 保存回读（toast 契约）
        name = drv.find_element(By.CSS_SELECTOR, "input[aria-label='策略名称']")
        name.send_keys('INT695_截图深色')
        time.sleep(0.3)
        save_btns = drv.find_elements(By.XPATH, "//button[contains(., '保存')]")
        save_btn = None
        for b in save_btns:
            if b.text.strip() == '保存':
                save_btn = b
                break
        if save_btn is None:
            save_btn = save_btns[0]
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", save_btn)
        time.sleep(0.3)
        drv.execute_script("arguments[0].click()", save_btn)
        time.sleep(1.0)
        _shot('04_save_readback_dark', drv)
        toasts = '\n'.join(t.text for t in drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]"))
        print('toast:', toasts[:200])
        print('ALL_DARK_CAPTURES_DONE')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
