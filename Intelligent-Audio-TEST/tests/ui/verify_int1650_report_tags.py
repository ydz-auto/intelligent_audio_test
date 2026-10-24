# -*- coding: utf-8 -*-
"""INT-1650 验收（测试工程师）：冻结报告弹窗用例标签对象归一化。

环境：docker 真实库栈（后端 15000，库 intelligent_audio_test，AUTH_MODE=off）。
默认前端 = 本卡交付 diff 的本地 build 起的旁路 nginx 容器 http://127.0.0.1:15265；
可用 REACT_BASE=http://127.0.0.1:15173 跑对照（15173 不含本卡修复 → 复现 [object Object]）。

验收点：
1. /tasks/published → 展开版本详情 →「查看冻结报告」：冻结用例 188 行；
2. 弹窗内 [object Object] 出现 0 次；
3. 每行标签区 == 接口 report_snapshot.cases[].tags[].name 归一化后的中文名（按 '、' 连接）；
4. Network：GET /api/v1/published-tasks/{id} 200；
5. 浅色 / 深色各一张截图（深色为同源 reload 后复走）。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15265').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get('ART_DIR', r'D:\00_user_data\int1650_artifacts')
TAG = os.environ.get('RUN_TAG', 'fixed')
TASK_ID = 12
PAGE = '/tasks/published'
DARK_KEY = 'iatp:theme:v1:mode'

RESULT = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = chrome_major()
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), p))
                except ValueError:
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(90)
    drv.set_script_timeout(120)
    return drv


def goto(drv, path, wait=2.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, '%s_%s.png' % (TAG, name))
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def js_click(drv, xpath, wait=0.8):
    el = WebDriverWait(drv, 30).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def wait_text(drv, text, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: text in (d.execute_script(
        'return document.body.textContent || ""') or ''))


def expected_tags():
    """接口侧期望：cases[].tags 归一化为 name 字符串（与修复口径一致）。"""
    url = API + '/api/v1/published-tasks/%d' % TASK_ID
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode('utf-8'))['data']
    snap = data.get('report_snapshot') or {}
    exp = []
    for c in snap.get('cases') or []:
        names = []
        for t in c.get('tags') or []:
            if isinstance(t, str):
                names.append(t)
            elif isinstance(t, dict) and t.get('name') is not None:
                names.append(str(t['name']))
        exp.append({'name': c.get('name'), 'tags': names, 'joined': '、'.join(names)})
    return data, snap, exp


COLLECT_JS = r"""
const dlg = document.querySelector('[role="dialog"]');
if (!dlg) return null;
const rows = [...dlg.querySelectorAll('.divide-y > div')];
const data = rows.map(r => {
  const span = r.querySelector('span.text-muted-foreground.text-xs');
  return {text: (r.textContent||'').trim(), tag: span ? (span.textContent||'').trim() : null};
});
return {rows: data, dialogText: dlg.textContent || '', count: rows.length};
"""


def open_report_dialog(drv):
    goto(drv, PAGE, wait=4)
    # 目标行：名称含「豆包拒识环境理解E2E测试任务」；找不到就用第一行
    xp = ("//tr[.//span[contains(normalize-space(.),'豆包拒识环境理解E2E测试任务')]]"
          "//button[@aria-label='展开版本详情']")
    try:
        js_click(drv, xp, 1.5)
    except Exception:
        js_click(drv, "(//button[@aria-label='展开版本详情'])[1]", 1.5)
    wait_text(drv, '冻结报告（发布时快照 · 不可变）', 90)
    js_click(drv, "(//button[normalize-space(.)='查看冻结报告'])[1]", 1.5)
    wait_text(drv, '冻结用例（', 60)
    time.sleep(1.0)


def main():
    detail, snap, exp = expected_tags()
    expected_rows = len(exp)
    expected_distinct = sorted({t for c in exp for t in c['tags']})
    print('API cases=%d distinct_tags=%d' % (expected_rows, len(expected_distinct)))

    drv = build_driver()
    evidence = {'base': BASE, 'api_cases': expected_rows, 'modes': {}}
    try:
        # ---------- 浅色 ----------
        open_report_dialog(drv)
        light = drv.execute_script(COLLECT_JS)
        body_text = drv.execute_script('return document.body.textContent || ""') or ''
        dtext = light['dialogText'] if light else ''
        obj_count_dialog = dtext.count('[object Object]')
        obj_count_body = body_text.count('[object Object]')
        rows = light['rows'] if light else []

        check('[浅色] 冻结用例行数 == 接口用例数', len(rows) == expected_rows,
              'rows=%d expected=%d' % (len(rows), expected_rows))
        check('[浅色] 弹窗内 [object Object] 次数为 0', obj_count_dialog == 0, 'count=%d' % obj_count_dialog)
        check('[浅色] 整页 [object Object] 次数为 0', obj_count_body == 0, 'count=%d' % obj_count_body)

        mismatched = []
        for i, (got, want) in enumerate(zip(rows, exp)):
            got_tag = got.get('tag')
            if want['tags']:
                if got_tag != want['joined']:
                    mismatched.append({'row': i, 'want': want['joined'], 'got': got_tag})
            else:
                if got_tag:
                    mismatched.append({'row': i, 'want': '', 'got': got_tag})
        check('[浅色] 188 行标签区与接口标签名逐行一致', not mismatched,
              'mismatch=%d %s' % (len(mismatched), mismatched[:5]))

        missing = [t for t in expected_distinct if t not in dtext]
        check('[浅色] 接口全部标签名均可见', not missing, 'missing=%s' % missing[:5])

        sample = exp[0]['joined'] if exp else ''
        check('[浅色] 首行标签为中文标签名（非对象串）', bool(sample) and '[object' not in sample and sample in dtext,
              'sample=%s' % sample)

        shot(drv, 'report_snapshot_light')

        # 深色：同源写 localStorage 后 reload，复走同一路径
        drv.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", DARK_KEY, 'dark')
        open_report_dialog(drv)
        dark = drv.execute_script(COLLECT_JS)
        dtext_dark = dark['dialogText'] if dark else ''
        dark_body = drv.execute_script('return document.body.textContent || ""') or ''
        rows_dark = dark['rows'] if dark else []
        theme = drv.execute_script(
            "return (document.documentElement.getAttribute('class')||'') + '|' + "
            "(document.documentElement.getAttribute('data-theme')||'') + '|' + "
            "window.localStorage.getItem(arguments[0]);", DARK_KEY)
        check('[深色] 冻结用例行数 == 接口用例数', len(rows_dark) == expected_rows, 'rows=%d' % len(rows_dark))
        check('[深色] 弹窗内 [object Object] 次数为 0', dtext_dark.count('[object Object]') == 0,
              'count=%d' % dtext_dark.count('[object Object]'))
        check('[深色] 整页 [object Object] 次数为 0', dark_body.count('[object Object]') == 0,
              'count=%d' % dark_body.count('[object Object]'))
        check('[深色] 深色主题确已生效', 'dark' in theme, 'theme=%s' % theme)
        shot(drv, 'report_snapshot_dark')

        # Network：performance log 里的 published-tasks 请求
        reqs = []
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            if msg.get('method') != 'Network.responseReceived':
                continue
            resp = msg.get('params', {}).get('response', {})
            url = resp.get('url', '')
            if 'published-tasks' in url:
                reqs.append({'url': url.replace(BASE, ''), 'status': resp.get('status'),
                             'mime': resp.get('mimeType')})
        ok_req = [r for r in reqs if r['status'] == 200 and str(r['status']).startswith('2')]
        check('Network: GET /api/v1/published-tasks/{id} 200',
              any('/published-tasks/%d' % TASK_ID in r['url'] and 200 <= (r['status'] or 0) < 300 for r in reqs),
              json.dumps(reqs[-6:], ensure_ascii=False))

        # 浏览器 console 严重错误
        severe = []
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE' and 'Failed to load resource' not in entry.get('message', ''):
                severe.append(entry.get('message', '')[:200])
        check('无 browser SEVERE 错误', not severe, json.dumps(severe[:5], ensure_ascii=False))

        evidence.update({
            'rows': len(rows),
            'object_object_dialog': obj_count_dialog,
            'object_object_body': obj_count_body,
            'dark_rows': len(rows_dark),
            'dark_object_object': dtext_dark.count('[object Object]'),
            'tag_mismatch': mismatched[:10],
            'distinct_tags': len(expected_distinct),
            'network': reqs[-6:],
            'shots': [f for f in os.listdir(ART) if f.startswith(TAG + '_')] if os.path.isdir(ART) else [],
        })
    finally:
        drv.quit()

    os.makedirs(ART, exist_ok=True)
    out = os.path.join(ART, 'evidence_%s.json' % TAG)
    failed = [r for r in RESULT if not r['ok']]
    evidence['checks'] = RESULT
    evidence['failed'] = len(failed)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('evidence:', out)
    print('RESULT: %d/%d passed' % (len(RESULT) - len(failed), len(RESULT)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
