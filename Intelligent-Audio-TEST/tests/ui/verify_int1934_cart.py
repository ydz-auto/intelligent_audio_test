# -*- coding: utf-8 -*-
"""INT-1934 补证第 3 项之 save-pick-set 窗（另存为挑选集）浅 + 深。

购物车 per-user：本脚本建/复用隔离账号（接线测试_int1934），用其 token 注入浏览器，
先用 API 加购 1 条候选（真实结果行），再走 UI 打开购物车抽屉 → 另存为挑选集（只截帧，不保存）。
收尾清空该账号购物车。

用法：python tests/ui/verify_int1934_cart.py
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
from _int1934_lib import Api, ensure_user, unwrap  # noqa: E402

ART = U.ART
USER = '接线测试_int1934'
PASS = 'JieXianTest@2026'
report = {'card': 'INT-1934', 'kind': 'save-pick-set', 'cart': {}}


def cart_total(api):
    st, d = api.get('/api/v1/tasks/cherry-picks/cart')
    return (unwrap(d) or {}).get('total'), st


def find_contains(d, label):
    for el in d.find_elements(By.CSS_SELECTOR, 'button, a'):
        try:
            if el.is_displayed() and label in (el.text or ''):
                return el
        except Exception:
            continue
    return None


def open_cart_and_save_dialog(d):
    btn = find_contains(d, '打开购物车')
    if btn is None:
        time.sleep(4)
        btn = find_contains(d, '打开购物车')
    assert btn is not None, '未找到「打开购物车」；可见按钮=%r' % [
        (b.get_attribute('aria-label'), b.text.strip()[:20])
        for b in d.find_elements(By.TAG_NAME, 'button') if b.is_displayed()][:40]
    U.js_click(d, btn)
    time.sleep(2.5)
    save = U.wait_text(d, '另存为挑选集', timeout=20)
    assert save is not None, '购物车抽屉未出现「另存为挑选集」'
    assert save.is_enabled(), '「另存为挑选集」被禁用（购物车空？）'
    U.js_click(d, save)
    time.sleep(1.2)
    assert save_dialog_input(d) is not None, '另存为挑选集弹窗未出现'


def save_dialog_input(d):
    """定位「另存为挑选集」弹窗本体：唯一带「挑选集名称」占位符的输入框。"""
    for el in d.find_elements(By.CSS_SELECTOR, 'input[placeholder]'):
        try:
            ph = el.get_attribute('placeholder') or ''
        except Exception:
            continue
        if '挑选集名称' in ph and el.is_displayed():
            return el
    return None


def dialog_of(d, el):
    return d.execute_script(
        "const d = arguments[0].closest('[role=dialog]');"
        "return d ? (d.innerText||'').trim() : '';", el)


def pass_one(d, token, mode):
    info = U.enter(d, token, '/tasks/cherry-picks', mode, timeout=60)
    # 页面就绪：等待合并容器行
    WebDriverWait(d, 60).until(lambda x: x.find_elements(
        By.CSS_SELECTOR, 'button[aria-label="挑选合并任务操作"]'))
    time.sleep(1.5)
    open_cart_and_save_dialog(d)
    time.sleep(1.0)
    inp = save_dialog_input(d)
    assert inp is not None, '另存为挑选集弹窗的输入框未出现'
    txt = dialog_of(d, inp)
    p = U.shot(d, 'w05_save_pick_set_%s' % mode)
    ph = inp.get_attribute('placeholder')
    save_btn = [b for b in d.find_elements(By.TAG_NAME, 'button')
                if b.is_displayed() and b.text.strip() == '保存'
                and d.execute_script(
                    "return !!arguments[0].closest('[role=dialog]')", b)]
    entry = {'theme': mode, 'shot': p, 'dialog_text': txt, 'placeholder': ph,
             'save_disabled_empty': (save_btn[0].get_attribute('disabled')
                                     if save_btn else None),
             'theme_state': info}
    U.close_dialog(d)   # 关另存为
    time.sleep(0.6)
    U.close_dialog(d)   # 关购物车抽屉
    return entry


def main():
    admin = Api()
    admin.login()
    row, created = ensure_user(admin, USER, 'int1934@jiexian.test', PASS)
    assert row, '隔离账号不可用'
    u = Api(user=USER, password=PASS)
    u.login()
    report['user'] = {'id': row['id'], 'created': created}
    t0, _ = cart_total(u)
    report['cart']['start_total'] = t0

    st, d = u.get('/api/v1/tasks/cherry-picks/candidates?per_page=3')
    items = (unwrap(d) or {}).get('items') or []
    assert items, '候选为空，无法加购'
    result_ids = [items[0]['result_id']]
    report['cart']['candidate'] = {k: items[0].get(k) for k in
                                   ('result_id', 'task_id', 'task_name', 'case_name')}
    st, d = u.post('/api/v1/tasks/cherry-picks/cart/items', {'result_ids': result_ids})
    report['cart']['add_status'] = st
    time.sleep(1.0)
    t1, _ = cart_total(u)
    report['cart']['after_add_total'] = t1
    print('cart', t0, '->', t1, report['cart']['candidate'])

    d = U.driver()
    try:
        entry_l = pass_one(d, u.token, 'light')
        time.sleep(1.0)
        entry_d = pass_one(d, u.token, 'dark')
        report['cart_lights'] = {'light': entry_l, 'dark': entry_d, 'ok': True}
        print('[save-pick-set] light', entry_l['theme_state'], '| dark', entry_d['theme_state'])
        print('  text:', entry_l['dialog_text'].replace('\n', ' | ')[:160])
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        report['cart_lights'] = {'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        try:
            d.quit()
        except Exception:
            pass
        # 收尾：清空隔离账号购物车
        st, _ = u.raw('/api/v1/tasks/cherry-picks/cart/items', method='DELETE')
        time.sleep(1.0)
        t2, _ = cart_total(u)
        report['cart']['end_total'] = t2
        report['cart']['clear_status'] = st
        with open(os.path.join(ART, 'cart_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('cart end', t2, 'report →', os.path.join(ART, 'cart_report.json'))


if __name__ == '__main__':
    main()
