# -*- coding: utf-8 -*-
"""INT-655 专项：实验室（laboratories）命令/查询服务 + gRPC servicer 契约。

覆盖：
- 创建：成功、code/name 必填、code 唯一冲突（409）、status 枚举校验
- 更新：部分更新、code 冲突、未知实验室 404、status 枚举校验
- 删除：软删除、未知实验室 404
- 查询：列表分页 + 资源统计（device_count/playback_device_count/test_case_count）、
  详情 + 统计、summary、未知实验室 404
- servicer：proto 新服务 LaboratoryConfigService 各 RPC 的 {success,message,data,code}
  信封契约（data 为 JSON 串、code 携带业务码）
- 审计 P2 修复：软删后同 code 可复用（部分唯一索引语义）、DB IntegrityError
  映射为显式 409（不泄漏 SQL 报错）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.application.commands.laboratory_command_service import LaboratoryCommandService
from device_service.application.queries.laboratory_query_service import LaboratoryQueryService
from device_service.interfaces.grpc.laboratory_config_servicers import LaboratoryConfigServiceServicer
from device_service.domain.entities import LaboratoryAggregate
from shared.utils.grpc_json import loads as _loads


class FakeLaboratoryRepository:
    """内存实验室仓储（对齐真实仓储语义：软删、code 唯一、计数）"""

    def __init__(self):
        self.labs = {}
        self._seq = 0
        self.devices_by_lab = {}  # lab_id -> int
        self.playback_by_lab = {}  # lab_id -> int
        self.test_cases_by_lab = {}  # lab_id -> int

    def _add(self, data):
        self._seq += 1
        lab = LaboratoryAggregate(
            id=self._seq,
            code=data['code'],
            name=data['name'],
            building=data.get('building'),
            floor=data.get('floor'),
            room_number=data.get('room_number'),
            description=data.get('description'),
            status=data.get('status') or 'active',
        )
        self.labs[self._seq] = lab
        return lab

    def create_laboratory(self, data):
        return self._add(data)

    def update_laboratory(self, lab_id, update_fields):
        lab = self.labs.get(lab_id)
        if not lab or lab.deleted:
            return None
        for key, value in update_fields.items():
            setattr(lab, key, value)
        return lab

    def delete_laboratory(self, lab_id):
        lab = self.labs.get(lab_id)
        if not lab or lab.deleted:
            return False
        lab.deleted = True
        return True

    def get_laboratory(self, lab_id):
        lab = self.labs.get(lab_id)
        if not lab or lab.deleted:
            return None
        return lab

    def get_laboratory_by_code(self, code):
        for lab in self.labs.values():
            if not lab.deleted and lab.code == code:
                return lab
        return None

    def list_laboratories(self, page=1, per_page=10, keyword=None, status=None):
        items = [lab for lab in self.labs.values() if not lab.deleted]
        if keyword:
            items = [lab for lab in items if keyword in lab.code or keyword in lab.name]
        if status:
            items = [lab for lab in items if lab.status == status]
        total = len(items)
        start = (page - 1) * per_page
        page_items = items[start:start + per_page]
        lab_ids = [lab.id for lab in page_items]
        device_counts = self.count_devices(lab_ids)
        playback_counts = self.count_playback_devices(lab_ids)
        testcase_counts = self.count_test_cases(lab_ids)
        result_items = []
        for lab in page_items:
            item = lab.to_dict()
            item['device_count'] = device_counts.get(lab.id, 0)
            item['playback_device_count'] = playback_counts.get(lab.id, 0)
            item['test_case_count'] = testcase_counts.get(lab.id, 0)
            result_items.append(item)
        return {
            'items': result_items, 'total': total,
            'page': page, 'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if total else 0,
        }

    def count_devices(self, lab_ids):
        return {lid: self.devices_by_lab.get(lid, 0) for lid in lab_ids}

    def count_playback_devices(self, lab_ids):
        return {lid: self.playback_by_lab.get(lid, 0) for lid in lab_ids}

    def count_test_cases(self, lab_ids):
        return {lid: self.test_cases_by_lab.get(lid, 0) for lid in lab_ids}


@pytest.fixture
def repo():
    return FakeLaboratoryRepository()


@pytest.fixture
def command(repo):
    return LaboratoryCommandService(repo=repo)


@pytest.fixture
def query(repo):
    return LaboratoryQueryService(repo=repo)


class TestCreateLaboratory:
    def test_create_success(self, command):
        result = command.create({'code': 'LAB-A-01', 'name': '音频实验室1', 'status': 'active'})
        assert result['success'] is True
        assert result['code'] == 201
        data = result['data']
        assert data['id'] == 1
        assert data['code'] == 'LAB-A-01'
        assert data['status'] == 'active'

    def test_create_missing_code_rejected(self, command):
        result = command.create({'name': 'x'})
        assert result['success'] is False
        assert 'code' in result['message']
        assert result['code'] == 400

    def test_create_missing_name_rejected(self, command):
        result = command.create({'code': 'LAB-A-02'})
        assert result['success'] is False
        assert 'name' in result['message']

    def test_create_duplicate_code_conflict(self, command):
        command.create({'code': 'LAB-A-01', 'name': 'A'})
        result = command.create({'code': 'LAB-A-01', 'name': 'B'})
        assert result['success'] is False
        assert result['code'] == 409
        assert '已存在' in result['message']

    def test_create_invalid_status_rejected(self, command):
        result = command.create({'code': 'LAB-X', 'name': 'X', 'status': 'bogus'})
        assert result['success'] is False
        assert result['code'] == 400
        assert 'status' in result['message']

    def test_create_defaults_to_active(self, command):
        result = command.create({'code': 'LAB-D', 'name': 'D'})
        assert result['data']['status'] == 'active'

    def test_create_same_code_after_soft_delete_allowed(self, command, repo):
        """审计 P2 修复：软删后同 code 可复用（部分唯一索引语义，对齐 device_group）。"""
        lab_id = command.create({'code': 'LAB-A-01', 'name': '一'})['data']['id']
        assert command.delete(lab_id)['success'] is True
        result = command.create({'code': 'LAB-A-01', 'name': '二'})
        assert result['success'] is True
        assert result['code'] == 201
        assert result['data']['name'] == '二'
        assert result['data']['id'] != lab_id


class TestCreateLaboratoryIntegrityErrorMapping:
    """审计 P2 修复：DB 层唯一冲突（TOCTOU 并发 / 旧库未迁移）→ 显式 409。"""

    class _IntegrityErrorRepo(FakeLaboratoryRepository):
        def create_laboratory(self, data):
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError(
                'INSERT INTO laboratories (code) VALUES (?)',
                {'code': data['code']},
                Exception('UNIQUE constraint failed: laboratories.code'),
            )

    def test_integrity_error_mapped_to_409(self):
        cmd = LaboratoryCommandService(repo=self._IntegrityErrorRepo())
        result = cmd.create({'code': 'LAB-A-01', 'name': 'A'})
        assert result['success'] is False
        assert result['code'] == 409
        assert '占用' in result['message']
        assert 'UNIQUE' not in result['message']
        assert 'sqlite' not in result['message'].lower()


class TestUpdateLaboratory:
    def test_update_partial(self, command):
        lab_id = command.create({'code': 'LAB-A-01', 'name': '旧名'})['data']['id']
        result = command.update(lab_id, {'name': '新名', 'description': 'd'})
        assert result['success'] is True
        assert result['data']['name'] == '新名'
        assert result['data']['description'] == 'd'
        assert result['data']['code'] == 'LAB-A-01'

    def test_update_unknown_lab_404(self, command):
        result = command.update(999, {'name': 'x'})
        assert result['code'] == 404
        assert result['success'] is False

    def test_update_code_conflict(self, command):
        command.create({'code': 'LAB-A-01', 'name': 'A'})
        lab_b = command.create({'code': 'LAB-A-02', 'name': 'B'})['data']['id']
        result = command.update(lab_b, {'code': 'LAB-A-01'})
        assert result['success'] is False
        assert result['code'] == 409

    def test_update_own_code_allowed(self, command):
        lab_id = command.create({'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        result = command.update(lab_id, {'code': 'LAB-A-01'})
        assert result['success'] is True

    def test_update_code_to_deleted_lab_code_allowed(self, command):
        """审计 P2 修复：更新到已软删实验室的 code 应成功（软删行不参与唯一性）。"""
        a_id = command.create({'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        b_id = command.create({'code': 'LAB-A-02', 'name': 'B'})['data']['id']
        command.delete(a_id)
        result = command.update(b_id, {'code': 'LAB-A-01'})
        assert result['success'] is True
        assert result['code'] == 200
        assert result['data']['code'] == 'LAB-A-01'

    def test_update_invalid_status_rejected(self, command):
        lab_id = command.create({'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        result = command.update(lab_id, {'status': 'bogus'})
        assert result['success'] is False
        assert result['code'] == 400


class TestDeleteLaboratory:
    def test_delete_soft(self, command, repo):
        lab_id = command.create({'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        result = command.delete(lab_id)
        assert result['success'] is True
        assert repo.labs[lab_id].deleted is True

    def test_delete_unknown_lab_404(self, command):
        result = command.delete(999)
        assert result['success'] is False
        assert result['code'] == 404


class TestQueryLaboratory:
    def test_get_all_paginated_with_counts(self, query, repo):
        from device_service.application.commands.laboratory_command_service import LaboratoryCommandService
        cmd = LaboratoryCommandService(repo=repo)
        lab_id = cmd.create({'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        repo.devices_by_lab[lab_id] = 5
        repo.playback_by_lab[lab_id] = 3
        repo.test_cases_by_lab[lab_id] = 120

        result = query.get_all(page=1, per_page=10)
        assert result['success'] is True
        data = result['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['device_count'] == 5
        assert item['playback_device_count'] == 3
        assert item['test_case_count'] == 120

    def test_get_all_status_filter(self, query, command):
        command.create({'code': 'LAB-A-01', 'name': 'A'})
        command.create({'code': 'LAB-A-02', 'name': 'B', 'status': 'maintenance'})
        result = query.get_all(page=1, per_page=10, status='maintenance')
        assert result['data']['total'] == 1
        assert result['data']['items'][0]['code'] == 'LAB-A-02'

    def test_get_all_keyword_filter(self, query, command):
        command.create({'code': 'LAB-A-01', 'name': '音频A'})
        command.create({'code': 'LAB-B-01', 'name': '噪声B'})
        result = query.get_all(page=1, per_page=10, keyword='音频')
        assert result['data']['total'] == 1

    def test_get_one_with_counts(self, query, repo):
        from device_service.application.commands.laboratory_command_service import LaboratoryCommandService
        lab_id = LaboratoryCommandService(repo=repo).create(
            {'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        repo.devices_by_lab[lab_id] = 2
        result = query.get_one(lab_id)
        assert result['success'] is True
        assert result['data']['device_count'] == 2
        assert result['data']['code'] == 'LAB-A-01'

    def test_get_one_unknown_404(self, query):
        result = query.get_one(999)
        assert result['code'] == 404

    def test_get_summary(self, query, repo):
        from device_service.application.commands.laboratory_command_service import LaboratoryCommandService
        lab_id = LaboratoryCommandService(repo=repo).create(
            {'code': 'LAB-A-01', 'name': 'A'})['data']['id']
        repo.devices_by_lab[lab_id] = 7
        result = query.get_summary(lab_id)
        assert result['success'] is True
        assert result['data'] == {
            'device_count': 7, 'playback_device_count': 0, 'test_case_count': 0,
        }

    def test_get_summary_unknown_404(self, query):
        result = query.get_summary(999)
        assert result['code'] == 404


class TestDeviceSerializerLabId:
    """device_service 序列化器：Device/PlaybackDevice dict 形态暴露 lab_id（INT-655 §11-25）"""

    def test_device_to_dict_includes_lab_id(self):
        from types import SimpleNamespace
        from device_service.infrastructure.persistence._device_serializers import _device_to_dict
        po = SimpleNamespace(
            id=1, name='d1', model='m', description=None, type='phone',
            system='Android', system_version='14', app_name='a', app_version='1',
            location=None, max_audio_duration=None, needs_prompt_audio=False,
            prompt_config=None, connection_type='usb', keywords=None,
            serial_number='s1', ip=None, status='online', last_online_at=None,
            created_at=None, updated_at=None, supported_algorithms=[],
            lab_id=7,
        )
        d = _device_to_dict(po)
        assert d['lab_id'] == 7

    def test_playback_to_dict_includes_lab_id(self):
        from types import SimpleNamespace
        from device_service.infrastructure.persistence._device_serializers import _playback_to_dict
        po = SimpleNamespace(
            id=1, name='p1', model='m', device_type='dry', sample_rate=44100,
            channel_index=0, device_unique_id='u', description=None,
            status='online', current_spl_mapping_id=None, lab_id=8,
            created_at=None, updated_at=None,
        )
        d = _playback_to_dict(po)
        assert d['lab_id'] == 8

    def test_device_entity_has_lab_id_field(self):
        from device_service.domain.entities import DeviceAggregate
        agg = DeviceAggregate(id=1, lab_id=3)
        assert agg.lab_id == 3
        assert agg.to_dict()['lab_id'] == 3

    def test_playback_entity_has_lab_id_field(self):
        from device_service.domain.entities import PlaybackDeviceAggregate
        agg = PlaybackDeviceAggregate(id=1, lab_id=4)
        assert agg.lab_id == 4
        assert agg.to_dict()['lab_id'] == 4


class TestLaboratoryGrpcServicer:
    """proto 契约：LaboratoryConfigService 各 RPC 信封（success/message/data/code）"""

    def _servicer_with_fakes(self):
        from shared.proto import device_service_pb2 as pb
        servicer = LaboratoryConfigServiceServicer()

        class FakeCommand:
            def create(self, data):
                return {'success': True, 'message': 'ok', 'data': {'id': 1, 'code': 'LAB-A-01', 'name': 'A'}, 'code': 201}

            def update(self, lab_id, data):
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}

            def delete(self, lab_id):
                return {'success': True, 'message': 'ok', 'data': None, 'code': 200}

        class FakeQuery:
            def get_all(self, **kwargs):
                return {'success': True, 'message': 'ok',
                        'data': {'items': [{'id': 1, 'code': 'LAB-A-01', 'name': 'A', 'device_count': 1}],
                                 'total': 1, 'page': 1, 'per_page': 10, 'pages': 1}, 'code': 200}

            def get_one(self, lab_id):
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}

            def get_summary(self, lab_id):
                return {'success': True, 'message': 'ok', 'data': {'device_count': 1}, 'code': 200}

        servicer._command = FakeCommand()
        servicer._query = FakeQuery()
        return servicer, pb

    def test_create_envelope(self):
        servicer, pb = self._servicer_with_fakes()
        resp = servicer.CreateLaboratory(pb.CreateLaboratoryRequest(
            data='{"code": "LAB-A-01", "name": "A"}'))
        assert resp.success is True
        assert resp.code == 201
        data = _loads(resp.data, {})
        assert data['id'] == 1

    def test_update_missing_returns_404_code(self):
        servicer, pb = self._servicer_with_fakes()
        resp = servicer.UpdateLaboratory(pb.UpdateLaboratoryRequest(lab_id=999, data='{"name": "x"}'))
        assert resp.success is False
        assert resp.code == 404

    def test_list_envelope(self):
        servicer, pb = self._servicer_with_fakes()
        resp = servicer.ListLaboratories(pb.ListLaboratoriesRequest(page=1, per_page=10))
        assert resp.success is True
        data = _loads(resp.data, {})
        assert data['items'][0]['device_count'] == 1

    def test_get_unknown_404(self):
        servicer, pb = self._servicer_with_fakes()
        resp = servicer.GetLaboratory(pb.GetLaboratoryRequest(lab_id=999))
        assert resp.success is False
        assert resp.code == 404

    def test_summary_envelope(self):
        servicer, pb = self._servicer_with_fakes()
        resp = servicer.GetLaboratorySummary(pb.GetLaboratorySummaryRequest(lab_id=1))
        assert resp.success is True
        assert _loads(resp.data, {}) == {'device_count': 1}
