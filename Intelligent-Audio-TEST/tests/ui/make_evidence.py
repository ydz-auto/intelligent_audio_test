# -*- coding: utf-8 -*-
"""证据截图生成（INT-260 验收：负责人抽查 2 条用例的截图证据）。

非测试脚本：复用 UI 层 Page Object 真实跑通两条用例操作流，在关键断言点
落盘截图到 tests/ui/artifacts/evidence/。截图仅作交付证据，不参与门禁。
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 直接脚本运行时 sys.path[0] 是脚本目录（tests/ui），tests.ui.* 会被误判为顶层包；
# 项目根必须插到最前
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # tests 包以仓库根为基准导入（pytest conftest 同口径）

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.test_case_page import TestCasePage
from tests.ui.utils.api_client import ApiClient, unique_suffix

FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:6273')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:6000')
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'artifacts', 'evidence')
# __file__ = tests/ui/make_evidence.py → 上一级即 tests/ui/，artifacts 挂在其下

import httpx  # noqa: E402
body = httpx.get(f'{API}/health', timeout=5, trust_env=False).json()
assert body.get('database') == 'intelligent_audio_test_test', f'非隔离库: {body}'

os.makedirs(OUT, exist_ok=True)
api = ApiClient(API)
api.login('admin', os.environ.get('UI_TEST_PASSWORD', 'admin123'))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from tests.ui.conftest import _resolve_chromedriver

options = Options()
options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
options.add_argument('--headless=new')
options.add_argument('--window-size=1600,1000')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
drv = webdriver.Chrome(options=options, service=Service(executable_path=_resolve_chromedriver()))
drv.set_page_load_timeout(45)

try:
    # ── 证据 1：真实登录操作流（表单输入 → 提交 → 跳转首页）──────────
    drv.get(f'{FRONTEND}/#/login')
    WebDriverWait(drv, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
    user_input = WebDriverWait(drv, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.login-card form input[type="text"]')))
    user_input.clear(); user_input.send_keys('admin')
    pw = drv.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
    pw.clear(); pw.send_keys(os.environ.get('UI_TEST_PASSWORD', 'admin123'))
    drv.save_screenshot(os.path.join(OUT, 'evidence_1_login_form_filled.png'))
    drv.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url.split('#')[-1])
    WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.main-content')))
    ActionChains(drv).move_to_element(drv.find_element(By.CSS_SELECTOR, '.sidebar')).perform()
    WebDriverWait(drv, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.sidebar-footer .user-name')))
    drv.save_screenshot(os.path.join(OUT, 'evidence_1_login_redirected_home.png'))
    print('[OK] 证据1：登录表单填写 → 提交 → 跳转首页（2 张）')

    # ── 证据 2：视图切换（分组视图自建用例可见 ↔ 切标签视图仍可见）────
    suffix = unique_suffix()
    group_name = f'ui260_ev_{suffix}'
    tag_name = f'ui260_evtag_{suffix}'
    gid = api.create_group(group_name)
    cid = api.create_testcase(f'ui260_证据用例_{suffix}', group=group_name, tags=[tag_name])
    tc = TestCasePage(drv, FRONTEND)
    tc.goto('/TestCaseManager')
    tc.wait_loaded(25)
    tc._exhaust_load_more()
    tc.wait_visible('.single-column-layout .category-card', 15)
    # 滚动到自建分组卡并展开，用例名入镜
    for card in drv.find_elements(By.CSS_SELECTOR, '.category-card'):
        title = card.find_element(By.CSS_SELECTOR, '.category-title').text.strip()
        if title == group_name:
            drv.execute_script('arguments[0].scrollIntoView({block: "center"});', card)
            drv.execute_script('arguments[0].click();', card.find_element(By.CSS_SELECTOR, '.category-header'))
            break
    WebDriverWait(drv, 10).until(
        lambda d: any(f'ui260_证据用例_{suffix}' in el.text
                      for el in d.find_elements(By.CSS_SELECTOR, '.case-name')))
    drv.save_screenshot(os.path.join(OUT, 'evidence_2_group_view_with_case.png'))
    tc.switch_view('tag')
    WebDriverWait(drv, 15).until(
        lambda d: any(tag_name in c.text for c in d.find_elements(By.CSS_SELECTOR, '.category-title')))
    # 展开自建标签卡并滚动入镜，用例名可见
    for card in drv.find_elements(By.CSS_SELECTOR, '.category-card'):
        title = card.find_element(By.CSS_SELECTOR, '.category-title').text.strip()
        if title == tag_name:
            drv.execute_script('arguments[0].scrollIntoView({block: "center"});', card)
            drv.execute_script('arguments[0].click();', card.find_element(By.CSS_SELECTOR, '.category-header'))
            break
    WebDriverWait(drv, 10).until(
        lambda d: any(f'ui260_证据用例_{suffix}' in el.text
                      for el in d.find_elements(By.CSS_SELECTOR, '.case-name')))
    drv.save_screenshot(os.path.join(OUT, 'evidence_2_tag_view_with_case.png'))
    print('[OK] 证据2：分组视图自建用例可见 → 切标签视图仍可见（2 张）')

    api.delete_testcase(cid)
    api.request('DELETE', f'/groups/{gid}')
    import psycopg2
    conn = psycopg2.connect(
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test_test',
        connect_timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT id FROM tags WHERE name=%s AND deleted=false", (tag_name,))
    for (tid,) in cur.fetchall():
        try: api.request('DELETE', f'/tags/{tid}')
        except Exception: pass
    conn.close()
    print('[OK] 证据用例已自清')
finally:
    drv.quit()

print('DONE ->', OUT)
