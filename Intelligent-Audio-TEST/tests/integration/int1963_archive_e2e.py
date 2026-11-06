# -*- coding: utf-8 -*-
"""INT-1963 一次性实测：日志归档「先上传、后删除 + 分批」端到端校验。

跑法（宿主，需要 docker 主栈的 postgres:15432 与 rustfs:9000）：

    python tests/integration/int1963_archive_e2e.py success
    python tests/integration/int1963_archive_e2e.py failure

- success：在**隔离库**（新建 int1963_archive_e2e，用完即删）造 3000 行冷日志，
  经真实 servicer 走完整驱动循环，校验 archived == deleted、归档对象内容与
  删除行逐条对应、单批响应字节数远低于 GRPC_MAX_MESSAGE_MB。
- failure：把 OSS 端点指成不可达（127.0.0.1:9），跑一轮，断言库内行数不变、
  没有 local:// 本地落盘产物。

不连主库、不写生产 OSS 前缀：隔离库独立创建，归档对象一律落在
OSS_KEY_PREFIX=int1963_e2e 下，跑完删除。脚本不参与 pytest 收集（文件名
不是 test_*.py），只在需要复跑实测时手动执行。
"""
import json
import os
import sys
from datetime import datetime, timedelta

# 直接以脚本方式运行时（python tests/integration/xxx.py），sys.path[0] 是本文件
# 目录而非仓库根；把仓库根补进来才能 import shared / task_service。
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

PG_HOST = '127.0.0.1'
PG_PORT = 15432
PG_USER = 'intelligent_audio_test'
PG_PASSWORD = 'intelligent_audio_test666'
E2E_DB = 'int1963_archive_e2e'
OSS_PREFIX = 'int1963_e2e'
OSS_BUCKET = 'intelligent-audio-test'
COLD_ROWS = 3000
HOT_ROWS = 5
BATCH_DAYS = 7


def _log(msg):
    print(f'[e2e] {msg}', flush=True)


# --------------------------------------------------------------------------
# 隔离库
# --------------------------------------------------------------------------

def create_isolated_db():
    import psycopg2
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASSWORD, dbname='postgres',
                            connect_timeout=10)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f'DROP DATABASE IF EXISTS {E2E_DB} WITH (FORCE)')
        cur.execute(f'CREATE DATABASE {E2E_DB}')
        cur.close()
    finally:
        conn.close()
    _log(f'isolated db created: {E2E_DB}')


def drop_isolated_db():
    import psycopg2
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASSWORD, dbname='postgres',
                            connect_timeout=10)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f'DROP DATABASE IF EXISTS {E2E_DB} WITH (FORCE)')
        cur.close()
    finally:
        conn.close()
    _log(f'isolated db dropped: {E2E_DB}')


def configure_env(oss_endpoint):
    os.environ['DATABASE_URL'] = (
        f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{E2E_DB}')
    os.environ['OSS_ENDPOINT'] = oss_endpoint
    os.environ['OSS_PUBLIC_ENDPOINT'] = ''
    os.environ['OSS_ACCESS_KEY'] = 'intelligent_audio_test'
    os.environ['OSS_SECRET_KEY'] = 'intelligent_audio_test666'
    os.environ['OSS_BUCKET_NAME'] = OSS_BUCKET
    os.environ['OSS_KEY_PREFIX'] = OSS_PREFIX
    os.environ['STORAGE_FALLBACK_ENABLED'] = 'true'
    # 失败注入阶段不要因为长重试拖住实测
    os.environ['OSS_ADMIN_CONNECT_TIMEOUT_SECONDS'] = '2'
    os.environ['OSS_ADMIN_READ_TIMEOUT_SECONDS'] = '2'
    os.environ['OSS_ADMIN_MAX_ATTEMPTS'] = '1'
    os.environ.setdefault('LOG_ARCHIVE_BATCH_ROWS', '1000')


def create_schema():
    from shared.models.database import Base, get_engine, init_db
    from task_service.infrastructure.persistence.models.system_models import Log  # noqa: F401
    init_db()  # 建立全局 engine（get_engine() 在 init_db 前为 None）
    engine = get_engine()
    Base.metadata.create_all(engine, tables=[Log.__table__])
    _log('schema created (isolated db only)')


def seed_logs(cold=COLD_ROWS, hot=HOT_ROWS):
    from shared.models.database import get_db_session, utc8now
    from task_service.infrastructure.persistence.models.system_models import Log

    now = utc8now()
    cold_time = now - timedelta(days=40)
    session = get_db_session()
    try:
        rows = []
        for i in range(cold):
            rows.append(Log(
                time=cold_time,
                level='INFO',
                category='Task',
                module='int1963e2e',
                source='int1963e2e',
                content=f'cold log row {i} ' + ('x' * 200),
                task_id=1963000000 + (i % 7),
                test_case_id=f'case-{i % 5}',
            ))
        for i in range(hot):
            rows.append(Log(
                time=now - timedelta(hours=1),
                level='INFO',
                category='Task',
                module='int1963e2e',
                source='int1963e2e',
                content=f'hot log row {i}',
                task_id=1963000000 + i,
                test_case_id=f'case-hot-{i}',
            ))
        session.add_all(rows)
        session.commit()
    finally:
        session.close()
    _log(f'seeded cold={cold} hot={hot}')


def count_rows(where=''):
    from shared.models.database import get_db_session
    from sqlalchemy import text
    session = get_db_session()
    try:
        sql = "select count(*) from logs where source = 'int1963e2e'"
        if where:
            sql += ' and ' + where
        return int(session.execute(text(sql)).scalar() or 0)
    finally:
        session.close()


def cold_ids():
    from shared.models.database import get_db_session
    from sqlalchemy import text
    session = get_db_session()
    try:
        rows = session.execute(text(
            "select id from logs where source = 'int1963e2e' "
            "and content like 'cold log row%' order by id")).fetchall()
        return sorted(int(r[0]) for r in rows)
    finally:
        session.close()


# --------------------------------------------------------------------------
# OSS 侧校验 / 清理
# --------------------------------------------------------------------------

def _s3_client():
    import boto3
    from botocore.config import Config as BotoConfig
    return boto3.client(
        's3',
        endpoint_url='http://127.0.0.1:9000',
        aws_access_key_id='intelligent_audio_test',
        aws_secret_access_key='intelligent_audio_test666',
        region_name='us-east-1',
        config=BotoConfig(signature_version='s3v4',
                          s3={'addressing_style': 'path'},
                          retries={'max_attempts': 2}),
    )


def list_archive_objects():
    client = _s3_client()
    resp = client.list_objects_v2(Bucket=OSS_BUCKET, Prefix=f'{OSS_PREFIX}/archives/')
    return [obj['Key'] for obj in resp.get('Contents', [])]


def read_archive_entries(keys):
    client = _s3_client()
    entries = []
    for key in keys:
        body = client.get_object(Bucket=OSS_BUCKET, Key=key)['Body'].read()
        entries.extend(json.loads(body))
    return entries


def purge_archive_objects():
    client = _s3_client()
    keys = list_archive_objects()
    for key in keys:
        client.delete_object(Bucket=OSS_BUCKET, Key=key)
    if keys:
        _log(f'purged {len(keys)} e2e archive objects under {OSS_PREFIX}/archives/')


# --------------------------------------------------------------------------
# 两个阶段
# --------------------------------------------------------------------------

def phase_success():
    configure_env('http://127.0.0.1:9000')
    create_isolated_db()
    purge_archive_objects()
    try:
        create_schema()
        seed_logs()
        before = count_rows()
        expected_ids = cold_ids()
        _log(f'rows before archive: {before} (cold={len(expected_ids)})')

        import json as _json
        from shared.infrastructure.config import BaseConfig
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

        servicer = TaskDataServiceServicer()
        batches = []
        while True:
            resp = servicer.ArchiveLogs(
                task_pb.ArchiveLogsRequest(days=BATCH_DAYS, dry_run=False))
            if not resp.success:
                raise SystemExit(f'batch failed: {resp.message}')
            data = _json.loads(resp.data)
            batches.append(data)
            _log(f"batch {len(batches)}: rows={data['archived_count']} "
                 f"deleted={data['deleted_count']} has_more={data['has_more']} "
                 f"files={data['archive_write_count']} response_bytes={data['response_bytes']}")
            if not data['has_more']:
                break
            if len(batches) > 50:
                raise SystemExit('too many batches (possible loop)')

        archived = sum(b['archived_count'] for b in batches)
        deleted = sum(b['deleted_count'] for b in batches)
        max_response_bytes = max(b['response_bytes'] for b in batches)
        file_writes = sum(b['archive_write_count'] for b in batches)
        cold_left = count_rows("content like 'cold log row%'")
        hot_left = count_rows("content like 'hot log row%'")

        keys = list_archive_objects()
        entries = read_archive_entries(keys)
        archive_ids = sorted(int(e['id']) for e in entries)

        # 隔离库里的 logs 表可能自带历史行（新建库不会），这里以 source 过滤
        limit = BaseConfig.GRPC_MAX_MESSAGE_MB * 1024 * 1024
        checks = {
            'batches': len(batches),
            'archived': archived,
            'deleted': deleted,
            'expected_cold': len(expected_ids),
            'cold_left': cold_left,
            'hot_left': hot_left,
            'archive_objects': len(keys),
            'archive_entries': len(entries),
            'ids_match': archive_ids == expected_ids,
            'archive_file_writes': file_writes,
            'max_response_bytes': max_response_bytes,
            'grpc_limit_bytes': limit,
            'response_well_below_limit': max_response_bytes < limit // 100,
            'archived_eq_deleted': archived == deleted,
        }
        _log('checks: ' + _json.dumps(checks, ensure_ascii=False))

        ok = (archived == deleted == len(expected_ids)
              and cold_left == 0 and hot_left == HOT_ROWS
              and checks['ids_match']
              and checks['response_well_below_limit'])
        if not ok:
            raise SystemExit('SUCCESS PHASE FAILED')
        _log('SUCCESS PHASE OK')
    finally:
        drop_isolated_db()


def phase_failure():
    configure_env('http://127.0.0.1:9')  # 不可达端点
    create_isolated_db()
    try:
        create_schema()
        seed_logs(cold=100, hot=0)
        before = count_rows()
        _log(f'rows before failure injection: {before}')

        from shared.infrastructure.config import BaseConfig
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

        servicer = TaskDataServiceServicer()
        resp = servicer.ArchiveLogs(
            task_pb.ArchiveLogsRequest(days=BATCH_DAYS, dry_run=False))
        after = count_rows()

        local_root = os.path.join(BaseConfig.STORAGE_LOCAL_ROOT, 'archives')
        local_files = []
        for root, _dirs, files in os.walk(local_root):
            for name in files:
                local_files.append(os.path.join(root, name))

        result = {
            'success_flag': bool(resp.success),
            'message': resp.message[:300],
            'rows_before': before,
            'rows_after': after,
            'unchanged': before == after,
            'local_archive_files': len(local_files),
        }
        _log('checks: ' + json.dumps(result, ensure_ascii=False))

        if resp.success:
            raise SystemExit('FAILURE PHASE FAILED: archive reported success with unreachable OSS')
        if not result['unchanged']:
            raise SystemExit('FAILURE PHASE FAILED: rows changed although upload failed')
        if local_files:
            raise SystemExit('FAILURE PHASE FAILED: local:// artifacts written')
        _log('FAILURE PHASE OK')
    finally:
        drop_isolated_db()


def main():
    phase = (sys.argv[1] if len(sys.argv) > 1 else '').lower()
    _log(f'start phase={phase} at {datetime.now().isoformat(timespec="seconds")}')
    if phase == 'success':
        phase_success()
    elif phase == 'failure':
        phase_failure()
    else:
        raise SystemExit('usage: python tests/integration/int1963_archive_e2e.py success|failure')


if __name__ == '__main__':
    main()
