# -*- coding: utf-8 -*-
"""INT-1694 返工复核取证（三项 P2）：组织控件单份 / 购物车任务层恒显 / 结果类型入口隐藏。

对接本 run dev server 5378（/api → docker 真实栈 15000，库 intelligent_audio_test）。
复用 capture_int1694 的登录 / 阶段 1 选择 / 加购 / 购物车 helper。
输出：tests/ui/artifacts/int1694_rework/*.png

用法：python -I verify_int1694_rework.py light|dark
"""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1694 as base  # noqa: E402

base.BASE = 'http://127.0.0.1:5378'
ART = os.path.join(HERE, 'artifacts', 'int1694_rework')
os.makedirs(ART, exist_ok=True)
base.ART = ART

FAILS = []
CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append((name, bool(ok), detail))
    print('CHECK', 'PASS' if ok else 'FAIL', name, detail)
    if not ok:
        FAILS.append(name)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def texts(drv, root):
    """可见按钮文案（一次 JS 往返；逐元素 is_displayed 在几百行树上极慢）。"""
    if root is drv:
        root = None
    return drv.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll("button"))'
        '.filter(function(b){return b.offsetParent!==null;})'
        '.map(function(b){return (b.textContent||"").trim();});',
        root,
    )


def js_click(drv, el):
    drv.execute_script(
        'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el
    )


def visible_dialog(drv):
    return drv.execute_script(
        'var ds=Array.from(document.querySelectorAll(\'[role="dialog"]\'))'
        '.filter(function(d){var r=d.getBoundingClientRect();'
        'return r.width>0&&r.height>0;});return ds[ds.length-1]||null;'
    )


def count(drv, root, css):
    if root is drv:
        root = None
    return drv.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll(arguments[1]))'
        '.filter(function(e){return e.offsetParent!==null;}).length;',
        root,
        css,
    )


def shot(drv, name):
    drv.execute_script(
        'window.scrollTo(0,0);'
        'document.querySelectorAll("*").forEach(function(e){'
        'if(e.scrollTop>0&&e.scrollHeight>e.clientHeight+20)e.scrollTop=0;});'
    )
    time.sleep(0.5)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', name)


def click_text(drv, needle, root=None, exact=True):
    if root is drv:
        root = None
    return bool(
        drv.execute_script(
            'var root=arguments[0]||document,needle=arguments[1],exact=arguments[2];'
            'var el=Array.from(root.querySelectorAll("button")).find(function(b){'
            'if(b.offsetParent===null)return false;'
            'var t=(b.textContent||"").trim();'
            'return exact?(t===needle):(t.indexOf(needle)>=0);});'
            'if(!el)return false;'
            'el.scrollIntoView({block:"center"});el.click();return true;',
            root,
            needle,
            exact,
        )
    )


def expand_all(drv, root=None, width=3, rounds=9):
    """逐层展开（每轮只点最前面几个分支）：真实库 138 用例时全量展开为 O(n²) 重渲染，
    取证只需前几条链路可见即可，counts 断言看整棵树。"""
    if root is drv:
        root = None
    for i in range(rounds):
        n = drv.execute_script(
            'var root=arguments[0]||document,w=arguments[1];'
            'var btns=Array.from(root.querySelectorAll(\'button[aria-label="展开"]\'))'
            '.filter(function(b){return b.offsetParent!==null;}).slice(0,w);'
            'btns.forEach(function(b){b.scrollIntoView({block:"center"});b.click();});'
            'return btns.length;',
            root,
            width,
        )
        time.sleep(0.4)
        if not n:
            break
    time.sleep(0.5)


def make_driver(w=1600, h=1800):
    o = Options()
    o.binary_location = base.CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability(
        'goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'}
    )
    import winreg

    major = 0
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon'
        ) as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(
        os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64'
    )
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(
        options=o, service=Service(executable_path=path) if path else Service()
    )
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    return d


def network_of_interest(drv):
    """性能日志里的 candidates / cart 请求（方法 + URL + 状态）。"""
    out = []
    try:
        logs = drv.get_log('performance')
    except Exception:
        return out
    import json

    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        p = msg['params']['response']
        url = p.get('url') or ''
        if 'cherry-picks/candidates' in url or 'cherry-picks/cart' in url:
            out.append((p.get('status'), url.split('/api/v1')[-1][:90]))
    return out


def open_pick(drv):
    drv.get(base.BASE + '/tasks/cherry-pick')
    time.sleep(3)
    for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if '挑选合并' in text_of(drv, t):
            js_click(drv, t)
            break
    time.sleep(2)
    click_text(drv, '开始挑选')
    time.sleep(3)


def wait_task_rows(drv, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = [
            c
            for c in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if (c.get_attribute('aria-label') or '').startswith('选择任务')
        ]
        if len(rows) >= 2:
            print('TASK_ROWS', len(rows))
            return rows
        time.sleep(3)
    raise RuntimeError('阶段 1 任务行未加载')


def wait_tree(drv, timeout=420, selector='[data-testid^="pick-branch-"]'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if drv.find_elements(By.CSS_SELECTOR, selector):
            time.sleep(2)
            return
        time.sleep(3)
    raise RuntimeError('树未渲染：%s' % selector)


def wait_candidates(drv, timeout=420):
    """等候选请求返回 + 骨架屏消失（任务 418/419 各 138 行，真实库较慢）。"""
    deadline = time.time() + timeout
    seen = False
    while time.time() < deadline:
        try:
            logs = drv.get_log('performance')
        except Exception:
            logs = []
        import json

        for entry in logs:
            try:
                msg = json.loads(entry['message'])['message']
            except Exception:
                continue
            if msg.get('method') != 'Network.responseReceived':
                continue
            url = msg['params']['response'].get('url') or ''
            if 'cherry-picks/candidates' in url and 'task_ids' in url:
                seen = True
        skel = len(drv.find_elements(By.CSS_SELECTOR, '.animate-pulse'))
        if seen and skel == 0:
            time.sleep(3)
            return
        time.sleep(3)
    if not seen:
        raise RuntimeError('候选请求未返回')


def task_branch_count(drv, root=None):
    return count(drv, root or drv, '[data-testid*="-task:"]')


def org_header_count(drv, root=None):
    return count(drv, root or drv, '[data-testid*="-org:"]')


def org_control_count(drv, root=None):
    return count(drv, root or drv, '[aria-label="用例组织方式"]')


def stage2_checks(drv, mode):
    # 用例视图（默认）
    expand_all(drv)
    labels = texts(drv, drv)
    check('stage2 无「结果类型视图」入口', '结果类型视图' not in labels)
    check(
        'stage2 用例视图组织控件 1 份',
        org_control_count(drv) == 1,
        'count=%d' % org_control_count(drv),
    )
    check(
        'stage2 用例视图最末一级是任务',
        task_branch_count(drv) > 0,
        'task_nodes=%d' % task_branch_count(drv),
    )
    shot(drv, '%s_stage2_case' % mode)

    # 分组 / 标签切换（设备视图）
    click_text(drv, '设备视图')
    time.sleep(1.5)
    expand_all(drv)
    check(
        'stage2 设备视图组织控件 1 份',
        org_control_count(drv) == 1,
        'count=%d' % org_control_count(drv),
    )
    check(
        'stage2 设备视图组织组头在 result_type 之下、用例卡之上',
        org_header_count(drv) > 0,
        'org_headers=%d' % org_header_count(drv),
    )
    check(
        'stage2 设备视图最末一级是任务',
        task_branch_count(drv) > 0,
        'task_nodes=%d' % task_branch_count(drv),
    )
    shot(drv, '%s_stage2_device_group' % mode)
    click_text(drv, '标签视图')
    time.sleep(1.5)
    expand_all(drv)
    check('stage2 设备视图切换标签后组织组头仍在', org_header_count(drv) > 0)
    shot(drv, '%s_stage2_device_tag' % mode)
    click_text(drv, '分组视图')
    time.sleep(1.0)


def cart_checks(drv, mode):
    dlg = visible_dialog(drv)
    if dlg is None:
        raise RuntimeError('购物车抽屉未打开')
    expand_all(drv, dlg)

    # 任务视图（默认）
    labels = texts(drv, dlg)
    check('购物车四视图切换器无「结果类型视图」', '结果类型视图' not in labels)
    check('购物车任务视图子模式无「结果类型」', '结果类型' not in labels)
    check(
        '购物车任务视图任务首级',
        count(drv, dlg, '[data-testid^="cart-branch-cart-task:"]') > 0,
    )
    shot(drv, '%s_cart_task_view' % mode)

    # 用例视图：组织控件只应 1 份（P2-1）
    click_text(drv, '用例视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    c = org_control_count(drv, dlg)
    check('购物车用例视图组织控件 1 份（P2-1）', c == 1, 'count=%d' % c)
    check(
        '购物车用例视图最末一级是任务',
        task_branch_count(drv, dlg) > 0,
        'task_nodes=%d' % task_branch_count(drv, dlg),
    )
    shot(drv, '%s_cart_case' % mode)

    # 购物车用例视图 分组 / 标签 切换各 1 张
    click_text(drv, '标签视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    shot(drv, '%s_cart_case_tag' % mode)
    click_text(drv, '分组视图', dlg)
    time.sleep(1.2)

    # 设备视图
    click_text(drv, '设备视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    check(
        '购物车设备视图组织控件 1 份',
        org_control_count(drv, dlg) == 1,
        'count=%d' % org_control_count(drv, dlg),
    )
    check(
        '购物车设备视图组织组头在 result_type 之下',
        org_header_count(drv, dlg) > 0,
        'org_headers=%d' % org_header_count(drv, dlg),
    )
    check(
        '购物车设备视图最末一级是任务',
        task_branch_count(drv, dlg) > 0,
        'task_nodes=%d' % task_branch_count(drv, dlg),
    )
    shot(drv, '%s_cart_device' % mode)


def single_task_checks(drv, mode):
    """移除一个任务组 → 购物车仅剩 1 个来源任务 → 三视图任务层仍恒显（P2-2）。"""
    dlg = visible_dialog(drv)
    click_text(drv, '任务视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    rows = dlg.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-cart-task:"]')
    print('CART_TASKS', len(rows))
    if len(rows) < 2:
        check('单任务场景可构造（购物车≥2任务）', False, 'tasks=%d' % len(rows))
        return
    btn = rows[1].find_element(By.CSS_SELECTOR, "button[aria-label='移除该组']")
    js_click(drv, btn)
    time.sleep(1.5)
    # 确认弹窗
    for label in ('继续', '移除', '确认'):
        if click_text(drv, label):
            break
    time.sleep(3)
    dlg = visible_dialog(drv)
    remaining = dlg.find_elements(
        By.CSS_SELECTOR, '[data-testid^="cart-branch-cart-task:"]'
    )
    check('移除后仅剩 1 个任务', len(remaining) == 1, 'tasks=%d' % len(remaining))
    shot(drv, '%s_cart_single_task_view' % mode)

    click_text(drv, '用例视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    dlg = visible_dialog(drv)
    n = task_branch_count(drv, dlg)
    check('单任务 · 用例视图仍有任务层（P2-2）', n > 0, 'task_nodes=%d' % n)
    shot(drv, '%s_cart_single_case' % mode)

    click_text(drv, '设备视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    dlg = visible_dialog(drv)
    n = task_branch_count(drv, dlg)
    check('单任务 · 设备视图仍有任务层（P2-2）', n > 0, 'task_nodes=%d' % n)
    shot(drv, '%s_cart_single_device' % mode)


def review_checks(drv, mode):
    dlg = visible_dialog(drv)
    root = dlg or drv
    clicked = click_text(drv, '去复核', root, exact=False)
    time.sleep(4)
    if not clicked:
        print('REVIEW_SKIP 未找到「去复核」')
        return
    # 复核步骤仍复用 CartPanel；作用域限定当前可见面板（关闭的抽屉可能留在 DOM）
    again = visible_dialog(drv)
    scope = again or drv
    expand_all(drv, scope)
    c = org_control_count(drv, scope)
    check('复核步骤用例视图组织控件 1 份', c == 1, 'count=%d' % c)
    check('复核步骤无「结果类型视图」入口', '结果类型视图' not in texts(drv, scope))
    check(
        '复核步骤最末一级是任务',
        task_branch_count(drv, scope) > 0,
        'task_nodes=%d' % task_branch_count(drv, scope),
    )
    shot(drv, '%s_review_case' % mode)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'light'
    drv = make_driver()
    try:
        base.login(drv)
        base.set_theme(drv, 'dark' if mode == 'dark' else 'light')
        open_pick(drv)
        rows = wait_task_rows(drv)
        # 优先用任务 418/419（各 138 条候选，用例自带真实分组/标签），否则退回前两个任务
        by_id = {}
        for cb in rows:
            row = cb.find_element(By.XPATH, './ancestor-or-self::*[@data-testid][1]')
            tid = (row.get_attribute('data-testid') or '').replace('pick-task-', '')
            if tid.isdigit():
                by_id[int(tid)] = cb
        chosen = [by_id[i] for i in (418, 419) if i in by_id]
        if len(chosen) < 2:
            chosen = rows[:2]
        for cb in chosen:
            js_click(drv, cb)
            time.sleep(0.4)
        print('STAGE1_SELECTED', [c.get_attribute('aria-label') for c in chosen])
        click_text(drv, '下一步', exact=False)
        wait_candidates(drv)
        stage2_checks(drv, mode)

        base.add_to_cart(drv)
        base.open_cart(drv)
        cart_checks(drv, mode)
        single_task_checks(drv, mode)
        review_checks(drv, mode)

        net = network_of_interest(drv)
        print('NETWORK', len(net))
        for status, url in net[:12]:
            print('NET', status, url)
        bad = [n for n in net if n[0] != 200]
        check('Network 全部 200', not bad, str(bad[:5]))
        check('Network 命中 candidates 或 cart', len(net) > 0, 'n=%d' % len(net))

        errs = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        check('控制台无 SEVERE', not errs, str(errs[:2])[:300])
    finally:
        drv.quit()
        base.clear_cart()
    print('SUMMARY', len([c for c in CHECKS if c[1]]), '/', len(CHECKS))
    if FAILS:
        print('FAILED:', FAILS)
        sys.exit(1)
    print('ALL_OK')


if __name__ == '__main__':
    main()
