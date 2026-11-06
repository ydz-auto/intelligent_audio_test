# -*- coding: utf-8 -*-
"""INT-1813 / M1：DROP 原始报文 JSON 两列收尾脚本的纯函数单测

只测脚本自己的判定逻辑（不连真库、不连 OSS）：列词表、DDL 合成、门禁在「列存在 /
列已删」两种形态下的行为，以及幂等的判据。脚本实测（pg_dump 副本上的
DROP → VACUUM FULL → ANALYZE 与 `--restore`）见交付评论里的副本取证，不在这里起栈。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                       'drop_raw_payload_columns_int1813.py')


def _load_script():
    spec = importlib.util.spec_from_file_location('int1813_m1', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules['int1813_m1'] = module
    spec.loader.exec_module(module)
    return module


class _FakeCursor:
    """按 SQL 关键词返回预置结果；记录执行过的语句。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.statements = []
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
    """一次 migrate() 只需要一条游标；记录是否被关闭。"""

    def __init__(self, cursor):
        self.autocommit = False
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


_POST_DROP_COLUMNS = [
    ('api_raw_response_uri', 'text'), ('api_raw_response_sha256', 'character'),
    ('api_raw_response_created_at', 'timestamp with time zone'),
    ('api_request_body_uri', 'text'), ('api_request_body_sha256', 'character'),
    ('api_request_body_created_at', 'timestamp with time zone'),
]
_TOAST_PENDING = {'pg_total_relation_size': 311000000, 'pg_relation_size': 66000000,
                  'pg_table_size': 79000000, 'toast_size': 232000000}
_TOAST_RECLAIMED = {'pg_total_relation_size': 28000000, 'pg_relation_size': 26000000,
                    'pg_table_size': 27000000, 'toast_size': 8192}


def test_target_columns_come_from_shared_vocabulary():
    """列词表必须来自 shared/utils/raw_payload.py 的 spec，脚本自己不另写一份。"""
    m = _load_script()
    assert m._target_columns() == ('api_raw_response', 'api_request_body')


def test_drop_ddl_is_single_alter_with_if_exists():
    """两条 DROP 合成一条 ALTER（只拿一次 ACCESS EXCLUSIVE 锁），且带 IF EXISTS 幂等。"""
    m = _load_script()
    ddl = m.build_drop_ddl(['api_raw_response', 'api_request_body'])
    assert ddl == ('ALTER TABLE test_result_dimensions '
                   'DROP COLUMN IF EXISTS api_raw_response, '
                   'DROP COLUMN IF EXISTS api_request_body')
    assert ddl.count('ALTER TABLE') == 1


def test_add_ddl_for_reverse_backfill():
    m = _load_script()
    ddl = m.build_add_ddl(['api_raw_response'])
    assert ddl == ('ALTER TABLE test_result_dimensions '
                   'ADD COLUMN IF NOT EXISTS api_raw_response json')


def test_pending_columns_drives_idempotency():
    m = _load_script()
    both = {'api_raw_response': 'json', 'api_request_body': 'json',
            'api_raw_response_uri': 'text'}
    assert m._pending_columns(both) == ['api_raw_response', 'api_request_body']
    # 列已删 → 没有待删项 → 脚本走 [SKIP]（不重复 DROP / 不重复 VACUUM）
    assert m._pending_columns({'api_raw_response_uri': 'text'}) == []


def test_gate_counts_skips_dropped_columns():
    """列已删时不再拼已不存在的列名（否则 M1 之后门禁复查会报 UndefinedColumn）。"""
    m = _load_script()
    cur = _FakeCursor()
    assert m.gate_counts(cur, {'api_raw_response_uri': 'text',
                               'api_request_body_uri': 'text'}) == {
        'resp': None, 'req': None}
    assert cur.statements == []  # 一条 SQL 都不发


def test_gate_counts_reports_dangling_rows():
    m = _load_script()
    cur = _FakeCursor(responses=[(7,), (0,)])
    result = m.gate_counts(cur, {'api_raw_response': 'json', 'api_request_body': 'json',
                                 'api_raw_response_uri': 'text',
                                 'api_request_body_uri': 'text'})
    assert result == {'resp': 7, 'req': 0}
    assert 'api_raw_response IS NOT NULL' in cur.statements[0][0]
    assert 'api_raw_response_uri IS NULL' in cur.statements[0][0]


def test_recent_write_violations_shape():
    m = _load_script()
    columns = {'api_raw_response': 'json', 'api_request_body': 'json',
               'api_raw_response_uri': 'text', 'api_request_body_uri': 'text'}
    cur = _FakeCursor(responses=[(120,), (0,), (3,)])
    recent = m.recent_write_violations(cur, columns, hours=24)
    assert recent == {'rows': 120, 'violations': {'resp': 0, 'req': 3}, 'window': 24}


def test_pointer_stats_flags_broken_chain():
    m = _load_script()
    columns = {'api_raw_response_uri': 'text', 'api_raw_response_sha256': 'character',
               'api_raw_response_created_at': 'timestamp with time zone',
               'api_request_body_uri': 'text', 'api_request_body_sha256': 'character',
               'api_request_body_created_at': 'timestamp with time zone'}
    cur = _FakeCursor(responses=[(10, 1, 0, None), (10, 0, 0, None)])
    stats = m.pointer_stats(cur, columns)
    assert stats['resp']['uri_without_sha'] == 1
    assert stats['req']['uri_without_sha'] == 0


def test_run_gates_blocks_when_backfill_gate_not_zero():
    """回填门禁未归零 → 任一确认都不放行（卡面前置 2 是硬门禁）。"""
    m = _load_script()
    columns = {'api_raw_response': 'json', 'api_request_body': 'json',
               'api_raw_response_uri': 'text', 'api_request_body_uri': 'text',
               'api_raw_response_sha256': 'character',
               'api_request_body_sha256': 'character',
               'api_raw_response_created_at': 'timestamp with time zone',
               'api_request_body_created_at': 'timestamp with time zone'}
    # gate_counts(resp=5, req=0) → recent(rows=100, resp=0, req=0) → pointer_stats ×2
    cur = _FakeCursor(responses=[(5,), (0,), (100,), (0,), (0,),
                                 (10, 0, 0, None), (10, 0, 0, None)])
    args = type('A', (), {'verify_objects': 0, 'confirm_read_path': True,
                          'strict_24h': False, 'ack_no_recent_traffic': False})()
    failures = m.run_gates(cur, columns, args)
    assert any('回填门禁未归零' in item for item in failures)


def test_run_gates_requires_ack_when_no_recent_traffic():
    """近 24h 无维度行不能自动算「无新写入」：必须操作人明确承认。"""
    m = _load_script()
    columns = {'api_raw_response': 'json', 'api_request_body': 'json',
               'api_raw_response_uri': 'text', 'api_request_body_uri': 'text',
               'api_raw_response_sha256': 'character',
               'api_request_body_sha256': 'character',
               'api_raw_response_created_at': 'timestamp with time zone',
               'api_request_body_created_at': 'timestamp with time zone'}
    cur = _FakeCursor(responses=[(0,), (0,), (0,), (0,), (0,),
                                 (10, 0, 0, None), (10, 0, 0, None)])
    args = type('A', (), {'verify_objects': 0, 'confirm_read_path': True,
                          'strict_24h': False, 'ack_no_recent_traffic': False})()
    failures = m.run_gates(cur, columns, args)
    assert any('ack-no-recent-traffic' in item for item in failures)

    # 承认之后同样的数据应放行
    cur = _FakeCursor(responses=[(0,), (0,), (0,), (0,), (0,),
                                 (10, 0, 0, None), (10, 0, 0, None)])
    args = type('A', (), {'verify_objects': 0, 'confirm_read_path': True,
                          'strict_24h': False, 'ack_no_recent_traffic': True})()
    assert m.run_gates(cur, columns, args) == []


def test_apply_requires_deployed_round_confirmation(monkeypatch):
    """DB 查不出来的一条门禁（C2+A1 部署并跑过一轮）必须由操作人显式确认。

    走真实 parser + ``migrate()``：缺 ``--confirm-deployed-round`` 时返回 4（DO NOT
    动库）——不是自己建一个 parser 断言自己设的默认值。
    """
    m = _load_script()
    cur = _FakeCursor(responses=[
        (1,),                                              # _table_exists
        [('api_raw_response', 'json'), ('api_request_body', 'json')]
        + _POST_DROP_COLUMNS,                             # _existing_columns
        (311000000, 66000000, 79000000, 232000000),        # _sizes
    ])
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    monkeypatch.setattr(m, 'run_gates', lambda *a, **k: [])

    args = m.build_parser().parse_args(['--apply'])
    assert m.migrate(args) == 4
    assert conn.closed is True
    # 一条 DDL 都没发（只有元数据 / 体积查询）
    assert not any('ALTER TABLE' in sql for sql, _ in cur.statements)


def test_parser_flags_do_not_drift():
    """开关名漂移会让运维照文档执行的命令直接报错，用真 parser 锁住常用组合。"""
    m = _load_script()
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-deployed-round', '--confirm-read-path', '--strict-24h'])
    assert args.apply and args.confirm_deployed_round and args.confirm_read_path
    assert args.strict_24h
    assert m.build_parser().parse_args(['--apply']).confirm_deployed_round is False


def test_vacuum_still_pending_uses_toast_size():
    """P2-1 判据：列已删但 TOAST 仍是删列前的量级 → 上次 VACUUM FULL 没跑成功。"""
    m = _load_script()
    assert m.vacuum_still_pending(_TOAST_PENDING) is True
    assert m.vacuum_still_pending(_TOAST_RECLAIMED) is False
    assert m.vacuum_still_pending({'toast_size': 0}) is False


def test_gate_after_drop_still_prints_pointer_stats(monkeypatch, capsys):
    """P3-1：删列后 ``--gate`` 仍打印门禁（N/A）+ 指针分布并 exit 0。

    只读复查不该被 idle in transaction 拦下，也不该因缺 ``--confirm-read-path`` 返回 1。
    """
    m = _load_script()
    cur = _FakeCursor(responses=[
        (0,),                       # recent_write_violations: 窗口内行数
        (50051, 0, 0, None),        # pointer_stats resp
        (42096, 0, 0, None),        # pointer_stats req
    ])
    args = m.build_parser().parse_args(['--gate'])
    args.apply = False
    code = m._after_drop(_FakeConn(cur), cur, dict(_POST_DROP_COLUMNS),
                         args, dict(_TOAST_RECLAIMED), 900000)
    out = capsys.readouterr().out
    assert code == 0
    assert '[GATE-2]' in out and 'N/A' in out
    assert '50051' in out and '42096' in out      # 指针分布两条都打出来了
    assert '[GATE-3]' in out and '两列已删' in out  # 空跑窗口也 N/A，不误判失败
    # 只读路径不查锁风险（没有 pg_stat_activity 查询）
    assert not any('pg_stat_activity' in sql for sql, _ in cur.statements)


def test_apply_after_drop_fails_when_toast_not_reclaimed(monkeypatch, capsys):
    """P2-1：VACUUM FULL 被超时顶掉后照提示重跑 --apply，必须 exit≠0 并指向 --force-vacuum。"""
    m = _load_script()
    cur = _FakeCursor(responses=[(10,), (50051, 0, 0, None), (42096, 0, 0, None)])
    monkeypatch.setattr(m, 'vacuum_full', lambda *a, **k: pytest.fail('不该重跑 VACUUM FULL'))
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-deployed-round', '--confirm-read-path', '--strict-24h'])
    code = m._after_drop(_FakeConn(cur), cur, dict(_POST_DROP_COLUMNS),
                         args, dict(_TOAST_PENDING), 900000)
    out = capsys.readouterr().out
    assert code == 3
    assert 'TOAST 未回收' in out and '--force-vacuum' in out


def test_apply_after_drop_force_vacuum_reclaims_and_verifies(monkeypatch):
    """--force-vacuum 是续跑路径：补跑 VACUUM FULL + ANALYZE，回收后 exit 0。"""
    m = _load_script()
    cur = _FakeCursor(responses=[
        (10,), (50051, 0, 0, None), (42096, 0, 0, None),   # 门禁
        [],                                                # lock_risks：无高风险会话
        (28000000, 26000000, 27000000, 8192),              # _sizes(after) 已回收
    ])
    calls = []
    monkeypatch.setattr(m, 'vacuum_full', lambda conn, timeout: calls.append(('vacuum', timeout)))
    monkeypatch.setattr(m, 'analyze', lambda conn: calls.append(('analyze', None)))
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-deployed-round', '--confirm-read-path',
         '--strict-24h', '--force-vacuum'])
    code = m._after_drop(_FakeConn(cur), cur, dict(_POST_DROP_COLUMNS),
                         args, dict(_TOAST_PENDING), 900000)
    assert code == 0
    assert calls == [('vacuum', 900000), ('analyze', None)]


def test_run_ddl_uses_and_resets_statement_timeout():
    """P3-3：``--statement-timeout-ms`` 不再是死配置——DDL 前设置、跑完复位。"""
    m = _load_script()
    cur = _FakeCursor()
    m._run_ddl(cur, 'ALTER TABLE t DROP COLUMN IF EXISTS c', 5000, 30000)
    sqls = [sql for sql, _ in cur.statements]
    assert sqls[0] == 'SET lock_timeout = 5000'
    assert 'SET statement_timeout = 30000' in sqls
    assert sqls[-1] == 'SET statement_timeout = 0'

    cur = _FakeCursor()
    m._run_ddl(cur, 'ALTER TABLE t DROP COLUMN IF EXISTS c', 5000)
    assert not any('statement_timeout' in sql for sql, _ in cur.statements)


@pytest.mark.parametrize('sizes,expected', [
    ({'pg_total_relation_size': 341475328, 'pg_relation_size': 94289920,
      'pg_table_size': 335872000, 'toast_size': 241532928},
     '325.66 MB'),
])
def test_size_formatting(sizes, expected, capsys):
    m = _load_script()
    m.print_sizes('BEFORE', sizes)
    out = capsys.readouterr().out
    assert expected in out
    assert 'pg_total_relation_size' in out and 'toast_size' not in out
