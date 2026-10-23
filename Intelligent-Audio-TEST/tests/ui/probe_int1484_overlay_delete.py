# -*- coding: utf-8 -*-
"""INT-1484 探针7：抽屉遮罩点击关闭（左侧空白区） / 分类删除可达性（删维度后）。"""
import json, os, time, urllib.request, urllib.error
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
STAMP = str(int(time.time()))[-6:]
C1 = '接线测试_INT1484_rmC_' + STAMP
D1 = '接线测试_INT1484_rmD_' + STAMP


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def drv_make():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN'):
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    for v in os.listdir(root):
        p = os.path.join(root, v, 'chromedriver.exe')
        if os.path.isfile(p) and v.split('.')[0].isdigit() and int(v.split('.')[0]) == major:
            exe = p
    return webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())


def js_click(drv, el):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)


def one(drv, expr, timeout=15):
    return WebDriverWait(drv, timeout).until(
        lambda d: (d.find_elements(By.XPATH, expr) or [False])[0])


st, b = call('POST', '/evaluation/categories', {'name': C1, 'description': 'probe', 'icon': 'fas fa-folder'})
cid = (b.get('data') or {}).get('id')
print('cat', st, cid)
st, b = call('POST', '/evaluation/dimensions', {
    'name': D1, 'type': 'auto', 'dimension_type': 'main', 'category_id': cid,
    'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
    'decimal_places': 2, 'estimated_exec_time': 5,
    'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
    'api_endpoints': [], 'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
})
dim_id = (b.get('data') or {}).get('id')
print('dim', st, dim_id)

drv = drv_make()
try:
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    WebDriverWait(drv, 15).until(lambda d: d.find_element(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    drv.get(BASE + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
    time.sleep(1.5)

    # ---- 遮罩点击（左侧空白 x≈300）----
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']"))
    time.sleep(1.2)
    overlay = drv.find_element(By.XPATH, "//*[@data-slot='sheet-overlay']")
    ActionChains(drv).move_to_element_with_offset(overlay, -500, 0).click().perform()
    time.sleep(1.2)
    print('sheet after left overlay click:', bool(drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']")))
    drv.save_screenshot(os.path.join(ART, 'INT1484_21_overlay_click.png'))
    if drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']"):
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

    # ---- 分类删除可达性 ----
    js_click(drv, one(drv, "//button[@role='tab'][normalize-space(.)='分组视图']"))
    time.sleep(1.5)
    del_btns = drv.find_elements(By.XPATH, "//button[@aria-label='删除分类 %s']" % C1)
    print('delete button present (with dim):', bool(del_btns),
          'disabled:', del_btns[0].get_attribute('disabled') is not None if del_btns else None)
    if del_btns:
        print('title/tooltip hint: with-dim disabled ->', del_btns[0].get_attribute('disabled'))
    drv.save_screenshot(os.path.join(ART, 'INT1484_22_category_delete_disabled_with_dims.png'))
    # 删除该分类下唯一维度（列表视图）
    js_click(drv, one(drv, "//button[@role='tab'][normalize-space(.)='列表视图']"))
    time.sleep(1.2)
    inp = one(drv, "//input[@aria-label='搜索评估维度']")
    js_click(drv, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(D1)
    time.sleep(1.2)
    js_click(drv, one(drv, "//button[@aria-label='删除维度 %s']" % D1))
    time.sleep(1.0)
    js_click(drv, one(drv, "//*[@data-slot='alert-dialog-content']//button[normalize-space(.)='删除']"))
    time.sleep(2.5)
    print('dims after delete:', [x['name'] for x in call('GET', '/evaluation/dimensions?per_page=1000')[1]['data']['items'] if x['name'].startswith('接线测试_INT1484_rm')])
    # 回到分组视图，看分类组/删除按钮是否还在
    drv.get(BASE + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
    time.sleep(1.2)
    js_click(drv, one(drv, "//button[@role='tab'][normalize-space(.)='分组视图']"))
    time.sleep(1.5)
    body = drv.find_element(By.TAG_NAME, 'body').text
    print('group view contains category name after dim delete:', C1 in body)
    print('delete button present after dim delete:', bool(drv.find_elements(By.XPATH, "//button[@aria-label='删除分类 %s']" % C1)))
    drv.save_screenshot(os.path.join(ART, 'INT1484_23_group_after_dim_delete.png'))
finally:
    drv.quit()
    call('DELETE', '/evaluation/categories/%s' % cid)
    print('cleanup done')
