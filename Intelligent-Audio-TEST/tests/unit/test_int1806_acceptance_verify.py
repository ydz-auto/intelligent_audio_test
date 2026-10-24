# -*- coding: utf-8 -*-
"""INT-1806 验收复测（测试工程师独立取证，非开发单测复制）。

用**两个真实隔离进程**跑真实链路：
  服务端进程 = 真实 `TaskDataServiceServicer` gRPC（审计文件唯一写盘者，H4），
               并执行 S4 直写（发布 / 人工复核 / AI 复核）与同微秒 cursor 探针；
  客户端进程 = 真实审计写入器 → `emit` 三分支 → `BatchCreateLogs` gRPC。

覆盖卡面可测验收：零写入（1）、H1（2）、H2（3）、H3（4）、H4（5）、D2（6）、
统一 30 天保留 + 归档（7）、回滚开关（8）。

说明：隔离库用 sqlite，其 `Log.time` 只接受 datetime，故服务端在
`E2E_DB_TIME_ADAPTER=1` 时给 `log_repository.batch_create` 包一层测试侧时间
适配；产品代码未改。
"""
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta

import pytest

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int1806_accept_') + '/accept.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HARNESS_DIR = os.path.join(REPO_ROOT, 'tests', 'unit', '_int1806_e2e')
SERVER_SCRIPT = os.path.join(HARNESS_DIR, 'server.py')
CLIENT_SCRIPT = os.path.join(HARNESS_DIR, 'client.py')

_CURSOR_SAFE_MAX = 2 ** 53
_AUDIT_NAME_RE = re.compile(
    r'^(?P<category>[a-z]+)\.(?P<service>[^.]+)\.(?P<identity>.+)\.jsonl$')
_FIVE_CATEGORIES = {'auth', 'benchmark', 'device', 'visibility', 'system'}


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _base_env():
    env = dict(os.environ)
    env['PYTHONPATH'] = REPO_ROOT + os.pathsep + os.path.join(REPO_ROOT, 'shared', 'proto')
    env['PYTHONIOENCODING'] = 'utf-8'
    env['TASK_SERVICE_HOST'] = '127.0.0.1'
    env['LOG_SWEEP_SERVICE'] = 'api_gateway'
    env['LOG_AUDIT_ARCHIVE_ENABLED'] = 'false'
    env['LOG_GRPC_PAYLOAD'] = 'false'
    env['OSS_ENDPOINT'] = 'http://127.0.0.1:1'
    env['OSS_ACCESS_KEY'] = env.get('OSS_ACCESS_KEY') or 'test'
    env['OSS_SECRET_KEY'] = env.get('OSS_SECRET_KEY') or 'test'
    return env


def _run_stack(tmp_path, audit_db_enabled=False, client_service='api_gateway',
               client_mode='gateway', expect_audit=4):
    """起服务端进程 + 跑客户端进程，返回现场信息。"""
    db_path = (tmp_path / 'accept.db').as_posix()
    server_root = tmp_path / 'task_logs'
    client_root = tmp_path / 'gateway_logs'
    ready_file = tmp_path / 'ready.txt'
    stop_file = tmp_path / 'stop.txt'
    port = _free_port()

    env = _base_env()
    env['DATABASE_URL'] = 'sqlite:///' + db_path
    env['E2E_GRPC_PORT'] = str(port)
    env['E2E_READY_FILE'] = str(ready_file)
    env['E2E_STOP_FILE'] = str(stop_file)
    env['E2E_DB_TIME_ADAPTER'] = '1' if audit_db_enabled else '0'
    env['SERVICE_NAME'] = 'task_service'
    env['LOG_ROOT_DIR'] = str(server_root)
    env['LOG_AUDIT_DB_ENABLED'] = 'true' if audit_db_enabled else 'false'
    env['TASK_SERVICE_GRPC_PORT'] = str(port)

    server_log_path = tmp_path / 'server.log'
    server_log = open(server_log_path, 'w', encoding='utf-8')
    server = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT], cwd=REPO_ROOT, env=env,
        stdout=server_log, stderr=subprocess.STDOUT, text=True,
        encoding='utf-8', errors='replace')
    try:
        deadline = time.time() + 180
        while time.time() < deadline and not ready_file.exists():
            if server.poll() is not None:
                raise AssertionError('服务端进程提前退出:\n'
                                     + server_log_path.read_text(encoding='utf-8', errors='replace'))
            time.sleep(0.1)
        assert ready_file.exists(), '服务端 gRPC 未就绪（180s）:\n' + \
            server_log_path.read_text(encoding='utf-8', errors='replace')

        client_env = dict(env)
        client_env['SERVICE_NAME'] = client_service
        client_env['LOG_ROOT_DIR'] = str(client_root)
        client_env['E2E_SERVER_LOG_ROOT'] = str(server_root)
        client_env['E2E_EXPECT_AUDIT'] = str(expect_audit)
        client_env['E2E_CLIENT_MODE'] = client_mode
        client = subprocess.run(
            [sys.executable, CLIENT_SCRIPT], cwd=REPO_ROOT, env=client_env,
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=300)
        assert client.returncode == 0, (
            '客户端进程失败 rc=%s\nSTDOUT:\n%s\nSTDERR:\n%s'
            % (client.returncode, client.stdout, client.stderr))
        client_out = client.stdout.strip().splitlines()[-1] if client.stdout.strip() else ''
    finally:
        stop_file.write_text('stop', encoding='utf-8')
        try:
            server.wait(timeout=60)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()

    records = []
    for dirpath, _, names in os.walk(server_root / 'audit'):
        for name in names:
            if not name.endswith('.jsonl'):
                continue
            with open(os.path.join(dirpath, name), encoding='utf-8') as handle:
                for line in handle:
                    if line.strip():
                        records.append((os.path.join(dirpath, name), json.loads(line)))

    return {
        'db_path': db_path,
        'server_root': server_root,
        'client_root': client_root,
        'records': records,
        'client_out': client_out,
    }


def _logs_table_count(db_path):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute('select count(*) from logs').fetchone()
    return int(row[0])


def _service_file_text(root):
    chunks = []
    for dirpath, _, names in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel.split(os.sep)[0] == 'audit':
            continue
        for name in names:
            if name.endswith('.log'):
                with open(os.path.join(dirpath, name), encoding='utf-8',
                          errors='replace') as handle:
                    chunks.append(handle.read())
    return '\n'.join(chunks)


# ---------------------------------------------------------------------------
# 验收 1/2/3/4/5/6：真实链路零写入 + 五类审计文件 + H1/H2/H3/H4 + D2
# ---------------------------------------------------------------------------

def test_real_stack_zero_db_write_and_audit_files(tmp_path):
    result = _run_stack(tmp_path)
    records = result['records']

    # 验收 1：logs 表增量 0（本次全部审计事件都落文件）
    assert _logs_table_count(result['db_path']) == 0, '审计事件写进了 logs 表'

    # 五类文件齐全，一条事件恰好一行
    by_category = {}
    for path, record in records:
        by_category.setdefault(record['category'], []).append((path, record))
    assert set(by_category) == _FIVE_CATEGORIES, \
        f'审计文件类别不全: {sorted(by_category)}'

    # 字段齐全 + 文件路径段与记录一致
    for path, record in records:
        category = record['category']
        name = os.path.basename(path)
        match = _AUDIT_NAME_RE.match(name)
        assert match, f'审计文件名不符合契约模板: {name}'
        assert match.group('category') == category
        assert match.group('service') == record['service'], \
            f'文件名 service 段与记录不一致: {name} vs {record["service"]}'
        date_dir = os.path.basename(os.path.dirname(path))
        assert date_dir == record['time'][:10], '按天切换目录与事件日期不一致'
        assert isinstance(record['cursor'], int) and record['cursor'] > 0
        assert record['cursor'] < _CURSOR_SAFE_MAX, 'cursor 超出 2^53'
        assert record['event'], '审计行缺 event'
        assert record['service'], '审计行缺 service'
        assert record['level'] in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        assert 'mark' not in record and 'id' not in record

    # 验收 3（H2）：操作人写侧从 content JSON 提取
    auth = [r for _, r in by_category['auth'] if r['event'] == 'AUTH_LOGIN']
    assert len(auth) == 1
    auth = auth[0]
    assert auth['operator_id'] == 369 and auth['user_id'] == 369
    assert auth['operator'] == '接线测试_admin'
    assert auth['target_type'] == 'user' and auth['target_id'] == 369
    assert auth['action'] == 'login' and auth['result'] == 'success'
    assert json.loads(auth['content'])['operator_id'] == 369, \
        'user_id 与 content JSON 不一致（H2）'
    assert auth['detail'] == json.loads(auth['content']), 'detail 不是 content JSON 全量'

    benchmark = [r for _, r in by_category['benchmark']
                 if r['event'] == 'BENCHMARK_RANKING_COMPUTED'][0]
    assert benchmark['operator_id'] == 42 and benchmark['user_id'] == 42
    device_audit = [r for _, r in by_category['device']
                    if r['event'] == 'DEVICE_ALARM_TRIGGERED'][0]
    assert device_audit['operator_id'] == 43 and device_audit['user_id'] == 43
    visibility = [r for _, r in by_category['visibility']
                  if r['event'] == 'PRIVATE_RESOURCE_ACCESS'][0]
    assert visibility['operator_id'] == 44 and visibility['user_id'] == 44
    assert visibility['result'] == 'denied'

    # S4（category=system）：发布 / 人工复核 / AI 复核
    system_events = {r['event']: r for _, r in by_category['system']}
    assert {'PUBLISHED_TASK_CREATED', 'MANUAL_REVIEW_SUBMITTED',
            'AI_REVIEW_INITIATED', 'CURSOR_PROBE'} <= set(system_events)
    assert system_events['PUBLISHED_TASK_CREATED']['operator_id'] == 42, \
        'published_by 未折叠为 operator_id'
    assert system_events['PUBLISHED_TASK_CREATED']['target_id'] == 101
    assert system_events['MANUAL_REVIEW_SUBMITTED']['operator_id'] == 42
    assert system_events['PUBLISHED_TASK_CREATED']['service'] == 'task_service'

    # 验收 4（H3）：同微秒两条事件 cursor +1；文件内严格递增且与时间同序
    probes = sorted((r for _, r in by_category['system'] if r['event'] == 'CURSOR_PROBE'),
                    key=lambda item: item['cursor'])
    assert len(probes) == 2
    assert probes[1]['cursor'] == probes[0]['cursor'] + 1, '同微秒冲突未 +1'
    assert probes[0]['time'] == probes[1]['time']

    for path in {p for p, _ in records}:
        rows = [r for p, r in records if p == path]
        cursors = [r['cursor'] for r in rows]
        times = [r['time'] for r in rows]
        assert cursors == sorted(cursors) and len(set(cursors)) == len(cursors), \
            f'{path} cursor 非严格递增'
        assert times == sorted(times), f'{path} cursor 与事件时间不同序'

    # 验收 2（H1）：同 category 的设备运维日志不进审计目录
    service_text = _service_file_text(result['client_root'])
    assert 'group command dispatched' in service_text, '设备运维日志未写服务文件'
    assert 'case preview step done' in service_text, '预览日志未写服务文件（D2）'
    for path, record in records:
        assert 'group command dispatched' not in record['content'], \
            f'H1 失败：运维日志进了审计文件 {path}'
        assert record['event'] != '', 'H1 失败：无 event 的条目进审计'
    # 审计事件不再写服务文件（一条事件恰好一行）
    assert 'AUTH_LOGIN' not in service_text, '审计事件被重复写进服务文件'
    assert 'DEVICE_ALARM_TRIGGERED' not in service_text

    # 验收 5（H4）：产生事件的进程本地日志根没有 audit/ 目录
    assert not (result['client_root'] / 'audit').exists(), \
        'api_gateway 进程本地也落审计文件（违反单写者）'
    # 审计文件只在 task_service（写盘进程）日志根
    assert (result['server_root'] / 'audit').is_dir()


def test_cursor_does_not_regress_across_restart(tmp_path):
    """验收 4：写入器重启（游标状态清零）后按事件时间继续，不落后于上一进程。"""
    from datetime import timezone

    from shared.logging.audit_writer import AuditLogFileWriter

    cst = timezone(timedelta(hours=8))
    settings = _settings(tmp_path, audit_max_bytes=50 * 1024 * 1024)

    def _entry(moment):
        return {
            'event': 'AUTH_LOGIN', 'category': 'auth', 'module': 'auth_login',
            'source': 'api_gateway', 'service': 'api_gateway', 'time': moment,
            'content': json.dumps({'event': 'AUTH_LOGIN', 'operator_id': 1}),
        }

    first = AuditLogFileWriter(settings=settings, service_name='api_gateway',
                               process_id='host-1')
    cursor_first = first.write(_entry(datetime(2026, 10, 24, 9, 0, 0, 111111, tzinfo=cst)))
    first.close_all()

    second = AuditLogFileWriter(settings=settings, service_name='api_gateway',
                                process_id='host-1')
    cursor_second = second.write(_entry(datetime(2026, 10, 24, 9, 0, 0, 222222, tzinfo=cst)))
    second.close_all()

    assert cursor_second > cursor_first, '重启后 cursor 回退'
    path = tmp_path / 'audit' / '2026-10-24' / 'auth.api_gateway.host-1.jsonl'
    assert len(path.read_text(encoding='utf-8').splitlines()) == 2, '重启后追加写丢行'


# ---------------------------------------------------------------------------
# 验收 5（H4）：宿主机 device_service 的审计事件经 BatchCreateLogs 落 task_service
# ---------------------------------------------------------------------------

def test_host_device_service_audit_lands_in_task_service_root(tmp_path):
    result = _run_stack(tmp_path, client_service='device_service',
                        client_mode='device_host', expect_audit=1)
    records = result['records']

    assert _logs_table_count(result['db_path']) == 0

    device_rows = [(path, r) for path, r in records
                   if r['event'] == 'DEVICE_ALARM_TRIGGERED'
                   and r['service'] == 'device_service']
    assert len(device_rows) == 1, 'device_service 审计事件未落到 task_service 日志根'
    path, record = device_rows[0]
    assert os.path.basename(os.path.dirname(path)) == record['time'][:10]
    assert os.path.basename(path).startswith('device.device_service.')
    assert record['category'] == 'device'
    assert record['device_id'] == 55
    assert record['result'] == 'success'
    # 设备告警是机器事件：content 无操作人，写侧不造操作人（H2 只从 content 提取）
    assert record['operator_id'] is None and record['user_id'] is None
    assert 'operator_id' not in record['detail']

    # 宿主机 device_service 本地日志根没有 audit/（单写者），运维日志只在服务文件
    assert not (result['client_root'] / 'audit').exists(), \
        '宿主机进程本地落了审计文件（违反 H4）'
    host_service_text = _service_file_text(result['client_root'])
    assert 'group command dispatched' in host_service_text
    assert 'case preview step done' in host_service_text


# ---------------------------------------------------------------------------
# 验收 8：LOG_AUDIT_DB_ENABLED=True 同一事件文件一行 + DB 一行
# ---------------------------------------------------------------------------
def test_rollback_switch_double_writes(tmp_path):
    result = _run_stack(tmp_path, audit_db_enabled=True)
    records = result['records']

    assert len(records) == 9, f'审计文件行数异常: {len(records)}'
    assert _logs_table_count(result['db_path']) == 4, \
        '回滚开关打开后 emit 路径事件未双写入库'

    with sqlite3.connect(result['db_path']) as conn:
        rows = conn.execute('select category, content from logs').fetchall()
    categories = sorted(row[0] for row in rows)
    assert categories == ['auth', 'benchmark', 'device', 'visibility'], categories
    db_auth = [json.loads(content) for category, content in rows if category == 'auth'][0]
    file_auth = [r for _, r in records if r['event'] == 'AUTH_LOGIN'][0]
    assert db_auth['operator_id'] == file_auth['operator_id'] == 369


# ---------------------------------------------------------------------------
# 验收 7：保留统一 30 天 + 归档 + 单清扫者
# ---------------------------------------------------------------------------

def _settings(root, **overrides):
    from shared.logging.config import LogSettings
    from shared.logging.enums import LogEnvironment
    values = dict(
        root_dir=str(root), environment=LogEnvironment.DEV, service_max_bytes=1024,
        service_retention_days=30, business_enabled=True, business_db_enabled=False,
        business_max_bytes=1024, business_retention_days=30,
        audit_enabled=True, audit_db_enabled=False, audit_max_bytes=1024,
        audit_retention_days=30, audit_archive_enabled=True,
        sweep_service='api_gateway', file_retention_days=30,
    )
    values.update(overrides)
    return LogSettings(**values)


def _touch(path, text='{}'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n', encoding='utf-8')


def test_retention_default_is_unified_30_days():
    from shared.infrastructure.config import BaseConfig
    assert BaseConfig.LOG_FILE_RETENTION_DAYS == 30
    assert BaseConfig.LOG_AUDIT_RETENTION_DAYS == 30
    assert BaseConfig.LOG_SERVICE_RETENTION_DAYS == 30
    assert BaseConfig.LOG_BUSINESS_RETENTION_DAYS == 30
    assert 180 not in (BaseConfig.LOG_AUDIT_RETENTION_DAYS,
                       BaseConfig.LOG_FILE_RETENTION_DAYS), '仍存在 180 天默认值'


def test_retention_archive_then_delete_and_failure_keeps_local(tmp_path, monkeypatch):
    from shared.infrastructure.storage import storage
    from shared.logging.enums import AUDIT_DIR
    from shared.logging.retention import sweep_audit_dates

    root = tmp_path / 'logs'
    old31 = (date.today() - timedelta(days=31)).isoformat()
    old200 = (date.today() - timedelta(days=200)).isoformat()
    recent = (date.today() - timedelta(days=3)).isoformat()
    for day in (old31, old200):
        _touch(root / AUDIT_DIR / day / 'auth.api_gateway.host-1.jsonl')
    _touch(root / AUDIT_DIR / recent / 'auth.api_gateway.host-1.jsonl')

    uploaded = []

    def _save_file(local_path, category, key):
        uploaded.append((category, key))
        return 'oss://' + category + '/' + key

    monkeypatch.setattr(storage, 'save_file', _save_file)
    stats = sweep_audit_dates(_settings(root))
    assert stats == {'archived': 2, 'deleted': 2, 'failed': 0}, stats
    assert ('archives', f'audit/{old31}/auth.api_gateway.host-1.jsonl') in uploaded
    assert ('archives', f'audit/{old200}/auth.api_gateway.host-1.jsonl') in uploaded
    assert not (root / AUDIT_DIR / old31).exists()
    assert not (root / AUDIT_DIR / old200).exists()
    assert (root / AUDIT_DIR / recent).exists(), '未到期审计目录被误删'

    # 归档失败：保留本地、不删
    def _boom(local_path, category, key):
        raise RuntimeError('storage down')

    monkeypatch.setattr(storage, 'save_file', _boom)
    expired = (date.today() - timedelta(days=120)).isoformat()
    target = root / AUDIT_DIR / expired / 'device.device_service.host-2.jsonl'
    _touch(target)
    stats = sweep_audit_dates(_settings(root))
    assert stats['failed'] == 1 and stats['deleted'] == 0
    assert target.exists(), '归档失败却删了本地文件'


def test_retention_single_sweeper(tmp_path, monkeypatch):
    from shared.logging.enums import AUDIT_DIR
    from shared.logging import retention

    root = tmp_path / 'logs'
    expired = (date.today() - timedelta(days=90)).isoformat()
    target = root / AUDIT_DIR / expired / 'auth.api_gateway.host-1.jsonl'
    _touch(target)

    # 非清扫者：一律跳过
    monkeypatch.setattr(retention, 'resolve_service_name', lambda: 'device_service')
    assert retention.sweep_log_root(_settings(root)) == 0
    assert target.exists(), '非清扫者删除了审计文件'

    # 清扫者：审计子树到期归档后删除
    from shared.infrastructure.storage import storage
    monkeypatch.setattr(retention, 'resolve_service_name', lambda: 'api_gateway')
    monkeypatch.setattr(storage, 'save_file', lambda *a, **k: 'oss://x')
    assert retention.sweep_log_root(_settings(root)) == 1
    assert not target.exists()
