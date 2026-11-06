# -*- coding: utf-8 -*-
"""INT-2215 / INT-2216 按字节登记音频（RegisterAudioByBytes）单测。

背景：用例 ZIP 导入回导需要在目标库「凭字节登记」一条音频（INT-2205 审计
「导入侧裁定」），落库复用上传链（`_save_audio` → 转码/存储/真实时长探测），
并以 md5 幂等——同 md5 已存在直接复用既有记录，不新建、不改名。

覆盖（与卡面「四类失败分类」一一对应）：
1. 新 md5 + 合法 wav → 新建，字段齐全（duration > 0，name/format/md5/size
   与存储对象一致，file_path 可读回并解码，created_by_user_id 取调用方上下文，
   visibility 默认 shared）
2. 同 md5 再登记 → 同一 id、reused=true、行数不增、不改名
3. md5 与字节不一致 → 400，无新增行（不得以实算 md5 静默改写）
4. 空字节 / 非音频 → 400，无新增行（INT-2202 口径）
5. 同名不同 md5 → 允许新建（去重维度只认 md5）
6. gRPC servicer 直调：request/response 原文（success/message/data JSON）
"""
import base64
import hashlib
import io
import json
import os
import shutil
import tempfile
import wave

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2216_') + '/register.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import Base, get_db_session, get_engine, init_db
from audio_service.infrastructure.persistence.models import Audio


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


@pytest.fixture(scope='module', autouse=True)
def _db():
    init_db()
    engine = get_engine()
    Base.metadata.create_all(engine, tables=[Audio.__table__])
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


@pytest.fixture(autouse=True)
def _no_stats_refresh(monkeypatch):
    """统计缓存刷新属于网关域，单测不触网（登记结果不受其影响）。"""
    from audio_service.application.services.audio_upload.register_by_bytes_mixin import (
        AudioRegisterByBytesMixin,
    )
    monkeypatch.setattr(AudioRegisterByBytesMixin, '_refresh_stats_after_register',
                        lambda self, audio_id: None)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    from audio_service.application.services.audio_upload.service import AudioUploadService
    from audio_service.application.services.audio_upload import transcoding_service as ts_mod

    monkeypatch.setattr('audio_service.config.config.Config.AUDIO_STORAGE_PATH',
                        str(tmp_path / 'upload'))
    fake = _LocalFakeStorage(str(tmp_path / 'store'))
    monkeypatch.setattr(ts_mod, 'storage', fake)
    return AudioUploadService()


@pytest.fixture()
def operator():
    """模拟网关经 gRPC metadata 透传的调用方用户上下文。"""
    from shared.infrastructure.user_context import set_current_user_id
    set_current_user_id(2216)
    yield 2216
    set_current_user_id(None)


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
        wf.writeframes(b'\x00\x01' * frames * channels)
    return buf.getvalue()


def _payload(content: bytes, name='接线测试_INT2216_音频.wav', **overrides) -> dict:
    data = {
        'name': name,
        'format': 'wav',
        'size': len(content),
        'md5': hashlib.md5(content).hexdigest(),
        'content_b64': _b64(content),
        'audio_type': 'dry',
        'source_filename': name,
    }
    data.update(overrides)
    return data


def _rows_by_name(name):
    # get_db_session() 是线程 scoped_session，单测里直接查、不 close
    return get_db_session().query(Audio).filter(Audio.name == name).all()


def _audio_count():
    return get_db_session().query(Audio).count()


class TestRegisterNewAudio:
    """新建登记：字段齐全、真实时长、存储对象可读回"""

    def test_register_new_audio_fields(self, service, operator):
        content = _wav_bytes(duration_ms=120, sample_rate=8000, channels=1)
        md5 = hashlib.md5(content).hexdigest()
        name = '接线测试_INT2216_新建.wav'

        result = service.register_audio_by_bytes(_payload(content, name=name))

        assert result['success'] is True, result
        assert result['code'] == 200
        data = result['data']
        assert data['reused'] is False
        assert data['code'] == 200
        assert data['md5'] == md5
        assert data['name'] == name
        assert data['format'] == 'wav'
        assert data['duration'] == pytest.approx(0.12, abs=0.03)
        assert data['sample_rate'] == 8000
        assert data['channels'] == 1
        assert data['visibility'] == 'shared'
        assert data['created_by_user_id'] == operator

        rows = _rows_by_name(name)
        assert len(rows) == 1
        row = rows[0]
        assert row.md5 == md5
        assert row.format == 'wav'
        assert row.audio_type == 'dry'
        assert row.duration > 0
        assert row.visibility == 'shared'
        assert row.created_by_user_id == operator

        # file_path 指向的存储对象可读回，且对合法 wav 不重编码：字节与入参一致
        # （md5 幂等键要在「导出→再导入」往复中稳定，存储字节必须等于入参字节）
        assert os.path.isfile(row.file_path), row.file_path
        with open(row.file_path, 'rb') as fh:
            stored = fh.read()
        assert hashlib.md5(stored).hexdigest() == md5
        assert len(stored) == len(content) == row.size
        from pydub import AudioSegment
        decoded = AudioSegment.from_file(row.file_path)
        assert len(decoded) / 1000.0 == pytest.approx(0.12, abs=0.03)
        assert decoded.frame_rate == 8000

    def test_missing_required_fields_rejected(self, service):
        for missing in ('name', 'md5', 'content_b64'):
            data = _payload(_wav_bytes())
            data.pop(missing)
            result = service.register_audio_by_bytes(data)
            assert result['success'] is False
            assert result['code'] == 400
            assert missing in result['message']


class TestRegisterIdempotentByMd5:
    """同 md5 幂等复用（不新建、不改名、行数不增）"""

    def test_same_md5_reuses_existing_record(self, service):
        content = _wav_bytes(duration_ms=150)
        first = service.register_audio_by_bytes(
            _payload(content, name='接线测试_INT2216_首次.wav'))
        assert first['success'] is True, first
        audio_id = first['data']['id']
        before = _audio_count()

        second = service.register_audio_by_bytes(
            _payload(content, name='接线测试_INT2216_改名尝试.wav'))

        assert second['success'] is True, second
        assert second['code'] == 200
        assert second['data']['id'] == audio_id
        assert second['data']['reused'] is True
        assert second['data']['name'] == '接线测试_INT2216_首次.wav'  # 不改名
        assert _audio_count() == before
        assert _rows_by_name('接线测试_INT2216_改名尝试.wav') == []

    def test_same_name_different_md5_creates_new_record(self, service):
        name = '接线测试_INT2216_同名.wav'
        a = service.register_audio_by_bytes(
            _payload(_wav_bytes(duration_ms=100, sample_rate=8000), name=name))
        b = service.register_audio_by_bytes(
            _payload(_wav_bytes(duration_ms=200, sample_rate=16000), name=name))

        assert a['success'] and b['success'], (a, b)
        assert a['data']['id'] != b['data']['id']
        assert a['data']['md5'] != b['data']['md5']
        assert len(_rows_by_name(name)) == 2


class TestRegisterRejects:
    """md5 不一致 / 空内容 / 非音频：400 且不落库"""

    def test_md5_mismatch_rejected(self, service):
        content = _wav_bytes()
        wrong_md5 = hashlib.md5(b'another-bytes').hexdigest()
        before = _audio_count()

        result = service.register_audio_by_bytes(
            _payload(content, md5=wrong_md5))

        assert result['success'] is False, result
        assert result['code'] == 400
        assert 'md5' in result['message']
        assert '不一致' in result['message']
        assert result['data']['reason'] == 'md5_mismatch'
        assert _audio_count() == before

    def test_empty_content_rejected(self, service):
        before = _audio_count()
        result = service.register_audio_by_bytes(
            {'name': '接线测试_INT2216_空.wav', 'format': 'wav', 'size': 0,
             'md5': hashlib.md5(b'').hexdigest(), 'content_b64': ''})

        assert result['success'] is False, result
        assert result['code'] == 400
        assert '为空' in result['message']
        assert result['data']['reason'] == 'empty_content'
        assert _audio_count() == before

    def test_non_audio_content_rejected(self, service):
        content = '这不是音频内容'.encode('utf-8')
        before = _audio_count()

        result = service.register_audio_by_bytes(
            _payload(content, name='接线测试_INT2216_纯文本.wav'))

        assert result['success'] is False, result
        assert result['code'] == 400
        assert '音频内容无效' in result['message']
        assert result['data']['reason'] == 'invalid_audio_content'
        assert _audio_count() == before

    def test_invalid_base64_rejected(self, service):
        before = _audio_count()
        result = service.register_audio_by_bytes(
            {'name': '接线测试_INT2216_坏b64.wav', 'format': 'wav',
             'md5': '0' * 32, 'content_b64': '###not-base64###'})

        assert result['success'] is False
        assert result['code'] == 400
        assert 'base64' in result['message']
        assert result['data']['reason'] == 'invalid_base64'
        assert _audio_count() == before


class TestServicerRegisterAudioByBytes:
    """gRPC servicer 直调（proto 接线 + 请求/响应原文）"""

    def _servicer(self):
        from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
        return AudioConfigServiceServicer()

    def test_register_via_servicer(self, service):
        from shared.proto import audio_service_pb2 as pb

        content = _wav_bytes(duration_ms=180)
        name = '接线测试_INT2216_servicer.wav'
        request = pb.RegisterAudioByBytesRequest(
            data=json.dumps(_payload(content, name=name), ensure_ascii=False))

        resp = self._servicer().RegisterAudioByBytes(request)

        assert resp.success is True, resp.message
        assert resp.message == '音频登记成功'
        data = json.loads(resp.data)
        assert data['id'] > 0
        assert data['reused'] is False
        assert data['code'] == 200
        assert data['md5'] == hashlib.md5(content).hexdigest()
        assert len(_rows_by_name(name)) == 1

        # 第二次同样字节 → 复用同一 id
        resp2 = self._servicer().RegisterAudioByBytes(request)
        assert resp2.success is True
        assert json.loads(resp2.data)['id'] == data['id']
        assert json.loads(resp2.data)['reused'] is True

    def test_md5_mismatch_via_servicer(self, service):
        from shared.proto import audio_service_pb2 as pb

        request = pb.RegisterAudioByBytesRequest(data=json.dumps(
            _payload(_wav_bytes(), md5='f' * 32), ensure_ascii=False))
        resp = self._servicer().RegisterAudioByBytes(request)

        assert resp.success is False
        assert 'md5' in resp.message
