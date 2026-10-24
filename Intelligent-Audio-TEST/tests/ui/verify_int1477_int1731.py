# -*- coding: utf-8 -*-
"""INT-1477 / INT-1731 四窗轮次范围复测（专属参数 / 播放设备 / 声压 / 噪声）。

docker 真实栈：前端 15173（新镜像，含 INT-1731 合入）/ 网关 15000 / 主库 intelligent_audio_test。
夹具：自建 2 轮用例 2 条（「接线测试_INT1477R」前缀），脚本末尾清理。
"""
import json
import os
import re
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

TAG = time.strftime('%m%d%H%M')
GROUP = '接线测试_INT1477R组' + TAG
NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']
OLDNAME = '接线测试_INT1477R_probe'
WINDOWS = [
    ('params', '批量设置专属参数', '批量设置用例专属参数'),
    ('device', '批量设置播放设备', '批量设置播放设备'),
    ('spl', '批量设置声压', '批量设置声压级'),
    ('noise', '批量设置噪声', '批量设置噪声'),
]
OUT = {'env': {}, 'fixtures': {}, 'windows': {}, 'submit': {}, 'cleanup': {}}


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


def find_text(d, t, tag='*', exact=True, timeout=0):
    end = time.time() + timeout
    while True:
        cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
        for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
            if e.is_displayed():
                return e
        if time.time() > end:
            return None
        time.sleep(0.4)


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
                                    'post': (r.get('postData') or '')[:900]}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def api(d, method, path, body=None):
    js = """
    var cb = arguments[arguments.length-1];
    var m = arguments[0], u = arguments[1], b = arguments[2];
    var opt = {method: m, headers: {'Accept':'application/json'}};
    if (b !== null) { opt.headers['Content-Type']='application/json'; opt.body = b; }
    fetch(u, opt).then(r => r.text().then(t => cb({status:r.status, body:t})))
      .catch(e => cb({status:-1, body:String(e)}));
    """
    d.set_script_timeout(90)
    r = d.execute_async_script(js, method, BASE + path,
                               None if body is None else json.dumps(body))
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


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


def ensure_group_visible(d, gname, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']"):
            if e.is_displayed():
                return e
        more = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if more:
            jsclick(d, more[0])
            time.sleep(1.5)
            continue
        time.sleep(0.8)
    return None


def expand_group(d, gname):
    els = [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']")
           if e.is_displayed()]
    if not els:
        raise AssertionError('未找到分组名 ' + gname)
    jsclick(d, els[0])
    end = time.time() + 40
    while time.time() < end:
        time.sleep(1.5)
        body = d.find_element(By.TAG_NAME, 'body').text
        if all(n in body for n in NAMES):
            return
    raise AssertionError('分组展开后未看到用例卡')


def select_cases(d):
    picked = 0
    for n in NAMES:
        boxes = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
                 if e.is_displayed() and (e.get_attribute('aria-label') or '') == f'选择 {n}']
        if not boxes:
            continue
        jsclick(d, boxes[0])
        picked += 1
        time.sleep(0.6)
    time.sleep(1.0)
    return picked


def open_page(d, dark=False):
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    if dark:
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time() + 1))
    wait_page(d)
    ensure_group_visible(d, GROUP)
    time.sleep(1.0)
    expand_group(d, GROUP)
    n = select_cases(d)
    if n != len(NAMES):
        raise AssertionError('勾选用例数不符: %d' % n)
    time.sleep(0.8)


def dialog(d, title, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        ds = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
              if e.is_displayed() and title in (e.text or '')]
        if ds:
            return ds[-1]
        time.sleep(0.4)
    return None


def round_labels(dlg):
    out = []
    for e in dlg.find_elements(By.XPATH, ".//*[starts-with(normalize-space(.),'第') and contains(normalize-space(.),'轮')]"):
        try:
            t = (e.text or '').strip()
        except Exception:
            continue
        if re.fullmatch(r'第\d+轮', t) and e.is_displayed():
            if t not in out:
                out.append(t)
    return out


def open_window(d, btn_label, dlg_title):
    b = find_text(d, btn_label, 'button', True, 15)
    if not b:
        raise AssertionError('未找到批量按钮: ' + btn_label)
    jsclick(d, b)
    dlg = dialog(d, dlg_title, 20)
    if not dlg:
        raise AssertionError('弹窗未出现: ' + dlg_title)
    return dlg


def close_dialog(d, dlg):
    b = find_text(d, '取消', 'button', True, 5)
    if b:
        jsclick(d, b)
    else:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)


def click_label(d, dlg, text):
    for e in dlg.find_elements(By.XPATH, f".//label[contains(normalize-space(.),'{text}')]"):
        if e.is_displayed():
            jsclick(d, e)
            time.sleep(0.8)
            return True
    return False


def window_probe(d, key, btn_label, dlg_title, theme):
    rec = {}
    dlg = open_window(d, btn_label, dlg_title)
    rec['dialog_title'] = dlg_title
    rec['description'] = (dlg.text or '').split('\n')[:3]
    # 所有轮次（统一设置）默认档的可见文本
    rec['all_mode_visible'] = '所有轮次（统一设置）' in (dlg.text or '')
    # 指定轮次
    if not click_label(d, dlg, '指定轮次（统一设置）'):
        raise AssertionError('未找到「指定轮次」档')
    rec['specific_rounds'] = round_labels(dlg)
    rec['specific_ok'] = rec['specific_rounds'] == ['第1轮', '第2轮']
    shot(d, f'r_{key}_{theme}_specific')
    # 逐轮设置
    if not click_label(d, dlg, '逐轮设置（每轮可不同）'):
        raise AssertionError('未找到「逐轮设置」档')
    rec['per_round_rounds'] = round_labels(dlg)
    rec['per_round_ok'] = rec['per_round_rounds'] == ['第1轮', '第2轮']
    shot(d, f'r_{key}_{theme}_per_round')
    close_dialog(d, dlg)
    return rec


def submit_cases(d, ids_by_name):
    """声压窗三种提交：指定第2轮 / 指定轮次空勾选 / 逐轮仅第2轮。"""
    out = {}
    detail_path = '/api/v1/testcases/'

    def round_state(cid):
        r = api(d, 'GET', detail_path + str(cid))
        data = (r.get('json') or {}).get('data') or {}
        rounds = ((data.get('config') or {}).get('rounds') or [])
        return [{'round_number': x.get('round_number'), 'spl': x.get('spl'),
                 'spl_value': x.get('spl_value'), 'spl_db': x.get('spl_db')} for x in rounds]

    def all_states():
        return {n: round_state(ids_by_name[n]) for n in NAMES}

    # (a) 指定轮次 → 只勾第2轮
    clear_log(d)
    dlg = open_window(d, '批量设置声压', '批量设置声压级')
    click_label(d, dlg, '指定轮次（统一设置）')
    # 默认勾选第1轮 → 取消，改勾第2轮
    for lbl in ('第1轮', '第2轮'):
        for e in dlg.find_elements(By.XPATH, f".//label[normalize-space(.)='{lbl}']"):
            if e.is_displayed():
                jsclick(d, e)
                time.sleep(0.6)
                break
    inp = dlg.find_element(By.XPATH, ".//input[@aria-label='声压级 dB']")
    inp.send_keys('65')
    time.sleep(0.5)
    b = [x for x in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']") if x.is_displayed()]
    jsclick(d, b[0])
    t0 = time.time()
    while time.time() - t0 < 150:
        time.sleep(2)
        if not [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
                if e.is_displayed() and '批量设置声压级' in (e.text or '')]:
            break
    cs = calls(d)
    batch = [c for c in cs if '/testcases/batch' in c['url']]
    out['specific_submit'] = {'elapsed': round(time.time() - t0, 1), 'batch': batch,
                              'toast': [e.text for e in d.find_elements(By.XPATH, "//*[@data-sonner-toast]")
                                        if e.is_displayed()]}
    out['readback_after_specific'] = all_states()

    # (b) 指定轮次但不勾任何轮次 → 应只提示、不发请求
    clear_log(d)
    dlg = open_window(d, '批量设置声压', '批量设置声压级')
    click_label(d, dlg, '指定轮次（统一设置）')
    for lbl in ('第1轮',):
        for e in dlg.find_elements(By.XPATH, f".//label[normalize-space(.)='{lbl}']"):
            if e.is_displayed():
                jsclick(d, e)
                time.sleep(0.6)
                break
    inp = dlg.find_element(By.XPATH, ".//input[@aria-label='声压级 dB']")
    inp.send_keys('66')
    time.sleep(0.5)
    b = [x for x in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']") if x.is_displayed()]
    jsclick(d, b[0])
    time.sleep(3.0)
    cs = calls(d)
    out['empty_rounds_submit'] = {
        'batch': [c for c in cs if '/testcases/batch' in c['url']],
        'toast': [e.text for e in d.find_elements(By.XPATH, "//*[@data-sonner-toast]")
                  if e.is_displayed()],
        'dialog_still_open': bool(dialog(d, '批量设置声压级', 2)),
    }
    shot(d, 'r_spl_empty_rounds')
    close_dialog(d, dialog(d, '批量设置声压级', 5) or dlg)

    # (c) 逐轮设置只编辑第2轮
    clear_log(d)
    dlg = open_window(d, '批量设置声压', '批量设置声压级')
    click_label(d, dlg, '逐轮设置（每轮可不同）')
    tabs = [e for e in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='第2轮']") if e.is_displayed()]
    if tabs:
        jsclick(d, tabs[0])
        time.sleep(0.8)
    inp = dlg.find_elements(By.XPATH, ".//input[@aria-label='声压级 dB']")
    inp = [x for x in inp if x.is_displayed()][0]
    inp.send_keys('67')
    time.sleep(0.5)
    b = [x for x in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']") if x.is_displayed()]
    jsclick(d, b[0])
    t0 = time.time()
    while time.time() - t0 < 150:
        time.sleep(2)
        if not [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
                if e.is_displayed() and '批量设置声压级' in (e.text or '')]:
            break
    cs = calls(d)
    out['per_round_submit'] = {'elapsed': round(time.time() - t0, 1),
                               'batch': [c for c in cs if '/testcases/batch' in c['url']],
                               'toast': [e.text for e in d.find_elements(By.XPATH, "//*[@data-sonner-toast]")
                                         if e.is_displayed()]}
    out['readback_after_per_round'] = all_states()
    return out


def create_fixtures(d):
    ids = []
    for n in NAMES:
        body = {
            'name': n, 'group': GROUP,
            'config': {
                'rounds': [
                    {'round_number': 1, 'audios': [], 'evaluation': {'enabled': True, 'dimensions': []}},
                    {'round_number': 2, 'audios': [], 'evaluation': {'enabled': True, 'dimensions': []}},
                ],
                'dimensions': [], 'background_noise': None,
            },
            'tags': [], 'algorithm_params': [], 'strategy_id': '',
        }
        r = api(d, 'POST', '/api/v1/testcases', body)
        cid = ((r.get('json') or {}).get('data') or {}).get('id')
        ids.append({'name': n, 'id': cid, 'status': r['status']})
    return ids


def cleanup(d):
    out = {}
    try:
        r = api(d, 'GET', '/api/v1/groups?page=1&per_page=200')
        data = (r.get('json') or {}).get('data') or {}
        items = data.get('items') if isinstance(data, dict) else data
        for g in items or []:
            if g.get('name') == GROUP or g.get('name') == '接线测试_INT1477R组探针':
                dg = api(d, 'DELETE', '/api/v1/groups/%s?cascade=true' % g.get('id'))
                out['group:' + str(g.get('name'))] = {'id': g.get('id'), 'delete': dg['status']}
    except Exception as e:
        out['groups'] = {'error': repr(e)}
    import urllib.parse
    for n in NAMES + [OLDNAME]:
        for q in ('', '&only_deleted=true'):
            try:
                r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&keyword=' +
                        urllib.parse.quote(n) + q)
                data = (r.get('json') or {}).get('data') or {}
                lst = data.get('items') if isinstance(data, dict) else data
                for it in lst or []:
                    if it.get('name') != n:
                        continue
                    cid = it.get('id')
                    if not q:
                        api(d, 'DELETE', '/api/v1/testcases/' + str(cid))
                    p = api(d, 'DELETE', '/api/v1/testcases/' + str(cid) + '/purge')
                    out[n + ':' + str(cid)] = {'purge': p['status']}
            except Exception as e:
                out[n + q] = {'error': repr(e)}
    return out


def main():
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group')
        wait_page(d)
        OUT['env']['auth_mode'] = api(d, 'GET', '/api/v1/auth/mode').get('json')
        OUT['env']['health'] = api(d, 'GET', '/health').get('json')
        OUT['fixtures']['created'] = create_fixtures(d)
        log('fixtures', json.dumps(OUT['fixtures']['created'], ensure_ascii=False))
        if any(not x['id'] for x in OUT['fixtures']['created']):
            raise AssertionError('夹具创建失败')
        OUT['ids'] = OUT['fixtures']['created']

        # 浅色四窗
        open_page(d)
        for key, btn, title in WINDOWS:
            try:
                OUT['windows'][key + '_light'] = window_probe(d, key, btn, title, 'light')
            except Exception as e:
                OUT['windows'][key + '_light'] = {'error': repr(e)}
                log('WIN-ERR', key, repr(e))
                try:
                    shot(d, f'r_{key}_light_error')
                except Exception:
                    pass
                try:
                    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except Exception:
                    pass
                time.sleep(1)

        # 深色四窗
        open_page(d, dark=True)
        for key, btn, title in WINDOWS:
            try:
                OUT['windows'][key + '_dark'] = window_probe(d, key, btn, title, 'dark')
            except Exception as e:
                OUT['windows'][key + '_dark'] = {'error': repr(e)}
                log('WIN-ERR-DARK', key, repr(e))
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        # 提交/回读（浅色）
        open_page(d)
        OUT['submit'] = submit_cases(d, {x['name']: x['id'] for x in OUT['fixtures']['created']})
    finally:
        try:
            OUT['cleanup'] = cleanup(d)
            log('cleanup', json.dumps(OUT['cleanup'], ensure_ascii=False))
        except Exception as e:
            OUT['cleanup'] = {'error': repr(e)}
        json.dump(OUT, open(os.path.join(ART, 'rounds_evidence.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    log('DONE')


if __name__ == '__main__':
    main()

