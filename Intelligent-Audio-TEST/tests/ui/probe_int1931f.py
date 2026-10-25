# -*- coding: utf-8 -*-
"""INT-1931 取证 F：批量「标记颜色 → 红色」原生点击全链路（菜单挂载等待加长、采集页面异常/请求/回读）。"""
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
OUT = os.path.join(ART, 'probe_int1931f.json')

PATCH = r"""
window.__errs = [];
window.addEventListener('error', function(e){ window.__errs.push('error: ' + (e.message||'')); });
window.addEventListener('unhandledrejection', function(e){ window.__errs.push('rejection: ' + String(e.reason)); });
window.__fetchLog = [];
const __of = window.fetch;
window.fetch = async function(input, init){
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const e = {url: url, method: ((init&&init.method)||'GET').toUpperCase(), body: init&&init.body?String(init.body):null, t: Date.now()};
  window.__fetchLog.push(e);
  try { const r = await __of.apply(this, arguments); e.status = r.status; if(!/export/.test(url)){ try{ e.text=(await r.clone().text()).slice(0,2000);}catch(x){} } return r; }
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
    d.set_script_timeout(120)
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


def snap(d, name):
    d.save_screenshot(os.path.join(ART, 'shots', name))


def state(d):
    t = d.find_element(By.TAG_NAME, 'body').text or ''
    return {'url': d.current_url, 'is500': t.strip().startswith('500'),
            'head': t[:80], 'errs': d.execute_script('return window.__errs || []'),
            'rows': len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')),
            'menus': d.execute_script("""
              return {slot: document.querySelectorAll('[data-slot="dropdown-menu-content"]').length,
                      role: document.querySelectorAll('[role="menu"]').length,
                      reds: Array.from(document.querySelectorAll('*')).filter(e=>e.children.length===0 && (e.textContent||'').trim()==='红色').length};
            """)}


res = {}
d = driver()
try:
    login(d)
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    apply_window(d)
    first = ids(d)
    res['page_ids'] = first[:6]
    for rid in first[:2]:
        d.find_element(By.CSS_SELECTOR, '[aria-label="选择日志 %d"]' % rid).click()
        time.sleep(0.5)
    res['selected'] = '已选择 2 条' in (d.find_element(By.TAG_NAME, 'body').text or '')
    d.execute_script('window.__errs = []; window.__fetchLog = [];')
    trig = None
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '标记颜色' and b.is_displayed():
            trig = b
            break
    trig.click()
    # 等菜单真正挂载（最多 15s），记录各时刻命中数
    probes = []
    red = None
    t0 = time.time()
    while time.time() - t0 < 15:
        cnt = d.execute_script("return document.querySelectorAll('[data-slot=\"dropdown-menu-content\"]').length")
        probes.append({'t': round(time.time() - t0, 1), 'content': cnt})
        if cnt:
            for it in d.find_elements(By.CSS_SELECTOR, '[data-slot="dropdown-menu-item"]'):
                if (it.text or '').strip() == '红色' and it.is_displayed():
                    red = it
                    break
            if red is not None:
                break
        time.sleep(0.5)
    res['menu_probes'] = probes
    res['menu_state'] = state(d)
    res['red_found'] = red is not None
    snap(d, 'f1_menu_open_light.png')
    if red is not None:
        try:
            red.click()
        except Exception as exc:  # noqa: BLE001
            res['red_native_click_err'] = repr(exc)
            d.execute_script('arguments[0].click()', red)
        time.sleep(3.0)
        res['after_red'] = state(d)
        res['net_mark'] = [e for e in (d.execute_script('return window.__fetchLog || []'))
                           if '/logs/mark' in e.get('url', '')]
        snap(d, 'f2_after_red_light.png')
        rb = d.execute_async_script("""
          const cb=arguments[arguments.length-1];
          const t=localStorage.getItem('iatp:auth:token:v1');
          fetch('http://127.0.0.1:15000/api/v1/logs?page=1&per_page=20&start_time=2026-10-24T00:00&end_time=2026-10-25T20:00&mark=red',{headers:{Authorization:'Bearer '+t}})
            .then(r=>r.text().then(x=>cb(x.slice(0,2000)))).catch(e=>cb(String(e)));
        """)
        try:
            res['red_readback_ids'] = [i['id'] for i in json.loads(rb)['data']['items']]
        except Exception:
            res['red_readback_raw'] = str(rb)[:300]
        res['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE'][:8]
    # 还原：清掉本次两条
    d.execute_async_script("""
      const cb=arguments[arguments.length-1];
      const t=localStorage.getItem('iatp:auth:token:v1');
      fetch('http://127.0.0.1:15000/api/v1/logs/mark',{method:'PUT',headers:{Authorization:'Bearer '+t,'Content-Type':'application/json'},body:JSON.stringify({log_ids:arguments[0],mark:''})})
        .then(r=>r.text().then(x=>cb(x))).catch(e=>cb(String(e)));
    """, first[:2])
    res['cleanup_touched'] = first[:2]
finally:
    d.quit()

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print('WROTE', OUT)
print(json.dumps({k: res.get(k) for k in ('page_ids', 'selected', 'menu_probes', 'menu_state', 'red_found',
                                          'after_red', 'net_mark', 'red_readback_ids', 'console_severe',
                                          'cleanup_touched')}, ensure_ascii=True)[:3500])
