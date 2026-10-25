# -*- coding: utf-8 -*-
"""INT-1477 复走·用例域：批量七窗逐项提交 + GET 回读 + 回收站链路 + 清理。

OPS 环境变量选择操作（逗号分隔）：
  group, tags, dims, spl, noise, device, algo, trash, restore, purge, cleanup
"""
import json
import os
import sys
import time
import urllib.parse

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
TAG2 = '接线测试_INT1477标签2'
GROUP = '接线测试_INT1477分组'
NAMES = ['接线测试_INT1477_A', '接线测试_INT1477_B', '接线测试_INT1477_C']
OPS = [s for s in (os.environ.get('OPS') or '').split(',') if s]
EVID = []
OUT = {}


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


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


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


def click_text(d, t, tag='*', exact=True, timeout=20):
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
                                    'post': (r.get('postData') or '')[:700]}
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


def unwrap(r):
    j = r.get('json') or {}
    return j.get('data', j)


def list_cases(d, name):
    r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&keyword=' + urllib.parse.quote(name))
    data = unwrap(r)
    items = data.get('items') if isinstance(data, dict) else data
    return [x for x in (items or []) if x.get('name') == name]


def get_case(d, cid):
    r = api(d, 'GET', f'/api/v1/testcases/{cid}')
    return unwrap(r)


def readback_all(d, label):
    """逐条 GET 回读 A/B/C，摘要关键字段。"""
    got = {}
    for n in NAMES:
        hits = list_cases(d, n)
        if not hits:
            got[n] = None
            continue
        detail = get_case(d, hits[0]['id'])
        got[n] = {
            'id': detail.get('id'),
            'name': detail.get('name'),
            'description': detail.get('description'),
            'group_id': detail.get('group_id'),
            'group_name': detail.get('group_name'),
            'tags': detail.get('tags'),
            'is_deleted': detail.get('is_deleted'),
            'config': detail.get('config'),
            'algorithm_type': detail.get('algorithm_type'),
        }
    OUT[label] = got
    log('  readback', label, json.dumps(
        {k: ({'g': (v or {}).get('group_name'), 'tags': (v or {}).get('tags'),
              'del': (v or {}).get('is_deleted')} if v else None) for k, v in got.items()},
        ensure_ascii=False))
    return got


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


def reload_page(d, view='by-group'):
    d.get(BASE + f'/testcases/{view}?rw=%d' % int(time.time()))
    wait_page(d)


def expand_group(d, gname, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']")
               if e.is_displayed()]
        if els:
            jsclick(d, els[0])
            time.sleep(2.2)
            return
        more = [e for e in d.find_elements(By.XPATH,
                                           "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if more:
            jsclick(d, more[0])
            time.sleep(1.5)
            continue
        time.sleep(0.6)
    raise AssertionError('未找到分组 ' + gname)


def select_cases(d, names, timeout=15):
    """确保分组展开并逐条勾选（勾选后再确认 aria-checked=true）。"""
    end = time.time() + timeout
    picked = []
    while time.time() < end and len(picked) < len(names):
        for n in names:
            if n in picked:
                continue
            boxes = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
                     if e.is_displayed() and (e.get_attribute('aria-label') or '') == f'选择 {n}']
            if boxes:
                jsclick(d, boxes[0])
                time.sleep(0.5)
                picked.append(n)
        if len(picked) < len(names):
            time.sleep(0.8)
    time.sleep(0.8)
    return picked


def add_tag(d, value):
    el = d.find_element(By.XPATH, "//input[@placeholder='输入标签，按回车或逗号添加']")
    jsclick(d, el)
    el.send_keys(value)
    el.send_keys(Keys.ENTER)
    time.sleep(0.6)


def pick_select(d, frag, option_text):
    trig = d.find_element(By.XPATH,
                          f"//button[@role='combobox'][contains(normalize-space(.),'{frag}')]")
    jsclick(d, trig)
    time.sleep(0.9)
    opt = d.find_element(By.XPATH, f"//*[@role='option'][normalize-space(.)='{option_text}']")
    jsclick(d, opt)
    time.sleep(0.6)


def pick_combo_option(d, label_frag, option_text):
    """按 label 定位下拉触发器（closed dialog combobox 残留坑），再点选项。"""
    trig = d.find_element(
        By.XPATH,
        f"//label[contains(normalize-space(.),'{label_frag}')]/following-sibling::button[@role='combobox']")
    jsclick(d, trig)
    time.sleep(0.9)
    opt = d.find_element(By.XPATH, f"//*[@role='option'][normalize-space(.)='{option_text}']")
    jsclick(d, opt)
    time.sleep(0.6)


def close_dialog(d, n=2):
    for _ in range(n):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.8)


def dialog_text(d):
    for e in d.find_elements(By.XPATH, "//*[@role='dialog' or @role='alertdialog']"):
        if e.is_displayed():
            return (e.text or '')
    return ''


def run_batch(d, label, action, shot_prefix, after=None):
    """勾选 A/B/C → 打开批量窗 → after(d) 交互 → 确定 → 记录。"""
    res = {'label': label}
    try:
        clear_log(d)
        click_text(d, label, 'button', timeout=15)
        time.sleep(2)
        shot(d, shot_prefix + '_open')
        res['dialog'] = dialog_text(d)[:600]
        if after:
            after(d)
            time.sleep(0.6)
        clear_log(d)
        click_text(d, '确定', 'button', timeout=15)
        time.sleep(3.5)
        cs = calls(d)
        shot(d, shot_prefix + '_done')
        res['calls'] = cs
        rec(f'batch:{label}', f'{label} 提交', cs, {'dialog': res['dialog'][:400]})
    except Exception as e:
        res['error'] = str(e)
        log('  FAIL', label, e)
        close_dialog(d)
    return res


def current_group(d):
    """用 API 读 A 当前所在分组名（批量调整分组后分组会变）。"""
    hits = list_cases(d, NAMES[0])
    return (hits[0].get('group_name') if hits else None) or GROUP


def do_batch(d, label, prefix, after):
    picked = select_cases(d, NAMES)
    if len(picked) < len(NAMES):
        log('  picked', picked, '→ 重新展开分组再试')
        try:
            expand_group(d, current_group(d))
        except Exception as e:
            log('  expand retry fail', e)
        picked = select_cases(d, NAMES)
    log('  picked', picked)
    if len(picked) < len(NAMES):
        raise AssertionError('勾选不足: ' + str(picked))
    return run_batch(d, label, None, prefix, after)


def main():
    d = driver()
    try:
        reload_page(d)
        if 'group' in OPS:
            expand_group(d, current_group(d))
            res = do_batch(d, '批量调整分组', 'crud_batch_group',
                           lambda dd: pick_select(dd, '请选择分', '接线测试_INT1477分组'))
            OUT['group'] = res
            readback_all(d, 'after_group')
        if 'tags' in OPS:
            reload_page(d)
            expand_group(d, current_group(d))
            res = do_batch(d, '批量管理标签', 'crud_batch_tags', lambda dd: add_tag(dd, TAG2))
            OUT['tags'] = res
            readback_all(d, 'after_tags')
        if 'dims' in OPS:
            reload_page(d)
            gname = (readback_all(d, 'pre_dims') or {}).get(NAMES[0], {}) or {}
            expand_group(d, gname.get('group_name') or GROUP)
            def _dims(dd):
                boxes = [e for e in dd.find_elements(By.XPATH, "//*[@role='checkbox']")
                         if e.is_displayed()]
                if boxes:
                    jsclick(dd, boxes[0])
                    time.sleep(1)
            res = do_batch(d, '批量设置评估维度', 'crud_batch_dims', _dims)
            res['round_tabs'] = [e.text for e in d.find_elements(By.XPATH, "//*[@role='tab']")
                                 if e.is_displayed()]
            OUT['dims'] = res
            readback_all(d, 'after_dims')
        if 'spl' in OPS:
            reload_page(d)
            gname = (readback_all(d, 'pre_spl') or {}).get(NAMES[0], {}) or {}
            expand_group(d, gname.get('group_name') or GROUP)
            def _spl(dd):
                inp = dd.find_element(By.XPATH,
                                      "//input[contains(@placeholder,'请输入声压级')]")
                jsclick(dd, inp)
                inp.send_keys('65')
                time.sleep(0.5)
            res = do_batch(d, '批量设置声压', 'crud_batch_spl', _spl)
            OUT['spl'] = res
            readback_all(d, 'after_spl')
        if 'noise' in OPS:
            reload_page(d)
            expand_group(d, current_group(d))
            res = do_batch(d, '批量设置噪声', 'crud_batch_noise', None)
            OUT['noise'] = res
            readback_all(d, 'after_noise')
        if 'device' in OPS:
            reload_page(d)
            expand_group(d, current_group(d))
            def _dev(dd):
                boxes = [e for e in dd.find_elements(By.XPATH, "//*[@role='checkbox']")
                         if e.is_displayed()]
                if boxes:
                    jsclick(dd, boxes[0])
                    time.sleep(1)
            res = do_batch(d, '批量设置播放设备', 'crud_batch_device', _dev)
            OUT['device'] = res
            readback_all(d, 'after_device')
        if 'algo' in OPS:
            reload_page(d)
            expand_group(d, current_group(d))
            res = do_batch(d, '批量设置专属参数', 'crud_batch_algo', None)
            OUT['algo'] = res
            readback_all(d, 'after_algo')
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
    json.dump(OUT, open(os.path.join(ART, 'crud_batch.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    log('OPS DONE', OPS)


if __name__ == '__main__':
    main()
