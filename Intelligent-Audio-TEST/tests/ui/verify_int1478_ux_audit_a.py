# -*- coding: utf-8 -*-
"""INT-1478 前端UX审计（A）：日常页签 8 窗 + 任务详情（INT-1492 三点）实测。
只读为主：确认类弹窗只验取消路径；导出/导入只打开不提交。
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
C.DL = os.path.join(ART, 'downloads')
os.makedirs(C.DL, exist_ok=True)

OUT = {'env': [], 'steps': {}, 'data': {}}


def api(path, params=None):
    url = C.API + '/api/v1' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode()).get('data')


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


def goto(drv, path, theme='light'):
    drv.get(C.BASE + '/')
    time.sleep(0.6)
    drv.execute_script('localStorage.setItem(%r, %r)' % (C.THEME_KEY, theme))
    drv.get(C.BASE + path)
    time.sleep(1.0)
    if theme == 'dark':
        WebDriverWait(drv, 20).until(lambda d: 'dark' in (d.execute_script('return document.documentElement.className') or ''))


def retheme(drv, theme):
    drv.execute_script('localStorage.setItem(%r, %r)' % (C.THEME_KEY, theme))
    drv.refresh()
    time.sleep(2.0)
    if theme == 'dark':
        WebDriverWait(drv, 20).until(lambda d: 'dark' in (d.execute_script('return document.documentElement.className') or ''))


def dialogs(drv):
    return [d for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if d.is_displayed()]


def last_dialog(drv):
    ds = dialogs(drv)
    return ds[-1] if ds else None


def close_dialog(drv, key=Keys.ESCAPE):
    try:
        last_dialog(drv).find_element(By.TAG_NAME, 'body').send_keys(key)
    except Exception:
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys(key)
        except Exception:
            pass
    time.sleep(0.8)


def open_row_menu(drv, index=0):
    btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if b.is_displayed()]
    if not btns:
        raise AssertionError('行操作按钮未找到')
    C.js_click(drv, btns[index])
    time.sleep(0.8)
    items = [i for i in drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if i.is_displayed()]
    return items


def click_menu_item(drv, text, index=0, exact=False):
    items = open_row_menu(drv, index)
    for i in items:
        label = (i.text or '').strip()
        if (label == text) if exact else (text in label):
            C.js_click(drv, i)
            time.sleep(1.0)
            return True
    raise AssertionError('菜单项未找到 %s 现有=%s' % (text, [i.text for i in items]))


def main():
    health = C.env_check('start')
    OUT['env'].append(health)
    tasks = api('/tasks', {'page': 1, 'per_page': 10})
    OUT['data']['tasks_total'] = tasks.get('total')
    OUT['data']['first_task'] = tasks['items'][0] if tasks.get('items') else None
    detail526 = api('/tasks/526')
    OUT['data']['task526'] = {
        'total_cases': detail526.get('total_cases'),
        'cases': len(detail526.get('cases') or []),
        'review_count': detail526.get('review_count'),
    }

    drv = C._driver()
    try:
        login(drv)
        C.clear_fetch_log(drv)
        drv.get(C.BASE + '/tasks/daily')
        WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')) > 0)
        time.sleep(1.5)

        def daily_page():
            txt = C.body(drv)
            m = re.search(r'共\s*([\d,]+)\s*条', txt)
            tabs = [(t.text or '').strip() for t in drv.find_elements(By.CSS_SELECTOR, '[role="tab"]') if t.is_displayed()]
            rows = len([b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if b.is_displayed()])
            return {'total_text': m.group(1) if m else None, 'tabs': tabs, 'rows': rows,
                    'api_total': OUT['data']['tasks_total']}
        C.step('daily_page', daily_page)

        def task_type_dialog():
            C.click_button(drv, '创建新任务')
            d = C.wait_dialog(drv, 15)
            txt = d.text
            C.shot(drv, '01_task_type_light.png')
            close_dialog(drv)
            C.click_button(drv, '创建新任务')
            d2 = C.wait_dialog(drv, 15)
            checked = len([r for r in d2.find_elements(By.CSS_SELECTOR, '[role="radio"][data-state="checked"], [role="radio"][aria-checked="true"]')])
            C.shot(drv, '01b_task_type_reopen_light.png')
            close_dialog(drv)
            return {'title_has': '任务类型' in txt or '选择' in txt, 'snippet': txt[:160], 'reopen_checked': checked}
        C.step('task_type_dialog', task_type_dialog)

        def quick_view():
            first = OUT['data']['first_task']
            click_menu_item(drv, '快速查看')
            d = C.wait_dialog(drv, 20)
            body = d.text
            C.shot(drv, '02_quick_view_light.png')
            retheme(drv, 'dark')
            # 重开后行菜单可能重建，直接重新打开
            click_menu_item(drv, '快速查看')
            C.wait_dialog(drv, 20)
            C.shot(drv, '02b_quick_view_dark.png')
            close_dialog(drv)
            retheme(drv, 'light')
            return {'dialog_snippet': body[:200], 'first_task_name': first['name'],
                    'first_task_status': first['status'], 'name_in_dialog': first['name'] in body,
                    'status_in_dialog': (first.get('status') or '') in body}
        C.step('quick_view', quick_view)

        def reexecute():
            C.clear_fetch_log(drv)
            click_menu_item(drv, '重新执行')
            d = C.wait_dialog(drv, 15)
            txt = d.text
            opts = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, '[role="radio"], label') if (o.text or '').strip()]
            C.shot(drv, '03_reexecute_light.png')
            close_dialog(drv)
            time.sleep(1.0)
            writes = [e for e in C.fetch_log(drv) if e['url'].find('/tasks/') >= 0 and e['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')]
            return {'snippet': txt[:200], 'options': opts[:8], 'writes_on_cancel': writes}
        C.step('reexecute_scope', reexecute)

        def confirm_delete_cancel():
            C.clear_fetch_log(drv)
            items = open_row_menu(drv, 0)
            labels = [i.text.strip() for i in items]
            click_menu_item(drv, '删除', 0, exact=True)
            d = C.wait_dialog(drv, 15)
            txt = d.text
            C.shot(drv, '04_confirm_delete_light.png')
            cancel = None
            for b in d.find_elements(By.XPATH, ".//button"):
                if (b.text or '').strip() in ('取消', 'Cancel'):
                    cancel = b
                    break
            if cancel is None:
                raise AssertionError('取消按钮未找到')
            C.js_click(drv, cancel)
            time.sleep(1.2)
            writes = [e for e in C.fetch_log(drv) if e['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')]
            return {'menu_items': labels, 'snippet': txt[:160], 'writes_on_cancel': writes}
        C.step('confirm_delete_cancel', confirm_delete_cancel)

        def export_dialog():
            boxes = [b for b in drv.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]') if b.is_displayed()]
            if not boxes:
                boxes = [b for b in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]') if b.is_displayed()]
            if not boxes:
                raise AssertionError('行复选框未找到')
            C.js_click(drv, boxes[0])
            time.sleep(1.2)
            C.click_button(drv, '导出数据')
            d = C.wait_dialog(drv, 15)
            txt = d.text
            C.shot(drv, '05_export_light.png')
            close_dialog(drv)
            return {'snippet': txt[:200]}
        C.step('export_dialog', export_dialog)

        def import_dialog():
            C.click_button(drv, '导入数据')
            d = C.wait_dialog(drv, 15)
            txt = d.text
            C.shot(drv, '06_import_light.png')
            close_dialog(drv)
            return {'snippet': txt[:200]}
        C.step('import_dialog', import_dialog)

        def publish_dialog():
            # 找可发布任务（已完成/失败/停止/待执行）
            c = None
            for idx in range(6):
                try:
                    click_menu_item(drv, '发布', idx)
                    c = C.wait_dialog(drv, 15)
                    break
                except Exception:
                    continue
            if c is None:
                raise AssertionError('未找到可发布任务/发布弹窗')
            time.sleep(4.0)
            txt = c.text
            C.shot(drv, '07_publish_light.png')
            # 触发器文本（不再显示裸 id）
            trig = c.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
            trig_txt = [t.text.strip() for t in trig]
            main_btn = None
            for b in c.find_elements(By.XPATH, ".//button"):
                if '发布' == (b.text or '').strip():
                    main_btn = b
            opts = [i.text.strip() for i in c.find_elements(By.CSS_SELECTOR, '[role="option"]') if (i.text or '').strip()]
            res = {'snippet': txt[:400], 'trigger_texts': trig_txt, 'option_count': len(opts),
                   'option_head': opts[:3],
                   'main_disabled': (main_btn.get_attribute('disabled') is not None) if main_btn else None,
                   'main_enabled_no_submit': True}
            close_dialog(drv)
            retheme(drv, 'dark')
            click_menu_item(drv, '发布', 0)
            C.wait_dialog(drv, 20)
            time.sleep(3.0)
            C.shot(drv, '07b_publish_dark.png')
            close_dialog(drv)
            retheme(drv, 'light')
            return res
        C.step('publish_dialog', publish_dialog)

        # ---------- 任务详情 526 ----------
        goto(drv, '/tasks/526', 'light')
        WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-testid="task-case-list"]')) > 0)
        time.sleep(2.0)

        def detail_flat():
            lst = drv.find_element(By.CSS_SELECTOR, '[data-testid="task-case-list"]')
            metrics = drv.execute_script(
                'const e=arguments[0];const rows=e.querySelectorAll("[role=\\"row\\"]");'
                'return {scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,rows:rows.length,'
                'grid:getComputedStyle(e.firstElementChild).gridTemplateColumns||"",'
                'maxH:getComputedStyle(e).maxHeight};', lst)
            C.shot(drv, '08_task526_flat_light.png')
            # 滚到底
            drv.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight;', lst)
            time.sleep(1.5)
            metrics2 = drv.execute_script(
                'const e=arguments[0];return {scrollTop:e.scrollTop, max:e.scrollHeight-e.clientHeight,'
                'rows:e.querySelectorAll("[role=\\"row\\"]").length};', lst)
            C.shot(drv, '08b_task526_flat_bottom_light.png')
            # 状态筛选
            names = C.select_options(drv, '状态筛选')
            return {'list': metrics, 'after_scroll': metrics2, 'status_options': names,
                    'api_cases': OUT['data']['task526']}
        C.step('detail_flat_and_filter_options', detail_flat)

        def detail_filter_apply():
            C.select_option(drv, '状态筛选', '评估失败')
            time.sleep(1.5)
            lst = drv.find_element(By.CSS_SELECTOR, '[data-testid="task-case-list"]')
            info_eval = drv.execute_script(
                'const e=arguments[0];return {sh:e.scrollHeight,rows:e.querySelectorAll("[role=\\"row\\"]").length,'
                'text:(e.textContent||"").slice(0,120)};', lst)
            C.shot(drv, '09_task526_filter_eval_failed_light.png')
            C.select_option(drv, '状态筛选', '执行失败')
            time.sleep(1.2)
            body = C.body(drv)
            empty = '暂无关联用例' in body
            rows_exec = drv.execute_script(
                'const e=document.querySelector(\'[data-testid="task-case-list"]\');'
                'return e?e.querySelectorAll(\'[role="row"]\').length:null;')
            C.shot(drv, '09b_task526_filter_exec_failed_light.png')
            C.select_option(drv, '状态筛选', '全部状态')
            time.sleep(1.0)
            return {'eval_filter': info_eval, 'exec_empty': empty, 'exec_rows': rows_exec}
        C.step('detail_filter_apply', detail_filter_apply)

        def review_history():
            goto(drv, '/tasks/417', 'light')
            WebDriverWait(drv, 90).until(lambda d: '查看复核历史' in C.body(d))
            time.sleep(1.5)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            if not btns:
                raise AssertionError('查看复核历史入口未找到')
            C.js_click(drv, btns[0])
            time.sleep(2.5)
            sheet = None
            for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
                if d.is_displayed() and '复核历史' in (d.text or ''):
                    sheet = d
            if sheet is None:
                raise AssertionError('复核历史抽屉未打开')
            txt = sheet.text
            items = drv.execute_script(
                "const d=arguments[0];const els=[...d.querySelectorAll('*')].filter(e=>e.children.length===0&&e.textContent&&e.textContent.length>40);"
                "return els.slice(0,6).map(e=>({text:e.textContent.slice(0,90),w:e.getBoundingClientRect().width,"
                "sw:e.scrollWidth,swClient:e.clientWidth,sel:e.className&&String(e.className).slice(0,60)}));", sheet)
            C.shot(drv, '10_review_history_light.png')
            retheme(drv, 'dark')
            WebDriverWait(drv, 90).until(lambda d: '查看复核历史' in C.body(d))
            time.sleep(1.5)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            C.js_click(drv, btns[0])
            time.sleep(2.5)
            C.shot(drv, '10b_review_history_dark.png')
            close_dialog(drv)
            retheme(drv, 'light')
            return {'snippet': txt[:400], 'count_occurrences': txt.count('复核'), 'long_text_nodes': items}
        C.step('review_history', review_history)

        health2 = C.env_check('mid')
        OUT['env'].append(health2)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    health3 = C.env_check('end')
    OUT['env'].append(health3)
    OUT['steps'] = C.RESULTS.get('steps', {})
    OUT['screenshots'] = C.RESULTS.get('screenshots', [])
    OUT['failed_steps'] = C.FAIL
    with open(os.path.join(ART, 'audit_a.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    print('FAILED STEPS:', C.FAIL)


if __name__ == '__main__':
    main()
