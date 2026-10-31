# -*- coding: utf-8 -*-
"""INT-2173 走查·C：挑选合并树节点状态汇总 / 叶行去重 / 全部展开计数。"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2173')
os.makedirs(ART, exist_ok=True)
RESULTS = []
CTX = {}
TASK_ID = 789
TASK_NAME = '测试任务_2026-10-31 09:08'


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1200]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))
    return ok


def body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text or ''


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def tree_summary(task_id):
    token, _ = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    st, d = B.api('/api/v1/tasks/cherry-picks/candidates/tree?task_ids=%d' % task_id, token)
    data = d.get('data') or d
    tree = data.get('tree') or []
    return token, data, (tree[0] if tree else None)


def main():
    token, data, node = tree_summary(TASK_ID)
    CTX['tree_api'] = node
    check('C 段核对候选树接口返回节点', node is not None and node.get('task_id') == TASK_ID, data.get('total'))

    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, None)
        B.goto(drv, '/tasks/cherry-picks', timeout=120)
        time.sleep(3)
        B.click_button_text(drv, '开始挑选', exact=True, timeout=30)
        time.sleep(4)
        # 勾选目标任务
        picked = drv.execute_script("""
          const name = arguments[0];
          for (const cb of document.querySelectorAll('[role=checkbox], input[type=checkbox]')) {
            const label = cb.getAttribute('aria-label') || '';
            if (label === '选择任务 ' + name) { cb.click(); return label; }
          }
          return null;
        """, TASK_NAME)
        check('挑选阶段1：勾选目标任务 %s' % TASK_NAME, picked is not None, {'picked': picked, 'tail': body(drv)[-200:]})
        time.sleep(1)
        drv.execute_script("""
          const b = [...document.querySelectorAll('button')].find(x => (x.textContent||'').includes('下一步'));
          b && b.click();
        """)
        time.sleep(5)
        txt = body(drv)
        check('挑选阶段2：候选树已渲染（任务视图 + 用例节点）',
              '选择结果' in txt and ('任务视图' in txt or '分组视图' in txt), txt[-300:])
        shot(drv, 'C01_pick_tree_light')

        # 全部展开后按叶子父节点（result_type 行）读取状态汇总
        expanded = drv.execute_script("""
          for (const b of document.querySelectorAll('button')) {
            if ((b.textContent||'').trim() === '全部展开') { b.click(); return true; }
          }
          return false;
        """)
        time.sleep(4)
        rows = drv.execute_script("""
          return [...document.querySelectorAll('[data-testid^="pick-branch-"]')].map(e => ({
            id: e.getAttribute('data-testid'),
            text: (e.textContent||'').trim().replace(/\s+/g, ' ')
          }));
        """)
        leaf_rows = [r for r in rows if r['id'].startswith('pick-branch-') and '-resultType:' in r['id']]
        CTX['leaf_rows'] = leaf_rows
        counts = (node or {}).get('execution_status_counts') or {}
        completed = counts.get('completed', 0)
        failed = counts.get('failed', 0)
        total = (node or {}).get('count', 0)
        evaluated = (node or {}).get('evaluated_count', 0)
        pending = total - evaluated
        check('挑选树：全部展开按钮生效并渲染全部结果节点', expanded and len(leaf_rows) == total,
              {'expanded': expanded, 'leaf_rows': len(leaf_rows), 'tree_total': total, 'rows': [r['text'][:80] for r in leaf_rows[:4]]})
        joined = ' || '.join(r['text'] for r in leaf_rows)
        ui_completed = joined.count('已完成')
        ui_failed = joined.count('执行失败')
        ui_eval = joined.count('待评估')
        ui_time = len([r for r in leaf_rows if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', r['text'])])
        check('挑选树节点行直出执行状态（UI 已完成=%d/执行失败=%d；接口 %d/%d）' % (ui_completed, ui_failed, completed, failed),
              ui_completed == completed and ui_failed == failed,
              {'ui': [ui_completed, ui_failed], 'api': counts})
        check('挑选树节点行直出评估数（UI 待评估=%d；接口 pending=%d）' % (ui_eval, pending),
              ui_eval == pending, {'ui_eval': ui_eval, 'pending': pending, 'evaluated': evaluated})
        check('挑选树节点行直出末条结果时间（%d/%d 行带时间）' % (ui_time, len(leaf_rows)),
              ui_time == len(leaf_rows), {'rows': [r['text'] for r in leaf_rows[:2]]})
        # 叶行去重：结果节点 count 之和 = 接口 total；接口 result_ids 去重数一致
        sum_counts = 0
        for r in leaf_rows:
            m2 = re.findall(r'(\d+) 条', r['text'])
            if m2:
                sum_counts += int(m2[-1])
        all_ids = []

        def walk(n):
            for rt in (n.get('result_types') or []):
                all_ids.extend(rt.get('result_ids') or [])
            for c in (n.get('cases') or []):
                for dv in (c.get('devices') or []):
                    walk(dv)
        for c in (node.get('cases') or []):
            for dv in (c.get('devices') or []):
                walk(dv)
        check('挑选叶行：结果节点计数之和 = 接口 total（%d），接口 result_ids 无重复' % total,
              sum_counts == total and len(all_ids) == total and len(set(all_ids)) == total,
              {'sum_counts': sum_counts, 'api_ids': len(all_ids), 'api_unique': len(set(all_ids))})
        ui_leaf_rows = drv.execute_script("return [...document.querySelectorAll('[data-testid^=\"pick-leaf-\"]')].map(e=>e.getAttribute('data-testid'))")
        CTX['ui_leaf_rows'] = ui_leaf_rows
        check('挑选叶行：无重复结果行（data-testid resultId 唯一；本数据每叶父 count=1 不展开，按设计直出汇总）',
              len(ui_leaf_rows) == len(set(ui_leaf_rows)),
              {'ui_leaf_count': len(ui_leaf_rows), 'note': 'count=1 节点 expandable=false（pick-tree.tsx:173）'})
        shot(drv, 'C02_pick_tree_expanded')

        # 三方一致：详情页同节点 targets 状态计数
        st, td = B.api('/api/v1/tasks/%d' % TASK_ID, token)
        d = td.get('data') or {}
        det_counts = {}
        det_targets = 0
        for c in (d.get('cases') or []):
            for t in (c.get('targets') or []):
                det_targets += 1
                det_counts[t.get('execution_status')] = det_counts.get(t.get('execution_status'), 0) + 1
        check('三方一致：详情 targets 状态计数 = 候选树节点 execution_status_counts',
              det_counts.get('completed', 0) == completed and det_counts.get('failed', 0) == failed,
              {'detail': det_counts, 'tree': counts})
        check('三方一致：详情 targets 行数 = 候选树 total（结果行数；detail.total_cases 是去重用例数）',
              det_targets == total, {'detail_targets': det_targets, 'tree_total': total, 'detail_total_cases': d.get('total_cases')})

        # 深色：重新进入并截图（选择后切主题会 reload，重走一遍）
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(6)
        B.goto(drv, '/tasks/cherry-picks', timeout=120)
        time.sleep(3)
        B.click_button_text(drv, '开始挑选', exact=True, timeout=30)
        time.sleep(4)
        drv.execute_script("""
          const name = arguments[0];
          for (const cb of document.querySelectorAll('[role=checkbox], input[type=checkbox]')) {
            if ((cb.getAttribute('aria-label') || '') === '选择任务 ' + name) { cb.click(); return true; }
          }
          return false;
        """, TASK_NAME)
        time.sleep(1)
        drv.execute_script("const b=[...document.querySelectorAll('button')].find(x=>(x.textContent||'').includes('下一步')); b&&b.click();")
        time.sleep(5)
        dark = drv.execute_script('return document.documentElement.className')
        check('挑选树深色截图已取（dark 生效）', 'dark' in (dark or ''), dark)
        shot(drv, 'C03_pick_tree_dark')
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light'); location.reload();")
    finally:
        drv.quit()

    failed = [r for r in RESULTS if not r['ok']]
    print('\n==== C: %d checks, %d failed ====' % (len(RESULTS), len(failed)))
    with open(os.path.join(ART, 'evidence_C.json'), 'w', encoding='utf-8') as f:
        json.dump({'checks': RESULTS, 'ctx': CTX}, f, ensure_ascii=False, indent=1)
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:200])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
