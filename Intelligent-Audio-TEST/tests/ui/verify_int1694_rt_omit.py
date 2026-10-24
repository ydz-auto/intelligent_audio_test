# -*- coding: utf-8 -*-
"""INT-1694 追加口径复核：结果类型只有 1 种 → 结果类型视图入口 + 树内 result_type 层都不渲染。

对接本 run dev server 5378（/api → docker 真实栈 15000，库 intelligent_audio_test）。
真实库候选 result_type 全为同一值，正好是本次口径的场景。
输出：tests/ui/artifacts/int1694_rt_omit/*.png

用法：python -I verify_int1694_rt_omit.py light|dark
"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1694 as base  # noqa: E402

base.BASE = 'http://127.0.0.1:5378'
ART = os.path.join(HERE, 'artifacts', 'int1694_rt_omit')
os.makedirs(ART, exist_ok=True)
base.ART = ART

FAILS = []
CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append((name, bool(ok), detail))
    print('CHECK', 'PASS' if ok else 'FAIL', name, detail)
    if not ok:
        FAILS.append(name)


# ---------- 选择器 ----------
SEL_RT = '[data-testid*="-resultType"]'
SEL_TASK = '[data-testid*="-task:"]'
SEL_ORG = '[data-testid*="-org:"]'
SEL_DEVICE = '[data-testid*="-device:"]'
SEL_CASE_CARD = '[aria-label^="选择 "]'


def make_driver(w=1600, h=1800):
    """独立构造 driver（带 performance 日志，用于 candidates / cart Network 取证）。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    o = Options()
    o.binary_location = base.CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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


def count(drv, css, root=None):
    if root is drv or root is None:
        root = None
    return drv.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll(arguments[1]))'
        '.filter(function(e){return e.offsetParent!==null;}).length;',
        root,
        css,
    )


def texts(drv, root=None):
    if root is drv or root is None:
        root = None
    return drv.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll("button"))'
        '.filter(function(b){return b.offsetParent!==null;})'
        '.map(function(b){return (b.textContent||"").trim();});',
        root,
    )


def click_text(drv, needle, root=None, exact=True):
    if root is drv or root is None:
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


def visible_dialog(drv):
    return drv.execute_script(
        'var ds=Array.from(document.querySelectorAll(\'[role="dialog"]\'))'
        '.filter(function(d){var r=d.getBoundingClientRect();'
        'return r.width>0&&r.height>0;});return ds[ds.length-1]||null;'
    )


def expand_all(drv, root=None, width=3, rounds=10):
    if root is drv or root is None:
        root = None
    for _ in range(rounds):
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


def open_pick(drv):
    drv.get(base.BASE + '/tasks/cherry-pick')
    time.sleep(3)
    for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if '挑选合并' in base.text_of(drv, t):
            base.js_click(drv, t)
            break
    time.sleep(2)
    click_text(drv, '开始挑选', exact=False)
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


def wait_candidates(drv, timeout=420):
    """等候选请求返回 + 骨架屏消失。"""
    deadline = time.time() + timeout
    seen = False
    while time.time() < deadline:
        try:
            logs = drv.get_log('performance')
        except Exception:
            logs = []
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


def network_of_interest(drv):
    out = []
    try:
        logs = drv.get_log('performance')
    except Exception:
        return out
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


def stage2_checks(drv, mode):
    # 用例视图（默认）
    expand_all(drv)
    labels = texts(drv, drv)
    check('阶段2 切换器无「结果类型视图」入口', '结果类型视图' not in labels, str(labels[:6]))
    check(
        '阶段2 用例视图无 result_type 层',
        count(drv, SEL_RT) == 0,
        'rt=%d' % count(drv, SEL_RT),
    )
    check('阶段2 用例视图仍有设备层', count(drv, SEL_DEVICE) > 0, 'devices=%d' % count(drv, SEL_DEVICE))
    check('阶段2 用例视图最末一级是任务', count(drv, SEL_TASK) > 0, 'tasks=%d' % count(drv, SEL_TASK))
    check('阶段2 用例视图有用例卡', count(drv, SEL_CASE_CARD) > 0, 'cases=%d' % count(drv, SEL_CASE_CARD))
    shot(drv, '%s_stage2_case' % mode)

    # 设备视图
    click_text(drv, '设备视图')
    time.sleep(1.5)
    expand_all(drv)
    check(
        '阶段2 设备视图无 result_type 层',
        count(drv, SEL_RT) == 0,
        'rt=%d' % count(drv, SEL_RT),
    )
    check(
        '阶段2 设备视图设备下直接是用例层组织组头',
        count(drv, SEL_ORG) > 0,
        'org=%d' % count(drv, SEL_ORG),
    )
    check('阶段2 设备视图最末一级是任务', count(drv, SEL_TASK) > 0, 'tasks=%d' % count(drv, SEL_TASK))
    shot(drv, '%s_stage2_device_group' % mode)
    click_text(drv, '标签视图')
    time.sleep(1.5)
    expand_all(drv)
    check('阶段2 设备视图切标签后组织组头仍在、无 result_type 层',
          count(drv, SEL_ORG) > 0 and count(drv, SEL_RT) == 0,
          'org=%d rt=%d' % (count(drv, SEL_ORG), count(drv, SEL_RT)))
    shot(drv, '%s_stage2_device_tag' % mode)
    click_text(drv, '分组视图')
    time.sleep(1.0)


def cart_checks(drv, mode):
    dlg = visible_dialog(drv)
    if dlg is None:
        raise RuntimeError('购物车抽屉未打开')
    expand_all(drv, dlg)

    labels = texts(drv, dlg)
    check('购物车切换器无「结果类型视图」', '结果类型视图' not in labels)
    check('购物车任务视图子模式无「结果类型」', '结果类型' not in labels)
    check('购物车任务视图任务首级',
          count(drv, '[data-testid^="cart-branch-cart-task:"]', dlg) > 0)
    check('购物车任务视图用例子模式无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    shot(drv, '%s_cart_task_case' % mode)

    # 任务视图 · 设备子模式
    check('任务视图设备子模式可点', click_text(drv, '设备', dlg))
    time.sleep(1.5)
    expand_all(drv, dlg)
    dlg = visible_dialog(drv)
    check('任务视图设备子模式无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    check('任务视图设备子模式设备下是组织组头',
          count(drv, SEL_ORG, dlg) > 0, 'org=%d' % count(drv, SEL_ORG, dlg))
    shot(drv, '%s_cart_task_device' % mode)

    # 用例视图
    check('购物车用例视图可点', click_text(drv, '用例视图', dlg))
    time.sleep(1.5)
    expand_all(drv, dlg)
    dlg = visible_dialog(drv)
    check('购物车用例视图无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    check('购物车用例视图任务层仍在',
          count(drv, SEL_TASK, dlg) > 0, 'tasks=%d' % count(drv, SEL_TASK, dlg))
    shot(drv, '%s_cart_case' % mode)
    click_text(drv, '标签视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg)
    shot(drv, '%s_cart_case_tag' % mode)
    click_text(drv, '分组视图', dlg)
    time.sleep(1.2)

    # 设备视图
    check('购物车设备视图可点', click_text(drv, '设备视图', dlg))
    time.sleep(1.5)
    expand_all(drv, dlg)
    dlg = visible_dialog(drv)
    check('购物车设备视图无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    check('购物车设备视图设备下是组织组头',
          count(drv, SEL_ORG, dlg) > 0, 'org=%d' % count(drv, SEL_ORG, dlg))
    check('购物车设备视图任务层仍在',
          count(drv, SEL_TASK, dlg) > 0, 'tasks=%d' % count(drv, SEL_TASK, dlg))
    shot(drv, '%s_cart_device' % mode)


def single_task_checks(drv, mode):
    """上一轮 P2-2 的运行时复核：移除一个任务组后，购物车三视图任务层仍恒显。"""
    dlg = visible_dialog(drv)
    if not click_text(drv, '任务视图', dlg):
        check('任务视图入口可点', False)
        return
    time.sleep(1.5)
    rows = dlg.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-cart-task:"]')
    print('CART_TASKS', len(rows))
    if len(rows) < 2:
        check('单任务场景可构造（购物车≥2任务）', False, 'tasks=%d' % len(rows))
        return
    btn = rows[1].find_element(By.CSS_SELECTOR, "button[aria-label='移除该组']")
    base.js_click(drv, btn)
    time.sleep(1.5)
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
    expand_all(drv, dlg, width=2, rounds=6)
    dlg = visible_dialog(drv)
    check('单任务 · 用例视图仍有任务层（P2-2）',
          count(drv, SEL_TASK, dlg) > 0, 'tasks=%d' % count(drv, SEL_TASK, dlg))
    check('单任务 · 用例视图仍无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    shot(drv, '%s_cart_single_case' % mode)

    click_text(drv, '设备视图', dlg)
    time.sleep(1.5)
    expand_all(drv, dlg, width=2, rounds=6)
    dlg = visible_dialog(drv)
    check('单任务 · 设备视图仍有任务层（P2-2）',
          count(drv, SEL_TASK, dlg) > 0, 'tasks=%d' % count(drv, SEL_TASK, dlg))
    check('单任务 · 设备视图仍无 result_type 层',
          count(drv, SEL_RT, dlg) == 0, 'rt=%d' % count(drv, SEL_RT, dlg))
    shot(drv, '%s_cart_single_device' % mode)


def review_checks(drv, mode):
    """复核步骤同样复用 CartPanel：组织控件 1 份、无结果类型入口 / 层、任务层仍在。"""
    dlg = visible_dialog(drv)
    root = dlg or drv
    if not click_text(drv, '去复核', root, exact=False):
        check('复核入口可点', False)
        return
    time.sleep(4)
    scope = visible_dialog(drv) or drv
    expand_all(drv, scope, width=2, rounds=6)
    scope = visible_dialog(drv) or drv
    labels = texts(drv, scope)
    check('复核步骤无「结果类型视图」入口', '结果类型视图' not in labels)
    check('复核步骤组织控件 1 份',
          count(drv, '[aria-label="用例组织方式"]', scope) == 1,
          'count=%d' % count(drv, '[aria-label="用例组织方式"]', scope))
    check('复核步骤无 result_type 层',
          count(drv, SEL_RT, scope) == 0, 'rt=%d' % count(drv, SEL_RT, scope))
    check('复核步骤任务层仍在',
          count(drv, SEL_TASK, scope) > 0, 'tasks=%d' % count(drv, SEL_TASK, scope))
    shot(drv, '%s_review_case' % mode)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'light'
    drv = make_driver()
    try:
        base.login(drv)
        base.set_theme(drv, 'dark' if mode == 'dark' else 'light')
        open_pick(drv)
        rows = wait_task_rows(drv)
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
            base.js_click(drv, cb)
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
