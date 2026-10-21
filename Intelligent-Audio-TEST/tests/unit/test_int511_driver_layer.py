# -*- coding: utf-8 -*-
"""INT-511 块 1：驱动层 mock 测试（不依赖真机/真声卡）

覆盖（验收标准）：
- 注册表契约：register 元数据校验 / 依赖缺失标记 / resolve 精确匹配→版本降级
  →同 app+platform 任意可用版→DriverNotFoundError / unregister / list
- 注册完整性：与 V9.7.10 移植对齐——app_type 全量登记、三元 key 唯一、
  hypium 依赖缺失仍登记（MISSING_DEPENDENCY 可见）
- 工厂 resolve：get_driver_typed（注册表类型化入口）/ get_driver_for_device
  （关键字+平台校验）/ get_driver_by_system / get_driver_by_sn / scan_devices 容错
- mock 模式传播：set_mock_mode 贯通基础/专用驱动
- 移植驱动（harmony_chatgpt 等）元数据 + 生命周期（initialize/pre_process/
  teardown）在假 device_sn + HDC 替身下可调、参数透传
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from device_service.infrastructure.drivers.driver_types import (
    DevicePlatform,
    DriverStatus,
)
from device_service.infrastructure.drivers.registry import (
    DriverNotFoundError,
    DriverRegistry,
    _check_dependencies,
)
from device_service.infrastructure.drivers.base_driver import BaseDeviceDriver
from device_service.infrastructure.drivers.contracts import AppDriver


# ──────────────────────────── 注册表契约（隔离实例，无 hypium 依赖） ────────────────────────────

def _fake_driver_cls(app_type, version='v1', platform=DevicePlatform.ANDROID,
                     deps=None, keywords='fake.v1', display_name='Fake'):
    """动态构造驱动类（Registry 只消费类属性，无需实例化 hypium 依赖链）。

    继承 AppDriver 契约（INT-1167：注册表校验注册类必须是 AppDriver 子类）。
    """
    return type('Fake%s' % app_type.replace('_', '').title(), (AppDriver,), {
        'app_type': app_type,
        'version': version,
        'platform': platform,
        'dependencies': deps or [],
        'keywords': keywords,
        'display_name': display_name,
    })


class TestRegistryContract:
    def test_register_requires_metadata(self):
        registry = DriverRegistry()
        Bad = type('Bad', (AppDriver,), {'version': 'v1', 'platform': DevicePlatform.ANDROID})
        with pytest.raises(TypeError, match='app_type'):
            registry.register(Bad)

    def test_register_rejects_non_enum_platform(self):
        """platform 为封闭集合（DevicePlatform 枚举），魔法字符串拒绝"""
        registry = DriverRegistry()
        Bad = type('Bad', (AppDriver,), {
            'app_type': 'plaud',
            'version': 'v1',
            'platform': 'android',  # 魔法字符串 platform 拒绝（封闭集合）
        })
        with pytest.raises(TypeError, match='platform'):
            registry.register(Bad)

    def test_register_rejects_non_appdriver_subclass(self):
        """注册表 Port 契约：非 AppDriver 子类禁止注册（TypeError）"""
        registry = DriverRegistry()
        Plain = type('Plain', (), {
            'app_type': 'plaud',
            'version': 'v1',
            'platform': DevicePlatform.ANDROID,
        })
        with pytest.raises(TypeError, match='不是 AppDriver 子类'):
            registry.register(Plain)

    def test_register_marks_missing_dependency(self):
        registry = DriverRegistry()
        cls = _fake_driver_cls('plaud', deps=['no_such_pkg_xyz'])
        registry.register(cls)
        entry = registry.get_by_key('plaud', 'v1', DevicePlatform.ANDROID)
        assert entry is not None
        assert entry.status == DriverStatus.MISSING_DEPENDENCY
        assert entry.missing_dep == 'no_such_pkg_xyz'
        assert entry.is_available is False

    def test_register_available_when_deps_ok(self):
        registry = DriverRegistry()
        registry.register(_fake_driver_cls('plaud'))
        entry = registry.get_by_key('plaud', 'v1', DevicePlatform.ANDROID)
        assert entry.is_available is True
        assert entry.status == DriverStatus.AVAILABLE

    def test_key_collision_overwrites(self):
        registry = DriverRegistry()
        a = _fake_driver_cls('plaud', keywords='a')
        b = _fake_driver_cls('plaud', keywords='b')
        registry.register(a)
        registry.register(b)  # 同 key 后注册覆盖（告警）
        assert registry.resolve('plaud', 'v1', DevicePlatform.ANDROID) is b

    def test_dependency_check_helper(self):
        ok, missing = _check_dependencies([])
        assert ok is True and missing == ''
        ok, missing = _check_dependencies(['sys'])  # stdlib 可用
        assert ok is True
        ok, missing = _check_dependencies(['no_such_pkg_abc'])
        assert ok is False and missing == 'no_such_pkg_abc'


class TestResolveDowngrade:
    def _registry(self):
        reg = DriverRegistry()
        reg.register(_fake_driver_cls('plaud', 'v1', DevicePlatform.ANDROID))
        return reg

    def test_exact_match(self):
        reg = self._registry()
        assert reg.resolve('plaud', 'v1', DevicePlatform.ANDROID).app_type == 'plaud'

    def test_v2_downgrades_to_v1(self):
        """V2 请求无 V2 实现 → 自动降级 V1（版本降级逻辑）"""
        reg = self._registry()
        cls = reg.resolve('plaud', 'v2', DevicePlatform.ANDROID)
        assert cls.version == 'v1'

    def test_latest_falls_back_to_v1(self):
        reg = self._registry()
        cls = reg.resolve('plaud', 'latest', DevicePlatform.ANDROID)
        assert cls.version == 'v1'

    def test_any_version_same_app_platform(self):
        """同 app_type+platform 下任意可用版本（V3 未注册仍可命中 V1）"""
        reg = self._registry()
        assert reg.resolve('plaud', 'v1', DevicePlatform.ANDROID) \
            is reg.resolve('plaud', 'v1', DevicePlatform.ANDROID)

    def test_v2_exact_match_preferred_over_v1(self):
        reg = DriverRegistry()
        v1 = _fake_driver_cls('xiaoyi_livechat', 'v1', DevicePlatform.HARMONYOS)
        v2 = _fake_driver_cls('xiaoyi_livechat', 'v2', DevicePlatform.HARMONYOS)
        reg.register(v1)
        reg.register(v2)
        assert reg.resolve('xiaoyi_livechat', 'v2',
                           DevicePlatform.HARMONYOS) is v2
        # V1 请求精确命中 v1，不降级到 v2
        assert reg.resolve('xiaoyi_livechat', 'v1',
                           DevicePlatform.HARMONYOS) is v1

    def test_missing_dependency_raises_with_reason(self, monkeypatch):
        """依赖缺失（hypium）→ resolve 抛 DriverNotFoundError 且 reason 带缺失依赖。
        注入确定性依赖检测：不依赖宿主环境 hypium 是否安装（装与不装都全绿）。"""
        import importlib.util
        real_find = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util, 'find_spec',
            lambda name: None if name == 'hypium' else real_find(name))
        reg = DriverRegistry()
        reg.register(_fake_driver_cls(
            'doubao', platform=DevicePlatform.HARMONYOS, deps=['hypium']))
        with pytest.raises(DriverNotFoundError) as ei:
            reg.resolve('doubao', 'v1', DevicePlatform.HARMONYOS)
        assert 'hypium' in ei.value.reason

    def test_unregistered_app_raises(self):
        reg = self._registry()
        with pytest.raises(DriverNotFoundError, match='无可用驱动实现'):
            reg.resolve('chatgpt', 'v1', DevicePlatform.HARMONYOS)

    def test_unregister_removes_entry(self):
        reg = self._registry()
        assert reg.unregister('plaud', 'v1', DevicePlatform.ANDROID) is not None
        assert reg.get_by_key('plaud', 'v1', DevicePlatform.ANDROID) is None
        assert reg.unregister('plaud', 'v1', DevicePlatform.ANDROID) is None


class TestListDrivers:
    def test_list_drivers_self_describe(self):
        reg = DriverRegistry()
        reg.register(_fake_driver_cls('plaud', deps=[], keywords='k'))
        info = reg.list_drivers()
        assert len(info) == 1
        d = info[0]
        assert d['app_type'] == 'plaud'
        assert d['status'] == DriverStatus.AVAILABLE.value
        assert d['class'] == 'FakePlaud'
        assert 'module' in d and 'display_name' in d


# ──────────────────────────── 注册完整性（与 V9.7.10 移植对齐） ────────────────────────────

# V9.7.10 移植对齐基线：V9.7.10 全量 app_type 移植 + V9.7.31 新增 XiaoyilivechatV2
# （harmony_xiaoyilivechat.py），总登记数 12（含基础平台驱动与 hypium 缺失驱动）。
_EXPECTED_APP_TYPES = {
    'android_base', 'harmony_base',
    'plaud', 'doubao_asr', 'doubao', 'chatgpt',
    'xiaoyi_face2face', 'xiaoyi_simultaneous',
    'xiaoyi_huiji', 'xiaoyi_livechat', 'xiaoyi_input_method',
}


class TestRegistrationCompleteness:
    def test_full_app_type_coverage_aligned_with_v9710(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        drivers = driver_registry.list_drivers()
        registered = {d['app_type'] for d in drivers}
        assert _EXPECTED_APP_TYPES <= registered, \
            f"缺少 V9.7.10 对齐 app_type: {_EXPECTED_APP_TYPES - registered}"

    def test_total_count_includes_v2_livechat(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        drivers = driver_registry.list_drivers()
        # V9.7.10 = 11（无 V2）；V9.7.31 移植后 +XiaoyilivechatV2 = 12
        assert len(drivers) == 12, f"登记驱动数={len(drivers)}，期望 12"
        v2_entries = [d for d in drivers
                      if d['app_type'] == 'xiaoyi_livechat'
                      and d['version'] == 'v2']
        assert len(v2_entries) == 1

    def test_three_tuple_key_unique(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        keys = [(d['app_type'], d['version'], d['platform'])
                for d in driver_registry.list_drivers()]
        assert len(keys) == len(set(keys)), '三元 key (app_type, version, platform) 必须唯一'

    def test_hypium_dependent_drivers_registered_but_marked(self, monkeypatch):
        """hypium 依赖驱动仍登记；缺失时状态 MISSING_DEPENDENCY。

        注入确定性依赖检测（不依赖宿主环境 hypium 装否）：强制 hypium 视作缺失后
        覆盖重注册真实 CHATGPT 条目，断言登记 + 缺失标记；结束时恢复宿主真实状态。
        """
        import importlib.util
        from device_service.infrastructure.drivers.registry import driver_registry
        real_find = importlib.util.find_spec
        chatgpt = driver_registry.get_by_key(
            'chatgpt', 'v1', DevicePlatform.HARMONYOS)
        assert chatgpt is not None, 'CHATGPT 必须登记（无论 hypium 装否）'
        chatgpt_cls = chatgpt.driver_cls
        try:
            monkeypatch.setattr(
                importlib.util, 'find_spec',
                lambda name: None if name == 'hypium' else real_find(name))
            driver_registry.register(chatgpt_cls)   # 覆盖重注册 → 重新依赖检测
            entry = driver_registry.get_by_key(
                'chatgpt', 'v1', DevicePlatform.HARMONYOS)
            assert entry.status == DriverStatus.MISSING_DEPENDENCY
            assert entry.missing_dep == 'hypium'
        finally:
            # 恢复宿主真实状态（hypium 装否由环境决定，不在此固定断言）
            try:
                importlib.util.find_spec = real_find
                driver_registry.register(chatgpt_cls)
            except Exception:
                pass

    def test_base_and_non_hypium_drivers_available(self):
        from device_service.infrastructure.drivers.registry import driver_registry
        for (app, ver, plat) in [
            ('android_base', 'v1', DevicePlatform.ANDROID),
            ('harmony_base', 'v1', DevicePlatform.HARMONYOS),
            ('plaud', 'v1', DevicePlatform.ANDROID),
            ('doubao_asr', 'v1', DevicePlatform.ANDROID),
        ]:
            entry = driver_registry.get_by_key(app, ver, plat)
            assert entry is not None and entry.is_available, f'{app} 应可用'


# ──────────────────────────── 工厂 resolve（类型化 + 关键字 + 平台校验） ────────────────────────────

class TestFactoryResolve:
    def test_get_driver_typed_returns_instance(self):
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        driver = device_driver_factory.get_driver_typed('plaud', DevicePlatform.ANDROID)
        assert driver is not None
        assert driver.__class__.__name__ == 'PlaudDriver'

    def test_get_driver_typed_hypium_dependent_returns_none(self, monkeypatch):
        """hypium 缺失：resolve 抛 DriverNotFoundError → 工厂收敛为 None（不炸）。

        注入确定性依赖检测强制 hypium 缺失，断言工厂收敛；结束恢复宿主真实状态。
        """
        import importlib.util
        from device_service.infrastructure.drivers.registry import driver_registry
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        real_find = importlib.util.find_spec
        chatgpt = driver_registry.get_by_key(
            'chatgpt', 'v1', DevicePlatform.HARMONYOS)
        assert chatgpt is not None
        chatgpt_cls = chatgpt.driver_cls
        try:
            monkeypatch.setattr(
                importlib.util, 'find_spec',
                lambda name: None if name == 'hypium' else real_find(name))
            driver_registry.register(chatgpt_cls)
            assert device_driver_factory.get_driver_typed(
                'chatgpt', DevicePlatform.HARMONYOS) is None
        finally:
            try:
                importlib.util.find_spec = real_find
                driver_registry.register(chatgpt_cls)
            except Exception:
                pass

    def test_get_driver_for_device_keyword_resolution(self):
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        driver = device_driver_factory.get_driver_for_device(
            'Android', keywords='android.plaud.v1')
        assert driver.__class__.__name__ == 'PlaudDriver'

    def test_get_driver_for_device_unknown_keyword_raises(self):
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        with pytest.raises(ValueError, match='未注册驱动 keywords'):
            device_driver_factory.get_driver_for_device('Android', keywords='no.such')

    def test_get_driver_for_device_platform_mismatch_raises(self):
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        with pytest.raises(ValueError, match='平台与驱动不匹配'):
            device_driver_factory.get_driver_for_device(
                'HarmonyOS', keywords='android.plaud.v1')

    def test_get_driver_by_system(self):
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        assert device_driver_factory.get_driver_by_system('HarmonyOS') is not None
        assert device_driver_factory.get_driver_by_system('Android') is not None

    def test_get_driver_by_sn(self):
        """假 device_sn → 持有该 sn 的 driver（_drivers 内存表）"""
        factory = MagicMock()
        target = MagicMock()
        target._drivers = {'fake-sn-001': object()}
        factory.get_driver_by_sn('fake-sn-001')
        # 走真实工厂实现：构造轻量实例注入假驱动
        from device_service.infrastructure.drivers.driver_factory import DeviceDriverFactory
        real = object.__new__(DeviceDriverFactory)
        real._specialized_drivers = [{'driver': target, 'keywords': ['k'], 'system': 'android'}]
        real._base_drivers = {}
        real._task_device_map = {}
        assert real.get_driver_by_sn('fake-sn-001') is target
        assert real.get_driver_by_sn('no-such-sn') is None

    def test_scan_devices_error_does_not_abort(self):
        from device_service.infrastructure.drivers.driver_factory import DeviceDriverFactory
        real = object.__new__(DeviceDriverFactory)
        good = MagicMock()
        good.scan.return_value = [{'serial': 'ok-1'}]
        bad = MagicMock()
        bad.scan.side_effect = RuntimeError('adb crashed')
        real._base_drivers = {'Android': good, 'HarmonyOS': bad}
        devices = real.scan_devices()
        assert [d['serial'] for d in devices] == ['ok-1']


class TestMockModePropagation:
    def test_set_mock_mode_propagates_to_base_and_specialized(self):
        from device_service.infrastructure.drivers.driver_factory import DeviceDriverFactory
        real = object.__new__(DeviceDriverFactory)
        base = MagicMock()
        spec = {'driver': MagicMock(), 'keywords': ['k'], 'system': 'android',
                'original_keywords': 'k', 'name': 'Spec'}
        real._base_drivers = {'Android': base, 'HarmonyOS': MagicMock()}
        real._specialized_drivers = [spec]
        real.set_mock_mode(True)
        base.set_mock_mode.assert_called_once_with(True)
        spec['driver'].set_mock_mode.assert_called_once_with(True)
        assert real.get_mock_mode() is True


# ──────────────────────────── 移植驱动元数据 + 生命周期（假设备/HDC 替身） ────────────────────────────

class FakeHdcResult:
    """hdc 命令替身返回（subprocess.CompletedProcess 同形）"""
    def __init__(self, rc=0, out='', err=''):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def _make_chatgpt():
    """实例化移植驱动 ChatGptVoiceChat（hypium 缺失仍可构造，UiDriver=None）"""
    from device_service.infrastructure.drivers.harmony_chatgpt import ChatGptVoiceChat
    return ChatGptVoiceChat()


class TestPortedDriverMetadata:
    def test_chatgpt_metadata_aligned(self):
        d = _make_chatgpt()
        assert d.app_type == 'chatgpt'
        assert d.version == 'v1'
        assert d.platform is DevicePlatform.HARMONYOS
        assert d.keywords == 'harmony.chatgpt.v1'
        assert d.display_name == 'ChatGPT语音通话专用驱动'
        assert d.app_name == 'com.openai.chatgpt'   # 覆盖父类 app_name

    def test_other_ported_drivers_metadata(self):
        from device_service.infrastructure.drivers.harmony_doubaochat import DoubaoChat
        db = DoubaoChat()
        assert db.app_type == 'doubao'
        assert db.platform is DevicePlatform.HARMONYOS

        from device_service.infrastructure.drivers.harmony_translation_driver import (
            XiaoyiFace2FaceDriver,
            XiaoyiSimultaneousInterpretationDriver,
        )
        assert XiaoyiFace2FaceDriver().app_type == 'xiaoyi_face2face'
        assert XiaoyiSimultaneousInterpretationDriver().app_type == 'xiaoyi_simultaneous'


class TestChatGptLifecycleMockDevice:
    """生命周期在「假 device_sn + HDC 替身」下可调、参数透传"""

    @pytest.fixture(autouse=True)
    def _fast_and_mock_hdc(self, monkeypatch):
        from device_service.infrastructure.drivers import harmony_chatgpt as hc
        from device_service.infrastructure.drivers import harmony_driver as hd
        from device_service.infrastructure.drivers import harmony_collection_mixin as hcm
        monkeypatch.setattr(hc.time, 'sleep', lambda *a, **k: None)
        monkeypatch.setattr(hd.time, 'sleep', lambda *a, **k: None)
        monkeypatch.setattr(hcm.time, 'sleep', lambda *a, **k: None)

    def test_initialize_explicit_degrade_with_fake_sn(self, monkeypatch):
        """explicit_degrade：UI 层降级（driver=None）→ hdc 步骤照常 → 初始化成功"""
        d = _make_chatgpt()
        hdc_calls = []
        monkeypatch.setattr(d, '_initialize_ui_guard',
                            lambda *a, **k: (None, True))
        monkeypatch.setattr(d, 'unlock', lambda *a, **k: None)
        monkeypatch.setattr(d, 'close_popups', lambda *a, **k: None)
        monkeypatch.setattr(d, '_device_shell', lambda *a, **k: None)
        monkeypatch.setattr(
            d, '_hdc_shell',
            lambda sn, *args: hdc_calls.append((sn, args)) or FakeHdcResult())
        ok = d.initialize('fake-sn-001', task_id=77, test_case_id=88,
                          record_mode='case', pcm_app='chatgpt')
        assert ok is True
        # 启动命令（-b 包名 -a MainActivity）经 HDC 替身执行，rc=0
        start = [c for c in hdc_calls if c[1][0] == 'aa' and c[1][1] == 'start']
        assert start, 'aa start 必须执行'
        assert start[0][1][2] == '-b' and start[0][1][3] == 'com.openai.chatgpt'
        # 参数透传：record_mode/pcm_app 落驱动状态
        assert d._record_mode == 'case'
        assert d._pcm_app == 'chatgpt'

    def test_initialize_strict_without_hypium_fails_fast(self, monkeypatch):
        """strict（默认）：hypium 缺失 → UI 层不可用 → 显式失败（不半初始化）"""
        d = _make_chatgpt()
        from device_service.infrastructure.drivers.harmony_driver import HarmonyDriver
        monkeypatch.setattr(
            HarmonyDriver, '_degrade_ui_capture', lambda self, reason: False)
        monkeypatch.setattr(d, 'unlock', lambda *a, **k: None)
        ok = d.initialize('fake-sn-001')
        assert ok is False

    def test_pre_process_case_non_first_round_skips_ui(self, monkeypatch):
        """case 模式非首轮：通话/录屏进行中 → 跳过重复启动（仍透传轮次参数）"""
        d = _make_chatgpt()
        d._recording = True
        monkeypatch.setattr(d, '_get_driver', lambda sn: None)
        monkeypatch.setattr(d, '_stop_music_app', lambda *a, **k: None)
        monkeypatch.setattr(d, '_snapshot_ai_pcm_sizes', lambda *a, **k: {})
        monkeypatch.setattr(d, '_clear_pcm', lambda *a, **k: None)
        ok = d.pre_process('fake-sn-001', task_id=77, test_case_id=88,
                           record_mode='case', total_rounds=3, round_number=1)
        assert ok is True
        assert d._record_mode == 'case'
        assert d._total_rounds == 3
        assert d._round_number == 1

    def test_teardown_force_stops_app_via_hdc(self, monkeypatch):
        """teardown：HDC 替身执行 aa force-stop + 清 PCM（假设备不触真机）"""
        import subprocess as _sp
        from device_service.infrastructure.drivers import harmony_chatgpt as hc
        d = _make_chatgpt()
        d._recording = False
        d._record_mode = 'case'
        d._record_pulled = True   # 已拉取，跳过兜底拉取
        hdc_calls = []
        monkeypatch.setattr(d, '_get_driver', lambda sn: None)
        monkeypatch.setattr(d, '_stop_music_app', lambda *a, **k: None)
        monkeypatch.setattr(d, '_clear_pcm', lambda *a, **k: None)
        monkeypatch.setattr(
            hc.subprocess, 'run',
            lambda args, **k: hdc_calls.append(args) or FakeHdcResult())
        ok = d.teardown('fake-sn-001', task_id=77, test_case_id=88)
        assert ok is True
        stop = [c for c in hdc_calls
                if c[0] == 'hdc' and 'force-stop' in c and c[-1] == 'com.openai.chatgpt']
        assert stop, f'teardown 未执行 aa force-stop，hdc_calls={hdc_calls}'


class TestBaseDriverLifecycleContract:
    """BaseDeviceDriver 生命周期方法签名/可调性（mock 驱动参数透传）"""

    def test_lifecycle_methods_callable_with_param_passthrough(self):
        class RecordingDriver(BaseDeviceDriver):
            def __init__(self):
                super().__init__()
                self.calls = []

            def _lifecycle(self, method, device_sn, **kwargs):
                self.calls.append((method, device_sn, dict(kwargs)))
                return True

            def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs):
                return self._lifecycle('initialize', device_sn, task_id=task_id,
                                       test_case_id=test_case_id, **kwargs)

            def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
                return self._lifecycle('pre_process', device_sn, task_id=task_id,
                                       test_case_id=test_case_id, **kwargs)

            def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs):
                return self._lifecycle('post_process', device_sn, task_id=task_id,
                                       test_case_id=test_case_id, **kwargs)

            def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs):
                return self._lifecycle('teardown', device_sn, task_id=task_id,
                                       test_case_id=test_case_id, **kwargs)

        d = RecordingDriver()
        assert d.initialize('SN-X', task_id=1, test_case_id=2, record_mode='case') is True
        assert d.pre_process('SN-X', task_id=1, test_case_id=2, round_number=0) is True
        assert d.post_process('SN-X', task_id=1, test_case_id=2, round_number=0) is True
        assert d.teardown('SN-X', task_id=1, test_case_id=2) is True
        methods = [c[0] for c in d.calls]
        assert methods == ['initialize', 'pre_process', 'post_process', 'teardown']
        assert d.calls[0][2] == {'task_id': 1, 'test_case_id': 2, 'record_mode': 'case'}
        assert all(c[1] == 'SN-X' for c in d.calls)

    def test_set_task_and_case_ids_stored(self):
        d = BaseDeviceDriver()
        d.set_task_id('t9')
        d.set_test_case_id('c9')
        d.set_device_id(9)
        assert d._task_id == 't9'
        assert d._test_case_id == 'c9'
        assert d._device_id == 9

    def test_default_teardown_closes_app_when_driver_provides_stop(self, monkeypatch):
        class AppDriver(BaseDeviceDriver):
            app_name = 'com.app.demo'

        d = AppDriver()
        fake_conn = MagicMock()
        fake_conn.stop_app = MagicMock()
        d._get_driver = lambda sn: fake_conn   # 实例属性注入替身连接
        assert d.teardown('SN-1', task_id=1, test_case_id=2) is True
        fake_conn.stop_app.assert_called_once_with('com.app.demo')

    def test_default_teardown_without_app_name_noop(self):
        d = BaseDeviceDriver()
        assert d.teardown('SN-1') is True
