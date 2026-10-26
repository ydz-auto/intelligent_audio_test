# -*- coding: utf-8 -*-
"""INT-1973 音频域并发扩容 5→20：配置口径 + server.py 读取路径回归。

锁定四点：
- concurrency_config.json 的 grpc.audio_service_workers 为 20
- config_manager 两个兜底分支（配置文件缺失 / JSON 解析失败）同为 20
- server.py 起服时 DB 连接池按 20 初始化（与线程池同口径，上限 20+overflow）
- server.py 读取线程池大小的函数内默认值为 20（配置文件缺该键时不回落到 5）
"""
import json
import os
import sys
import tempfile
import types

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1973_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils import config_manager as cm_mod
from shared.utils.config_manager import ConfigManager
from audio_service.interfaces.grpc import server as srv


EXPECTED_WORKERS = 20
EXPECTED_POOL_SIZE = 20


# ---- 配置口径 ----

def test_concurrency_config_sets_audio_workers_20():
    """共享并发配置：音频 gRPC 线程池 20（原 5）。"""
    with open(cm_mod.config_manager.config_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['grpc']['audio_service_workers'] == EXPECTED_WORKERS


def _load_fallback_config(config_path):
    """绕过单例，直接跑 ConfigManager.load_config() 取兜底分支结果。"""
    instance = object.__new__(ConfigManager)
    instance.config = {}
    instance.config_path = config_path
    instance.flask_config = None
    instance.load_config()
    return instance


@pytest.mark.parametrize('case', ['file_missing', 'json_decode_error'])
def test_config_manager_fallbacks_use_20(tmp_path, case):
    """两个兜底分支都必须给 20，否则缺配置文件的部署会退回 5 线程。"""
    if case == 'file_missing':
        path = str(tmp_path / 'no_such_concurrency_config.json')
    else:
        path = tmp_path / 'broken_concurrency_config.json'
        path.write_text('{ this is not json', encoding='utf-8')
        path = str(path)

    instance = _load_fallback_config(path)
    assert instance.get_config('grpc')['audio_service_workers'] == EXPECTED_WORKERS


# ---- server.py 读取路径 ----

class _FakeServer:
    def __init__(self, executor=None):
        self.executor = executor
        self.bound_address = None
        self.started = False

    def add_insecure_port(self, address):
        self.bound_address = address
        return 0

    def start(self):
        self.started = True


def _run_start_server(monkeypatch, get_value):
    """在不绑定真实端口的前提下跑一遍 start_grpc_server，返回观测到的落点。"""
    seen = {}

    from shared.models import database as dbmod

    def fake_init_db(pool_size=3):
        seen['pool_size'] = pool_size
        return None

    def fake_server(executor=None, options=None, interceptors=None):
        seen['max_workers'] = executor._max_workers
        seen['options'] = options
        return _FakeServer(executor)

    class _FakeCleaner:
        def start(self):
            seen['cleaner_started'] = True

    class _FakeAudioEngine:
        def init_driver(self):
            pass

    fake_engine_module = types.ModuleType('audio_service.infrastructure.audio.audio_engine')
    fake_engine_module.audio_service = _FakeAudioEngine()

    monkeypatch.setattr(srv, '_configure_pydub_ffmpeg', lambda: None)
    monkeypatch.setattr(dbmod, 'init_db', fake_init_db)
    monkeypatch.setattr(srv.grpc, 'server', fake_server)
    monkeypatch.setattr(cm_mod.config_manager, 'get_value', get_value)
    monkeypatch.setitem(sys.modules,
                        'audio_service.infrastructure.audio.audio_engine', fake_engine_module)

    import audio_service.infrastructure.persistence.soft_delete_cleaner as cleaner_mod
    monkeypatch.setattr(cleaner_mod, 'get_cleaner', lambda: _FakeCleaner())

    # servicer 构造与 proto 注册不影响本次观测，替换为无副作用桩
    for name in ('AudioServiceServicer', 'PlaybackServiceServicer',
                 'AudioConfigServiceServicer', 'RenderServiceServicer'):
        monkeypatch.setattr(srv, name, lambda: object())
    for name in ('add_AudioServiceServicer_to_server', 'add_PlaybackServiceServicer_to_server',
                 'add_AudioConfigServiceServicer_to_server', 'add_RenderServiceServicer_to_server'):
        monkeypatch.setattr(srv.audio_grpc, name, lambda servicer, server: None)

    server = srv.start_grpc_server(port=0)
    seen['started'] = server.started
    return seen


def test_start_server_reads_workers_from_config(monkeypatch):
    """配置文件给出 20 时，线程池 max_workers 取配置值，DB 池同口径 20。"""
    calls = []

    def fake_get_value(section, key, default=None):
        calls.append((section, key, default))
        return 20

    seen = _run_start_server(monkeypatch, fake_get_value)

    assert calls[0][:2] == ('grpc', 'audio_service_workers')
    assert seen['max_workers'] == 20
    assert seen['pool_size'] == EXPECTED_POOL_SIZE
    assert seen['cleaner_started'] is True
    assert seen['started'] is True


def test_start_server_worker_default_is_20(monkeypatch):
    """配置文件缺该键时，server.py 的函数内默认值必须是 20（不是旧的 5）。"""
    captured = {}

    def fake_get_value(section, key, default=None):
        captured['default'] = default
        return default

    seen = _run_start_server(monkeypatch, fake_get_value)

    assert captured['default'] == EXPECTED_WORKERS
    assert seen['max_workers'] == EXPECTED_WORKERS


def test_pool_size_constant_matches_worker_scale():
    """连接池与线程池同口径：模块常量锁定 20，且 overflow=5 时上限 25 条。"""
    assert srv.AUDIO_DB_POOL_SIZE == EXPECTED_POOL_SIZE
    assert srv.AUDIO_GRPC_WORKERS_DEFAULT == EXPECTED_WORKERS

    from shared.models.database import _pool_kwargs
    kw = _pool_kwargs('postgresql://u:p@localhost:5432/audit', srv.AUDIO_DB_POOL_SIZE)
    assert kw['pool_size'] == EXPECTED_POOL_SIZE
    assert kw['pool_size'] + kw['max_overflow'] == 25
