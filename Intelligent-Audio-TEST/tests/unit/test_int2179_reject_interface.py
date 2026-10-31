# -*- coding: utf-8 -*-
"""INT-2179 补证：拒识轮驱动的服务层接口口径（参数透传 / 路由分支）。

打回项 3 要求「接口级验证（参数、路由、结果落库字段）」。路由与真实设备初始化
由 tests/verify/int2179_reject_probe.py 走宿主机 device_service 取证；本文件补
服务层口径：
- `DeviceServiceServicer.CreateDriver(action='post_process')` 会把 device_config
  的 kwargs 原样传给驱动（is_reject / timing / next_round_is_reject 不缺不改）
- 真实 XiaoyiLivechatReject 经该入口：非打断且非连续拒识 → 受限等待；
  打断型 / 下一轮仍拒识 → 不等待
"""
import json
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.proto import device_service_pb2 as pb
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer
from device_service.infrastructure.drivers.harmony_xiaoyichat import Xiaoyilivechat
from device_service.infrastructure.drivers.harmony_xiaoyi_reject import XiaoyiLivechatReject

SN = '5SM0125701000448'


class _SpyDriver:
    def __init__(self):
        self.received = None

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        self.received = {'device_sn': device_sn, 'task_id': task_id,
                         'test_case_id': test_case_id, 'kwargs': dict(kwargs)}
        return True


class _FakeFactory:
    def __init__(self, driver):
        self.driver = driver

    def resolve_driver(self, system=None, keywords=None, device_sn=None, task_id=None):
        return self.driver


def _make_reject_driver():
    driver = XiaoyiLivechatReject.__new__(XiaoyiLivechatReject)
    driver._logs = []
    driver._log = lambda **kw: driver._logs.append(kw)
    driver.HW_PARAMS_PATH = '/proc/asound/card0/pcm0p/sub0/hw_params'
    driver.HW_PARAMS_CLOSED_CONFIRM = 3
    driver._check_stop = lambda *a, **k: False
    driver._get_driver = lambda sn: None
    driver._wait_calls = []
    driver._wait_reject_reply_end_limited = lambda sn, task_id=None, test_case_id=None: (
        driver._wait_calls.append(sn) or True)
    return driver


def _servicer(monkeypatch, driver):
    servicer = DeviceServiceServicer()
    fake = _FakeFactory(driver)
    monkeypatch.setattr(DeviceServiceServicer, 'factory', property(lambda self: fake))
    return servicer


def _post_process_request(kwargs):
    payload = {'action': 'post_process', 'device_sn': SN, 'system': 'HarmonyOS',
               'keywords': 'harmony.xiaoyi_livechat_reject.v1', 'kwargs': kwargs}
    return pb.CreateDriverRequest(task_id='int2179-iface',
                                  device_config=json.dumps(payload, ensure_ascii=False))


class TestServicerParamPassthrough:
    def test_reject_kwargs_reach_driver_unchanged(self, monkeypatch):
        spy = _SpyDriver()
        servicer = _servicer(monkeypatch, spy)
        kwargs = {'is_reject': True, 'timing': 'silence',
                  'next_round_is_reject': False, 'record_mode': 'round',
                  'total_rounds': 2, 'round_number': 1}
        resp = servicer.CreateDriver(_post_process_request(kwargs))
        assert resp.success is True
        assert spy.received['device_sn'] == SN
        assert spy.received['task_id'] == 'int2179-iface'
        assert spy.received['kwargs'] == kwargs, '服务层改写了驱动 kwargs'


class TestRealRejectDriverThroughServicer:
    @pytest.mark.parametrize('kwargs,should_wait', [
        ({'is_reject': True, 'timing': 'silence', 'next_round_is_reject': False}, True),
        ({'is_reject': True, 'timing': 'response', 'next_round_is_reject': False}, False),
        ({'is_reject': True, 'timing': 'silence', 'next_round_is_reject': True}, False),
        ({'is_reject': False, 'timing': 'silence', 'next_round_is_reject': False}, False),
    ])
    def test_limited_wait_branch_selected(self, monkeypatch, kwargs, should_wait):
        driver = _make_reject_driver()
        # 基类收尾用桩替换，避免依赖真机录音文件
        monkeypatch.setattr(Xiaoyilivechat, 'post_process', lambda self, *a, **k: True)
        servicer = _servicer(monkeypatch, driver)
        resp = servicer.CreateDriver(_post_process_request(kwargs))
        assert resp.success is True
        assert bool(driver._wait_calls) is should_wait
        # 轮次口径字段不得被驱动回写
        assert 'is_interruption' not in kwargs
