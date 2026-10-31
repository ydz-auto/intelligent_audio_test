# -*- coding: utf-8 -*-
"""INT-2202 音频上传/合并内容校验

缺陷：0 字节 `.wav` 与纯文本改名 `.wav` 直连上传链（init → register → chunk →
merge）全部返回成功并入库，audio.duration=0；merge 返回里没有失败项，前端逐条
报错链路（{name, error}）永远拿不到内容非法的文件。

修复口径：
- merge 合并在入库前用 pydub 真实解码探测时长/采样率/声道；空文件、无法解码、
  时长 ≤ 0 → 抛 InvalidAudioContentError → 该文件判失败（400 + 原因）且不落库，
  同时清理临时合并文件与该文件的分片目录。
- 直传（complete-direct）路径同口径，时长 ≤ 0 同样拒绝。

覆盖：
1. 0 字节 .wav → merge 400、message 带原因、无 audio 记录、分片目录清理
2. 纯文本改名 .wav → 同上
3. 正常 WAV → merge 成功，入库 duration/sample_rate/channels 为真实探测值
4. 直传元数据探测：空文件/不可解析 → InvalidAudioContentError
"""
import base64
import io
import os
import shutil
import tempfile
import wave

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2202_') + '/content.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import Base, get_db_session, get_engine, init_db
from audio_service.infrastructure.persistence.models import (
    Audio,
    UploadChunk,
    UploadFile,
    UploadTask,
)
from audio_service.domain.exceptions import InvalidAudioContentError


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


@pytest.fixture(scope='module', autouse=True)
def _db():
    init_db()
    engine = get_engine()
    Base.metadata.create_all(engine, tables=[
        UploadTask.__table__, UploadFile.__table__,
        UploadChunk.__table__, Audio.__table__,
    ])
    yield


class _LocalFakeStorage:
    """把 storage 的 OSS 语义换成临时目录下的本地副本（测试不发网络请求）。"""

    def __init__(self, root):
        self.root = root

    def _path(self, key):
        return os.path.join(self.root, key.replace('/', os.sep))

    def exists(self, key):
        return os.path.exists(self._path(key))

    def save_file(self, local_path, category, key, **kwargs):
        dst = self._path(f'{category}/{key}')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(local_path, dst)
        return dst

    def load_file(self, path, local_path=None, **kwargs):
        src = self._path(path)
        if local_path is None:
            local_path = tempfile.mktemp(suffix='.wav')
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(src, local_path)
        return local_path

    def delete(self, path):
        p = self._path(path)
        if os.path.exists(p):
            os.remove(p)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    from audio_service.application.services.audio_upload.service import AudioUploadService
    from audio_service.application.services.audio_upload import transcoding_service as ts_mod

    monkeypatch.setattr(
        'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(ts_mod, 'storage', _LocalFakeStorage(str(tmp_path / 'store')))
    return AudioUploadService()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _wav_bytes(duration_ms=100, sample_rate=8000, channels=1) -> bytes:
    """生成一组合法 PCM WAV 字节。"""
    frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x00' * frames * channels)
    return buf.getvalue()


def _init_task(service):
    res = service.init_upload_task({})
    assert res['success'], res
    return res['data']['task_id']


def _upload_one_chunk(service, payload: bytes, name='测试音频.wav'):
    """init → register → chunk，返回 (task_id, file_id)。"""
    task_id = _init_task(service)
    reg = service.register_upload_file({
        'task_id': task_id,
        'files': [{'name': name, 'size': len(payload), 'md5': ''}],
    })
    assert reg['success'], reg
    file = reg['data']['files'][0]
    res = service.upload_chunk({
        'file_id': file['file_id'], 'chunk_index': 0,
        'total_chunks': file['total_chunks'], 'task_id': task_id,
        'chunk_content': _b64(payload),
    })
    assert res['success'], res
    return task_id, file['file_id']


def _audio_count():
    return get_db_session().query(Audio).count()


class TestMergeRejectsInvalidAudio:
    """0 字节 / 非音频内容不得入库（INT-2202 复现路径）"""

    @pytest.mark.parametrize('payload, name', [
        (b'', '空文件.wav'),
        ('这不是音频内容'.encode('utf-8'), '纯文本.wav'),
    ])
    def test_invalid_wav_rejected(self, service, tmp_path, payload, name):
        before = _audio_count()
        task_id, file_id = _upload_one_chunk(service, payload, name)

        merged = service.merge_chunks({'file_id': file_id, 'task_id': task_id})

        assert merged['success'] is False, merged
        assert merged['code'] == 400
        assert '音频内容无效' in merged['message']
        # 不落库（原缺陷：返回 200 + audio_id，duration=0）
        assert _audio_count() == before
        # 临时分片目录已清理
        assert not os.path.isdir(os.path.join(str(tmp_path), 'chunks', file_id))

    def test_valid_wav_still_merged_with_real_metadata(self, service, tmp_path):
        payload = _wav_bytes(duration_ms=100, sample_rate=8000, channels=1)
        task_id, file_id = _upload_one_chunk(service, payload)

        merged = service.merge_chunks({'file_id': file_id, 'task_id': task_id})

        assert merged['success'] is True, merged
        audio = service.repo.get_audio(merged['data']['audio_id'])
        assert audio is not None
        assert audio.duration == pytest.approx(0.1, abs=0.02)
        assert audio.sample_rate == 8000
        assert audio.channels == 1


class TestDirectUploadRejectsInvalidAudio:
    """直传（complete-direct）路径同口径"""

    def test_empty_object_rejected(self, service, tmp_path, monkeypatch):
        from audio_service.application.services.audio_upload import direct_mixin as dm_mod
        fake = _LocalFakeStorage(str(tmp_path / 'store2'))
        empty = os.path.join(str(tmp_path), 'empty_src.wav')
        with open(empty, 'wb'):
            pass
        dst = fake._path('audios/direct/empty.wav')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(empty, dst)
        monkeypatch.setattr(dm_mod, 'storage', fake)

        with pytest.raises(InvalidAudioContentError):
            service._download_and_extract_direct_meta('direct/empty.wav')

    def test_text_object_rejected(self, service, tmp_path, monkeypatch):
        from audio_service.application.services.audio_upload import direct_mixin as dm_mod
        fake = _LocalFakeStorage(str(tmp_path / 'store3'))
        src = os.path.join(str(tmp_path), 'text_src.wav')
        with open(src, 'wb') as fh:
            fh.write('not audio'.encode('utf-8'))
        dst = fake._path('audios/direct/text.wav')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        monkeypatch.setattr(dm_mod, 'storage', fake)

        with pytest.raises(InvalidAudioContentError):
            service._download_and_extract_direct_meta('direct/text.wav')

    def test_valid_object_probed(self, service, tmp_path, monkeypatch):
        from audio_service.application.services.audio_upload import direct_mixin as dm_mod
        fake = _LocalFakeStorage(str(tmp_path / 'store4'))
        dst = fake._path('audios/direct/ok.wav')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as fh:
            fh.write(_wav_bytes(duration_ms=200, sample_rate=16000, channels=1))
        monkeypatch.setattr(dm_mod, 'storage', fake)

        temp_file, size, sr, bps, duration = service._download_and_extract_direct_meta(
            'direct/ok.wav')
        try:
            assert size > 0
            assert duration == pytest.approx(0.2, abs=0.02)
            assert sr == 16000
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
