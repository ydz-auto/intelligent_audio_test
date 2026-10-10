# -*- coding: utf-8 -*-
"""INT-81 日志体系改造单元测试。

覆盖：
- 业务日志路径模板（task/device/api/round/evaluation 段解析与清洗、切分序号）
- 业务日志 JSONL 写入（路径落位、超限切分 -NNN、句柄上限）
- 业务日志读取（设备/轮次/类型/级别/关键词过滤、排序、分页）
- 服务运行日志双条件轮转（同日多次超限 -NNN 命名、跨天轮转）
- 保留清扫（过期文件删除、空目录回收）

gRPC/DB 边界不触达（本文件不涉及 emit 分流，分流见 test_log_handler_audit_emit.py）。
"""
import logging
import os
import time

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'), 'int81_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.logging import (
    BusinessLogFileWriter,
    BusinessLogPathBuilder,
    BusinessLogReader,
    BusinessLogType,
    LogSettings,
    reset_log_settings,
    sweep_expired_files,
)
from shared.logging.config import get_log_settings
from shared.logging.service_handler import ServiceRotatingFileHandler
from shared.logging.enums import LogEnvironment


def _make_settings(root, *, business_max_bytes=50 * 1024 * 1024, retention_days=30):
    return LogSettings(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=retention_days,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=business_max_bytes,
        business_retention_days=retention_days,
    )


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    """独立日志根目录 + 配置快照隔离。"""
    root = str(tmp_path / 'logs')
    settings = _make_settings(root)
    monkeypatch.setattr('shared.logging.config._SETTINGS', settings)
    yield root
    reset_log_settings()


# ---------- 路径模板 ----------

class TestPathBuilder:

    def setup_method(self):
        self.builder = BusinessLogPathBuilder()

    def test_device_round_path(self):
        path = self.builder.build_rel_path(
            task_id=101, log_type=BusinessLogType.EXECUTION,
            service_name='e2e_test_service', device_id=7, round_value=2)
        normalized = path.replace(os.sep, '/')
        assert normalized == 'business/101/7/2/execution.e2e_test_service.log'

    def test_api_path_fallback_shared_scope(self):
        path = self.builder.build_rel_path(
            task_id=5, log_type=BusinessLogType.EXECUTION,
            service_name='api_test_service', api_id=33)
        normalized = path.replace(os.sep, '/')
        assert normalized == 'business/5/33/shared/execution.api_test_service.log'

    def test_common_segment_when_no_device_no_api(self):
        path = self.builder.build_rel_path(
            task_id=9, log_type=BusinessLogType.EVALUATION, service_name='evaluation_service')
        normalized = path.replace(os.sep, '/')
        assert normalized == 'business/9/common/shared/evaluation.evaluation_service.log'

    def test_evaluation_id_precedes_round(self):
        path = self.builder.build_rel_path(
            task_id=9, log_type=BusinessLogType.EVALUATION, service_name='s',
            device_id=1, evaluation_id=77, round_value=2)
        normalized = path.replace(os.sep, '/')
        assert normalized == 'business/9/1/77/evaluation.s.log'

    def test_sanitize_rejects_traversal(self):
        assert self.builder.sanitize_segment('../../etc') != '../../etc'
        assert '..' not in self.builder.sanitize_segment('..')
        assert self.builder.sanitize_segment('a/b') == 'a_b'

    def test_requires_task_id(self):
        with pytest.raises(ValueError):
            self.builder.build_rel_path(task_id=None, log_type=BusinessLogType.DEVICE,
                                        service_name='s')

    def test_split_index_parsing(self):
        assert self.builder.split_index_of('execution.s-001.log') == 1
        assert self.builder.split_index_of('execution.s-012.log') == 12
        assert self.builder.split_index_of('execution.s.log') == 0


# ---------- 业务日志写入 ----------

class TestBusinessWriter:

    def _entry(self, **overrides):
        entry = {
            'time': '2026-10-10T12:00:00+08:00',
            'level': 'INFO',
            'category': 'execution',
            'module': 'Engine',
            'source': 'backend',
            'content': 'round line',
            'task_id': 101,
            'device_id': 7,
            'api_id': None,
            'test_case_id': 'TC-1',
            'thread_id': 't1',
            'algorithm_type': None,
            'round': 2,
            'evaluation_id': None,
        }
        entry.update(overrides)
        return entry

    def test_write_lands_at_expected_path(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root), service_name='e2e_test_service')
        rel = writer.write(self._entry())
        assert rel.replace(os.sep, '/') == 'business/101/7/2/execution.e2e_test_service.log'
        import json
        line = json.loads(open(os.path.join(log_root, rel), 'rb').read().decode('utf-8'))
        assert line['task_id'] == 101 and line['round'] == 2
        assert line['service'] == 'e2e_test_service'
        assert line['log_type'] == 'execution'

    def test_oversize_split_with_sequential_suffix(self, log_root):
        writer = BusinessLogFileWriter(
            settings=_make_settings(log_root, business_max_bytes=200),
            service_name='svc')
        total_lines = 6
        for i in range(total_lines):
            writer.write(self._entry(content=f'line {i} with some padding text here'))
        base = os.path.join(log_root, 'business', '101', '7', '2')
        names = sorted(os.listdir(base))
        # 超限切分：-NNN 序号文件，序号从 001 递增；活跃文件可能存在（末条未触发切分时）
        assert any(name.endswith('-001.log') for name in names)
        assert not any(name.endswith('-000.log') for name in names)
        assert all(name.startswith('execution.svc') for name in names)
        # 内容零丢失：切分文件行数总和等于写入条数
        written_lines = 0
        for name in names:
            with open(os.path.join(base, name), 'rb') as handle:
                written_lines += len([ln for ln in handle.read().decode('utf-8').splitlines() if ln.strip()])
        assert written_lines == total_lines

    def test_no_task_id_skipped(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root), service_name='svc')
        assert writer.write(self._entry(task_id=None)) is None

    def test_disabled_by_settings(self, log_root):
        settings = _make_settings(log_root)
        disabled = LogSettings(
            root_dir=settings.root_dir, environment=settings.environment,
            service_max_bytes=settings.service_max_bytes,
            service_retention_days=settings.service_retention_days,
            business_enabled=False, business_db_enabled=False,
            business_max_bytes=settings.business_max_bytes,
            business_retention_days=settings.business_retention_days,
        )
        writer = BusinessLogFileWriter(settings=disabled, service_name='svc')
        assert writer.write(self._entry()) is None

    def test_category_maps_to_log_type(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root), service_name='svc')
        writer.write(self._entry(category='evaluation'))
        rel = writer.write(self._entry(category='audio', content='device line'))
        assert rel.replace(os.sep, '/').endswith('device.svc.log')
        eval_file = os.path.join(log_root, 'business', '101', '7', '2', 'evaluation.svc.log')
        assert os.path.exists(eval_file)

    def test_prod_env_drops_debug_entries(self, log_root, monkeypatch):
        """dev/prod 环境区分：prod 下 DEBUG 级业务日志不落文件。"""
        from shared.utils.log_handler import log_and_emit
        import shared.utils.log_handler._state as lh_state
        settings = LogSettings(
            root_dir=log_root, environment=LogEnvironment.PROD,
            service_max_bytes=50 * 1024 * 1024, service_retention_days=30,
            business_enabled=True, business_db_enabled=False,
            business_max_bytes=50 * 1024 * 1024, business_retention_days=30,
        )
        monkeypatch.setattr('shared.logging.config._SETTINGS', settings)

        prev = lh_state._global_db_handler
        if prev is not None:
            prev.queue.put(None)
            if getattr(prev, 'worker_thread', None):
                prev.worker_thread.join(timeout=2.0)
        import shared.clients.grpc_clients as grpc_clients_mod
        monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', lambda payload: [1] * len(payload))
        monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
        monkeypatch.setattr(grpc_clients_mod, 'archive_logs',
                            lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
        import shared.clients.oss_client as oss_client_mod
        monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
        from shared.utils.log_handler import DatabaseLogHandler
        handler = DatabaseLogHandler()
        handler._batch_size = 1
        handler.set_console_log(False)
        monkeypatch.setattr(lh_state, '_global_db_handler', handler)
        try:
            log_and_emit('DEBUG', 'Engine', 'debug line prod', category='execution',
                         task_id=701, device_id=1, round=1)
            log_and_emit('INFO', 'Engine', 'info line prod', category='execution',
                         task_id=701, device_id=1, round=1)
            from shared.logging import resolve_service_name
            deadline = time.time() + 3
            biz_file = os.path.join(log_root, 'business', '701', '1', '1',
                                    f'execution.{resolve_service_name()}.log')
            while time.time() < deadline and not os.path.exists(biz_file):
                time.sleep(0.05)
            assert os.path.exists(biz_file), 'INFO 日志未落文件'
            content = open(biz_file, encoding='utf-8').read()
            assert 'info line prod' in content
            assert 'debug line prod' not in content, 'prod 环境不应落 DEBUG 业务日志'
        finally:
            handler.queue.put(None)


# ---------- 业务日志读取 ----------

class TestBusinessReader:

    def _seed(self, log_root):
        writer = BusinessLogFileWriter(settings=_make_settings(log_root), service_name='svc')
        rows = [
            dict(task_id=101, device_id=7, round=2, category='execution', content='e2e r2',
                 level='INFO', time='2026-10-10T12:00:01+08:00'),
            dict(task_id=101, device_id=7, round=2, category='evaluation', content='eval r2',
                 level='ERROR', time='2026-10-10T12:00:02+08:00'),
            dict(task_id=101, device_id=8, round=1, category='device', content='dev r1',
                 level='WARNING', time='2026-10-10T12:00:03+08:00'),
            dict(task_id=202, api_id=33, round=None, category='execution', content='api case',
                 level='INFO', time='2026-10-10T12:00:04+08:00'),
        ]
        for row in rows:
            writer.write(row)
        return rows

    def test_read_by_task_scoped_round(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=101, round_value=2)
        assert len(items) == 2
        # 时间倒序
        assert items[0]['content'] == 'eval r2'
        assert items[1]['content'] == 'e2e r2'
        assert items[0]['level'] == 'ERROR'

    def test_read_by_device_filter(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=101, device_id=8)
        assert len(items) == 1
        assert items[0]['content'] == 'dev r1'
        assert items[0]['log_type'] == 'device'

    def test_read_by_log_type(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        items = reader.read_entries(task_id=101, log_type=BusinessLogType.EVALUATION)
        assert len(items) == 1
        assert items[0]['content'] == 'eval r2'

    def test_level_and_keyword_filters(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        assert len(reader.read_entries(task_id=101, level='ERROR')) == 1
        assert len(reader.read_entries(task_id=101, level='INFO,ERROR')) == 2
        assert len(reader.read_entries(task_id=101, keyword='eval')) == 1
        assert reader.read_entries(task_id=101, keyword='nomatch') == []

    def test_pagination(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        page = reader.read_page(task_id=101, page=1, per_page=2)
        assert page['total'] == 3
        assert len(page['items']) == 2
        page2 = reader.read_page(task_id=101, page=2, per_page=2)
        assert len(page2['items']) == 1

    def test_task_isolation(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        assert len(reader.read_entries(task_id=202)) == 1
        assert reader.read_entries(task_id=999) == []

    def test_load_file_bytes_for_download(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        files = reader.load_file_bytes(task_id=101, device_id=7)
        rels = sorted(rel for rel, _ in files)
        # 设备 7 只有轮次 2 的执行/评估日志（设备 8 的设备日志不在此范围）
        assert rels == ['7/2/evaluation.svc.log', '7/2/execution.svc.log']
        for _rel, content in files:
            assert b'task_id' in content

    def test_stable_ids_across_reads(self, log_root):
        self._seed(log_root)
        reader = BusinessLogReader(root_dir=log_root)
        first = reader.read_entries(task_id=101)
        second = reader.read_entries(task_id=101)
        assert [item['id'] for item in first] == [item['id'] for item in second]


# ---------- 服务运行日志双条件轮转 ----------

class TestServiceRotation:

    def test_writes_to_service_dir(self, tmp_path, log_root):
        handler = ServiceRotatingFileHandler(str(tmp_path / 'svc_logs'), max_bytes=10 * 1024 * 1024)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger = logging.getLogger('int81_rotation_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info('hello service log')
        finally:
            logger.removeHandler(handler)
            handler.close()
        log_file = tmp_path / 'svc_logs' / 'app.log'
        assert log_file.exists()
        assert 'hello service log' in log_file.read_text(encoding='utf-8')

    def test_size_rollover_names_with_day_and_seq(self, tmp_path, log_root):
        handler = ServiceRotatingFileHandler(str(tmp_path / 'svc_logs'), max_bytes=50)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger = logging.getLogger('int81_size_test')
        logger.propagate = False
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            for i in range(20):
                logger.info(f'line {i:02d} padding padding padding')
        finally:
            logger.removeHandler(handler)
            handler.close()
        names = os.listdir(tmp_path / 'svc_logs')
        rotated = [n for n in names if n != 'app.log']
        # 轮转名带日期与序号：app-YYYYMMDD-001.log
        assert rotated, 'size rollover 未产生轮转文件'
        assert all(n.startswith('app-') and n.endswith('.log') for n in rotated)
        assert any('-001.log' in n for n in rotated)
        # 活跃文件已重建
        assert (tmp_path / 'svc_logs' / 'app.log').exists()


# ---------- 保留清扫 ----------

class TestRetention:

    def test_expired_files_removed(self, tmp_path, log_root):
        old_dir = tmp_path / 'keep' / 'business' / '9' / '1' / '1'
        old_dir.mkdir(parents=True)
        old_file = old_dir / 'execution.svc.log'
        old_file.write_text('old', encoding='utf-8')
        aged = time.time() - 40 * 86400
        os.utime(old_file, (aged, aged))

        new_dir = tmp_path / 'keep' / 'business' / '10' / '1' / '1'
        new_dir.mkdir(parents=True)
        new_file = new_dir / 'execution.svc.log'
        new_file.write_text('new', encoding='utf-8')

        deleted = sweep_expired_files(str(tmp_path / 'keep'), retention_days=30)
        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()
        # 空目录回收
        assert not old_dir.exists()

    def test_non_log_files_untouched(self, tmp_path, log_root):
        keep_dir = tmp_path / 'keep2'
        keep_dir.mkdir()
        data_file = keep_dir / 'result.json'
        data_file.write_text('{}', encoding='utf-8')
        aged = time.time() - 400 * 86400
        os.utime(data_file, (aged, aged))
        sweep_expired_files(str(keep_dir), retention_days=30)
        assert data_file.exists()
