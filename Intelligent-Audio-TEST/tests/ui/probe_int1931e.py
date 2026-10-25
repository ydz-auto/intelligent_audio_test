# -*- coding: utf-8 -*-
"""INT-1931 补充取证 E：①批量「标记颜色」下拉是否导致整页 500；②翻页重复的成因（后端排序 vs 前端瞬时态）。

运行：D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/probe_int1931e.py
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1931')
OUT = os.path.join(ART, 'probe_int1931e.json')

PATCH = r"""
window.__errs = [];
window.addEventListener('error', function(e){ window.__errs.push('error: ' + (e.message||'') + ' @ ' + (e.filename||'')); });
window.addEventListener('unhandledrejection', function(e){ window.__errs.push('rejection: ' + String(e.reason)); });
window.__fetchLog = [];
const __of = window.fetch;
window.fetch = async function(input, init){
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const e = {url: url, method: ((init&&init.method)||'GET').toUpperCase(), body: init&&init.body?String(init.body):null, t: Date.now()};
  window.__fetchLog.push(e);
  try { const r = await __of.apply(this, arguments); e.status = r.status; if(!/export/.test(url)){ try{ e.text = (await r.clone().text()).slice(0,3000);}catch(x){} } return r; }
  catch(err){ e.error = String(err); throw err; }
};
"""


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.page_load_strategy = 'eager'
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    for v in os.listdir(cache):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e) and v.startswith('155'):
            p = e
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_script_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


def login(d):
    d.get(BASE + '/login')
    WebDriverWait(d, 40).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)


def set_dt(d, aria, value):
    el = d.find_element(By.CSS_SELECTOR, 'input[aria-label="%s"]' % aria)
    d.execute_script(
        "const el=arguments[0];const v=arguments[1];"
        "const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
        "s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));", el, value)
    time.sleep(1.0)


def apply_window(d):
    set_dt(d, '开始时间', '2026-10-24T00:00')
    set_dt(d, '结束时间', '2026-10-25T20:00')
    time.sleep(1.8)
    WebDriverWait(d, 45).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)


def ids(d):
    return d.execute_script(
        "return Array.from(document.querySelectorAll('[aria-label^=\"选择日志 \"]')).map(e=>Number((e.getAttribute('aria-label')||'').replace('选择日志 ','')))")


def state(d):
    return {'url': d.current_url,
            'has500': '500' in (d.find_element(By.TAG_NAME, 'body').text or '')[:50],
            'body_head': (d.find_element(By.TAG_NAME, 'body').text or '')[:120],
            'errs': d.execute_script('return window.__errs || []'),
            'rows': len(d.find_elements(By.CSS_SELECTOR, 'tbody tr'))}


def js_fetch(d, path):
    js = """
    const cb=arguments[arguments.length-1];
    const t=localStorage.getItem('iatp:auth:token:v1');
    fetch('http://127.0.0.1:15000/api/v1%s',{headers:{Authorization:'Bearer '+t}})
      .then(r=>r.text().then(x=>cb({s:r.status,b:x})))
      .catch(e=>cb({s:-1,b:String(e)}));
    """ % path
    return d.execute_async_script(js)


res = {'bulk_mark': {}, 'paging': {}}
d = driver()
try:
    login(d)
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    apply_window(d)
    first = ids(d)
    res['bulk_mark']['page1_ids'] = first[:5]
    # 原生点击勾选两条
    for rid in first[:2]:
        el = d.find_element(By.CSS_SELECTOR, '[aria-label="选择日志 %d"]' % rid)
        try:
            el.click()
        except Exception:
            d.execute_script('arguments[0].click()', el)
        time.sleep(0.5)
    res['bulk_mark']['selected_text'] = '已选择' in (d.find_element(By.TAG_NAME, 'body').text or '')
    d.execute_script('window.__errs = []; window.__fetchLog = [];')
    # 原生点击「标记颜色」
    btn = None
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '标记颜色' and b.is_displayed():
            btn = b
            break
    res['bulk_mark']['trigger_found'] = btn is not None
    if btn:
        btn.click()
        time.sleep(1.5)
        res['bulk_mark']['after_open'] = state(d)
        res['bulk_mark']['menus'] = d.execute_script("""
          return {
            content: document.querySelectorAll('[data-slot="dropdown-menu-content"]').length,
            items: Array.from(document.querySelectorAll('[data-slot="dropdown-menu-item"]')).map(e=>(e.innerText||'').trim()),
            roleitems: Array.from(document.querySelectorAll('[role="menuitem"]')).map(e=>(e.innerText||'').trim())
          };
        """)
        d.save_screenshot(os.path.join(ART, 'shots', 'e1_bulk_menu_light.png'))
        # 原生点「红色」
        red = None
        for it in d.find_elements(By.CSS_SELECTOR, '[data-slot="dropdown-menu-item"]'):
            if (it.text or '').strip() == '红色' and it.is_displayed():
                red = it
                break
        res['bulk_mark']['red_found'] = red is not None
        if red:
            try:
                red.click()
            except Exception:
                d.execute_script('arguments[0].click()', red)
            time.sleep(2.5)
            res['bulk_mark']['after_red'] = state(d)
            res['bulk_mark']['net'] = [e for e in (d.execute_script('return window.__fetchLog || []'))
                                       if '/logs/mark' in e.get('url', '')]
            d.save_screenshot(os.path.join(ART, 'shots', 'e1_after_bulk_mark_light.png'))
            # 回读
            rb = d.execute_async_script("""
              const cb=arguments[arguments.length-1];
              const t=localStorage.getItem('iatp:auth:token:v1');
              fetch('http://127.0.0.1:15000/api/v1/logs?page=1&per_page=20&start_time=2026-10-24T00:00&end_time=2026-10-25T20:00&mark=red',{headers:{Authorization:'Bearer '+t}})
                .then(r=>r.text().then(x=>cb({s:r.status,b:x.slice(0,2000)}))).catch(e=>cb({s:-1,b:String(e)}));
            """)
            try:
                items = json.loads(rb['b'])['data']['items']
                res['bulk_mark']['red_readback_ids'] = [i['id'] for i in items]
            except Exception:
                res['bulk_mark']['red_readback_raw'] = str(rb)[:400]
    # 清理本次标记
    touched = first[:2]
    d.execute_async_script("""
      const cb=arguments[arguments.length-1];
      const t=localStorage.getItem('iatp:auth:token:v1');
      fetch('http://127.0.0.1:15000/api/v1/logs/mark',{method:'PUT',headers:{Authorization:'Bearer '+t,'Content-Type':'application/json'},body:JSON.stringify({log_ids:arguments[0],mark:''})})
        .then(r=>r.text().then(x=>cb(x))).catch(e=>cb(String(e)));
    """, touched)
    # 刷新回 /logs 继续翻页测试
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    apply_window(d)
    p1 = ids(d)
    res['paging']['ui_page1'] = p1
    d.execute_script('window.__fetchLog = [];')
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '下一页':
            b.click()
            break
    timeline = []
    t0 = time.time()
    last = None
    while time.time() - t0 < 25:
        cur = ids(d)
        if cur and cur != last:
            timeline.append({'t': round(time.time() - t0, 1), 'ids': cur[:3], 'n': len(cur)})
            last = cur
        time.sleep(0.5)
    res['paging']['timeline'] = timeline
    res['paging']['ui_page2_final'] = ids(d)
    reqs = [e for e in (d.execute_script('return window.__fetchLog || []')) if '/logs?' in e.get('url', '')]
    res['paging']['reqs'] = [{'url': e.get('url'), 'status': e.get('status')} for e in reqs]
    if reqs:
        try:
            data = json.loads(reqs[-1]['text'])['data']
            res['paging']['api_page2'] = {'page': data.get('page'), 'per_page': data.get('per_page'),
                                          'total': data.get('total'), 'ids': [i['id'] for i in data['items']]}
        except Exception:
            pass
    # 直接对齐三页
    apis = {}
    for n in (1, 2, 3):
        rb = js_fetch(d, '/logs?page=%d&per_page=20&start_time=2026-10-24T00:00&end_time=2026-10-25T20:00' % n)
        try:
            data = json.loads(rb['b'])['data']
            apis[n] = {'ids': [i['id'] for i in data['items']], 'times': [i['time'] for i in data['items']], 'total': data.get('total')}
        except Exception:
            apis[n] = {'raw': str(rb)[:200]}
    res['paging']['apis'] = apis
    s1 = set(apis.get(1, {}).get('ids', []))
    s2 = set(apis.get(2, {}).get('ids', []))
    s3 = set(apis.get(3, {}).get('ids', []))
    res['paging']['api_overlap_1_2'] = sorted(s1 & s2)
    res['paging']['api_overlap_2_3'] = sorted(s2 & s3)
    d.save_screenshot(os.path.join(ART, 'shots', 'e2_page2_after_settle_light.png'))
finally:
    d.quit()

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print('WROTE', OUT)
print(json.dumps({k: v for k, v in res['bulk_mark'].items() if k in
                  ('trigger_found', 'after_open', 'menus', 'red_found', 'after_red', 'net',
                   'red_readback_ids', 'selected_text')}, ensure_ascii=True)[:2500])
print(json.dumps({'timeline': res['paging'].get('timeline'), 'ui2': (res['paging'].get('ui_page2_final') or [])[:5],
                  'api2': (res['paging'].get('api_page2') or {}).get('ids', [])[:5],
                  'overlap12': res['paging'].get('api_overlap_1_2'),
                  'overlap23': res['paging'].get('api_overlap_2_3'),
                  'ui_page1_len': len(res['paging'].get('ui_page1') or [])}, ensure_ascii=True)[:2000])
