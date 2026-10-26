# -*- coding: utf-8 -*-
"""INT-1819 返工（终审 P1）实测：阶段 2「全部展开」不得触发叶明细并发请求。

被测入口：本 run worktree 的 frontend-react dist 起的旁路容器（nginx:alpine，
--network intelligent-audio-test_default，http://127.0.0.1:15229），
/api → api_gateway（真实库 intelligent_audio_test）。

验证点（对终端代码审计员的三条复测口径）：
  1) 三视图（用例 / 设备 / 结果类型）各点一次「全部展开」→ Network 中
     GET /tasks/cherry-picks/candidates（叶明细）请求数 = 0；
     树骨架（用例卡 / 设备 / result_type 行）仍然展开。
  2) 单击单个叶的父级节点展开 → 叶明细分页请求 = 1（page=1&per_page=20），结果行渲染。
  3) 真实库口径：117 个任务 → total=3614 / task_count=117；浅/深色截图。

用法：python test/../verify_int1819_rework.py   （前置：旁路容器 15229 在线）
"""
import importlib.util
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('INT1497_BASE_URL', 'http://127.0.0.1:15229')
spec = importlib.util.spec_from_file_location(
    'i1497', os.path.join(HERE, 'verify_int1497_cherry_pick.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

By = base.By
BASE = base.BASE
ART = os.path.join(base.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1819_rework')
os.makedirs(ART, exist_ok=True)

LEAF_PATH = '/tasks/cherry-picks/candidates'
TREE_PATH = '/tasks/cherry-picks/candidates/tree'
SELECT_ALL_PATH = '/tasks/cherry-picks/candidates/select-all'


# ---------------------------------------------------------------- Network 取证
def drain(drv):
    """清空 performance 缓冲（只读一次，读即清空）。"""
    drv.get_log('performance')


def capture(drv):
    """按路径分类候选域请求：tree / leaf（candidates 分页）/ select-all。"""
    out = {'tree': [], 'leaf': [], 'select_all': []}
    for raw in drv.get_log('performance'):
        try:
            msg = json.loads(raw['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.requestWillBeSent':
            continue
        req = msg['params']['request']
        url = req.get('url', '')
        if TREE_PATH in url:
            out['tree'].append({'method': req.get('method'), 'url': url})
        elif SELECT_ALL_PATH in url:
            out['select_all'].append({'method': req.get('method'), 'url': url})
        elif LEAF_PATH in url:
            out['leaf'].append({'method': req.get('method'), 'url': url})
    return out


# ---------------------------------------------------------------- 交互
def js_expand_buttons(drv):
    return drv.execute_script(
        "return [...document.querySelectorAll(\"button[aria-label='展开']\")]"
        ".filter(e=>e.offsetParent!==null).length"
    )


def js_click_expand(drv, idx=0):
    """点按文档顺序第 idx 个可见「展开」按钮（骨架行 / 用例卡共用）。"""
    ok = drv.execute_script(
        """
        const els=[...document.querySelectorAll("button[aria-label='展开']")]
          .filter(e=>e.offsetParent!==null);
        if(!els[arguments[0]]) return false;
        els[arguments[0]].scrollIntoView({block:'center'});
        els[arguments[0]].click();
        return true;
        """,
        idx,
    )
    if not ok:
        raise AssertionError(f'第 {idx} 个「展开」按钮不可点')
    time.sleep(1.2)


def enter_stage2(drv, select_all_tasks=True):
    """开始挑选 → 阶段 1（默认全量 117 个任务）→ 下一步 → 阶段 2。"""
    drv.get(BASE + '/tasks/cherry-picks')
    base.wait_text(drv, '开始挑选', timeout=90)
    base.click_button_text(drv, '开始挑选', timeout=30)
    base.wait_text(drv, '阶段 1：选择任务', timeout=90)
    if select_all_tasks:
        base.click_button_text(drv, '全选当前筛选', timeout=60)
        time.sleep(1.0)
    base.click_button_text(drv, '下一步：选择结果', timeout=60)
    base.wait_text(drv, '阶段 2：选择结果', timeout=90)
    # 全量树：117 任务 / 3614 结果（真实库口径）
    end = time.time() + 180
    while time.time() < end:
        txt = base.body_text(drv)
        if '共 3614 条结果' in txt and '117 个任务' in txt:
            return txt
        if '候选加载失败' in txt:
            raise AssertionError('候选树加载失败')
        time.sleep(0.5)
    raise AssertionError(f'全量树未就绪：{base.body_text(drv)[:300]}')


def switch_view(drv, label):
    base.click_button_text(drv, label, timeout=30)
    time.sleep(2.0)


def has_leaf_row(drv):
    return drv.execute_script(
        "return document.querySelectorAll(\"[data-testid^='pick-leaf-']\").length"
    )


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('  screenshot:', path)
    return path


def case_card_count(drv):
    """已展开的用例卡（aria-label=收起 的卡片展开钮）——骨架展开的证据。"""
    return drv.execute_script(
        "return [...document.querySelectorAll(\"button[aria-label='收起']\")]"
        ".filter(e=>e.offsetParent!==null).length"
    )


def network_html(rows, path):
    body = '\n'.join(
        '<tr><td>%s</td><td><code>%s</code></td><td><code>%s</code></td></tr>'
        % (r[0], r[1], r[2])
        for r in rows
    )
    html = """<!doctype html><html><head><meta charset="utf-8">
<style>body{font:13px/1.6 system-ui;margin:24px;color:#111}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 10px;vertical-align:top}
code{font-size:11px;word-break:break-all}h1{font-size:18px}</style></head><body>
<h1>INT-1819 返工 · Network 取证（阶段 2 候选域请求分类）</h1>
<p>被测：http://127.0.0.1:15229（本 run dist 旁路容器）· 真实库 intelligent_audio_test ·
阶段 1 全选 117 任务 · 树 total=3614</p>
<table><tr><th>操作</th><th>请求类别</th><th>次数 / 证据</th></tr>%s</table>
<p>叶明细 = GET /api/v1/tasks/cherry-picks/candidates?task_ids=…&amp;page=1&amp;per_page=20</p>
</body></html>""" % body
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def main():
    print('被测入口:', BASE, '| 产物目录:', ART)
    import urllib.request
    with urllib.request.urlopen(BASE + '/health', timeout=15) as r:
        health = json.loads(r.read().decode())
    assert health.get('database') == 'intelligent_audio_test', f'后端库不符: {health}'
    print('health:', health)

    evidence = []
    results = []
    drv = base.make_driver()
    try:
        # ---------- 阶段 2 首屏（真实库口径）
        txt = enter_stage2(drv, select_all_tasks=True)
        assert '共 3614 条结果' in txt and '117 个任务' in txt, '全量树口径不符'
        results.append('阶段 2 全量树 total=3614 / task_count=117（阶段 1 全选 117 任务）')
        shot(drv, '01_stage2_tree_light')

        drain(drv)  # 丢弃首屏（tree 请求）噪声

        # ---------- ② 单节点展开 = 1 条叶明细
        n_expand = js_expand_buttons(drv)
        assert n_expand > 0, '用例卡展开钮缺失'
        js_click_expand(drv, 0)          # 打开第一张用例卡
        js_click_expand(drv, 0)          # 打开卡内设备行
        before_leaf = has_leaf_row(drv)
        js_click_expand(drv, 0)          # 打开 result_type（叶的父级）→ 按需分页
        end = time.time() + 30
        while time.time() < end and has_leaf_row(drv) == 0:
            time.sleep(0.4)
        leaf_rows = has_leaf_row(drv)
        cap = capture(drv)
        assert len(cap['leaf']) == 1, f"单节点展开叶明细请求数应为 1，实际 {len(cap['leaf'])}: {cap['leaf']}"
        assert 'per_page=20' in cap['leaf'][0]['url'], '叶分页参数不是 20'
        assert leaf_rows > 0, f'单节点展开后无结果行（{before_leaf} → {leaf_rows}）'
        rows_dom = base.body_text(drv)
        results.append(
            '单节点展开（用例卡→设备→结果类型）：叶明细请求 1 条（page=1&per_page=20），'
            f'结果行渲染 {leaf_rows} 行'
        )
        evidence.append(('单节点展开 result_type 叶父级', 'candidates 叶明细分页', '1 次', ))
        shot(drv, '02_single_leaf_expand')

        # ---------- ① 用例视图「全部展开」= 0 条叶明细
        base.click_button_text(drv, '全部收起', timeout=30)
        time.sleep(1.0)
        drain(drv)
        base.click_button_text(drv, '全部展开', timeout=30)
        time.sleep(12)  # 1057 张用例卡 + 骨架行渲染
        cap = capture(drv)
        cards = case_card_count(drv)
        assert len(cap['leaf']) == 0, f"用例视图「全部展开」叶请求应为 0，实际 {len(cap['leaf'])}"
        assert len(cap['tree']) == 0, '「全部展开」不应重取树'
        assert cards > 0, '「全部展开」未展开任何骨架节点'
        results.append(
            f'用例视图「全部展开」：叶明细请求 0（骨架已展开 {cards} 个节点，不重取 tree）'
        )
        evidence.append(('用例视图 全部展开', 'candidates 叶明细分页', '0 次', ))
        shot(drv, '03_case_view_expand_all')

        # ---------- ① 设备视图「全部展开」= 0
        switch_view(drv, '设备视图')
        base.click_button_text(drv, '全部收起', timeout=30)
        time.sleep(1.0)
        drain(drv)
        base.click_button_text(drv, '全部展开', timeout=30)
        time.sleep(12)
        cap = capture(drv)
        assert len(cap['leaf']) == 0, f"设备视图「全部展开」叶请求应为 0，实际 {len(cap['leaf'])}"
        results.append('设备视图「全部展开」：叶明细请求 0（设备/result_type 骨架展开）')
        evidence.append(('设备视图 全部展开', 'candidates 叶明细分页', '0 次', ))
        shot(drv, '04_device_view_expand_all')

        # ---------- ① 结果类型视图「全部展开」= 0
        switch_view(drv, '结果类型视图')
        base.click_button_text(drv, '全部收起', timeout=30)
        time.sleep(1.0)
        drain(drv)
        base.click_button_text(drv, '全部展开', timeout=30)
        time.sleep(12)
        cap = capture(drv)
        assert len(cap['leaf']) == 0, f"结果类型视图「全部展开」叶请求应为 0，实际 {len(cap['leaf'])}"
        results.append('结果类型视图「全部展开」：叶明细请求 0（result_type/设备骨架展开）')
        evidence.append(('结果类型视图 全部展开', 'candidates 叶明细分页', '0 次', ))
        shot(drv, '05_resulttype_view_expand_all')

        # ---------- 叶明细仍可按需扩展：设备视图下单击用例卡 = 1
        drain(drv)
        js_click_expand(drv, 0)  # 设备视图：第一张用例卡（叶父级）
        end = time.time() + 30
        while time.time() < end and has_leaf_row(drv) == 0:
            time.sleep(0.4)
        cap = capture(drv)
        assert len(cap['leaf']) == 1, f"设备视图单击用例卡叶请求应为 1，实际 {len(cap['leaf'])}"
        assert has_leaf_row(drv) > 0, '设备视图单击用例卡后无结果行'
        results.append('设备视图单击单个用例卡：叶明细请求 1 条、结果行渲染（按需分页未退化）')
        evidence.append(('设备视图 单击用例卡', 'candidates 叶明细分页', '1 次', ))
        shot(drv, '06_device_single_card_expand')

        # ---------- 深色（阶段 2 树 + 全部展开）
        base.set_theme(drv, 'dark')
        enter_stage2(drv, select_all_tasks=True)
        drain(drv)
        base.click_button_text(drv, '全部展开', timeout=30)
        time.sleep(12)
        cap = capture(drv)
        assert len(cap['leaf']) == 0, f"深色「全部展开」叶请求应为 0，实际 {len(cap['leaf'])}"
        shot(drv, '07_stage2_tree_dark_expand_all')
        results.append('深色主题阶段 2「全部展开」同样 0 条叶明细请求')
        evidence.append(('深色 用例视图 全部展开', 'candidates 叶明细分页', '0 次', ))

        # ---------- Network 取证页（截图）
        net_rows = []
        for label, cls, count in evidence:
            net_rows.append((label, cls, count))
        net_html = network_html(net_rows, os.path.join(ART, 'network_evidence.html'))
        drv.get('file:///' + net_html.replace('\\', '/'))
        time.sleep(0.6)
        shot(drv, '08_network_evidence')

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump({'base': BASE, 'health': health, 'results': results,
                       'evidence': evidence}, f, ensure_ascii=False, indent=2)
        print('\n'.join('✅ ' + r for r in results))
        print('SUMMARY_OK')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
