# -*- coding: utf-8 -*-
"""INT-2179 补证：同 SN 设备步骤互斥（087e9d31e `serialized_device_step`）。

打回项 1 要求：同 SN 两次并发 `CreateDriver` 串行、后到者等待；制造一次等待
超时得到「设备 X 正在执行其他操作（同 SN 步骤串行），等待 Ns 超时」，且不污染
另一 SN。本文件直接走 servicer 真实入口（未绕过装饰器），驱动用假实现卡在
`pre_process` 内，只测加锁语义，不碰真机/真驱动。

- 两线程同 SN：第二个必须在第一个释放后才进入驱动层
- 等待超时：文案可读 + 日志 WARNING；同窗口另一 SN 不被阻塞
- 非硬件 action（register）不受锁影响；不同 SN 并行
- 真实 CreateDriver 确实挂了装饰器，串行 action 集合与实现一致
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import logging
import threading
import time

import pytest

from shared.proto import device_service_pb2 as pb
from shared.utils.grpc_json import dumps as _dumps
from device_service.interfaces.grpc import device_runtime_servicers as servicer_mod
from device_service.interfaces.grpc.device_runtime_servicers import (
    DeviceServiceServicer,
    _SERIALIZED_ACTIONS,
)

SN_A = 'INT2179_SN_A_5SM0125701000448'
SN_B = 'INT2179_SN_B_6YF0126211000225'


@pytest.fixture(autouse=True)
def _clean_step_locks():
    """模块级锁表按 SN 常驻，测试间必须清空，避免上一用例残留锁影响下一用例。"""
    servicer_mod._device_step_locks.clear()
    servicer_mod._device_step_holders.clear()
    servicer_mod._device_step_waiters.clear()
    yield
    servicer_mod._device_step_locks.clear()
    servicer_mod._device_step_holders.clear()
    servicer_mod._device_step_waiters.clear()


class _GatedDriver:
    """pre_process 进入即放行进入信号，阻塞到 release 事件（或超时）后返回。"""

    def __init__(self, entered_event, release_event, result=True):
        self.entered_event = entered_event
        self.release_event = release_event
        self.result = result
        self.calls = 0
        self.entered_at = []
        self.left_at = []

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        self.calls += 1
        self.entered_at.append((threading.current_thread().name, time.time()))
        if self.entered_event is not None:
            self.entered_event.set()
        if self.release_event is not None:
            assert self.release_event.wait(timeout=10), '驱动层未收到释放信号'
        self.left_at.append((threading.current_thread().name, time.time()))
        return self.result


class _FakeFactory:
    def __init__(self, driver):
        self.driver = driver
        self.registered = []

    def resolve_driver(self, system=None, keywords=None, device_sn=None, task_id=None):
        return self.driver

    def register_task_devices(self, task_id, device_info_list):
        self.registered.append((task_id, device_info_list))


def _make_servicer(monkeypatch, driver):
    servicer = DeviceServiceServicer()
    fake = _FakeFactory(driver)
    monkeypatch.setattr(DeviceServiceServicer, 'factory', property(lambda self: fake))
    return servicer, fake


def _request(action, device_sn, **extra):
    config = {'action': action, 'device_sn': device_sn, 'system': 'HarmonyOS',
              'keywords': 'harmony.xiaoyi_livechat.v1'}
    config.update(extra)
    return pb.CreateDriverRequest(task_id='int2179-lock', device_config=_dumps(config))


def _call_in_thread(servicer, request, key, out):
    box = {}

    def _run():
        started = time.time()
        box[key] = (servicer.CreateDriver(request), started, time.time())
    thread = threading.Thread(target=_run, name=f'int2179-lock-{key}', daemon=True)
    thread.start()
    out[key] = (thread, box)
    return thread


def _hold_lock_in_thread(lock, device_sn=SN_A, action='initialize'):
    """RLock 可重入且按线程持有：超时用例必须由另一线程持锁，主线程调用才会真等待。

    同时登记持锁动作（INT-2257 起超时文案要带「持锁动作 + 已持锁时长」），
    与真实步骤路径一致。
    """
    held = threading.Event()
    release = threading.Event()

    def _run():
        assert lock.acquire(timeout=5)
        servicer_mod._device_step_holder_enter(device_sn, action)
        held.set()
        release.wait(timeout=10)
        servicer_mod._device_step_holder_leave(device_sn)
        lock.release()

    thread = threading.Thread(target=_run, name='int2179-lock-holder', daemon=True)
    thread.start()
    assert held.wait(timeout=5), '持锁线程未拿到锁'
    return thread, release


class TestSameSnSerialization:
    def test_two_threads_same_sn_run_one_after_another(self, monkeypatch):
        entered = threading.Event()
        release = threading.Event()
        driver = _GatedDriver(entered, release)
        servicer, _ = _make_servicer(monkeypatch, driver)

        out = {}
        _call_in_thread(servicer, _request('pre_process', SN_A), 'first', out)
        assert entered.wait(timeout=5), '第一个请求未进入驱动层'

        _call_in_thread(servicer, _request('pre_process', SN_A), 'second', out)
        # 后到者被同 SN 锁挡住：驱动层不应被再次进入
        time.sleep(0.4)
        assert driver.calls == 1, '同 SN 第二个请求在第一个释放前就进入了驱动层（未串行）'

        release.set()
        out['first'][0].join(timeout=10)
        out['second'][0].join(timeout=10)

        first_resp = out['first'][1]['first'][0]
        second_resp = out['second'][1]['second'][0]
        assert first_resp.success and second_resp.success
        assert driver.calls == 2
        # 后到者进入驱动层的时间必须晚于第一个离开驱动层的时间
        assert driver.entered_at[1][1] >= driver.left_at[0][1] - 0.05, (
            f'第二个进入 {driver.entered_at[1][1]:.3f} 早于第一个离开 {driver.left_at[0][1]:.3f}')

    def test_wait_timeout_message_and_warning(self, monkeypatch, caplog):
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', 1, raising=False)

        driver = _GatedDriver(None, None)
        servicer, _ = _make_servicer(monkeypatch, driver)

        holder, release = _hold_lock_in_thread(servicer_mod._device_step_lock(SN_A))
        try:
            began = time.time()
            with caplog.at_level(logging.WARNING, logger=servicer_mod.__name__):
                resp = servicer.CreateDriver(_request('pre_process', SN_A))
            elapsed = time.time() - began
        finally:
            release.set()
            holder.join(timeout=5)

        assert resp.success is False
        # 原「同 SN 步骤串行 + 等待 Ns 超时」句式保留；INT-2257 起追加持锁动作 /
        # 已持锁时长 / 排队位次，便于判定是排队还是卡死。
        assert resp.message.startswith(
            f'设备 {SN_A} 正在执行其他操作（同 SN 步骤串行），等待 1s 超时（持锁动作 initialize 已持锁 ')
        assert resp.message.endswith('；步骤 pre_process 本请求排队第 2 位）')
        assert elapsed >= 0.9, f'等待时长 {elapsed:.2f}s 未按配置 1s 生效'
        assert driver.calls == 0, '超时后不应进入驱动层'
        assert any('等待同 SN 串行锁超时' in (r.getMessage() or '')
                   for r in caplog.records), '超时缺少 WARNING 日志'

    def test_timeout_does_not_block_other_sn(self, monkeypatch):
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', 1, raising=False)

        driver = _GatedDriver(None, None)
        servicer, _ = _make_servicer(monkeypatch, driver)

        holder, release = _hold_lock_in_thread(servicer_mod._device_step_lock(SN_A))
        try:
            began = time.time()
            resp = servicer.CreateDriver(_request('pre_process', SN_B))
            elapsed = time.time() - began
        finally:
            release.set()
            holder.join(timeout=5)

        assert resp.success is True
        assert elapsed < 0.9, f'另一 SN 被同 SN 锁阻塞 {elapsed:.2f}s'
        assert driver.calls == 1


class TestLockScope:
    def test_register_action_not_serialized(self, monkeypatch):
        driver = _GatedDriver(None, None)
        servicer, fake = _make_servicer(monkeypatch, driver)

        holder, release = _hold_lock_in_thread(servicer_mod._device_step_lock(SN_A))
        try:
            began = time.time()
            resp = servicer.CreateDriver(_request('register', SN_A,
                                                  device_info_list=[SN_A]))
            elapsed = time.time() - began
        finally:
            release.set()
            holder.join(timeout=5)

        assert resp.success is True
        assert elapsed < 0.9, 'register（非硬件动作）不应等同 SN 步骤锁'
        assert fake.registered, 'register 动作应按原逻辑登记任务设备'

    def test_serialized_actions_cover_hardware_steps(self):
        expected = {'initialize', 'pre_process', 'post_process', 'get_results',
                    'extract_results_from_archive', 'get_final_results', 'teardown'}
        assert _SERIALIZED_ACTIONS == frozenset(expected)

    def test_real_servicer_create_driver_is_decorated(self):
        # functools.wraps 保留 __wrapped__：真实 gRPC 入口确实经过锁装饰器，
        # 而不是只在测试里手工套了一层。
        wrapped = DeviceServiceServicer.CreateDriver.__wrapped__
        assert wrapped is not None
        assert wrapped.__name__ == 'CreateDriver'
