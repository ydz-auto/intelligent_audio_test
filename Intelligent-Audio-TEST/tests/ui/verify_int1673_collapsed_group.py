# -*- coding: utf-8 -*-
"""INT-1673 P3-3 边界复核：分组**未展开**时从组头「批量修改」开批量弹窗的轮次数。

交付自述边界：折叠组的用例尚未加载 → 宿主无轮次数据源 → 弹窗按 1 轮渲染。
本脚本用「只有 3 轮用例」的临时分组验证该边界的实际表现（期望：渲染第1轮，不出现第2/3/4轮）。
写数据纪律：只建本 run 的「接线测试_INT1673B_」分组与用例，结束前删掉。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15268')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1673_collapsed')
TS = int(time.time())
GROUP = '接线测试_INT1673B_%d' % TS
REPORT = {'cases': [], 'screenshots': [], 'fail': []}


def log(m):
    print(m, flush=True)


def check(name, ok, detail=''):
    REPORT['cases'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        REPORT['fail'].append({'name': name, 'detail': detail})
        log('FAIL %s | %s' % (name, detail))
    else:
        log('OK   %s | %s' % (name, detail))


def api(method, path, payload=None, params=None):
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {'raw': e.read().decode(errors='replace')[:300]}


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox', '--lang=zh-CN'):
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for v in os.listdir(root):
            exe = os.path.join(root, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(v.split('.')[0]) == major:
                        path = exe
                except Exception:
                    pass
    drv = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    drv.set_page_load_timeout(120)
    return drv


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def xp(drv, xpath, root=None):
    return (root or drv).find_elements(By.XPATH, xpath)


def dialogs(drv):
    return [d for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if d.is_displayed()]


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=15).read().decode())
    assert health.get('database') == 'intelligent_audio_test', health
    st, g = api('POST', '/api/v1/groups', {'name': GROUP, 'description': 'INT-1673 折叠组边界复核'})
    gid = (g.get('data') or {}).get('id')
    st, c = api('POST', '/api/v1/testcases', {
        'name': '接线测试_INT1673B_3轮_%d' % TS,
        'group_id': gid,
        'tags': ['接线测试_INT1673B'],
        'description': 'INT-1673 折叠组边界临时用例',
        'algorithm_type': 'voice_llm',
        'config': {'rounds': [
            {'round_number': i + 1, 'audios': [], 'evaluation': {}, 'noise': {}} for i in range(3)
        ]},
        'algorithm_params': [],
    })
    cid = (c.get('data') or {}).get('id')
    check('自建夹具：3 轮用例 1 条（分组默认折叠）', bool(gid) and bool(cid), (gid, cid))
    drv = driver()
    try:
        drv.get(BASE + '/')
        time.sleep(1.0)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        drv.get(BASE + '/testcases')
        WebDriverWait(drv, 240, 0.4).until(
            lambda d: len(xp(d, "//*[contains(@aria-label,'批量修改')]")) > 0)
        # 分组列表按用例数降序分页：点「加载更多」直到自建分组出现
        for _ in range(12):
            if xp(drv, "//button[@aria-label='%s 批量修改']" % GROUP):
                break
            more = [b for b in xp(drv, "//button[contains(., '加载更多')]") if b.is_displayed()]
            if not more:
                break
            js_click(drv, more[0])
            time.sleep(3.5)
        time.sleep(1.0)
        # 不展开分组，直接组头「批量修改」→ 批量设置声压级
        js_click(drv, xp(drv, "//button[@aria-label='%s 批量修改']" % GROUP)[0])
        time.sleep(0.8)
        for b in xp(drv, "//*[contains(normalize-space(.), '声压')]"):
            if b.is_displayed() and b.tag_name in ('button', 'div') and '声压' == (b.text or '').strip():
                js_click(drv, b)
                break
        WebDriverWait(drv, 40, 0.4).until(lambda d: any('批量设置声压级' in (x.text or '') for x in dialogs(d)))
        time.sleep(0.8)
        dlg = [x for x in dialogs(drv) if '批量设置声压级' in (x.text or '')][-1]
        labels = [l for l in xp(drv, ".//label[contains(., '指定轮次')]", dlg) if l.is_displayed()]
        js_click(drv, labels[0])
        time.sleep(0.6)
        rounds = drv.execute_script(
            "return Array.from(arguments[0].querySelectorAll('label'))"
            ".map(function(l){return (l.textContent||'').trim();})"
            ".filter(function(t){return /^第\\d+轮$/.test(t);});", dlg)
        path = os.path.join(ART, 'collapsed_group_rounds.png')
        drv.save_screenshot(path)
        REPORT['rounds'] = rounds
        REPORT['screenshot'] = {'name': 'collapsed_group_rounds.png', 'size': os.path.getsize(path)}
        log('ROUNDS(折叠组) = %s' % rounds)
        check('折叠组 + 组头批量修改：弹窗轮次可用（不出现第 4 轮）', '第4轮' not in rounds, rounds)
        check('折叠组 + 组头批量修改：按 1 轮渲染（交付自述的已知边界）', rounds == ['第1轮'], rounds)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        if cid:
            api('DELETE', '/api/v1/testcases/%s' % cid)
            api('DELETE', '/api/v1/testcases/%s/purge' % cid)
        if gid:
            log('cleanup group → %s' % api('DELETE', '/api/v1/groups/%s' % gid, params={'cascade': True})[0])
    with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    log('FAILS: %d' % len(REPORT['fail']))
    return 1 if REPORT['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
