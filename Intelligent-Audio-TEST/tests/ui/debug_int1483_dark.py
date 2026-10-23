# -*- coding: utf-8 -*-
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import int1483_helpers as H

def find(xp, t=15):
    return WebDriverWait(d, t).until(lambda x: x.find_element(By.XPATH, xp))

d = H.driver()
try:
    H.login(d); H.goto_page(d)
    H.apply_theme(d, 'dark')
    # 导入弹窗（深色）
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")); time.sleep(0.5)
    H.click_menuitem(d, '导入算法'); time.sleep(1)
    H.shot(d, 'D1_import_dialog_dark')
    d.find_element(By.TAG_NAME, 'body').send_keys('\ue00c'); time.sleep(0.8)
    # 删除确认（深色）
    H.open_row_menu(d, '小艺语音大模型'); H.click_menuitem(d, '删除'); time.sleep(1)
    H.shot(d, 'A5_delete_confirm_dark')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]")); time.sleep(0.6)
    # 分组管理（深色，含一行数据）
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")); time.sleep(0.5)
    H.click_menuitem(d, '分组管理'); WebDriverWait(d, 15).until(lambda x: '算法分组管理' in H.body_text(x)); time.sleep(0.8)
    if '暂无分组' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '新建分组')]"))
        WebDriverWait(d, 15).until(lambda x: x.find_elements(By.ID, 'group-name'))
        d.find_element(By.ID, 'group-name').send_keys('接线测试_INT1483_深色分组')
        d.find_element(By.ID, 'group-order').clear()
        d.find_element(By.ID, 'group-order').send_keys('2')
        H.js_click(d, find("//form//button[@type='submit']")); time.sleep(3)
    H.shot(d, 'C6_group_rows_dark')
    print('TEXT', H.body_text(d)[-400:])
    # 清掉这个深色截图用分组
    for b in d.find_elements(By.XPATH, "//button[starts-with(@aria-label,'删除分组 接线测试_INT1483_深色分组')]"):
        H.js_click(d, b); time.sleep(0.8)
        H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]")); time.sleep(2)
    H.apply_theme(d, 'light')
finally:
    d.quit()
