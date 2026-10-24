# -*- coding: utf-8 -*-
"""INT-1488 补走：级别/关键词/空态 + 导出小结果集非空 + 实时日志/实时配置弹窗。"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver, _open_trigger, _close_popups

import redis
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

REDIS_URL = os.environ.get('INT1488_REDIS_URL', 'redis://localhost:16379')


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    uname = WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'username')))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url or '欢迎' in body(d))
    time.sleep(2)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'tbody tr')


def level_chip(drv, level):
    for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
        if (b.text or '').strip().startswith(level) and b.is_displayed():
            return b
    return None


def wait_total(drv, expected, timeout=60):
    """等页脚总数等于期望值（接口慢，最多等 timeout 秒）。"""
    deadline = time.time() + timeout
    seen = None
    while time.time() < deadline:
        seen = page_total_text(drv)
        if seen == expected:
            return seen
        time.sleep(1)
    return seen


def goto_logs(drv, theme='light'):
    drv.get(BASE + '/')
    time.sleep(1)
    drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, theme))
    drv.get(BASE + '/logs')
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.5)


def main():
    os.makedirs(ART, exist_ok=True)
    env_check('part2_start')
    drv = _driver()
    try:
        login(drv)
        goto_logs(drv)

        def filter_level_error():
            clear_fetch_log(drv)
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(1.2)
            api = api_total({'level': 'ERROR'})
            ui = wait_total(drv, api, 60)
            req = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '') and e.get('status') == 200][-1:]
            levels = [r.find_elements(By.CSS_SELECTOR, 'td')[3].text.strip()
                      for r in rows(drv)[:10] if len(r.find_elements(By.CSS_SELECTOR, 'td')) > 5]
            shot(drv, 'light_15_filter_level_error_verified.png')
            return {'ui_total': ui, 'api_total': api, 'match': ui == api,
                    'visible_levels': sorted(set(levels)), 'request': req}
        step('30_filter_level_error_verified', filter_level_error)

        def filter_keyword():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            clear_fetch_log(drv)
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys('AUTH_LOGIN')
            api = api_total({'keyword': 'AUTH_LOGIN'})
            ui = wait_total(drv, api, 90)
            req = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '') and e.get('status') == 200][-1:]
            shot(drv, 'light_16_filter_keyword_verified.png')
            return {'ui_total': ui, 'api_total': api, 'match': ui == api, 'request': req}
        step('31_filter_keyword_verified', filter_keyword)

        def empty_state():
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys(Keys.CONTROL, 'a')
            inp.send_keys(Keys.DELETE)
            time.sleep(0.5)
            inp.send_keys('INT1488_NO_MATCH_ZZZ')
            deadline = time.time() + 90
            txt = ''
            found = []
            while time.time() < deadline:
                txt = body(drv)
                found = [t for t in ['未找到匹配日志', '暂无日志'] if t in txt]
                if found:
                    break
                time.sleep(1)
            shot(drv, 'light_17_empty_state_verified.png')
            return {'empty_texts': found, 'rows': len(rows(drv)),
                    'skeleton': len(drv.find_elements(By.CSS_SELECTOR, '[data-slot="skeleton"]'))}
        step('32_empty_state_verified', empty_state)

        def export_small_level_error():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(1.2)
            wait_total(drv, api_total({'level': 'ERROR'}), 60)
            clear_fetch_log(drv)
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.5)
            summary = dlg.text
            # 选 JSON
            combos = [c for c in dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if c.is_displayed()]
            trig = combos[0]
            content = _open_trigger(drv, trig)
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            names = [(i.text or '').strip() for i in items]
            target = [i for i in items if (i.text or '').strip() == 'JSON'][0]
            js_click(drv, target)
            time.sleep(0.8)
            dlg = wait_dialog(drv)
            btn = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='导出']") if b.is_displayed()][0]
            js_click(drv, btn)
            # 等 fetch 完成（导出 799 条约 5s）
            req = None
            deadline = time.time() + 90
            while time.time() < deadline:
                hits = [e for e in fetch_log(drv) if '/api/v1/logs/export' in e.get('url', '')]
                if hits:
                    req = hits[-1]
                    break
                time.sleep(1)
            path, size = wait_download('logs_', 90)
            head = ''
            if path and size:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    head = f.read(300)
            try:
                doc = json.loads(open(path, encoding='utf-8').read()) if path and size else None
                n_rows = len(doc) if isinstance(doc, list) else None
            except Exception:
                n_rows = None
            shot(drv, 'light_18_export_done.png')
            if dialog(drv) is not None:
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            return {'summary': summary, 'format_options': names, 'request': req,
                    'download': os.path.basename(path) if path else None, 'size': size,
                    'exported_rows': n_rows, 'content_head': head[:200],
                    'toast': '日志已导出' in body(drv)}
        step('33_export_small_level_error', export_small_level_error)

        # ---------------- 实时日志 + 实时配置弹窗 ----------------
        def realtime_ws_and_config():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            wait_text(drv, '实时监控中', 30)
            wait_text(drv, 'WS实时', 30)
            time.sleep(1)
            shot(drv, 'light_19_realtime_on.png')
            out = {'indicator': 'WS实时' in body(drv)}

            # 合成 task_log（Redis task_events → 网关 EventBusForwarder → /ws/logs）
            marker = 'INT1488_WS_%d' % int(time.time())
            rc = redis.from_url(REDIS_URL)
            rc.publish('task_events', json.dumps({
                'event_type': 'task_log',
                'payload': {
                    'task_id': None,
                    'log_payload': {
                        'id': 990000000 + int(time.time()) % 1000000,
                        'time': '2026-10-23 19:55:00', 'level': 'INFO', 'module': 'run_all',
                        'content': marker, 'mark': '', 'task_id': None,
                        'test_case_id': None, 'category': 'test', 'source': 'run_all',
                    },
                },
            }, ensure_ascii=False))
            rc.close()
            got = False
            deadline = time.time() + 30
            while time.time() < deadline:
                first = rows(drv)[0].text if rows(drv) else ''
                if marker in first:
                    got = True
                    break
                time.sleep(1)
            out['ws_marker_received'] = got
            out['first_row'] = (rows(drv)[0].text[:160] if rows(drv) else '')
            shot(drv, 'light_20_realtime_ws_received.png')

            # 配置弹窗（监视条「配置」钮）
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out['config_text_before'] = dlg.text
            shot(drv, 'light_21_realtime_config_dialog.png')
            # 轮询间隔选项
            combos = [c for c in dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if c.is_displayed()]
            trig = combos[0]
            out['interval_trigger_text'] = trig.text
            content = _open_trigger(drv, trig)
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            out['interval_options'] = [(i.text or '').strip() for i in items]
            target = [i for i in items if (i.text or '').strip() == '10s'][0]
            js_click(drv, target)
            time.sleep(0.8)
            dlg = wait_dialog(drv)
            # 关自动滚动 / 关 toast
            switches = dlg.find_elements(By.CSS_SELECTOR, '[data-slot="switch"], [role="switch"]')
            out['switch_count'] = len(switches)
            for s in switches:
                js_click(drv, s)
                time.sleep(0.5)
            shot(drv, 'light_22_realtime_config_edited.png')
            # 完成关闭
            click_button(drv, '完成', dlg)
            time.sleep(0.8)
            out['closed_by_done'] = dialog(drv) is None
            # 重开回读
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            combos = [c for c in dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if c.is_displayed()]
            out['reopen_interval_text'] = combos[0].text
            out['reopen_text'] = dlg.text
            switches = dlg.find_elements(By.CSS_SELECTOR, '[data-slot="switch"], [role="switch"]')
            out['reopen_switch_states'] = [s.get_attribute('aria-checked') or s.get_attribute('data-checked') for s in switches]
            shot(drv, 'light_23_realtime_config_reopen.png')
            # 恢复原值：5s + 两个开关打开
            content = _open_trigger(drv, combos[0])
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            target = [i for i in items if (i.text or '').strip() == '5s'][0]
            js_click(drv, target)
            time.sleep(0.6)
            dlg = wait_dialog(drv)
            switches = dlg.find_elements(By.CSS_SELECTOR, '[data-slot="switch"], [role="switch"]')
            for s in switches:
                st = s.get_attribute('aria-checked') or s.get_attribute('data-checked')
                if st in ('false', None):
                    js_click(drv, s)
                    time.sleep(0.4)
            out['after_restore_text'] = dlg.text
            click_button(drv, '完成', dlg)
            time.sleep(0.8)
            out['restored_closed'] = dialog(drv) is None
            # 关闭实时开关，恢复页面初始态
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            time.sleep(1)
            out['realtime_off'] = '实时监控已停止' in body(drv)
            return out
        step('34_realtime_ws_and_config', realtime_ws_and_config)

        def realtime_dark():
            drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, 'dark'))
            drv.get(BASE + '/logs')
            WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
            time.sleep(1.5)
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            wait_text(drv, '实时监控中', 30)
            time.sleep(1)
            shot(drv, 'dark_05_realtime_on.png')
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            shot(drv, 'dark_06_realtime_config_dialog.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            time.sleep(0.8)
            return {'dark': 'dark' in drv.execute_script('return document.documentElement.className')}
        step('35_realtime_dark', realtime_dark)

        env_check('part2_end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'results_part2.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        log('FAILED STEPS: %s' % FAIL)


if __name__ == '__main__':
    main()
