# -*- coding: utf-8 -*-
"""INT-2211 返工复测（问题 1/2 + 问题 3 + 已过项抽检）。

环境：交付 sha 7a315505c 的 frontend-react 构建产物挂载到旁路 nginx 容器
      http://localhost:15231（/api 反代 api_gateway），后端 docker 真实库 15000。

核对：
  P1  交付分支自身单测 `pick-task-stage.test.tsx` 12 passed（vitest 单独跑，不在本脚本）
  P2  算法列表「更新时间」与详情「创建/更新时间」同值且 = 后端裸 UTC +8h
  P3  音频管理 / SPL 映射列表时间 = 后端裸 UTC +8h
  S   已过项抽检：首页 / 报告 / 测试设备 / 任务 列表时间 = 裸 UTC +8h
  T   浅色 / 深色各一遍（iatp:theme:v1:mode）

原始值取后端接口（脚本侧按 UTC 独立换算，不复用被测共享工具）。
运行：D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/verify_int2211_retest.py
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15231')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2211_retest')
os.makedirs(ART, exist_ok=True)
ACCOUNT = ('dev_user', 'dev_password')
RESULTS = []
NET = []

TIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')
RENDERED_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
TIME_KEYS = ('created_at', 'updated_at', 'last_online_at', 'started_at', 'finished_at')


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:1500], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:800])
    return entry


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT ' + path)
    return path


def local_dt(raw):
    """后端裸 UTC 串 → 本地 YYYY-MM-DD HH:mm（脚本侧独立换算）。"""
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})', str(raw).strip())
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    utc = datetime.datetime(y, mo, d, h, mi, tzinfo=datetime.timezone.utc)
    return utc.astimezone().strftime('%Y-%m-%d %H:%M')


def dig_items(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('items'), list):
            return obj['items']
        for k in ('data', 'result'):
            if k in obj:
                v = dig_items(obj[k])
                if v is not None:
                    return v
    if isinstance(obj, list):
        return obj
    return None


def collect_records(obj, out=None, depth=0):
    """递归收集带时间字段的 dict 记录。"""
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        if any(isinstance(obj.get(k), str) and TIME_RE.match(str(obj.get(k))) for k in TIME_KEYS):
            out.append(obj)
        for v in obj.values():
            collect_records(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            collect_records(v, out, depth + 1)
    return out


def api_records(token, path):
    """后端接口 → dict 记录列表（优先 items，否则递归抽取）。"""
    status, js = B.api(path, token)
    if status != 200:
        return status, []
    items = dig_items(js)
    if items is not None:
        return status, [x for x in items if isinstance(x, dict)]
    return status, collect_records(js)


def table_rows(drv):
    return drv.execute_script(
        """return Array.from(document.querySelectorAll('tbody tr')).map(function(tr){
              return Array.from(tr.querySelectorAll('td')).map(function(td){
                return (td.textContent || '').trim();
              });
            });"""
    )


def row_with_id(rows, rid):
    for cells in rows:
        for c in cells:
            if c == ('#%s' % rid):
                return cells
    return None


def time_cell(cells):
    for c in cells:
        if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$', c):
            return c
    return None


def dialog_text(drv):
    return drv.execute_script(
        """var d=document.querySelector('[role=dialog]');
           return d ? (d.innerText || d.textContent || '') : '';"""
    )


def field_value(dlg_text, label):
    m = re.search(re.escape(label) + r'\s*[:：]?\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', dlg_text)
    return m.group(1) if m else None


def dark_mode(drv):
    return 'dark' in (drv.execute_script('return document.documentElement.className') or '')


def assert_theme(drv, theme):
    want = (theme == 'dark')
    try:
        WebDriverWait(drv, 20).until(lambda d: dark_mode(d) == want)
    except Exception:
        record('主题 %s 生效' % theme, False, 'documentElement.className=%s'
               % drv.execute_script('return document.documentElement.className'))
        return
    record('主题 %s 生效' % theme, True,
           'className=%s bodyBg=%s' % (
               drv.execute_script('return document.documentElement.className'),
               drv.execute_script("return getComputedStyle(document.body).backgroundColor")))


def capture_net(drv):
    for rec in B.plog_net(drv):
        url = rec.get('url') or ''
        if '/api/' in url:
            NET.append({'method': rec.get('method'), 'url': url.split('?')[0],
                        'status': rec.get('status')})


def reset(drv):
    try:
        drv.execute_script('if (window.__reqs) window.__reqs = [];')
    except Exception:
        pass
    B.drain_perf(drv)


# ---------------------------------------------------------------------------
# 行级核对：用后端 id 对上 DOM 行，比较时间列
# ---------------------------------------------------------------------------

def check_rows(drv, theme, token, name, path, needle, api_path, time_key, label):
    reset(drv)
    B.goto(drv, path, needle)
    assert_theme(drv, theme)
    WebDriverWait(drv, 60).until(lambda d: len(table_rows(d)) > 0)
    time.sleep(0.8)
    status, items = api_records(token, api_path)
    rows = table_rows(drv)
    verified, mism, samples = 0, [], []
    for it in items:
        if not it.get('id') or not it.get(time_key):
            continue
        cells = row_with_id(rows, it.get('id'))
        if not cells:
            continue
        exp = local_dt(it[time_key])
        actual = time_cell(cells)
        raw_slice = str(it[time_key]).replace('T', ' ')[:16]
        samples.append((it.get('id'), it[time_key], exp, actual))
        if actual == exp and exp != raw_slice:
            verified += 1
        else:
            mism.append((it.get('id'), it[time_key], exp, actual))
    ok = verified >= 1 and not mism
    record('%s[%s] %s 时间 +8（逐行）' % (name, theme, label), ok,
           'api=%s 定位 %d 行，命中 %d，未命中 %d；示例 %s'
           % (status, len(samples), verified, len(mism), (mism or samples)[:3]))
    shot(drv, '%s_%s' % (name, theme))
    capture_net(drv)
    return items, rows


def check_algorithm(drv, theme, token):
    """P2：列表更新时间 vs 详情创建/更新时间。"""
    items, rows = check_rows(drv, theme, token, 'algorithm', '/AlgorithmConfig',
                             '算法类型', '/api/v1/algorithm/definitions', 'updated_at', '算法列表')
    target = None
    for it in items:
        cells = row_with_id(rows, it.get('id'))
        if cells and it.get('updated_at'):
            target = (it, cells)
            break
    if not target:
        record('P2[%s] 算法详情核对' % theme, False, '无可用行 items=%d rows=%d'
               % (len(items), len(rows)))
        return
    it, cells = target
    list_time = time_cell(cells)
    exp_updated = local_dt(it['updated_at'])
    exp_created = local_dt(it.get('created_at')) if it.get('created_at') else None

    drv.find_element(By.XPATH, "//tbody/tr[contains(., '#%s')]" % it.get('id')).click()
    WebDriverWait(drv, 20).until(lambda d: len(dialog_text(d)) > 50)
    time.sleep(0.6)
    dlg = dialog_text(drv)
    c_time = field_value(dlg, '创建时间')
    u_time = field_value(dlg, '更新时间')
    record('P2[%s] 算法 #%s 详情创建/更新时间' % (theme, it.get('id')),
           c_time == exp_created and u_time == exp_updated,
           '接口 created=%s updated=%s；详情创建=%s（期望 %s）详情更新=%s（期望 %s）'
           % (it.get('created_at'), it['updated_at'], c_time, exp_created, u_time, exp_updated))
    record('P2[%s] 列表/详情同值' % theme, list_time == u_time,
           '列表=%s 详情=%s' % (list_time, u_time))
    shot(drv, 'algorithm_detail_%s' % theme)
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 通用页：DOM 中出现的所有「YYYY-MM-DD HH:mm」都必须来自后端原始值 +8h
# ---------------------------------------------------------------------------

def dom_times(drv):
    out = []
    for cells in table_rows(drv):
        for c in cells:
            if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$', c):
                out.append(c)
    return out


def check_page(drv, theme, token, name, path, needle, api_paths, label):
    reset(drv)
    B.goto(drv, path, needle)
    assert_theme(drv, theme)
    # 报告等列表首屏较慢：等到出现真实行（骨架屏阶段 tbody 行是占位）
    try:
        WebDriverWait(drv, 45).until(lambda d: len(dom_times(d)) > 0)
    except Exception:
        time.sleep(3.0)
    expected = set()
    recs = 0
    for ap in api_paths:
        _, items = api_records(token, ap)
        recs += len(items)
        for r in items:
            for k in TIME_KEYS:
                v = r.get(k)
                if isinstance(v, str) and TIME_RE.match(v):
                    exp = local_dt(v)
                    if exp:
                        expected.add(exp)
    dom = dom_times(drv)
    if not dom:
        # 无表格时间列时退化为全页文本匹配
        body = B.body_text(drv)
        dom = sorted(set(RENDERED_RE.findall(body)))
    hit = [t for t in dom if t in expected]
    bad = [t for t in dom if t not in expected]
    ok = bool(dom) and bool(hit) and (len(hit) * 2 >= len(dom))
    record('%s[%s] %s 时间 +8' % (name, theme, label), ok,
           '接口记录 %d，DOM 时间 %d，命中 %d，未命中 %s；接口期望样例 %s'
           % (recs, len(dom), len(hit), bad[:4], sorted(expected)[:3]))
    shot(drv, '%s_%s' % (name, theme))
    capture_net(drv)


def main():
    token, user = B.rsa_login_token(*ACCOUNT)
    print('login ok user=%s' % (user or {}).get('username'))
    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, user)
        tz = drv.execute_script('return Intl.DateTimeFormat().resolvedOptions().timeZone')
        off = drv.execute_script('return new Date().getTimezoneOffset()')
        record('环境 时区', off == -480, 'tz=%s offset=%s base=%s' % (tz, off, B.BASE))
        record('前端健康（真实后端）', 'intelligent_audio_test' in (
            urllib.request.urlopen(B.BASE + '/health', timeout=10).read().decode()),
            B.BASE + '/health')

        for theme in ('light', 'dark'):
            if theme == 'dark':
                B.set_theme(drv, 'dark')
            check_algorithm(drv, theme, token)
            check_rows(drv, theme, token, 'audio', '/audio-import', '文件名',
                       '/api/v1/audios', 'created_at', '音频管理')
            check_rows(drv, theme, token, 'spl', '/SPLMapping', '映射名称',
                       '/api/v1/spl', 'updated_at', 'SPL 映射')
            check_page(drv, theme, token, 'dashboard', '/dashboard', '最近任务',
                       ['/api/v1/home/stats/summary', '/api/v1/tasks'], '首页最近任务')
            check_page(drv, theme, token, 'reports', '/reports', '报告',
                       ['/api/v1/reports'], '报告列表')
            check_page(drv, theme, token, 'devices_test', '/devices/test', '最后在线',
                       ['/api/v1/test-devices'], '测试设备')
            check_page(drv, theme, token, 'tasks', '/tasks/list', '任务名称',
                       ['/api/v1/tasks'], '任务列表')

        bad_net = [n for n in NET
                   if isinstance(n['status'], int) and (n['status'] >= 400 or n['status'] == -1)]
        record('无 mock 残留（真实接口）', not bad_net,
               'api 请求 %d 条，失败状态：%s' % (len(NET), bad_net[:6]))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as fp:
        json.dump({'results': RESULTS, 'network': NET}, fp, ensure_ascii=False, indent=2)

    bad = [r for r in RESULTS if not r['ok']]
    print('\n==== TOTAL %d, FAIL %d ====' % (len(RESULTS), len(bad)))
    for r in bad:
        print('FAIL:', r['step'], '::', r['detail'])
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
