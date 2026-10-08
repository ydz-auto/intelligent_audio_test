# -*- coding: utf-8 -*-
"""任务数据导入导出 —— 补偿/进度/批次登记单测

涉及 Redis 的部分使用 fakeredis 不可用时跳过；纯逻辑部分直接验证。
"""
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.constants.data_transfer import (
    FkMappingKey,
    ImportProgressStep,
)


def _remaps_only(mapping):
    """与 task_service.application.task.data_transfer_import_service._remaps_only
    相同语义（只保留真正的重映射条目）——此处显式断言该语义契约"""
    from task_service.application.task.data_transfer_import_service import _remaps_only
    return _remaps_only(mapping)


class TestRemapsOnly:
    def test_identity_entries_dropped(self):
        assert _remaps_only({1: 1, 2: 202, 3: 3}) == {2: 202}

    def test_empty_mapping(self):
        assert _remaps_only({}) == {}
        assert _remaps_only(None) == {}


class TestProgressPercentage:
    """进度百分比阶段推进（Redis 不实际连接，只测纯计算）"""

    def _reporter(self):
        from task_service.application.task.import_progress_reporter import (
            ImportProgressReporter,
        )
        return ImportProgressReporter('batch-test')

    def test_phase_base_percentages(self):
        reporter = self._reporter()
        assert reporter._percentage(ImportProgressStep.PARSING) == 0
        assert reporter._percentage(ImportProgressStep.EXTRACTING_FILES) == 70
        assert reporter._percentage(ImportProgressStep.UPDATING_PATHS) == 90
        assert reporter._percentage(ImportProgressStep.DONE) == 100

    def test_writing_db_advances_with_rows(self):
        reporter = self._reporter()
        reporter.set_total_rows(200)
        reporter._processed_rows = 100
        pct = reporter._percentage(ImportProgressStep.WRITING_DB)
        # writing_db 基线 5%，至 extracting_files 基线 70%，走完一半 → 37.5
        assert pct == 37.5

    def test_zero_total_no_division_error(self):
        reporter = self._reporter()
        assert reporter._percentage(ImportProgressStep.WRITING_DB) == 5


class TestBatchRegistry:
    """批次登记（Redis HASH）；Redis 不可用时跳过"""

    def test_record_load_remove_roundtrip(self):
        pytest.importorskip('redis')
        try:
            from shared.utils.data_transfer_batch import TransferBatchRegistry
            from shared.utils.redis_pubsub import RedisStore
            RedisStore().redis_client.ping()
        except Exception:
            pytest.skip('Redis 未运行，跳过批次登记测试')

        import uuid
        registry = TransferBatchRegistry()
        batch_id = uuid.uuid4().hex
        try:
            registry.record(batch_id, 'task_service', {'test_tasks': [1, 2]})
            registry.record(batch_id, 'evaluation_service',
                            {'test_result_dimensions': [3]})
            assert registry.load_service(batch_id, 'task_service') == {'test_tasks': [1, 2]}
            assert registry.load_service(batch_id, 'evaluation_service') == \
                {'test_result_dimensions': [3]}
            registry.remove_service(batch_id, 'evaluation_service')
            assert registry.load_service(batch_id, 'evaluation_service') == {}
            assert registry.load_service(batch_id, 'task_service') == {'test_tasks': [1, 2]}
        finally:
            registry.delete(batch_id)
