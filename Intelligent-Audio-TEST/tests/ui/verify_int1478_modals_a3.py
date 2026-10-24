# -*- coding: utf-8 -*-
"""INT-1478 A 段收尾：发布提交（551）+ 彻底删除确认取消（551 再次软删后取消 purge）。"""
import json
import os
import sys
import time
import traceback
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

BASE = 'http://127.0.0.1:15173'
BACK = 'http://127.0.0.1:15000'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1478_modals_a')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
TS = time.strftime('%H%M%S')
PRIME = '接线测试_INT1478_PRIME'
PUB_NAME = '接线测试_INT1478_发布_%s' % TS
report = []
utils = {}


def api(path, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BACK + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode('utf-8'))


def sq(s):
    return urllib.parse.quote(s)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_a3_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(120)
    d.set_script_timeout(90)
    return d


def js(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    d.execute_script('arguments[0].click();', el)


def visible(d, css):
    return [e for e in d.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()]


def find_by_text(d, texts, tags=('button', '*[role=menuitem]', '*[role=option]', '*[role=tab]', 'a', 'label')):
    for tag in tags:
        for el in d.find_elements(By.CSS_SELECTOR, tag):
            try:
                if el.is_displayed() and el.text.strip() in texts:
                    return el
            except Exception:
                continue
    return None


def wait_text(d, text, timeout=20, tags=('button', '*[role=menuitem]', '*[role=option]', '*[role=tab]', 'a', 'label')):
    end = time.time() + timeout
    while time.time() < end:
        el = find_by_text(d, {text}, tags)
        if el is not None:
            return el
        time.sleep(0.35)
    return None


def wait_sel(d, css, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        els = visible(d, css)
        if els:
            return els[0]
        time.sleep(0.35)
    return None


def perf_mark(d):
    return len(d.get_log('performance'))


def perf_since(d, mark):
    reqs, resps = {}, []
    for m in d.get_log('performance')[mark:]:
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        meth = msg.get('method')
        if meth == 'Network.requestWillBeSent':
            r = msg['params']['request']
            if '/api/' in r['url']:
                reqs[r.get('requestId')] = {'method': r['method'],
                                            'url': r['url'].replace(BASE, ''),
                                            'post': (r.get('postData') or '')[:600]}
        elif meth == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/' in r['url']:
                info = dict(reqs.get(msg['params'].get('requestId'), {}))
                info.update({'status': r['status'], 'url': r['url'].replace(BASE, '')})
                resps.append(info)
    return [x for x in resps if x.get('method')]


def writes(d, mark):
    return [a for a in perf_since(d, mark) if a.get('method') in ('POST', 'PUT', 'DELETE', 'PATCH')]


def dialog_text(d):
    els = visible(d, '[role=dialog], [role=alertdialog]')
    return els[0].text.strip() if els else ''


def set_dark(d, on):
    d.execute_script("document.documentElement.classList.remove('%s');document.documentElement.classList.add('%s');"
                     % ('light' if on else 'dark', 'dark' if on else 'light'))


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    return p


def capture(d, key):
    time.sleep(0.7)
    out = {'light': shot(d, key + '_light'), 'text': dialog_text(d)}
    set_dark(d, True)
    time.sleep(0.5)
    out['dark'] = shot(d, key + '_dark')
    set_dark(d, False)
    time.sleep(0.25)
    return out


def close_dialog(d):
    els = visible(d, '[role=dialog] [data-slot=dialog-close], [role=alertdialog] [data-slot=dialog-close]')
    if els:
        js(d, els[0])
    else:
        ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)


def type_input(d, el, value):
    js(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)
    time.sleep(0.3)


def search_task(d, name):
    box = wait_sel(d, 'input[placeholder*="搜索任务名称"]')
    assert box is not None, '未找到任务搜索框'
    type_input(d, box, name)
    q = wait_text(d, '查询', 6, tags=('button',))
    if q is not None:
        js(d, q)
    time.sleep(2.5)


def row_menu(d, task_name, item):
    search_task(d, task_name)
    trig = wait_sel(d, 'button[aria-label="任务操作"]', 25)
    assert trig is not None, '未找到行操作按钮（%s）' % task_name
    js(d, trig)
    time.sleep(0.6)
    it = wait_text(d, item, 10, tags=('*[role=menuitem]',))
    assert it is not None, '菜单项「%s」未出现' % item
    js(d, it)
    time.sleep(0.9)


def step(key, title, fn, d):
    mark = perf_mark(d)
    entry = {'key': key, 'title': title, 'ok': False, 'error': None, 'evidence': {}, 'api': []}
    t0 = time.time()
    try:
        if visible(d, '[role=dialog], [role=alertdialog]'):
            close_dialog(d)
        fn(d, entry['evidence'])
        entry['ok'] = True
    except Exception as exc:  # noqa: BLE001
        entry['error'] = '%s: %s' % (type(exc).__name__, exc)
        traceback.print_exc()
        try:
            close_dialog(d)
        except Exception:
            pass
    entry['api'] = perf_since(d, mark)
    entry['seconds'] = round(time.time() - t0, 1)
    report.append(entry)
    print(('[OK]  ' if entry['ok'] else '[FAIL]') + ' ' + key + ' ' +
          (entry['error'] or '') + ' (%ss)' % entry['seconds'])
    flush()
    return entry


def flush():
    with open(os.path.join(ART, 'report_a3.json'), 'w', encoding='utf-8') as f:
        json.dump({'env': {'base': BASE, 'back': BACK, 'ts': TS, 'utils': utils}, 'steps': report},
                  f, ensure_ascii=False, indent=2)


def s_publish(d, e):
    d.get(BASE + '/tasks/daily')
    time.sleep(8)
    row_menu(d, PRIME, '发布')
    assert wait_sel(d, '[role=dialog]') is not None, '发布弹窗未出现'
    trig = wait_sel(d, '[role=dialog] [aria-label="选择来源任务"]')
    assert trig is not None, '未找到来源任务选择器'
    end = time.time() + 60
    opts = []
    while time.time() < end:
        js(d, trig)
        time.sleep(1.2)
        opts = [o.text.strip() for o in visible(d, '*[role=option]')]
        if opts and '加载中…' not in ' '.join(opts):
            break
        ActionChains(d).send_keys(Keys.ESCAPE).perform()
        time.sleep(1.5)
    e['option_count'] = len(opts)
    e['option_sample'] = opts[:5]
    tasks = api('/api/v1/tasks?page=1&per_page=100')['data']['items']
    e['api_publishable_first100'] = len(
        [t for t in tasks if t.get('execution_status') in ('completed', 'failed', 'stopped', 'pending')])
    ev = capture(d, '05_publish_task')
    e['dialog_open_text'] = ev.pop('text')
    ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)
    name_input = wait_sel(d, '[role=dialog] input[placeholder*="发布后展示"]')
    assert name_input is not None, '未找到名称输入'
    type_input(d, name_input, PUB_NAME)
    shot(d, '05b_publish_filled_light')
    mark = perf_mark(d)
    submit = None
    for b in visible(d, '[role=dialog] button'):
        if b.text.strip() == '发布':
            submit = b
    assert submit is not None, '未找到发布钮'
    js(d, submit)
    time.sleep(5)
    e['submit_writes'] = writes(d, mark)
    e['toast'] = ' '.join(t.text for t in visible(d, '[data-sonner-toast]'))
    pub = api('/api/v1/published-tasks?page=1&per_page=50&keyword=' + sq('INT1478_发布'))
    hits = [p for p in pub['data']['items'] if PUB_NAME in p['name']]
    e['readback'] = [{'id': p['id'], 'name': p['name'], 'version': p.get('version')} for p in hits]
    assert hits, '发布后 /published-tasks 未回读到'
    utils['published_id'] = hits[0]['id']
    det = api('/api/v1/published-tasks/%d' % hits[0]['id'])['data']
    e['roundtrip'] = {'name': det.get('name'), 'status': det.get('status'),
                      'source_task_id': det.get('source_task_id'),
                      'snapshot_keys': list((det.get('snapshot_config') or {}).keys())[:8]}


def s_purge_cancel(d, e):
    # 551 当前在册 → 软删 → 回收站 → 彻底删除确认 → 取消（不实际删除）
    d.get(BASE + '/tasks/daily')
    time.sleep(7)
    row_menu(d, PRIME, '删除')
    time.sleep(1.0)
    for b in visible(d, '[role=alertdialog] button, [role=dialog] button'):
        if b.text.strip() == '删除':
            js(d, b)
            break
    time.sleep(4)
    e['after_delete'] = api('/api/v1/tasks?page=1&per_page=20&search=%s&deleted=true' % sq('接线测试_INT1478'))['data']['total']
    js(d, wait_text(d, '回收站', 10, tags=('button',)))
    time.sleep(4)
    row_menu(d, PRIME, '彻底删除')
    time.sleep(1.2)
    ev = capture(d, '07d_purge_confirm')
    e['purge_dialog'] = ev.pop('text')
    mark = perf_mark(d)
    js(d, find_by_text(d, {'取消'}, tags=('button',)))
    time.sleep(1.5)
    e['cancel_writes'] = writes(d, mark)
    e['still_in_trash'] = api('/api/v1/tasks?page=1&per_page=20&search=%s&deleted=true' % sq('接线测试_INT1478'))['data']['total']
    assert not e['cancel_writes'], '取消彻底删除产生了写请求'


def main():
    d = driver()
    try:
        step('publish', '发布任务（提交 + 回读 + 来源选项）', s_publish, d)
        step('purge_cancel', '彻底删除二次确认（取消路径）', s_purge_cancel, d)
    finally:
        flush()
        try:
            d.quit()
        except Exception:
            pass
        ok = sum(1 for r in report if r['ok'])
        print('\n== %d/%d 步骤通过 ==' % (ok, len(report)))


if __name__ == '__main__':
    main()
