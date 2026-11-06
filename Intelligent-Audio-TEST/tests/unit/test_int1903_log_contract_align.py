# -*- coding: utf-8 -*-
"""INT-1903 日志两处口径与契约对齐。

覆盖卡面验收 1：

1. `PUT /logs/mark` 响应带 `data.updated`（契约 §Q2：`updated` = 实际更新行数，
   文件游标 → 0）：
   - 全文件游标 → `data.updated == 0` + 专用文案；
   - 混合（文件游标 + legacy id）→ 只为 legacy 行更新，`data.updated` = 实际数；
   - 纯 legacy 行 → `data.updated` = 实际数；
   - 三条分支的 `code` / `message` 与改造前逐字一致。
2. DB 保留清扫豁免已标记行（契约 §Q5.1）：`mark IS NULL` 与 `mark = ''` 都算未标记，
   只有它们被归档 + 删除；已标记行既不归档也不删。默认口径是豁免（`keep_marked=True`），
   一次性清理脚本须显式 `--include-marked` 才整类清。

DB 用 pytest 进程级 sqlite（conftest 兜底），对象存储用本文件的内存 FakeObjectStore
（语义对齐 `OSSClient`：缺对象抛 `ClientError(NoSuchKey)`）。
"""
import importlib.util
import json
import os

import pytest
from botocore.exceptions import ClientError

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from shared.utils.query_utils import now_cst  # noqa: E402
from task_service.infrastructure.persistence.log_db_archive import (  # noqa: E402
    ArchiveStore,
    LogArchivePurger,
    PurgeResult,
)
from task_service.infrastructure.persistence.log_retention_cleaner import (  # noqa: E402
    LogRetentionCleaner,
)

# 本文件的造数标记：sqlite 库为 pytest 进程共享，按 source 精确圈定自己的行
_SOURCE = 'int1903_test'
_TASK_ID = 9101903
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARCHIVES = 'archives'

# 契约 §Q4：文件游标与 legacy logs 自增 id 用 10^12 隔开
_FILE_CURSOR = 1_790_000_000_000_000


def _not_found():
    """真实 OSS 的「对象不存在」：ClientError Code=NoSuchKey / 404。"""
    return ClientError({
        'Error': {'Code': 'NoSuchKey',
                  'Message': 'The specified key does not exist.'},
        'ResponseMetadata': {'HTTPStatusCode': 404},
    }, 'GetObject')


class FakeObjectStore:
    """内存对象存储，接口与 `OSSClient` 一致（download_bytes/upload_bytes/exists）。"""

    def __init__(self):
        self.objects = {}          # (category, key) -> bytes

    def download_bytes(self, category, key):
        try:
            return self.objects[(category, key)]
        except KeyError:
            raise _not_found()

    def upload_bytes(self, data, category, key, content_type=None):
        self.objects[(category, key)] = data
        return key

    def exists(self, category, key):
        return (category, key) in self.objects

    def archive(self, group_key):
        """读归档条目（group_key 不含 category 前缀与 .json）。"""
        return json.loads(self.objects[(_ARCHIVES, f'{group_key}.json')])


# =====================================================================
# DB 夹具（照 test_int1785_logs_purge 的进程级 sqlite 用法）
# =====================================================================

@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.source == _SOURCE).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _now():
    return now_cst().replace(tzinfo=None)


def _seed(rows):
    """rows: [(time, category, test_case_id, content, mark)]"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.add_all([
            Log(time=ts, level='INFO', category=cat, module='Test', source=_SOURCE,
                content=content, task_id=_TASK_ID, test_case_id=case_id, mark=mark)
            for ts, cat, case_id, content, mark in rows
        ])
        session.commit()
    finally:
        session.close()


def _remaining_contents():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        return sorted(r.content for r in
                      session.query(Log).filter(Log.source == _SOURCE).all())
    finally:
        session.close()


def _store(fake) -> ArchiveStore:
    return ArchiveStore(client=fake)


def _no_lock(cleaner):
    """清掉 Redis 锁依赖（单进程测试无需互斥）。"""
    cleaner._acquire_lock = lambda: None
    cleaner._release_lock = lambda token: None
    return cleaner


# =====================================================================
# 1. PUT /logs/mark 响应体带 data.updated（契约 §Q2）
# =====================================================================

class _FakeTaskDataProxy:
    """task_data_service 假实现（记录入参，返回预设 updated）。"""

    def __init__(self, updated=0):
        self.updated = updated
        self.mark_args = None

    def update_logs_mark(self, log_ids, mark):
        self.mark_args = (list(log_ids), mark)
        return {'updated': self.updated}


@pytest.fixture()
def fake_proxy(monkeypatch):
    proxy = _FakeTaskDataProxy()
    monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                        proxy)
    return proxy


def _set_request(body=None):
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(SimpleNamespace(
        state=SimpleNamespace(_json_body=body, user_id=0),
        query_params={},
        method='PUT',
    ))


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(None)


class TestMarkResponseCarriesUpdated:
    """三条分支都在 data.updated 里给实际更新行数，文案与 code 不变。"""

    def test_file_cursor_only_returns_updated_zero(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        _set_request({'log_ids': [_FILE_CURSOR, _FILE_CURSOR + 7], 'mark': 'flagged'})
        body, http_code = LogCommandService.mark_logs()

        assert http_code == 200
        assert body['code'] == 0
        assert body['data'] == {'updated': 0}
        assert body['message'] == '所选为文件日志，不支持标记（仅历史库行可标记）'
        assert fake_proxy.mark_args is None, '文件游标不应送 DB 更新'

    def test_mixed_ids_updated_is_actual_legacy_count(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        fake_proxy.updated = 1
        _set_request({'log_ids': [_FILE_CURSOR, 11], 'mark': 'flagged'})
        body, http_code = LogCommandService.mark_logs()

        assert http_code == 200
        assert body['code'] == 0
        assert body['data'] == {'updated': 1}
        assert body['message'] == '已为 1 条日志添加标记: flagged'
        assert fake_proxy.mark_args == ([11], 'flagged'), '只有 legacy id 送 DB'

    def test_legacy_only_updated_is_actual_count(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        fake_proxy.updated = 2
        _set_request({'log_ids': [11, 12], 'mark': 'flagged'})
        body, http_code = LogCommandService.mark_logs()

        assert http_code == 200
        assert body['code'] == 0
        assert body['data'] == {'updated': 2}
        assert body['message'] == '已为 2 条日志添加标记: flagged'
        assert fake_proxy.mark_args == ([11, 12], 'flagged')

    def test_partial_update_still_reports_actual_count(self, fake_proxy):
        """存在但已被删的 legacy id：updated 是真实更新数（不是请求条数）。"""
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        fake_proxy.updated = 1
        _set_request({'log_ids': [21, 22, 23], 'mark': 'flagged'})
        body, _http_code = LogCommandService.mark_logs()

        assert body['data'] == {'updated': 1}
        assert body['message'] == '已为 1 条日志添加标记: flagged'


# =====================================================================
# 2. DB 保留清扫豁免已标记行（契约 §Q5.1）
# =====================================================================

class TestPurgerKeepsMarkedRows:
    def test_default_skips_marked_rows(self):
        """默认口径即豁免：只有 mark IS NULL / '' 的行参与归档 + 删除。"""
        old = (_now() - timedelta(days=3)).replace(microsecond=0)
        _seed([
            (old, 'execution', 'c1', '已标记', 'flagged'),
            (old, 'execution', 'c1', '空串标记', ''),
            (old, 'execution', 'c1', '未标记', None),
        ])
        storage = FakeObjectStore()
        result = LogArchivePurger(store=_store(storage), batch_size=10).run(
            _now() - timedelta(days=1))

        assert not result.failed
        assert (result.archived_count, result.deleted_count) == (2, 2)
        assert _remaining_contents() == ['已标记']
        archived = storage.archive(f'tasks/{_TASK_ID}/c1/{old.strftime("%Y-%m-%d")}')
        assert {e['content'] for e in archived} == {'空串标记', '未标记'}

    def test_keep_marked_false_still_purges_everything(self):
        """显式整类清（脚本 --include-marked / 人工 clear keep_marked=false）不受影响。"""
        old = (_now() - timedelta(days=3)).replace(microsecond=0)
        _seed([
            (old, 'execution', 'c2', '已标记', 'flagged'),
            (old, 'execution', 'c2', '未标记', None),
        ])
        result = LogArchivePurger(store=_store(FakeObjectStore()), batch_size=10,
                                  keep_marked=False).run(_now() - timedelta(days=1))

        assert (result.archived_count, result.deleted_count) == (2, 2)
        assert _remaining_contents() == []


class TestRetentionCleanerExemptsMarked:
    def test_cleaner_keeps_marked_row_and_deletes_unmarked(self):
        """造 1 条 3 天前已标记行 + 未标记行，retention_days=1 跑一轮只删未标记。"""
        old = (_now() - timedelta(days=3)).replace(microsecond=0)
        _seed([
            (old, 'execution', 'c3', '三天前已标记', 'flagged'),
            (old, 'execution', 'c3', '三天前空串', ''),
            (old, 'execution', 'c3', '三天前未标记', None),
        ])
        storage = FakeObjectStore()
        cleaner = _no_lock(LogRetentionCleaner(
            retention_days=1, store=_store(storage), batch_size=10))

        summary = cleaner.run_once()

        assert summary['status'] == 'ok'
        assert (summary['archived'], summary['deleted']) == (2, 2)
        assert _remaining_contents() == ['三天前已标记']
        archived = storage.archive(f'tasks/{_TASK_ID}/c3/{old.strftime("%Y-%m-%d")}')
        assert {e['content'] for e in archived} == {'三天前空串', '三天前未标记'}

    def test_daily_cleaner_passes_keep_marked_true(self, monkeypatch):
        """清扫链路必须显式透传 keep_marked=True（不能靠默认值漂移）。"""
        captured = {}

        class _SpyPurger:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run(self, cutoff):
                captured['cutoff'] = cutoff
                return PurgeResult(remaining_count=0)

        monkeypatch.setattr(
            'task_service.infrastructure.persistence.log_retention_cleaner'
            '.LogArchivePurger', _SpyPurger)
        cleaner = _no_lock(LogRetentionCleaner(retention_days=1, batch_size=10))

        cleaner.run_once()

        assert captured['keep_marked'] is True
        assert captured['exclude_audit'] is True


def _load_purge_script():
    path = os.path.join(_PROJECT_ROOT, 'scripts', 'maintenance',
                        'purge_legacy_logs_int1785.py')
    spec = importlib.util.spec_from_file_location('purge_legacy_logs_int1903', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOneOffScriptMarkedPolicy:
    def test_script_keeps_marked_by_default(self, monkeypatch):
        old = (_now() - timedelta(days=3)).replace(microsecond=0)
        _seed([
            (old, 'execution', 'c4', '脚本已标记', 'flagged'),
            (old, 'execution', 'c4', '脚本未标记', None),
        ])
        storage = FakeObjectStore()
        monkeypatch.setattr('shared.clients.oss_client.oss', storage)
        script = _load_purge_script()

        code = script.main(['--cutoff', (_now() - timedelta(days=1)).isoformat()])

        assert code == script.EXIT_OK == 0
        assert _remaining_contents() == ['脚本已标记']

    def test_script_include_marked_clears_all(self, monkeypatch):
        old = (_now() - timedelta(days=3)).replace(microsecond=0)
        _seed([
            (old, 'execution', 'c5', '脚本已标记', 'flagged'),
            (old, 'execution', 'c5', '脚本未标记', None),
        ])
        storage = FakeObjectStore()
        monkeypatch.setattr('shared.clients.oss_client.oss', storage)
        script = _load_purge_script()

        code = script.main(['--cutoff', (_now() - timedelta(days=1)).isoformat(),
                            '--include-marked'])

        assert code == script.EXIT_OK == 0
        assert _remaining_contents() == []
