# -*- coding: utf-8 -*-
"""A→B→C 三区评估链路集成测试（INT-29/INT-49）。

验收标准：EVAL_REQUEST → T-B 出站投递 → EVAL_RESULT 全流程联调（本地模拟 C 区端点），
幂等去重与失败重试在链路层可验证，审计事件与传输流水完整（dst=C 流水对应真实传输）。

- 本地模拟 C 区端点：http.server（multipart / feature / presigned 三种契约 + 幂等计数）
- transfer_agent：真实 FastAPI 路由栈 + uvicorn（port=0），注入内存仓储 + 临时目录存储，
  含出站投递腿 /outbound/{transfer_id}/dispatch（C 客户端指向模拟 C 端点）
- evaluation_service ACL：真实打包/签名/分片上传/出站投递/解包全链路（B→C 经 T-B，无直连）

不依赖 DB / OSS / Redis。
"""
import hashlib
import io
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import requests

import transfer_agent.interfaces.api.routes as transfer_routes
from evaluation_service.domain.events.evaluation_events import (
    ThirdPartyEvalCompleted,
    ThirdPartyEvalDispatched,
)
from evaluation_service.infrastructure.acl.third_party_eval_acl import (
    ThirdPartyEvalACL,
    ThirdPartyEvalSettings,
)
from evaluation_service.infrastructure.acl.third_party_outbound_adapter import (
    ThirdPartyEvalAdapterFactory,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import TransferEvalClient
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
from tests.unit.test_transfer_handlers import FakeChunkRepo, FakeRecordRepo

TOKENS = {'A_B': 'secret-ab', 'B_C': 'secret-bc'}
CHUNK = 1024
AUDIO_BYTES = b'RIFF' + os.urandom(3 * 1024)  # 3KB → 多分片


# ================= 模拟 C 区第三方评估 API =================
def _disp_attr(disposition: str, attr: str):
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
        filename = _disp_attr(disposition, 'filename')
        if name is None:
            continue
        if filename:
            files[name] = content
        else:
            fields[name] = content.decode('utf-8')
    return fields, files


class FakeCEndpointHandler(BaseHTTPRequestHandler):
    """C 区第三方评估 API 替身：三种契约 + transfer_id 幂等计数 + 可注入首次失败。"""

    def log_message(self, *args):  # 静默访问日志
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

    def _evaluate(self, fields, files):
        transfer_id = str(fields.get('transfer_id') or '')
        self.state['hits'][transfer_id] = self.state['hits'].get(transfer_id, 0) + 1
        # 链路重试验证：标记的 transfer_id 首次返回 500
        if transfer_id in self.state['fail_first'] and self.state['hits'][transfer_id] == 1:
            self._reply(500, {'msg': 'simulated transient failure'})
            return
        # C 侧幂等去重：按 transfer_id 记录评估结果，重复请求返回一致结果
        self.state['seen_files'][transfer_id] = {
            name: hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()
            for name, content in files.items()
        }
        self.state['last_fields'] = dict(fields)
        self._reply(200, {'code': 0, 'msg': 'ok',
                          'data': {'result': {'score': 0.92, 'value': '0.92'}}})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        content_type = self.headers.get('Content-Type', '')
        if path == '/evaluate':
            if content_type.startswith('multipart/form-data'):
                fields, files = parse_multipart(self._read_body(), content_type)
                self._evaluate(fields, files)
            else:
                body = json.loads(self._read_body() or b'{}')
                objects = {name: f'obj:{ref}' for name, ref in (body.get('objects') or {}).items()}
                features = {name: str(feat) for name, feat in (body.get('features') or {}).items()}
                self._evaluate({**(body.get('fields') or {}), **body}, {**objects, **features})
        elif path == '/upload-url':
            body = json.loads(self._read_body() or b'{}')
            self.state['upload_seq'] += 1
            seq = self.state['upload_seq']
            host, port = self.server.server_address[:2]
            self.state['presigned'][body.get('sha256')] = body
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
    server.state = {'hits': {}, 'fail_first': set(), 'seen_files': {},
                    'last_fields': {}, 'presigned': {}, 'uploads': {}, 'upload_seq': 0}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f'http://{host}:{port}', server.state
    server.shutdown()
    server.server_close()


# ================= transfer_agent HTTP（内存仓储 + 临时目录存储 + 出站投递腿） =================
class TempDirStorage:
    """TransferStorageABC 的本地临时目录实现（分片→transit 合并→提升终桶）。"""

    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, 'chunks'), exist_ok=True)
        os.makedirs(os.path.join(root, 'transit'), exist_ok=True)
        os.makedirs(os.path.join(root, 'final'), exist_ok=True)

    def _chunk_dir(self, transfer_id):
        path = os.path.join(self.root, 'chunks', transfer_id)
        os.makedirs(path, exist_ok=True)
        return path

    def save_chunk(self, transfer_id, chunk_index, data):
        with open(os.path.join(self._chunk_dir(transfer_id), f'{chunk_index}.part'), 'wb') as f:
            f.write(data)

    def chunk_exists(self, transfer_id, chunk_index):
        return os.path.isfile(os.path.join(self._chunk_dir(transfer_id), f'{chunk_index}.part'))

    def delete_chunks(self, transfer_id, total_chunks):
        import shutil
        shutil.rmtree(os.path.join(self.root, 'chunks', transfer_id), ignore_errors=True)

    def merge_chunks(self, transfer_id, total_chunks):
        staged_dir = os.path.join(self.root, 'transit', transfer_id)
        os.makedirs(staged_dir, exist_ok=True)
        staged_path = os.path.join(staged_dir, 'merged.bin')
        sha = hashlib.sha256()
        with open(staged_path, 'wb') as out:
            for index in range(total_chunks):
                with open(os.path.join(self._chunk_dir(transfer_id), f'{index}.part'), 'rb') as f:
                    block = f.read()
                sha.update(block)
                out.write(block)
        return staged_path, sha.hexdigest()

    def promote_file(self, staged_path, dest_category, dest_key):
        final_path = os.path.join(self.root, 'final', dest_category, dest_key)
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        os.replace(staged_path, final_path)
        return final_path

    def read_file(self, path):
        with open(path, 'rb') as f:
            return f.read()

    def delete_transit_file(self, path):
        if os.path.isfile(path):
            os.remove(path)


@pytest.fixture(scope='module')
def transfer_http(fake_c, tmp_path_factory):
    c_url, _c_state = fake_c
    record_repo = FakeRecordRepo()
    chunk_repo = FakeChunkRepo()
    storage = TempDirStorage(str(tmp_path_factory.mktemp('transfer_storage')))
    command_handler = TransferCommandHandler(
        record_repo=record_repo, chunk_repo=chunk_repo, storage=storage,
        signature_service=SignatureService(TOKENS),
        ttl_bounds=(60, 7 * 86400), default_chunk_size=CHUNK,
    )
    query_handler = TransferQueryHandler(
        record_repo=record_repo, chunk_repo=chunk_repo,
        signature_service=SignatureService(TOKENS),
    )
    # 出站投递腿（B→C 数据面）：真实编排服务，C 客户端指向模拟 C 端点
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
def write_settings_config(base_dir, ta_url, self_zone='B', hub_zone='B',
                          relay_poll_interval_seconds=2, relay_result_timeout_seconds=900):
    os.makedirs(base_dir, exist_ok=True)
    config_path = os.path.join(base_dir, 'eval_capability_config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump({
            'dimension_capabilities': [
                {'dimension': 'llm_judge', 'target': 'THIRD_PARTY_C',
                 'adapter': 'multipart', 'enabled': True},
            ],
            'third_party': {
                'self_zone': self_zone, 'hub_zone': hub_zone,
                'transfer_agent_base_url': ta_url, 'hub_transfer_agent_base_url': ta_url,
                'adapter': 'multipart',
                'timeout_seconds': 10, 'dispatch_timeout_seconds': 30,
                'staging_ttl_seconds': 600,
                'sync_back_enabled': True, 'sync_back_zone': 'A',
                'response_required_keys': [],
                'relay_poll_interval_seconds': relay_poll_interval_seconds,
                'relay_result_timeout_seconds': relay_result_timeout_seconds,
            },
        }, f, ensure_ascii=False)
    return config_path


def build_acl(config_path, ta_url, hub_url=None, tokens=None, events=None):
    settings = ThirdPartyEvalSettings(config_path=config_path)
    client = TransferEvalClient(base_url=hub_url or ta_url, tokens=tokens or TOKENS,
                                timeout_seconds=10, chunk_size=CHUNK)
    return ThirdPartyEvalACL(
        settings=settings, adapter_factory=ThirdPartyEvalAdapterFactory(),
        client=client, event_sink=(events.append if events is not None else None))


def group_kwargs():
    return dict(
        payload={'task_type': 'llm_judge'},
        form_fields={'task_type': 'llm_judge', 'prompt': '评分', 'threshold': 0.6},
        files={'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
        representative_dim_data={'id': 7, 'name': 'llm_judge',
                                 'task_type_code': 'llm_judge', 'dimension_type': 'main'},
        dim_names=['llm_judge'],
        dim_info={'task_type_code': 'llm_judge'},
        task_id=101, test_case_id='2024',
    )


class TestHubFullChain:
    """中枢（B）全流程：打包→分片传输登记→T-B 出站投递 C→结果校验→审计。"""

    def test_eval_request_to_eval_result_full_chain(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config = write_settings_config(tmp_path, ta_url)
        events = []
        acl = build_acl(config, ta_url, events=events)

        resp = acl.evaluate_dimension_group(**group_kwargs())

        assert resp['code'] == 0
        assert resp['data']['result']['score'] == 0.92
        # ② 传输流水：EVAL_REQUEST B→C DELIVERED（dst=C 流水对应真实传输）
        packages = list(record_repo.packages.values())
        assert len(packages) == 1
        pkg = packages[0]
        assert pkg.pkg_type == 'EVAL_REQUEST'
        assert (pkg.src_zone, pkg.dst_zone) == ('B', 'C')
        assert pkg.status == 'DELIVERED'
        assert pkg.ephemeral is True  # transit 暂存，不落持久盘
        assert pkg.total_chunks >= 4  # 3KB 文件按 1KB 分片
        assert pkg.meta['delivery']['status'] == 'delivered'
        assert pkg.meta['delivery']['dst_status'] == 200
        # ③ C 端收到完整 multipart（T-B 出站腿按契约投递，字段 + 文件字节一致）
        tid = pkg.transfer_id
        assert c_state['hits'][tid] == 1
        assert c_state['seen_files'][tid]['record_file'] == hashlib.sha256(AUDIO_BYTES).hexdigest()
        assert c_state['last_fields']['task_type'] == 'llm_judge'
        # ⑦ 审计事件完整
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]
        assert events[0].transfer_id == tid

    def test_idempotent_resend_dedups_transfer_record(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config = write_settings_config(tmp_path, ta_url)
        acl = build_acl(config, ta_url)

        resp1 = acl.evaluate_dimension_group(**group_kwargs(), transfer_id='dedup-tid')
        resp2 = acl.evaluate_dimension_group(**group_kwargs(), transfer_id='dedup-tid')

        assert resp1['code'] == resp2['code'] == 0
        # 幂等：同 transfer_id 重复接收，传输流水仅一条（create 幂等去重）
        dedup_records = [p for p in record_repo.packages.values() if p.transfer_id == 'dedup-tid']
        assert len(dedup_records) == 1
        # 出站投递幂等重投（DELIVERED 重投）：C 按 transfer_id 去重，结果一致
        assert c_state['hits']['dedup-tid'] == 2

    def test_retry_on_transient_c_failure(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config = write_settings_config(tmp_path, ta_url)
        events = []
        acl = build_acl(config, ta_url, events=events)

        acl.evaluate_dimension_group(**group_kwargs(), transfer_id='retry-tid')
        c_state['fail_first'].add('retry-tid-2')
        resp = acl.evaluate_dimension_group(**group_kwargs(), transfer_id='retry-tid-2')

        # 失败重试（T-B 出站腿内）：首次 500 → 指数退避重试 → 成功
        assert resp['code'] == 0
        assert c_state['hits']['retry-tid-2'] == 2
        # 第二次评估的审计事件完整（前两组为首次评估事件）
        assert [type(e) for e in events[-2:]] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]

    def test_feature_extract_and_presigned_forms(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, _ = transfer_http
        config = write_settings_config(tmp_path, ta_url)
        acl = build_acl(config, ta_url)
        kwargs = group_kwargs()

        # 特征提取形态：T-B 出站腿预处理→只传特征（C 收 JSON）
        acl.evaluate_dimension_group(**{**kwargs, 'adapter_kind': 'feature_extract',
                                        'transfer_id': 'feat-tid'})
        feature_blob = c_state['last_fields'].get('features') or {}
        record_features = feature_blob.get('record_file') or {}
        assert 'sha256' in str(record_features)
        # 预签名 URL 形态：T-B 申请预签名→PUT 上传→携带对象引用评估
        acl.evaluate_dimension_group(**{**kwargs, 'adapter_kind': 'presigned_url',
                                        'transfer_id': 'presign-tid'})
        assert c_state['presigned'], '预签名申请未到达 C 端'
        # PUT 上传的字节与源文件一致
        uploaded = list(c_state['uploads'].values())
        assert AUDIO_BYTES in uploaded


class TestEdgeRelayFullEightSteps:
    """边缘（A）发起 → 中枢（B）执行（出站投递 C）→ 结果回同步 A：8 步完整链路。"""

    def test_relay_chain(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config_hub = write_settings_config(tmp_path / 'hub', ta_url)
        config_edge = write_settings_config(tmp_path / 'edge', ta_url, self_zone='A')
        hub_events, edge_events = [], []
        hub_acl = build_acl(config_hub, ta_url, events=hub_events)
        edge_acl = build_acl(config_edge, ta_url, events=edge_events)

        # ①② A 打包 EVAL_REQUEST → 分片传输到 B（过 GW-1 的逻辑对应）
        dispatched = edge_acl.dispatch_eval_request(
            form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
            files={'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
            eval_params={'task_id': 101, 'test_case_id': '2024',
                         'dimensions': ['llm_judge'], 'adapter': 'multipart'},
            transfer_id='relay-001')
        assert dispatched['hub_zone'] == 'B'

        # ③~⑦ B 解包→T-B 出站投递 C→校验→审计
        hub_resp = hub_acl.execute_incoming('relay-001')
        assert hub_resp['code'] == 0
        assert hub_resp['data']['result']['score'] == 0.92
        assert c_state['hits']['relay-001'] == 1

        # ⑧ EVAL_RESULT 回同步 A（B→A 传输流水）
        fetched = edge_acl.fetch_incoming_result('relay-001-result')
        assert fetched['transfer_id'] == 'relay-001'
        assert fetched['result'] == hub_resp

        # 传输流水审计完整：EVAL_REQUEST A→B（出站投递后 DELIVERED）+ EVAL_RESULT B→A
        types = sorted((p.pkg_type, p.src_zone, p.dst_zone, p.status)
                       for p in record_repo.packages.values())
        assert ('EVAL_REQUEST', 'A', 'B', 'DELIVERED') in types
        assert ('EVAL_RESULT', 'B', 'A', 'COMPLETED') in types
        # 中枢审计事件：Dispatched→Completed（synced_back）
        completed = [e for e in hub_events if isinstance(e, ThirdPartyEvalCompleted)]
        assert completed and completed[0].synced_back is True


class TestEdgeAutoRelayFullChain:
    """A 区（EDGE）自动中转接线（F2.2/INT-50）：evaluate_dimension_group 一跳完成
    A→B→C→B→A 全链路（后台线程模拟中枢侧中转执行触发器），模拟 A 区部署形态下
    THIRD_PARTY_C 维度用例自动完成全链路，传输流水与审计事件全链路可验证。"""

    def test_auto_relay_full_chain(self, tmp_path, fake_c, transfer_http):
        c_url, c_state = fake_c
        ta_url, record_repo = transfer_http
        config_hub = write_settings_config(tmp_path / 'hub', ta_url)
        config_edge = write_settings_config(tmp_path / 'edge', ta_url, self_zone='A',
                                            relay_poll_interval_seconds=0.05,
                                            relay_result_timeout_seconds=30)
        hub_events, edge_events = [], []
        hub_acl = build_acl(config_hub, ta_url, events=hub_events)
        edge_acl = build_acl(config_edge, ta_url, events=edge_events)

        # 中枢侧（B）模拟：发现本卡 A→B 的 EVAL_REQUEST 包完成传输（COMPLETED）即执行
        # （生产形态为中枢侧中转执行触发器调 execute_incoming，本测试代为触发）
        def _hub_relay():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                package = record_repo.packages.get('auto-relay-001')
                if package is not None and package.pkg_type == 'EVAL_REQUEST' \
                        and str(package.status) == 'COMPLETED':
                    try:
                        hub_acl.execute_incoming('auto-relay-001')
                        return
                    except Exception:
                        if time.monotonic() >= deadline:
                            return
                        time.sleep(0.05)
                time.sleep(0.02)
        relay_thread = threading.Thread(target=_hub_relay, daemon=True)
        relay_thread.start()

        # A 区生产入口一跳完成全链路（EDGE 自动 ①②③ dispatch → ⑧ 轮询取回）
        resp = edge_acl.evaluate_dimension_group(
            **group_kwargs(), transfer_id='auto-relay-001')
        relay_thread.join(timeout=25)
        assert not relay_thread.is_alive(), '中枢侧中转执行未被触发'

        assert resp == {'code': 0, 'msg': 'ok',
                        'data': {'result': {'score': 0.92, 'value': '0.92'}}}, \
            f'A 区自动中转未取回回同步结果: {resp}'
        assert c_state['hits']['auto-relay-001'] == 1, 'C 端未收到评估请求（T-B 出站投递未发生）'
        # 传输流水全链路完整：EVAL_REQUEST A→B（出站投递后 DELIVERED）+ EVAL_RESULT B→A
        types = sorted((p.pkg_type, p.src_zone, p.dst_zone, p.status)
                       for p in record_repo.packages.values())
        assert ('EVAL_REQUEST', 'A', 'B', 'DELIVERED') in types
        assert ('EVAL_RESULT', 'B', 'A', 'COMPLETED') in types
        # A 区审计事件：Dispatched（发起中转）→ Completed（取回回同步结果）
        assert [type(e) for e in edge_events] == [
            ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]
        assert edge_events[0].transfer_id == edge_events[1].transfer_id == 'auto-relay-001'
        assert (edge_events[0].src_zone, edge_events[0].dst_zone) == ('A', 'B')
        assert edge_events[1].synced_back is True
