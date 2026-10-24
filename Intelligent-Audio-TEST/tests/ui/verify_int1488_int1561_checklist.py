# -*- coding: utf-8 -*-
"""INT-1488 复走（第二轮·清单复核）：镜像重建后重走筛选/详情/空态/清除弹窗。

镜像 iat-react-frontend 已重建（2026-10-23T19:57Z），上轮浅走证据作废，
本脚本在当前镜像上复跑：关键词/时间筛选与接口条数一致、空态、行详情、清除弹窗取消路径。
清除弹窗只验确认文案与取消，绝不点「清除」。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver

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


def set_dt(drv, el, value):
    set_input_js(drv, el, value)


def main():
    os.makedirs(ART, exist_ok=True)
    env_check('checklist_start')
    drv = _driver()
    try:
        login(drv)
        goto_logs(drv, 'light')

        def kw_filter():
            clear_fetch_log(drv)
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys('AUTH_LOGIN')
            api = api_total({'keyword': 'AUTH_LOGIN'})
            ui = wait_total(drv, api, 90)
            reqs = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '') and e.get('status') == 200]
            out = {'ui_total': ui, 'api_total': api, 'match': ui == api,
                   'request': reqs[-1] if reqs else None}
            shot(drv, 'light_1561_keyword_verified.png')
            assert out['match'], '关键词筛选条数不一致 %s' % out
            return out
        step('Y1_keyword_filter', kw_filter)

        def time_filter():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            clear_fetch_log(drv)
            start = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="开始时间"]')
            set_dt(drv, start, '2026-10-23T00:00')
            api = api_total({'start_time': '2026-10-23T00:00'})
            ui = wait_total(drv, api, 90)
            reqs = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '') and e.get('status') == 200]
            out = {'ui_total': ui, 'api_total': api, 'match': ui == api,
                   'request': reqs[-1] if reqs else None}
            shot(drv, 'light_1561_time_filter_verified.png')
            assert out['match'], '时间筛选条数不一致 %s' % out
            return out
        step('Y2_time_filter', time_filter)

        def level_filter():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            clear_fetch_log(drv)
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(1.0)
            api = api_total({'level': 'ERROR'})
            ui = wait_total(drv, api, 90)
            cells = [r.find_elements(By.CSS_SELECTOR, 'td')[3].text.strip()
                     for r in rows(drv)[:10] if len(r.find_elements(By.CSS_SELECTOR, 'td')) > 5]
            out = {'ui_total': ui, 'api_total': api, 'match': ui == api,
                   'visible_levels': sorted(set(cells))}
            assert out['match'] and out['visible_levels'] == ['ERROR'], '级别筛选不对 %s' % out
            return out
        step('Y3_level_filter', level_filter)

        def empty_state():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys('INT1488_NO_MATCH_ZZZ')
            deadline = time.time() + 90
            found = []
            while time.time() < deadline:
                txt = body(drv)
                found = [t for t in ['未找到匹配日志', '暂无日志'] if t in txt]
                if found:
                    break
                time.sleep(1)
            shot(drv, 'light_1561_empty_state_verified.png')
            assert found, '空态文案缺失'
            return {'empty_texts': found, 'rows': len(rows(drv))}
        step('Y4_empty_state', empty_state)

        def detail_expand():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            row = rows(drv)[0]
            tds = row.find_elements(By.CSS_SELECTOR, 'td')
            js_click(drv, tds[2])
            time.sleep(1.2)
            txt = body(drv)
            fields = [t for t in ['详细信息', '上下文信息', '时间', '级别', '分类', '模块',
                                  '算法类型', '来源', '设备ID', '任务ID', '线程ID', '内容'] if t in txt]
            shot(drv, 'light_1561_row_detail.png')
            assert '详细信息' in txt and '上下文信息' in txt, '详情未展开 %s' % fields
            return {'fields': fields, 'row_head': rows(drv)[0].text[:200]}
        step('Y5_row_detail', detail_expand)

        def clear_dialog_paths():
            out = {}
            click_button(drv, '清除日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out['default_text'] = dlg.text
            before = dlg.find_element(By.ID, 'log-clear-before')
            out['default_before_value'] = before.get_attribute('value')
            sw = dlg.find_element(By.ID, 'log-clear-keep-marked')
            out['default_keep_marked'] = sw.get_attribute('aria-checked') or sw.get_attribute('data-checked')
            shot(drv, 'light_1561_clear_dialog.png')
            # 编辑：设时间 + 关保留已标记
            before.clear()
            set_input_js(drv, before, '2026-10-22T00:00')
            js_click(drv, dlg.find_element(By.ID, 'log-clear-keep-marked'))
            time.sleep(1.0)
            out['edited_text'] = wait_dialog(drv).text
            shot(drv, 'light_1561_clear_dialog_edited.png')
            # 取消
            cancel = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消']") if b.is_displayed()]
            js_click(drv, cancel[0])
            time.sleep(0.9)
            out['closed_by_cancel'] = dialog(drv) is None
            # 重开默认值恢复
            click_button(drv, '清除日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            b2 = dlg.find_element(By.ID, 'log-clear-before')
            sw2 = dlg.find_element(By.ID, 'log-clear-keep-marked')
            out['reopen_before_value'] = b2.get_attribute('value')
            out['reopen_keep_marked'] = sw2.get_attribute('aria-checked') or sw2.get_attribute('data-checked')
            out['reopen_text'] = dlg.text
            # Esc
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.9)
            out['closed_by_esc'] = dialog(drv) is None
            # 遮罩
            click_button(drv, '清除日志')
            wait_dialog(drv)
            time.sleep(0.8)
            drv.execute_script("document.elementFromPoint(8, 8).click()")
            time.sleep(0.9)
            out['closed_by_overlay'] = dialog(drv) is None
            if dialog(drv) is not None:
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            out['never_clicked_clear'] = True
            return out
        step('Y6_clear_dialog_paths', clear_dialog_paths)

        def stats_vs_api():
            s = api_get('/logs/stats') or {}
            ui = page_total_text(drv)
            out = {'ui_total': ui, 'stats_total': s.get('total'), 'rows': len(rows(drv))}
            out['stats_keys'] = sorted(s.keys())[:12]
            return out
        step('Y7_stats_vs_api', stats_vs_api)

        def dark_clear():
            goto_logs(drv, 'dark')
            click_button(drv, '清除日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out = {'dark_class': drv.execute_script('return document.documentElement.className'),
                   'text': dlg.text}
            shot(drv, 'dark_1561_clear_dialog.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            out['closed_by_esc'] = dialog(drv) is None
            return out
        step('Y8_dark_clear', dark_clear)

        env_check('checklist_end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'results_int1561_checklist.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        log('FAILED STEPS: %s' % FAIL)


if __name__ == '__main__':
    main()
