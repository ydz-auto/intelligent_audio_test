# -*- coding: utf-8 -*-
"""INT-1488 复走（第二轮）：INT-1561 修复后重走受影响三处显示。

覆盖：日志页工具栏 4 个 Select + 页脚每页条数、导出弹窗格式 + 导出成功关闭弹窗、
实时监控配置轮询间隔。浅色 / 深色各截，逐项记录请求与 GET 回读。

环境：docker iat-react-frontend http://localhost:15173 + 真实库栈 http://localhost:15000
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver, _open_trigger, _close_popups

import urllib.request
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


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


def goto_logs(drv, theme='light'):
    drv.get(BASE + '/')
    time.sleep(1)
    drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, theme))
    drv.get(BASE + '/logs')
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.5)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'tbody tr')


def toolbar_trigger(drv, label):
    """工具栏 Select 触发器（限定在页面主区，排除弹窗内残留）。"""
    for t in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="%s"]' % label):
        if t.is_displayed() and not t.find_elements(By.XPATH, './ancestor::*[@role="dialog"]'):
            return t
    raise AssertionError('工具栏触发器未找到: %s' % label)


def page_size_trigger(drv):
    """页脚每页条数触发器：页面内（非弹窗）唯一显示「N 条/页」的 combobox。"""
    for t in drv.find_elements(By.CSS_SELECTOR, 'button[role="combobox"]'):
        if not t.is_displayed():
            continue
        if t.find_elements(By.XPATH, './ancestor::*[@role="dialog"]'):
            continue
        if '条/页' in (t.text or ''):
            return t
    raise AssertionError('页脚每页条数触发器未找到')


def trigger_text(drv, el):
    return (el.text or '').strip()


def _close_select(drv, trig):
    """只关下拉，不按 Esc（Esc 会连带关掉所属弹窗）。再点一次触发器收回。"""
    for _ in range(2):
        contents = [c for c in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-content"]') if c.is_displayed()]
        if not contents:
            return
        try:
            js_click(drv, trig)
        except Exception:
            pass
        time.sleep(0.4)
    contents = [c for c in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-content"]') if c.is_displayed()]
    if contents:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.4)


def options_of(drv, trig):
    content = _open_trigger(drv, trig)
    items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
    names = [(i.text or '').strip() for i in items]
    _close_select(drv, trig)
    return names


def choose(drv, trig, text):
    content = _open_trigger(drv, trig)
    items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
    target = None
    for i in items:
        if (i.text or '').strip() == text:
            target = i
            break
    if target is None:
        raise AssertionError('选项未找到 %s，现有=%s' % (text, [(i.text or '').strip() for i in items]))
    js_click(drv, target)
    time.sleep(0.9)


def assert_eq(name, got, want, out):
    out[name] = {'got': got, 'want': want, 'ok': got == want}
    if got != want:
        raise AssertionError('%s 期望 %r 实际 %r' % (name, want, got))


def expression_total(params):
    return api_total(params)


def wait_total(drv, expected, timeout=90):
    deadline = time.time() + timeout
    seen = None
    while time.time() < deadline:
        seen = page_total_text(drv)
        if seen == expected:
            return seen
        time.sleep(1)
    return seen


def close_any_dialog(drv):
    if dialog(drv) is not None:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.7)


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(DL, exist_ok=True)
    for f in os.listdir(DL):
        try:
            os.remove(os.path.join(DL, f))
        except Exception:
            pass
    env_check('rewalk_start')
    drv = _driver()
    try:
        login(drv)
        goto_logs(drv, 'light')

        # ---------- A. 工具栏 4 个 Select 关闭态 + 选项数 ----------
        def toolbar_labels():
            out = {}
            want = {'分类': '所有分类', '模块': '所有模块',
                    '标记筛选': '所有标记', '算法类型': '全部算法'}
            for label, w in want.items():
                trig = toolbar_trigger(drv, label)
                got = trigger_text(drv, trig)
                assert_eq(label + '_closed', got, w, out)
            shot(drv, 'light_1561_toolbar_closed.png')
            return out
        step('A1_toolbar_closed_labels_light', toolbar_labels)

        def toolbar_options():
            out = {}
            counts = {'分类': 4, '模块': 4, '标记筛选': 5}
            for label, n in counts.items():
                names = options_of(drv, toolbar_trigger(drv, label))
                assert_eq(label + '_options', len(names), n, out)
                out[label + '_names'] = names
            # 算法：1 个真实算法选项 + 「全部算法」
            algo_names = options_of(drv, toolbar_trigger(drv, '算法类型'))
            api_algo = api_get('/algorithm/options')
            algo_api_n = len(api_algo) if isinstance(api_algo, list) else None
            out['algorithm_options'] = {'names': algo_names, 'count': len(algo_names),
                                        'api_count': algo_api_n,
                                        'ok': len(algo_names) == (algo_api_n or 0) + 1}
            return out
        step('A2_toolbar_option_counts', toolbar_options)

        # ---------- B. 选中后回显 + 接口回读 ----------
        def category_selected():
            out = {}
            clear_fetch_log(drv)
            choose(drv, toolbar_trigger(drv, '分类'), '系统日志')
            trig = toolbar_trigger(drv, '分类')
            assert_eq('category_after_select', trigger_text(drv, trig), '系统日志', out)
            api = expression_total({'category': 'system'})
            ui = wait_total(drv, api, 90)
            out['total'] = {'ui': ui, 'api': api, 'ok': ui == api}
            reqs = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '')]
            out['request'] = reqs[-1] if reqs else None
            shot(drv, 'light_1561_category_selected.png')
            assert out['total']['ok'], '分类筛选总数不一致 %s' % out['total']
            return out
        step('B1_category_selected_readback', category_selected)

        def reset_filters():
            click_button(drv, '清除过滤器')
            time.sleep(2)
            return {'category_after_reset': trigger_text(drv, toolbar_trigger(drv, '分类'))}
        step('B2_reset_filters', reset_filters)

        # ---------- C. 页脚每页条数 ----------
        def page_size():
            out = {}
            trig = page_size_trigger(drv)
            assert_eq('page_size_closed', trigger_text(drv, trig), '20 条/页', out)
            names = options_of(drv, trig)
            assert_eq('page_size_options', len(names), 4, out)
            out['page_size_names'] = names
            clear_fetch_log(drv)
            choose(drv, page_size_trigger(drv), '50 条/页')
            assert_eq('page_size_after_select', trigger_text(drv, page_size_trigger(drv)), '50 条/页', out)
            time.sleep(2)
            reqs = [e for e in fetch_log(drv) if '/api/v1/logs?' in e.get('url', '')]
            out['request'] = reqs[-1] if reqs else None
            out['row_count'] = len(rows(drv))
            assert_eq('row_count', out['row_count'], 50, out)
            assert out['request'] and 'per_page=50' in out['request']['url'], '未发出 per_page=50'
            shot(drv, 'light_1561_page_size_50.png')
            # 复位 20
            choose(drv, page_size_trigger(drv), '20 条/页')
            time.sleep(2)
            assert_eq('page_size_restored', trigger_text(drv, page_size_trigger(drv)), '20 条/页', out)
            return out
        step('C1_page_size_select', page_size)

        # ---------- D. 导出弹窗 ----------
        def export_dialog_format():
            out = {}
            for f in os.listdir(DL):
                try:
                    os.remove(os.path.join(DL, f))
                except Exception:
                    pass
            clear_fetch_log(drv)
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.2)
            out['summary'] = dlg.text[:400]
            fmt = dlg.find_element(By.ID, 'log-export-format')
            assert_eq('format_closed', trigger_text(drv, fmt), '文本', out)
            names = options_of(drv, fmt)
            assert_eq('format_options', names, ['文本', 'JSON', 'CSV'], out)
            choose(drv, dlg.find_element(By.ID, 'log-export-format'), 'JSON')
            assert_eq('format_after_select', trigger_text(drv, dlg.find_element(By.ID, 'log-export-format')), 'JSON', out)
            shot(drv, 'light_1561_export_dialog.png')
            return out
        step('D1_export_dialog_format_light', export_dialog_format)

        def export_submit_closes():
            out = {}
            clear_fetch_log(drv)
            dlg = wait_dialog(drv)
            btn = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='导出']") if b.is_displayed()][0]
            js_click(drv, btn)
            req = None
            deadline = time.time() + 90
            while time.time() < deadline:
                hits = [e for e in fetch_log(drv) if '/api/v1/logs/export' in e.get('url', '')]
                if hits:
                    req = hits[-1]
                    break
                time.sleep(0.5)
            out['request'] = req
            # 弹窗应在成功后被关闭
            closed = False
            deadline = time.time() + 30
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
                    out['rows'] = len(doc) if isinstance(doc, list) else None
                except Exception as e:
                    out['rows'] = 'parse_error:%s' % e
            out['toast'] = '日志已导出' in body(drv)
            shot(drv, 'light_1561_export_closed.png')
            assert closed, '导出成功后弹窗未关闭'
            assert req and req.get('status') == 200, '导出请求失败 %s' % req
            assert size > 0, '下载文件为空'
            return out
        step('D2_export_submit_closes_dialog', export_submit_closes)

        def export_reopen_residue():
            out = {}
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            out['format_on_reopen'] = trigger_text(drv, dlg.find_element(By.ID, 'log-export-format'))
            # Esc 关闭
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            out['closed_by_esc'] = dialog(drv) is None
            # 关闭按钮
            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(0.6)
            x = [b for b in dlg.find_elements(By.XPATH, ".//button[@aria-label='Close' or @aria-label='关闭']") if b.is_displayed()]
            if not x:
                x = [b for b in dlg.find_elements(By.CSS_SELECTOR, 'button') if b.is_displayed() and (b.text or '').strip() == '']
            if x:
                js_click(drv, x[-1])
            time.sleep(0.8)
            out['closed_by_button'] = dialog(drv) is None
            close_any_dialog(drv)
            return out
        step('D3_export_cancel_paths', export_reopen_residue)

        # ---------- E. 实时监控配置弹窗 ----------
        def realtime_config():
            out = {}
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            wait_text(drv, '实时监控中', 30)
            time.sleep(1)
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            interval = dlg.find_element(By.ID, 'realtime-poll-interval')
            assert_eq('interval_closed', trigger_text(drv, interval), '5s', out)
            names = options_of(drv, interval)
            assert_eq('interval_options', names, ['2s', '5s', '10s', '30s', '60s'], out)
            shot(drv, 'light_1561_realtime_config.png')
            choose(drv, dlg.find_element(By.ID, 'realtime-poll-interval'), '10s')
            assert_eq('interval_after_select',
                      trigger_text(drv, wait_dialog(drv).find_element(By.ID, 'realtime-poll-interval')), '10s', out)
            click_button(drv, '完成', drv)
            time.sleep(1.0)
            out['closed_by_done'] = dialog(drv) is None
            # 重开回读
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            reopened = trigger_text(drv, dlg.find_element(By.ID, 'realtime-poll-interval'))
            assert_eq('interval_on_reopen', reopened, '10s', out)
            shot(drv, 'light_1561_realtime_config_reopen.png')
            # 恢复 5s
            choose(drv, dlg.find_element(By.ID, 'realtime-poll-interval'), '5s')
            click_button(drv, '完成', drv)
            time.sleep(1.0)
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            assert_eq('interval_restored', trigger_text(drv, dlg.find_element(By.ID, 'realtime-poll-interval')), '5s', out)
            # Esc 取消路径
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            out['closed_by_esc'] = dialog(drv) is None
            # 关实时开关
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            time.sleep(1.0)
            out['realtime_off'] = '实时监控已停止' in body(drv)
            return out
        step('E1_realtime_config_light', realtime_config)

        env_check('rewalk_before_dark')

        # ---------- F. 深色 ----------
        def dark_all():
            out = {}
            goto_logs(drv, 'dark')
            out['html_class'] = drv.execute_script('return document.documentElement.className')
            assert 'dark' in out['html_class'], '深色未生效'
            for label, want in {'分类': '所有分类', '模块': '所有模块',
                                '标记筛选': '所有标记', '算法类型': '全部算法'}.items():
                assert_eq('dark_' + label, trigger_text(drv, toolbar_trigger(drv, label)), want, out)
            assert_eq('dark_page_size', trigger_text(drv, page_size_trigger(drv)), '20 条/页', out)
            shot(drv, 'dark_1561_toolbar_closed.png')

            click_button(drv, '导出日志')
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            assert_eq('dark_export_format', trigger_text(drv, dlg.find_element(By.ID, 'log-export-format')), '文本', out)
            shot(drv, 'dark_1561_export_dialog.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            out['dark_export_closed_by_esc'] = dialog(drv) is None

            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            wait_text(drv, '实时监控中', 30)
            time.sleep(1)
            cfg_btn = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='配置']") if b.is_displayed()][0]
            js_click(drv, cfg_btn)
            dlg = wait_dialog(drv)
            time.sleep(1.0)
            assert_eq('dark_interval', trigger_text(drv, dlg.find_element(By.ID, 'realtime-poll-interval')), '5s', out)
            shot(drv, 'dark_1561_realtime_config.png')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
            sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
            js_click(drv, sw)
            time.sleep(0.8)
            out['dark_realtime_off'] = '实时监控已停止' in body(drv)
            return out
        step('F1_dark_all', dark_all)

        # ---------- G. GET 回读基线 ----------
        def get_readback():
            out = {'ui_total': page_total_text(drv), 'api_total': expression_total({}),
                   'rows': len(rows(drv))}
            out['ok'] = abs((out['ui_total'] or 0) - (out['api_total'] or 0)) <= 5
            return out
        step('G1_get_readback', get_readback)

        env_check('rewalk_end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'results_int1561_rewalk.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        log('FAILED STEPS: %s' % FAIL)


if __name__ == '__main__':
    main()
