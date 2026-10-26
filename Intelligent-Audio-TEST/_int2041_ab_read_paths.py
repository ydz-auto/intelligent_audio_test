# -*- coding: utf-8 -*-
"""INT-2041 真实库 A/B：``column`` vs ``snapshot`` 读源四类读路径逐字节等价 + 耗时。

判定口径（本卡验收 2/3）：

- **详情 / 搜索**：``report_repository.load_cases(report_id)`` → ``build_case_dict_from_entity``
  → ``build_case_item``（含 ``_expand_rounds`` 的 ``@round:N`` 展开）——与
  ``handle_get_report_cases`` 同一条装配链；
- **对比 / 挑选合并**：``report_repository.get_cases_by_report_id(report_id)`` →
  ``report_compare_helpers._get_source_cases_from_reports`` 的 case_item 映射——与
  对比 / 挑选合并读取同一条链；
- **导出**：``ReportAggregationService.build_export_data`` + ``build_export_payload('csv')``
  的报告元数据载荷（当前导出不读 report_cases，本项作为"不受影响"的对照）。

每份报告逐条比 ``canonical_bytes``（列表顺序参与比较），差异必须为 0；同时比
用例行 id 序列（行序）。

只读：只发 SELECT（``load_cases`` / ``get_cases_by_report_id`` / 报告元数据）。
禁止刷部署、禁止起本地栈（环境铁律）。

用法::

    python _int2041_ab_read_paths.py                  # 默认取用例数 Top 22（含报告 395）
    python _int2041_ab_read_paths.py --pre-fix        # 关掉键序还原=复现修复前口径
    python _int2041_ab_read_paths.py --reports 395,383,387
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from types import SimpleNamespace

DB_HOST = os.environ.get('INT2041_DB_HOST', '127.0.0.1')
DB_PORT = os.environ.get('INT2041_DB_PORT', '15432')
DB_NAME = os.environ.get('INT2041_DB_NAME', 'intelligent_audio_test')
DB_USER = os.environ.get('INT2041_DB_USER', 'intelligent_audio_test')
DB_PASS = os.environ.get('INT2041_DB_PASS', 'intelligent_audio_test666')

os.environ['DATABASE_URL'] = (
    f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

REQUIRED_REPORT = 395   # 793 例，父卡明确要求覆盖


def _log(msg: str) -> None:
    print(msg, flush=True)


def _select_reports(limit: int) -> list:
    """按用例数降序取前 N 份报告（保证覆盖 REQUIRED_REPORT）。"""
    import psycopg2
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                            password=DB_PASS, dbname=DB_NAME)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT report_id, count(*) FROM report_cases "
            "GROUP BY report_id ORDER BY count(*) DESC, report_id LIMIT %s",
            (limit,))
        report_ids = [int(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()
    if REQUIRED_REPORT not in report_ids:
        report_ids[-1] = REQUIRED_REPORT
    return report_ids


def _detail_items(repository, report_id: int) -> list:
    """详情链路：实体 → case dict → 前端用例项（含 @round 展开）。"""
    from report_service.application.services.report_aggregation.cases_mixin import (
        _AggregationCasesMixin,
    )
    cases = repository.load_cases(report_id)
    return {
        'ids': [c.id for c in cases],
        'items': [
            _AggregationCasesMixin.build_case_item(
                _AggregationCasesMixin.build_case_dict_from_entity(c))
            for c in cases
        ],
    }


def _compare_items(report_id: int) -> dict:
    """对比 / 挑选合并链路：get_cases_by_report_id → source_cases 映射。"""
    from report_service.application.services.report_compare_helpers import (
        ReportCompareHelpers,
    )
    cases = ReportCompareHelpers._get_source_cases_from_reports(
        [SimpleNamespace(id=report_id)])
    return {'ids': [c.get('id') for c in cases], 'items': cases}


def _export_payload(report_id: int) -> dict:
    """导出链路：报告元数据 csv 载荷（不读用例，作对照）。"""
    from report_service.application.services.report_aggregation_service import (
        ReportAggregationService,
    )
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    data = ReportAggregationService.build_export_data([report_id],
                                                      report_repository)
    if data is None:
        return {'filename': None, 'content_base64': ''}
    payload = ReportAggregationService.build_export_payload(data, 'csv')
    return {'filename': payload.get('filename'),
            'content_base64': payload.get('content_base64', '')}


def _read_once(report_ids: list, source: str) -> dict:
    """在某一读源下把四类读路径全跑一遍，返回结果与耗时。"""
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )

    os.environ['REPORT_CASE_SNAPSHOT_SOURCE'] = source
    out = {'source': source, 'reports': {}, 'seconds': {}}

    t_detail = t_compare = 0.0
    for rid in report_ids:
        t0 = time.perf_counter()
        out['reports'][rid] = {'detail': _detail_items(report_repository, rid)}
        t_detail += time.perf_counter() - t0
        _log(f'  [{source}] detail 报告 {rid}: '
             f'{len(out["reports"][rid]["detail"]["items"])} 例 '
             f'{time.perf_counter() - t0:.1f}s')

        t0 = time.perf_counter()
        out['reports'][rid]['compare'] = _compare_items(rid)
        t_compare += time.perf_counter() - t0
        _log(f'  [{source}] compare 报告 {rid}: '
             f'{len(out["reports"][rid]["compare"]["items"])} 例 '
             f'{time.perf_counter() - t0:.1f}s')

    # 导出抽 3 份
    t_export = 0.0
    for rid in report_ids[:3]:
        t0 = time.perf_counter()
        out['reports'][rid]['export'] = _export_payload(rid)
        t_export += time.perf_counter() - t0

    out['seconds'] = {'detail': t_detail, 'compare': t_compare,
                      'export': t_export,
                      'total': t_detail + t_compare + t_export}
    return out


def _interleaved_timing(report_ids: list, rounds: int = 2) -> dict:
    """交错计时（共享库/宿主负载下顺序分批会互相误导，见 devloop 性能口径）。

    逐报告交替先跑 column / snapshot，第 2 轮换起点，取每源的中位数与总和。
    """
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )

    samples = {'column': [], 'snapshot': []}
    for rnd in range(rounds):
        order = ['column', 'snapshot'] if rnd % 2 == 0 else ['snapshot', 'column']
        for rid in report_ids:
            for source in order:
                os.environ['REPORT_CASE_SNAPSHOT_SOURCE'] = source
                t0 = time.perf_counter()
                _detail_items(report_repository, rid)
                elapsed = time.perf_counter() - t0
                samples[source].append(elapsed)
                _log(f'  [timing r{rnd}] 报告 {rid} {source}: {elapsed:.2f}s')

    out = {}
    for source, values in samples.items():
        out[source] = {
            'total': round(sum(values), 2),
            'median': round(statistics.median(values), 3),
            'p90': round(sorted(values)[max(int(len(values) * 0.9) - 1, 0)], 3),
            'n': len(values),
        }
    out['ratio'] = {
        'total': round(out['snapshot']['total'] / max(out['column']['total'], 1e-9), 2),
        'median': round(out['snapshot']['median'] / max(out['column']['median'], 1e-9), 2),
    }
    return out


def _diff_report(column: dict, snapshot: dict, report_ids: list) -> dict:
    """逐报告、逐用例比 canonical 字节 + 行序。"""
    from shared.utils.raw_payload import canonical_bytes

    result = {'reports': [], 'diffs': 0, 'cases': 0}
    for rid in report_ids:
        c = column['reports'][rid]
        s = snapshot['reports'][rid]
        entry = {'report_id': rid, 'detail_cases': len(c['detail']['items']),
                 'detail_diffs': [], 'row_order_diff': False,
                 'compare_diffs': [], 'export_diff': False}
        result['cases'] += len(c['detail']['items'])

        if c['detail']['ids'] != s['detail']['ids']:
            entry['row_order_diff'] = True
        for idx, (ci, si) in enumerate(zip(c['detail']['items'],
                                          s['detail']['items'])):
            if canonical_bytes(ci) != canonical_bytes(si):
                entry['detail_diffs'].append(idx)

        for idx, (ci, si) in enumerate(zip(c['compare']['items'],
                                          s['compare']['items'])):
            if canonical_bytes(ci) != canonical_bytes(si):
                entry['compare_diffs'].append(idx)
        if len(c['compare']['items']) != len(s['compare']['items']):
            entry['compare_diffs'].append('length')

        if 'export' in c:
            entry['export_diff'] = (
                c['export']['filename'] != s['export']['filename']
                or c['export']['content_base64'] != s['export']['content_base64'])

        bad = (entry['detail_diffs'] or entry['compare_diffs']
               or entry['row_order_diff'] or entry['export_diff'])
        if bad:
            result['diffs'] += 1
            if entry['detail_diffs']:
                idx = entry['detail_diffs'][0]
                ci = c['detail']['items'][idx]
                si = s['detail']['items'][idx]
                entry['first_diff'] = _first_diff(ci, si)
        result['reports'].append(entry)
    return result


def _first_diff(column_item, snapshot_item) -> dict:
    """定位首个差异（字段 + 值的前 40 字符），复现父卡「值不变、顺序变」定位法。"""
    from shared.utils.raw_payload import canonical_bytes

    cb = canonical_bytes(column_item)
    sb = canonical_bytes(snapshot_item)
    pos = next((i for i, (a, b) in enumerate(zip(cb, sb)) if a != b), min(len(cb), len(sb)))
    start = max(0, pos - 60)
    return {'byte_offset': pos,
            'column': cb[start:pos + 80].decode('utf-8', 'replace'),
            'snapshot': sb[start:pos + 80].decode('utf-8', 'replace')}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--reports', default='')
    ap.add_argument('--limit', type=int, default=22)
    ap.add_argument('--pre-fix', action='store_true',
                    help='关掉键序还原，复现修复前口径')
    ap.add_argument('--json', default='')
    ap.add_argument('--no-timing', action='store_true',
                    help='只比等价、不跑交错计时（省一半时间）')
    ap.add_argument('--rounds', type=int, default=2,
                    help='交错计时轮数（第 2 轮换起点）')
    ap.add_argument('--timing-only', action='store_true',
                    help='只跑交错计时（等价结论沿用上一轮）')
    args = ap.parse_args()

    from shared.models.database import init_db
    init_db()

    if args.pre_fix:
        from report_service.infrastructure.persistence import (
            report_case_snapshot_store as store,
        )
        store.normalize_jsonb_order = lambda value: value  # 修复前行为
        print('[pre-fix] normalize_jsonb_order 已禁用（复现差异）')

    report_ids = ([int(x) for x in args.reports.split(',') if x.strip()]
                  if args.reports else _select_reports(args.limit))
    _log(f'[A/B] 报告 {len(report_ids)} 份: {report_ids}')

    if args.timing_only:
        timings = _interleaved_timing(report_ids, rounds=args.rounds)
        print(json.dumps({'reports': len(report_ids),
                          'interleaved_detail_timing': timings},
                         ensure_ascii=False, indent=2))
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as fh:
                json.dump({'timing': timings}, fh, ensure_ascii=False, indent=2)
        return 0

    t0 = time.perf_counter()
    column = _read_once(report_ids, 'column')
    t_column = time.perf_counter() - t0
    t0 = time.perf_counter()
    snapshot = _read_once(report_ids, 'snapshot')
    t_snapshot = time.perf_counter() - t0

    diff = _diff_report(column, snapshot, report_ids)

    timings = (_interleaved_timing(report_ids, rounds=args.rounds)
               if not args.no_timing else {})

    ratio = (t_snapshot / t_column) if t_column else 0
    summary = {
        'reports': len(report_ids),
        'cases': diff['cases'],
        'differing_reports': diff['diffs'],
        'detail_case_diffs': sum(len(r['detail_diffs']) for r in diff['reports']),
        'compare_case_diffs': sum(len(r['compare_diffs']) for r in diff['reports']),
        'row_order_diffs': sum(1 for r in diff['reports'] if r['row_order_diff']),
        'export_diffs': sum(1 for r in diff['reports'] if r['export_diff']),
        'seconds': {'column': round(t_column, 2), 'snapshot': round(t_snapshot, 2),
                    'ratio': round(ratio, 2)},
        'breakdown': {
            'column': {k: round(v, 2) for k, v in column['seconds'].items()},
            'snapshot': {k: round(v, 2) for k, v in snapshot['seconds'].items()},
        },
        'interleaved_detail_timing': timings,
        'per_case_ms': {
            'column': round(t_column * 1000 / max(diff['cases'], 1), 3),
            'snapshot': round(t_snapshot * 1000 / max(diff['cases'], 1), 3),
        },
    }
    print(json.dumps({**summary, 'reports_detail': diff['reports']},
                     ensure_ascii=False, indent=2), flush=True)
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'summary': summary, 'reports': diff['reports']}, fh,
                      ensure_ascii=False, indent=2)
    return 0 if summary['differing_reports'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
