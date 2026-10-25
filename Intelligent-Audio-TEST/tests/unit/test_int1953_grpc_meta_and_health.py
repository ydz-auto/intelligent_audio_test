# -*- coding: utf-8 -*-
"""INT-1953（A3 后端对齐）单测：meta.grpc 凭据脱敏 / 写侧校验 / test_connection 按协议分支。

覆盖卡面 §四 验收标准：
1. 脱敏：`GET /apis`、`GET /apis/{id}` 中 `meta.grpc.metadata` 敏感键为 `****`、
   响应体字符串不含明文；非敏感键（x-request-id）原样。
2. 保留语义：回传 `****` 保留库里原值、显式新值覆盖、显式空串删除该键。
3. 写侧校验：8 条规则非法样本各 400 且 message 指明字段；合法样本 201/200；
   `protocol=grpc` 无 `meta.grpc` → 400；非 grpc 协议下脏 `meta.grpc` 同样 400。
4. test_connection：http / websocket 行为原样；SSE 不拼 `/health`；gRPC target
   不再回「不支持的协议」。
"""
import json
import os
import time
import uuid
from types import SimpleNamespace

# 与 tests/unit/test_int839_api_proxy.py 同口径：api_crud_service 导入链拉起
# shared BaseConfig，补齐必填环境变量（不触库 / 不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

import pytest

from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService
from api_test_service.domain.value_objects.grpc_meta import (
    CREDENTIAL_MASK,
    METHOD_KINDS,
    PROTO_MAX_BYTES,
    merge_grpc_metadata_credentials,
    redact_grpc_meta_credentials,
    validate_grpc_meta,
)

GRPC_META = {
    'proto_object_key': 'local://proto/echo.proto',
    'proto_sha256': 'a' * 64,
    'proto_size': 1024,
    'service': 'echo.EchoService',
    'method': 'Echo',
    'method_kind': 'unary',
    'deadline_ms': 5000,
    'metadata': {'authorization': 'Bearer SECRET', 'x-request-id': 'abc'},
    'reflection': False,
}


def _grpc_meta(**overrides):
    """合法 meta.grpc 的浅拷贝 + 覆盖（overrides 值 None 表示删键）。"""
    cfg = dict(GRPC_META)
    for key, value in overrides.items():
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = value
    return {'grpc': cfg}


class _FakeEventBus:
    def publish(self, *args, **kwargs):
        return None


def _fake_api(meta, protocol='http', endpoints=None, api_id=7, status='online'):
    return SimpleNamespace(
        id=api_id,
        name=f'API-{api_id}',
        status=status,
        meta=meta,
        protocol=protocol,
        streaming=False,
        api_endpoints=endpoints if endpoints is not None else
        [{'endpoint': 'http://api.example.com', 'max_timeout': 30}],
        default_max_process=5,
        default_max_timeout=30,
        default_max_audio_duration=60,
        proxy_type=None,
        proxy_url=None,
        output_types=[],
    )


class _ReadRepo:
    def __init__(self, api):
        self.api = api

    def get_api(self, api_id):
        return self.api

    def list_apis(self, **kwargs):
        return {'items': [self.api], 'total': 1, 'page': 1, 'per_page': 10, 'pages': 1}

    def update_api(self, api_id, fields):
        return None


class _WriteRepo:
    """create / update 双用：记录落库字段，update 回读返回带新 meta 的对象。"""

    def __init__(self, api=None):
        self.api = api
        self.captured = {}

    def create_api(self, data):
        self.captured.update(data)
        return SimpleNamespace(id=21)

    def get_api(self, api_id):
        return self.api

    def get_api_meta(self, api_id):
        return self.api.meta if self.api else None

    def update_api(self, api_id, fields):
        self.captured.update(fields)
        merged_meta = fields.get('meta', self.api.meta)
        self.api = SimpleNamespace(**{**vars(self.api), 'meta': merged_meta})
        return self.api


def _install_repo(monkeypatch, repo):
    monkeypatch.setattr(api_crud_module, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(api_crud_module, 'api_test_repository', repo)


def _install_log_noop(monkeypatch):
    monkeypatch.setattr(api_crud_module, 'log_not_emit', lambda **kw: None)


# ═══════════════════ 1. 读侧脱敏 ═══════════════════

class TestReadRedaction:

    def test_get_one_masks_grpc_metadata_credentials(self, monkeypatch):
        repo = _ReadRepo(_fake_api(_grpc_meta(), protocol='grpc'))
        _install_repo(monkeypatch, repo)

        res = APICrudService.get_one(7)

        metadata = res['data']['meta']['grpc']['metadata']
        assert metadata['authorization'] == CREDENTIAL_MASK
        # 非敏感键透传行为不变
        assert metadata['x-request-id'] == 'abc'
        assert 'SECRET' not in json.dumps(res, ensure_ascii=False)
        # 库里原值不被读侧改写（纯派生）
        assert repo.api.meta['grpc']['metadata']['authorization'] == 'Bearer SECRET'

    def test_get_all_masks_grpc_metadata_credentials(self, monkeypatch):
        repo = _ReadRepo(_fake_api(_grpc_meta(), protocol='grpc'))
        _install_repo(monkeypatch, repo)

        res = APICrudService.get_all(page=1, per_page=10)

        item = res['data']['items'][0]
        assert item['meta']['grpc']['metadata']['authorization'] == CREDENTIAL_MASK
        assert 'SECRET' not in json.dumps(res, ensure_ascii=False)

    def test_non_sensitive_only_means_no_new_dict(self):
        meta = {'grpc': {'metadata': {'x-request-id': 'abc'}}}
        assert redact_grpc_meta_credentials(meta) is meta

    @pytest.mark.parametrize('key', [
        'authorization', 'Authorization', 'proxy-authorization', 'x-api-key',
        'api-key', 'apikey', 'token', 'x-auth-token', 'X-Auth-Token',
    ])
    def test_sensitive_key_vocabulary(self, key):
        meta = {'grpc': {'metadata': {key: 'Bearer SECRET'}}}
        assert redact_grpc_meta_credentials(meta)['grpc']['metadata'][key] == CREDENTIAL_MASK


# ═══════════════════ 2. 写侧保留语义 ═══════════════════

class TestUpdateCredentialRetention:

    @pytest.mark.parametrize('sent,expected', [
        (CREDENTIAL_MASK, 'Bearer SECRET'),      # 回传掩码 → 保留库里原值
        ('Bearer NEW', 'Bearer NEW'),            # 显式新值 → 覆盖
        ('', None),                              # 显式空串 → 删除该键
    ])
    def test_roundtrip_semantics(self, monkeypatch, sent, expected):
        stored = _grpc_meta()
        repo = _WriteRepo(_fake_api(stored, protocol='grpc'))
        _install_repo(monkeypatch, repo)
        reads = APICrudService.get_one(7)
        assert reads['data']['meta']['grpc']['metadata']['authorization'] == CREDENTIAL_MASK

        incoming = reads['data']['meta']
        incoming['grpc']['metadata']['authorization'] = sent
        res = APICrudService.update(7, {'meta': incoming})

        assert res['code'] == 200
        stored_metadata = repo.captured['meta']['grpc']['metadata']
        if expected is None:
            assert 'authorization' not in stored_metadata
        else:
            assert stored_metadata['authorization'] == expected
        # 非敏感键照旧透传
        assert stored_metadata['x-request-id'] == 'abc'

    def test_merge_does_not_touch_non_sensitive_values(self):
        incoming = _grpc_meta(metadata={'x-request-id': 'xyz'})
        assert merge_grpc_metadata_credentials(incoming, _grpc_meta()) is incoming

    def test_mask_without_stored_value_is_dropped(self):
        """库里没有该键时，回传的掩码不落库（不把字面量 **** 当凭据存）。"""
        incoming = _grpc_meta(metadata={'authorization': CREDENTIAL_MASK})
        merged = merge_grpc_metadata_credentials(incoming, {'grpc': {'metadata': {}}})
        assert 'authorization' not in merged['grpc']['metadata']


# ═══════════════════ 3. 写侧校验（create + update 共用） ═══════════════════

INVALID_GRPC_META_CASES = [
    # (说明, meta.grpc 覆盖项, 期望 message 片段)
    ('meta.grpc 非对象', 'not-an-object', '必须是'),
    ('缺 proto_object_key', {'proto_object_key': None}, 'proto_object_key'),
    ('缺 service', {'service': None}, 'service'),
    ('缺 method', {'method': None}, 'method'),
    ('缺 method_kind', {'method_kind': None}, 'method_kind'),
    ('reflection 为真', {'reflection': True}, 'reflection'),
    ('method_kind 非法', {'method_kind': 'client_stream'}, 'method_kind'),
    ('deadline_ms 为 0', {'deadline_ms': 0}, 'deadline_ms'),
    ('deadline_ms 为负', {'deadline_ms': -1}, 'deadline_ms'),
    ('deadline_ms 非整数', {'deadline_ms': '5000'}, 'deadline_ms'),
    ('deadline_ms 为布尔', {'deadline_ms': True}, 'deadline_ms'),
    ('metadata 非对象', {'metadata': 'x-request-id: abc'}, 'metadata'),
    ('metadata 键大写', {'metadata': {'Authorization': 'Bearer X'}}, '小写'),
    ('metadata 值含 CRLF', {'metadata': {'x-trace': 'a\nb'}}, 'CR/LF'),
    ('proto_size 为 0', {'proto_size': 0}, 'proto_size'),
    ('proto_size 超上限', {'proto_size': PROTO_MAX_BYTES + 1}, 'proto_size'),
    ('proto_size 非整数', {'proto_size': '1024'}, 'proto_size'),
    ('proto_sha256 非十六进制', {'proto_sha256': 'Z' * 64}, 'proto_sha256'),
    ('proto_sha256 长度错', {'proto_sha256': 'a' * 63}, 'proto_sha256'),
    ('proto_sha256 大写', {'proto_sha256': 'A' * 64}, 'proto_sha256'),
    ('表外未知键', {'unknown_key': 1}, '未知键'),
]


class TestWriteSideValidation:

    @pytest.mark.parametrize('label,override,expected_fragment', INVALID_GRPC_META_CASES,
                             ids=[c[0] for c in INVALID_GRPC_META_CASES])
    def test_create_rejects_invalid_grpc_meta(self, monkeypatch, label, override,
                                              expected_fragment):
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)
        meta = {'grpc': override} if isinstance(override, str) else _grpc_meta(**override)

        res = APICrudService.create({'name': 'API-BAD', 'meta': meta,
                                     'protocol': 'grpc', 'streaming': False})

        assert res['code'] == 400, label
        assert expected_fragment in res['message'], res['message']
        assert repo.captured == {}  # 未落库

    def test_create_accepts_legal_grpc_meta(self, monkeypatch):
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({'name': 'API-OK', 'meta': _grpc_meta(),
                                     'protocol': 'grpc', 'streaming': False})

        assert res['code'] == 201, res['message']
        assert repo.captured['meta']['grpc']['service'] == 'echo.EchoService'

    def test_create_drops_mask_without_stored_value(self, monkeypatch):
        """导出文件回灌：新建时掩码无原值可保留，不把 **** 当凭据落库。"""
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({
            'name': 'API-IMPORT', 'protocol': 'grpc', 'streaming': False,
            'meta': _grpc_meta(metadata={'authorization': CREDENTIAL_MASK,
                                         'x-request-id': 'abc'}),
        })

        assert res['code'] == 201
        stored_metadata = repo.captured['meta']['grpc']['metadata']
        assert 'authorization' not in stored_metadata
        assert stored_metadata['x-request-id'] == 'abc'

    def test_grpc_protocol_requires_meta_grpc(self, monkeypatch):
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({'name': 'API-NOGRPC', 'meta': {},
                                     'protocol': 'grpc', 'streaming': False})

        assert res['code'] == 400
        assert 'meta.grpc' in res['message']

    def test_validation_runs_regardless_of_protocol(self, monkeypatch):
        """存在即校验：http 协议下带脏 meta.grpc 同样 400（不按协议放行）。"""
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({'name': 'API-HTTP', 'meta': _grpc_meta(method_kind='bad'),
                                     'protocol': 'http', 'streaming': False})

        assert res['code'] == 400
        assert 'method_kind' in res['message']

    def test_meta_grpc_absent_on_http_is_fine(self, monkeypatch):
        repo = _WriteRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({'name': 'API-HTTP', 'meta': {'environment': 'dev'},
                                     'protocol': 'http', 'streaming': False})

        assert res['code'] == 201

    def test_update_rejects_invalid_grpc_meta(self, monkeypatch):
        repo = _WriteRepo(_fake_api(_grpc_meta(), protocol='grpc'))
        _install_repo(monkeypatch, repo)

        res = APICrudService.update(7, {'meta': _grpc_meta(deadline_ms=-5)})

        assert res['code'] == 400
        assert 'deadline_ms' in res['message']
        assert repo.captured == {}

    def test_update_switch_to_grpc_without_meta_is_rejected(self, monkeypatch):
        repo = _WriteRepo(_fake_api({'environment': 'dev'}, protocol='http'))
        _install_repo(monkeypatch, repo)

        res = APICrudService.update(7, {'protocol': 'grpc'})

        assert res['code'] == 400
        assert 'meta.grpc' in res['message']


# ═══════════════════ 公共常量同源 ═══════════════════

def test_shared_constants_are_single_source():
    from shared.models import proto_limits
    from api_test_service.domain.value_objects import grpc_meta
    from api_test_service.infrastructure.adapters.transport import grpc_client

    # proto 上限源头在 shared/（网关侧预检也要用，不能反向依赖本服务）
    assert proto_limits.PROTO_MAX_BYTES is PROTO_MAX_BYTES
    assert grpc_meta.PROTO_MAX_BYTES is proto_limits.PROTO_MAX_BYTES
    assert grpc_client.PROTO_MAX_BYTES is proto_limits.PROTO_MAX_BYTES
    assert grpc_client.METHOD_KINDS is METHOD_KINDS
    assert set(METHOD_KINDS) == {'unary', 'server_stream', 'bidi'}


def test_grpc_adapter_reuses_shared_validation():
    from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
    from api_test_service.infrastructure.adapters.transport.grpc_client import GrpcProtoError

    class _Cfg:
        meta = {'grpc': {'proto_object_key': 'local://a.proto', 'service': 's',
                         'method': 'm', 'method_kind': 'client_stream'}}
        api_endpoints = []

    with pytest.raises(GrpcProtoError) as exc:
        GrpcAdapter(_Cfg()).grpc_config()
    assert 'method_kind' in str(exc.value)


def test_validate_grpc_meta_ignores_absent_block_outside_grpc():
    assert validate_grpc_meta({'environment': 'dev'}, protocol='http') is None
    assert validate_grpc_meta(None, protocol='http') is None


# ═══════════════════ 4. test_connection 按协议分支 ═══════════════════

class _HealthRepo:
    def __init__(self, api):
        self.api = api
        self.updated = {}

    def get_api(self, api_id):
        return self.api

    def update_api(self, api_id, fields):
        self.updated.update(fields)
        self.api = SimpleNamespace(**{**vars(self.api), **fields})
        return self.api


def _health_setup(monkeypatch, api):
    repo = _HealthRepo(api)
    _install_repo(monkeypatch, repo)
    _install_log_noop(monkeypatch)
    return repo


class TestTestConnectionByProtocol:

    def test_http_keeps_health_suffix_and_proxies(self, monkeypatch):
        import requests
        captured = {}

        def fake_get(url, **kwargs):
            captured['url'] = url
            captured['proxies'] = kwargs.get('proxies')
            captured['stream'] = kwargs.get('stream')
            return SimpleNamespace(status_code=200, close=lambda: None)

        monkeypatch.setattr(requests, 'get', fake_get)
        api = _fake_api({}, protocol='http',
                        endpoints=[{'endpoint': 'http://api.example.com', 'max_timeout': 30}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'True'
        assert res['data']['status_code'] == 200
        # 存量行为：http 仍拼 /health，且不要求 stream
        assert captured['url'] == 'http://api.example.com/health'
        assert captured['proxies'] is None

    def test_http_failure_message_unchanged(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, 'get', lambda url, **kw: SimpleNamespace(status_code=503))
        api = _fake_api({}, protocol='http',
                        endpoints=[{'endpoint': 'http://api.example.com', 'max_timeout': 30}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'False'
        assert res['data']['error'] == '端点连接失败: 503'

    def test_websocket_branch_unchanged(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def settimeout(self, t):
                captured['timeout'] = t

            def connect(self, url, **kwargs):
                captured['url'] = url

            def close(self):
                captured['closed'] = True

        monkeypatch.setattr(ws_client, 'WebSocket', _FakeWS)
        api = _fake_api({}, protocol='websocket',
                        endpoints=[{'endpoint': 'ws://api.example.com/ws', 'max_timeout': 12}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'True'
        assert captured['url'] == 'ws://api.example.com/ws'
        assert captured['timeout'] == 12
        assert captured.get('closed') is True

    def test_sse_does_not_append_health(self, monkeypatch):
        """现状错误场景①：SSE 端点被拼 /health 去测不存在的路径。"""
        import requests
        captured = {}

        def fake_get(url, **kwargs):
            captured['url'] = url
            captured['stream'] = kwargs.get('stream')
            return SimpleNamespace(status_code=200, close=lambda: None)

        monkeypatch.setattr(requests, 'get', fake_get)
        api = _fake_api({}, protocol='sse',
                        endpoints=[{'endpoint': 'http://10.0.0.5:8080/stream',
                                    'max_timeout': 30}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert captured['url'] == 'http://10.0.0.5:8080/stream'  # 未拼 /health
        assert captured['stream'] is True
        assert res['data']['endpoints_status'] == 'True'
        assert res['data']['status_code'] == 200

    def test_sse_4xx_reports_status_code(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, 'get',
                            lambda url, **kw: SimpleNamespace(status_code=401, close=lambda: None))
        api = _fake_api({}, protocol='sse',
                        endpoints=[{'endpoint': 'http://10.0.0.5:8080/stream',
                                    'max_timeout': 30}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'False'
        assert res['data']['error'] == 'SSE 端点返回 401'
        assert res['data']['status_code'] == 401

    def test_grpc_target_no_longer_unsupported(self, monkeypatch):
        """现状错误场景②：gRPC target 无 scheme → 「不支持的协议: 」。"""
        api = _fake_api({}, protocol='grpc',
                        endpoints=[{'endpoint': '100.70.20.135:5000', 'max_timeout': 5}])
        _health_setup(monkeypatch, api)
        monkeypatch.setattr(APICrudService, '_probe_grpc',
                            classmethod(lambda cls, target, timeout: (12.0, None)))

        res = APICrudService.test_connection(7)

        assert '不支持的协议' not in str(res)
        assert res['data']['endpoints_status'] == 'True'
        assert res['data']['response_time'] == '12.00ms'

    def test_grpc_unreachable_reports_status(self, monkeypatch):
        api = _fake_api({}, protocol='grpc',
                        endpoints=[{'endpoint': '127.0.0.1:1', 'max_timeout': 2}])
        _health_setup(monkeypatch, api)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'False'
        assert 'gRPC 目标不可达' in res['data']['error']
        assert '不支持的协议' not in res['data']['error']

    def test_probe_grpc_ready_against_local_server(self):
        """真实 gRPC 服务：channel_ready_future 就绪即在线。"""
        import grpc
        from concurrent.futures import ThreadPoolExecutor

        server = grpc.server(ThreadPoolExecutor(max_workers=1))
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            duration, error = APICrudService._probe_grpc(f'127.0.0.1:{port}', 5)
            assert error is None
            assert duration >= 0
        finally:
            server.stop(0)

    def test_probe_grpc_unavailable(self):
        """关闭的端口：回 UNAVAILABLE，且不超出探测超时。"""
        sock_probe = __import__('socket').socket()
        sock_probe.bind(('127.0.0.1', 0))
        closed_port = sock_probe.getsockname()[1]
        sock_probe.close()

        started = time.time()
        duration, error = APICrudService._probe_grpc(f'127.0.0.1:{closed_port}', 2)
        elapsed = time.time() - started

        assert error is not None
        assert 'UNAVAILABLE' in error
        assert elapsed < 5  # 不得把请求挂死

    def test_legacy_row_without_protocol_falls_back_to_scheme(self, monkeypatch):
        """protocol 列缺失（老数据）仍按 scheme 分支，存量行为不劣化。"""
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def settimeout(self, t):
                pass

            def connect(self, url, **kwargs):
                captured['url'] = url

            def close(self):
                pass

        monkeypatch.setattr(ws_client, 'WebSocket', _FakeWS)
        api = _fake_api({}, endpoints=[{'endpoint': 'ws://api.example.com/ws',
                                        'max_timeout': 30}])
        del_patched = SimpleNamespace(**{k: v for k, v in vars(api).items() if k != 'protocol'})
        _health_setup(monkeypatch, del_patched)

        res = APICrudService.test_connection(7)

        assert res['data']['endpoints_status'] == 'True'
        assert captured['url'] == 'ws://api.example.com/ws'

    def test_health_log_carries_protocol_name(self, monkeypatch):
        import requests
        logs = []
        monkeypatch.setattr(requests, 'get',
                            lambda url, **kw: SimpleNamespace(status_code=200, close=lambda: None))
        api = _fake_api({}, protocol='sse',
                        endpoints=[{'endpoint': 'http://10.0.0.5:8080/stream',
                                    'max_timeout': 30}])
        _health_setup(monkeypatch, api)
        monkeypatch.setattr(api_crud_module, 'log_not_emit',
                            lambda **kw: logs.append(kw))

        APICrudService.test_connection(7)

        assert logs and logs[0]['category'] == 'HealthCheck'
        assert 'sse' in logs[0]['content']
