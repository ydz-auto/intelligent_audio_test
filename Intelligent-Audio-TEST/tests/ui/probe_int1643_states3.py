# -*- coding: utf-8 -*-
"""INT-1643 探针 3：分组展开 + 行复选框 + 批量条。"""
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


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        trig = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                     if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None)
        print('trig', trig and trig.text)
        if trig:
            L.js_click(d, trig)
            time.sleep(1.5)
            opts = [(b.text or '').strip() for b in d.find_elements(By.TAG_NAME, 'button') if vis(b)]
            print('options', [o for o in opts if '打断' in o or '全部' in o][:10])
            opt = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                        if vis(b) and (b.text or '').strip() == '打断与恢复'), None)
            if opt:
                L.js_click(d, opt)
                time.sleep(8)
        print('body:', L.body_text(d)[:1500].replace('\n', ' | '))
        hdr = next((e for e in d.find_elements(
            By.XPATH, "//span[normalize-space(.)='打断与恢复']/ancestor::div[contains(@class,'cursor-pointer')][1]")
            if vis(e)), None)
        print('hdr', hdr is not None)
        if hdr:
            L.js_click(d, hdr)
            time.sleep(6)
        cbs = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']") if vis(e)]
        print('checkboxes', len(cbs))
        rows = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='row']") if vis(e)]
        print('rows', len(rows))
        for r in rows[:5]:
            print('ROW', (r.text or '')[:150].replace('\n', ' | '))
        # 编辑按钮
        edits = [e for e in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='编辑用例']") if vis(e)]
        print('edit buttons', len(edits), (edits[0].get_attribute('aria-label') if edits else None))
        L.save_evidence('probe3', {'body': L.body_text(d)[:4000], 'rows': [r.text for r in rows[:10]],
                                   'checkboxes': len(cbs), 'edits': len(edits)})
        L.shot(d, 'probe3_group')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
