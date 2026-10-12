# -*- coding: utf-8 -*-
"""INT-148 缺陷#3 回归：已发布任务列表 type/algorithm_type 筛选端到端补齐。

原缺陷：V9.7.10 published_tasks 冻结 type（api/e2e）与 algorithm_type 冗余列，
列表按二者筛选；V9.7.31 前后端均无（benchmark 筛选为新增能力）。

修复语义（本文件覆盖）：
- 发布时由快照用例级 device_type 派生 type（任一 http_api/websocket_api →
  api，否则 e2e；无 caseDevices 的历史快照回退 apiIds），algorithm_type 取
  快照 algorithmType 冻结；
- create_version：指定新来源任务时重新派生，否则沿用当前版本（对齐 V9.7.10）；
- get_list / 仓储过滤 / _item_dict 契约 / 网关参数解析与 Schema 全链路；
- 迁移脚本派生规则与发布链路一致。

隔离方式：服务层用 fake repo 替身注入（同 test_published_task_benchmark）；
仓储过滤用独立 sqlite 内存库建 published_tasks 表；网关用 fake ACL。
"""
import json
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import task_service.application.services.published_task_service as pts_module
from task_service.application.services.published_task_service import (
    PublishedTaskService,
    published_task_service,
)
import task_service.infrastructure.persistence.published_task_repository as ptr_module
from task_service.infrastructure.persistence.models import PublishedTask


def make_task(**overrides):
    task = type('TaskPO', (), {})()
    task.id = 123
    task.deleted = False
    task.status = 'completed'
    task.config = {}
    task.algorithm_type = 'translation'
    task.algorithm_params = {}
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


def make_pt(**overrides):
    pt = type('PublishedTaskPO', (), {})()
    pt.id = 1001
    pt.task_group_id = 1001
    pt.source_task_id = 123
    pt.name = '已发布任务'
    pt.description = None
    pt.type = 'e2e'
    pt.algorithm_type = 'translation'
    pt.status = 'published'
    pt.benchmark = False
    pt.version = 1
    pt.is_current = True
    pt.snapshot_config = {'caseIds': [1], 'deviceIds': [], 'apiIds': [], 'tags': []}
    pt.published_by = None
    pt.published_at = None
    pt.archived_by = None
    pt.archived_at = None
    pt.created_at = None
    for k, v in overrides.items():
        setattr(pt, k, v)
    return pt


class FakeRepo:
    """published_task_repository 替身：记录调用并返回预设对象。"""

    def __init__(self, source_task=None, current_pt=None, case_devices=None):
        self.source_task = source_task or make_task()
        self.current_pt = current_pt or make_pt()
        self.case_devices = case_devices if case_devices is not None else []
        self.create_kwargs = None
        self.create_version_kwargs = None
        self.get_list_kwargs = None

    def get_task(self, task_id):
        return self.source_task

    def get_task_case_devices(self, task_id):
        return self.case_devices

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
            'type': kwargs.get('task_type'),
            'algorithm_type': kwargs.get('algorithm_type'),
            'benchmark': kwargs.get('benchmark', False),
        })

    def get_by_id(self, published_task_id):
        return self.current_pt

    def get_current_version(self, group_id):
        return self.current_pt

    def create_version(self, **kwargs):
        self.create_version_kwargs = kwargs
        return make_pt(**{
            'id': 1002,
            'version': kwargs.get('version', 2),
            'type': kwargs.get('task_type'),
            'algorithm_type': kwargs.get('algorithm_type'),
            'benchmark': kwargs.get('benchmark', False),
            'task_group_id': self.current_pt.task_group_id,
        })

    def get_list(self, **kwargs):
        self.get_list_kwargs = kwargs
        return [], 0

    def get_version_counts(self, group_ids):
        return {}

    def archive(self, published_task_id, archived_by=None):
        self.current_pt.status = 'archived'
        return self.current_pt


class FakeLogRepo:
    def __init__(self):
        self.batch = []

    def batch_create(self, logs):
        self.batch.extend(logs)
        return list(range(len(self.batch)))


@pytest.fixture
def env(monkeypatch):
    fake_repo = FakeRepo()
    fake_log = FakeLogRepo()
    monkeypatch.setattr(pts_module, 'repo', fake_repo)
    monkeypatch.setattr(pts_module, 'log_repository', fake_log)
    return {'repo': fake_repo, 'log': fake_log}


class TestPublishDerivesTypeAndAlgorithmType:
    """发布：由快照用例级 device_type 派生 type，冻结 algorithm_type。"""

    def test_any_api_case_derives_api_type(self, monkeypatch):
        repo = FakeRepo(case_devices=[
            {'case_id': 'c1', 'device_type': 'physical', 'device_id': '3', 'lab_id': None},
            {'case_id': 'c2', 'device_type': 'http_api', 'device_id': '7', 'lab_id': None},
        ])
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        result = published_task_service.publish({'source_task_id': 123, 'name': 'API 任务'})

        assert result['success'] is True
        assert repo.create_kwargs['task_type'] == 'api'
        assert repo.create_kwargs['algorithm_type'] == 'translation'

    def test_all_physical_cases_derive_e2e_type(self, monkeypatch):
        repo = FakeRepo(case_devices=[
            {'case_id': 'c1', 'device_type': 'physical', 'device_id': '3', 'lab_id': None},
        ])
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        published_task_service.publish({'source_task_id': 123, 'name': 'E2E 任务'})

        assert repo.create_kwargs['task_type'] == 'e2e'

    def test_legacy_snapshot_without_case_devices_falls_back_to_api_ids(self, monkeypatch):
        """历史快照无 caseDevices：apiIds 非空 → api（与迁移回填规则一致）。"""
        repo = FakeRepo(case_devices=[])
        repo.get_task_api_ids = lambda task_id: [7]
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        published_task_service.publish({'source_task_id': 123, 'name': '历史快照'})

        assert repo.create_kwargs['task_type'] == 'api'

    def test_algorithm_type_frozen_from_snapshot(self, monkeypatch):
        repo = FakeRepo(case_devices=[])
        repo.source_task = make_task(algorithm_type='asr')
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        published_task_service.publish({'source_task_id': 123, 'name': 'ASR 任务'})

        assert repo.create_kwargs['algorithm_type'] == 'asr'


class TestCreateVersionTypeSemantics:
    """新版本：指定新来源任务重新派生，否则沿用当前版本。"""

    def test_version_without_source_inherits_current_type(self, monkeypatch):
        repo = FakeRepo(current_pt=make_pt(
            type='api',
            snapshot_config={'caseIds': [1], 'deviceIds': [], 'apiIds': [],
                             'tags': [], 'algorithmType': 'asr'}))
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        result = published_task_service.create_version(1001, {'name': 'v2'})

        assert result['success'] is True
        assert repo.create_version_kwargs['task_type'] == 'api'
        # 算法类型沿用当前版本快照冻结值
        assert repo.create_version_kwargs['algorithm_type'] == 'asr'

    def test_version_with_new_source_rederives_type(self, monkeypatch):
        repo = FakeRepo(
            current_pt=make_pt(type='e2e', algorithm_type='asr'),
            case_devices=[{'case_id': 'c1', 'device_type': 'websocket_api',
                           'device_id': '9', 'lab_id': None}])
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepo())

        published_task_service.create_version(1001, {'source_task_id': 555})

        assert repo.create_version_kwargs['task_type'] == 'api'


class TestItemContract:
    """列表项契约携带 type / algorithm_type。"""

    def test_item_dict_contains_type_fields(self):
        item = PublishedTaskService._item_dict(make_pt(type='api', algorithm_type='tts'))
        assert item['type'] == 'api'
        assert item['algorithm_type'] == 'tts'

    def test_item_dict_tolerates_legacy_po_without_columns(self):
        pt = make_pt()
        del pt.type
        del pt.algorithm_type
        item = PublishedTaskService._item_dict(pt)
        assert item['type'] is None
        assert item['algorithm_type'] is None


class TestGetListPassThrough:
    """get_list 筛选参数透传仓储。"""

    def test_type_and_algorithm_type_passed(self, env):
        published_task_service.get_list(task_type='api', algorithm_type='asr')
        assert env['repo'].get_list_kwargs['task_type'] == 'api'
        assert env['repo'].get_list_kwargs['algorithm_type'] == 'asr'

    def test_empty_by_default(self, env):
        published_task_service.get_list()
        assert env['repo'].get_list_kwargs['task_type'] == ''
        assert env['repo'].get_list_kwargs['algorithm_type'] == ''


class TestRepositoryFilter:
    """仓储 get_list 过滤（sqlite 真库）。"""

    def _build_session(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool)
        from shared.models.database import Base
        Base.metadata.create_all(bind=engine, tables=[PublishedTask.__table__])
        factory = sessionmaker(bind=engine)
        monkeypatch.setattr(ptr_module, 'get_db_session', factory)
        return factory

    def _seed(self, factory):
        repo = ptr_module.published_task_repository
        repo.create(name='API 任务', task_type='api', algorithm_type='asr')
        repo.create(name='E2E 任务', task_type='e2e', algorithm_type='translation')

    def test_filter_by_task_type(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        self._seed(factory)
        repo = ptr_module.published_task_repository

        rows, total = repo.get_list(task_type='api')

        assert total == 1
        assert rows[0].name == 'API 任务'
        assert rows[0].type == 'api'

    def test_filter_by_algorithm_type(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        self._seed(factory)
        repo = ptr_module.published_task_repository

        rows, total = repo.get_list(algorithm_type='translation')

        assert total == 1
        assert rows[0].name == 'E2E 任务'

    def test_all_means_no_filter(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        self._seed(factory)
        repo = ptr_module.published_task_repository

        _, total = repo.get_list(task_type='all', algorithm_type='all')

        assert total == 2


class TestGatewayContract:
    """网关 Schema 与筛选参数解析。"""

    def test_item_schema_type_fields(self):
        from api_gateway.schemas.published_task import PublishedTaskItem
        item = PublishedTaskItem.model_validate({
            'id': 1, 'name': 'x', 'type': 'api', 'algorithm_type': 'asr',
            'status': 'published', 'version': 1, 'is_current': True,
        })
        assert item.type == 'api'
        assert item.algorithm_type == 'asr'
        dumped = item.model_dump(by_alias=False)
        assert dumped['type'] == 'api'
        assert dumped['algorithm_type'] == 'asr'

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

    def test_type_and_algorithm_type_passed_to_acl(self, monkeypatch):
        _, captured = self._run(monkeypatch, {'type': 'api', 'algorithm_type': 'asr'})
        assert captured['task_type'] == 'api'
        assert captured['algorithm_type'] == 'asr'

    def test_algorithm_type_camel_case_accepted(self, monkeypatch):
        _, captured = self._run(monkeypatch, {'algorithmType': 'tts'})
        assert captured['algorithm_type'] == 'tts'

    def test_invalid_type_rejected(self, monkeypatch):
        result, _ = self._run(monkeypatch, {'type': 'whatever'})
        payload, http_code = result
        assert http_code == 400
        assert payload['success'] is False

    def test_all_type_accepted(self, monkeypatch):
        _, captured = self._run(monkeypatch, {'type': 'all'})
        assert captured['task_type'] == 'all'


class TestMigrationDeriveRule:
    """迁移脚本派生规则与发布链路一致（纯函数）。"""

    def test_rule_consistency(self):
        import importlib.util
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            'scripts', 'migrations', '202610', 'add_published_task_type_algorithm_type.py')
        spec = importlib.util.spec_from_file_location('_pt_type_migration', script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.derive_task_type({'caseDevices': [
            {'device_type': 'physical'}]}) == 'e2e'
        assert module.derive_task_type({'caseDevices': [
            {'device_type': 'physical'}, {'device_type': 'websocket_api'}]}) == 'api'
        assert module.derive_task_type({'apiIds': [7]}) == 'api'
        assert module.derive_task_type({}) == 'e2e'
        assert module.derive_task_type(None) == 'e2e'
