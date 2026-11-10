# -*- coding: utf-8 -*-
"""INT-2381 峰值内存 / 耗时探针（隔离栈 + pg_dump 副本内运行）。

用途：在一次性容器里跑「查询链 GetCaseAverages」或「报告主生成链」，
读容器 cgroup memory.peak + 进程 VmHWM 作为峰值证据，并把业务输出落盘供
逐字节 diff。

用法（容器内 /app 下）：
    python tests/ui/probe_int2381_include_body_memory.py \
        --action query --task-id 402 --dump /tmp/q402.json
    python tests/ui/probe_int2381_include_body_memory.py \
        --action report --task-id 402 --dump /tmp/r402.json

约定：只在 pg_dump 副本库与一次性容器里跑，不碰共享主库（report 动作会软删
目标任务的既有报告，脚本对主库 DATABASE_URL 直接拒绝）。
"""
import argparse
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


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
    for path in ('/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/memory/memory.max_usage_in_bytes'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            continue
    return None


def _run_query(task_id):
    from shared.models.database import init_db
    from report_service.application.handlers.report_handlers import ReportQueryHandler

    init_db(pool_size=5)
    handler = ReportQueryHandler()
    started = time.time()
    result = handler.handle_get_case_averages({'task_id': int(task_id)})
    return result, time.time() - started


def _assert_not_main_db():
    """report 动作会软删目标任务的既有报告——只允许在副本库上跑。

    硬红线（卡面实测纪律）：不得在共享主栈 / 主库 intelligent_audio_test 上
    生成或重生成 402/407。这里按 DATABASE_URL 的库名兜底，主库直接拒绝。
    """
    url = os.environ.get('DATABASE_URL', '')
    if url.rstrip('/').endswith('/intelligent_audio_test'):
        raise SystemExit(
            '拒绝执行：DATABASE_URL 指向主库 intelligent_audio_test，'
            'report 动作会软删既有报告，请在 pg_dump 副本库上运行。')


def _run_report(task_id):
    from shared.models.database import init_db, get_db_session
    from report_service.infrastructure.persistence.models import Report as ReportPO
    from report_service.application.services.report_task_generator import ReportTaskGenerator

    _assert_not_main_db()
    init_db(pool_size=5)
    # 副本库内把既有报告软删，放行「按 task_id 去重」检查（只动副本，不碰主库）
    session = get_db_session()
    try:
        session.query(ReportPO).filter(ReportPO.task_id == int(task_id)).update(
            {ReportPO.deleted: True}, synchronize_session=False)
        session.commit()
    finally:
        session.close()

    started = time.time()
    ReportTaskGenerator._generate_task_report_async(int(task_id), None, None, None)
    elapsed = time.time() - started

    session = get_db_session()
    try:
        rows = (session.query(ReportPO)
                .filter(ReportPO.task_id == int(task_id), ReportPO.deleted == False)  # noqa: E712
                .order_by(ReportPO.id.desc()).all())
        report_id = rows[0].id if rows else None
    finally:
        session.close()
    return {'report_id': report_id}, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', choices=['query', 'report'], required=True)
    parser.add_argument('--task-id', type=int, required=True)
    parser.add_argument('--dump', default=None)
    args = parser.parse_args()

    if args.action == 'query':
        payload, elapsed = _run_query(args.task_id)
    else:
        payload, elapsed = _run_report(args.task_id)

    if args.dump and payload is not None:
        with open(args.dump, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True, default=str)

    print(json.dumps({
        'action': args.action,
        'task_id': args.task_id,
        'chunk_size': os.environ.get('REPORT_DIM_RESULT_BODY_CHUNK_SIZE', '(default)'),
        'elapsed_s': round(elapsed, 2),
        'peak_cgroup_bytes': _peak_cgroup_bytes(),
        'peak_rss_bytes': _peak_rss_bytes(),
        'dump': args.dump,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
