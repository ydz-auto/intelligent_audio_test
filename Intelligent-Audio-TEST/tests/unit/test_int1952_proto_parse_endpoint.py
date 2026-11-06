# -*- coding: utf-8 -*-
"""INT-1952 proto 上传与符号解析端点单测（api_test_service + 网关）。

覆盖卡面 §六 第 1 条清单：
- 内容类错误 → code 400 且文案含实际原因（大小 / 非 UTF-8 / 非法 import /
  编译失败 / 无 service），存储不可用 → code 503（不被压成 400）；
- sha256 / size 由服务端计算，与独立计算结果一致；
- 幂等 = 同 key 覆盖写：同内容二次上传返回同一 object_key，且**未调用 exists()**；
- 网关权限：缺 `api_config:create` → 403（走真实 `require_permission` 依赖）；
- 网关巨型 body 预检：Content-Length 与无该头（chunked）两条路都在调 RPC 之前拒绝；
- 网关常量 == shared 常量（防漂移）；
- 端到端：真实 servicer + multipart 上传 → 符号表 → 把返回值填进 `meta.grpc`
  后执行期 `grpc_config()` + `_proto_bytes()` 通过校验。
"""
import hashlib
import io
import json
import os
import types

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import StorageUnavailableError
from shared.models.proto_limits import PROTO_MAX_BYTES as SHARED_PROTO_MAX_BYTES
from shared.proto import api_test_service_pb2 as api_pb

import api_test_service.application.api_proto_service as proto_app
from api_test_service.application.api_proto_service import (
    CODE_STORAGE_UNAVAILABLE,
    ApiProtoService,
    ProtoParseError,
)
from api_test_service.infrastructure.adapters.transport.grpc_client import (
    clear_proto_cache,
)
from api_test_service.interfaces.grpc.servicers import APITestServiceServicer

VALID_PROTO = """\
syntax = "proto3";
package wiring;

import "google/protobuf/timestamp.proto";

message EchoRequest {
  string text = 1;
  Nested nested = 2;
  google.protobuf.Timestamp at = 3;
}

message Nested {
  string id = 1;
  Nested child = 2;
}

message EchoReply {
  string text = 1;
}

service WiringEcho {
  rpc Say (EchoRequest) returns (EchoReply);
  rpc Stream (EchoRequest) returns (stream EchoReply);
  rpc ClientOnly (stream EchoRequest) returns (EchoReply);
}
"""
VALID_BYTES = VALID_PROTO.encode('utf-8')


# ── 存储替身：只落本地目录、记录调用（绝不调 exists）──────────────────────

class _FakeStorage:
    def __init__(self, local_root: str, fail=None):
        self.local_root = local_root
        self.fail = fail
        self.saved = []
        self.exists_calls = 0

    def save_bytes(self, data, category, key, content_type=None,
                   allow_fallback=True):
        if self.fail is not None:
            raise self.fail
        self.saved.append({'category': category, 'key': key, 'size': len(data),
                           'content_type': content_type,
                           'allow_fallback': allow_fallback})
        dst = os.path.join(self.local_root, category, key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as fh:
            fh.write(data)
        return f'local://{category}/{key}'

    def exists(self, *args, **kwargs):
        self.exists_calls += 1
        return True


@pytest.fixture()
def fake_storage(tmp_path, monkeypatch):
    """把应用服务的 storage 换成落临时目录的替身（执行期读回也走真 Storage）。"""
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
    store = _FakeStorage(str(tmp_path))
    monkeypatch.setattr(proto_app, 'storage', store)
    return store


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_proto_cache()
    yield
    clear_proto_cache()


# ── 1. 应用服务：内容类错误 / 存储错误 ────────────────────────────────────

class TestParseServiceErrors:

    def test_empty_content(self, fake_storage):
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', b'')
        assert excinfo.value.code == 400
        assert '未收到 proto 文件' in str(excinfo.value)

    def test_size_over_limit(self, fake_storage):
        oversized = b'# ' + b'a' * SHARED_PROTO_MAX_BYTES
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', oversized)
        assert excinfo.value.code == 400
        assert f'{SHARED_PROTO_MAX_BYTES} 字节上限' in str(excinfo.value)
        assert f'实际 {len(oversized)}' in str(excinfo.value)
        assert fake_storage.saved == []

    def test_non_utf8(self, fake_storage):
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', b'syntax = "proto3";\n\xff\xfe')
        assert excinfo.value.code == 400
        assert 'UTF-8' in str(excinfo.value)

    def test_illegal_import(self, fake_storage):
        proto = b'syntax = "proto3";\nimport "other/x.proto";\n'
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', proto)
        assert excinfo.value.code == 400
        assert '白名单' in str(excinfo.value)

    def test_compile_failure(self, fake_storage):
        proto = b'syntax = "proto3";\nmessage Bad { string }\n'
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', proto)
        assert excinfo.value.code == 400
        assert '编译失败' in str(excinfo.value)

    def test_no_callable_service(self, fake_storage):
        proto = b'syntax = "proto3";\npackage x;\nmessage M { string a = 1; }\n'
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', proto)
        assert excinfo.value.code == 400
        assert '没有可调用的 service' in str(excinfo.value)
        assert fake_storage.saved == []

    def test_storage_unavailable_is_503(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
        store = _FakeStorage(str(tmp_path),
                             fail=StorageUnavailableError('oss down'))
        monkeypatch.setattr(proto_app, 'storage', store)
        with pytest.raises(ProtoParseError) as excinfo:
            ApiProtoService.parse('x.proto', VALID_BYTES)
        assert excinfo.value.code == CODE_STORAGE_UNAVAILABLE == 503
        assert str(excinfo.value).startswith('存储不可用')


# ── 2. 应用服务：成功 / 幂等 / 服务端计算 ────────────────────────────────

class TestParseServiceSuccess:

    def test_sha_size_computed_server_side(self, fake_storage):
        data = ApiProtoService.parse('wiring.proto', VALID_BYTES)
        assert data['sha256'] == hashlib.sha256(VALID_BYTES).hexdigest()
        assert data['size'] == len(VALID_BYTES)
        assert data['object_key'] == f"local://api-protos/{data['sha256']}.proto"

    def test_symbol_table_matches_descriptor(self, fake_storage):
        data = ApiProtoService.parse('wiring.proto', VALID_BYTES)
        assert [svc['name'] for svc in data['services']] == ['wiring.WiringEcho']
        methods = {m['name']: m for m in data['services'][0]['methods']}
        assert set(methods) == {'Say', 'Stream'}  # ClientOnly 是 client-streaming
        assert methods['Say']['method_kind'] == 'unary'
        assert methods['Stream']['method_kind'] == 'server_stream'
        assert methods['Say']['input_type'] == 'wiring.EchoRequest'
        paths = [f['path'] for f in methods['Say']['input_fields']]
        # 第 2 层展开；nested.child 是自引用，只给类型名不再往下展开
        assert paths == ['text', 'nested', 'nested.id', 'nested.child', 'at']

    def test_idempotent_same_key_and_no_exists_probe(self, fake_storage):
        first = ApiProtoService.parse('wiring.proto', VALID_BYTES)
        second = ApiProtoService.parse('wiring.proto', VALID_BYTES)
        assert first['object_key'] == second['object_key']
        assert fake_storage.exists_calls == 0           # 不做 exists() 预检
        assert len(fake_storage.saved) == 2             # 同 key 覆盖写
        assert all(item['allow_fallback'] is False for item in fake_storage.saved)
        assert all(item['category'] == 'api-protos' for item in fake_storage.saved)

    def test_client_filename_not_used_for_storage_or_compile(self, fake_storage):
        data = ApiProtoService.parse('../../evil/x.proto', VALID_BYTES)
        assert data['object_key'].endswith(f"/{data['sha256']}.proto")
        assert 'evil' not in data['object_key']
        assert not os.path.exists(os.path.join(str(fake_storage.local_root), 'evil'))


# ── 3. servicer：code 通道 ───────────────────────────────────────────────

class TestServicerParseProto:

    def test_success_returns_code_zero_and_json(self, fake_storage):
        servicer = APITestServiceServicer()
        resp = servicer.ParseProto(api_pb.ParseProtoRequest(
            filename='wiring.proto', content=VALID_BYTES))
        assert resp.success is True
        assert resp.code == 0
        payload = json.loads(resp.data)
        assert payload['sha256'] == hashlib.sha256(VALID_BYTES).hexdigest()
        assert payload['services'][0]['name'] == 'wiring.WiringEcho'

    def test_content_error_returns_code_400(self, fake_storage):
        servicer = APITestServiceServicer()
        resp = servicer.ParseProto(api_pb.ParseProtoRequest(content=b''))
        assert resp.success is False
        assert resp.code == 400
        assert '未收到 proto 文件' in resp.message

    def test_storage_unavailable_returns_code_503(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
        monkeypatch.setattr(proto_app, 'storage',
                            _FakeStorage(str(tmp_path),
                                         fail=StorageUnavailableError('oss down')))
        servicer = APITestServiceServicer()
        resp = servicer.ParseProto(api_pb.ParseProtoRequest(content=VALID_BYTES))
        assert resp.success is False
        assert resp.code == 503          # 不被压成 400

    def test_unexpected_error_returns_code_500(self, monkeypatch):
        class _Boom:
            @staticmethod
            def parse(filename, content):
                raise RuntimeError('boom')

        servicer = APITestServiceServicer()
        monkeypatch.setattr(servicer, '_proto_service', _Boom)
        resp = servicer.ParseProto(api_pb.ParseProtoRequest(content=VALID_BYTES))
        assert resp.success is False
        assert resp.code == 500


# ── 4. 网关：权限 / 预检 / 常量 ──────────────────────────────────────────

class _PermissionsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, permissions):
        super().__init__(app)
        self._permissions = permissions

    async def dispatch(self, request, call_next):
        request.state.permissions = self._permissions
        return await call_next(request)


def _gateway_app(monkeypatch, permissions=None, acl_result=None, on_call=None):
    """只挂 api_bp 的迷你网关（RequestAdapter 预解析 multipart）。"""
    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes.api_bp import router
    import api_gateway.application.services.api.api_command_service as cmd_service

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    if permissions is not None:
        app.add_middleware(_PermissionsMiddleware, permissions=permissions)
    app.include_router(router, prefix='/api/v1/apis')

    def _parse_proto(filename, content):
        if on_call is not None:
            on_call(filename, content)
        return acl_result or {'success': True, 'message': '',
                              'data': {'object_key': 'local://api-protos/x.proto'},
                              'code': 0}

    monkeypatch.setattr(cmd_service._api_acl, 'parse_proto', _parse_proto)
    return app


class TestGatewayEndpoint:

    def test_missing_permission_is_403(self, monkeypatch):
        client = TestClient(_gateway_app(monkeypatch, permissions=[]))
        resp = client.post('/api/v1/apis/proto',
                           files={'file': ('wiring.proto', VALID_BYTES, 'text/plain')})
        assert resp.status_code == 403
        assert 'api_config:create' in resp.json()['detail']

    def test_upload_ok_forwards_basename_and_bytes(self, monkeypatch):
        calls = []
        app = _gateway_app(monkeypatch, permissions={'api_config:create'},
                           on_call=lambda f, c: calls.append((f, c)))
        client = TestClient(app)
        resp = client.post('/api/v1/apis/proto',
                           files={'file': ('..\\..\\wiring.proto', VALID_BYTES,
                                           'text/plain')})
        assert resp.status_code == 200
        assert calls and calls[0][0] == 'wiring.proto'   # basename 归一
        assert calls[0][1] == VALID_BYTES

    def test_storage_unavailable_maps_to_503(self, monkeypatch):
        app = _gateway_app(monkeypatch, permissions={'*'},
                           acl_result={'success': False, 'data': None,
                                       'message': '存储不可用: oss down', 'code': 503})
        resp = TestClient(app).post(
            '/api/v1/apis/proto',
            files={'file': ('wiring.proto', VALID_BYTES, 'text/plain')})
        assert resp.status_code == 503
        assert '存储不可用' in resp.json()['message']

    def test_content_length_over_ceiling_rejected_before_rpc(self, monkeypatch):
        calls = []
        app = _gateway_app(monkeypatch, permissions={'*'},
                           on_call=lambda f, c: calls.append(f))
        oversized = b'# ' + b'a' * SHARED_PROTO_MAX_BYTES
        resp = TestClient(app).post(
            '/api/v1/apis/proto',
            files={'file': ('big.proto', oversized, 'text/plain')})
        assert resp.status_code == 400
        assert '字节上限' in resp.json()['message']
        assert calls == []                     # 在调 RPC 之前拒绝

    def test_chunked_without_content_length_rejected_before_rpc(self, monkeypatch,
                                                                tmp_path):
        """无 Content-Length（chunked）→ 按块读满上限 + 1 即拒，不调 RPC。"""
        from api_gateway.infrastructure import request_adapter
        import api_gateway.application.services.api.api_command_service as cmd_service

        calls = []
        app = _gateway_app(monkeypatch, permissions={'*'},
                           on_call=lambda f, c: calls.append(f))
        assert app  # 仅用于 monkeypatch ACL；本用例直接驱动应用服务

        oversized = b'#' + b'a' * SHARED_PROTO_MAX_BYTES
        upload = types.SimpleNamespace(
            filename='big.proto', name='file', content_type='text/plain',
            file=io.BytesIO(oversized))
        fake_request = types.SimpleNamespace(
            state=types.SimpleNamespace(_files={'file': upload}),
            headers={},                      # 没有 content-length → chunked 路径
            method='POST',
        )
        request_adapter.set_current_request(fake_request)
        try:
            payload, http_code = cmd_service.ApiCommandService.parse_proto()
        finally:
            request_adapter.set_current_request(None)

        assert http_code == 400
        assert '字节上限' in payload['message']
        assert calls == []

    def test_gateway_constants_match_shared(self):
        from api_gateway.application.services.api import proto_upload
        from api_test_service.infrastructure.adapters.transport import grpc_client

        assert proto_upload.PROTO_MAX_BYTES == SHARED_PROTO_MAX_BYTES
        assert grpc_client.PROTO_MAX_BYTES == SHARED_PROTO_MAX_BYTES


# ── 5. 端到端：multipart → 真实 servicer → 符号表 → 执行期读回 ────────────

class TestUploadEndToEnd:

    def test_upload_then_execution_side_validation(self, tmp_path, monkeypatch):
        import api_gateway.infrastructure.grpc_proxies.api_config_proxies as proxies

        monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
        monkeypatch.setattr(proto_app, 'storage', _FakeStorage(str(tmp_path)))

        servicer = APITestServiceServicer()
        stub = types.SimpleNamespace(ParseProto=servicer.ParseProto)
        monkeypatch.setattr(proxies, 'get_api_test_service_stub', lambda: stub)

        app = _gateway_app(monkeypatch, permissions={'api_config:create'},
                           acl_result=None)
        # 恢复真实 ACL（上面 acl_result=None 已返回占位 data，这里换回真链路）
        import api_gateway.application.services.api.api_command_service as cmd_service
        from api_gateway.infrastructure.acl import ApiConfigAclRepositoryImpl
        monkeypatch.setattr(cmd_service._api_acl, 'parse_proto',
                            ApiConfigAclRepositoryImpl().parse_proto)

        resp = TestClient(app).post(
            '/api/v1/apis/proto',
            files={'file': ('wiring.proto', VALID_BYTES, 'text/plain')})
        assert resp.status_code == 200, resp.text
        data = resp.json()['data']
        assert data['sha256'] == hashlib.sha256(VALID_BYTES).hexdigest()
        assert data['size'] == len(VALID_BYTES)
        assert data['object_key'] == f"local://api-protos/{data['sha256']}.proto"
        assert [svc['name'] for svc in data['services']] == ['wiring.WiringEcho']

        # 把返回的元信息填进 meta.grpc → 执行期（未改动）能通过校验并解析方法
        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter

        api_config = types.SimpleNamespace(
            meta={'grpc': {
                'proto_object_key': data['object_key'],
                'proto_sha256': data['sha256'],
                'proto_size': data['size'],
                'service': 'wiring.WiringEcho',
                'method': 'Say',
                'method_kind': 'unary',
            }},
            api_endpoints=[{'endpoint': '127.0.0.1:1'}],
        )
        adapter = GrpcAdapter(api_config, {})
        cfg = adapter.grpc_config()
        raw = adapter._proto_bytes(cfg)
        assert raw == VALID_BYTES
        assert hashlib.sha256(raw).hexdigest() == data['sha256']
        method = adapter.method()
        assert method.kind == 'unary'
        assert method.path == '/wiring.WiringEcho/Say'
