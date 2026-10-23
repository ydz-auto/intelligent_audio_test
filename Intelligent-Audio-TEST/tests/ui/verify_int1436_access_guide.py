# -*- coding: utf-8 -*-
"""INT-1436 接入指南 doc 页 测试工程师独立验收探针（dev server 5273，公开路由）。

验收标准逐条核对：
1) 页面可打开（公开路由，无需登录）
2) 三章目录跳转正常（目录锚点 → 正文标题）
3) 代码块 / 表格渲染正确（shiki 高亮、表格含『适用算法』列）
4) 手册切换导航（使用手册 / API 手册 / 接入指南）与关于页入口
5) 浅色 + 深色两主题
6) 移动端阅读（390px 目录折叠展开）
7) 无 mock 残留（页面无占位/假数据，仅平台 mock 服务作为验证工具被文档引用）
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver(width=1680, height=1050):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument(f'--window-size={width},{height}')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    ver_t = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if ver_t and ver_t[0] == chrome_major:
                    drv_path = exe
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def main():
    drv = _driver()
    results = []
    failures = []
    try:
        # ① 页面可打开（公开路由，HTTP 200）
        drv.get(BASE + '/user-guide-integration')
        time.sleep(3.0)
        assert '/user-guide-integration' in drv.current_url, drv.current_url
        body = _body_text(drv)
        assert '接入指南' in body
        results.append('① 公开路由 /user-guide-integration 打开 ✓')

        # ② 三章正文标题（带锚点 id）
        h2s = drv.find_elements(By.CSS_SELECTOR, '.guide-prose h2')
        titles = [h2.text for h2 in h2s]
        for expect in ['Realtime API 接入（websocket_api）',
                       '普通 HTTP API 接入（http_api）',
                       '实体设备 E2E 接入（physical）']:
            if expect not in titles:
                failures.append(f'正文三章标题缺失: {expect}，实际: {titles}')
        anchors = [h2.get_attribute('id') for h2 in h2s]
        for expect in ['realtime-api-接入websocket_api',
                       '普通-http-api-接入http_api',
                       '实体设备-e2e-接入physical']:
            if expect not in anchors:
                failures.append(f'标题锚点 id 缺失: {expect}，实际: {anchors}')
        if not failures:
            results.append('② 三章标题 + 锚点 id 渲染 ✓')

        # ③ 目录锚点跳转（点击后 scrollY 前进 / 目标标题可见）
        toc_links = drv.find_elements(By.CSS_SELECTOR, 'aside ul a[href^="#"]')
        if len(toc_links) != 3:
            failures.append(f'目录条目数 = {len(toc_links)}（期望 3）')
        else:
            for lnk in toc_links:
                href = lnk.get_attribute('href')
                target = unquote(href.split('#', 1)[1])
                drv.execute_script('window.scrollTo(0, 0)')
                time.sleep(0.3)
                before = drv.execute_script('return window.scrollY')
                lnk.click()
                time.sleep(0.8)
                after = drv.execute_script('return window.scrollY')
                target_el = drv.find_elements(By.CSS_SELECTOR, f"[id='{target}']")
                if not target_el:
                    failures.append(f'锚点 #{target} 目标不存在')
                elif after <= before:
                    failures.append(f'锚点 #{target} 点击后 scrollY 未推进 ({before}→{after})')
            if not failures:
                results.append('③ 目录三章锚点跳转 ✓')

        # ④ 代码块 shiki 高亮（Python 适配器/驱动模板）
        shiki = drv.find_elements(By.CSS_SELECTOR, '.guide-prose pre code.shiki')
        if len(shiki) < 6:
            failures.append(f'shiki 代码块数 = {len(shiki)}（期望 ≥6）')
        # 语言以 pre aria-label + CodeBlockFrame title 呈现；高亮以 token span 的
        # --shiki-light/--shiki-dark CSS 变量为证（GuideCodeBlock 渲染路径）
        langs = set()
        for pre in drv.find_elements(By.CSS_SELECTOR, '.guide-prose pre[aria-label]'):
            langs.add(pre.get_attribute('aria-label'))
        if 'python' not in langs:
            failures.append(f'代码块未标注 python 语言（aria-label 集合: {sorted(langs)}）')
        highlighted_tokens = drv.find_elements(
            By.CSS_SELECTOR, ".guide-prose pre code.shiki span[style*='--shiki-light']")
        if not highlighted_tokens:
            failures.append('shiki 高亮 token（--shiki-light 变量）未渲染')
        if not failures:
            results.append(
                f'④ 代码块渲染（{len(shiki)} 个 shiki，语言 {sorted(langs)}，'
                f'高亮 token {len(highlighted_tokens)}）✓')

        # ⑤ 表格渲染（含『适用算法』列）
        tables = drv.find_elements(By.CSS_SELECTOR, '.guide-prose table')
        if len(tables) < 4:
            failures.append(f'表格数 = {len(tables)}（期望 ≥4）')
        has_applicable = any('适用算法' in t.text for t in tables)
        if not has_applicable:
            failures.append('无含『适用算法』列的表格')
        if not failures:
            results.append(f'⑤ 表格渲染（{len(tables)} 张，含适用算法列）✓')

        # ⑥ 复制代码按钮
        copies = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '复制代码')]")
        if not copies:
            failures.append('复制代码按钮缺失')
        else:
            results.append(f'⑥ 复制代码按钮（{len(copies)} 个）✓')

        # ⑦ 侧栏手册切换导航（三本，当前高亮）
        nav = drv.find_element(By.CSS_SELECTOR, 'aside nav')
        nav_text = nav.text
        for expect in ['使用手册', 'API 手册', '接入指南']:
            if expect not in nav_text:
                failures.append(f'侧栏导航缺 {expect}')
        current = drv.find_elements(By.CSS_SELECTOR, "aside nav a[aria-current='page']")
        if not current or '接入指南' not in current[0].text:
            failures.append('接入指南未高亮为当前手册')
        if not failures:
            results.append('⑦ 侧栏手册切换导航（三本+当前高亮）✓')

        # ⑧ 浅色 / 深色切换
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'dark')")
        drv.get('about:blank')
        drv.get(BASE + '/user-guide-integration')
        time.sleep(2.0)
        is_dark = drv.execute_script("return document.documentElement.classList.contains('dark')")
        if not is_dark:
            failures.append('深色主题未生效')
        else:
            results.append('⑧ 深色主题生效 ✓')

        # ⑨ 移动端 390px：目录折叠触发器 + 三章条目
        drv.set_window_size(390, 844)
        time.sleep(1.5)
        toc_btn = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '目录')]")
        if not toc_btn:
            failures.append('移动端目录折叠触发器缺失')
        else:
            toc_btn[0].click()
            time.sleep(1.0)
            items = drv.find_elements(By.CSS_SELECTOR, 'aside ul a[href^="#"]')
            if len(items) != 3:
                failures.append(f'移动端目录条目数 = {len(items)}（期望 3）')
            else:
                results.append('⑨ 移动端 390px 目录折叠 + 三章条目 ✓')

        # ⑩ 关于页「文档链接」卡含「接入指南」入口
        drv.set_window_size(1680, 1050)
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'light')")
        drv.get('about:blank')
        drv.get(BASE + '/about')
        time.sleep(2.5)
        about_body = _body_text(drv)
        if '接入指南' not in about_body:
            failures.append('关于页文档链接卡缺「接入指南」')
        else:
            link = drv.find_elements(By.CSS_SELECTOR, "a[href='/user-guide-integration']")
            if not link:
                failures.append('关于页「接入指南」链接不可点')
            else:
                results.append('⑩ 关于页文档链接卡含「接入指南」✓')

        # ⑪ 无 mock 残留 + ⑫ 内容抽检 —— 先回到接入指南页再读正文
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'light')")
        drv.get('about:blank')
        drv.get(BASE + '/user-guide-integration')
        time.sleep(2.5)
        source = drv.page_source
        for bad in ['待文档卡产出', '占位', '演示', '假数据']:
            if bad in source:
                failures.append(f'页面残留占位文案: {bad}')
        if not failures:
            results.append('⑪ 无 mock / 占位残留 ✓')

        # ⑫ 内容抽检：与 INT-1291 源稿（实机接入指南_API与Realtime测试.md）关键口径一致
        body_all = _body_text(drv)
        for key in ['RealtimeAdapterBase', 'OpenAIRealtimeAdapter', 'mock_realtime_api',
                    'user_speech_started', 'response_cancelled', 'allow_barge_in',
                    'reject_judge', 'BaseDeviceDriver', 'register_driver',
                    'DevicePlatform', 'http_api', 'websocket_api']:
            if key not in body_all:
                failures.append(f'内容缺关键口径: {key}')
        if not failures:
            results.append('⑫ 内容抽检（适配器三级体系 / 打断归一化 / 驱动注册 / 评估侧）✓')

        print('\n===== 验收探针结果 =====')
        for r in results:
            print(r)
        if failures:
            print('\n===== FAILURES =====')
            for f in failures:
                print(' -', f)
            sys.exit(1)
        print('===== ALL PASS =====')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
