# -*- coding: utf-8 -*-
"""INT-1478 复走：INT-1492 集成后（15173 新镜像）对负责人三点的回归复核。

三点：
1) 关联用例平铺 = 紧凑行式列表（不再是 3 列 CaseCard 卡片网格）；
2) 虚拟滚动：只渲染可视窗口行，max-h 400px，可滚动到末条；
3) 状态筛选补「执行失败 / 评估失败」独立项，且对任务 526 有效（评估失败 1737 / 执行失败 0）。

输出：artifacts/int1478_recheck/report.json + 浅/深截图。
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

BASE = 'http://127.0.0.1:15173'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1478_recheck')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
TASK = 526
out = {'task': TASK, 'base': BASE}
os.makedirs(ART, exist_ok=True)


def js(d, code, *args):
    return d.execute_script(code, *args)


def read_list_state(d):
    return js(d, r"""
      const list = document.querySelector("[data-testid='task-case-list']");
      const spacer = document.querySelector("[data-testid='task-case-list-spacer']");
      const rows = document.querySelectorAll("[data-testid='task-case-row']");
      const empty = Array.from(document.querySelectorAll('p'))
        .map(p => p.textContent.trim()).find(t => t === '暂无关联用例');
      if (!list) return {listPresent: false, emptyText: empty || null};
      const cs = getComputedStyle(list);
      return {
        listPresent: true,
        emptyText: empty || null,
        rowsRendered: rows.length,
        spacerHeight: spacer ? Math.round(parseFloat(spacer.style.height)) : null,
        scrollHeight: list.scrollHeight,
        clientHeight: list.clientHeight,
        scrollTop: Math.round(list.scrollTop),
        maxHeight: cs.maxHeight,
        overflowY: cs.overflowY,
        firstRowText: rows.length ? rows[0].innerText.replace(/\n/g, ' | ') : null,
        lastRowText: rows.length ? rows[rows.length - 1].innerText.replace(/\n/g, ' | ') : null,
      };
    """)


def open_status_select(d):
    trig = d.find_element(By.CSS_SELECTOR, "button[aria-label='状态筛选']")
    js(d, "arguments[0].click();", trig)
    time.sleep(0.8)
    return [e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")]


def pick_option(d, label):
    for e in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if e.text.strip() == label:
            js(d, "arguments[0].click();", e)
            time.sleep(2.0)
            return True
    return False


def main():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_recheck_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(180)
    d.set_script_timeout(180)
    try:
        # --- 登录 ---
        d.get(BASE + '/tasks/daily')
        time.sleep(4)
        out['auth_mode_off'] = '/login' not in d.current_url
        if '/login' in d.current_url:
            d.find_element(By.ID, 'username').send_keys('接线测试_admin')
            d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            d.find_element(By.XPATH, "//button[contains(., '登')]").click()
            WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
            time.sleep(2)
        out['bundle'] = js(d, "return (document.querySelector('script[src*=\"index.\"]')||{}).src || ''")

        # --- 打开任务详情，记录网络 ---
        js(d, "localStorage.setItem('iatp:theme:v1:mode','light');")
        d.get_log('performance')
        mark = len(d.get_log('performance'))
        d.get(BASE + '/tasks/%d' % TASK)
        WebDriverWait(d, 180).until(lambda x: js(
            x, "return !!document.querySelector(\"[data-testid='task-case-list']\") "
               "|| !!Array.from(document.querySelectorAll('p')).find(p=>p.textContent.trim()==='暂无关联用例')"))
        time.sleep(6)

        sent, recv = [], []
        for m in d.get_log('performance')[mark:]:
            try:
                msg = json.loads(m['message'])['message']
            except Exception:
                continue
            if msg.get('method') == 'Network.requestWillBeSent':
                u = msg['params']['request']['url']
                if str(TASK) in u:
                    sent.append(msg['params']['request']['method'] + ' ' + u.replace(BASE, ''))
            if msg.get('method') == 'Network.responseReceived':
                r = msg['params']['response']
                if str(TASK) in r['url'] and '/api/' in r['url']:
                    recv.append({'status': r['status'], 'url': r['url'].replace(BASE, ''),
                                 'mime': r.get('mimeType')})
        out['requests'] = list(dict.fromkeys(sent))
        out['responses'] = recv

        # --- 页面摘要（进度卡计数） ---
        out['summary_badges'] = js(d, r"""
          const txt = document.body.innerText;
          const nums = {};
          const re = /(\d+)\s*\n?\s*(已完成|进行中|待执行|执行失败|评估失败)/g;
          let m;
          while ((m = re.exec(txt)) !== null) { nums[m[2]] = Number(m[1]); }
          const i = txt.indexOf('总进度');
          return {...nums, 进度卡片段: i >= 0 ? txt.slice(i, i + 160) : null};
        """)

        # --- 点1/2：行式列表 + 虚拟滚动 ---
        st = read_list_state(d)
        out['flat_default'] = st
        out['card_grid_present'] = js(d, r"""
          const list = document.querySelector("[data-testid='task-case-list']");
          if (!list) return null;
          const nodes = Array.from(document.querySelectorAll('div'));
          const grid3 = nodes.filter(n => {
            const c = getComputedStyle(n).gridTemplateColumns;
            return c && c.split(' ').length >= 3 && n.querySelector('[data-testid="task-case-row"]') == null
                   && n.innerText.includes('用例');
          }).length;
          const rowH = document.querySelector("[data-testid='task-case-row']")
                     ? Math.round(document.querySelector("[data-testid='task-case-row']").getBoundingClientRect().height) : null;
          return {grid3Containers: grid3, firstRowHeight: rowH,
                  hasLegacyGridClass: !!document.querySelector("[class*='xl:grid-cols-3']")};
        """)
        d.save_screenshot(os.path.join(ART, '01_flat_rows_light.png'))

        # 滚到底：验证可到末条
        js(d, r"""
          const l = document.querySelector("[data-testid='task-case-list']");
          l.scrollTop = l.scrollHeight;
        """)
        time.sleep(2.0)
        out['flat_scrolled_bottom'] = read_list_state(d)
        d.save_screenshot(os.path.join(ART, '02_flat_bottom_light.png'))
        js(d, "const l=document.querySelector(\"[data-testid='task-case-list']\"); if(l) l.scrollTop=0;")
        time.sleep(1.0)

        # --- 点3：状态筛选 ---
        opts = open_status_select(d)
        out['status_options'] = opts
        d.save_screenshot(os.path.join(ART, '03_status_options_light.png'))
        out['pick_evaluation_failed'] = pick_option(d, '评估失败')
        out['filter_evaluation_failed'] = read_list_state(d)
        out['filter_eval_trigger_label'] = js(d, r"""
          const b = document.querySelector("button[aria-label='状态筛选']");
          return b ? b.innerText.trim() : null;
        """)
        d.save_screenshot(os.path.join(ART, '04_filter_evaluation_failed_light.png'))

        open_status_select(d)
        out['pick_execution_failed'] = pick_option(d, '执行失败')
        out['filter_execution_failed'] = read_list_state(d)
        d.save_screenshot(os.path.join(ART, '05_filter_execution_failed_light.png'))

        open_status_select(d)
        pick_option(d, '全部状态')
        time.sleep(1.0)
        out['reset_all'] = read_list_state(d)

        # --- 页面内 fetch 交叉核对 ---
        out['fetch'] = d.execute_async_script(r"""
          const ar = arguments[arguments.length - 1];
          fetch('/api/v1/tasks/526', {headers: {'Accept': 'application/json'}})
            .then(r => r.json().then(j => {
              const data = j.data || j;
              const cases = data.cases || [];
              const ev = {}, ex = {};
              for (const c of cases) {
                ev[c.evaluation_status] = (ev[c.evaluation_status] || 0) + 1;
                ex[c.execution_status] = (ex[c.execution_status] || 0) + 1;
              }
              ar({status: r.status, total_cases: data.total_cases, cases: cases.length,
                  evaluation_status_counts: ev, execution_status_counts: ex,
                  last_case: cases.length ? (cases[cases.length - 1].case_id || cases[cases.length - 1].case_name) : null});
            }))
            .catch(e => ar({error: String(e)}));
        """)

        # --- 深色 ---
        js(d, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.refresh()
        WebDriverWait(d, 300).until(lambda x: js(
            x, "return !!document.querySelector(\"[data-testid='task-case-list']\") "
               "|| !!Array.from(document.querySelectorAll('p')).find(p=>p.textContent.trim()==='暂无关联用例')"))
        time.sleep(5)
        out['dark'] = js(d, r"""
          return {htmlClass: document.documentElement.className,
                  bodyBg: getComputedStyle(document.body).backgroundColor,
                  rows: document.querySelectorAll("[data-testid='task-case-row']").length};
        """)
        d.save_screenshot(os.path.join(ART, '06_flat_rows_dark.png'))
        # 深色下再验一次评估失败筛选
        open_status_select(d)
        pick_option(d, '评估失败')
        out['dark_filter_eval'] = read_list_state(d)
        d.save_screenshot(os.path.join(ART, '07_filter_evaluation_failed_dark.png'))
        js(d, "localStorage.setItem('iatp:theme:v1:mode','light');")
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        out['error'] = '%s: %s' % (type(exc).__name__, exc)
    finally:
        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        d.quit()
        print(json.dumps(out, ensure_ascii=False, indent=2)[:8000])
        print('report.json written to', ART)


if __name__ == '__main__':
    main()
