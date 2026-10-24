# -*- coding: utf-8 -*-
"""INT-1806 验收端到端夹具（服务端隔离进程，非产品代码）。

扮演 task_service：真实 `TaskDataServiceServicer` + 真实 gRPC server，作为审计
文件的**唯一写盘者**（H4）。启动时先走 S4 直写路径（发布 / 人工复核 / AI 复核）
与同微秒 cursor 探针，再等待编排器写 STOP 文件。

环境变量：
    E2E_GRPC_PORT          监听端口
    E2E_READY_FILE         就绪标记文件
    E2E_STOP_FILE          停止标记文件
    E2E_DB_TIME_ADAPTER    '1' 时给 log_repository 包一层时间适配（仅 sqlite：
                           worker 送 ISO 串，sqlite 的 DateTime 只接受 datetime）
"""
import json
import os
import sys
import time
from concurrent import futures
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'shared', 'proto'))

CST = timezone(timedelta(hours=8))


def main():
    port = int(os.environ['E2E_GRPC_PORT'])
    ready_file = os.environ['E2E_READY_FILE']
    stop_file = os.environ['E2E_STOP_FILE']

    import grpc

    from shared.models.database import Base, get_engine, init_db
    from task_service.infrastructure.persistence.models.system_models import Log
    init_db()
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])

    from task_service.interfaces.grpc import task_data_service as tds

    if os.environ.get('E2E_DB_TIME_ADAPTER') == '1':
        _orig_batch_create = tds.log_repository.batch_create

        def _patched(rows):
            fixed = []
            for row in rows:
                row = dict(row)
                if isinstance(row.get('time'), str):
                    try:
                        row['time'] = datetime.fromisoformat(row['time'])
                    except ValueError:
                        pass
                fixed.append(row)
            return _orig_batch_create(fixed)

        tds.log_repository.batch_create = _patched

    from shared.proto import task_service_pb2_grpc
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    task_service_pb2_grpc.add_TaskDataServiceServicer_to_server(
        tds.TaskDataServiceServicer(), server)
    bound = server.add_insecure_port('127.0.0.1:%d' % port)
    server.start()

    # ---- S4 直写路径（task_service 进程内，category=system）----
    from shared.logging.audit_writer import write_audit_event
    from shared.models.common_enums import AuditEvent, AuditLogCategory
    from task_service.application.services.published_task_service import PublishedTaskService
    from task_service.application.task.ai_review_service import AiReviewService
    from task_service.application.task.review_service import ReviewService

    PublishedTaskService._write_audit(AuditEvent.PUBLISHED_TASK_CREATED, {
        'published_task_id': 101,
        'task_group_id': 101,
        'version': 1,
        'source_task_id': 55,
        'published_by': 42,
    })
    ReviewService._write_audit([9001, 9002], 'completed', 'completed', [71],
                               operator_id=42)
    AiReviewService._write_audit(AuditEvent.AI_REVIEW_INITIATED.value,
                                 result_ids=[9001], affected_task_ids=[71],
                                 force=True)

    # ---- H3：同一微秒两条事件，cursor 必须 +1 ----
    moment = datetime.now(CST)
    for _ in range(2):
        write_audit_event(
            event='CURSOR_PROBE',
            category=AuditLogCategory.SYSTEM.value,
            module='cursor_probe',
            source='task_service',
            content=json.dumps({'event': 'CURSOR_PROBE', 'operator_id': 7},
                               ensure_ascii=False),
            time=moment,
        )

    with open(ready_file, 'w', encoding='utf-8') as handle:
        handle.write(str(bound))

    deadline = time.time() + 240
    while not os.path.exists(stop_file) and time.time() < deadline:
        time.sleep(0.1)
    server.stop(0)


if __name__ == '__main__':
    main()
