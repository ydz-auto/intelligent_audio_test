# -*- coding: utf-8 -*-
"""T-B 出站投递腿单元测试（INT-49）。

覆盖：
- ThirdPartyCAPIClient：三契约投递载荷构造、5xx/网络错误指数退避重试、4xx 不重试
- OutboundDeliveryService：读包→投递→流水对齐（DELIVERED + meta.delivery + 事件）、
  失败保持可重投、幂等重投（DELIVERED）、包类型/状态/token/路由白名单拦截
"""
import io
import json
import os
import sys
import zipfile
from datetime import timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import requests

from shared.models.common_enums import TransferStatus

from transfer_agent.application.commands.transfer_commands import OutboundDispatchCommand
from transfer_agent.application.services.outbound_delivery_service import (
    OutboundDeliveryService,
)
from transfer_agent.domain.entities.transfer_package import TransferPackage, utc8now
from transfer_agent.domain.errors import (
    AccessTokenInvalidError,
    InvalidPackageFieldError,
    InvalidTransferStateError,
    PackageExpiredError,
    PackageNotFoundError,
    RouteNotAllowedError,
)
from transfer_agent.domain.events.transfer_events import (
    TransferDeliveryFailed,
    TransferDelivered,
)
from transfer_agent.domain.services.eval_request_bundle import (
    EvalRequestBundle,
    EvalRequestFile,
)
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy
from transfer_agent.infrastructure.acl.c_api_client import (
    CADeliveryOutcome,
    ThirdPartyCAPIClient,
)
from tests.unit.test_transfer_handlers import FakeRecordRepo

TOKENS = {'B_C': 'secret-bc', 'A_B': 'secret-ab'}


# ================= 桩件 =================
def make_manifest_zip(transfer_id='tid-x'):
    """与 evaluation_service ACL _pack_bundle 同格式的 EVAL_REQUEST zip。"""
    manifest = {
        'transfer_id': transfer_id,
        'form_fields': {'task_type': 'llm_judge', 'prompt': '评分'},
        'eval_params': {'adapter': 'multipart', 'task_id': 1},
        'src_zone': 'B', 'dst_zone': 'C',
        'files': {'record_file': {'filename': 'a.wav', 'content_type': 'audio/wav',
                                  'size': 16}},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('request.json', json.dumps(manifest, ensure_ascii=False))
        zf.writestr('files/record_file', b'RIFFxxxxWAVEfmt ')
    return buf.getvalue()


class FakeStorage:
    def __init__(self):
        self.files = {}
        self.deleted = []

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def delete_transit_file(self, path):
        self.deleted.append(path)
        self.files.pop(path, None)


def make_package(**overrides):
    fields = dict(
        transfer_id='tid-x', pkg_type='EVAL_REQUEST', src_zone='B', dst_zone='C',
        category='case-result', key='eval_request/1/11/tid-x.zip',
        file_hash='sha256:' + '0' * 64, file_size=1234, ttl_seconds=3600,
        ephemeral=True, timestamp='2026-10-09T00:00:00+08:00',
        signature='sig', meta={'adapter': 'multipart'}, status='COMPLETED',
        final_path='local://transit/tid-x/pkg.zip',
    )
    fields.update(overrides)
    return TransferPackage(**fields)


class FakeCAPIClient:
    def __init__(self, outcome=None):
        self.calls = []
        self.outcome = outcome or CADeliveryOutcome(
            delivered=True, dst_status=200, body={'code': 0, 'msg': 'ok'}, attempts=1)

    def deliver(self, adapter_kind, bundle):
        self.calls.append({'adapter_kind': adapter_kind, 'bundle': bundle})
        return self.outcome


def make_service(package=None, c_client=None, outbound_zone='B', token='secret-bc'):
    repo = FakeRecordRepo()
    pkg = package or make_package()
    repo.packages[pkg.transfer_id] = pkg
    store = FakeStorage()
    store.files[pkg.final_path] = make_manifest_zip(pkg.transfer_id)
    client = c_client or FakeCAPIClient()
    events = []
    svc = OutboundDeliveryService(
        record_repo=repo, storage=store, route_policy=ZoneRoutePolicy(),
        c_client=client, signature_service=SignatureService(TOKENS),
        event_sink=events.append, outbound_zone=outbound_zone)
    return svc, pkg, client, events


def make_command(transfer_id='tid-x', adapter_kind='multipart', token='secret-bc'):
    return OutboundDispatchCommand(transfer_id=transfer_id,
                                   adapter_kind=adapter_kind, token=token)


def make_bundle(transfer_id='tid-001'):
    return EvalRequestBundle(
        transfer_id=transfer_id,
        form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
        eval_params={'adapter': 'multipart'},
        files={'record_file': EvalRequestFile(
            name='record_file', filename='a.wav',
            content=b'RIFFxxxxWAVEfmt ', content_type='audio/wav')},
    )


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


class FakeSession:
    """按脚本顺序回放响应的替身 Session（记录全部请求）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({'method': method, 'url': url, **kwargs})
        if not self.responses:
            raise AssertionError('FakeSession 响应脚本耗尽')
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_c_client(responses, **overrides):
    fields = dict(base_url='http://c', max_retries=3, backoff_seconds=0.01)
    fields.update(overrides)
    session = FakeSession(responses)
    return ThirdPartyCAPIClient(session=session, **fields), session


OK_RESULT = {'code': 0, 'msg': 'ok', 'data': {'result': {'score': 0.92}}}


# ================= OutboundDeliveryService 编排 =================
class TestOutboundDeliveryService:
    def test_delivers_reads_bundle_and_marks_delivered(self):
        svc, pkg, client, events = make_service()

        view = svc.dispatch(make_command())

        assert view['delivered'] is True
        assert view['dst_status'] == 200
        assert view['dst_body'] == {'code': 0, 'msg': 'ok'}
        # 按第三方契约投递：包内容解包后交投递客户端（multipart 形态）
        assert len(client.calls) == 1
        assert client.calls[0]['adapter_kind'] == 'multipart'
        bundle = client.calls[0]['bundle']
        assert bundle.transfer_id == 'tid-x'
        assert bundle.form_fields['task_type'] == 'llm_judge'
        assert bundle.files['record_file'].content == b'RIFFxxxxWAVEfmt '
        # 流水对齐：dst=C 记录状态 DELIVERED（真实传输），meta.delivery 落审计
        assert pkg.status == TransferStatus.DELIVERED.value
        assert pkg.meta['delivery']['status'] == 'delivered'
        assert pkg.meta['delivery']['dst_status'] == 200
        assert pkg.meta['delivery']['delivered_at']
        # 事件完整
        assert [type(e) for e in events] == [TransferDelivered]
        assert events[0].transfer_id == 'tid-x'
        assert events[0].dst_status == 200

    def test_idempotent_redispatch_after_delivered(self):
        svc, pkg, client, events = make_service()

        first = svc.dispatch(make_command())
        second = svc.dispatch(make_command())

        assert first['delivered'] is True and second['delivered'] is True
        assert len(client.calls) == 2  # 幂等重投真实重发（C 按 transfer_id 去重）
        assert pkg.status == TransferStatus.DELIVERED.value

    def test_delivery_failure_keeps_dispatchable_and_records_meta(self):
        outcome = CADeliveryOutcome(delivered=False, dst_status=503, attempts=4,
                                    error='C 第三方 API 服务端错误: HTTP 503')
        svc, pkg, client, events = make_service(c_client=FakeCAPIClient(outcome))

        view = svc.dispatch(make_command())

        assert view['delivered'] is False
        assert view['dst_status'] == 503
        assert 'HTTP 503' in view['error']
        # 流水保持 COMPLETED（可重投），meta.delivery 记录最近一次投递结果
        assert pkg.status == TransferStatus.COMPLETED.value
        assert pkg.meta['delivery']['status'] == 'failed'
        assert pkg.meta['delivery']['attempts'] == 4
        assert [type(e) for e in events] == [TransferDeliveryFailed]
        # 修复后重投成功
        client.outcome = CADeliveryOutcome(delivered=True, dst_status=200,
                                           body={'code': 0, 'msg': 'ok'}, attempts=1)
        assert svc.dispatch(make_command())['delivered'] is True
        assert pkg.status == TransferStatus.DELIVERED.value

    def test_wrong_pkg_type_rejected(self):
        pkg = make_package(pkg_type='REPORT_SYNC')
        svc, *_ = make_service(package=pkg)
        with pytest.raises(InvalidPackageFieldError, match='仅 EVAL_REQUEST'):
            svc.dispatch(make_command())

    def test_non_completed_state_rejected(self):
        pkg = make_package(status='CREATED')
        svc, *_ = make_service(package=pkg)
        with pytest.raises(InvalidTransferStateError, match='COMPLETED/DELIVERED'):
            svc.dispatch(make_command())

    def test_expired_package_rejected(self):
        pkg = make_package(created_at=utc8now() - timedelta(seconds=4000),
                           ttl_seconds=3600)
        svc, *_ = make_service(package=pkg)
        with pytest.raises(PackageExpiredError):
            svc.dispatch(make_command())

    def test_outbound_route_whitelist_blocks_zone_a_instance(self):
        # A 区实例无 →C 出站权限（DEFAULT_ROUTES 无 ('A','C')）
        svc, *_ = make_service(outbound_zone='A')
        with pytest.raises(RouteNotAllowedError):
            svc.dispatch(make_command())

    def test_invalid_token_rejected(self):
        svc, *_ = make_service(token='wrong-token')
        with pytest.raises(AccessTokenInvalidError):
            svc.dispatch(make_command(token='wrong-token'))

    def test_missing_package_404(self):
        svc, *_ = make_service()
        with pytest.raises(PackageNotFoundError):
            svc.dispatch(make_command(transfer_id='no-such'))


# ================= ThirdPartyCAPIClient 三契约与重试 =================
class TestCAPIClientContracts:
    def test_multipart_sends_fields_files_and_transfer_id(self):
        client, session = make_c_client([FakeResponse(200, OK_RESULT)])
        outcome = client.deliver('multipart', make_bundle())
        assert outcome.delivered is True
        assert outcome.dst_status == 200
        assert outcome.body == OK_RESULT
        call = session.calls[0]
        assert (call['method'], call['url']) == ('POST', 'http://c/evaluate')
        assert call['data']['transfer_id'] == 'tid-001'
        assert call['data']['task_type'] == 'llm_judge'
        filename, content, ctype = call['files']['record_file']
        assert (filename, ctype) == ('a.wav', 'audio/wav')
        assert content.read() == b'RIFFxxxxWAVEfmt '

    def test_feature_extract_sends_features_only(self):
        client, session = make_c_client([FakeResponse(200, OK_RESULT)])
        outcome = client.deliver('feature_extract', make_bundle())
        assert outcome.delivered is True
        body = session.calls[0]['json']
        assert body['transfer_id'] == 'tid-001'
        # 非法 WAV 内容 → wave 解析失败回退基础特征（size/sha256），无声道字段
        feats = body['features']['record_file']
        assert feats['size_bytes'] == len(b'RIFFxxxxWAVEfmt ')
        assert 'sha256' in feats and 'channels' not in feats
        assert 'files' not in body

    def test_presigned_flow_upload_then_evaluate(self):
        client, session = make_c_client([
            FakeResponse(200, {'upload_url': 'http://c/upload/1', 'object_ref': 'obj-1'}),
            FakeResponse(200, {}),
            FakeResponse(200, OK_RESULT),
        ])
        outcome = client.deliver('presigned_url', make_bundle())
        assert outcome.delivered is True
        assert len(session.calls) == 3
        assert session.calls[1]['method'] == 'PUT'
        assert session.calls[1]['data'] == b'RIFFxxxxWAVEfmt '
        body = session.calls[2]['json']
        assert body['objects'] == {'record_file': 'obj-1'}

    def test_presigned_missing_object_ref_fails(self):
        client, session = make_c_client(
            [FakeResponse(200, {'upload_url': 'http://c/u'})], max_retries=0)
        outcome = client.deliver('presigned_url', make_bundle())
        assert outcome.delivered is False
        assert 'object_ref' in outcome.error
        assert len(session.calls) == 1

    def test_invalid_kind_fail_closed(self):
        client, _ = make_c_client([])
        with pytest.raises(InvalidPackageFieldError, match='非法第三方评估投递形态'):
            client.deliver('smoke_signal', make_bundle())


class TestCAPIClientRetry:
    def test_retries_on_5xx_then_succeeds(self):
        client, session = make_c_client([
            FakeResponse(500, None, text='boom'),
            FakeResponse(200, OK_RESULT),
        ])
        outcome = client.deliver('multipart', make_bundle())
        assert outcome.delivered is True
        assert outcome.attempts == 2
        assert len(session.calls) == 2

    def test_no_retry_on_4xx(self):
        client, session = make_c_client([FakeResponse(400, {'detail': 'bad'}, text='bad')])
        outcome = client.deliver('multipart', make_bundle())
        assert outcome.delivered is False
        assert outcome.dst_status == 400
        assert 'HTTP 400' in outcome.error
        assert len(session.calls) == 1

    def test_exhausts_retries_on_network_error(self):
        client, session = make_c_client(
            [requests.exceptions.ConnectionError('down')] * 4)
        outcome = client.deliver('multipart', make_bundle())
        assert outcome.delivered is False
        assert '不可达' in outcome.error
        assert outcome.attempts == 4  # 首次 + 3 次重试
        assert len(session.calls) == 4

    def test_non_json_200_body_passthrough_text(self):
        client, _ = make_c_client([FakeResponse(200, None, text='not-json')])
        outcome = client.deliver('multipart', make_bundle())
        # 投递语义成功（HTTP 200 已送达），评估语义（非 JSON）由 evaluation_service 判定
        assert outcome.delivered is True
        assert outcome.body is None
        assert outcome.text == 'not-json'
