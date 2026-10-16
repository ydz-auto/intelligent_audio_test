# -*- coding: utf-8 -*-
"""INT-537 验收（拆分①）：实验室 CRUD + 列表 + summary + 资源计数读模型。

覆盖（验收标准 1/3 的单测部分）：
- 仓储：create/get/list/update/delete（软删），list 过滤 status、软删不可见
- 命令服务：create 201 / code 冲突（含软删行）409 / update 404·409 / delete 404·引用 409
- 查询服务：list 信封 items/total/page/per_page/pages 与字段结构、summary 三计数结构
- 资源读模型：lab_id 过滤未就绪（拆分②③）容错为 0；就绪后按 total 计数；
  子资源列表未就绪退化为无过滤透传，就绪后携带 lab_id

DB：进程级 SQLite（tests/conftest.py 注入），按需建 laboratories 表（对齐 migration
202608 add_laboratory_tables 结构），用例间清理。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from shared.models.database import init_db, get_db_session, remove_db_session
from api_gateway.infrastructure.request_adapter import set_current_request
from api_gateway.application.services.laboratory.laboratory_command_service import (
    LaboratoryCommandService,
)
from api_gateway.application.services.laboratory.laboratory_query_service import (
    LaboratoryQueryService,
)
from api_gateway.infrastructure.repositories.laboratory_repository import (
    LaboratoryRepositoryImpl,
)
from api_gateway.infrastructure.read_models.laboratory_resource_read_model import (
    LaboratoryResourceReadModel,
)

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


def _ensure_db():
    global _LAB_TABLE_CREATED
    init_db(pool_size=2)
    if not _LAB_TABLE_CREATED:
        session = get_db_session()
        try:
            session.execute(text(_CREATE_LAB_TABLE))
            session.commit()
        finally:
            remove_db_session()
        _LAB_TABLE_CREATED = True


def _cleanup():
    session = get_db_session()
    try:
        session.execute(text('DELETE FROM laboratories'))
        session.commit()
    finally:
        remove_db_session()


def _fake_request(json_body=None, query=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


def _make_lab(code='LAB-A-01', name='音频测试实验室', status='active'):
    repo = LaboratoryRepositoryImpl()
    lab = repo.create({'code': code, 'name': name, 'status': status})
    get_db_session().commit()
    remove_db_session()
    return lab.id


# ==================== 仓储 ====================

class TestLaboratoryRepository:
    def setup_method(self):
        _ensure_db()
        _cleanup()

    def test_create_and_get(self):
        repo = LaboratoryRepositoryImpl()
        lab = repo.create({'code': 'LAB-A-01', 'name': '音频测试实验室1',
                           'building': 'A栋', 'floor': '2楼', 'room_number': '201',
                           'description': '主实验室', 'status': 'active'})
        get_db_session().commit()
        try:
            got = repo.get(lab.id)
            assert got is not None
            assert got.code == 'LAB-A-01'
            assert got.name == '音频测试实验室1'
            assert got.building == 'A栋' and got.floor == '2楼'
            assert got.status.value == 'active'
            assert got.deleted is False
        finally:
            remove_db_session()

    def test_list_status_filter_and_order(self):
        _make_lab('LAB-A-01', '一', 'active')
        _make_lab('LAB-A-02', '二', 'inactive')
        repo = LaboratoryRepositoryImpl()
        items, total = repo.list(status='active', page=1, per_page=20)
        assert total == 1
        assert [it.code for it in items] == ['LAB-A-01']
        items_all, total_all = repo.list(status=None, page=1, per_page=20)
        assert total_all == 2

    def test_list_pagination(self):
        for i in range(5):
            _make_lab(f'LAB-P-{i}', f'分页{i}')
        repo = LaboratoryRepositoryImpl()
        items, total = repo.list(status=None, page=2, per_page=2)
        assert total == 5
        assert len(items) == 2

    def test_get_by_code_includes_soft_deleted(self):
        lab_id = _make_lab('LAB-S-01', '软删冲突')
        repo = LaboratoryRepositoryImpl()
        repo.delete(lab_id, deleted_by_user_id=1)
        get_db_session().commit()
        try:
            # 软删后 get 不可见，但 get_by_code 仍命中（唯一冲突语义）
            assert repo.get(lab_id) is None
            assert repo.get_by_code('LAB-S-01') is not None
        finally:
            remove_db_session()

    def test_update_partial_fields(self):
        lab_id = _make_lab('LAB-U-01', '原名')
        repo = LaboratoryRepositoryImpl()
        updated = repo.update(lab_id, {'name': '改名', 'status': 'maintenance'})
        get_db_session().commit()
        try:
            assert updated.name == '改名'
            assert updated.status.value == 'maintenance'
            got = repo.get(lab_id)
            assert got.code == 'LAB-U-01'  # 未提供的字段保持
        finally:
            remove_db_session()

    def test_delete_soft_and_get_none(self):
        lab_id = _make_lab('LAB-D-01', '待删')
        repo = LaboratoryRepositoryImpl()
        assert repo.delete(lab_id, deleted_by_user_id=7) is True
        get_db_session().commit()
        try:
            assert repo.get(lab_id) is None
            assert repo.delete(lab_id) is False  # 已软删二次删除 False
        finally:
            remove_db_session()


# ==================== 命令服务 ====================

class TestLaboratoryCommandService:
    def setup_method(self):
        _ensure_db()
        _cleanup()

    def test_create_success_201(self):
        set_current_request(_fake_request(json_body={
            'code': 'LAB-A-01', 'name': '音频测试实验室1',
            'building': 'A栋', 'floor': '2楼', 'room_number': '201',
            'status': 'active'}))
        try:
            payload, http_code = LaboratoryCommandService.create()
        finally:
            set_current_request(None)
        assert http_code == 201
        assert payload['success'] is True
        assert 'id' in payload['data']
        got = LaboratoryRepositoryImpl().get(payload['data']['id'])
        assert got.code == 'LAB-A-01' and got.status.value == 'active'

    def test_create_code_conflict_409(self):
        _make_lab('LAB-A-01', '已存在')
        set_current_request(_fake_request(json_body={
            'code': 'LAB-A-01', 'name': '重复'}))
        try:
            payload, http_code = LaboratoryCommandService.create()
        finally:
            set_current_request(None)
        assert http_code == 409
        assert payload['success'] is False

    def test_create_code_conflict_with_soft_deleted_409(self):
        """软删行 code 唯一索引未过滤 deleted：重建同名按 409 处理（父卡 §6 风险）。"""
        lab_id = _make_lab('LAB-A-01', '将被软删')
        repo = LaboratoryRepositoryImpl()
        repo.delete(lab_id, deleted_by_user_id=1)
        get_db_session().commit()
        try:
            set_current_request(_fake_request(json_body={
                'code': 'LAB-A-01', 'name': '重建同名'}))
            try:
                payload, http_code = LaboratoryCommandService.create()
            finally:
                set_current_request(None)
            assert http_code == 409
        finally:
            remove_db_session()

    def test_create_invalid_status_400(self):
        set_current_request(_fake_request(json_body={
            'code': 'LAB-X-01', 'name': '非法状态', 'status': 'bogus'}))
        try:
            payload, http_code = LaboratoryCommandService.create()
        finally:
            set_current_request(None)
        assert http_code == 400
        assert payload['success'] is False

    def test_update_success_200(self):
        lab_id = _make_lab('LAB-U-01', '原名')
        set_current_request(_fake_request(json_body={
            'name': '改名', 'status': 'inactive'}))
        try:
            payload, http_code = LaboratoryCommandService.update(lab_id)
        finally:
            set_current_request(None)
        assert http_code == 200
        got = LaboratoryRepositoryImpl().get(lab_id)
        assert got.name == '改名' and got.status.value == 'inactive'

    def test_update_not_found_404(self):
        set_current_request(_fake_request(json_body={'name': '改'}))
        try:
            payload, http_code = LaboratoryCommandService.update(999999)
        finally:
            set_current_request(None)
        assert http_code == 404

    def test_update_code_conflict_409(self):
        _make_lab('LAB-U-01', '源')
        _make_lab('LAB-U-02', '占用 code')
        set_current_request(_fake_request(json_body={'code': 'LAB-U-02'}))
        try:
            payload, http_code = LaboratoryCommandService.update(
                LaboratoryRepositoryImpl().get_by_code('LAB-U-01').id)
        finally:
            set_current_request(None)
        assert http_code == 409

    def test_delete_success_and_soft(self):
        lab_id = _make_lab('LAB-D-01', '待删')
        set_current_request(_fake_request())
        try:
            payload, http_code = LaboratoryCommandService.delete(lab_id)
        finally:
            set_current_request(None)
        assert http_code == 200
        assert LaboratoryRepositoryImpl().get(lab_id) is None

    def test_delete_not_found_404(self):
        set_current_request(_fake_request())
        try:
            payload, http_code = LaboratoryCommandService.delete(999999)
        finally:
            set_current_request(None)
        assert http_code == 404

    def test_delete_referenced_409(self, monkeypatch):
        """删除前引用校验：设备/播放设备/用例任一引用计数 > 0 → 409。"""
        lab_id = _make_lab('LAB-R-01', '有引用')
        monkeypatch.setattr(
            LaboratoryResourceReadModel, 'counts',
            staticmethod(lambda lab_id_: {
                'device_count': 1, 'playback_device_count': 0, 'test_case_count': 0}))
        set_current_request(_fake_request())
        try:
            payload, http_code = LaboratoryCommandService.delete(lab_id)
        finally:
            set_current_request(None)
        assert http_code == 409
        assert payload['success'] is False
        # 409 时未软删
        assert LaboratoryRepositoryImpl().get(lab_id) is not None


# ==================== 查询服务 ====================

class TestLaboratoryQueryService:
    def setup_method(self):
        _ensure_db()
        _cleanup()

    def test_list_envelope_and_item_fields(self):
        # 全字段填充：响应经 success_response（model_dump exclude_none=True），
        # 空字段会被省略（网关既有行为），故用非空值断言字段结构完整
        repo = LaboratoryRepositoryImpl()
        repo.create({'code': 'LAB-A-01', 'name': '音频测试实验室1',
                     'building': 'A栋', 'floor': '2楼', 'room_number': '201',
                     'description': '主实验室', 'status': 'active'})
        get_db_session().commit()
        remove_db_session()
        set_current_request(_fake_request(query={'page': '1', 'per_page': '20'}))
        try:
            payload, http_code = LaboratoryQueryService.list()
        finally:
            set_current_request(None)
        assert http_code == 200
        data = payload['data']
        assert {'items', 'total', 'page', 'per_page', 'pages'} <= set(data)
        assert data['total'] == 1 and data['page'] == 1 and data['per_page'] == 20
        item = data['items'][0]
        assert {'id', 'code', 'name', 'building', 'floor', 'room_number',
                'description', 'status', 'device_count', 'playback_device_count',
                'test_case_count'} <= set(item)
        assert item['code'] == 'LAB-A-01'
        assert item['status'] == 'active'
        assert item['building'] == 'A栋' and item['room_number'] == '201'
        # counts 未就绪容错为 0（拆分②③ RPC lab_id 过滤未合入）
        assert item['device_count'] == 0
        assert item['playback_device_count'] == 0
        assert item['test_case_count'] == 0

    def test_list_soft_deleted_invisible(self):
        lab_id = _make_lab('LAB-A-01', '将被软删')
        LaboratoryRepositoryImpl().delete(lab_id, deleted_by_user_id=1)
        get_db_session().commit()
        try:
            set_current_request(_fake_request(query={'page': '1'}))
            try:
                payload, _ = LaboratoryQueryService.list()
            finally:
                set_current_request(None)
            assert payload['data']['total'] == 0
        finally:
            remove_db_session()

    def test_get_404(self):
        set_current_request(_fake_request())
        try:
            payload, http_code = LaboratoryQueryService.get(999999)
        finally:
            set_current_request(None)
        assert http_code == 404

    def test_sub_resources_404_when_lab_missing(self):
        """按实验室查资源：实验室不存在 → 404（不返回空列表误导）。"""
        set_current_request(_fake_request(query={'page': '1'}))
        try:
            for method in (LaboratoryQueryService.devices,
                           LaboratoryQueryService.playback_devices,
                           LaboratoryQueryService.test_cases):
                payload, http_code = method(999999)
                assert http_code == 404
                assert payload['success'] is False
        finally:
            set_current_request(None)

    def test_sub_resources_return_list_when_lab_exists(self, monkeypatch):
        """实验室存在时子资源列表走读模型透传（lab_id 过滤未就绪退化为无过滤）。"""
        lab_id = _make_lab('LAB-SUB-01', '子资源实验室')
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeNoLabId:
            def get_all(self, page=1, per_page=10, keyword=''):
                return {'success': True, 'data': {
                    'items': [{'id': 11, 'name': 'd11'}], 'total': 1,
                    'page': page, 'per_page': per_page}}

        class _FakeNoLabIdTestCase:
            def list_testcases(self, page=1, per_page=10, algorithm_type=''):
                return {'success': True, 'data': {
                    'items': [{'id': 'c11', 'name': 'c11'}], 'total': 1,
                    'page': page, 'per_page': per_page}}

        monkeypatch.setattr(proxies_pkg, 'device_config_service', _FakeNoLabId())
        monkeypatch.setattr(proxies_pkg, 'playback_config_service', _FakeNoLabId())
        monkeypatch.setattr(proxies_pkg, 'testcase_config_service', _FakeNoLabIdTestCase())
        set_current_request(_fake_request(query={'page': '1', 'per_page': '10'}))
        try:
            _, code_dev = LaboratoryQueryService.devices(lab_id)
            _, code_pb = LaboratoryQueryService.playback_devices(lab_id)
            _, code_tc = LaboratoryQueryService.test_cases(lab_id)
            payload, code_ok = LaboratoryQueryService.devices(lab_id)
        finally:
            set_current_request(None)
        assert code_dev == 200 and code_pb == 200 and code_tc == 200
        assert payload['data']['total'] == 1

    def test_summary_three_counts_structure(self):
        lab_id = _make_lab('LAB-A-01', '统计实验室')
        set_current_request(_fake_request())
        try:
            payload, http_code = LaboratoryQueryService.summary(lab_id)
        finally:
            set_current_request(None)
        assert http_code == 200
        data = payload['data']
        assert {'device_count', 'playback_device_count', 'test_case_count'} <= set(data)


# ==================== 资源读模型 ====================

class TestLaboratoryResourceReadModel:
    """计数经 gRPC 聚合：lab_id 过滤未就绪（拆分②③）容错为 0；就绪后取 total。"""

    def test_counts_zero_when_lab_id_filter_not_supported(self, monkeypatch):
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeNoLabId:
            def get_all(self, page=1, per_page=1):
                return {'success': True, 'data': {'total': 999}}

        class _FakeNoLabIdTestCase:
            def list_testcases(self, page=1, per_page=1):
                return {'success': True, 'data': {'total': 999}}

        monkeypatch.setattr(proxies_pkg, 'device_config_service', _FakeNoLabId())
        monkeypatch.setattr(proxies_pkg, 'playback_config_service', _FakeNoLabId())
        monkeypatch.setattr(proxies_pkg, 'testcase_config_service', _FakeNoLabIdTestCase())
        counts = LaboratoryResourceReadModel.counts(1)
        assert counts == {
            'device_count': 0, 'playback_device_count': 0, 'test_case_count': 0}

    def test_counts_when_lab_id_supported(self, monkeypatch):
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeWithLabId:
            def __init__(self):
                self.captured = []

            def get_all(self, page=1, per_page=1, lab_id=None):
                self.captured.append(lab_id)
                return {'success': True, 'data': {'total': 5}}

        class _FakeWithLabIdTestCase:
            def __init__(self):
                self.captured = []

            def list_testcases(self, page=1, per_page=1, lab_id=None):
                self.captured.append(lab_id)
                return {'success': True, 'data': {'total': 120}}

        dev = _FakeWithLabId()
        pb = _FakeWithLabId()
        tc = _FakeWithLabIdTestCase()
        monkeypatch.setattr(proxies_pkg, 'device_config_service', dev)
        monkeypatch.setattr(proxies_pkg, 'playback_config_service', pb)
        monkeypatch.setattr(proxies_pkg, 'testcase_config_service', tc)
        counts = LaboratoryResourceReadModel.counts(7)
        assert counts == {
            'device_count': 5, 'playback_device_count': 5, 'test_case_count': 120}
        assert dev.captured == [7] and pb.captured == [7] and tc.captured == [7]

    def test_counts_service_unavailable_fallback_zero(self, monkeypatch):
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeError:
            def get_all(self, **kwargs):
                raise RuntimeError('gRPC 服务不可用')

        class _FakeErrorTestCase:
            def list_testcases(self, **kwargs):
                raise RuntimeError('gRPC 服务不可用')

        monkeypatch.setattr(proxies_pkg, 'device_config_service', _FakeError())
        monkeypatch.setattr(proxies_pkg, 'playback_config_service', _FakeError())
        monkeypatch.setattr(proxies_pkg, 'testcase_config_service', _FakeErrorTestCase())
        counts = LaboratoryResourceReadModel.counts(1)
        assert counts == {
            'device_count': 0, 'playback_device_count': 0, 'test_case_count': 0}

    def test_list_devices_degrades_without_lab_id(self, monkeypatch):
        """子资源列表：RPC 未支持 lab_id 时退化为无过滤透传（路由骨架语义）。"""
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeNoLabId:
            def get_all(self, page=1, per_page=10, keyword=''):
                return {'success': True, 'data': {
                    'items': [{'id': 1, 'name': 'd1'}], 'total': 1,
                    'page': page, 'per_page': per_page}}

        monkeypatch.setattr(proxies_pkg, 'device_config_service', _FakeNoLabId())
        data = LaboratoryResourceReadModel.list_devices(9, page=1, per_page=10)
        assert data['total'] == 1

    def test_list_devices_passes_lab_id_when_supported(self, monkeypatch):
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _FakeWithLabId:
            def __init__(self):
                self.captured = {}

            def get_all(self, page=1, per_page=10, keyword='', lab_id=None):
                self.captured = {'page': page, 'per_page': per_page, 'lab_id': lab_id}
                return {'success': True, 'data': {
                    'items': [{'id': 2, 'name': 'd2'}], 'total': 1,
                    'page': page, 'per_page': per_page}}

        fake = _FakeWithLabId()
        monkeypatch.setattr(proxies_pkg, 'device_config_service', fake)
        data = LaboratoryResourceReadModel.list_devices(3, page=1, per_page=10)
        assert data['total'] == 1
        assert fake.captured['lab_id'] == 3
        assert fake.captured['page'] == 1
