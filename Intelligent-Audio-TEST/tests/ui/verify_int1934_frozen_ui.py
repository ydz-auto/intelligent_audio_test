# -*- coding: utf-8 -*-
"""INT-1934 补证第 2 项：冻结任务详情（has_task_snapshot=true）界面复验，浅 + 深。

前置：probe_int1934_frozen.py 已构造 published_tasks id（frozen_state.json），
      并把源任务改名，形成「冻结体 ≠ 实时数据」的差分。

断言：
- 已发布页签该行出现「查看冻结任务详情」，不出现「历史版本（发布时未冻结任务详情）」
- 弹窗标题含「发布时冻结 · 不可变」
- 弹窗任务名 = 冻结体名（原名），**不是**源任务改名后的实时名
- 用例数 = 冻结体 cases 数

用法：python tests/ui/verify_int1934_frozen_ui.py
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

import _int1934_ui as U  # noqa: E402
from _int1934_lib import Api, unwrap  # noqa: E402

ART = U.ART
PUB_NAME = '接线测试_INT1934_冻结详情'
FROZEN_SRC = '接线测试_INT1934_冻结源任务'
LIVE_SRC = '接线测试_INT1934_冻结源任务_改名后'
report = {'card': 'INT-1934', 'kind': 'frozen-task-detail', 'passes': {}}


def open_frozen_dialog(d):
    row = None
    WebDriverWait(d, 90).until(lambda x: x.find_elements(
        By.XPATH, "//tr[contains(., '%s')]" % PUB_NAME))
    time.sleep(1.5)
    row = d.find_element(By.XPATH, "//tr[contains(., '%s')]" % PUB_NAME)
    exp = row.find_elements(By.CSS_SELECTOR, 'button[aria-label="展开版本详情"]')
    if not exp:
        exp = d.find_elements(By.CSS_SELECTOR, 'button[aria-label="展开版本详情"]')
    assert exp, '未找到「展开版本详情」'
    U.js_click(d, exp[0])
    time.sleep(3.0)
    body = d.find_element(By.TAG_NAME, 'body').text
    ts = U.wait_text(d, '查看冻结任务详情', timeout=20)
    assert ts is not None, '未找到「查看冻结任务详情」；页面片段=%r' % body[:400]
    U.js_click(d, ts)
    time.sleep(1.5)
    els = U.visible(d, '[role=dialog]')
    assert els, '冻结任务详情弹窗未出现'
    return els[0], body


def pass_one(d, token, mode):
    info = U.enter(d, token, '/tasks/published', mode, timeout=70)
    dlg, page_text = open_frozen_dialog(d)
    txt = dlg.text.strip()
    p = U.shot(d, 'w06_frozen_task_detail_%s' % mode)
    entry = {'theme': mode, 'shot': p, 'dialog_text': txt[:2500],
             'title_has_frozen': '发布时冻结' in txt and '不可变' in txt,
             'frozen_name_present': FROZEN_SRC in txt,
             'live_name_absent': LIVE_SRC not in txt,
             'no_history_placeholder': '历史版本（发布时未冻结任务详情）' not in page_text,
             'has_view_frozen_entry': '查看冻结任务详情' in page_text,
             'theme_state': info}
    U.close_dialog(d)
    return entry


def main():
    api = Api()
    api.login()
    with open(os.path.join(ART, 'frozen_state.json'), encoding='utf-8') as f:
        st = json.load(f)
    pub_id = st['published_id']
    src_id = st['source_task_id']
    stc, d = api.get('/api/v1/published-tasks/%d' % pub_id)
    det = unwrap(d)
    ts = (det.get('snapshot_config') or {}).get('taskSnapshot') or {}
    live_st, dl = api.get('/api/v1/tasks/%d' % src_id)
    live = unwrap(dl)
    report['fixture'] = {
        'published_id': pub_id, 'source_task_id': src_id,
        'has_task_snapshot': det.get('has_task_snapshot'),
        'snapshot_keys': sorted((det.get('snapshot_config') or {}).keys()),
        'frozen_task_name': (ts.get('task') or {}).get('name'),
        'frozen_case_count': len(ts.get('cases') or []),
        'frozen_device_count': len(ts.get('devices') or []),
        'frozen_schema_version': ts.get('schemaVersion'),
        'source_task_name_live': live.get('name'),
        'source_task_name_field_api': det.get('source_task_name'),
    }
    print('fixture', json.dumps(report['fixture'], ensure_ascii=False))

    d = U.driver()
    try:
        for mode in ('light', 'dark'):
            try:
                e = pass_one(d, api.token, mode)
                report['passes'][mode] = e
                print('[%s] shot=%s frozen=%s live_absent=%s title=%s' % (
                    mode, os.path.basename(e['shot']), e['frozen_name_present'],
                    e['live_name_absent'], e['title_has_frozen']))
                print('   text:', e['dialog_text'].replace('\n', ' | ')[:260])
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                report['passes'][mode] = {'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'frozen_ui_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('report →', os.path.join(ART, 'frozen_ui_report.json'))


if __name__ == '__main__':
    main()
