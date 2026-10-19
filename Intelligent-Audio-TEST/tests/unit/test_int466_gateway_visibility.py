# -*- coding: utf-8 -*-
"""INT-466 专项：api_gateway 数据可见性路由层（share 端点 + PRIVATE_RESOURCE_ACCESS 审计 + 字段透出）。

覆盖验收标准（网关侧）：
1. 6 个资源:share 端点（task/testcase/group/tag/report/dimension；audios 不走独立
   端点）：非 owner 403、owner 切换 shared↔private 生效、非法值 400
2. admin 豁免：admin 可切换任意资源可见性
3. PRIVATE_RESOURCE_ACCESS 审计：admin 访问私有资源详情落审计（旁路）
4. 网关响应透出 visibility/created_by_user_id（前端徽标 / owner 判定）

DB：进程级 SQLite（tests/conftest.py 注入），纯网关侧单测不落业务表。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.infrastructure.request_adapter import set_current_request
from api_gateway.application.services.visibility.visibility_service import VisibilityService
from api_gateway.application.services.visibility import visibility_service as vis_mod
from api_gateway.application.services.task import task_query_service as task_qs_mod
from api_gateway.application.services.testcase import testcase_query_service as tc_qs_mod
from api_gateway.application.services.report import report_query_sevice as rpt_qs_mod
from api_gateway.application.services.evaluation import evaluation_query_service as eva_qs_mod
from api_gateway.application.services.tag import tag_query_service as tag_qs_mod
from api_gateway.infrastructure.acl import config_acl_repository as acl_mod


# ---------------- 工具 ----------------

def _fake_request(user_id=100, permissions=None, username='dev_user', json_body=None):
    state = SimpleNamespace(
        user_id=user_id,
        permissions=list(permissions or []),
        username=username,
        role_id=1,
        _json_body=json_body or {},
    )
    return SimpleNamespace(state=state, query_params={})


class _Recorder:
    """记录 ACL/查询调用与审计写入的桩。"""

    def __init__(self):
        self.calls = []
        self.audit_rows = []

    def update(self, *args, **kwargs):
        self.calls.append(('update', args, kwargs))
        return {'success': True, 'message': 'ok', 'data': None}

    def update_tag(self, *args, **kwargs):
        self.calls.append(('update_tag', args, kwargs))
        return {'success': True, 'message': 'ok', 'data': None}

    def update_dimension(self, *args, **kwargs):
        self.calls.append(('update_dimension', args, kwargs))
        return {'success': True, 'message': 'ok', 'data': {'id': args[0]}}


def _detail_payload(resource_type, rid, owner, visibility):
    """构造详情响应 data（模拟下游 read model 透出 visibility/owner）。"""
    if resource_type == 'task':
        return {
            'id': rid, 'name': '任务', 'status': 'completed',
            'visibility': visibility, 'created_by_user_id': owner,
            'cases': [], 'devices': [], 'apis': [],
        }
    if resource_type == 'testcase':
        return {
            'id': rid, 'name': '用例', 'config': {},
            'visibility': visibility, 'created_by_user_id': owner,
            'audios': [], 'dimensions': [],
        }
    if resource_type == 'report':
        return {
            'id': rid, 'name': '报告', 'type': 'task', 'status': 'published',
            'visibility': visibility, 'created_by_user_id': owner,
        }
    if resource_type == 'dimension':
        return {
            'id': rid, 'name': '维度', 'visibility': visibility,
            'created_by_user_id': owner,
        }
    if resource_type == 'tag':
        return {
            'id': rid, 'name': '标签', 'visibility': visibility,
            'created_by_user_id': owner,
        }
    return {}


def _stub_detail(monkeypatch, mod, resource_type, owner, visibility, rid=5):
    """stub 查询服务 get_one 返回固定详情（透出 visibility/owner）。"""
    def _get_one(resource_id):
        return ({'success': True, 'message': '',
                 'data': _detail_payload(resource_type, resource_id, owner, visibility)}, 200)
    monkeypatch.setattr(mod, 'get_one', _get_one)


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    set_current_request(None)


# ---------------- share 端点：owner / 非 owner / admin / 非法值 ----------------

class TestTaskShareEndpoint:
    def test_owner_can_toggle_task_visibility(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'shared')
        monkeypatch.setattr(acl_mod.TaskConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_task_visibility(5, 'private')
        assert http_code == 200
        assert payload['data']['visibility'] == 'private'
        assert rec.calls[0][1][1] == {'visibility': 'private'}

    def test_non_owner_gets_403(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'shared')
        monkeypatch.setattr(acl_mod.TaskConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=200))  # 非 owner

        payload, http_code = VisibilityService.update_task_visibility(5, 'private')
        assert http_code == 403
        assert not rec.calls  # 未触发下游写

    def test_admin_exempt_owner_check(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'private')
        monkeypatch.setattr(acl_mod.TaskConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=200, permissions=['*']))  # admin

        payload, http_code = VisibilityService.update_task_visibility(5, 'shared')
        assert http_code == 200
        assert rec.calls

    def test_invalid_visibility_400(self, monkeypatch):
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'shared')
        set_current_request(_fake_request(user_id=100))
        payload, http_code = VisibilityService.update_task_visibility(5, 'public')
        assert http_code == 400


class TestOtherShareEndpoints:
    def test_testcase_owner_toggle(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, tc_qs_mod.TestCaseQueryService, 'testcase', 100, 'shared')
        monkeypatch.setattr(acl_mod.TestCaseConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_testcase_visibility('tc1', 'private')
        assert http_code == 200
        assert rec.calls[0][1][1] == {'visibility': 'private'}

    def test_report_owner_toggle(self, monkeypatch):
        _stub_detail(monkeypatch, rpt_qs_mod.ReportQueryService, 'report', 100, 'shared')

        class _FakeStub:
            def UpdateReport(self, request, context=None):
                self.request = request
                return SimpleNamespace(success=True, message='ok', data='{}')

        fake_stub = _FakeStub()
        from api_gateway.infrastructure.grpc_proxies import report_proxies
        monkeypatch.setattr(
            report_proxies._ReportConfigProxy, 'stub', property(lambda self: fake_stub))
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_report_visibility(7, 'private')
        assert http_code == 200
        assert 'visibility' in fake_stub.request.data

    def test_dimension_non_owner_403(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, eva_qs_mod.EvaluationQueryService, 'dimension', 100, 'private')
        monkeypatch.setattr(acl_mod.EvaluationConfigAclRepositoryImpl, 'update_dimension', rec.update_dimension)
        set_current_request(_fake_request(user_id=200))

        payload, http_code = VisibilityService.update_dimension_visibility(9, 'shared')
        assert http_code == 403
        assert not rec.calls

    def test_tag_non_owner_403(self, monkeypatch):
        rec = _Recorder()
        _stub_detail(monkeypatch, tag_qs_mod.TagQueryService, 'tag', 100, 'private')
        monkeypatch.setattr(acl_mod.TagConfigAclRepositoryImpl, 'update_tag', rec.update_tag)
        set_current_request(_fake_request(user_id=200))

        payload, http_code = VisibilityService.update_tag_visibility(3, 'shared')
        assert http_code == 403
        assert not rec.calls

    def test_group_owner_toggle(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies import task_data_service

        calls = []
        monkeypatch.setattr(task_data_service, 'get_testcase_group_by_id',
                            lambda gid: {'id': gid, 'name': 'g',
                                         'visibility': 'shared', 'created_by_user_id': 100})
        monkeypatch.setattr(task_data_service, 'update_testcase_group',
                            lambda group_id, visibility: calls.append(visibility) or {'id': group_id})
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_group_visibility('g1', 'private')
        assert http_code == 200
        assert calls == ['private']


# ---------------- 审计：share 切换触碰私有态 ----------------

class TestShareAudit:
    def test_owner_private_toggle_writes_audit(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = []
        monkeypatch.setattr(vis_audit_mod, 'write_private_access_audit',
                            lambda *a, **kw: rows.append((a, kw)))
        rec = _Recorder()
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'shared')
        monkeypatch.setattr(acl_mod.TaskConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_task_visibility(5, 'private')
        assert http_code == 200
        assert rows, 'shared→private 切换触碰私有态应落审计'
        assert rows[0][0][2] == 'update_visibility'

    def test_shared_to_shared_no_audit(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = []
        monkeypatch.setattr(vis_audit_mod, 'write_private_access_audit',
                            lambda *a, **kw: rows.append((a, kw)))
        rec = _Recorder()
        _stub_detail(monkeypatch, task_qs_mod.TaskQueryService, 'task', 100, 'shared')
        monkeypatch.setattr(acl_mod.TaskConfigAclRepositoryImpl, 'update', rec.update)
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_task_visibility(5, 'shared')
        assert http_code == 200
        assert not rows


# ---------------- 审计：admin 访问私有资源 ----------------

class TestPrivateAccessAudit:
    def test_admin_detail_read_private_task_writes_audit(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = []
        monkeypatch.setattr(vis_audit_mod, 'write_private_access_audit',
                            lambda *a, **kw: rows.append((a, kw)))
        monkeypatch.setattr(task_qs_mod, '_task_acl',
                            SimpleNamespace(
                                get_task_detail=lambda task_id: {
                                    'success': True, 'data': _detail_payload('task', task_id, 100, 'private')}))
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        payload, http_code = task_qs_mod.TaskQueryService.get_one(5)
        assert http_code == 200
        assert rows, 'admin 访问私有任务应落 PRIVATE_RESOURCE_ACCESS 审计'
        assert rows[0][0][2] == 'read'

    def test_non_admin_read_private_task_no_audit(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = []
        monkeypatch.setattr(vis_audit_mod, 'write_private_access_audit',
                            lambda *a, **kw: rows.append((a, kw)))
        monkeypatch.setattr(task_qs_mod, '_task_acl',
                            SimpleNamespace(
                                get_task_detail=lambda task_id: {
                                    'success': True, 'data': _detail_payload('task', task_id, 100, 'private')}))
        set_current_request(_fake_request(user_id=200, permissions=['testcase:read']))

        payload, http_code = task_qs_mod.TaskQueryService.get_one(5)
        assert http_code == 200
        assert not rows


# ---------------- 字段透出 ----------------

class TestFieldExposure:
    def test_task_detail_exposes_visibility_and_owner(self, monkeypatch):
        monkeypatch.setattr(task_qs_mod, '_task_acl',
                            SimpleNamespace(
                                get_task_detail=lambda task_id: {
                                    'success': True, 'data': _detail_payload('task', task_id, 100, 'private')}))
        set_current_request(_fake_request(user_id=100))

        payload, http_code = task_qs_mod.TaskQueryService.get_one(5)
        assert http_code == 200
        data = payload['data']
        assert data['visibility'] == 'private'
        assert data['created_by_user_id'] == 100

    def test_task_list_exposes_visibility(self, monkeypatch):
        class _Acl:
            def list_tasks(self, **kwargs):
                return {'success': True, 'data': {
                    'items': [{'id': 1, 'name': 't', 'status': 'completed',
                               'visibility': 'private', 'created_by_user_id': 100}],
                    'total': 1, 'page': 1, 'per_page': 10, 'pages': 1,
                }}

        monkeypatch.setattr(task_qs_mod, '_task_acl', _Acl())
        set_current_request(_fake_request(user_id=100))

        payload, http_code = task_qs_mod.TaskQueryService.get_all()
        assert http_code == 200
        item = payload['data']['items'][0]
        assert item['visibility'] == 'private'
        assert item['created_by_user_id'] == 100


# ---------------- 审计：admin 一般 update/delete 私有资源（P1 收口） ----------------

def _audit_capture(monkeypatch):
    """捕获 write_private_access_audit 调用的桩（返回 rows 列表）。"""
    from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
    rows = []
    monkeypatch.setattr(vis_audit_mod, 'write_private_access_audit',
                        lambda *a, **kw: rows.append((a, kw)))
    return rows


class _CmdRecorder:
    """命令侧桩：预取 get_* 透出 visibility/owner，写操作记录调用并可控制成败。"""

    def __init__(self, detail=None, success=True):
        self.detail = detail or {}
        self.success = success
        self.calls = []

    # 预取 get_*
    def get_task_detail(self, _id):
        return {'success': True, 'data': self.detail}

    def get_testcase_detail(self, _id):
        return {'success': True, 'data': self.detail}

    def get_tag(self, _id):
        return {'success': True, 'data': self.detail}

    def get_category(self, _id):
        return {'success': True, 'data': self.detail}

    def get_dimension(self, _id):
        return {'success': True, 'data': self.detail}

    def get_one(self, _id):
        return {'success': True, 'data': self.detail}

    def list_categories(self):
        return {'success': True, 'data': {'items': [self.detail]} if self.detail else []}

    # 写操作
    def update(self, *a, **kw):
        self.calls.append(('update', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def delete(self, *a, **kw):
        self.calls.append(('delete', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def update_tag(self, *a, **kw):
        self.calls.append(('update_tag', a, kw))
        return {'success': self.success, 'message': 'ok',
                'data': {'id': a[0], 'name': 'x'}}

    def delete_tag(self, *a, **kw):
        self.calls.append(('delete_tag', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def update_category(self, *a, **kw):
        self.calls.append(('update_category', a, kw))
        return {'success': self.success, 'message': 'ok',
                'data': {'id': a[0], 'name': 'x'}}

    def delete_category(self, *a, **kw):
        self.calls.append(('delete_category', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def update_dimension(self, *a, **kw):
        self.calls.append(('update_dimension', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': {'id': a[0]}}

    def delete_dimension(self, *a, **kw):
        self.calls.append(('delete_dimension', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def update_metadata(self, *a, **kw):
        self.calls.append(('update_metadata', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}

    def update_audio_algorithms(self, *a, **kw):
        self.calls.append(('update_audio_algorithms', a, kw))
        return {'success': self.success, 'message': 'ok', 'data': None}


class TestAuditWriteHelpers:
    """maybe_audit_private_write / preload_private_state 行为单测。"""

    def test_admin_private_writes_audit(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = _audit_capture(monkeypatch)
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        vis_audit_mod.maybe_audit_private_write('task', 5, 'update',
                                                {'visibility': 'private'})
        assert rows and rows[0][0][2] == 'update'
        assert rows[0][0][0] == 'task'

    def test_non_admin_skips(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = _audit_capture(monkeypatch)
        set_current_request(_fake_request(user_id=200, permissions=['task:update']))

        vis_audit_mod.maybe_audit_private_write('task', 5, 'update',
                                                {'visibility': 'private'})
        assert not rows

    def test_shared_skips(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        rows = _audit_capture(monkeypatch)
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        vis_audit_mod.maybe_audit_private_write('task', 5, 'delete',
                                                {'visibility': 'shared'})
        assert not rows

    def test_preload_only_fetches_for_admin(self, monkeypatch):
        from api_gateway.application.services.visibility import visibility_audit as vis_audit_mod
        calls = []
        # 非 admin：不应触发 fetch（零额外 gRPC 往返）
        set_current_request(_fake_request(user_id=200, permissions=['task:update']))
        assert vis_audit_mod.preload_private_state(lambda: calls.append(1) or {}) is None
        assert not calls
        # admin：触发 fetch 并返回 data
        set_current_request(_fake_request(user_id=1, permissions=['*']))
        data = vis_audit_mod.preload_private_state(
            lambda: calls.append(1) or {'visibility': 'private'})
        assert data == {'visibility': 'private'}
        assert calls == [1]


class TestAdminWriteAudit:
    """P1：admin 一般 update/delete 私有资源 → PRIVATE_RESOURCE_ACCESS 审计。"""

    def test_admin_update_private_task_writes_audit(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 5, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_task_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.TaskCommandService.update(5)
        assert http_code == 200
        assert rows, 'admin 修改私有任务应落审计'
        assert rows[0][0][0] == 'task' and rows[0][0][2] == 'update'

    def test_admin_delete_private_task_writes_audit(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 5, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_task_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        payload, http_code = cmd_mod.TaskCommandService.delete(5)
        assert http_code == 200
        assert rows and rows[0][0][2] == 'delete'

    def test_admin_update_shared_task_no_audit(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 5, 'visibility': 'shared', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_task_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.TaskCommandService.update(5)
        assert http_code == 200
        assert not rows

    def test_non_admin_update_private_task_no_audit(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 5, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_task_acl', rec)
        set_current_request(_fake_request(user_id=100, permissions=['task:update'],
                                          json_body={'name': 'x'}))

        payload, http_code = cmd_mod.TaskCommandService.update(5)
        assert http_code == 200
        assert not rows

    def test_admin_update_private_task_failed_write_no_audit(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 5, 'visibility': 'private', 'created_by_user_id': 100},
                           success=False)
        monkeypatch.setattr(cmd_mod, '_task_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.TaskCommandService.update(5)
        assert http_code != 200
        assert not rows, '写失败不应落审计'

    def test_admin_delete_private_testcase_writes_audit(self, monkeypatch):
        from api_gateway.application.services.testcase import testcase_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 'tc1', 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_testcase_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        payload, http_code = cmd_mod.TestCaseCommandService.delete('tc1')
        assert http_code == 200
        assert rows and rows[0][0][0] == 'testcase' and rows[0][0][2] == 'delete'

    def test_admin_update_private_tag_writes_audit(self, monkeypatch):
        from api_gateway.application.services.tag import tag_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 3, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_tag_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.TagCommandService.update(3)
        assert http_code == 200
        assert rows and rows[0][0][0] == 'tag' and rows[0][0][2] == 'update'

    def test_admin_update_private_audio_writes_audit(self, monkeypatch):
        from api_gateway.application.services.audio import audio_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 9, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_audio_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.AudioCommandService.update_metadata(9)
        assert http_code == 200
        assert rows and rows[0][0][0] == 'audio' and rows[0][0][2] == 'update'

    def test_admin_delete_private_dimension_writes_audit(self, monkeypatch):
        from api_gateway.application.services.evaluation import evaluation_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 7, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_evaluation_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        payload, http_code = cmd_mod.EvaluationCommandService.delete(7)
        assert http_code == 200
        assert rows and rows[0][0][0] == 'dimension' and rows[0][0][2] == 'delete'

    def test_admin_update_private_category_writes_audit(self, monkeypatch):
        from api_gateway.application.services.evaluation import evaluation_command_service as cmd_mod
        rows = _audit_capture(monkeypatch)
        rec = _CmdRecorder(detail={'id': 2, 'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(cmd_mod, '_evaluation_acl', rec)
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = cmd_mod.EvaluationCommandService.update_category(2)
        assert http_code == 200
        assert rows and rows[0][0][0] == 'category' and rows[0][0][2] == 'update'

    def test_admin_delete_private_report_writes_audit(self, monkeypatch):
        from api_gateway.application.services.report import report_query_sevice as rpt_qs
        from api_gateway.application.services.report import report_command_sevice as cmd_mod
        from api_gateway.infrastructure.grpc_proxies import report_proxies
        rows = _audit_capture(monkeypatch)
        monkeypatch.setattr(
            rpt_qs.ReportQueryService, 'get_one',
            lambda rid: ({'success': True, 'message': '',
                          'data': {'id': rid, 'name': 'r', 'visibility': 'private',
                                   'created_by_user_id': 100}}, 200))

        class _FakeStub:
            def DeleteReport(self, request, context=None):
                self.request = request
                return SimpleNamespace(success=True, message='ok', data='{}')

        fake_stub = _FakeStub()
        monkeypatch.setattr(report_proxies._ReportConfigProxy, 'stub',
                            property(lambda self: fake_stub))
        set_current_request(_fake_request(user_id=1, permissions=['*']))

        payload, http_code = cmd_mod.ReportCommandService.delete(7)
        assert http_code == 200
        assert rows and rows[0][0][0] == 'report' and rows[0][0][2] == 'delete'

    def test_admin_update_private_group_writes_audit(self, monkeypatch):
        from api_gateway.application.services import group_service as grp_mod
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        rows = _audit_capture(monkeypatch)
        monkeypatch.setattr(task_data_service, 'get_testcase_group_by_id',
                            lambda gid: {'id': gid, 'name': 'g',
                                         'visibility': 'private', 'created_by_user_id': 100})
        monkeypatch.setattr(task_data_service, 'update_testcase_group',
                            lambda **kw: {'id': kw.get('group_id')})
        set_current_request(_fake_request(user_id=1, permissions=['*'], json_body={'name': 'x'}))

        payload, http_code = grp_mod.GroupService.update('g1')
        assert http_code == 200
        assert rows and rows[0][0][0] == 'group' and rows[0][0][2] == 'update'


# ---------------- P2：share 端点并发删除分组 → 404，不回显内部异常 ----------------

class TestGroupShareConcurrentDelete:
    def test_group_visibility_concurrent_delete_maps_404(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        monkeypatch.setattr(task_data_service, 'get_testcase_group_by_id',
                            lambda gid: {'id': gid, 'name': 'g',
                                         'visibility': 'shared', 'created_by_user_id': 100})

        def _boom(*a, **kw):
            raise ValueError('group deleted concurrently')

        monkeypatch.setattr(task_data_service, 'update_testcase_group', _boom)
        set_current_request(_fake_request(user_id=100))

        payload, http_code = VisibilityService.update_group_visibility('g1', 'private')
        assert http_code == 404
        assert '不存在' in payload.get('message', '')
        assert 'deleted' not in payload.get('message', '')  # 不回显内部异常文本


# ---------------- ?visibility= 服务端筛选（网关→proto→task_service→SQL） ----------------

_TABLES = None


def _ensure_tables():
    from shared.models.database import Base, init_db, get_engine
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TestCase, TestCaseGroup, Tag, TagCategory, TaskCase,
            TaskDevice, TaskAPI, TaskMergeRelation, TestResult,
            TaskTag, TestCaseTag, Favorite, Log, PublishedTask,
            TaskCherryPickRelation,
        )
        _TABLES = [t.__table__ for t in (
            Task, TestCase, TestCaseGroup, Tag, TagCategory, TaskCase,
            TaskDevice, TaskAPI, TaskMergeRelation, TestResult,
            TaskTag, TestCaseTag, Favorite, Log, PublishedTask,
            TaskCherryPickRelation,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


@pytest.fixture(autouse=True)
def _sqlite_cleanup():
    """为 SQL 筛选用例建表并清空（仅该测试类生效，靠显式调用）。"""
    yield
    from shared.infrastructure.user_context import (
        set_current_user_id, set_current_user_is_admin,
    )
    set_current_user_id(None)
    set_current_user_is_admin(False)


class TestVisibilityServerFilter:
    """INT-466：?visibility= 服务端筛选贯通（task/testcase 列表按 visibility 过滤）。"""

    def _insert_task(self, session, task_id, name, vis, owner):
        from task_service.infrastructure.persistence.models import Task
        from datetime import datetime
        task = Task(
            id=task_id, name=name, status='completed',
            visibility=vis, created_by_user_id=owner,
            created_at=datetime.now(),
        )
        session.add(task)

    def test_search_tasks_visibility_filter(self, monkeypatch):
        _ensure_tables()
        from shared.models.database import get_db_session
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        from task_service.infrastructure.persistence.models import Task

        session = get_db_session()
        try:
            for table in reversed(_TABLES):
                session.execute(table.delete())
            self._insert_task(session, 1, 'shared任务', 'shared', 100)
            self._insert_task(session, 2, 'private任务', 'private', 100)
            session.commit()
        finally:
            session.close()

        # admin 可见全部；visibility='private' 只返回私有行
        from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
        set_current_user_id(100)
        set_current_user_is_admin(True)

        result = task_read_model.search_tasks(visibility='private', page=1, per_page=10)
        items = result['items']
        assert len(items) == 1
        assert items[0]['name'] == 'private任务'
        assert items[0]['visibility'] == 'private'
        assert items[0]['created_by_user_id'] == 100

        result = task_read_model.search_tasks(visibility='shared', page=1, per_page=10)
        items = result['items']
        assert len(items) == 1
        assert items[0]['visibility'] == 'shared'

        # visibility=None（空）→ 全部
        result = task_read_model.search_tasks(page=1, per_page=10)
        assert len(result['items']) == 2

    def test_query_testcases_visibility_filter(self):
        _ensure_tables()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import TestCase

        session = get_db_session()
        try:
            for table in reversed(_TABLES):
                session.execute(table.delete())
            session.add_all([
                TestCase(id='tc1', name='shared用例', visibility='shared',
                         created_by_user_id=100, config={}),
                TestCase(id='tc2', name='private用例', visibility='private',
                         created_by_user_id=100, config={}),
            ])
            session.commit()
        finally:
            session.close()

        from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
        set_current_user_id(100)
        set_current_user_is_admin(True)

        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        result = testcase_repository.query_testcases(visibility='private', page=1, per_page=10)
        assert result.total == 1
        assert result.items[0].name == 'private用例'
