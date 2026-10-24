# -*- coding: utf-8 -*-
"""INT-1478 复走·React·任务域 —— 模态窗逐窗实测（docker 真实栈 15173 / 后端 15000 / 主库）。

每窗：浅色截图 + 深色截图 + 本窗期间的 /api 请求/响应（performance log）+ 可见文案。
失败步骤不阻断后续，逐条记录到 report.json。

用法：REACT_BASE=http://127.0.0.1:15173 python -I tests/ui/verify_int1478_task_modals.py
"""
import json
import os
import sys
import time
import traceback

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1478_task_modals')
os.makedirs(ART, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')

report = []


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_walk_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(90)
    return d


def js(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    d.execute_script('arguments[0].click();', el)


def find_by_text(d, texts, tags=('button', '*[role=menuitem]', '*[role=option]', 'a')):
    for tag in tags:
        for el in d.find_elements(By.CSS_SELECTOR, tag):
            try:
                if el.is_displayed() and el.text.strip() in texts:
                    return el
            except Exception:
                continue
    return None


def wait_text(d, text, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        el = find_by_text(d, {text})
        if el is not None:
            return el
        time.sleep(0.4)
    return None


def wait_sel(d, css, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(0.4)
    return None


def api_since(d, mark):
    out = []
    for m in d.get_log('performance')[mark:]:
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/' in r['url']:
                out.append({'status': r['status'], 'url': r['url'].replace(BASE, ''),
                            'mime': r.get('mimeType', '')})
    return out


def dialog_text(d):
    els = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog], [role=alertdialog]')
           if e.is_displayed()]
    if not els:
        return ''
    return els[0].text.strip()


def close_dialog(d):
    els = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog] [data-slot=dialog-close], [role=alertdialog] [data-slot=dialog-close]')
           if e.is_displayed()]
    if els:
        js(d, els[0])
    else:
        try:
            ActionChains(d).send_keys(Keys.ESCAPE).perform()
        except Exception:
            pass
    time.sleep(0.6)
    # 兜底：点遮罩外的取消钮
    if any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog]')):
        btn = find_by_text(d, {'取消', '关闭'})
        if btn is not None:
            js(d, btn)
    time.sleep(0.5)


def set_dark(d, on):
    d.execute_script(
        "document.documentElement.classList.remove('%s');"
        "document.documentElement.classList.add('%s');"
        % ('light' if on else 'dark', 'dark' if on else 'light'))


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    return p


def step(key, title, fn, d):
    mark = len(d.get_log('performance'))
    entry = {'key': key, 'title': title, 'ok': False, 'light': None, 'dark': None,
             'dialog_text': '', 'api': [], 'error': None}
    try:
        fn(d, entry)
        entry['ok'] = True
    except Exception as exc:  # noqa: BLE001
        entry['error'] = '%s: %s' % (type(exc).__name__, exc)
        traceback.print_exc()
        try:
            close_dialog(d)
        except Exception:
            pass
    entry['api'] = api_since(d, mark)
    report.append(entry)
    print(('[OK]  ' if entry['ok'] else '[FAIL]') + ' ' + key + ' ' +
          (entry['error'] or entry['dialog_text'][:80].replace('\n', ' | ')))
    return entry


def capture(d, entry, key):
    time.sleep(0.8)
    entry['dialog_text'] = dialog_text(d)
    entry['light'] = shot(d, key + '_light')
    set_dark(d, True)
    time.sleep(0.5)
    entry['dark'] = shot(d, key + '_dark')
    set_dark(d, False)
    time.sleep(0.25)


# ---------------- steps ----------------

def s_create_task(d, e):
    btn = wait_text(d, '创建新任务')
    assert btn is not None, '未找到「创建新任务」'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '01_task_type')
    close_dialog(d)


def s_import(d, e):
    btn = wait_text(d, '导入数据')
    assert btn is not None, '未找到「导入数据」'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '02_data_import')
    close_dialog(d)


def _row_menu(d, item_text):
    trig = wait_sel(d, 'button[aria-label="任务操作"]')
    assert trig is not None, '未找到行操作按钮'
    js(d, trig)
    time.sleep(0.6)
    item = wait_text(d, {item_text}, timeout=8)
    assert item is not None, '菜单项「%s」未出现' % item_text
    js(d, item)
    time.sleep(0.8)


def s_quick_view(d, e):
    _row_menu(d, '快速查看')
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '03_quick_view')
    close_dialog(d)


def s_publish(d, e):
    _row_menu(d, '发布')
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '04_publish_task')
    close_dialog(d)


def s_reexecute(d, e):
    _row_menu(d, '重新执行')
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '05_reexecute_scope')
    close_dialog(d)


def s_delete_confirm(d, e):
    _row_menu(d, '删除')
    assert wait_sel(d, '[role=alertdialog], [role=dialog]') is not None, '确认弹窗未出现'
    capture(d, e, '06_task_confirm_delete')
    close_dialog(d)


def s_export(d, e):
    box = wait_sel(d, 'input[type=checkbox], button[aria-label^="选择 "]')
    assert box is not None, '未找到行勾选框'
    js(d, box)
    time.sleep(0.6)
    btn = wait_text(d, '导出数据', timeout=10)
    assert btn is not None, '批量浮条「导出数据」未出现'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '弹窗未出现'
    capture(d, e, '07_data_export')
    close_dialog(d)


def s_published_snapshots(d, e):
    tab = wait_text(d, {'已发布'}, tags=('button', '*[role=tab]'))
    assert tab is not None, '未找到「已发布」页签'
    js(d, tab)
    time.sleep(2.5)
    exp = wait_sel(d, 'button[aria-label="展开版本详情"]', timeout=20)
    assert exp is not None, '未找到「展开版本详情」'
    js(d, exp)
    time.sleep(2.5)
    ts = wait_text(d, '查看冻结任务详情', timeout=12)
    assert ts is not None, '未找到「查看冻结任务详情」'
    js(d, ts)
    assert wait_sel(d, '[role=dialog]') is not None, '任务快照弹窗未出现'
    capture(d, e, '08_task_snapshot')
    close_dialog(d)
    rs = wait_text(d, '查看冻结报告', timeout=10)
    if rs is not None:
        js(d, rs)
        time.sleep(1.0)
        e['report_snapshot'] = dialog_text(d)
        e['dark'] = e['dark'] or shot(d, '09_report_snapshot_dark')
        shot(d, '09_report_snapshot_light')
        close_dialog(d)


def s_cherry_cart(d, e):
    tab = wait_text(d, {'挑选合并'}, tags=('button', '*[role=tab]'))
    assert tab is not None, '未找到「挑选合并」页签'
    js(d, tab)
    time.sleep(3)
    btn = wait_text(d, '打开购物车', timeout=15)
    assert btn is not None, '未找到「打开购物车」'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '购物车抽屉未出现'
    capture(d, e, '10_cart_drawer')
    close_dialog(d)


def s_cherry_rename(d, e):
    trig = wait_sel(d, 'button[aria-label="挑选合并任务操作"]', timeout=20)
    assert trig is not None, '未找到容器行操作'
    js(d, trig)
    time.sleep(0.6)
    item = wait_text(d, {'重命名'}, timeout=8)
    assert item is not None, '菜单项「重命名」未出现'
    js(d, item)
    assert wait_sel(d, '[role=dialog]') is not None, '重命名弹窗未出现'
    capture(d, e, '11_container_rename')
    close_dialog(d)


def s_cherry_pick_wizard(d, e):
    btn = wait_text(d, '开始挑选', timeout=15)
    assert btn is not None, '未找到「开始挑选」'
    js(d, btn)
    assert wait_sel(d, '[role=dialog]') is not None, '挑选向导未出现'
    capture(d, e, '12_pick_wizard')
    # 向导内「另存挑选集」入口：找到即点
    sv = find_by_text(d, {'另存挑选集', '保存挑选集'})
    if sv is not None:
        js(d, sv)
        time.sleep(1.0)
        e['save_set_dialog'] = dialog_text(d)
        shot(d, '13_save_pick_set_light')
        set_dark(d, True)
        shot(d, '13_save_pick_set_dark')
        set_dark(d, False)
        close_dialog(d)
    close_dialog(d)


def s_detail_review(d, e):
    d.get(BASE + '/tasks/527')
    time.sleep(6)
    body = d.find_element(By.TAG_NAME, 'body').text
    e['page_text'] = body[:300]
    btn = find_by_text(d, {'复核', '人工复核', '快速复核'})
    if btn is not None:
        js(d, btn)
        time.sleep(1.0)
        e['manual_review_dialog'] = dialog_text(d)
        shot(d, '14_manual_review_light')
        set_dark(d, True)
        shot(d, '14_manual_review_dark')
        set_dark(d, False)
        close_dialog(d)
    hist = find_by_text(d, {'查看复核历史'})
    if hist is not None:
        js(d, hist)
        time.sleep(1.5)
        e['history_drawer'] = dialog_text(d) or d.find_element(By.TAG_NAME, 'body').text[-300:]
        shot(d, '15_review_history_light')
        set_dark(d, True)
        shot(d, '15_review_history_dark')
        set_dark(d, False)
        close_dialog(d)
    assert btn is not None or hist is not None, '详情页未找到复核入口'


def main():
    d = driver()
    try:
        d.get(BASE + '/tasks/daily')
        time.sleep(8)
        assert wait_sel(d, 'button[aria-label="任务操作"]', 30) is not None, '任务列表未渲染'
        shot(d, '00_tasks_daily_light')
        step('task_type', '创建新任务（TaskTypeDialog）', s_create_task, d)
        step('data_import', '导入任务数据（DataImportDialog）', s_import, d)
        step('quick_view', '快速查看（QuickViewDialog）', s_quick_view, d)
        step('publish', '发布任务（PublishTaskDialog）', s_publish, d)
        step('reexecute', '重新执行范围（ReexecuteScopeDialog）', s_reexecute, d)
        step('delete_confirm', '删除确认（TaskConfirmDialogs）', s_delete_confirm, d)
        step('data_export', '导出任务数据（DataExportDialog）', s_export, d)
        step('published_snapshot', '已发布冻结快照（Task/ReportSnapshotDialog）',
             s_published_snapshots, d)
        step('cart_drawer', '购物车抽屉（CartDrawer）', s_cherry_cart, d)
        step('container_rename', '容器重命名（ContainerRenameDialog）', s_cherry_rename, d)
        step('pick_wizard', '挑选向导 + 另存挑选集（PickDialog/SavePickSetDialog）',
             s_cherry_pick_wizard, d)
        step('detail_review', '详情页人工复核 + 复核历史', s_detail_review, d)
    finally:
        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
        ok = sum(1 for r in report if r['ok'])
        print('\n== %d/%d 步骤通过 ==' % (ok, len(report)))


if __name__ == '__main__':
    main()
