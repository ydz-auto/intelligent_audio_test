# -*- coding: utf-8 -*-
"""INT-1480 探针：确认开关/确认弹窗/抽屉表单结构的真实 DOM。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By
from verify_int1480_device_modals import _driver, _goto, _body, _wait_text, _jsclick, _menu_item

drv = _driver()
try:
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    print('--- role=switch ---')
    for el in drv.find_elements(By.XPATH, "//*[@role='switch']"):
        print(el.get_attribute('outerHTML')[:300])
    print('--- aria-label contains 告警 ---')
    for el in drv.find_elements(By.XPATH, "//*[contains(@aria-label,'告警')]"):
        print(el.tag_name, el.get_attribute('aria-label'), (el.get_attribute('outerHTML') or '')[:200])
    print('--- 监控 text nodes ---')
    print('监控告警面板' in _body(drv))

    # 抽屉结构
    for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
        if b.is_displayed():
            _jsclick(drv, b)
            break
    _wait_text(drv, '测试设备信息', 10)
    time.sleep(1)
    print('--- inputs in drawer ---')
    for el in drv.find_elements(By.XPATH, "//input"):
        if el.is_displayed():
            print(repr(el.get_attribute('placeholder')), el.get_attribute('type'), el.get_attribute('id'),
                  (el.get_attribute('aria-label') or ''))
    print('--- labels ---')
    for el in drv.find_elements(By.XPATH, "//label"):
        if el.is_displayed():
            print(repr(el.text), el.get_attribute('for'))
    print('--- comboboxes ---')
    for el in drv.find_elements(By.XPATH, "//*[@role='combobox']"):
        print(el.tag_name, el.get_attribute('aria-label'), el.text[:40], el.get_attribute('aria-expanded'))
    print('--- buttons in drawer ---')
    for el in drv.find_elements(By.XPATH, "//button"):
        if el.is_displayed() and el.text.strip():
            print(repr(el.text.strip()[:30]), el.get_attribute('type'), el.get_attribute('aria-label'))
finally:
    drv.quit()
