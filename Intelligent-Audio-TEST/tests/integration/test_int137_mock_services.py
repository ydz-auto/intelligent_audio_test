# -*- coding: utf-8 -*-
"""INT-137 独立 mock 替身服务集成测试（契约对齐 + 注入语义）。

被测对象：mock_services/ 两个独立 mock 服务（生产替身，非测试夹具）：
- mock_third_party_eval  第三方评估 C 区替身：三契约端点 + EVAL_RESULT 回传 +
  延迟 / 5xx 重试退避 / 4xx 不重试 / 幂等去重注入
- mock_realtime_api      Realtime 被测产品替身：session.update 确认 + 逐帧 ack +
  commit 响应流收口 + 延迟 / 中途断连 / 协议错误 / barge-in 注入

链路形态（与既有第三方评估链路集成测试同构）：
- 真实 transfer_agent FastAPI 路由栈（uvicorn port=0）+ 出站投递腿，C 客户端
  指向 mock 评估服务（真实 HTTP，非测试桩）
- 真实 evaluation_service ACL（打包→签名→分片上传→出站投递→校验→审计）
- 真实 RealtimeWSClient 对接 mock realtime（真实 WS 握手与事件协议）

外部依赖以替身仿真（仓储/存储用内存桩，DB/OSS 不依赖）——生产组件边界全真实。
"""
import base64
import hashlib
import os
import sys
import time

import pytest
import requests

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer
from mock_services.mock_third_party_eval import MockEvalBehavior, MockEvalServer
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
from evaluation_service.infrastructure.acl.third_party_eval_acl import (
    ThirdPartyEvalACL,
    ThirdPartyEvalSettings,
)
from evaluation_service.infrastructure.acl.third_party_outbound_adapter import (
    ThirdPartyEvalAdapterFactory,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import TransferEvalClient
from transfer_agent.application.services.outbound_delivery_service import (
    OutboundDeliveryService,
)
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy
from transfer_agent.infrastructure.acl.c_api_client import ThirdPartyCAPIClient
from tests.unit.test_transfer_handlers import FakeChunkRepo, FakeRecordRepo

TOKENS = {'A_B': 'secret-ab', 'B_C': 'secret-bc'}
CHUNK = 1024
AUDIO_BYTES = b'RIFF' + os.urandom(3 * 1024)


# ================= mock 第三方评估服务（独立可运行替身，port=0 进程内起） =================
@pytest.fixture(scope='module')
def mock_eval():
    server = MockEvalServer(MockEvalBehavior())
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def mock_eval_clean(mock_eval):
    """每用例前后重置 mock 行为与状态（注入互不污染）。"""
    mock_eval.service.behavior = MockEvalBehavior()
    mock_eval.service.state.reset()
    yield mock_eval
    mock_eval.service.behavior = MockEvalBehavior()
    mock_eval.service.state.reset()


@pytest.fixture(scope='module')
def transfer_http(mock_eval):
    """真实 transfer_agent 路由栈（内存仓储 + 临时目录存储 + 出站投递腿指向 mock 评估）。"""
    import uvicorn
    from fastapi import FastAPI
    import transfer_agent.interfaces.api.routes as transfer_routes
    from transfer_agent.application.handlers.transfer_handlers import (
        TransferCommandHandler,
        TransferQueryHandler,
    )
    from tests.integration.test_third_party_eval_chain import TempDirStorage
    import tempfile

    record_repo = FakeRecordRepo()
    chunk_repo = FakeChunkRepo()
    storage = TempDirStorage(tempfile.mkdtemp(prefix='int137_transfer_'))
    command_handler = TransferCommandHandler(
        record_repo=record_repo, chunk_repo=chunk_repo, storage=storage,
        signature_service=SignatureService(TOKENS),
        ttl_bounds=(60, 7 * 86400), default_chunk_size=CHUNK,
    )
    query_handler = TransferQueryHandler(
        record_repo=record_repo, chunk_repo=chunk_repo,
        signature_service=SignatureService(TOKENS),
    )
    outbound_service = OutboundDeliveryService(
        record_repo=record_repo, storage=storage, route_policy=ZoneRoutePolicy(),
        c_client=ThirdPartyCAPIClient(base_url=mock_eval.base_url, timeout_seconds=10,
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
        app = FastAPI()
        app.include_router(transfer_routes.router)
        config = uvicorn.Config(app, host='127.0.0.1', port=0, lifespan='off',
                                log_level='error')
        server = uvicorn.Server(config)
        import threading
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


def build_acl(ta_url, tmp_path, adapter='multipart', events=None):
    config_path = os.path.join(str(tmp_path), 'eval_capability_config.json')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    import json as _json
    with open(config_path, 'w', encoding='utf-8') as f:
        _json.dump({
            'dimension_capabilities': [],
            'third_party': {
                'self_zone': 'B', 'hub_zone': 'B',
                'transfer_agent_base_url': ta_url,
                'hub_transfer_agent_base_url': ta_url,
                'adapter': adapter,
                'timeout_seconds': 10, 'dispatch_timeout_seconds': 30,
                'staging_ttl_seconds': 600,
                'response_required_keys': [],
            },
        }, f, ensure_ascii=False)
    settings = ThirdPartyEvalSettings(config_path=config_path)
    client = TransferEvalClient(base_url=ta_url, tokens=TOKENS,
                                timeout_seconds=10, chunk_size=CHUNK)
    return ThirdPartyEvalACL(
        settings=settings, adapter_factory=ThirdPartyEvalAdapterFactory(),
        client=client, event_sink=(events.append if events is not None else None))


def group_kwargs(transfer_id):
    return dict(
        payload={'task_type': 'llm_judge'},
        form_fields={'task_type': 'llm_judge', 'prompt': '评分', 'threshold': 0.6},
        files={'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
        representative_dim_data={'id': 7, 'name': 'llm_judge',
                                 'task_type_code': 'llm_judge', 'dimension_type': 'main'},
        dim_names=['llm_judge'],
        dim_info={'task_type_code': 'llm_judge'},
        task_id=1370, test_case_id='13700',
        transfer_id=transfer_id,
    )


class TestMockThirdPartyEvalContract:
    """AC1：mock 评估三契约 + EVAL_RESULT 回传全链（真实 ACL + 真实 transfer_agent 栈）。"""

    def test_multipart_full_chain_fixed_score(
            self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, record_repo = transfer_http
        events = []
        acl = build_acl(ta_url, tmp_path, adapter='multipart', events=events)

        resp = acl.evaluate_dimension_group(**group_kwargs('int137-mp-1'))

        # EVAL_RESULT 合法回传（schema 与既有集成测试本地 C 区端点一致）
        assert resp['code'] == 0
        assert resp['data']['result']['score'] == 0.92
        assert resp['data']['result']['value'] == '0.92'
        # mock 侧观测：multipart 契约收到完整字段与文件字节
        last = server.service.state.last_request
        assert last['form'] == 'multipart'
        assert last['transfer_id'] == 'int137-mp-1'
        assert last['fields']['task_type'] == 'llm_judge'
        assert last['files']['record_file'] == hashlib.sha256(AUDIO_BYTES).hexdigest()
        # 传输流水：EVAL_REQUEST B→C DELIVERED + meta.delivery 真实投递结果
        pkg = record_repo.packages['int137-mp-1']
        assert (pkg.src_zone, pkg.dst_zone, pkg.status) == ('B', 'C', 'DELIVERED')
        delivery = pkg.meta['delivery']
        assert delivery['status'] == 'delivered' and delivery['dst_status'] == 200
        # 审计事件完整
        assert [type(e).__name__ for e in events] == [
            'ThirdPartyEvalDispatched', 'ThirdPartyEvalCompleted']

    def test_feature_extract_form(self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, _ = transfer_http
        acl = build_acl(ta_url, tmp_path, adapter='feature_extract')

        resp = acl.evaluate_dimension_group(**group_kwargs('int137-feat-1'))

        assert resp['code'] == 0
        last = server.service.state.last_request
        assert last['form'] == 'feature_extract'
        features = last['features'].get('record_file') or {}
        assert 'sha256' in str(features), '特征提取形态未收到特征向量'

    def test_presigned_url_form(self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, _ = transfer_http
        acl = build_acl(ta_url, tmp_path, adapter='presigned_url')

        resp = acl.evaluate_dimension_group(**group_kwargs('int137-presign-1'))

        assert resp['code'] == 0
        # 预签名申请 + PUT 上传 + 对象引用评估三步全到 mock
        assert server.service.state.presigned.get('int137-presign-1'), '预签名申请未达 mock'
        uploaded = list(server.service.state.uploads.values())
        assert AUDIO_BYTES in uploaded, 'PUT 上传字节与源文件不一致'
        last = server.service.state.last_request
        assert last['form'] == 'presigned_url'
        assert last['objects'].get('record_file', '').startswith('obj-')

    def test_delay_injection(self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, _ = transfer_http
        # 经控制端点热更新注入延迟（HTTP 控制面本身是 mock 契约的一部分）
        r = requests.post(f'{server.base_url}/__control', json={'delay_ms': 400}, timeout=5)
        assert r.status_code == 200 and r.json()['behavior']['delay_ms'] == 400
        acl = build_acl(ta_url, tmp_path, adapter='multipart')

        started = time.monotonic()
        resp = acl.evaluate_dimension_group(**group_kwargs('int137-delay-1'))
        elapsed = time.monotonic() - started

        assert resp['code'] == 0
        assert elapsed >= 0.4, f'延迟注入未生效（耗时 {elapsed:.2f}s）'

    def test_first_5xx_retry_backoff(self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, _ = transfer_http
        requests.post(f'{server.base_url}/__control?fail_mode=first_5xx', timeout=5)
        acl = build_acl(ta_url, tmp_path, adapter='multipart')

        resp = acl.evaluate_dimension_group(**group_kwargs('int137-5xx-1'))

        # 首次 5xx → 出站腿指数退避重试 → 成功（C 端恰好命中两次）
        assert resp['code'] == 0
        assert server.service.state.hits['int137-5xx-1'] == 2

    def test_always_4xx_no_retry_converges(self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, record_repo = transfer_http
        requests.post(f'{server.base_url}/__control?fail_mode=always_4xx', timeout=5)
        events = []
        acl = build_acl(ta_url, tmp_path, adapter='multipart', events=events)

        resp = acl.evaluate_dimension_group(**group_kwargs('int137-4xx-1'))

        # 4xx 不重试（恰好一次）→ 链路收敛 __error__ + 审计 Failed(stage=third_party_call)
        assert '__error__' in resp
        assert server.service.state.hits['int137-4xx-1'] == 1
        failed = [e for e in events if type(e).__name__ == 'ThirdPartyEvalFailed']
        assert len(failed) == 1 and failed[0].stage == 'third_party_call'
        pkg = record_repo.packages['int137-4xx-1']
        assert pkg.status == 'COMPLETED'  # 传输段成功，失败发生在 C 调用环节

    def test_idempotent_dedup_replays_same_result(
            self, tmp_path, mock_eval_clean, transfer_http):
        server = mock_eval_clean
        ta_url, _ = transfer_http
        requests.post(f'{server.base_url}/__control', json={'score_mode': 'random'},
                      timeout=5)
        acl = build_acl(ta_url, tmp_path, adapter='multipart')

        resp1 = acl.evaluate_dimension_group(**group_kwargs('int137-dedup-1'))
        resp2 = acl.evaluate_dimension_group(**group_kwargs('int137-dedup-1'))

        # C 侧幂等去重：同 transfer_id 重复投递回放同结果（重发场景结果一致）
        assert resp1 == resp2
        assert server.service.state.hits['int137-dedup-1'] == 2

    def test_control_rejects_invalid_behavior(self, mock_eval_clean):
        server = mock_eval_clean
        r = requests.post(f'{server.base_url}/__control',
                          json={'fail_mode': 'carrier_pigeon'}, timeout=5)
        assert r.status_code == 400 and '非法 fail_mode' in r.json()['msg']

    def test_health_endpoint(self, mock_eval_clean):
        r = requests.get(f'{mock_eval_clean.base_url}/health', timeout=5)
        assert r.status_code == 200 and r.json()['status'] == 'ok'


# ================= mock Realtime API 服务 =================
@pytest.fixture()
def mock_rt():
    server = MockRealtimeServer(MockRealtimeBehavior())
    server.start()
    try:
        yield server
    finally:
        server.stop()
        server.service.state.reset()
        server.service.behavior = MockRealtimeBehavior()


def _connect(url):
    client = RealtimeWSClient(url, chunk_duration_ms=20)
    assert client.connect() is True
    return client


class TestMockRealtimeApi:
    """AC2：RealtimeSessionExecutor 客户端协议对接 mock realtime（真实 WS）。"""

    def test_session_and_stream_round_with_per_frame_ack(self, mock_rt):
        client = _connect(mock_rt.url)
        try:
            # 会话建立：session.update → session.updated
            assert client.pre_process({'voice': 'mock'}) is True

            # 逐帧推送：每帧 ack（frame 通道逐帧可见）
            chunk_b64 = base64.b64encode(b'\x00\x01' * 40).decode('ascii')
            for _ in range(3):
                client.send_audio_chunk(chunk_b64)
            client.commit_input()
            assert client.wait_ai_complete(start_timeout=5, end_timeout=5) is True

            output = client.output
            types = [f['type'] for f in output['frame_results']]
            # 逐帧 ack 3 帧（未知事件透传 payload=None，seq 断言取原始事件日志）
            assert types.count('input_audio_buffer.append.ack') == 3
            raw_acks = [e for e in client._raw_event_log
                        if e.get('type') == 'input_audio_buffer.append.ack']
            assert [e['seq'] for e in raw_acks] == [1, 2, 3]
            # AI 响应流：delta × 3 + done 收口 + 文本
            assert types.count('ai_audio_delta') == 3
            assert 'ai_audio_done' in types
            assert output['text'] == 'mock 回复文本'
            assert output['audio'] == b'\x01\x02' * 40 * 3
            # 首帧延迟已测得（commit → 首帧）
            assert output['latency_ms'] is not None
            # 服务端观测：会话建立/心跳/收口语义事件齐备
            assert mock_rt.service.state.received[0] == 'session.update'
            assert mock_rt.service.state.received.count(
                'input_audio_buffer.append') == 3
            assert 'input_audio_buffer.commit' in mock_rt.service.state.received
            assert mock_rt.service.state.responses_streamed == 1
        finally:
            client.close()

    def test_first_delta_delay_injection(self, mock_rt):
        mock_rt.set_behavior({'first_delta_delay_ms': 400})
        client = _connect(mock_rt.url)
        try:
            assert client.pre_process() is True
            client.commit_input()
            started = time.monotonic()
            assert client.wait_ai_complete(start_timeout=10, end_timeout=5) is True
            elapsed_ms = (time.monotonic() - started) * 1000
            # 延迟注入生效：commit → 首帧延迟含注入的 400ms
            assert client.output['latency_ms'] >= 350
            assert elapsed_ms >= 350
        finally:
            client.close()

    def test_disconnect_injection_converges(self, mock_rt):
        mock_rt.set_behavior({'disconnect_after_events': 2})
        client = _connect(mock_rt.url)
        try:
            # 事件 1：session.update 正常确认
            assert client.pre_process() is True
            # 事件 2：首个 append 处理后服务端主动断连 → 客户端收敛 connection_closed
            client.send_audio_chunk(base64.b64encode(b'\x00\x01').decode('ascii'))
            deadline = time.time() + 5
            closed = False
            while time.time() < deadline:
                event = client.recv(timeout=1)
                if event.get('type') == 'connection_closed':
                    closed = True
                    break
            assert closed, '服务端断连后客户端未收敛 connection_closed'
            assert client.wait_ai_complete(start_timeout=2, end_timeout=2) is False
        finally:
            client.close()

    def test_protocol_error_injection(self, mock_rt):
        mock_rt.set_behavior({'protocol_error_on_event': 'session.update'})
        client = _connect(mock_rt.url)
        try:
            # 协议错误注入：session.update 回 error → pre_process 收敛失败
            assert client.pre_process() is False
        finally:
            client.close()

    def test_barge_in_renew_flow(self, mock_rt):
        mock_rt.set_behavior({'barge_in': True})
        client = _connect(mock_rt.url)
        try:
            assert client.pre_process() is True
            # 第 1 轮正常收口
            client.commit_input()
            assert client.wait_ai_complete(start_timeout=5, end_timeout=5) is True
            # 打断轮：AI 已在说话（预置 delta）→ speech_started/cancelled 到达
            client.reset_round_state()
            assert client.wait_ai_speaking(start_timeout=5) is True
            deadline = time.time() + 5
            seen = set()
            while time.time() < deadline:
                event = client.recv(timeout=0.5)
                seen.add(event.get('type'))
                if {'user_speech_started', 'response_cancelled'} <= seen:
                    break
            assert client.barge_in_detected is True
            assert 'user_speech_started' in seen and 'response_cancelled' in seen
            # 打断后重新收口（renew）：推送打断音频 + commit → 新响应流
            client.send_audio_chunk(base64.b64encode(b'\x00\x01').decode('ascii'))
            client.commit_input()
            assert client.wait_ai_complete(start_timeout=5, end_timeout=5) is True
        finally:
            client.close()
