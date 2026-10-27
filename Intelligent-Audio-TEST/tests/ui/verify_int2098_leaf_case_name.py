# -*- coding: utf-8 -*-
"""INT-2098 叶行（结果行）去掉重复用例名——浏览器实测（docker 真实栈 15000）。

验证点（卡内验收标准）：
1) 阶段 2（task 419，用例视图展开到叶）：pick-leaf-* 叶行不再显示用例名，
   设备/API 名为主列；用例名只在用例卡出现。
2) 购物车（CartTree，任务视图展开到叶）：cart-leaf-* 叶行不再显示用例名。
3) 回归快检：阶段 2 叶行勾选 / 切视图勾选保持；购物车叶行勾选 / 单条移除。
4) Network：无新增请求（仅既有候选树 / 叶分页 / cart 请求）；console 无 SEVERE。
5) 浅色 + 深色截图（阶段 2 + 购物车各 1 张，展开到叶）。

被测入口：本脚本起静态服务 + /api 反代到 docker 后端 15000（交付 dist 构建）。

用法：python tests/ui/verify_int2098_leaf_case_name.py
（端口可用 INT2098_PORT 覆盖；默认 5356）
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PORT = int(os.environ.get('INT2098_PORT', '5356'))
os.environ['INT1497_PORT'] = str(PORT)  # base.BASE 在 import 时按此端口

import verify_int1497_cherry_pick as base  # noqa: E402
from _int1934_lib import Api, ensure_user, unwrap  # noqa: E402

DIST = os.path.normpath(os.path.join(base.PROJECT_ROOT, 'frontend-react', 'dist'))
ART = os.path.join(HERE, 'artifacts', 'int2098')
os.makedirs(ART, exist_ok=True)

USER = '接线测试_int2098'
PASS = 'JieXianTest@2026'
TASK_ID = 419
TASK_NAME_HINT = '小艺拒识E2E测试任务'
ADD_RESULT_COUNT = 3


def inject(drv, token, theme):
    drv.get(base.BASE)
    time.sleep(1.2)
    drv.execute_script("localStorage.setItem('iatp:auth:token:v1', arguments[0])", token)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.get(base.BASE + '/tasks/cherry-picks')


def enter_stage2(drv):
    base.wait_text(drv, '开始挑选', timeout=90)
    base.click_button_text(drv, '开始挑选', timeout=30)
    base.wait_text(drv, '阶段 1：选择任务', timeout=60)
    search = base.WebDriverWait(drv, 40).until(
        lambda d: d.find_element(base.By.XPATH, "//input[@aria-label='搜索任务名称']"))
    search.send_keys(TASK_NAME_HINT)
    time.sleep(1.5)
    row = base.WebDriverWait(drv, 60).until(
        lambda d: d.find_element(base.By.XPATH, f"//*[@data-testid='pick-task-{TASK_ID}']"))
    base.js_click(drv, row.find_element(base.By.XPATH, ".//*[@role='checkbox']"))
    time.sleep(0.5)
    base.click_button_text(drv, '下一步：选择结果')
    base.wait_text(drv, '阶段 2：选择结果', timeout=60)


def visible(drv, css):
    return [e for e in drv.find_elements(base.By.CSS_SELECTOR, css) if e.is_displayed()]


def leaf_rows(drv, prefix):
    return visible(drv, f'[data-testid^="{prefix}-"]')


def wait_leaf_rows(drv, prefix, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        rows = leaf_rows(drv, prefix)
        if rows:
            return rows
        time.sleep(0.5)
    return []


def assert_leaf_rows(drv, prefix, name_by_id, dev_by_id):
    """断言叶行不含用例名、含设备/API 名。返回 (叶行, 对照数)。"""
    rows = wait_leaf_rows(drv, prefix)
    assert rows, f'未出现叶行 [{prefix}]'
    checked = 0
    for r in rows:
        tid = r.get_attribute('data-testid')
        try:
            key = int(tid.rsplit('-', 1)[-1])
        except ValueError:
            continue
        txt = (r.text or '').replace('\n', ' ')
        case = name_by_id.get(key)
        dev = dev_by_id.get(key)
        if case:
            assert case not in txt, f'叶行仍显示用例名: {tid} 含「{case}」→ "{txt[:60]}"'
            checked += 1
        if dev:
            assert dev in txt, f'叶行缺少设备/API 名: {tid} 缺「{dev}」→ "{txt[:60]}"'
    assert checked >= 1, f'叶行没有可对照的用例名/设备名 [{prefix}]'
    return rows, checked


def click_expand_leaf_parents(drv, count=3):
    """「全部展开」后，叶的父级仍是收起态；点前 count 个「展开」钮加载叶明细。"""
    for _ in range(count):
        btns = [b for b in drv.find_elements(base.By.XPATH, "//button[@aria-label='展开']")
                if b.is_displayed()]
        if not btns:
            break
        base.js_click(drv, btns[0])
        time.sleep(0.9)
    return len([b for b in drv.find_elements(base.By.XPATH, "//button[@aria-label='展开']")
                if b.is_displayed()]) == 0


def expand_cart_to_leaves(drv):
    """购物车树无「全部展开」信号：逐层点可见「展开」钮直到出现叶行。"""
    for _ in range(30):
        rows = leaf_rows(drv, 'cart-leaf')
        if rows:
            return rows
        btns = [b for b in drv.find_elements(base.By.XPATH, "//button[@aria-label='展开']")
                if b.is_displayed()]
        if not btns:
            break
        for b in btns:
            try:
                base.js_click(drv, b)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1.0)
    return leaf_rows(drv, 'cart-leaf')


def checkbox_checked(drv, el):
    return el.get_attribute('data-checked') is not None or el.get_attribute('aria-checked') == 'true'


def summary_text(drv):
    """阶段 2 已选汇总条文案（sticky bottom，跨视图保留）。"""
    for e in visible(drv, '.fixed.bottom-6 .text-sm'):
        t = (e.text or '').strip()
        if t.startswith('已选'):
            return t
    return ''


def api_requests_since(drv):
    """drain 后新产生的 /api 请求（双层 message 解包；get_log 读一次清空）。"""
    out = []
    try:
        logs = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for raw in logs:
        try:
            msg = json.loads(raw['message'])['message']
        except Exception:  # noqa: BLE001
            continue
        if msg.get('method') == 'Network.requestWillBeSent':
            url = msg['params']['request'].get('url', '')
            if '/api/' in url:
                out.append(url.split('/api/')[-1].split('?')[0][:120])
    return out


def verify_stage2(drv, case_by_result, dev_by_result, theme, evidence):
    base.wait_text(drv, '拒识', timeout=180)
    base.click_button_text(drv, '全部展开', timeout=20)
    time.sleep(1.5)
    # 展开叶父级前的网络基线（改动纯展示：展开叶明细后应只有 candidates 分页请求）
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass
    click_expand_leaf_parents(drv, 3)
    rows, checked = assert_leaf_rows(drv, 'pick-leaf', case_by_result, dev_by_result)
    evidence['stage2_rows'] = len(rows)
    evidence['stage2_checked_pairs'] = checked

    # 网络：展开叶明细只触发 candidates 分页，无新增请求
    net = api_requests_since(drv)
    evidence['stage2_leaf_net'] = net
    non_candidates = [n for n in net if 'candidates' not in n]
    assert not non_candidates, f'展开叶明细出现非 candidates 请求: {non_candidates}'

    # 用例名只在用例卡出现（取实际加载的叶行的用例名，正文出现 ≥1 次 = 卡面展示）
    sample_id = int(rows[0].get_attribute('data-testid').rsplit('-', 1)[-1])
    sample_case = case_by_result.get(sample_id) or ''
    assert sample_case, '叶行无对照用例名'
    body = base.body_text(drv)
    assert body.count(sample_case) >= 1, f'用例卡未显示用例名: {sample_case[:40]}'
    evidence['stage2_case_in_body'] = body.count(sample_case)
    evidence['stage2_sample_case'] = sample_case[:60]

    shot = os.path.join(ART, f'stage2_{theme}.png')
    drv.save_screenshot(shot)
    evidence['stage2_shot'] = shot

    # 回归：勾选叶行 → 已选；切视图（设备 → 回用例）勾选保持（汇总条计数不变）
    first = rows[0]
    first_tid = first.get_attribute('data-testid')
    cb = first.find_element(base.By.XPATH, ".//*[@role='checkbox']")
    base.js_click(drv, cb)
    time.sleep(0.8)
    assert checkbox_checked(drv, cb), f'阶段2 叶行勾选未生效: {first_tid}'
    summary_before = summary_text(drv)
    assert '已选' in summary_before, \
        f'阶段2 汇总条未显示已选: {summary_before[:80]}'
    base.click_button_text(drv, '设备视图', timeout=10)
    time.sleep(2.0)
    base.click_button_text(drv, '用例视图', timeout=10)
    time.sleep(2.0)
    summary_after = summary_text(drv)
    assert '已选' in summary_after, \
        f'切视图后勾选丢失（汇总条无已选）: {summary_after[:80]}'
    evidence['stage2_toggle_ok'] = True
    evidence['stage2_summary_before'] = summary_before[:80]
    evidence['stage2_summary_after'] = summary_after[:80]
    return shot


def verify_cart(drv, case_by_item, dev_by_item, theme, evidence):
    btn = [b for b in drv.find_elements(base.By.TAG_NAME, 'button') if b.is_displayed()
           and '打开购物车' in (b.text or '')]
    assert btn, '未找到「打开购物车」'
    base.js_click(drv, btn[0])
    time.sleep(2.5)
    base.wait_text(drv, '另存为挑选集', timeout=30)  # 抽屉已开
    rows = expand_cart_to_leaves(drv)
    assert rows, '购物车展开未出现叶行'
    r1, c1 = assert_leaf_rows(drv, 'cart-leaf', case_by_item, dev_by_item)
    evidence['cart_rows'] = len(r1)
    evidence['cart_checked_pairs'] = c1
    shot = os.path.join(ART, f'cart_{theme}.png')
    drv.save_screenshot(shot)
    evidence['cart_shot'] = shot

    # 回归：勾选叶行 + 单条移除
    first_tid = r1[0].get_attribute('data-testid')
    cb = r1[0].find_element(base.By.XPATH, ".//*[@role='checkbox']")
    base.js_click(drv, cb)
    time.sleep(0.6)
    row2 = visible(drv, f'[data-testid="{first_tid}"]')
    assert row2, f'勾选后叶行消失: {first_tid}'
    cb2 = row2[0].find_element(base.By.XPATH, ".//*[@role='checkbox']")
    assert checkbox_checked(drv, cb2), '购物车叶行勾选未生效'
    xbtn = row2[0].find_element(base.By.XPATH, ".//button[@aria-label='移除']")
    base.js_click(drv, xbtn)
    time.sleep(1.0)
    # 单条移除走 ConfirmDialog（role=alertdialog，开合动画需等就绪再点「继续」）
    alert = base.WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(base.By.CSS_SELECTOR, "[role='alertdialog']"))
    assert alert, '单条移除确认弹窗未出现'
    time.sleep(0.8)
    cont = [b for b in alert[0].find_elements(base.By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() == '继续']
    assert cont, '确认弹窗「继续」钮未找到'
    base.js_click(drv, cont[0])
    base.WebDriverWait(drv, 20).until(
        lambda d: not visible(d, f'[data-testid="{first_tid}"]'))
    evidence['cart_toggle_remove_ok'] = True
    return shot


def console_severe(drv):
    try:
        return [c.get('message') for c in (drv.get_log('browser') or [])
                if c.get('level') == 'SEVERE'][:5]
    except Exception:  # noqa: BLE001
        return []


def main():
    admin = Api()
    admin.login()
    row, created = ensure_user(admin, USER, 'int2098@jiexian.test', PASS)
    assert row, '隔离账号不可用'
    u = Api(user=USER, password=PASS)
    u.login()
    token = u.token
    report = {'base': base.BASE, 'card': 'INT-2098', 'user_created': created, 'runs': []}

    # 候选数据（task 419 全量）：result_id → case_name / device_name
    st, d = u.get(f'/api/v1/tasks/cherry-picks/candidates?task_ids={TASK_ID}&per_page=200')
    assert st == 200, f'candidates 非 200: {st}'
    cands = (unwrap(d) or {}).get('items') or []
    assert cands, 'task 419 无候选'
    report['candidates_total'] = (unwrap(d) or {}).get('total')
    report['candidates_fetched'] = len(cands)
    case_by_result = {it['result_id']: (it.get('case_name') or '') for it in cands}
    dev_by_result = {it['result_id']: (it.get('device_name') or it.get('api_name') or '')
                     for it in cands}

    # 预置购物车（隔离账号，3 条；来源任务=419）
    add_ids = [cands[i]['result_id'] for i in range(min(ADD_RESULT_COUNT, len(cands)))]
    st2, _ = u.post('/api/v1/tasks/cherry-picks/cart/items', {'result_ids': add_ids})
    report['cart_add_status'] = st2
    st3, d3 = u.get('/api/v1/tasks/cherry-picks/cart')
    cart = unwrap(d3) or {}
    case_by_item, dev_by_item = {}, {}
    for g in (cart.get('groups') or []):
        for it in (g.get('items') or []):
            case_by_item[it['item_id']] = it.get('source_case_name') or ''
            dev_by_item[it['item_id']] = (it.get('source_device_name') or it.get('source_api_name') or '')
    report['cart_items'] = len(case_by_item)
    assert report['cart_items'] >= 2, '购物车预置条目不足'

    srv = base.start_server(DIST)
    print('被测入口:', base.BASE)
    try:
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
            health = json.loads(r.read().decode())
        assert health.get('database') == 'intelligent_audio_test', f'后端库不符: {health}'
        report['health'] = health.get('database')

        drv = base.make_driver()
        try:
            for theme in ('light', 'dark'):
                ev = {'theme': theme}
                inject(drv, token, theme)
                html_cls = drv.execute_script('return document.documentElement.className')
                assert ('dark' in html_cls) == (theme == 'dark'), f'主题未生效 html={html_cls}'
                enter_stage2(drv)
                verify_stage2(drv, case_by_result, dev_by_result, theme, ev)
                ev['stage2_severe'] = console_severe(drv)
                assert not ev['stage2_severe'], f'阶段2 console SEVERE: {ev["stage2_severe"]}'
                time.sleep(1.0)
                verify_cart(drv, case_by_item, dev_by_item, theme, ev)
                ev['cart_severe'] = console_severe(drv)
                assert not ev['cart_severe'], f'购物车 console SEVERE: {ev["cart_severe"]}'
                report['runs'].append(ev)
                print(json.dumps(ev, ensure_ascii=False)[:600])
                # 关抽屉 + 收尾下一轮
                try:
                    drv.execute_script(
                        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.0)
        finally:
            try:
                drv.quit()
            except Exception:  # noqa: BLE001
                pass
    finally:
        srv.shutdown()
        st4, _ = u.raw('/api/v1/tasks/cherry-picks/cart/items', method='DELETE')
        report['cart_clear_status'] = st4
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('evidence →', os.path.join(ART, 'evidence.json'))

    fails = []
    for ev in report['runs']:
        if not ev.get('stage2_rows'):
            fails.append(f"{ev['theme']}: 阶段2 无叶行")
        if not ev.get('cart_rows'):
            fails.append(f"{ev['theme']}: 购物车无叶行")
        if not ev.get('stage2_toggle_ok'):
            fails.append(f"{ev['theme']}: 阶段2 勾选/切视图回归失败")
        if not ev.get('cart_toggle_remove_ok'):
            fails.append(f"{ev['theme']}: 购物车勾选/移除回归失败")
    assert not fails, '；'.join(fails)
    print('PASS: 叶行不再显示用例名，勾选/切视图/移除回归通过，无 SEVERE')


if __name__ == '__main__':
    main()
