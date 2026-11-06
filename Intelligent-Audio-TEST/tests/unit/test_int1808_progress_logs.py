# -*- coding: utf-8 -*-
"""INT-1808 进度事件「最近日志」取数改造回归。

原缺陷（INT-1793 D5）：`_progress.py` 的最近日志走 `list_logs`（DB），而
INT-81 起业务日志已去库化落文件（logs/business/{task_id}/...）→ 新任务的
进度事件「最近日志」恒空。

修复语义（本文件覆盖，纯单测不触真实 DB/gRPC/Redis）：
- 任务在业务日志根下有 .log 文件 → 读文件最近 20 条（按 time 倒序取头再
  反转为正序，与 DB 路径输出顺序一致），level 小写、message=content；
- 无任何日志文件（目录不存在 / 目录为空，即 INT-81 之前的历史任务）→
  回落 DB `list_logs`，不报错；
- 文件存在但读到空列表 → 以文件为准，不再回落（避免重复读库）；
- 文件读取异常 → 回落 DB，进度事件不中断；
- 条数上限 20（RECENT_LOG_LIMIT）。
"""
import json
import os
from datetime import datetime, timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402,F401  先定位仓库根，再导入事件管理器
from shared.logging import reset_log_settings  # noqa: E402
from shared.logging.config import LogSettings  # noqa: E402
from shared.logging.enums import LogEnvironment  # noqa: E402
from shared.utils.event_manager._progress import (  # noqa: E402
    RECENT_LOG_LIMIT,
    _build_logs_from_business_files,
    _build_recent_logs,
)
import shared.utils.event_manager._progress as progress_mod  # noqa: E402

_TASK_ID = 18080001
_OTHER_TASK_ID = 18080002
_TIME_FMT = '%Y-%m-%d %H:%M:%S.%f'
_BASE_TIME = datetime(2026, 10, 24, 9, 0, 0)


def _make_settings(root):
    return LogSettings(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
        business_max_scan_entries=100_000,
        business_scan_cache_ttl_seconds=3,
    )


def _entry(minute, content, level='INFO'):
    return {
        'time': (_BASE_TIME + timedelta(minutes=minute)).strftime(_TIME_FMT),
        'level': level,
        'category': 'execution',
        'module': 'execution_engine',
        'source': 'task_service',
        'content': content,
        'task_id': _TASK_ID,
    }


def _write_business_file(root, rel_path, entries):
    """按业务日志路径模板落一个 JSON Lines 文件。"""
    path = os.path.join(root, 'business', rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for record in entries:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    return path


def _expected_ts(minute):
    """与 _ts_ms 同口径：naive 东八区时间 → 毫秒时间戳。"""
    from shared.utils.time_utils import UTC8
    return int((_BASE_TIME + timedelta(minutes=minute)).replace(tzinfo=UTC8).timestamp() * 1000)


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    reset_log_settings()
    import shared.logging.business_reader as br
    br._SCAN_CACHE.clear()


@pytest.fixture()
def db_logs(monkeypatch):
    """DB 回退桩：记录 list_logs 调用参数并返回固定历史行。"""
    calls = []

    def _fake_list_logs(**kwargs):
        calls.append(kwargs)
        # 与 task_service 仓储同口径：id 倒序返回（最新在前），进度链反转后正序展示
        return {'items': [
            {'id': 12, 'level': 'WARNING', 'content': '历史任务DB日志-新',
             'time': '2026-09-01 10:05:00'},
            {'id': 11, 'level': 'INFO', 'content': '历史任务DB日志-旧',
             'time': '2026-09-01 10:00:00'},
        ]}

    monkeypatch.setattr('shared.clients.grpc_clients.list_logs', _fake_list_logs)
    return calls


class TestBusinessFileSource:
    """有业务文件：读文件，结构与排序与 DB 路径一致。"""

    def test_reads_recent_logs_from_business_file(self, log_root):
        _write_business_file(
            log_root, f'{_TASK_ID}/dev-1/round-1/execution.task_service.host-1.log',
            [_entry(0, '开始执行用例1'), _entry(1, '用例1执行完成'),
             _entry(2, '开始执行用例2', level='ERROR')])

        logs = _build_recent_logs(_TASK_ID)

        assert [item.message for item in logs] == [
            '开始执行用例1', '用例1执行完成', '开始执行用例2']
        # 时间正序（与 DB 路径 reversed 后一致）
        assert [item.timestamp for item in logs] == [
            _expected_ts(0), _expected_ts(1), _expected_ts(2)]
        # level 统一小写（前端契约）
        assert [item.level for item in logs] == ['info', 'info', 'error']
        # 文件条目 id 为稳定 int（非 DB id 亦然）
        assert all(isinstance(item.id, int) and item.id > 0 for item in logs)

    def test_merges_devices_and_sorts_by_time(self, log_root):
        """多设备/多轮目录：跨文件按时间全局正序。"""
        _write_business_file(
            log_root, f'{_TASK_ID}/dev-1/round-1/execution.task_service.host-1.log',
            [_entry(0, 'dev1-0'), _entry(2, 'dev1-2')])
        _write_business_file(
            log_root, f'{_TASK_ID}/dev-2/round-1/execution.task_service.host-2.log',
            [_entry(1, 'dev2-1'), _entry(3, 'dev2-3')])

        logs = _build_recent_logs(_TASK_ID)

        assert [item.message for item in logs] == ['dev1-0', 'dev2-1', 'dev1-2', 'dev2-3']

    def test_limits_to_20_newest(self, log_root):
        entries = [_entry(i, f'日志{i:02d}') for i in range(RECENT_LOG_LIMIT + 5)]
        _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log',
            entries)

        logs = _build_recent_logs(_TASK_ID)

        assert RECENT_LOG_LIMIT == 20
        assert len(logs) == RECENT_LOG_LIMIT
        # 取最近 20 条（丢最早 5 条），并保持正序
        assert [item.message for item in logs] == [f'日志{i:02d}' for i in range(5, 25)]

    def test_global_newest_20_across_multiple_files(self, log_root):
        """多文件（多设备/多轮）交错：全局最新 20 条跨文件取，不按文件截断。"""
        for device in range(3):
            _write_business_file(
                log_root,
                f'{_TASK_ID}/dev-{device}/round-1/'
                f'execution.task_service.host-{device}.log',
                # 设备 d 的时间为 d, 3+d, 6+d ...（交错）
                [_entry(i * 3 + device, f'dev{device}-{i:02d}') for i in range(30)])

        logs = _build_recent_logs(_TASK_ID)

        assert len(logs) == RECENT_LOG_LIMIT
        # 时间 87..72 共 16 条 + 71..69（时间 71 有 dev2 一条；逐条核对全局最新）
        times = [item.timestamp for item in logs]
        assert times == sorted(times)
        expected = sorted(
            (_expected_ts(i * 3 + d), f'dev{d}-{i:02d}')
            for d in range(3) for i in range(30))[-RECENT_LOG_LIMIT:]
        assert [(item.timestamp, item.message) for item in logs] == expected

    def test_files_present_but_empty_does_not_fall_back(self, log_root, db_logs):
        """文件存在（空文件）→ 以文件为准，即使读到空列表也不读库。"""
        _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log', [])

        assert _build_logs_from_business_files(_TASK_ID) == []
        assert _build_recent_logs(_TASK_ID) == []
        assert db_logs == []

    def test_tail_read_grows_chunk_for_long_lines(self, log_root, monkeypatch):
        """尾块不足 20 条时按需翻倍，不因长行截断而漏条或报错。"""
        monkeypatch.setattr(progress_mod, 'BUSINESS_LOG_TAIL_CHUNK_BYTES', 128)
        _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log',
            [_entry(i, f'长内容日志{i:02d}-' + 'x' * 200) for i in range(30)])

        logs = _build_recent_logs(_TASK_ID)

        assert len(logs) == RECENT_LOG_LIMIT
        assert logs[0].message.startswith('长内容日志10-')
        assert logs[-1].message.startswith('长内容日志29-')

    def test_tail_read_is_bounded_on_large_file(self, log_root, monkeypatch):
        """大文件只回读尾部：2 万行文件单次读取远小于文件本身。"""
        path = _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log',
            [_entry(i, f'大文件日志{i:05d}') for i in range(20000)])
        read_bytes = {'total': 0}
        real_open = open

        def _counting_open(file, mode='r', *args, **kwargs):
            handle = real_open(file, mode, *args, **kwargs)
            if file == path and 'b' in mode:
                real_read = handle.read

                def _read(size=-1):
                    data = real_read(size)
                    read_bytes['total'] += len(data)
                    return data

                handle.read = _read
            return handle

        monkeypatch.setattr('builtins.open', _counting_open)
        file_size = os.path.getsize(path)

        logs = _build_recent_logs(_TASK_ID)

        assert len(logs) == RECENT_LOG_LIMIT
        assert logs[-1].message == '大文件日志19999'
        assert read_bytes['total'] < file_size // 10, \
            f"尾读读取量 {read_bytes['total']} 应远小于文件 {file_size}"

    def test_ids_stable_across_emits(self, log_root):
        """同一记录多次取数 id 稳定（前端列表 key 不抖动）。"""
        _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log',
            [_entry(0, 'A'), _entry(1, 'B')])

        first = _build_recent_logs(_TASK_ID)
        second = _build_recent_logs(_TASK_ID)

        assert [item.id for item in first] == [item.id for item in second]
        assert len({item.id for item in first}) == 2

    def test_other_task_files_are_not_used(self, log_root, db_logs):
        """只读本任务目录；别的任务有文件不影响本任务判定。"""
        _write_business_file(
            log_root, f'{_OTHER_TASK_ID}/common/shared/execution.task_service.host-1.log',
            [_entry(0, '别的任务')])

        logs = _build_recent_logs(_TASK_ID)

        assert len(db_logs) == 1  # 回落 DB
        assert [item.message for item in logs] == ['历史任务DB日志-旧', '历史任务DB日志-新']


class TestDbFallback:
    """无业务文件的历史任务：回落 DB 且不报错。"""

    def test_no_directory_falls_back_to_db(self, log_root, db_logs):
        assert _build_logs_from_business_files(_TASK_ID) is None

        logs = _build_recent_logs(_TASK_ID)

        assert len(db_logs) == 1
        assert db_logs[0]['task_id'] == _TASK_ID
        assert db_logs[0]['per_page'] == RECENT_LOG_LIMIT
        assert [item.message for item in logs] == ['历史任务DB日志-旧', '历史任务DB日志-新']
        assert [item.level for item in logs] == ['info', 'warning']
        assert logs[-1].timestamp == _expected_ts_from_iso('2026-09-01 10:05:00')

    def test_empty_task_directory_falls_back_to_db(self, log_root, db_logs):
        """任务目录存在但没有任何 .log 文件 → 视同无业务文件，回落 DB。"""
        os.makedirs(os.path.join(log_root, 'business', str(_TASK_ID)), exist_ok=True)

        assert _build_logs_from_business_files(_TASK_ID) is None
        assert len(_build_recent_logs(_TASK_ID)) == 2
        assert len(db_logs) == 1

    def test_read_error_falls_back_to_db(self, log_root, db_logs, monkeypatch):
        """文件读取异常不打断进度事件：回落 DB。"""
        _write_business_file(
            log_root, f'{_TASK_ID}/common/shared/execution.task_service.host-1.log',
            [_entry(0, '文件内日志')])

        def _boom(*args, **kwargs):
            raise OSError('模拟日志文件不可读')

        monkeypatch.setattr(progress_mod, '_file_tail_records', _boom)

        logs = _build_recent_logs(_TASK_ID)

        assert len(db_logs) == 1
        assert [item.message for item in logs] == ['历史任务DB日志-旧', '历史任务DB日志-新']

    def test_db_unavailable_returns_empty(self, log_root, monkeypatch):
        """两侧都不可用（无文件 + DB 异常）→ 空列表，不抛。"""
        def _boom(**kwargs):
            raise RuntimeError('gRPC 不可用')

        monkeypatch.setattr('shared.clients.grpc_clients.list_logs', _boom)

        assert _build_recent_logs(_TASK_ID) == []


def _expected_ts_from_iso(text):
    from shared.utils.time_utils import UTC8
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC8).timestamp() * 1000)
