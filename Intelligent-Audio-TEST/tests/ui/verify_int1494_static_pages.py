# -*- coding: utf-8 -*-
"""INT-1494 静态页深走查（rankings / reports / about / user-guide×3 / agent-connect /
错误页×5 / Agent 工作台浮窗）。

每个页面：浅色 + 深色截图、真实请求清单、关键交互。结果 JSON 落 artifacts/int1494/。
"""
import json
import os
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from int1494_helpers import (ARTIFACTS, BASE, body_text, clear_perf, driver,
                             goto, js_click, requests_simple, result, set_theme,
                             shot)

R = []


def run(name, fn):
    try:
        fn()
    except Exception as exc:  # 单项失败不影响其它页
        R.append(result(name, False, 'EXC: %r' % (exc,)))
        traceback.print_exc()


def wait(d, cond, timeout=25):
    try:
        return WebDriverWait(d, timeout).until(cond)
    except Exception:
        return None


# ---------------- /rankings ----------------
def rankings():
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/rankings', wait_text='Benchmark')
        time.sleep(2)
        txt = body_text(d)
        calls = requests_simple(d, '/benchmarks')
        sh1 = shot(d, 'rankings_light')
        selects = d.find_elements(By.CSS_SELECTOR, '[role=combobox], button[role=combobox], select')
        opts = {}
        for i, s in enumerate(selects[:4]):
            try:
                js_click(d, s)
                time.sleep(0.6)
                items = [x.text.strip() for x in d.find_elements(By.CSS_SELECTOR, '[role=option]') if x.text.strip()]
                opts['select%d' % i] = {'trigger': s.text.strip()[:30], 'options': items}
                d.find_element(By.TAG_NAME, 'body').send_keys('')  # ESC
                time.sleep(0.4)
            except Exception as exc:
                opts['select%d' % i] = {'error': repr(exc)}
        set_theme(d, 'dark')
        goto(d, '/rankings', wait_text='Benchmark')
        time.sleep(2)
        sh2 = shot(d, 'rankings_dark')
        R.append(result('rankings', '排行' in txt or 'Benchmark' in txt,
                        {'text': txt[:700], 'api': calls, 'selects': opts},
                        [sh1, sh2]))
    finally:
        d.quit()


# ---------------- /reports（ReportShowcasePage） ----------------
def reports_showcase():
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/reports')
        time.sleep(3)
        txt = body_text(d)
        calls = requests_simple(d, '/')
        sh1 = shot(d, 'reports_light')
        # 卡片/链接统计
        cards = d.find_elements(By.CSS_SELECTOR, 'a[href], button')
        hrefs = sorted({a.get_attribute('href') for a in d.find_elements(By.CSS_SELECTOR, 'a[href]')
                        if a.get_attribute('href') and '/reports' in a.get_attribute('href')})
        set_theme(d, 'dark')
        goto(d, '/reports')
        time.sleep(3)
        sh2 = shot(d, 'reports_dark')
        R.append(result('reports_showcase', len(txt) > 50,
                        {'text': txt[:900], 'api': calls[:40],
                         'anchors': hrefs[:15], 'clickable': len(cards)},
                        [sh1, sh2]))
    finally:
        d.quit()


# ---------------- /about ----------------
def about():
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/about', wait_text='关于')
        time.sleep(2)
        txt = body_text(d)
        calls = requests_simple(d, '/')
        heads = [h.text.strip() for h in d.find_elements(By.CSS_SELECTOR, 'h1,h2,h3') if h.text.strip()]
        # 刷新按钮（服务状态卡）
        refresh_clicked = None
        btns = [b for b in d.find_elements(By.CSS_SELECTOR, 'button') if b.is_displayed()]
        for b in btns:
            if '刷新' in (b.text or '') or (b.get_attribute('aria-label') or '').find('刷新') >= 0:
                js_click(d, b)
                refresh_clicked = b.text or b.get_attribute('aria-label')
                time.sleep(2)
                break
        calls2 = requests_simple(d, '/health')
        sh1 = shot(d, 'about_light')
        set_theme(d, 'dark')
        goto(d, '/about', wait_text='关于')
        time.sleep(2)
        sh2 = shot(d, 'about_dark')
        R.append(result('about', '关于' in txt,
                        {'heads': heads, 'text': txt[:800], 'api': calls[:25],
                         'refresh_clicked': refresh_clicked, 'health_calls': calls2},
                        [sh1, sh2]))
    finally:
        d.quit()


# ---------------- /user-guide ×3 ----------------
def guides():
    d = driver()
    try:
        set_theme(d, 'light')
        out = {}
        shots = []
        for path, marker, name in (
                ('/user-guide', '使用手册', 'user_guide'),
                ('/user-guide-api', 'API 手册', 'user_guide_api'),
                ('/user-guide-integration', '接入指南', 'user_guide_integration')):
            clear_perf(d)
            goto(d, path, wait_text=marker, timeout=40)
            time.sleep(2)
            txt = body_text(d)
            toc = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, 'nav a, aside a')
                   if a.text.strip()]
            code_blocks = len(d.find_elements(By.CSS_SELECTOR, 'pre, code'))
            imgs = [i.get_attribute('src') for i in d.find_elements(By.TAG_NAME, 'img')]
            out[name] = {'len': len(txt), 'text_head': txt[:400],
                         'toc': toc[:25], 'code_blocks': code_blocks,
                         'imgs': imgs[:5],
                         'api': requests_simple(d, '/')[:10]}
            shots.append(shot(d, name + '_light'))
        set_theme(d, 'dark')
        goto(d, '/user-guide', wait_text='使用手册')
        time.sleep(1)
        shots.append(shot(d, 'user_guide_dark'))
        goto(d, '/user-guide-api', wait_text='API 手册')
        time.sleep(1)
        shots.append(shot(d, 'user_guide_api_dark'))
        goto(d, '/user-guide-integration', wait_text='接入指南')
        time.sleep(1)
        shots.append(shot(d, 'user_guide_integration_dark'))
        R.append(result('guides', all(v['len'] > 300 for v in out.values()), out, shots))
    finally:
        d.quit()


# ---------------- /agent-connect ----------------
def agent_connect():
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/agent-connect', wait_text='agent')
        time.sleep(2)
        txt = body_text(d)
        calls = requests_simple(d, '/')
        dl = []
        for b in d.find_elements(By.CSS_SELECTOR, 'button, a'):
            t = (b.text or '') + (b.get_attribute('aria-label') or '')
            if '下载' in t or 'download' in t.lower():
                dl.append(t.strip()[:40])
        sh1 = shot(d, 'agent_connect_light')
        # 点下载按钮抓真实请求
        clicked = None
        for b in d.find_elements(By.CSS_SELECTOR, 'button, a'):
            t = (b.text or '') + (b.get_attribute('aria-label') or '')
            if ('下载' in t) and b.is_displayed():
                clear_perf(d)
                js_click(d, b)
                clicked = t.strip()
                time.sleep(3)
                break
        dl_calls = requests_simple(d, '/agent')
        sh2 = shot(d, 'agent_connect_after_download')
        set_theme(d, 'dark')
        goto(d, '/agent-connect', wait_text='agent')
        time.sleep(1)
        sh3 = shot(d, 'agent_connect_dark')
        R.append(result('agent_connect', 'agent' in txt.lower(),
                        {'text': txt[:800], 'download_buttons': dl,
                         'clicked': clicked, 'api': calls[:20],
                         'download_api': dl_calls}, [sh1, sh2, sh3]))
    finally:
        d.quit()


# ---------------- 错误页 ----------------
def errors():
    d = driver()
    try:
        set_theme(d, 'light')
        out, shots = {}, []
        for code in ('401', '403', '404', '500', '503'):
            goto(d, '/' + code)
            time.sleep(1.5)
            txt = body_text(d)
            btns = [b.text.strip() for b in d.find_elements(By.CSS_SELECTOR, 'button, a') if b.text.strip()]
            out[code] = {'text': txt[:300], 'actions': btns[:8], 'has_code': code in txt}
            shots.append(shot(d, 'error_' + code + '_light'))
        set_theme(d, 'dark')
        for code in ('401', '403', '404', '500', '503'):
            goto(d, '/' + code)
            time.sleep(1)
            shots.append(shot(d, 'error_' + code + '_dark'))
        ok = all(v['has_code'] for v in out.values())
        R.append(result('errors', ok, out, shots))
    finally:
        d.quit()


# ---------------- Agent 工作台浮窗 ----------------
def workbench():
    d = driver()
    try:
        set_theme(d, 'light')
        goto(d, '/dashboard')
        time.sleep(2)
        btn = wait(d, lambda x: x.find_element(By.CSS_SELECTOR, "button[aria-label='打开全局 Agent 工作台']"))
        state = {'button_found': btn is not None}
        if not btn:
            R.append(result('workbench', False, state))
            return
        js_click(d, btn)
        time.sleep(2)
        panel = d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")
        state['opened'] = len(panel) > 0
        shots = [shot(d, 'workbench_open_light')]
        # 最小化 → 胶囊
        if state['opened']:
            js_click(d, panel[0])
            time.sleep(1.5)
            cap = d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复 Agent 工作台']")
            state['capsule'] = len(cap) > 0
            shots.append(shot(d, 'workbench_capsule_light'))
            # 胶囊点导航按钮（页头）应恢复浮窗
            if cap:
                js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='打开全局 Agent 工作台']"))
                time.sleep(1.5)
                state['restored_by_nav'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) > 0
                shots.append(shot(d, 'workbench_restored_light'))
            # 跨页保持
            d.get(BASE + '/rankings')
            time.sleep(2.5)
            state['survives_nav'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) > 0
            shots.append(shot(d, 'workbench_crosspage_light'))
            # 关闭
            close = d.find_elements(By.CSS_SELECTOR, "button[aria-label='关闭']")
            if close:
                js_click(d, close[0])
                time.sleep(1)
                state['closed'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) == 0
        set_theme(d, 'dark')
        goto(d, '/dashboard')
        time.sleep(2)
        b2 = d.find_elements(By.CSS_SELECTOR, "button[aria-label='打开全局 Agent 工作台']")
        if b2:
            js_click(d, b2[0])
            time.sleep(2)
            shots.append(shot(d, 'workbench_open_dark'))
        R.append(result('workbench', bool(state.get('opened')), state, shots))
    finally:
        d.quit()


for nm, fn in (('rankings', rankings), ('reports_showcase', reports_showcase),
               ('about', about), ('guides', guides),
               ('agent_connect', agent_connect), ('errors', errors),
               ('workbench', workbench)):
    run(nm, fn)

with open(os.path.join(ARTIFACTS, 'int1494_static.json'), 'w', encoding='utf-8') as f:
    json.dump(R, f, ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2))
