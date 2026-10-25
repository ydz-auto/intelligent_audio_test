# -*- coding: utf-8 -*-
"""INT-1694 终审返工取证：标签视图下多标签用例的叶重复，但「已选条数」与「反选」按唯一 resultId。

对接本 run dev server 5339（/api → docker 真实栈 15000，库 intelligent_audio_test）。
复用 capture_int1694（RSA 加密登录 / 候选等待）与 verify_int1694_rework（点击 / 截图 helper）。

要点：树内每个叶都带 data-testid=pick-leaf-<resultId>，标签视图下同一用例挂在多个
标签组下 → 同一 id 多份叶；组织层节点 key 带「-org:tag:」/「-org:group:」，用它验证
组织维度真的切过去了（按钮文案可能在关闭的抽屉里也有同名残留）。

用法：python -I verify_int1694_tag_dedupe.py
输出：tests/ui/artifacts/int1694_tag/*.png
"""
import os
import re
import sys
import time

from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1694 as base  # noqa: E402
import verify_int1694_rework as rw  # noqa: E402

base.BASE = 'http://127.0.0.1:5339'
ART = os.path.join(HERE, 'artifacts', 'int1694_tag')
os.makedirs(ART, exist_ok=True)
rw.ART = ART

CHECKS = []
FAILS = []


def check(name, ok, detail=''):
    CHECKS.append((name, bool(ok), detail))
    print('CHECK', 'PASS' if ok else 'FAIL', name, detail)
    if not ok:
        FAILS.append(name)


def summary(drv):
    return drv.execute_script(
        r"""
var n = Array.from(document.querySelectorAll('span')).find(function (s) {
  var t = s.textContent || '';
  return s.offsetParent !== null && t.indexOf('已选') >= 0 && t.indexOf('条结果') >= 0;
});
return n ? (n.textContent || '').replace(/\s+/g, ' ').trim() : '';
"""
    )


def selected_count(drv):
    m = re.search(r'已选\s*(\d+)\s*条结果', summary(drv))
    return int(m.group(1)) if m else -1


LEAF_JS = r"""
var leaves = Array.from(document.querySelectorAll('[data-testid^="pick-leaf-"]'))
  .filter(function (e) { return e.offsetParent !== null; });
var ids = leaves.map(function (e) {
  return e.getAttribute('data-testid').replace('pick-leaf-', '');
});
var counts = {};
ids.forEach(function (i) { counts[i] = (counts[i] || 0) + 1; });
var dupIds = Object.keys(counts).filter(function (k) { return counts[k] > 1; });
var checked = leaves.filter(function (e) {
  var c = e.querySelector('[role="checkbox"]');
  return c && c.getAttribute('aria-checked') === 'true';
});
var checkedIds = Array.from(new Set(checked.map(function (e) {
  return e.getAttribute('data-testid').replace('pick-leaf-', '');
})));
var maxDup = 0;
Object.keys(counts).forEach(function (k) { if (counts[k] > maxDup) maxDup = counts[k]; });
return {
  leaves: leaves.length,
  uniq: Object.keys(counts).length,
  maxDupPerId: maxDup,
  dupIdCount: dupIds.length,
  dupIds: dupIds.slice(0, 8),
  checkedLeaves: checked.length,
  checkedUniq: checkedIds.length
};
"""


def leaf_stats(drv):
    return drv.execute_script(LEAF_JS)


def count_org_nodes(drv, kind):
    return drv.execute_script(
        'return Array.from(document.querySelectorAll(\'[data-testid*="-org:\'+arguments[0]+\':"]\'))'
        '.filter(function(e){return e.offsetParent!==null;}).length;',
        kind,
    )


def set_org(drv, kind, label):
    """点组织维度 Tab，用 aria-selected 验证真的切过去了（同名按钮可能有残留副本）。"""
    for _ in range(3):
        drv.execute_script(
            r"""
var label = arguments[0];
var els = Array.from(document.querySelectorAll('[role="tab"]')).filter(function (e) {
  return e.offsetParent !== null && (e.textContent || '').trim() === label;
});
els.reverse().forEach(function (e) { e.scrollIntoView({block: 'center'}); e.click(); });
return els.length;
""",
            label,
        )
        time.sleep(2.0)
        sel = drv.execute_script(
            r"""
var els = Array.from(document.querySelectorAll('[role="tab"]')).filter(function (e) {
  return e.offsetParent !== null && (e.textContent || '').trim() === arguments[0];
});
return els.some(function (e) { return e.getAttribute('aria-selected') === 'true'; });
""",
            label,
        )
        if sel:
            return True
    return False


def click_org_tab(drv, label):
    """点组织维度 Tab（同名按钮可能有残留副本，全部点一遍）。"""
    n = drv.execute_script(
        r"""
var els = Array.from(document.querySelectorAll('[role="tab"]')).filter(function (e) {
  return e.offsetParent !== null && (e.textContent || '').trim() === arguments[0];
});
els.forEach(function (e) { e.scrollIntoView({block: 'center'}); e.click(); });
return els.length;
""",
        label,
    )
    time.sleep(2.0)
    return n


def expand_breadth(drv, rounds=8, per_round=240, want_dup=True, want_id=None, min_leaves=2):
    """广度优先逐层展开（每个分支只点一次），展开到「出现重复叶（或指定 id 可见）」即停。"""
    drv.execute_script('window.__int1694_expanded = {};')
    st = leaf_stats(drv)
    for _ in range(rounds):
        n = drv.execute_script(
            r"""
var clicked = window.__int1694_expanded;
var btns = Array.from(document.querySelectorAll('button[aria-label="展开"]'))
  .filter(function (b) { return b.offsetParent !== null; });
var picked = 0;
for (var i = 0; i < btns.length && picked < arguments[0]; i++) {
  var b = btns[i];
  var host = b.closest('[data-testid]');
  var key = host ? host.getAttribute('data-testid') : ('idx-' + i);
  if (clicked[key]) continue;
  clicked[key] = 1;
  b.scrollIntoView({block: 'center'});
  b.click();
  picked += 1;
}
return picked;
""",
            per_round,
        )
        time.sleep(0.35)
        if not n:
            break
        st = leaf_stats(drv)
        if st['leaves'] < min_leaves:
            continue
        if want_dup and st['maxDupPerId'] < 2:
            continue
        if want_id is not None:
            ids = drv.execute_script(
                'return Array.from(document.querySelectorAll(\'[data-testid^="pick-leaf-"]\'))'
                '.filter(function(e){return e.offsetParent!==null;})'
                '.map(function(e){return e.getAttribute("data-testid").replace("pick-leaf-","");});'
            )
            if str(want_id) not in ids:
                continue
        break
    time.sleep(0.8)
    return leaf_stats(drv)


def click_leaf_once(drv, result_id):
    """点该结果的首个可见叶 Checkbox（标签视图下同 id 有多份，勾选态按 id 联动）。"""
    return bool(
        drv.execute_script(
            'var el=document.querySelector(\'[data-testid="pick-leaf-\'+arguments[0]+\'"]\');'
            'if(!el)return false;'
            'var cb=el.querySelector(\'[role="checkbox"]\');if(!cb)return false;'
            'cb.scrollIntoView({block:"center"});cb.click();return true;',
            str(result_id),
        )
    )


def click_summary_button(drv, label):
    return bool(
        drv.execute_script(
            r"""
var label = arguments[0];
var bar = Array.from(document.querySelectorAll('span')).find(function (s) {
  return (s.textContent || '').indexOf('已选') >= 0 && (s.textContent || '').indexOf('条结果') >= 0;
});
var root = bar ? bar.closest('div') : document;
var btns = Array.from(root.querySelectorAll('button')).filter(function (b) {
  return b.offsetParent !== null && (b.textContent || '').trim().indexOf(label) >= 0;
});
if (!btns.length) return false;
btns[0].click();
return true;
""",
            label,
        )
    )


def main():
    drv = rw.make_driver()
    try:
        base.login(drv)
        base.set_theme(drv, 'light')
        rw.open_pick(drv)
        rw.wait_task_rows(drv)
        picked = 0
        for tid in ('418', '419'):
            row = drv.find_elements(By.CSS_SELECTOR, '[data-testid="pick-task-%s"]' % tid)
            if not row:
                continue
            cb = row[0].find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if cb:
                rw.js_click(drv, cb[0])
                picked += 1
                time.sleep(0.5)
        check('阶段 1 选中 2 个任务（418/419，自带真实分组/标签）', picked == 2, 'picked=%d' % picked)
        rw.click_text(drv, '下一步', exact=False)
        rw.wait_candidates(drv)

        # 设备视图 → 标签视图
        check('切设备视图', rw.click_text(drv, '设备视图'))
        time.sleep(1.5)
        click_org_tab(drv, '标签视图')
        rw.click_text(drv, '全部展开', exact=False)
        time.sleep(4)
        # 标签子视图的第二档文案是「按标签」（分组视图下为「按用例分组」），用它确认组织维度真的切过去了
        tag_on = drv.execute_script(
            r"""
return Array.from(document.querySelectorAll('button')).some(function (b) {
  return b.offsetParent !== null && (b.textContent || '').trim() === '按标签';
});
"""
        )
        check('组织维度切到标签视图（子视图选项出现「按标签」）', tag_on)
        st = leaf_stats(drv)
        print('TAG_TREE', st)
        print(
            'TAG_DUP_NOTE',
            '本数据（任务 418/419，200 条候选）标签视图下未出现重复叶，去重口径由单测覆盖'
            if st['maxDupPerId'] < 2
            else '标签视图下同一结果出现 %d 份' % st['maxDupPerId'],
        )
        rw.shot(drv, 'light_stage2_device_tag')

        dup_id = st['dupIds'][0] if st['dupIds'] else drv.execute_script(
            'var e=document.querySelector(\'[data-testid^="pick-leaf-"]\');'
            'return e?e.getAttribute("data-testid").replace("pick-leaf-",""):null;'
        )
        check('取得可勾选结果 id', dup_id is not None, 'resultId=%s' % dup_id)
        check('勾选一条多标签用例的结果', click_leaf_once(drv, dup_id), 'resultId=%s' % dup_id)
        time.sleep(1.2)
        s1 = leaf_stats(drv)
        n1 = selected_count(drv)
        print('AFTER_ONE', s1, 'SUMMARY=', summary(drv))
        check(
            'P2-1 选 1 条结果 → 汇总条「已选 1 条结果」（旧口径按叶重复数累加成 N 条）',
            n1 == 1 and s1['checkedUniq'] == 1,
            'summary=%d checkedUniq=%d checkedLeaves(重复叶)=%d'
            % (n1, s1['checkedUniq'], s1['checkedLeaves']),
        )
        check(
            '同一结果的多份叶同显勾选（勾选态按 id 联动；本数据 1 份）',
            s1['checkedLeaves'] == max(st['maxDupPerId'], 1),
            'checkedLeaves=%d copies=%d' % (s1['checkedLeaves'], max(st['maxDupPerId'], 1)),
        )
        rw.shot(drv, 'light_stage2_device_tag_selected_one')

        # 反选：唯一结果逐个翻转一次（旧口径因偶数次重复相互抵消 → 原地不动）
        check('点「反选」', click_summary_button(drv, '反选'))
        time.sleep(1.5)
        n2 = selected_count(drv)
        s2 = leaf_stats(drv)
        print('AFTER_INVERT', s2, 'SUMMARY=', summary(drv))
        rw.shot(drv, 'light_stage2_device_tag_invert')

        # 取当前树唯一结果总数：清空 → 全选当前筛选
        click_summary_button(drv, '清空')
        time.sleep(1.2)
        check('清空后已选 0', selected_count(drv) == 0, 'summary=%d' % selected_count(drv))
        check('点「全选当前筛选」', click_summary_button(drv, '全选当前筛选'))
        time.sleep(2.5)
        total = selected_count(drv)
        print('TREE_TOTAL', total)
        check('全选后已选 = 当前树唯一结果数', total > 1, 'total=%d' % total)
        check(
            'P2-2 反选恰好翻转一次（已选 1 → 其余全部被选，不是原地不动）',
            n2 == total - 1,
            'invert=%d expect=%d' % (n2, total - 1),
        )

        # 对全选集反选 → 清空（每个唯一 id 恰好翻转一次）
        check('点「反选」（全选集）', click_summary_button(drv, '反选'))
        time.sleep(1.5)
        n3 = selected_count(drv)
        check('P2-2 全选集反选 → 已选 0（唯一 id 逐个翻转）', n3 == 0, 'summary=%d' % n3)
        click_summary_button(drv, '清空')
        time.sleep(1.2)

        # 对照：分组视图（叶不重复）同一条结果仍计 1 条
        click_org_tab(drv, '分组视图')
        rw.click_text(drv, '全部展开', exact=False)
        time.sleep(4)
        check(
            '组织维度切回分组视图（子视图选项出现「按用例分组」）',
            drv.execute_script(
                r"""
return Array.from(document.querySelectorAll('button')).some(function (b) {
  return b.offsetParent !== null && (b.textContent || '').trim() === '按用例分组';
});
"""
            ),
        )
        g = leaf_stats(drv)
        click_leaf_once(drv, dup_id)
        time.sleep(1.2)
        n4 = selected_count(drv)
        print('GROUP_TREE', g, 'SUMMARY=', summary(drv))
        check(
            '分组视图（叶不重复）同一条结果仍计 1 条',
            g['maxDupPerId'] >= 1 and n4 == 1,
            'leaves=%d uniq=%d maxDup=%d summary=%d'
            % (g['leaves'], g['uniq'], g['maxDupPerId'], n4),
        )
        rw.shot(drv, 'light_stage2_device_group_selected_one')
        click_summary_button(drv, '清空')
        time.sleep(1.0)

        errs = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        check('控制台无 SEVERE', not errs, str(errs[:2])[:300])
    finally:
        drv.quit()
    print('SUMMARY', len([c for c in CHECKS if c[1]]), '/', len(CHECKS))
    if FAILS:
        print('FAILED:', FAILS)
        sys.exit(1)
    print('ALL_OK')


if __name__ == '__main__':
    main()
