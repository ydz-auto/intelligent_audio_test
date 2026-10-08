# -*- coding: utf-8 -*-
"""已发布任务 Benchmark 标记钩子测试（INT-26）。

测试 task_service.application.services.published_task_service：
- publish 携带 benchmark 标记持久化 + PUBLISHED_TASK_BENCHMARK_MARKED 审计事件落库
- publish 不带标记时不产生审计事件
- create_version 未显式指定时继承当前版本标记，显式指定时可覆盖
- get_list benchmark 三态筛选参数解析
- 网关 Schema benchmark 字段（camelCase/snake_case 兼容）

仓储与日志仓储以 fake 替身注入（不依赖 DB）。
"""
import json
import os

import pytest

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import AuditEvent

import task_service.application.services.published_task_service as pts_module
from task_service.application.services.published_task_service import (
    PublishedTaskService,
    published_task_service,
)
from task_service.infrastructure.persistence.published_task_repository import (
    parse_benchmark_filter,
)


def make_task(**overrides):
    """来源日常任务替身（Task PO 形状）。"""
    task = type('TaskPO', (), {})()
    task.id = 123
    task.deleted = False
    task.status = 'completed'
    task.type = 'e2e'
    task.config = {}
    task.algorithm_type = None
    task.algorithm_params = {}
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


def make_pt(**overrides):
    """已发布任务 PO 替身。"""
    pt = type('PublishedTaskPO', (), {})()
    pt.id = 1001
    pt.task_group_id = 1001
    pt.source_task_id = 123
    pt.name = '已发布任务'
    pt.description = None
    pt.type = 'e2e'
    pt.status = 'published'
    pt.benchmark = False
    pt.version = 1
    pt.is_current = True
    pt.snapshot_config = {'caseIds': [1], 'deviceIds': [], 'apiIds': [], 'tags': []}
    pt.published_by = None
    pt.published_at = None
    pt.archived_at = None
    pt.created_at = None
    for k, v in overrides.items():
        setattr(pt, k, v)
    return pt


class FakeRepo:
    """published_task_repository 替身：记录调用并返回预设对象。"""

    def __init__(self, source_task=None, current_pt=None):
        self.source_task = source_task or make_task()
        self.current_pt = current_pt or make_pt()
        self.create_kwargs = None
        self.create_version_kwargs = None
        self.get_list_kwargs = None

    # ---- publish 链路 ----
    def get_task(self, task_id):
        return self.source_task

    def get_task_case_ids(self, task_id):
        return [1, 2]

    def get_task_device_ids(self, task_id):
        return []

    def get_task_api_ids(self, task_id):
        return []

    def get_task_tag_names(self, task_id):
        return []

    def get_existing_case_ids(self, case_ids):
        return set(case_ids)

    def freeze_report_snapshot(self, source_task_id):
        return None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return make_pt(**{
            'id': 1001,
            'benchmark': kwargs.get('benchmark', False),
        })

    # ---- create_version 链路 ----
    def get_by_id(self, published_task_id):
        return self.current_pt

    def get_current_version(self, group_id):
        return self.current_pt

    def create_version(self, **kwargs):
        self.create_version_kwargs = kwargs
        return make_pt(**{
            'id': 1002,
            'version': kwargs.get('version', 2),
            'benchmark': kwargs.get('benchmark', False),
            'task_group_id': self.current_pt.task_group_id,
        })

    # ---- get_list 链路 ----
    def get_list(self, **kwargs):
        self.get_list_kwargs = kwargs
        return [], 0

    def get_version_counts(self, group_ids):
        return {}


class FakeLogRepo:
    """log_repository 替身：捕获审计写入。"""

    def __init__(self):
        self.batch = []

    def batch_create(self, logs):
        self.batch.extend(logs)
        return list(range(len(self.batch)))


@pytest.fixture
def env(monkeypatch):
    """注入 fake repo 与 fake log_repository，返回可断言的容器。"""
    fake_repo = FakeRepo()
    fake_log = FakeLogRepo()
    monkeypatch.setattr(pts_module, 'repo', fake_repo)
    monkeypatch.setattr(pts_module, 'log_repository', fake_log)
    return {'repo': fake_repo, 'log': fake_log}


class TestPublishBenchmark:
    """发布携带 benchmark 标记。"""

    def test_publish_with_benchmark_true_persists_and_audits(self, env):
        result = published_task_service.publish({
            'source_task_id': 123,
            'name': 'Benchmark 任务',
            'benchmark': True,
        })
        assert result['success'] is True
        assert env['repo'].create_kwargs['benchmark'] is True

        # 审计事件落库：事件名 + 任务标识
        assert len(env['log'].batch) == 1
        content = json.loads(env['log'].batch[0]['content'])
        assert content['event'] == AuditEvent.PUBLISHED_TASK_BENCHMARK_MARKED.value
        assert content['published_task_id'] == 1001
        assert content['version'] == 1
        assert content['source_task_id'] == 123
        assert content['result'] == 'success'

    def test_publish_without_benchmark_no_audit(self, env):
        result = published_task_service.publish({
            'source_task_id': 123,
            'name': '普通任务',
        })
        assert result['success'] is True
        assert env['repo'].create_kwargs['benchmark'] is False
        assert env['log'].batch == []

    def test_publish_benchmark_string_coerced(self, env):
        published_task_service.publish({
            'source_task_id': 123,
            'name': '字符串标记',
            'benchmark': 'true',
        })
        assert env['repo'].create_kwargs['benchmark'] is True

    def test_audit_write_failure_does_not_break_publish(self, env, monkeypatch):
        def broken_batch_create(logs):
            raise RuntimeError('db down')

        monkeypatch.setattr(env['log'], 'batch_create', broken_batch_create)
        result = published_task_service.publish({
            'source_task_id': 123,
            'name': '审计失败不阻断',
            'benchmark': True,
        })
        assert result['success'] is True
        assert env['repo'].create_kwargs['benchmark'] is True


class TestCreateVersionBenchmark:
    """新版本 benchmark 标记继承与覆盖。"""

    def test_version_inherits_benchmark_from_current(self, env):
        env['repo'].current_pt = make_pt(benchmark=True)
        result = published_task_service.create_version(1001, {})
        assert result['success'] is True
        assert env['repo'].create_version_kwargs['benchmark'] is True
        # 继承标记同样触发审计（新版本进入实测轨）
        assert len(env['log'].batch) == 1

    def test_version_inherits_false_when_unspecified(self, env):
        env['repo'].current_pt = make_pt(benchmark=False)
        result = published_task_service.create_version(1001, {})
        assert result['success'] is True
        assert env['repo'].create_version_kwargs['benchmark'] is False
        assert env['log'].batch == []

    def test_version_explicit_override_false(self, env):
        env['repo'].current_pt = make_pt(benchmark=True)
        result = published_task_service.create_version(1001, {'benchmark': False})
        assert result['success'] is True
        assert env['repo'].create_version_kwargs['benchmark'] is False
        assert env['log'].batch == []

    def test_version_explicit_override_true(self, env):
        env['repo'].current_pt = make_pt(benchmark=False)
        result = published_task_service.create_version(1001, {'benchmark': True})
        assert result['success'] is True
        assert env['repo'].create_version_kwargs['benchmark'] is True
        assert len(env['log'].batch) == 1


class TestListBenchmarkFilter:
    """列表 benchmark 筛选。"""

    @pytest.mark.parametrize('raw,expected', [
        ('true', True),
        ('True', True),
        ('1', True),
        ('false', False),
        ('False', False),
        ('0', False),
        ('', None),
        (None, None),
        ('invalid', None),
    ])
    def test_parse_benchmark_filter(self, raw, expected):
        assert parse_benchmark_filter(raw) is expected

    def test_get_list_passes_benchmark_through(self, env):
        published_task_service.get_list(benchmark='true')
        assert env['repo'].get_list_kwargs['benchmark'] == 'true'

    def test_get_list_without_benchmark(self, env):
        published_task_service.get_list()
        assert env['repo'].get_list_kwargs['benchmark'] is None


class TestItemContract:
    """列表项/详情契约携带 benchmark 字段。"""

    def test_item_dict_contains_benchmark(self):
        item = PublishedTaskService._item_dict(make_pt(benchmark=True))
        assert item['benchmark'] is True

    def test_item_dict_benchmark_default_false(self):
        pt = make_pt()
        pt.benchmark = None  # 历史行兜底
        item = PublishedTaskService._item_dict(pt)
        assert item['benchmark'] is False


class TestGatewaySchema:
    """网关 Schema benchmark 字段兼容性。"""

    def test_create_request_accepts_benchmark(self):
        from api_gateway.schemas.published_task import (
            PublishedTaskCreateRequest,
            PublishedTaskVersionCreateRequest,
        )
        req = PublishedTaskCreateRequest.model_validate({
            'sourceTaskId': 123,
            'name': 'Benchmark 任务',
            'publishReason': '基线',
            'benchmark': True,
        })
        dumped = req.model_dump(by_alias=False, exclude_none=True)
        assert dumped['benchmark'] is True

        req2 = PublishedTaskCreateRequest.model_validate({
            'source_task_id': 123,
            'name': '默认任务',
        })
        assert req2.model_dump(by_alias=False, exclude_none=True)['benchmark'] is False

        ver = PublishedTaskVersionCreateRequest.model_validate({'name': 'v2'})
        assert 'benchmark' not in ver.model_dump(by_alias=False, exclude_none=True)

        ver2 = PublishedTaskVersionCreateRequest.model_validate({'benchmark': True})
        assert ver2.model_dump(by_alias=False, exclude_none=True)['benchmark'] is True

    def test_item_schema_benchmark_field(self):
        from api_gateway.schemas.published_task import PublishedTaskItem
        item = PublishedTaskItem.model_validate({
            'id': 1, 'name': 'x', 'type': 'e2e', 'status': 'published',
            'version': 1, 'is_current': True, 'benchmark': True,
        })
        assert item.benchmark is True


class TestGatewayBenchmarkFilter:
    """网关 get_all benchmark 筛选参数解析与透传。"""

    class _FakeArgs:
        def __init__(self, params):
            self._params = params

        def to_dict(self):
            return dict(self._params)

    def _run(self, monkeypatch, params):
        import api_gateway.application.services.published_task.published_task_service as gw

        captured = {}

        class FakeACL:
            def get_list(self, **kwargs):
                captured.update(kwargs)
                return {'success': True, 'data': {'items': [], 'total': 0, 'page': 1,
                                                 'per_page': 10, 'pages': 0}}

        fake_request = type('R', (), {})()
        fake_request.args = self._FakeArgs(params)
        monkeypatch.setattr(gw, 'request', fake_request, raising=False)
        monkeypatch.setattr(gw, '_pt_acl', FakeACL())
        return gw.PublishedTaskService.get_all(), captured

    def test_benchmark_true_passed_to_acl(self, monkeypatch):
        _, captured = self._run(monkeypatch, {'benchmark': 'true'})
        assert captured['benchmark'] == 'true'

    def test_benchmark_absent_passes_empty(self, monkeypatch):
        _, captured = self._run(monkeypatch, {})
        assert captured['benchmark'] == ''

    def test_benchmark_invalid_rejected(self, monkeypatch):
        result, _ = self._run(monkeypatch, {'benchmark': 'maybe'})
        # 网关内部错误契约：(payload, http_code) 元组，路由层 to_response 转换
        payload, http_code = result
        assert http_code == 400
        assert payload['success'] is False
        assert payload['code'] == 100


class TestBenchmarkSnapshotFields:
    """D1 衔接：发布/新版本携带 benchmarkSuite/benchmarkCategory 进快照（INT-27）。"""

    def test_publish_writes_suite_and_category_into_snapshot(self, env):
        published_task_service.publish({
            'sourceTaskId': 123, 'name': '基准', 'benchmark': True,
            'benchmarkSuite': 'librispeech-v1', 'benchmarkCategory': 'asr',
        })
        snapshot = env['repo'].create_kwargs['snapshot_config']
        assert snapshot['benchmarkSuite'] == 'librispeech-v1'
        assert snapshot['benchmarkCategory'] == 'asr'
        # 快照其余结构不受影响
        assert snapshot['caseIds'] == [1, 2]

    def test_publish_without_fields_keeps_snapshot_clean(self, env):
        published_task_service.publish({'sourceTaskId': 123, 'name': '基准'})
        snapshot = env['repo'].create_kwargs['snapshot_config']
        assert 'benchmarkSuite' not in snapshot
        assert 'benchmarkCategory' not in snapshot

    def test_version_inherits_fields_from_current_snapshot(self, env, monkeypatch):
        repo = FakeRepo(current_pt=make_pt(snapshot_config={
            'caseIds': [1], 'benchmarkSuite': 'librispeech-v1', 'benchmarkCategory': 'asr'}))
        monkeypatch.setattr(pts_module, 'repo', repo)
        published_task_service.create_version(1001, {'name': '升级'})
        snapshot = repo.create_version_kwargs['snapshot_config']
        # 请求未显式指定 → 继承当前版本快照（版本链语义延续）
        assert snapshot['benchmarkSuite'] == 'librispeech-v1'
        assert snapshot['benchmarkCategory'] == 'asr'

    def test_version_explicit_override(self, env, monkeypatch):
        repo = FakeRepo(current_pt=make_pt(snapshot_config={
            'caseIds': [1], 'benchmarkSuite': 'old-v1', 'benchmarkCategory': 'asr'}))
        monkeypatch.setattr(pts_module, 'repo', repo)
        published_task_service.create_version(1001, {
            'benchmarkSuite': 'full-duplex-v2', 'benchmarkCategory': 'voice_llm'})
        snapshot = repo.create_version_kwargs['snapshot_config']
        assert snapshot['benchmarkSuite'] == 'full-duplex-v2'
        assert snapshot['benchmarkCategory'] == 'voice_llm'
