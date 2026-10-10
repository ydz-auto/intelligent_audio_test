# -*- coding: utf-8 -*-
"""INT-74 枚举消费接线验收测试 — OutputType / CalibrationStatus / DeviceType 消费方行为锁定

对应 issue INT-74 验收标准（枚举已建必接线，拒绝魔法字符串）：
1. OutputType（API 聚合 output_types 读写）：
   - normalize_output_types 归一（去重 / 剔除非法值 / 按 OutputType 枚举定义序输出）
   - APIAggregate.set_output_types 聚合根消费
   - APICrudService 校验拒绝非法值与非法结构（400 路径）、创建/更新链路落库前归一
   - _api_to_dict 读侧回显归一
2. CalibrationStatus（校准状态流转）：
   - 创建映射默认未校准（无校准点）
   - 创建/更新携带有效校准点 → 置已校准
   - 环境参数（distance / test_frequency）变更 → 回退未校准并清空校准数据
   - 校准完成（calibrate）→ 置已校准并落校准历史
3. DeviceType（benchmark 归类）：
   - _resolve_subject 按 websocket/http 协议归类 WEBSOCKET_API / HTTP_API，
     物理设备归类 PHYSICAL，均缺失回退空串；以字面量锁定线上契约值不变
"""
import os

# api_crud_service / benchmark_ranking_service 导入链拉起 shared BaseConfig，
# 无 .env 加载机制的裸 pytest 环境下补齐必填环境变量（本文件全部测试不触库/不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

import pytest

from shared.models.common_enums import CalibrationStatus, DeviceType, OutputType
from api_test_service.domain.entities.api import APIAggregate, normalize_output_types
from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService
from report_service.application.services.benchmark_ranking_service import _resolve_subject
from report_service.domain.entities.benchmark import SubjectType
from device_service.application.commands import spl_command_service as spl_cmd_module
from device_service.application.commands.spl_command_service import SPLCommandService


# ========== 1. OutputType：normalize_output_types 归一 ==========

class TestNormalizeOutputTypes:
    def test_dedup_invalid_and_enum_order(self):
        assert normalize_output_types(['text', 'audio', 'audio', 'bogus']) == ['audio', 'text']

    def test_output_follows_enum_definition_order(self):
        assert OutputType.AUDIO.value == 'audio'
        assert normalize_output_types(['video', 'image', 'text', 'audio']) == ['audio', 'text', 'video', 'image']

    def test_non_list_returns_empty(self):
        assert normalize_output_types(None) == []
        assert normalize_output_types('audio') == []
        assert normalize_output_types(123) == []
        assert normalize_output_types({'audio': 1}) == []

    def test_tuple_set_inputs_accepted(self):
        assert normalize_output_types(('video', 'audio')) == ['audio', 'video']
        assert normalize_output_types({'video', 'audio'}) == ['audio', 'video']

    def test_all_invalid_returns_empty(self):
        assert normalize_output_types(['hologram', 42, '']) == []


# ========== 2. OutputType：APIAggregate 聚合根消费 ==========

class TestAPIAggregateOutputTypes:
    def test_default_empty(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        assert api.output_types == []

    def test_set_output_types_normalizes(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        result = api.set_output_types(['text', 'audio', 'audio', 'bogus'])
        assert result == ['audio', 'text']
        assert api.output_types == ['audio', 'text']


# ========== 3. OutputType：APICrudService 校验 / 创建 / 更新 / 读侧回显 ==========

class TestAPICrudServiceOutputTypes:
    def test_validate_rejects_non_list(self):
        err = APICrudService._validate_api_data({'output_types': 'audio'})
        assert err and '必须是一个数组' in err

    def test_validate_rejects_illegal_value(self):
        err = APICrudService._validate_api_data({'output_types': ['audio', 'hologram']})
        assert err and '非法的输出类型' in err and 'hologram' in err

    def test_validate_accepts_valid_values(self):
        assert APICrudService._validate_api_data({'output_types': ['audio', 'text']}) is None

    def test_create_normalizes_before_persist(self, monkeypatch):
        captured = {}

        class _Repo:
            def create_api(self, data):
                captured.update(data)
                return SimpleNamespace(id=7)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.create({
            'name': '被测API', 'meta': {'k': 'v'},
            'output_types': ['text', 'audio', 'audio'],
        })
        assert res['code'] == 201
        assert captured['output_types'] == ['audio', 'text']

    def test_create_rejects_illegal_value_with_400(self, monkeypatch):
        monkeypatch.setattr(api_crud_module, 'api_test_repository', _NeverCalledRepo())
        res = APICrudService.create({'name': '被测API', 'meta': {'k': 'v'}, 'output_types': ['hologram']})
        assert res['code'] == 400
        assert '非法的输出类型' in res['message']

    def test_update_rejects_illegal_value_with_400(self, monkeypatch):
        class _NoUpdateRepo:
            def get_api(self, api_id):
                return SimpleNamespace(id=api_id, name='n', status='online',
                                       api_endpoints=[], output_types=['audio'])

            def __getattr__(self, name):
                raise AssertionError(f'非法 output_types 不应在触达 update_api 前被放行: {name}')

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _NoUpdateRepo())
        res = APICrudService.update(7, {'output_types': ['audio', 'hologram']})
        assert res['code'] == 400
        assert '非法的输出类型' in res['message'] and 'hologram' in res['message']

    def test_update_normalizes_before_persist(self, monkeypatch):
        captured = {}

        class _Repo:
            @staticmethod
            def _api(api_id, output_types):
                return SimpleNamespace(id=api_id, name='n', status='online',
                                       api_endpoints=[], output_types=output_types)

            def get_api(self, api_id):
                return self._api(api_id, ['audio'])

            def update_api(self, api_id, fields):
                captured.update(fields)
                return self._api(api_id, fields.get('output_types', []))

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.update(7, {'output_types': ['text', 'audio', 'audio']})
        assert res['code'] == 200
        assert captured['output_types'] == ['audio', 'text']

    def test_api_to_dict_echoes_normalized(self):
        api = SimpleNamespace(id=1, name='n', status='online',
                              output_types=['audio', 'audio', 'bogus'], api_endpoints=[])
        d = APICrudService._api_to_dict(api)
        assert d['output_types'] == ['audio']


class _NeverCalledRepo:
    """任何仓储调用都视为缺陷（校验应在触库前拒绝）"""

    def __getattr__(self, name):
        raise AssertionError(f'非法 output_types 不应触达仓储方法: {name}')


# ========== 4. CalibrationStatus：SPL 校准状态流转 ==========

class _FakeSPLRepo:
    def __init__(self):
        self.create_data = None
        self.update_fields = {}
        self.history = []
        self._mappings = {}

    def create_spl_mapping(self, data):
        self.create_data = dict(data)
        mapping = SimpleNamespace(
            id=1, deleted=False, name=data['name'],
            distance=data['distance'], test_frequency=data['test_frequency'],
            device_id=data['device_id'],
        )
        self._mappings[1] = mapping
        return mapping

    def get_spl_mapping(self, mapping_id):
        return self._mappings.get(mapping_id)

    def update_spl_mapping(self, mapping_id, fields):
        self.update_fields.setdefault(mapping_id, {}).update(fields)
        mapping = self._mappings.get(mapping_id)
        if mapping:
            for k, v in fields.items():
                setattr(mapping, k, v)
        return mapping

    def commit(self):
        pass

    def create_calibration_history(self, mapping_id, data, distance, test_frequency):
        self.history.append((mapping_id, data, distance, test_frequency))

    def update_playback_device_spl_ref(self, device_id, mapping_id):
        pass


class _FakePlaybackRepo:
    def get_playback_device(self, device_id):
        return None


@pytest.fixture()
def spl_svc():
    repo = _FakeSPLRepo()
    return SPLCommandService(repo=repo, playback_repo=_FakePlaybackRepo()), repo


class TestSPLCalibrationFlow:
    def test_create_without_points_defaults_uncalibrated(self, spl_svc):
        svc, repo = spl_svc
        res = svc.create({'name': '映射', 'device_id': 1})
        assert res['code'] == 201
        assert repo.create_data['calibration_status'] == CalibrationStatus.UNCALIBRATED.value
        assert repo.create_data['calibration_status'] == 'uncalibrated'

    def test_create_with_valid_points_calibrated(self, spl_svc):
        svc, repo = spl_svc
        res = svc.create({'name': '映射', 'device_id': 1,
                          'calibration_data': {'points': [{'gain': 10, 'spl': 80}]}})
        assert res['code'] == 201
        assert repo.create_data['calibration_status'] == CalibrationStatus.CALIBRATED.value
        assert repo.create_data['calibration_status'] == 'calibrated'

    def test_update_env_param_change_resets_to_uncalibrated(self, spl_svc):
        svc, repo = spl_svc
        assert svc.create({'name': '映射', 'device_id': 1,
                           'calibration_data': {'points': [{'gain': 10, 'spl': 80}]}})['code'] == 201
        repo.update_fields.clear()
        res = svc.update(1, {'distance': 2.0})
        assert res['code'] == 200
        fields = repo.update_fields[1]
        assert fields['calibration_status'] == CalibrationStatus.UNCALIBRATED.value
        assert fields['calibration_data'] is None

    def test_update_test_frequency_change_resets_to_uncalibrated(self, spl_svc):
        svc, repo = spl_svc
        assert svc.create({'name': '映射', 'device_id': 1,
                           'calibration_data': {'points': [{'gain': 10, 'spl': 80}]}})['code'] == 201
        repo.update_fields.clear()
        res = svc.update(1, {'test_frequency': 2000})
        assert res['code'] == 200
        assert repo.update_fields[1]['calibration_status'] == CalibrationStatus.UNCALIBRATED.value

    def test_update_with_new_valid_points_calibrated(self, spl_svc):
        svc, repo = spl_svc
        assert svc.create({'name': '映射', 'device_id': 1})['code'] == 201
        repo.update_fields.clear()
        res = svc.update(1, {'calibration_data': {'points': [{'gain': 20, 'spl': 85}]}})
        assert res['code'] == 200
        assert repo.update_fields[1]['calibration_status'] == CalibrationStatus.CALIBRATED.value

    def test_calibrate_completes_to_calibrated_with_history(self, spl_svc, monkeypatch):
        svc, repo = spl_svc
        assert svc.create({'name': '映射', 'device_id': 1})['code'] == 201
        monkeypatch.setattr(spl_cmd_module, 'log_and_emit', lambda *a, **k: None)
        monkeypatch.setattr(spl_cmd_module.time, 'sleep', lambda s: None)
        res = svc.calibrate(1)
        assert res['code'] == 200
        assert res['data']['calibration_status'] == CalibrationStatus.CALIBRATED.value
        assert repo.update_fields[1]['calibration_status'] == CalibrationStatus.CALIBRATED.value
        assert repo.history and repo.history[0][0] == 1


# ========== 5. DeviceType：benchmark 归类（字面量锁定线上契约） ==========

class TestBenchmarkResolveSubject:
    def test_websocket_api_subject(self):
        name, dtype, stype = _resolve_subject({'apis': [{'type': 'websocket', 'name': 'X'}]}, 'fb')
        assert name == 'X'
        assert dtype == DeviceType.WEBSOCKET_API.value
        assert dtype == 'websocket_api'
        assert stype == SubjectType.CLOSED_SOURCE.value

    def test_http_api_subject(self):
        _, dtype, _ = _resolve_subject({'apis': [{'protocol': 'https', 'name': 'Y'}]}, 'fb')
        assert dtype == DeviceType.HTTP_API.value
        assert dtype == 'http_api'

    def test_physical_device_subject(self):
        name, dtype, stype = _resolve_subject({'devices': [{'app_name': 'Z'}]}, 'fb')
        assert name == 'Z'
        assert dtype == DeviceType.PHYSICAL.value
        assert dtype == 'physical'
        assert stype == SubjectType.APP.value

    def test_empty_summary_falls_back(self):
        assert _resolve_subject({}, 'fb') == ('fb', '', SubjectType.CLOSED_SOURCE.value)
