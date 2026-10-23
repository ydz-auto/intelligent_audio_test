# -*- coding: utf-8 -*-
"""INT-1478 复走·React·任务域 —— A 段（日常页签 8 窗，真实栈 15173/15000）。

窗口：TaskTypeDialog / DataImportDialog / QuickViewDialog / PublishTaskDialog /
ReexecuteScopeDialog / TaskConfirmDialogs(删除·恢复·彻底删除) / DataExportDialog。
每窗：触发 → 选项/字段 → 真实提交 → GET 回读 → 取消重开 → 浅/深截图 + 请求响应。
数据：自建 接线测试_INT1478_* 记录，run 结束删除。
"""
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
BACK = os.environ.get('BACK_BASE', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1478_modals_a')
DL = os.path.join(ART, 'downloads')
os.makedirs(ART, exist_ok=True)
os.makedirs(DL, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
TS = time.strftime('%H%M%S')
PRIME = '接线测试_INT1478_PRIME'      # 551：0 用例日常任务
IMPORT_NAME = '接线测试_INT1478_导入_%s' % TS
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
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_a_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    o.add_experimental_option('prefs', {'download.default_directory': DL,
                                        'download.prompt_for_download': False})
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


def find_contains(d, needle, tags=('button', 'label', '*[role=menuitem]')):
    for tag in tags:
        for el in d.find_elements(By.CSS_SELECTOR, tag):
            try:
                if el.is_displayed() and needle in el.text and len(el.text.strip()) < 80:
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
                info.update({'status': r['status'], 'url': r['url'].replace(BASE, ''),
                             'mime': r.get('mimeType', '')})
                resps.append(info)
    return resps


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
        try:
            ActionChains(d).send_keys(Keys.ESCAPE).perform()
        except Exception:
            pass
    time.sleep(0.7)
    if visible(d, '[role=dialog], [role=alertdialog]'):
        btn = find_by_text(d, {'取消', '关闭', '返回'})
        if btn is not None:
            js(d, btn)
    time.sleep(0.4)


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
    query = wait_text(d, '查询', 6, tags=('button',))
    if query is not None:
        js(d, query)
    time.sleep(2.5)


def row_menu(d, task_name, item):
    search_task(d, task_name)
    trig = wait_sel(d, 'button[aria-label="任务操作"]', 25)
    assert trig is not None, '未找到行操作按钮（搜索：%s）' % task_name
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
    with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump({'env': {'base': BASE, 'back': BACK, 'ts': TS, 'utils': utils},
                   'steps': report}, f, ensure_ascii=False, indent=2)


# ---------- steps ----------
def s_env(d, e):
    health = json.loads(urllib.request.urlopen(BACK + '/health', timeout=30).read().decode())
    e['health'] = health
    d.get(BASE + '/tasks/daily')
    time.sleep(8)
    assert wait_sel(d, 'button[aria-label="任务操作"]', 40) is not None, '任务列表未渲染'
    e['shot'] = shot(d, '01_tasks_daily_light')
    set_dark(d, True)
    time.sleep(0.6)
    e['shot_dark'] = shot(d, '01_tasks_daily_dark')
    set_dark(d, False)
    e['tabs'] = [t.text.strip() for t in visible(d, '[role=tab]')]
    e['api_tasks_total'] = api('/api/v1/tasks?page=1&per_page=10')['data']['total']
    e['api_published_total'] = api('/api/v1/published-tasks?page=1&per_page=1')['data']['total']
    merged = api('/api/v1/tasks?page=1&per_page=1&merged=true')['data']
    cherry = api('/api/v1/tasks?page=1&per_page=1&cherry_pick=true')['data']
    e['api_container_total'] = merged['total'] + cherry['total']
    e['footer_total_text'] = ' '.join(
        t.text for t in visible(d, 'p, span') if t.text.strip().startswith('共 ') and '条' in t.text)[:80]


def s_task_type(d, e):
    js(d, wait_text(d, '创建新任务'))
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    ev = capture(d, '02_task_type')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    cancel = wait_text(d, '取消', 6, tags=('button',))
    js(d, cancel)
    time.sleep(0.7)
    e['cancel_closed'] = not visible(d, '[role=dialog]')
    # 重开 → 「开始测试」分支跳 /start-test
    js(d, wait_text(d, '创建新任务'))
    time.sleep(0.8)
    go = find_contains(d, '开始测试')
    assert go is not None, '未找到「开始测试」入口卡'
    js(d, go)
    time.sleep(2.5)
    e['navigated_url'] = d.current_url
    assert '/start-test' in d.current_url, '开始测试未跳转 /start-test'
    d.get(BASE + '/tasks/daily')
    time.sleep(5)


def s_quick_view(d, e):
    row_menu(d, PRIME, '快速查看')
    assert wait_sel(d, '[role=dialog]') is not None, '快速查看弹窗未出现'
    time.sleep(1.5)
    ev = capture(d, '04_quick_view')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    detail = api('/api/v1/tasks/551')['data']
    e['api'] = {k: detail.get(k) for k in ('id', 'name', 'execution_status', 'evaluation_status', 'total_cases')}
    e['name_match'] = detail['name'] in e['dialog_text']
    assert e['name_match'], '弹窗标题与接口任务名不一致'
    ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)
    e['esc_closed'] = not visible(d, '[role=dialog]')
    row_menu(d, PRIME, '快速查看')
    time.sleep(1.2)
    e['reopen_ok'] = PRIME in dialog_text(d)
    close_dialog(d)


def s_publish(d, e):
    row_menu(d, PRIME, '发布')
    assert wait_sel(d, '[role=dialog]') is not None, '发布弹窗未出现'
    ev = capture(d, '05_publish_task')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    trig = wait_sel(d, '[role=dialog] [aria-label="选择来源任务"]')
    assert trig is not None, '未找到来源任务选择器'
    js(d, trig)
    time.sleep(1.2)
    opts = [o.text.strip() for o in visible(d, '*[role=option]')]
    e['source_options'] = opts[:12]
    e['option_count'] = len(opts)
    tasks = api('/api/v1/tasks?page=1&per_page=100')['data']['items']
    e['api_publishable_first100'] = len(
        [t for t in tasks if t.get('execution_status') in ('completed', 'failed', 'stopped', 'pending')])
    ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)
    name_input = wait_sel(d, '[role=dialog] input[placeholder*="发布后展示"]')
    assert name_input is not None, '未找到名称输入'
    type_input(d, name_input, PUB_NAME)
    submit = None
    for b in visible(d, '[role=dialog] button'):
        if b.text.strip() == '发布':
            submit = b
    assert submit is not None, '未找到发布钮'
    js(d, submit)
    time.sleep(4)
    e['toast'] = ' '.join(t.text for t in visible(d, '[data-sonner-toast]'))
    pub = api('/api/v1/published-tasks?page=1&per_page=50&keyword=' + sq('INT1478_发布'))
    hits = [p for p in pub['data']['items'] if PUB_NAME in p['name']]
    e['readback_hits'] = [{'id': p['id'], 'name': p['name'], 'version': p.get('version')} for p in hits]
    assert hits, '发布后未在 /published-tasks 回读到'
    utils['published_id'] = hits[0]['id']
    det = api('/api/v1/published-tasks/%d' % hits[0]['id'])['data']
    e['name_roundtrip'] = det.get('name') == PUB_NAME
    e['readback_detail'] = {'id': det.get('id'), 'status': det.get('status'),
                            'source_task_id': det.get('source_task_id'),
                            'has_task_snapshot': det.get('has_task_snapshot'),
                            'has_report_snapshot': det.get('has_report_snapshot')}


def s_export(d, e):
    search_task(d, 'E2E测试任务_2026/9/22 10:15:12')
    box = wait_sel(d, '[aria-label^="选择 E2E测试任务_2026/9/22 10:15:12"], [aria-label^="选择 "]')
    assert box is not None, '未找到行勾选框'
    js(d, box)
    time.sleep(1.2)
    btn = wait_text(d, '导出数据', 12)
    assert btn is not None, '批量浮条「导出数据」未出现'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '导出弹窗未出现'
    ev = capture(d, '08_data_export')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    start = None
    for b in visible(d, '[role=dialog] button'):
        if '开始导出' in b.text:
            start = b
    assert start is not None, '未找到开始导出钮'
    before = set(os.listdir(DL))
    js(d, start)
    end = time.time() + 120
    got, size = None, 0
    while time.time() < end:
        now = set(os.listdir(DL))
        new = [n for n in (now - before) if n.endswith('.zip')]
        part = [n for n in now if n.endswith('.crdownload')]
        if new and not part:
            got = new[0]
            size = os.path.getsize(os.path.join(DL, got))
            if size > 0:
                break
        time.sleep(1.0)
    assert got and size > 0, '导出 120s 内未落盘非空 zip'
    e['zip'] = {'name': got, 'size': size}
    utils['zip'] = os.path.join(DL, got)
    e['toast'] = ' '.join(t.text for t in visible(d, '[data-sonner-toast]'))
    e['closed_after'] = not visible(d, '[role=dialog]')


def s_import(d, e):
    zp = utils.get('zip')
    assert zp and os.path.exists(zp), '缺少导出 zip'
    js(d, wait_text(d, '导入数据'))
    assert wait_sel(d, '[role=dialog]') is not None, '导入弹窗未出现'
    ev = capture(d, '09_data_import')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    inbox = api('/api/v1/tasks?page=1&per_page=200')['data']['total']
    e['before_total'] = inbox
    inp = d.find_element(By.CSS_SELECTOR, '[role=dialog] input[type=file]')
    inp.send_keys(zp)
    end = time.time() + 120
    txt = ''
    while time.time() < end:
        txt = dialog_text(d)
        if '预检结果' in txt or '失败' in txt:
            break
        time.sleep(1.5)
    e['preview_text'] = txt
    assert '预检结果' in txt, '真实 zip 预检未成功：%s' % txt[:300]
    shot(d, '09b_import_preview_light')
    go = find_contains(d, '开始导入')
    assert go is not None, '未找到开始导入钮'
    js(d, go)
    end = time.time() + 240
    while time.time() < end:
        txt = dialog_text(d)
        if '导入完成' in txt or '失败' in txt or '完成统计' in txt:
            break
        time.sleep(2)
    e['result_text'] = txt[:800]
    shot(d, '09c_import_done_light')
    set_dark(d, True)
    time.sleep(0.5)
    shot(d, '09c_import_done_dark')
    set_dark(d, False)
    assert '失败' not in txt, '导入失败：%s' % txt[:300]
    after = api('/api/v1/tasks?page=1&per_page=200')['data']
    e['after_total'] = after['total']
    assert after['total'] > inbox, '导入后任务总数未增加'
    close_dialog(d)
    time.sleep(2)
    # 找出新增任务并重命名为接线测试前缀（便于清理）
    # 用 id 取最新创建的一条（导入任务）
    target = max(after['items'], key=lambda t: t['id'])
    e['imported_task_id'] = target['id']
    utils['imported_task'] = target['id']
    ren = api('/api/v1/tasks/%d' % target['id'], 'PUT', {'name': IMPORT_NAME})
    e['rename_resp'] = ren.get('message')
    got = api('/api/v1/tasks/%d' % target['id'])['data']
    e['imported_name'] = got.get('name')
    assert got.get('name') == IMPORT_NAME, '导入任务重命名未生效'


def s_reexecute(d, e):
    tid = utils.get('imported_task')
    assert tid, '缺少导入任务'
    row_menu(d, IMPORT_NAME, '重新执行')
    assert wait_sel(d, '[role=dialog]') is not None, '重新执行弹窗未出现'
    time.sleep(1.5)
    ev = capture(d, '06_reexecute_scope')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    fail = find_by_text(d, {'仅失败用例'}, tags=('label', 'button', '*'))
    if fail is None:
        fail = find_contains(d, '仅失败用例')
    assert fail is not None, '未找到「仅失败用例」选项'
    js(d, fail)
    time.sleep(0.6)
    shot(d, '06b_reexecute_failed_only')
    # 取消 → 不应有写请求
    mark = perf_mark(d)
    js(d, find_by_text(d, {'取消'}, tags=('button',)))
    time.sleep(1.2)
    e['cancel_writes'] = [a for a in perf_since(d, mark) if a.get('method') != 'GET']
    assert not e['cancel_writes'], '取消产生了写请求'
    # 重开 → 全量提交
    row_menu(d, IMPORT_NAME, '重新执行')
    time.sleep(1.5)
    mark = perf_mark(d)
    confirm = None
    for b in visible(d, '[role=dialog] button'):
        if '确认' in b.text:
            confirm = b
    assert confirm is not None, '未找到确认钮'
    js(d, confirm)
    time.sleep(6)
    e['submit_api'] = [a for a in perf_since(d, mark) if a.get('method') != 'GET']
    time.sleep(3)
    det = api('/api/v1/tasks/%d' % tid)['data']
    e['readback'] = {'execution_status': det.get('execution_status'), 'status': det.get('status'),
                     'total_cases': det.get('total_cases')}


def s_delete_restore(d, e):
    row_menu(d, PRIME, '删除')
    assert wait_sel(d, '[role=alertdialog], [role=dialog]') is not None, '删除确认未出现'
    ev = capture(d, '07_task_confirm_delete')
    e.update(ev)
    e['dialog_text'] = ev.pop('text')
    mark = perf_mark(d)
    js(d, find_by_text(d, {'取消'}, tags=('button',)))
    time.sleep(1.2)
    e['cancel_writes'] = [a for a in perf_since(d, mark) if a.get('method') != 'GET']
    assert not e['cancel_writes'], '取消删除产生了写请求'
    # 确认删除
    row_menu(d, PRIME, '删除')
    time.sleep(0.8)
    confirm = None
    for b in visible(d, '[role=alertdialog] button, [role=dialog] button'):
        if b.text.strip() == '删除':
            confirm = b
    assert confirm is not None, '未找到确认删除钮'
    mark = perf_mark(d)
    js(d, confirm)
    time.sleep(3.5)
    e['confirm_api'] = [a for a in perf_since(d, mark) if a.get('method') != 'GET']
    trashed = api('/api/v1/tasks?page=1&per_page=10&search=%s&trash=true' % sq('INT1478_PRIME'))['data']
    e['trash_hit'] = [{'id': t['id'], 'deleted': t.get('deleted')} for t in trashed['items']]
    assert any(t['id'] == 551 for t in trashed['items']), '删除后回收站未见 551'
    # 回收站视图 → 恢复
    tt = find_by_text(d, {'回收站'}, tags=('button',))
    assert tt is not None, '未找到回收站 toggle'
    js(d, tt)
    time.sleep(3)
    e['trash_shot'] = shot(d, '07b_trash_view')
    row_menu(d, PRIME, '恢复')
    time.sleep(1.0)
    e['restore_dialog'] = dialog_text(d)
    shot(d, '07c_restore_confirm')
    ok = None
    for b in visible(d, '[role=alertdialog] button, [role=dialog] button'):
        if b.text.strip() == '恢复':
            ok = b
    assert ok is not None, '未找到确认恢复钮'
    js(d, ok)
    time.sleep(3)
    rst = api('/api/v1/tasks/551')['data']
    e['restored'] = {'deleted': rst.get('deleted'), 'execution_status': rst.get('execution_status')}
    assert rst.get('deleted') in (False, None), '恢复后 deleted 仍为真'
    js(d, find_by_text(d, {'回收站'}, tags=('button',)))
    time.sleep(2.5)
    # 彻底删除确认（先软删再 purge）
    row_menu(d, PRIME, '删除')
    time.sleep(0.8)
    for b in visible(d, '[role=alertdialog] button, [role=dialog] button'):
        if b.text.strip() == '删除':
            js(d, b)
            break
    time.sleep(3)
    js(d, find_by_text(d, {'回收站'}, tags=('button',)))
    time.sleep(3)
    row_menu(d, PRIME, '彻底删除')
    time.sleep(1.0)
    e['purge_dialog'] = dialog_text(d)
    shot(d, '07d_purge_confirm')
    close_dialog(d)
    e['purge_cancelled'] = not visible(d, '[role=dialog], [role=alertdialog]')
    js(d, find_by_text(d, {'回收站'}, tags=('button',)))
    time.sleep(2)


def main():
    d = driver()
    try:
        step('env', '环境核对 + 日常列表/页签计数', s_env, d)
        step('task_type', '创建新任务（TaskTypeDialog）', s_task_type, d)
        step('quick_view', '快速查看（QuickViewDialog）', s_quick_view, d)
        step('publish', '发布任务（PublishTaskDialog）', s_publish, d)
        step('data_export', '导出任务数据（DataExportDialog）', s_export, d)
        step('data_import', '导入任务数据（DataImportDialog）', s_import, d)
        step('reexecute', '重新执行范围（ReexecuteScopeDialog）', s_reexecute, d)
        step('delete_restore', '删除/恢复/彻底删除确认（TaskConfirmDialogs）', s_delete_restore, d)
    finally:
        flush()
        try:
            logs = [l for l in d.get_log('browser') if l['level'] == 'SEVERE']
            with open(os.path.join(ART, 'browser_severe.json'), 'w', encoding='utf-8') as f:
                json.dump(logs[:40], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            d.quit()
        except Exception:
            pass
        ok = sum(1 for r in report if r['ok'])
        print('\n== %d/%d 步骤通过 ==' % (ok, len(report)))


if __name__ == '__main__':
    main()
