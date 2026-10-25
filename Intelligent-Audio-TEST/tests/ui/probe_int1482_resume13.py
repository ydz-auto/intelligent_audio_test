# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮探针13：核对 INT-1776 task_name 是否已生效，并预判任务 411 的统计页指标可用性。

背景：任务 411「E2E测试任务_2026/9/24 16:18:31」completed / 2 用例关联 / 2 结果 / 6 维度(全 completed) /
1 设备 / test_reports 0 行（含软删），是当前真实库里唯一「有 task_case_relations + 有结果与维度 + 无报告」
的可用夹具。先用 case-averages 预判指标层是否有数据，避免生成后才发现仍空。
"""
import json
import os
import sys

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        r = L.api(d, '/reports?page=1&per_page=5&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['list_http'] = r['status']
        OUT['list_items'] = [
            {'id': i.get('id'), 'task_id': i.get('task_id'),
             'has_task_name': 'task_name' in i, 'task_name': i.get('task_name')}
            for i in items
        ]
        for rid in (564, 566):
            rr = L.api(d, '/reports/%d' % rid)
            dj = ((rr.get('json') or {}).get('data') or {})
            OUT['detail_%d' % rid] = {
                'http': rr['status'], 'task_id': dj.get('task_id'),
                'has_task_name': 'task_name' in dj, 'task_name': dj.get('task_name'),
            }
        for tid in (411, 412):
            ar = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=180)
            j = ar.get('json') or {}
            data = j.get('data') or {}
            OUT['case_avg_%d' % tid] = {
                'http': ar['status'], 'msg': j.get('message'),
                'total_cases': data.get('total_cases'),
                'total_results': data.get('total_results'),
                'overall_n': len(data.get('overall_averages') or []),
                'resources_n': len(data.get('resources') or []),
                'metric_data_n': len(data.get('metric_data') or []),
                'metric_sample': (data.get('metric_data') or [])[:2],
                'partial': data.get('partial'),
                'keys': sorted(data.keys()),
            }
        print('ok')
    finally:
        os.makedirs(L.ART, exist_ok=True)
        with open(os.path.join(L.ART, 'probe13_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()
