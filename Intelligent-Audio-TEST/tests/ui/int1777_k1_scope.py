# -*- coding: utf-8 -*-
"""INT-1777 追加取证：取消后重开的残留范围（新增态 / 请求模板草稿 / 设备类型）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

L.BASE = 'http://127.0.0.1:15277'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1777')
NAME = '接线测试_INT1777_残留范围'


def dlg(drv):
    ds = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]
    return ds[-1] if ds else None


def by_id(drv, ident):
    return dlg(drv).find_element(By.ID, ident)


def combos(drv):
    return dlg(drv).find_elements(By.CSS_SELECTOR, "[role='combobox']")


def combo_text(drv, i):
    return (combos(drv)[i].text or '').strip()


def fill(el, text):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.BACKSPACE if text == '' else text)
    time.sleep(0.3)


def click_btn(drv, text):
    for b in dlg(drv).find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            L.js_click(drv, b)
            return True
    return False


def tab_click(drv, label):
    for t in dlg(drv).find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (t.text or '').strip() == label:
            L.js_click(drv, t)
            time.sleep(0.5)
            return


def pick(drv, idx, text):
    L.js_click(drv, combos(drv)[idx])
    time.sleep(0.7)
    for o in [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]:
        if (o.text or '').strip() == text:
            L.js_click(drv, o)
            time.sleep(0.5)
            return True
    return False


def open_new(drv):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and (b.text or '').strip() == '新增 API':
            L.js_click(drv, b)
            break
    for _ in range(20):
        time.sleep(0.5)
        d = dlg(drv)
        if d and '新增 API' in (d.text or ''):
            return d
    raise RuntimeError('new dialog not open')


def find_card(drv, name):
    for _ in range(8):
        try:
            cards = [c for c in drv.find_elements(By.CSS_SELECTOR, 'div')
                     if c.is_displayed() and name in (c.text or '') and len(c.text or '') < 800]
            if cards:
                cards.sort(key=lambda c: len(c.text or ''))
                return cards[0]
            return None
        except Exception:
            time.sleep(0.5)
    return None


def open_edit(drv, name):
    card = find_card(drv, name)
    if card is None:
        raise RuntimeError('card not found')
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
    time.sleep(0.4)
    more = None
    for b in card.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']"):
        more = b
    if more is None:
        parent = card
        for _ in range(4):
            parent = parent.find_element(By.XPATH, '..')
            ms = parent.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']")
            if ms:
                more = ms[0]
                break
    L.js_click(drv, more)
    time.sleep(0.8)
    for i in [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if e.is_displayed()]:
        if (i.text or '').strip() == '编辑':
            L.js_click(drv, i)
            break
    for _ in range(20):
        time.sleep(0.5)
        d = dlg(drv)
        if d and '编辑 API' in (d.text or ''):
            return d
    raise RuntimeError('edit dialog not open')


def main():
    d = L.driver()
    api_id = None
    out = {}
    try:
        L.login(d)
        d.get(L.BASE + '/start-test')
        time.sleep(5)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        L.js_click(d, steps[0])
        time.sleep(3.5)

        # ---- 新增态：填 → 取消 → 再新增 ----
        open_new(d)
        fill(by_id(d, 'api-name'), '新增态残留名字')
        fill(by_id(d, 'api-desc'), '新增态残留描述')
        pick(d, 2, '48000 Hz')
        L.js_click(d, combos(d)[1])
        time.sleep(0.7)
        for o in [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]:
            if 'Realtime WS' in (o.text or ''):
                L.js_click(d, o)
                break
        time.sleep(0.5)
        click_btn(d, '取消')
        time.sleep(1.5)
        open_new(d)
        out['new_name'] = by_id(d, 'api-name').get_attribute('value')
        out['new_desc'] = by_id(d, 'api-desc').get_attribute('value')
        out['new_sample_rate'] = combo_text(d, 2)
        out['new_device_type'] = combo_text(d, 1)
        out['default_tab_selected'] = [
            (t.text or '').strip() for t in dlg(d).find_elements(By.CSS_SELECTOR, "[role='tab']")
            if t.get_attribute('aria-selected') == 'true']
        print('NEW-REOPEN', json.dumps(out, ensure_ascii=False))
        click_btn(d, '取消')
        time.sleep(1.2)

        # ---- 编辑态：改请求模板 → 取消 → 重开，看 meta 草稿是否复位 ----
        st, p, _ = L.api_json(d, '/algorithms?page=1&page_size=20')
        algos = (((p or {}).get('data') or {}).get('items') or []) if p else []
        algo = (algos[0].get('algorithm_name') or algos[0].get('name')) if algos else 'voice_llm'
        st, p, raw = L.api_json(d, '/apis', 'POST', {
            'name': NAME, 'algorithm_type': algo,
            'endpoints': [{'endpoint': 'https://api.example.com/v1/asr', 'name': '主', 'priority': 1,
                           'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60}],
            'meta': {'method': 'POST', 'vendor_adapter': 'HttpApiAdapter'},
        })
        st, p, _ = L.api_json(d, '/apis?page=1&page_size=200')
        for it in (((p or {}).get('data') or {}).get('items') or []):
            if it.get('name') == NAME:
                api_id = it['id']
        d.get(L.BASE + '/start-test')
        time.sleep(5)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        L.js_click(d, steps[0])
        time.sleep(4)

        open_edit(d, NAME)
        tab_click(d, '请求模板')
        base_body = by_id(d, 'meta-body-template').get_attribute('value')
        base_method = combo_text(d, 0)
        base_vendor = by_id(d, 'meta-vendor-adapter').get_attribute('value')
        fill(by_id(d, 'meta-body-template'), '{"garbage":true}')
        fill(by_id(d, 'meta-vendor-adapter'), 'BAD_ADAPTER')
        pick(d, 0, 'DELETE')
        click_btn(d, '取消')
        time.sleep(1.5)
        open_edit(d, NAME)
        tab_click(d, '请求模板')
        out['meta_base'] = {'body': base_body, 'method': base_method, 'vendor': base_vendor}
        out['meta_reopen'] = {
            'body': by_id(d, 'meta-body-template').get_attribute('value'),
            'method': combo_text(d, 0),
            'vendor': by_id(d, 'meta-vendor-adapter').get_attribute('value'),
        }
        out['meta_residue'] = out['meta_reopen'] != out['meta_base']
        print('META-REOPEN', json.dumps(out, ensure_ascii=False))
        L.shot(d, 'k1_scope_meta')
        click_btn(d, '取消')
        time.sleep(1.0)
        L.save_evidence('k1_scope', out)
    finally:
        try:
            if api_id:
                print('cleanup', L.api_json(d, '/apis/%s' % api_id, 'DELETE')[0])
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()
