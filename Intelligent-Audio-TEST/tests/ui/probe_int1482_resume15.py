# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮探针15：评估维度读模型是否为空（case-averages 的 metric_data 来源）。

若 evaluation_service ListDimensions 返回 0 条，则任何任务的 case-averages metric_data 都恒空，
统计页评估维度/散点/热力图不是数据条件问题而是维度读模型缺口——必须区分清楚再写结论。
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
        for path in ('/dimensions?page=1&per_page=10',
                     '/dimensions?page=1&per_page=200',
                     '/evaluation/dimensions?page=1&per_page=10',
                     '/dimension-categories?page=1&per_page=10'):
            r = L.api(d, path)
            j = r.get('json') or {}
            data = j.get('data')
            items = (data or {}).get('items') if isinstance(data, dict) else None
            OUT[path] = {
                'http': r['status'],
                'msg': j.get('message'),
                'total': (data or {}).get('total') if isinstance(data, dict) else None,
                'items_n': len(items) if isinstance(items, list) else None,
                'first': items[0] if isinstance(items, list) and items else None,
            }
        print('ok')
    finally:
        os.makedirs(L.ART, exist_ok=True)
        with open(os.path.join(L.ART, 'probe15_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()
