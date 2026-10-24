# -*- coding: utf-8 -*-
"""INT-1601 自测：音频行菜单移除「播放历史」入口 + 弹窗删除。

- 前端：本 worktree 的 React dev server（默认 5333，代理 docker 网关 15000 → 主库 intelligent_audio_test）
- 断言：行菜单项不含「播放历史」；其余项（预览/详情/转换格式/特征分析·质量评估/删除）不变；
        DOM 无播放历史弹窗；Network 无 playback/history 相关请求。
- 证据：浅色 + 深色行菜单展开帧。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5333')
DRIVER = os.environ.get(
    'CHROMEDRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
ART = os.path.join('tests', 'ui', 'artifacts', 'int1601')
os.makedirs(ART, exist_ok=True)

NET_PATCH = r"""
window.__int1601Net = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  try { window.__int1601Net.push({url: url, method: method}); } catch (e) {}
  return __origFetch.apply(this, arguments);
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2.5)
    if '/login' not in drv.current_url:
        log('login: 已自动登录（AUTH_MODE=off）→ %s' % drv.current_url)
        return
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('shot %s' % path)


def wait_rows(drv, timeout=90):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.querySelectorAll('table tbody tr').length") > 0)


def open_row_menu(drv):
    btn = drv.find_elements(
        By.XPATH, "//button[contains(@aria-label,'的操作')]")[0]
    js_click(drv, btn)
    time.sleep(0.9)


def menu_items(drv):
    items = []
    for m in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
        if m.is_displayed():
            items.append((m.text or '').strip())
    return [t for t in items if t]


def main():
    drv = webdriver.Chrome(options=_opts(), service=Service(DRIVER))
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': NET_PATCH})
    result = {}
    try:
        login(drv)
        for mode, fname in (('light', '01_row_menu_light.png'),
                            ('dark', '02_row_menu_dark.png')):
            set_theme(drv, mode)
            drv.get(BASE + '/audio-import')
            wait_rows(drv)
            time.sleep(1.5)
            txt = drv.execute_script('return document.body.innerText')
            header = [l for l in txt.splitlines() if '个' in l][:3]
            open_row_menu(drv)
            items = menu_items(drv)
            log('[%s] 行菜单项: %s' % (mode, items))
            log('[%s] 页头: %s' % (mode, header))
            shot(drv, fname)
            result[mode] = {
                'menu': items,
                'has_playback_history': any('播放历史' in t for t in items),
                'has_preview': any(t == '预览' for t in items),
                'has_download': any(t == '下载' for t in items),
                'has_feature_analysis': any('特征分析' in t for t in items),
                'has_delete': any(t == '删除' for t in items),
            }
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)

        # DOM 残留：不应存在播放历史弹窗
        dom_txt = drv.execute_script('return document.body.innerText')
        dialogs = drv.execute_script(
            "return [...document.querySelectorAll('[role=dialog]')]"
            ".filter(e => (e.innerText||'').includes('播放历史')).length")
        result['dom'] = {
            'has_playback_history_text': '播放历史' in dom_txt,
            'playback_dialogs': dialogs,
        }
        # Network：无 playback / history 请求
        net = drv.execute_script('return window.__int1601Net || []')
        plugged = [n for n in net if 'playback' in n['url'].lower()
                   or 'history' in n['url'].lower()]
        result['network'] = {
            'total_requests': len(net),
            'audio_requests': [n for n in net if '/api/v1/audios' in n['url']][:3],
            'playback_history_requests': plugged,
        }
        log('dom: %s' % result['dom'])
        log('network total=%s playback_history=%s' % (len(net), plugged))
        log('RESULT %s' % json.dumps(result, ensure_ascii=False))
        ok = (
            not any(result[m]['has_playback_history'] for m in ('light', 'dark'))
            and result['light']['has_preview']
            and result['light']['has_download']
            and result['light']['has_feature_analysis']
            and not result['dom']['has_playback_history_text']
            and result['dom']['playback_dialogs'] == 0
            and not result['network']['playback_history_requests']
        )
        result['ok'] = ok
        log('OK=%s' % ok)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
