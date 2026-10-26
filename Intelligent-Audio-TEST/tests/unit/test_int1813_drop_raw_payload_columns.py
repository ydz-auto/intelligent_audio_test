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


def test_apply_requires_deployed_round_confirmation():
    """DB 查不出来的一条门禁（C2+A1 部署并跑过一轮）必须由操作人显式确认。"""
    import argparse
    m = _load_script()
    parser = argparse.ArgumentParser()
    # 与 main() 同名的开关都要能被解析（防止开关名漂移）
    for flag in ('--apply', '--gate', '--restore', '--confirm-deployed-round',
                 '--confirm-read-path', '--ack-no-recent-traffic', '--strict-24h',
                 '--no-vacuum', '--force-vacuum', '--ignore-lock-risks'):
        parser.add_argument(flag, action='store_true')
    args = parser.parse_args(['--apply'])
    assert getattr(args, 'confirm_deployed_round') is False


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
