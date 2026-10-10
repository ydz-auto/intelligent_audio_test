# -*- coding: utf-8 -*-
"""INT-104 验收测试：建任务路径派生 task_case_relations.device_type。

POST /api/v1/tasks 创建路径此前不派生 device_type（仅显式 caseDevices 写入，
否则 NULL），NULL 行被 task_dispatch 兜底按 physical 路由，API 任务全部误进
E2E 执行器（gRPC 分发失败）。修复后与 PATCH 用例路径 _apply_case_action
口径一致：未显式指定的用例由配置形态派生
（含 playback_device_id → physical，否则 http_api）。

真库验证（进程级 SQLite 文件库 + 真实 task_repository 单例）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_E2E_CASE_ID = 'int104-case-e2e'
_API_CASE_ID = 'int104-case-api'
_E2E_CONFIG = {'rounds': [{'audios': [{'audio_id': 1, 'playback_device_id': 7}]}]}
_API_CONFIG = {'rounds': [{'audios': [{'audio_id': 2}]}]}


@pytest.fixture(scope='module')
def db():
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[Task.__table__, TaskCase.__table__, TestCase.__table__],
    )
    yield
    remove_db_session()


def _seed_cases():
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        for case_id, config in [(_E2E_CASE_ID, _E2E_CONFIG), (_API_CASE_ID, _API_CONFIG)]:
            if session.get(TestCase, case_id) is None:
                session.add(TestCase(id=case_id, name=case_id, config=config))
        session.commit()
    finally:
        remove_db_session()


def _create_task(case_ids, case_devices=None):
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name='INT-104 派生验证任务',
        description='',
        config=None,
        algorithm_type=None,
        algorithm_params=None,
        case_ids=list(case_ids),
        device_ids=[],
        api_ids=[],
        created_by=None,
        case_devices=case_devices,
    )


def _read_case_device_types(task_id):
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    try:
        return {
            row.test_case_id: row.device_type
            for row in session.query(TaskCase).filter(TaskCase.task_id == task_id).all()
        }
    finally:
        remove_db_session()


class TestCreatePathDeviceTypeDerivation:
    def test_create_without_case_devices_derives_from_config(self, db):
        """不传 caseDevices：E2E 形态用例 → physical，API 形态用例 → http_api。"""
        _seed_cases()
        task_id = _create_task([_E2E_CASE_ID, _API_CASE_ID])
        rows = _read_case_device_types(task_id)
        assert rows[_E2E_CASE_ID] == 'physical'
        assert rows[_API_CASE_ID] == 'http_api'

    def test_explicit_case_devices_override_derivation(self, db):
        """显式 caseDevices 优先；同任务未指定的用例仍由配置形态派生。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID, _API_CASE_ID],
            case_devices=[{'case_id': _E2E_CASE_ID, 'device_type': 'http_api'}],
        )
        rows = _read_case_device_types(task_id)
        assert rows[_E2E_CASE_ID] == 'http_api'
        assert rows[_API_CASE_ID] == 'http_api'

    def test_missing_case_row_falls_back_to_http_api(self, db):
        """用例行不存在（config 取不到）：按 API 形态兜底，与 PATCH 路径一致。"""
        task_id = _create_task(['int104-case-not-exist'])
        rows = _read_case_device_types(task_id)
        assert rows['int104-case-not-exist'] == 'http_api'
