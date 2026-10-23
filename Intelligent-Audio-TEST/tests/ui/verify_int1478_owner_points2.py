# -*- coding: utf-8 -*-
"""INT-1478 补充复核（二）：Network 证据 + 深色截图（主题 key 为纯字符串）+ 滚动容器实测。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1478_owner_points')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
out = {}


def main():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_owner_points_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(120)
    try:
        # 登录（复用 profile 时可能已有会话，/login 会直接跳 dashboard）
        d.get(BASE + '/login')
        time.sleep(3)
        if '/login' in d.current_url:
            d.find_element(By.ID, 'username').send_keys('接线测试_admin')
            d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            d.find_element(By.XPATH, "//button[contains(., '登')]").click()
            WebDriverWait(d, 30).until(lambda x: '/login' not in x.current_url)
            time.sleep(2)
        print('session url:', d.current_url)

        # 深色主题（纯字符串 key）
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        mark = len(d.get_log('performance'))
        d.get(BASE + '/tasks/526')
        time.sleep(3)
        WebDriverWait(d, 120).until(
            lambda x: x.execute_script('return !!document.querySelector(\'div[class*="xl:grid-cols-3"]\')'))
        time.sleep(10)
        theme = d.execute_script(
            "return {cls: document.documentElement.className, ls: localStorage.getItem('iatp:theme:v1:mode')}")
        out['theme'] = theme
        print('theme:', theme)
        d.save_screenshot(os.path.join(ART, '04_tasks526_flat_dark.png'))
        print('shot 04 dark re-captured')

        # Network：本页所有 /api 请求
        reqs = []
        for m in d.get_log('performance')[mark:]:
            try:
                msg = json.loads(m['message'])['message']
            except Exception:
                continue
            if msg.get('method') == 'Network.responseReceived':
                r = msg['params']['response']
                if '/api/' in r['url']:
                    reqs.append({'status': r['status'], 'url': r['url'].replace(BASE, ''),
                                 'mime': r.get('mimeType')})
        out['api_responses'] = reqs
        print('api responses:', json.dumps(reqs, ensure_ascii=False)[:1500])

        # 页面内 fetch 直接核对详情数据（同页面 token 口径）
        fetch = r"""
        const ar = arguments[arguments.length-1];
        fetch('/api/v1/tasks/526', {headers: {'Accept':'application/json'}})
          .then(r => r.text().then(t => ar({status: r.status, len: t.length, body: t.slice(0, 200000)})))
          .catch(e => ar({error: String(e)}));
        """
        d.set_script_timeout(120)
        res = d.execute_async_script(fetch)
        out['fetch_status'] = res.get('status')
        out['fetch_len'] = res.get('len')
        try:
            payload = json.loads(res.get('body') or '{}')
            data = payload.get('data', payload)
            cases = data.get('cases') or []
            ev = {}
            ex = {}
            for c in cases:
                ev[str(c.get('evaluation_status'))] = ev.get(str(c.get('evaluation_status')), 0) + 1
                ex[str(c.get('execution_status'))] = ex.get(str(c.get('execution_status')), 0) + 1
            out['fetch_cases'] = len(cases)
            out['fetch_eval_status'] = ev
            out['fetch_exec_status'] = ex
            out['fetch_total_cases'] = data.get('total_cases')
        except Exception as exc:
            out['fetch_parse_error'] = str(exc)
        print('fetch:', {k: out[k] for k in out if k.startswith('fetch')})

        # 滚动容器实测：滚到底部，确认最后一张卡片可见（无虚拟滚动/分页）
        scroll = r"""
        const g = document.querySelector('div[class*="xl:grid-cols-3"]');
        let sc = g; while (sc && sc !== document.body) {
          const s = getComputedStyle(sc);
          if (/(auto|scroll)/.test(s.overflowY)) break;
          sc = sc.parentElement;
        }
        const info = {scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight,
                      cards: g.children.length, atBottomBefore: sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2};
        sc.scrollTop = sc.scrollHeight;
        const last = g.lastElementChild ? g.lastElementChild.getBoundingClientRect() : null;
        return Object.assign(info, {
          scrollTopAfter: sc.scrollTop,
          atBottomAfter: sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2,
          lastCardVisible: !!last && last.top < window.innerHeight && last.bottom > 0,
          lastCardTop: last ? Math.round(last.top) : null
        });
        """
        out['scroll'] = d.execute_script(scroll)
        print('scroll:', out['scroll'])
        d.save_screenshot(os.path.join(ART, '06_scroll_container_bottom_dark.png'))

        # 回浅色
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        out['error'] = '%s: %s' % (type(exc).__name__, exc)
    finally:
        with open(os.path.join(ART, 'report2.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        d.quit()
        print('report2 written')


if __name__ == '__main__':
    main()
