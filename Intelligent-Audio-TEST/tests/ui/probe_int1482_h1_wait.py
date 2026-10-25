# -*- coding: utf-8 -*-
"""INT-1482 补图轮探针 2：等用例卡渲染后再看按钮 / 徽标 / 打开详情与抽屉。"""
import json
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

RID = sys.argv[1] if len(sys.argv) > 1 else '484'
d = L.driver()
try:
    L.login(d)
    t0 = time.time()
    d.get(L.BASE + '/report/%s' % RID)
    WebDriverWait(d, 90).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
    end = time.time() + 180
    n_detail = 0
    while time.time() < end:
        time.sleep(3)
        btns = [b for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='详情']") if b.is_displayed()]
        n_detail = len(btns)
        if n_detail:
            break
    info = {'wait_seconds': round(time.time() - t0, 1), 'detail_buttons': n_detail}
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    info['badges'] = len([b for b in root.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']") if b.is_displayed()])
    info['root_text_head'] = (root.text or '')[:400]
    info['visible_dialogs'] = []
    for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        try:
            if dl.is_displayed():
                info['visible_dialogs'].append((dl.text or '')[:120])
        except Exception:
            pass
    if n_detail:
        d.execute_script("arguments[0].click();", btns[0])
        time.sleep(3)
        info['after_detail_dialogs'] = []
        for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
            try:
                if dl.is_displayed():
                    info['after_detail_dialogs'].append((dl.text or '')[:500])
            except Exception:
                pass
        d.save_screenshot('tests/ui/artifacts/int1482/probe_rid%s_detail.png' % RID)
        # close
        from selenium.webdriver.common.keys import Keys
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
        # badge → drawer
        badges = [b for b in root.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']") if b.is_displayed()]
        if badges:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", badges[0])
            d.execute_script("arguments[0].click();", badges[0])
            time.sleep(4)
            info['after_badge_dialogs'] = []
            for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
                try:
                    if dl.is_displayed():
                        info['after_badge_dialogs'].append((dl.text or '')[:600])
                except Exception:
                    pass
            d.save_screenshot('tests/ui/artifacts/int1482/probe_rid%s_drawer.png' % RID)
    print(json.dumps(info, ensure_ascii=False, indent=1))
finally:
    d.quit()
