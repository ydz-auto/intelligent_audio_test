# -*- coding: utf-8 -*-
"""INT-1931 取证 G：批量「标记颜色」用 ActionChains 真鼠标点两轮，采菜单挂载/请求/回读/页面异常。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1931')
OUT = os.path.join(ART, 'probe_int1931g.json')
PATCH = r"""
window.__errs = [];
window.addEventListener('error', function(e){ window.__errs.push('error: ' + (e.message||'')); });
window.addEventListener('unhandledrejection', function(e){ window.__errs.push('rejection: ' + String(e.reason)); });
window.__fetchLog = [];
const __of = window.fetch;
window.fetch = async function(input, init){
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const e = {url:url, method:((init&&init.method)||'GET').toUpperCase(), body:init&&init.body?String(init.body):null, t:Date.now()};
  window.__fetchLog.push(e);
  try { const r = await __of.apply(this, arguments); e.status=r.status; if(!/export/.test(url)){try{e.text=(await r.clone().text()).slice(0,1200);}catch(x){}} return r; }
  catch(err){ e.error=String(err); throw err; }
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


def st(d):
    t = d.find_element(By.TAG_NAME, 'body').text or ''
    return {'is500': t.strip().startswith('500'), 'url': d.current_url,
            'errs': d.execute_script('return window.__errs || []'),
            'menu_slot': d.execute_script("return document.querySelectorAll('[data-slot=\"dropdown-menu-content\"]').length"),
            'rows': len(d.find_elements(By.CSS_SELECTOR, 'tbody tr'))}


res = {'attempts': []}
d = driver()
touched = []
try:
    login(d)
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    apply_window(d)
    for attempt in (1, 2):
        cur = ids(d)
        pick = cur[:2] if attempt == 1 else cur[2:4]
        # 先取消已选（点全选两下）
        try:
            allcb = d.find_element(By.CSS_SELECTOR, '[aria-label="全选当前页"]')
            ActionChains(d).move_to_element(allcb).click().perform()
            time.sleep(0.4)
            ActionChains(d).move_to_element(allcb).click().perform()
            time.sleep(0.6)
        except Exception:
            pass
        for rid in pick:
            cb = d.find_element(By.CSS_SELECTOR, '[aria-label="选择日志 %d"]' % rid)
            ActionChains(d).move_to_element(cb).click().perform()
            time.sleep(0.4)
        touched.extend(pick)
        d.execute_script('window.__errs = []; window.__fetchLog = [];')
        trig = None
        for b in d.find_elements(By.CSS_SELECTOR, 'button'):
            if (b.text or '').strip() == '标记颜色' and b.is_displayed():
                trig = b
                break
        info = {'attempt': attempt, 'pick': pick, 'trigger': trig is not None}
        if trig is None:
            res['attempts'].append(info)
            continue
        ActionChains(d).move_to_element(trig).click().perform()
        probes, red = [], None
        t0 = time.time()
        while time.time() - t0 < 8:
            cnt = d.execute_script("return document.querySelectorAll('[data-slot=\"dropdown-menu-content\"]').length")
            probes.append(cnt)
            if cnt:
                for it in d.find_elements(By.CSS_SELECTOR, '[data-slot="dropdown-menu-item"]'):
                    if (it.text or '').strip() == '红色' and it.is_displayed():
                        red = it
                        break
            if red is not None:
                break
            time.sleep(0.4)
        info['probes'] = probes
        info['state_after_open'] = st(d)
        d.save_screenshot(os.path.join(ART, 'shots', 'g%d_menu_%s.png' % (attempt, 'open' if red else 'missing')))
        info['red_found'] = red is not None
        if red is not None:
            ActionChains(d).move_to_element(red).click().perform()
            time.sleep(3.0)
            info['state_after_red'] = st(d)
            info['net_mark'] = [e for e in (d.execute_script('return window.__fetchLog || []'))
                                if '/logs/mark' in e.get('url', '')]
            d.save_screenshot(os.path.join(ART, 'shots', 'g%d_after_red.png' % attempt))
            rb = d.execute_async_script("""
              const cb=arguments[arguments.length-1];
              const t=localStorage.getItem('iatp:auth:token:v1');
              fetch('http://127.0.0.1:15000/api/v1/logs?page=1&per_page=50&start_time=2026-10-24T00:00&end_time=2026-10-25T20:00&mark=red',{headers:{Authorization:'Bearer '+t}})
                .then(r=>r.text().then(x=>cb(x.slice(0,3000)))).catch(e=>cb(String(e)));
            """)
            try:
                info['red_readback_ids'] = [i['id'] for i in json.loads(rb)['data']['items']]
            except Exception:
                info['red_readback_raw'] = str(rb)[:200]
            info['console_severe'] = [e.get('message', '')[:200] for e in d.get_log('browser') if e.get('level') == 'SEVERE'][:6]
        res['attempts'].append(info)
    # 还原本轮标记
    if touched:
        d.execute_async_script("""
          const cb=arguments[arguments.length-1];
          const t=localStorage.getItem('iatp:auth:token:v1');
          fetch('http://127.0.0.1:15000/api/v1/logs/mark',{method:'PUT',headers:{Authorization:'Bearer '+t,'Content-Type':'application/json'},body:JSON.stringify({log_ids:arguments[0],mark:''})})
            .then(r=>r.text().then(x=>cb(x))).catch(e=>cb(String(e)));
        """, touched)
    res['touched'] = touched
finally:
    d.quit()

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print('WROTE', OUT)
print(json.dumps(res, ensure_ascii=True)[:4000])
