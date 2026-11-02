# -*- coding: utf-8 -*-
"""adb track-devices 帧解析单测（L0 设备事件源）。

覆盖：长度前缀帧读取、设备表解析、在线状态归一、截断/损坏帧。
"""
import os
from io import BytesIO

# BaseConfig 必填项（驱动链会导入 shared.infrastructure.config）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.infrastructure.drivers.adb_track import (  # noqa: E402
    ADB_DEVICE_STATE_ONLINE,
    is_device_online,
    parse_device_snapshot,
    read_device_frame,
)


def frame(text: str) -> bytes:
    payload = text.encode('utf-8')
    return f'{len(payload):04x}'.encode('ascii') + payload


class TestReadDeviceFrame:
    def test_reads_length_prefixed_frame(self):
        stream = BytesIO(frame('SN1\tdevice\nSN2\toffline\n'))
        assert read_device_frame(stream) == b'SN1\tdevice\nSN2\toffline\n'

    def test_empty_snapshot_frame(self):
        stream = BytesIO(b'0000')
        assert read_device_frame(stream) == b''
        assert read_device_frame(stream) is None  # 流结束

    def test_skips_stray_newlines_between_frames(self):
        stream = BytesIO(b'\r\n' + frame('SN1\tdevice\n'))
        assert read_device_frame(stream) == b'SN1\tdevice\n'

    def test_truncated_payload_returns_none(self):
        assert read_device_frame(BytesIO(b'0010SN1\tdev')) is None

    def test_corrupted_header_returns_none(self):
        assert read_device_frame(BytesIO(b'zzzz')) is None


class TestParseDeviceSnapshot:
    def test_parses_serial_state_pairs(self):
        payload = (
            'R58M111\tdevice product:beyond1q model:SM_G973F device:beyond1q transport_id:1\n'
            'emulator-5554\toffline\n'
        ).encode('utf-8')
        assert parse_device_snapshot(payload) == {
            'R58M111': 'device',
            'emulator-5554': 'offline',
        }

    def test_unauthorized_and_blank_lines(self):
        payload = b'\nR58M222\tunauthorized usb:1-1\n\n'
        assert parse_device_snapshot(payload) == {'R58M222': 'unauthorized'}

    def test_empty_payload(self):
        assert parse_device_snapshot(b'') == {}


class TestIsDeviceOnline:
    def test_only_device_state_is_online(self):
        assert is_device_online(ADB_DEVICE_STATE_ONLINE) is True
        assert is_device_online('offline') is False
        assert is_device_online('unauthorized') is False
        assert is_device_online('') is False
