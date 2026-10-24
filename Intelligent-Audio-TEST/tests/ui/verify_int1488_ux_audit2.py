# -*- coding: utf-8 -*-
"""INT-1488 前端UX审计（补测）：空态终态 / 行详情 / 页脚计数 / 导出文件非空（页内 fetch 取字节数）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1488_ux_audit')
R = {}


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(d, name):
    d.save_screenshot(os.path.join(ART, name + '.png'))
    print('SHOT', name, flush=True)


def body(d):
    return d.find_element(By.TAG_NAME, 'body').text


def set_input(d, el, value):
    js_click(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def rows(d):
    return len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))


o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1050')
o.add_argument('--no-sandbox')
o.page_load_strategy = 'eager'
o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
p = ''
for v in os.listdir(cache):
    e = os.path.join(cache, v, 'chromedriver.exe')
    if os.path.isfile(e) and v.startswith('155'):
        p = e
d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
d.set_page_load_timeout(90)
d.set_script_timeout(150)
try:
    d.get(BASE + '/login')
    time.sleep(2)
    if '/login' not in d.current_url:
        d.get(BASE + '/login')
        time.sleep(2)
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    tok = d.execute_script("return localStorage.getItem('iatp:auth:token:v1') || ''")
    R['token_ok'] = bool(tok)
    d.get(BASE + '/logs')
    t0 = time.time()
    while time.time() - t0 < 180 and rows(d) == 0:
        time.sleep(4)
    R['rows'] = rows(d)
    # 页脚计数（JS 取整页文本，绕开 XPath 文本节点问题）
    R['footer'] = d.execute_script(
        "const all=[...document.querySelectorAll('span,div')].map(e=>e.textContent||'');"
        "return all.filter(t=>t.indexOf('条日志')>=0 && t.length<40).slice(0,3);")
    print('FOOTER', R['footer'], flush=True)

    # 行详情：点「时间」单元格（避开勾选列与操作列）
    tr = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')[0]
    tds = tr.find_elements(By.TAG_NAME, 'td')
    js_click(d, tds[2])
    time.sleep(1.5)
    txt = body(d)
    R['row_detail'] = {'has_detail': '详细信息' in txt, 'has_context': '上下文信息' in txt,
                       'has_fields': all(k in txt for k in ('设备ID', '任务ID', '线程ID'))}
    shot(d, 'light_12_row_detail')
    print('ROWDETAIL', R['row_detail'], flush=True)
    # 收起
    js_click(d, tds[2])
    time.sleep(0.8)

    # 空态终态：等骨架消失（Skeleton 无 role，按「未找到匹配日志」/行数判断）
    search = [e for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索日志内容']") if e.is_displayed()][0]
    set_input(d, search, 'INT1488_NO_SUCH_LOG_XYZ')
    t0 = time.time()
    state = None
    while time.time() - t0 < 150:
        tx = body(d)
        if '未找到匹配日志' in tx:
            state = 'empty'
            break
        if '日志列表加载失败' in tx:
            state = 'error'
            break
        time.sleep(3)
    R['empty_state'] = {'state': state, 'rows': rows(d),
                        'footer': d.execute_script(
                            "const all=[...document.querySelectorAll('span,div')].map(e=>e.textContent||'');"
                            "return all.filter(t=>t.indexOf('条日志')>=0 && t.length<40).slice(0,3);"),
                        'copy': [l for l in body(d).split('\n') if '匹配' in l or '筛选' in l][:4]}
    shot(d, 'light_13_empty_state_final')
    print('EMPTY', R['empty_state'], flush=True)

    # 复位
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '清除过滤器' and b.is_displayed():
            js_click(d, b)
            break
    time.sleep(4)

    # 导出文件非空（页内 fetch 实测字节；level=ERROR 小结果集）
    blob = d.execute_async_script(
        "const cb=arguments[arguments.length-1];"
        "const t=localStorage.getItem('iatp:auth:token:v1');"
        "fetch('" + BASE + "/api/v1/logs/export?page=1&per_page=20&level=ERROR',"
        "{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+t},"
        "body:JSON.stringify({format:'json'})})"
        ".then(async r=>{const b=await r.arrayBuffer();"
        "cb({status:r.status,bytes:b.byteLength,ctype:r.headers.get('content-type'),"
        "cd:r.headers.get('content-disposition'),head:new TextDecoder().decode(b.slice(0,120))})})"
        ".catch(e=>cb({status:-1,err:String(e)}));")
    R['export_json'] = blob
    print('EXPORT_JSON', blob, flush=True)
    blob2 = d.execute_async_script(
        "const cb=arguments[arguments.length-1];"
        "const t=localStorage.getItem('iatp:auth:token:v1');"
        "fetch('" + BASE + "/api/v1/logs/export?page=1&per_page=20&level=ERROR',"
        "{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+t},"
        "body:JSON.stringify({format:'txt'})})"
        ".then(async r=>{const b=await r.arrayBuffer();"
        "cb({status:r.status,bytes:b.byteLength,ctype:r.headers.get('content-type')})})"
        ".catch(e=>cb({status:-1,err:String(e)}));")
    R['export_txt'] = blob2
    print('EXPORT_TXT', blob2, flush=True)

    R['health_end'] = d.execute_async_script(
        "const cb=arguments[arguments.length-1];"
        "fetch('http://127.0.0.1:15000/health').then(r=>r.text()).then(t=>cb(t)).catch(e=>cb('ERR '+e));")
    R['console'] = [e for e in d.get_log('browser') if e.get('level') in ('SEVERE', 'WARNING')]
    print('CONSOLE', len(R['console']), flush=True)
    for e in R['console'][:6]:
        print(' ', e['message'][:200].encode('ascii', 'replace').decode(), flush=True)
finally:
    try:
        d.quit()
    except Exception:
        pass
    with open(os.path.join(ART, 'result2.json'), 'w', encoding='utf-8') as fp:
        json.dump(R, fp, ensure_ascii=False, indent=2, default=str)
print('DONE2', flush=True)
