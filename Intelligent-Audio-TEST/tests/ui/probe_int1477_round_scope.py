# -*- coding: utf-8 -*-
"""INT-1477：批量弹窗「轮次范围」真实轮次复验（INT-1642 只修了评估维度窗，其余四个仍走 batch-shared 默认 4）。

做法：自建 2 条 2 轮夹具用例 → 勾选 → 依次打开 专属参数 / 播放设备 / 声压 / 噪声 四个批量窗 →
点「指定轮次」→ 记录轮次号标签集合。真实轮次=2 时出现「第3轮/第4轮」即 mock 残留。
结束删除夹具。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
API = 'http://127.0.0.1:15000/api/v1'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477_fix')
os.makedirs(ART, exist_ok=True)

TS = time.strftime('%m%d%H%M%S')
PREFIX = '接线测试_INT1477_RND_'
GROUP_NAME = PREFIX + TS
STATE = {'group_id': None, 'case_ids': []}


def log(*a):
    print(*a, flush=True)


def api(method, path, body=None, timeout=90):
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN'):
        o.add_argument(a)
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
        c = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    c.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in c if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(90)
    return d


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def find(d, t, tag='*', exact=True):
    cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
    for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
        if e.is_displayed():
            return e
    return None


def click_text(d, t, tag='*', exact=True, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        e = find(d, t, tag, exact)
        if e:
            jsclick(d, e)
            return e
        time.sleep(0.4)
    raise AssertionError('未找到可点击: ' + t)


def wait_ready(d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            b = ''
        if '用例管理' in b and '导出' in b:
            time.sleep(2)
            return
        time.sleep(1)
    raise AssertionError('用例页未就绪')


def close_top_dialog(d):
    try:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.8)


def make_fixtures():
    s, d = api('GET', '/testcases?per_page=1&keyword=' + urllib.parse.quote('HJ050'))
    items = (d.get('data') or {}).get('items') or []
    base_id = items[0]['id']
    s, det = api('GET', '/testcases/' + base_id)
    base = det['data']
    rounds = ((base.get('config') or {}).get('rounds') or [])[:2]
    for i, r in enumerate(rounds):
        r['round_number'] = i + 1
    s, g = api('POST', '/groups', {'name': GROUP_NAME})
    gid = (g.get('data') or {}).get('id') or g.get('id')
    STATE['group_id'] = gid
    log(f'[fixture] group {gid} {GROUP_NAME}')
    made = []
    for tag in ('A', 'B'):
        payload = {
            'name': PREFIX + TS + '_' + tag,
            'description': '批量轮次范围复验夹具',
            'group_id': gid,
            'algorithm_type': base.get('algorithm_type'),
            'tags': [],
            'config': {'rounds': rounds, 'dimensions': [], 'background_noise': None, 'auto_generated': False},
            'algorithm_params': base.get('algorithm_params') or {},
            'reference_params': base.get('reference_params') or {},
        }
        s, r = api('POST', '/testcases', payload)
        cid = str((r.get('data') or {}).get('id') or '')
        log(f'[fixture] case {cid} -> {s}')
        made.append(cid)
    STATE['case_ids'] = made
    return made


def cleanup():
    ids = STATE.get('case_ids') or []
    for cid in ids:
        api('DELETE', '/testcases/' + cid)
    if ids:
        s, r = api('POST', '/testcases/purge', {'ids': ids})
        log('[cleanup] purge', s, json.dumps(r, ensure_ascii=False)[:120])
    if STATE.get('group_id'):
        s, _ = api('DELETE', '/groups/' + str(STATE['group_id']))
        log('[cleanup] del group', s)
    s, d = api('GET', '/testcases?per_page=100&keyword=' + urllib.parse.quote(PREFIX))
    left = len(((d.get('data') or {}).get('items') or []))
    s, d2 = api('GET', '/testcases?per_page=100&only_deleted=1&keyword=' + urllib.parse.quote(PREFIX))
    left2 = len(((d2.get('data') or {}).get('items') or []))
    s, d3 = api('GET', '/groups?per_page=200')
    gleft = len([g for g in ((d3.get('data') or {}).get('items') or []) if g['name'].startswith(PREFIX)])
    log(f'[cleanup] 残留 cases={left} deleted={left2} groups={gleft}')
    return {'cases': left, 'deleted': left2, 'groups': gleft}


def load_more_until_group(d):
    # 先等分组列表首屏渲染（真实库 8~20s）
    end = time.time() + 90
    while time.time() < end:
        try:
            b = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            b = ''
        if '个分组' in b or '加载更多' in b:
            break
        time.sleep(2)
    end = time.time() + 150
    while time.time() < end:
        if [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{GROUP_NAME}']")
                if e.is_displayed()]:
            return True
        btns = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if not btns:
            return False
        jsclick(d, btns[0])
        time.sleep(4)
    return False


def select_group_all(d):
    g = [e for e in d.find_elements(
        By.XPATH, f"//*[@role='checkbox' and @aria-label='全选分组 {GROUP_NAME}']") if e.is_displayed()]
    assert g, '找不到组级全选复选框'
    jsclick(d, g[0])
    time.sleep(2.5)
    body = d.find_element(By.TAG_NAME, 'body').text
    assert '已选择' in body, '未出现批量浮条'


def round_labels(dlg_text):
    import re
    return sorted(set(re.findall(r'第\s*([0-9]+)\s*轮', dlg_text)), key=int)


def main():
    make_fixtures()
    d = driver()
    results = []
    try:
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_ready(d)
        assert load_more_until_group(d), '分组卡未出现'
        select_group_all(d)
        for label in ('批量设置专属参数', '批量设置播放设备', '批量设置声压', '批量设置噪声', '批量设置评估维度'):
            try:
                click_text(d, label, 'button')
                time.sleep(2.5)
            except AssertionError as e:
                results.append({'window': label, 'error': str(e)})
                continue
            spec = [e for e in d.find_elements(By.XPATH, "//label[contains(normalize-space(.),'指定轮次')]")
                    if e.is_displayed()]
            if spec:
                jsclick(d, spec[0])
                time.sleep(1.5)
            dlg = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']") if e.is_displayed()]
            txt = dlg[-1].text if dlg else ''
            labels = round_labels(txt)
            log(f'  {label}: 轮次标签={labels}')
            shot = os.path.join(ART, 'rnd_' + str(len(results)) + '.png')
            d.save_screenshot(shot)
            results.append({'window': label, 'rounds': labels, 'shot': os.path.basename(shot),
                            'head': txt[:200]})
            close_top_dialog(d)
            time.sleep(0.8)
    finally:
        try:
            d.quit()
        except Exception:
            pass
        clean = cleanup()
    out = {'ts': TS, 'results': results, 'cleanup': clean}
    p = os.path.join(ART, 'evidence_round_scope.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    import urllib.error  # noqa: F401
    main()
