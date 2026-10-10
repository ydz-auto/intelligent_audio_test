# -*- coding: utf-8 -*-
"""INT-81 审计打回修复回归（2026-10-10 审计问题 1-4/6）。

- 问题 1（阻塞）：多副本日志轮转竞态 —— 服务运行日志活跃名含 PID
  （app-{pid}.log）、业务日志文件名含 PID；两真实子进程并发高频轮转/
  切分零丢行（旧实现共享文件名会 os.replace 互踩）
- 问题 2（子集）：读取侧条数上限 LOG_BUSINESS_MAX_SCAN_ENTRIES，
  total 下界语义，超限保留最新条目
- 问题 3：服务日志清扫排除 business/ 子树，两套保留天数互不叠加
- 问题 4：category='device'（审计类别）带 task_id 的日志保持业务文件
  路径不被改道入库（分流顺序钉死），auth 审计照旧入库
- 问题 6：写入侧统一 LOG_TIME_FORMAT；读取侧时间过滤按可解析时间比较
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int81_rework_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import shared.logging  # noqa: E402  定位仓库根供子进程 sys.path 注入
from shared.logging import (  # noqa: E402
    BusinessLogFileWriter,
    BusinessLogReader,
    LogSettings,
    reset_log_settings,
    sweep_expired_files,
    sweep_log_root,
)
from shared.logging.enums import LogEnvironment  # noqa: E402
from shared.logging.path_builder import BUSINESS_DIR  # noqa: E402
from shared.logging.service_handler import (  # noqa: E402
    ServiceRotatingFileHandler,
    default_service_base_name,
)

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])

_AGE_DAY = 86400


def _make_settings(root, *, business_max_bytes=50 * 1024 * 1024,
                   service_retention_days=30, business_retention_days=30,
                   business_max_scan_entries=100_000):
    return LogSettings(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=service_retention_days,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=business_max_bytes,
        business_retention_days=business_retention_days,
        business_max_scan_entries=business_max_scan_entries,
    )


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    reset_log_settings()


def _age_file(path: Path, days: float):
    stamp = time.time() - days * _AGE_DAY
    os.utime(path, (stamp, stamp))


# ---------------------------------------------------------------------------
# 问题 1：多副本并发轮转（真实两子进程）
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = '''
import os
import sys

repo_root, mode, log_dir, count = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
sys.path.insert(0, repo_root)
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'), 'int81_worker_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

if mode == 'service':
    import logging
    from shared.logging.service_handler import ServiceRotatingFileHandler

    handler = ServiceRotatingFileHandler(log_dir, max_bytes=256)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('int81_worker')
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    for i in range(count):
        logger.info('worker-%d-line-%04d' % (os.getpid(), i))
    handler.close()
else:
    from datetime import datetime
    from shared.logging import BusinessLogFileWriter, LogEnvironment, LogSettings

    settings = LogSettings(
        root_dir=log_dir, environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024, service_retention_days=30,
        business_enabled=True, business_db_enabled=False,
        business_max_bytes=300, business_retention_days=30)
    writer = BusinessLogFileWriter(settings=settings, service_name='worker_svc')
    for i in range(count):
        writer.write({
            'time': datetime.now(), 'level': 'INFO', 'category': 'execution',
            'module': 'worker', 'source': 'backend',
            'content': 'worker-%d-line-%04d' % (os.getpid(), i),
            'task_id': 9001, 'device_id': 1, 'round': 1,
        })
    writer.close_all()
print('OK %d' % os.getpid())
'''


def _run_two_workers(log_root, mode, count=60):
    """并发拉起两个写入子进程（模拟 deploy.replicas=2），返回 (pids, results)。"""
    script = Path(log_root).parent / 'int81_worker.py'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_WORKER_SCRIPT, encoding='utf-8')
    procs = [
        subprocess.Popen(
            [sys.executable, str(script), _REPO_ROOT, mode, str(log_root), str(count)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    results = [proc.communicate() for proc in procs]
    for proc, (out, err) in zip(procs, results):
        assert proc.returncode == 0, f'worker 异常退出: {err}'
    pids = [int(out.strip().split()[-1]) for out, _ in results]
    return pids, results


class TestTwoProcessConcurrency:
    """审计问题 1：共享日志卷 + 多副本并发轮转/切分零丢行。"""

    def test_service_logs_concurrent_rotation_no_line_loss(self, tmp_path):
        log_dir = str(tmp_path / 'logs' / 'api_test_service')
        count = 60
        pids, _ = _run_two_workers(log_dir, 'service', count)

        lines = []
        for name in os.listdir(log_dir):
            with open(os.path.join(log_dir, name), 'rb') as handle:
                lines.extend(handle.read().decode('utf-8').splitlines())
        expected = {f'worker-{pid}-line-{i:04d}' for pid in pids for i in range(count)}
        assert sorted(lines) == sorted(expected), (
            '两副本并发轮转丢行/重复行：共享活跃文件名或轮转目标冲突')

    def test_business_logs_concurrent_split_no_line_loss(self, tmp_path):
        root = str(tmp_path / 'logs')
        count = 60
        pids, _ = _run_two_workers(root, 'business', count)

        biz_dir = os.path.join(root, BUSINESS_DIR, '9001', '1', '1')
        names = os.listdir(biz_dir)
        # 每个写入进程持有独立文件族（PID 进文件名，活跃或切分形态均算）
        pid_files = {n for n in names
                     for pid in pids if f'.{pid}.' in n or f'.{pid}-' in n}
        assert len(pid_files) >= 2, f'两副本应各持有独立活跃文件，实际: {names[:8]}...'
        contents = []
        for name in names:
            with open(os.path.join(biz_dir, name), 'rb') as handle:
                for line in handle.read().decode('utf-8').splitlines():
                    if line.strip():
                        contents.append(json.loads(line)['content'])
        expected = [f'worker-{pid}-line-{i:04d}' for pid in pids for i in range(count)]
        assert sorted(contents) == sorted(expected), (
            '两副本并发切分丢行/重复行：切分目标 os.replace 互踩')


class TestCrossLineageRotationIsolation:
    """同目录两条 PID 线同时轮转互不干扰（确定性，单进程模拟双副本）。"""

    def test_simultaneous_rollover_no_cross_replace(self, tmp_path):
        import logging
        dir_path = str(tmp_path / 'svc')
        first = ServiceRotatingFileHandler(dir_path, base_name='app-111.log',
                                           max_bytes=0)
        second = ServiceRotatingFileHandler(dir_path, base_name='app-222.log',
                                            max_bytes=0)
        logger_a = logging.getLogger('int81_iso_a')
        logger_b = logging.getLogger('int81_iso_b')
        for logger, handler in ((logger_a, first), (logger_b, second)):
            logger.propagate = False
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        try:
            logger_a.info('a-yesterday')
            logger_b.info('b-yesterday')
            first._current_day = '20200101'
            second._current_day = '20200101'
            # 两线同一时刻跨天轮转：各自 rename 各自的活跃文件
            logger_a.info('a-line')
            logger_b.info('b-line')
        finally:
            for logger, handler in ((logger_a, first), (logger_b, second)):
                logger.removeHandler(handler)
            first.close()
            second.close()
        rotated_a = os.path.join(dir_path, 'app-111-20200101-001.log')
        rotated_b = os.path.join(dir_path, 'app-222-20200101-001.log')
        assert os.path.exists(rotated_a)
        assert os.path.exists(rotated_b)
        assert 'a-yesterday' in open(rotated_a, encoding='utf-8').read()
        assert 'b-yesterday' in open(rotated_b, encoding='utf-8').read()
        active_a = os.path.join(dir_path, 'app-111.log')
        active_b = os.path.join(dir_path, 'app-222.log')
        assert 'a-line' in open(active_a, encoding='utf-8').read()
        assert 'b-line' in open(active_b, encoding='utf-8').read()


# ---------------------------------------------------------------------------
# 问题 3：保留天数互不叠加
# ---------------------------------------------------------------------------

class TestRetentionSeparation:

    def test_business_retention_independent_of_service_days(self, tmp_path):
        root = tmp_path / 'logs'
        svc_dir = root / 'evaluation_service'
        svc_dir.mkdir(parents=True)
        biz_dir = root / BUSINESS_DIR / '5' / '1' / '1'
        biz_dir.mkdir(parents=True)

        svc_32d = svc_dir / 'app-111.log'
        svc_32d.write_text('svc', encoding='utf-8')
        biz_32d = biz_dir / 'execution.svc.4321.log'
        biz_32d.write_text('biz recent', encoding='utf-8')
        biz_40d = biz_dir / 'execution.svc.4322.log'
        biz_40d.write_text('biz stale', encoding='utf-8')
        _age_file(svc_32d, 32)
        _age_file(biz_32d, 32)
        _age_file(biz_40d, 40)

        settings = _make_settings(str(root), service_retention_days=30,
                                  business_retention_days=35)
        sweep_log_root(settings)

        # 服务日志按 30 天清（32 天文件删除）；业务日志按 35 天清（32 天保留）
        assert not svc_32d.exists(), '服务日志 30 天保留未生效'
        assert biz_32d.exists(), '业务日志被服务保留天数误清（保留天数叠加）'
        assert not biz_40d.exists(), '业务日志 35 天保留未生效'

    def test_exclude_dir_keeps_subtree_files(self, tmp_path):
        keep_dir = tmp_path / 'keep' / BUSINESS_DIR / '9'
        keep_dir.mkdir(parents=True)
        keep_file = keep_dir / 'execution.svc.log'
        keep_file.write_text('x', encoding='utf-8')
        _age_file(keep_file, 400)
        # exclude 指定时：business 子树的过期文件与空目录均不触碰
        deleted = sweep_expired_files(str(tmp_path / 'keep'), retention_days=30,
                                      exclude_dir=BUSINESS_DIR)
        assert deleted == 0
        assert keep_file.exists()


# ---------------------------------------------------------------------------
# 问题 4：device 审计类别 + task_id 保持业务分流
# ---------------------------------------------------------------------------

@pytest.fixture()
def emit_env(tmp_path, monkeypatch):
    """独立 DatabaseLogHandler（同 audit 套件隔离手法）。"""
    import shared.clients.grpc_clients as grpc_clients_mod
    import shared.utils.log_handler._state as lh_state
    from shared.utils.log_handler import DatabaseLogHandler

    prev = lh_state._global_db_handler
    if prev is not None:
        prev.queue.put(None)
        prev_worker = getattr(prev, 'worker_thread', None)
        if prev_worker is not None:
            prev_worker.join(timeout=2.0)

    captured = []

    def _fake_batch_create(logs_payload):
        captured.extend(logs_payload)
        return [9500 + i for i in range(len(logs_payload))]

    monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
    monkeypatch.setattr(
        grpc_clients_mod, 'archive_logs',
        lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
    import shared.clients.oss_client as oss_client_mod
    monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)

    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    monkeypatch.chdir(tmp_path)
    handler = DatabaseLogHandler()
    handler._batch_size = 1
    handler.set_console_log(False)
    monkeypatch.setattr(lh_state, '_global_db_handler', handler)
    yield tmp_path / 'logs', captured
    handler.queue.put(None)
    reset_log_settings()


def _wait_for(condition, timeout=3.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


class TestDeviceCategoryTaskScopedRouting:

    def test_device_category_with_task_id_stays_on_business_path(self, emit_env):
        """category='device'（同属审计枚举）带 task_id 是设备交互业务日志：
        必须落业务文件，不得按审计类别优先改道入库（去库化红线）。"""
        from shared.logging import resolve_service_name
        from shared.utils.log_handler import log_not_emit

        logs_root, captured = emit_env
        log_not_emit('INFO', 'device_engine', 'device interaction during task',
                     category='device', task_id=301, device_id=9, round=1)
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), \
            "category='device' 业务日志被审计类别改道入库"
        biz_file = (logs_root / 'business' / '301' / '9' / '1'
                    / f'device.{resolve_service_name()}.{os.getpid()}.log')
        assert _wait_for(biz_file.exists), '设备交互业务日志未落业务文件'
        entry = json.loads(biz_file.read_text(encoding='utf-8').splitlines()[0])
        assert entry['log_type'] == 'device'
        assert 'device interaction during task' in entry['content']

    def test_auth_audit_without_task_still_lands_db(self, emit_env):
        """审计写入器（无任务上下文）照旧落库：分流顺序改动不回退 INT-30。"""
        from auth_service.application.services.auth_audit import write_auth_audit
        from shared.models.common_enums import AuditEvent

        _, captured = emit_env
        write_auth_audit(AuditEvent.AUTH_USER_CREATED, 'user_management', {
            'operator_id': 1, 'target_id': 2, 'delta': {'username': 'u2'},
        })
        assert _wait_for(lambda: len(captured) >= 1), 'auth 审计未落库'
        assert captured[0]['category'] == 'auth'
        assert captured[0]['task_id'] is None


# ---------------------------------------------------------------------------
# 问题 6：读取侧时间过滤按可解析时间比较
# ---------------------------------------------------------------------------

class TestReaderTimeFilter:

    def _seed(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc', process_id=4321)
        for i, content in enumerate(('early', 'middle', 'late')):
            writer.write({
                'time': datetime(2026, 10, 10, 12, i, 30, 100000,
                                 tzinfo=timezone(timedelta(hours=8))),
                'level': 'INFO', 'category': 'execution', 'module': 'm',
                'source': 'backend', 'content': content,
                'task_id': 501, 'device_id': 2, 'round': 1,
            })

    def test_iso_start_time_filters_space_format_entries(self, log_root):
        """start_time 用 ISO 'T' 分隔、文件条目为空格分隔：按时间比较而非字符串。"""
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=501,
                                    start_time='2026-10-10T12:01:00')
        assert [item['content'] for item in items] == ['late', 'middle']

    def test_end_time_inclusive_boundary(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=501,
                                    end_time='2026-10-10T12:01:30.100000')
        assert [item['content'] for item in items] == ['middle', 'early']

    def test_unparseable_time_falls_back_to_string_compare(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        # 不可解析的时间串：回退字符串比较，不抛异常
        items = reader.read_entries(task_id=501, start_time='not-a-date')
        assert items == []


# ---------------------------------------------------------------------------
# 问题 2 子集：读取条数上限
# ---------------------------------------------------------------------------

class TestScanCap:

    def _seed(self, log_root, total=8):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc', process_id=4321)
        for i in range(total):
            writer.write({
                'time': datetime(2026, 10, 10, 12, 0, i, 100000,
                                 tzinfo=timezone(timedelta(hours=8))),
                'level': 'INFO', 'category': 'execution', 'module': 'm',
                'source': 'backend', 'content': f'line-{i}',
                'task_id': 601, 'device_id': 2, 'round': 1,
            })

    def test_cap_keeps_newest_entries(self, log_root, monkeypatch):
        monkeypatch.setattr(
            'shared.logging.config._SETTINGS',
            _make_settings(log_root, business_max_scan_entries=5))
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=601)
        assert len(items) == 5
        # 保留最新 5 条（写入序 3-7），最旧 3 条被截断
        assert [item['content'] for item in items] == \
            [f'line-{i}' for i in (7, 6, 5, 4, 3)]

    def test_cap_zero_means_unlimited(self, log_root, monkeypatch):
        monkeypatch.setattr(
            'shared.logging.config._SETTINGS',
            _make_settings(log_root, business_max_scan_entries=0))
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        assert len(reader.read_entries(task_id=601)) == 8

    def test_page_total_is_floor_semantics(self, log_root, monkeypatch):
        monkeypatch.setattr(
            'shared.logging.config._SETTINGS',
            _make_settings(log_root, business_max_scan_entries=5))
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        page = reader.read_page(task_id=601, page=1, per_page=2)
        assert page['total'] == 5  # 下界语义
        assert len(page['items']) == 2


# ---------------------------------------------------------------------------
# 问题 1 收尾：默认服务日志活跃名 / 业务文件名均含 PID
# ---------------------------------------------------------------------------

class TestPidNaming:

    def test_default_service_base_name(self):
        assert default_service_base_name() == f'app-{os.getpid()}.log'

    def test_writer_default_process_id_is_current_pid(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc')
        rel = writer.write({
            'time': '2026-10-10 12:00:00.000000', 'level': 'INFO',
            'category': 'execution', 'module': 'm', 'source': 'backend',
            'content': 'pid line', 'task_id': 701, 'device_id': 2, 'round': 1,
        })
        assert rel.replace(os.sep, '/').endswith(f'execution.svc.{os.getpid()}.log')
