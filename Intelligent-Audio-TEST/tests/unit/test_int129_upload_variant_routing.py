# -*- coding: utf-8 -*-
"""任务执行路由只认 device_type（不再按用例配置形态派生 api/e2e）。

用例不再区分 api/e2e：执行方式由 task_case_relations.device_type 决定
（task_dispatch 唯一依据，不允许为空）。口径：
- 建任务：前端按目标展开 case_devices（device_type 必填，INT-1433）；
- 动态加用例：PATCH /tasks/{id}/cases add 必须随请求传 case_devices；
- 旧调用未传 case_devices：按任务目标展开——每个 device_id 落 physical，
  api_ids 非空落 API 亲和域；无任何目标时物理域兜底（device_type 仍非空）。

覆盖：建任务路径 + 动态加用例路径（真库）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

_CASE_A = 'int129-case-a'
_CASE_B = 'int129-case-b'


@pytest.fixture(scope='module')
def db():
    from shared.models.database import (
        Base, init_db, get_engine, remove_db_session,
    )
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TaskDevice,
    )
    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[Task.__table__, TaskCase.__table__, TaskDevice.__table__],
    )
    yield
    remove_db_session()


def _create_task(case_ids, case_devices=None, device_ids=None, api_ids=None):
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name='device_type 路由验证任务',
        description='',
        config=None,
        algorithm_type=None,
        algorithm_params=None,
        case_ids=list(case_ids),
        device_ids=list(device_ids or []),
        api_ids=list(api_ids or []),
        created_by=None,
        case_devices=case_devices,
    )


def _read_case_routes(task_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    try:
        return [
            (row.test_case_id, row.device_type, row.device_id)
            for row in session.query(TaskCase).filter(TaskCase.task_id == task_id).all()
        ]
    finally:
        remove_db_session()


def _read_single_route(task_id, case_id):
    return next(
        (r for r in _read_case_routes(task_id) if r[0] == case_id), None
    )


class TestCreateTaskRouting:
    def test_explicit_case_devices_written_as_is(self, db):
        """显式 case_devices：device_type/device_id 原样落库。"""
        task_id = _create_task(
            [_CASE_A, _CASE_B],
            case_devices=[
                {'case_id': _CASE_A, 'device_type': 'websocket_api', 'device_id': '9'},
                {'case_id': _CASE_B, 'device_type': 'physical', 'device_id': '7'},
            ],
        )
        routes = _read_case_routes(task_id)
        assert _CASE_A in [r[0] for r in routes]
        assert _read_single_route(task_id, _CASE_A) == (_CASE_A, 'websocket_api', '9')
        assert _read_single_route(task_id, _CASE_B) == (_CASE_B, 'physical', '7')

    def test_missing_device_type_rejected(self, db):
        """case_devices 条目缺 device_type：契约错误，不猜。"""
        from task_service.infrastructure.persistence._task_crud_mixin import (
            MissingDeviceTypeError,
        )
        with pytest.raises(MissingDeviceTypeError):
            _create_task(
                [_CASE_A],
                case_devices=[{'case_id': _CASE_A, 'device_id': '7'}],
            )

    def test_legacy_device_targets_expand_physical_rows(self, db):
        """旧调用（无 case_devices）：按 device_ids 展开 physical 路由。"""
        task_id = _create_task([_CASE_A], device_ids=[7, 8])
        task_routes = [r for r in _read_case_routes(task_id) if r[0] == _CASE_A]
        assert sorted(r[2] for r in task_routes) == ['7', '8']
        assert all(r[1] == 'physical' for r in task_routes)

    def test_legacy_no_targets_falls_back_physical(self, db):
        """旧调用且无任何目标：物理域兜底（device_type 非空）。"""
        task_id = _create_task([_CASE_A])
        assert _read_single_route(task_id, _CASE_A) == (_CASE_A, 'physical', None)


class TestDynamicAddRouting:
    def test_add_requires_case_devices(self, db):
        """动态加用例必须显式给 device_type。"""
        task_id = _create_task([_CASE_A])
        from task_service.infrastructure.persistence.task_repository import task_repository
        result = task_repository.update_cases(task_id, 'add', [_CASE_B])
        assert result['code'] == 400
        assert _read_single_route(task_id, _CASE_B) is None

    def test_add_with_case_devices_writes_route(self, db):
        task_id = _create_task([_CASE_A])
        from task_service.infrastructure.persistence.task_repository import task_repository
        result = task_repository.update_cases(
            task_id, 'add', [_CASE_B],
            [{'case_id': _CASE_B, 'device_type': 'http_api', 'device_id': '3'}],
        )
        assert result == {'task_id': task_id, 'total_count': 2}
        assert _read_single_route(task_id, _CASE_B) == (_CASE_B, 'http_api', '3')
        assert _read_single_route(task_id, _CASE_A) == (_CASE_A, 'physical', None)

    def test_add_duplicate_case_is_idempotent(self, db):
        task_id = _create_task([_CASE_A])
        from task_service.infrastructure.persistence.task_repository import task_repository
        task_repository.update_cases(
            task_id, 'add', [_CASE_A],
            [{'case_id': _CASE_A, 'device_type': 'physical'}],
        )
        assert _read_single_route(task_id, _CASE_A) == (_CASE_A, 'physical', None)
