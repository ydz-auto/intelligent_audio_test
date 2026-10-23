# -*- coding: utf-8 -*-
"""INT-1492 验收（测试工程师）：任务详情关联用例 行式列表 / 虚拟滚动 / 执行失败·评估失败筛选。

环境：本 run dev server 5320（临时 rsbuild 配置）→ 真实库栈网关 5700（主库 intelligent_audio_test，
AUTH_MODE=dev，表单登录 接线测试_admin）。任务 526 = 1737 条关联用例。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5320')
TASK_ID = os.environ.get('TASK_ID', '526')
TASK_CASE_TOTAL = int(os.environ.get('TASK_CASE_TOTAL', '1737'))
USER = os.environ.get('REAL_USER', '接线测试_admin')
PASSWORD = os.environ.get('REAL_PASSWORD', 'JieXianTest@2026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', os.environ.get('ART_DIR', 'int1492_live'))
THEME_KEY = 'iatp:theme:v1:mode'

results = []


def check(name, ok, detail=''):
    results.append((name, ok, detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + (' | ' + detail if detail else ''))
    return ok


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import shutil
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv = os.environ.get('CHROMEDRIVER', '')
    if not drv and chrome_major and os.path.isdir(cache_root):
        cands = [os.path.join(cache_root, v, 'chromedriver.exe') for v in os.listdir(cache_root)]
        cands = [c for c in cands if os.path.isfile(c)]
        if cands:
            drv = sorted(cands)[-1]
    if not drv:
        drv = shutil.which('chromedriver') or ''
    service = Service(drv) if drv else Service()
    return webdriver.Chrome(service=service, options=options)


def js(driver, script, *args):
    return driver.execute_script(script, *args)


def auth_mode():
    import urllib.request
    try:
        with urllib.request.urlopen(BASE + '/api/v1/auth/mode', timeout=10) as r:
            return json.loads(r.read().decode()).get('auth_mode') or ''
    except Exception:
        return ''


def login(driver):
    """AUTH_MODE=dev 走表单登录（RSA 加密由前端完成）；off 模式直接放行。"""
    if auth_mode() != 'dev':
        return
    driver.get(BASE + '/login')
    WebDriverWait(driver, 20).until(lambda d: d.find_elements(By.ID, 'username'))
    driver.find_element(By.ID, 'username').send_keys(USER)
    driver.find_element(By.ID, 'password').send_keys(PASSWORD)
    js(driver, "document.querySelector(\"button[type='submit']\").click();")
    WebDriverWait(driver, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(0.5)


def wait_rows(driver, timeout=60):
    WebDriverWait(driver, timeout).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']")
    )


def open_task(driver, dark=False, login_first=False):
    if login_first:
        login(driver)
        driver.get(BASE + '/')  # 确保落在本站源下，localStorage 可写
    js(driver, "window.localStorage.setItem(arguments[0], arguments[1]);",
       THEME_KEY, 'dark' if dark else 'light')
    driver.get(BASE + '/tasks/' + TASK_ID)
    wait_rows(driver)
    time.sleep(1.0)


def open_status_filter(driver):
    trigger = driver.find_element(By.CSS_SELECTOR, "[aria-label='状态筛选']")
    js(driver, "arguments[0].click();", trigger)
    try:
        # 等选项真正渲染出文案（关掉后残留的空文本 option 节点会误命中）
        WebDriverWait(driver, 10).until(
            lambda d: any(o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"))
        )
    except Exception:
        raise AssertionError('状态筛选未展开：' + str([o.text for o in driver.find_elements(By.CSS_SELECTOR, "[role='option']")]))
    time.sleep(0.3)
    return trigger


def pick_status(driver, label, shot_name=None):
    open_status_filter(driver)
    if shot_name:
        shot(driver, shot_name)
    opts = [o for o in driver.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip()]
    target = None
    for o in opts:
        if o.text.strip() == label:
            target = o
            break
    if target is None:
        raise AssertionError('状态筛选项未找到：' + label + ' / 现有：' + str([o.text for o in opts]))
    js(driver, "arguments[0].click();", target)
    time.sleep(0.8)


def filter_options(driver):
    open_status_filter(driver)
    labels = [o.text.strip() for o in driver.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip()]
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)
    return labels


def count_rows(driver):
    return len(driver.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']"))


def count_badge(driver):
    els = driver.find_elements(By.CSS_SELECTOR, "[data-slot='case-count-badge']")
    return els[0].text.strip() if els else ''


def list_metrics(driver):
    return js(driver, """
        const el = document.querySelector("[data-testid='task-case-list']");
        if (!el) return null;
        return {
          scrollHeight: el.scrollHeight,
          clientHeight: el.clientHeight,
          scrollTop: el.scrollTop,
          domRows: document.querySelectorAll("[data-testid='task-case-row']").length,
          spacerHeight: (document.querySelector("[data-testid='task-case-list-spacer']")||{}).clientHeight || 0
        };
    """)


def network_task_request(driver):
    hits = []
    for entry in driver.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg['params']['response']
        url = resp.get('url', '')
        if '/api/v1/tasks/' + TASK_ID in url and 'tasks/' + TASK_ID + '?' not in url:
            hits.append((url, resp.get('status')))
    return hits


def shot(driver, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name)
    driver.save_screenshot(path)
    print('SHOT ' + path)
    return path


def main():
    driver = _driver()
    try:
        # ---------- 浅色（首次登录） ----------
        open_task(driver, dark=False, login_first=True)
        print('URL', driver.current_url)
        # 先取任务详情请求（页面加载已发生），再清空日志避免登录噪声混入
        reqs = network_task_request(driver)
        driver.get_log('performance')

        m = list_metrics(driver)
        check('列表容器受控 max-h 400px', bool(m) and m['clientHeight'] <= 420,
              'clientHeight=%s' % (m or {}).get('clientHeight'))
        check('虚拟滚动：DOM 行数远小于总数', m and m['domRows'] <= 60, 'domRows=%s' % (m or {}).get('domRows'))
        check('内层占位高度 = 条数 × 54px', m and m['spacerHeight'] >= TASK_CASE_TOTAL * 54 - 10,
              'spacer=%s' % (m or {}).get('spacerHeight'))
        check('计数徽章 = %d' % TASK_CASE_TOTAL, count_badge(driver).strip() == str(TASK_CASE_TOTAL),
              'badge=%s' % count_badge(driver))

        headers = [h.text.strip() for h in driver.find_elements(By.CSS_SELECTOR, "[role='columnheader']")]
        check('行式表头 6 列', headers == ['用例名称', '执行状态', '评估状态', '耗时', '轮次', '操作'], str(headers))
        first_row_cells = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            return r ? Array.from(r.querySelectorAll("[role='cell']")).length : 0;
        """)
        check('行内 6 单元格', first_row_cells == 6, 'cells=%s' % first_row_cells)
        row_h = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            return r ? Math.round(r.getBoundingClientRect().height) : 0;
        """)
        check('行高 54px', row_h == 54, 'height=%s' % row_h)
        widths = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            if (!r) return null;
            return Array.from(r.querySelectorAll("[role='cell']")).map(c=>Math.round(c.getBoundingClientRect().width));
        """)
        check('行内 6 单元格均可见（宽 > 0）', bool(widths) and all(w > 0 for w in widths), str(widths))

        eval_labels = js(driver, """
            return Array.from(document.querySelectorAll("[data-column='evaluation'] [data-slot='status-badge']")).slice(0,5).map(e=>e.textContent.trim());
        """)
        check('评估列徽章 = 评估失败（非「已失败」）',
              bool(eval_labels) and all('评估失败' == t for t in eval_labels), str(eval_labels))
        exec_labels = js(driver, """
            return Array.from(document.querySelectorAll("[data-column='execution'] [data-slot='status-badge']")).slice(0,5).map(e=>e.textContent.trim());
        """)
        print('INFO execution badges:', exec_labels)

        # ---------- 滚到底 ----------
        js(driver, "const el=document.querySelector(\"[data-testid='task-case-list']\"); el.scrollTop = el.scrollHeight;")
        time.sleep(0.8)
        m2 = list_metrics(driver)
        last_rows = js(driver, """
            return Array.from(document.querySelectorAll("[data-testid='task-case-row']")).slice(-2).map(r=>r.getAttribute('data-case-id'));
        """)
        check('滚到底：scrollTop+clientHeight ≥ scrollHeight',
              m2 and m2['scrollTop'] + m2['clientHeight'] >= m2['scrollHeight'] - 2,
              'scrollTop=%s client=%s scrollH=%s' % (m2['scrollTop'], m2['clientHeight'], m2['scrollHeight']))
        check('底部仍只渲染窗口行', m2 and m2['domRows'] <= 60, 'domRows=%s' % m2['domRows'])
        check('底部行为真实 case_id', bool(last_rows) and all(last_rows), str(last_rows))
        shot(driver, 'light_scrolled_bottom.png')

        # ---------- 搜索 ----------
        keyword = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            const b = r ? r.querySelector('button') : null;
            return b ? b.textContent.trim() : '';
        """)
        frag = (keyword.split('_')[-1][:6] if keyword else '') or 'JG'
        box = driver.find_element(By.CSS_SELECTOR, "[aria-label='搜索用例']")
        box.click()
        box.send_keys(Keys.CONTROL, 'a')
        box.send_keys(frag)
        time.sleep(0.9)
        badge_search = count_badge(driver)
        check('搜索后计数显示「命中 / 总数」', '/' in badge_search, 'badge=%s frag=%s' % (badge_search, frag))
        shot(driver, 'light_search.png')
        box.send_keys(Keys.CONTROL, 'a')
        box.send_keys(Keys.DELETE)
        time.sleep(0.9)
        check('清空搜索恢复 %d' % TASK_CASE_TOTAL, count_badge(driver).strip() == str(TASK_CASE_TOTAL),
              'badge=%s' % count_badge(driver))

        # ---------- 状态筛选 ----------
        labels = filter_options(driver)
        check('筛选项含 执行失败 / 评估失败',
              '执行失败' in labels and '评估失败' in labels, str(labels))
        shot(driver, 'light_status_filter_options.png')

        pick_status(driver, '评估失败')
        badge_eval = count_badge(driver)
        check('筛选 评估失败 = %d' % TASK_CASE_TOTAL, badge_eval.strip() == str(TASK_CASE_TOTAL), 'badge=%s' % badge_eval)
        shot(driver, 'light_filter_evaluation_failed.png')

        pick_status(driver, '执行失败')
        empty = driver.find_elements(By.XPATH, "//p[contains(text(),'暂无关联用例')]")
        check('筛选 执行失败 = 0 且空态', bool(empty), 'badge=%s' % count_badge(driver))
        shot(driver, 'light_filter_execution_failed.png')

        pick_status(driver, '全部状态')
        time.sleep(0.6)
        shot(driver, 'light_case_rows.png')

        # ---------- Network ----------
        ok_net = any(str(s) == '200' for _, s in reqs)
        check('Network：GET /api/v1/tasks/%s → 200' % TASK_ID, ok_net, str(reqs[-3:]))
        js(driver, "const el=document.querySelector(\"[data-testid='task-case-list']\"); el.scrollTop = 0;")
        time.sleep(0.5)

        # ---------- 标签视图 ----------
        js(driver, """const t=Array.from(document.querySelectorAll("[role='tab']")).find(e=>e.textContent.trim()==='标签'); if(t) t.click();""")
        time.sleep(1.0)
        grouped = driver.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-grouped-list']")
        check('标签视图组内行式列表存在', bool(grouped), 'groupsContainer=%d' % len(grouped))
        shot(driver, 'light_tag_view.png')
        js(driver, """const t=Array.from(document.querySelectorAll("[role='tab']")).find(e=>e.textContent.trim()==='平铺'); if(t) t.click();""")
        time.sleep(0.8)

        # ---------- 深色 ----------
        driver2 = _driver()
        try:
            open_task(driver2, dark=True, login_first=True)
            shot(driver2, 'dark_case_rows.png')
            ok_dark = js(driver2, "return document.documentElement.className;")
            check('深色模式生效', 'dark' in (ok_dark or ''), str(ok_dark))
            pick_status(driver2, '评估失败')
            check('深色下 评估失败 = %d' % TASK_CASE_TOTAL,
                  count_badge(driver2).strip() == str(TASK_CASE_TOTAL), 'badge=%s' % count_badge(driver2))
            shot(driver2, 'dark_filter_evaluation_failed.png')
        finally:
            driver2.quit()
    finally:
        driver.quit()

    failed = [r for r in results if not r[1]]
    print('\n===== INT-1492 实测：%d 项，失败 %d =====' % (len(results), len(failed)))
    for name, ok, detail in failed:
        print('  FAIL', name, detail)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
