# -*- coding: utf-8 -*-
"""INT-1799 单测：API 模型正交拆分（protocol × streaming）+ 执行道收敛

覆盖（B0 裁定文档 `09_API协议面与执行道契约.md` §5.3）：
- 协议词表归一（别名 → 规范值，非法值报错）；
- `lane_of()` 真值表（道只由 streaming 决定）；
- 协议 × 流式性可用矩阵（B1 只放行 http+false / websocket+true）；
- 迁移映射表逐值（http_api / websocket_api / physical / 未知值 / meta 冲突）；
- CRUD 写侧：缺省默认、device_type 显式 400、未上线组合 400、更新合并口径；
- 读侧序列化：只出 protocol / streaming，不再出 device_type；
- 执行器白名单复制（漏复制即恒默认值）；
- task_service 亲和域令牌派生（single-lane / ACL 取不到 → 400）。
"""
import importlib.util
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.common_enums import (
    APIProtocol,
    AVAILABLE_PROTOCOL_STREAMING,
    ExecutionLane,
    is_protocol_streaming_available,
    lane_of,
    normalize_protocol,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────── 协议词表 ────────────────────────────

class TestProtocolVocabulary:
    @pytest.mark.parametrize('raw,want', [
        ('http', 'http'), ('https', 'http'), ('ws', 'websocket'),
        ('wss', 'websocket'), ('websocket', 'websocket'), ('HTTP', 'http'),
        ('sse', 'sse'), ('grpc', 'grpc'),
    ])
    def test_normalize_aliases(self, raw, want):
        assert normalize_protocol(raw) == want

    @pytest.mark.parametrize('bad', ['', None, 'ftp', 'realtime', 'http_api'])
    def test_normalize_rejects_unknown(self, bad):
        with pytest.raises(ValueError):
            normalize_protocol(bad)

    def test_protocol_values(self):
        assert [p.value for p in APIProtocol] == ['http', 'websocket', 'sse', 'grpc']


# ──────────────────────────── lane_of 真值表 ────────────────────────────

class TestLaneOf:
    @pytest.mark.parametrize('streaming,lane', [
        (True, ExecutionLane.STREAMING),
        (False, ExecutionLane.NON_STREAMING),
        (1, ExecutionLane.STREAMING),
        (0, ExecutionLane.NON_STREAMING),
        (None, ExecutionLane.NON_STREAMING),
    ])
    def test_truth_table(self, streaming, lane):
        assert lane_of(streaming) is lane

    def test_two_lanes_only(self):
        assert [l.value for l in ExecutionLane] == ['streaming', 'non_streaming']


# ──────────────────────────── 可用矩阵 ────────────────────────────

class TestAvailabilityMatrix:
    @pytest.mark.parametrize('protocol,streaming,want', [
        ('http', False, True),
        ('websocket', True, True),
        ('http', True, False),
        ('websocket', False, False),
        ('sse', True, False),
        ('sse', False, False),
        ('grpc', False, False),
        ('grpc', True, False),
    ])
    def test_matrix(self, protocol, streaming, want):
        assert is_protocol_streaming_available(protocol, streaming) is want

    def test_matrix_shape(self):
        assert AVAILABLE_PROTOCOL_STREAMING == {('http', False), ('websocket', True)}


# ──────────────────────────── 迁移映射 ────────────────────────────

def _load_migration_module():
    path = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                        'add_api_protocol_streaming_int1798.py')
    spec = importlib.util.spec_from_file_location('int1799_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationMapping:
    @pytest.fixture(scope='class')
    def mig(self):
        return _load_migration_module()

    @pytest.mark.parametrize('device_type,meta,expect', [
        ('http_api', None, ('http', False)),
        ('websocket_api', None, ('websocket', True)),
        ('http_api', '{"protocol": "https"}', ('http', False)),
        ('http_api', '{"protocol": "http", "vendor": "x"}', ('http', False)),
        ('websocket_api', '{"protocol": "wss"}', ('websocket', True)),
    ])
    def test_supported_rows(self, mig, device_type, meta, expect):
        resolved, reason = mig._resolve_row(1, device_type, meta)
        assert resolved == expect, reason

    @pytest.mark.parametrize('device_type,meta,keyword', [
        ('physical', None, '非法'),
        ('', None, '非法'),
        (None, None, '非法'),
        ('webrtc_api', None, '非法'),
        ('http_api', '{"protocol": "ftp"}', '非法'),
        # meta.protocol 与 device_type 推出的协议冲突 → 中止，不猜不覆盖
        ('http_api', '{"protocol": "ws"}', '冲突'),
    ])
    def test_illegal_rows_abort(self, mig, device_type, meta, keyword):
        resolved, reason = mig._resolve_row(1, device_type, meta)
        assert resolved is None
        assert keyword in reason


# ──────────────────────────── CRUD 写侧 ────────────────────────────

class TestCrudValidation:
    def test_device_type_write_rejected(self):
        from api_test_service.application.api_crud_service import APICrudService
        err = APICrudService._validate_api_data({'device_type': 'websocket_api'})
        assert err == 'device_type 已废弃，请改用 protocol + streaming'

    def test_empty_device_type_is_ignored(self):
        from api_test_service.application.api_crud_service import APICrudService
        assert APICrudService._validate_api_data({'device_type': ''}) is None

    @pytest.mark.parametrize('protocol,streaming,want_ok', [
        ('http', False, True),
        ('websocket', True, True),
        ('http', True, False),
        ('websocket', False, False),
        ('sse', True, False),
        ('grpc', False, False),
    ])
    def test_lane_combo(self, protocol, streaming, want_ok):
        from api_test_service.application.api_crud_service import APICrudService
        err = APICrudService._validate_lane_combo(protocol, streaming)
        if want_ok:
            assert err is None
        else:
            assert '实现未上线' in err

    def test_streaming_must_be_bool(self):
        from api_test_service.application.api_crud_service import APICrudService
        assert '布尔' in APICrudService._validate_api_data({'streaming': 'true'})

    def test_create_defaults(self, monkeypatch):
        from api_test_service.application import api_crud_service as mod
        captured = {}

        def _fake_create(data):
            captured.update(data)
            return SimpleNamespace(id=11)

        monkeypatch.setattr(mod.api_test_repository, 'create_api', _fake_create)
        monkeypatch.setattr(mod, 'refresh_stats_cache', lambda: None)
        monkeypatch.setattr(mod.APICrudService, '_publish_config_changed',
                            staticmethod(lambda *a, **k: None))

        result = mod.APICrudService.create({'name': 'demo', 'meta': {}})
        assert result['success'] is True and result['code'] == 201
        assert captured['protocol'] == 'http'
        assert captured['streaming'] is False
        assert 'device_type' not in captured

    def test_create_rejects_device_type(self):
        from api_test_service.application.api_crud_service import APICrudService
        result = APICrudService.create({
            'name': 'demo', 'meta': {}, 'device_type': 'http_api'})
        assert result['code'] == 400
        assert 'device_type 已废弃' in result['message']

    def test_create_rejects_unavailable_combo(self):
        from api_test_service.application.api_crud_service import APICrudService
        result = APICrudService.create({
            'name': 'demo', 'meta': {}, 'protocol': 'grpc', 'streaming': False})
        assert result['code'] == 400
        assert '实现未上线' in result['message']

    def test_update_merges_current_values_for_matrix(self, monkeypatch):
        """只改一维：http+false 改 streaming=true → 400（合并后组合未上线）"""
        from api_test_service.application import api_crud_service as mod
        api = SimpleNamespace(id=1, protocol='http', streaming=False,
                              proxy_type=None, proxy_url=None,
                              default_max_process=5, default_max_timeout=30,
                              default_max_audio_duration=60, api_endpoints=[])
        monkeypatch.setattr(mod.api_test_repository, 'get_api', lambda _id: api)
        result = mod.APICrudService.update(1, {'streaming': True})
        assert result['code'] == 400
        assert '实现未上线' in result['message']

    def test_update_to_websocket_streaming_allowed(self, monkeypatch):
        """http+false 同时改 protocol+streaming → websocket+true 放行"""
        from api_test_service.application import api_crud_service as mod
        api = SimpleNamespace(id=1, protocol='http', streaming=False,
                              proxy_type=None, proxy_url=None,
                              default_max_process=5, default_max_timeout=30,
                              default_max_audio_duration=60, api_endpoints=[])
        captured = {}

        def _fake_update(api_id, fields):
            captured.update(fields)
            return SimpleNamespace(id=api_id, name='x', status='online',
                                   protocol=fields.get('protocol', 'http'),
                                   streaming=fields.get('streaming', False),
                                   output_types=[], vendor=None, description=None,
                                   meta={}, algorithm_type=None,
                                   default_max_process=5, default_max_timeout=30,
                                   default_max_audio_duration=60, health_score=100,
                                   adapter_class=None, audio_config=None,
                                   rms_spl_mapping_id=None, proxy_type=None,
                                   proxy_url=None, api_endpoints=[],
                                   endpoint_keys_summary=[], created_at=None,
                                   updated_at=None)

        monkeypatch.setattr(mod.api_test_repository, 'get_api', lambda _id: api)
        monkeypatch.setattr(mod.api_test_repository, 'update_api', _fake_update)
        monkeypatch.setattr(mod.APICrudService, '_publish_config_changed',
                            staticmethod(lambda *a, **k: None))
        result = mod.APICrudService.update(
            1, {'protocol': 'websocket', 'streaming': True})
        assert result['code'] == 200
        assert captured['protocol'] == 'websocket'
        assert captured['streaming'] is True


# ──────────────────────────── 读侧序列化 ────────────────────────────

class TestApiToDict:
    def test_no_device_type_and_new_fields(self):
        from api_test_service.application.api_crud_service import APICrudService
        api = SimpleNamespace(
            id=1, name='demo', status='online', vendor=None, description=None,
            meta={}, algorithm_type=None, default_max_process=5,
            default_max_timeout=30, default_max_audio_duration=60,
            health_score=100, output_types=[], device_type='http_api',
            protocol='websocket', streaming=True, adapter_class=None,
            audio_config=None, rms_spl_mapping_id=None, proxy_type=None,
            proxy_url=None, api_endpoints=[], created_at=None, updated_at=None)
        data = APICrudService._api_to_dict(api)
        assert data['protocol'] == 'websocket'
        assert data['streaming'] is True
        assert 'device_type' not in data


# ──────────────────────────── 执行器白名单 ────────────────────────────

class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = __import__('threading').Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass


class TestExecutorWhitelist:
    def test_process_api_configs_copies_lane_fields(self):
        from api_test_service.core.api_executor import APIExecutor
        executor = APIExecutor(_EngineStub())
        cfg = SimpleNamespace(
            id=3, api_endpoints=[{'endpoint': 'ws://x'}], default_max_process=2,
            meta={}, max_timeout=30, vendor=None, protocol='websocket',
            streaming=True, adapter_class=None, proxy_type=None, proxy_url=None)
        processed = executor._process_api_configs([cfg])
        assert processed[0].protocol == 'websocket'
        assert processed[0].streaming is True


# ──────────────────────────── task_service 亲和域令牌 ────────────────────────────

class TestTaskAffinityToken:
    def test_no_api_ids_keeps_http_api(self):
        from task_service.infrastructure.persistence._task_crud_mixin import (
            resolve_api_affinity_token)
        assert resolve_api_affinity_token([]) == 'http_api'

    def test_all_non_streaming(self, monkeypatch):
        from task_service.infrastructure.persistence import _task_crud_mixin as mixin
        from task_service.infrastructure.acl import api_acl_repository as acl_mod
        monkeypatch.setattr(acl_mod.api_acl_repository, 'get_api_streaming_flags',
                            lambda ids: {int(i): False for i in ids})
        assert mixin.resolve_api_affinity_token([1, 2]) == 'http_api'

    def test_any_streaming(self, monkeypatch):
        from task_service.infrastructure.persistence import _task_crud_mixin as mixin
        from task_service.infrastructure.acl import api_acl_repository as acl_mod
        monkeypatch.setattr(acl_mod.api_acl_repository, 'get_api_streaming_flags',
                            lambda ids: {int(i): True for i in ids})
        assert mixin.resolve_api_affinity_token([1, 2]) == 'websocket_api'

    def test_mixed_lanes_rejected(self, monkeypatch):
        from task_service.infrastructure.persistence import _task_crud_mixin as mixin
        from task_service.infrastructure.acl import api_acl_repository as acl_mod
        monkeypatch.setattr(acl_mod.api_acl_repository, 'get_api_streaming_flags',
                            lambda ids: {1: False, 2: True})
        with pytest.raises(mixin.ExecutionAffinityError, match='流式性不一致'):
            mixin.resolve_api_affinity_token([1, 2])

    def test_acl_unavailable_rejected(self, monkeypatch):
        from task_service.infrastructure.persistence import _task_crud_mixin as mixin
        from task_service.infrastructure.acl import api_acl_repository as acl_mod
        monkeypatch.setattr(acl_mod.api_acl_repository, 'get_api_streaming_flags',
                            lambda ids: None)
        with pytest.raises(mixin.ExecutionAffinityError, match='取不到'):
            mixin.resolve_api_affinity_token([1])
