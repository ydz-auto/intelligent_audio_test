# -*- coding: utf-8 -*-
"""INT-1643 探针 4：批量七窗结构 + 抽屉结构。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15933')

from selenium.webdriver.common.by import By


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def enter_group(d):
    trig = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                 if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None)
    L.js_click(d, trig)
    time.sleep(1.5)
    opt = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                if vis(b) and (b.text or '').strip() == '打断与恢复'), None)
    L.js_click(d, opt)
    time.sleep(8)
    hdr = next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='打断与恢复']/ancestor::div[contains(@class,'cursor-pointer')][1]")
        if vis(e)), None)
    if hdr:
        L.js_click(d, hdr)
        time.sleep(6)


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        enter_group(d)
        cbs = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']") if vis(e)]
        print('cbs', len(cbs))
        for i, c in enumerate(cbs[:5]):
            print('cb', i, c.get_attribute('aria-label'), c.get_attribute('data-state'))
        picked = 0
        for c in cbs:
            lab = (c.get_attribute('aria-label') or '')
            if '全选' in lab or '选择' in lab and '行' not in lab:
                continue
            L.js_click(d, c)
            picked += 1
            time.sleep(0.4)
            if picked == 3:
                break
        time.sleep(2)
        print('body after select:', L.body_text(d)[-400:].replace('\n', ' | '))
        btns = {}
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if not vis(b):
                continue
            t = (b.text or '').strip()
            if t.startswith('批量') or t in ('清除选择', '复制', '删除'):
                btns[t] = b
        print('bulk buttons', list(btns.keys()))
        data = {'bulk_buttons': list(btns.keys())}
        for label in ['批量调整分组', '批量设置专属参数', '批量设置播放设备', '批量设置声压级',
                      '批量设置评估维度', '批量管理标签', '批量设置噪声']:
            b = btns.get(label)
            if not b:
                data[label] = 'NO_BUTTON'
                print(label, 'NO_BUTTON')
                continue
            L.js_click(d, b)
            time.sleep(3.5)
            dlg = next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(x)), None)
            if dlg is None:
                data[label] = 'NO_DIALOG'
                print(label, 'NO_DIALOG')
                continue
            txt = dlg.text
            btns_in = [(x.text or '').strip() for x in dlg.find_elements(By.TAG_NAME, 'button') if vis(x)]
            data[label] = {'text': txt[:1200], 'buttons': btns_in}
            print('===', label, '===')
            print(txt[:700].replace('\n', ' | '))
            print('buttons', btns_in)
            L.shot(d, 'probe4_' + label)
            # 关闭
            esc = d.find_element(By.TAG_NAME, 'body')
            esc.send_keys('')
            time.sleep(1.2)
        L.save_evidence('probe4', data)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
