# -*- coding: utf-8 -*-
"""INT-135 回归：存量对比报告 audios 清洗脚本的去重口径与幂等性。

scripts/migrations/202610/cleanup_compare_report_audios_dup.py 承担
INT-134 修复前落库数据的对象级去重清洗。本测试锁定其纯函数行为：
规范化 JSON 判同（键序无关）、保首见保顺序、合法多位置不误删、
噪声段（末尾唯一）不受影响、扫描聚合统计正确、清洗后天然幂等。
清洗结果须与修复后生成侧布局等价（compare 每音频恰好一次），
该等价性由隔离端到端验证（dedup(buggy) == 修复后 _build_audios_list
输出）覆盖，本文件不重复拉起 report_service。
"""
import importlib.util
import os
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[2]
           / 'scripts' / 'migrations' / '202610' / 'cleanup_compare_report_audios_dup.py')
_spec = importlib.util.spec_from_file_location('int135_cleanup_script', _SCRIPT)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def _key(item):
    return script.canonical_key(item)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows


class _FakeConn:
    """SCAN_SQL -> report_cases 行；DELETED_SQL -> 已删除报告计数。"""

    def __init__(self, rows, deleted_count=0):
        self._rows = rows
        self._deleted = deleted_count

    def execute(self, sql, params=None):
        if 'FROM report_cases' in str(sql):
            return _FakeResult(self._rows)
        return _FakeResult(self._deleted)


def test_dedup_adjacent_duplicate_keeps_first_and_order():
    """缺陷形态（同 dict 紧邻两份）去重后每项一次，保首见保顺序。"""
    x = {'id': 11, 'spl': 70}
    y = {'id': 12, 'spl': 70}
    noise = {'id': 13, 'spl': 40}
    kept, removed = script.dedup_audios([x, x, y, y, noise])
    assert removed == 2
    assert kept == [x, y, noise]
    assert [k['id'] for k in kept] == [11, 12, 13], '噪声保持末尾一次'


def test_dedup_key_order_insensitive():
    """判同按规范化 JSON（sort_keys）：仅键序不同的 dict 视为同一项。"""
    a = {'a': 1, 'b': 2}
    b = {'b': 2, 'a': 1}
    kept, removed = script.dedup_audios([a, b])
    assert removed == 1
    assert kept == [a], '保留首见项'


def test_dedup_keeps_legal_multi_position_items():
    """合法多位置（同 audio_id、不同 timeline/spl/round）不误删。"""
    p1 = {'id': 999, 'timelineStart': 0.0, 'timelineEnd': 3.0, 'spl': 70}
    p2 = {'id': 999, 'timelineStart': 6.0, 'timelineEnd': 9.0, 'spl': 75}
    kept, removed = script.dedup_audios([p1, p2])
    assert removed == 0
    assert kept == [p1, p2]


def test_dedup_idempotent():
    """幂等：对去重结果再次去重为零移除、结果不变。"""
    x = {'id': 1, 'v': 'a'}
    y = {'id': 2, 'v': 'b'}
    kept, removed = script.dedup_audios([x, x, y])
    kept2, removed2 = script.dedup_audios(kept)
    assert removed == 1 and removed2 == 0
    assert kept2 == kept


def test_scan_aggregates_scope_and_stats():
    """扫描仅聚合 compare 报告行；统计口径（case/项数/去重数）正确。"""
    x = {'id': 1, 'v': 'a'}
    rows = [
        {'report_id': 376, 'report_name': 'r1', 'report_type': 'secondary_comparison',
         'case_id': 1, 'audios': [x, dict(x), {'id': 2, 'v': 'b'}]},
        {'report_id': 376, 'report_name': 'r1', 'report_type': 'secondary_comparison',
         'case_id': 2, 'audios': [{'id': 3, 'v': 'c'}]},
    ]
    affected, stats = script.scan(_FakeConn(rows, deleted_count=2))
    assert stats['reports_scanned'] == 1
    assert stats['cases_scanned'] == 2
    assert stats['audio_items_total'] == 4
    assert stats['cases_affected'] == 1
    assert stats['duplicates_removed'] == 1
    assert stats['skipped_deleted_compare_reports'] == 2
    assert [a['case_id'] for a in affected] == [1]
    assert affected[0]['items_before'] == 3 and affected[0]['items_after'] == 2
    per_report = stats['per_report'][0]
    assert per_report['cases'] == 2 and per_report['affected_cases'] == 1
    assert per_report['items_before'] == 4 and per_report['items_after'] == 3


def test_scan_clean_data_yields_zero_affected():
    """干净数据扫描：0 受影响，统计仍完整（幂等 no-op 的前提）。"""
    rows = [
        {'report_id': 382, 'report_name': 'r2', 'report_type': 'comparison',
         'case_id': 5, 'audios': [{'id': 1}, {'id': 2}]},
    ]
    affected, stats = script.scan(_FakeConn(rows))
    assert affected == []
    assert stats['reports_affected'] == 0 and stats['duplicates_removed'] == 0
    assert stats['audio_items_after'] == stats['audio_items_total'] == 2


def test_scan_skips_non_list_audios():
    """audios 非列表（异常落库形态）跳过计数，不参与去重也不误报。"""
    rows = [
        {'report_id': 1, 'report_name': 'r', 'report_type': 'comparison',
         'case_id': 7, 'audios': None},
        {'report_id': 1, 'report_name': 'r', 'report_type': 'comparison',
         'case_id': 8, 'audios': 'not-a-list'},
    ]
    affected, stats = script.scan(_FakeConn(rows))
    assert affected == []
    assert stats['cases_scanned'] == 0
