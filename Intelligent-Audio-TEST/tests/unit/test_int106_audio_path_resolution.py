# -*- coding: utf-8 -*-
"""INT-106 单轮执行链音频路径解析单测

覆盖：
1. resolve_audio_local_path 解析顺序：本地已存在 → 历史静态根重映射
   （AUDIO_LEGACY_STATIC_ROOTS → LOCAL_STORAGE_ROOT）→ oss:// / local://
   存储引用 / 裸 key 经统一存储层下载 → 无法解析返回 None
2. APITaskRunner.health_check：存储引用音频经解析后通过存在性校验；
   解析失败报错（不再被 normpath 破坏 scheme）
3. APITaskRunner.create_task：存储引用原样透传（不做 normpath）
"""
import os
from unittest import mock

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig
from shared.utils.audio_path_utils import resolve_audio_local_path


class TestResolveAudioLocalPath:

    def test_empty_returns_none(self):
        assert resolve_audio_local_path('') is None
        assert resolve_audio_local_path(None) is None

    def test_existing_local_path_returned_as_is(self, tmp_path):
        f = tmp_path / 'a.wav'
        f.write_bytes(b'RIFF')
        resolved = resolve_audio_local_path(str(f))
        assert resolved == os.path.abspath(str(f))

    def test_legacy_static_root_remapped(self, tmp_path, monkeypatch):
        """旧根下的记录 → LOCAL_STORAGE_ROOT 同相对路径（存储根迁移场景）。"""
        new_root = tmp_path / 'new_static'
        (new_root / 'audios').mkdir(parents=True)
        (new_root / 'audios' / 'legacy.wav').write_bytes(b'RIFF')

        legacy_root = tmp_path / 'legacy_root'
        (legacy_root / 'audios').mkdir(parents=True)  # 旧根下文件已不存在

        monkeypatch.setattr(BaseConfig, 'LOCAL_STORAGE_ROOT', str(new_root))
        monkeypatch.setattr(BaseConfig, 'AUDIO_LEGACY_STATIC_ROOTS',
                            f'{tmp_path / "old_first"},{legacy_root}')

        resolved = resolve_audio_local_path(
            str(legacy_root / 'audios' / 'legacy.wav'))
        assert resolved == os.path.abspath(str(new_root / 'audios' / 'legacy.wav'))

    def test_legacy_root_configured_but_file_missing_returns_none(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'LOCAL_STORAGE_ROOT',
                            str(tmp_path / 'new_static'))
        monkeypatch.setattr(BaseConfig, 'AUDIO_LEGACY_STATIC_ROOTS',
                            str(tmp_path / 'legacy_root'))
        resolved = resolve_audio_local_path(
            str(tmp_path / 'legacy_root' / 'audios' / 'gone.wav'))
        assert resolved is None

    def test_oss_scheme_downloaded_via_storage(self, monkeypatch, tmp_path):
        local = tmp_path / 'dl.wav'
        local.write_bytes(b'RIFF')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        return_value=str(local)) as load_file:
            resolved = resolve_audio_local_path('oss://audios/t/dl.wav')
        assert resolved == str(local)
        load_file.assert_called_once_with('oss://audios/t/dl.wav')

    def test_local_scheme_downloaded_via_storage(self, monkeypatch, tmp_path):
        local = tmp_path / 'dl.wav'
        local.write_bytes(b'RIFF')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        return_value=str(local)) as load_file:
            resolved = resolve_audio_local_path('local://audios/t/dl.wav')
        assert resolved == str(local)
        load_file.assert_called_once_with('local://audios/t/dl.wav')

    def test_bare_key_upgraded_to_audios_ref(self, monkeypatch, tmp_path):
        local = tmp_path / 'dl.wav'
        local.write_bytes(b'RIFF')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        return_value=str(local)) as load_file:
            resolved = resolve_audio_local_path('t\\k\\dl.wav')
        assert resolved == str(local)
        load_file.assert_called_once_with('oss://audios/t/k/dl.wav')

    def test_unresolvable_returns_none(self, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'AUDIO_LEGACY_STATIC_ROOTS', '')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        side_effect=FileNotFoundError('missing')):
            assert resolve_audio_local_path('no/such/file.wav') is None


# ── APITaskRunner 集成 ────────────────────────────────────────

class _LogExecutorStub:
    """执行器替身：仅提供 runner 依赖的 _log / _handle_control"""

    def __init__(self):
        self.logs = []

    def _log(self, level='INFO', content='', task_id=None, **kwargs):
        self.logs.append((level, content))

    def _handle_control(self, task_id):
        pass


def _make_runner():
    from api_test_service.core.api_task_runner import APITaskRunner
    executor = _LogExecutorStub()
    return APITaskRunner(executor), executor


def _api_config():
    cfg = mock.MagicMock()
    cfg.endpoint = ''
    cfg.api_endpoints = []
    cfg.meta = {}
    cfg.vendor = 'mock'
    return cfg


class _StubDriver:
    """vendor adapter 驱动替身：记录请求并按预置响应返回"""

    captured = {}

    def execute(self, data, method='POST'):
        type(self).captured.update({'method': method, 'data': dict(data)})
        return {'success': True, 'status_code': 200, 'error': None,
                'json': {'data': {'task_id': 'dut-1'}},
                'raw_response': '{}', 'latency': 1.0, 'biz_code': None,
                'biz_msg': None}


class TestRunnerAudioPath:

    def test_health_check_passes_with_oss_audio(self, monkeypatch, tmp_path):
        """oss:// 音频经存储解析后通过健康检查存在性校验（INT-106 断点 1）。"""
        runner, executor = _make_runner()
        local = tmp_path / 'a.wav'
        local.write_bytes(b'RIFF')
        monkeypatch.setattr(BaseConfig, 'AUDIO_LEGACY_STATIC_ROOTS', '')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        return_value=str(local)), \
             mock.patch('api_test_service.core.api_task_runner.vendor_adapter_registry',
                        mock.MagicMock(create_from_config=lambda *a, **k: _StubDriver())):
            context = runner.health_check(
                'task-1', 'case',
                {'id': 1, 'asr_text': '', 'file_path': 'oss://audios/x.wav'},
                _api_config(), {}, {'health': '/health'},
                lambda: 'http://dut', lambda url: None)
        assert context['audio_id'] == 1

    def test_health_check_fails_when_unresolvable(self, monkeypatch):
        runner, executor = _make_runner()
        monkeypatch.setattr(BaseConfig, 'AUDIO_LEGACY_STATIC_ROOTS', '')
        with mock.patch('shared.infrastructure.storage.storage.load_file',
                        side_effect=FileNotFoundError('missing')):
            with pytest.raises(Exception, match='无法从存储解析'):
                runner.health_check(
                    'task-1', 'case',
                    {'id': 1, 'file_path': 'oss://audios/gone.wav'},
                    _api_config(), {}, {'health': '/health'},
                    lambda: 'http://dut', lambda url: None)

    def test_create_task_passes_storage_ref_verbatim(self, monkeypatch):
        """create_task 原样透传存储引用（normpath 会把 oss:// 破坏为 oss:\\）。"""
        runner, _ = _make_runner()
        algo_acl = mock.MagicMock()
        algo_acl.get_field_mappings.return_value = {
            'original': {'api': {'input': {
                'audio_path': {'transform': 'none'},
                'vendor': {'transform': 'none'},
            }}}
        }
        _StubDriver.captured = {}
        with mock.patch('api_test_service.core.api_task_runner._algo_acl', algo_acl), \
             mock.patch('api_test_service.core.api_task_runner.dto_to_dict',
                        side_effect=lambda d: d), \
             mock.patch('api_test_service.core.api_task_runner.vendor_adapter_registry',
                        mock.MagicMock(create_from_config=lambda *a, **k: _StubDriver())):
            api_task_id = runner.create_task(
                'task-1', {'id': 1, 'file_path': 'oss://audios/x.wav'},
                _api_config(), {}, {'create_task': '/api/create_task'},
                lambda: 'http://dut', lambda url: None,
                algorithm_type='translation')

        assert api_task_id == 'dut-1'
        assert _StubDriver.captured['data']['audio_path'] == 'oss://audios/x.wav'
