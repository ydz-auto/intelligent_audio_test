# -*- coding: utf-8 -*-
"""INT-92：GetPlaybackDevice 响应 code 字段——「设备未找到」与「服务故障」区分。

- device_service servicer 按失败原因填充 code（200 成功 / 404 未找到 / 500 故障）
- audio_service ACL 据此决策：NOT_FOUND(404)/未透传(0，旧版本兼容) 返回 None
  维持「设备未配置」降级语义；其余故障 code 上抛 PlaybackDeviceQueryError
  携带真实错误信息，不再静默吞成 None
- 真链路：进程内真实 gRPC server + 真实 pb2 序列化，验证端到端故障注入语义
"""
import json
from concurrent import futures

import grpc
import pytest

from shared.models.common_enums import PlaybackQueryCode
from audio_service.domain.repositories.acl.playback_acl_repository import (
    PlaybackDeviceQueryError,
)


# ==================== 测试替身 ====================

class _FakeStub:
    """按 behavior(request) 返回假响应/抛异常的 PlaybackConfigService stub。"""

    def __init__(self, behavior):
        self._behavior = behavior

    def GetPlaybackDevice(self, request):
        return self._behavior(request)


class _Resp:
    def __init__(self, success, data='', message='', code=0):
        self.success = success
        self.data = data
        self.message = message
        self.code = code


class _FakeQuery:
    """按 behavior(device_id) 返回/抛出的 PlaybackQueryService 替身。"""

    def __init__(self, behavior):
        self._behavior = behavior

    def get_one(self, device_id):
        return self._behavior(device_id)


def _install_stub(monkeypatch, behavior):
    from shared.clients import grpc_clients
    monkeypatch.setattr(grpc_clients, 'get_playback_config_service_stub',
                        lambda: _FakeStub(behavior))


def _req(device_id):
    from shared.proto import device_service_pb2 as pb
    return pb.GetPlaybackDeviceRequest(device_id=device_id)


@pytest.fixture()
def acl():
    from audio_service.infrastructure.acl.playback_acl_repository import (
        PlaybackConfigACLRepositoryImpl,
    )
    return PlaybackConfigACLRepositoryImpl()


@pytest.fixture()
def servicer():
    from device_service.interfaces.grpc.playback_config_servicers import (
        PlaybackConfigServiceServicer,
    )
    return PlaybackConfigServiceServicer()


# ==================== device_service servicer：code 填充 ====================

def test_servicer_passes_not_found_code(servicer):
    """设备不存在（query 404）→ success=False 且 code=404 透传。"""
    servicer._query = _FakeQuery(lambda did: {
        'success': False, 'message': '未找到播放设备', 'data': None,
        'code': PlaybackQueryCode.NOT_FOUND.value})
    resp = servicer.GetPlaybackDevice(_req(999))
    assert resp.success is False
    assert resp.code == PlaybackQueryCode.NOT_FOUND.value
    assert '未找到播放设备' in resp.message


def test_servicer_passes_success_code(servicer):
    """查询成功 → code=200 透传，data 正常序列化。"""
    servicer._query = _FakeQuery(lambda did: {
        'success': True, 'message': 'Success', 'data': {'id': 7, 'name': 'dry-1'},
        'code': PlaybackQueryCode.OK.value})
    resp = servicer.GetPlaybackDevice(_req(7))
    assert resp.success is True
    assert resp.code == PlaybackQueryCode.OK.value
    assert '"id": 7' in resp.data


def test_servicer_exception_reports_internal_error_code(servicer):
    """query 抛异常（存储故障等）→ code=500 + 真实错误 message，不得裸 success=False。"""
    def boom(did):
        raise RuntimeError('人为注入：device_service 存储层不可用')

    servicer._query = _FakeQuery(boom)
    resp = servicer.GetPlaybackDevice(_req(7))
    assert resp.success is False
    assert resp.code == PlaybackQueryCode.INTERNAL_ERROR.value
    assert '人为注入：device_service 存储层不可用' in resp.message


# ==================== audio_service ACL：code 消费决策 ====================

def test_acl_not_found_code_returns_none(acl, monkeypatch):
    """code=404（设备不存在/已删除）→ None，调用方按「设备未配置」降级。"""
    _install_stub(monkeypatch, lambda req: _Resp(
        False, message='未找到播放设备', code=PlaybackQueryCode.NOT_FOUND.value))
    assert acl.get_playback_device(999) is None


def test_acl_legacy_no_code_returns_none(acl, monkeypatch):
    """code=0（旧版本 device_service 未透传）→ None，保持向后兼容。"""
    _install_stub(monkeypatch, lambda req: _Resp(False, message='未找到播放设备'))
    assert acl.get_playback_device(999) is None


def test_acl_internal_error_code_raises_real_message(acl, monkeypatch):
    """code=500（服务故障）→ 上抛 PlaybackDeviceQueryError 携带真实错误，不再静默 None。"""
    _install_stub(monkeypatch, lambda req: _Resp(
        False, message='database is locked',
        code=PlaybackQueryCode.INTERNAL_ERROR.value))
    with pytest.raises(PlaybackDeviceQueryError) as ei:
        acl.get_playback_device(7)
    assert 'database is locked' in str(ei.value)
    assert 'GetPlaybackDevice' in str(ei.value)


def test_acl_unknown_fault_code_raises(acl, monkeypatch):
    """其余非降级 code（如 400/未来新增码）一律按故障上抛，不降级。"""
    _install_stub(monkeypatch, lambda req: _Resp(
        False, message='bad request', code=400))
    with pytest.raises(PlaybackDeviceQueryError) as ei:
        acl.get_playback_device(7)
    assert 'bad request' in str(ei.value)


def test_acl_success_with_code_returns_device(acl, monkeypatch):
    """code=200 成功路径不受影响，正常返回设备 dict。"""
    _install_stub(monkeypatch, lambda req: _Resp(
        True, data=json.dumps({'id': 7, 'name': 'dry-1'}),
        code=PlaybackQueryCode.OK.value))
    assert acl.get_playback_device(7) == {'id': 7, 'name': 'dry-1'}


# ==================== 真链路：进程内 gRPC server + 真实 pb2 序列化 ====================

class _SwitchableQuery:
    """真实 servicer 委托的 query 替身，behavior 测试内切换。"""

    def __init__(self):
        self.behavior = None

    def get_one(self, device_id):
        return self.behavior(device_id)


@pytest.fixture()
def live_server():
    """真实 PlaybackConfigServiceServicer 挂在进程内 gRPC server（随机端口）。

    返回 (port, query替身)；ACL 侧 stub 工厂被替换为指向该 server 的真实 channel，
    code 字段经真实 pb2 序列化往返。
    """
    from device_service.interfaces.grpc.playback_config_servicers import (
        PlaybackConfigServiceServicer,
    )
    from shared.proto import device_service_pb2_grpc as pb_grpc

    query = _SwitchableQuery()
    servicer = PlaybackConfigServiceServicer()
    servicer._query = query
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_PlaybackConfigServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    yield port, query
    server.stop(grace=None)


@pytest.fixture()
def live_acl(live_server, monkeypatch):
    """get_playback_config_service_stub 指向进程内真 server 的 ACL 实例。"""
    from shared.clients import grpc_clients
    from shared.proto import device_service_pb2_grpc as pb_grpc

    port, _ = live_server
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')
    monkeypatch.setattr(grpc_clients, 'get_playback_config_service_stub',
                        lambda: pb_grpc.PlaybackConfigServiceStub(channel))
    from audio_service.infrastructure.acl.playback_acl_repository import (
        PlaybackConfigACLRepositoryImpl,
    )
    yield PlaybackConfigACLRepositoryImpl()
    channel.close()


def test_live_fault_injection_raises_real_error(live_acl, live_server):
    """验收①：人为制造 device_service 故障 → 上游收到真实错误信息，不再静默 None。"""
    _, query = live_server
    query.behavior = lambda did: (_ for _ in ()).throw(
        RuntimeError('人为注入：device_service 存储层不可用'))
    with pytest.raises(PlaybackDeviceQueryError) as ei:
        live_acl.get_playback_device(7)
    assert '人为注入：device_service 存储层不可用' in str(ei.value)


def test_live_not_found_degrades_to_none(live_acl, live_server):
    """验收②：设备确实不存在 → 行为不变（None，调用方按「设备未配置」降级）。"""
    _, query = live_server
    query.behavior = lambda did: {
        'success': False, 'message': '未找到播放设备', 'data': None,
        'code': PlaybackQueryCode.NOT_FOUND.value}
    assert live_acl.get_playback_device(999) is None


def test_live_success_round_trip(live_acl, live_server):
    """成功路径真实 pb2 往返：device dict 原样到达上游。"""
    _, query = live_server
    query.behavior = lambda did: {
        'success': True, 'message': 'Success',
        'data': {'id': 7, 'name': 'dry-1', 'device_unique_id': 'uid-7'},
        'code': PlaybackQueryCode.OK.value}
    dev = live_acl.get_playback_device(7)
    assert dev == {'id': 7, 'name': 'dry-1', 'device_unique_id': 'uid-7'}
