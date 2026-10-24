# -*- coding: utf-8 -*-
"""INT-1686 复测（打回项 + 回归）：批量「设置播放设备」Select 闭合态文案。

覆盖：
  1. 批量设置播放设备：选完设备后触发器显示「{设备名} (通道 n) [干声/噪声]」，不显示设备 id；
     浅/深截图；
  2. 回归 1：批量调整分组触发器显示分组名（不显示 UUID）；
  3. 回归 2：批量设置专属参数触发器显示算法中文名 + 同一字段只渲染一个控件；
  4. 回归 3：用例抽屉「关联算法」参数同一字段只出现一次。

前端：旁路容器（本 run dist + 15173 同款 nginx），`REACT_BASE` 可指向任意前端做 A/B。
夹具：临时算法 `wire_test_int1686d`（顶层 fields 与 groups[].fields 同源双份），由
`probe_int1686_fixture.py` 创建、`cleanup_int1686_fixture.py` 删除。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1483_helpers as H  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

ART = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1686r2',
    H.BASE.rstrip('/').rsplit(':', 1)[-1])
os.makedirs(ART, exist_ok=True)

ALGO_TYPE = 'wire_test_int1686d'
ALGO_NAME = '接线测试_验收去重算法1686d'
DUP_FIELD_LABEL = '接线测试阈值'
GROUP_ID = os.environ.get('CASE_GROUP_ID', 'dec6503f-a86e-4b5d-b60e-7f4801b82325')


def log(msg):
    print(msg, flush=True)


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    log('shot -> ' + p)
    return p


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def body_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : "";') or ''


def dialogs(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]')


def top_dialog(drv):
    ds = dialogs(drv)
    return ds[-1] if ds else None


def open_case_page(drv):
    url = H.BASE + '/testcases/by-group'
    if GROUP_ID:
        url += '?group=' + GROUP_ID
    drv.get(url)
    WebDriverWait(drv, 90).until(lambda d: '用例' in body_text(d))
    rows = []
    deadline = time.time() + 90
    while time.time() < deadline:
        rows = [e for e in drv.find_elements(By.CSS_SELECTOR, "div[class*='cursor-pointer']")
                if '条' in text_of(drv, e)]
        if rows:
            break
        time.sleep(2)
    if not rows:
        raise SystemExit('no group row; body=%r' % body_text(drv)[:400])
    js_click(drv, rows[0])
    log('expanded group: %r' % text_of(drv, rows[0])[:30])
    WebDriverWait(drv, 120).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]'))
    time.sleep(1.0)


def select_two_cases(drv):
    boxes = drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
    if not boxes:
        raise SystemExit('no case checkboxes')
    for box in boxes[:2]:
        js_click(drv, box)
        time.sleep(0.4)
    time.sleep(1.0)


def bulk_button(drv, label):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if text_of(drv, b) == label and b.is_displayed():
                return b
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit('bulk button not found: ' + label)


def open_bulk(drv, label):
    js_click(drv, bulk_button(drv, label))
    WebDriverWait(drv, 40).until(lambda d: top_dialog(d) is not None)
    time.sleep(1.0)
    return top_dialog(drv)


def close_top_dialog(drv):
    d = top_dialog(drv)
    if d is None:
        return
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b) == '取消':
            js_click(drv, b)
            break
    else:
        drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
    time.sleep(1.2)


def pick_option(drv, dlg, contains=''):
    """点开弹窗内第一个 combobox，选中 label 含 contains 的选项（空=第一个），返回触发器。"""
    last = None
    for attempt in range(4):
        trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        WebDriverWait(drv, 60).until(lambda d: trig.is_enabled())
        js_click(drv, trig)
        try:
            opt = WebDriverWait(drv, 12).until(
                lambda d: next((o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
                                if o.is_displayed() and contains in text_of(d, o)), None))
            label = text_of(drv, opt)
            js_click(drv, opt)
            time.sleep(1.2)
            trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
            return trig, label
        except Exception as exc:  # noqa: BLE001
            last = exc
            log('pick_option attempt %d failed (options=%d)'
                % (attempt + 1, len(drv.find_elements(By.CSS_SELECTOR, '[role="option"]'))))
            drv.execute_script(
                "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
            time.sleep(1.5)
    raise last if last else RuntimeError('pick_option failed')


def count_text(drv, dlg, needle):
    return len(dlg.find_elements(
        By.XPATH, ".//*[normalize-space(text())='%s']" % needle))


def main():
    ev = {'base': H.BASE}
    drv = H.driver()
    try:
        H.login(drv)
        open_case_page(drv)
        select_two_cases(drv)

        # ---------- 1. 打回项：批量设置播放设备 ----------
        dlg = open_bulk(drv, '批量设置播放设备')
        trig, opt_label = pick_option(drv, dlg)
        shown = text_of(drv, trig)
        ev['device_option_label'] = opt_label
        ev['device_trigger'] = shown
        ev['device_trigger_is_numeric'] = shown.strip().isdigit()
        ev['device_trigger_matches_option'] = shown == opt_label
        log('device trigger = %r (option=%r)' % (shown, opt_label))
        shot(drv, '01_batch_device_light')
        H.apply_theme(drv, 'dark')
        shot(drv, '02_batch_device_dark')
        H.apply_theme(drv, 'light')
        close_top_dialog(drv)

        # ---------- 2. 回归：批量调整分组 ----------
        dlg = open_bulk(drv, '批量调整分组')
        trig, opt_label = pick_option(drv, dlg)
        shown = text_of(drv, trig)
        ev['group_trigger'] = shown
        ev['group_trigger_is_uuid'] = len(shown) == 36 and shown.count('-') == 4
        log('group trigger = %r' % shown)
        shot(drv, '03_batch_group_light')
        H.apply_theme(drv, 'dark')
        shot(drv, '04_batch_group_dark')
        H.apply_theme(drv, 'light')
        close_top_dialog(drv)

        # ---------- 3. 回归：批量设置专属参数（闭合态 + 字段去重） ----------
        dlg = open_bulk(drv, '批量设置专属参数')
        trig, opt_label = pick_option(drv, dlg, ALGO_NAME)
        shown = text_of(drv, trig)
        ev['algo_trigger'] = shown
        log('algo trigger = %r' % shown)
        WebDriverWait(drv, 60).until(lambda d: DUP_FIELD_LABEL in body_text(d))
        time.sleep(0.8)
        dlg = top_dialog(drv)
        ev['batch_dup_count'] = count_text(drv, dlg, DUP_FIELD_LABEL)
        ev['batch_number_inputs'] = len(dlg.find_elements(By.CSS_SELECTOR, 'input[type="number"]'))
        log('batch field count=%d numbers=%d' % (ev['batch_dup_count'], ev['batch_number_inputs']))
        net = H.fetch_log(drv, 'form-schema')
        ev['form_schema'] = [{'url': e['url'], 'status': e['status'],
                              'top_fields': '"fields"' in (e.get('resBody') or ''),
                              'groups': '"groups"' in (e.get('resBody') or '')}
                             for e in net[-2:]]
        shot(drv, '05_batch_params_light')
        H.apply_theme(drv, 'dark')
        shot(drv, '06_batch_params_dark')
        H.apply_theme(drv, 'light')
        close_top_dialog(drv)

        # ---------- 4. 回归：用例抽屉「关联算法」字段去重 ----------
        edit_btn = WebDriverWait(drv, 40).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"))
        js_click(drv, edit_btn[0])
        WebDriverWait(drv, 40).until(lambda d: dialogs(d))
        time.sleep(2.5)
        drawer = dialogs(drv)[-1]
        algo_sel = drawer.find_element(
            By.XPATH, ".//*[normalize-space(text())='关联算法']/ancestor::section[1]//*[@role='combobox']")
        js_click(drv, algo_sel)
        time.sleep(0.8)
        opt = WebDriverWait(drv, 25).until(
            lambda d: next((o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
                            if ALGO_NAME in text_of(d, o)), None))
        js_click(drv, opt)
        WebDriverWait(drv, 60).until(lambda d: DUP_FIELD_LABEL in body_text(d))
        time.sleep(1.0)
        drawer = dialogs(drv)[-1]
        ev['drawer_dup_count'] = count_text(drv, drawer, DUP_FIELD_LABEL)
        log('drawer field count=%d' % ev['drawer_dup_count'])
        shot(drv, '07_drawer_params_light')
        H.apply_theme(drv, 'dark')
        shot(drv, '08_drawer_params_dark')
        H.apply_theme(drv, 'light')
        close_top_dialog(drv)  # 抽屉是 role=dialog；取消关闭，不保存，真实用例不变

        json.dump(ev, open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        log('EVIDENCE ' + json.dumps(ev, ensure_ascii=False))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
