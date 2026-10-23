# -*- coding: utf-8 -*-
"""INT-1492 任务详情关联用例浏览器实测：行式列表 / 虚拟滚动 / 执行失败·评估失败筛选。

连本 run 的 dev server（默认 5312）→ docker 真实库栈网关 15000（AUTH_MODE=off）。
证据：浅/深色截图 + Network（performance log 解析 GET /api/v1/tasks/526）+ 断言计数。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5312')
TASK_ID = os.environ.get('TASK_ID', '526')
TASK_CASE_TOTAL = int(os.environ.get('TASK_CASE_TOTAL', '1737'))
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1492')
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


def wait_rows(driver, timeout=40):
    WebDriverWait(driver, timeout).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']")
    )


def js(driver, script, *args):
    return driver.execute_script(script, *args)


def open_task(driver, dark=False):
    driver.get(BASE + '/')
    # 主题：iatp:theme:v1:mode（next-themes 非默认 key，CLAUDE 记忆）
    js(driver, "window.localStorage.setItem(arguments[0], arguments[1]);",
       THEME_KEY, 'dark' if dark else 'light')
    driver.get(BASE + '/tasks/' + TASK_ID)
    wait_rows(driver)
    time.sleep(1.0)


def open_status_filter(driver):
    """打开「状态筛选」Select（base-ui：JS click 触发 + 等选项渲染）"""
    trigger = driver.find_element(By.CSS_SELECTOR, "[aria-label='状态筛选']")
    js(driver, "arguments[0].click();", trigger)
    WebDriverWait(driver, 10).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[role='option']")
    )
    return trigger


def pick_status(driver, label, shot_name=None):
    open_status_filter(driver)
    if shot_name:
        shot(driver, shot_name)
    opts = driver.find_elements(By.CSS_SELECTOR, "[role='option']")
    target = None
    for o in opts:
        if o.text.strip() == label:
            target = o
            break
    if target is None:
        raise AssertionError('状态筛选项未找到：' + label + ' / 现有：' + str([o.text for o in opts]))
    js(driver, "arguments[0].click();", target)
    time.sleep(0.8)


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
        if '/api/v1/tasks/' + TASK_ID in resp.get('url', '') and 'tasks/' + TASK_ID + '?' not in resp.get('url', ''):
            hits.append((resp.get('url'), resp.get('status')))
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
        # ---------- 浅色 ----------
        open_task(driver, dark=False)

        m = list_metrics(driver)
        check('列表容器存在（max-h 受控 400px）', bool(m) and m['clientHeight'] <= 420,
              'clientHeight=%s' % (m or {}).get('clientHeight'))
        check('虚拟滚动生效：DOM 行数远小于 %d 条' % TASK_CASE_TOTAL,
              m and m['domRows'] <= 60, 'domRows=%s' % (m or {}).get('domRows'))
        check('内层占位高度 = 条数 × 54px', m and m['spacerHeight'] >= TASK_CASE_TOTAL * 54 - 10,
              'spacer=%s' % (m or {}).get('spacerHeight'))

        # 行式布局：表头 6 列 + 行内 6 单元格
        headers = [h.text.strip() for h in driver.find_elements(By.CSS_SELECTOR, "[role='columnheader']")]
        check('行式表头 = 用例名称/执行状态/评估状态/耗时/轮次/操作',
              headers == ['用例名称', '执行状态', '评估状态', '耗时', '轮次', '操作'], str(headers))
        first_row_cells = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            return r ? Array.from(r.querySelectorAll("[role='cell']")).length : 0;
        """)
        check('行内 6 个单元格（名称/执行/评估/耗时/轮次/操作）', first_row_cells == 6, 'cells=%s' % first_row_cells)
        row_h = js(driver, """
            const r = document.querySelector("[data-testid='task-case-row']");
            return r ? Math.round(r.getBoundingClientRect().height) : 0;
        """)
        check('行高 54px（V9.7.10 caseItemHeight 口径）', row_h == 54, 'height=%s' % row_h)

        # 状态徽章区分执行失败/评估失败
        eval_labels = js(driver, """
            return Array.from(document.querySelectorAll("[data-column='evaluation'] [data-slot='status-badge']")).slice(0,5).map(e=>e.textContent.trim());
        """)
        check('评估列徽章显示「评估失败」而非「已失败」',
              bool(eval_labels) and all('评估失败' == t for t in eval_labels), str(eval_labels))

        # 滚动到底：可见行切到列表尾部，DOM 行数仍受控
        js(driver, "const el=document.querySelector(\"[data-testid='task-case-list']\"); el.scrollTop = el.scrollHeight;")
        time.sleep(0.6)
        m2 = list_metrics(driver)
        last_rows = js(driver, """
            return Array.from(document.querySelectorAll("[data-testid='task-case-row']")).slice(-2).map(r=>r.getAttribute('data-case-id'));
        """)
        check('滚到列表底部：scrollTop 到达底部附近',
              m2 and m2['scrollTop'] + m2['clientHeight'] >= m2['scrollHeight'] - 2,
              'scrollTop=%s/%s' % (m2['scrollTop'], m2['scrollHeight']))
        check('底部仍只渲染可视窗口行（虚拟滚动未退化）', m2 and m2['domRows'] <= 60, 'domRows=%s' % m2['domRows'])
        check('底部行有真实 case_id', bool(last_rows) and all(last_rows), str(last_rows))
        shot(driver, 'int1492_light_scrolled_bottom.png')

        # 搜索：按名称关键字
        keyword = js(driver, """
            const rows = Array.from(document.querySelectorAll("[data-testid='task-case-row']"));
            const t = rows[0] ? rows[0].querySelector('button') : null;
            return t ? t.textContent.trim() : '';
        """)
        frag = keyword.split('_')[-1][:6] if keyword else 'JG'
        box = driver.find_element(By.CSS_SELECTOR, "[aria-label='搜索用例']")
        box.clear()
        box.send_keys(frag)
        time.sleep(0.8)
        badge_search = count_badge(driver)
        check('搜索后计数徽章显示「命中 / 总数」', '/' in badge_search, 'badge=%s keyword=%s' % (badge_search, frag))
        shot(driver, 'int1492_light_search.png')

        # 清空搜索（受控输入：全选 + 删除，clear() 不一定同步 React 状态）
        box.send_keys(Keys.CONTROL, 'a')
        box.send_keys(Keys.DELETE)
        time.sleep(0.8)
        check('清空搜索后恢复全部用例', count_badge(driver).replace(' ', '') in (str(TASK_CASE_TOTAL), '%d / %d' % (TASK_CASE_TOTAL, TASK_CASE_TOTAL)),
              'badge=%s' % count_badge(driver))

        # 状态筛选：评估失败 → 1737 条
        pick_status(driver, '评估失败', shot_name='int1492_light_status_filter_options.png')
        badge_eval = count_badge(driver)
        check('筛选「评估失败」得到 %d 条' % TASK_CASE_TOTAL,
              badge_eval.replace(' ', '') == '%d / %d' % (TASK_CASE_TOTAL, TASK_CASE_TOTAL) or badge_eval.strip() == str(TASK_CASE_TOTAL),
              'badge=%s' % badge_eval)
        shot(driver, 'int1492_light_filter_evaluation_failed.png')

        # 状态筛选：执行失败 → 0 条（任务 526 执行状态 pending）
        pick_status(driver, '执行失败')
        empty = driver.find_elements(By.XPATH, "//p[contains(text(),'暂无关联用例')]")
        check('筛选「执行失败」= 0 条并显示空态', bool(empty), 'badge=%s' % count_badge(driver))
        shot(driver, 'int1492_light_filter_execution_failed.png')

        # 回到 全部状态 + 浅色截图
        pick_status(driver, '全部状态')
        time.sleep(0.6)
        shot(driver, 'int1492_light_case_rows.png')

        # Network：GET /api/v1/tasks/526 200
        reqs = network_task_request(driver)
        ok_net = any(str(s) == '200' for _, s in reqs)
        check('Network：GET /api/v1/tasks/%s → 200' % TASK_ID, ok_net, str(reqs[-3:]))

        # ---------- 深色 ----------
        driver2 = _driver()
        try:
            open_task(driver2, dark=True)
            shot(driver2, 'int1492_dark_case_rows.png')
            pick_status(driver2, '评估失败')
            shot(driver2, 'int1492_dark_filter_evaluation_failed.png')
            ok_dark = js(driver2, "return document.documentElement.className;")
            check('深色模式生效', 'dark' in (ok_dark or ''), str(ok_dark))
            check('深色下筛选「评估失败」计数正确',
                  count_badge(driver2).replace(' ', '') in ('%d / %d' % (TASK_CASE_TOTAL, TASK_CASE_TOTAL), str(TASK_CASE_TOTAL)),
                  'badge=%s' % count_badge(driver2))
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
