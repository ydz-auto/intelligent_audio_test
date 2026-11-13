# -*- coding: utf-8 -*-
"""INT-2436 M1 峰值分解探针（隔离栈 + pg_dump 副本内运行）。

在一次性容器里跑报告主生成链，对 INT-2381 迭代分块链的四个结构性开销
打分（另附容器 cgroup / 进程 VmHWM 总峰值）：

- 基础 map：非 body 拉取的完整维度结果 map（完整性基准，_get_dimension_results_batch 产出）；
- payload：带 body 拉取时**单块**的解析后体积，以及块内「唯一 sha 去重后」体积
  （两者之差 = 同报文按维度行重复传输/解析的 wire 级放大）；
- 聚合 item：块内提取标量后（raw_fields 化）的压缩 map；
- 报表结构：_build_task_summary 产出的 summary dict（落库 detail 的来源）。

口径与 §3.9.1 一致：pg_dump 副本库 + 一次性容器，容器 cgroup memory.peak 与
/proc/self/status VmHWM；对主库 DATABASE_URL 直接拒绝。

用法（容器内 /app 下）：
    python tests/ui/probe_int2436_peak_decomposition.py \
        --task-id 402 --dump /out/decomp_402.json
"""
import argparse
import dataclasses
import json
import os
import sys
import time


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _now_rss_bytes():
    try:
        with open('/proc/self/status', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _peak_rss_bytes():
    try:
        with open('/proc/self/status', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VmHWM:'):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _peak_cgroup_bytes():
    for path in ('/sys/fs/cgroup/memory.peak',
                 '/sys/fs/cgroup/memory/memory.max_usage_in_bytes'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            continue
    return None


def _deep_size(obj, _memo=None):
    """估算对象图的常驻字节数（按对象身份去重，避免共享串重复计数）。"""
    if _memo is None:
        _memo = set()
    oid = id(obj)
    if oid in _memo:
        return 0
    _memo.add(oid)
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            size += _deep_size(k, _memo) + _deep_size(v, _memo)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            size += _deep_size(item, _memo)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            size += _deep_size(getattr(obj, f.name), _memo)
    elif hasattr(obj, '__dict__'):
        size += _deep_size(obj.__dict__, _memo)
    return size


def _raw_response(row):
    return row.get('api_raw_response')


def _assert_not_main_db():
    url = os.environ.get('DATABASE_URL', '')
    if url.rstrip('/').endswith('/intelligent_audio_test'):
        raise SystemExit(
            '拒绝执行：DATABASE_URL 指向主库 intelligent_audio_test，'
            'report 动作会软删既有报告，请在 pg_dump 副本库上运行。')


def _patch_recorder():
    """给聚合链挂峰值分解打点，返回 (metrics, unpatch)。"""
    from report_service.application.services import report_data_builder_task_mixin as rdbtm
    from report_service.application.services.report_task_generator import ReportTaskGenerator

    metrics = {
        'chunk_size': os.environ.get('REPORT_DIM_RESULT_BODY_CHUNK_SIZE', '(default)'),
        'base_map': {},
        'payload': {},
        'aggregate_items': {},
        'report_structure': {},
        'rss_trace': [],
    }

    original_compressed = rdbtm.ReportDataTaskMixin._get_dimension_results_compressed
    original_iter = rdbtm._grpc_iter_dimension_results_with_body
    original_summary = ReportTaskGenerator._build_task_summary

    chunk_stats = []

    def _recording_iter(result_ids):
        for chunk_map, coverage in original_iter(result_ids):
            rows_all = [row for rows in chunk_map.values() for row in rows]
            raws = [_raw_response(row) for row in rows_all]
            first_raw = next((r for r in raws if r is not None), None)
            chunk_stats.append({
                'result_ids': len(chunk_map),
                'rows': len(rows_all),
                'raw_rows': sum(1 for r in raws if r is not None),
                'chunk_deep_bytes': _deep_size(chunk_map),
                'first_raw_deep_bytes': _deep_size(first_raw) if first_raw is not None else 0,
                'first_raw_json_bytes': (
                    len(json.dumps(first_raw, ensure_ascii=False).encode('utf-8'))
                    if first_raw is not None else 0),
                'requested_ids': len(coverage.get('requested_ids') or []),
                'failed_chunks': len(coverage.get('failed_chunks') or []),
                'dropped_ids': len(coverage.get('dropped_ids') or []),
            })
            yield chunk_map, coverage

    def _wrapped_compressed(base_map, result_ids, output_params_by_dim=None):
        rss0 = _now_rss_bytes()
        base_rows = sum(len(v) for v in (base_map or {}).values())
        metrics['base_map'] = {
            'results': len(base_map or {}),
            'rows': base_rows,
            'deep_bytes': _deep_size(base_map or {}),
            'rss_before_bytes': rss0,
        }
        # 记录压缩 map 本身相对基础 map 的增量，便于区分「基础行」与「raw_fields 标量」
        result = original_compressed(base_map, result_ids, output_params_by_dim)
        compressed, coverage = result
        rows_after = sum(len(v) for v in compressed.values())
        metrics['aggregate_items'] = {
            'results': len(compressed),
            'rows': rows_after,
            'deep_bytes': _deep_size(compressed),
            'rss_after_bytes': _now_rss_bytes(),
            'requested_results': len(coverage.get('requested_ids') or []),
            'covered_results': len(coverage.get('covered_ids') or []),
            'failed_chunks': len(coverage.get('failed_chunks') or []),
            'dropped_ids': len(coverage.get('dropped_ids') or []),
            'rows_without_body': coverage.get('rows_without_body'),
            'total_rows': coverage.get('total_rows'),
        }
        if chunk_stats:
            metrics['payload'] = {
                'chunks': len(chunk_stats),
                'max_chunk_deep_bytes': max(c['chunk_deep_bytes'] for c in chunk_stats),
                'max_rows_per_chunk': max(c['rows'] for c in chunk_stats),
                'max_raw_rows_per_chunk': max(c['raw_rows'] for c in chunk_stats),
                'max_first_raw_deep_bytes': max(
                    c['first_raw_deep_bytes'] for c in chunk_stats),
                'max_first_raw_json_bytes': max(
                    c['first_raw_json_bytes'] for c in chunk_stats),
                'sum_chunk_deep_bytes': sum(c['chunk_deep_bytes'] for c in chunk_stats),
                'sum_raw_rows': sum(c['raw_rows'] for c in chunk_stats),
                'chunk_samples': chunk_stats[:3] + chunk_stats[-2:],
            }
        metrics['rss_trace'].append(_now_rss_bytes())
        return result

    def _wrapped_summary(task, task_id, results, data_dict):
        rss0 = _now_rss_bytes()
        summary = original_summary(task, task_id, results, data_dict)
        metrics['report_structure'] = {
            'summary_deep_bytes': _deep_size(summary),
            'rss_before_bytes': rss0,
            'rss_after_bytes': _now_rss_bytes(),
        }
        return summary

    rdbtm.ReportDataTaskMixin._get_dimension_results_compressed = staticmethod(_wrapped_compressed)
    rdbtm._grpc_iter_dimension_results_with_body = _recording_iter
    ReportTaskGenerator._build_task_summary = staticmethod(_wrapped_summary)

    def _unpatch():
        rdbtm.ReportDataTaskMixin._get_dimension_results_compressed = original_compressed
        rdbtm._grpc_iter_dimension_results_with_body = original_iter
        ReportTaskGenerator._build_task_summary = original_summary

    return metrics, _unpatch


def _run_report(task_id, metrics):
    from shared.models.database import init_db, get_db_session
    from report_service.infrastructure.persistence.models import Report as ReportPO
    from report_service.application.services.report_task_generator import ReportTaskGenerator

    _assert_not_main_db()
    init_db(pool_size=5)
    session = get_db_session()
    try:
        session.query(ReportPO).filter(ReportPO.task_id == int(task_id)).update(
            {ReportPO.deleted: True}, synchronize_session=False)
        session.commit()
    finally:
        session.close()

    started = time.time()
    ReportTaskGenerator._generate_task_report_async(int(task_id), None, None, None)
    metrics['elapsed_s'] = round(time.time() - started, 2)

    session = get_db_session()
    try:
        rows = (session.query(ReportPO)
                .filter(ReportPO.task_id == int(task_id), ReportPO.deleted == False)  # noqa: E712
                .order_by(ReportPO.id.desc()).all())
        metrics['report_id'] = rows[0].id if rows else None
    finally:
        session.close()


def _db_payload_summary(task_id):
    """库侧报文口径：行数 / 唯一 sha 数 / gzip 字节（去重前后）/ 单结果最大行数。

    只作 payload 字节的参照系（行集合按 evaluation_status 过滤，报告链另按
    用例评估状态过滤，数量可能更小）。
    """
    from sqlalchemy import text
    from shared.models.database import get_db_session

    base_sql = (
        "select count(*) as rows, "
        "count(distinct d.api_raw_response_sha256) as shas, "
        "coalesce(sum(d.api_raw_response_bytes), 0) as gzip_bytes_sum, "
        "count(*) filter (where d.api_raw_response_sha256 is null) as rows_without_sha "
        "from test_result_dimensions d join test_results r on r.id = d.test_result_id "
        "where r.task_id = :tid and d.evaluation_status <> 'failed'"
    )
    uniq_sql = (
        "select coalesce(sum(b), 0) as uniq_gzip_bytes from ("
        "select max(d.api_raw_response_bytes) as b from test_result_dimensions d "
        "join test_results r on r.id = d.test_result_id "
        "where r.task_id = :tid and d.evaluation_status <> 'failed' "
        "and d.api_raw_response_sha256 is not null group by d.api_raw_response_sha256) t"
    )
    per_result_sql = (
        "select coalesce(max(c), 0) as max_rows_per_result, count(*) as results from ("
        "select d.test_result_id, count(*) as c from test_result_dimensions d "
        "join test_results r on r.id = d.test_result_id "
        "where r.task_id = :tid and d.evaluation_status <> 'failed' "
        "and d.api_raw_response_sha256 is not null group by d.test_result_id) t"
    )
    session = get_db_session()
    try:
        base = session.execute(text(base_sql), {'tid': int(task_id)}).mappings().first()
        uniq = session.execute(text(uniq_sql), {'tid': int(task_id)}).mappings().first()
        per_result = session.execute(
            text(per_result_sql), {'tid': int(task_id)}).mappings().first()
    finally:
        session.close()
    return {
        'rows': int(base['rows']),
        'unique_shas': int(base['shas']),
        'rows_without_sha': int(base['rows_without_sha']),
        'gzip_bytes_sum': int(base['gzip_bytes_sum']),
        'unique_gzip_bytes': int(uniq['uniq_gzip_bytes']),
        'max_rows_per_result': int(per_result['max_rows_per_result']),
        'results_with_payload': int(per_result['results']),
        'row_scope': 'evaluation_status<>failed（报告链另按用例评估状态过滤）',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', type=int, required=True)
    parser.add_argument('--dump', default=None)
    args = parser.parse_args()

    metrics, unpatch = _patch_recorder()
    try:
        _run_report(args.task_id, metrics)
    finally:
        unpatch()

    try:
        metrics['db_payload'] = _db_payload_summary(args.task_id)
    except Exception as e:  # noqa: BLE001 —— 分解口径失败不影响主结论
        metrics['db_payload'] = {'error': str(e)}

    metrics.update({
        'task_id': args.task_id,
        'peak_cgroup_bytes': _peak_cgroup_bytes(),
        'peak_rss_bytes': _peak_rss_bytes(),
        'final_rss_bytes': _now_rss_bytes(),
    })
    out = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
    if args.dump:
        with open(args.dump, 'w', encoding='utf-8') as f:
            f.write(out)
    print(out)


if __name__ == '__main__':
    main()
