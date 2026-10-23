# -*- coding: utf-8 -*-
"""INT-1436 接入指南 doc 页浏览器实测（真实 Chrome headless，dev server 5273）。

公开路由 /user-guide-integration（无需登录、无后端依赖，纯静态手册）：
1) 三章目录条目存在且锚点跳转正常
2) 正文三章标题 / Python 代码块 shiki 高亮 / 表格（滚动包裹）渲染
3) 手册切换导航（使用手册 / API 手册 / 接入指南）存在
4) 浅色 + 深色截图（§2.5.3 交付附图）
"""
import os
import sys
import time
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1436_guide')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5273')
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


def _shot(drv, name, full=False):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    if full:
        height = drv.execute_script('return document.body.scrollHeight')
        drv.set_window_size(1680, min(height, 4000))
        time.sleep(0.3)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    print('saved', name)


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _set_theme(drv, mode):
    # 先在站点 origin 写入主题 key（about:blank 上 localStorage 被拒），再 about:blank 打断 bfcache 强刷
    drv.get(BASE + '/user-guide-integration')
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', %r);" % mode)
    drv.get('about:blank')
    drv.get(BASE + '/user-guide-integration')
    time.sleep(2.0)


def main():
    drv = _driver()
    results = []
    try:
        drv.get(BASE + '/user-guide-integration')
        time.sleep(3.0)
        body = _body(drv)

        # ① 页面与三章标题
        assert '接入指南' in body, '页面标题缺失'
        for title in ['Realtime API 接入', '普通 HTTP API 接入', '实体设备 E2E 接入']:
            headings = drv.find_elements(By.XPATH, f"//h2[contains(., '{title}')]")
            assert headings, f'正文标题缺失: {title}'
        results.append('① 三章正文标题渲染 ✓')

        # ② 侧栏手册切换导航（三本手册）
        nav = drv.find_element(By.CSS_SELECTOR, "aside nav")
        nav_text = nav.text
        assert '使用手册' in nav_text and 'API 手册' in nav_text and '接入指南' in nav_text, nav_text
        assert '接入指南' in drv.find_element(By.CSS_SELECTOR, "aside").text
        results.append('② 手册切换导航（含接入指南）✓')

        # ③ 目录锚点跳转（三章）
        toc_links = drv.find_elements(By.CSS_SELECTOR, "aside ul a[href^='#']")
        assert len(toc_links) == 3, f'目录条目数 = {len(toc_links)}'
        for i, lnk in enumerate(toc_links):
            href = lnk.get_attribute('href')
            lnk.click()
            time.sleep(0.8)
            target = unquote(href.split('#', 1)[1])
            # 锚点目标标题存在
            els = drv.find_elements(By.CSS_SELECTOR, f"[id='{target}']")
            assert els, f'锚点 #{target} 目标不存在'
            results.append(f'③ 目录锚点 #{target} 跳转可达 ✓')

        # ④ Python 代码块 shiki 高亮
        shiki_codes = drv.find_elements(By.CSS_SELECTOR, '.guide-prose pre code.shiki')
        assert shiki_codes, '无 shiki 高亮代码块'
        results.append(f'④ 代码块渲染（{len(shiki_codes)} 个 shiki 高亮）✓')

        # ⑤ 表格滚动包裹（适用算法列等）
        tables = drv.find_elements(By.CSS_SELECTOR, '.guide-prose table')
        assert len(tables) >= 4, f'表格数 = {len(tables)}'
        results.append(f'⑤ 表格渲染（{len(tables)} 个）✓')

        # ⑥ 复制按钮存在
        copies = drv.find_elements(By.XPATH, "//button[contains(., '复制代码')]")
        assert copies, '复制代码按钮缺失'
        results.append(f'⑥ 复制按钮（{len(copies)} 个）✓')

        # 浅色截图（整页）
        drv.set_window_size(1680, 1050)
        _shot(drv, 'light_top')
        # 整页滚动截图
        _shot(drv, 'light_full', full=True)
        # 深色
        _set_theme(drv, 'dark')
        time.sleep(1.0)
        is_dark = drv.execute_script(
            "return document.documentElement.classList.contains('dark')")
        assert is_dark, '深色未生效'
        _shot(drv, 'dark_top')
        _shot(drv, 'dark_full', full=True)
        results.append('⑦ 浅色 + 深色截图 ✓')

        print('\n===== 实测结果 =====')
        for r in results:
            print(r)
        print('===== ALL PASS =====')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
