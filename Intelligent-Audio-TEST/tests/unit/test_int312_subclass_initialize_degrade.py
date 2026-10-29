# -*- coding: utf-8 -*-
"""INT-312 验收：explicit_degrade 降级覆盖自带 initialize 覆写的子类驱动。

审计遗留：INT-296 的降级仅对 HarmonyDriver 基类 initialize 生效；自带 initialize
覆写的子类驱动在 super().initialize() 之后直接 _get_driver() → None → return False，
行为等价 strict（fail-closed，无数据污染，仅降级语义失效）。

行为契约（审计点名 6 组驱动 × 两形态 × 两模式矩阵）：
1. 自定义 initialize（不调 super）驱动（DoubaoChat / ChatGptVoiceChat / 小艺慧记）：
   入口走 _initialize_ui_guard 统一分流——
   - explicit_degrade + UI 层不可用 → initialize 成功 + ui_capture_available=false
     + degrade_reason 结构化标记；hdc 步骤（force-stop / aa start / fwk 采集参数）不降级
   - strict + UI 层不可用 → 显式失败（INT-158 语义，状态保持无降级）
2. 链式 super().initialize() 驱动（Xiaoyilivechat v1 / V2 / 翻译三驱动）：
   super().initialize 成功后走 _resume_driver_after_super_initialize 只读降级结论——
   - explicit_degrade → 全链路返回成功 + 降级标记，UI 导航步骤显式跳过
   - strict → super().initialize 显式失败，子类透传失败
3. UI 层可用 → 子类照常执行全部步骤且 capabilities 不降级（resume 路径不误伤）
4. 单例跨用例：子类 strict 失败后降级标记无残留
5. 无隐式默认降级：默认配置（strict）下 UI 层不可用仍显式失败（INT-296 红线）
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.constants.ui_capture import UiCaptureDegradeReason
from device_service.infrastructure.drivers.harmony_xiaoyichat import Xiaoyilivechat
from device_service.infrastructure.drivers.harmony_xiaoyilivechat import XiaoyilivechatV2
from device_service.infrastructure.drivers.harmony_doubaochat import DoubaoChat
from device_service.infrastructure.drivers.harmony_chatgpt import ChatGptVoiceChat
from device_service.infrastructure.drivers.harmony_xiaoyihuiji_driver import (
    HarmonyHardenXiaoyiHuiJiDriver,
)
from device_service.infrastructure.drivers.harmony_translation_driver import (
    HarmonyXiaoyiTranslationDriver,
    XiaoyiFace2FaceDriver,
    XiaoyiSimultaneousInterpretationDriver,
)

HD = 'device_service.infrastructure.drivers.harmony_driver'
DOUBAO_MOD = 'device_service.infrastructure.drivers.harmony_doubaochat'
CHATGPT_MOD = 'device_service.infrastructure.drivers.harmony_chatgpt'
XIAOYICHAT_MOD = 'device_service.infrastructure.drivers.harmony_xiaoyichat'
HUIJI_LIFECYCLE_MOD = \
    'device_service.infrastructure.drivers.harmony_xiaoyihuiji_driver._lifecycle_mixin'
SN = '5SM0125613000197'


# --------------------------------------------------------------------------- #
#  驱动替身构造                                                                 #
# --------------------------------------------------------------------------- #

def _base_host(cls):
    """绕过真实 hdc/UiDriver/config 的最小驱动宿主（仿 INT-296 _make_driver）"""
    d = cls.__new__(cls)
    d._task_id = None
    d._test_case_id = None
    d._device_id = None
    d._mock_mode = False
    d._drivers = {}
    d._close_buttons = []
    d._popup_keywords = []
    d.ui_capture_available = True
    d.ui_degrade_reason = None
    d.logs = []
    d._log = lambda level='INFO', content='', **kw: d.logs.append((level, content))
    d._check_stop = lambda name='': False
    d._hdc_shell = MagicMock(return_value=SimpleNamespace(returncode=0, stdout='', stderr=''))
    return d


def _unavailable(reason_value):
    """UI 层不可用形态（_get_driver_for_initialize 生产返回口径：字符串 reason）"""
    return lambda sn: (None, reason_value)


def _make_v1():
    d = _base_host(Xiaoyilivechat)
    # hdc 采集链步骤打桩（非被测对象），只验证其在降级下仍被调用
    d._enable_dsp_audio_dump = MagicMock()
    d._clear_alarms = MagicMock()
    d._clear_pcm = MagicMock()
    d._clear_dsp_audio_hook = MagicMock()
    return d


def _make_doubao():
    return _base_host(DoubaoChat)


def _make_chatgpt():
    d = _base_host(ChatGptVoiceChat)
    d.app_name = 'com.openai.chat'
    return d


def _degrade_warning_logs(d):
    return [c for lv, c in d.logs if lv == 'WARNING' and 'UI 抓取层降级（explicit_degrade）' in c]


# --------------------------------------------------------------------------- #
#  Pattern B：自定义 initialize（不调 super）→ 入口统一分流                      #
# --------------------------------------------------------------------------- #

class TestCustomInitializeDrivers:

    # ---- DoubaoChat ----

    def test_doubao_degrade_succeeds_with_markers(self):
        d = _make_doubao()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'), \
             patch(f'{DOUBAO_MOD}.time.sleep'):
            assert d.initialize(SN, task_id='500') is True
        assert d.ui_capture_available is False
        assert d.ui_degrade_reason == UiCaptureDegradeReason.HYPIUM_MISSING.value
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}

    def test_doubao_degrade_keeps_hdc_capture_chain(self):
        """降级不连带采集链：残留强停/aa start/fwk 采集参数全走 hdc 直连"""
        d = _make_doubao()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'), \
             patch(f'{DOUBAO_MOD}.time.sleep'):
            assert d.initialize(SN, task_id='500') is True
        arg_list = [c.args for c in d._hdc_shell.call_args_list]
        assert (SN, 'aa', 'start', '-b', DoubaoChat.DOUBAO_BUNDLE,
                '-a', DoubaoChat.DOUBAO_ABILITY) in arg_list
        assert (SN, 'aa', 'force-stop', DoubaoChat.DOUBAO_BUNDLE) in arg_list
        assert (SN, 'param set sys.audio.dump.writeserver.enable w') in arg_list
        assert (SN, 'chmod 777 /data/local/tmp') in arg_list

    def test_doubao_degrade_daemon_unavailable_reason(self):
        d = _make_doubao()
        d._get_driver_for_initialize = _unavailable(
            UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'), \
             patch(f'{DOUBAO_MOD}.time.sleep'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities()['degrade_reason'] == 'uitest_daemon_unavailable'

    def test_doubao_strict_fails(self):
        d = _make_doubao()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        # strict 失败不得携带降级标记（INT-158 语义保持）
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}
        assert d._hdc_shell.call_args_list == []

    # ---- ChatGptVoiceChat ----

    def test_chatgpt_degrade_succeeds_with_markers(self):
        d = _make_chatgpt()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'), \
             patch(f'{CHATGPT_MOD}.time.sleep'):
            assert d.initialize(SN, task_id='500') is True
        assert d.ui_capture_available is False
        assert d.ui_degrade_reason == 'hypium_missing'
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        # aa start ChatGPT（hdc）在降级下照常执行
        arg_list = [c.args for c in d._hdc_shell.call_args_list]
        assert (SN, 'aa', 'start', '-b', d.app_name,
                '-a', f'{d.app_name}.MainActivity') in arg_list

    def test_chatgpt_strict_fails(self):
        d = _make_chatgpt()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    # ---- 小艺慧记 ----

    def test_huiji_degrade_succeeds_with_markers(self):
        d = _base_host(HarmonyHardenXiaoyiHuiJiDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'), \
             patch(f'{HUIJI_LIFECYCLE_MOD}.subprocess.run',
                   return_value=SimpleNamespace(stdout='ok')):
            assert d.initialize(SN, task_id='500') is True
        assert d.ui_capture_available is False
        assert d.ui_degrade_reason == 'hypium_missing'
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        # UI 导航步骤显式跳过留痕
        assert _degrade_warning_logs(d)

    def test_huiji_strict_fails(self):
        d = _base_host(HarmonyHardenXiaoyiHuiJiDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}


# --------------------------------------------------------------------------- #
#  Pattern A：链式 super().initialize() → 只读降级结论                          #
# --------------------------------------------------------------------------- #

class TestChainedInitializeDrivers:

    # ---- Xiaoyilivechat v1 ----

    def test_v1_degrade_succeeds_with_markers(self):
        d = _make_v1()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.ui_capture_available is False
        assert d.ui_degrade_reason == 'hypium_missing'
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        # hdc 采集链步骤（DSP dump / 清闹钟 / 清 pcm）不随 UI 层降级
        d._enable_dsp_audio_dump.assert_called_once()
        d._clear_alarms.assert_called_once()
        d._clear_pcm.assert_called_once()
        # UI 步骤显式跳过留痕
        assert _degrade_warning_logs(d)

    def test_v1_degrade_daemon_unavailable_reason(self):
        d = _make_v1()
        d._get_driver_for_initialize = _unavailable(
            UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities()['degrade_reason'] == 'uitest_daemon_unavailable'

    def test_v1_strict_fails(self):
        d = _make_v1()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}
        d._enable_dsp_audio_dump.assert_not_called()

    def test_v1_pre_process_degade_explicit_fail(self):
        """UI 层降级时 pre_process 显式失败（通话 live 态 UI 控制步骤不可跳过）

        降级路径 driver=None 时 pre_process 不得崩溃（AttributeError），须在 UI 控制
        步骤前显式失败并留痕降级原因；hdc 采集链步骤（清闹钟/清 pcm/清 audio_hook）
        不随 UI 层降级，照常执行。
        """
        d = _make_v1()
        d._get_driver = lambda sn: None
        d.ui_capture_available = False
        d.ui_degrade_reason = UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value
        assert d.pre_process(SN, task_id='500') is False
        err = [c for lv, c in d.logs if lv == 'ERROR' and '显式失败' in c]
        assert err and 'uitest_daemon_unavailable' in err[0]
        # hdc 采集链不随 UI 层降级
        d._clear_alarms.assert_called_once()
        d._clear_pcm.assert_called_once()
        d._clear_dsp_audio_hook.assert_called_once()

    # ---- XiaoyilivechatV2 ----

    def test_v2_degrade_succeeds_with_markers(self):
        d = _base_host(XiaoyilivechatV2)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        assert _degrade_warning_logs(d)

    def test_v2_strict_fails(self):
        d = _base_host(XiaoyilivechatV2)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    # ---- 翻译三驱动（链式两级 super）----

    def test_translation_base_degrade_succeeds_with_markers(self):
        d = _base_host(HarmonyXiaoyiTranslationDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        assert _degrade_warning_logs(d)

    def test_translation_base_strict_fails(self):
        d = _base_host(HarmonyXiaoyiTranslationDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    def test_face2face_degrade_full_chain_markers(self):
        """两级 super 链路（face2face → 翻译基类 → HarmonyDriver）降级结论只读透传"""
        d = _base_host(XiaoyiFace2FaceDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        assert _degrade_warning_logs(d)

    def test_face2face_strict_fails(self):
        d = _base_host(XiaoyiFace2FaceDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    def test_simultaneous_degrade_full_chain_markers(self):
        d = _base_host(XiaoyiSimultaneousInterpretationDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities() == {'ui_capture_available': False,
                                           'degrade_reason': 'hypium_missing'}
        assert _degrade_warning_logs(d)

    def test_simultaneous_strict_fails(self):
        d = _base_host(XiaoyiSimultaneousInterpretationDriver)
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}


# --------------------------------------------------------------------------- #
#  防回退与红线                                                                  #
# --------------------------------------------------------------------------- #

class TestResumePathNoRegression:

    def test_v1_ui_available_resume_runs_full_flow(self):
        """UI 层可用：resume 返回真实 driver，子类照常执行全部步骤且不降级"""
        d = _make_v1()
        fake_ui = MagicMock()
        # 图标存在（桌面已就绪）：小艺只能靠点图标启动
        fake_ui.find_component.return_value = MagicMock()
        d._get_driver_for_initialize = lambda sn: (fake_ui, None)
        d._get_driver = MagicMock(return_value=fake_ui)
        d.app_name = 'x'
        d.app_icon_key = 'k'
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'), \
             patch(f'{HD}.subprocess.run'), \
             patch(f'{HD}.time.sleep'), \
             patch(f'{HD}.By', MagicMock()), \
             patch(f'{XIAOYICHAT_MOD}.By', MagicMock()):
            assert d.initialize(SN, task_id='500') is True
        # resume 深处的小艺 UI 步骤与采集链步骤都真实执行
        d._enable_dsp_audio_dump.assert_called_once()
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    def test_v1_degrade_state_reset_on_next_strict_initialize(self):
        """单例跨用例：降级成功后下一次 strict initialize 无标记残留"""
        d = _make_v1()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert d.initialize(SN) is True
        assert d.ui_capture_available is False
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert d.initialize(SN) is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}

    def test_default_mode_remains_strict_no_implicit_degrade(self):
        """红线：strict（默认）配置下 UI 层不可用必须显式失败，严禁隐式默认降级"""
        from device_service.config.config import Config
        from shared.constants.ui_capture import UiCaptureMode
        d = _make_doubao()
        d._get_driver_for_initialize = _unavailable(UiCaptureDegradeReason.HYPIUM_MISSING.value)
        # 显式钉住 strict 默认语义（不依赖进程环境）：服务 app.py 的 load_dotenv
        # 会把本机 .env 的 UI_CAPTURE_MODE=explicit_degrade 带进全量 pytest 进程，
        # Config 类属性在惰性首导时冻结该值（INT-296 test_default_mode_is_strict
        # 同受此影响，见交付评论）——本例验证的是 strict 语义本身，故显式钉住。
        with patch.object(Config, 'UI_CAPTURE_MODE', UiCaptureMode.STRICT.value):
            assert d.initialize(SN, task_id='500') is False
        assert d.get_ui_capabilities() == {'ui_capture_available': True, 'degrade_reason': None}
