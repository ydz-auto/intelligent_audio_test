# -*- coding: utf-8 -*-
"""INT-104 验收补充：建任务路径与 PATCH add 路径 device_type 派生口径一致性。

issue 验收点（INT-79 收敛范围）：同一用例配置形态经
POST /api/v1/tasks（create_task_with_relations → _add_task_relations）与
PATCH /tasks/{id}/cases add（update_cases → _apply_case_action）
两条路径写入的 task_case_relations.device_type 必须一致，
且显式 caseDevices（含 websocket_api）在创建路径仍优先于派生。

真库验证（进程级 SQLite 文件库 + 真实 task_repository 单例）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_E2E_CASE_ID = 'int104-dual-case-e2e'
_API_CASE_ID = 'int104-dual-case-api'
_MISSING_CASE_ID = 'int104-dual-case-not-exist'
_E2E_CONFIG = {'rounds': [{'audios': [{'audio_id': 11, 'playback_device_id': 7}]}]}
_API_CONFIG = {'rounds': [{'audios': [{'audio_id': 12}]}]}


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
        name='INT-104 双路径一致性验证任务',
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


class TestDualPathDeviceTypeConsistency:
    def test_create_and_patch_add_derive_identically(self, db):
        """同一用例集合：创建路径与 PATCH add 路径派生结果逐项一致。"""
        _seed_cases()
        case_ids = [_E2E_CASE_ID, _API_CASE_ID, _MISSING_CASE_ID]

        task_id_create = _create_task(case_ids)
        task_id_patch = _create_task([])

        from task_service.infrastructure.persistence.task_repository import task_repository
        result = task_repository.update_cases(task_id_patch, 'add', case_ids)
        assert result is not None and 'error' not in result

        by_create = _read_case_device_types(task_id_create)
        by_patch = _read_case_device_types(task_id_patch)
        assert by_create == by_patch
        # 口径锚定：E2E 形态 → physical，API 形态与缺失用例行 → http_api
        assert by_create[_E2E_CASE_ID] == 'physical'
        assert by_create[_API_CASE_ID] == 'http_api'
        assert by_create[_MISSING_CASE_ID] == 'http_api'

    def test_explicit_websocket_api_case_device_wins_on_create(self, db):
        """显式 caseDevices 优先于派生：realtime 的 websocket_api 不被改写。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID, _API_CASE_ID],
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'websocket_api'},
            ],
        )
        rows = _read_case_device_types(task_id)
        assert rows[_E2E_CASE_ID] == 'websocket_api'
        # 同任务未显式指定的用例仍按形态派生
        assert rows[_API_CASE_ID] == 'http_api'
