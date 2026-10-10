# -*- coding: utf-8 -*-
"""INT-81 测试验收补充：跨天轮转 / 天+大小组合轮转 / 线程级轮次上下文落盘。

开发自测的 test_int81_log_system.py 覆盖了按大小轮转与路径模板，
本文件补齐验收标准 1 的「跨天」条件与轮次上下文的 emit 集成：

- 服务运行日志跨天自动轮转（_current_day 过期 → 下一条日志触发轮转）
- 跨天轮转与同日超限切分叠加时按天前缀命名互不覆盖
- emit 分流中线程级 log_round() 上下文将业务日志归入轮次目录
  （E2E 轮次循环/评估 Worker 的接线方式，调用点零显式传参）
"""
import logging
import os
import tempfile
import time
from datetime import datetime

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int81_acc_') + '/acc.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.logging import LogSettings, reset_log_settings
from shared.logging.config import resolve_service_name
from shared.logging.enums import LogEnvironment
from shared.logging.service_handler import ServiceRotatingFileHandler


def _make_settings(root, **overrides):
    values = dict(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
    )
    values.update(overrides)
    return LogSettings(**values)


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    reset_log_settings()


def _attach(handler, name):
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _detach(logger, handler):
    logger.removeHandler(handler)
    handler.close()


class TestDayRollover:

    def test_day_change_rotates_before_write(self, tmp_path, log_root):
        """跨天：日期变化后下一条日志先轮转再写入，旧文件保留昨日内容。"""
        handler = ServiceRotatingFileHandler(str(tmp_path / 'svc'),
                                             base_name='app.log', max_bytes=0)
        logger = _attach(handler, 'int81_day_test')
        try:
            logger.info('yesterday line')
            # 模拟午夜跨越：活跃日戳停留在过期日期
            handler._current_day = '20200101'
            logger.info('today line')
        finally:
            _detach(logger, handler)

        rotated = tmp_path / 'svc' / 'app-20200101-001.log'
        active = tmp_path / 'svc' / 'app.log'
        assert rotated.exists(), '跨天未产生轮转文件'
        rotated_text = rotated.read_text(encoding='utf-8')
        assert 'yesterday line' in rotated_text
        assert 'today line' not in rotated_text
        active_text = active.read_text(encoding='utf-8')
        assert 'today line' in active_text
        assert 'yesterday line' not in active_text
        assert handler._current_day == datetime.now().strftime('%Y%m%d')

    def test_day_rollover_after_size_split_no_overwrite(self, tmp_path, log_root):
        """跨天与超限切分叠加：轮转名按天前缀命名，同日切分文件不被覆盖。"""
        handler = ServiceRotatingFileHandler(str(tmp_path / 'svc'),
                                             base_name='app.log', max_bytes=50)
        logger = _attach(handler, 'int81_day_size_test')
        try:
            today = datetime.now().strftime('%Y%m%d')
            for i in range(8):
                logger.info(f'line {i:02d} padding padding padding')
            # 至少一次超限切分发生（同日 -001）
            assert (tmp_path / 'svc' / f'app-{today}-001.log').exists()
            size_split_before = (tmp_path / 'svc' / f'app-{today}-001.log').read_bytes()
            # 跨天再写一条
            handler._current_day = '20200101'
            logger.info('next day line')
        finally:
            _detach(logger, handler)

        # 跨天轮转目标带新日期前缀，不与同日切分文件同名
        day_file = tmp_path / 'svc' / 'app-20200101-001.log'
        assert day_file.exists(), '跨天轮转文件缺失'
        assert 'next day line' not in day_file.read_text(encoding='utf-8')
        # 同日超限切分文件内容未被覆盖
        assert (tmp_path / 'svc' / f'app-{today}-001.log').read_bytes() == size_split_before


class TestThreadRoundContext:

    @pytest.fixture()
    def emit_env(self, tmp_path, monkeypatch):
        """独立 DatabaseLogHandler + 独立日志根目录（复用 audit 套件的隔离手法）。"""
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
            return [8000 + i for i in range(len(logs_payload))]

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

    def test_log_round_context_routes_to_round_dir(self, emit_env):
        """log_round() 范围内的业务日志自动归轮次目录（E2E 轮次循环接线方式）。"""
        from shared.logging.context import log_round
        from shared.utils.log_handler import log_not_emit

        logs_root, captured = emit_env
        with log_round(5):
            log_not_emit('INFO', 'round_engine', 'thread-scoped round line',
                         category='execution', task_id=88, device_id=4)
        # 范围外同任务日志不受线程上下文残留影响
        log_not_emit('INFO', 'round_engine', 'post-round line',
                     category='execution', task_id=88, device_id=4)

        svc = resolve_service_name()
        round_file = logs_root / 'business' / '88' / '4' / '5' / f'execution.{svc}.{os.getpid()}.log'
        deadline = time.time() + 3
        while time.time() < deadline and not round_file.exists():
            time.sleep(0.05)
        assert round_file.exists(), '轮次上下文未将业务日志归入轮次目录'
        content = round_file.read_text(encoding='utf-8')
        assert 'thread-scoped round line' in content

        # 上下文退出后（round=None）落 shared 目录
        shared_file = logs_root / 'business' / '88' / '4' / 'shared' / f'execution.{svc}.{os.getpid()}.log'
        deadline = time.time() + 3
        while time.time() < deadline and not shared_file.exists():
            time.sleep(0.05)
        assert shared_file.exists(), 'log_round 退出后上下文未清除，日志误归轮次目录'
        assert 'post-round line' in shared_file.read_text(encoding='utf-8')
        assert captured == [], '业务日志不应进入 DB 队列'

    def test_business_db_enabled_rollback_double_writes(self, emit_env, monkeypatch):
        """LOG_BUSINESS_DB_ENABLED=True 回滚开关：业务日志恢复入库双写。"""
        import shared.logging.config as log_config
        from shared.utils.log_handler import log_not_emit

        logs_root, captured = emit_env
        # emit_env 的 handler 已按默认（不入库）构建；换一个开启回滚开关的实例
        prev = log_config.get_log_settings()
        monkeypatch.setattr(
            'shared.logging.config._SETTINGS',
            _make_settings(str(logs_root), business_db_enabled=True))

        import shared.utils.log_handler._state as lh_state
        from shared.utils.log_handler import DatabaseLogHandler
        handler = DatabaseLogHandler()
        handler._batch_size = 1
        handler.set_console_log(False)
        monkeypatch.setattr(lh_state, '_global_db_handler', handler)
        try:
            log_not_emit('INFO', 'rollback_engine', 'rollback switch line',
                         category='execution', task_id=99, device_id=2)
            deadline = time.time() + 3
            while time.time() < deadline and not captured:
                time.sleep(0.05)
            assert captured, '回滚开关开启后业务日志未恢复入库'
            entry = captured[-1]
            assert entry['task_id'] == 99
            assert 'rollback switch line' in entry['content']
        finally:
            handler.queue.put(None)
            monkeypatch.setattr('shared.logging.config._SETTINGS', prev)

        # 双写：文件侧同样落盘
        svc = resolve_service_name()
        biz_file = logs_root / 'business' / '99' / '2' / 'shared' / f'execution.{svc}.{os.getpid()}.log'
        deadline = time.time() + 3
        while time.time() < deadline and not biz_file.exists():
            time.sleep(0.05)
        assert biz_file.exists(), '回滚开关开启后业务文件双写丢失'
        assert 'rollback switch line' in biz_file.read_text(encoding='utf-8')
