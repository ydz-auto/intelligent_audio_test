# -*- coding: utf-8 -*-
"""INT-1477 复走·用例域：真实写闭环（新建 / GET 逐字段回读 / 编辑 / 删除）。

docker 真实栈：前端 15173 / 网关 15000 / 主库 intelligent_audio_test。
只写「接线测试_INT1477_」前缀数据，脚本末尾（配合 verify_int1477_crud_cleanup.py）清理。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)

TAG = '接线测试_INT1477标签'
GROUP = '接线测试_INT1477分组'
NAMES = ['接线测试_INT1477_A', '接线测试_INT1477_B', '接线测试_INT1477_C']
EVID = []


def log(*a):
    print(*a, flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(90)
    return d


def find(d, t, tag='*', exact=True, timeout=0):
    end = time.time() + timeout
    while True:
        cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
        for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
            if e.is_displayed():
                return e
        if time.time() > end:
            return None
        time.sleep(0.4)


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def click_text(d, t, tag='*', exact=True, timeout=15):
    e = find(d, t, tag, exact, timeout)
    if not e:
        raise AssertionError('未找到: ' + t)
    jsclick(d, e)
    return e


def shot(d, name):
    d.save_screenshot(os.path.join(ART, name + '.png'))
    log('  shot:', name)


def clear_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def calls(d):
    reqs = {}
    try:
        logs = d.get_log('performance')
    except Exception:
        return []
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        p = m.get('params', {})
        if m.get('method') == 'Network.requestWillBeSent':
            r = p['request']
            if '/api/' not in r['url']:
                continue
            reqs[p['requestId']] = {'method': r['method'],
                                    'url': r['url'].split(BASE)[-1],
                                    'status': None,
                                    'post': (r.get('postData') or '')[:600]}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def show(cs):
    return ' ; '.join(f"{c['method']} {c['url'].split('?')[0]} -> {c['status']}" for c in cs)


def rec(window, note, cs=None, extra=None):
    item = {'window': window, 'theme': 'light', 'note': note, 'calls': cs or []}
    if extra:
        item.update(extra)
    EVID.append(item)
    log(f'  [{window}] {note} | {show(cs or [])}')
    return item


def api(d, method, path, body=None):
    js = """
    var cb = arguments[arguments.length-1];
    var m = arguments[0], u = arguments[1], b = arguments[2];
    var opt = {method: m, headers: {'Accept':'application/json'}};
    if (b !== null) { opt.headers['Content-Type']='application/json'; opt.body = b; }
    fetch(u, opt).then(r => r.text().then(t => cb({status:r.status, body:t})))
      .catch(e => cb({status:-1, body:String(e)}));
    """
    d.set_script_timeout(40)
    r = d.execute_async_script(js, method, BASE + path,
                               None if body is None else json.dumps(body))
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


def wait_drawer(d, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog']"):
            if e.is_displayed() and '用例名称' in (e.text or ''):
                return e
        time.sleep(0.4)
    raise AssertionError('用例抽屉未出现')


def wait_page(d, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if '用例管理' in d.find_element(By.TAG_NAME, 'body').text:
                time.sleep(1.5)
                return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError('用例页未就绪')


def set_input(d, css_or_id, value, by=By.ID):
    el = d.find_element(by, css_or_id)
    jsclick(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


def add_tag(d, value):
    el = d.find_element(By.XPATH, "//input[@placeholder='输入标签，按回车或逗号添加']")
    jsclick(d, el)
    el.send_keys(value)
    el.send_keys(Keys.ENTER)
    time.sleep(0.6)


def pick_select(d, trigger_text, option_text):
    """base-ui Select：点触发器 → 点选项。"""
    trig = d.find_element(By.XPATH,
                          f"//button[@role='combobox'][contains(normalize-space(.),'{trigger_text}')]")
    jsclick(d, trig)
    time.sleep(0.8)
    opt = d.find_element(By.XPATH, f"//*[@role='option'][normalize-space(.)='{option_text}']")
    jsclick(d, opt)
    time.sleep(0.6)


def create_case(d, name, desc, tag=None, new_group=None):
    cs0 = None
    click_text(d, '新增用例', 'button')
    wait_drawer(d)
    time.sleep(1.2)
    set_input(d, 'case-name', name)
    if desc:
        set_input(d, 'case-desc', desc, By.ID)
    if tag:
        add_tag(d, tag)
    if new_group:
        pick_select(d, '请选择分组', '+ 新建分组')
        inp = d.find_element(By.CSS_SELECTOR, "input[aria-label='新分组名称']")
        jsclick(d, inp)
        inp.send_keys(new_group)
        time.sleep(0.4)
    clear_log(d)
    click_text(d, '保存', 'button')
    time.sleep(3.5)
    cs = calls(d)
    shot(d, f'crud_create_{name[-1]}')
    return cs


def main():
    d = driver()
    out = {}
    try:
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_page(d)
        log('URL', d.current_url)

        created = []
        for i, name in enumerate(NAMES):
            cs = create_case(d, name, f'复走新建 {name}',
                             tag=TAG, new_group=GROUP if i == 0 else None)
            rec('case-mutate-drawer', f'新建 {name} 提交', cs)
            # 回读
            r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&keyword=' +
                    __import__('urllib.parse', fromlist=['quote']).quote(name))
            items = (r.get('json') or {}).get('data', {})
            lst = items.get('items') if isinstance(items, dict) else items
            lst = lst or []
            hit = [x for x in lst if x.get('name') == name]
            out[name] = {'create_calls': cs, 'list': r['status'],
                         'found': bool(hit), 'item': hit[0] if hit else None}
            rec('GET /testcases', f'回读 {name}（status={r["status"]}）', [],
                {'readback': hit[0] if hit else None})
            log('  found', bool(hit), json.dumps(hit[0], ensure_ascii=False)[:400] if hit else '')
            # 关抽屉（保存后已自动关闭，这里兜底）
            try:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
            time.sleep(1)

        json.dump(out, open(os.path.join(ART, 'crud_created.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    ev = os.path.join(ART, 'evidence.json')
    merged = []
    if os.path.isfile(ev):
        try:
            merged = json.load(open(ev, encoding='utf-8'))
        except Exception:
            merged = []
    merged += EVID
    json.dump(merged, open(ev, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    log('DONE')


if __name__ == '__main__':
    main()
