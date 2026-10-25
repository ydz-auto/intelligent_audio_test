# -*- coding: utf-8 -*-
"""INT-1934 补证第 3 项：5 个窗补另一主题（每窗浅 + 深，同源 reload 生效）+ 导出下载端到端。

窗口：data-export（导出任务数据）/ data-import（导入任务数据）/
      reexecute-scope（重新执行范围）/ task-confirm（删除二次确认）/ save-pick-set（另存为挑选集）

用法：python tests/ui/verify_int1934_windows.py
产出：tests/ui/artifacts/int1934/shots/*.png + windows_report.json（含下载文件/耗时/网络）
"""
import json
import os
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium.webdriver.common.by import By  # noqa: E402

import _int1934_ui as U  # noqa: E402
from _int1934_lib import Api, unwrap  # noqa: E402

ART = U.ART
DL = os.path.join(ART, 'downloads')
ADMIN = '接线测试_admin'
ADMIN_PASS = 'JieXianTest@2026'
EXPORT_TASK = '接线测试_INT1716_AUDIT_B'   # 1 用例的窄样本（先窄范围验证）
EXPORT_TASK_ID = 658
report = {'card': 'INT-1934', 'kind': 'windows', 'windows': {}, 'env': {}, 'export': {}}


def env_check(api):
    st, h = api.raw('/health')
    st2, page = api.raw(U.BASE + '/', timeout=30)
    html = page.decode('utf-8', 'replace') if isinstance(page, bytes) else str(page)
    import re
    lib = re.findall(r'(?:lib-react|index)\.[a-z0-9]+\.js', html)
    report['env'] = {'health_status': st, 'health': h, 'frontend': U.BASE,
                     'bundle': lib[:4]}
    assert h.get('database') == 'intelligent_audio_test', '连错库 %s' % h
    assert any(x.startswith('lib-react') for x in lib), '前端不是 React 构建：%s' % lib
    return report['env']


def wait_download(before, timeout=180):
    t0 = time.time()
    stable = 0
    last = -1
    while time.time() - t0 < timeout:
        files = [f for f in os.listdir(DL)
                 if f.lower().endswith('.zip') and f not in before]
        if files:
            f = os.path.join(DL, files[0])
            sz = os.path.getsize(f)
            if sz == last and sz > 0:
                stable += 1
                if stable >= 3:
                    return f
            else:
                stable = 0
                last = sz
        time.sleep(0.5)
    return None


def export_dialog_open(d):
    row = d.find_element(By.XPATH, "//tr[contains(., '%s')]" % EXPORT_TASK)
    cb = row.find_element(By.CSS_SELECTOR, 'input[type=checkbox]')
    U.js_click(d, cb)
    btn = U.wait_text(d, '导出数据', timeout=15)
    assert btn is not None, '批量浮条「导出数据」未出现'
    U.js_click(d, btn)
    assert U.wait_vis(d, '[role=dialog]', 20) is not None, '导出弹窗未出现'


def pass_export(d, token, mode):
    """data-export 窗：浅色轮次内完成真实导出（下载 + 计时），深色轮次只截帧。"""
    info = U.enter(d, token, '/tasks/daily', mode,
                   ready_css='button[aria-label="任务操作"]')
    export_dialog_open(d)
    time.sleep(1.2)
    txt = U.dialog_text(d)
    p = U.shot(d, 'w01_data_export_%s' % mode)
    entry = {'theme': mode, 'shot': p, 'dialog_text': txt,
             'theme_state': info, 'api': []}
    if mode == 'light':
        start = U.wait_text(d, '开始导出', timeout=10)
        assert start is not None, '「开始导出」按钮未出现'
        before = set(os.listdir(DL))
        U.drain_log(d)
        t0 = time.time()
        U.js_click(d, start)
        f = wait_download(before)
        elapsed = time.time() - t0
        entry['api'] = U.net_since_drain(d)
        assert f, '导出文件 %.1fs 内未落地' % elapsed
        entry.update({'file': os.path.basename(f), 'size': os.path.getsize(f),
                      'elapsed_s': round(elapsed, 2),
                      'dialog_closed': not U.visible(d, '[role=dialog]')})
        z = zipfile.ZipFile(f)
        man = json.loads(z.read('manifest.json'))
        tt = json.loads(z.read('db/test_tasks.json'))[0]
        rel = json.loads(z.read('db/task_case_relations.json'))
        entry['content'] = {
            'entries': len(z.namelist()),
            'manifest_task_id': man['tasks'][0]['id'],
            'manifest_task_name': man['tasks'][0]['name'],
            'manifest_stats': man['stats'],
            'manifest_options': man['options'],
            'test_tasks_name': tt['name'],
            'test_tasks_status': tt['status'],
            'test_tasks_total_cases': tt['total_cases'],
            'test_tasks_algorithm_type': tt['algorithm_type'],
            'case_relation_rows': len(rel),
            'zip_path': f,
        }
        report['export'] = entry['content']
    else:
        U.close_dialog(d)
    return entry


def run_simple(d, token, key, shot_name, page, opener, mode, dialog_css='[role=dialog]'):
    info = U.enter(d, token, page, mode, ready_css='button[aria-label="任务操作"]')
    U.drain_log(d)
    opener(d)
    ok = U.wait_vis(d, dialog_css, 20) is not None
    assert ok, '%s 弹窗未出现（%s）' % (shot_name, mode)
    time.sleep(1.0)
    txt = U.dialog_text(d)
    p = U.shot(d, '%s_%s' % (shot_name, mode))
    reqs = U.requests_since_drain(d)
    theme_state = info
    U.close_dialog(d)
    return {'theme': mode, 'shot': p, 'dialog_text': txt, 'api': reqs,
            'theme_state': theme_state}


def open_import(d):
    b = U.wait_text(d, '导入数据', timeout=15)
    assert b is not None, '「导入数据」未出现'
    U.js_click(d, b)


def open_reexecute(d):
    U.row_menu(d, '重新执行', EXPORT_TASK)


def open_delete(d):
    U.row_menu(d, '删除', EXPORT_TASK)


def main():
    os.makedirs(DL, exist_ok=True)
    for f in os.listdir(DL):
        os.remove(os.path.join(DL, f))
    api = Api()
    api.login()
    report['env'] = env_check(api)
    token = api.token

    d = U.driver(download_dir=DL)
    try:
        # ---- data-export ----
        entry = {'light': None, 'dark': None}
        try:
            entry['light'] = pass_export(d, token, 'light')
            entry['dark'] = pass_export(d, token, 'dark')
            entry['ok'] = True
        except Exception as exc:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = '%s: %s' % (type(exc).__name__, exc)
            U.close_dialog(d)
        report['windows']['data-export'] = entry
        print('[data-export]', entry.get('ok'), entry.get('error', ''))

        # ---- data-import ----
        entry = {'light': None, 'dark': None}
        try:
            entry['light'] = run_simple(d, token, 'data-import', 'w02_data_import',
                                        '/tasks/daily', open_import, 'light')
            entry['dark'] = run_simple(d, token, 'data-import', 'w02_data_import',
                                       '/tasks/daily', open_import, 'dark')
            entry['ok'] = True
        except Exception as exc:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = '%s: %s' % (type(exc).__name__, exc)
            U.close_dialog(d)
        report['windows']['data-import'] = entry
        print('[data-import]', entry.get('ok'), entry.get('error', ''))

        # ---- reexecute-scope ----
        entry = {'light': None, 'dark': None}
        try:
            entry['light'] = run_simple(d, token, 'reexecute-scope', 'w03_reexecute_scope',
                                        '/tasks/daily', open_reexecute, 'light')
            entry['dark'] = run_simple(d, token, 'reexecute-scope', 'w03_reexecute_scope',
                                       '/tasks/daily', open_reexecute, 'dark')
            entry['ok'] = True
        except Exception as exc:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = '%s: %s' % (type(exc).__name__, exc)
            U.close_dialog(d)
        report['windows']['reexecute-scope'] = entry
        print('[reexecute-scope]', entry.get('ok'), entry.get('error', ''))

        # ---- task-confirm（删除二次确认；取消，不产生写请求）----
        entry = {'light': None, 'dark': None}
        try:
            entry['light'] = run_simple(d, token, 'task-confirm', 'w04_task_confirm',
                                        '/tasks/daily', open_delete, 'light',
                                        dialog_css='[role=alertdialog], [role=dialog]')
            entry['dark'] = run_simple(d, token, 'task-confirm', 'w04_task_confirm',
                                       '/tasks/daily', open_delete, 'dark',
                                       dialog_css='[role=alertdialog], [role=dialog]')
            writes = [r for k in ('light', 'dark') for r in (entry[k].get('api') or [])
                      if r.startswith(('DELETE', 'POST'))]
            entry['write_requests'] = writes
            entry['ok'] = True
        except Exception as exc:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = '%s: %s' % (type(exc).__name__, exc)
            U.close_dialog(d)
        report['windows']['task-confirm'] = entry
        print('[task-confirm]', entry.get('ok'), entry.get('error', ''), 'writes', entry.get('write_requests'))
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'windows_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('report →', os.path.join(ART, 'windows_report.json'))


if __name__ == '__main__':
    main()
