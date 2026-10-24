# -*- coding: utf-8 -*-
"""INT-1694 取证：阶段 2 三视图（任务末级）+ 购物车任务视图/三视图（任务首级/末级）。

对接本 run dev server（5331，/api 代理 docker 真实栈 15000，库 intelligent_audio_test）。
输出：tests/ui/artifacts/int1694/*.png
"""
import os
import sys
import time
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5331'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1694')
os.makedirs(ART, exist_ok=True)
SHOTS = []


def make_driver(w=1600, h=1600):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    return d


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(drv, name):
    drv.execute_script('window.scrollTo(0,0);')
    time.sleep(0.4)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    SHOTS.append(p)
    print('SHOT', name)


def click_text(drv, needle, css='button', limit=None):
    for el in drv.find_elements(By.CSS_SELECTOR, css):
        try:
            if needle in text_of(drv, el):
                js_click(drv, el)
                return el
        except Exception:
            pass
    if limit:
        return None
    raise RuntimeError('找不到按钮/元素: %s' % needle)


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.refresh()
    time.sleep(3)


def open_pick(drv):
    drv.get(BASE + '/tasks/cherry-pick')
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "[role='tab']")) > 0)
    time.sleep(1.5)
    for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if '挑选合并' in text_of(drv, t):
            js_click(drv, t)
            break
    time.sleep(2)
    click_text(drv, '开始挑选')
    WebDriverWait(drv, 60).until(
        lambda d: len([b for b in d.find_elements(By.CSS_SELECTOR, 'button') if '\u4e0b\u4e00\u6b65' in text_of(d, b)]) > 0
    )
    time.sleep(2)


def select_two_tasks(drv):
    """阶段 1：勾选 2 个可挑选任务（每个任务 ≥2 条），返回任务名。"""
    rows = [c for c in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if (c.get_attribute('aria-label') or '').startswith('选择任务')]
    chosen = []
    picked = 0
    for cb in rows[:2]:
        label = cb.get_attribute('aria-label') or ''
        if picked >= 2:
            break
        js_click(drv, cb)
        picked += 1
        chosen.append(label)
        time.sleep(0.3)
    print('STAGE1_SELECTED', chosen)
    if picked < 2:
        raise RuntimeError('阶段 1 未勾到两个任务')
    return chosen


def expand_all(drv):
    """逐层展开：重复点击树内所有「展开」钮，直到没有可展开项。"""
    for _ in range(8):
        btns = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='\u5c55\u5f00']")]
        if not btns:
            break
        for b in btns:
            try:
                js_click(drv, b)
            except Exception:
                pass
        time.sleep(0.6)
    time.sleep(0.8)


def stage2_shots(drv, prefix):
    # 用例视图（默认）
    expand_all(drv)
    shot(drv, prefix + '_stage2_case')
    # 组织：标签视图
    tab = click_text(drv, '标签视图', limit=True)
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_stage2_case_tag')
    click_text(drv, '分组视图', limit=True)
    time.sleep(1)
    # 设备视图
    click_text(drv, '设备视图')
    expand_all(drv)
    shot(drv, prefix + '_stage2_device')
    # 结果类型视图
    click_text(drv, '结果类型视图')
    expand_all(drv)
    shot(drv, prefix + '_stage2_resulttype')


def add_to_cart(drv):
    click_text(drv, '全选当前筛选', limit=True)
    time.sleep(1)
    click_text(drv, '加入购物车', limit=True)
    time.sleep(4)
    print('ADDED')


def open_cart(drv):
    click_text(drv, '打开购物车', limit=True)
    WebDriverWait(drv, 60).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-"]')) > 0
        or '\u8d2d\u7269\u8f66\u4e3a\u7a7a' in d.find_element(By.TAG_NAME, 'body').text
    )
    time.sleep(2)
    if not drv.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        click_text(drv, '去复核', limit=True)
        time.sleep(2)
    print('CART_OPEN')


def cart_shots(drv, prefix):
    # 任务视图（默认）+ 用例子模式
    expand_all(drv)
    shot(drv, prefix + '_cart_task_case')
    # 分组/标签切换
    click_text(drv, '标签视图', limit=True)
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_task_case_tag')
    click_text(drv, '分组视图', limit=True)
    time.sleep(1)
    # 任务视图 · 设备 / 结果类型 子模式
    click_text(drv, '设备', limit=True, css='button')
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_task_device')
    click_text(drv, '结果类型', limit=True, css='button')
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_task_resulttype')
    # 基础三视图
    click_text(drv, '用例视图', limit=True)
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_case')
    click_text(drv, '设备视图', limit=True)
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_device')
    click_text(drv, '结果类型视图', limit=True)
    time.sleep(1)
    expand_all(drv)
    shot(drv, prefix + '_cart_resulttype')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'light'
    d = make_driver()
    try:
        d.get(BASE + '/tasks/cherry-pick')
        time.sleep(2)
        if mode == 'dark':
            set_theme(d, 'dark')
        else:
            set_theme(d, 'light')
        open_pick(d)
        select_two_tasks(d)
        click_text(d, '下一步', limit=True)
        WebDriverWait(d, 240).until(
            lambda x: len(x.find_elements(By.CSS_SELECTOR, '.animate-pulse')) == 0
        )
        time.sleep(3)
        stage2_shots(d, mode)
        add_to_cart(d)
        open_cart(d)
        cart_shots(d, mode)
        print('OK')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
