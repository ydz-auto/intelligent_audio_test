# -*- coding: utf-8 -*-
"""INT-1494 第二轮：供应商管理校验/删除回读、工作台浮窗跨页驻留（应用内导航）、
报告展示页交互、关于页链接。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, BASE, body_text, clear_perf, driver,  # noqa: E402
                             goto, js_click, requests_simple, result, set_theme,
                             shot)
from verify_int1494_aichat import start_stub  # noqa: E402

R = []
PROVIDER = '接线测试_LLM供应商'


def find_btn(d, *texts, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        for b in d.find_elements(By.CSS_SELECTOR, 'button, [role=button], a'):
            try:
                t = ((b.text or '') + ' ' + (b.get_attribute('aria-label') or '')).strip()
            except Exception:
                continue
            for want in texts:
                if want in t and b.is_displayed():
                    return b
        time.sleep(0.3)
    return None


def wait_text(d, text, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if text in body_text(d):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def open_manager(d):
    trig = find_btn(d, '未配置', '管理供应商', 'LLM', timeout=4)
    if trig is None:
        cb = d.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        if cb:
            js_click(d, cb[0])
            time.sleep(1)
            trig = find_btn(d, '管理供应商', '管理')
    if trig is not None:
        js_click(d, trig)
        time.sleep(1.2)
    return wait_text(d, 'LLM 供应商管理', 8)


def provider_flow():
    srv = start_stub()
    d = driver()
    try:
        set_theme(d, 'light')
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        time.sleep(2.5)
        st = {}
        st['opened'] = open_manager(d)
        shots = []
        if not st['opened']:
            R.append(result('provider_manager_r2', False, st))
            return
        add = find_btn(d, '添加供应商')
        if add:
            js_click(d, add)
            time.sleep(1)
        # 必填留空
        sv = find_btn(d, '保存')
        if sv:
            js_click(d, sv)
        time.sleep(1.2)
        t = body_text(d)
        st['errors_empty'] = [x for x in ('请输入供应商名称', '请输入 API Base URL', '请输入 API Key') if x in t]
        shots.append(shot(d, 'manager_validation_light'))
        # 非法 Base URL → 测试连接错误态
        d.find_element(By.ID, 'provider-name').send_keys(PROVIDER)
        d.find_element(By.ID, 'provider-base-url').send_keys('http://127.0.0.1:1/v1')
        d.find_element(By.ID, 'provider-api-key').send_keys('sk-bad')
        tc = find_btn(d, '测试连接')
        if tc:
            js_click(d, tc)
            time.sleep(4)
        st['test_fail_toast'] = '无法连接该供应商' in body_text(d)
        shots.append(shot(d, 'manager_test_fail_light'))
        # 正确地址 → 保存
        bu = d.find_element(By.ID, 'provider-base-url')
        bu.send_keys(Keys.CONTROL, 'a')
        bu.send_keys(Keys.DELETE)
        bu.send_keys('http://127.0.0.1:18899/v1')
        fm = find_btn(d, '自动获取模型列表')
        if fm:
            js_click(d, fm)
            time.sleep(3)
        sv = find_btn(d, '保存')
        if sv:
            js_click(d, sv)
        time.sleep(1.5)
        st['saved'] = PROVIDER in body_text(d)
        st['ls_after_save'] = d.execute_script(
            "return window.localStorage.getItem('iatp:ai-chat:v1:providers');")
        # 深色下弹窗
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
        time.sleep(1)
        shots.append(shot(d, 'manager_saved_dark'))
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")
        time.sleep(1)
        # 删除 + 确认
        dl = find_btn(d, '删除')
        if dl:
            js_click(d, dl)
            time.sleep(1.5)
            t = body_text(d)
            st['delete_confirm_text'] = '删除供应商' in t
            shots.append(shot(d, 'manager_delete_confirm_light'))
            for b in d.find_elements(By.CSS_SELECTOR, 'button'):
                if (b.text or '').strip() in ('删除', '确认', '确定') and b.is_displayed():
                    js_click(d, b)
                    break
            time.sleep(1.8)
        st['after_delete_has_provider'] = PROVIDER in body_text(d)
        st['ls_after_delete'] = d.execute_script(
            "return window.localStorage.getItem('iatp:ai-chat:v1:providers');")
        shots.append(shot(d, 'manager_after_delete_light'))
        d.execute_script("window.localStorage.removeItem('iatp:ai-chat:v1:providers');")
        R.append(result('provider_manager_r2',
                        bool(st.get('errors_empty')) and st.get('saved') and
                        not st.get('after_delete_has_provider'), st, shots))
    except Exception as exc:
        R.append(result('provider_manager_r2', False, 'EXC %r' % (exc,)))
    finally:
        d.quit()
        srv.shutdown()


def workbench_nav():
    d = driver()
    try:
        set_theme(d, 'light')
        goto(d, '/dashboard')
        time.sleep(2.5)
        st = {}
        b = d.find_elements(By.CSS_SELECTOR, "button[aria-label='打开全局 Agent 工作台']")
        if not b:
            R.append(result('workbench_nav', False, {'no_button': True}))
            return
        js_click(d, b[0])
        time.sleep(2)
        st['opened'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) > 0
        shots = [shot(d, 'workbench_nav_open_light')]
        # 应用内导航（点侧栏「开始测试」），浮窗应保持
        link = None
        for a in d.find_elements(By.CSS_SELECTOR, 'a[href]'):
            if (a.get_attribute('href') or '').endswith('/testcases') or '开始测试' in (a.text or '') or '用例管理' in (a.text or ''):
                link = a
                break
        if link is not None:
            js_click(d, link)
            time.sleep(3)
        st['url_after_nav'] = d.current_url
        st['survives_inapp_nav'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) > 0
        shots.append(shot(d, 'workbench_nav_crosspage_light'))
        # 关闭
        c = d.find_elements(By.CSS_SELECTOR, "button[aria-label='关闭']")
        if c:
            js_click(d, c[0])
            time.sleep(1.2)
        st['closed'] = len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='最小化']")) == 0
        R.append(result('workbench_nav', st.get('opened') and st.get('survives_inapp_nav'), st, shots))
    except Exception as exc:
        R.append(result('workbench_nav', False, 'EXC %r' % (exc,)))
    finally:
        d.quit()


def reports_interact():
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/reports')
        time.sleep(4)
        st = {}
        shots = []
        # 类别页签
        for t in ('对比报告', 'Benchmark 报告'):
            b = find_btn(d, t, timeout=4)
            if b is not None:
                js_click(d, b)
                time.sleep(2)
                st['tab_' + t] = body_text(d)[-500:]
        b = find_btn(d, '全部', timeout=4)
        if b is not None:
            js_click(d, b)
            time.sleep(2)
        # 查看第一行
        view = find_btn(d, '查看', timeout=5)
        if view is not None:
            clear_perf(d)
            js_click(d, view)
            time.sleep(4)
            st['view_url'] = d.current_url
            st['view_api'] = requests_simple(d, '/reports')[:6]
            shots.append(shot(d, 'reports_view_light'))
            d.back()
            time.sleep(3)
        # 复制链接
        cp = find_btn(d, '复制链接', timeout=4)
        if cp is not None:
            js_click(d, cp)
            time.sleep(2)
            st['copy_toast'] = '复制' in body_text(d)
            shots.append(shot(d, 'reports_copy_light'))
        shots.append(shot(d, 'reports_table_light'))
        R.append(result('reports_interact', bool(st.get('view_url')), st, shots))
    except Exception as exc:
        R.append(result('reports_interact', False, 'EXC %r' % (exc,)))
    finally:
        d.quit()


for fn in (provider_flow, workbench_nav, reports_interact):
    try:
        fn()
    except Exception:
        pass

with open(os.path.join(ARTIFACTS, 'int1494_round2.json'), 'w', encoding='utf-8') as f:
    json.dump(R, f, ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2)[:7000])
