# -*- coding: utf-8 -*-
"""INT-399 验收补充：device_service PlaybackCommandService.check_status 回归防线。

根因（验收阶段暴露的第二缺陷）：check_status 内 `self._get_audio_service()` 未定义
（PlaybackCommandService 从未定义该方法，仅兄弟查询服务 spl_command_service 定义过），
请求穿透网关路由修复（字面路由先于 /{device_id}）后在 device_service 抛
AttributeError → 400 `'PlaybackCommandService' object has no attribute '_get_audio_service'`
（该缺陷被原路由恒 422 一直掩盖）。

修复：改用本类已存在等价引用 _get_physical_devices_via_grpc()（ACL 仓储直取物理设备
列表，与兄弟查询服务 playback_query_service.scan 同款引用），并去掉未定义引用。

本测试独立验证 check_status 行为（进程内打桩，不触 gRPC/真实 Redis/DB）：
1. 无物理设备 → 全部设备 offline → data 状态数组 → code 200
   （修复前此处 AttributeError → code 400，本断言即回归防线）；
2. 物理设备命中 → online + 携带 device_index；未命中 → offline；
3. 写副作用保留：batch_update_playback_status 状态落库 + DeviceStatusChanged
   事件经 EventBus 逐个发布（DEVICE_EVENTS 频道）。
"""
import os

# BaseConfig 类属性在首次导入即冻结；device_service 依赖链会触达 shared/
# infrastructure/config（OSS_ACCESS_KEY/SECRET_KEY 为 required）—— 与仓库
# 「单测普遍以 setdefault('OSS_ACCESS_KEY', 'test') 伪造凭据」口径一致。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import types  # noqa: E402

from device_service.application.commands.playback_command_service import PlaybackCommandService  # noqa: E402


class _FakeRepo:
    """最小仓储桩：get_all_playback_devices 返回内存设备，batch 记录调用。"""

    def __init__(self, devices):
        self.devices = devices
        self.batch_calls = []

    def get_all_playback_devices(self):
        return self.devices

    def batch_update_playback_status(self, status_map):
        self.batch_calls.append(dict(status_map))
        return len(status_map)


class _FakeEventBus:
    """EventBus 替身：记录发布事件，避免触达真实 Redis。"""

    published = []

    def __init__(self, redis_url=None):
        pass

    def publish(self, channel, event_type, payload):
        _FakeEventBus.published.append((channel, event_type, payload))


def _make_service(repo, monkeypatch, physical_devices):
    monkeypatch.setattr(
        PlaybackCommandService, '_get_physical_devices_via_grpc',
        staticmethod(lambda: physical_devices))
    _FakeEventBus.published.clear()
    monkeypatch.setattr('shared.utils.redis_pubsub.EventBus', _FakeEventBus)
    return PlaybackCommandService(repo=repo, spl_repo=None)


def _two_devices():
    return [
        types.SimpleNamespace(id=1, name='dry-1', device_unique_id='UID-1'),
        types.SimpleNamespace(id=2, name='noise-1', device_unique_id='UID-2'),
    ]


# ── 1. 无物理设备 → 全 offline → 200 状态数组（回归防线） ─────────
def test_check_status_all_offline_when_no_physical_devices(monkeypatch):
    """ACL 无物理设备时 check_status 应 200 全 offline（修复前此处 AttributeError 400）。"""
    svc = _make_service(_FakeRepo(_two_devices()), monkeypatch, physical_devices=[])

    result = svc.check_status()

    assert result['code'] == 200, f'check_status 应 200，实际: {result}'
    assert result['success'] is True
    data = result['data']
    assert isinstance(data, list) and len(data) == 2, \
        f'返回应为播放设备状态数组，实际: {str(data)[:200]}'
    assert [d['status'] for d in data] == ['offline', 'offline']
    assert all(d['device_index'] is None for d in data)

    # 写副作用：batch_update_playback_status 落库 + DeviceStatusChanged 事件发布
    assert svc.repo.batch_calls == [{1: 'offline', 2: 'offline'}]
    assert len(_FakeEventBus.published) == 2
    from shared.utils.redis_pubsub import EventChannel, EventType
    assert all(
        ch == EventChannel.DEVICE_EVENTS and et == EventType.DEVICE_STATUS_CHANGED
        for ch, et, _ in _FakeEventBus.published)


# ── 2. 物理设备命中 → online；未命中 → offline ────────────────────
def test_check_status_online_matching_physical_devices(monkeypatch):
    """物理设备命中 UID-1 → online + device_index；UID-2 未命中 → offline。"""
    physical = [{'unique_id': 'UID-1', 'device_index': 0}]
    repo = _FakeRepo(_two_devices())
    svc = _make_service(repo, monkeypatch, physical_devices=physical)

    result = svc.check_status()

    assert result['code'] == 200, f'check_status 应 200，实际: {result}'
    by_id = {d['id']: d for d in result['data']}
    assert by_id[1]['status'] == 'online' and by_id[1]['device_index'] == 0
    assert by_id[2]['status'] == 'offline' and by_id[2]['device_index'] is None
    assert repo.batch_calls == [{1: 'online', 2: 'offline'}]


# ── 3. 空设备表 → 200 空数组，不触发写库/事件 ────────────────────
def test_check_status_empty_playback_table(monkeypatch):
    """无任何播放设备记录 → 200 空数组，batch_update 与事件发布均不发生。"""
    svc = _make_service(_FakeRepo([]), monkeypatch, physical_devices=[])

    result = svc.check_status()

    assert result['code'] == 200
    assert result['data'] == []
    assert svc.repo.batch_calls == []
    assert _FakeEventBus.published == []
