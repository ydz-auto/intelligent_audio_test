# -*- coding: utf-8 -*-
"""INT-148 缺陷#1 回归：任务 start 前对 API 用例目标 API 做在线预检。

原缺陷：V9.7.10 任务启动含设备占用提示 + API 任务对 API 在线预检；V9.7.31
仅保留设备离线检查（占用互斥移到引擎队列属架构差异，不恢复），API 在线
预检缺失——目标 API 离线时任务照常启动，逐用例执行期才失败。

修复语义（本文件覆盖）：
- check_environment_for_start 在设备检查后追加 API 预检（_check_apis_online）；
- http_api/websocket_api 用例的目标 API（TaskCase.device_id）逐一调用
  api_test_service TestAPIConnection（经 api_acl_repository ACL）；
- 明确 offline → 阻断启动并给出含 api_id 与失败原因的报错；
- gRPC 不可达（ACL 返回 None）→ 不阻塞启动（与设备检查降级策略一致）。

隔离方式：ACL 健康检查与用例查询分别以 monkeypatch 替身注入；
_get_task_api_case_ids 用独立 sqlite 内存库建 TaskCase 表验证过滤/去重。
"""
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import task_service.infrastructure.persistence._task_lifecycle_mixin as lifecycle_module
from task_service.infrastructure.persistence._task_lifecycle_mixin import TaskLifecycleMixin
from task_service.infrastructure.persistence.models import TaskCase


class TestCheckApisOnline:
    """_check_apis_online：offline 阻断 / online 通过 / ACL 不可用降级。"""

    def _patch_case_ids(self, monkeypatch, api_ids):
        monkeypatch.setattr(
            TaskLifecycleMixin, '_get_task_api_case_ids',
            staticmethod(lambda task_id: api_ids))

    def _patch_acl(self, monkeypatch, results):
        """results: {api_id: 返回值}；未命中的 api_id 返回 {'status': 'online'}。"""
        from task_service.infrastructure.acl import api_acl_repository as acl_module

        def fake_test(api_id):
            return results.get(api_id, {'id': api_id, 'status': 'online'})

        monkeypatch.setattr(acl_module.api_acl_repository, 'test_api_connection', fake_test)

    def test_offline_api_blocks_start_with_clear_message(self, monkeypatch):
        self._patch_case_ids(monkeypatch, [7])
        self._patch_acl(monkeypatch, {7: {'id': 7, 'status': 'offline', 'error': '端点连接异常: timeout'}})

        can_start, err = TaskLifecycleMixin._check_apis_online(1)

        assert can_start is False
        assert '7' in err
        assert '离线' in err
        assert '端点连接异常: timeout' in err

    def test_online_api_passes(self, monkeypatch):
        self._patch_case_ids(monkeypatch, [7])
        self._patch_acl(monkeypatch, {7: {'id': 7, 'status': 'online'}})

        can_start, err = TaskLifecycleMixin._check_apis_online(1)

        assert (can_start, err) == (True, '')

    def test_offline_among_multiple_apis_blocks(self, monkeypatch):
        self._patch_case_ids(monkeypatch, [7, 8])
        self._patch_acl(monkeypatch, {7: {'id': 7, 'status': 'online'},
                                      8: {'id': 8, 'status': 'offline', 'error': '端点连接失败: 502'}})

        can_start, err = TaskLifecycleMixin._check_apis_online(1)

        assert can_start is False
        assert 'id=8' in err

    def test_grpc_unavailable_does_not_block_start(self, monkeypatch):
        """ACL 返回 None（gRPC 失败）→ 预检不可用不阻塞启动（与设备检查策略一致）。"""
        self._patch_case_ids(monkeypatch, [7])
        self._patch_acl(monkeypatch, {7: None})

        can_start, err = TaskLifecycleMixin._check_apis_online(1)

        assert (can_start, err) == (True, '')

    def test_no_api_cases_skips_check(self, monkeypatch):
        self._patch_case_ids(monkeypatch, [])
        called = []

        from task_service.infrastructure.acl import api_acl_repository as acl_module
        monkeypatch.setattr(
            acl_module.api_acl_repository, 'test_api_connection',
            lambda api_id: called.append(api_id) or {'status': 'online'})

        can_start, err = TaskLifecycleMixin._check_apis_online(1)

        assert (can_start, err) == (True, '')
        assert called == []


class TestGetTaskApiCaseIds:
    """_get_task_api_case_ids：device_type 过滤 + 去重 + None 过滤（sqlite）。"""

    def _build_session(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool)
        from shared.models.database import Base
        Base.metadata.create_all(bind=engine, tables=[TaskCase.__table__])
        factory = sessionmaker(bind=engine)
        monkeypatch.setattr(lifecycle_module, 'get_db_session', factory)
        return factory

    def test_filters_api_device_types_and_dedupes(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        session = factory()
        try:
            session.add(TaskCase(task_id=1, test_case_id='c1',
                                 device_type='http_api', device_id='7'))
            session.add(TaskCase(task_id=1, test_case_id='c2',
                                 device_type='websocket_api', device_id='8'))
            session.add(TaskCase(task_id=1, test_case_id='c3',
                                 device_type='http_api', device_id='7'))  # 重复
            session.add(TaskCase(task_id=1, test_case_id='c4',
                                 device_type='physical', device_id='3'))  # 物理用例不算
            session.add(TaskCase(task_id=1, test_case_id='c5',
                                 device_type='http_api', device_id=None))  # 无目标
            session.commit()
        finally:
            session.close()

        api_ids = TaskLifecycleMixin._get_task_api_case_ids(1)

        assert api_ids == [7, 8]

    def test_empty_for_task_without_api_cases(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        session = factory()
        try:
            session.add(TaskCase(task_id=2, test_case_id='c1',
                                 device_type='physical', device_id='3'))
            session.commit()
        finally:
            session.close()

        assert TaskLifecycleMixin._get_task_api_case_ids(2) == []


class TestCheckEnvironmentOrchestration:
    """check_environment_for_start 编排：设备检查失败短路，API 检查兜底执行。"""

    def test_device_offline_short_circuits_before_api_check(self, monkeypatch):
        monkeypatch.setattr(
            TaskLifecycleMixin, '_check_devices_online',
            staticmethod(lambda device_ids: (False, '设备离线，无法启动: dev-1')))
        monkeypatch.setattr(
            TaskLifecycleMixin, '_get_task_api_case_ids',
            staticmethod(lambda task_id: pytest.fail('设备检查失败不应继续 API 预检')))
        repo = TaskLifecycleMixin()

        # TaskDevice 查询走 get_db_session，预置一条关联设备使设备检查执行
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                               poolclass=StaticPool)
        from shared.models.database import Base
        from task_service.infrastructure.persistence.models import TaskDevice
        Base.metadata.create_all(bind=engine, tables=[TaskDevice.__table__])
        factory = sessionmaker(bind=engine)
        monkeypatch.setattr(lifecycle_module, 'get_db_session', factory)
        session = factory()
        try:
            session.add(TaskDevice(task_id=1, device_id=3))
            session.commit()
        finally:
            session.close()

        can_start, err = repo.check_environment_for_start(1)

        assert can_start is False
        assert '设备离线' in err

    def test_device_ok_then_api_check_runs(self, monkeypatch):
        monkeypatch.setattr(
            TaskLifecycleMixin, '_check_devices_online',
            staticmethod(lambda device_ids: (True, '')))
        monkeypatch.setattr(
            TaskLifecycleMixin, '_get_task_api_case_ids',
            staticmethod(lambda task_id: []))
        repo = TaskLifecycleMixin()

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                               poolclass=StaticPool)
        from shared.models.database import Base
        from task_service.infrastructure.persistence.models import TaskDevice
        Base.metadata.create_all(bind=engine, tables=[TaskDevice.__table__])
        factory = sessionmaker(bind=engine)
        monkeypatch.setattr(lifecycle_module, 'get_db_session', factory)

        can_start, err = repo.check_environment_for_start(1)

        assert (can_start, err) == (True, '')
