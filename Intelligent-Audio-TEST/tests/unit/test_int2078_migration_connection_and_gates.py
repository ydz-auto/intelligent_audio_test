# -*- coding: utf-8 -*-
"""INT-2078 / 迁移链缺陷：fix_users_email_unique 连错库风险 + drop_apis_api_url 缺停用确认门禁

只测脚本自己的判定逻辑（不连真库）：
- ``fix_users_email_unique`` 的连接串解析（DATABASE_URL 优先 / DATABASE_URI 兜底 /
  两者都缺 → exit 1，不静默连 localhost 默认库）；
- ``drop_apis_api_url`` 的 argparse 开关、``--apply`` 缺 ``--confirm-read-path``
  拒绝执行（exit 4）、``--gate`` 只读门禁、列已删幂等 SKIP。

脚本实测（隔离库 int2078_verify 上的红-绿一遍）见交付评论里的取证，不在这里起栈。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:5432/db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_EMAIL_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                             'fix_users_email_unique.py')
_API_URL_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                               'drop_apis_api_url.py')


def _load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ 连接串解析（两脚本共用口径）

@pytest.mark.parametrize('script_path,name', [
    (_EMAIL_SCRIPT, 'int2078_email'),
    (_API_URL_SCRIPT, 'int2078_apiurl'),
], ids=['fix_users_email_unique', 'drop_apis_api_url'])
def test_resolve_database_url_prefers_database_url(monkeypatch, script_path, name):
    """DATABASE_URL 优先于 DATABASE_URI。"""
    m = _load_script(script_path, name)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://a:b@host:15432/target')
    monkeypatch.setenv('DATABASE_URI', 'postgresql://x:y@host:5432/wrong')
    assert m.resolve_database_url() == 'postgresql://a:b@host:15432/target'


@pytest.mark.parametrize('script_path,name', [
    (_EMAIL_SCRIPT, 'int2078_email'),
    (_API_URL_SCRIPT, 'int2078_apiurl'),
], ids=['fix_users_email_unique', 'drop_apis_api_url'])
def test_resolve_database_url_falls_back_to_uri(monkeypatch, script_path, name):
    """DATABASE_URL 缺失时回落 DATABASE_URI（引导链把 DATABASE_URL 从 DATABASE_URI setdefault）。"""
    m = _load_script(script_path, name)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_URI', 'postgresql://x:y@host:15432/iso')
    assert m.resolve_database_url() == 'postgresql://x:y@host:15432/iso'


@pytest.mark.parametrize('script_path,name', [
    (_EMAIL_SCRIPT, 'int2078_email'),
    (_API_URL_SCRIPT, 'int2078_apiurl'),
], ids=['fix_users_email_unique', 'drop_apis_api_url'])
def test_resolve_database_url_exits_when_both_missing(monkeypatch, script_path, name, capsys):
    """两者都缺 → exit 1 + 报错，绝不静默连 localhost 默认库。"""
    m = _load_script(script_path, name)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URI', raising=False)
    with pytest.raises(SystemExit) as exc:
        m.resolve_database_url()
    assert exc.value.code == 1
    out = capsys.readouterr().err
    assert '未设置 DATABASE_URL / DATABASE_URI' in out


# ------------------------------------------------------------------ drop_apis_api_url 门禁

class _FakeCursor:
    """按预置响应队列返回结果；记录执行过的语句。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.statements = []
        self.rowcount = 0
        self._last = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        self._last = self.responses.pop(0) if self.responses else None

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self.autocommit = False
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_drop_api_url_parser_flags_do_not_drift():
    """开关名漂移会让运维照文档执行的命令直接报错，用真 parser 锁住常用组合。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    args = m.build_parser().parse_args(['--apply', '--confirm-read-path'])
    assert args.apply and args.confirm_read_path
    assert not args.gate and not args.dry_run
    args = m.build_parser().parse_args(['--gate'])
    assert args.gate and not args.apply
    args = m.build_parser().parse_args(['--dry-run'])
    assert args.dry_run and not args.apply
    assert m.build_parser().parse_args(['--apply']).confirm_read_path is False


def test_drop_api_url_apply_without_confirm_rejects(monkeypatch):
    """--apply 缺 --confirm-read-path → return 4，一条 DDL 都不发。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    cur = _FakeCursor(responses=[(1,)])          # column_exists: api_url 存在
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    args = m.build_parser().parse_args(['--apply'])
    assert m.migrate(args) == 4
    assert conn.closed is True
    assert not any('DROP COLUMN' in sql or 'UPDATE apis' in sql
                   for sql, _ in cur.statements)


def test_drop_api_url_gate_is_readonly(monkeypatch, capsys):
    """--gate：门禁报告 + 回填预览，不执行回填 / DROP。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    cur = _FakeCursor(responses=[(1,), (7,)])
    # ① migrate 的 column_exists → ② run_gates 的待回填 count
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    args = m.build_parser().parse_args(['--gate'])
    assert m.migrate(args) == 0
    out = capsys.readouterr().out
    assert '待回填 7 行' in out
    assert '--confirm-read-path' in out
    assert not any('DROP COLUMN' in sql or 'UPDATE apis' in sql
                   for sql, _ in cur.statements)
    assert conn.closed is True


def test_drop_api_url_apply_with_confirm_executes(monkeypatch, capsys):
    """--apply --confirm-read-path：回填 → DROP → 复查列不存在 → 0。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    cur = _FakeCursor(responses=[(1,), None, None, None])
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    args = m.build_parser().parse_args(['--apply', '--confirm-read-path'])
    assert m.migrate(args) == 0
    sqls = [sql for sql, _ in cur.statements]
    assert any('UPDATE apis' in sql and 'DROP COLUMN api_url' not in sql
               for sql in sqls)                 # 先回填
    assert any('ALTER TABLE apis DROP COLUMN api_url' in sql for sql in sqls)
    out = capsys.readouterr().out
    assert '[VERIFY] apis.api_url 已不存在 → OK' in out


def test_drop_api_url_apply_after_column_gone_is_idempotent_skip(monkeypatch, capsys):
    """列已删后再跑 --apply --confirm-read-path：全 SKIP，exit 0。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    cur = _FakeCursor(responses=[None, None])   # 两处 column_exists 都返回不存在
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    args = m.build_parser().parse_args(['--apply', '--confirm-read-path'])
    assert m.migrate(args) == 0
    out = capsys.readouterr().out
    assert '[SKIP] apis.api_url 已删除' in out
    assert not any('UPDATE apis' in sql or 'DROP COLUMN' in sql
                   for sql, _ in cur.statements)


def test_drop_api_url_recheck_failure_returns_3(monkeypatch, capsys):
    """DROP 后复查列仍在 → return 3（执行后校验失败）。"""
    m = _load_script(_API_URL_SCRIPT, 'int2078_apiurl')
    cur = _FakeCursor(responses=[(1,), None, None, (1,)])
    # ① 前置 column_exists 存在 → ② 回填 → ③ DROP → ④ 复查 column_exists 仍存在
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    args = m.build_parser().parse_args(['--apply', '--confirm-read-path'])
    assert m.migrate(args) == 3
    out = capsys.readouterr().out
    assert '[FAIL] 复查：apis.api_url 仍存在' in out
