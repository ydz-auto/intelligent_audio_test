# -*- coding: utf-8 -*-
"""INT-1284 补充验证（独立会话，避免长会话浏览器崩溃）：
1. 空分组（test_case_count=0）展开 → 组内空态，不发懒加载请求。
2. /start-test 与 /testcases 按分组全量 9 卡 + 页脚计数一致截图（浅/深）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5304'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1284_te')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

LOG = []


def log(msg):
    LOG.append(msg)
    try:
        print(msg)
    except Exception:
        pass


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\\Google\\Chrome\\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    cands = []
    if chrome_major and os.path.isdir(cache_root):
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
    return webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())


def _drain(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _net(drv):
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            r = params.get('request') or {}
            reqs[params.get('requestId')] = {'method': r.get('method', 'GET'), 'url': r.get('url', '')}
    return reqs


def _card_info(drv):
    return drv.execute_script('''
      const out = [];
      document.querySelectorAll('div.bg-card').forEach(card => {
        const name = card.querySelector('span.font-medium.truncate');
        if (!name) return;
        const badge = card.querySelector('span.rounded-md');
        out.push({ name: name.textContent.trim(), badge: badge ? badge.textContent.trim() : null });
      });
      return out;
    ''')


def _wait_cards(drv, timeout=35):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cards = _card_info(drv)
            if cards and any(c['name'] and c['name'] != '未分组' for c in cards):
                return True
        except Exception:
            pass
        time.sleep(0.8)
    return False


def _click_group(drv, name):
    els = drv.find_elements(By.CSS_SELECTOR, 'span.font-medium.truncate')
    for el in els:
        if el.text.strip() == name:
            drv.execute_script('arguments[0].click();', el)
            return True
    return False


def _wait_text(drv, text, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if text in (drv.execute_script('return document.body.textContent || ""') or ''):
                return True
        except Exception:
            return False
        time.sleep(0.8)
    return False


def _set_theme(drv, mode):
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "%s")' % mode)


def _load_more_all(drv):
    for _ in range(3):
        found = False
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                found = True
                time.sleep(1)
                break
        if not found:
            return


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1)
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(2)
        log('LOGIN OK')

        # ---- 空分组展开 → 空态 + 无懒加载请求 ----
        _drain(drv)
        drv.get(BASE + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        _load_more_all(drv)
        time.sleep(1.5)
        cards_all = _card_info(drv)
        log('start-test all cards(%d): %s' % (len(cards_all), json.dumps(cards_all, ensure_ascii=False)))
        footer = drv.execute_script('''
          const ps = [...document.querySelectorAll('p')].map(p=>p.textContent.trim()).filter(t=>t.includes('个分组'));
          const btns = [...document.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(t=>t.includes('个分组'));
          return {ps, btns};
        ''')
        log('start-test footer: %s' % json.dumps(footer, ensure_ascii=False))
        _drain(drv)
        clicked = _click_group(drv, '默认分组')
        empty_seen = _wait_text(drv, '该分组暂无用例', timeout=15)
        time.sleep(2)
        reqs = _net(drv)
        lazy_for_empty = [r for r in reqs.values() if '/testcases' in r['url'] and 'group_id=' in r['url']]
        log('EXPAND 默认分组(0条) clicked=%s empty=%s lazy=%d' % (clicked, empty_seen, len(lazy_for_empty)))
        if lazy_for_empty:
            log('  unexpected lazy: %s' % json.dumps([r['url'] for r in lazy_for_empty], ensure_ascii=False))

        # ---- 截图：/start-test 浅/深（全量 9 卡）----
        _set_theme(drv, 'light')
        drv.get(BASE + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        _load_more_all(drv)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-light.png'))
        _set_theme(drv, 'dark')
        drv.get(BASE + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        _load_more_all(drv)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-dark.png'))
        log('start-test light+dark screenshots saved')

        # 展开 打断与恢复（懒加载用例卡）截图
        _click_group(drv, '打断与恢复')
        _wait_text(drv, '条 · 加载更多', timeout=20)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-expanded-lazy.png'))
        log('expanded-lazy screenshot saved')

        # ---- 截图：/testcases 浅/深 ----
        _set_theme(drv, 'light')
        drv.get(BASE + '/testcases/by-group')
        _wait_cards(drv)
        time.sleep(1.5)
        _load_more_all(drv)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'testcases-grouped-light.png'))
        _set_theme(drv, 'dark')
        drv.get(BASE + '/testcases/by-group')
        _wait_cards(drv)
        time.sleep(1.5)
        _load_more_all(drv)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'testcases-grouped-dark.png'))
        log('testcases light+dark screenshots saved')

        ok = clicked and empty_seen and not lazy_for_empty
        log('SUPP ASSERT OK=%s' % ok)
        with open(os.path.join(ARTIFACTS, 'evidence_supp.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(LOG) + '\n')
        return 0 if ok else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
