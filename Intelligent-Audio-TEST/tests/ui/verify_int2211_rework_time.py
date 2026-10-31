# -*- coding: utf-8 -*-
"""INT-2211 返工复核：并入 wiring/react 头后，时间口径与 INT-2210 已用时长守卫均保持正确。

用途（只做打回项 + 抽检，不复跑全量）：
  1) 任务详情 789（started_at 早于 created_at 的真实库脏数据）→「已用时长」必须为「—」（INT-2210 守卫在合并后仍生效）
  2) 任务详情 730（起止正常）→「已用时长」= 起止推算
  3) 任务详情 526（started_at 为空）→「已用时长」=「—」
  4) 任务列表 / 设备测试页 / 报告列表：后端裸 UTC → 页面本地 +8（本卡跨域口径未因合并回退）
  5) 页面内 fetch 取接口原始值作 Network 证据；浅 / 深各一遍

被测：REACT_BASE（默认本卡合并树构建产物容器 15251），后端 docker 真实库 http://localhost:15000。
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int2201_task_time as V  # 复用登录 / driver / 主题 / 取值辅助

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2211_rework')
RESULT = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))


def note(name, detail=''):
    RESULT.append({'name': name, 'ok': None, 'detail': str(detail)[:2000]})
    print('[NOTE] ' + name + ((' | ' + str(detail)[:400]) if detail else ''))


def inpage_get(drv, path):
    """页面内带 token 拉真实接口（Network 证据，返回 status + JSON 原文片段）。"""
    script = """
    const done = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1') || '';
    fetch(arguments[0], {headers: {Authorization: 'Bearer ' + token}})
      .then(async r => done({status: r.status, body: await r.text()}))
      .catch(e => done({status: -1, body: String(e)}));
    """
    raw = drv.execute_async_script(script, '/api/v1' + path)
    body = (raw or {}).get('body') or ''
    try:
        data = json.loads(body)
    except Exception:
        data = None
    return (raw or {}).get('status'), data, body[:400]


def safe_open(drv, path, attempts=3):
    """导航重试：宿主高负载时网关偶发 ConnectionReset，重试即可。"""
    last = None
    for _ in range(attempts):
        try:
            V.login_and_open(drv, path)
            return True
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4)
    note('导航失败 %s' % path, repr(last))
    return False


def used_time_of(drv, task_id, timeout=35):
    safe_open(drv, '/tasks/%d' % task_id)
    end = time.time() + timeout
    text = ''
    while time.time() < end:
        text = V.body_text(drv)
        m = re.search(r'已用时长\s*([^\n]{0,40})', text)
        if m:
            return m.group(1).strip(), text
        time.sleep(2)
    return None, text


def wait_for_text(drv, needle, timeout=40):
    """慢页面（报告列表约 15s、设备页约 10-40s）轮询等待，返回是否命中。"""
    end = time.time() + timeout
    while time.time() < end:
        if needle and needle != '—' and needle in V.body_text(drv):
            return True
        time.sleep(2)
    return False


def main():
    os.makedirs(ART, exist_ok=True)
    V.ART = ART
    token = V.get_token()
    V.TOKEN = token

    health = json.loads(urllib.request.urlopen(V.API + '/health', timeout=30).read().decode('utf-8'))
    check('后端库 = intelligent_audio_test', health.get('database') == 'intelligent_audio_test', health)

    # ---- 动态挑样本（真实库任务会轮换，不写死 id）----
    tasks = V.api_get(token, '/api/v1/tasks?page=1&per_page=100')
    items = tasks.get('data', {}).get('items') or tasks.get('items') or []
    dirty = norm = nullstart = None
    for r in items:
        s, c, e = V.parse_dt(r.get('started_at')), V.parse_dt(r.get('created_at')), V.parse_dt(r.get('completed_at'))
        if not s:
            nullstart = nullstart or r
        elif c and s < c:
            dirty = dirty or r
        elif e and (e - s).total_seconds() > 30:
            norm = norm or r
    check('已发现 started_at<created_at 脏数据样本', dirty is not None,
          (dirty or {}).get('id'))
    check('已发现起止正常样本', norm is not None, (norm or {}).get('id'))
    check('已发现 started_at 为空样本', nullstart is not None, (nullstart or {}).get('id'))
    if not (dirty and norm and nullstart):
        note('样本不全，后续按可用样本继续', 'dirty=%r norm=%r null=%r'
             % ((dirty or {}).get('id'), (norm or {}).get('id'), (nullstart or {}).get('id')))

    DIRTY_ID = (dirty or {}).get('id')
    NORM_ID = (norm or {}).get('id')
    NULL_ID = (nullstart or {}).get('id')

    d789 = V.api_get(token, '/api/v1/tasks/%d' % DIRTY_ID) if DIRTY_ID else {}
    d789 = d789.get('data') or d789
    dirty_flag = bool(d789.get('started_at') and d789.get('created_at')
                      and V.parse_dt(d789['started_at']) < V.parse_dt(d789['created_at']))
    note('脏数据样本 %r 起止' % DIRTY_ID,
         'created=%r started=%r completed=%r used_time=%r dirty=%s'
         % (d789.get('created_at'), d789.get('started_at'), d789.get('completed_at'),
            d789.get('used_time'), dirty_flag))
    check('脏数据样本仍是 started_at<created_at（守卫应有意义）', dirty_flag, d789.get('started_at'))

    d730 = V.api_get(token, '/api/v1/tasks/%d' % NORM_ID) if NORM_ID else {}
    d730 = d730.get('data') or d730
    e730 = V.expected_elapsed(d730)
    trow = items[0] if items else {}
    t_created_local = V.local_str(trow.get('created_at'))
    note('任务列表首条', 'id=%r created_at=%r 本地=%r'
         % (trow.get('id'), trow.get('created_at'), t_created_local))

    devs = V.api_get(token, '/api/v1/test-devices?page=1&per_page=20')
    ditems = devs.get('data', {}).get('items') or devs.get('items') or []
    dev = next((d for d in ditems if d.get('last_online_at')), None)
    dev_local = V.local_str((dev or {}).get('last_online_at'))
    note('测试设备首条 last_online_at', '%r → 本地 %r'
         % ((dev or {}).get('last_online_at'), dev_local))

    reps = V.api_get(token, '/api/v1/reports?page=1&per_page=20')
    ritems = reps.get('data', {}).get('items') or reps.get('items') or []
    rep = next((r for r in ritems if r.get('created_at')), None)
    rep_local = V.local_str((rep or {}).get('created_at'))
    note('报告首条 created_at', '%r → 本地 %r' % ((rep or {}).get('created_at'), rep_local))

    drv = V.build_driver()
    try:
        # ---- 1/2/3 已用时长 ----
        shown789, text789 = used_time_of(drv, DIRTY_ID)
        check('详情 %r 已用时长 = —（INT-2210 守卫）' % DIRTY_ID, shown789 == '—',
              '实际 %r / 后端 used_time %r' % (shown789, d789.get('used_time')))
        drv.save_screenshot(os.path.join(ART, 'task_dirty_used_light.png'))

        shown730, _ = used_time_of(drv, NORM_ID)
        check('详情 %r 已用时长 = 起止推算 %s' % (NORM_ID, e730),
              shown730 is not None and shown730.startswith(e730), '实际 %r' % shown730)

        shown526, _ = used_time_of(drv, NULL_ID)
        check('详情 %r 已用时长 = —（started_at 为空）' % NULL_ID, shown526 == '—', '实际 %r' % shown526)

        # ---- 4 跨域时区口径 ----
        safe_open(drv, '/tasks/daily')
        time.sleep(4)
        rows = V.rows_text(drv)
        hit_row = None
        if trow.get('id') is not None:
            for r in rows:
                if str(trow.get('id')) in r:
                    hit_row = r
                    break
        if hit_row is None and trow.get('name'):
            hit_row = next((r for r in rows if trow['name'] in r), None)
        cells = V.time_cells(hit_row or '')
        check('任务列表创建时间 = 本地 %s' % t_created_local,
              bool(cells) and cells[-1] == t_created_local,
              '时间列 %r / 行 %r' % (cells[-1] if cells else None, (hit_row or '')[:160]))
        st, obj, raw = inpage_get(drv, '/tasks?page=1&per_page=10')
        check('页面内 fetch /tasks 命中真实网关', st == 200 and isinstance(obj, dict),
              'status=%s body=%r' % (st, raw))
        drv.save_screenshot(os.path.join(ART, 'tasks_list_light.png'))

        safe_open(drv, '/devices/test')
        ok_dev = wait_for_text(drv, dev_local)
        check('设备测试页最后在线 = 本地 %s' % dev_local,
              ok_dev, '页面是否含 %r：%s' % (dev_local, ok_dev))
        drv.save_screenshot(os.path.join(ART, 'devices_test_light.png'))

        safe_open(drv, '/reports')
        ok_rep = wait_for_text(drv, rep_local)
        check('报告列表创建时间 = 本地 %s' % rep_local,
              ok_rep, '页面是否含 %r：%s' % (rep_local, ok_rep))
        drv.save_screenshot(os.path.join(ART, 'reports_light.png'))

        sev = V.console_severe(drv)
        known = [m for m in sev if '/api/v1/reports/by_task/' in m]
        other = [m for m in sev if m not in known]
        note('console SEVERE（%d 条 /reports/by_task 404 既存）' % len(known), sev[:3])
        check('console 无其他 SEVERE', not other, other[:3])

        # ---- 深色 ----
        try:
            V.set_theme(drv, 'dark')
        except Exception as e:
            note('切换深色失败', repr(e))
        shown789d, _ = used_time_of(drv, DIRTY_ID)
        check('[dark] 详情 %r 已用时长 = —' % DIRTY_ID, shown789d == '—', '实际 %r' % shown789d)
        drv.save_screenshot(os.path.join(ART, 'task_dirty_used_dark.png'))
        safe_open(drv, '/devices/test')
        ok_dev_d = wait_for_text(drv, dev_local)
        check('[dark] 设备测试页最后在线 = 本地 %s' % dev_local, ok_dev_d, dev_local)
        drv.save_screenshot(os.path.join(ART, 'devices_test_dark.png'))
        safe_open(drv, '/reports')
        wait_for_text(drv, rep_local)
        drv.save_screenshot(os.path.join(ART, 'reports_dark.png'))
        try:
            V.set_theme(drv, 'light')
        except Exception as e:
            note('切回浅色失败', repr(e))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out = os.path.join(ART, 'result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'base': V.BASE, 'result': RESULT}, f, ensure_ascii=False, indent=2)
    fails = [r for r in RESULT if r['ok'] is False]
    print('\n==== %d checks, %d fail ====' % (len([r for r in RESULT if r['ok'] is not None]), len(fails)))
    for f_ in fails:
        print('FAIL: %s | %s' % (f_['name'], f_['detail'][:300]))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
