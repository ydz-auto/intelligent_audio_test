# -*- coding: utf-8 -*-
"""INT-1488 复走（第二轮·导出专项）：INT-1561 缺陷 2 复核。

小结果集（level=ERROR，799 条）真实导出：格式 Select 关闭态、请求/响应、
下载非空、导出成功后弹窗关闭、取消三条路径、重开残留。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver, _open_trigger

import urllib.request
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'username'))).send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url or '欢迎' in body(d))
    time.sleep(2)


def goto_logs(drv, theme='light'):
    drv.get(BASE + '/')
    time.sleep(1)
    drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, theme))
    drv.get(BASE + '/logs')
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.5)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'tbody tr')


def level_chip(drv, level):
    for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
        if (b.text or '').strip().startswith(level) and b.is_displayed():
            return b
    return None


def wait_total(drv, expected, timeout=90):
    deadline = time.time() + timeout
    seen = None
    while time.time() < deadline:
        seen = page_total_text(drv)
        if seen == expected:
            return seen
        time.sleep(1)
    return seen


def _close_select(drv, trig):
    for _ in range(2):
        if not [c for c in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-content"]') if c.is_displayed()]:
            return
        try:
            js_click(drv, trig)
        except Exception:
            pass
        time.sleep(0.4)


def close_button(dlg):
    for b in dlg.find_elements(By.CSS_SELECTOR, 'button'):
        if not b.is_displayed():
            continue
        label = (b.get_attribute('aria-label') or '').strip()
        txt = (b.text or '').strip()
        if label in ('Close', '关闭') or txt == 'Close':
            return b
    return None


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(DL, exist_ok=True)
    for f in os.listdir(DL):
        try:
            os.remove(os.path.join(DL, f))
        except Exception:
            pass
    env_check('export_start')
    drv = _driver()
    try:
        login(drv)
        goto_logs(drv, 'light')

        # 收窄到 level=ERROR（小结果集，上轮实测 799 条）
        def set_error_filter():
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(1.0)
            api = api_total({'level': 'ERROR'})
            ui = wait_total(drv, api, 90)
            return {'ui_total': ui, 'api_total': api, 'ok': ui == api}
        step('X1_set_error_filter', set_error_filter)

        def export_small():
            out = {}
            clear_fetch_log(drv)
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out['dialog_text'] = dlg.text[:300]
            fmt = dlg.find_element(By.ID, 'log-export-format')
            out['format_closed'] = (fmt.text or '').strip()
            # 选 JSON
            content = _open_trigger(drv, fmt)
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            out['format_options'] = [(i.text or '').strip() for i in items]
            [js_click(drv, i) for i in items if (i.text or '').strip() == 'JSON']
            time.sleep(0.9)
            out['format_after_select'] = (wait_dialog(drv).find_element(By.ID, 'log-export-format').text or '').strip()
            shot(drv, 'light_1561_export_dialog_2.png')

            dlg = wait_dialog(drv)
            btn = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='导出']") if b.is_displayed()][0]
            js_click(drv, btn)
            # 等请求
            req = None
            deadline = time.time() + 60
            while time.time() < deadline:
                hits = [e for e in fetch_log(drv) if '/api/v1/logs/export' in e.get('url', '')]
                if hits:
                    req = hits[-1]
                    break
                time.sleep(0.5)
            out['request'] = req
            # 弹窗应关闭
            closed = False
            deadline = time.time() + 60
            while time.time() < deadline:
                if dialog(drv) is None:
                    closed = True
                    break
                time.sleep(0.5)
            out['dialog_closed_after_success'] = closed
            path, size = wait_download('logs_', 90)
            out['download'] = {'file': os.path.basename(path) if path else None, 'size': size}
            if path and size:
                try:
                    doc = json.loads(open(path, encoding='utf-8').read())
                    out['exported_rows'] = len(doc) if isinstance(doc, list) else None
                except Exception as e:
                    out['exported_rows'] = 'parse_error:%s' % e
            out['toast'] = '日志已导出' in body(drv)
            shot(drv, 'light_1561_export_closed_2.png')
            assert closed, '导出成功后弹窗未关闭'
            assert req and req.get('status') == 200, '导出请求失败 %s' % req
            assert size > 0, '下载文件为空'
            assert out['toast'], '未见导出成功 toast'
            return out
        step('X2_export_small_closes', export_small)

        def reopen_and_cancel_paths():
            out = {}
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.8)
            out['format_on_reopen'] = (dlg.find_element(By.ID, 'log-export-format').text or '').strip()
            # 关闭按钮
            cb = close_button(dlg)
            out['close_button_found'] = cb is not None
            if cb is not None:
                js_click(drv, cb)
            time.sleep(0.9)
            out['closed_by_button'] = dialog(drv) is None
            # Esc
            click_button(drv, '导出日志')
            wait_dialog(drv)
            time.sleep(0.6)
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.9)
            out['closed_by_esc'] = dialog(drv) is None
            # 遮罩
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.8)
            drv.execute_script("document.elementFromPoint(8, 8).click()")
            time.sleep(0.9)
            out['closed_by_overlay'] = dialog(drv) is None
            if dialog(drv) is not None:
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            # 取消按钮
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.6)
            cancel = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='取消']") if b.is_displayed()]
            if cancel:
                js_click(drv, cancel[0])
            time.sleep(0.9)
            out['closed_by_cancel'] = dialog(drv) is None
            return out
        step('X3_export_cancel_paths', reopen_and_cancel_paths)

        def dark_export():
            goto_logs(drv, 'dark')
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out = {'dark_class': drv.execute_script('return document.documentElement.className'),
                   'format_closed': (dlg.find_element(By.ID, 'log-export-format').text or '').strip()}
            shot(drv, 'dark_1561_export_dialog_2.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            out['closed_by_esc'] = dialog(drv) is None
            return out
        step('X4_dark_export', dark_export)

        env_check('export_end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'results_int1561_export.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        log('FAILED STEPS: %s' % FAIL)


if __name__ == '__main__':
    main()
