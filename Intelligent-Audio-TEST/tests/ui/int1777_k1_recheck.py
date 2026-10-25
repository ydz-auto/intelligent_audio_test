# -*- coding: utf-8 -*-
"""INT-1777 定点复测：取消 / 关闭后再打开，弹窗是否残留上次输入（K1 复核）。

自建 API 用接口前置，复测后删除；不动真实记录。
"""
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
NAME = '接线测试_INT1777_残留复核'


def dlg(drv):
    ds = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]
    return ds[-1] if ds else None


def by_id(drv, ident):
    return dlg(drv).find_element(By.ID, ident)


def fill(el, text):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    if text == '':
        el.send_keys(Keys.BACKSPACE)
    else:
        el.send_keys(text)
    time.sleep(0.3)


def click_btn(drv, text):
    for b in dlg(drv).find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            L.js_click(drv, b)
            return True
    return False


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
        raise RuntimeError('card not found: %s' % name)
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
    try:
        L.login(d)
        d.get(L.BASE + '/start-test')
        time.sleep(5)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        L.js_click(d, steps[0])
        time.sleep(3.5)

        # 前置：找现成算法名
        st, p, _ = L.api_json(d, '/algorithms?page=1&page_size=20')
        algos = (((p or {}).get('data') or {}).get('items') or []) if p else []
        algo = (algos[0].get('algorithm_name') or algos[0].get('name')) if algos else 'voice_llm'
        st, p, raw = L.api_json(d, '/apis', 'POST', {
            'name': NAME, 'algorithm_type': algo,
            'endpoints': [{'endpoint': 'https://api.example.com/v1/asr', 'name': '主', 'priority': 1,
                           'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60}],
            'meta': {'method': 'POST'},
        })
        print('create', st, raw[:160])
        st, p, _ = L.api_json(d, '/apis?page=1&page_size=200')
        for it in (((p or {}).get('data') or {}).get('items') or []):
            if it.get('name') == NAME:
                api_id = it['id']
        print('api_id', api_id)

        # 列表快照刷新（接口建的，页面未 invalidate）
        d.get(L.BASE + '/start-test')
        time.sleep(5)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        L.js_click(d, steps[0])
        time.sleep(4)

        # 第一次打开
        open_edit(d, NAME)
        base_name = by_id(d, 'api-name').get_attribute('value')
        base_desc = by_id(d, 'api-desc').get_attribute('value')
        print('BASE', repr(base_name), repr(base_desc))
        fill(by_id(d, 'api-name'), '不该保存的名字')
        fill(by_id(d, 'api-desc'), '不该保存的描述')
        click_btn(d, '取消')
        time.sleep(1.5)
        closed = not (dlg(d) and '编辑 API' in (dlg(d).text or ''))
        print('closed after cancel', closed)

        # 再次打开同一 API
        open_edit(d, NAME)
        re_name = by_id(d, 'api-name').get_attribute('value')
        re_desc = by_id(d, 'api-desc').get_attribute('value')
        print('REOPEN', repr(re_name), repr(re_desc))
        print('RESIDUE', re_name != base_name or re_desc != base_desc)

        # 追加场景：改成别的 API 再打开（同组件实例）
        L.shot(d, 'k1_reopen_residue')
        click_btn(d, '取消')
        time.sleep(1.2)

        out = {
            'base_name': base_name, 'base_desc': base_desc,
            'reopen_name': re_name, 'reopen_desc': re_desc,
            'closed_after_cancel': closed,
            'residue': re_name != base_name or re_desc != base_desc,
        }
        L.save_evidence('k1_recheck', out)
        print(json.dumps(out, ensure_ascii=False))
    finally:
        try:
            if api_id:
                print('cleanup', L.api_json(d, '/apis/%s' % api_id, 'DELETE')[0])
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()
