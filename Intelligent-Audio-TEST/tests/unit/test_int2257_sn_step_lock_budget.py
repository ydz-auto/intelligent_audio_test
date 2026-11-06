# -*- coding: utf-8 -*-
"""INT-2257：同 SN 步骤锁等待预算按单步上界 / 排队位次给足，慢初始化不再被误判失败。

缺陷：`DEVICE_SN_STEP_LOCK_WAIT_SECONDS` 旧默认 60s 是「整组排队总预算」，而真机
initialize 在守护自愈 + UI RPC 抖动时可超 200s（见 `GRPC_DEVICE_OP_DEADLINE_SECONDS`
默认 300 的注释）。同 SN 第 2 条起等待 60s 必然超时 → e2e initialize_driver 上抛 →
整条用例失败。

修复口径：
- 单步预算与单步最长耗时对齐（默认 = 调用方 deadline 的 90%，仍满足
  「等待 < 调用方 deadline」）；
- 等待预算按排队位次累加：第 N 位最多等 N 个单步；
- 再按调用方剩余 deadline 截断（留响应余量），超时消息带持锁动作 / 已持锁时长 /
  排队位次。

用例按真实比例设置：等待 2s、单步 3s —— 后到者必失败；把等待上限调到 5s 后成功。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import threading
import time

import pytest

from shared.proto import device_service_pb2 as pb
from shared.utils.grpc_json import dumps as _dumps
from device_service.interfaces.grpc import device_runtime_servicers as servicer_mod
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer

SN = 'INT2257_SN_5SM0125701000999'
SN_OTHER = 'INT2257_SN_OTHER_6YF0126211000888'


@pytest.fixture(autouse=True)
def _clean_step_state():
    """锁表 / 持锁者 / 排队者都是模块级按 SN 常驻，用例间必须清空。"""
    for table in (servicer_mod._device_step_locks,
                  servicer_mod._device_step_holders,
                  servicer_mod._device_step_waiters):
        table.clear()
    yield
    for table in (servicer_mod._device_step_locks,
                  servicer_mod._device_step_holders,
                  servicer_mod._device_step_waiters):
        table.clear()


class _TimedDriver:
    """pre_process 固定占用 step_seconds（模拟真机慢初始化），记录进入 / 离开时刻。"""

    def __init__(self, step_seconds):
        self.step_seconds = step_seconds
        self.calls = 0
        self.entered_at = []
        self.left_at = []
        self._lock = threading.Lock()

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        with self._lock:
            self.calls += 1
        self.entered_at.append((threading.current_thread().name, time.time()))
        time.sleep(self.step_seconds)
        self.left_at.append((threading.current_thread().name, time.time()))
        return True


class _GatedDriver:
    """pre_process 阻塞到 release 事件，用于构造「仍在跑」的持锁者。"""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=10), '驱动层未收到释放信号'
        return True


class _FakeFactory:
    def __init__(self, driver):
        self.driver = driver

    def resolve_driver(self, system=None, keywords=None, device_sn=None, task_id=None):
        return self.driver

    def register_task_devices(self, task_id, device_info_list):
        pass


def _make_servicer(monkeypatch, driver):
    servicer = DeviceServiceServicer()
    fake = _FakeFactory(driver)
    monkeypatch.setattr(DeviceServiceServicer, 'factory', property(lambda self: fake))
    return servicer


def _request(action, device_sn=SN):
    config = {'action': action, 'device_sn': device_sn, 'system': 'HarmonyOS',
              'keywords': 'harmony.xiaoyi_livechat.v1'}
    return pb.CreateDriverRequest(task_id='int2257-budget', device_config=_dumps(config))


def _start(servicer, request, out, key, context=None):
    """在线程里发起一次 CreateDriver，记录返回值与起止时间。"""
    def _run():
        began = time.time()
        resp = servicer.CreateDriver(request, context)
        out[key] = (resp, began, time.time())
        return resp
    thread = threading.Thread(target=_run, name=f'int2257-{key}', daemon=True)
    thread.start()
    return thread


def _wait_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _set_base_wait(monkeypatch, seconds):
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', seconds, raising=False)


class TestWaitBudgetVersusSingleStep:
    def test_slow_step_times_out_when_budget_below_step(self, monkeypatch):
        """等待 2s、单步 3s：后到者必然失败，且文案说清持锁动作与排队位次。"""
        _set_base_wait(monkeypatch, 2)
        driver = _TimedDriver(step_seconds=3)
        servicer = _make_servicer(monkeypatch, driver)

        out = {}
        first = _start(servicer, _request('pre_process'), out, 'first')
        assert _wait_until(lambda: driver.calls == 1), '第一个请求未进入驱动层'

        began = time.time()
        resp = servicer.CreateDriver(_request('pre_process'))
        elapsed = time.time() - began

        first.join(timeout=10)
        assert resp.success is False
        assert '等待 2s 超时' in resp.message
        assert '持锁动作 pre_process' in resp.message
        assert '已持锁' in resp.message
        assert '排队第 2 位' in resp.message
        assert 1.8 <= elapsed <= 3.0, f'等待时长 {elapsed:.2f}s 未按 2s 预算收敛'
        assert driver.calls == 1, '超时后不应进入驱动层'

    def test_aligning_budget_with_step_lets_waiter_run(self, monkeypatch):
        """同一场景把等待上限调到 5s（> 单步 3s）：后到者等到锁后正常执行。"""
        _set_base_wait(monkeypatch, 5)
        driver = _TimedDriver(step_seconds=3)
        servicer = _make_servicer(monkeypatch, driver)

        out = {}
        first = _start(servicer, _request('pre_process'), out, 'first')
        assert _wait_until(lambda: driver.calls == 1), '第一个请求未进入驱动层'

        began = time.time()
        resp = servicer.CreateDriver(_request('pre_process'))
        elapsed = time.time() - began

        first.join(timeout=10)
        assert resp.success is True, resp.message
        assert elapsed >= 2.8, f'后到者只等了 {elapsed:.2f}s，未真正排队到第一个步骤结束'
        assert driver.calls == 2
        assert driver.entered_at[1][1] >= driver.left_at[0][1] - 0.05

    def test_budget_accumulates_by_queue_position(self, monkeypatch):
        """第 3 位（前方 2 个步骤）拿到 2 倍预算：2s 预算下第 2 位超时、第 3 位成功。"""
        _set_base_wait(monkeypatch, 2)
        driver = _TimedDriver(step_seconds=3)
        servicer = _make_servicer(monkeypatch, driver)

        out = {}
        first = _start(servicer, _request('pre_process'), out, 'first')
        assert _wait_until(lambda: driver.calls == 1), '第一个请求未进入驱动层'
        second = _start(servicer, _request('pre_process'), out, 'second')
        assert _wait_until(lambda: servicer_mod._device_step_waiters.get(SN, 0) >= 1), \
            '第 2 个请求未进入排队'
        third = _start(servicer, _request('pre_process'), out, 'third')
        assert _wait_until(lambda: servicer_mod._device_step_waiters.get(SN, 0) >= 2), \
            '第 3 个请求未进入排队'

        for thread in (first, second, third):
            thread.join(timeout=15)

        assert out['first'][0].success is True
        assert out['second'][0].success is False, '第 2 位只有 2s 预算，单步 3s 应当超时'
        assert '排队第 2 位' in out['second'][0].message
        assert out['third'][0].success is True, out['third'][0].message
        assert '排队第 3 位' not in out['third'][0].message
        assert driver.calls == 2, f'驱动层调用次数 {driver.calls} 与成功步骤数不符'


class TestTimeoutDiagnostics:
    def test_message_reports_holding_action_and_held_seconds(self, monkeypatch):
        _set_base_wait(monkeypatch, 1)
        driver = _GatedDriver()
        servicer = _make_servicer(monkeypatch, driver)

        out = {}
        holder = _start(servicer, _request('pre_process'), out, 'holder')
        assert driver.entered.wait(timeout=5), '持锁请求未进入驱动层'

        began = time.time()
        resp = servicer.CreateDriver(_request('pre_process'))
        elapsed = time.time() - began

        driver.release.set()
        holder.join(timeout=10)
        assert resp.success is False
        assert resp.message.startswith(
            f'设备 {SN} 正在执行其他操作（同 SN 步骤串行），等待 1s 超时（持锁动作 pre_process 已持锁 ')
        assert '；步骤 pre_process 本请求排队第 2 位）' in resp.message
        assert elapsed >= 0.9


class TestCallerDeadlineCap:
    """等待预算必须小于调用方 deadline，否则调用方只看到 DEADLINE_EXCEEDED。"""

    class _Context:
        def __init__(self, remaining):
            self._remaining = remaining

        def time_remaining(self):
            return self._remaining

    def test_wait_budget_capped_by_caller_remaining_deadline(self, monkeypatch):
        _set_base_wait(monkeypatch, 60)
        driver = _TimedDriver(step_seconds=0.1)
        servicer = _make_servicer(monkeypatch, driver)

        holder, release = self._hold_lock()
        try:
            began = time.time()
            resp = servicer.CreateDriver(_request('pre_process'), self._Context(8.0))
            elapsed = time.time() - began
        finally:
            release.set()
            holder.join(timeout=5)

        # min(60, 8 - 5) = 3s
        assert resp.success is False
        assert '等待 3s 超时' in resp.message, resp.message
        assert elapsed < 6.0, f'未被调用方 deadline 截断，等待 {elapsed:.2f}s'

    @staticmethod
    def _hold_lock():
        lock = servicer_mod._device_step_lock(SN)
        release = threading.Event()
        held = threading.Event()

        def _run():
            assert lock.acquire(timeout=5)
            servicer_mod._device_step_holder_enter(SN, 'initialize')
            held.set()
            release.wait(timeout=10)
            servicer_mod._device_step_holder_leave(SN)
            lock.release()

        thread = threading.Thread(target=_run, name='int2257-deadline-holder', daemon=True)
        thread.start()
        assert held.wait(timeout=5), '持锁线程未拿到锁'
        return thread, release

    def test_no_deadline_keeps_full_budget(self, monkeypatch):
        """非 gRPC 上下文（context=None）不截断，仍按单步预算等待。"""
        _set_base_wait(monkeypatch, 30)
        assert servicer_mod._device_step_wait_budget(30, 1, None) == 30
        assert servicer_mod._device_step_wait_budget(30, 0, None) == 30

    def test_accumulated_budget_still_capped_by_deadline(self):
        assert servicer_mod._device_step_wait_budget(
            60, 2, self._Context(20.0)) == 15  # min(120, 20-5)
        assert servicer_mod._device_step_wait_budget(
            60, 2, self._Context(400.0)) == 120  # 位次累加生效


class TestDefaultBudgetConfig:
    def test_default_covers_single_step_and_stays_below_caller_deadline(self):
        from shared.infrastructure.config import BaseConfig
        name = 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS'
        if name in os.environ:
            pytest.skip('环境变量显式覆盖了等待预算')
        assert BaseConfig.DEVICE_SN_STEP_LOCK_WAIT_SECONDS >= 200, (
            '单步真机 initialize 可超 200s，等待预算低于它仍会误杀慢初始化')
        assert BaseConfig.DEVICE_SN_STEP_LOCK_WAIT_SECONDS < \
            BaseConfig.GRPC_DEVICE_OP_DEADLINE_SECONDS, (
                '等待预算必须小于调用方 deadline（否则调用方先 DEADLINE_EXCEEDED）')
