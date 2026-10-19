# -*- coding: utf-8 -*-
"""INT-818 音频批量操作 move / copy / rename / modify-properties 单测。

覆盖（验收标准）：
- 四分支：move / copy / rename / modify-properties（metadata、audio-type、spl 拒绝）
- 存储 / 路径冲突处理：目标 key 已存在 → _N 序号去重；move 目标=源 → 原地不动
- 向后兼容：camelCase（audioIds / targetFolder / renameRule / propertyValue）双口径 +
  旧 Vue extraParams 透传（extra="ignore" 未声明字段不报错）
- 逐项失败不中断整批（failed_count 统计）
"""
import os
import sys
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='int818_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

import pytest
from unittest import mock

from shared.infrastructure.storage import storage
from audio_service.application.commands.audio_commands import BatchActionAudiosCommand
from audio_service.application.handlers.audio_command_handler import AudioCommandHandler


class FakeAudio:
    """领域实体替身（AudioAggregate 的 PO 兼容属性子集）。"""

    def __init__(self, **kw):
        self.id = kw['id']
        self.name = kw.get('name', 'sample.wav')
        self.original_filename = kw.get('original_filename', 'sample.wav')
        self.file_path = kw.get('file_path', 'oss://audios/direct/test_data/dry/sample.wav')
        self.size = kw.get('size', 1024)
        self.duration = kw.get('duration', 3.0)
        self.sample_rate = kw.get('sample_rate', 44100)
        self.channels = kw.get('channels', 1)
        self.bitrate = kw.get('bitrate', 705600)
        self.format = kw.get('format', 'wav')
        self.audio_type = kw.get('audio_type', 'dry')
        self.asr_text = kw.get('asr_text', '')
        self.description = kw.get('description', '')
        self.md5 = kw.get('md5', 'abc123')
        self.source_language = kw.get('source_language', '')


class FakeRepo:
    """实现 handler 用到的仓储方法子集（内存版）。"""

    def __init__(self, audios):
        self.audios = {a.id: a for a in audios}
        self.next_id = max(self.audios, default=0) + 1
        self.committed = False
        self.rolled_back = False

    def get_audios_by_ids(self, ids):
        return [self.audios[i] for i in ids if i in self.audios]

    def get_audio(self, audio_id):
        return self.audios.get(audio_id)

    def update_audio(self, audio_id, update_fields):
        audio = self.audios[audio_id]
        for key, value in update_fields.items():
            setattr(audio, key, value)
        return audio

    def create_audio(self, data):
        audio = FakeAudio(id=self.next_id, **data)
        self.next_id += 1
        self.audios[audio.id] = audio
        return audio

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def flush(self):
        pass


@pytest.fixture
def repo():
    audios = [
        FakeAudio(id=1, name='a.wav', file_path='oss://audios/direct/test_data/dry/a.wav'),
        FakeAudio(id=2, name='b.wav', file_path='oss://audios/direct/test_data/dry/b.wav',
                  audio_type='noise', description='旧描述', source_language='zh'),
    ]
    return FakeRepo(audios)


@pytest.fixture
def handler(repo):
    return AudioCommandHandler(repository=repo)


@pytest.fixture
def storage_mocks():
    """桩化 storage：exists=False（无冲突）、load/save/delete 走内存语义。"""
    with mock.patch.object(storage, 'exists', return_value=False), \
            mock.patch.object(storage, 'load_file', return_value='C:/tmp/int818_loaded.wav'), \
            mock.patch.object(storage, 'save_file',
                              side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
            mock.patch.object(storage, 'delete', return_value=None) as m_delete:
        yield {'delete': m_delete}


def _run(handler, data):
    return handler.handle_batch_action(BatchActionAudiosCommand(data=data))


# ==================== move ====================

class TestBatchMove:
    def test_move_updates_file_path_and_deletes_old_object(self, handler, repo, storage_mocks):
        result = _run(handler, {'audio_ids': [1], 'action': 'move', 'target_folder': 'test_data/noise'})

        assert result['success'] is True
        assert result['data']['action'] == 'move'
        assert result['data']['success_count'] == 1
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/noise/a.wav'
        storage_mocks['delete'].assert_called_once_with('oss://audios/direct/test_data/dry/a.wav')
        assert repo.committed is True

    def test_move_accepts_camelcase_target_folder(self, handler, repo, storage_mocks):
        # 旧 Vue extraParams 以 camelCase 透传
        result = _run(handler, {'audioIds': [1], 'action': 'move', 'targetFolder': 'test_data/prompt'})

        assert result['success'] is True
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/prompt/a.wav'

    def test_move_target_equals_source_is_noop(self, handler, repo, storage_mocks):
        result = _run(handler, {'audio_ids': [1], 'action': 'move', 'target_folder': 'test_data/dry'})

        assert result['success'] is True
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/dry/a.wav'
        # 未删除源对象、未触发重存
        storage_mocks['delete'].assert_not_called()

    def test_move_dedupes_existing_target_key(self, handler, repo):
        def fake_exists(path):
            # 目标 a.wav 已存在，_1 不存在 → 去重生成 a_1.wav
            return path.endswith('direct/test_data/noise/a.wav')

        with mock.patch.object(storage, 'exists', side_effect=fake_exists), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int818_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete', return_value=None):
            result = _run(handler, {'audio_ids': [1], 'action': 'move', 'target_folder': 'test_data/noise'})

        assert result['success'] is True
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/noise/a_1.wav'

    def test_move_rejects_unsafe_target_folder(self, handler, repo):
        result = _run(handler, {'audio_ids': [1], 'action': 'move', 'target_folder': '../evil'})
        assert result['success'] is False
        assert '非法路径段' in result['message']

    def test_move_empty_folder_fails(self, handler, repo):
        result = _run(handler, {'audio_ids': [1], 'action': 'move'})
        assert result['success'] is False

    def test_move_missing_audios_fails(self, handler, repo):
        result = _run(handler, {'audio_ids': [99], 'action': 'move', 'target_folder': 'x'})
        assert result['success'] is False


# ==================== copy ====================

class TestBatchCopy:
    def test_copy_creates_new_record_keeps_source(self, handler, repo, storage_mocks):
        result = _run(handler, {'audio_ids': [1], 'action': 'copy', 'target_folder': 'test_data/noise'})

        assert result['success'] is True
        assert result['data']['action'] == 'copy'
        assert result['data']['success_count'] == 1
        # 新记录
        assert len(repo.audios) == 3
        new_audio = repo.audios[3]
        assert new_audio.file_path == 'oss://audios/direct/test_data/noise/a.wav'
        assert new_audio.name == 'a.wav'
        assert new_audio.audio_type == 'dry'
        # 源记录与源存储对象保留
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/dry/a.wav'
        storage_mocks['delete'].assert_not_called()

    def test_copy_dedupes_when_source_in_target_folder(self, handler, repo):
        # 复制到同目录：目标 key 已存在（源文件就在目标目录）→ a_1.wav
        def fake_exists(path):
            return path.endswith('direct/test_data/dry/a.wav')

        with mock.patch.object(storage, 'exists', side_effect=fake_exists), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int818_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete', return_value=None):
            result = _run(handler, {'audio_ids': [1], 'action': 'copy', 'target_folder': 'test_data/dry'})

        assert result['success'] is True
        assert repo.audios[3].file_path == 'oss://audios/direct/test_data/dry/a_1.wav'


# ==================== rename ====================

class TestBatchRename:
    def test_rename_applies_prefix_and_sequence(self, handler, repo):
        result = _run(handler, {'audio_ids': [1, 2], 'action': 'rename', 'rename_rule': '测试音频_'})

        assert result['success'] is True
        assert repo.audios[1].name == '测试音频_01.wav'
        assert repo.audios[2].name == '测试音频_02.wav'

    def test_rename_accepts_camelcase_rename_rule(self, handler, repo):
        result = _run(handler, {'audioIds': [1], 'action': 'rename', 'renameRule': '新前缀_'})

        assert result['success'] is True
        assert repo.audios[1].name == '新前缀_01.wav'

    def test_rename_without_extension(self, handler, repo):
        repo.audios[1].name = '无扩展名'
        result = _run(handler, {'audio_ids': [1], 'action': 'rename', 'rename_rule': 'p'})

        assert result['success'] is True
        assert repo.audios[1].name == 'p01'

    def test_rename_missing_rule_fails(self, handler, repo):
        result = _run(handler, {'audio_ids': [1], 'action': 'rename'})
        assert result['success'] is False
        assert '重命名规则' in result['message']


# ==================== modify-properties ====================

class TestBatchModifyProperties:
    def test_metadata_updates_whitelisted_fields(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1, 2], 'action': 'modify-properties',
            'property': 'metadata',
            'property_value': {'description': '新描述', 'audio_type': 'prompt', 'source_language': 'en'},
        })

        assert result['success'] is True
        assert repo.audios[1].description == '新描述'
        assert repo.audios[1].audio_type == 'prompt'
        assert repo.audios[2].source_language == 'en'

    def test_metadata_accepts_camelcase_property_value(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties',
            'property': 'metadata', 'propertyValue': {'description': 'camel'},
        })

        assert result['success'] is True
        assert repo.audios[1].description == 'camel'

    def test_metadata_ignores_non_whitelisted_columns(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties',
            'property': 'metadata', 'property_value': {'file_path': 'hack', 'deleted': True},
        })

        assert result['success'] is False
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/dry/a.wav'

    def test_audio_type_updates_with_validation(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1, 2], 'action': 'modify-properties',
            'property': 'audio-type', 'property_value': 'noise',
        })

        assert result['success'] is True
        assert repo.audios[1].audio_type == 'noise'
        assert repo.audios[2].audio_type == 'noise'

    def test_audio_type_invalid_value_fails(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties',
            'property': 'audio-type', 'property_value': 'invalid',
        })

        assert result['success'] is False
        assert '无效的音频类型' in result['message']
        assert repo.audios[1].audio_type == 'dry'

    def test_audio_type_accepts_bare_value_field(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties',
            'property': 'audio-type', 'value': 'mixed',
        })

        assert result['success'] is True
        assert repo.audios[1].audio_type == 'mixed'

    def test_spl_rejected_with_clear_reason(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties',
            'property': 'spl', 'property_value': 80,
        })

        assert result['success'] is False
        assert 'SPL' in result['message']
        assert repo.audios[1].audio_type == 'dry'  # 未误改

    def test_unknown_property_fails(self, handler, repo):
        result = _run(handler, {
            'audio_ids': [1], 'action': 'modify-properties', 'property': 'whatever',
        })

        assert result['success'] is False


# ==================== 逐项失败 / 未知 action / 向后兼容 ====================

class TestBatchEdgeCases:
    def test_partial_failure_counts_failed_and_continues(self, repo):
        handler = AudioCommandHandler(repository=repo)

        def flaky_save(src, category, key):
            if key.endswith('b.wav'):
                raise OSError('存储不可用')
            return f'oss://{category}/{key}'

        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int818_loaded.wav'), \
                mock.patch.object(storage, 'save_file', side_effect=flaky_save), \
                mock.patch.object(storage, 'delete', return_value=None):
            result = _run(handler, {'audio_ids': [1, 2], 'action': 'move', 'target_folder': 'test_data/noise'})

        assert result['success'] is True
        assert result['data']['success_count'] == 1
        assert result['data']['failed_count'] == 1
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/noise/a.wav'
        assert repo.audios[2].file_path == 'oss://audios/direct/test_data/dry/b.wav'

    def test_unsupported_action_still_fails(self, handler, repo):
        result = _run(handler, {'audio_ids': [1], 'action': 'archive'})
        assert result['success'] is False
        assert '不支持的操作' in result['message']

    def test_extra_params_pass_through_without_validation_error(self):
        # 网关 schema：旧 Vue extraParams 未声明字段被忽略，不报校验错误
        from api_gateway.schemas.audio import BatchActionRequest

        validated = BatchActionRequest.model_validate({
            'audio_ids': [1], 'action': 'move',
            'target_folder': 'test_data/noise', 'legacy_param': 'ignored',
        })
        assert validated.audio_ids == [1]
        assert validated.target_folder == 'test_data/noise'

    def test_gateway_schema_accepts_camelcase_alias(self):
        from api_gateway.schemas.audio import BatchActionRequest

        validated = BatchActionRequest.model_validate({
            'audioIds': [1], 'action': 'modify-properties',
            'targetFolder': 'x', 'renameRule': 'y', 'propertyValue': {'description': 'd'},
        })
        assert validated.audio_ids == [1]
        assert validated.target_folder == 'x'
        assert validated.rename_rule == 'y'
        assert validated.property_value == {'description': 'd'}
