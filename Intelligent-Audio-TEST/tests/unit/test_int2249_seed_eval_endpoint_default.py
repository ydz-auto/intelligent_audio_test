# -*- coding: utf-8 -*-
"""INT-2249：评估维度种子端点缺省与 compose 同源，不再回落死端点 100.70.20.135:8888。

背景：10 个维度种子脚本原先 `EVAL_SERVER_URL` 缺省硬编码为历史外部端点
`http://100.70.20.135:8888`（已下线）。compose 引导链会透传 env 所以 docker 路径
没事，但脱离 compose 手工跑种子（脚本 docstring 就写着这么用）会把整批维度写成
死端点，评估阶段 Connection refused。

本文件钉死四件事（不连库）：
1. 10 个种子脚本源码零 `100.70.20.135` 命中，统一走 shared/config/eval_endpoint.py；
2. 无 EVAL_SERVER_URL（或空串）时每个脚本模块级 API_URL = 缺省端点；
3. 该缺省与 docker/docker-compose.yml 的 db_bootstrap.EVAL_SERVER_URL 缺省一致
   （两处漂移即红）；
4. 引导链 db_bootstrap 把 EVAL_SERVER_URL 原样透传给种子子进程；
5. .env.example 不再宣称旧端点是不设时的默认。
"""
import importlib.util
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# tests/unit/conftest.py 的全局日志 worker 夹具在 teardown 导入
# shared.utils.log_handler → shared.infrastructure.config，模块 import 期校验配置
# 非空（不触网）；先序 setdefault 与其它单测一致，避免 teardown 报缺键。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
# 引导链 _prepare_env 需要 DATABASE_URI（映射到子进程 DATABASE_URL）
os.environ.setdefault('DATABASE_URI', 'postgresql://u:p@localhost:1/unused')

BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                              'db_bootstrap_entrypoint.py')
COMPOSE_PATH = os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.yml')
ENV_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, '.env.example')

# 引导链步骤表里出现 / 需要保持一致的全部维度种子脚本
SEED_FILES = [
    'scripts/migrations/202609/seed_env_sound_judge.py',
    'scripts/migrations/202609/seed_interruption_dimensions.py',
    'scripts/migrations/202609/seed_llm_judge_dimension.py',
    'scripts/migrations/202609/seed_noise_latency.py',
    'scripts/migrations/202609/seed_non_interactive_latency.py',
    'scripts/migrations/202609/seed_reject_judge.py',
    'scripts/migrations/202609/seed_xiaoyi_dimensions.py',
    'scripts/migrations/202610/seed_env_judge.py',
    'scripts/migrations/202610/seed_interruption_v2.py',
    'scripts/migrations/202610/seed_turn_eval.py',
]

LEGACY_ENDPOINT = '100.70.20.135'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _seed_path(rel):
    return os.path.join(PROJECT_ROOT, *rel.split('/'))


def _compose_default_eval_url():
    """从 base compose 的 db_bootstrap env 里取 EVAL_SERVER_URL 缺省表达式。"""
    with open(COMPOSE_PATH, encoding='utf-8') as fh:
        text = fh.read()
    match = re.search(r'EVAL_SERVER_URL:\s*\$\{EVAL_SERVER_URL:-([^}]+)\}', text)
    assert match, 'docker-compose.yml 未找到 db_bootstrap 的 EVAL_SERVER_URL 缺省'
    return match.group(1).strip()


def test_default_matches_compose():
    from shared.config.eval_endpoint import DEFAULT_EVAL_SERVER_URL

    assert DEFAULT_EVAL_SERVER_URL == _compose_default_eval_url()
    assert LEGACY_ENDPOINT not in DEFAULT_EVAL_SERVER_URL


def test_resolve_eval_server_url_env_override_and_fallback():
    from shared.config.eval_endpoint import (
        DEFAULT_EVAL_SERVER_URL,
        resolve_eval_server_url,
    )

    assert resolve_eval_server_url({}) == DEFAULT_EVAL_SERVER_URL
    assert resolve_eval_server_url({'EVAL_SERVER_URL': ''}) == DEFAULT_EVAL_SERVER_URL
    assert resolve_eval_server_url({'EVAL_SERVER_URL': '   '}) == DEFAULT_EVAL_SERVER_URL
    assert (resolve_eval_server_url({'EVAL_SERVER_URL': 'http://custom:5000'})
            == 'http://custom:5000')


def test_seed_scripts_have_no_legacy_endpoint_and_use_shared_helper():
    for rel in SEED_FILES:
        with open(_seed_path(rel), encoding='utf-8') as fh:
            source = fh.read()
        assert LEGACY_ENDPOINT not in source, f'{rel} 仍残留旧端点 {LEGACY_ENDPOINT}'
        assert 'resolve_eval_server_url()' in source, (
            f'{rel} 未经 shared/config/eval_endpoint.py 取端点')


def test_seed_modules_default_to_compose_endpoint_without_env(monkeypatch):
    """无 EVAL_SERVER_URL 时，10 个脚本模块级 API_URL 都落到 compose 同源缺省。"""
    from shared.config.eval_endpoint import DEFAULT_EVAL_SERVER_URL

    monkeypatch.delenv('EVAL_SERVER_URL', raising=False)
    for idx, rel in enumerate(SEED_FILES):
        module = _load(_seed_path(rel), f'int2249_seed_unset_{idx}')
        assert module.API_URL == DEFAULT_EVAL_SERVER_URL, rel


def test_seed_module_respects_explicit_env(monkeypatch):
    """显式 EVAL_SERVER_URL 仍然优先（隔离栈指向本栈 mock 的路径不变）。"""
    monkeypatch.setenv('EVAL_SERVER_URL', 'http://mock_eval_server_judge:5097')
    module = _load(_seed_path('scripts/migrations/202610/seed_turn_eval.py'),
                   'int2249_seed_env_override')
    assert module.API_URL == 'http://mock_eval_server_judge:5097'


def test_bootstrap_passes_eval_server_url_to_seed_subprocess(monkeypatch):
    """引导链 _prepare_env 复制 os.environ：compose 注入的端点会传给种子子进程。"""
    monkeypatch.setenv('EVAL_SERVER_URL', 'http://host.docker.internal:5097')

    bootstrap = _load(BOOTSTRAP_PATH, 'int2249_db_bootstrap')
    env = bootstrap._prepare_env({
        'lock_timeout_ms': 5000,
        'statement_timeout_ms': 300000,
        'idle_in_tx_timeout_ms': 60000,
    })
    assert env['EVAL_SERVER_URL'] == 'http://host.docker.internal:5097'


def test_bootstrap_leaves_env_unset_for_seed_script_fallback(monkeypatch):
    """env 未透传时引导链不注入端点：种子脚本缺省即 compose 缺省，两路同值。"""
    from shared.config.eval_endpoint import DEFAULT_EVAL_SERVER_URL

    monkeypatch.delenv('EVAL_SERVER_URL', raising=False)
    bootstrap = _load(BOOTSTRAP_PATH, 'int2249_db_bootstrap_noenv')
    env = bootstrap._prepare_env({
        'lock_timeout_ms': 5000,
        'statement_timeout_ms': 300000,
        'idle_in_tx_timeout_ms': 60000,
    })
    assert 'EVAL_SERVER_URL' not in env
    assert DEFAULT_EVAL_SERVER_URL == _compose_default_eval_url()


def test_env_example_does_not_declare_legacy_default():
    with open(ENV_EXAMPLE_PATH, encoding='utf-8') as fh:
        text = fh.read()
    assert f'不设则默认 http://{LEGACY_ENDPOINT}:8888' not in text
    assert 'shared/config/eval_endpoint.py' in text
