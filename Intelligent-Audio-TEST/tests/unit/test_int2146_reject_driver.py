# -*- coding: utf-8 -*-
"""INT-2363 验收：小艺通话拒识轮驱动播放后 AI PCM RMS 回复检测（INT-2146 口径重写）。

覆盖（卡面可测验收标准 1~3）：
1. 注册可发现且不新增驱动（注册数保持 13）；timing 词表与显式 is_interruption 优先不变
2. 静默拒识轮播放后时序：input_gap_ms 0 不等待 / >0 切片等待并响应停止信号
3. AI PCM RMS 主路径三态：fresh 等说完（silence_seconds=0）/ ended 不再等 /
   none+remote 判未回复（置空问答、跳过提取、无 5s 冗余等待）
4. hw_params 降级：remote None 时 2s 窗口内 open 判已回复且结束等待封顶
   REJECT_REPLY_WAIT_TIMEOUT；窗口内未 open 判未回复直接收尾；不回退 UI
5. 基类两处形参默认值回归：silence_seconds=None 用模块常量（8s）；
   reply_detected=None 仍自行检测
6. 执行器不再注入 next_round_is_reject（下一轮是否拒识不影响等待）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import time

import pytest

from device_service.infrastructure.drivers.harmony_xiaoyichat import Xiaoyilivechat
from device_service.infrastructure.drivers.harmony_xiaoyi_reject import (
    XiaoyiLivechatReject,
)
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers import harmony_xiaoyi_reject as reject_mod
from device_service.infrastructure.drivers import harmony_xiaoyichat as xiaoyichat_mod


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


@pytest.fixture
def super_capture(monkeypatch):
    """拦截基类 post_process（记录收到的 kwargs），避免跑真实收尾 UI/录屏流程。"""
    captured = {}

    def fake_base(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(Xiaoyilivechat, 'post_process', fake_base)
    return captured


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

    def test_driver_count_unchanged(self):
        """注册表总数：INT-2146 后为 13，INT-2402 新增豆包拒识驱动后为 14。"""
        from device_service.infrastructure.drivers.registry import driver_registry
        assert len(driver_registry.list_drivers()) == 14


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


# ──────────────────────────── 3. post_process 路由 ────────────────────────────

class TestRejectPostProcess:
    @pytest.mark.parametrize('is_reject', [None, '', 'false', '0', False, 0])
    def test_non_reject_round_goes_straight_to_base(self, super_capture, is_reject):
        driver = _make_reject_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        kwargs = {'timing': 'silence'}
        if is_reject is not None:
            kwargs['is_reject'] = is_reject
        assert driver.post_process('SN', **kwargs) is True
        assert detects == [], 'is_reject 缺省/假值不得进入拒识分支'
        assert 'reply_detected' not in super_capture, '非拒识轮不得改变基类判定'
        assert 'skip_reply_wait' not in super_capture, '非拒识轮不得改变基类等待行为'

    def test_explicit_interruption_skips_detection_and_keeps_kwargs(self, super_capture):
        driver = _make_reject_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        kwargs = {'is_reject': True, 'timing': 'silence', 'is_interruption': True}
        assert driver.post_process('SN', **kwargs) is True
        assert detects == [], '显式打断型不做回复检测'
        # 任何情况下不改写 kwargs 的 is_interruption（打断族评估轮次口径）
        assert kwargs['is_interruption'] is True
        assert super_capture['is_interruption'] is True
        assert super_capture['skip_reply_wait'] is True
        assert 'reply_detected' not in super_capture

    def test_timing_derived_interruption_skips_detection(self, super_capture):
        driver = _make_reject_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        assert driver.post_process('SN', is_reject=True, timing='回复过程中') is True
        assert detects == [], '由 timing 推出的打断型不等待'
        assert 'is_interruption' not in super_capture, 'timing 推导值不得回写进 kwargs'
        assert super_capture['skip_reply_wait'] is True

    def test_silent_reject_passes_reply_detected_to_base(self, super_capture):
        driver = _make_reject_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: True
        assert driver.post_process('SN', is_reject=True, timing='静默') is True
        assert super_capture['reply_detected'] is True
        assert 'skip_reply_wait' not in super_capture, \
            'skip_reply_wait 会强制 replied=True，不能用来传判定结果'

    def test_unreplied_result_passed_to_base_as_false(self, super_capture):
        driver = _make_reject_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: False
        assert driver.post_process('SN', is_reject=True, timing='silence') is True
        assert super_capture['reply_detected'] is False

    def test_stop_signal_aborts_without_base_post_process(self, super_capture):
        driver = _make_reject_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: None
        assert driver.post_process('SN', is_reject=True, timing='silence') is True
        assert super_capture == {}, '停止信号应直接收敛，不再走收尾'
        assert any('停止信号' in m for m in _messages(driver, 'INFO'))

    def test_next_round_is_reject_no_longer_affects_wait(self, super_capture):
        """INT-2363：不再依赖下一轮 timing，注入值既不等待也不跳过。"""
        driver = _make_reject_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        for value in (True, False, 'true'):
            detects.clear()
            assert driver.post_process(
                'SN', is_reject=True, timing='silence',
                next_round_is_reject=value) is True
            assert detects == [1], '下一轮是否拒识不再影响本轮检测'
            assert super_capture['reply_detected'] is True


# ──────────────────────────── 4. input_gap_ms 播放后时序 ────────────────────────────

class TestInputGap:
    @pytest.mark.parametrize('gap', [None, '', 0, '0', 'abc', -5])
    def test_zero_or_invalid_gap_never_waits(self, gap):
        driver = _make_reject_driver()
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': gap}) is True
        assert time.time() - start < 0.2, '缺省/非正值不得等待'

    def test_invalid_gap_warns(self):
        driver = _make_reject_driver()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 'abc'}) is True
        assert any('非法' in m for m in _messages(driver, 'WARNING'))

    def test_positive_gap_waits_sliced(self):
        driver = _make_reject_driver()
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 600}) is True
        elapsed = time.time() - start
        assert elapsed >= 0.5, f'>0 应等待约 0.6s，实际 {elapsed:.2f}s'
        assert elapsed < 2.0

    def test_positive_gap_responds_to_stop_signal(self):
        driver = _make_reject_driver(_check_stop=lambda *a, **k: True)
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 3000}) is False
        assert time.time() - start < 0.5, '停止信号应中断切片等待'

    def test_gap_runs_before_reply_detection(self):
        """播放后时序：先 input_gap，再 AI PCM RMS 检测。"""
        driver = _make_reject_driver()
        order = []
        driver._wait_input_gap_after = lambda *a, **k: order.append('gap') or True
        driver._wait_ai_reply_start_via_pcm = (
            lambda *a, **k: order.append('rms_start') or ('ended', '/pcm'))
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert order == ['gap', 'rms_start']


# ──────────────────────────── 5. AI PCM RMS 主检测三态 ────────────────────────────

class TestPcmReplyDetection:
    def _driver(self, status, remote, **attrs):
        driver = _make_reject_driver(**attrs)
        driver._wait_ai_reply_start_via_pcm = lambda *a, **k: (status, remote)
        driver._end_calls = []

        def fake_end(*a, **k):
            driver._end_calls.append(k)
            return k.get('silence_seconds') == 0
        driver._wait_ai_reply_end_via_pcm = fake_end
        return driver

    def test_fresh_waits_for_end_with_zero_silence(self):
        driver = self._driver('fresh', '/pcm')
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert len(driver._end_calls) == 1
        assert driver._end_calls[0].get('silence_seconds') == 0, \
            'fresh 必须等说完且 silence_seconds=0'

    def test_ended_does_not_wait(self):
        driver = self._driver('ended', '/pcm')
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert driver._end_calls == [], 'ended（回复已结束）不再等'

    def test_none_with_remote_means_not_replied_and_skips_extraction(self):
        driver = self._driver('none', '/pcm')
        start = time.time()
        assert driver._detect_silent_reject_reply('SN', {}) is False
        assert time.time() - start < 0.5, '未回复路径不得有 5s 冗余等待'
        assert driver.question_text == '小艺识别为空'
        assert driver.answer_text == '小艺回复为空'
        assert driver._end_calls == [], '未回复不做结束等待'
        assert any('未回复' in m for m in _messages(driver, 'INFO'))


# ──────────────────────────── 6. hw_params 降级（remote 不可得） ────────────────────────────

class TestHwParamsFallback:
    def _driver(self, replying, **attrs):
        driver = _make_reject_driver(**attrs)
        driver._wait_ai_reply_start_via_pcm = lambda *a, **k: ('none', None)
        driver._hw_params_replying = lambda sn: replying
        driver._end_calls = []

        def fake_end(*a, **k):
            driver._end_calls.append(k)
            return True
        driver._wait_ai_reply_end_via_hw_params = fake_end
        return driver

    def test_open_within_window_means_replied_and_capped(self):
        driver = self._driver(True)
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert len(driver._end_calls) == 1
        assert driver._end_calls[0].get('timeout') == reject_mod.REJECT_REPLY_WAIT_TIMEOUT, \
            '结束等待必须封顶 REJECT_REPLY_WAIT_TIMEOUT，不复用 300s'
        assert 'hw_params 降级' in ' '.join(_messages(driver, 'INFO'))

    def test_not_open_within_window_means_not_replied_immediately(
            self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_SILENT_NO_REPLY_SECONDS', 0.12)
        driver = self._driver(False)
        driver.REJECT_REPLY_POLL_INTERVAL = 0.02
        start = time.time()
        assert driver._detect_silent_reject_reply('SN', {}) is False
        assert time.time() - start < 0.6, '窗口内未 open 应直接收尾，不追加等待'
        assert driver._end_calls == []
        assert driver.question_text == '小艺识别为空'
        assert driver.answer_text == '小艺回复为空'

    def test_fallback_never_falls_back_to_ui(self):
        """降级路径只读 hw_params，不得 find_component。"""
        ui_calls = []

        class _Ui:
            def find_component(self, selector):
                ui_calls.append(selector)
                return object()

        driver = self._driver(True, _get_driver=lambda sn: _Ui())
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert ui_calls == [], '任何情况下不回退 UI 判定'

    def test_stop_signal_during_fallback_window(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_SILENT_NO_REPLY_SECONDS', 0.5)
        driver = self._driver(False, _check_stop=lambda *a, **k: True)
        driver.REJECT_REPLY_POLL_INTERVAL = 0.02
        assert driver._detect_silent_reject_reply('SN', {}) is None


# ──────────────────────────── 7. 基类形参默认值回归 ────────────────────────────

def _make_base_driver():
    """构造基类实例（__new__ 绕过 __init__），只桩掉日志/停止/取流。"""
    driver = Xiaoyilivechat.__new__(Xiaoyilivechat)
    driver._logs = []
    driver._log = lambda **kw: driver._logs.append(kw)
    driver._check_stop = lambda *a, **k: False
    driver._find_ai_pcm_remote = lambda *a, **k: '/pcm'
    calls = {'n': 0}

    def fake_rms(*a, **k):
        calls['n'] += 1
        return (1000, 100) if calls['n'] == 1 else (0, 100)
    driver._read_tail_rms = fake_rms
    return driver


class TestBaseDefaults:
    def test_pcm_end_default_uses_module_silence_constant(self, monkeypatch):
        """不传 silence_seconds 时用模块常量（此处压成 100s → 必然超时）。"""
        monkeypatch.setattr(xiaoyichat_mod, 'RMS_SILENCE_SECONDS', 100.0)
        monkeypatch.setattr(xiaoyichat_mod, 'RMS_END_TIMEOUT', 0.05)
        driver = _make_base_driver()
        assert driver._wait_ai_reply_end_via_pcm('SN', interval=0.01) is True
        assert any('超时' in m for m in _messages(driver, 'WARNING'))

    def test_pcm_end_explicit_zero_silence_ends_immediately(self, monkeypatch):
        monkeypatch.setattr(xiaoyichat_mod, 'RMS_SILENCE_SECONDS', 100.0)
        monkeypatch.setattr(xiaoyichat_mod, 'RMS_END_TIMEOUT', 5)
        driver = _make_base_driver()
        assert driver._wait_ai_reply_end_via_pcm(
            'SN', interval=0.01, silence_seconds=0) is True
        assert any('尾部静默 0s' in m for m in _messages(driver, 'INFO'))
        assert not any('超时' in m for m in _messages(driver, 'WARNING'))

    def _post_driver(self, monkeypatch):
        driver = Xiaoyilivechat.__new__(Xiaoyilivechat)
        driver._logs = []
        driver._log = lambda **kw: driver._logs.append(kw)
        driver._check_stop = lambda *a, **k: False
        driver._hw_params_replying = lambda sn: None
        driver._record_mode = 'round'
        driver._round_number = 0
        driver._total_rounds = 1
        driver._stop_recorder = lambda *a, **k: True
        detect = []
        driver._detect_ai_pcm_first_frame = lambda *a, **k: detect.append(1) or 123
        waits = []

        def fake_wait_for_condition(*a, **k):
            waits.append(k.get('operation_name'))
            return False
        driver._wait_for_condition = fake_wait_for_condition
        driver._detect_calls = detect
        driver._wait_calls = waits

        class _Ui:
            def __init__(self):
                self.find_all_calls = 0

            def find_component(self, selector):
                return None

            def find_all_components(self, selector):
                self.find_all_calls += 1
                return []

            def wait(self, seconds):
                pass

        ui = _Ui()
        driver._get_driver = lambda sn: ui
        monkeypatch.setattr(xiaoyichat_mod, 'EXTRA_LONG_WAIT', 0)
        return driver, ui

    def test_reply_detected_none_still_self_detects(self, monkeypatch):
        driver, ui = self._post_driver(monkeypatch)
        assert driver.post_process('SN') is True
        assert driver._detect_calls == [1], '缺省 None 必须仍走自行检测'
        assert driver._wait_calls, '缺省 None 必须走回复开始等待'
        assert driver.question_text == '小艺识别为空'
        assert ui.find_all_calls == 0, '未回复不得提取问答'

    def test_reply_detected_false_skips_detection_and_extraction(self, monkeypatch):
        driver, ui = self._post_driver(monkeypatch)
        assert driver.post_process('SN', reply_detected=False) is True
        assert driver._detect_calls == [], '子类已判未回复，不再自行检测'
        assert driver._wait_calls == []
        assert ui.find_all_calls == 0, '未回复不得提取问答'

    def test_reply_detected_true_skips_detection_but_extracts(self, monkeypatch):
        driver, ui = self._post_driver(monkeypatch)
        assert driver.post_process('SN', reply_detected=True) is True
        assert driver._detect_calls == [], '子类已判已回复，不再自行检测'
        assert ui.find_all_calls == 2, '已回复应提取问/答文本'


# ──────────────────────────── 8. 执行器不再注入 next_round_is_reject ────────────────────────────

from e2e_test_service.application.services.e2e_executor import (  # noqa: E402
    rounds_loop_mixin as loop_mod,
)
from e2e_test_service.application.services.e2e_executor.rounds_loop_mixin import (  # noqa: E402
    RoundsLoopMixin,
)


@pytest.fixture
def pure_normalizer(monkeypatch):
    """把算法参数规范化收敛为纯函数（本单测不连 algorithm_service gRPC）。"""
    def fake_normalize(algorithm_params=None):
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
    def __init__(self):
        class _Result:
            audio_timelines = None
        self._result = _Result()

    def play_round(self, **_kwargs):
        return self._result


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


class TestExecutorNoNextRoundInject:
    def test_next_round_reject_not_injected(self, pure_normalizer, monkeypatch):
        rounds = [_round(1, is_reject=True), _round(2, is_reject=True)]
        params = _run_round(monkeypatch, rounds, 0)
        assert 'next_round_is_reject' not in params
        assert params['is_reject'] is True, '本轮 is_reject 仍原样透传'

    def test_other_rounds_unaffected(self, pure_normalizer, monkeypatch):
        rounds = [_round(1, is_reject=True), _round(2, is_reject=False)]
        params = _run_round(monkeypatch, rounds, 0)
        assert 'next_round_is_reject' not in params
        rounds = [_round(1, is_reject=True), _round(2, is_reject=True)]
        params = _run_round(monkeypatch, rounds, 1)
        assert 'next_round_is_reject' not in params

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
        assert 'next_round_is_reject' not in params

    def test_helper_removed(self):
        assert not hasattr(_Executor(), '_next_round_is_reject')
