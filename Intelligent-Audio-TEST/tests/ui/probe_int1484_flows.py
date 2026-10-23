# -*- coding: utf-8 -*-
"""INT-1484 探针6：分类编辑提交行为 / 分类删除确认 / 抽屉遮罩关闭。"""
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
os.makedirs(ART, exist_ok=True)
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
STAMP = str(int(time.time()))[-6:]
C1 = '接线测试_INT1484_probeC_' + STAMP
C2 = C1 + '_renamed'

FETCH = r"""
window.__fetchLog=[];
(function(){const o=window.fetch;window.fetch=async function(i,init){
 const url=typeof i==='string'?i:(i&&i.url)||'';const m=((init&&init.method)||(i&&i.method)||'GET').toUpperCase();
 let body=(init&&init.body&&typeof init.body==='string')?init.body:null;let r;
 try{r=await o.apply(this,arguments);}catch(e){window.__fetchLog.push({url,method:m,status:'ERR',reqBody:body,error:String(e)});throw e;}
 try{window.__fetchLog.push({url,method:m,status:r.status,reqBody:body});}catch(e){}
 return r;};})();
"""


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


def cats():
    st, b = call('GET', '/evaluation/categories?per_page=100')
    return b['data']['items'] if isinstance(b, dict) else []


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
    drv = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH})
    return drv


def js_click(drv, el):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)


def one(drv, expr, timeout=15):
    return WebDriverWait(drv, timeout).until(
        lambda d: (d.find_elements(By.XPATH, expr) or [False])[0])


def clear_type(drv, el, text):
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(text)


def net(drv):
    return drv.execute_script('return window.__fetchLog || []')


def clear_net(drv):
    drv.execute_script('window.__fetchLog=[];')


def main():
    st, b = call('POST', '/evaluation/categories', {'name': C1, 'description': 'probe 描述', 'icon': 'fas fa-folder'})
    cid = (b.get('data') or {}).get('id') if isinstance(b, dict) else None
    print('create cat', st, cid)
    st2, b2 = call('POST', '/evaluation/dimensions', {
        'name': '接线测试_INT1484_probeD_' + STAMP, 'type': 'auto', 'dimension_type': 'main',
        'category_id': cid, 'status': True, 'weight': 5, 'result_type': 1,
        'result_min': 0, 'result_max': 100, 'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'api_endpoints': [], 'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = (b2.get('data') or {}).get('id') if isinstance(b2, dict) else None
    print('create dim', st2, dim_id)
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

        # ---- 1) 分类编辑 ----
        js_click(drv, one(drv, "//button[@role='tab'][normalize-space(.)='分组视图']"))
        time.sleep(1.5)
        js_click(drv, one(drv, "//button[@aria-label='编辑分类 %s']" % C1, timeout=20))
        time.sleep(1.2)
        dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='编辑分类']]")
        print('edit dialog open, name=', dlg.find_element(By.ID, 'category-name').get_attribute('value'))
        clear_type(drv, dlg.find_element(By.ID, 'category-name'), C2)
        time.sleep(0.4)
        sub = dlg.find_element(By.XPATH, ".//button[@type='submit']")
        print('submit disabled=', sub.get_attribute('disabled'))
        clear_net(drv)
        js_click(drv, sub)
        time.sleep(3)
        print('edit requests:', json.dumps([n for n in net(drv) if '/evaluation/categories' in n['url']],
                                           ensure_ascii=False)[:600])
        time.sleep(1)
        now = cats()
        names = [c['name'] for c in now]
        print('after edit categories:', names)
        print('renamed exists:', C2 in names, '| original exists:', C1 in names)
        drv.save_screenshot(os.path.join(ART, 'INT1484_20_category_edit_after_save.png'))

        # ---- 2) 分类删除确认 ----
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
        time.sleep(1.5)
        js_click(drv, one(drv, "//button[@role='tab'][normalize-space(.)='分组视图']"))
        time.sleep(1.5)
        target = C2 if C2 in [c['name'] for c in cats()] else C1
        try:
            js_click(drv, one(drv, "//button[@aria-label='删除分类 %s']" % target, timeout=15))
            time.sleep(1.2)
            slots = [s.get_attribute('data-slot') for s in drv.find_elements(By.CSS_SELECTOR, '[data-slot]')]
            print('slots with dialog:', sorted(set(x for x in slots if 'dialog' in (x or ''))))
            body = drv.find_element(By.TAG_NAME, 'body').text
            print('body has delete confirm:', '确定删除分类' in body)
            drv.save_screenshot(os.path.join(ART, 'INT1484_18_delete_category_confirm_light.png'))
            btn = one(drv, "//*[@data-slot='alert-dialog-content']//button[normalize-space(.)='删除']", timeout=10)
            clear_net(drv)
            js_click(drv, btn)
            time.sleep(2.5)
            print('delete requests:', json.dumps([n for n in net(drv) if '/evaluation/categories' in n['url']],
                                                 ensure_ascii=False)[:400])
            print('categories after delete:', [c['name'] for c in cats()])
        except Exception as e:
            print('delete flow error:', e)

        # ---- 3) 抽屉遮罩点击 ----
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
        time.sleep(1.2)
        js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']"))
        time.sleep(1.2)
        overlay = drv.find_element(By.XPATH, "//*[@data-slot='sheet-overlay']")
        box = drv.execute_script("return (function(e){var r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]}) (arguments[0])", overlay)
        print('overlay box', box, 'sheet present', bool(drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']")))
        ActionChains(drv).move_to_element_with_offset(overlay, 20, 20).click().perform()
        time.sleep(1.2)
        print('after overlay click sheet present:', bool(drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']")))
        drv.save_screenshot(os.path.join(ART, 'INT1484_21_overlay_click.png'))
    finally:
        drv.quit()
        for d in call('GET', '/evaluation/dimensions?per_page=1000')[1]['data']['items']:
            if d['name'].startswith('接线测试_INT1484_probeD_'):
                print('cleanup dim', d['id'], call('DELETE', '/evaluation/dimensions/%s' % d['id'])[0])
        for c in cats():
            if c['name'].startswith('接线测试_INT1484_probeC_'):
                print('cleanup cat', c['id'], c['name'], call('DELETE', '/evaluation/categories/%s' % c['id'])[0])


if __name__ == '__main__':
    main()
