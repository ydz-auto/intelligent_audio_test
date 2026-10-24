# -*- coding: utf-8 -*-
"""INT-1478 前端UX审计（C）：确认弹窗（alertdialog）取消路径 + 导出真实下载 + 任务类型深色。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1488_common as C
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ART = os.path.join('tests', 'ui', 'artifacts', 'int1478_audit')
os.makedirs(ART, exist_ok=True)
C.ART = ART
DL = os.path.join(ART, 'downloads')
os.makedirs(DL, exist_ok=True)
C.DL = DL

OUT = {'steps': {}, 'env': []}


def login(drv):
    drv.get(C.BASE + '/login')
    time.sleep(2)
    try:
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def any_dialog(drv):
    for sel in ('[role="alertdialog"]', '[role="dialog"]'):
        for d in drv.find_elements(By.CSS_SELECTOR, sel):
            if d.is_displayed():
                return d
    return None


def wait_any(drv, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: any_dialog(d))


def retheme(drv, theme):
    drv.execute_script('localStorage.setItem(%r, %r)' % (C.THEME_KEY, theme))
    drv.refresh()
    time.sleep(2.0)
    if theme == 'dark':
        WebDriverWait(drv, 20).until(lambda d: 'dark' in (d.execute_script('return document.documentElement.className') or ''))


def main():
    OUT['env'].append(C.env_check('start'))
    api = C.API + '/api/v1'
    before = json.loads(urllib.request.urlopen(api + '/tasks?page=1&per_page=1', timeout=90).read().decode())['data']
    OUT['tasks_total_before'] = before.get('total')
    drv = C._driver()
    try:
        login(drv)
        drv.get(C.BASE + '/tasks/daily')
        WebDriverWait(drv, 90).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')) > 0)
        time.sleep(1.5)

        def open_menu():
            btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if b.is_displayed()]
            C.js_click(drv, btns[0])
            time.sleep(0.8)
            return [i for i in drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if i.is_displayed()]

        def delete_cancel():
            C.clear_fetch_log(drv)
            items = open_menu()
            labels = [(i.text or '').strip() for i in items]
            target = [i for i in items if (i.text or '').strip() == '删除']
            if not target:
                raise AssertionError('删除项缺失: %s' % labels)
            C.js_click(drv, target[0])
            d = wait_any(drv, 15)
            txt = d.text
            role = d.get_attribute('role')
            C.shot(drv, '04_confirm_delete_light.png')
            cancel = [b for b in d.find_elements(By.XPATH, ".//button") if (b.text or '').strip() in ('取消', 'Cancel')]
            C.js_click(drv, cancel[0])
            time.sleep(1.5)
            writes = [e for e in C.fetch_log(drv) if e['method'] in ('DELETE', 'POST', 'PUT', 'PATCH')]
            gone = any_dialog(drv) is None
            return {'role': role, 'menu_labels': labels, 'snippet': txt[:160], 'closed_after_cancel': gone, 'writes_on_cancel': writes}
        C.step('delete_confirm_cancel', delete_cancel)

        def export_download():
            boxes = [b for b in drv.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]') if b.is_displayed()]
            C.js_click(drv, boxes[0])
            time.sleep(1.2)
            C.click_button(drv, '导出数据')
            d = wait_any(drv, 15)
            txt = d.text
            C.shot(drv, '05b_export_filled_light.png')
            C.clear_fetch_log(drv)
            bar = C.find_button(drv, '导出', root=d)
            btns = [(b.text or '').strip() for b in d.find_elements(By.XPATH, './/button')]
            target = None
            for b in d.find_elements(By.XPATH, './/button'):
                t = (b.text or '').strip()
                if t in ('导出', '确认导出', '开始导出'):
                    target = b
            if target is None:
                raise AssertionError('导出提交钮未找到: %s' % btns)
            C.js_click(drv, target)
            path, size = C.wait_download('task_export_', timeout=180)
            resp = [e for e in C.fetch_log(drv) if e['method'] in ('POST', 'GET') and 'export' in e['url']]
            closed = any_dialog(drv) is None
            return {'snippet': txt[:200], 'file': os.path.basename(path) if path else None, 'size': size,
                    'dialog_closed': closed, 'requests': resp[-3:], 'buttons': btns}
        C.step('export_download', export_download)

        def task_type_dark():
            retheme(drv, 'dark')
            C.click_button(drv, '创建新任务')
            wait_any(drv, 15)
            C.shot(drv, '01c_task_type_dark.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            retheme(drv, 'light')
            return {'ok': True}
        C.step('task_type_dark', task_type_dark)

        OUT['env'].append(C.env_check('end'))
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    after = json.loads(urllib.request.urlopen(api + '/tasks?page=1&per_page=1', timeout=90).read().decode())['data']
    OUT['tasks_total_after'] = after.get('total')
    OUT['steps'] = C.RESULTS.get('steps', {})
    OUT['failed_steps'] = C.FAIL
    with open(os.path.join(ART, 'audit_c.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    print('FAILED STEPS:', C.FAIL)


if __name__ == '__main__':
    main()
