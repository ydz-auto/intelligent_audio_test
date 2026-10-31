# -*- coding: utf-8 -*-
"""INT-2201 验收：任务列表 / 详情 / 挑选树时间按本地时区展示 + 已用时长按起止推算。

浏览器实测（headless Chrome + Selenium），被测前端 = 交付提交 13599b40d 构建产物（临时容器），
后端 = docker 真实库栈 http://localhost:15000（/health database=intelligent_audio_test）。

用法：
  python verify_int2201_task_time.py            # 15281 交付构建，按期望断言
  BASE=http://127.0.0.1:15173 python verify_int2201_task_time.py --baseline   # 旧镜像对照（不作断言）
"""
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15281').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
BASELINE = '--baseline' in sys.argv
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2201')
TOKEN_KEY = 'iatp:auth:token:v1'
THEME_KEY = 'iatp:theme:v1:mode'
USERNAME = os.environ.get('REACT_USER', '接线测试_admin')
PASSWORD = os.environ.get('REACT_PWD', 'JieXianTest@2026')
LOCAL = timezone(timedelta(hours=8))

LIST_TASK = 811          # 名称含「测试任务_2026-10-31 10:51」
DETAIL_TASK = 526        # 无 started_at
USED_TASK = 789          # 有 started_at + completed_at（后端 used_time 异常值样本）

RESULT = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))


def note(name, detail=''):
    RESULT.append({'name': name, 'ok': None, 'detail': str(detail)[:2000]})
    print('[NOTE] ' + name + ((' | ' + str(detail)[:400]) if detail else ''))


# ---------- API 侧 ----------
def get_token():
    with urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key', timeout=60) as r:
        key_data = json.loads(r.read().decode('utf-8'))
    pub = serialization.load_pem_public_key(key_data['public_key'].encode())
    enc = pub.encrypt(
        PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = urllib.parse.urlencode({
        'username': USERNAME,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': key_data['kid'],
    }).encode()
    req = urllib.request.Request(
        API + '/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))['access_token']


def api_get(token, path):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def parse_dt(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def local_str(value, with_seconds=False):
    dt = parse_dt(value)
    if not dt:
        return '—'
    fmt = '%Y-%m-%d %H:%M:%S' if with_seconds else '%Y-%m-%d %H:%M'
    return dt.astimezone(LOCAL).strftime(fmt)


def expected_elapsed(row):
    start, end = parse_dt(row.get('started_at')), parse_dt(row.get('completed_at'))
    if not start:
        return '—'
    if not end:
        return '(进行中)'
    total_seconds = max(0, int((end - start).total_seconds()))
    if total_seconds < 60:
        return '%d 秒' % total_seconds
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return '%d 分钟' % total_minutes
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return ('%d 小时 %d 分钟' % (hours, minutes)) if minutes else ('%d 小时' % hours)
    days, rest = divmod(hours, 24)
    return ('%d 天 %d 小时' % (days, rest)) if rest else ('%d 天' % days)


# ---------- 浏览器 ----------
def build_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1600,1100')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(90)
    return drv


def wait_ready(drv, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')


def body_text(drv):
    return drv.execute_script('return document.body.innerText') or ''


def rows_text(drv):
    return drv.execute_script(
        "return Array.from(document.querySelectorAll('tbody tr')).map(r => r.innerText);"
    ) or []


TIME_TOKEN = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})')


def time_cells(text):
    """行/卡片文本里的所有「日期 时:分」——最后一个是时间列，前几个可能是任务名里的时间。"""
    return TIME_TOKEN.findall(text or '')


def login_and_open(drv, path):
    drv.get(BASE + '/login')
    time.sleep(1)
    drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);',
                       TOKEN_KEY, TOKEN)
    drv.get(BASE + path)
    wait_ready(drv)
    time.sleep(3)


def set_theme(drv, mode):
    drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', THEME_KEY, mode)
    time.sleep(1)
    drv.refresh()
    wait_ready(drv)
    time.sleep(4)


def console_severe(drv):
    out = []
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                out.append(entry.get('message', '')[:300])
    except Exception as e:
        out.append('log error: %s' % e)
    return out


def card_line(drv, label):
    text = body_text(drv)
    m = re.search(r'%s\s*[:：]?\s*([^\n·]{0,60})' % re.escape(label), text)
    return (m.group(1).strip() if m else None), text


def pick_tree_flow(drv, tag, expected_tree_times, acc, list_created_local, assert_checks=True):
    """挑选合并：容器列表 →「开始挑选」→ 阶段 1 选任务 → 阶段 2 树，返回树文本。"""
    login_and_open(drv, '/tasks/cherry-picks')
    time.sleep(6)
    try:
        start_btn = drv.find_element(By.XPATH, "//button[contains(., '开始挑选')]")
        drv.execute_script('arguments[0].click()', start_btn)
        time.sleep(6)
    except Exception as e:
        note('[%s] 点击「开始挑选」失败' % tag, repr(e))
    try:
        inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索任务名称"]')
        drv.execute_script(
            "const el = arguments[0];"
            "const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
            "setter.call(el, arguments[1]);"
            "el.dispatchEvent(new Event('input', {bubbles: true}));",
            inp, '测试任务_2026-10-31 10:51')
        time.sleep(4)
    except Exception as e:
        note('[%s] 阶段 1 搜索框输入失败' % tag, repr(e))
    stage1_rows = drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-testid^=\"pick-task-\"]')).map(r => r.innerText);"
    ) or []
    s1 = [r for r in stage1_rows if '测试任务_2026-10-31 10:51' in r]
    if assert_checks:
        check('[%s] 挑选阶段 1 任务行出现（%d 行）' % (tag, len(stage1_rows)), bool(s1), stage1_rows[:1])
        if s1:
            cells = time_cells(s1[0])
            check('[%s] 挑选阶段 1 创建时间 = 本地 %s' % (tag, list_created_local),
                  bool(cells) and cells[-1] == list_created_local,
                  '时间列 %r / 整行 %r' % (cells[-1] if cells else None, s1[0].replace('\n', ' | ')))
    picked = False
    for sel in ('[data-testid="pick-task-%d"] input[type=checkbox]' % LIST_TASK,
                '[data-testid="pick-task-%d"] [role=checkbox]' % LIST_TASK):
        try:
            cb = drv.find_element(By.CSS_SELECTOR, sel)
            drv.execute_script('arguments[0].click()', cb)
            picked = True
            break
        except Exception:
            continue
    if not picked:
        note('[%s] 勾选阶段 1 任务失败' % tag, '未找到任务 %d 的勾选框' % LIST_TASK)
        return ''
    time.sleep(1)
    try:
        btn = drv.find_element(By.XPATH, "//button[contains(., '下一步：选择结果')]")
        drv.execute_script('arguments[0].click()', btn)
        time.sleep(6)
        try:
            eb = drv.find_element(By.XPATH, "//button[contains(., '全部展开')]")
            drv.execute_script('arguments[0].click()', eb)
            time.sleep(5)
        except Exception:
            pass
        time.sleep(2)
    except Exception as e:
        note('[%s] 阶段 2 展开失败' % tag, repr(e))
    return body_text(drv)



def main():
    os.makedirs(ART, exist_ok=True)
    global TOKEN
    TOKEN = get_token()

    health = json.loads(urllib.request.urlopen(API + '/health', timeout=30).read().decode('utf-8'))
    check('后端库 = intelligent_audio_test', health.get('database') == 'intelligent_audio_test', health)

    # --- 期望值（接口侧推） ---
    lst = api_get(TOKEN, '/api/v1/tasks?page=1&per_page=10')
    items = lst.get('data', {}).get('items') or lst.get('items') or []
    row = next((t for t in items if t.get('id') == LIST_TASK), None)
    check('列表含任务 %d' % LIST_TASK, row is not None)
    list_created_local = local_str((row or {}).get('created_at'))
    note('列表任务 %d 名称/接口 created_at/本地期望' % LIST_TASK,
         '%r / %r / %r' % ((row or {}).get('name'), (row or {}).get('created_at'), list_created_local))

    d526 = api_get(TOKEN, '/api/v1/tasks/%d' % DETAIL_TASK)
    d526 = d526.get('data') or d526
    d526_created_local = local_str(d526.get('created_at'))
    d526_elapsed = expected_elapsed(d526)

    d789 = api_get(TOKEN, '/api/v1/tasks/%d' % USED_TASK)
    d789 = d789.get('data') or d789
    d789_elapsed = expected_elapsed(d789)
    note('任务 %d 起止/后端 used_time/推算' % USED_TASK,
         '%r → %r, used_time=%r, 推算=%r' % (d789.get('started_at'), d789.get('completed_at'),
                                            d789.get('used_time'), d789_elapsed))

    tree = api_get(TOKEN, '/api/v1/tasks/cherry-picks/candidates/tree?task_ids=%d' % LIST_TASK)
    tree_nodes = (tree.get('data') or {}).get('tree') or []

    def collect_last_result(node, acc):
        if isinstance(node, dict):
            if node.get('last_result_at'):
                acc.append(node['last_result_at'])
            for c in (node.get('cases') or []):
                collect_last_result(c, acc)
            for c in (node.get('devices') or []):
                collect_last_result(c, acc)
            for c in (node.get('result_types') or []):
                collect_last_result(c, acc)
            for c in (node.get('children') or []):
                collect_last_result(c, acc)
        elif isinstance(node, list):
            for c in node:
                collect_last_result(c, acc)

    acc = []
    collect_last_result(tree_nodes, acc)
    expected_tree_times = sorted({local_str(v) for v in acc})
    note('挑选树 last_result_at 原始值 %d 个' % len(acc),
         '%r → 本地 %r' % (sorted(set(acc))[:6], expected_tree_times[:6]))

    drv = build_driver()
    try:
        # ---------- 1. 任务列表 ----------
        login_and_open(drv, '/tasks/daily')
        time.sleep(3)
        rows = rows_text(drv)
        target = [r for r in rows if '测试任务_2026-10-31 10:51' in r]
        check('列表页渲染任务行（%d 行）' % len(rows), bool(target), target[:1])
        if target:
            cells = time_cells(target[0])
            check('列表创建时间列 = 本地时间 %s' % list_created_local,
                  bool(cells) and cells[-1] == list_created_local,
                  '时间列 %r / 整行 %r' % (cells[-1] if cells else None,
                                          target[0].replace('\n', ' | ')))
            check('列表不再出现旧 UTC 切片 %s' % ((row or {}).get('created_at', '')[11:16]),
                  (row or {}).get('created_at', '')[11:16] not in target[0],
                  target[0].replace('\n', ' | '))
        drv.save_screenshot(os.path.join(ART, 'list_light_%s.png' % ('base' if BASELINE else 'fix')))

        # ---------- 2. 任务详情 526 ----------
        login_and_open(drv, '/tasks/%d' % DETAIL_TASK)
        time.sleep(3)
        text = body_text(drv)
        m = re.search(r'创建时间\s*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2})', text)
        shown_created = m.group(1) if m else None
        check('详情 %d 创建时间显示 = %s' % (DETAIL_TASK, d526_created_local),
              shown_created == d526_created_local, '实际 %r' % shown_created)
        m2 = re.search(r'已用时长\s*([^\n]{0,40})', text)
        shown_used = m2.group(1).strip() if m2 else None
        check('详情 %d 已用时长 = %s（started_at 为空）' % (DETAIL_TASK, d526_elapsed),
              shown_used is not None and shown_used.startswith(d526_elapsed), '实际 %r' % shown_used)
        drv.save_screenshot(os.path.join(ART, 'detail_light_%s.png' % ('base' if BASELINE else 'fix')))

        # ---------- 3. 任务详情 789（已用时长按起止推算） ----------
        login_and_open(drv, '/tasks/%d' % USED_TASK)
        time.sleep(3)
        text = body_text(drv)
        m3 = re.search(r'已用时长\s*([^\n]{0,40})', text)
        shown_used789 = m3.group(1).strip() if m3 else None
        check('详情 %d 已用时长 = 起止推算 %s' % (USED_TASK, d789_elapsed),
              shown_used789 is not None and shown_used789.startswith(d789_elapsed),
              '实际 %r / 后端 used_time %r' % (shown_used789, d789.get('used_time')))
        m4 = re.search(r'已用时间\s*([^\n/]{0,40})\s*/\s*预计时间', text)
        note('详情 %d 进度卡「已用时间」' % USED_TASK, repr(m4.group(1).strip() if m4 else None))

        # ---------- 3b. 起止时间正常（秒级）样本：确认短时长分级正确 ----------
        try:
            d730 = api_get(TOKEN, '/api/v1/tasks/730')
            d730 = d730.get('data') or d730
            e730 = expected_elapsed(d730)
            login_and_open(drv, '/tasks/730')
            time.sleep(3)
            m5 = re.search(r'已用时长\s*([^\n]{0,40})', body_text(drv))
            shown730 = m5.group(1).strip() if m5 else None
            check('详情 730 已用时长 = 起止推算 %s（%r→%r）' % (e730, d730.get('started_at'), d730.get('completed_at')),
                  shown730 is not None and shown730.startswith(e730), '实际 %r' % shown730)
        except Exception as e:
            note('详情 730 检查异常', repr(e))

        # ---------- 4. 挑选合并树 ----------
        tree_text = pick_tree_flow(drv, 'light', expected_tree_times, acc, list_created_local, assert_checks=True)
        hit = [t for t in expected_tree_times if t != '—' and t in tree_text]
        check('挑选树末条结果时间命中本地时间（%d/%d 期望值）' % (len(hit), len(expected_tree_times)),
              bool(hit), '命中 %r；期望 %r' % (hit, expected_tree_times[:6]))
        utc_slices = sorted({v[11:16] for v in set(acc)})
        bad = [s for s in utc_slices if re.search(r'(?<!\d)%s(?!\d)' % re.escape(s), tree_text)
               and s not in ''.join(expected_tree_times)]
        check('挑选树不再出现 UTC 切片 %r' % utc_slices, not bad, '残留 %r' % bad)
        drv.save_screenshot(os.path.join(ART, 'picktree_light_%s.png' % ('base' if BASELINE else 'fix')))
        sev = console_severe(drv)
        # /api/v1/reports/by_task/{id} 的 404 是既存噪声（15173 旧镜像同样报），与时间展示无关
        known = [m for m in sev if '/api/v1/reports/by_task/' in m]
        other = [m for m in sev if m not in known]
        note('console SEVERE（%d 条 /reports/by_task 404 为既存）' % len(known), sev[:3])
        check('console 无其他 SEVERE', not other, other[:3])

        # ---------- 深色 ----------
        set_theme(drv, 'dark')
        login_and_open(drv, '/tasks/daily')
        time.sleep(9)
        dark_rows = rows_text(drv)
        dark_target = [r for r in dark_rows if '测试任务_2026-10-31 10:51' in r]
        dark_cells = time_cells(dark_target[0]) if dark_target else []
        check('深色列表创建时间 = 本地 %s' % list_created_local,
              bool(dark_cells) and dark_cells[-1] == list_created_local,
              '时间列 %r / 整行 %r' % (dark_cells[-1] if dark_cells else None, dark_target[:1]))
        drv.save_screenshot(os.path.join(ART, 'list_dark_%s.png' % ('base' if BASELINE else 'fix')))
        login_and_open(drv, '/tasks/%d' % DETAIL_TASK)
        time.sleep(9)
        drv.save_screenshot(os.path.join(ART, 'detail_dark_%s.png' % ('base' if BASELINE else 'fix')))
        login_and_open(drv, '/tasks/cherry-picks')
        time.sleep(3)
        drv.save_screenshot(os.path.join(ART, 'pickstage_dark_%s.png' % ('base' if BASELINE else 'fix')))
        dark_tree_text = pick_tree_flow(drv, 'dark', expected_tree_times, acc, list_created_local, assert_checks=False)
        dark_hit = [t for t in expected_tree_times if t != '—' and t in dark_tree_text]
        note('[dark] 挑选树末条结果时间命中 %r' % dark_hit, '')
        drv.save_screenshot(os.path.join(ART, 'picktree_dark_%s.png' % ('base' if BASELINE else 'fix')))
        set_theme(drv, 'light')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'result_%s.json' % ('baseline' if BASELINE else 'fix'))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'base': BASE, 'baseline': BASELINE, 'result': RESULT}, f, ensure_ascii=False, indent=2)
    fails = [r for r in RESULT if r['ok'] is False]
    print('\n==== %d checks, %d fail ====' % (len([r for r in RESULT if r['ok'] is not None]), len(fails)))
    for f_ in fails:
        print('FAIL: %s | %s' % (f_['name'], f_['detail'][:300]))


if __name__ == '__main__':
    main()
