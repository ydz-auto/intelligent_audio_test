# -*- coding: utf-8 -*-
"""INT-2402 验收：豆包通话拒识驱动 DoubaoReject（V9.7.10 412037ea1 适配移植）。

覆盖卡面验收标准 1~6（真机拒识时序无法容器验证，只做单测级证明）：
1. 注册与解析：registry.resolve / factory.get_driver_for_device 命中，登记数 14，
   驱动文件位于 infrastructure/drivers 层且不依赖上层模块
2. timing 词表归一（英文/中文白名单、未知值 WARNING 按非打断型、显式 is_interruption 优先）
3. 静默拒识轮播放后时序：input_gap_ms 0 不等待 / >0 切片等待并响应停止信号
4. AI PCM RMS 三态：fresh 等说完（子类 RMS_SILENCE_SECONDS=0，不传基类不支持的
   silence_seconds）/ ended 不再等 / none+remote 判未回复（豆包空文案、跳过提取）
5. hw_params 降级轮询：窗口内 open 判已回复且结束等待封顶 REJECT_REPLY_WAIT_TIMEOUT；
   窗口内未 open 判未回复；不回退 UI
6. DoubaoChat.post_process 新增 reply_detected=None 的缺省回归：不传时仍自行检测，
   行为与改动前一致；非拒识轮/打断型拒识轮不改写 kwargs
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import inspect
import time

import pytest

from device_service.infrastructure.drivers.harmony_doubaochat import DoubaoChat
from device_service.infrastructure.drivers.harmony_doubaolivechat import DoubaoReject
from device_service.infrastructure.drivers.reject_timing import RejectTimingMixin
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers import harmony_doubaolivechat as reject_mod

KEYWORDS = 'harmony.doubao_reject.v1'


# ──────────────────────────── 公共构造 ────────────────────────────

def _make_driver(**attrs):
    """构造不依赖 hypium/真机的驱动实例（__new__ 绕过 __init__）。"""
    driver = DoubaoReject.__new__(DoubaoReject)
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
    """拦截 DoubaoChat.post_process（记录收到的 kwargs），避免跑真实收尾流程。"""
    captured = {}

    def fake_base(self, device_sn, task_id=None, test_case_id=None, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(DoubaoChat, 'post_process', fake_base)
    return captured


# ──────────────────────────── 1. 注册与解析 ────────────────────────────

class TestRegistration:
    def test_registry_entry_and_metadata(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        entry = driver_registry.get_by_key(
            'doubao_reject', 'v1', DevicePlatform.HARMONYOS)
        assert entry is not None, '豆包拒识驱动必须登记到注册表'
        cls = entry.driver_cls
        assert cls.keywords == KEYWORDS
        assert cls.display_name == '豆包通话拒识试验驱动'
        assert cls.platform == DevicePlatform.HARMONYOS
        assert cls.version == 'v1'
        assert cls.dependencies == ['hypium']
        # 复用豆包常规驱动基础设施 + 与小艺拒识驱动共用 timing 口径
        assert issubclass(cls, DoubaoChat)
        assert issubclass(cls, RejectTimingMixin)

    def test_registry_resolve_returns_class(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        assert driver_registry.resolve(
            'doubao_reject', 'v1', DevicePlatform.HARMONYOS) is DoubaoReject

    def test_factory_resolves_by_device_keywords(self):
        from device_service.infrastructure.drivers import driver_factory as factory_mod
        if not factory_mod._HYPium_AVAILABLE:
            pytest.skip('hypium 不可用：工厂不实例化 HarmonyOS 专用驱动'
                        '（注册表条目测试仍覆盖）')
        driver = factory_mod.device_driver_factory.get_driver_for_device(
            'HarmonyOS', keywords=KEYWORDS)
        assert isinstance(driver, DoubaoReject)

    def test_factory_keywords_include_doubao_reject(self):
        from device_service.infrastructure.drivers import driver_factory as factory_mod
        if not factory_mod._HYPium_AVAILABLE:
            pytest.skip('hypium 不可用：工厂不实例化 HarmonyOS 专用驱动')
        keywords = [e['keywords'] for e in factory_mod.DeviceDriverFactory().get_registered_keywords()]
        assert KEYWORDS in keywords

    def test_driver_count_is_14(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        drivers = driver_registry.list_drivers()
        assert len(drivers) == 14, f'登记驱动数={len(drivers)}，期望 14'
        assert any(d['app_type'] == 'doubao_reject' for d in drivers)

    def test_driver_module_stays_in_infrastructure_layer(self):
        """驱动落点在 infrastructure/drivers，无 application/interfaces/gateway 依赖。"""
        assert DoubaoReject.__module__ == (
            'device_service.infrastructure.drivers.harmony_doubaolivechat')
        source = inspect.getsource(reject_mod)
        for forbidden in ('device_service.application', 'device_service.interfaces',
                          'api_gateway', 'e2e_test_service'):
            assert forbidden not in source, f'驱动不得依赖上层模块: {forbidden}'


# ──────────────────────────── 2. timing 词表归一 ────────────────────────────

class TestTimingMapping:
    @pytest.mark.parametrize('timing', ['response', 'Response', ' RESPONSE ', '回复过程中', ' 回复过程中 '])
    def test_interruption_timing_values(self, timing):
        driver = _make_driver()
        assert driver._resolve_timing_is_interruption(timing) is True
        assert _messages(driver, 'WARNING') == []

    @pytest.mark.parametrize('timing', ['silence', 'Silence', '静默', '', None, '  '])
    def test_non_interruption_timing_values(self, timing):
        driver = _make_driver()
        assert driver._resolve_timing_is_interruption(timing) is False
        assert _messages(driver, 'WARNING') == []

    def test_unknown_timing_warns_and_is_non_interruption(self):
        driver = _make_driver()
        assert driver._resolve_timing_is_interruption('一直听') is False
        warnings = _messages(driver, 'WARNING')
        assert len(warnings) == 1 and '未知' in warnings[0]

    def test_explicit_is_interruption_wins_over_timing(self):
        driver = _make_driver()
        assert driver._effective_is_interruption(
            {'is_interruption': True, 'timing': 'silence'}) is True
        assert driver._effective_is_interruption(
            {'is_interruption': 'false', 'timing': '回复过程中'}) is False

    def test_vocabulary_shared_with_xiaoyi_reject_driver(self):
        """两个拒识驱动共用同一份词表对象，不产生第三份口径。"""
        from device_service.infrastructure.drivers.harmony_xiaoyi_reject import (
            XiaoyiLivechatReject,
        )
        assert (DoubaoReject.INTERRUPTION_TIMING_VALUES
                is XiaoyiLivechatReject.INTERRUPTION_TIMING_VALUES)
        assert (DoubaoReject.NON_INTERRUPTION_TIMING_VALUES
                is XiaoyiLivechatReject.NON_INTERRUPTION_TIMING_VALUES)
        assert DoubaoReject._resolve_timing_is_interruption is \
            RejectTimingMixin._resolve_timing_is_interruption


# ──────────────────────────── 3. post_process 路由 ────────────────────────────

class TestRejectPostProcess:
    @pytest.mark.parametrize('is_reject', [None, '', 'false', '0', False, 0])
    def test_non_reject_round_goes_straight_to_base(self, super_capture, is_reject):
        driver = _make_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        kwargs = {'timing': 'silence'}
        if is_reject is not None:
            kwargs['is_reject'] = is_reject
        assert driver.post_process('SN', **kwargs) is True
        assert detects == [], 'is_reject 缺省/假值不得进入拒识分支'
        assert 'reply_detected' not in super_capture, '非拒识轮不得改变基类判定'

    def test_explicit_interruption_skips_detection_and_keeps_kwargs(self, super_capture):
        driver = _make_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        kwargs = {'is_reject': True, 'timing': 'silence', 'is_interruption': True}
        assert driver.post_process('SN', **kwargs) is True
        assert detects == [], '显式打断型不做回复检测'
        # 任何情况下不改写 kwargs 的 is_interruption（打断族评估轮次口径）
        assert kwargs['is_interruption'] is True
        assert super_capture['is_interruption'] is True
        assert 'reply_detected' not in super_capture

    def test_timing_derived_interruption_skips_detection(self, super_capture):
        driver = _make_driver()
        detects = []
        driver._detect_silent_reject_reply = lambda *a, **k: detects.append(1) or True
        assert driver.post_process('SN', is_reject=True, timing='回复过程中') is True
        assert detects == [], '由 timing 推出的打断型不等待'
        assert 'is_interruption' not in super_capture, 'timing 推导值不得回写进 kwargs'
        assert 'reply_detected' not in super_capture

    def test_silent_reject_passes_reply_detected_to_base(self, super_capture):
        driver = _make_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: True
        assert driver.post_process('SN', is_reject=True, timing='静默') is True
        assert super_capture['reply_detected'] is True

    def test_unreplied_result_passed_to_base_as_false(self, super_capture):
        driver = _make_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: False
        assert driver.post_process('SN', is_reject=True, timing='silence') is True
        assert super_capture['reply_detected'] is False

    def test_stop_signal_aborts_without_base_post_process(self, super_capture):
        driver = _make_driver()
        driver._detect_silent_reject_reply = lambda *a, **k: None
        assert driver.post_process('SN', is_reject=True, timing='silence') is True
        assert super_capture == {}, '停止信号应直接收敛，不再走收尾'
        assert any('停止信号' in m for m in _messages(driver, 'INFO'))


# ──────────────────────────── 4. input_gap_ms 播放后时序 ────────────────────────────

class TestInputGap:
    @pytest.mark.parametrize('gap', [None, '', 0, '0', 'abc', -5])
    def test_zero_or_invalid_gap_never_waits(self, gap):
        driver = _make_driver()
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': gap}) is True
        assert time.time() - start < 0.2, '缺省/非正值不得等待'

    def test_invalid_gap_warns(self):
        driver = _make_driver()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 'abc'}) is True
        assert any('非法' in m for m in _messages(driver, 'WARNING'))

    def test_positive_gap_waits_sliced(self):
        driver = _make_driver()
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 600}) is True
        elapsed = time.time() - start
        assert elapsed >= 0.5, f'>0 应等待约 0.6s，实际 {elapsed:.2f}s'
        assert elapsed < 2.0

    def test_positive_gap_responds_to_stop_signal(self):
        driver = _make_driver(_check_stop=lambda *a, **k: True)
        start = time.time()
        assert driver._wait_input_gap_after('SN', {'input_gap_ms': 3000}) is False
        assert time.time() - start < 0.5, '停止信号应中断切片等待'

    def test_gap_runs_before_reply_detection(self):
        """播放后时序：先 input_gap，再 AI PCM RMS 检测。"""
        driver = _make_driver()
        order = []
        driver._wait_input_gap_after = lambda *a, **k: order.append('gap') or True
        driver._wait_ai_reply_start_via_pcm = (
            lambda *a, **k: order.append('rms_start') or ('ended', '/pcm'))
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert order == ['gap', 'rms_start']


# ──────────────────────────── 5. AI PCM RMS 主检测三态 ────────────────────────────

class TestPcmReplyDetection:
    def _driver(self, status, remote, **attrs):
        driver = _make_driver(**attrs)
        driver._wait_ai_reply_start_via_pcm = lambda *a, **k: (status, remote)
        driver._end_calls = []

        def fake_end(*a, **k):
            driver._end_calls.append(k)
            return True
        driver._wait_ai_reply_end_via_pcm = fake_end
        return driver

    def test_silence_seconds_zero_via_subclass_attribute(self):
        """DoubaoChat 覆写的 end 方法无 silence_seconds 形参 → 子类类属性为 0。"""
        assert DoubaoReject.RMS_SILENCE_SECONDS == 0
        assert DoubaoChat.RMS_SILENCE_SECONDS == 8

    def test_fresh_waits_for_end_without_silence_seconds_kwarg(self):
        driver = self._driver('fresh', '/pcm')
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert len(driver._end_calls) == 1, 'fresh 必须等说完'
        assert 'silence_seconds' not in driver._end_calls[0], \
            '基类覆写无该形参，必须由子类类属性 RMS_SILENCE_SECONDS=0 生效'

    def test_ended_does_not_wait(self):
        driver = self._driver('ended', '/pcm')
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert driver._end_calls == [], 'ended（回复已结束）不再等'

    def test_none_with_remote_means_not_replied_and_skips_extraction(self):
        driver = self._driver('none', '/pcm')
        start = time.time()
        assert driver._detect_silent_reject_reply('SN', {}) is False
        assert time.time() - start < 0.5, '未回复路径不得有 5s 冗余等待'
        assert driver.question_text == '豆包识别为空'
        assert driver.answer_text == '豆包回复为空'
        assert driver._end_calls == [], '未回复不做结束等待'
        assert any('未回复' in m for m in _messages(driver, 'INFO'))


# ──────────────────────────── 6. hw_params 降级（remote 不可得） ────────────────────────────

class TestHwParamsFallback:
    def _driver(self, states, **attrs):
        """states: 依次返回的 _hw_params_replying 结果（用尽后保持最后一个）。"""
        driver = _make_driver(**attrs)
        driver._wait_ai_reply_start_via_pcm = lambda *a, **k: ('none', None)
        calls = {'n': 0}

        def fake_replying(sn):
            idx = min(calls['n'], len(states) - 1)
            calls['n'] += 1
            return states[idx]
        driver._hw_params_replying = fake_replying
        driver._poll_calls = calls
        driver._end_calls = []

        def fake_end(*a, **k):
            driver._end_calls.append(k)
            return True
        driver._wait_ai_reply_end_via_hw_params = fake_end
        return driver

    def test_open_within_window_means_replied_and_capped(self):
        driver = self._driver([True])
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert len(driver._end_calls) == 1
        assert driver._end_calls[0].get('timeout') == reject_mod.REJECT_REPLY_WAIT_TIMEOUT, \
            '结束等待必须封顶 REJECT_REPLY_WAIT_TIMEOUT，不复用 300s'
        assert 'hw_params 降级' in ' '.join(_messages(driver, 'INFO'))

    def test_polls_until_open_within_window(self, monkeypatch):
        """轮询时序：窗口内按 REJECT_REPLY_POLL_INTERVAL 反复探测，open 即判已回复。"""
        monkeypatch.setattr(reject_mod, 'REJECT_SILENT_NO_REPLY_SECONDS', 0.5)
        driver = self._driver([False, False, True])
        driver.REJECT_REPLY_POLL_INTERVAL = 0.02
        start = time.time()
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert time.time() - start < 0.5
        assert driver._poll_calls['n'] >= 3, '窗口内应轮询多次，open 后立即结束'

    def test_not_open_within_window_means_not_replied_immediately(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_SILENT_NO_REPLY_SECONDS', 0.12)
        driver = self._driver([False])
        driver.REJECT_REPLY_POLL_INTERVAL = 0.02
        start = time.time()
        assert driver._detect_silent_reject_reply('SN', {}) is False
        assert time.time() - start < 0.6, '窗口内未 open 应直接收尾，不追加等待'
        assert driver._end_calls == []
        assert driver.question_text == '豆包识别为空'
        assert driver.answer_text == '豆包回复为空'

    def test_fallback_never_falls_back_to_ui(self):
        """降级路径只读 hw_params，不得 find_component。"""
        ui_calls = []

        class _Ui:
            def find_component(self, selector):
                ui_calls.append(selector)
                return object()

        driver = self._driver([True], _get_driver=lambda sn: _Ui())
        assert driver._detect_silent_reject_reply('SN', {}) is True
        assert ui_calls == [], '任何情况下不回退 UI 判定'

    def test_stop_signal_during_fallback_window(self, monkeypatch):
        monkeypatch.setattr(reject_mod, 'REJECT_SILENT_NO_REPLY_SECONDS', 0.5)
        driver = self._driver([False], _check_stop=lambda *a, **k: True)
        driver.REJECT_REPLY_POLL_INTERVAL = 0.02
        assert driver._detect_silent_reject_reply('SN', {}) is None


# ──────────────────────────── 7. DoubaoChat.post_process reply_detected 回归 ────────────────────────────

def _make_doubao_chat():
    """构造豆包常规驱动实例（__new__ 绕过 __init__），case 模式中间轮早退避免真实等待。"""
    driver = DoubaoChat.__new__(DoubaoChat)
    driver._logs = []
    driver._log = lambda **kw: driver._logs.append(kw)
    driver._check_stop = lambda *a, **k: False
    driver._record_mode = 'case'
    driver._round_number = 0
    driver._total_rounds = 2          # 中间轮：不触发停录屏/挂断/提取
    driver._recording = True
    driver.question_text = None
    driver.answer_text = None
    driver._get_driver = lambda sn: object()
    driver._detect_calls = []
    driver._wait_calls = []
    driver._start_calls = []
    driver._detect_ai_pcm_first_frame = (
        lambda *a, **k: driver._detect_calls.append(1) or 123)

    def fake_wait_end(*a, **k):
        driver._wait_calls.append(k.get('silence_seconds'))
        return driver._wait_result
    driver._wait_result = True
    driver._wait_ai_reply_end_via_pcm = fake_wait_end

    def fake_wait_start(*a, **k):
        driver._start_calls.append(k.get('start_timeout'))
        return driver._interruption_status, None
    driver._interruption_status = 'none'
    driver._wait_ai_reply_start_via_pcm = fake_wait_start
    return driver


class TestDoubaoChatReplyDetectedRegression:
    def test_default_still_self_detects(self):
        """不传 reply_detected（改动前调用形态）：仍走首帧检测 + RMS 等结束。"""
        driver = _make_doubao_chat()
        assert driver.post_process('SN') is True
        assert driver._detect_calls == [1], '缺省 None 必须仍走自行检测'
        assert len(driver._wait_calls) == 1

    def test_default_not_replied_sets_empty_texts(self):
        """改动前「未回复」分支逐字保留：置豆包空文案后跳过问答提取。"""
        driver = _make_doubao_chat()
        driver._wait_result = False
        assert driver.post_process('SN') is True
        assert driver.question_text == '豆包识别为空'
        assert driver.answer_text == '豆包回复为空'

    def test_reply_detected_false_skips_detection_and_empty_texts(self):
        driver = _make_doubao_chat()
        assert driver.post_process('SN', reply_detected=False) is True
        assert driver._detect_calls == [], '子类已判未回复，不再自行检测'
        assert driver._wait_calls == []
        assert driver.question_text is None, '空文案由子类负责，基类不覆盖'
        assert driver.answer_text is None

    def test_reply_detected_true_skips_detection(self):
        driver = _make_doubao_chat()
        assert driver.post_process('SN', reply_detected=True) is True
        assert driver._detect_calls == []
        assert driver._wait_calls == []

    def test_interruption_takes_priority_over_reply_detected(self):
        """与 Xiaoyilivechat.post_process 口径一致：打断轮分支优先。"""
        driver = _make_doubao_chat()
        driver._interruption_status = 'none'
        assert driver.post_process('SN', is_interruption=True,
                                   reply_detected=True) is True
        assert len(driver._start_calls) == 1, '打断轮走 AI 开始回复检测'
        assert driver._wait_calls == [], '打断轮不等回复结束'
        assert driver.question_text == '豆包识别为空'
