# -*- coding: utf-8 -*-
"""INT-1486 复走补测 G：api-edit / api-health 浅深截图与保存回读、filter-all 空筛选入口拦截。"""
import json, os, time, urllib.parse, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SUF = str(int(time.time()))[-6:]
NAME = '接线测试_INT1486_GAPI_' + SUF
NAME2 = NAME + '_改'
EMPTY_KEYWORD = 'ZZZ_NO_MATCH_INT1486'
report = {'checks': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | ' + str(detail)[:300])


token = open(os.path.join(ART, 'token.txt')).read().strip()


def req(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:300]


FETCH = r"""
window.__fetchLog=[];const f=window.fetch;
window.fetch=function(i,init){let u=typeof i==='string'?i:(i&&i.url)||'';const m=(init&&init.method)||(i&&i.method)||'GET';
const e={url:String(u),method:m,status:null,reqBody:init&&init.body?String(init.body).slice(0,20000):null};
window.__fetchLog.push(e);return f.apply(this,arguments).then(r=>{e.status=r.status;return r;}).catch(err=>{e.status='ERR';throw err;});};
"""


def driver():
    o = Options(); o.binary_location = CHROME
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run']:
        o.add_argument(a)
    cache = r'D:\00_user_data\.cache\selenium\chromedriver\win64'
    path = ''
    for v in os.listdir(cache):
        exe = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(exe):
            path = exe
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH})
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text(d):
    return d.execute_script('return document.body.innerText') or ''


def dialogs(d):
    return [x for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if x.is_displayed()]


def dtext(d):
    ds = dialogs(d)
    return '\n'.join(x.text for x in ds) if ds else ''


def shot(d, n):
    p = os.path.join(ART, n)
    d.save_screenshot(p); print('SHOT', n, os.path.getsize(p))


def close_dialog(d):
    for _ in range(3):
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        if not dialogs(d):
            return True
    return not dialogs(d)


def enter_step2(d, keyword=None):
    d.get(BASE + '/start-test')
    wait = WebDriverWait(d, 90)
    wait.until(lambda x: '按分组' in text(x))
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
            break
        time.sleep(2)
    time.sleep(2)
    if keyword:
        inp = d.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索用例名称或描述"]')
        if inp:
            inp[0].send_keys(Keys.CONTROL, 'a'); inp[0].send_keys(Keys.DELETE)
            inp[0].send_keys(keyword); time.sleep(6)
    nxt = d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")
    if not nxt:
        return False, 'no next button'
    js_click(d, nxt[0])
    try:
        wait.until(lambda x: '执行参数' in text(x))
    except Exception:
        return False, 'step2 not reached'
    time.sleep(3)
    return True, text(d)


def wait_api_card(d, name, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        els = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 API {name}"]')
        if els:
            return els
        time.sleep(2)
    return []


def card_of(d, el):
    return d.execute_script('''
      let n = arguments[0];
      while (n && n !== document.body) {
        if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
        n = n.parentElement;
      }
      return arguments[0].parentElement;
    ''', el)


def open_edit(d, name):
    cb = wait_api_card(d, name)
    if not cb:
        return False
    # 由卡片自己的勾选框向上定位它所在卡片，避免误命中同列表其它 API 的「更多操作」
    more = d.find_elements(
        By.XPATH,
        f'//*[@aria-label="选择 API {name}"]/ancestor::div[.//button[@aria-label="更多操作"]][1]//button[@aria-label="更多操作"]')
    if not more:
        return False
    js_click(d, more[0]); time.sleep(1.2)
    mi = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
    if not mi:
        return False
    js_click(d, mi[0]); time.sleep(2.5)
    return bool(d.find_elements(By.ID, 'api-name'))


def main():
    st, hc = req('POST', '/api/v1/apis', {
        'name': NAME, 'description': 'INT-1486 复走补测', 'algorithm_type': 'voice_llm', 'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://example.test/int1486-g', 'name': None, 'max_process': 1,
                       'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                       'description': None}]})
    api_id = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
    chk('G0 临时 API 创建', st < 300 and api_id, {'status': st, 'id': api_id})
    d = driver()
    try:
        # ---- api-edit 浅色 + 回填 + 改名保存 + GET 回读 ----
        ok, _ = enter_step2(d, 'JG0081')
        chk('G1 进入步骤二', ok)
        opened = open_edit(d, NAME)
        chk('G2 api-edit 打开', opened, dtext(d)[:200])
        if opened:
            back = d.find_element(By.ID, 'api-name').get_attribute('value')
            urls = d.find_elements(By.CSS_SELECTOR, "input[aria-label='端点 URL']")
            burl = urls[0].get_attribute('value') if urls else None
            chk('G3 编辑回填名称', back == NAME, repr(back))
            chk('G4 编辑回填端点 URL', burl == 'https://example.test/int1486-g', repr(burl))
            shot(d, 'F_api_edit_light.png')
            if back != NAME:
                # 兜底：回填不是本 run 自建记录 → 绝不写入，避免改到真实数据
                chk('G5 改名保存 GET 回读', False, '回填名称不符，已中止写入')
                close_dialog(d)
                raise SystemExit('edit dialog targets a foreign API: %r' % back)
            ni = d.find_element(By.ID, 'api-name')
            ni.send_keys(Keys.CONTROL, 'a'); ni.send_keys(Keys.DELETE); ni.send_keys(NAME2)
            time.sleep(0.8)
            js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']")[0])
            try:
                WebDriverWait(d, 60).until(lambda x: '修改被测 API 配置' not in dtext(x))
            except Exception:
                pass
            time.sleep(2)
            st, one = req('GET', f'/api/v1/apis/{api_id}')
            nm = ((one.get('data') or {}) if isinstance(one, dict) else {}).get('name')
            chk('G5 改名保存 GET 回读', nm == NAME2, {'status': st, 'name': nm})
            # 重开核对回填新名
            opened2 = open_edit(d, NAME2)
            v2 = d.find_element(By.ID, 'api-name').get_attribute('value') if opened2 else None
            chk('G6 重开回读新名', v2 == NAME2, repr(v2))
            close_dialog(d)

        # ---- api-health 浅色 ----
        hb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {NAME2}"]')
        if not hb:
            hb = wait_api_card(d, NAME2)  # 卡片可能仍在异步加载
            hb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {NAME2}"]')
        chk('G7 api-health 入口', bool(hb), len(hb))
        if hb:
            js_click(d, hb[0]); time.sleep(0.8)
            try:
                WebDriverWait(d, 90).until(lambda x: '重新测试' in dtext(x) or not dialogs(x))
            except Exception:
                pass
            ht = dtext(d)
            chk('G8 api-health 结果态', '重新测试' in ht, ht[:300])
            shot(d, 'F_api_health_light.png')
            close_dialog(d)

        # ---- 深色 api-edit / api-health ----
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        ok, _ = enter_step2(d, 'JG0081')
        chk('G9 深色下进入步骤二', ok)
        if open_edit(d, NAME2):
            shot(d, 'F_api_edit_dark.png')
            close_dialog(d)
        hb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {NAME2}"]')
        if hb:
            js_click(d, hb[0])
            try:
                WebDriverWait(d, 90).until(lambda x: '重新测试' in dtext(x) or not dialogs(x))
            except Exception:
                pass
            time.sleep(1)
            shot(d, 'F_api_health_dark.png')
            close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        # ---- C8 空筛选入口拦截（到步骤二点开始测试） ----
        ok, body = enter_step2(d, EMPTY_KEYWORD)
        print('C8 step2 body', [ln for ln in body.splitlines() if '条用例' in ln or '执行参数' in ln][:4] if ok else body)
        mark = len(d.execute_script('return window.__fetchLog || []'))
        starts = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        print('C8 start buttons', len(starts))
        if starts:
            js_click(d, starts[-1]); time.sleep(3)
        t = text(d)
        posts = [e for e in d.execute_script('return window.__fetchLog || []')[mark:]
                 if '/tasks' in e['url'] and e['method'] == 'POST']
        toast = [ln for ln in t.splitlines() if '没有可用' in ln or '调整筛选' in ln][:3]
        chk('G10 空筛选 开始测试 后无 POST /tasks', len(posts) == 0, [p['url'] for p in posts])
        chk('G11 空筛选提示调整筛选条件', bool(toast), toast)
        shot(d, 'F_filter_empty_blocked_light.png')
    finally:
        d.quit()
        # 只删本 run 自建的记录（按 id），不按名称前缀扫库
        if api_id:
            print('CLEAN api', api_id, req('DELETE', f'/api/v1/apis/{api_id}')[0])
        st, apis = req('GET', '/api/v1/apis?per_page=1000')
        residue = [(x.get('id'), x.get('name')) for x in (apis.get('data', apis) or {}).get('items', [])
                   if '接线测试_INT1486' in (x.get('name') or '')]
        print('RESIDUE', residue)
        report['residue'] = residue
        with open(os.path.join(ART, 'rewalk_g_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'total': len(report['checks'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
