# -*- coding: utf-8 -*-
"""INT-1488 主走查：日志页筛选/查询/详情 + 导出/清除模态窗（浅/深）。"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver, _open_trigger, _close_popups

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys


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
    log('login -> %s' % drv.current_url)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'tbody tr')


def last_requests(drv, needle):
    return [e for e in fetch_log(drv) if needle in e.get('url', '')]


def wait_request(drv, needle, since=0, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = [e for e in last_requests(drv, needle)][since:]
        if hits:
            return hits[-1]
        time.sleep(0.4)
    return None


def level_chip(drv, level):
    for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
        if (b.text or '').strip().startswith(level) and b.is_displayed():
            return b
    return None


def click_backdrop(drv):
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(drv).move_by_offset(8, 8).click().perform()
    time.sleep(0.7)


def main():
    os.makedirs(ART, exist_ok=True)
    if os.path.isdir(DL):
        shutil.rmtree(DL, ignore_errors=True)
    os.makedirs(DL, exist_ok=True)

    env_check('run_start')
    drv = _driver()  # noqa: F405
    try:
        login(drv)
        set_theme_and_goto_logs(drv, 'light')

        def baseline():
            clear_fetch_log(drv)
            drv.find_element(By.XPATH, "//button[normalize-space(.)='刷新日志']").click()
            time.sleep(2)
            ui_total = page_total_text(drv)
            api = api_total()
            stats = api_get('/logs/stats')
            stat_text = body(drv)
            shot(drv, 'light_01_logs_page.png')
            return {'ui_total': ui_total, 'api_total': api, 'rows': len(rows(drv)),
                    'stats': stats,
                    'stats_text': stat_text[stat_text.find('总日志条数'):stat_text.find('总日志条数') + 60],
                    'total_matches': ui_total == api and stats.get('total') == api}
        step('01_baseline_list', baseline)

        def filter_level_error():
            clear_fetch_log(drv)
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(0.5)
            time.sleep(1.8)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            ui_total = page_total_text(drv)
            api = api_total({'level': 'ERROR'})
            levels = [r.find_elements(By.CSS_SELECTOR, 'td')[3].text.strip() for r in rows(drv)[:10] if len(r.find_elements(By.CSS_SELECTOR, 'td')) > 5]
            shot(drv, 'light_02_filter_level_error.png')
            return {'request': req, 'ui_total': ui_total, 'api_total': api,
                    'visible_levels': sorted(set(levels))}
        step('02_filter_level_error', filter_level_error)

        def reset_filters():
            clear_fetch_log(drv)
            click_button(drv, '清除过滤器')
            time.sleep(2)
            return {'ui_total': page_total_text(drv), 'api_total': api_total()}
        step('03_reset_filters', reset_filters)

        def option_counts():
            out = {}
            out['category_options'] = select_options(drv, '分类')
            out['module_options'] = select_options(drv, '模块')
            out['mark_options'] = select_options(drv, '标记筛选')
            out['algorithm_options'] = select_options(drv, '算法类型')
            out['algorithm_api'] = [a.get('name') for a in (api_get('/algorithm/options') or {}).get('algorithms', [])]
            return out
        step('04_option_counts', option_counts)

        def filter_category():
            clear_fetch_log(drv)
            names = select_option(drv, '分类', '系统日志')
            time.sleep(2)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            trig = drv.find_element(By.CSS_SELECTOR, 'button[aria-label="分类"]')
            out = {'options': names, 'trigger_text': trig.text, 'request': req,
                   'ui_total': page_total_text(drv), 'api_total': api_total({'category': 'system'})}
            shot(drv, 'light_03_filter_category.png')
            return out
        step('05_filter_category', filter_category)

        def category_data_coverage():
            return {'category_auth_total': api_total({'category': 'auth'}),
                    'category_execution_total': api_total({'category': 'execution'}),
                    'category_test_total': api_total({'category': 'test'}),
                    'module_run_all_total': api_total({'module': 'run_all'}),
                    'module_evaluation_total': api_total({'module': 'evaluation'})}
        step('06_category_module_data_coverage', category_data_coverage)

        def filter_algorithm():
            clear_fetch_log(drv)
            names = select_option(drv, '算法类型', '小艺语音大模型')
            time.sleep(2)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            trig = drv.find_element(By.CSS_SELECTOR, 'button[aria-label="算法类型"]')
            return {'options': names, 'trigger_text': trig.text, 'request': req,
                    'ui_total': page_total_text(drv), 'api_total': api_total({'algorithm_type': 'voice_llm'})}
        step('07_filter_algorithm', filter_algorithm)

        def filter_keyword():
            clear_fetch_log(drv)
            click_button(drv, '清除过滤器')
            time.sleep(1.5)
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys('AUTH_LOGIN')
            time.sleep(2.5)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            out = {'request': req, 'ui_total': page_total_text(drv),
                   'api_total': api_total({'keyword': 'AUTH_LOGIN'})}
            shot(drv, 'light_04_filter_keyword.png')
            return out
        step('08_filter_keyword', filter_keyword)

        def filter_time_range():
            clear_fetch_log(drv)
            click_button(drv, '清除过滤器')
            time.sleep(1.5)
            start = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="开始时间"]')
            set_input_js(drv, start, '2026-10-23T00:00')
            time.sleep(2.5)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            api = api_total({'start_time': '2026-10-23T00:00:00'})
            out = {'request': req, 'ui_total': page_total_text(drv), 'api_total_start_0000': api}
            shot(drv, 'light_05_filter_time_range.png')
            return out
        step('09_filter_time_range', filter_time_range)

        def pagination():
            clear_fetch_log(drv)
            click_button(drv, '清除过滤器')
            time.sleep(1.5)
            # 分页条 Select 无 aria-label：页面内无 aria-label 的可见 combobox
            combos = [c for c in drv.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
                      if c.is_displayed() and not c.get_attribute('aria-label')]
            trig = combos[-1]
            trig_text_before = trig.text
            content = _open_trigger(drv, trig)
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            names = [(i.text or '').strip() for i in items]
            target = [i for i in items if (i.text or '').strip() == '50 条/页'][0]
            js_click(drv, target)
            time.sleep(2)
            _close_popups(drv)
            req = wait_request(drv, '/api/v1/logs?', 0, 15)
            out = {'trigger_text_before': trig_text_before, 'trigger_text': trig.text, 'options': names, 'request': req,
                   'rows': len([r for r in rows(drv) if r.find_elements(By.CSS_SELECTOR, 'td')]),
                   'footer': body(drv)[body(drv).find('共 '):body(drv).find('共 ') + 60]}
            shot(drv, 'light_06_pagesize_50.png')
            return out
        step('10_pagination_pagesize', pagination)

        def empty_state():
            click_button(drv, '清除过滤器')
            time.sleep(1.2)
            inp = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]')
            inp.send_keys('INT1488_NO_MATCH_ZZZ')
            deadline = time.time() + 15
            txt = ''
            while time.time() < deadline:
                txt = body(drv)
                if '未找到匹配日志' in txt or '暂无日志' in txt:
                    break
                time.sleep(0.5)
            shot(drv, 'light_07_empty_state.png')
            found = [t for t in ['未找到匹配日志', '暂无日志'] if t in txt]
            return {'empty_texts': found, 'rows': len(rows(drv)),
                    'skeleton': len(drv.find_elements(By.CSS_SELECTOR, '[data-slot="skeleton"]'))}
        step('11_empty_state', empty_state)

        def error_state():
            click_button(drv, '清除过滤器')
            time.sleep(1)
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1/logs*']})
            drv.get(BASE + '/logs')
            time.sleep(4)
            txt = body(drv)
            shot(drv, 'light_08_error_state.png')
            out = {'has_retry': '重试' in txt, 'has_error_state': ('加载失败' in txt or '获取失败' in txt or '请求失败' in txt or '重试' in txt),
                   'snippet': txt[txt.find('日志查看'):txt.find('日志查看') + 300]}
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
            drv.get(BASE + '/logs')
            WebDriverWait(drv, 30).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
            time.sleep(1)
            return out
        step('12_error_state', error_state)

        def detail_expand():
            row = rows(drv)[0]
            tds = row.find_elements(By.CSS_SELECTOR, 'td')
            js_click(drv, tds[2])
            time.sleep(1.2)
            txt = body(drv)
            has = '详细信息' in txt and '上下文信息' in txt
            fields = [t for t in ['时间', '级别', '分类', '模块', '算法类型', '来源', '设备ID', '任务ID', '线程ID', '内容'] if t in txt]
            shot(drv, 'light_09_row_detail.png')
            return {'detail_visible': has, 'fields': fields}
        step('13_row_detail', detail_expand)

        # ---------------- 导出弹窗 ----------------
        def export_dialog_open_light():
            # 后端 LogExportQuery 只认 level/module：用小结果集 level=ERROR（799 条）做非空导出
            click_button(drv, '清除过滤器')
            time.sleep(1.2)
            for lv in ['DEBUG', 'INFO', 'WARNING', 'CRITICAL']:
                chip = level_chip(drv, lv)
                if chip:
                    js_click(drv, chip)
                    time.sleep(0.5)
            time.sleep(2)
            clear_fetch_log(drv)
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.8)
            txt = dlg.text
            summary = {}
            for label in ['时间范围', '分类', '模块', '级别', '标记', '算法', '关键词']:
                m = re.search(re.escape(label) + r'\s*([^\n]*)', txt)
                summary[label] = m.group(1).strip() if m else None
            shot(drv, 'light_10_export_dialog.png')
            return {'dialog_text': txt, 'summary': summary,
                    'title': txt.split('\n')[0]}
        step('14_export_dialog_open', export_dialog_open_light)

        def export_format_options():
            dlg = dialog(drv)
            trig = dlg.find_element(By.CSS_SELECTOR, 'button[aria-label="格式"], button[aria-label="导出格式"]') if len(
                dlg.find_elements(By.CSS_SELECTOR, 'button[aria-label="格式"], button[aria-label="导出格式"]')) else None
            # 没有 aria-label 时用对话框内唯一 combobox
            combos = [c for c in dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if c.is_displayed()]
            trig = trig or combos[0]
            trig_text = trig.text
            content = _open_trigger(drv, trig)
            items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
            names = [(i.text or '').strip() for i in items]
            shot(drv, 'light_11_export_format_options.png')
            # 选 JSON
            target = [i for i in items if (i.text or '').strip() == 'JSON'][0]
            js_click(drv, target)
            time.sleep(0.6)
            _close_popups(drv)
            return {'options': names, 'trigger_text_before': trig_text,
                    'trigger_text_after': dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0].text}
        step('15_export_format_options', export_format_options)

        def export_small():
            dlg = dialog(drv)
            clear_fetch_log(drv)
            click_button(drv, '导出', dlg)
            req = wait_request(drv, '/api/v1/logs/export', 0, 20)
            path, size = wait_download('logs_', 120)
            content_head = ''
            if path and size:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content_head = f.read(600)
            toast = body(drv)
            return {'request': req, 'download_path': os.path.basename(path) if path else None,
                    'size': size, 'content_head': content_head[:400],
                    'toast': '日志已导出' in toast,
                    'dialog_still_open': dialog(drv) is not None}
        step('16_export_small_filtered', export_small)

        def export_reopen_residue():
            # 关闭后重开，检查格式是否残留上次选择
            dlg = dialog(drv)
            if dlg is not None:
                try:
                    drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
                except Exception:
                    pass
                time.sleep(0.6)
            if dialog(drv) is None:
                click_button(drv, '导出日志')
                time.sleep(0.8)
            dlg = dialog(drv)
            combos = [c for c in dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if c.is_displayed()]
            combo_text = combos[0].text if combos else ''
            return {'reopen_format_text': combo_text, 'residue': combo_text.strip().lower() in ('json', '文本', 'csv')}
        step('17_export_reopen_residue', export_reopen_residue)

        def export_close_paths():
            out = {}
            dlg = dialog(drv)
            click_button(drv, '取消', dlg)
            time.sleep(0.7)
            out['cancel_closed'] = dialog(drv) is None
            click_button(drv, '导出日志')
            time.sleep(0.7)
            drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.7)
            out['esc_closed'] = dialog(drv) is None
            click_button(drv, '导出日志')
            time.sleep(0.7)
            click_backdrop(drv)
            out['backdrop_closed'] = dialog(drv) is None
            if dialog(drv) is not None:
                drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            return out
        step('18_export_close_paths', export_close_paths)

        def export_large():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            clear_fetch_log(drv)
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.6)
            click_button(drv, '导出', dlg)
            req = wait_request(drv, '/api/v1/logs/export', 0, 30)
            path, size = wait_download('logs_', 180)
            content_head = ''
            if path and size:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content_head = f.read(300)
            if dialog(drv) is not None:
                try:
                    drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
                except Exception:
                    pass
            shot(drv, 'dark_04_export_large_after.png')
            return {'request': req, 'download_path': os.path.basename(path) if path else None,
                    'size': size, 'content_head': content_head, 'ui_total': page_total_text(drv)}
        # 大结果集导出放到深色截图之后（60s 级且会拖慢网关，别影响其余取证）

        # ---------------- 清除弹窗 ----------------
        def clear_dialog_state():
            click_button(drv, '清除日志')
            dlg = wait_dialog(drv)
            time.sleep(0.6)
            inp = dlg.find_element(By.ID, 'log-clear-before')
            sw = dlg.find_element(By.ID, 'log-clear-keep-marked')
            txt = dlg.text
            shot(drv, 'light_13_clear_dialog.png')
            m = re.search(r'将清除约\s*([\d,]+)\s*条日志', txt)
            return {'text': txt, 'datetime_value': inp.get_attribute('value'),
                    'keep_marked_checked': sw.get_attribute('aria-checked') or sw.get_attribute('data-checked'),
                    'estimated_text': m.group(1) if m else None,
                    'api_total': api_total()}
        step('20_clear_dialog_defaults', clear_dialog_state)

        def clear_dialog_edit():
            dlg = dialog(drv)
            inp = dlg.find_element(By.ID, 'log-clear-before')
            # datetime-local 直接 send_keys 分段输入不稳，用 JS 设值触发 React onChange
            set_input_js(drv, inp, '2026-10-22T00:00')
            sw = dlg.find_element(By.ID, 'log-clear-keep-marked')
            js_click(drv, sw)
            time.sleep(0.6)
            txt = dlg.text
            shot(drv, 'light_14_clear_dialog_edited.png')
            return {'datetime_value': inp.get_attribute('value'),
                    'keep_marked_checked': sw.get_attribute('aria-checked') or sw.get_attribute('data-checked'),
                    'text_after': txt[txt.find('将清除约'):txt.find('将清除约') + 80]}
        step('21_clear_dialog_edit', clear_dialog_edit)

        def clear_dialog_reopen_reset():
            out = {}
            dlg = dialog(drv)
            click_button(drv, '取消', dlg)
            time.sleep(0.8)
            out['cancel_closed'] = dialog(drv) is None
            click_button(drv, '清除日志')
            dlg = wait_dialog(drv)
            time.sleep(0.6)
            out['reopen_datetime'] = dlg.find_element(By.ID, 'log-clear-before').get_attribute('value')
            out['reopen_keep_marked'] = dlg.find_element(By.ID, 'log-clear-keep-marked').get_attribute('aria-checked') or dlg.find_element(By.ID, 'log-clear-keep-marked').get_attribute('data-checked')
            drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.7)
            out['esc_closed'] = dialog(drv) is None
            click_button(drv, '清除日志')
            time.sleep(0.6)
            click_backdrop(drv)
            out['backdrop_closed'] = dialog(drv) is None
            if dialog(drv) is not None:
                drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            return out
        step('22_clear_dialog_close_paths', clear_dialog_reopen_reset)

        # ---------------- 深色 ----------------
        def dark_pass():
            set_theme_and_goto_logs(drv, 'dark')
            shot(drv, 'dark_01_logs_page.png')
            click_button(drv, '导出日志')
            wait_dialog(drv)
            time.sleep(0.8)
            shot(drv, 'dark_02_export_dialog.png')
            drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.7)
            click_button(drv, '清除日志')
            wait_dialog(drv)
            time.sleep(0.8)
            shot(drv, 'dark_03_clear_dialog.png')
            drv.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)
            return {'theme_class': drv.execute_script('return document.documentElement.className')}
        step('23_dark_pass', dark_pass)
        step('24_export_large_unfiltered', export_large)

        env_check('before_delivery')
        RESULTS['requests'] = fetch_log(drv)[-40:]
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'results_main.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        log('\nFAILED STEPS: %s' % FAIL)


if __name__ == '__main__':
    main()
