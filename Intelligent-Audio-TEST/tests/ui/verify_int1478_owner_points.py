# -*- coding: utf-8 -*-
"""INT-1478 负责人补充三点复核（docker 真实栈：前端 15173 / 后端 15000 / 主库）。

复核对象（负责人 2026-10-23 于 /tasks/526 实测，修复卡 INT-1492）：
1) 关联用例平铺视图为 3 列 CaseCard 卡片网格（V9.7.10 为紧凑行式列表）；
2) 1737 条用例全量渲染，内容区 scrollHeight 极大、无分页/虚拟滚动（V9.7.10 400px 面板 + 虚拟滚动）；
3) 状态筛选缺「执行失败 / 评估失败」两个独立选项（现合并为「已失败」），摘要「评估失败 1737」筛不到。

产出：artifacts/int1478_owner_points/report.json + 浅/深截图 + 关键尺寸。
用法：python -I tests/ui/verify_int1478_owner_points.py
"""
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
BACK = os.environ.get('BACK_BASE', 'http://127.0.0.1:15000')
TASK_ID = 526
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1478_owner_points')
os.makedirs(ART, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')

out = {'checks': {}, 'api': {}, 'sizes': {}, 'options': [], 'errors': []}


def driver():
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
    return d


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    print('  shot:', p)
    return p


def wait_ready(d, timeout=90):
    WebDriverWait(d, timeout).until(
        lambda x: x.execute_script('return document.readyState') == 'complete')


def perf_api(d, mark=0):
    rows = []
    for m in d.get_log('performance')[mark:]:
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/v1/tasks/%d' % TASK_ID in r['url']:
                rows.append({'status': r['status'], 'url': r['url'], 'mime': r.get('mimeType')})
    return rows


def main():
    d = driver()
    try:
        # ---- 环境三次核对之一（run 开始）----
        import urllib.request
        with urllib.request.urlopen(BACK + '/health', timeout=10) as r:
            h = json.loads(r.read().decode())
        out['health_start'] = h
        print('health:', h)
        assert h.get('database') == 'intelligent_audio_test', '非主库，停'

        # ---- 登录（真实账号）----
        d.get(BASE + '/login')
        wait_ready(d)
        time.sleep(2)
        u = d.find_element(By.ID, 'username')
        p = d.find_element(By.ID, 'password')
        u.clear(); u.send_keys('接线测试_admin')
        p.clear(); p.send_keys('JieXianTest@2026')
        d.find_element(By.XPATH, "//button[contains(., '登')]").click()
        WebDriverWait(d, 30).until(lambda x: '/login' not in x.current_url)
        time.sleep(2)
        print('logged in:', d.current_url)

        # ---- 打开任务详情 ----
        mark = len(d.get_log('performance'))
        d.get(BASE + '/tasks/%d' % TASK_ID)
        wait_ready(d)
        # 等待关联用例卡片渲染（1737 张，渲染较慢）
        WebDriverWait(d, 120).until(
            lambda x: x.execute_script(
                "return !!document.querySelector('div[class*=\"xl:grid-cols-3\"]')"))
        time.sleep(8)
        out['api']['task_detail'] = perf_api(d, mark)
        print('api:', out['api']['task_detail'])
        out['url'] = d.current_url

        js_measure = r"""
        const grid = document.querySelector('div[class*="xl:grid-cols-3"]');
        const cards = grid ? Array.from(grid.children) : [];
        const cs = grid ? getComputedStyle(grid) : null;
        const cols = cs ? cs.gridTemplateColumns.split(' ').filter(Boolean) : [];
        // 找最近的滚动容器
        let sc = grid, chain = [];
        while (sc && sc !== document.body) {
          const s = getComputedStyle(sc);
          if (/(auto|scroll)/.test(s.overflowY)) chain.push({
            tag: sc.tagName, cls: (sc.className||'').toString().slice(0,80),
            scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight
          });
          sc = sc.parentElement;
        }
        const de = document.scrollingElement || document.documentElement;
        // 单个卡片高度
        const h0 = cards.length ? cards[0].getBoundingClientRect().height : 0;
        // 是否出现分页控件（关联用例区域附近）
        const card = grid ? grid.closest('section, div[class*=card], .card') : null;
        const pagers = Array.from(document.querySelectorAll('button')).filter(b =>
          /下一页|上一页|加载更多/.test((b.textContent||'')) && b.offsetParent !== null);
        return {
          gridClass: grid ? (grid.className||'').toString() : null,
          gridColumns: cols, columnCount: cols.length,
          cardCount: cards.length, firstCardHeight: h0,
          docScrollHeight: de.scrollHeight, docClientHeight: de.clientHeight,
          scrollChain: chain,
          pagerButtons: pagers.map(b => (b.textContent||'').trim()),
          bodyText: document.body.innerText.slice(0, 1200)
        };
        """
        m = d.execute_script(js_measure)
        out['sizes'] = m
        print('sizes:', json.dumps({k: v for k, v in m.items() if k != 'bodyText'},
                                   ensure_ascii=False))

        shot(d, '01_tasks526_flat_light')

        # ---- 摘要「评估失败」计数 ----
        summary = d.execute_script(r"""
        const cells = Array.from(document.querySelectorAll('div')).filter(el => {
          const t = el.innerText || '';
          return el.children.length === 2 && /^\d+\n(已完成|进行中|待执行|执行失败|评估失败)$/.test(t.trim());
        }).map(el => el.innerText.trim().replace('\n', ':'));
        return cells;
        """)
        out['summary_cells'] = summary
        print('summary:', summary)

        # ---- 状态筛选选项 ----
        trig = d.find_element(By.CSS_SELECTOR, "[aria-label='状态筛选']")
        d.execute_script('arguments[0].scrollIntoView({block:"center"});', trig)
        d.execute_script('arguments[0].click();', trig)
        WebDriverWait(d, 20).until(
            lambda x: len(x.find_elements(By.CSS_SELECTOR, '[role=option]')) > 0)
        time.sleep(1)
        opts = [e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, '[role=option]')
                if e.is_displayed()]
        out['options'] = opts
        print('status options:', opts)
        shot(d, '02_status_select_open_light')

        # 选「已失败」看过滤结果条数
        def pick_opt(text):
            for e in d.find_elements(By.CSS_SELECTOR, '[role=option]'):
                if e.is_displayed() and e.text.strip() == text:
                    d.execute_script('arguments[0].click();', e)
                    return True
            return False

        picked = pick_opt('已失败')
        time.sleep(5)
        out['checks']['pick_failed'] = picked
        out['checks']['filtered_count_failed'] = d.execute_script(
            "const g=document.querySelector('div[class*=\"xl:grid-cols-3\"]');return g?g.children.length:-1")
        print('after 已失败 filter, cards =', out['checks']['filtered_count_failed'])
        shot(d, '03_filter_failed_light')

        # 恢复全部状态
        d.execute_script('arguments[0].click();', trig)
        time.sleep(0.8)
        pick_opt('全部状态')
        time.sleep(4)

        # ---- 深色截图 ----
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('dark'));")
        d.get(BASE + '/tasks/%d' % TASK_ID)
        wait_ready(d)
        WebDriverWait(d, 120).until(
            lambda x: x.execute_script(
                "return !!document.querySelector('div[class*=\"xl:grid-cols-3\"]')"))
        time.sleep(8)
        shot(d, '04_tasks526_flat_dark')
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('light'));")
        d.get(BASE + '/tasks/%d' % TASK_ID)
        wait_ready(d)
        time.sleep(10)

        # ---- 滚到底部测试 ----
        bottom = d.execute_script(r"""
        const g = document.querySelector('div[class*="xl:grid-cols-3"]');
        const de = document.scrollingElement || document.documentElement;
        const before = de.scrollTop;
        const t0 = performance.now();
        de.scrollTop = de.scrollHeight;
        const dt = performance.now() - t0;
        return {before, after: de.scrollTop, scrollHeight: de.scrollHeight,
                clientHeight: de.clientHeight, ms: Math.round(dt),
                lastVisible: !!g && g.getBoundingClientRect().bottom <= window.innerHeight};
        """)
        out['sizes']['scroll_to_bottom'] = bottom
        print('scroll bottom:', bottom)
        shot(d, '05_after_scroll_bottom_light')

        out['health_end'] = json.loads(
            urllib.request.urlopen(BACK + '/health', timeout=10).read().decode())
        print('health end:', out['health_end'])
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        out['errors'].append('%s: %s' % (type(exc).__name__, exc))
        try:
            shot(d, '99_error')
        except Exception:
            pass
    finally:
        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
        print('\nreport ->', os.path.join(ART, 'report.json'))


if __name__ == '__main__':
    main()
