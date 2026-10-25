# -*- coding: utf-8 -*-
"""INT-1731 四窗复测二段：深色 3 窗截图 + 声压窗三种提交/回读。

复用 verify_int1477_int1731 的驱动与辅助函数（导入即用，不跑其 main）。
夹具：沿用上一段自建的 2 轮用例（按名字查找）。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_int1477_int1731 as base  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

TAG = os.environ.get('FIXTAG', '10241546')
base.GROUP = '接线测试_INT1477R组' + TAG
base.NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']
NAMES = base.NAMES
ART = base.ART
OUT = {'fixtures': {}, 'dark': {}, 'submit': {}}


def log(*a):
    print(*a, flush=True)


def find_ids(d):
    import urllib.parse
    ids = {}
    for n in NAMES:
        r = base.api(d, 'GET', '/api/v1/testcases?page=1&per_page=20&keyword=' + urllib.parse.quote(n))
        data = (r.get('json') or {}).get('data') or {}
        lst = data.get('items') if isinstance(data, dict) else data
        hit = [x for x in (lst or []) if x.get('name') == n]
        ids[n] = hit[0]['id'] if hit else None
    return ids


def round_state(d, cid):
    r = base.api(d, 'GET', '/api/v1/testcases/' + str(cid))
    data = (r.get('json') or {}).get('data') or {}
    rounds = ((data.get('config') or {}).get('rounds') or [])
    return [{k: x.get(k) for k in ('round_number', 'spl', 'spl_value', 'spl_db')} for x in rounds]


def all_states(d, ids):
    return {n: round_state(d, ids[n]) for n in NAMES}


def spl_submit(d, mode, rounds_to_toggle, spl_value, shot_name):
    """mode: specific_deselect_first | specific_none | per_round_second"""
    base.clear_log(d)
    dlg = base.open_window(d, '批量设置声压', '批量设置声压级')
    rec = {'spl_value': spl_value}
    if mode.startswith('specific'):
        base.click_label(d, dlg, '指定轮次（统一设置）')
        # 默认勾选第1轮；specific_none 需把它取消
        labels = rounds_to_toggle
        for lbl in labels:
            for e in dlg.find_elements(By.XPATH, f".//label[normalize-space(.)='{lbl}']"):
                if e.is_displayed():
                    base.jsclick(d, e)
                    time.sleep(0.6)
                    break
        rec['selected_labels'] = labels
    else:
        base.click_label(d, dlg, '逐轮设置（每轮可不同）')
        tabs = [e for e in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='第2轮']")
                if e.is_displayed()]
        if tabs:
            base.jsclick(d, tabs[0])
            time.sleep(0.8)
        rec['active_tab'] = '第2轮'
    inp = [x for x in dlg.find_elements(By.XPATH, ".//input[@aria-label='声压级 dB']")
           if x.is_displayed()][0]
    inp.send_keys(spl_value)
    time.sleep(0.5)
    b = [x for x in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']")
         if x.is_displayed()]
    rec['confirm_disabled'] = not b[0].is_enabled() if b else None
    base.jsclick(d, b[0])
    t0 = time.time()
    while time.time() - t0 < 150:
        time.sleep(2)
        if not [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
                if e.is_displayed() and '批量设置声压级' in (e.text or '')]:
            break
    cs = base.calls(d)
    rec['elapsed'] = round(time.time() - t0, 1)
    rec['batch'] = [c for c in cs if '/testcases/batch' in c['url']]
    rec['toast'] = [e.text for e in d.find_elements(By.XPATH, "//*[@data-sonner-toast]")
                    if e.is_displayed()]
    rec['dialog_still_open'] = bool([e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
                                     if e.is_displayed() and '批量设置声压级' in (e.text or '')])
    base.shot(d, shot_name)
    if rec['dialog_still_open']:
        base.close_dialog(d, dlg)
    return rec


def main():
    d = base.driver()
    try:
        d.get(base.BASE + '/testcases/by-group')
        base.wait_page(d)
        ids = find_ids(d)
        OUT['fixtures'] = ids
        log('fixtures', ids)
        if any(v is None for v in ids.values()):
            raise AssertionError('夹具用例缺失')

        # ---------- 深色：device / spl / noise ----------
        base.open_page(d, dark=True)
        OUT['dark']['theme_check'] = d.execute_script(
            "return {mode: localStorage.getItem('iatp:theme:v1:mode'),"
            " cls: document.documentElement.className,"
            " bg: getComputedStyle(document.body).backgroundColor}")
        for key, btn, title in base.WINDOWS:
            if key == 'params':
                continue
            try:
                OUT['dark'][key] = base.window_probe(d, key, btn, title, 'dark')
            except Exception as e:
                OUT['dark'][key] = {'error': repr(e)}
                log('DARK-ERR', key, repr(e))
                try:
                    base.shot(d, f'r_{key}_dark_error')
                except Exception:
                    pass
                try:
                    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except Exception:
                    pass
                time.sleep(1)

        # ---------- 浅色：声压三种提交 ----------
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        base.open_page(d)
        OUT['submit']['before'] = all_states(d, ids)
        try:
            OUT['submit']['a_specific_round2'] = spl_submit(
                d, 'specific', ['第1轮', '第2轮'], '65', 'r_spl_submit_specific')
            OUT['submit']['after_a'] = all_states(d, ids)
        except Exception as e:
            OUT['submit']['a_specific_round2'] = {'error': repr(e)}
            log('SUB-A ERR', repr(e))
            try:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
            time.sleep(1)
        try:
            OUT['submit']['b_specific_none'] = spl_submit(
                d, 'specific_none', ['第1轮'], '66', 'r_spl_submit_none')
            OUT['submit']['after_b'] = all_states(d, ids)
        except Exception as e:
            OUT['submit']['b_specific_none'] = {'error': repr(e)}
            log('SUB-B ERR', repr(e))
            try:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
            time.sleep(1)
        try:
            OUT['submit']['c_per_round_round2'] = spl_submit(
                d, 'per_round', [], '67', 'r_spl_submit_per_round')
            OUT['submit']['after_c'] = all_states(d, ids)
        except Exception as e:
            OUT['submit']['c_per_round_round2'] = {'error': repr(e)}
            log('SUB-C ERR', repr(e))
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
    finally:
        json.dump(OUT, open(os.path.join(ART, 'rounds_evidence_b.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    log('DONE')


if __name__ == '__main__':
    main()
