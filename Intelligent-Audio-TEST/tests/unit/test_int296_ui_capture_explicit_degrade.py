# -*- coding: utf-8 -*-
"""INT-296 验收：E2E 物理链 UI 层显式降级。

行为契约：
1. 驱动侧（HarmonyDriver.initialize）× 两形态 × 两模式矩阵：
   - hypium 缺失形态（UiDriver=None，miniconda）+ explicit_degrade → 成功 +
     ui_capture_available=false + degrade_reason=hypium_missing
   - hypium 在、uitest 守护不可达形态（connect 失败）+ explicit_degrade → 成功 +
     degrade_reason=uitest_daemon_unavailable
   - strict（默认）两形态 → 显式失败（INT-158 语义保持，错误透传真因）
   - UI 层可用 → initialize 正常成功且 capabilities 不降级
   - 单例跨用例：reset_ui_capture_state 防降级标记残留
2. servicer 分流：initialize 成功响应 data.ui_capabilities 结构化透传；
   strict 失败响应不带降级标记
3. e2e 侧：initialize_devices 消费 ui_capabilities → executor 留痕；
   轮次记录 round_data.ui_capture = skipped/environment_excluded；
   TestResult.result_data.ui_capture_degraded 任务级留痕；
   无降级时无任何 ui_capture 字段（杜绝无痕跳过与误标记）
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.infrastructure.drivers.harmony_driver import HarmonyDriver
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer
from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager
from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor
from shared.constants.ui_capture import (
    UI_CAPTURE_MODE_VALUES,
    UiCaptureDegradeReason,
    UiCaptureMode,
    normalize_ui_capture_mode,
)

HD = 'device_service.infrastructure.drivers.harmony_driver'
FACTORY_TARGET = 'device_service.infrastructure.drivers.driver_factory.device_driver_factory'
SN = '5SM0125613000197'


# --------------------------------------------------------------------------- #
#  枚举与配置归一                                                               #
# --------------------------------------------------------------------------- #

class TestUiCaptureEnums:
    def test_mode_values(self):
        assert UI_CAPTURE_MODE_VALUES == ('strict', 'explicit_degrade')

    def test_degrade_reason_values(self):
        assert UiCaptureDegradeReason.HYPIUM_MISSING.value == 'hypium_missing'
        assert UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value == 'uitest_daemon_unavailable'

    def test_normalize_accepts_enum_and_str(self):
        assert normalize_ui_capture_mode(UiCaptureMode.STRICT) == 'strict'
        assert normalize_ui_capture_mode('explicit_degrade') == 'explicit_degrade'

    def test_normalize_rejects_illegal(self):
        with pytest.raises(ValueError, match='UI_CAPTURE_MODE'):
            normalize_ui_capture_mode('silent_skip')

    def test_default_mode_is_strict(self):
        from device_service.config.config import Config
        assert Config.UI_CAPTURE_MODE == UiCaptureMode.STRICT.value


# --------------------------------------------------------------------------- #
#  驱动侧：两形态 × 两模式矩阵                                                   #
# --------------------------------------------------------------------------- #

class _DegradableDriver(HarmonyDriver):
    """UI 层不可用形态的驱动替身（绕过真实 hdc/UiDriver 依赖）"""

    def __init__(self):
        self.logs = []
        self._task_id = None
        self._test_case_id = None
        self._drivers = {}
        self._config = {}
        self.app_name = 'x'
        self.app_icon_key = 'k'
        self.ui_capture_available = True
        self.ui_degrade_reason = None
        self.unlock_calls = 0

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))

    def unlock(self, device_sn, **kwargs):
        self.unlock_calls += 1

    def close_popups(self, device_sn):
        return True

    def _check_stop(self, name=''):
        return False


def _make_driver(hypium_present, connect_ok=True):
    """构造指定形态的驱动：hypium_present=False 模拟 miniconda（UiDriver=None）；
    connect_ok=False 模拟 hypium 在但 uitest 守护不可达"""
    driver = _DegradableDriver.__new__(_DegradableDriver)
    _DegradableDriver.__init__(driver)
    if not hypium_present:
        driver._get_driver_for_initialize = \
            lambda sn: (None, UiCaptureDegradeReason.HYPIUM_MISSING)
    else:
        if connect_ok:
            driver._get_driver_for_initialize = lambda sn: (MagicMock(), None)
        else:
            def _fail(sn):
                driver.logs.append(('ERROR', f'Failed to connect to Harmony device {sn}: rpc down'))
                return None, UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE
            driver._get_driver_for_initialize = _fail
    return driver


class TestDriverInitializeMatrix:

    # ---- 形态 1：miniconda（无 hypium，UiDriver=None 短路）----

    def test_hypium_missing_explicit_degrade_succeeds(self):
        driver = _make_driver(hypium_present=False)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert driver.initialize(SN, task_id='500') is True
        assert driver.ui_capture_available is False
        assert driver.ui_degrade_reason == UiCaptureDegradeReason.HYPIUM_MISSING.value
        caps = driver.get_ui_capabilities()
        assert caps == {'ui_capture_available': False,
                        'degrade_reason': 'hypium_missing'}

    def test_hypium_missing_strict_fails(self):
        driver = _make_driver(hypium_present=False)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert driver.initialize(SN, task_id='500') is False
        # strict 失败不得携带降级标记（INT-158 语义保持）
        assert driver.get_ui_capabilities()['ui_capture_available'] is True

    # ---- 形态 2：conda env（hypium 在、uitest 守护不可达）----

    def test_daemon_unavailable_explicit_degrade_succeeds(self):
        driver = _make_driver(hypium_present=True, connect_ok=False)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert driver.initialize(SN, task_id='500') is True
        assert driver.ui_capture_available is False
        assert driver.ui_degrade_reason == UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value
        assert driver.get_ui_capabilities()['degrade_reason'] == 'uitest_daemon_unavailable'

    def test_daemon_unavailable_strict_fails_with_reason(self):
        driver = _make_driver(hypium_present=True, connect_ok=False)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert driver.initialize(SN, task_id='500') is False
        warn = [c for lv, c in driver.logs if lv == 'ERROR' and 'UI 抓取层不可用' in c]
        assert warn and 'uitest_daemon_unavailable' in warn[0]
        # strict 失败状态不得携带降级标记
        assert driver.get_ui_capabilities() == {'ui_capture_available': True,
                                                'degrade_reason': None}

    # ---- UI 层可用：任何模式都正常成功且不降级 ----

    def test_ui_available_succeeds_without_degrade(self):
        driver = _make_driver(hypium_present=True, connect_ok=True)
        driver.unlock = MagicMock()
        driver.close_popups = MagicMock()
        fake_ui = MagicMock()
        fake_ui.find_component.return_value = None
        driver._connect_ui_driver = MagicMock(return_value=fake_ui)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'), \
             patch(f'{HD}.subprocess.run'), \
             patch(f'{HD}.time.sleep'), \
             patch(f'{HD}.By', MagicMock()):
            assert driver.initialize(SN, task_id='500') is True
        caps = driver.get_ui_capabilities()
        assert caps == {'ui_capture_available': True, 'degrade_reason': None}

    # ---- 单例跨用例残留防护 ----

    def test_degrade_state_reset_on_each_initialize(self):
        driver = _make_driver(hypium_present=False)
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='explicit_degrade'):
            assert driver.initialize(SN) is True
        assert driver.ui_capture_available is False
        # 第二次 initialize（同单例）入口先重置再判定
        with patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'):
            assert driver.initialize(SN) is False
        assert driver.get_ui_capabilities()['ui_capture_available'] is True
        assert driver.get_ui_capabilities()['degrade_reason'] is None


# --------------------------------------------------------------------------- #
#  RPC 守护自愈（V9.7.10 语义回归）                                             #
# --------------------------------------------------------------------------- #

class TestRpcSelfHealOnInitialize:
    """RPC 守护不可达时先自愈（重启守护+重连），自愈失败才按模式分流

    回归背景：V9.7.31 重构把 _connect_ui_driver 的 RPC 异常吞成 None，导致
    @with_rpc_retry 永远收不到异常、守护自愈能力丢失（V9.7.10 会 pkill +
    start-daemon + 重连后重试）。本类锁定恢复后的行为契约。
    """

    def _drv(self):
        d = _DegradableDriver.__new__(_DegradableDriver)
        _DegradableDriver.__init__(d)
        return d

    def test_connect_reraises_rpc_error(self):
        """RPC 类错误必须向上抛出，否则 with_rpc_retry 无法触发自愈"""
        d = self._drv()
        with patch(f'{HD}.UiDriver') as m:
            m.connect.side_effect = RuntimeError('UI RPC listening port is not found')
            with pytest.raises(RuntimeError):
                d._connect_ui_driver(SN)

    def test_connect_swallows_non_rpc_error(self):
        """非 RPC 异常仍按原语义返回 None（不改变既有容错口径）"""
        d = self._drv()
        with patch(f'{HD}.UiDriver') as m:
            m.connect.side_effect = ValueError('bad parameter')
            assert d._connect_ui_driver(SN) is None

    def test_initialize_recovers_rpc_then_returns_driver(self):
        """自愈成功：重启守护 + 重连后拿到驱动，不降级"""
        d = self._drv()
        fake = MagicMock()
        with patch(f'{HD}.UiDriver') as m, \
                patch(f'{HD}.restart_uitest_daemon', return_value=True) as restart:
            m.connect.side_effect = [
                RuntimeError('UI RPC listening port is not found'), fake,
            ]
            driver, reason = d._get_driver_for_initialize(SN)
        assert driver is fake
        assert reason is None
        restart.assert_called_once_with(SN)

    def test_initialize_downgrades_when_recovery_fails(self):
        """自愈失败：返回结构化降级原因，由 UI_CAPTURE_MODE 分流"""
        d = self._drv()
        with patch(f'{HD}.UiDriver') as m, \
                patch(f'{HD}.restart_uitest_daemon', return_value=False):
            m.connect.side_effect = RuntimeError('UI RPC listening port is not found')
            driver, reason = d._get_driver_for_initialize(SN)
        assert driver is None
        assert reason == UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value

    def test_initialize_self_heal_keeps_strict_success(self):
        """strict 模式下自愈成功 → initialize 显式成功（不再因守护抖动失败）"""
        d = self._drv()
        fake = MagicMock()
        # 图标存在（桌面已就绪）：小艺只能靠点图标启动
        fake.find_component.return_value = MagicMock()
        d.unlock = MagicMock()
        d.close_popups = MagicMock()
        with patch(f'{HD}.UiDriver') as m, \
                patch(f'{HD}.restart_uitest_daemon', return_value=True), \
                patch(f'{HD}.normalize_ui_capture_mode', return_value='strict'), \
                patch(f'{HD}.subprocess.run'), \
                patch(f'{HD}.time.sleep'), \
                patch(f'{HD}.By', MagicMock()):
            m.connect.side_effect = [
                RuntimeError('UI RPC listening port is not found'), fake,
            ]
            assert d.initialize(SN, task_id='500') is True
        assert d.get_ui_capabilities() == {'ui_capture_available': True,
                                           'degrade_reason': None}


# --------------------------------------------------------------------------- #
#  servicer：ui_capabilities 结构化透传                                          #
# --------------------------------------------------------------------------- #

def _req(cfg):
    return SimpleNamespace(device_config=json.dumps(cfg), task_id='500')


class TestServicerUiCapabilities:

    def _servicer(self, driver):
        factory = MagicMock()
        factory.get_driver_for_device.return_value = driver
        s = DeviceServiceServicer()
        return s, patch(FACTORY_TARGET, factory)

    @staticmethod
    def _req_cfg():
        return _req({'action': 'initialize', 'system': 'HarmonyOS',
                     'keywords': 'harmony.base.v1', 'device_sn': SN,
                     'device_info_list': [], 'kwargs': {}})

    def test_degraded_capabilities_passthrough(self):
        driver = MagicMock()
        driver.initialize.return_value = True
        driver.get_ui_capabilities.return_value = {
            'ui_capture_available': False, 'degrade_reason': 'hypium_missing'}
        s, p = self._servicer(driver)
        with p:
            resp = s.CreateDriver(self._req_cfg())
        assert resp.success is True
        caps = json.loads(resp.data)['ui_capabilities']
        assert caps == {'ui_capture_available': False, 'degrade_reason': 'hypium_missing'}

    def test_normal_capabilities_passthrough(self):
        driver = MagicMock()
        driver.initialize.return_value = True
        driver.get_ui_capabilities.return_value = {
            'ui_capture_available': True, 'degrade_reason': None}
        s, p = self._servicer(driver)
        with p:
            resp = s.CreateDriver(self._req_cfg())
        assert json.loads(resp.data)['ui_capabilities']['ui_capture_available'] is True

    def test_initialize_false_fails_without_degrade_marker(self):
        driver = MagicMock()
        driver.initialize.return_value = False
        s, p = self._servicer(driver)
        with p:
            resp = s.CreateDriver(self._req_cfg())
        assert resp.success is False
        assert 'initialize failed' in resp.message


# --------------------------------------------------------------------------- #
#  e2e 侧：降级留痕 + 轮次标记 + 无降级零侵入                                     #
# --------------------------------------------------------------------------- #

def _make_manager(initialize_driver):
    mgr = object.__new__(E2EDeviceManager)
    executor = SimpleNamespace(
        _playback_timestamps={},
        execution_engine=SimpleNamespace(device_control_pool=ThreadPoolExecutor(max_workers=2)),
        _log=lambda **kw: None,
        set_ui_capture_degraded=lambda degraded, **kw: None,
    )
    mgr._executor = executor
    mgr._device_repo = SimpleNamespace(initialize_driver=initialize_driver)
    return mgr


def _manager_with_executor(initialize_driver):
    """带 executor 留痕钩子的 manager（set_ui_capture_degraded 真实落 executor 状态）"""
    mgr = object.__new__(E2EDeviceManager)
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._ui_capture_degraded = None
    ex._ui_capture_degraded_note = None
    ex._log = MagicMock()
    executor = SimpleNamespace(
        _playback_timestamps={},
        execution_engine=SimpleNamespace(device_control_pool=ThreadPoolExecutor(max_workers=2)),
        _log=lambda **kw: None,
        set_ui_capture_degraded=ex.set_ui_capture_degraded,
    )
    # E2EDeviceManager 通过 self._executor 访问 executor；executor 自身方法绑定在 ex
    mgr._executor = executor
    mgr._device_repo = SimpleNamespace(initialize_driver=initialize_driver)
    return mgr, ex


DEVICES = [{'device_sn': SN, 'device_name': 'd9', 'system': 'HarmonyOS',
            'keywords': 'harmony.base.v1'}]


class TestE2eInitializeConsumesCapabilities:

    def test_no_degrade_no_marker(self):
        repo = MagicMock(return_value={'ui_capabilities': {
            'ui_capture_available': True, 'degrade_reason': None}})
        mgr = _make_manager(repo)
        mgr.initialize_devices(DEVICES, task_id=500, test_case_id='c1')
        assert mgr.get_ui_capture_degraded() is None
        assert repo.call_args[0][1][0]['action'] == 'initialize'

    def test_degraded_capabilities_reach_executor(self):
        events = []

        def _setter(degraded, **kw):
            events.append(degraded)

        def repo(task_id, cfg):
            return {'ui_capabilities': {'ui_capture_available': False,
                                        'degrade_reason': 'hypium_missing'}}

        mgr = _make_manager(repo)
        mgr._executor.set_ui_capture_degraded = _setter
        mgr.initialize_devices(DEVICES, task_id=500, test_case_id='c1')
        assert events and events[0][0]['degrade_reason'] == 'hypium_missing'
        assert events[0][0]['device_name'] == 'd9'

    def test_initialize_failure_still_raises(self):
        repo = MagicMock(side_effect=RuntimeError('initialize failed on sn1 (result=False)'))
        mgr = _make_manager(repo)
        with pytest.raises(RuntimeError, match='initialize failed'):
            mgr.initialize_devices(DEVICES, task_id=500, test_case_id='c1')

    def test_full_chain_executor_state_and_note(self):
        """initialize 消费降级 → executor 状态 + 轮次留痕结构一次成形"""
        def repo(task_id, cfg):
            return {'ui_capabilities': {'ui_capture_available': False,
                                        'degrade_reason': 'uitest_daemon_unavailable'}}

        mgr, ex = _manager_with_executor(repo)
        mgr.initialize_devices(DEVICES, task_id=500, test_case_id='c1')
        assert ex._ui_capture_degraded[0]['degrade_reason'] == 'uitest_daemon_unavailable'
        assert ex._ui_capture_degraded_note['status'] == 'skipped'
        assert ex._ui_capture_degraded_note['skip_reason'] == 'environment_excluded'
        assert ex._ui_capture_degraded_note['degrade_reason'] == 'uitest_daemon_unavailable'
        assert ex._ui_capture_degraded_note['devices'] == ['d9']


class TestRoundRecordMarker:

    def _executor(self, note):
        ex = E2EExecutor.__new__(E2EExecutor)
        ex._aggregator = MagicMock()
        ex._task_data_repo = MagicMock()
        ex._device_repo = MagicMock()
        ex._playback_repo = MagicMock()
        ex._thread_ctx = SimpleNamespace()
        ex._eval_submit_failures = []
        ex._ui_capture_degraded_note = note
        ex._log = MagicMock()
        ex._evaluate_result = MagicMock()
        return ex

    _LOOP_ARGS = dict(
        task_id='t1', tc_rel_id='tc1',
        data={'case_algorithm_params': None},
        case_config={'rounds': [{'round_number': 1, 'audios': [],
                                 'evaluation': {'dimensions': []}}]},
        case_name='case-x', algorithm_type='voice_llm', test_case_id='c1',
        rounds=[{'round_number': 1, 'audios': []}],
        result_id=99, case_reference_params=None,
        round_idx=0, primary={'success': True},
        tagged_results=[{'success': True}],
        rounds_data=[], round_algo_params={},
    )

    def test_skipped_marker_written_when_degraded(self):
        note = {'status': 'skipped', 'skip_reason': 'environment_excluded',
                'degrade_reason': 'hypium_missing', 'devices': ['d9']}
        ex = self._executor(note)
        round_data = ex._build_and_submit_round_data(**self._LOOP_ARGS)
        assert round_data['ui_capture'] == note

    def test_no_marker_when_not_degraded(self):
        ex = self._executor(None)
        round_data = ex._build_and_submit_round_data(**self._LOOP_ARGS)
        assert 'ui_capture' not in round_data

    def test_marker_missing_on_fresh_executor(self):
        """getattr 兜底：__new__ 裸宿主（无 __init__）不带标记也不炸"""
        ex = self._executor(None)
        del ex._ui_capture_degraded_note
        round_data = ex._build_and_submit_round_data(**self._LOOP_ARGS)
        assert 'ui_capture' not in round_data


class TestFinalizationMergeMarker:

    _FIN_ARGS = dict(
        task_id='t1', tc_rel_id='tc1', data={}, case_name='case-x',
        algorithm_type='voice_llm', test_case_id='c1', result_id=99,
        all_round_results=[{'response_time': 100}],
        case_reference_params=None, last_adjusted_ref_params=None,
        device_info_list=None,
    )

    def _host(self):
        from shared.utils.status_constants import ExecutionStatus
        ex = E2EExecutor.__new__(E2EExecutor)
        ex._log = MagicMock()
        ex._handle_control = MagicMock()
        ex._eval_submit_failures = []
        ex._aggregator = MagicMock()
        ex._aggregator.build_algorithm_result.return_value = {
            'rounds': [{'round': 0, 'output': {}}], 'aggregated': {}}
        ex._aggregator.process_results.return_value = True
        ex._task_data_repo = MagicMock()
        ex._playback_repo = MagicMock()
        return ex

    def test_final_rounds_carry_marker_when_degraded(self):
        import e2e_test_service.application.services.e2e_executor.finalization_mixin as fin_mod
        note = {'status': 'skipped', 'skip_reason': 'environment_excluded',
                'degrade_reason': 'hypium_missing'}
        ex = self._host()
        ex._ui_capture_degraded_note = note
        with patch.object(fin_mod, 'write_result_data_file', MagicMock(return_value=None)):
            ex._finalize_rounds(case_config={'rounds': []}, execution_success=True,
                                **self._FIN_ARGS)
        rounds = ex._aggregator.update_test_result.call_args.kwargs['algo_result']['rounds']
        assert rounds and all(r.get('ui_capture') == note for r in rounds)

    def test_final_rounds_clean_without_degrade(self):
        import e2e_test_service.application.services.e2e_executor.finalization_mixin as fin_mod
        ex = self._host()
        ex._ui_capture_degraded_note = None
        with patch.object(fin_mod, 'write_result_data_file', MagicMock(return_value=None)):
            ex._finalize_rounds(case_config={'rounds': []}, execution_success=True,
                                **self._FIN_ARGS)
        rounds = ex._aggregator.update_test_result.call_args.kwargs['algo_result']['rounds']
        assert rounds and all('ui_capture' not in r for r in rounds)


class TestPreparationTaskLevelTrace:

    def _prepare_host(self):
        ex = E2EExecutor.__new__(E2EExecutor)
        ex._log = MagicMock()
        ex._handle_control = MagicMock()
        ex._save_result = MagicMock(return_value=99)
        ex._prepare_audio_files = MagicMock()
        ex._audio_local_paths = {}
        ex._device_manager = MagicMock()
        ex._device_manager.get_ui_capture_degraded.return_value = None
        ex._device_manager.get_device_info.return_value = {
            'success': True,
            'data': {'device_info_list': [{'device_id': 1, 'device_name': 'd9',
                                           'device_sn': SN, 'system': 'HarmonyOS',
                                           'keywords': 'harmony.base.v1'}]}}
        ex._device_manager.initialize_devices = MagicMock()
        DeviceAcl = MagicMock()
        DeviceAcl().register_task_devices.return_value = True
        return ex

    _PREP_ARGS = dict(
        task_id='t1', tc_rel_id='tc1',
        data={'case_algorithm_params': None, 'case_name': 'c', 'test_case_id': 'c1'},
        case_config={'rounds': [{'round_number': 1, 'audios': []}]},
        algorithm_type='voice_llm', case_field_values={}, rounds=[{'round_number': 1}],
        test_case_id='c1',
    )

    def test_result_data_clean_without_degrade(self):
        ex = self._prepare_host()
        device_info_list, result_id = ex._prepare_rounds(**self._PREP_ARGS)
        assert result_id == 99
        kwargs = ex._save_result.call_args.kwargs
        assert kwargs['result_data'] == {'multi_round': True, 'total_rounds': 1}

    def test_result_data_carries_degrade_trace(self):
        ex = self._prepare_host()
        ex._device_manager.get_ui_capture_degraded.return_value = [
            {'device_name': 'd9', 'degrade_reason': 'hypium_missing'}]
        ex._prepare_rounds(**self._PREP_ARGS)
        result_data = ex._save_result.call_args.kwargs['result_data']
        assert result_data['ui_capture_degraded'] == [
            {'device_name': 'd9', 'degrade_reason': 'hypium_missing'}]
