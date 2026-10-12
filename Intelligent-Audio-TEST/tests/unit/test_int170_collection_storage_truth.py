# -*- coding: utf-8 -*-
"""INT-170 专项：E2E 物理链采集产物 wav 转换降级可观测 + 存储落点真实性。

覆盖：
- _upload_file_to_oss 回传 storage.save_file 真实返回值（oss:// / local://），
  不再构造性拼 oss://（OSS 失败降级本地时路径不谎报）
- save_file 抛异常（上传彻底失败，降级未开启）时返回 None
- _mp4_to_wav：ffmpeg 不可用 → None + WARNING 显式告警（不再裸跑 subprocess 静默失败）
- _mp4_to_wav：转换失败 → None + ERROR；转换成功 → wav 本地路径
- _pull_record_to_oss：wav 缺失时透出 wav_note（转换失败 / 上传失败两种口径）
- _pull_record_to_oss：全部上传失败 → error；未启动录屏 → error
- get_results：降级口径写入 message（wav 回退标注 / 本地降级标注 / 拉取失败）；
  success 判定基于真实路径——本地降级 local:// 仍有内容，彻底失败不误判
"""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.infrastructure.drivers.harmony_collection_mixin import (
    HarmonyCollectionMixin,
)

MIXIN = 'device_service.infrastructure.drivers.harmony_collection_mixin'


class StubCollectionDriver(HarmonyCollectionMixin):
    """仅具备混入采集能力的最小驱动替身（记录日志，不依赖设备）"""

    def __init__(self):
        self.logs = []
        self._record_file_name = 'round0.mp4'
        self._record_device_path = '/storage/media/100/local/files/Photo/round0.mp4'

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))


def _make_mp4(tmp_path, name='round0.mp4'):
    f = tmp_path / name
    f.write_bytes(b'fake-mp4-bytes')
    return f


# ---------------- _upload_file_to_oss：落点真实性 ----------------

def test_upload_returns_real_oss_path_when_saved_to_oss(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.storage.save_file',
               return_value='oss://case_result/486/c1/SN/round0.mp4') as sf:
        url = driver._upload_file_to_oss(str(f), '486/c1/SN')
    assert url == 'oss://case_result/486/c1/SN/round0.mp4'
    sf.assert_called_once()


def test_upload_returns_local_path_on_oss_degradation(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.storage.save_file',
               return_value='local://case_result/486/c1/SN/round0.mp4'):
        url = driver._upload_file_to_oss(str(f), '486/c1/SN')
    # OSS 不可用降级本地时必须回传 local:// 真实落点，不得谎报 oss://
    assert url == 'local://case_result/486/c1/SN/round0.mp4'
    assert not url.startswith('oss://')


def test_upload_returns_none_when_save_raises(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.storage.save_file', side_effect=RuntimeError('oss down')):
        url = driver._upload_file_to_oss(str(f), '486/c1/SN')
    assert url is None
    assert any(lv == 'WARNING' and '存储上传失败' in c for lv, c in driver.logs)


def test_upload_returns_none_for_invalid_local_path(tmp_path):
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.storage.save_file') as sf:
        url = driver._upload_file_to_oss(str(tmp_path / 'missing.mp4'), '486/c1/SN')
    assert url is None
    sf.assert_not_called()


# ---------------- _mp4_to_wav：ffmpeg 可用性与降级告警 ----------------

def test_mp4_to_wav_warns_when_ffmpeg_unavailable(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.shutil.which', return_value=None):
        result = driver._mp4_to_wav(str(f))
    assert result is None
    warnings = [c for lv, c in driver.logs if lv == 'WARNING']
    assert any('ffmpeg' in c and '不可用' in c for c in warnings)


def test_mp4_to_wav_error_on_conversion_failure(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    with patch(f'{MIXIN}.shutil.which', return_value='/usr/bin/ffmpeg'), \
         patch(f'{MIXIN}.subprocess.run',
               return_value=SimpleNamespace(returncode=1, stderr='bad input')):
        result = driver._mp4_to_wav(str(f))
    assert result is None
    errors = [c for lv, c in driver.logs if lv == 'ERROR']
    assert any('mp4转wav失败' in c for c in errors)


def test_mp4_to_wav_success_returns_wav_path(tmp_path):
    f = _make_mp4(tmp_path)
    driver = StubCollectionDriver()
    expected_wav = os.path.splitext(str(f))[0] + '.wav'

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b'RIFF-fake-wav')
        return SimpleNamespace(returncode=0, stderr='')

    with patch(f'{MIXIN}.shutil.which', return_value='/usr/bin/ffmpeg'), \
         patch(f'{MIXIN}.subprocess.run', side_effect=fake_run):
        result = driver._mp4_to_wav(str(f))
    assert result == expected_wav


# ---------------- _pull_record_to_oss：wav 缺失降级原因透出 ----------------

def _pull_with(tmp_path, driver, wav_result, upload_side_effects):
    def fake_recv(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b'fake-mp4-bytes')
        return SimpleNamespace(returncode=0, stderr='')

    with patch(f'{MIXIN}.subprocess.run', side_effect=fake_recv), \
         patch.object(driver, '_mp4_to_wav', return_value=wav_result), \
         patch.object(driver, '_upload_file_to_oss',
                      side_effect=upload_side_effects):
        return driver._pull_record_to_oss('SN123', task_id=486, test_case_id='c1')


def test_pull_threads_wav_note_on_conversion_failure(tmp_path):
    driver = StubCollectionDriver()
    record, wav, error, note = _pull_with(
        tmp_path, driver, None,
        ['oss://case_result/486/c1/SN123/round0.mp4', None])
    assert record == 'oss://case_result/486/c1/SN123/round0.mp4'
    assert wav is None
    assert error is None
    assert note is not None
    assert 'wav 转换失败' in note and '回退使用 mp4' in note


def test_pull_threads_wav_note_on_wav_upload_failure(tmp_path):
    driver = StubCollectionDriver()
    wav_local = str(_make_mp4(tmp_path, 'round0.wav'))
    record, wav, error, note = _pull_with(
        tmp_path, driver, wav_local,
        ['oss://case_result/486/c1/SN123/round0.mp4', None])
    assert record == 'oss://case_result/486/c1/SN123/round0.mp4'
    assert wav is None
    assert error is None
    assert note is not None
    assert 'wav 上传存储失败' in note and '回退使用 mp4' in note


def test_pull_clean_success_has_no_note(tmp_path):
    driver = StubCollectionDriver()
    wav_local = str(_make_mp4(tmp_path, 'round0.wav'))
    record, wav, error, note = _pull_with(
        tmp_path, driver, wav_local,
        ['oss://case_result/486/c1/SN123/round0.mp4',
         'oss://case_result/486/c1/SN123/round0.wav'])
    assert error is None
    assert note is None
    assert wav == 'oss://case_result/486/c1/SN123/round0.wav'


def test_pull_returns_error_when_all_uploads_fail(tmp_path):
    driver = StubCollectionDriver()
    record, wav, error, note = _pull_with(tmp_path, driver, None, [None, None])
    assert record is None and wav is None
    assert error is not None
    assert '上传存储失败' in error


def test_pull_returns_error_without_record_file_name():
    driver = StubCollectionDriver()
    driver._record_file_name = None
    record, wav, error, note = driver._pull_record_to_oss('SN123')
    assert record is None and wav is None
    assert '未启动录屏' in (error or '')
    assert note is None


# ---------------- get_results：降级口径外溢到 message ----------------

def _make_harmony_driver():
    from device_service.infrastructure.drivers.harmony_driver import HarmonyDriver
    driver = HarmonyDriver()
    driver.logs = []
    driver._log = lambda *args, **kwargs: driver.logs.append(
        (kwargs.get('level', 'INFO'), kwargs.get('content', '')))
    return driver


def test_get_results_message_notes_wav_fallback_to_mp4():
    driver = _make_harmony_driver()
    with patch.object(driver, '_pull_record_to_oss', return_value=(
            'oss://case_result/486/c1/SN/round0.mp4', None, None,
            'wav 转换失败（ffmpeg 不可用或转换出错），wav_path 回退使用 mp4')):
        result = driver.get_results('SN', task_id=486, test_case_id='c1')
    assert result['success'] is True
    assert 'wav 转换失败' in result['message'] and '回退使用 mp4' in result['message']
    # wav 缺失时 wav_path 回退 mp4 真实路径
    assert result['wav_path'] == 'oss://case_result/486/c1/SN/round0.mp4'
    assert result['record_path'] == result['wav_path']


def test_get_results_message_notes_local_degradation_scheme():
    driver = _make_harmony_driver()
    with patch.object(driver, '_pull_record_to_oss', return_value=(
            'local://case_result/486/c1/SN/round0.mp4',
            'local://case_result/486/c1/SN/round0.wav', None, None)):
        result = driver.get_results('SN', task_id=486, test_case_id='c1')
    # 本地降级 local:// 是真实落点 → success 保持 True，但口径须在 message 可见
    assert result['success'] is True
    assert 'local://' in result['message'] and 'OSS 不可用' in result['message']
    assert result['wav_path'] == 'local://case_result/486/c1/SN/round0.wav'
    assert result['record_path'].startswith('local://')


def test_get_results_success_without_degradation_stays_clean():
    driver = _make_harmony_driver()
    with patch.object(driver, '_pull_record_to_oss', return_value=(
            'oss://case_result/486/c1/SN/round0.mp4',
            'oss://case_result/486/c1/SN/round0.wav', None, None)):
        result = driver.get_results('SN', task_id=486, test_case_id='c1')
    assert result['success'] is True
    assert result['message'] == 'Success'


def test_get_results_failure_when_nothing_collected():
    driver = _make_harmony_driver()
    pull_error = '录屏文件上传存储失败: /tmp/x'
    with patch.object(driver, '_pull_record_to_oss', return_value=(
            None, None, pull_error, None)):
        result = driver.get_results('SN', task_id=486, test_case_id='c1')
    assert result['success'] is False
    assert result['message'] == pull_error
    assert result['wav_path'] == ''
    assert result['record_path'] == ''


def test_get_results_pull_error_noted_but_text_content_keeps_success():
    driver = _make_harmony_driver()
    driver.question_text = '今天天气'
    driver.answer_text = '晴天'
    with patch.object(driver, '_pull_record_to_oss', return_value=(
            None, None, '录屏文件拉取失败: device_path=/x stderr=timeout', None)):
        result = driver.get_results('SN', task_id=486, test_case_id='c1')
    assert result['success'] is True
    assert '录屏拉取失败' in result['message']
