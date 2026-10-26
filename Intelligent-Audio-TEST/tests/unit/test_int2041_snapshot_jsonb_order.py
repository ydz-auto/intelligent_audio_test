# -*- coding: utf-8 -*-
"""INT-2041（P1 缺陷）：snapshot 读源保持 jsonb 键序 + 用例行序确定化。

背景（父卡 INT-2008 解阻窗口实测）：``REPORT_CASE_SNAPSHOT_SOURCE=column`` 读
行上 jsonb 列拿到的是 PG jsonb 键序（先比键 UTF-8 字节长度、再字节 memcmp）；
``snapshot`` 读源解出来的 payload 是 ``canonical_bytes(sort_keys=True)`` 的
**字典序**。两者取值完全相同，但只要消费方按 ``dict.items()`` 遍历（
``stats_mixin._expand_rounds()`` 展开 ``@round:N``），差别就会以**列表条目
顺序**的形式浮到 ``algorithmResults`` 上 → 22 份报告里 7 份（3,686 例）不
逐字节等价。

覆盖口径：

1. ``normalize_jsonb_order`` 递归键序还原：多层嵌套、键长优先、等长按字节、
   多字节 UTF-8 键、数组内嵌对象、数组本身保序、标量原样；
2. ``fetch_batch`` 返回的就是 jsonb 键序，且 **sha 校验口径没变**（写侧仍按
   ``canonical_bytes`` 算，A→B→A 往返不崩）；
3. 详情链路（``load_cases`` → ``build_case_dict_from_entity`` → ``build_case_item``）
   在两种读源下产出逐字节相同（含 ``algorithmResults`` 条目顺序）；
4. ``load_cases`` / ``get_cases_by_report_id`` 的查询带 ``ORDER BY report_cases.id``
   （结构断言：抓到实际 SQL），返回行按 id 升序。

隔离方式同 ``test_int1994_report_case_snapshots.py``：sqlite 内存库 + 三个 mixin
模块的 ``get_db_session`` monkeypatch 到同一 sessionmaker。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.infrastructure.persistence._report_children_load_mixin as load_mixin
import report_service.infrastructure.persistence._report_children_write_mixin as write_mixin
import report_service.infrastructure.persistence._report_query_mixin as query_mixin
from report_service.infrastructure.persistence import report_case_snapshot_store as store
from shared.utils.raw_payload import canonical_bytes, sha256_hex

REPORT_ID = 9311


# ------------------------------------------------------------------ 夹具

@pytest.fixture()
def session_factory(monkeypatch):
    """三表 sqlite 内存库；读/写/查询三个 mixin 的 get_db_session 都指向它。"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable

    from report_service.infrastructure.persistence.models import (
        ReportCase, ReportCaseSnapshot,
    )
    from shared.models.database import Base

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[
        ReportCaseSnapshot.__table__,
    ])
    # report_cases.id 是 BigInteger，sqlite 只有 INTEGER PRIMARY KEY 才自增
    ddl = str(CreateTable(ReportCase.__table__).compile(
        dialect=sqlite_dialect.dialect())).replace(
        'id BIGINT NOT NULL', 'id INTEGER NOT NULL')
    with engine.begin() as conn:
        conn.execute(text(ddl))
    factory = sessionmaker(bind=engine)
    for module in (load_mixin, write_mixin, query_mixin):
        monkeypatch.setattr(module, 'get_db_session', factory)
    return factory


@pytest.fixture()
def repository():
    from report_service.infrastructure.persistence.report_repository import (
        ReportRepository,
    )
    return ReportRepository()


def _sql_capture(session_factory):
    """抓真实执行的 SQL（结构断言用：不靠 sqlite 的隐式行序猜）。"""
    from sqlalchemy import event

    seen = []
    engine = session_factory.kw['bind']

    def _before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, 'before_cursor_execute', _before)
    return seen


def _rounds_case(**overrides):
    """一份带 voice_llm ``rounds[].output`` 的用例（差异现场同形）。

    ``output`` 的键按 **jsonb 键序**给：``ai_wav``(6) / ``end_ms``(6) /
    ``start_ms``(8) / ``user_wav``(8) / ``record_file``(11) /
    ``first_frame_ms``(14)。字典序会是 ai_wav / end_ms / first_frame_ms /
    record_file / start_ms / user_wav —— 故意让两种口径分叉。
    """
    data = {
        'test_case_id': 'CASE-2041',
        'name': '多轮语音识别',
        'description': 'rounds 展开顺序',
        'category': '语音识别',
        'tags': ['多轮'],
        'metrics': [],
        'results': [{'round': 1, 'status': 'passed'}],
        'audios': [{'id': 1, 'name': 'a.wav'}],
        'reference_params': {'ref': 'x'},
        'algorithm_results': [
            {'param_code': 'rounds', 'paramCode': 'rounds', 'param_type': 'json',
             'value': [
                 {'round': 0, 'output': {
                     'ai_wav': 'ai0.wav', 'end_ms': 1200, 'start_ms': 100,
                     'user_wav': 'user0.wav', 'record_file': 'rec0.wav',
                     'first_frame_ms': 80,
                 }},
                 {'round': 1, 'output': {'ai_wav': 'ai1.wav', 'start_ms': 900}},
             ]},
        ],
        'algorithm_type': 'voice_llm',
        'logs': 'ok',
    }
    data.update(overrides)
    return data


def _detail_item(case_entity):
    """详情链路：实体 → case dict → 前端用例项（含 rounds 展开）。"""
    from report_service.application.services.report_aggregation.cases_mixin import (
        _AggregationCasesMixin,
    )
    return _AggregationCasesMixin.build_case_item(
        _AggregationCasesMixin.build_case_dict_from_entity(case_entity))


# ------------------------------------------------------------------ 1. 键序还原

class TestNormalizeJsonbOrder:
    def test_key_length_beats_lexicographic(self):
        """jsonb 先比键字节长度：单字符键排在更长的键之前（字典序相反）。"""
        value = {'ab': 1, 'z': 2, 'abc': 3, 'y': 4}
        assert list(store.normalize_jsonb_order(value)) == ['y', 'z', 'ab', 'abc']

    def test_same_length_keys_compared_by_bytes(self):
        value = {'ab': 1, 'aa': 2, 'aA': 3, 'a1': 4}
        # 等长（2 字节）按字节 memcmp：'a1'(0x31) < 'aA'(0x41) < 'aa'(0x61) < 'ab'
        assert list(store.normalize_jsonb_order(value)) == ['a1', 'aA', 'aa', 'ab']

    def test_multibyte_utf8_keys_sort_by_byte_length(self):
        """中文键按 UTF-8 字节算长度：'ab'(2) < '中'(3) < '中文'(6)。"""
        value = {'中文': 1, '中': 2, 'ab': 3}
        assert list(store.normalize_jsonb_order(value)) == ['ab', '中', '中文']

    def test_nested_objects_recursively_normalized(self):
        value = {'outer': {'bbb': {'dd': 1, 'c': 2}, 'a': 3}, 'z': 4}
        root = store.normalize_jsonb_order(value)
        assert list(root) == ['z', 'outer']
        assert list(root['outer']) == ['a', 'bbb']
        assert list(root['outer']['bbb']) == ['c', 'dd']

    def test_arrays_keep_order_and_normalize_embedded_objects(self):
        value = [
            {'bb': 1, 'a': 2},
            {'dddd': 3, 'c': 4},
            7,
            [{'y': 5, 'xx': 6}],
        ]
        out = store.normalize_jsonb_order(value)
        assert isinstance(out, list) and len(out) == 4
        assert list(out[0]) == ['a', 'bb']
        assert list(out[1]) == ['c', 'dddd']
        assert out[2] == 7
        assert list(out[3][0]) == ['y', 'xx']
        # 数组元素顺序原样（jsonb 数组保序）
        assert [list(x)[0] for x in (out[0], out[1])] == ['a', 'c']

    def test_scalars_and_none_untouched(self):
        for value in (None, 0, 1.5, 'text', True):
            assert store.normalize_jsonb_order(value) == value

    def test_values_never_changed_only_order(self):
        import json
        value = {'b': {'z': 1, 'a': [{'q': 2, 'p': 3}]}, 'aa': 'x'}
        out = store.normalize_jsonb_order(value)
        # 键序变了，但按内容比较完全一致
        assert json.dumps(out, sort_keys=True) == json.dumps(value, sort_keys=True)
        # 且不是同一个 dict 对象（不改调用方的入参）
        assert out is not value


# ------------------------------------------------------------------ 2. fetch_batch

class TestFetchBatchReturnsJsonbOrder:
    def test_fetch_batch_payload_is_jsonb_ordered(self, session_factory):
        payload = store.build_payload(_rounds_case())
        sha = store.payload_sha(payload)
        session = session_factory()
        try:
            store.put(session, payload)
            session.commit()
            got = store.fetch_batch(session, [sha])[sha]
        finally:
            session.close()

        # 顶层九字段：按 (字节长度, 字节) —— 字典序是 algorithm_results 打头
        expected = sorted(store.PAYLOAD_FIELDS,
                          key=lambda k: (len(k.encode('utf-8')),
                                         k.encode('utf-8')))
        assert list(got) == expected
        assert expected[0] == 'name'                # 4 字节
        assert expected[-1] == 'algorithm_results'  # 17 字节

        # 列表保序 + 内嵌对象按 jsonb 键序
        rounds = got['algorithm_results'][0]['value']
        assert [r['round'] for r in rounds] == [0, 1]
        assert list(rounds[0]['output']) == [
            'ai_wav', 'end_ms', 'start_ms', 'user_wav',
            'record_file', 'first_frame_ms',
        ]

    def test_sha_check_still_uses_canonical_bytes(self, session_factory):
        """写侧口径一字不改：库里 sha 仍是 sort_keys 规范化字节的 sha。"""
        payload = store.build_payload(_rounds_case())
        session = session_factory()
        try:
            pointer = store.put(session, payload)
            session.commit()
            # canonical（字典序）算出来的 sha 与指针一致
            assert pointer.sha256 == sha256_hex(payload)
            # 读出来的 dict 键序变了，但内容与写入值完全相同（sha 校验靠内容）
            got = store.fetch_batch(session, [pointer.sha256])[pointer.sha256]
            assert canonical_bytes(got) == canonical_bytes(payload)
        finally:
            session.close()

    def test_empty_sha_list_returns_empty(self, session_factory):
        session = session_factory()
        try:
            assert store.fetch_batch(session, []) == {}
            assert store.fetch_batch(session, ['', None]) == {}
        finally:
            session.close()


# ------------------------------------------------------------------ 3. 详情链路等价

class TestDetailPathEquivalence:
    def test_snapshot_and_column_sources_build_identical_case_items(
            self, session_factory, repository, monkeypatch):
        """两读源在详情链路产出逐字节相同（含 algorithmResults 条目顺序）。

        sqlite 的 JSON 列按写入时的键序原样存回，所以这里把用例按 **jsonb
        键序** 写进去 = 模拟 PG ``column`` 读源；snapshot 读源走快照 + 键序还原。
        """
        repository.add_case(REPORT_ID, _rounds_case())

        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_COLUMN)
        column_items = [_detail_item(c) for c in repository.load_cases(REPORT_ID)]

        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_SNAPSHOT)
        snapshot_items = [_detail_item(c) for c in repository.load_cases(REPORT_ID)]

        assert len(column_items) == len(snapshot_items) == 1
        assert canonical_bytes(snapshot_items) == canonical_bytes(column_items)

        # 差异现场本身被覆盖到了：@round 条目顺序 = jsonb 的 output 键序
        codes = [x.get('paramCode') for x in snapshot_items[0]['algorithmResults']]
        assert [c for c in codes if c and c.endswith('@round:1')] == [
            'ai_wav@round:1', 'end_ms@round:1', 'start_ms@round:1',
            'user_wav@round:1', 'record_file@round:1', 'first_frame_ms@round:1',
        ]

    def test_compare_path_identical_across_sources(self, session_factory,
                                                   repository, monkeypatch):
        repository.add_case(REPORT_ID, _rounds_case())
        repository.add_case(REPORT_ID, _rounds_case(test_case_id='CASE-2042',
                                                    name='第二条'))

        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_COLUMN)
        column_rows = [
            {f: getattr(r, f) for f in store.PAYLOAD_FIELDS}
            for r in repository.get_cases_by_report_id(REPORT_ID)
        ]
        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_SNAPSHOT)
        snapshot_rows = [
            {f: getattr(r, f) for f in store.PAYLOAD_FIELDS}
            for r in repository.get_cases_by_report_id(REPORT_ID)
        ]
        assert canonical_bytes(snapshot_rows) == canonical_bytes(column_rows)


# ------------------------------------------------------------------ 4. 行序

class TestDeterministicRowOrder:
    def test_load_cases_query_orders_by_report_cases_id(self, session_factory,
                                                        repository):
        repository.add_case(REPORT_ID, _rounds_case())
        seen = _sql_capture(session_factory)
        repository.load_cases(REPORT_ID)
        matched = [s for s in seen if 'FROM report_cases' in s]
        assert matched, '没有抓到 report_cases 查询'
        assert 'ORDER BY report_cases.id' in matched[-1]

    def test_get_cases_by_report_id_query_orders_by_report_cases_id(
            self, session_factory, repository):
        repository.add_case(REPORT_ID, _rounds_case())
        seen = _sql_capture(session_factory)
        repository.get_cases_by_report_id(REPORT_ID)
        matched = [s for s in seen if 'FROM report_cases' in s]
        assert matched, '没有抓到 report_cases 查询'
        assert 'ORDER BY report_cases.id' in matched[-1]

    def test_returned_rows_are_id_ascending(self, session_factory, repository):
        ids = [repository.add_case(REPORT_ID, _rounds_case(
            test_case_id=f'CASE-{i}', name=f'用例{i}')) for i in range(6)]
        assert ids == sorted(ids)
        assert [c.id for c in repository.load_cases(REPORT_ID)] == ids
        assert [c.id for c in repository.get_cases_by_report_id(REPORT_ID)] == ids
