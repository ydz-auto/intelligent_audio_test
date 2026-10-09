# -*- coding: utf-8 -*-
"""INT-29 验收测试（测试工程师独立验收，与开发自测互补）。

对应验收标准：
1. 能力注册表可注册/发现/禁用 THIRD_PARTY_C 能力
   —— 经真实 HTTP 服务（uvicorn port=0）验证 evaluation_service 4 个能力管理端点：
      注册/发现/禁用/启用/持久化/热加载/非法值 fail-closed，禁用后 resolve 回落 LOCAL。
2. EVAL_REQUEST → EVAL_RESULT 全流程联调
   —— 注册表驱动适配形态端到端：注册表登记 presigned_url 后，ACL 未显式指定
      adapter_kind 时按注册表选择 B→C 形态（排除 settings 默认值的假阳性）。
3. 幂等去重与失败重试在链路层可验证；审计事件完整
   —— 确定性打包（幂等重发判重前提）；transfer_agent 不可达时 __error__ 秒级收敛
      不悬挂；C 端 4xx 不重试且链路收敛、审计 Failed 事件带 stage。

开发自测未覆盖的补充点：注册表 HTTP 管理端点（0 测试）、注册表驱动适配形态、
TA 不可达收敛、4xx 链路级收敛、确定性打包。
"""
import hashlib
import json
import os
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
import requests

import evaluation_service.interfaces.api.routes as evaluation_routes
import transfer_agent.interfaces.api.routes as transfer_routes
from evaluation_service.domain.events.evaluation_events import (
    ThirdPartyEvalCompleted,
    ThirdPartyEvalDispatched,
    ThirdPartyEvalFailed,
)
from evaluation_service.domain.services.evaluation_capability_registry import (
    EvaluationCapabilityRegistry,
)
from evaluation_service.domain.services import (
    evaluation_capability_registry as registry_module,
)
from evaluation_service.infrastructure.acl.third_party_eval_acl import (
    ThirdPartyEvalACL,
    ThirdPartyEvalSettings,
)
from evaluation_service.infrastructure.acl.third_party_outbound_adapter import (
    ThirdPartyEvalAdapterFactory,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import TransferEvalClient
from tests.unit.test_transfer_handlers import FakeChunkRepo, FakeRecordRepo, FakeStorage

TOKENS = {'A_B': 'secret-ab', 'B_C': 'secret-bc'}
CHUNK = 1024
AUDIO_BYTES = b'RIFF' + os.urandom(2 * 1024)


# ================= 模拟 C 区端点（multipart / presigned / 失败注入） =================
def _disp_attr(disposition: str, attr: str):
    import re
    match = re.search(f'{attr}="([^"]*)"', disposition)
    return match.group(1) if match else None


def parse_multipart(body: bytes, content_type: str):
    boundary = content_type.split('boundary=', 1)[1].split(';', 1)[0].strip().encode()
    parts = body.split(b'--' + boundary)
    fields, files = {}, {}
    for part in parts[1:-1]:
        part = part.lstrip(b'\r\n')
        if not part or part == b'--':
            continue
        header_blob, _, content = part.partition(b'\r\n\r\n')
        if content.endswith(b'\r\n'):
            content = content[:-2]
        disposition = ''
        for line in header_blob.split(b'\r\n'):
            key, _, value = line.partition(b':')
            if key.decode().strip().lower() == 'content-disposition':
                disposition = value.decode().strip()
        name = _disp_attr(disposition, 'name')
        if name is None:
            continue
        if _disp_attr(disposition, 'filename'):
            files[name] = content
        else:
            fields[name] = content.decode('utf-8')
    return fields, files


class FakeCEndpointHandler(BaseHTTPRequestHandler):
    """C 区替身：multipart/presigned 契约 + 幂等计数 + 失败模式注入。

    fail_mode: None | 'always_400'（持久 4xx）| 'first_500'（瞬时 5xx）
    """

    def log_message(self, *args):
        pass

    @property
    def state(self):
        return self.server.state

    def _reply(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length)

    def _record_hit(self, transfer_id):
        self.state['hits'][transfer_id] = self.state['hits'].get(transfer_id, 0) + 1
        fail_mode = self.state['fail_mode']
        if fail_mode == 'always_400':
            self._reply(400, {'msg': 'simulated permanent client error'})
            return True
        if fail_mode == 'first_500' and self.state['hits'][transfer_id] == 1:
            self._reply(500, {'msg': 'simulated transient failure'})
            return True
        return False

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        content_type = self.headers.get('Content-Type', '')
        if path == '/evaluate':
            if content_type.startswith('multipart/form-data'):
                fields, files = parse_multipart(self._read_body(), content_type)
                tid = fields.get('transfer_id', '')
                self.state['last_multipart_files'] = {
                    k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
                if not self._record_hit(tid):
                    self._reply(200, {'code': 0, 'msg': 'ok',
                                      'data': {'result': {'score': 0.88}}})
            else:
                body = json.loads(self._read_body() or b'{}')
                tid = body.get('transfer_id', '')
                self.state['last_json_body'] = body
                if not self._record_hit(tid):
                    self._reply(200, {'code': 0, 'msg': 'ok',
                                      'data': {'result': {'score': 0.88}}})
        elif path == '/upload-url':
            body = json.loads(self._read_body() or b'{}')
            self.state['upload_seq'] += 1
            seq = self.state['upload_seq']
            self.state['presigned'].setdefault(body.get('transfer_id', ''), []).append(body)
            host, port = self.server.server_address[:2]
            self._reply(200, {'upload_url': f'http://{host}:{port}/upload/{seq}',
                              'object_ref': f'obj-{seq}'})
        else:
            self._reply(404, {'msg': 'not found'})

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/upload/'):
            self.state['uploads'][path] = self._read_body()
            self._reply(200, {})
        else:
            self._reply(404, {})


@pytest.fixture(scope='module')
def fake_c():
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeCEndpointHandler)
    server.state = {'hits': {}, 'fail_mode': None, 'presigned': {}, 'uploads': {},
                    'upload_seq': 0, 'last_multipart_files': {}, 'last_json_body': {}}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f'http://{host}:{port}', server.state
    server.shutdown()
    server.server_close()


# ================= transfer_agent 真实路由栈（内存仓储 + 出站投递腿） =================
@pytest.fixture(scope='module')
def transfer_http(fake_c):
    c_url, _ = fake_c
    record_repo, chunk_repo, storage = FakeRecordRepo(), FakeChunkRepo(), FakeStorage()
    from transfer_agent.application.handlers.transfer_handlers import (
        TransferCommandHandler,
        TransferQueryHandler,
    )
    from transfer_agent.application.services.outbound_delivery_service import (
        OutboundDeliveryService,
    )
    from transfer_agent.domain.services.signature_service import SignatureService
    from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy
    from transfer_agent.infrastructure.acl.c_api_client import ThirdPartyCAPIClient
    command_handler = TransferCommandHandler(
        record_repo=record_repo, chunk_repo=chunk_repo, storage=storage,
        signature_service=SignatureService(TOKENS),
        ttl_bounds=(60, 7 * 86400), default_chunk_size=CHUNK,
    )
    query_handler = TransferQueryHandler(
        record_repo=record_repo, chunk_repo=chunk_repo,
        signature_service=SignatureService(TOKENS),
    )
    # 出站投递腿（B→C 数据面）：C 客户端指向模拟 C 端点，重试退避压缩到测试节奏
    outbound_service = OutboundDeliveryService(
        record_repo=record_repo, storage=storage, route_policy=ZoneRoutePolicy(),
        c_client=ThirdPartyCAPIClient(base_url=c_url, timeout_seconds=5,
                                      max_retries=3, backoff_seconds=0.05),
        signature_service=SignatureService(TOKENS), outbound_zone='B',
    )
    original_command = transfer_routes._command_handler
    original_query = transfer_routes._query_handler
    original_outbound = transfer_routes._outbound_service
    transfer_routes._command_handler = command_handler
    transfer_routes._query_handler = query_handler
    transfer_routes._outbound_service = outbound_service
    try:
        import uvicorn
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(transfer_routes.router)
        config = uvicorn.Config(app, host='127.0.0.1', port=0, lifespan='off',
                                log_level='error')
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, 'transfer_agent uvicorn 启动失败'
        host, port = server.servers[0].sockets[0].getsockname()[:2]
        yield f'http://{host}:{port}', record_repo
        server.should_exit = True
        thread.join(timeout=5)
    finally:
        transfer_routes._command_handler = original_command
        transfer_routes._query_handler = original_query
        transfer_routes._outbound_service = original_outbound


# ================= 被测 ACL 装配 =================
def write_capability_config(base_dir, dimensions, third_party_overrides=None):
    os.makedirs(base_dir, exist_ok=True)
    config_path = os.path.join(base_dir, 'eval_capability_config.json')
    third_party = {
        'self_zone': 'B', 'hub_zone': 'B',
        'transfer_agent_base_url': 'http://127.0.0.1:5010',
        'hub_transfer_agent_base_url': 'http://127.0.0.1:5010',
        'c_api_base_url': 'http://127.0.0.1:5101',
        'adapter': 'multipart',
        'timeout_seconds': 10, 'max_retries': 3, 'backoff_seconds': 0.05,
        'staging_enabled': True, 'staging_ttl_seconds': 600,
        'sync_back_enabled': False, 'sync_back_zone': 'A',
        'response_required_keys': [],
    }
    third_party.update(third_party_overrides or {})
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump({'dimension_capabilities': dimensions, 'third_party': third_party},
                  f, ensure_ascii=False)
    return config_path


def group_kwargs(transfer_id=None):
    return dict(
        payload={'task_type': 'llm_judge'},
        form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
        files={'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
        representative_dim_data={'id': 7, 'name': 'llm_judge',
                                 'task_type_code': 'llm_judge', 'dimension_type': 'main'},
        dim_names=['llm_judge'],
        dim_info={'task_type_code': 'llm_judge'},
        task_id=901, test_case_id='9001',
        transfer_id=transfer_id,
    )


def build_acl(config_path, ta_url, c_url, events=None, tokens=None, registry=None):
    settings = ThirdPartyEvalSettings(config_path=config_path)
    client = TransferEvalClient(base_url=ta_url, tokens=tokens or TOKENS,
                                timeout_seconds=10, chunk_size=CHUNK)
    return ThirdPartyEvalACL(
        settings=settings, registry=registry,
        adapter_factory=ThirdPartyEvalAdapterFactory(),
        client=client, event_sink=(events.append if events is not None else None))


# ============================================================================
# 验收标准 1：能力注册表可注册/发现/禁用 THIRD_PARTY_C 能力（HTTP 管理端点）
# ============================================================================
@pytest.fixture(scope='module')
def capability_http(tmp_path_factory):
    """真实 HTTP 服务挂 evaluation_service 路由，注册表单例绑定临时配置文件。"""
    config_path = write_capability_config(tmp_path_factory.mktemp('cap_cfg'), [])
    registry = EvaluationCapabilityRegistry(config_path=config_path, persist=True)
    original = registry_module.evaluation_capability_registry
    registry_module.evaluation_capability_registry = registry
    try:
        import uvicorn
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(evaluation_routes.router)
        config = uvicorn.Config(app, host='127.0.0.1', port=0, lifespan='off',
                                log_level='error')
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, 'evaluation_service uvicorn 启动失败'
        host, port = server.servers[0].sockets[0].getsockname()[:2]
        yield f'http://{host}:{port}/api/evaluation', registry, config_path
        server.should_exit = True
        thread.join(timeout=5)
    finally:
        registry_module.evaluation_capability_registry = original


class TestAcceptance1CapabilityRegistryHTTP:
    """AC1：注册 / 发现 / 禁用 / 启用 / 持久化 / 热加载 / fail-closed / 禁用回落 LOCAL。"""

    def test_register_discover_disable_enable_lifecycle(self, capability_http):
        base_url, registry, config_path = capability_http

        # 注册 THIRD_PARTY_C 能力
        resp = requests.post(f'{base_url}/capabilities', json={
            'dimension': 'llm_judge', 'target': 'THIRD_PARTY_C',
            'adapter': 'multipart', 'enabled': True})
        assert resp.status_code == 200
        assert resp.json()['success'] is True
        assert resp.json()['data']['target'] == 'THIRD_PARTY_C'

        # 发现：列表含该能力
        listed = requests.get(f'{base_url}/capabilities').json()
        dims = {e['dimension']: e for e in listed['data']}
        assert dims['llm_judge']['target'] == 'THIRD_PARTY_C'
        assert dims['llm_judge']['enabled'] is True

        # 注册状态持久化到配置文件（重启不丢）
        with open(config_path, 'r', encoding='utf-8') as f:
            persisted = json.load(f)
        assert any(e['dimension'] == 'llm_judge' and e['target'] == 'THIRD_PARTY_C'
                   for e in persisted['dimension_capabilities'])

        # 禁用：enabled=False，resolve 回落 None（调用方视为 LOCAL）
        disabled = requests.post(f'{base_url}/capabilities/llm_judge/disable').json()
        assert disabled['success'] is True and disabled['data']['enabled'] is False
        assert registry.resolve({'task_type_code': 'llm_judge'}) is None

        # 启用：恢复第三方路由
        enabled = requests.post(f'{base_url}/capabilities/llm_judge/enable').json()
        assert enabled['success'] is True and enabled['data']['enabled'] is True
        entry = registry.resolve({'task_type_code': 'llm_judge'})
        assert entry is not None and entry.target.value == 'THIRD_PARTY_C'

    def test_register_rejects_invalid_values_fail_closed(self, capability_http):
        base_url, _, _ = capability_http
        bad_target = requests.post(f'{base_url}/capabilities', json={
            'dimension': 'dim_x', 'target': 'SOMEWHERE_ELSE'}).json()
        assert bad_target['success'] is False and '非法' in bad_target['message']
        bad_adapter = requests.post(f'{base_url}/capabilities', json={
            'dimension': 'dim_x', 'target': 'THIRD_PARTY_C',
            'adapter': 'carrier_pigeon'}).json()
        assert bad_adapter['success'] is False and '非法' in bad_adapter['message']
        empty_dim = requests.post(f'{base_url}/capabilities', json={
            'dimension': '', 'target': 'LOCAL'}).json()
        assert empty_dim['success'] is False
        listed = requests.get(f'{base_url}/capabilities').json()
        assert not any(e['dimension'] == 'dim_x' for e in listed['data'])

    def test_hot_reload_from_external_config_change(self, capability_http):
        base_url, registry, config_path = capability_http
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['dimension_capabilities'] = [
            {'dimension': 'ext_dim', 'target': 'THIRD_PARTY_C',
             'adapter': 'presigned_url', 'enabled': True}]
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        future = time.time() + 120
        os.utime(config_path, (future, future))  # 强制 mtime 变化触发热加载

        listed = requests.get(f'{base_url}/capabilities').json()
        dims = {e['dimension']: e for e in listed['data']}
        assert 'ext_dim' in dims, '外部配置修改未热加载'
        assert dims['ext_dim']['adapter'] == 'presigned_url'

    def test_repo_default_config_third_party_disabled(self):
        """仓库默认配置 fail-safe：THIRD_PARTY_C 项默认禁用，不改变现网评估行为。"""
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        config_path = os.path.join(repo_root, 'shared', 'config',
                                   'evaluation_capability_config.json')
        registry = EvaluationCapabilityRegistry(config_path=config_path, persist=False)
        for entry in registry.list_capabilities():
            if entry['target'] == 'THIRD_PARTY_C':
                assert entry['enabled'] is False, \
                    f"默认配置 {entry['dimension']} 未禁用（fail-safe 破坏）"


# ============================================================================
# 验收标准 2/3：链路层（注册表驱动形态 / 失败收敛 / 审计 / 幂等前提）
# ============================================================================
class TestAcceptance23LinkLayer:

    def test_registry_drives_adapter_form_end_to_end(self, tmp_path, fake_c, transfer_http):
        """AC1→AC2 贯通：注册表登记 presigned_url 后，ACL 按注册表选择 B→C 形态。"""
        c_url, c_state = fake_c
        ta_url, _ = transfer_http
        config = write_capability_config(tmp_path, [
            {'dimension': 'llm_judge', 'target': 'THIRD_PARTY_C',
             'adapter': 'presigned_url', 'enabled': True},
        ], {'c_api_base_url': c_url})
        registry = EvaluationCapabilityRegistry(config_path=config, persist=False)
        acl = build_acl(config, ta_url, c_url, registry=registry)
        kwargs = group_kwargs(transfer_id='reg-form-1')
        kwargs.pop('adapter_kind', None)  # 不显式指定，注册表说了算

        resp = acl.evaluate_dimension_group(**kwargs)

        assert resp['code'] == 0, f'链路失败: {resp}'
        assert c_state['presigned'].get('reg-form-1'), \
            '注册表 presigned_url 未生效（走了 settings 默认 multipart）'
        uploaded = list(c_state['uploads'].values())
        assert uploaded and AUDIO_BYTES in uploaded, '预签名 PUT 字节与源文件不一致'

    def test_deterministic_packing_same_input_same_bytes(self, tmp_path, fake_c, transfer_http):
        """AC3 幂等前提：同输入两次打包字节一致；输入不同则包不同。"""
        c_url, _ = fake_c
        ta_url, _ = transfer_http
        config = write_capability_config(tmp_path, [], {'c_api_base_url': c_url})
        acl = build_acl(config, ta_url, c_url)
        request = acl._build_request('det-tid', {'task_type': 'llm_judge'},
                                     {'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
                                     {'task_id': 1})
        path1 = acl._pack_bundle(request)
        path2 = acl._pack_bundle(request)
        try:
            with open(path1, 'rb') as f1, open(path2, 'rb') as f2:
                assert f1.read() == f2.read(), '同输入打包结果字节不一致，幂等判重前提不成立'
        finally:
            os.remove(path1)
            os.remove(path2)

    def test_transfer_agent_unreachable_converges_fast(self, tmp_path, fake_c, transfer_http):
        """AC3：transfer_agent 不可达 → __error__ 秒级收敛（不悬挂）+ 审计 Failed(stage=transfer)。"""
        c_url, _ = fake_c
        ta_url, _ = transfer_http
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        dead_port = sock.getsockname()[1]
        sock.close()  # 必然连接拒绝的端口
        config = write_capability_config(tmp_path, [], {
            'transfer_agent_base_url': f'http://127.0.0.1:{dead_port}',
            'hub_transfer_agent_base_url': f'http://127.0.0.1:{dead_port}',
            'c_api_base_url': c_url})
        events = []
        acl = build_acl(config, f'http://127.0.0.1:{dead_port}', c_url, events=events)

        started = time.monotonic()
        resp = acl.evaluate_dimension_group(**group_kwargs(transfer_id='ta-down-1'))
        elapsed = time.monotonic() - started

        assert '__error__' in resp, f'不可达未收敛为错误: {resp}'
        assert elapsed < 15, f'收敛耗时 {elapsed:.1f}s，任务可能悬挂'
        failed = [e for e in events if isinstance(e, ThirdPartyEvalFailed)]
        assert len(failed) == 1 and failed[0].stage == 'transfer'
        assert not [e for e in events if isinstance(e, ThirdPartyEvalCompleted)]

    def test_c_permanent_4xx_no_retry_and_converges(self, tmp_path, fake_c, transfer_http):
        """AC3：C 端持久 4xx 不重试（hits==1），__error__ 收敛 + 审计 Failed(stage=third_party_call)。"""
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config = write_capability_config(tmp_path, [], {'c_api_base_url': c_url})
        events = []
        acl = build_acl(config, ta_url, c_url, events=events)
        c_state['fail_mode'] = 'always_400'
        try:
            resp = acl.evaluate_dimension_group(**group_kwargs(transfer_id='c4xx-1'))
        finally:
            c_state['fail_mode'] = None

        assert '__error__' in resp, f'4xx 未收敛为错误: {resp}'
        assert c_state['hits']['c4xx-1'] == 1, '4xx 语义错误不应重试'
        failed = [e for e in events if isinstance(e, ThirdPartyEvalFailed)]
        assert len(failed) == 1 and failed[0].stage == 'third_party_call'
        # 传输段本身成功：EVAL_REQUEST 流水已落（COMPLETED），失败发生在 C 调用环节
        pkg = record_repo.packages.get('c4xx-1')
        assert pkg is not None and pkg.status == 'COMPLETED' and pkg.pkg_type == 'EVAL_REQUEST'

    def test_transient_5xx_retries_and_audits_completed(self, tmp_path, fake_c, transfer_http):
        """AC3：C 端瞬时 5xx 指数退避重试后成功，审计事件 Dispatched→Completed 完整。"""
        c_url, c_state = fake_c
        ta_url, _ = transfer_http
        config = write_capability_config(tmp_path, [], {'c_api_base_url': c_url})
        events = []
        acl = build_acl(config, ta_url, c_url, events=events)
        c_state['fail_mode'] = 'first_500'
        try:
            resp = acl.evaluate_dimension_group(**group_kwargs(transfer_id='c5xx-1'))
        finally:
            c_state['fail_mode'] = None

        assert resp['code'] == 0, f'瞬时失败重试后未成功: {resp}'
        assert c_state['hits']['c5xx-1'] == 2, '应恰好重试一次'
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]

    def test_dst_c_transfer_record_aligns_with_real_outbound_delivery(
            self, tmp_path, fake_c, transfer_http):
        """AC（INT-49）：transfer_records dst=C 流水与真实数据路径对齐——中枢内联
        dst='C' 登记即真实 B→C 数据面，经 T-B 出站投递腿送达 C 后流水转 DELIVERED、
        meta.delivery 记录真实投递结果；A→B 中转腿（dst='B'）不携带投递语义，
        审计流水与真实传输一一对应。"""
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        edge_config = write_capability_config(
            os.path.join(str(tmp_path), 'edge'), [],
            {'c_api_base_url': c_url, 'self_zone': 'A', 'hub_zone': 'B',
             'hub_transfer_agent_base_url': ta_url})
        hub_config = write_capability_config(
            os.path.join(str(tmp_path), 'hub'), [],
            {'c_api_base_url': c_url, 'self_zone': 'B', 'hub_zone': 'B',
             'transfer_agent_base_url': ta_url,
             'hub_transfer_agent_base_url': ta_url})

        # A→B 中转腿：真实数据面，dst='B'，不携带投递语义标注。
        # 包体取极小值（整包 < 单分片上限）：harness 服务端分片上限人为设为 1024，
        # 而 A→B 腿经 _client_for 构造的客户端用默认 4MB 分片（与生产默认一致），
        # 大包体会触发 413——本测试验证 meta 语义而非分片（多分片由其余用例覆盖）
        edge_acl = build_acl(edge_config, ta_url, c_url)
        edge_acl.dispatch_eval_request(
            form_fields={'task_type': 'llm_judge'},
            files={'record_file': ('a.wav', b'RIFFsmallWAVEfmt ', 'audio/wav')},
            eval_params={'task_id': 902, 'test_case_id': '9002',
                         'dimensions': ['llm_judge'], 'adapter': 'multipart'},
            transfer_id='stage-meta-ab')
        ab_pkg = record_repo.packages.get('stage-meta-ab')
        assert ab_pkg is not None and ab_pkg.dst_zone == 'B'
        assert 'delivery' not in (ab_pkg.meta or {}), \
            'A→B 中转腿登记不应携带出站投递语义'
        assert 'staging_purpose' not in (ab_pkg.meta or {}), \
            '过渡期审计锚点标注应已随 F2.1 退役'

        # 中枢内联 dst='C' 登记：真实 B→C 数据面，出站投递后 DELIVERED + meta.delivery
        hub_acl = build_acl(hub_config, ta_url, c_url)
        resp = hub_acl.evaluate_dimension_group(**group_kwargs(transfer_id='stage-meta-c'))
        assert resp.get('code') == 0, f'中枢内联流程未成功: {resp}'
        c_pkg = record_repo.packages.get('stage-meta-c')
        assert c_pkg is not None and c_pkg.dst_zone == 'C'
        assert c_pkg.status == 'DELIVERED', \
            f'dst=C 流水应反映真实传输（DELIVERED）: {c_pkg.status}'
        delivery = (c_pkg.meta or {}).get('delivery') or {}
        assert delivery.get('status') == 'delivered', \
            f'dst=C 流水 meta 缺少真实投递结果: {c_pkg.meta}'
        assert delivery.get('dst_status') == 200
        assert delivery.get('delivered_at')
