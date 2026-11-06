# -*- coding: utf-8 -*-
"""INT-573 专项：任务执行/控制叠加 owner 校验（私有任务非 owner 403）。

覆盖验收标准（后端）：
1. 私有任务 start/retry/stop/control/remove_case/rextract 非 owner → 403
   （VisibilityDenied，网关层映射 HTTP 403）；
2. 共享任务 + task:execute 权限可正常启动（零回归，不叠加 owner 过滤）；
3. 控制操作「owner 或启动人」放行、其他拒绝；start/retry 记录启动人
   （last_started_by_user_id），启动人不可再次 start/retry（仅 owner）；
4. admin 豁免全通过，网关侧 admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计；
5. 网关生命周期路径把下游 code=403 映射为 HTTP 403（镜像 INT-564 写路径）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内清理，对齐 test_int463_task_service_visibility.py 口径。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
from shared.infrastructure.visibility_filter import VisibilityDenied
from shared.models.database import (
    Base, init_db, get_engine, get_db_session,
)
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskStatus,
)
from api_gateway.infrastructure.request_adapter import set_current_request
import api_gateway.application.services.task.task_lifecycle_service as gw_lifecycle_mod

# ---------------- 工具 ----------------

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, Tag, TagCategory, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log, PublishedTask, TaskCherryPickRelation,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log, PublishedTask, TaskCherryPickRelation,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    """每个用例前清空涉及表，保证固定 ID 夹具互不冲突。"""
    _ensure_tables()
    session = get_db_session()
    try:
        for table in reversed(_TABLES):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)
    set_current_request(None)


def _set_user(user_id=None, is_admin=False):
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


_UNSET = object()


def _set_task_visibility(task_id, visibility, owner=_UNSET, starter=_UNSET):
    """直接置任务行 visibility / owner / starter（测试夹具）。

    owner / starter 仅在显式传入时更新（传 None 表示置 NULL）。用 SQL UPDATE
    绕过 ORM 身份映射，避免已提交 PO 的 DetachedInstanceError。
    """
    from task_service.infrastructure.persistence.models import Task
    from sqlalchemy import update
    session = get_db_session()
    try:
        values = {'visibility': visibility}
        if owner is not _UNSET:
            values['created_by_user_id'] = owner
        if starter is not _UNSET:
            values['last_started_by_user_id'] = starter
        session.execute(update(Task).where(Task.id == task_id).values(**values))
        session.commit()
    finally:
        session.close()


def _make_task(user_id):
    """以 user_id 上下文建任务（created_by_user_id 取上下文）。"""
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name='t', description='', config={}, algorithm_type='translation',
        algorithm_params={}, case_ids=[], device_ids=[], api_ids=[], created_by=user_id,
    )


def _set_task_status(task_id, status):
    from task_service.infrastructure.persistence.models import Task
    from sqlalchemy import update
    session = get_db_session()
    try:
        session.execute(update(Task).where(Task.id == task_id).values(status=status))
        session.commit()
    finally:
        session.close()


def _engine_mock():
    """执行引擎替身：start/control 成功 + 时间估算占位。"""
    engine = MagicMock()
    engine.start_task.return_value = (True, '任务已启动')
    engine.control_task.return_value = (True, 'ok')
    engine.event_manager.calculate_time_estimate.return_value = {
        'expected_total_time': 10, 'expected_complete_time': 60}
    return engine


def _eval_repo_mock():
    """evaluation_acl_repository 替身：rextract_result 成功。"""
    repo = MagicMock()
    repo.reextract_result.return_value = {
        'success': True, 'message': '重新提取成功',
        'data': {'message': '重新提取成功', 'reextracted_cases': []},
    }
    return repo


def _svc():
    from task_service.application.task.task_lifecycle_service import TaskLifecycleService
    return TaskLifecycleService()


# ---------------- 1. 非 owner 对私有任务执行/控制一律 403 ----------------

class TestPrivateTaskNonOwnerDenied:
    """私有任务非 owner 六条执行/控制路径全部 403（校验先于任何业务逻辑）。"""

    def _private_task(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        return tid

    def test_start_403(self):
        tid = self._private_task()
        _set_user(200)
        resp = _svc().start(tid)
        assert resp['code'] == 403
        assert resp['success'] is False

    def test_retry_403(self):
        tid = self._private_task()
        _set_user(200)
        resp = _svc().retry(tid)
        assert resp['code'] == 403

    def test_stop_403(self):
        tid = self._private_task()
        _set_user(200)
        resp = _svc().stop(tid)
        assert resp['code'] == 403

    def test_control_403(self):
        tid = self._private_task()
        _set_user(200)
        resp = _svc().control(tid, {'action': 'pause'})
        assert resp['code'] == 403

    def test_remove_case_403(self):
        tid = self._private_task()
        _set_user(200)
        resp = _svc().remove_case(tid, 'c1')
        assert resp['code'] == 403

    def test_rextract_403(self):
        tid = self._private_task()
        _set_task_status(tid, TaskStatus.COMPLETED)
        _set_user(200)
        resp = _svc().rextract(tid, {})
        assert resp['code'] == 403

    def test_unauthenticated_start_403(self):
        tid = self._private_task()
        _set_user(None)
        resp = _svc().start(tid)
        assert resp['code'] == 403


# ---------------- 2. owner 执行/控制放行 + 启动人记录 ----------------

class TestPrivateTaskOwnerAllowed:
    """私有任务 owner 全路径放行；start 记录启动人 last_started_by_user_id。"""

    def test_start_success_records_starter(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().start(tid)
        assert resp['success'] is True
        session = get_db_session()
        try:
            assert session.get(Task, tid).last_started_by_user_id == 100
        finally:
            session.close()

    def test_retry_success_records_starter(self):
        """retry 有可重试用例时走完重执行并记录启动人。"""
        from task_service.infrastructure.persistence.models import Task, TaskCase
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        # 直接插入一条 failed TaskCase（绕过仓储，测试夹具）
        session = get_db_session()
        try:
            session.add(TaskCase(
                task_id=tid, test_case_id='c1', status='failed',
                execution_status=ExecutionStatus.FAILED,
                evaluation_status=EvaluationStatus.FAILED,
            ))
            session.commit()
        finally:
            session.close()
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().retry(tid)
        assert resp['success'] is True
        assert '重试' in resp['message']
        session = get_db_session()
        try:
            assert session.get(Task, tid).last_started_by_user_id == 100
        finally:
            session.close()

    def test_stop_success(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().stop(tid)
        assert resp['success'] is True

    def test_control_success(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().control(tid, {'action': 'pause'})
        assert resp['success'] is True

    def test_remove_case_success(self):
        """owner 私有任务移除 pending 用例：物理删 + 计数重算 + 成功。"""
        from task_service.infrastructure.persistence.models import Task, TaskCase
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        session = get_db_session()
        try:
            session.add(TaskCase(
                task_id=tid, test_case_id='c1', status='pending',
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
            ))
            session.commit()
        finally:
            session.close()
        with patch('task_service.application.task.task_lifecycle_service.TaskLifecycleService._publish_removal_audit'):
            resp = _svc().remove_case(tid, 'c1')
        assert resp['success'] is True

    def test_rextract_success(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        _set_task_status(tid, TaskStatus.COMPLETED)
        with patch('task_service.infrastructure.acl.evaluation_acl_repository.evaluation_acl_repository',
                   _eval_repo_mock()):
            resp = _svc().rextract(tid, {})
        assert resp['success'] is True


# ---------------- 3. 启动人可控制、不可再次执行 ----------------

class TestStarterControlSemantics:
    """控制校验「owner 或启动人」；执行（start/retry）仍仅 owner。"""

    def _private_task_started_by_other(self):
        """owner=100 建私有任务，启动人 200 已记录。"""
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        _set_task_visibility(tid, 'private', starter=200)  # 显式置启动人
        return tid

    def test_starter_can_stop(self):
        tid = self._private_task_started_by_other()
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().stop(tid)
        assert resp['success'] is True

    def test_starter_can_control(self):
        tid = self._private_task_started_by_other()
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().control(tid, {'action': 'pause'})
        assert resp['success'] is True

    def test_starter_can_remove_case(self):
        from task_service.infrastructure.persistence.models import TaskCase
        tid = self._private_task_started_by_other()
        session = get_db_session()
        try:
            session.add(TaskCase(
                task_id=tid, test_case_id='c1', status='pending',
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
            ))
            session.commit()
        finally:
            session.close()
        _set_user(200)
        with patch('task_service.application.task.task_lifecycle_service.TaskLifecycleService._publish_removal_audit'):
            resp = _svc().remove_case(tid, 'c1')
        assert resp['success'] is True

    def test_starter_can_rextract(self):
        tid = self._private_task_started_by_other()
        _set_task_status(tid, TaskStatus.COMPLETED)
        _set_user(200)
        with patch('task_service.infrastructure.acl.evaluation_acl_repository.evaluation_acl_repository',
                   _eval_repo_mock()):
            resp = _svc().rextract(tid, {})
        assert resp['success'] is True

    def test_starter_cannot_restart(self):
        """启动人（非 owner）不可再次 start/retry 私有任务——执行仅 owner。"""
        tid = self._private_task_started_by_other()
        _set_user(200)
        resp = _svc().start(tid)
        assert resp['code'] == 403
        resp = _svc().retry(tid)
        assert resp['code'] == 403

    def test_third_party_cannot_control(self):
        """非 owner 且非启动人（300）控制私有任务仍 403。"""
        tid = self._private_task_started_by_other()
        _set_user(300)
        resp = _svc().stop(tid)
        assert resp['code'] == 403
        resp = _svc().control(tid, {'action': 'pause'})
        assert resp['code'] == 403


# ---------------- 4. 共享任务零回归 ----------------

class TestSharedTaskZeroRegression:
    """共享任务回落 RBAC 语义，不叠加 owner 过滤。"""

    def test_shared_start_any_user(self):
        _set_user(100)
        tid = _make_task(100)
        # 默认 shared，不显式置 private
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().start(tid)
        assert resp['success'] is True

    def test_shared_control_any_user(self):
        _set_user(100)
        tid = _make_task(100)
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().control(tid, {'action': 'pause'})
        assert resp['success'] is True

    def test_shared_stop_any_user(self):
        _set_user(100)
        tid = _make_task(100)
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().stop(tid)
        assert resp['success'] is True

    def test_shared_start_records_starter(self):
        """共享任务 start 同样记录启动人（后置 owner 转私有后启动人可控制）。"""
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = _make_task(100)
        _set_user(200)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().start(tid)
        assert resp['success'] is True
        session = get_db_session()
        try:
            assert session.get(Task, tid).last_started_by_user_id == 200
        finally:
            session.close()


# ---------------- 5. admin 豁免 ----------------

class TestAdminExemption:
    """admin 对私有任务全路径放行（校验豁免，不落 403）。"""

    def _private_task(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        return tid

    def test_admin_start(self):
        tid = self._private_task()
        _set_user(999, is_admin=True)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().start(tid)
        assert resp['success'] is True

    def test_admin_retry(self):
        tid = self._private_task()
        _set_user(999, is_admin=True)
        resp = _svc().retry(tid)  # 无重试用例 → 早退成功，校验已放行
        assert resp['success'] is True

    def test_admin_stop(self):
        tid = self._private_task()
        _set_user(999, is_admin=True)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().stop(tid)
        assert resp['success'] is True

    def test_admin_control(self):
        tid = self._private_task()
        _set_user(999, is_admin=True)
        with patch('task_service.core.execution_engine.execution_engine', _engine_mock()):
            resp = _svc().control(tid, {'action': 'pause'})
        assert resp['success'] is True

    def test_admin_remove_case(self):
        from task_service.infrastructure.persistence.models import TaskCase
        tid = self._private_task()
        session = get_db_session()
        try:
            session.add(TaskCase(
                task_id=tid, test_case_id='c1', status='pending',
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
            ))
            session.commit()
        finally:
            session.close()
        _set_user(999, is_admin=True)
        with patch('task_service.application.task.task_lifecycle_service.TaskLifecycleService._publish_removal_audit'):
            resp = _svc().remove_case(tid, 'c1')
        assert resp['success'] is True

    def test_admin_rextract(self):
        tid = self._private_task()
        _set_task_status(tid, TaskStatus.COMPLETED)
        _set_user(999, is_admin=True)
        with patch('task_service.infrastructure.acl.evaluation_acl_repository.evaluation_acl_repository',
                   _eval_repo_mock()):
            resp = _svc().rextract(tid, {})
        assert resp['success'] is True


# ---------------- 6. check_task_control_visible 单元 ----------------

class TestCheckTaskControlVisible:
    """控制可见性判定单元：私有 owner/启动人/admin 放行，其余 VisibilityDenied。"""

    def _task_obj(self, owner=100, vis='shared', starter=None):
        return SimpleNamespace(
            created_by_user_id=owner, visibility=vis, last_started_by_user_id=starter)

    def test_private_owner_pass(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        check_task_control_visible(self._task_obj(owner=100, vis='private'), user_id=100, is_admin=False)

    def test_private_starter_pass(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        check_task_control_visible(
            self._task_obj(owner=100, vis='private', starter=200), user_id=200, is_admin=False)

    def test_private_non_owner_denied(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        with pytest.raises(VisibilityDenied):
            check_task_control_visible(
                self._task_obj(owner=100, vis='private', starter=200), user_id=300, is_admin=False)

    def test_private_unauthenticated_denied(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        with pytest.raises(VisibilityDenied):
            check_task_control_visible(self._task_obj(owner=100, vis='private'), user_id=None, is_admin=False)

    def test_private_admin_pass(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        check_task_control_visible(
            self._task_obj(owner=100, vis='private'), user_id=300, is_admin=True)

    def test_shared_any_user_pass(self):
        from task_service.infrastructure.visibility_context import check_task_control_visible
        check_task_control_visible(
            self._task_obj(owner=100, vis='shared'), user_id=300, is_admin=False)


# ---------------- 7. 网关：403/404 映射 + admin 审计 ----------------

def _fake_gw_request(user_id=None, permissions=None, json_body=None):
    state = SimpleNamespace(
        _json_body=json_body, _files={}, _form_data={},
        user_id=user_id, permissions=permissions or [],
    )
    return SimpleNamespace(state=state, query_params={})


def _gw_acl(**kwargs):
    """构造 TaskConfigAclRepositoryImpl 替身：默认各操作成功 + get_task_detail。

    get_task_detail 按真实 gRPC 代理信封形状（{success, message, data}，data 为
    详情 DTO，含 visibility/created_by_user_id——INT-982 P1-2 修复后详情 DTO
    契约字段）。
    """
    defaults = dict(
        get_task_detail=lambda tid: {'success': True, 'message': 'ok', 'data': {
            'id': tid, 'visibility': 'shared', 'created_by_user_id': 100}},
        start=lambda tid: {'success': True, 'message': 'ok', 'data': {'task_id': tid}},
        retry=lambda tid, data: {'success': True, 'message': 'ok', 'data': {'task_id': tid}},
        control=lambda tid, data: {'success': True, 'message': 'ok', 'data': {'task_id': tid}},
        stop=lambda tid: {'success': True, 'message': 'ok', 'data': None},
        reextract=lambda tid, data: {'success': True, 'message': 'ok',
                                     'data': {'task_id': tid, 'reextracted_cases': []}},
        remove_case=lambda tid, cid: {'success': True, 'message': 'ok',
                                      'data': {'task_id': tid, 'case_id': cid,
                                               'removed': True, 'idempotent': False,
                                               'purged': False, 'report_requeued': False}},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestGateway403Mapping:
    """网关生命周期路径：下游 code=403 → HTTP 403（INT-573）。"""

    _BODY_FOR = {'control': {'action': 'pause'},
                 'reextract': {'task_id': 5, 'executionStatus': 'completed'}}

    def _run_denied(self, method_name, *args):
        """monkeypatch _task_acl 返回 code=403，跑网关方法并断言 HTTP 403。

        信封按真实 gRPC 代理形状（失败 code 内嵌 data，经代理 _resp 提升顶层——
        INT-982 P1-1 修复后与真实序列化链一致）。
        """
        acl = _gw_acl(**{method_name: (lambda *a, **k: {
            'success': False, 'message': '资源不存在或无权访问',
            'data': {'code': 403}, 'code': 403})})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch.object(gw_lifecycle_mod, '_audit_task_private_operation'):
            set_current_request(_fake_gw_request(
                user_id=200, permissions=['task:execute'],
                json_body=self._BODY_FOR.get(method_name)))
            try:
                body, http_code = getattr(
                    gw_lifecycle_mod.TaskLifecycleService, method_name)(*args)
            finally:
                set_current_request(None)
        assert http_code == 403
        assert body['code'] == 403

    def test_start_maps_403(self):
        self._run_denied('start', 5)

    def test_retry_maps_403(self):
        self._run_denied('retry', 5)

    def test_control_maps_403(self):
        self._run_denied('control', 5)

    def test_stop_maps_403(self):
        self._run_denied('stop', 5)

    def test_remove_case_maps_403(self):
        self._run_denied('remove_case', 5, 'c1')

    def test_reextract_maps_403(self):
        self._run_denied('reextract', 5)

    def test_not_found_maps_404(self):
        acl = _gw_acl(**{'start': lambda tid: {
            'success': False, 'message': '任务 ID 不存在', 'code': 404}})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch.object(gw_lifecycle_mod, '_audit_task_private_operation'):
            set_current_request(_fake_gw_request(user_id=200))
            try:
                body, http_code = gw_lifecycle_mod.TaskLifecycleService.start(5)
            finally:
                set_current_request(None)
        assert http_code == 404

    def test_business_error_stays_400(self):
        acl = _gw_acl(**{'start': lambda tid: {
            'success': False, 'message': '环境预检失败', 'code': 400}})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch.object(gw_lifecycle_mod, '_audit_task_private_operation'):
            set_current_request(_fake_gw_request(user_id=200))
            try:
                body, http_code = gw_lifecycle_mod.TaskLifecycleService.start(5)
            finally:
                set_current_request(None)
        assert http_code == 400


class TestGatewayAdminAudit:
    """admin 操作私有任务 → PRIVATE_RESOURCE_ACCESS 审计（旁路）。"""

    def _run(self, method_name, acl, action, *args):
        """预取私有态（admin）→ 操作成功 → 断言审计落 write_private_access_audit。"""
        calls = []
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch('api_gateway.application.services.visibility.visibility_audit'
                      '.write_private_access_audit',
                      side_effect=lambda *a, **k: calls.append((a, k))):
            # admin 请求（permissions 含 '*'）
            set_current_request(_fake_gw_request(user_id=999, permissions=['*']))
            try:
                resp = getattr(gw_lifecycle_mod.TaskLifecycleService, method_name)(*args)
            finally:
                set_current_request(None)
        assert resp[1] == 200
        assert calls, f'admin 操作私有任务应落 PRIVATE_RESOURCE_ACCESS 审计（{action}）'
        args, kwargs = calls[0]
        assert args[0] == 'task'
        assert args[1] == 5
        assert args[2] == action

    def test_admin_start_private_writes_audit(self):
        acl = _gw_acl(
            get_task_detail=lambda tid: {'success': True, 'message': 'ok', 'data': {
                'id': tid, 'visibility': 'private', 'created_by_user_id': 100}})
        self._run('start', acl, 'start', 5)

    def test_admin_stop_private_writes_audit(self):
        acl = _gw_acl(
            get_task_detail=lambda tid: {'success': True, 'message': 'ok', 'data': {
                'id': tid, 'visibility': 'private', 'created_by_user_id': 100}})
        self._run('stop', acl, 'stop', 5)

    def test_admin_shared_no_audit(self):
        """admin 操作共享任务：不落审计。"""
        acl = _gw_acl(
            get_task_detail=lambda tid: {'success': True, 'message': 'ok', 'data': {
                'id': tid, 'visibility': 'shared', 'created_by_user_id': 100}})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch('api_gateway.application.services.visibility.visibility_audit'
                      '.write_private_access_audit') as w:
            set_current_request(_fake_gw_request(user_id=999, permissions=['*']))
            try:
                resp = gw_lifecycle_mod.TaskLifecycleService.start(5)
            finally:
                set_current_request(None)
        assert resp[1] == 200
        w.assert_not_called()

    def test_non_admin_private_no_audit(self):
        """非 admin 操作私有任务：不预取、不落审计（旁路短路）。"""
        acl = _gw_acl(
            get_task_detail=lambda tid: {'success': True, 'message': 'ok', 'data': {
                'id': tid, 'visibility': 'private', 'created_by_user_id': 100}})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch('api_gateway.application.services.visibility.visibility_audit'
                      '.write_private_access_audit') as w:
            set_current_request(_fake_gw_request(user_id=200, permissions=['task:execute']))
            try:
                resp = gw_lifecycle_mod.TaskLifecycleService.stop(5)
            finally:
                set_current_request(None)
        assert resp[1] == 200
        w.assert_not_called()


# ---------------- 8. legacy /api/v1/execution/ 直连路径防旁路 ----------------

class TestLegacyExecutionRouteGuard:
    """legacy ExecutionService（直连执行引擎，不经过 task_lifecycle_service）防旁路。

    INT-573：该路径私有任务非 owner 拦截 403，避免绕过 task 侧 owner 校验。
    """

    import api_gateway.application.services.execution_service as exec_mod

    def _run_start(self, acl_detail, user_id, permissions):
        acl = SimpleNamespace(
            get_task_detail=lambda tid: {'success': True, 'data': acl_detail},
            start_task=lambda app, tid: SimpleNamespace(success=True, message='ok'),
        )
        with patch.object(self.exec_mod, '_task_acl', acl), \
                patch.object(self.exec_mod, '_execution_acl',
                             SimpleNamespace(start_task=acl.start_task,
                                             control_task=lambda app, tid, action:
                                             SimpleNamespace(success=True, message='ok'))):
            set_current_request(_fake_gw_request(user_id=user_id, permissions=permissions))
            try:
                body, http_code = self.exec_mod.ExecutionService.start(5)
            finally:
                set_current_request(None)
        return body, http_code

    def test_private_non_owner_start_403(self):
        body, http_code = self._run_start(
            {'id': 5, 'visibility': 'private', 'created_by_user_id': 100},
            user_id=200, permissions=['task:execute'])
        assert http_code == 403
        assert body['code'] == 403

    def test_private_owner_start_passes_guard(self):
        body, http_code = self._run_start(
            {'id': 5, 'visibility': 'private', 'created_by_user_id': 100},
            user_id=100, permissions=['task:execute'])
        # 越过 owner 校验后按 legacy 逻辑走（无 pending 用例 → 业务 400，非 403）
        assert http_code != 403

    def test_private_admin_start_passes_guard(self):
        body, http_code = self._run_start(
            {'id': 5, 'visibility': 'private', 'created_by_user_id': 100},
            user_id=999, permissions=['*'])
        assert http_code != 403

    def test_shared_non_owner_start_passes_guard(self):
        body, http_code = self._run_start(
            {'id': 5, 'visibility': 'shared', 'created_by_user_id': 100},
            user_id=200, permissions=['task:execute'])
        assert http_code != 403

    def test_private_non_owner_control_403(self):
        acl = SimpleNamespace(
            get_task_detail=lambda tid: {'success': True, 'data': {
                'id': 5, 'visibility': 'private', 'created_by_user_id': 100}},
            control_task=lambda app, tid, action: SimpleNamespace(success=True, message='ok'),
        )
        with patch.object(self.exec_mod, '_task_acl', acl), \
                patch.object(self.exec_mod, '_execution_acl',
                             SimpleNamespace(control_task=acl.control_task)):
            set_current_request(_fake_gw_request(
                user_id=200, permissions=['task:execute'], json_body={'action': 'pause'}))
            try:
                body, http_code = self.exec_mod.ExecutionService.control(5)
            finally:
                set_current_request(None)
        assert http_code == 403
        assert body['code'] == 403


# ---------------- 9. 详情 DTO 契约：visibility / created_by_user_id ----------------

class TestTaskDetailDtoVisibilityFields:
    """详情 DTO 契约（INT-982 P1-2 回归）：detail 数据须含 visibility / created_by_user_id。

    网关侧 admin 私有任务审计预取（preload_private_state）与 legacy
    /api/v1/execution/ 防旁路守卫（_check_execution_visible）都依赖这两个字段；
    此前详情 DTO 缺该两键导致真实链路审计永不落库、legacy 守卫形同虚设。
    """

    def test_private_detail_carries_visibility_and_owner(self):
        _set_user(100)
        tid = _make_task(100)
        _set_task_visibility(tid, 'private')
        _set_user(999, is_admin=True)
        from task_service.infrastructure.read_models.task_read_model import TaskReadModel
        dto = TaskReadModel().find_by_id_with_relations(tid)
        assert dto is not None
        assert dto['visibility'] == 'private'
        assert dto['created_by_user_id'] == 100

    def test_shared_detail_carries_visibility_and_owner(self):
        _set_user(100)
        tid = _make_task(100)
        _set_user(999, is_admin=True)
        from task_service.infrastructure.read_models.task_read_model import TaskReadModel
        dto = TaskReadModel().find_by_id_with_relations(tid)
        assert dto is not None
        assert dto['visibility'] == 'shared'
        assert dto['created_by_user_id'] == 100


# ---------------- 10. 跨两端 _resp 真实序列化链（P1-1 回归） ----------------

class TestGrpcSerializationChain:
    """应用层失败信封 → servicer `_resp` → proto → 网关代理 `_resp` 的真实链路。

    INT-982 P1-1 回归：失败 code 必须经 gRPC data JSON 透传（proto 仅
    success/message/data 三字段），网关 `_resp` 提升顶层 code 后映射 HTTP
    403/404。此前 data=None 导致 code 在序列化链丢失、网关误映射 HTTP 400。
    """

    @staticmethod
    def _through_chain(result):
        """应用层失败信封经两端 `_resp` 的真实序列化，返回网关侧结果 dict。"""
        from task_service.interfaces.grpc.task_config import TaskConfigServiceServicer
        from api_gateway.infrastructure.grpc_proxies.task_testcase_config_proxies import _TaskConfigProxy
        proto = TaskConfigServiceServicer._resp(result)
        return _TaskConfigProxy()._resp(proto)

    def test_403_survives_serialization(self):
        result = self._through_chain(
            {'success': False, 'message': '资源不存在或无权访问', 'data': {'code': 403}, 'code': 403})
        assert result['success'] is False
        assert result['code'] == 403
        assert result['data']['code'] == 403

    def test_404_survives_serialization(self):
        result = self._through_chain(
            {'success': False, 'message': '未找到任务', 'data': {'code': 404}, 'code': 404})
        assert result['code'] == 404

    def test_400_survives_serialization(self):
        result = self._through_chain(
            {'success': False, 'message': '环境预检失败', 'data': {'code': 400}, 'code': 400})
        assert result['code'] == 400

    def test_real_denied_chain_maps_http_403(self):
        """真实链路端到端：应用层 403 信封经序列化链 → 网关 `_task_acl` → HTTP 403。

        把网关测试从 mock `_task_acl` 下沉到真实序列化链：_task_acl 返回的即
        是两端 `_resp` 的真实产物，不再手工捏造顶层 code。
        """
        acl = _gw_acl(**{'start': lambda tid: self._through_chain(
            {'success': False, 'message': '资源不存在或无权访问',
             'data': {'code': 403}, 'code': 403})})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch.object(gw_lifecycle_mod, '_audit_task_private_operation'):
            set_current_request(_fake_gw_request(
                user_id=200, permissions=['task:execute'], json_body={}))
            try:
                body, http_code = gw_lifecycle_mod.TaskLifecycleService.start(5)
            finally:
                set_current_request(None)
        assert http_code == 403
        assert body['code'] == 403

    def test_real_not_found_chain_maps_http_404(self):
        acl = _gw_acl(**{'start': lambda tid: self._through_chain(
            {'success': False, 'message': '任务 ID 不存在',
             'data': {'code': 404}, 'code': 404})})
        with patch.object(gw_lifecycle_mod, '_task_acl', acl), \
                patch.object(gw_lifecycle_mod, '_audit_task_private_operation'):
            set_current_request(_fake_gw_request(user_id=200))
            try:
                body, http_code = gw_lifecycle_mod.TaskLifecycleService.start(5)
            finally:
                set_current_request(None)
        # 404 路径网关 body 业务码用 ErrorCode.NOT_FOUND（201），HTTP 状态透传 404
        assert http_code == 404

