# -*- coding: utf-8 -*-
"""INT-68 数据基座验收测试 — apis 扩展列 + ApiRmsSplMapping 五层（UC-0901/0902）

对应 issue INT-68 验收标准：
1. UC-0901：apis 新增记录含 device_type/adapter_class/audio_config/output_types；
   CRUD 全 gRPC（servicer 委托）；audio_config 按 AudioBitDepth/AudioContainer/DeviceType 枚举校验
2. UC-0902：api_rms_spl_mappings 落库并与 API 关联（仓储写侧）；
   执行期 spl_to_gain(api_id, spl) 与校准点一致（线性插值）；
   并发校准分布式锁互斥（DistributedLock lock:spl:calibration:{api_id}）；
   命令侧发布 CONFIG_EVENTS / SPL_MAPPING_CONFIG_CHANGED
"""
import os

# api_crud_service / api_rms_spl_config_service 导入链拉起 shared BaseConfig，
# 无 .env 加载机制的裸 pytest 环境下补齐必填环境变量（本文件全部测试不触库/不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

import pytest

from shared.models.common_enums import (
    AudioBitDepth,
    AudioContainer,
    CalibrationStatus,
    DeviceType,
    RedisKeyPrefix,
)
from api_test_service.domain.entities.api import APIAggregate
from api_test_service.domain.entities.api_rms_spl_mapping import (
    ApiRmsSplMapping,
    CalibrationPoint,
)
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService
from api_test_service.application import api_rms_spl_config_service as rms_spl_module
from api_test_service.application.api_rms_spl_config_service import ApiRmsSplConfigService


class _NeverCalledRepo:
    def __getattr__(self, name):
        raise AssertionError(f'非法入参不应触达仓储方法: {name}')


# ========== 1. UC-0901：apis 扩展列 ==========

class TestAPIAggregateNewColumns:
    def test_defaults(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        assert api.device_type == DeviceType.HTTP_API.value
        assert api.adapter_class is None
        assert api.audio_config is None

    def test_set_audio_config_keeps_known_keys(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        result = api.set_audio_config({
            'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1,
            'container': 'pcm', 'evil_key': 'x',
        })
        assert result == {'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'}

    def test_set_audio_config_none_allowed(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        assert api.set_audio_config(None) is None
        assert api.audio_config is None

    def test_set_audio_config_rejects_non_dict(self):
        api = APIAggregate(id=1, name='n', url='http://x')
        with pytest.raises(ValueError):
            api.set_audio_config('24000')


class TestAPICrudServiceNewColumns:
    def test_validate_rejects_illegal_device_type(self):
        err = APICrudService._validate_api_data({'device_type': 'quantum_device'})
        assert err and '非法的被测设备类型' in err

    def test_validate_accepts_all_device_types(self):
        for dt in DeviceType:
            assert APICrudService._validate_api_data({'device_type': dt.value}) is None

    def test_validate_rejects_illegal_sample_rate(self):
        err = APICrudService._validate_api_data({'audio_config': {'sample_rate': 12345}})
        assert err and '非法采样率' in err

    def test_validate_accepts_numeric_bit_depth_alias(self):
        assert APICrudService._validate_api_data({'audio_config': {'bit_depth': 16}}) is None

    def test_validate_rejects_illegal_bit_depth(self):
        err = APICrudService._validate_api_data({'audio_config': {'bit_depth': 's12'}})
        assert err and '非法位深' in err

    def test_validate_rejects_illegal_channels(self):
        err = APICrudService._validate_api_data({'audio_config': {'channels': 5}})
        assert err and '非法通道数' in err

    def test_validate_rejects_illegal_container(self):
        err = APICrudService._validate_api_data({'audio_config': {'container': 'flac'}})
        assert err and '非法音频容器' in err

    def test_validate_rejects_non_dict_audio_config(self):
        err = APICrudService._validate_api_data({'audio_config': '24000/s16'})
        assert err and '必须是一个 JSON 对象' in err

    def test_create_persists_new_columns(self, monkeypatch):
        captured = {}

        class _Repo:
            def create_api(self, data):
                captured.update(data)
                return SimpleNamespace(id=9)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.create({
            'name': 'ChatGPT Realtime', 'meta': {'api_key': 'sk-x'},
            'device_type': 'websocket_api',
            'adapter_class': 'OpenAIRealtimeAdapter',
            'audio_config': {'sample_rate': 24000, 'bit_depth': 16, 'channels': 1, 'container': 'pcm'},
        })
        assert res['code'] == 201
        assert captured['device_type'] == 'websocket_api'
        assert captured['adapter_class'] == 'OpenAIRealtimeAdapter'
        assert captured['audio_config']['sample_rate'] == 24000
        assert captured['audio_config']['bit_depth'] == 16

    def test_create_rejects_illegal_audio_config_with_400(self, monkeypatch):
        monkeypatch.setattr(api_crud_module, 'api_test_repository', _NeverCalledRepo())
        res = APICrudService.create({
            'name': 'x', 'meta': {'k': 'v'}, 'audio_config': {'sample_rate': 12345},
        })
        assert res['code'] == 400 and '非法采样率' in res['message']

    def test_update_persists_new_columns(self, monkeypatch):
        captured = {}

        class _Repo:
            @staticmethod
            def _api(api_id):
                return SimpleNamespace(id=api_id, name='n', status='online',
                                       api_endpoints=[], output_types=[],
                                       device_type='http_api', adapter_class=None,
                                       audio_config=None)

            def get_api(self, api_id):
                return self._api(api_id)

            def update_api(self, api_id, fields):
                captured.update(fields)
                return self._api(api_id)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.update(9, {'adapter_class': 'HttpStreamAdapter'})
        assert res['code'] == 200
        assert captured['adapter_class'] == 'HttpStreamAdapter'

    def test_api_to_dict_echoes_new_columns(self):
        api = SimpleNamespace(
            id=9, name='n', vendor='openai', api_url=None, description=None,
            status='online', meta={}, algorithm_type=None,
            default_max_process=5, default_max_timeout=30, default_max_audio_duration=60,
            health_score=100, output_types=['audio', 'text'],
            device_type='websocket_api', adapter_class='OpenAIRealtimeAdapter',
            audio_config={'sample_rate': 24000}, rms_spl_mapping_id=3,
            api_endpoints=[], created_at=None, updated_at=None,
        )
        data = APICrudService._api_to_dict(api)
        assert data['device_type'] == 'websocket_api'
        assert data['adapter_class'] == 'OpenAIRealtimeAdapter'
        assert data['audio_config'] == {'sample_rate': 24000}
        assert data['rms_spl_mapping_id'] == 3
        assert data['output_types'] == ['audio', 'text']


class TestAPIConfigChangedEvent:
    def test_create_publishes_api_config_changed(self, monkeypatch):
        published = []

        class _FakeBus:
            def publish(self, channel, event_type, payload):
                published.append((channel, event_type, payload))

        monkeypatch.setattr(rms_spl_module, 'EventBus', _FakeBus)
        monkeypatch.setattr(api_crud_module, 'EventBus', _FakeBus)

        class _Repo:
            def create_api(self, data):
                return SimpleNamespace(id=11)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.create({'name': 'x', 'meta': {'k': 'v'}})
        assert res['code'] == 201
        assert len(published) == 1
        channel, event_type, payload = published[0]
        assert channel.value == 'config_events'
        assert event_type.value == 'api_config_changed'
        assert payload == {'action': 'created', 'api_id': 11}


# ========== 2. UC-0902：映射 CRUD / 校准互斥 / 增益一致 ==========

def _make_mapping(mapping_id=3, api_id=5, points=None):
    return ApiRmsSplMapping(
        id=mapping_id,
        api_id=api_id,
        name='OpenAI Realtime 灵敏度校准',
        reference_spl=65.0,
        reference_gain_linear=1.0,
        calibration_points=points or [],
    )


class _FakeRmsSplRepo:
    """内存版映射仓储（覆盖 ABC 全方法，模拟落库）"""

    def __init__(self):
        self._store = {}
        self._next_id = 1

    def create_mapping(self, data):
        mapping = ApiRmsSplMapping(
            id=self._next_id,
            api_id=int(data['api_id']),
            name=data.get('name') or '',
            reference_spl=data.get('reference_spl', 65.0),
            reference_gain_linear=data.get('reference_gain_linear', 1.0),
            calibration_status=data.get('calibration_status') or CalibrationStatus.UNCALIBRATED.value,
            min_gain_linear=data.get('min_gain_linear', 0.001),
            max_gain_linear=data.get('max_gain_linear', 10.0),
        )
        self._store[mapping.id] = mapping
        self._next_id += 1
        return mapping

    def update_mapping(self, mapping_id, data):
        mapping = self._store.get(int(mapping_id))
        if mapping is None:
            return None
        for key, value in data.items():
            if key == 'calibration_data':
                points = (value or {}).get('points', [])
                mapping.calibration_points = [
                    CalibrationPoint(target_spl=p['target_spl'], gain_linear=p['gain_linear'],
                                     rms_dbfs=p.get('rms_dbfs'))
                    for p in points
                ]
            elif hasattr(mapping, key):
                setattr(mapping, key, value)
        return mapping

    def delete_mapping(self, mapping_id):
        return self._store.pop(int(mapping_id), None) is not None

    def get_mapping(self, mapping_id):
        return self._store.get(int(mapping_id))

    def get_default_mapping(self, api_id):
        candidates = [m for m in self._store.values() if m.api_id == int(api_id)]
        return candidates[-1] if candidates else None

    def list_mappings(self, page=1, per_page=10, api_id=None, calibration_status=None):
        items = list(self._store.values())
        if api_id is not None:
            items = [m for m in items if m.api_id == int(api_id)]
        if calibration_status:
            items = [m for m in items if m.calibration_status == calibration_status]
        return {'items': items, 'total': len(items), 'page': page, 'per_page': per_page, 'pages': 1}

    def list_by_api(self, api_id):
        return [m for m in self._store.values() if m.api_id == int(api_id)]


class TestRmsSplMappingCrud:
    def test_validate_requires_api_id(self):
        err = ApiRmsSplConfigService._validate_mapping_data({'name': 'x'})
        assert err and 'api_id' in err

    def test_validate_rejects_spl_out_of_range(self):
        err = ApiRmsSplConfigService._validate_mapping_data({'api_id': 1, 'reference_spl': 500})
        assert err and 'reference_spl' in err

    def test_validate_rejects_illegal_calibration_status(self):
        err = ApiRmsSplConfigService._validate_mapping_data({'api_id': 1, 'calibration_status': 'half'})
        assert err and '非法的校准状态' in err

    def test_validate_rejects_min_gain_ge_max(self):
        err = ApiRmsSplConfigService._validate_mapping_data({
            'api_id': 1, 'min_gain_linear': 10.0, 'max_gain_linear': 1.0,
        })
        assert err and 'min_gain_linear' in err

    def test_create_defaults_uncalibrated(self, monkeypatch):
        published = []

        class _FakeBus:
            def publish(self, channel, event_type, payload):
                published.append((channel, event_type, payload))

        monkeypatch.setattr(rms_spl_module, 'EventBus', _FakeBus)
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        res = service.create({'api_id': 5, 'name': '映射A'})
        assert res['code'] == 201
        mapping = service.repository.get_mapping(res['data']['id'])
        assert mapping.calibration_status == CalibrationStatus.UNCALIBRATED.value
        channel, event_type, payload = published[0]
        assert event_type.value == 'spl_mapping_config_changed'
        assert payload['api_id'] == 5

    def test_update_missing_returns_404(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        res = service.update(999, {'name': 'x'})
        assert res['code'] == 404

    def test_delete(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})
        res = service.delete(created['data']['id'])
        assert res['code'] == 200
        assert service.get_one(created['data']['id'])['code'] == 404


class TestCalibrationMutex:
    def test_calibrate_writes_points_and_marks_calibrated(self, monkeypatch):
        published = []

        class _FakeBus:
            def publish(self, channel, event_type, payload):
                published.append((channel, event_type, payload))

        monkeypatch.setattr(rms_spl_module, 'EventBus', _FakeBus)
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5, 'name': '映射A'})

        res = service.calibrate(created['data']['id'], {
            'points': [
                {'target_spl': 55.0, 'gain_linear': 0.5},
                {'target_spl': 65.0, 'gain_linear': 1.0},
                {'target_spl': 75.0, 'gain_linear': 2.0},
            ],
        })
        assert res['code'] == 200
        data = res['data']
        assert data['calibration_status'] == CalibrationStatus.CALIBRATED.value
        assert len(data['calibration_points']) == 3
        assert data['is_calibrated'] is True

    def test_calibrate_rejects_empty_points(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})
        res = service.calibrate(created['data']['id'], {'points': []})
        assert res['code'] == 400

    def test_concurrent_calibration_mutex_rejected_with_409(self, monkeypatch):
        """锁被其它线程持有时，并发校准请求被 409 拒绝且不写校准点"""
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})
        mapping_id = created['data']['id']

        class _HeldLock:
            def __init__(self, key, **kwargs):
                assert key.startswith(RedisKeyPrefix.SPL_CALIBRATION_LOCK.value)
                assert key.endswith(':5')

            def acquire(self, blocking=True):
                return False

            def release(self):
                pass

        monkeypatch.setattr(rms_spl_module, 'DistributedLock', _HeldLock)
        res = service.calibrate(mapping_id, {'points': [{'target_spl': 65, 'gain_linear': 1.0}]})
        assert res['code'] == 409
        assert service.get_one(mapping_id)['data']['calibration_points'] == []

    def test_lock_released_after_success(self, monkeypatch):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})

        released = []

        class _OkLock:
            def __init__(self, key, **kwargs):
                pass

            def acquire(self, blocking=True):
                return True

            def release(self):
                released.append(True)

        monkeypatch.setattr(rms_spl_module, 'DistributedLock', _OkLock)
        res = service.calibrate(created['data']['id'], {'points': [{'target_spl': 65, 'gain_linear': 1.0}]})
        assert res['code'] == 200
        assert released == [True]

    def test_lock_released_on_update_failure(self, monkeypatch):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})

        released = []

        class _OkLock:
            def __init__(self, key, **kwargs):
                pass

            def acquire(self, blocking=True):
                return True

            def release(self):
                released.append(True)

        monkeypatch.setattr(rms_spl_module, 'DistributedLock', _OkLock)

        class _BoomRepo(_FakeRmsSplRepo):
            def update_mapping(self, mapping_id, data):
                raise RuntimeError('db down')

        boom = _BoomRepo()
        boom._store = service._repository._store  # 继承已落库数据，仅让写路径炸
        service._repository = boom
        res = service.calibrate(created['data']['id'], {'points': [{'target_spl': 65, 'gain_linear': 1.0}]})
        assert res['code'] == 400
        assert released == [True]


class TestSetDefaultMapping:
    def test_set_default_updates_api(self, monkeypatch):
        captured = {}

        class _ApiRepo:
            def update_api(self, api_id, fields):
                captured.update({'api_id': api_id, **fields})
                return SimpleNamespace(id=api_id)

        monkeypatch.setattr(
            'api_test_service.infrastructure.persistence.api_test_repository.api_test_repository',
            _ApiRepo(),
        )
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})
        res = service.set_default(5, created['data']['id'])
        assert res['code'] == 200
        assert captured == {'api_id': 5, 'rms_spl_mapping_id': created['data']['id']}

    def test_set_default_rejects_foreign_mapping(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5})
        res = service.set_default(6, created['data']['id'])
        assert res['code'] == 400

    def test_clear_default_passes_none(self, monkeypatch):
        captured = {}

        class _ApiRepo:
            def update_api(self, api_id, fields):
                captured.update({'api_id': api_id, **fields})
                return SimpleNamespace(id=api_id)

        monkeypatch.setattr(
            'api_test_service.infrastructure.persistence.api_test_repository.api_test_repository',
            _ApiRepo(),
        )
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        res = service.set_default(5, None)
        assert res['code'] == 200
        assert captured == {'api_id': 5, 'rms_spl_mapping_id': None}


class TestSplGainConsistency:
    """执行期 spl_to_gain(api_id, spl) 与校准点一致（UC-0902 验收）"""

    def _calibrated_service(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        created = service.create({'api_id': 5, 'name': '校准映射'})
        service.calibrate(created['data']['id'], {
            'points': [
                {'target_spl': 55.0, 'gain_linear': 0.5},
                {'target_spl': 65.0, 'gain_linear': 1.0},
                {'target_spl': 75.0, 'gain_linear': 2.0},
            ],
        })
        return service, created['data']['id']

    def test_gain_matches_calibration_points_exactly(self):
        service, _ = self._calibrated_service()
        gain = service.get_spl_gain(5, 65.0)['data']['gain_linear']
        assert gain == pytest.approx(1.0)
        gain = service.get_spl_gain(5, 55.0)['data']['gain_linear']
        assert gain == pytest.approx(0.5)
        gain = service.get_spl_gain(5, 75.0)['data']['gain_linear']
        assert gain == pytest.approx(2.0)

    def test_gain_interpolates_between_points(self):
        service, _ = self._calibrated_service()
        gain = service.get_spl_gain(5, 70.0)['data']['gain_linear']
        assert gain == pytest.approx(1.5)  # 65↔75 线性插值中点

    def test_unmapped_api_falls_back_to_linear_approx(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        gain = service.get_spl_gain(999, 65.0)['data']['gain_linear']
        assert gain == pytest.approx(1.0)  # 10^((65-65)/20)
        gain = service.get_spl_gain(999, 85.0)['data']['gain_linear']
        assert gain == pytest.approx(10.0)  # 10^((85-65)/20)

    def test_domain_service_uses_repository(self):
        """域服务经仓储端口取默认映射（执行链路注入方式）"""
        repo = _FakeRmsSplRepo()
        repo.create_mapping({'api_id': 5})
        svc = ApiRmsSplService(repo)
        assert svc.spl_to_gain(5, 65.0) == pytest.approx(1.0)


# ========== 3. 五层贯通：proto / servicer 存在性 ==========

class TestGrpcLayerWiring:
    def test_proto_has_api_rms_spl_config_service(self):
        from shared.proto import api_test_service_pb2_grpc as grpc_mod
        assert hasattr(grpc_mod, 'ApiRmsSplConfigServiceServicer')
        assert hasattr(grpc_mod, 'ApiRmsSplConfigServiceStub')
        assert hasattr(grpc_mod, 'add_ApiRmsSplConfigServiceServicer_to_server')

    def test_server_registers_rms_spl_servicer(self):
        import inspect
        from api_test_service.interfaces.grpc import server as server_mod
        source = inspect.getsource(server_mod)
        assert 'add_ApiRmsSplConfigServiceServicer_to_server' in source

    def test_stub_factory_exists(self):
        from shared.clients.grpc_clients import get_api_rms_spl_config_service_stub
        assert callable(get_api_rms_spl_config_service_stub)

    def test_servicer_delegates_to_application_service(self):
        """servicer 委托 application 层（CQRS：读侧不产生副作用）"""
        servicer = __import__(
            'api_test_service.interfaces.grpc.servicers', fromlist=['ApiRmsSplConfigServiceServicer']
        ).ApiRmsSplConfigServiceServicer()
        calls = []

        class _FakeService:
            def get_one(self, mapping_id):
                calls.append(('get_one', mapping_id))
                return {'success': True, 'message': 'ok', 'data': {'id': mapping_id}, 'code': 200}

        servicer._config_service = _FakeService()
        resp = servicer.GetRmsSplMapping(SimpleNamespace(mapping_id=3))
        assert resp.success is True
        assert calls == [('get_one', 3)]


# ========== 4. 枚举锁定（线上契约字面量） ==========

class TestEnumLiterals:
    def test_audio_bit_depth_values(self):
        assert [e.value for e in AudioBitDepth] == ['s16', 's24', 's32']

    def test_audio_container_values(self):
        assert [e.value for e in AudioContainer] == ['pcm', 'wav']

    def test_spl_calibration_lock_prefix(self):
        assert RedisKeyPrefix.SPL_CALIBRATION_LOCK.value == 'lock:spl:calibration'


# ========== 5. 审计返修补充：校准数值校验 / 全量替换语义 / update 路径越权校验 ==========

class TestCalibratePointValidation:
    """审计问题5：calibrate 校准点复用正数校验并加 math.isfinite（NaN 穿透插值）"""

    def _service_with_mapping(self):
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        mapping_id = service.create({'api_id': 5})['data']['id']
        return service, mapping_id

    def test_rejects_nan_gain_400(self):
        service, mapping_id = self._service_with_mapping()
        res = service.calibrate(mapping_id, {
            'points': [{'target_spl': 65, 'gain_linear': float('nan')}]})
        assert res['code'] == 400 and 'gain_linear' in res['message']
        assert service.get_one(mapping_id)['data']['calibration_points'] == []

    def test_rejects_inf_target_spl_400(self):
        service, mapping_id = self._service_with_mapping()
        res = service.calibrate(mapping_id, {
            'points': [{'target_spl': float('inf'), 'gain_linear': 1.0}]})
        assert res['code'] == 400 and 'target_spl' in res['message']

    def test_rejects_negative_gain_400(self):
        service, mapping_id = self._service_with_mapping()
        res = service.calibrate(mapping_id, {
            'points': [{'target_spl': 65, 'gain_linear': -0.5}]})
        assert res['code'] == 400 and 'gain_linear' in res['message']

    def test_rejects_non_numeric_gain_400(self):
        service, mapping_id = self._service_with_mapping()
        res = service.calibrate(mapping_id, {
            'points': [{'target_spl': 65, 'gain_linear': 'loud'}]})
        assert res['code'] == 400 and 'gain_linear' in res['message']


class TestCalibrateReplaceSemantics:
    """审计问题4：校准以请求点集全量替换（锁内重读，不依赖抢锁前陈旧快照）"""

    def test_recalibrate_replaces_not_appends(self):
        """重复校准：新点集整体取代旧曲线，不在同一 target_spl 累积重复点"""
        service = ApiRmsSplConfigService(repository=_FakeRmsSplRepo())
        mapping_id = service.create({'api_id': 5})['data']['id']
        service.calibrate(mapping_id, {'points': [
            {'target_spl': 55, 'gain_linear': 0.5},
            {'target_spl': 65, 'gain_linear': 1.0},
        ]})
        res = service.calibrate(mapping_id, {'points': [
            {'target_spl': 65, 'gain_linear': 2.0},
        ]})
        assert res['code'] == 200
        pts = res['data']['calibration_points']
        assert [(p['target_spl'], p['gain_linear']) for p in pts] == [(65.0, 2.0)]

    def test_stale_concurrent_commit_not_merged_into_write(self):
        """抢锁前快照陈旧（并发校准已提交）时，写入仍只含本次请求点集"""
        repo = _FakeRmsSplRepo()
        service = ApiRmsSplConfigService(repository=repo)
        mapping_id = service.create({'api_id': 5})['data']['id']

        real_get = repo.get_mapping
        state = {'reads': 0}

        def _get_with_concurrent_commit(mapping_id):
            state['reads'] += 1
            if state['reads'] == 1:
                # 模拟并发校准 A 在 B 抢锁前完成提交：旧点集已落库
                m = real_get(mapping_id)
                m.replace_calibration_points([CalibrationPoint(target_spl=90.0, gain_linear=9.0)])
            return real_get(mapping_id)

        repo.get_mapping = _get_with_concurrent_commit
        res = service.calibrate(mapping_id, {'points': [{'target_spl': 65, 'gain_linear': 1.5}]})
        assert res['code'] == 200
        pts = res['data']['calibration_points']
        # A 提交的 (90, 9.0) 不被合并进 B 的写入
        assert [(p['target_spl'], p['gain_linear']) for p in pts] == [(65.0, 1.5)]

    def test_returns_404_when_mapping_deleted_before_lock(self):
        """首读后、抢锁前映射被并发删除：锁内重读命中 None，返回 404 而非异常"""
        repo = _FakeRmsSplRepo()
        service = ApiRmsSplConfigService(repository=repo)
        mapping_id = service.create({'api_id': 5})['data']['id']

        real_get = repo.get_mapping
        state = {'reads': 0}

        def _get_then_delete(mapping_id):
            state['reads'] += 1
            if state['reads'] == 2:
                repo._store.pop(int(mapping_id), None)
            return real_get(mapping_id)

        repo.get_mapping = _get_then_delete
        res = service.calibrate(mapping_id, {'points': [{'target_spl': 65, 'gain_linear': 1.0}]})
        assert res['code'] == 404


class TestApiUpdateSplMappingOwnership:
    """审计问题2：API update 路径 rms_spl_mapping_id 存在性/归属双校验（与 set-default 同口径）"""

    @staticmethod
    def _spl_repo():
        class _SplRepo:
            def get_mapping(self, mapping_id):
                return {3: ApiRmsSplMapping(id=3, api_id=5),
                        4: ApiRmsSplMapping(id=4, api_id=6)}.get(int(mapping_id))
        return _SplRepo()

    @staticmethod
    def _api_repo(captured=None):
        def _api(api_id):
            return SimpleNamespace(id=api_id, name='n', status='online', api_endpoints=[],
                                   output_types=[], device_type='http_api', adapter_class=None,
                                   audio_config=None, default_max_process=5,
                                   default_max_timeout=30, default_max_audio_duration=60)

        class _ApiRepo:
            def get_api(self, api_id):
                return _api(api_id)

            def update_api(self, api_id, fields):
                if captured is not None:
                    captured.update(fields)
                return _api(api_id)

        return _ApiRepo()

    def _patch(self, monkeypatch, captured=None):
        monkeypatch.setattr(api_crud_module, 'api_test_repository', self._api_repo(captured))
        monkeypatch.setattr(api_crud_module, 'ApiRmsSplRepositoryImpl', self._spl_repo)

    def test_update_rejects_missing_mapping_404(self, monkeypatch):
        self._patch(monkeypatch)
        res = APICrudService.update(5, {'rms_spl_mapping_id': 999})
        assert res['code'] == 404 and '未找到映射记录' in res['message']

    def test_update_rejects_foreign_mapping_400(self, monkeypatch):
        """映射 4 归属 API 6，不得设为 API 5 的默认映射（越权配置写入）"""
        self._patch(monkeypatch)
        res = APICrudService.update(5, {'rms_spl_mapping_id': 4})
        assert res['code'] == 400 and '不属于' in res['message']

    def test_update_accepts_own_mapping(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        res = APICrudService.update(5, {'rms_spl_mapping_id': 3})
        assert res['code'] == 200
        assert captured['rms_spl_mapping_id'] == 3

    def test_update_null_clears_mapping(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        res = APICrudService.update(5, {'rms_spl_mapping_id': None})
        assert res['code'] == 200
        assert captured['rms_spl_mapping_id'] is None


class TestCreateAudioConfigNormalized:
    """审计问题6：CRUD 写路径复用聚合 normalize_audio_config 过滤未知键"""

    def test_create_filters_unknown_audio_config_keys(self, monkeypatch):
        captured = {}

        class _Repo:
            def create_api(self, data):
                captured.update(data)
                return SimpleNamespace(id=12)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.create({
            'name': 'x', 'meta': {'k': 'v'},
            'audio_config': {'sample_rate': 24000, 'channels': 1, 'unknown_key': 'junk'},
        })
        assert res['code'] == 201
        assert captured['audio_config'] == {'sample_rate': 24000, 'channels': 1}

    def test_update_filters_unknown_audio_config_keys(self, monkeypatch):
        captured = {}

        class _Repo:
            @staticmethod
            def _api(api_id):
                return SimpleNamespace(id=api_id, name='n', status='online', api_endpoints=[],
                                       output_types=[], device_type='http_api', adapter_class=None,
                                       audio_config=None, default_max_process=5,
                                       default_max_timeout=30, default_max_audio_duration=60)

            def get_api(self, api_id):
                return self._api(api_id)

            def update_api(self, api_id, fields):
                captured.update(fields)
                return self._api(api_id)

        monkeypatch.setattr(api_crud_module, 'api_test_repository', _Repo())
        res = APICrudService.update(9, {'audio_config': {'sample_rate': 48000, 'junk': 1}})
        assert res['code'] == 200
        assert captured['audio_config'] == {'sample_rate': 48000}
