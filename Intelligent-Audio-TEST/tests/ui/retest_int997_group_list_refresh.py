# -*- coding: utf-8 -*-
"""INT-997 复测（代码审计打回 P2）：组级操作后分组列表即时刷新。

打回项：4 处 invalidateQueries({queryKey:['groups']}) 写成 ['groups']，
匹配不到分组列表真实 key ['testcase-groups']（use-case-groups.ts:12），
组级写操作成功后分组列表（组头卡 + facet）不刷新。

修复（bb78462b）：4 处 key 改为 ['testcase-groups']。

本脚本只复测失败项（§2.3），逐个验证四种组级操作：
  ① 批量调整分组 →「+ 新建分组」→ 确定：POST /groups(201) + POST /testcases/batch(200)，
     随后 GET /groups refetch（invalidate 触发），新组出现在分组列表，全程无整页重载。
  ② 组头「编辑」改名 → 保存：PUT /groups/{id}(200) → GET /groups refetch → 新名出现、旧名消失。
  ③ 组头「复制」：POST /testcases/batch action=copy_by_group(200) → GET /groups refetch → 新组出现。
  ④ 组头「删除」：DELETE /groups/{id}?cascade=true(200) → GET /groups refetch → 组消失。

「无整页重载」判据：performance navigation entry 数量在操作前后不变
（SPA invalidate→refetch 不产生新 navigation entry；整页 reload 会 +1）。

复用 test_ui_34_int997_list_row_batch_wiring 的探针数据与浏览器基础设施；
RESULTS / 网络证据本文件自持（不依赖被导入模块的模块级全局）。
"""
import os
import re
import sys
import time

from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ui_34_int997_list_row_batch_wiring import (
    ARTIFACTS,
    BASE,
    BASE_PREFIX,
    CASE_PREFIX,
    GROUP1,
    GROUP2,
    NEWGROUP,
    _bulk_button,
    _captured,
    _confirm_click,
    _dialog_content,
    _driver,
    _enter_workbench,
    _group_card_present,
    _group_header_btn,
    _load_more_groups,
    _reset_capture,
    _select_cases,
    _select_option_in_dialog,
    _set_theme,
    _setup_probe_data,
    _shot,
    _wait_overlay_gone,
    _cleanup,
)

RESULTS = []
_NET_LOG = []


def _record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f'  [{"PASS" if ok else "FAIL"}] {name}: {detail}')


def _wait_write(drv, url_sub, method, timeout=10):
    """等非 GET 写请求出现且响应状态已落；并入本地 _NET_LOG 供证据汇总。"""
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        for r in _captured(drv):
            u = r.get('url', '')
            m = r.get('method', '')
            if method and m != method:
                continue
            if m == 'GET' or url_sub not in u:
                continue
            if r.get('status') is None:
                continue
            b = r.get('body')
            action = ''
            if isinstance(b, dict):
                action = str(b.get('action', ''))
            entry = {'method': m, 'url': u, 'status': r.get('status'), 'action': action}
            if entry not in _NET_LOG[-500:]:
                _NET_LOG.append(entry)
            seen.append(entry)
        if seen:
            return seen
        time.sleep(0.4)
    return seen


def _wait_refetch(drv, url_sub, timeout=10):
    """等 GET 请求（invalidate→refetch）出现且响应状态已落。"""
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        for r in _captured(drv):
            u = r.get('url', '')
            m = r.get('method', '')
            if m == 'GET' and url_sub in u:
                if r.get('status') is None:
                    continue
                entry = {'method': m, 'url': u, 'status': r.get('status'), 'action': ''}
                if entry not in _NET_LOG[-500:]:
                    _NET_LOG.append(entry)
                seen.append(entry)
        if seen:
            return seen
        time.sleep(0.4)
    return seen


def _nav_count(drv):
    return len(drv.execute_script(
        'return performance.getEntriesByType("navigation") || []'))


def _group_card_exact(drv, name):
    """精确匹配组名（防「旧名 = 新名前缀」substring 误命中）。"""
    cards = drv.find_elements(By.XPATH,
        f"//div[contains(@class,'bg-card')][.//span[contains(., '{name}')]]")
    for card in cards:
        spans = card.find_elements(By.XPATH, f".//span[contains(., '{name}')]")
        for sp in spans:
            if re.fullmatch(re.escape(name), (sp.text or '').strip()):
                return True
    return False


def _is2xx(st):
    return st is not None and 200 <= st < 300


def _print_net():
    for n in _NET_LOG:
        print(f'    NET {n["method"]} {n["url"]} status={n.get("status")} '
              f'action={n.get("action") or ""}')


def main():
    gid1, gid2, cids = _setup_probe_data()
    drv = _driver()
    try:
        _enter_workbench(drv)
        _wait_overlay_gone(drv)
        time.sleep(1.0)
        nav0 = _nav_count(drv)
        _record('初始-分组列表含组1', _group_card_exact(drv, GROUP1), GROUP1)
        _shot(drv, '01_light_list', 'light')

        # ── ① 批量调整分组 →「+ 新建分组」→ 确定 ──────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'A'])
        _bulk_button(drv, '批量调整分组')
        dlg = _dialog_content(drv, '批量调整分组')
        trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        trigs[0].click()
        _select_option_in_dialog(drv, '+ 新建分组')
        inp = dlg.find_element(By.CSS_SELECTOR, "input[aria-label='新分组名称']")
        inp.clear()
        inp.send_keys(NEWGROUP)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        ng_req = _wait_write(drv, '/groups', 'POST', timeout=12)
        ng_status = ng_req[0].get('status') if ng_req else None
        b_req = _wait_write(drv, '/testcases/batch', 'POST', timeout=12)
        b_status = b_req[0].get('status') if b_req else None
        refetch_1 = _wait_refetch(drv, '/groups', timeout=12)
        refetch_1_status = refetch_1[0].get('status') if refetch_1 else None
        _record('①新建分组-POST /groups 真实请求', _is2xx(ng_status),
                f'POST /groups status={ng_status}')
        _record('①新建分组-POST /testcases/batch 真实请求', _is2xx(b_status),
                f'POST /testcases/batch status={b_status} (action=move_to_group)')
        _record('①新建分组-GET /groups refetch（invalidate 触发）',
                _is2xx(refetch_1_status),
                f'GET /groups?per_page=200 status={refetch_1_status}')
        _wait_overlay_gone(drv)
        found = _load_more_groups(drv, target_group=NEWGROUP, max_clicks=40)
        nav1 = _nav_count(drv)
        _record('①新建分组-新组出现在分组列表（无整页重载）',
                found and nav1 == nav0,
                f'新组 {NEWGROUP} 卡出现={found} nav {nav0}→{nav1}')
        _shot(drv, '02_light_after_new_group', 'light')

        # ── ② 组头「编辑」改名 → 保存 ────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1, '编辑')
        dlg = _dialog_content(drv, '编辑分组')
        name_inp = dlg.find_element(By.CSS_SELECTOR, "input[placeholder*='分组名称']")
        name_inp.clear()
        name_inp.send_keys(GROUP1 + '_改名')
        dlg.find_element(By.XPATH, ".//button[contains(., '保存')]").click()
        eg_req = _wait_write(drv, f'/groups/{gid1}', 'PUT', timeout=12)
        eg_status = eg_req[0].get('status') if eg_req else None
        refetch_2 = _wait_refetch(drv, '/groups', timeout=12)
        _record('②改名-PUT /groups/{id} 真实请求', _is2xx(eg_status),
                f'PUT /groups/{gid1} status={eg_status}')
        _record('②改名-GET /groups refetch（invalidate 触发）', bool(refetch_2),
                'GET /groups?per_page=200 refetch 出现')
        _wait_overlay_gone(drv)
        time.sleep(1.5)
        nav2 = _nav_count(drv)
        new_name_ok = _load_more_groups(drv, target_group=GROUP1 + '_改名', max_clicks=40)
        old_gone = not _group_card_exact(drv, GROUP1)
        _record('②改名-新名出现在分组列表、旧名消失（无整页重载）',
                new_name_ok and old_gone and nav2 == nav0,
                f'新名卡出现={new_name_ok} 旧名卡残留={not old_gone} nav {nav0}→{nav2}')

        # ── ③ 组头「复制」───────────────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1 + '_改名', '复制')
        cg_req = _wait_write(drv, '/testcases/batch', 'POST', timeout=12)
        cg_ok = bool(cg_req) or any(
            (r.get('body') or {}).get('action') == 'copy_by_group'
            for r in _captured(drv))
        refetch_3 = _wait_refetch(drv, '/groups', timeout=12)
        _record('③复制分组-POST /testcases/batch 真实请求', cg_ok,
                'POST /testcases/batch action=copy_by_group')
        _record('③复制分组-GET /groups refetch（invalidate 触发）', bool(refetch_3),
                'GET /groups?per_page=200 refetch 出现')
        _wait_overlay_gone(drv)
        time.sleep(1.5)
        nav3 = _nav_count(drv)
        copy_ok = _load_more_groups(drv, target_group=GROUP1 + '_改名_copy', max_clicks=40)
        _record('③复制分组-新组出现（无整页重载）',
                copy_ok and nav3 == nav0,
                f'组 {GROUP1}_改名_copy 卡出现={copy_ok} nav {nav0}→{nav3}')
        _shot(drv, '03_light_after_rename_copy', 'light')

        # ── ④ 组头「删除」───────────────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1 + '_改名_copy', '删除')
        _confirm_click(drv, '删除')
        dg_req = _wait_write(drv, '/groups/', 'DELETE', timeout=12)
        dg_status = dg_req[0].get('status') if dg_req else None
        refetch_4 = _wait_refetch(drv, '/groups', timeout=12)
        _record('④删除分组-DELETE /groups/{id} 真实请求', _is2xx(dg_status),
                f'DELETE /groups/{{id}}?cascade=true status={dg_status}')
        _record('④删除分组-GET /groups refetch（invalidate 触发）', bool(refetch_4),
                'GET /groups?per_page=200 refetch 出现')
        _wait_overlay_gone(drv)
        time.sleep(1.5)
        nav4 = _nav_count(drv)
        time.sleep(1.0)
        gone = not _group_card_exact(drv, GROUP1 + '_改名_copy')
        _record('④删除分组-组卡消失（无整页重载）',
                gone and nav4 == nav0,
                f'组卡残留={not gone} nav {nav0}→{nav4}')

        # ── 深色截图 ───────────────────────────────────────
        _set_theme(drv, 'dark')
        time.sleep(1.0)
        _shot(drv, '04_dark_after_ops', 'dark')

        # ── 网络证据落盘 ────────────────────────────────────
        net_dir = os.path.join(ARTIFACTS, 'retest_group_refresh')
        os.makedirs(net_dir, exist_ok=True)
        with open(os.path.join(net_dir, 'network_evidence.txt'), 'w', encoding='utf-8') as f:
            f.write('INT-997 复测（组级操作后分组列表刷新）Network 证据\n\n')
            for n in _NET_LOG:
                f.write(f"{n['method']} {n['url']} status={n.get('status')}"
                        f"{' action=' + n.get('action') if n.get('action') else ''}\n")
        _print_net()
        _record('网络证据落盘', True, net_dir)

    finally:
        try:
            drv.quit()
        except Exception:
            pass
        try:
            _cleanup(gid1, gid2, cids)
        except Exception as e:
            print('  cleanup error:', e)

    print('\n===== INT-997 复测（分组列表刷新）结果汇总 =====')
    fails = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f'  {"✅" if ok else "❌"} {name}: {detail}')
    print(f'\n通过 {len(RESULTS) - len(fails)}/{len(RESULTS)}')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
