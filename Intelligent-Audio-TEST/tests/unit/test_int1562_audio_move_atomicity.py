# -*- coding: utf-8 -*-
"""INT-1562 批量移动非原子性回归单测。

缺陷：move 在 audio_service 中断窗口内「先删源对象、后落库」，
服务死在两步之间 → DB 仍指向已被删除的文件，记录永久悬空、无法自愈。

修复口径：复制 → 提交 DB → 提交成功后才尽力删除源对象。
本文件锁定的行为：

- 源对象删除必须发生在 repo.commit() 成功之后（顺序断言）
- 提交失败：源对象从未删除，本次新写入的目标对象回删（存储回到原状）
- 删除源对象失败：只泄漏对象，批量响应仍成功、记录已指向新路径
- 单项失败：该项源对象不删，同批其它项不受影响
- copy / 原地不动（目标=源）：不删源对象
"""
import os
import sys
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='int1562_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

import pytest
from unittest import mock

from shared.infrastructure.storage import storage
from audio_service.application.commands.audio_commands import BatchActionAudiosCommand
from audio_service.application.handlers.audio_command_handler import AudioCommandHandler


class FakeAudio:
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
    """内存仓储 + 事件顺序记录（commit / rollback / update）。"""

    def __init__(self, audios, fail_commit=False, fail_update_ids=()):
        self.audios = {a.id: a for a in audios}
        self.next_id = max(self.audios, default=0) + 1
        self.events = []
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit
        self.fail_update_ids = set(fail_update_ids)

    def get_audios_by_ids(self, ids):
        return [self.audios[i] for i in ids if i in self.audios]

    def get_audio(self, audio_id):
        return self.audios.get(audio_id)

    def update_audio(self, audio_id, update_fields):
        if audio_id in self.fail_update_ids:
            raise RuntimeError('DB 写入失败')
        audio = self.audios[audio_id]
        for key, value in update_fields.items():
            setattr(audio, key, value)
        self.events.append(('update', audio_id))
        return audio

    def create_audio(self, data):
        audio = FakeAudio(id=self.next_id, **data)
        self.next_id += 1
        self.audios[audio.id] = audio
        self.events.append(('create', audio.id))
        return audio

    def commit(self):
        if self.fail_commit:
            self.events.append(('commit_failed',))
            raise RuntimeError('提交失败')
        self.committed = True
        self.events.append(('commit',))

    def rollback(self):
        self.rolled_back = True
        self.events.append(('rollback',))

    def flush(self):
        pass


@pytest.fixture
def audios():
    return [
        FakeAudio(id=1, name='a.wav', file_path='oss://audios/direct/test_data/dry/a.wav'),
        FakeAudio(id=2, name='b.wav', file_path='oss://audios/direct/test_data/dry/b.wav'),
    ]


@pytest.fixture
def repo(audios):
    return FakeRepo(audios)


@pytest.fixture
def handler(repo):
    return AudioCommandHandler(repository=repo)


@pytest.fixture
def storage_mocks(repo):
    """桩化 storage，并把 save/delete 记录进 repo.events 以断言相对顺序。"""

    def fake_save(src, category, key):
        repo.events.append(('save', key))
        return f'oss://{category}/{key}'

    def fake_delete(path):
        repo.events.append(('delete', path))

    with mock.patch.object(storage, 'exists', return_value=False), \
            mock.patch.object(storage, 'load_file', return_value='C:/tmp/int1562_loaded.wav'), \
            mock.patch.object(storage, 'save_file', side_effect=fake_save), \
            mock.patch.object(storage, 'delete', side_effect=fake_delete):
        yield repo.events


def _run(handler, data):
    return handler.handle_batch_action(BatchActionAudiosCommand(data=data))


def _move(handler, ids=(1,), folder='test_data/noise'):
    return _run(handler, {'audio_ids': list(ids), 'action': 'move', 'target_folder': folder})


class TestMoveCommitOrdering:
    def test_source_deleted_only_after_commit(self, handler, repo, storage_mocks):
        result = _move(handler, ids=(1,))
        assert result['success'] is True

        kinds = [e[0] for e in repo.events]
        assert kinds.index('commit') < kinds.index('delete'), repo.events
        # 提交前不得出现任何源对象删除
        assert kinds[:kinds.index('commit')].count('delete') == 0
        delete = next(e for e in repo.events if e[0] == 'delete')
        assert delete[1] == 'oss://audios/direct/test_data/dry/a.wav'
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/noise/a.wav'

    def test_commit_failure_keeps_source_and_rolls_back(self, audios):
        repo = FakeRepo(audios, fail_commit=True)
        handler = AudioCommandHandler(repository=repo)
        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int1562_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete') as m_delete:
            result = _move(handler)

        assert result['success'] is False
        assert repo.rolled_back is True
        # 源对象从未删除；只回删了新写入的目标对象
        deleted = [c.args[0] for c in m_delete.call_args_list]
        assert 'oss://audios/direct/test_data/dry/a.wav' not in deleted
        assert 'oss://audios/direct/test_data/noise/a.wav' in deleted

    def test_db_write_failure_keeps_source(self, audios):
        repo = FakeRepo(audios, fail_update_ids=(1,))
        handler = AudioCommandHandler(repository=repo)
        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int1562_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete') as m_delete:
            result = _move(handler)

        # 单项失败不中断整批，但失败的 1 号源对象必须保留
        assert result['success'] is True
        assert result['data']['failed_count'] == 1
        deleted = [c.args[0] for c in m_delete.call_args_list]
        assert 'oss://audios/direct/test_data/dry/a.wav' not in deleted
        # 新写入的目标对象被回删（无 DB 记录引用）
        assert 'oss://audios/direct/test_data/noise/a.wav' in deleted


class TestMoveDeleteFailure:
    def test_delete_failure_does_not_fail_committed_batch(self, handler, repo):
        def boom(path):
            raise RuntimeError('OSS 删除超时')

        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int1562_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete', side_effect=boom):
            result = _move(handler, ids=(1, 2))

        assert result['success'] is True
        assert result['data']['success_count'] == 2
        assert repo.committed is True
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/noise/a.wav'
        assert repo.audios[2].file_path == 'oss://audios/direct/test_data/noise/b.wav'


class TestMovePartialAndNoop:
    def test_partial_save_failure_deletes_only_successful_source(self, handler, repo, storage_mocks):
        def flaky_save(src, category, key):
            if key.endswith('b.wav'):
                raise OSError('存储不可用')
            repo.events.append(('save', key))
            return f'oss://{category}/{key}'

        with mock.patch.object(storage, 'save_file', side_effect=flaky_save):
            result = _move(handler, ids=(1, 2))

        assert result['success'] is True
        assert result['data']['success_count'] == 1
        assert result['data']['failed_count'] == 1
        deletes = [e[1] for e in repo.events if e[0] == 'delete']
        assert deletes == ['oss://audios/direct/test_data/dry/a.wav']

    def test_same_folder_move_is_noop(self, handler, repo, storage_mocks):
        result = _move(handler, ids=(1,), folder='test_data/dry')

        assert result['success'] is True
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/dry/a.wav'
        assert [e[0] for e in repo.events if e[0] in ('save', 'delete')] == []

    def test_bare_key_source_is_deleted_by_storage_path(self, audios):
        audios[0].file_path = 'direct/test_data/dry/a.wav'
        repo = FakeRepo(audios)
        handler = AudioCommandHandler(repository=repo)
        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', return_value='C:/tmp/int1562_loaded.wav'), \
                mock.patch.object(storage, 'save_file',
                                  side_effect=lambda src, category, key: f'oss://{category}/{key}'), \
                mock.patch.object(storage, 'delete') as m_delete:
            result = _move(handler)

        assert result['success'] is True
        m_delete.assert_called_once_with('oss://audios/direct/test_data/dry/a.wav')


class TestCopyKeepsSource:
    def test_copy_never_deletes_source(self, handler, repo, storage_mocks):
        result = _run(handler, {'audio_ids': [1], 'action': 'copy', 'target_folder': 'test_data/noise'})

        assert result['success'] is True
        assert [e[0] for e in repo.events if e[0] == 'delete'] == []
        assert repo.audios[1].file_path == 'oss://audios/direct/test_data/dry/a.wav'


class TestInterruptWindow:
    """缺陷原始场景：服务在「写目标对象」与「落库」之间中断（进程被杀）。"""

    def test_interrupt_before_commit_keeps_source_object(self, tmp_path):
        source_key = 'direct/test_data/dry/a.wav'
        source_file = tmp_path / 'a.wav'
        source_file.write_bytes(b'RIFF-int1562-source')
        objects = {source_key: source_file}

        def fake_load(path, local_path=None):
            # 与真实 storage 一致：下载到独立临时副本，不动源对象
            loaded = tmp_path / f'loaded_{len(list(tmp_path.iterdir()))}.wav'
            loaded.write_bytes(source_file.read_bytes())
            return str(loaded)

        def fake_save(local_path, category, key):
            dst = tmp_path / key.replace('/', '__')
            dst.write_bytes(source_file.read_bytes())
            objects[key] = dst
            return f'local://{category}/{key}'

        def fake_delete(path):
            key = path.split('audios/', 1)[-1]
            objects.pop(key, None)

        repo = FakeRepo([FakeAudio(id=1, name='a.wav', file_path=f'local://audios/{source_key}')])
        # 模拟进程中断：BaseException 不会被 handler 的 except Exception 吞掉，
        # 与真实进程被杀一致——源对象删除代码根本不会执行
        repo.update_audio = mock.Mock(side_effect=SystemExit('simulated service kill'))
        handler = AudioCommandHandler(repository=repo)

        with mock.patch.object(storage, 'exists', return_value=False), \
                mock.patch.object(storage, 'load_file', side_effect=fake_load), \
                mock.patch.object(storage, 'save_file', side_effect=fake_save), \
                mock.patch.object(storage, 'delete', side_effect=fake_delete):
            with pytest.raises(SystemExit):
                _move(handler)

        # 关键断言：源对象仍在（修复前这里会已被删除，形成悬空记录）
        assert objects.get(source_key) is not None
        assert objects[source_key].read_bytes() == b'RIFF-int1562-source'
        assert repo.committed is False

