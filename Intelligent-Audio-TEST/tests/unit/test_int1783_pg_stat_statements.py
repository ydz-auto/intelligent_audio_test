# -*- coding: utf-8 -*-
"""INT-1783：PG 观测基线（pg_stat_statements + 慢 SQL 阈值）静态守卫。

背景：卡面要求「仓库内落地配置 + 扩展安装进引导链」，不能只改运行中的容器。
重启类改动一旦漂移（有人把 command 删了、或把新步骤挪到统计兜底之后），下次
recreate 就静默丢掉观测能力，而这类丢失没有任何运行时信号。本文件把三件事钉死：

1. docker/docker-compose.yml 的 postgres 服务以 `-c` 内联加载
   shared_preload_libraries=pg_stat_statements、pg_stat_statements.max=5000、
   pg_stat_statements.track=all、log_min_duration_statement=500；
2. 本卡不动 shared_buffers / work_mem（档 5 未批准，改它们是越权）；
3. 迁移脚本进引导链且带 --apply，且仍排在 INT-1741 统计兜底（必须最后一步）
   之前；脚本只发只读 SELECT / SHOW 与 CREATE EXTENSION，默认 dry-run，
   已安装时 [SKIP] 不发任何写入。

DB：无（文本 + 假连接）。
"""
import importlib.util
import os
import sys

import pytest
import psycopg2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202610/'
                  'add_pg_stat_statements_int1783.py')
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_COMPOSE_PATH = os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.yml')
_ANALYZE_REL = ('scripts/migrations/202610/'
                'analyze_stale_statistics_int1741.py')

# 模块 import 期只校验配置非空，不连库
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_script = _load(_MIGRATION, 'int1783_pg_stat_statements')
_bootstrap = _load(_BOOTSTRAP_PATH, 'int1783_db_bootstrap')


def _compose_text():
    with open(_COMPOSE_PATH, encoding='utf-8') as fh:
        return fh.read()


def _postgres_block():
    """截取 postgres 服务的 YAML 片段（到下一个顶层 service 前）。"""
    text = _compose_text()
    start = text.index('\n  postgres:')
    rest = text[start + 1:]
    lines = rest.splitlines()
    block = [lines[0]]
    for line in lines[1:]:
        # 下一个同级 service（两个空格缩进 + 非空 + 冒号）
        if line.startswith('  ') and not line.startswith('    ') and line.strip():
            break
        block.append(line)
    return '\n'.join(block)


# ---------------------------------------------------------------- compose 配置

def test_postgres_loads_pg_stat_statements_at_startup():
    block = _postgres_block()
    assert 'shared_preload_libraries=pg_stat_statements' in block, \
        'postgres 服务未在 command 里预加载 pg_stat_statements（运行期无法补载）'
    assert 'pg_stat_statements.max=5000' in block
    assert 'pg_stat_statements.track=all' in block


def test_postgres_slow_statement_threshold_is_500ms():
    assert 'log_min_duration_statement=500' in _postgres_block()


def test_command_starts_with_postgres_for_entrypoint():
    """官方镜像 entrypoint 只对「首参数是 postgres」的 command 走正常启动路径。"""
    block = _postgres_block()
    idx = block.index('command:')
    tail = block[idx:].splitlines()
    first_arg = tail[1].strip().lstrip('-').strip()
    assert first_arg == 'postgres'


def test_memory_settings_untouched():
    """档 5 未批准：不得借本卡改 shared_buffers / work_mem。"""
    block = _postgres_block()
    # 注释里会解释「没改」，只对生效的 YAML 行做断言
    effective = '\n'.join(line for line in block.splitlines()
                          if line.strip() and not line.strip().startswith('#'))
    assert 'shared_buffers' not in effective
    assert 'work_mem' not in effective


def test_postgres_log_is_bounded():
    """500ms 阈值会放大库日志量，postgres 服务必须有轮转上限。"""
    block = _postgres_block()
    assert 'max-size' in block and 'max-file' in block


# ---------------------------------------------------------------- 引导链

def test_bootstrap_chain_has_step_with_apply():
    steps = [step for step in _bootstrap.BOOTSTRAP_STEPS
             if step[1] == _MIGRATION_REL]
    assert steps, f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：新库/隔离库永远不会有该扩展'
    assert '--apply' in steps[0], f'{_MIGRATION_REL} 在引导链中缺少 --apply（只预览不执行）'


def test_bootstrap_step_runs_before_analyze():
    """在统计兜底之前：CREATE EXTENSION 也是 DDL，放后面会让 ANALYZE 结果过期。"""
    rels = [step[1] for step in _bootstrap.BOOTSTRAP_STEPS]
    assert rels.index(_MIGRATION_REL) < rels.index(_ANALYZE_REL)
    assert rels[-1] == _ANALYZE_REL, 'INT-1741 统计兜底必须仍是引导链最后一步'


# ---------------------------------------------------------------- 脚本行为

class _FakeCursor:
    def __init__(self, store):
        self.store = store
        self._last = None

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split())
        self.store['executed'].append(text)
        low = text.lower()
        if low.startswith('create extension'):
            self.store['version'] = '1.10'
            self._last = None
        elif 'pg_available_extensions' in low:
            self._last = (self.store['available'],)
        elif 'pg_extension' in low:
            version = self.store['version']
            self._last = (version,) if version else None
        elif low.startswith('show '):
            name = text.split()[-1]
            self._last = (self.store['settings'].get(name),)
        elif 'count(*)' in low:
            if self.store['view_queryable']:
                self._last = (7,)
            else:
                # 服务端未预加载时 PG 抛的正是这个错误（psycopg2.Error 子类）
                raise psycopg2.Error(
                    'pg_stat_statements must be loaded via '
                    'shared_preload_libraries')
        else:
            self._last = None

    def fetchone(self):
        return self._last

    def close(self):
        pass


class _FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _FakeCursor(self.store)

    def rollback(self):
        pass

    def close(self):
        pass


def _store(**overrides):
    store = {
        'available': '1.10',
        'version': None,
        'view_queryable': True,
        'executed': [],
        'settings': {
            'shared_preload_libraries': 'pg_stat_statements',
            'pg_stat_statements.max': '5000',
            'pg_stat_statements.track': 'all',
            'log_min_duration_statement': '500ms',
        },
    }
    store.update(overrides)
    return store


def _run(monkeypatch, store, apply_changes):
    monkeypatch.setattr(_script, '_connect', lambda: _FakeConn(store))
    return _script.migrate(dry_run=not apply_changes)


def _writes(store):
    forbidden = ('ALTER', 'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE',
                 'VACUUM')
    return [q for q in store['executed']
            if q.upper().startswith(forbidden)]


def test_default_dry_run_issues_no_create(monkeypatch):
    store = _store()
    assert _run(monkeypatch, store, apply_changes=False) == 0
    assert not [q for q in store['executed']
                if q.lower().startswith('create extension')]
    assert not _writes(store)


def test_apply_creates_extension_once(monkeypatch):
    store = _store()
    assert _run(monkeypatch, store, apply_changes=True) == 0
    creates = [q for q in store['executed']
               if q.lower().startswith('create extension')]
    assert creates == [
        'CREATE EXTENSION IF NOT EXISTS pg_stat_statements']
    assert not _writes(store)


def test_idempotent_when_already_installed(monkeypatch):
    store = _store(version='1.10')
    assert _run(monkeypatch, store, apply_changes=True) == 0
    assert not [q for q in store['executed']
                if q.lower().startswith('create extension')]
    assert not _writes(store)


def test_missing_available_extension_fails_loudly(monkeypatch):
    """镜像不带 contrib 时必须报错，不能静默跳过（否则观测基线永远建不起来）。"""
    store = _store(available=None)
    assert _run(monkeypatch, store, apply_changes=True) == 1
    assert not [q for q in store['executed']
                if q.lower().startswith('create extension')]


def test_view_unqueryable_only_warns(monkeypatch, capsys):
    """服务端未预加载时视图不可查询，属 docker 侧配置问题，引导链只 WARN。"""
    store = _store(view_queryable=False,
                   settings={'shared_preload_libraries': ''})
    assert _run(monkeypatch, store, apply_changes=True) == 0
    out = capsys.readouterr().out
    assert '[WARN]' in out
