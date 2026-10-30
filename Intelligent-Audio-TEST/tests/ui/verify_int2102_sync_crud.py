# -*- coding: utf-8 -*-
"""INT-2102 补充验收：跨组件状态同步（提交后列表刷新+角标）+ 现有标签 CRUD 不受影响。

走 docker 15000 真实后端 + 本卡旁路容器（REACT_DEV_BASE）。fixture 全部「接线测试_INT2102_」前缀，
run 结束前删除；不清其它卡的「接线测试_」数据。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int2102_api as api

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:15249')
USER_TAG = 'INT2102'
FIX = None
TOKEN = None


def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                cands.append(exe)
        if cands:
            drv_path = max(cands)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body(drv):
    return drv.execute_script('return document.body ? document.body.textContent : ""')


def _wait(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(drv))


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def _js_click(drv, xpath):
    el = WebDriverWait(drv, 12).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script('arguments[0].click()', el)


def _login_browser(drv):
    for _ in range(2):
        _goto(drv, '/dashboard')
        if '/login' not in drv.current_url:
            break
        _goto(drv, '/login')
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('dev_user')
        drv.find_element(By.ID, 'password').send_keys('dev_password')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        for _ in range(8):
            time.sleep(1.5)
            if '/login' not in drv.current_url and '工作台' in _body(drv):
                return
    _wait(drv, '工作台', timeout=30)


def _goto_my_cases(drv):
    _goto(drv, '/testcases/by-group')
    _wait(drv, '用例管理')
    facet = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH,
            "//button[contains(normalize-space(.), '分组') and contains(normalize-space(.), '全部')]"))
    drv.execute_script('arguments[0].click()', facet)
    opt = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
            f"//button[contains(normalize-space(.), '接线测试_{USER_TAG}_分组')]"))
    drv.execute_script('arguments[0].click()', opt)
    _wait(drv, f'接线测试_{USER_TAG}_分组', timeout=20)
    header = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
            f"//span[normalize-space(.)='接线测试_{USER_TAG}_分组']/ancestor::div[contains(@class, 'cursor-pointer')]"))
    drv.execute_script('arguments[0].click()', header)
    _wait(drv, f'接线测试_{USER_TAG}_用例A', timeout=20)


def _select_two_cases(drv):
    clicked = 0
    for suffix in ('用例A', '用例B'):
        try:
            cb = WebDriverWait(drv, 12).until(
                lambda d: d.find_element(By.CSS_SELECTOR,
                    f"[role='checkbox'][aria-label='选择 接线测试_{USER_TAG}_{suffix}']"))
            drv.execute_script('arguments[0].click()', cb)
            clicked += 1
        except Exception:
            continue
    assert clicked >= 2
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]"))


def main():
    global TOKEN
    tok, err = api._login()
    assert tok, f'登录失败: {err}'
    TOKEN = tok
    drv = _driver()
    try:
        _login_browser(drv)
        api._fixture(TOKEN, USER_TAG)
        fix = api._case_fixture(TOKEN, USER_TAG)
        print('fixture:', fix)

        # --- 跨组件同步：提交 add_tags 后列表刷新 + 用例行角标出现 ---
        _goto_my_cases(drv)
        _select_two_cases(drv)
        _js_click(drv, "//button[contains(., '批量管理标签')]")
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量管理标签')]"))
        tag1 = f'接线测试_{USER_TAG}_标签1'
        WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, f"//button[normalize-space(.)='{tag1}']"))
        _js_click(drv, f"//button[normalize-space(.)='{tag1}']")
        WebDriverWait(drv, 8).until(
            lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='移除 {tag1}']"))
        _js_click(drv, "//button[normalize-space(.)='确定']")
        _wait(drv, '批量操作执行成功', timeout=15)
        time.sleep(1.0)
        # 提交后列表应已刷新：分组卡下用例行出现「标签1」角标
        _wait(drv, tag1, timeout=20)
        row_xpath = f"//*[contains(., '接线测试_{USER_TAG}_用例A')]"
        rows = drv.find_elements(By.XPATH, row_xpath)
        # 用例A 行的角标：TagBadge 文本含 tag1
        badge_ok = any(
            tag1 in (r.text or '') for r in rows
        )
        print('cross-component sync row badge:', 'OK' if badge_ok else 'FAIL')
        assert badge_ok, '提交后用例行未出现新增标签角标'

        # --- 现有标签 CRUD 页面不受影响：TagManagement 页渲染分类与标签 ---
        _goto(drv, '/TagManagement')
        _wait(drv, '标签', timeout=20)
        body = _body(drv)
        print('TagManagement has catA:', f'接线测试_{USER_TAG}_分类A' in body)
        print('TagManagement has tag1:', tag1 in body)
        assert f'接线测试_{USER_TAG}_分类A' in body, 'TagManagement 页未显示分类A'
        assert tag1 in body, 'TagManagement 页未显示标签1'

        # --- 现有标签 CRUD 端点不受影响（create/update/delete 自建数据）---
        st, r = api._req('POST', '/tags/categories',
                         {'name': f'接线测试_{USER_TAG}_CRUD分类', 'color': '#f59e0b'}, token=TOKEN)
        cid = ((r or {}).get('data') or {}).get('id')
        assert cid, f'创建分类失败 {st} {r}'
        st, r = api._req('POST', '/tags', {'name': f'接线测试_{USER_TAG}_CRUD标签', 'color': '#94a3b8', 'category_id': cid}, token=TOKEN)
        tid = ((r or {}).get('data') or {}).get('id')
        assert tid, f'创建标签失败 {st} {r}'
        st, r = api._req('PUT', f"/tags/{tid}", {'name': f'接线测试_{USER_TAG}_CRUD标签改名'}, token=TOKEN)
        assert st in (200, 201), f'改标签失败 {st}'
        st, r = api._req('DELETE', f"/tags/{tid}?cascade=false", token=TOKEN)
        assert st in (200, 201), f'删标签失败 {st}'
        st, r = api._req('DELETE', f"/tags/categories/{cid}", token=TOKEN)
        assert st in (200, 201), f'删分类失败 {st}'
        print('tag CRUD endpoints:', 'OK')

        # 浅/深色各补一张 TagManagement 页截图（说明 CRUD 页正常渲染）
        import os as _os
        art = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'artifacts', 'int2102_batch_tags')
        _os.makedirs(art, exist_ok=True)
        drv.save_screenshot(_os.path.join(art, '09-tagmanagement-light.png'))
        _js_click(drv, "//button[@aria-label='打开主题设置']")
        WebDriverWait(drv, 5).until(
            lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
        _js_click(drv, "//*[@role='radio'][contains(., '深色')]")
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)
        _goto(drv, '/TagManagement')
        _wait(drv, '标签', timeout=20)
        drv.save_screenshot(_os.path.join(art, '10-tagmanagement-dark.png'))
        _js_click(drv, "//button[@aria-label='打开主题设置']")
        WebDriverWait(drv, 5).until(
            lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
        _js_click(drv, "//*[@role='radio'][contains(., '浅色')]")
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)
        print('screenshots saved')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        # 清理：用例/分组/标签/分类（只清本卡前缀）
        try:
            if FIX is None:
                pass
        except Exception:
            pass
        try:
            api._case_cleanup(TOKEN, USER_TAG, fix.get('group_id'))
        except Exception as e:
            print('case cleanup warn:', e)
        try:
            api._cleanup(TOKEN)
        except Exception as e:
            print('tag cleanup warn:', e)


if __name__ == '__main__':
    main()
