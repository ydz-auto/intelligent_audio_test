# -*- coding: utf-8 -*-
"""INT-540 验收（拆分④）：任务 lab_ids + /tasks/validate 校验 + 关联实验室返回。

覆盖（验收标准 1/2/4 的单测部分）：
- 持久化：create_task_with_relations(lab_ids) → task_laboratory_relations（含 priority、
  去重）；无 lab_ids → 零关联（回归）
- 读取：task_read_model.get_task_labs / search_tasks / 详情 DTO 内联 labs
  （N:M、priority 排序、软删实验室过滤）
- 用例 lab 解析：get_testcase_lab_ids（config JSONB，空=通用→None，不存在不在返回）
- 网关 /tasks/validate 各分支：case 通用/专属正反例、device 归属正反例（含未绑定）、
  playback 有值/跳过、lab_ids 不存在
- 网关 POST /api/tasks：lab_ids 存在性校验 + 透传创建 + 响应内联 labs；无 lab_ids 回归
- 契约：/validate 路由先于 /{task_id}；validate errors / labs / create 响应结构

DB：进程级 SQLite（tests/conftest.py 注入），按需建 laboratories 表（对齐 migration
202608 add_laboratory_tables）+ Task/TaskLaboratoryRelation/TestCase PO 表。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import text

from shared.models.database import (
    Base, init_db, get_db_session, get_engine, remove_db_session,
)
from api_gateway.infrastructure.request_adapter import set_current_request
from api_gateway.application.services.task.task_command_service import TaskCommandService
from api_gateway.application.services.task.task_query_service import TaskQueryService
from api_gateway.routes.task_bp import router as task_router

_LAB_TABLE_CREATED = False

# 与 scripts/migrations/202608/add_laboratory_tables.py Step1 对齐（SQLite 兼容形态）
_CREATE_LAB_TABLE = """
CREATE TABLE IF NOT EXISTS laboratories (
    id INTEGER PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    building VARCHAR(50),
    floor VARCHAR(20),
    room_number VARCHAR(50),
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# 与 migration Step2 对齐（SQLite 兼容形态：id INTEGER PRIMARY KEY 才能自增；
# PO 的 BigInteger PK 在 SQLite 下 create_all 不产生自增，须 raw DDL 兜底）
_CREATE_TASK_LAB_REL_TABLE = """
CREATE TABLE IF NOT EXISTS task_laboratory_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    lab_id INTEGER NOT NULL,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, lab_id)
)
"""


def _ensure_db():
    global _LAB_TABLE_CREATED
    init_db(pool_size=2)
    if not _LAB_TABLE_CREATED:
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI,
            Favorite, Tag, TaskTag, TestCase,
        )
        Base.metadata.create_all(
            bind=get_engine(),
            tables=[t.__table__ for t in (
                Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI,
                Favorite, Tag, TaskTag, TestCase,
            )],
        )
        session = get_db_session()
        try:
            session.execute(text(_CREATE_LAB_TABLE))
            session.execute(text(_CREATE_TASK_LAB_REL_TABLE))
            session.commit()
        finally:
            remove_db_session()
        _LAB_TABLE_CREATED = True


def _cleanup():
    session = get_db_session()
    try:
        session.execute(text('DELETE FROM task_laboratory_relations'))
        session.execute(text('DELETE FROM task_case_relations'))
        session.execute(text('DELETE FROM task_device_relations'))
        session.execute(text('DELETE FROM task_api_relations'))
        session.execute(text('DELETE FROM task_tags'))
        session.execute(text('DELETE FROM task_merge_relations'))
        session.execute(text('DELETE FROM test_tasks'))
        session.execute(text('DELETE FROM test_cases'))
        session.execute(text('DELETE FROM tags'))
        session.execute(text('DELETE FROM favorites'))
        session.execute(text('DELETE FROM laboratories'))
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture(scope='module')
def db():
    _ensure_db()
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    set_current_request(None)


def _fake_request(json_body=None, query=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='POST', is_json=False, headers={})


def _seed_lab(lab_id, code, name, deleted=False):
    session = get_db_session()
    try:
        session.execute(
            text('INSERT INTO laboratories (id, code, name, status, deleted) '
                 "VALUES (:id, :code, :name, 'active', :deleted)"),
            {'id': lab_id, 'code': code, 'name': name, 'deleted': deleted},
        )
        session.commit()
    finally:
        remove_db_session()


def _create_task(lab_ids=None, name='INT-540 任务'):
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name=name, description='', config=None, algorithm_type=None,
        algorithm_params=None, case_ids=[], device_ids=[], api_ids=[],
        created_by=None, lab_ids=lab_ids,
    )


def _read_task_lab_rows(task_id):
    from task_service.infrastructure.persistence.models import TaskLaboratoryRelation
    session = get_db_session()
    try:
        return session.query(TaskLaboratoryRelation).filter_by(task_id=task_id).all()
    finally:
        remove_db_session()


# ==================== 持久化（验收标准 1） ====================

class TestTaskLabPersistence:
    def test_create_with_lab_ids_persists_relations(self, db):
        """lab_ids 持久化到 task_laboratory_relations，priority 按传入顺序、去重。"""
        task_id = _create_task(lab_ids=[1, 2, 2])
        rows = _read_task_lab_rows(task_id)
        assert [r.lab_id for r in rows] == [1, 2]
        assert [r.priority for r in rows] == [1, 2]

    def test_create_without_lab_ids_no_relations(self, db):
        """无 lab_ids 创建任务零关联（回归：lab_ids 可选缺省兼容现状）。"""
        task_id = _create_task(lab_ids=None)
        assert _read_task_lab_rows(task_id) == []
        task_id2 = _create_task(lab_ids=[])
        assert _read_task_lab_rows(task_id2) == []

    def test_create_with_lab_ids_does_not_break_task(self, db):
        """带 lab_ids 创建任务主表记录正常（回归）。"""
        task_id = _create_task(lab_ids=[1])
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models import Task
            task = session.get(Task, task_id)
            assert task is not None and task.name == 'INT-540 任务'
        finally:
            remove_db_session()


# ==================== 读取：labs 内联 + get_task_labs（验收标准 1/2） ====================

class TestTaskLabsReadModel:
    def test_get_task_labs_returns_ordered_labs(self, db):
        """get_task_labs：N:M 多实验室按 priority 排序（创建时 lab_ids 顺序）。"""
        _seed_lab(1, 'LAB-A-01', '音频测试实验室1')
        _seed_lab(2, 'LAB-B-01', '音频测试实验室2')
        task_id = _create_task(lab_ids=[2, 1])
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        result = task_read_model.get_task_labs(task_id)
        assert result['task_id'] == task_id
        assert result['labs'] == [
            {'id': 2, 'code': 'LAB-B-01', 'name': '音频测试实验室2'},
            {'id': 1, 'code': 'LAB-A-01', 'name': '音频测试实验室1'},
        ]

    def test_get_task_labs_excludes_soft_deleted_lab(self, db):
        """已软删实验室不计入 labs（与 laboratory_repository.get 软删过滤口径一致）。"""
        _seed_lab(1, 'LAB-A-01', '音频测试实验室1')
        _seed_lab(2, 'LAB-B-01', '音频测试实验室2', deleted=True)
        task_id = _create_task(lab_ids=[1, 2])
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        result = task_read_model.get_task_labs(task_id)
        assert result['labs'] == [{'id': 1, 'code': 'LAB-A-01', 'name': '音频测试实验室1'}]

    def test_get_task_labs_missing_task_returns_none(self, db):
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        assert task_read_model.get_task_labs(999999) is None

    def test_search_tasks_inlines_labs(self, db):
        """任务列表 TaskItem 内联 labs。"""
        _seed_lab(5, 'LAB-E', '实验室E')
        task_id = _create_task(lab_ids=[5])
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        result = task_read_model.search_tasks(page=1, per_page=10)
        items = result['items']
        assert any(item['id'] == task_id and item.get('labs') == [
            {'id': 5, 'code': 'LAB-E', 'name': '实验室E'}
        ] for item in items)

    def test_detail_dto_inlines_labs(self, db):
        """任务详情 DTO 内联 labs。"""
        _seed_lab(7, 'LAB-G', '实验室G')
        task_id = _create_task(lab_ids=[7])
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        result = task_read_model.find_by_id_with_relations(task_id)
        assert result is not None
        assert result['labs'] == [{'id': 7, 'code': 'LAB-G', 'name': '实验室G'}]


# ==================== 用例 lab 解析（验收标准 1） ====================

class TestTestCaseLabIds:
    def test_parse_config_lab_id(self, db):
        """config lab_id 解析：专属用例返回 lab_id，通用用例返回 None，不存在不在返回。"""
        from task_service.infrastructure.persistence.task_repository import task_repository
        from task_service.infrastructure.persistence.models import TestCase
        session = get_db_session()
        try:
            session.add(TestCase(id='tc-dedicated', name='专属用例', config={'lab_id': 1}))
            session.add(TestCase(id='tc-generic', name='通用用例', config={'rounds': []}))
            session.add(TestCase(id='tc-missing-key', name='缺 lab_id', config={}))
            session.add(TestCase(id='tc-str', name='字符串 lab_id', config={'lab_id': '3'}))
            session.commit()
        finally:
            remove_db_session()

        result = task_repository.get_testcase_lab_ids(
            ['tc-dedicated', 'tc-generic', 'tc-missing-key', 'tc-str', 'tc-not-exist'])
        assert result == {
            'tc-dedicated': 1,
            'tc-generic': None,
            'tc-missing-key': None,
            'tc-str': 3,
        }
        assert 'tc-not-exist' not in result


# ==================== 网关 /tasks/validate（验收标准 1） ====================

class TestGatewayValidate:
    def _run_validate(self, body):
        set_current_request(_fake_request(json_body=body))
        resp = TaskCommandService.validate()
        # resp 为 (payload, http_code) 元组
        payload = resp[0]
        return payload['data']

    def test_lab_ids_missing_reports_error(self, db):
        """lab_ids 不存在 → laboratory 错误。"""
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist',
            return_value=[99],
        ):
            data = self._run_validate({'lab_ids': [99], 'case_ids': [], 'device_ids': []})
        assert data['valid'] is False
        assert data['errors'][0]['resource_type'] == 'laboratory'
        assert data['errors'][0]['resource_id'] == 99

    def test_case_generic_and_in_lab_ids_valid(self, db):
        """case 通用（lab_id None）与专属在 lab_ids 内 → 合法。"""
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={'c1': None, 'c2': 1},
        ):
            data = self._run_validate(
                {'lab_ids': [1], 'case_ids': ['c1', 'c2'], 'device_ids': []})
        assert data['valid'] is True, data['errors']
        assert data['errors'] == []

    def test_case_dedicated_out_of_lab_ids_invalid(self, db):
        """case 专属但不在 lab_ids → 非法。"""
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={'c1': 2},
        ):
            data = self._run_validate(
                {'lab_ids': [1], 'case_ids': ['c1'], 'device_ids': []})
        assert data['valid'] is False
        err = data['errors'][0]
        assert err['resource_type'] == 'test_case' and err['resource_id'] == 'c1'

    def test_case_not_exists_invalid(self, db):
        """case 不存在 → 非法（区别于通用用例）。"""
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={'c-exists': 1},
        ):
            data = self._run_validate(
                {'lab_ids': [1], 'case_ids': ['c-exists', 'c-missing'], 'device_ids': []})
        assert data['valid'] is False
        assert [e['resource_id'] for e in data['errors']] == ['c-missing']

    def test_device_belonging_valid_and_invalid(self, db):
        """device 归属正反例：在 lab_ids 内合法，越域/未绑定非法。"""
        from api_gateway.infrastructure.acl import DeviceAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={},
        ), mock.patch.object(
            DeviceAclRepositoryImpl, 'get_one',
            side_effect=lambda did: {'success': True, 'data': {
                'id': did, 'lab_id': {1: 1, 2: 2, 3: None}[did]}},
        ):
            data = self._run_validate(
                {'lab_ids': [1], 'device_ids': [1, 2, 3]})
        assert data['valid'] is False
        by_id = {e['resource_id']: e for e in data['errors']}
        assert 2 in by_id and 3 in by_id
        assert 1 not in by_id
        assert by_id[2]['reason'] == '设备不属于已选实验室'
        assert by_id[3]['reason'] == '设备不属于已选实验室'

    def test_device_not_exists_invalid(self, db):
        from api_gateway.infrastructure.acl import DeviceAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={},
        ), mock.patch.object(
            DeviceAclRepositoryImpl, 'get_one', return_value={'success': False},
        ):
            data = self._run_validate({'lab_ids': [1], 'device_ids': [42]})
        assert data['valid'] is False
        assert data['errors'][0]['resource_type'] == 'device'

    def test_playback_checked_when_provided(self, db):
        """playback_device_ids 有值 → 校验 lab 归属；越域非法。"""
        from api_gateway.infrastructure.acl import PlaybackConfigAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={},
        ), mock.patch.object(
            PlaybackConfigAclRepositoryImpl, 'get_one',
            side_effect=lambda pid: {'success': True, 'data': {'id': pid, 'lab_id': {11: 1, 12: 2}[pid]}},
        ):
            data = self._run_validate(
                {'lab_ids': [1], 'playback_device_ids': [11, 12]})
        assert data['valid'] is False
        assert [e['resource_id'] for e in data['errors']] == [12]
        assert data['errors'][0]['resource_type'] == 'playback_device'

    def test_playback_skipped_when_not_provided(self, db):
        """playback_device_ids 无值 → 跳过（不校验、无 playback 错误）。"""
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={},
        ):
            data = self._run_validate({'lab_ids': [1], 'case_ids': [], 'device_ids': []})
        assert data['valid'] is True
        assert data['errors'] == []

    def test_empty_lab_ids_generic_case_valid_devices_invalid(self, db):
        """lab_ids 空：通用用例合法、设备全部非法。"""
        from api_gateway.infrastructure.acl import DeviceAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch(
            'api_gateway.infrastructure.grpc_proxies.task_data_proxies.task_data_service.get_testcase_lab_ids',
            return_value={'c1': None},
        ), mock.patch.object(
            DeviceAclRepositoryImpl, 'get_one',
            return_value={'success': True, 'data': {'id': 1, 'lab_id': 1}},
        ):
            data = self._run_validate(
                {'lab_ids': [], 'case_ids': ['c1'], 'device_ids': [1]})
        assert data['valid'] is False
        assert [e['resource_type'] for e in data['errors']] == ['device']


# ==================== 网关 POST /api/tasks（验收标准 1/4） ====================

class TestGatewayCreate:
    def test_create_with_lab_ids_validates_and_returns_labs(self, db):
        """带 lab_ids 创建：存在性校验通过 + 透传创建 + 响应内联 labs。"""
        from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[],
        ), mock.patch.object(
            TaskConfigAclRepositoryImpl, 'create',
            return_value={'success': True, 'message': 'ok', 'data': {'id': 1001}},
        ), mock.patch.object(
            TaskCommandService, '_fetch_task_labs',
            return_value=[{'id': 1, 'code': 'LAB-A', 'name': '实验室A'}],
        ):
            set_current_request(_fake_request(json_body={
                'name': '跨实验室任务', 'lab_ids': [1, 2],
            }))
            payload = TaskCommandService.create()[0]
        assert payload['success'] is True
        data = payload['data']
        assert data['id'] == 1001
        assert data['labs'] == [{'id': 1, 'code': 'LAB-A', 'name': '实验室A'}]

    def test_create_with_missing_lab_id_rejected(self, db):
        """lab_ids 含不存在实验室 → 400 校验错误，不调用创建。"""
        from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[99],
        ), mock.patch.object(
            TaskConfigAclRepositoryImpl, 'create',
            return_value={'success': True, 'message': 'ok', 'data': {'id': 1001}},
        ) as m_create:
            set_current_request(_fake_request(json_body={
                'name': '非法实验室任务', 'lab_ids': [99],
            }))
            resp = TaskCommandService.create()
        assert resp[1] == 400
        assert '99' in resp[0]['message']
        m_create.assert_not_called()

    def test_create_without_lab_ids_regression(self, db):
        """无 lab_ids 创建（回归）：不做实验室校验，正常创建返回 labs=[]。"""
        from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
        with mock.patch.object(
            TaskCommandService, '_validate_lab_ids_exist', return_value=[99],
        ) as m_validate, mock.patch.object(
            TaskConfigAclRepositoryImpl, 'create',
            return_value={'success': True, 'message': 'ok', 'data': {'id': 1002}},
        ), mock.patch.object(
            TaskCommandService, '_fetch_task_labs', return_value=[],
        ):
            set_current_request(_fake_request(json_body={'name': '普通任务'}))
            payload = TaskCommandService.create()[0]
        m_validate.assert_not_called()
        assert payload['success'] is True
        assert payload['data']['labs'] == []


# ==================== 契约（验收标准 2） ====================

class TestTaskLabsContract:
    def test_validate_route_registered_before_task_id(self):
        """/tasks/validate 路由先于 /{task_id}（同 /stats 先例，防 int 校验 422）。"""
        paths = [r.path for r in task_router.routes]
        assert '/validate' in paths
        assert '/{task_id}' in paths
        assert paths.index('/validate') < paths.index('/{task_id}')

    def test_get_task_labs_route_registered(self):
        """GET /api/tasks/{id}/labs 路由在册。"""
        paths = [r.path for r in task_router.routes]
        assert '/{task_id}/labs' in paths

    def test_validate_error_schema(self):
        from api_gateway.schemas.task import TaskValidateError, TaskValidateData
        err = TaskValidateError(resource_type='device', resource_id='1', reason='x')
        assert err.model_dump() == {'resource_type': 'device', 'resource_id': '1', 'reason': 'x'}
        data = TaskValidateData(valid=False, errors=[err])
        assert data.model_dump()['valid'] is False
        assert data.model_dump()['errors'][0]['resource_type'] == 'device'

    def test_task_labs_schema_structure(self):
        from api_gateway.schemas.task import TaskLabBrief, TaskCreateData, TaskLabsData, TaskListItem
        lab = TaskLabBrief(id=1, code='LAB-A', name='实验室A')
        assert TaskCreateData(id=1, labs=[lab]).model_dump() == {
            'id': 1, 'labs': [{'id': 1, 'code': 'LAB-A', 'name': '实验室A'}]}
        assert TaskLabsData(task_id=1, labs=[lab]).model_dump()['task_id'] == 1
        # TaskListItem 内联 labs 结构
        item = TaskListItem(id=1, name='t', status='pending', labs=[lab])
        assert item.model_dump()['labs'] == [{'id': 1, 'code': 'LAB-A', 'name': '实验室A'}]

    def test_create_request_accepts_lab_ids(self):
        from api_gateway.schemas.task import TaskCreateRequest
        req = TaskCreateRequest.model_validate({'name': 't', 'lab_ids': [1, 2]})
        assert req.lab_ids == [1, 2]
        req2 = TaskCreateRequest.model_validate({'name': 't'})
        assert req2.lab_ids is None


# ==================== gRPC servicer 适配层（无实机栈，直调 servicer） ====================

class TestTaskDataServicerLabs:
    def test_get_task_labs_servicer(self, db):
        """GetTaskLabs servicer：直调返回 labs JSON；任务不存在 → 成功信封 + data None。"""
        import json
        from shared.utils.grpc_json import loads as _loads
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

        _seed_lab(1, 'LAB-A', '实验室A')
        task_id = _create_task(lab_ids=[1])
        servicer = TaskDataServiceServicer()

        resp = servicer.GetTaskLabs(
            type('Req', (), {'data': json.dumps({'task_id': task_id})})())
        assert resp.success is True
        data = _loads(resp.data, None)
        assert data['task_id'] == task_id
        assert data['labs'] == [{'id': 1, 'code': 'LAB-A', 'name': '实验室A'}]

        # 任务不存在 → 成功信封 + data 空（网关据此映射 404）
        resp = servicer.GetTaskLabs(
            type('Req', (), {'data': json.dumps({'task_id': 999999})})())
        assert resp.success is True
        assert resp.data == ''

    def test_get_testcase_lab_ids_servicer(self, db):
        """GetTestCaseLabIds servicer：直调返回 {case_id: lab_id}。"""
        import json
        from shared.utils.grpc_json import loads as _loads
        from task_service.infrastructure.persistence.models import TestCase
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

        session = get_db_session()
        try:
            session.add(TestCase(id='tc-lab', name='专属', config={'lab_id': 2}))
            session.add(TestCase(id='tc-gen', name='通用', config={}))
            session.commit()
        finally:
            remove_db_session()

        servicer = TaskDataServiceServicer()
        resp = servicer.GetTestCaseLabIds(
            type('Req', (), {'data': json.dumps({'case_ids': ['tc-lab', 'tc-gen', 'tc-none']})})())
        assert resp.success is True
        data = _loads(resp.data, {})
        assert data == {'tc-lab': 2, 'tc-gen': None}
