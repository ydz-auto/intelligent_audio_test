# -*- coding: utf-8 -*-
"""INT-892 复测补充：深色主题下草稿恢复实证截图（草稿保存 → 落库 → 重开恢复 → 深色截图 → 清理）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_ui_32_int892_algorithm_modals as T

from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

draft_type = f'itest892_draft_dark_{T.RUN_TAG}'
draft_name = f'接线测试_INT892_草稿深色_{T.RUN_TAG}'

T._api_create_algorithm(draft_type, draft_name)
drv = T._driver()
try:
    T._goto(drv, '/login')
    try:
        drv.execute_script("window.localStorage.clear()")
    except Exception:
        pass
    T._goto(drv, '/login')
    # 深色主题：直接写 storage key（iatp:theme:v1:mode）+ about:blank 打断 bfcache 强刷
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    drv.get('about:blank')
    T._goto(drv, '/AlgorithmConfig')
    T._wait_list_ready(drv)
    T._search_algo(drv, draft_name)
    T._open_row_menu(drv, draft_name)
    T._click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in T._body_text(drv))
    time.sleep(1.2)
    # 改名称 → 变脏 → 手动保存草稿（真实 PUT /definitions/draft）
    T._edit_field(drv, "//input[@id='algo-name']", draft_name + '_draft')
    T._js_click(drv, "//button[normalize-space()='保存草稿']")
    WebDriverWait(drv, 8).until(lambda d: '草稿已保存' in T._body_text(d))
    T._close_sheet(drv)
    # 后端落库实证
    d = T._api_get(f'/algorithm/definitions/draft/{draft_type}')
    assert d['data'].get('name') == draft_name + '_draft', f'深色链路草稿应落库，实际 {d}'
    # 重开编辑 → 草稿恢复（深色）
    T._search_algo(drv, draft_name)
    T._open_row_menu(drv, draft_name)
    T._click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in T._body_text(drv))
    time.sleep(1.2)
    name_val = drv.find_element(T.By.XPATH, "//input[@id='algo-name']").get_attribute('value')
    assert name_val == draft_name + '_draft', f'深色重开应恢复草稿名，实际 {name_val}'
    assert '该算法存在未发布的草稿' in T._body_text(drv), '深色重开应显示未发布草稿横幅'
    T._screenshot(drv, '10_draft_restored_dark')
    print(f'OK dark draft-restored screenshot captured, type={draft_type}')
finally:
    try:
        T._api_clear_draft(draft_type)
    except Exception:
        pass
    try:
        T._api_delete_algorithm(draft_type)
    except Exception:
        pass
    try:
        drv.quit()
    except Exception:
        pass
