# -*- coding: utf-8 -*-
"""INT-1569 UX 审计补充：空态 colSpan=7 跨列 + 控制台报错零容忍。

服务对象：本 run 旁路容器 http://127.0.0.1:15279（交付 ae44daff 构建的 dist）→ docker 真实库栈。
写数据纪律：仅建「接线测试_」前缀算法，末了删除。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15279'
API = 'http://127.0.0.1:15000/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1569')
os.makedirs(ART, exist_ok=True)

TS = time.strftime('%H%M%S')
NEW_TYPE = f'qa_int1569_audit_{TS}'
NEW_NAME = f'接线测试_审计_{TS}'
DEFAULT = 'en'
logs = []


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    logs.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    log(('PASS ' if ok else 'FAIL ') + name + ' | ' + str(detail)[:600])
    if not ok:
        raise AssertionError(name)


def api_call(method, path, body=None):
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}


def new_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = [os.path.join(cache_root, v, 'chromedriver.exe') for v in os.listdir(cache_root)]
    cands = [c for c in cands if os.path.isfile(c)]
    d = webdriver.Chrome(options=o, service=Service(executable_path=sorted(cands)[-1]))
    d.set_page_load_timeout(90)
    return d


def js_click(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.15)
    d.execute_script("arguments[0].click();", el)


def find(d, xpath, timeout=25):
    def cond(dd):
        for e in dd.find_elements(By.XPATH, xpath):
            if e.is_displayed():
                return e
        return False
    return WebDriverWait(d, timeout, poll_frequency=0.25).until(cond)


def find_all(d, xpath):
    return [e for e in d.find_elements(By.XPATH, xpath) if e.is_displayed()]


def click_tab(d, label_regex):
    import re
    for el in find_all(d, "//button[@role='tab']"):
        if re.search(label_regex, el.text or ''):
            js_click(d, el)
            time.sleep(0.6)
            return el.text
    raise AssertionError('tab not found: ' + label_regex)


def table_headers(table):
    return [(th.text or '').strip() for th in table.find_elements(By.XPATH, './/thead//th')]


def main():
    d = new_driver()
    created = False
    try:
        h = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20).read())
        check('0 真实库 /health', h.get('database') == 'intelligent_audio_test', h)

        payload = {
            'type': NEW_TYPE, 'name': NEW_NAME, 'group_id': None, 'display_order': 0,
            'status': 'online', 'description': 'INT-1569 UX 审计临时算法',
            'device_params': [{
                'param_code': 'lang_audit', 'param_name': '语言', 'label': '语言',
                'param_type': 'text', 'direction': 'input', 'required': False,
                'default_value': DEFAULT, 'help_text': None, 'ui_order': 0, 'hidden': False,
            }],
            'api_params': [], 'case_params': [], 'reference_params': [],
            'mappings': {'device': [], 'api': [], 'evaluation': []},
            'associated_dimensions': [],
        }
        code, body = api_call('POST', '/algorithm/definitions', payload)
        created = code < 300
        check('1 自建算法（仅设备参数，默认值 en）创建', created, f'{code} {body}')

        code, det = api_call('GET', f'/algorithm/definitions/{NEW_TYPE}')
        data = det.get('data') or det
        got = (data.get('device_params') or [{}])[0].get('default_value')
        check('2 GET 回读 default_value = en', code == 200 and got == DEFAULT, f'{code} {got}')

        d.get(BASE + '/AlgorithmConfig')
        WebDriverWait(d, 40).until(lambda dd: dd.execute_script('return document.readyState') == 'complete')
        find(d, f"//button[@aria-label='算法 {NEW_NAME} 的操作']", timeout=40)
        js_click(d, find(d, f"//button[@aria-label='算法 {NEW_NAME} 的操作']"))
        find(d, "//*[@role='menuitem']", timeout=10)
        for it in find_all(d, "//*[@role='menuitem']"):
            if '详情' in (it.text or ''):
                js_click(d, it)
                break
        WebDriverWait(d, 20).until(lambda dd: '算法定义与参数映射只读详情' in (dd.find_element(By.XPATH, "//*[@role='dialog']").text or ''))
        time.sleep(0.8)

        tables = find_all(d, "//section[@aria-labelledby='algorithm-params-title']//table")
        headers = table_headers(tables[0])
        rows = [[(td.text or '').strip() for td in tr.find_elements(By.XPATH, './td')]
                for tr in tables[0].find_elements(By.XPATH, './/tbody/tr')]
        check('3 设备参数默认值回显 en', rows == [['lang_audit', '语言', '文本', '输入', '否', 'en', '—']], rows)

        click_tab(d, r'^API参数（0）')
        tables = find_all(d, "//section[@aria-labelledby='algorithm-params-title']//table")
        check('4 API 页签表头仍 7 列', table_headers(tables[0]) == ['参数代码', '参数名称', '类型', '方向', '必填', '默认值', '帮助文本'], table_headers(tables[0]))
        td = tables[0].find_element(By.XPATH, './/tbody/tr/td')
        colspan = td.get_attribute('colspan')
        geom = d.execute_script(
            "const td=arguments[0], tb=td.closest('table');"
            "return {td:td.getBoundingClientRect().width, table:tb.getBoundingClientRect().width,"
            " text:td.innerText.trim()};", td)
        check('5 空态单元格 colspan=7 且横跨整表', colspan == '7' and geom['td'] >= geom['table'] - 4,
              f'colspan={colspan} geom={geom}')
        d.save_screenshot(os.path.join(ART, 'int1569_light_api_empty.png'))
        log('SHOT api_empty')

        seg = d.get_log('browser')
        severe = [s for s in seg if s.get('level') == 'SEVERE']
        check('6 页面控制台无 SEVERE 报错', len(severe) == 0, severe[:5])
    finally:
        if created:
            code, body = api_call('DELETE', f'/algorithm/definitions/{NEW_TYPE}')
            log('DELETE', code, body)
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'audit_extra.json'), 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    fails = 0
    try:
        main()
    except AssertionError as e:
        log('FAILED', e)
        fails = 1
    log('TOTAL %d FAILS %d' % (len(logs), fails))
    sys.exit(fails)
