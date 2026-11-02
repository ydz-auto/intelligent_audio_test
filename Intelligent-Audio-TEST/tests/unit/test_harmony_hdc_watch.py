# -*- coding: utf-8 -*-
"""HarmonyOS hdc 设备表变更监听单测。

hdc 3.2.0c 无原生 device-track 命令，驱动用 ``hdc list targets`` 短周期变更检测
产出与 adb 相同的快照流；本单测覆盖解析与“仅变化时产出”。
"""
import os
import threading

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.infrastructure.drivers import harmony_driver  # noqa: E402


def fake_check_output(output):
    def _run(*args, **kwargs):
        if isinstance(output, Exception):
            raise output
        return output
    return _run


def test_scan_target_snapshot_parses_serials(monkeypatch):
    monkeypatch.setattr(
        harmony_driver.subprocess, 'check_output',
        fake_check_output('5SM0125606000434\n6YF0126211000225\n'),
    )
    assert harmony_driver.HarmonyDriver._scan_target_snapshot(None) == {
        '5SM0125606000434': 'device',
        '6YF0126211000225': 'device',
    }


def test_scan_target_snapshot_empty(monkeypatch):
    monkeypatch.setattr(
        harmony_driver.subprocess, 'check_output',
        fake_check_output('[Empty]\n'),
    )
    assert harmony_driver.HarmonyDriver._scan_target_snapshot(None) == {}


def test_scan_target_snapshot_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        harmony_driver.subprocess, 'check_output',
        fake_check_output(FileNotFoundError('hdc')),
    )
    # None 表示本轮不可信，调用方不得据此把设备判离线
    assert harmony_driver.HarmonyDriver._scan_target_snapshot(None) is None


class FakeWatchDriver:
    """复用 HarmonyDriver 的 watch 生成器，覆盖扫描为受控序列。"""

    watch_device_snapshots = harmony_driver.HarmonyDriver.watch_device_snapshots

    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self.scans = 0

    def supports_device_watch(self):
        return True

    def _scan_target_snapshot(self):
        index = min(self.scans, len(self._snapshots) - 1)
        self.scans += 1
        return self._snapshots[index]


def test_watch_yields_only_on_change(monkeypatch):
    monkeypatch.setattr(harmony_driver.config_manager, 'get_value', lambda *a, **k: 0.001)
    driver = FakeWatchDriver([
        {'SN1': 'device'},
        {'SN1': 'device'},   # 与上一轮相同，不产出
        {},                  # 设备全部拔掉，产出空快照
    ])
    stop_event = threading.Event()

    stream = driver.watch_device_snapshots(stop_event)
    assert next(stream) == {'SN1': 'device'}
    assert next(stream) == {}
    stop_event.set()
    assert list(stream) == []
