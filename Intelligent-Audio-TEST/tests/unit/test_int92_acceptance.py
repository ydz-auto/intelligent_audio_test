# -*- coding: utf-8 -*-
"""INT-92 独立验收：GetPlaybackDevice code 字段——真实生产路径验收。

补齐开发自测用替身绕过的真实链路环节：
- 真实 PlaybackQueryService.get_one（生产 200/404 code 的实际产地，无 try/except，
  repo 异常直接上抛给 servicer 的 500 分支）+ 真实 servicer；
- 全链（ACL → 真实进程内 gRPC server → 真实 servicer → 真实 get_one → repo 故障/无设备）。

验收标准：
① 人为制造 device_service 故障 → 上游收到真实错误信息，不再静默 None；
② 设备确实不存在 → 行为不变（None，「设备未配置」降级）。
"""
import json
import os
from concurrent import futures

import grpc
import pytest

# 真实 PlaybackQueryService 导入链会触发 shared.infrastructure.config 校验
# （DATABASE_URL 由 tests/conftest.py 兜底，OSS 两个键按 tests/integration 既有
# 模式 setdefault），先于应用层导入设置。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import PlaybackQueryCode
from audio_service.domain.repositories.acl.playback_acl_repository import (
    PlaybackDeviceQueryError,
)

_REPO_FAULT_MSG = '人为注入：device_service 存储层故障（DB 不可用）'


class _DeviceObj:
    """repo 返回的设备 ORM 替身（get_one 调 to_dict()）。"""

    def to_dict(self):
        return {'id': 7, 'name': 'acc-7', 'device_unique_id': 'uid-7'}


class _RepoStub:
    """get_one 依赖的 PlaybackRepositoryInterface 最小替身。"""

    def __init__(self, behavior):
        self._behavior = behavior

    def get_playback_device(self, device_id):
        return self._behavior(device_id)


def _real_query(repo_behavior):
    from device_service.application.queries.playback_query_service import (
        PlaybackQueryService,
    )
    return PlaybackQueryService(repo=_RepoStub(repo_behavior))


def _req(device_id):
    from shared.proto import device_service_pb2 as pb
    return pb.GetPlaybackDeviceRequest(device_id=device_id)


@pytest.fixture()
def servicer():
    from device_service.interfaces.grpc.playback_config_servicers import (
        PlaybackConfigServiceServicer,
    )
    return PlaybackConfigServiceServicer()


# ==================== 验收①：真实 get_one 生产路径的故障 → code=500 + 真实错误 ====================

def test_real_query_repo_fault_servicer_reports_500_real_message(servicer):
    """repo 故障 → 真实 get_one（无 try/except）上抛 → servicer 500 分支携带真实 message。

    生产故障形态（存储层不可用）从 repo 层全链穿透，非替手造 dict。
    """
    def repo_boom(device_id):
        raise RuntimeError(_REPO_FAULT_MSG)

    servicer._query = _real_query(repo_boom)
    resp = servicer.GetPlaybackDevice(_req(7))
    assert resp.success is False
    assert resp.code == PlaybackQueryCode.INTERNAL_ERROR.value
    assert _REPO_FAULT_MSG in resp.message


def test_real_query_repo_found_servicer_reports_200(servicer):
    """repo 命中 → 真实 get_one 产出 code=200，data 正常序列化（200 的生产产地）。"""
    servicer._query = _real_query(lambda device_id: _DeviceObj())
    resp = servicer.GetPlaybackDevice(_req(7))
    assert resp.success is True
    assert resp.code == PlaybackQueryCode.OK.value
    assert json.loads(resp.data)['device_unique_id'] == 'uid-7'


def test_real_query_repo_missing_servicer_reports_404(servicer):
    """repo 返回 None → 真实 get_one 产出 code=404 + 未找到 message（404 的生产产地）。"""
    servicer._query = _real_query(lambda device_id: None)
    resp = servicer.GetPlaybackDevice(_req(999))
    assert resp.success is False
    assert resp.code == PlaybackQueryCode.NOT_FOUND.value
    assert '未找到播放设备' in resp.message


# ==================== 全链：ACL → 真实 gRPC server → 真实 servicer → 真实 get_one → repo ====================

class _LiveRepo:
    def __init__(self):
        self.behavior = None

    def get_playback_device(self, device_id):
        return self.behavior(device_id)


@pytest.fixture()
def live_acl_and_repo():
    """真实 servicer + 真实 PlaybackQueryService + 可切换 repo，挂进程内 gRPC server。"""
    from device_service.interfaces.grpc.playback_config_servicers import (
        PlaybackConfigServiceServicer,
    )
    from device_service.application.queries.playback_query_service import (
        PlaybackQueryService,
    )
    from shared.proto import device_service_pb2_grpc as pb_grpc

    repo = _LiveRepo()
    servicer = PlaybackConfigServiceServicer()
    servicer._query = PlaybackQueryService(repo=repo)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_PlaybackConfigServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()

    from shared.clients import grpc_clients
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')
    grpc_clients.get_playback_config_service_stub = (
        lambda: pb_grpc.PlaybackConfigServiceStub(channel))

    from audio_service.infrastructure.acl.playback_acl_repository import (
        PlaybackConfigACLRepositoryImpl,
    )
    try:
        yield PlaybackConfigACLRepositoryImpl(), repo
    finally:
        channel.close()
        server.stop(grace=None)


def test_full_chain_repo_fault_raises_real_error(live_acl_and_repo):
    """验收①全链：repo 存储故障 → ACL 上抛真实错误信息，不再静默 None。"""
    acl, repo = live_acl_and_repo

    def repo_boom(device_id):
        raise RuntimeError(_REPO_FAULT_MSG)

    repo.behavior = repo_boom
    with pytest.raises(PlaybackDeviceQueryError) as ei:
        acl.get_playback_device(7)
    assert _REPO_FAULT_MSG in str(ei.value)
    assert 'GetPlaybackDevice' in str(ei.value)


def test_full_chain_missing_device_degrades_to_none(live_acl_and_repo):
    """验收②全链：repo 无此设备（生产 404 产地）→ ACL 返回 None，降级语义不变。"""
    acl, repo = live_acl_and_repo
    repo.behavior = lambda device_id: None
    assert acl.get_playback_device(999) is None


def test_full_chain_found_device_round_trip(live_acl_and_repo):
    """全链成功路径：repo 设备对象 → to_dict → ACL dict 原样到达上游。"""
    acl, repo = live_acl_and_repo
    repo.behavior = lambda device_id: _DeviceObj()
    assert acl.get_playback_device(7) == {
        'id': 7, 'name': 'acc-7', 'device_unique_id': 'uid-7'}
