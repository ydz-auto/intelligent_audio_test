# -*- coding: utf-8 -*-
"""INT-554 日志归档链路后端缺陷修复回归。

1. 写盘单前缀：save_archive 以 category='archives' + 逻辑 key 落盘，不再出现
   archives/archives/ 双前缀；exists/load_bytes 用同一完整路径（含 category）。
2. 前缀口径对齐：task_service 分组 key 改为 tasks/{task_id}/{case_id}/{date}、
   tasks/{task_id}/{date}、cases/{case_id}/{date}、other/{date}，与读侧
   get_archive_status（tasks/ cases/ other/）及 get_archived_logs 一致。
3. download_archive 文件锁：改用 load_bytes 写入临时句柄后关闭，消除
   Windows WinError 32（原实现 load_file 落盘同一路径时句柄未关闭）。
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('STORAGE_FALLBACK_ENABLED', 'true')

import pytest  # noqa: E402

import shared.logging  # noqa: E402
from shared.infrastructure.storage import storage  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from task_service.infrastructure.persistence.log_repository import LogRepository  # noqa: E402
from api_gateway.application.services.log.log_command_service import LogCommandService  # noqa: E402
from api_gateway.application.services.log.log_query_service import LogQueryService  # noqa: E402
from api_gateway.infrastructure.request_adapter import set_current_request  # noqa: E402

_TASK_ID = 554001001


class _FakeRequest:
    """FastAPI Request 的最小替身：仅提供 query_params（dict 即被 _QueryParams 接受）。"""

    def __init__(self, query_params):
        self.query_params = query_params


class _FakeOSS:
    """OSS 客户端替身：任何方法调用立即抛错，迫使 storage 走本地降级。"""

    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise ConnectionError('OSS unavailable (test stub)')
        return _raise


@pytest.fixture(autouse=True)
def _force_local_storage(monkeypatch):
    """强制本地降级存储：测试不触达真实 OSS。

    仓库 conftest 把 OSS_ENDPOINT 指向死端口 127.0.0.1:9（连接拒绝应瞬时失败），
    但本机并行环境可能半开监听该端口使 SYN 挂起——测试改为显式禁 OSS，既快且稳。
    """
    monkeypatch.setattr(storage, '_oss_available', lambda: False)
    monkeypatch.setattr(storage, '_oss_client', _FakeOSS())


# ============================================================
# 1) 写路径前缀：log_repository.archive 分组 key 口径
# ============================================================

@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean_logs():
    """每个用例后清掉本卡 task_id 的行（进程级共享 sqlite，防计数串扰）。"""
    yield
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.task_id == _TASK_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _insert_logs(session, Log, rows):
    for row in rows:
        session.add(Log(
            time=row['time'],
            level=row.get('level', 'INFO'),
            category=row.get('category', 'Task'),
            module=row.get('module', 'test'),
            source=row.get('source', 'int554'),
            content=row.get('content', 'cold'),
            task_id=row.get('task_id'),
            test_case_id=row.get('test_case_id'),
        ))
    session.commit()


def test_archive_group_keys_canonical_prefixes():
    """task_service 分组 key 与读侧 tasks/cases/other 前缀口径一致。"""
    from shared.models.database import get_db_session
    from shared.models.database import utc8now
    from task_service.infrastructure.persistence.models.system_models import Log

    session = get_db_session()
    try:
        cold = utc8now() - timedelta(days=40)
        _insert_logs(session, Log, [
            {'time': cold, 'task_id': _TASK_ID, 'test_case_id': 'case-1'},     # both → tasks/
            {'time': cold, 'task_id': _TASK_ID, 'test_case_id': None},          # task only → tasks/
            {'time': cold, 'task_id': None, 'test_case_id': 'case-2'},          # case only → cases/
            {'time': cold, 'task_id': None, 'test_case_id': None},              # neither → other/
        ])
        # 热日志（近 1 天）不应被归档
        hot = utc8now() - timedelta(days=1)
        _insert_logs(session, Log, [
            {'time': hot, 'task_id': _TASK_ID, 'test_case_id': 'case-hot'},
        ])
    finally:
        session.close()

    result = LogRepository().archive(days=30, dry_run=False)
    groups = result.get('groups', {})
    keys = set(groups.keys())
    assert keys == {
        f'tasks/{_TASK_ID}/case-1/{(cold).strftime("%Y-%m-%d")}',
        f'tasks/{_TASK_ID}/{(cold).strftime("%Y-%m-%d")}',
        f'cases/case-2/{(cold).strftime("%Y-%m-%d")}',
        f'other/{(cold).strftime("%Y-%m-%d")}',
    }, f'分组 key 应为 tasks/cases/other 口径，实际: {sorted(keys)}'
    assert result['archived_count'] == 4
    assert result['deleted_count'] == 4

    # 热日志仍保留
    from shared.models.database import get_db_session as _s
    from task_service.infrastructure.persistence.models.system_models import Log as _Log
    session = _s()
    try:
        remaining = session.query(_Log).filter(_Log.task_id == _TASK_ID).count()
    finally:
        session.close()
    assert remaining == 1


# ============================================================
# 2) 写盘单前缀：log_command_service.save_archive（缺陷 1）
# ============================================================

def _make_archive_result(groups):
    return {
        'archived_count': sum(len(v) for v in groups.values()),
        'deleted_count': sum(len(v) for v in groups.values()),
        'remaining_count': 0,
        'groups': groups,
    }


def _patch_task_data(monkeypatch, result):
    from api_gateway.infrastructure.grpc_proxies import task_data_service
    monkeypatch.setattr(task_data_service, 'archive_logs',
                        lambda days=30, dry_run=False: result)
    return task_data_service


def test_command_save_archive_single_prefix(monkeypatch):
    """save_archive 落盘 key 为 archives 类目内单前缀；exists/load 用完整路径。"""
    groups = {
        'tasks/123/2026-09-06': [{'id': 1, 'time': '2026-09-06T10:00:00'}],
        'cases/555/2026-09-06': [{'id': 2, 'time': '2026-09-06T11:00:00'}],
    }
    _patch_task_data(monkeypatch, _make_archive_result(groups))

    exists_calls = []
    saved = []
    monkeypatch.setattr(storage, 'exists', lambda path: (exists_calls.append(path) or False))
    monkeypatch.setattr(storage, 'load_bytes',
                        lambda path: (_ for _ in ()).throw(AssertionError('首次归档不应读取已存在文件')))
    monkeypatch.setattr(storage, 'save_bytes',
                        lambda data, category, key, content_type=None: (
                            saved.append((category, key, data)) or f'oss://{category}/{key}'))

    payload, http_code = LogCommandService.archive_logs()
    assert http_code == 200
    assert payload['success'] is True

    # exists 检查用完整路径（category + key），不得是裸 key
    assert exists_calls == [
        'archives/tasks/123/2026-09-06.json',
        'archives/cases/555/2026-09-06.json',
    ]
    # save_bytes key 不含重复 archives/ 前缀
    assert [(c, k) for c, k, _ in saved] == [
        ('archives', 'tasks/123/2026-09-06.json'),
        ('archives', 'cases/555/2026-09-06.json'),
    ]
    assert '任务: 1' in payload['message'] and '用例: 1' in payload['message']


def test_command_save_archive_merge_existing(monkeypatch):
    """归档同一 key 已存在时合并读取（完整路径读取）后落盘。"""
    groups = {
        'tasks/123/2026-09-06': [{'id': 2, 'time': '2026-09-06T12:00:00'}],
    }
    _patch_task_data(monkeypatch, _make_archive_result(groups))

    existing = [{'id': 1, 'time': '2026-09-06T09:00:00'}]
    monkeypatch.setattr(storage, 'exists', lambda path: True)
    monkeypatch.setattr(storage, 'load_bytes', lambda path: json.dumps(existing).encode('utf-8'))

    saved = []
    monkeypatch.setattr(storage, 'save_bytes',
                        lambda data, category, key, content_type=None: (
                            saved.append((category, key, data)) or f'oss://{category}/{key}'))

    payload, http_code = LogCommandService.archive_logs()
    assert http_code == 200
    _, key, data = saved[0]
    assert key == 'tasks/123/2026-09-06.json'
    merged = json.loads(data)
    assert [m['id'] for m in merged] == [1, 2]  # 已存在 + 新，按 time 升序


# ============================================================
# 3) 存储层单前缀 + 本地降级往返（缺陷 1 的实机语义）
# ============================================================

def test_storage_local_roundtrip_single_prefix(monkeypatch, tmp_path):
    """真实 storage.save_bytes/list/exists/load 单前缀往返：无 archives/archives/ 双前缀。"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))

    data = json.dumps([{'id': 1, 'time': '2026-09-06T10:00:00'}], ensure_ascii=False).encode('utf-8')
    path = storage.save_bytes(data, 'archives', 'tasks/123/2026-09-06.json')
    assert path == f'local://archives/tasks/123/2026-09-06.json'
    # 落盘位置：{root}/archives/tasks/...（单前缀，不得再套一层 archives/）
    assert os.path.exists(os.path.join(str(tmp_path), 'archives', 'tasks', '123', '2026-09-06.json'))
    assert not os.path.exists(os.path.join(str(tmp_path), 'archives', 'archives'))

    # list_objects 返回逻辑 key（不含 category）
    assert storage.list_objects('archives', prefix='tasks/123/') == ['tasks/123/2026-09-06.json']
    assert storage.list_objects('archives', prefix='tasks/') == ['tasks/123/2026-09-06.json']
    # exists/load 用完整路径
    assert storage.exists('archives/tasks/123/2026-09-06.json') is True
    assert storage.load_bytes('archives/tasks/123/2026-09-06.json') == data


# ============================================================
# 4) 读侧对齐：get_archive_status / get_archived_logs（缺陷 2）
# ============================================================

def test_get_archive_status_prefixes(monkeypatch):
    """状态计数按 tasks/cases/other 前缀统计，与写路径口径一致。"""
    from api_gateway.infrastructure.grpc_proxies import task_data_service

    def fake_list(category, prefix=''):
        return {
            'tasks/': ['tasks/123/a.json', 'tasks/456/b.json'],
            'cases/': ['cases/555/c.json'],
            'other/': ['other/2026-09-06.json'],
        }[prefix]

    monkeypatch.setattr(storage, 'list_objects', fake_list)
    monkeypatch.setattr(task_data_service, 'get_log_count',
                        lambda start_date=None: {'total': 100, 'hot': 80, 'cold': 20})

    payload, http_code = LogQueryService.get_archive_status()
    assert http_code == 200
    data = payload['data']
    assert data['taskArchives'] == 2
    assert data['caseArchives'] == 1
    assert data['otherArchives'] == 1
    assert data['totalLogs'] == 100


def test_get_archived_logs_roundtrip_tasks_and_cases(monkeypatch, tmp_path):
    """真实归档文件（本地降级）→ GET /logs/archive/logs 按 task_id / case 读取。"""
    from shared.infrastructure.config import BaseConfig
    from shared.models.database import utc8now
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))

    t = (utc8now() - timedelta(days=1)).isoformat()
    storage.save_bytes(json.dumps([{
        'id': 1, 'time': t, 'level': 'INFO', 'category': 'Task', 'module': 'm',
        'source': 's', 'content': 'both', 'task_id': _TASK_ID, 'test_case_id': 'case-1',
    }], ensure_ascii=False).encode('utf-8'), 'archives', f'tasks/{_TASK_ID}/case-1/2026-09-06.json')
    storage.save_bytes(json.dumps([{
        'id': 2, 'time': t, 'level': 'INFO', 'category': 'Task', 'module': 'm',
        'source': 's', 'content': 'task-only', 'task_id': _TASK_ID, 'test_case_id': None,
    }], ensure_ascii=False).encode('utf-8'), 'archives', f'tasks/{_TASK_ID}/2026-09-06.json')
    storage.save_bytes(json.dumps([{
        'id': 3, 'time': t, 'level': 'INFO', 'category': 'Task', 'module': 'm',
        'source': 's', 'content': 'case-only', 'task_id': None, 'test_case_id': 'case-2',
    }], ensure_ascii=False).encode('utf-8'), 'archives', 'cases/case-2/2026-09-06.json')

    # 按 task_id 查询：同时命中 tasks/{task_id}/{case}/date 与 tasks/{task_id}/date
    set_current_request(_FakeRequest({'task_id': str(_TASK_ID)}))
    try:
        payload, http_code = LogQueryService.get_archived_logs()
    finally:
        set_current_request(None)
    assert http_code == 200
    items = payload['data']['items']
    assert {it['id'] for it in items} == {1, 2}
    assert all(it['task_id'] == _TASK_ID for it in items)

    # 按 test_case_id 查询：命中 cases/{case}/date
    set_current_request(_FakeRequest({'test_case_id': 'case-2'}))
    try:
        payload, http_code = LogQueryService.get_archived_logs()
    finally:
        set_current_request(None)
    assert http_code == 200
    items = payload['data']['items']
    assert {it['id'] for it in items} == {3}


# ============================================================
# 5) download_archive 文件锁（缺陷 3）
# ============================================================

def test_download_archive_no_file_lock(monkeypatch, tmp_path):
    """download_archive 改用 load_bytes 写临时句柄，load_file 不再落盘同一路径。"""
    monkeypatch.setattr(storage, 'list_objects',
                        lambda category, prefix='': ['tasks/123/2026-09-06.json'])
    monkeypatch.setattr(storage, 'load_bytes',
                        lambda path: b'[{"id": 1, "time": "2026-09-06T10:00:00"}]')
    # 若实现回退到 load_file(同一 tmp 路径) 则必抛 WinError 32
    def _winerror(*args, **kwargs):
        raise OSError(32, 'file in use: 同一路径被 NamedTemporaryFile 句柄占用')
    monkeypatch.setattr(storage, 'load_file', _winerror)

    resp = LogQueryService.download_archive('2026-09-06.json')
    # 返回 FileResponse 且临时文件内容正确
    assert resp.path and os.path.exists(resp.path)
    with open(resp.path, 'rb') as f:
        assert f.read() == b'[{"id": 1, "time": "2026-09-06T10:00:00"}]'
