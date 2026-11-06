# -*- coding: utf-8 -*-
"""INT-1974：device_service ACL 解析 audio_service.GetPhysicalDevices 载荷。

缺陷：audio_service 的 `GetPhysicalDevices` 返回 **裸数组**（servicer 直接
`_dumps(devices)`，api_gateway 代理也按裸数组 `json.loads`），而 device_service
ACL 按 `{"devices": [...]}` 解析 —— `list.get` 抛 AttributeError 被
`except Exception` 静默吞掉，恒返回 `([], False)`，导致：

  - `GET /playback-devices/check-status` 把全部设备刷成 offline；
  - `POST /playback-devices/scan` 恒扫 0 个通道；
  - `GET /playback-devices/{id}/diagnosis` 「可枚举」恒不可用；
  - `POST /playback-devices/{id}/reset-config` 恒 409。

本测试直接打 ACL 真实实现（**不 mock ACL 本身**），只替换 gRPC stub 工厂，
覆盖卡面要求的五种输入：裸数组 / `{"devices": [...]}` / 空数组 /
`success=False` / 非 JSON。另补「dict 无 devices」与「形状不可识别」两种
载荷，确保不会退回静默吞错。
"""
import os

# BaseConfig 类属性在首次导入即冻结；device_service 依赖链会触达 shared/
# infrastructure/config（OSS_ACCESS_KEY/SECRET_KEY 为 required）—— 与仓库
# 单测普遍 setdefault 伪造凭据的口径一致。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json  # noqa: E402

import pytest  # noqa: E402

from shared.clients import grpc_clients  # noqa: E402
from device_service.infrastructure.acl.audio_service_acl_repository import (  # noqa: E402
    AudioServiceACLRepository,
    _parse_physical_devices_payload,
)


class _FakeResponse(object):
    def __init__(self, success, data, message=''):
        self.success = success
        self.data = data
        self.message = message


class _FakeStub(object):
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = 0

    def GetPhysicalDevices(self, request):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._response


def _patch_stub(monkeypatch, response=None, error=None):
    stub = _FakeStub(response=response, error=error)
    monkeypatch.setattr(grpc_clients, 'get_audio_service_stub', lambda: stub)
    return stub


def _devices():
    return [
        {'unique_id': 'UID-UCX-1', 'name': 'RME Fireface UCX II', 'channel_index': 0,
         'sample_rate': 96000, 'host_api': 'ASIO'},
        {'unique_id': 'UID-UCX-1', 'name': 'RME Fireface UCX II', 'channel_index': 1,
         'sample_rate': 96000, 'host_api': 'ASIO'},
    ]


# ── 五种卡面输入 ────────────────────────────────────────────────
def test_bare_array_payload_is_accepted(monkeypatch):
    """现行契约：data 是裸数组 → 直接取用，available=True。"""
    _patch_stub(monkeypatch, _FakeResponse(True, json.dumps(_devices())))
    devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert available is True
    assert [d['channel_index'] for d in devices] == [0, 1]
    assert devices[0]['unique_id'] == 'UID-UCX-1'


def test_dict_devices_payload_is_still_supported(monkeypatch):
    """历史形状 {"devices": [...]} 仍可解析（不写兼容层，只做入参兼容）。"""
    _patch_stub(monkeypatch, _FakeResponse(True, json.dumps({'devices': _devices()})))
    devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert available is True
    assert len(devices) == 2


def test_empty_array_means_no_devices_not_unavailable(monkeypatch):
    """空数组 = 没有设备，与「枚举不可用」区分：available 仍为 True。"""
    _patch_stub(monkeypatch, _FakeResponse(True, json.dumps([])))
    devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is True


def test_success_false_marks_unavailable(monkeypatch):
    """audio_service 返回 success=False → available=False。"""
    _patch_stub(monkeypatch, _FakeResponse(False, '', message='设备枚举失败'))
    devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is False


def test_non_json_payload_marks_unavailable_and_warns(monkeypatch, caplog):
    """非 JSON 载荷 → 解析失败 available=False，且必须留下 warning（不再静默）。"""
    _patch_stub(monkeypatch, _FakeResponse(True, 'not-a-json{{'))
    with caplog.at_level('WARNING'):
        devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is False
    assert any('GetPhysicalDevices' in r.message for r in caplog.records)


# ── 边界：形状异常 / gRPC 异常 ───────────────────────────────────
def test_dict_without_devices_list_falls_back_to_empty(monkeypatch, caplog):
    """dict 但 devices 不是 list → 空列表 + warning，available 仍为 True。"""
    _patch_stub(monkeypatch, _FakeResponse(True, json.dumps({'devices': 'oops'})))
    with caplog.at_level('WARNING'):
        devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is True
    assert any('devices' in r.message for r in caplog.records)


@pytest.mark.parametrize('payload', ['123', '"str"', 'true'])
def test_unrecognized_json_shape_falls_back_to_empty(monkeypatch, payload, caplog):
    """其他 JSON 类型 → 空列表 + warning（卡面口径：按空列表处理）。"""
    _patch_stub(monkeypatch, _FakeResponse(True, payload))
    with caplog.at_level('WARNING'):
        devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is True
    assert any('形状不可识别' in r.message for r in caplog.records)


def test_grpc_error_marks_unavailable(monkeypatch):
    """gRPC 调用异常 → available=False（原语义保持不变）。"""
    _patch_stub(monkeypatch, error=RuntimeError('channel closed'))
    devices, available = AudioServiceACLRepository().enumerate_physical_devices()
    assert devices == []
    assert available is False


# ── 解析函数直测（不经 stub，防回归） ───────────────────────────
def test_parser_handles_none_and_bytes():
    assert _parse_physical_devices_payload(None) == []
    assert _parse_physical_devices_payload('') == []
    assert _parse_physical_devices_payload(json.dumps([]).encode('utf-8')) == []
    assert _parse_physical_devices_payload(json.dumps(_devices())) == _devices()
    assert _parse_physical_devices_payload('{bad') is None
