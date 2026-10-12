# -*- coding: utf-8 -*-
"""INT-158 第二轮打回修复（b03b4f01）验收：采集链硬化行为锁定。

四组修复的行为契约：
1. 录屏产物校验：ffprobe 判定不可播放（moov 缺失/未收尾）的 mp4 直接按采集
   失败处理——不上传、不转 wav、不回退 wav_path=坏文件
2. servicer 透传：initialize/pre_process/post_process 驱动返回 False →
   gRPC success=False（driver 未注册同失败；None/True 兼容无返回值驱动）；
   e2e 侧 pre/post_process_devices 把 create_driver 的 False 落为轮次失败
3. 录屏收尾：stop 以文件 size 连续两次读数稳定为判据，仍增长再 toggle 复验；
   启动无产物时恢复 toggle + 二次短轮询（首 toggle 可能停掉残留录制）
4. 发现兜底：启动轮询超时后按"本轮新增 mp4 diff"取 size 最大者——兼容忽略
   --ps CustomizedFileName 的机型（VID_* 命名，mediatool 按名查询永不命中）
"""
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.infrastructure.drivers.harmony_collection_mixin import (
    HarmonyCollectionMixin,
)
from device_service.infrastructure.drivers.harmony_driver import HarmonyDriver
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer
from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager

MIXIN = 'device_service.infrastructure.drivers.harmony_collection_mixin'
HD = 'device_service.infrastructure.drivers.harmony_driver'
FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'

SN = '5SM0125613000197'


class StubCollectionDriver(HarmonyCollectionMixin):
    """仅具备混入采集能力的最小驱动替身（记录日志，不依赖设备）"""

    def __init__(self):
        self.logs = []
        self._record_file_name = 'case_r0.mp4'
        self._record_device_path = None
        self._preexisting_mp4_set = set()
        self._recording = False

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))


def _ok(stdout=''):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr='')


def _patch_timing():
    """把录屏轮询超时压到亚秒级，保持真实 time.time() 判定逻辑不变"""
    return patch.multiple(
        MIXIN,
        BASE_RECORDER_START_TIMEOUT=0.2,
        BASE_RECORDER_START_RECOVERY_TIMEOUT=0.2,
        BASE_RECORDER_STOP_VERIFY_TIMEOUT=0.3,
        BASE_RECORDER_STOP_VERIFY_INTERVAL=0.01,
        NORMAL_WAIT=0.01,
    )


# ==================== 1. _validate_mp4：ffprobe 可播放性校验 ====================

class TestValidateMp4:
    def test_healthy_mp4_passes(self, tmp_path):
        f = tmp_path / 'a.mp4'
        f.write_bytes(b'fake')
        driver = StubCollectionDriver()
        with patch(f'{MIXIN}.subprocess.run',
                   return_value=SimpleNamespace(returncode=0, stdout='mov,mp4', stderr='')):
            assert driver._validate_mp4(str(f)) is True

    def test_corrupted_mp4_rejected_with_error_log(self, tmp_path):
        f = tmp_path / 'a.mp4'
        f.write_bytes(b'truncated-no-moov')
        driver = StubCollectionDriver()
        with patch(f'{MIXIN}.subprocess.run',
                   return_value=SimpleNamespace(returncode=1, stdout='', stderr='moov atom not found')):
            assert driver._validate_mp4(str(f)) is False
        assert any(lv == 'ERROR' and '不可播放' in c for lv, c in driver.logs)

    def test_ffprobe_missing_skips_validation_with_warning(self, tmp_path):
        f = tmp_path / 'a.mp4'
        f.write_bytes(b'fake')
        driver = StubCollectionDriver()
        with patch(f'{MIXIN}.subprocess.run', side_effect=FileNotFoundError('no ffprobe')):
            assert driver._validate_mp4(str(f)) is True
        assert any(lv == 'WARNING' and 'ffprobe 不可用' in c for lv, c in driver.logs)

    def test_ffprobe_unexpected_error_treated_as_corrupted(self, tmp_path):
        f = tmp_path / 'a.mp4'
        f.write_bytes(b'fake')
        driver = StubCollectionDriver()
        with patch(f'{MIXIN}.subprocess.run', side_effect=__import__('subprocess').TimeoutExpired('ffprobe', 5)):
            assert driver._validate_mp4(str(f)) is False
        assert any(lv == 'WARNING' and '校验异常' in c for lv, c in driver.logs)


# ==================== 2. _pull_record_to_oss：坏文件不外流 ====================

class TestPullRecordGating:
    def _make_local_file(self, cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b'local-copy-of-mp4')
        return _ok()

    def test_corrupted_mp4_no_upload_no_wav_fallback(self):
        driver = StubCollectionDriver()
        driver._discover_round_record_file = lambda *a, **k: ('/dev/path/case_r0.mp4', 'case_r0.mp4')
        driver._validate_mp4 = lambda *a, **k: False
        driver._upload_file_to_oss = MagicMock()
        driver._mp4_to_wav = MagicMock()
        with patch(f'{MIXIN}.subprocess.run', side_effect=self._make_local_file):
            record, wav, error, note = driver._pull_record_to_oss(SN, task_id=500)
        assert record is None and wav is None and note is None
        assert '不可播放' in error
        driver._upload_file_to_oss.assert_not_called()
        driver._mp4_to_wav.assert_not_called()

    def test_healthy_mp4_uploads_record_and_wav(self):
        driver = StubCollectionDriver()
        driver._discover_round_record_file = lambda *a, **k: ('/dev/path/case_r0.mp4', 'case_r0.mp4')
        driver._validate_mp4 = lambda *a, **k: True
        driver._mp4_to_wav = MagicMock(return_value='/tmp/fake.wav')
        driver._upload_file_to_oss = MagicMock(
            side_effect=['oss://case_result/500/c1/SN/case_r0.mp4',
                         'oss://case_result/500/c1/SN/case_r0.wav'])
        with patch(f'{MIXIN}.subprocess.run', side_effect=self._make_local_file):
            record, wav, error, note = driver._pull_record_to_oss(SN, task_id=500, test_case_id='c1')
        assert error is None and note is None
        assert record == 'oss://case_result/500/c1/SN/case_r0.mp4'
        assert wav == 'oss://case_result/500/c1/SN/case_r0.wav'

    def test_actual_filename_divergence_logged(self):
        driver = StubCollectionDriver()
        driver._discover_round_record_file = lambda *a, **k: ('/dev/path/VID_20260101.mp4', 'VID_20260101.mp4')
        driver._validate_mp4 = lambda *a, **k: True
        driver._mp4_to_wav = MagicMock(return_value=None)
        driver._upload_file_to_oss = MagicMock(return_value='oss://x')
        with patch(f'{MIXIN}.subprocess.run', side_effect=self._make_local_file):
            record, wav, error, note = driver._pull_record_to_oss(SN, task_id=500)
        assert record == 'oss://x'
        assert wav == 'oss://x'  # wav 转换失败回退 mp4
        assert note and 'wav' in note
        assert any('实际文件名' in c for lv, c in driver.logs if lv == 'INFO')


# ==================== 3. _stop_recorder：size 稳定收尾判据 ====================

class TestStopRecorder:
    def _driver_with_path(self):
        driver = StubCollectionDriver()
        driver._record_device_path = '/dev/path/case_r0.mp4'
        return driver

    def test_toggle_failure_returns_false(self):
        driver = self._driver_with_path()
        calls = []
        with _patch_timing(), patch.object(driver, '_hdc_shell',
                                           side_effect=lambda sn, *a: calls.append(a) or SimpleNamespace(returncode=1)):
            assert driver._stop_recorder(SN) is False
        assert len(calls) == 1  # toggle 失败不再复验

    def test_size_stable_stops_without_second_toggle(self):
        driver = self._driver_with_path()
        calls = []
        stat_calls = []

        def fake_shell(sn, *a):
            calls.append(a)
            if a[0] == 'stat':
                stat_calls.append(1)
                return _ok('100' if len(stat_calls) >= 2 else '50')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            assert driver._stop_recorder(SN) is True
        assert sum(1 for a in calls if a[0] == 'aa') == 1  # 仅一次 toggle

    def test_still_growing_re_toggles_then_stable(self):
        driver = self._driver_with_path()
        state = {'aa': 0, 'stat': 0}
        calls = []

        def fake_shell(sn, *a):
            calls.append(a)
            if a[0] == 'stat':
                state['stat'] += 1
                if state['aa'] < 2:
                    return _ok(str(100 + state['stat'] * 50))  # 首轮等待期间持续增长
                return _ok('999')  # 复验期间稳定
            if a[:2] == ('aa', 'start'):
                state['aa'] += 1
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            assert driver._stop_recorder(SN) is True
        assert state['aa'] == 2  # 首次 toggle + 复验 toggle

    def test_never_stable_returns_false_after_re_toggle(self):
        driver = self._driver_with_path()
        state = {'aa': 0, 'stat': 0}

        def fake_shell(sn, *a):
            if a[0] == 'stat':
                state['stat'] += 1
                return _ok(str(100 + state['stat'] * 50))  # 始终增长
            if a[:2] == ('aa', 'start'):
                state['aa'] += 1
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            assert driver._stop_recorder(SN) is False
        assert state['aa'] == 2

    def test_no_device_path_degrades_to_fixed_wait(self):
        driver = StubCollectionDriver()  # _record_device_path=None
        calls = []
        with _patch_timing(), patch.object(driver, '_hdc_shell',
                                           side_effect=lambda sn, *a: calls.append(a) or _ok()):
            assert driver._stop_recorder(SN) is True
        assert sum(1 for a in calls if a[0] == 'aa') == 1


# ==================== 4. _start_recorder：恢复 toggle + diff 快照 ====================

class TestStartRecorder:
    def test_first_window_success_no_recovery_toggle(self):
        driver = StubCollectionDriver()
        state = {'find': 0, 'aa': 0}

        def fake_shell(sn, *a):
            if a[:2] == ('aa', 'start'):
                state['aa'] += 1
                return _ok()
            if a[0] == 'find':
                state['find'] += 1
                return _ok('/old.mp4' if state['find'] == 1 else '/old.mp4\n/data/new.mp4')
            if a[0] == 'stat':
                return _ok('42' if a[-1] == '/data/new.mp4' else '100')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            started, path, first_frame = driver._start_recorder(SN, file_name='case_r0.mp4')
        assert started is True
        assert path == '/data/new.mp4'
        assert first_frame is not None
        assert state['aa'] == 1
        assert driver._preexisting_mp4_set == {'/old.mp4'}

    def test_no_artifact_triggers_recovery_toggle(self):
        driver = StubCollectionDriver()
        state = {'find': 0, 'aa': 0}

        def fake_shell(sn, *a):
            if a[:2] == ('aa', 'start'):
                state['aa'] += 1
                return _ok()
            if a[0] == 'find':
                state['find'] += 1
                # 恢复 toggle（第 2 次 aa start）后才出现新文件
                if state['aa'] >= 2 and state['find'] > 1:
                    return _ok('/old.mp4\n/data/VID_20260101.mp4')
                return _ok('/old.mp4')
            if a[0] == 'stat':
                return _ok('42' if a[-1] == '/data/VID_20260101.mp4' else '100')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            started, path, first_frame = driver._start_recorder(SN, file_name='case_r0.mp4')
        assert started is True
        assert path == '/data/VID_20260101.mp4'
        assert state['aa'] == 2  # 首次 toggle + 恢复 toggle

    def test_aa_start_failure_returns_not_started(self):
        driver = StubCollectionDriver()

        def fake_shell(sn, *a):
            if a[:2] == ('aa', 'start'):
                return SimpleNamespace(returncode=1, stdout='', stderr='boom')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            started, path, first_frame = driver._start_recorder(SN)
        assert started is False and path is None and first_frame is None


# ==================== 5. _discover_round_record_file：三级发现 ====================

class TestDiscoverRoundRecordFile:
    def test_primary_device_path_wins(self):
        driver = StubCollectionDriver()
        driver._record_device_path = '/dev/path/case_r0.mp4'
        assert driver._discover_round_record_file(SN) == ('/dev/path/case_r0.mp4', 'case_r0.mp4')

    def test_diff_finds_largest_new_file(self):
        driver = StubCollectionDriver()
        driver._record_device_path = None
        driver._preexisting_mp4_set = {'/old.mp4'}

        def fake_shell(sn, *a):
            if a[0] == 'find':
                return _ok('/old.mp4\n/VID_20260101.mp4\n/VID_small.mp4')
            if a[0] == 'stat':
                return _ok({'/VID_20260101.mp4': '500', '/VID_small.mp4': '10'}.get(a[-1], '-1'))
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            path, name = driver._discover_round_record_file(SN, task_id=500)
        assert (path, name) == ('/VID_20260101.mp4', 'VID_20260101.mp4')
        assert any('新增文件 diff' in c for lv, c in driver.logs if lv == 'INFO')

    def test_mediatool_fallback_when_no_diff(self):
        driver = StubCollectionDriver()
        driver._record_device_path = None
        driver._preexisting_mp4_set = {'/old.mp4'}  # diff 无新增

        def fake_shell(sn, *a):
            if a[0] == 'mediatool':
                return _ok('MediaLibrary\n/data/local/tmp/case_r0.mp4\nuri:file://x')
            if a[0] == 'find':
                return _ok('/old.mp4')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            path, name = driver._discover_round_record_file(SN, task_id=500)
        assert (path, name) == ('/data/local/tmp/case_r0.mp4', 'case_r0.mp4')

    def test_nothing_found_returns_empty(self):
        driver = StubCollectionDriver()
        driver._record_device_path = None
        driver._preexisting_mp4_set = set()

        def fake_shell(sn, *a):
            if a[0] == 'find':
                return _ok('')
            if a[0] == 'mediatool':
                return _ok('MediaLibrary')
            return _ok()

        with _patch_timing(), patch.object(driver, '_hdc_shell', side_effect=fake_shell):
            assert driver._discover_round_record_file(SN) == ('', '')


# ==================== 6. servicer 透传（修复 2） ====================

def _req(cfg):
    return SimpleNamespace(device_config=json.dumps(cfg), task_id='500')


class TestServicerPassthrough:
    def _servicer(self, factory):
        s = DeviceServiceServicer()
        return s, patch(FACTORY_TARGET, factory)

    def test_initialize_false_fails(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.initialize.return_value = False
        factory.get_driver_for_device.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': '',
                'device_sn': SN, 'device_info_list': [{'device_sn': SN}], 'kwargs': {}}))
        assert resp.success is False
        assert 'initialize failed' in resp.message and SN in resp.message
        assert json.loads(resp.data)['initialize_result'] is False

    def test_initialize_true_passes(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.initialize.return_value = True
        factory.get_driver_for_device.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': '',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is True
        assert json.loads(resp.data)['initialize_result'] is True

    def test_initialize_none_passes_no_return_value_drivers(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.initialize.return_value = None
        factory.get_driver_for_device.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': '',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is True

    def test_initialize_driver_missing_fails(self):
        factory = MagicMock()
        factory.get_driver_for_device.return_value = None
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': '',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert 'initialize failed' in resp.message

    def test_pre_process_false_fails(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.pre_process.return_value = False
        factory.get_driver_by_sn.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'pre_process', 'device_sn': SN, 'test_case_id': 'c1', 'kwargs': {}}))
        assert resp.success is False
        assert 'pre_process failed' in resp.message
        assert json.loads(resp.data)['result'] is False

    def test_pre_process_none_passes_face2face_compat(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.pre_process.return_value = None
        factory.get_driver_by_sn.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'pre_process', 'device_sn': SN, 'test_case_id': 'c1', 'kwargs': {}}))
        assert resp.success is True

    def test_post_process_false_fails(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.post_process.return_value = False
        factory.get_driver_by_sn.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'post_process', 'device_sn': SN, 'test_case_id': 'c1', 'kwargs': {}}))
        assert resp.success is False
        assert 'post_process failed' in resp.message

    def test_pre_process_driver_missing_fails(self):
        factory = MagicMock()
        factory.get_driver_by_sn.return_value = None
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'pre_process', 'device_sn': SN, 'test_case_id': 'c1', 'kwargs': {}}))
        assert resp.success is False
        assert json.loads(resp.data)['executed'] is False

    def test_initialize_exception_maps_to_failure(self):
        factory = MagicMock()
        driver = MagicMock()
        driver.initialize.side_effect = RuntimeError('hypium rpc down')
        factory.get_driver_for_device.return_value = driver
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': '',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert 'hypium rpc down' in resp.message


# ==================== 7. e2e pre/post_process_devices 消费 False（修复 2） ====================

def _make_manager(create_driver):
    mgr = object.__new__(E2EDeviceManager)
    executor = SimpleNamespace(
        _playback_timestamps={},
        execution_engine=SimpleNamespace(device_control_pool=ThreadPoolExecutor(max_workers=2)),
        _log=lambda **kw: None,
    )
    mgr._executor = executor
    mgr._device_repo = SimpleNamespace(create_driver=create_driver)
    return mgr


DEVICES = [{'device_sn': SN, 'device_name': 'd9'}]


class TestE2eDeviceManagerBoolConsumption:
    def test_pre_process_false_becomes_round_failure(self):
        repo = MagicMock(return_value=False)
        mgr = _make_manager(repo)
        try:
            assert mgr.pre_process_devices(DEVICES, task_id=500, test_case_id='c1') is False
        finally:
            mgr._executor.execution_engine.device_control_pool.shutdown(wait=True)
        repo.assert_called_once()
        assert repo.call_args[0][1][0]['action'] == 'pre_process'

    def test_pre_process_true_succeeds(self):
        repo = MagicMock(return_value=True)
        mgr = _make_manager(repo)
        try:
            assert mgr.pre_process_devices(DEVICES, task_id=500, test_case_id='c1') is True
        finally:
            mgr._executor.execution_engine.device_control_pool.shutdown(wait=True)

    def test_pre_process_exception_becomes_failure(self):
        repo = MagicMock(side_effect=RuntimeError('grpc down'))
        mgr = _make_manager(repo)
        try:
            assert mgr.pre_process_devices(DEVICES, task_id=500) is False
        finally:
            mgr._executor.execution_engine.device_control_pool.shutdown(wait=True)

    def test_mixed_devices_any_false_fails(self):
        repo = MagicMock(side_effect=[True, False])
        mgr = _make_manager(repo)
        try:
            devices = [{'device_sn': 'A', 'device_name': 'a'}, {'device_sn': 'B', 'device_name': 'b'}]
            assert mgr.pre_process_devices(devices, task_id=500) is False
        finally:
            mgr._executor.execution_engine.device_control_pool.shutdown(wait=True)

    def test_post_process_false_becomes_failure(self):
        repo = MagicMock(return_value=False)
        mgr = _make_manager(repo)
        try:
            assert mgr.post_process_devices(DEVICES, task_id=500, test_case_id='c1') is False
        finally:
            mgr._executor.execution_engine.device_control_pool.shutdown(wait=True)
        assert repo.call_args[0][1][0]['action'] == 'post_process'


# ==================== 8. pre_process 轮首唤醒/解锁（修复 1） ====================

class StubHarmonyDriver(HarmonyDriver):
    def __init__(self):
        self.logs = []
        self._task_id = None
        self._test_case_id = None
        self.locked = False
        self.unlock_calls = 0
        self.start_calls = []

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))

    def is_locked(self, device_sn):
        return self.locked

    def unlock(self, device_sn, **kwargs):
        self.unlock_calls += 1

    def _start_recorder(self, device_sn, file_name=None):
        self.start_calls.append(file_name)
        self._record_device_path = f'/dev/path/{file_name}'
        self._recorder_first_frame_ms = 111
        return True, self._record_device_path, 111


class TestPreProcessWakeupUnlock:
    def test_locked_device_wakes_and_unlocks(self):
        driver = StubHarmonyDriver()
        driver.locked = True
        with patch(f'{HD}.subprocess.run') as run:
            ok = driver.pre_process(SN, task_id=500, test_case_id='c1', round_number=0)
        assert ok is True
        run.assert_called_once()
        assert 'power-shell' in run.call_args[0][0] and 'wakeup' in run.call_args[0][0]
        assert driver.unlock_calls == 1
        assert driver.start_calls == ['c1_r0.mp4']

    def test_unlocked_device_skips_unlock(self):
        driver = StubHarmonyDriver()
        driver.locked = False
        with patch(f'{HD}.subprocess.run'):
            ok = driver.pre_process(SN, task_id=500, test_case_id='c1', round_number=1)
        assert ok is True
        assert driver.unlock_calls == 0
        assert driver.start_calls == ['c1_r1.mp4']

    def test_wakeup_failure_does_not_block_recording(self):
        driver = StubHarmonyDriver()
        with patch(f'{HD}.subprocess.run', side_effect=RuntimeError('hdc gone')):
            ok = driver.pre_process(SN, task_id=500, test_case_id='c1', round_number=0)
        assert ok is True
        assert driver.start_calls == ['c1_r0.mp4']  # 唤醒失败仅告警，录照录
        assert any(lv == 'WARNING' and '唤醒/解锁失败' in c for lv, c in driver.logs)

    def test_start_failure_returns_false_now_propagates(self):
        driver = StubHarmonyDriver()

        def fail_start(sn, file_name=None):
            return False, None, None

        driver._start_recorder = fail_start
        with patch(f'{HD}.subprocess.run'):
            ok = driver.pre_process(SN, task_id=500, test_case_id='c1', round_number=0)
        assert ok is False  # 透传后该 False 将使 servicer/e2e 轮次 fail-fast
        assert any(lv == 'ERROR' and '启动录屏失败' in c for lv, c in driver.logs)
