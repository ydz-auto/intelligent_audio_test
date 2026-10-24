# -*- coding: utf-8 -*-
"""INT-1482 续测：对比弹窗 UI 提交一次（任务 390+413，端点与 412+390 同一条）。"""
import atexit
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
STAMP = time.strftime('%H%M%S')
NAME = '接线测试_INT1482_对比_' + STAMP
CREATED = []


def save():
    with open(os.path.join(L.ART, 'cmpui_result.json'), 'w', encoding='utf-8') as f:
        json.dump({'out': OUT, 'created': CREATED}, f, ensure_ascii=False, indent=1, default=str)


atexit.register(save)


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
        time.sleep(2)
        for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')[:2]:
            try:
                L.js_click(d, tr.find_element(By.XPATH, ".//*[@role='checkbox']"))
                time.sleep(0.4)
            except Exception:
                pass
        L.click_text(d, '批量对比')
        L.wait_dialog(d, '报告对比')
        for _ in range(40):
            dlg = [x['el'] for x in L.dialogs(d) if '基于任务' in x['text']]
            if dlg and dlg[-1].find_elements(By.TAG_NAME, 'label'):
                break
            time.sleep(1)
        dropped = []
        for tid in (390, 413):
            dlg = [x['el'] for x in L.dialogs(d) if '基于任务' in x['text']][-1]
            done = False
            for lab in dlg.find_elements(By.TAG_NAME, 'label'):
                if ('#%d' % tid) in (lab.text or ''):
                    L.js_click(d, lab.find_element(By.CSS_SELECTOR, "[role='checkbox']"))
                    done = True
                    time.sleep(0.6)
                    break
            if not done:
                dropped.append(tid)
        OUT['tasks_dropped'] = dropped
        dlg = [x['el'] for x in L.dialogs(d) if '基于任务' in x['text']][-1]
        OUT['picked_text'] = dlg.text[-120:]
        for t in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if (t.text or '').strip() == '对比配置':
                L.js_click(d, t)
                break
        time.sleep(1.5)
        dlg = [x['el'] for x in L.dialogs(d) if '基于任务' in x['text']][-1]
        OUT['config_text'] = dlg.text[:300]
        n = dlg.find_element(By.ID, 'compare-name')
        n.clear()
        n.send_keys(NAME)
        L.shot(d, 'c01_compare_config_light')
        L.reset_fetch_log(d)
        t0 = L.now_ms()
        dlg = [x['el'] for x in L.dialogs(d) if '基于任务' in x['text']][-1]
        for b in dlg.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '生成对比报告':
                L.js_click(d, b)
                break
        cr = []
        for i in range(120):
            time.sleep(1)
            cr = [e for e in L.fetch_log(d, t0) if '/reports/compare' in e['url']]
            if cr:
                break
        OUT['cmp_req'] = [{k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody')} for e in cr]
        samples = []
        end = time.time() + 180
        while time.time() < end:
            time.sleep(2)
            cur = [x for x in L.dialogs(d) if any(k in x['text'] for k in ('正在生成', '生成完成', '生成失败', '排队')) and '基于任务' not in x['text']]
            if cur:
                txt = cur[-1]['text'][:250]
                if not samples or samples[-1] != txt:
                    samples.append(txt)
                if '生成完成' in txt or '生成失败' in txt:
                    L.shot(d, 'c02_compare_progress_light')
                    break
            elif samples:
                break
        OUT['progress_samples'] = samples
        time.sleep(4)
        OUT['url_after'] = d.current_url
        OUT['body_after'] = L.body(d)[:300]
        r = L.api(d, '/reports?page=1&per_page=50')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        mine = [i for i in items if NAME in (i.get('name') or '')]
        OUT['readback'] = [(i['id'], i['name'], i.get('report_type'), (i.get('summary') or {}).get('total_cases')) for i in mine[:3]]
        if mine:
            rid = mine[0]['id']
            CREATED.append(rid)
            OUT['report_id'] = rid
            det = L.api(d, '/reports/%d' % rid)
            dj = ((det.get('json') or {}).get('data') or {})
            OUT['detail'] = {'http': det['status'], 'name': dj.get('name'), 'type': dj.get('report_type'),
                             'summary': {k: (dj.get('summary') or {}).get(k) for k in ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                             'resources': (dj.get('summary') or {}).get('resources'),
                             'metric_data_n': len((dj.get('summary') or {}).get('metric_data') or [])}
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            OUT['detail_text'] = L.body(d)[:500]
            L.shot(d, 'c03_compare_detail_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            L.shot(d, 'c04_compare_detail_dark')
            L.apply_theme(d, 'light')
    except Exception:
        OUT['error'] = traceback.format_exc()[-1200:]
    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
