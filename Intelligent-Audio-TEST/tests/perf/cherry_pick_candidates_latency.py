# -*- coding: utf-8 -*-
"""挑选合并候选聚合时延实测脚本（INT-1625）。

用途：在真实库上直接调用 task_service 的候选聚合（`list_candidates`），量
`GET /tasks/cherry-picks/candidates?page=1&per_page=200` 的后端聚合耗时——
即 60s gRPC DEADLINE_EXCEEDED 的成因段，不需要起本地栈（环境铁律：实测一律
docker，禁起本地栈）。

用法（宿主，conda 环境 intelligent_audio_test；端口取 docker 主 compose 的映射）：
    python tests/perf/cherry_pick_candidates_latency.py \
        --database-url postgresql://intelligent_audio_test:...@localhost:15432/intelligent_audio_test \
        --evaluation-port 53091 --device-port 50053 --audio-port 50052 \
        --per-page 200 --budget 30

只读：不写任何表，不改任务/结果状态。
口径：与真实请求同一条聚合路径（含 evaluated 标记、用例元信息、设备名、
result_type 解析）；不含网关与 gRPC 序列化开销，属后端聚合耗时下限。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, __file__.rsplit('tests', 1)[0])


def _prepare_env(args):
    os.environ['DATABASE_URL'] = args.database_url
    os.environ.setdefault('REDIS_URL', 'redis://localhost:16379/9')
    os.environ.setdefault('AUTH_MODE', 'off')
    os.environ.setdefault('EVALUATION_SERVICE_GRPC_PORT', str(args.evaluation_port))
    os.environ.setdefault('EVALUATION_CONFIG_GRPC_PORT', str(args.evaluation_port))
    os.environ.setdefault('DEVICE_SERVICE_GRPC_PORT', str(args.device_port))
    os.environ.setdefault('DEVICE_CONFIG_GRPC_PORT', str(args.device_port))
    os.environ.setdefault('AUDIO_SERVICE_GRPC_PORT', str(args.audio_port))
    os.environ.setdefault('AUDIO_CONFIG_GRPC_PORT', str(args.audio_port))
    for key, val in (
        ('OSS_ACCESS_KEY', 'intelligent_audio_test'),
        ('OSS_SECRET_KEY', 'intelligent_audio_test666'),
        ('OSS_ENDPOINT', 'http://localhost:9000'),
        ('OSS_REGION', 'us-east-1'),
        ('OSS_BUCKET_NAME', 'intelligent-audio-test'),
        ('OSS_KEY_PREFIX', 'intelligent_audio_test'),
    ):
        os.environ.setdefault(key, val)


def _measure(per_page, extra):
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    payload = {'page': 1, 'per_page': per_page}
    payload.update(extra or {})
    t0 = time.time()
    out = cherry_pick_service.list_candidates(payload)
    elapsed = time.time() - t0
    data = (out or {}).get('data') or {}
    return {
        'success': bool((out or {}).get('success')),
        'elapsed': elapsed,
        'items': len(data.get('items') or []),
        'total': data.get('total'),
        'message': (out or {}).get('message'),
    }


def main():
    parser = argparse.ArgumentParser(description='INT-1625 候选聚合时延实测（只读）')
    parser.add_argument('--database-url', required=True, help='真实库连接串')
    parser.add_argument('--evaluation-port', type=int, default=53091)
    parser.add_argument('--device-port', type=int, default=50053)
    parser.add_argument('--audio-port', type=int, default=50052)
    parser.add_argument('--per-page', type=int, default=200)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--budget', type=float, default=30.0,
                        help='验收线（秒）：per_page=200 单次耗时上限')
    parser.add_argument('--evaluation-status', default=None,
                        help='可选：completed/failed/pending，验证评估状态筛选路径')
    args = parser.parse_args()

    _prepare_env(args)

    from shared.models.database import init_db
    init_db()
    import task_service.infrastructure.persistence.models  # noqa: F401

    extra = {'evaluation_status': args.evaluation_status} if args.evaluation_status else {}
    # 预热：首连 gRPC 通道 + DB 连接池（跨主机建连 500~1500ms，不计入结论）
    _measure(5, extra)

    worst = 0.0
    failed = 0
    for i in range(max(1, args.repeat)):
        r = _measure(args.per_page, extra)
        if not r['success']:
            failed += 1
        worst = max(worst, r['elapsed'] if r['success'] else float('inf'))
        print(f"run#{i + 1} success={r['success']} elapsed={r['elapsed']:.2f}s "
              f"items={r['items']} total={r['total']} message={r['message']}")

    verdict = 'PASS' if (failed == 0 and worst <= args.budget) else 'FAIL'
    print(f"[{verdict}] per_page={args.per_page} worst={worst:.2f}s budget={args.budget}s "
          f"failed={failed}/{args.repeat}")
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
