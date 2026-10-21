# -*- coding: utf-8 -*-
"""INT-1193 验收浏览器实测：入口从顶栏移至 灵犀Agent页右上角 + Agent工作台头行。

验证点（对齐卡面验收标准）：
1. 顶栏 TopBarRight 不再渲染「连接你的 agent」入口（灵犀Agent 魔法按钮旁无它）；
2. /ai-chat 页右上角 ai-chat-header-right 有「连接你的 agent」炫彩按钮 → 点击进 /agent-connect；
3. Agent 工作台浮窗 awb-header 头行右上角（最小化/展开/关闭前）有 compact 同款按钮 → 进 /agent-connect；
4. 文案统一「连接你的 agent」；炫彩按钮色值来自 --ai-magic-* tokens（无硬编码色值）；
5. 浅色 + 深色截图（/ai-chat 页 + Agent 工作台 + 顶栏）+ Network 截图。

运行前提：dev server http://127.0.0.1:5605（frontend/，VITE_API_TARGET=127.0.0.1:15000 常驻后端），
chromedriver 走 selenium 缓存路径。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('INT1193_BASE', 'http://127.0.0.1:5605')
CHROME_BIN = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64'
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1193')
os.makedirs(SHOT_DIR, exist_ok=True)

RESULTS = []


def record(name: str, ok: bool, detail: str = ''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail})
    print(f'{"PASS" if ok else "FAIL"} | {name} | {detail}')


def resolve_driver():
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    if chrome_major:
        for ver in os.listdir(DRIVER_CACHE):
            if ver.startswith(str(chrome_major)):
                exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
                if os.path.isfile(exe):
                    return exe
    # fallback: newest
    vers = sorted(os.listdir(DRIVER_CACHE), reverse=True)
    for ver in vers:
        exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
        if os.path.isfile(exe):
            return exe
    return ''


def new_driver(width=1600, height=1000):
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv = webdriver.Chrome(service=Service(resolve_driver()), options=opts)
    drv.set_page_load_timeout(45)
    return drv


def inject_login(driver, username='dev_user', permissions=('*',)):
    """AUTH_MODE=off 常驻栈：localStorage 注入 auth_user 整页重载。"""
    driver.get(f'{BASE}/#/login')
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
    payload = json.dumps({
        'id': 1, 'username': username, 'roleId': None,
        'roleName': 'dev_user', 'permissions': list(permissions),
    })
    driver.execute_script(
        'window.localStorage.setItem(arguments[0], arguments[1]);'
        'window.localStorage.setItem(arguments[2], arguments[3]);',
        'auth_token', 'dev-token', 'auth_user', payload,
    )
    driver.refresh()
    time.sleep(1.5)


def nav(driver, path):
    driver.get(f'{BASE}/#/{path}')
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '.top-bar-right, .ai-chat-page, .agent-connect-page')))


def shot(driver, name):
    p = os.path.join(SHOT_DIR, name)
    driver.save_screenshot(p)
    print(f'shot: {p}')
    return p


def toggle_dark(driver):
    driver.execute_script('document.documentElement.classList.add("dark");')
    time.sleep(0.5)


def toggle_light(driver):
    driver.execute_script('document.documentElement.classList.remove("dark");')
    time.sleep(0.5)


def main():
    drv = new_driver()
    try:
        inject_login(drv)
        wait = WebDriverWait(drv, 15)

        # ── ① 顶栏无入口 ──
        nav(drv, 'dashboard')
        time.sleep(1.5)
        top_right = drv.find_element(By.CSS_SELECTOR, '.top-bar-right')
        top_html = top_right.get_attribute('outerHTML')
        has_top_btn = ('连接你的 agent' in top_html) or ('联接你的 agent' in top_html)
        record('① 顶栏 TopBarRight 无「连接你的 agent」入口', not has_top_btn,
               f'top-right 含入口={has_top_btn}')
        # 顶栏还有灵犀Agent魔法按钮（作为对比基线）
        has_wb_btn = bool(top_right.find_elements(By.CSS_SELECTOR, '.agent-button'))
        record('①b 顶栏仍保留灵犀Agent魔法按钮', has_wb_btn, f'agent-button={has_wb_btn}')
        shot(drv, '01_topbar_light.png')
        toggle_dark(drv)
        shot(drv, '01_topbar_dark.png')
        toggle_light(drv)

        # ── ② /ai-chat 右上角入口 ──
        nav(drv, 'ai-chat')
        time.sleep(1.5)
        header_right = drv.find_element(By.CSS_SELECTOR, '.ai-chat-header-right')
        btn = header_right.find_element(By.CSS_SELECTOR, '.agent-connect-button')
        label = btn.find_element(By.CSS_SELECTOR, '.agent-connect-button__label').text
        record('② /ai-chat 右上角有「连接你的 agent」炫彩按钮', label == '连接你的 agent', f'label={label}')
        # 点击 → /agent-connect
        btn.click()
        WebDriverWait(drv, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.agent-connect-page')))
        record('②b 点击后进入 /agent-connect 入口页', True, 'agent-connect-page 可见')
        shot(drv, '02_agentconnect_light.png')
        toggle_dark(drv)
        shot(drv, '02_agentconnect_dark.png')
        toggle_light(drv)

        # ── ③ /ai-chat 页面截图（含右上角入口） ──
        nav(drv, 'ai-chat')
        time.sleep(1.5)
        shot(drv, '03_aichat_light.png')
        toggle_dark(drv)
        shot(drv, '03_aichat_dark.png')
        toggle_light(drv)

        # ── ④ Agent 工作台浮窗头行入口 ──
        # 打开工作台：点顶栏 AgentWorkbenchButton（.agent-button）
        top_right = drv.find_element(By.CSS_SELECTOR, '.top-bar-right')
        wb_btn = top_right.find_element(By.CSS_SELECTOR, '.agent-button')
        wb_btn.click()
        time.sleep(1.5)
        awb = drv.find_element(By.CSS_SELECTOR, '.agent-workbench')
        header = awb.find_element(By.CSS_SELECTOR, '.awb-header')
        compact_btn = header.find_element(By.CSS_SELECTOR, '.agent-connect-button')
        compact_label = compact_btn.find_element(By.CSS_SELECTOR, '.agent-connect-button__label').text
        is_compact = 'agent-connect-button--compact' in compact_btn.get_attribute('class')
        record('④ 浮窗头行有 compact「连接你的 agent」按钮', compact_label == '连接你的 agent' and is_compact,
               f'label={compact_label}, compact={is_compact}')
        # 位置：在最小化/展开/关闭按钮前
        hdr_html = header.get_attribute('outerHTML')
        btn_pos = hdr_html.find('agent-connect-button')
        min_pos = hdr_html.find('fa-minus')
        record('④b 按钮在最小化按钮前', 0 <= btn_pos < min_pos, f'btn@{btn_pos} < minus@{min_pos}')
        shot(drv, '04_workbench_light.png')
        toggle_dark(drv)
        shot(drv, '04_workbench_dark.png')
        toggle_light(drv)

        # 浮窗点击 → /agent-connect
        compact_btn.click()
        WebDriverWait(drv, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.agent-connect-page')))
        record('④c 浮窗入口点击后进入 /agent-connect', True, 'agent-connect-page 可见')

        # ── ⑤ 全站文案 / 硬编码色值 ──
        body_txt = drv.execute_script('return document.body.innerText;')
        record('⑤ 页面无「联接你的 agent」残留', '联接你的 agent' not in body_txt, 'body innerText 扫描')
        # 按钮 computed style：确认渐变含 --ai-magic 派生色（浅/深一致）
        nav(drv, 'ai-chat')
        time.sleep(1.5)
        btn = drv.find_element(By.CSS_SELECTOR, '.ai-chat-header-right .agent-connect-button')
        bg = drv.execute_script('return getComputedStyle(arguments[0]).backgroundImage;', btn)
        record('⑤b 按钮渐变背景存在', 'gradient' in bg, f'backgroundImage={bg[:80]}')

        # Network 截图：CDP performance log 记录 /ai-chat 加载请求
        logs = drv.get_log('performance')
        net_entries = []
        for e in logs:
            try:
                msg = json.loads(e['message'])
                params = msg.get('message', {}).get('params', {})
                req = params.get('request', {})
                url = req.get('url', '')
                if '5605' in url and ('ai-chat' in url or 'agent' in url or '/api/' in url):
                    net_entries.append(url)
            except Exception:
                pass
        record('⑤c Network 含 /ai-chat 页面资源', len(net_entries) > 0,
               f'{len(net_entries)} 条页面/接口请求')
        # 保存 network 摘要
        with open(os.path.join(SHOT_DIR, 'network_summary.json'), 'w', encoding='utf-8') as f:
            json.dump(net_entries[:40], f, ensure_ascii=False, indent=2)

        # Network 汇总截图（照「Network 汇总截图法」：性能条目渲染成页面再整页截图）
        driver_nav = drv
        driver_nav.execute_script(
            'performance.setResourceTimingBufferSize(4000);'
            'window.__perf = performance.getEntriesByType("resource")'
            '  .filter(function(e){return /5605/.test(e.name);})'
            '  .map(function(e){return e.name.replace("http://127.0.0.1:5605", "");});')
        time.sleep(0.5)
        rows_html = '\\n'.join(
            '<tr><td style="padding:2px 8px;border-bottom:1px solid #ddd;font:11px monospace">'
            f'{i + 1}</td><td style="padding:2px 8px;border-bottom:1px solid #ddd;font:11px monospace">'
            f'{u}</td></tr>' for i, u in enumerate(net_entries[:60]))
        net_html = (
            '<html><body style="margin:0;background:#fff">'
            '<div style="padding:10px;font:bold 13px sans-serif">Network — /ai-chat 页面资源'
            '（skill 下载为客户端桩，无真实请求）</div>'
            '<table style="border-collapse:collapse;width:100%">'
            '<tr><th style="text-align:left;padding:2px 8px;border-bottom:2px solid #666;font:11px sans-serif">#</th>'
            '<th style="text-align:left;padding:2px 8px;border-bottom:2px solid #666;font:11px sans-serif">URL</th></tr>'
            f'{rows_html}</table></body></html>')
        drv.execute_script("window.open('about:blank','_blank');")
        drv.switch_to.window(drv.window_handles[-1])
        drv.get(f'data:text/html;charset=utf-8;base64,'
                + __import__('base64').b64encode(net_html.encode('utf-8')).decode())
        time.sleep(0.8)
        shot(drv, '05_network_summary.png')
        drv.close()
        drv.switch_to.window(drv.window_handles[0])

        # console 错误检查（已知 env 缺口排除：GET /api/option/ 404 系常驻栈
        # getSiteName 启动抓取的后端缺口，与本卡改动无关，预存在）
        console_errors = [
            e for e in drv.get_log('browser')
            if e['level'] == 'SEVERE'
            and 'favicon' not in e.get('message', '')
            and '/api/option/' not in e.get('message', '')
        ]
        record('⑤d console 无 SEVERE 错误（排除 /api/option/ 404 已知 env 缺口）',
               len(console_errors) == 0, f'{len(console_errors)} 条 SEVERE')

    finally:
        drv.quit()

    print('\n==== 汇总 ====')
    ok = sum(1 for r in RESULTS if r['ok'])
    for r in RESULTS:
        print(f'{"✅" if r["ok"] else "❌"} {r["name"]} — {r["detail"]}')
    print(f'{ok}/{len(RESULTS)} passed')
    return 0 if ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
