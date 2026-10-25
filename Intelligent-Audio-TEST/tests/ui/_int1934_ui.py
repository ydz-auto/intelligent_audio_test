# -*- coding: utf-8 -*-
"""INT-1934 UI 取证公共件：driver / token 注入切会话 / 主题同源 reload / 截图 / 网络。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1934')
SHOTS = os.path.join(ART, 'shots')
os.makedirs(SHOTS, exist_ok=True)


def driver(download_dir=None):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    if download_dir:
        o.add_experimental_option('prefs', {
            'download.default_directory': download_dir,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': True,
        })
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_script_timeout(90)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    d.execute_script('arguments[0].click();', el)


def visible(d, css):
    return [e for e in d.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()]


def wait_vis(d, css, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        els = visible(d, css)
        if els:
            return els[0]
        time.sleep(0.4)
    return None


def wait_text(d, text, timeout=20, tags=('button', '*[role=menuitem]', '*[role=option]', 'a')):
    end = time.time() + timeout
    while time.time() < end:
        for tag in tags:
            for el in d.find_elements(By.CSS_SELECTOR, tag):
                try:
                    if el.is_displayed() and el.text.strip() == text:
                        return el
                except Exception:
                    continue
        time.sleep(0.4)
    return None


def body_bg(d):
    return d.execute_script(
        "return getComputedStyle(document.body).backgroundColor")


def enter(d, token, path, mode, ready_css=None, timeout=60):
    """同源注入 token + 主题 → 进页面 → 断言主题生效（浅色断言无 dark class / 深色断言有）。"""
    d.get(BASE + '/login')
    time.sleep(1.2)
    d.execute_script("localStorage.setItem('iatp:auth:token:v1', arguments[0])", token)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.get(BASE + path)
    if ready_css:
        if wait_vis(d, ready_css, timeout) is None:
            raise AssertionError('页面未就绪：等待 %s 超时' % ready_css)
    else:
        time.sleep(5)
    # 主题断言（reload 后可复验）
    html_cls = d.execute_script('return document.documentElement.className')
    bg = body_bg(d)
    if mode == 'dark':
        assert 'dark' in html_cls, '深色未生效 html.class=%r' % html_cls
        assert _is_dark_color(bg), '体背景不是深色：%s' % bg
    else:
        assert 'dark' not in html_cls, '浅色未生效 html.class=%r' % html_cls
        assert not _is_dark_color(bg), '体背景不是浅色：%s' % bg
    return {'html_class': html_cls, 'body_bg': bg}


def _is_dark_color(rgb):
    try:
        nums = [int(x) for x in rgb.replace('rgba(', '').replace('rgb(', '')
                .replace(')', '').split(',')[:3]]
        return sum(nums) / 3.0 < 90
    except Exception:
        return False


def shot(d, name):
    p = os.path.join(SHOTS, name + '.png')
    d.save_screenshot(p)
    return p


def dialog_text(d):
    els = visible(d, '[role=dialog], [role=alertdialog]')
    return els[0].text.strip() if els else ''


def close_dialog(d):
    if not visible(d, '[role=dialog], [role=alertdialog]'):
        return
    try:
        d.execute_script(
            "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    except Exception:
        pass
    time.sleep(0.8)
    if not visible(d, '[role=dialog], [role=alertdialog]'):
        return
    for label in ('取消', '关闭'):
        b = wait_text(d, label, timeout=3)
        if b is not None:
            js_click(d, b)
            time.sleep(0.8)
            return
    btn = visible(d, '[role=dialog] [data-slot=dialog-close], '
                     '[role=alertdialog] [data-slot=dialog-close]')
    if btn:
        js_click(d, btn[0])
        time.sleep(0.8)


def drain_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def net_since_drain(d):
    """drain 之后产生的 /api 响应（Selenium 每次读都会清空缓冲，故必须先 drain）。"""
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    for m in logs:
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/' in r['url']:
                out.append({'status': r['status'],
                            'method': msg['params'].get('type'),
                            'url': r['url'].split('/api/')[-1][:120]})
    return out


def requests_since_drain(d):
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    for m in logs:
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.requestWillBeSent':
            r = msg['params']['request']
            if '/api/' in r['url']:
                out.append('%s %s' % (r.get('method'), r['url'].split('/api/')[-1][:120]))
    return out


def row_menu(d, menu_label, task_name):
    row = d.find_element(By.XPATH, "//tr[contains(., '%s')]" % task_name)
    trig = row.find_element(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
    js_click(d, trig)
    item = wait_text(d, menu_label, timeout=12)
    assert item is not None, '行菜单「%s」未出现' % menu_label
    js_click(d, item)
    time.sleep(1.2)
