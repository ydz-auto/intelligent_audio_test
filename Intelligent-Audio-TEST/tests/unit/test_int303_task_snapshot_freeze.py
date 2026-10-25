# -*- coding: utf-8 -*-
"""INT-303 回归：已发布版本任务详情真冻结（taskSnapshot 内联）。

原缺陷：published_tasks.snapshot_config 实测只存 {"caseIds": [...]} 引用列表
——指向源任务的用例 ID，源用例被编辑/删除后，已发布版本的"任务详情"随之
失真/失效；与 INT-179/258（报告真冻结）同一裁定：任务详情也要真冻结。

修复语义（本文件覆盖）：
- freeze_task_snapshot：任务详情全量数据冻结体（schemaVersion=2）——任务基本
  信息 + 用例完整配置深拷贝（rounds/音频引用/标签/分组/评价维度/算法参数/
  参考参数内容内联）+ 设备/API/播放设备引用快照（含名称）；
- _build_snapshot：发布快照携带 taskSnapshot；
- execute：taskSnapshot 存在时按冻结数据还原用例（影子用例 + 路由重映射），
  源用例被删后仍可执行；存量快照回退引用轨；
- create_version：指定新来源任务时重新冻结；未指定时深拷贝沿用当前版本
  冻结体（版本链语义延续）；
- get_detail：has_task_snapshot 标记（存量 → 历史版本标注）。

隔离方式：freeze/restore 用独立 sqlite 内存库建 task_service 段表 +
monkeypatch get_db_session（同 test_int258 惯例）；service 层用 fake repo 替身。
"""
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json as _json

import pytest

import task_service.infrastructure.persistence.published_task_repository as ptr_module
from task_service.application.services.published_task_service import (
    PublishedTaskService,
)
from task_service.infrastructure.persistence.models import (
    Task, TaskCase, TaskDevice, TaskAPI, TaskTag, Tag, PublishedTask,
)
from task_service.infrastructure.persistence.models.testcase_models import (
    TagCategory, TestCase, TestCaseGroup, TestCaseTag,
)


def _build_session_factory(monkeypatch, tables):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from shared.models.database import Base

    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=tables)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(ptr_module, 'get_db_session', factory)
    return factory


def _case_tables():
    return [Task.__table__, TaskCase.__table__, TaskDevice.__table__,
            TaskAPI.__table__, TaskTag.__table__, Tag.__table__,
            PublishedTask.__table__,
            TagCategory.__table__, TestCase.__table__,
            TestCaseGroup.__table__, TestCaseTag.__table__]


def _seed_task_with_cases(factory, *, case_config=None, audio=None):
    """写入源任务 + 用例（rounds 配置 / 标签 / 分组），返回 (task_id, case_id)。

    JSON 列直接传 Python 对象（与生产 psycopg2 序列化口径一致）。
    """
    session = factory()
    group = TestCaseGroup(id='grp-int303', name='INT303分组', algorithm_type='asr')
    session.add(group)
    category = TagCategory(id=1, name='场景')
    session.add(category)
    tag = Tag(id=7, name='回归标签', category_id=1)
    session.add(tag)
    session.flush()

    config = case_config if case_config is not None else {
        'rounds': [
            {
                'round_number': 1,
                'audios': audio if audio is not None else [
                    {'audio_id': 88, 'spl': 80, 'play_order': 1,
                     'playback_device_id': 5},
                ],
                'evaluation': {'dimensions': [{'id': 3, 'name': 'WER'}]},
            },
        ],
    }
    case = TestCase(
        id='tc-int303-a', name='登录用例', description='源用例描述',
        config=config, algorithm_type='asr',
        algorithm_params=[{'round_number': 1, 'params': [{'field_code': 'lang', 'field_value': 'zh'}]}],
        reference_params=[{'round_number': 1, 'reference_params_path': 'local://ref_params/tc-int303-a/round_1.json'}],
        group_id='grp-int303',
    )
    session.add(case)
    session.flush()
    session.add(TestCaseTag(id=1, test_case_id='tc-int303-a', tag_id=7))
    task = Task(id=123, name='INT303源任务', description='源任务说明',
                status='completed', total_cases=1)
    session.add(task)
    session.flush()
    session.add(TaskCase(task_id=123, test_case_id='tc-int303-a',
                         device_type='physical', device_id='9', lab_id=2))
    session.add(TaskDevice(task_id=123, device_id=11))
    session.add(TaskAPI(task_id=123, api_id=13))
    session.add(TaskTag(id=1, task_id=123, tag_id=7))
    session.commit()
    session.close()
    return 123, 'tc-int303-a'


# ---------------------------------------------------------------------------
# freeze_task_snapshot：任务详情全量冻结
# ---------------------------------------------------------------------------

def _patch_name_acls(monkeypatch):
    """隔离跨服务名称解析（单测环境无服务依赖；本机 gRPC 可能连通真实栈）。

    - 设备：device_acl_repository.get_device_statuses
    - API：api_test_acl_repository.fetch_api_names
    - 播放设备：shared.clients.grpc_clients.get_playback_config_service_stub
    """
    import task_service.infrastructure.acl.device_acl_repository as dev_mod
    import task_service.infrastructure.acl.report_acl_repository as api_mod

    monkeypatch.setattr(
        dev_mod.device_acl_repository, 'get_device_statuses',
        lambda ids: [{'id': i, 'name': f'设备{i}', 'status': 'idle'} for i in (ids or [])])
    monkeypatch.setattr(
        api_mod.api_test_acl_repository, 'fetch_api_names',
        lambda ids: {i: f'API{i}' for i in (ids or [])})

    class _FakePlaybackStub:
        def GetPlaybackDevice(self, request, context=None, timeout=None):
            item = {'id': request.device_id, 'name': f'播放设备{request.device_id}'}
            return type('Resp', (), {
                'success': True, 'data': _json.dumps(item), 'message': 'ok'})()

    import shared.clients.grpc_clients as grpc_clients_mod
    monkeypatch.setattr(
        grpc_clients_mod, 'get_playback_config_service_stub', lambda: _FakePlaybackStub())


class TestFreezeTaskSnapshot:
    """freeze_task_snapshot：任务详情真冻结（引用 + 内容内联）。"""

    def test_freeze_full_structure(self, monkeypatch):
        factory = _build_session_factory(monkeypatch, _case_tables())
        _patch_name_acls(monkeypatch)
        _seed_task_with_cases(factory)
        task = factory().get(Task, 123)

        frozen = ptr_module.published_task_repository.freeze_task_snapshot(task)

        assert frozen['schemaVersion'] == 2
        # 任务基本信息冻结
        assert frozen['task']['name'] == 'INT303源任务'
        assert frozen['task']['description'] == '源任务说明'
        assert frozen['task']['tags'] == ['回归标签']
        # 用例完整配置深拷贝
        assert len(frozen['cases']) == 1
        case = frozen['cases'][0]
        assert case['caseId'] == 'tc-int303-a'
        assert case['name'] == '登录用例'
        assert case['config']['rounds'][0]['round_number'] == 1
        # 音频引用（含播放设备）随 config 内联
        audio_item = case['config']['rounds'][0]['audios'][0]
        assert audio_item['audio_id'] == 88
        assert audio_item['playback_device_id'] == 5
        assert case['algorithmType'] == 'asr'
        assert case['algorithmParams'] == [
            {'round_number': 1, 'params': [{'field_code': 'lang', 'field_value': 'zh'}]}]
        # 标签 / 分组 / 用例级路由快照
        assert case['tags'] == ['回归标签']
        assert case['group'] == {'id': 'grp-int303', 'name': 'INT303分组',
                                 'description': None, 'algorithmType': 'asr'}
        assert case['deviceType'] == 'physical'
        assert case['deviceId'] == '9'
        assert case['labId'] == 2
        # 参考参数留档路径（存储读取失败时内容为空、路径保留——单测库无该文件）
        assert case['referenceParamsSource'] == [
            {'roundNumber': 1, 'path': 'local://ref_params/tc-int303-a/round_1.json'}]
        assert case['referenceParams'][0]['roundNumber'] == 1
        assert case['referenceParams'][0]['path'] == 'local://ref_params/tc-int303-a/round_1.json'
        # 关联设备/API/播放设备引用快照（名称经 ACL 解析；隔离后为夹具值）
        assert frozen['devices'] == [{'id': 11, 'name': '设备11'}]
        assert frozen['apis'] == [{'id': 13, 'name': 'API13'}]
        assert frozen['playbackDevices'] == [{'id': 5, 'name': '播放设备5'}]

    def test_freeze_is_deep_copy(self, monkeypatch):
        """冻结体与源 PO 不共享可变引用（源后续编辑不影响冻结体）。"""
        factory = _build_session_factory(monkeypatch, _case_tables())
        _patch_name_acls(monkeypatch)
        _seed_task_with_cases(factory)
        session = factory()
        task = session.get(Task, 123)

        frozen = ptr_module.published_task_repository.freeze_task_snapshot(task)

        frozen['cases'][0]['config']['rounds'][0]['audios'][0]['audio_id'] = 99999
        frozen['task']['tags'].append('脏数据')
        session.expire_all()
        task2 = session.get(Task, 123)
        frozen2 = ptr_module.published_task_repository.freeze_task_snapshot(task2)
        assert frozen2['cases'][0]['config']['rounds'][0]['audios'][0]['audio_id'] == 88
        assert frozen2['task']['tags'] == ['回归标签']

    def test_freeze_task_without_cases(self, monkeypatch):
        factory = _build_session_factory(monkeypatch, _case_tables())
        session = factory()
        session.add(Task(id=77, name='空任务', status='pending'))
        session.commit()
        task = session.get(Task, 77)
        session.close()

        frozen = ptr_module.published_task_repository.freeze_task_snapshot(task)

        assert frozen['schemaVersion'] == 2
        assert frozen['task']['name'] == '空任务'
        assert frozen['cases'] == []


# ---------------------------------------------------------------------------
# restore_frozen_cases：执行链路按冻结数据还原
# ---------------------------------------------------------------------------

class TestRestoreFrozenCases:
    """restore_frozen_cases：源用例被删后按冻结数据还原影子用例。"""

    def _frozen_payload(self, config, case_id='tc-int303-a', *, ref_source=None):
        return [{
            'caseId': case_id,
            'name': '登录用例',
            'description': '源用例描述',
            'config': config,
            'algorithmType': 'asr',
            'algorithmParams': [{'round_number': 1, 'params': [{'field_code': 'lang', 'field_value': 'zh'}]}],
            'referenceParams': [],
            'referenceParamsSource': ref_source
            if ref_source is not None
            else [{'roundNumber': 1, 'path': 'local://ref_params/tc-int303-a/round_1.json'}],
            'tags': ['回归标签'],
            'group': None,
            'deviceType': 'physical',
            'deviceId': '9',
            'labId': 2,
        }]

    def test_reuse_existing_when_config_unchanged(self, monkeypatch):
        factory = _build_session_factory(monkeypatch, _case_tables())
        _seed_task_with_cases(factory)
        session = factory()
        case = session.get(TestCase, 'tc-int303-a')
        config = case.config
        session.close()

        restored = ptr_module.published_task_repository.restore_frozen_cases(
            self._frozen_payload(config), [{'case_id': 'tc-int303-a', 'device_type': 'physical',
                                            'device_id': '9', 'lab_id': 2}])

        # 源用例仍在且配置一致 → 直接复用原 ID 与原路由
        assert len(restored) == 1
        new_id, device_type, device_id, lab_id = restored[0]
        assert new_id == 'tc-int303-a'
        assert (device_type, device_id, lab_id) == ('physical', '9', 2)

    def test_restore_shadow_case_when_source_deleted(self, monkeypatch):
        """源用例被删除 → 以新 UUID 重建影子用例（配置/标签按冻结数据）。"""
        factory = _build_session_factory(monkeypatch, _case_tables())
        _seed_task_with_cases(factory)
        session = factory()
        case = session.get(TestCase, 'tc-int303-a')
        config = case.config
        # 模拟源用例被删除
        session.query(TestCase).filter(TestCase.id == 'tc-int303-a').update({'deleted': True})
        session.commit()
        session.close()

        restored = ptr_module.published_task_repository.restore_frozen_cases(
            self._frozen_payload(config), [{'case_id': 'tc-int303-a', 'device_type': 'physical',
                                            'device_id': '9', 'lab_id': 2}])

        assert len(restored) == 1
        new_id, device_type, device_id, lab_id = restored[0]
        assert new_id != 'tc-int303-a'
        assert (device_type, device_id, lab_id) == ('physical', '9', 2)

        session = factory()
        shadow = session.get(TestCase, new_id)
        assert shadow is not None
        assert shadow.deleted is False
        assert shadow.config == config
        assert shadow.algorithm_type == 'asr'
        assert [t.name for t in shadow.tags] == ['回归标签']
        session.close()

    def test_restore_shadow_case_when_source_config_edited(self, monkeypatch):
        """源用例配置被编辑（未删）→ 不复用，按冻结数据还原影子用例。"""
        factory = _build_session_factory(monkeypatch, _case_tables())
        _seed_task_with_cases(factory)
        session = factory()
        case = session.get(TestCase, 'tc-int303-a')
        config = case.config
        # 模拟源用例被编辑：rounds 被改动
        edited = {'rounds': [{'round_number': 1, 'audios': []}]}
        session.query(TestCase).filter(TestCase.id == 'tc-int303-a').update({'config': edited})
        session.commit()
        session.close()

        restored = ptr_module.published_task_repository.restore_frozen_cases(
            self._frozen_payload(config), [{'case_id': 'tc-int303-a', 'device_type': 'physical',
                                            'device_id': '9', 'lab_id': 2}])

        new_id = restored[0][0]
        assert new_id != 'tc-int303-a'
        session = factory()
        shadow = session.get(TestCase, new_id)
        assert shadow.config == config  # 影子用例配置 = 冻结数据（发布时原貌）
        # 源用例保持编辑后的现值（还原不回写源）
        assert session.get(TestCase, 'tc-int303-a').config == edited
        session.close()

    def test_restore_deterministic_id_for_same_frozen_content(self, monkeypatch):
        """同一冻结内容两次还原 → 同一影子用例 ID（幂等，不重复建行）。"""
        factory = _build_session_factory(monkeypatch, _case_tables())
        _seed_task_with_cases(factory)
        session = factory()
        config = session.get(TestCase, 'tc-int303-a').config
        session.query(TestCase).filter(TestCase.id == 'tc-int303-a').update({'deleted': True})
        session.commit()
        session.close()
        payload = self._frozen_payload(config)

        first = ptr_module.published_task_repository.restore_frozen_cases(
            payload, [{'case_id': 'tc-int303-a', 'device_type': 'physical'}])
        second = ptr_module.published_task_repository.restore_frozen_cases(
            payload, [{'case_id': 'tc-int303-a', 'device_type': 'physical'}])

        assert first[0][0] == second[0][0]

    def test_route_remap_uses_snapshot_case_devices(self, monkeypatch):
        """路由按快照 caseDevices（发布时冻结），不读现库 task_case_relations。"""
        factory = _build_session_factory(monkeypatch, _case_tables())
        _seed_task_with_cases(factory)
        session = factory()
        config = session.get(TestCase, 'tc-int303-a').config
        session.close()

        restored = ptr_module.published_task_repository.restore_frozen_cases(
            self._frozen_payload(config),
            [{'case_id': 'tc-int303-a', 'device_type': 'http_api', 'device_id': '42', 'lab_id': None}])

        _new_id, device_type, device_id, lab_id = restored[0]
        assert (device_type, device_id, lab_id) == ('http_api', '42', None)


# ---------------------------------------------------------------------------
# execute：冻结还原执行 / 存量引用轨回退
# ---------------------------------------------------------------------------

def make_task(**overrides):
    task = type('TaskPO', (), {})()
    task.id = 456
    task.deleted = False
    task.status = 'completed'
    task.config = {}
    task.algorithm_type = 'translation'
    task.algorithm_params = {}
    task.created_by_user_id = None
    task.visibility = 'shared'
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
    pt.report_snapshot = None
    pt.publish_reason = None
    pt.published_by = None
    pt.published_at = None
    pt.archived_by = None
    pt.archived_at = None
    pt.created_at = None
    pt.created_by_user_id = None
    pt.visibility = 'shared'
    for k, v in overrides.items():
        setattr(pt, k, v)
    return pt


TASK_SNAPSHOT = {
    'schemaVersion': 2,
    'task': {'name': 'INT303源任务', 'tags': ['回归标签']},
    'cases': [
        {'caseId': 'tc-src', 'name': '源用例', 'config': {'rounds': [{'round_number': 1}]},
         'tags': ['回归标签'], 'referenceParams': []},
        {'caseId': 'tc-src-2', 'name': '第二用例', 'config': {'rounds': []},
         'tags': [], 'referenceParams': []},
    ],
    'devices': [{'id': 11, 'name': '测试手机'}],
    'apis': [],
    'playbackDevices': [],
}


class FakeRepo:
    """published_task_repository 替身：捕获执行链路还原调用。"""

    def __init__(self, current_pt=None, restored=None, existing_case_ids=None):
        self.current_pt = current_pt or make_pt()
        self.restored = restored or []
        self.existing_case_ids = existing_case_ids
        self.create_daily_task_kwargs = None

    def get_by_id(self, published_task_id):
        return self.current_pt

    def get_existing_case_ids(self, case_ids):
        if self.existing_case_ids is not None:
            return set(self.existing_case_ids)
        return set(case_ids)

    def restore_frozen_cases(self, frozen_cases, case_devices):
        # (new_id, device_type, device_id, lab_id) 逐冻结用例还原
        return self.restored or [
            (frozen.get('caseId'), None, None, None) for frozen in frozen_cases]

    def create_daily_task(self, **kwargs):
        self.create_daily_task_kwargs = kwargs
        return 555

    def update_task_trace(self, task_id, **kwargs):
        return True


class FakeLogRepository:
    def __init__(self):
        self.logs = []

    def batch_create(self, logs):
        self.logs.extend(logs)
        return logs


class TestExecuteFrozenRestore:
    """execute：taskSnapshot 冻结还原 / 存量引用轨回退。"""

    def _run(self, monkeypatch, repo, pt):
        import task_service.application.services.published_task_service as pts_module
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepository())
        return PublishedTaskService.execute(pt.id)

    def test_execute_restores_frozen_cases(self, monkeypatch):
        """快照带 taskSnapshot → 按冻结数据还原（caseIds 以还原结果为准）。"""
        pt = make_pt(snapshot_config={
            'caseIds': ['tc-src'],
            'caseDevices': [{'case_id': 'tc-src', 'device_type': 'physical'}],
            'deviceIds': [], 'apiIds': [], 'tags': [],
            'taskSnapshot': TASK_SNAPSHOT,
        })
        repo = FakeRepo(current_pt=pt, restored=[
            ('tc-frozen-new-1', 'physical', '9', None),
            ('tc-frozen-new-2', 'http_api', '42', None),
        ])

        result = self._run(monkeypatch, repo, pt)

        assert result['success'] is True
        kwargs = repo.create_daily_task_kwargs
        # 还原后的用例 ID 与路由进入建任务链路
        assert kwargs['case_ids'] == ['tc-frozen-new-1', 'tc-frozen-new-2']
        assert kwargs['restored_cases'] == repo.restored
        assert kwargs['snapshot_config']['taskSnapshot'] == TASK_SNAPSHOT

    def test_execute_legacy_snapshot_falls_back_to_reference_track(self, monkeypatch):
        """存量快照（无 taskSnapshot）→ 引用轨（caseIds 原样，restored_cases=None）。"""
        pt = make_pt(snapshot_config={
            'caseIds': ['tc-src'], 'caseDevices': [], 'deviceIds': [], 'apiIds': [], 'tags': [],
        })
        repo = FakeRepo(current_pt=pt)

        result = self._run(monkeypatch, repo, pt)

        assert result['success'] is True
        kwargs = repo.create_daily_task_kwargs
        assert kwargs['case_ids'] == ['tc-src']
        assert kwargs['restored_cases'] is None

    def test_execute_frozen_track_ignores_dead_case_ids(self, monkeypatch):
        """冻结轨：源用例全被删（引用 caseIds 失效）仍按冻结数据还原执行。"""
        pt = make_pt(snapshot_config={
            'caseIds': ['tc-gone-1', 'tc-gone-2'], 'caseDevices': [], 'deviceIds': [],
            'apiIds': [], 'tags': [],
            'taskSnapshot': TASK_SNAPSHOT,
        })
        repo = FakeRepo(current_pt=pt, existing_case_ids=set(), restored=[
            ('tc-frozen-new-1', 'physical', '9', None),
            ('tc-frozen-new-2', 'http_api', '42', None),
        ])

        result = self._run(monkeypatch, repo, pt)

        assert result['success'] is True
        kwargs = repo.create_daily_task_kwargs
        assert kwargs['case_ids'] == ['tc-frozen-new-1', 'tc-frozen-new-2']
        assert kwargs['restored_cases'] == repo.restored

    def test_execute_legacy_snapshot_rejects_when_all_cases_gone(self, monkeypatch):
        """存量引用轨：源用例全失效 → 拒绝执行（无冻结体可还原，不建残缺任务）。"""
        pt = make_pt(snapshot_config={
            'caseIds': ['tc-gone'], 'caseDevices': [], 'deviceIds': [], 'apiIds': [], 'tags': [],
        })
        repo = FakeRepo(current_pt=pt, existing_case_ids=set())

        result = self._run(monkeypatch, repo, pt)

        assert result['success'] is False
        assert repo.create_daily_task_kwargs is None


# ---------------------------------------------------------------------------
# create_version / get_detail：版本链冻结语义
# ---------------------------------------------------------------------------

class TestCreateVersionTaskSnapshotSemantics:
    """create_version：新来源任务重新冻结 / 未指定时深拷贝沿用。"""

    def _run(self, monkeypatch, repo, data):
        import task_service.application.services.published_task_service as pts_module
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr(pts_module, 'log_repository', FakeLogRepository())
        return PublishedTaskService.create_version(1001, data)

    def test_new_source_task_refreezes_task_snapshot(self, monkeypatch):
        frozen = {'schemaVersion': 2, 'task': {'name': '新源任务'}, 'cases': [{'caseId': 'c1'}]}
        repo = _FreezeAwareFakeRepo(
            source_task=make_task(id=456), current_pt=make_pt(), frozen=frozen)

        result = self._run(monkeypatch, repo, {'sourceTaskId': 456})

        assert result['success'] is True
        # 重新冻结的 taskSnapshot 进入新版本快照
        assert repo.create_version_kwargs['snapshot_config']['taskSnapshot'] == frozen
        assert repo.create_version_kwargs['source_task_id'] == 456

    def test_no_new_source_deep_copies_current_snapshot(self, monkeypatch):
        current = make_pt(snapshot_config={
            'caseIds': ['tc-src'], 'caseDevices': [], 'deviceIds': [], 'apiIds': [],
            'tags': [], 'taskSnapshot': TASK_SNAPSHOT,
        })
        repo = _FreezeAwareFakeRepo(current_pt=current)

        result = self._run(monkeypatch, repo, {})

        assert result['success'] is True
        passed = repo.create_version_kwargs['snapshot_config']
        assert passed['taskSnapshot'] == TASK_SNAPSHOT
        # 深拷贝：新版本快照与当前版本快照不共享冻结体可变引用
        assert passed['taskSnapshot'] is not current.snapshot_config['taskSnapshot']
        assert passed['taskSnapshot']['task'] is not current.snapshot_config['taskSnapshot']['task']


class _FreezeAwareFakeRepo:
    """create_version 链路替身：捕获 freeze_task_snapshot 与 create_version 调用。"""

    def __init__(self, source_task=None, current_pt=None, frozen=None):
        self.source_task = source_task
        self.current_pt = current_pt
        self.frozen = frozen
        self.create_version_kwargs = None

    def get_task(self, task_id):
        return self.source_task

    def get_task_case_devices(self, task_id):
        return []

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

    def get_by_id(self, published_task_id):
        return self.current_pt

    def freeze_task_snapshot(self, task):
        return self.frozen

    def freeze_report_snapshot(self, source_task_id):
        return None

    def get_current_version(self, group_id):
        return self.current_pt

    def create_version(self, **kwargs):
        self.create_version_kwargs = kwargs
        return make_pt(**{
            'id': 1002,
            'version': kwargs.get('version', 2),
            'task_group_id': self.current_pt.task_group_id,
        })


class TestGetDetailHasTaskSnapshot:
    """get_detail：has_task_snapshot 标记（存量 → 历史版本标注依据）。"""

    def _run(self, monkeypatch, pt):
        import task_service.application.services.published_task_service as pts_module

        class _Repo:
            def get_by_id(self, published_task_id):
                return pt

            def get_source_task_summary(self, task_id):
                return None

            def get_group_versions(self, group_id):
                return [pt]

            def get_execution_history(self, version_ids):
                return []

        monkeypatch.setattr(pts_module, 'repo', _Repo())
        return PublishedTaskService.get_detail(pt.id)

    def test_detail_reports_frozen_flag(self, monkeypatch):
        pt = make_pt(snapshot_config={'caseIds': [1], 'taskSnapshot': TASK_SNAPSHOT})

        result = self._run(monkeypatch, pt)

        assert result['success'] is True
        assert result['data']['has_task_snapshot'] is True

    def test_detail_legacy_snapshot_flag_false(self, monkeypatch):
        pt = make_pt(snapshot_config={'caseIds': [1]})

        result = self._run(monkeypatch, pt)

        assert result['success'] is True
        assert result['data']['has_task_snapshot'] is False
