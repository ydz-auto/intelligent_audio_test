# -*- coding: utf-8 -*-
"""INT-1931 取证 H：批量标记下拉到底有没有挂载（全文档找「红色」文本 + body 尾部 DOM 快照）。"""
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
OUT = os.path.join(ART, 'probe_int1931h.json')


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.page_load_strategy = 'eager'
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    for v in os.listdir(cache):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e) and v.startswith('155'):
            p = e
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_script_timeout(60)
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


def probe(d):
    return d.execute_script("""
      const reds = Array.from(document.querySelectorAll('*')).filter(e=>e.children.length===0 && (e.textContent||'').trim()==='红色');
      return {
        reds: reds.length,
        redVisible: reds.filter(e=>e.getBoundingClientRect().height>0).length,
        menuSlot: document.querySelectorAll('[data-slot="dropdown-menu-content"]').length,
        roleMenu: document.querySelectorAll('[role="menu"]').length,
        roleMenuItems: document.querySelectorAll('[role="menuitem"]').length,
        bodyChildren: Array.from(document.body.children).map(c=>(c.tagName+':'+(c.getAttribute('data-slot')||'-')).slice(0,60)),
        last: document.body.lastElementChild ? document.body.lastElementChild.outerHTML.slice(0,600) : null
      };
    """)


res = {}
d = driver()
try:
    login(d)
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    set_dt(d, '开始时间', '2026-10-24T00:00')
    set_dt(d, '结束时间', '2026-10-25T20:00')
    time.sleep(2.0)
    ids = d.execute_script(
        "return Array.from(document.querySelectorAll('[aria-label^=\"选择日志 \"]')).map(e=>Number((e.getAttribute('aria-label')||'').replace('选择日志 ','')))")
    res['ids'] = ids[:4]
    for rid in ids[:2]:
        d.find_element(By.CSS_SELECTOR, '[aria-label="选择日志 %d"]' % rid).click()
        time.sleep(0.4)
    res['before'] = probe(d)
    trig = None
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '标记颜色' and b.is_displayed():
            trig = b
            break
    res['trig_html'] = trig.get_attribute('outerHTML')[:400] if trig else None
    trig.click()
    time.sleep(2.5)
    res['after_click'] = probe(d)
    d.save_screenshot(os.path.join(ART, 'shots', 'h1_after_click.png'))
    # 再点一次（base-ui 两次点击应开-关，若第一次已开则关闭）
    trig.click()
    time.sleep(1.5)
    res['after_second'] = probe(d)
    d.save_screenshot(os.path.join(ART, 'shots', 'h2_after_second.png'))
    if res['after_click']['reds']:
        # 打开状态下点红色（用 JS 精确点击文本节点父按钮）
        clicked = d.execute_script("""
          const reds = Array.from(document.querySelectorAll('*')).filter(e=>e.children.length===0 && (e.textContent||'').trim()==='红色' && e.getBoundingClientRect().height>0);
          if (!reds.length) return 'none';
          let el = reds[0];
          for (let i=0;i<5 && el;i++){ if (el.tagName==='BUTTON' || el.getAttribute('role')==='menuitem') break; el = el.parentElement; }
          if (!el) return 'no-button';
          el.click();
          return 'clicked';
        """)
        res['red_click'] = clicked
        time.sleep(2.5)
        res['after_red'] = probe(d)
        d.save_screenshot(os.path.join(ART, 'shots', 'h3_after_red.png'))
finally:
    d.quit()

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=True)[:3000])
