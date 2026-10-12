# -*- coding: utf-8 -*-
"""打断驱动链路离线回归测试（VEGA-7）。

覆盖「用例轮次配置 → 聚合层打断轮推导 → 执行引擎注入 → 设备驱动打断分支」链路中
可离线验证的部分：
- 聚合层 is_interruption 推导：直接字段 / algorithm_params / camelCase / 字符串布尔
- executor 注入：pre/post extra_params 的 is_interruption 为归一化 bool（含直接字段形态）
- 驱动 _as_bool kwargs 兼容性：True/'true'/'1'/1（及 'True'/'yes'/'是' 等扩展形态）
- base_driver._check_stop 停止/暂停穿透：暂停阻塞等待恢复、暂停中可停止、停止立即返回
"""
import threading
import time

import pytest


# ──────────────────────────────────────────────
#  聚合层推导
# ──────────────────────────────────────────────

@pytest.mark.parametrize('marked', [True, 'true', '1', 1, 'True', 'yes'])
def test_aggregator_marks_next_round_for_various_truthy_forms(marked):
    from backend.services.execution.e2e_aggregator import E2EAggregator

    metadata = E2EAggregator.build_interruption_round_metadata([
        {'is_interruption': marked},
        {'is_interruption': False},
    ])
    assert metadata['is_interruption'] == [True, False]
    assert metadata['interruption_rounds'] == [1]
    assert metadata['dangling_interruption_rounds'] == []


def test_aggregator_reads_algorithm_params_list_and_camel_field():
    from backend.services.execution.e2e_aggregator import E2EAggregator

    metadata = E2EAggregator.build_interruption_round_metadata([
        {'algorithm_params': [{'field_code': 'is_interruption', 'field_value': 1}]},
        {'isInterruption': 'true'},
    ])
    assert metadata['is_interruption'] == [True, True]
    # 标记轮的下一轮才是实际打断语音轮；末轮标记为 dangling
    assert metadata['interruption_rounds'] == [1]
    assert metadata['dangling_interruption_rounds'] == [1]


# ──────────────────────────────────────────────
#  executor 注入（离线：假 device_manager + 假 playback_orchestrator）
# ──────────────────────────────────────────────

class _FakeDeviceManager:
    def __init__(self):
        self.pre_params = []
        self.post_params = []

    def setup_env_devices_for_round(self, round_algo_params, task_id):
        return {}

    def teardown_env_devices_for_round(self, env_states, task_id):
        pass

    def pre_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        self.pre_params.append(kwargs.get('extra_params', {}))
        return True

    def post_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        self.post_params.append(kwargs.get('extra_params', {}))
        # 返回 False 让 _execute_single_round 提前返回，
        # 本测试只验证注入的 extra_params，不走采集/评估链路
        return False


def _make_executor(fake_dm):
    from backend.services.execution.e2e_executor import E2EExecutor
    from backend.services.execution.e2e_aggregator import E2EAggregator

    executor = E2EExecutor.__new__(E2EExecutor)
    executor._log = lambda **kw: None
    executor._aggregator = E2EAggregator(executor)
    executor._device_manager = fake_dm
    executor._playback_timestamps = {}
    executor._collect_playback_timestamps = lambda *a, **kw: None
    return executor


@pytest.mark.parametrize('round_config,expected', [
    ({'is_interruption': 1}, True),        # 直接字段（前端标准落点，config.rounds 轮级）
    ({'is_interruption': 'true'}, True),   # 直接字段字符串布尔
    ({'isInterruption': True}, True),      # camelCase 直接字段
    ({'algorithm_params': [{'field_code': 'is_interruption', 'field_value': 1}]}, True),
    ({'algorithm_params': [{'field_code': 'isInterruption', 'field_value': 'true'}]}, True),
    ({}, False),
    ({'is_interruption': 0}, False),
    ({'is_interruption': 'false'}, False),
])
def test_executor_injects_normalized_is_interruption(monkeypatch, round_config, expected):
    import backend.services.execution.e2e_executor as e2e_mod

    class _FakeOrchestrator:
        @staticmethod
        def play_round(**kwargs):
            return True

    monkeypatch.setattr(e2e_mod, 'playback_orchestrator', _FakeOrchestrator)

    fake_dm = _FakeDeviceManager()
    executor = _make_executor(fake_dm)

    rounds = [round_config, {}]
    executor._execute_single_round(
        task_id=1, tc_rel_id=1, data={}, case_config={'rounds': rounds},
        case_name='case', algorithm_type='voice_llm', test_case_id=1,
        rounds=rounds, device_info_list=[{'device_sn': 'SN', 'driver': None}],
        result_id=1, case_reference_params={},
        round_idx=0, round_config=round_config, round_number=1, rounds_data=[],
    )

    # pre/post 注入的必须是归一化 bool（驱动侧 _as_bool 亦可再兼容原始形态）
    assert fake_dm.pre_params[0]['is_interruption'] is expected
    assert fake_dm.post_params[0]['is_interruption'] is expected


# ──────────────────────────────────────────────
#  驱动 _as_bool kwargs 兼容性（三个 harmony 聊天驱动共用父类实现）
# ──────────────────────────────────────────────

def test_driver_as_bool_kwargs_compatibility():
    from backend.utils.device_driver.harmony_xiaoyichat import Xiaoyilivechat
    from backend.utils.device_driver.harmony_doubaochat import DoubaoChat
    from backend.utils.device_driver.harmony_chatgpt import ChatGptVoiceChat

    for driver_cls in (Xiaoyilivechat, DoubaoChat, ChatGptVoiceChat):
        as_bool = driver_cls._as_bool
        # 验收标准要求的 4 种形态 + 聚合层 _as_bool 覆盖的扩展形态
        for truthy in (True, 'true', '1', 1, 'True', ' TRUE ', 'yes', 'y', '是'):
            assert as_bool(truthy) is True, (driver_cls.__name__, truthy)
        for falsy in (False, 'false', '0', 0, None, '', 'no', {}):
            assert as_bool(falsy) is False, (driver_cls.__name__, falsy)


# ──────────────────────────────────────────────
#  base_driver._check_stop 停止/暂停穿透
# ──────────────────────────────────────────────

def _make_driver_with_events(stop_event, pause_event):
    from backend.utils.device_driver.base_driver import BaseDeviceDriver
    from backend.utils.device_driver.utils import register_task_events, unregister_task_events

    driver = BaseDeviceDriver()
    driver._task_id = 'unit-test-check-stop'
    register_task_events(driver._task_id, stop_event, pause_event)
    return driver, unregister_task_events


def test_check_stop_returns_true_when_stopped():
    stop_event = threading.Event()
    pause_event = threading.Event()
    pause_event.set()  # 运行中
    stop_event.set()   # 已停止
    driver, unregister = _make_driver_with_events(stop_event, pause_event)
    try:
        assert driver._check_stop('单测') is True
    finally:
        unregister(driver._task_id)


def test_check_stop_blocks_while_paused_and_resumes():
    stop_event = threading.Event()
    pause_event = threading.Event()  # 未置位 = 已暂停
    driver, unregister = _make_driver_with_events(stop_event, pause_event)
    try:
        result = {}

        def _call():
            result['ret'] = driver._check_stop('单测暂停')
            result['elapsed'] = time.time()

        t = threading.Thread(target=_call)
        start = time.time()
        t.start()
        time.sleep(0.3)
        assert t.is_alive(), '暂停期间 _check_stop 应阻塞等待恢复'
        pause_event.set()  # 恢复运行
        t.join(timeout=3)
        assert not t.is_alive()
        assert result['ret'] is False
        assert result['elapsed'] - start >= 0.3
    finally:
        unregister(driver._task_id)


def test_check_stop_stop_during_pause_returns_true():
    stop_event = threading.Event()
    pause_event = threading.Event()  # 已暂停
    driver, unregister = _make_driver_with_events(stop_event, pause_event)
    try:
        result = {}

        def _call():
            result['ret'] = driver._check_stop('单测暂停中停止')

        t = threading.Thread(target=_call)
        t.start()
        time.sleep(0.3)
        assert t.is_alive()
        stop_event.set()  # 暂停期间下停止指令
        t.join(timeout=3)
        assert result['ret'] is True
    finally:
        unregister(driver._task_id)
