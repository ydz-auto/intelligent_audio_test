# -*- coding: utf-8 -*-
"""INT-2176 覆盖 7/8/9：报告阅读目录常驻、轮次轴与评分指标一致、多轮结果源判定、
二次对比报告统计字段数组渲染（docker 15173 + 15000 真实栈，只读）。

产出：tests/ui/artifacts/int2176/report/
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000/api/v1'
USER, PWD = '接线测试_admin', 'JieXianTest@2026'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176', 'report')
TOKEN = open(os.path.join(HERE, 'artifacts', 'int2176', 'token.txt'), encoding='utf-8').read().strip()
RESULT = {}

JS_VIS = "const vis=x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0;};"


def api(method, path, body=None, tries=4):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request(API + path, data=data, method=method,
                                       headers={'Authorization': 'Bearer ' + TOKEN,
                                                'Content-Type': 'application/json'})
            with urllib.request.urlopen(r, timeout=180) as resp:
                raw = resp.read().decode('utf-8')
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace')
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw[:300]
        except Exception:
            time.sleep(2)
    raise RuntimeError('api failed ' + path)


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ['--headless=new', '--window-size=1680,1050', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run',
              '--no-default-browser-check']:
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    return d


def login(d):
    d.get(BASE + '/login')
    WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PWD)
    d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
    time.sleep(2)


def ready(d, wait=3.0):
    WebDriverWait(d, 50).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def body_text(d):
    return d.execute_script('return document.body.innerText')


def dialog_text(d):
    return d.execute_script(
        JS_VIS + "const ds=[...document.querySelectorAll('[role=dialog]')].filter(vis);"
        "return ds.length?ds[ds.length-1].innerText:''")


def shot(d, name, extra=None):
    p = os.path.join(ART, name)
    os.makedirs(p, exist_ok=True)
    d.save_screenshot(os.path.join(p, 'shot.png'))
    open(os.path.join(p, 'text.txt'), 'w', encoding='utf-8').write(body_text(d))
    open(os.path.join(p, 'console.log'), 'w', encoding='utf-8').write(
        '\n'.join(json.dumps(e, ensure_ascii=False) for e in d.get_log('browser')))
    if extra is not None:
        open(os.path.join(p, 'extra.json'), 'w', encoding='utf-8').write(
            json.dumps(extra, ensure_ascii=False, indent=2))


def set_theme(d, mode, url):
    d.get(url)
    ready(d, 3)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.refresh()
    ready(d, 4)
    return d.execute_script(
        "return {dark: document.documentElement.className.includes('dark'),"
        "bg: getComputedStyle(document.body).backgroundColor}")


def nav_rect(d):
    return d.execute_script(
        "const n=document.querySelector(\"nav[aria-label='本页目录']\");"
        "const c=document.querySelector('.report-view-container');"
        "if(!n||!c) return null;"
        "const nr=n.getBoundingClientRect(), cr=c.getBoundingClientRect();"
        "return {navTop:Math.round(nr.top), navBottom:Math.round(nr.bottom),"
        " contTop:Math.round(cr.top), contBottom:Math.round(cr.bottom),"
        " offsetFromContTop:Math.round(nr.top-cr.top), scrollTop:Math.round(c.scrollTop),"
        " scrollHeight:c.scrollHeight, clientHeight:c.clientHeight};")


def scroll_container(d, frac=1.0):
    return d.execute_script(
        "const c=document.querySelector('.report-view-container');"
        "c.scrollTop=(c.scrollHeight-c.clientHeight)*arguments[0];"
        "return c.scrollTop;", frac)


def open_first_case_detail(d):
    r = d.execute_script(
        JS_VIS + "const bs=[...document.querySelectorAll('button')].filter(vis)"
        ".filter(b=>(b.innerText||'').trim()==='详情');"
        "if(!bs.length) return {ok:false};"
        "bs[0].scrollIntoView({block:'center'}); bs[0].click(); return {ok:true, n:bs.length};")
    time.sleep(3)
    return r


def round_info(d):
    return d.execute_script(JS_VIS + """
      const vis2=vis;
      const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis2).pop();
      if(!dl) return {ok:false, why:'no dialog'};
      const bars=[...dl.querySelectorAll('[role=tablist]')].filter(vis2);
      return {ok:true, tabs: bars.map(b=>({label:b.getAttribute('aria-label'),
        items:[...b.querySelectorAll('[role=tab]')].filter(vis2).map(t=>({txt:(t.innerText||'').trim(), sel:t.getAttribute('aria-selected')}))}))};
    """)


def click_round(d, label):
    r = d.execute_script(JS_VIS + """
      const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
      if(!dl) return {ok:false};
      const bars=[...dl.querySelectorAll('[role=tablist]')].filter(b=>(b.getAttribute('aria-label')||'')==='轮次切换' && vis(b));
      if(!bars.length) return {ok:false, why:'no round bar'};
      const t=[...bars[0].querySelectorAll('[role=tab]')].find(x=>(x.innerText||'').trim()===arguments[0]);
      if(!t) return {ok:false, why:'no tab', items:[...bars[0].querySelectorAll('[role=tab]')].map(x=>x.innerText)};
      t.click(); return {ok:true};
    """, label)
    time.sleep(2.5)
    return r


def metric_rows(d):
    return d.execute_script(JS_VIS + """
      const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
      if(!dl) return null;
      // 评分指标区块 = 含「评分指标」标题后的第一张表
      const secs=[...dl.querySelectorAll('section')];
      const sec=secs.find(s=>(s.innerText||'').includes('评分指标'));
      if(!sec) return null;
      const rows=[...sec.querySelectorAll('table tr')].map(tr=>[...tr.querySelectorAll('th,td')].map(c=>(c.innerText||'').trim()));
      const activeTab=[...dl.querySelectorAll('[role=tablist][aria-label="轮次切换"] [role=tab]')].filter(vis).map(t=>({t:t.innerText.trim(),sel:t.getAttribute('aria-selected')}));
      return {rows: rows, tabs: activeTab};
    """)


def main():
    os.makedirs(ART, exist_ok=True)
    d = driver()
    try:
        login(d)

        # ---------- 9. 二次对比报告 ----------
        st561, r561 = api('GET', '/reports/561')
        d561 = (r561 or {}).get('data') or {}
        summ = d561.get('summary') or {}
        d.get(BASE + '/report/561')
        ready(d, 7)
        t561 = body_text(d)
        raw = summ.get('raw_data') or []
        metric_pairs = []
        if raw:
            for m in (raw[0].get('metrics') or [])[:5]:
                vals = m.get('values') or []
                v = vals[0] if vals else None
                metric_pairs.append({'metric': m.get('metric'), 'value': v})
        RESULT['secondary_comparison'] = {
            'api_status': st561,
            'api_summary_keys': sorted(summ.keys()),
            'raw_data_is_list': isinstance(raw, list),
            'raw_data_len': len(raw),
            'metric_sample': metric_pairs,
            'page_text_len': len(t561),
            'has_title': '二次对比' in t561,
            'has_device_stats': '设备与API统计' in t561,
            'has_case_compare': '按用例分组对比' in t561,
            'no_blank': len(t561) > 500,
            'rendered_contains_100pct': '100.0%' in t561,
            'snippet': t561[:400],
        }
        shot(d, '01-secondary-561-light')
        RESULT['secondary_dark'] = set_theme(d, 'dark', BASE + '/report/561')
        shot(d, '02-secondary-561-dark')
        RESULT['secondary_dark_has_title'] = '二次对比' in body_text(d)

        # ---------- 8. 报告阅读目录常驻（对比报告 567） ----------
        RESULT['theme_light'] = set_theme(d, 'light', BASE + '/report/567')
        ready(d, 5)
        before = nav_rect(d)
        top1 = scroll_container(d, 0.5)
        ready(d, 1.5)
        mid = nav_rect(d)
        top2 = scroll_container(d, 1.0)
        ready(d, 1.5)
        end = nav_rect(d)
        RESULT['reading_nav'] = {'before': before, 'mid': mid, 'end': end,
                                 'scroll_mid': top1, 'scroll_end': top2}
        shot(d, '03-comparison-567-bottom-light')

        # ---------- 7/8. 用例详情轮次轴（对比报告 567） ----------
        st567, r567 = api('POST', '/reports/567/cases/search', {'page': 1, 'page_size': 50})
        items = ((r567 or {}).get('data') or {}).get('items') or []
        # 选一个轮次最多的用例
        def rounds_of(c):
            return sorted({m['metric'].split('@')[-1] for mm in c.get('metrics') or []
                           for m in mm.get('metrics') or [] if '@' in m['metric']})
        cand = sorted(items, key=lambda c: len(rounds_of(c)), reverse=True)
        target = cand[0] if cand else None
        api_case = None
        if target:
            api_case = {
                'name': target.get('name'),
                'rounds': rounds_of(target),
                'metrics': [{'metric': m['metric'], 'value': m.get('value')}
                            for mm in target.get('metrics') or [] for m in mm.get('metrics') or []][:40],
                'resources': [r.get('resource') for r in target.get('results') or []],
                'algorithm_results_has_rounds_key': 'rounds' in json.dumps(target.get('algorithmResults'), ensure_ascii=False),
            }
        RESULT['case_api_567'] = api_case

        opened = open_first_case_detail(d)
        RESULT['open_case_detail'] = opened
        dtxt = dialog_text(d)
        RESULT['case_dialog'] = {
            'len': len(dtxt),
            'has_metric_section': '评分指标' in dtxt,
            'has_execution': '执行结果' in dtxt,
            'has_multi_round_block': '多轮对话结果' in dtxt,
            'snippet': dtxt[:300],
        }
        RESULT['round_tabs'] = round_info(d)
        rows_before = metric_rows(d)
        RESULT['metric_rows_first'] = {'tabs': (rows_before or {}).get('tabs'),
                                        'rows': ((rows_before or {}).get('rows') or [])[:8]}
        shot(d, '04-case-detail-567-light')
        # 切换到第二/第三轮次
        round_labels = [t['txt'] for t in ((RESULT['round_tabs'] or {}).get('tabs') or [{}])[0].get('items', [])] if RESULT.get('round_tabs') else []
        pick = None
        for lb in round_labels:
            if lb and lb != next((t['txt'] for t in RESULT['round_tabs']['tabs'][0]['items'] if t['sel'] == 'true'), None):
                pick = lb
                break
        if pick:
            RESULT['switch_round'] = {'to': pick, 'result': click_round(d, pick)}
            rows_after = metric_rows(d)
            RESULT['metric_rows_after_switch'] = {'tabs': (rows_after or {}).get('tabs'),
                                                  'rows': ((rows_after or {}).get('rows') or [])[:8]}
            shot(d, '05-case-detail-567-round2-light')
        RESULT['case_dialog_dark'] = set_theme(d, 'dark', BASE + '/report/567')
        RESULT['case_dialog_dark_open'] = open_first_case_detail(d)
        shot(d, '06-case-detail-567-dark')

        # ---------- 7. API / E2E 两类任务报告的多轮源判定 ----------
        for rid, kind in [(658, 'api'), (669, 'e2e')]:
            st, rep = api('GET', f'/reports/{rid}')
            dd = (rep or {}).get('data') or {}
            stc, cases = api('POST', f'/reports/{rid}/cases/search', {'page': 1, 'page_size': 20})
            citems = ((cases or {}).get('data') or {}).get('items') or []
            has_rounds = any('"rounds"' in json.dumps(c.get('algorithmResults'), ensure_ascii=False) for c in citems)
            d.get(BASE + f'/report/{rid}')
            ready(d, 6)
            txt = body_text(d)
            res = {'report': rid, 'kind': kind, 'api_status': st, 'type': dd.get('type'),
                   'cases': len(citems), 'algorithm_results_has_rounds': has_rounds,
                   'page_len': len(txt), 'page_has_multi_round': '多轮对话结果' in txt}
            if citems:
                res['first_case_rounds'] = sorted({m['metric'].split('@')[-1]
                                                   for mm in citems[0].get('metrics') or []
                                                   for m in mm.get('metrics') or [] if '@' in m['metric']})
                opened = open_first_case_detail(d)
                res['open_detail'] = opened
                dt = dialog_text(d)
                res['dialog_has_metric'] = '评分指标' in dt
                res['dialog_has_multi_round'] = '多轮对话结果' in dt
                res['dialog_has_execution'] = '执行结果' in dt
                res['round_tabs'] = round_info(d)
                shot(d, f'07-case-{kind}-{rid}')
            RESULT.setdefault('task_reports', []).append(res)

        RESULT['bundle_end'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src.split('/').pop())")
        RESULT['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    finally:
        try:
            d.quit()
        except Exception:
            pass
    open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8').write(
        json.dumps(RESULT, ensure_ascii=False, indent=2))
    print('done')


if __name__ == '__main__':
    main()
