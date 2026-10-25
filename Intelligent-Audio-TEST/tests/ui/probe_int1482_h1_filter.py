# -*- coding: utf-8 -*-
"""INT-1482 补图轮探针 3：用例名称筛选 + 定位目标用例卡（抽屉目标用例）。"""
import json
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

RID = sys.argv[1] if len(sys.argv) > 1 else '387'
NAME = sys.argv[2] if len(sys.argv) > 2 else '测试用例_DD197'
d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/report/%s' % RID)
    WebDriverWait(d, 90).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
    end = time.time() + 180
    while time.time() < end:
        if [b for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='详情']") if b.is_displayed()]:
            break
        time.sleep(3)
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    info = {'inputs': [{'ph': i.get_attribute('placeholder'), 'type': i.get_attribute('type'),
                        'id': i.get_attribute('id')} for i in root.find_elements(By.TAG_NAME, 'input')[:10]],
            'badges_before': len([b for b in root.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']") if b.is_displayed()]),
            'text_head': (root.text or '')[:300]}
    # 找第一个文本输入框写名称
    inp = None
    for i in root.find_elements(By.TAG_NAME, 'input'):
        if (i.get_attribute('type') or 'text') == 'text':
            inp = i
            break
    info['input_used_placeholder'] = inp.get_attribute('placeholder') if inp else None
    if inp:
        d.execute_script("""
          const el = arguments[0], v = arguments[1];
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', {bubbles: true}));
        """, inp, NAME)
        time.sleep(1)
        for b in root.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '应用筛选' and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(6)
        info['text_after_filter'] = (root.text or '')[:500]
        info['badges_after'] = len([b for b in root.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']") if b.is_displayed()])
        info['details_after'] = len([b for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='详情']") if b.is_displayed()])
    d.save_screenshot('tests/ui/artifacts/int1482/probe_filter_%s.png' % RID)
    print(json.dumps(info, ensure_ascii=False, indent=1))
finally:
    d.quit()
