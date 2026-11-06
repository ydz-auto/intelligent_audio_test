# -*- coding: utf-8 -*-
"""统一存储 allow_fallback 参数单测（INT-1805）。

覆盖：
  1. 默认（allow_fallback=True）零行为变更：OSS 不可用 / 上传失败照旧降级本地盘。
  2. allow_fallback=False：OSS 不可用 / 上传失败抛 StorageUnavailableError，
     且本地降级目录内不产生任何文件（关键断言）。
  3. 正常路径：OSS 可用时 allow_fallback=False 返回 oss://（且可读回）。
  4. 读侧：local:// 路径与 OSS 读取失败在 allow_fallback=False 下都抛错，
     不从本地降级副本读。
"""
import inspect
import io
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import shared.infrastructure.storage as storage_mod
from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import StorageUnavailableError


class _FakeOSS:
    """最小 OSS 桩：可配可用性与上传 / 下载失败，并记录落库对象。"""

    def __init__(self, available=True, fail_upload=False, fail_download=False):
        self.available = available
        self.fail_upload = fail_upload
        self.fail_download = fail_download
        self.objects = {}
        self.uploads = []

    def is_available(self):
        return self.available

    @staticmethod
    def _maybe_fail(flag, what):
        if flag:
            raise RuntimeError(f'OSS {what} failed: boom')

    def upload_bytes(self, data, category, key, content_type=None):
        self._maybe_fail(self.fail_upload, 'upload_bytes')
        self.objects[(category, key)] = data
        self.uploads.append((category, key))

    def upload_file(self, local_path, category, key):
        self._maybe_fail(self.fail_upload, 'upload_file')
        with open(local_path, 'rb') as f:
            self.objects[(category, key)] = f.read()
        self.uploads.append((category, key))

    def upload_stream(self, stream, category, key, content_type=None):
        self._maybe_fail(self.fail_upload, 'upload_stream')
        self.objects[(category, key)] = stream.read()
        self.uploads.append((category, key))

    def download_bytes(self, category, key):
        self._maybe_fail(self.fail_download, 'download_bytes')
        if (category, key) not in self.objects:
            raise FileNotFoundError(f'{category}/{key}')
        return self.objects[(category, key)]

    def download_file(self, category, key, local_path):
        data = self.download_bytes(category, key)
        with open(local_path, 'wb') as f:
            f.write(data)
        return local_path


@pytest.fixture(autouse=True)
def _clean_warn_state():
    storage_mod._oss_warn_state.clear()
    yield
    storage_mod._oss_warn_state.clear()


@pytest.fixture
def local_root(tmp_path, monkeypatch):
    """把本地降级根目录指向临时目录，并恢复默认降级开关。"""
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
    monkeypatch.setattr(BaseConfig, 'STORAGE_FALLBACK_ENABLED', True)
    return tmp_path


def _install_oss(monkeypatch, fake: _FakeOSS):
    """把单例的 OSS 客户端替换为桩，并置好可用性缓存。"""
    inst = storage_mod.Storage()
    monkeypatch.setattr(inst, '_oss_client', fake, raising=False)
    monkeypatch.setattr(inst, '_oss_checked', fake.available, raising=False)
    monkeypatch.setattr(inst, '_oss_ok', fake.available, raising=False)
    return inst


def _local_files(root):
    return [p for p in root.rglob('*') if p.is_file()]


class TestDefaultBehaviourUnchanged:
    """allow_fallback 默认 True：与 INT-1805 之前完全一致。"""

    def test_save_bytes_oss_unavailable_falls_back_to_local(self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(available=False))
        path = st.save_bytes(b'abc', 'case_result', 'k.json')
        assert path == 'local://case_result/k.json'
        assert (local_root / 'case_result' / 'k.json').read_bytes() == b'abc'

    def test_save_bytes_upload_error_falls_back_to_local(self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_upload=True))
        path = st.save_bytes(b'abc', 'case_result', 'k.json',
                             content_type='application/json')
        assert path == 'local://case_result/k.json'
        assert (local_root / 'case_result' / 'k.json').read_bytes() == b'abc'

    def test_save_file_and_stream_fall_back_to_local(self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_upload=True))
        src = local_root / 'src.bin'
        src.write_bytes(b'file-payload')

        assert st.save_file(str(src), 'audios', 'a.wav') == 'local://audios/a.wav'
        assert (local_root / 'audios' / 'a.wav').read_bytes() == b'file-payload'

        assert st.save_stream(io.BytesIO(b'stream-payload'), 'audios',
                              'b.wav') == 'local://audios/b.wav'
        assert (local_root / 'audios' / 'b.wav').read_bytes() == b'stream-payload'

    def test_load_bytes_oss_failure_reads_local_fallback(self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_download=True))
        dst = local_root / 'case_result' / 'k.json'
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b'from-local')

        assert st.load_bytes('oss://case_result/k.json') == b'from-local'

    def test_load_file_oss_failure_reads_local_fallback(self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_download=True))
        src = local_root / 'case_result' / 'k.bin'
        src.parent.mkdir(parents=True)
        src.write_bytes(b'from-local')

        out = local_root / 'out.bin'
        assert st.load_file('oss://case_result/k.bin', str(out)) == str(out)
        assert out.read_bytes() == b'from-local'


class TestAllowFallbackFalseNeverWritesLocal:
    """allow_fallback=False：要么进 OSS，要么报错，不落本地盘。"""

    def test_save_bytes_upload_error_raises_and_writes_nothing(
            self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_upload=True))

        with pytest.raises(StorageUnavailableError):
            st.save_bytes(b'abc', 'case_result', 'k.json', allow_fallback=False)

        assert _local_files(local_root) == []

    def test_save_bytes_oss_unavailable_raises_and_writes_nothing(
            self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(available=False))

        with pytest.raises(StorageUnavailableError):
            st.save_bytes(b'abc', 'case_result', 'k.json', allow_fallback=False)

        assert _local_files(local_root) == []

    def test_save_file_upload_error_raises_and_writes_nothing(
            self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_upload=True))
        src = local_root / 'src.bin'
        src.write_bytes(b'file-payload')

        with pytest.raises(StorageUnavailableError):
            st.save_file(str(src), 'case_result', 'raw.bin', allow_fallback=False)

        # 只有测试自己写进去的源文件，降级目录里没有任何副本
        assert _local_files(local_root) == [src]

    def test_save_stream_upload_error_raises_and_writes_nothing(
            self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_upload=True))

        with pytest.raises(StorageUnavailableError):
            st.save_stream(io.BytesIO(b'stream-payload'), 'case_result',
                           'raw.bin', allow_fallback=False)

        assert _local_files(local_root) == []


class TestAllowFallbackFalseOssHappyPath:
    def test_save_bytes_returns_oss_and_roundtrips(self, local_root, monkeypatch):
        fake = _FakeOSS()
        st = _install_oss(monkeypatch, fake)
        key = 'task_1/case_2/dev_3/raw.json'

        path = st.save_bytes(b'{"a":1}', 'case_result', key,
                             content_type='application/json',
                             allow_fallback=False)

        assert path == f'oss://case_result/{key}'
        assert fake.uploads == [('case_result', key)]
        assert _local_files(local_root) == []
        assert st.load_bytes(path, allow_fallback=False) == b'{"a":1}'

    def test_save_file_and_stream_upload_to_oss(self, local_root, monkeypatch):
        fake = _FakeOSS()
        st = _install_oss(monkeypatch, fake)
        src = local_root / 'src.bin'
        src.write_bytes(b'file-payload')

        assert st.save_file(str(src), 'case_result', 'raw.bin',
                            allow_fallback=False) == 'oss://case_result/raw.bin'
        assert st.save_stream(io.BytesIO(b'stream-payload'), 'case_result',
                              'raw.bin', allow_fallback=False
                              ) == 'oss://case_result/raw.bin'

        assert _local_files(local_root) == [src]


class TestAllowFallbackFalseRejectsLocalReads:
    def test_load_bytes_local_scheme_raises(self, local_root, monkeypatch):
        _install_oss(monkeypatch, _FakeOSS())
        dst = local_root / 'case_result' / 'x'
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b'stale')

        with pytest.raises(StorageUnavailableError):
            storage_mod.storage.load_bytes('local://case_result/x',
                                           allow_fallback=False)

    def test_load_file_local_scheme_raises(self, local_root, monkeypatch):
        _install_oss(monkeypatch, _FakeOSS())
        dst = local_root / 'case_result' / 'x.bin'
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b'stale')

        with pytest.raises(StorageUnavailableError):
            storage_mod.storage.load_file('local://case_result/x.bin',
                                          str(local_root / 'out.bin'),
                                          allow_fallback=False)

    def test_load_bytes_oss_failure_does_not_read_local_copy(
            self, local_root, monkeypatch):
        """OSS 读失败时不得悄悄读本地降级副本（容器重建即丢）。"""
        st = _install_oss(monkeypatch, _FakeOSS(fail_download=True))
        dst = local_root / 'case_result' / 'k.json'
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b'stale-local')

        with pytest.raises(StorageUnavailableError):
            st.load_bytes('oss://case_result/k.json', allow_fallback=False)

    def test_load_file_oss_failure_does_not_read_local_copy(
            self, local_root, monkeypatch):
        st = _install_oss(monkeypatch, _FakeOSS(fail_download=True))
        dst = local_root / 'case_result' / 'k.bin'
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b'stale-local')
        out = local_root / 'out.bin'

        with pytest.raises(StorageUnavailableError):
            st.load_file('oss://case_result/k.bin', str(out), allow_fallback=False)
        assert not out.exists()


class TestSignatures:
    def test_allow_fallback_defaults_to_true(self):
        for name in ('save_bytes', 'save_file', 'save_stream',
                     'load_bytes', 'load_file'):
            param = inspect.signature(
                getattr(storage_mod.Storage, name)).parameters['allow_fallback']
            assert param.default is True, name
            assert param.kind is inspect.Parameter.KEYWORD_ONLY or \
                param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
