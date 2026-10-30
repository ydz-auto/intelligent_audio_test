# -*- coding: utf-8 -*-
"""INT-2146 验收：小艺通话拒识轮驱动（XiaoyiLivechatReject）+ 执行器 next_round_is_reject 注入。

覆盖（卡面可测验收标准 1~5）：
1. 注册可发现：registry /（hypium 可用时）driver_factory 取到实例，元数据符合
2. timing 词表映射 + 显式 is_interruption 优先且 kwargs 不被改写
3. is_reject 缺省（''/'false'/None）→ 不进入拒识分支、不触发等待
4. 受限等待：hw_params 连续 3 次 closed 结束；持续 replying 5s 上限放行；
   hw_params 读不到回退 UI 法；打断型 / 下一轮拒识轮不等待
5. 执行器：下一轮 is_reject=true → post_extra_params 注入 next_round_is_reject；
   末轮不注入；is_interruption / record_mode / ai_start_timeout 行为不变
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import time
from types import SimpleNamespace

import pytest

from device_service.infrastructure.drivers.harmony_xiaoyichat import Xiaoyilivechat
from device_service.infrastructure.drivers.harmony_xiaoyi_reject import (
    XiaoyiLivechatReject,
)
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers import harmony_xiaoyi_reject as reject_mod


# ──────────────────────────── 公共构造 ────────────────────────────

def _make_reject_driver(**attrs):
    """构造不依赖 hypium/真机的驱动实例（__new__ 绕过 __init__）。"""
    driver = XiaoyiLivechatReject.__new__(XiaoyiLivechatReject)
    driver._logs = []
    driver._log = lambda **kw: driver._logs.append(kw)
    driver.HW_PARAMS_PATH = '/proc/asound/card0/pcm0p/sub0/hw_params'
    driver.HW_PARAMS_CLOSED_CONFIRM = 3
    driver._check_stop = lambda *a, **k: False
    driver._get_driver = lambda sn: None
    for key, value in attrs.items():
        setattr(driver, key, value)
    return driver


def _messages(driver, level=None):
    return [r.get('content', '') for r in driver._logs
            if level is None or r.get('level') == level]


# ──────────────────────────── 1. 注册可发现 ────────────────────────────

class TestRegistration:
    def test_registry_entry_and_metadata(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        entry = driver_registry.get_by_key(
            'xiaoyi_livechat_reject', 'v1', DevicePlatform.HARMONYOS)
        assert entry is not None, '拒识驱动必须登记到注册表'
        cls = entry.driver_cls
        assert cls.keywords == 'harmony.xiaoyi_livechat_reject.v1'
        assert cls.display_name == '小艺通话聊天拒识试验驱动'
        assert cls.platform == DevicePlatform.HARMONYOS
        assert cls.version == 'v1'
        # 继承基类：非拒识轮行为复用 Xiaoyilivechat
        assert issubclass(cls, Xiaoyilivechat)

    def test_factory_keywords_include_reject_driver(self):
        from device_service.infrastructure.drivers import driver_factory as factory_mod
        if not factory_mod._HYPium_AVAILABLE:
            pytest.skip('hypium 不可用：工厂不实例化 HarmonyOS 专用驱动'
                        '（注册表条目测试 test_registry_entry_and_metadata 仍覆盖）')
        keywords = [e['keywords'] for e in factory_mod.DeviceDriverFactory().get_registered_keywords()]
        assert 'harmony.xiaoyi_livechat_reject.v1' in keywords

    def test_factory_import_error_fallback_is_declared(self):
        """hypium 不可用时 driver_factory 的 ImportError 兜底置 None（不炸）。"""
        from device_service.infrastructure.drivers import driver_factory as factory_mod
        assert hasattr(factory_mod, 'XiaoyiLivechatReject')


# ──────────────────────────── 2. timing 词表映射 ────────────────────────────

class TestTimingMapping:
    @pytest.mark.parametrize('timing', ['response', 'Response', ' RESPONSE ', '回复过程中', ' 回复过程中 '])
    def test_interruption_timing_values(self, timing):
        driver = _make_reject_driver()
        assert driver._resolve_timing_is_interruption(timing) is True
        assert _messages(driver, 'WARNING') == []

    @pytest.mark.parametrize('timing', ['silence', 'Silence', '静默', '', None, '  '])
    def test_non_interruption_timing_values(self, timing):
        driver = _make_reject_driver()
        assert driver._resolve_timing_is_interruption(timing) is False
        assert _messages(driver, 'WARNING') == []

    def test_unknown_timing_warns_and_is_non_interruption(self):
        driver = _make_reject_driver()
        assert driver._resolve_timing_is_interruption('一直听') is False
        warnings = _messages(driver, 'WARNING')
        assert len(warnings) == 1 and '未知' in warnings[0]

    def test_explicit_is_interruption_wins_over_timing(self):
        driver = _make_reject_driver()
        assert driver._effective_is_interruption(
            {'is_interruption': True, 'timing': 'silence'}) is True
        assert driver._effective_is_interruption(
            {'is_interruption': 'false', 'timing': '回复过程中'}) is False

    def test_timing_used_only_when_is_interruption_absent(self):
        driver = _make_reject_driver()
        assert driver._effective_is_interruption({'timing': 'response'}) is True
        assert driver._effective_is_interruption({'timing': '静默'}) is False
        assert driver._effective_is_interruption({}) is False


# ──────────────────────────── 3/4. post_process 分支与受限等待 ────────────────────────────

@pytest.fixture
def super_capture(monkeypatch):
    """拦截基类 post_process（记录收到的 kwargs），避免跑真实收尾 UI/录屏流程。"""
    captured = {}

    def fake_base(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(Xiaoyilivechat, 'post_process', fake_base)
    return captured


class TestRejectPostProcess:
    @pytest.mark.parametrize('is_reject', [None, '', 'false', '0', False, 0])
    def test_non_reject_round_goes_straight_to_base(self, super_capture, is_reject):
        driver = _make_reject_driver()
        waits = []
        driver._wait_reject_reply_end_limited = lambda *a, **k: waits.append(1) or True
        kwargs = {'timing': 'silence'}
        if is_reject is not None:
            kwargs['is_reject'] = is_reject
        assert driver.post_process('SN', **kwargs) is True
        assert waits == [], 'is_reject 缺省/假值不得进入拒识分支'
        assert 'skip_reply_wait' not in super_capture, '非拒识轮不得改变基类等待行为'

    def test_explicit_interruption_skips_wait_and_keeps_kwargs(
            self, super_capture):
        driver = _make_reject_driver()
        waits = []
        driver._wait_reject_reply_end_limited = lambda *a, **k: waits.append(1) or True
        kwargs = {'is_reject': True, 'timing': 'silence', 'is_interruption': True}
        assert driver.post_process('SN', **kwargs) is True
        assert waits == [], '显式打断型不等待'
        # 任何情况下不改写 kwargs 的 is_interruption（打断族评估轮次口径）
        assert kwargs['is_interruption'] is True
        assert super_capture['is_interruption'] is True
        assert super_capture['skip_reply_wait'] is True

    def test_timing_derived_interruption_skips_wait(self, super_capture):
        driver = _make_reject_driver()
        waits = []
        driver._wait_reject_reply_end_limited = lambda *a, **k: waits.append(1) or True
        assert driver.post_process('SN', is_reject=True, timing='回复过程中') is True
        assert waits == [], '由 timing 推出的打断型不等待'
        assert 'is_interruption' not in super_capture, 'timing 推导值不得回写进 kwargs'

    def test_next_round_reject_skips_wait(self, super_capture):
        driver = _make_reject_driver()
        waits = []
        driver._wait_reject_reply_end_limited = lambda *a, **k: waits.append(1) or True
        assert driver.post_process(
            'SN', is_reject=True, timing='silence', next_round_is_reject=True) is True
        assert waits == [], '下一轮仍是拒识轮 → 不等待'

    def test_await_reply_when_non_interruption_and_next_round_not_reject(
            self, super_capture):
        driver = _make_reject_driver()
        waits = []
        driver._wait_reject_reply_end_limited = lambda *a, **k: waits.append(1) or True
        assert driver.post_process('SN', is_reject=True, timing='静默') is True
        assert waits == [1], '非打断型 + 下一轮非拒识轮 → 执行受限等待'
        assert super_capture['is_reject'] is True
        assert super_capture['skip_reply_wait'] is True

    def test_input_gap_ms_logged_and_not_waited(self, super_capture):
        driver = _make_reject_driver()
        driver._wait_reject_reply_end_limited = lambda *a, **k: True
        start = time.time()
        assert driver.post_process(
            'SN', is_reject=True, timing='silence', input_gap_ms=3000) is True
        assert time.time() - start < 1
        assert any('input_gap_ms' in m for m in _messages(driver, 'INFO'))


class TestLimitedWait:
    def _driver(self, **attrs):
        driver = _make_reject_driver(**attrs)
        driver.REJECT_REPLY_POLL_INTERVAL = 0.01
        return driver

    def test_three_consecutive_closed_ends_quickly(self):
        driver = _make_reject_driver()   # 保留 1s 轮询，验证真实节奏
        calls = []
        driver._hw_params_replying = lambda sn: calls.append(1) or False
        start = time.time()
        assert driver._wait_reject_reply_end_limited('SN') is True
        elapsed = time.time() - start
        assert len(calls) == driver.HW_PARAMS_CLOSED_CONFIRM
        assert elapsed < reject_mod.REJECT_REPLY_WAIT_TIMEOUT, \
            f'连续 3 次 closed 应在上限内结束，实际 {elapsed:.2f}s'

    def test_replying_until_timeout_releases_with_warning(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_REPLY_WAIT_TIMEOUT', 0.2)
        driver = self._driver()
        driver._hw_params_replying = lambda sn: True
        start = time.time()
        assert driver._wait_reject_reply_end_limited('SN') is True
        assert time.time() - start < 2
        warnings = _messages(driver, 'WARNING')
        assert any('超时' in m and '直接进入下一轮' in m for m in warnings)

    def test_hw_params_unreadable_falls_back_to_ui(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_REPLY_WAIT_TIMEOUT', 0.5)

        class _FakeUi:
            def find_component(self, _selector):
                return object()   # "正在听…" 恒命中 → 连续确认

        driver = self._driver(_get_driver=lambda sn: _FakeUi())
        driver._hw_params_replying = lambda sn: None
        assert driver._wait_reject_reply_end_limited('SN') is True
        warnings = _messages(driver, 'WARNING')
        assert any('回退UI法' in m for m in warnings)
        infos = _messages(driver, 'INFO')
        assert any('正在听…' in m for m in infos)

    def test_hw_params_unreadable_and_no_ui_driver_releases(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_REPLY_WAIT_TIMEOUT', 0.5)
        driver = self._driver(_get_driver=lambda sn: None)
        driver._hw_params_replying = lambda sn: None
        assert driver._wait_reject_reply_end_limited('SN') is True
        warnings = _messages(driver, 'WARNING')
        assert any('UI 抓取层不可用' in m for m in warnings)

    def test_stop_signal_aborts_wait(self):
        driver = self._driver(_check_stop=lambda *a, **k: True)
        driver._hw_params_replying = lambda sn: True
        assert driver._wait_reject_reply_end_limited('SN') is False


# ──────────────────────────── 5. 执行器 next_round_is_reject 注入 ────────────────────────────

from e2e_test_service.application.services.e2e_executor import (  # noqa: E402
    rounds_loop_mixin as loop_mod,
)
from e2e_test_service.application.services.e2e_executor.rounds_loop_mixin import (  # noqa: E402
    RoundsLoopMixin,
)


@pytest.fixture
def pure_normalizer(monkeypatch):
    """把算法参数规范化收敛为纯函数（本单测不连 algorithm_service gRPC）。"""
    calls = []

    def fake_normalize(algorithm_params=None):
        calls.append(algorithm_params)
        result = {}
        for item in (algorithm_params or []):
            if isinstance(item, dict) and 'field_code' in item:
                result[item['field_code']] = item.get('field_value')
        return result

    monkeypatch.setattr(
        loop_mod.AlgorithmAclRepositoryImpl,
        'normalize_algorithm_params',
        staticmethod(fake_normalize),
    )
    return calls


class _FakeDeviceManager:
    def __init__(self):
        self.post_extra_params = None
        self.pre_extra_params = None

    def setup_env_devices_for_round(self, algo_params, task_id):
        return {}

    def pre_process_devices(self, device_info_list, task_id, test_case_id=None, extra_params=None):
        self.pre_extra_params = extra_params
        return True

    def post_process_devices(self, device_info_list, task_id, test_case_id=None, extra_params=None):
        self.post_extra_params = extra_params
        return False   # 后处理失败即短路返回，避免单测触达采集/评估链路

    def teardown_env_devices_for_round(self, env_states, task_id):
        return None


class _FakePlayback:
    def play_round(self, **_kwargs):
        return SimpleNamespace(audio_timelines=None)


class _Executor(RoundsLoopMixin):
    def __init__(self):
        self._device_manager = _FakeDeviceManager()
        self._logs = []
        self._playback_timestamps = {}
        self._audio_local_paths = {}
        self._collector = None

    def _log(self, level='INFO', content='', **kwargs):
        self._logs.append(content)

    def _handle_control(self, task_id):
        return None

    def _register_voiceprint(self, *a, **k):
        return None

    def _collect_playback_timestamps(self, task_id, play_result, case_config):
        self._playback_timestamps[task_id] = {}

    def _failed_round_data(self, round_idx, result_ids):
        return {}


def _round(number, is_reject=None, **extra):
    cfg = {'round_number': number, 'audios': [], **extra}
    if is_reject is not None:
        cfg['algorithm_params'] = [{'field_code': 'is_reject', 'field_value': is_reject}]
    return cfg


def _run_round(monkeypatch, rounds, round_idx, round_config=None):
    monkeypatch.setattr(loop_mod, 'PlaybackAclRepositoryImpl', _FakePlayback)
    executor = _Executor()
    executor._execute_single_round(
        'T1', 'TCREL', {}, {}, '用例', 'voice_llm', 101, rounds,
        [{'device_sn': 'SN', 'device_id': 1}], {1: 900}, {},
        round_idx, round_config or rounds[round_idx], round_idx + 1, {},
    )
    return executor._device_manager.post_extra_params


class TestExecutorNextRoundIsReject:
    def test_next_round_reject_injected(self, pure_normalizer, monkeypatch):
        rounds = [_round(1, is_reject=True), _round(2, is_reject=True)]
        params = _run_round(monkeypatch, rounds, 0)
        assert params['next_round_is_reject'] is True
        assert params['is_reject'] is True

    def test_next_round_non_reject_injected_false(self, pure_normalizer, monkeypatch):
        rounds = [_round(1, is_reject=True), _round(2, is_reject=False)]
        params = _run_round(monkeypatch, rounds, 0)
        assert params['next_round_is_reject'] is False

    def test_last_round_does_not_inject(self, pure_normalizer, monkeypatch):
        rounds = [_round(1, is_reject=True), _round(2, is_reject=True)]
        params = _run_round(monkeypatch, rounds, 1)
        assert 'next_round_is_reject' not in params

    def test_switch_forms_parsed(self):
        driver = _Executor()
        for truthy in (True, 1, 'true', '1', '是'):
            assert driver._as_switch_on(truthy) is True
        for falsy in (False, 0, 'false', '0', '', None, 'no'):
            assert driver._as_switch_on(falsy) is False

    def test_existing_control_fields_unchanged(self, pure_normalizer, monkeypatch):
        rounds = [
            _round(1, is_reject=True, isInterruption=True,
                   recordMode='case', aiStartTimeout=12),
            _round(2, is_reject=False),
        ]
        params = _run_round(monkeypatch, rounds, 0)
        assert params['is_interruption'] is True
        assert params['record_mode'] == 'case'
        assert params['ai_start_timeout'] == 12
        assert params['next_round_is_reject'] is False
