# -*- coding: utf-8 -*-
"""INT-2436 报告内容规范化导出（跨分块逐字节比对用）。

按 report_id 导出报告各表内容，去掉自增 id / report_id / 时间戳 / 操作人等
每次生成都会变化的列，按稳定键排序后输出一份规范化 JSON，供 chunk=4 与
chunk=1 的产物做 diff（「逐字节不变」证据）。

用法（容器内 /app 下，副本库）：
    python tests/ui/probe_int2436_report_content_dump.py --report-id 444 --out /out/c444.json
"""
import argparse
import datetime
import decimal
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# (表名, 参与比对的列, 排序键)
_TABLES = (
    ('test_reports', ('task_id', 'type', 'status', 'analysis', 'algorithm_type', 'visibility'),
     ('task_id', 'status')),
    ('report_summaries', ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate',
                          'duration', 'started_at', 'completed_at', 'task_ids', 'review_count'),
     ('task_ids',)),
    ('report_summary_meta', ('dimension_values', 'case_categories', 'all_case_tags', 'devices',
                             'apis', 'resources', 'resource_headers', 'all_metrics',
                             'field_mappings'), ()),
    ('report_raw_data', ('raw_data',), ()),
    ('report_cases', ('test_case_id', 'algorithm_type', 'logs'), ('test_case_id',)),
    ('report_metric_stats', ('metric_data', 'tag_metric_data', 'tag_category_metric_data',
                             'case_type_stats', 'device_stats', 'api_stats'), ()),
)


def _jsonable(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-id', type=int, required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    from sqlalchemy import text
    from shared.models.database import init_db, get_db_session

    init_db(pool_size=2)
    session = get_db_session()
    payload = {}
    try:
        for table, columns, order_by in _TABLES:
            where = 'id = :rid' if table == 'test_reports' else 'report_id = :rid'
            order = (' order by ' + ', '.join(order_by)) if order_by else ' order by id'
            sql = f"select {', '.join(columns)} from {table} where {where}{order}"
            rows = session.execute(text(sql), {'rid': args.report_id}).mappings().all()
            payload[table] = [
                {c: _jsonable(row[c]) for c in columns} for row in rows
            ]
    finally:
        session.close()

    out = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(out)
    print(json.dumps({
        'report_id': args.report_id,
        'out': args.out,
        'bytes': len(out.encode('utf-8')),
        'rows': {k: len(v) for k, v in payload.items()},
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
