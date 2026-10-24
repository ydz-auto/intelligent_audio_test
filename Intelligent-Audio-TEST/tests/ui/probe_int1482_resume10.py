# -*- coding: utf-8 -*-
"""INT-1482 续测探针10：抓统计页自己的 /reports 列表响应，看 task_id 是否可用于 case-averages。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By

OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        L.reset_fetch_log(d)
        d.get(L.BASE + '/report-statistics')
        time.sleep(18)
        log = L.fetch_log(d, 0)
        picks = [e for e in log if '/api/v1/reports' in e.get('url', '')]
        OUT['n_reqs'] = len(log)
        OUT['report_reqs'] = []
        for e in picks:
            body = e.get('resBody') or ''
            rec = {'method': e['method'], 'url': e['url'][:160], 'status': e.get('status')}
            try:
                j = json.loads(body)
                data = j.get('data') or {}
                items = data.get('items') or []
                rec['total'] = data.get('total')
                rec['items_n'] = len(items)
                rec['task_id_samples'] = [
                    {'id': i.get('id'), 'task_id': i.get('task_id'), 'type': i.get('report_type') or i.get('type')}
                    for i in items[:6]
                ]
                rec['numeric_task_id_n'] = len([i for i in items if isinstance(i.get('task_id'), int) and i.get('task_id') > 0])
                rec['type_of_task_id'] = sorted({type(i.get('task_id')).__name__ for i in items})
            except Exception as ex:
                rec['parse'] = str(ex)[:80]
                rec['body_head'] = body[:300]
            OUT['report_reqs'].append(rec)
        OUT['has_case_avg_req'] = any('/reports/case-averages' in e.get('url', '') for e in log)
        OUT['all_urls'] = [e.get('url', '')[:100] for e in log][:40]
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe10_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()
