# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮探针14：横向比对候选任务的 case-averages 指标可用性。

目的：找出「有 task_case_relations + 有结果维度 + 无存活报告」且 metric_data 非空的任务，
作为统计页评估维度/设备性能/散点·热力图的真实数据夹具。
"""
import json
import os
import sys

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

TASKS = [412, 413, 407, 411, 598, 585, 579, 575, 563, 495, 482]
OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        for tid in TASKS:
            ar = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=240)
            j = ar.get('json') or {}
            data = j.get('data') or {}
            md = data.get('metric_data') or []
            OUT[str(tid)] = {
                'http': ar['status'], 'msg': j.get('message'),
                'total_cases': data.get('total_cases'),
                'total_results': data.get('total_results'),
                'overall_n': len(data.get('overall_averages') or []),
                'resources_n': len(data.get('resources') or []),
                'metric_data_n': len(md),
                'resource_headers': data.get('resource_headers'),
                'metric_sample': md[:2],
                'partial': data.get('partial'),
            }
            print(tid, OUT[str(tid)]['total_cases'], OUT[str(tid)]['metric_data_n'],
                  OUT[str(tid)]['resources_n'], flush=True)
    finally:
        os.makedirs(L.ART, exist_ok=True)
        with open(os.path.join(L.ART, 'probe14_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()
