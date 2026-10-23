# -*- coding: utf-8 -*-
"""INT-1483 Phase H5：范围约束 min>max 的可见校验证据（发布按钮禁用态 / 是否红字 / aria-invalid）。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'I' + H.RUN_TAG
TYPE = f'itest1483_i_{TAG.lower()}'
NAME = f'接线测试_INT1483_范围_{TAG}'
OUT = {'tag': TAG, 'type': TYPE, 'name': NAME}


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def wtext(text, t=25):
    WebDriverWait(d, t).until(lambda x: text in H.body_text(x))


def save():
    H.save_evidence('phaseH5_range_validation', OUT)


def row_el(code):
    return d.execute_script("""
      var els = Array.prototype.slice.call(document.querySelectorAll("input[aria-label='参数代码']"));
      var t = null;
      for (var k = 0; k < els.length; k++) { if ((els[k].value||'') === arguments[0]) { t = els[k]; break; } }
      return t ? t.closest('tr') : null;
    """, code)


d = H.driver()
try:
    H.login(d)
    H.goto_page(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1)
    d.find_element(By.ID, 'algo-type').send_keys(TYPE)
    d.find_element(By.ID, 'algo-name').send_keys(NAME)
    time.sleep(0.4)

    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 噪声']"))
    time.sleep(1)
    row = row_el('noise_level')
    trig = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '文本':
            trig = t
            break
    H.js_click(d, trig)
    time.sleep(0.7)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.9)

    pub = find("//button[@type='submit' and contains(normalize-space(.), '发布')]")
    OUT['publish_disabled_valid_form'] = not pub.is_enabled()

    # 合法范围先验：0 ~ 10
    mn = d.find_element(By.CSS_SELECTOR, "input[aria-label='最小值']")
    mx = d.find_element(By.CSS_SELECTOR, "input[aria-label='最大值']")
    mn.clear(); mn.send_keys('0')
    mx.clear(); mx.send_keys('10')
    time.sleep(1.2)
    pub = find("//button[@type='submit' and contains(normalize-space(.), '发布')]")
    OUT['publish_disabled_after_valid_range'] = not pub.is_enabled()
    H.shot(d, 'H5_range_valid_light')

    # 非法范围：10 ~ 5
    mn = d.find_element(By.CSS_SELECTOR, "input[aria-label='最小值']")
    mx = d.find_element(By.CSS_SELECTOR, "input[aria-label='最大值']")
    mn.clear(); mn.send_keys('10')
    mx.clear(); mx.send_keys('5')
    time.sleep(1.2)
    pub = find("//button[@type='submit' and contains(normalize-space(.), '发布')]")
    OUT['minmax'] = {
        'publish_disabled': not pub.is_enabled(),
        'min_aria_invalid': d.find_element(By.CSS_SELECTOR, "input[aria-label='最小值']").get_attribute('aria-invalid'),
        'max_aria_invalid': d.find_element(By.CSS_SELECTOR, "input[aria-label='最大值']").get_attribute('aria-invalid'),
        'error_text_present': '最小值不能大于最大值' in H.body_text(d),
        'max_error_text_present': '最大值不能小于最小值' in H.body_text(d),
        'row_text': (row_el('noise_level').text or '')[:200],
        'alerts': [e.text for e in d.find_elements(By.CSS_SELECTOR, "[role='alert']")][:5],
    }
    H.shot(d, 'H5_range_invalid_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'H5_range_invalid_dark')
    H.apply_theme(d, 'light')

    # 直接点禁用按钮：无请求无 toast
    H.clear_fetch_log(d)
    H.js_click(d, pub)
    time.sleep(2)
    OUT['click_disabled_publish'] = {
        'fetches': [(e['method'], e['url'], e['status']) for e in H.fetch_log(d, '/algorithm/definitions')],
        'toasts': [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')],
    }
    save()

    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.9)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
finally:
    try:
        d.quit()
    except Exception:
        pass
