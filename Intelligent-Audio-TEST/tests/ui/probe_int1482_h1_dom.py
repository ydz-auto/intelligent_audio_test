# -*- coding: utf-8 -*-
"""INT-1482 补图轮探针：报告详情页结构（可见对话框 / 用例卡按钮 / 复核徽标）。"""
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
    d.get(L.BASE + '/report/%s' % RID)
    WebDriverWait(d, 60).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
    time.sleep(3)
    info = {}
    info['url'] = d.current_url
    info['dialogs_on_load'] = []
    for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        try:
            info['dialogs_on_load'].append({'shown': dl.is_displayed(), 'text': (dl.text or '')[:200]})
        except Exception:
            pass
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    info['root_text_head'] = (root.text or '')[:600]
    info['buttons'] = []
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if not b.is_displayed():
                continue
            info['buttons'].append({'t': (b.text or '')[:30], 'aria': b.get_attribute('aria-label'),
                                    'expanded': b.get_attribute('aria-expanded')})
        except Exception:
            pass
    info['badges'] = len(root.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']"))
    info['cards_texts'] = [e.text[:120] for e in root.find_elements(By.CSS_SELECTOR, 'li')][:8]
    print(json.dumps(info, ensure_ascii=False, indent=1))
finally:
    d.quit()
