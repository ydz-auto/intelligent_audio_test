# -*- coding: utf-8 -*-
"""INT-1994/1995（档4 R1/M1）：report_cases 九字段 payload 内容寻址外置。

覆盖口径（设计文档 ``10_报告用例快照外置.md`` §2 / §5 / §6 / §8）：

1. 规范化 / sha256 / gzip **纯函数复用** ``shared/utils/raw_payload.py``（不另写
   第二套算法）；
2. 写路径：快照行 + 行上 4 指针列，同一事务、先快照后行；同值只产生一行快照；
   M1（INT-1995）之后内容列已 DROP，行上只留五列 + 指针列；
3. 解引用：``load_cases`` / ``get_cases_by_report_id`` 属性名不变、值从快照还原，
   且 ``metrics == []`` 不被折成 ``{}``（逐字节冻结的前提）；M1 起恒走快照读源，
   ``REPORT_CASE_SNAPSHOT_SOURCE=column`` 不再生效；
4. 失败语义：指针为 NULL / 快照行缺失 / sha 不符，一律**显式抛错**（不返回空）；
5. 导入 / 替换链路不悬空：R1 旧包按行上内容列重算并覆盖指针，M1 包（快照行 +
   纯指针用例行）先建快照再建用例行，``snapshot_created_at`` 沿用源行时间；
6. 登记：新表进 ``tests/data/schema_baseline.json``、进 ``create_all_tables``
   模型全集（``EXPECTED_TABLE_COUNT``）与引导链；M1 后九字段内容列从基线移除。

隔离方式：sqlite 内存库建 test_reports / report_cases / report_case_snapshots
三表 + monkeypatch 三个 mixin 模块的 ``get_db_session``（同
test_int258_report_snapshot_freeze.py 先例）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.infrastructure.persistence._report_children_load_mixin as load_mixin
import report_service.infrastructure.persistence._report_children_write_mixin as write_mixin
import report_service.infrastructure.persistence._report_query_mixin as query_mixin
import report_service.infrastructure.persistence.report_transfer_repository as transfer_repo
from report_service.infrastructure.persistence import report_case_snapshot_store as store
from shared.utils.raw_payload import canonical_bytes, sha256_hex, sha256_of_bytes

REPORT_ID = 9001


# ------------------------------------------------------------------ 夹具

@pytest.fixture()
def session_factory(monkeypatch):
    """三表 sqlite 内存库；三个 mixin 与导入仓储的 get_db_session 都指向它。"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable

    from report_service.infrastructure.persistence.models import (
        Report, ReportCase, ReportCaseSnapshot, ReportComparisonMatrix,
        ReportMetricStats, ReportRawData, ReportSummary, ReportSummaryMeta,
    )

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    from shared.models.database import Base
    Base.metadata.create_all(bind=engine, tables=[
        Report.__table__, ReportCaseSnapshot.__table__,
        # 报告 7 表其余 5 张：导入仓储会逐表取已有主键（导入链路用）
        ReportSummary.__table__, ReportSummaryMeta.__table__,
        ReportRawData.__table__, ReportMetricStats.__table__,
        ReportComparisonMatrix.__table__,
    ])
    # report_cases 的 id 是 BigInteger：sqlite 只有 INTEGER PRIMARY KEY 才自增
    #（test_int258 先例），这里按同构 DDL 建一次，好让 add_case 走真实写路径。
    ddl = str(CreateTable(ReportCase.__table__).compile(
        dialect=sqlite_dialect.dialect())).replace(
        'id BIGINT NOT NULL', 'id INTEGER NOT NULL')
    with engine.begin() as conn:
        conn.execute(text(ddl))
    factory = sessionmaker(bind=engine)
    for module in (load_mixin, write_mixin, query_mixin, transfer_repo):
        monkeypatch.setattr(module, 'get_db_session', factory)
    return factory


@pytest.fixture()
def repository():
    """报告仓储（写/读三组 mixin 的组合体）。"""
    from report_service.infrastructure.persistence.report_repository import (
        ReportRepository,
    )
    return ReportRepository()


def _case_payload(**overrides):
    data = {
        'test_case_id': 'CASE-1',
        'name': '播放在线音乐',
        'description': '验证播放链路',
        'category': '播放功能',
        'tags': ['冒烟', '回归'],
        'metrics': [{'resource': 'res-a', 'metrics': [{'metric': 'WER', 'value': 7.2}]}],
        'results': [{'round': 1, 'status': 'passed'}],
        'audios': [{'id': 3, 'name': 'a.wav'}],
        'reference_params': {'ref': 'x'},
        'algorithm_results': {'asr': {'text': 'hello'}},
        'algorithm_type': 'asr',
        'logs': 'ok',
    }
    data.update(overrides)
    return data


def _snapshot_count(session_factory) -> int:
    from report_service.infrastructure.persistence.models import ReportCaseSnapshot
    session = session_factory()
    try:
        return session.query(ReportCaseSnapshot).count()
    finally:
        session.close()


# ------------------------------------------------------------------ 1. 口径复用

class TestCanonicalReuse:
    def test_sha_matches_shared_canonical_implementation(self):
        payload = store.build_payload(_case_payload())
        assert set(payload) == set(store.PAYLOAD_FIELDS)
        assert len(payload) == 9
        # 与 shared 侧唯一实现逐字节一致（不另写第二套算法）
        assert store.payload_sha(payload) == sha256_hex(payload)
        assert store.payload_sha(payload) == sha256_of_bytes(canonical_bytes(payload))

    def test_uri_records_carrier_scheme(self):
        pointer = store.SnapshotPointer(sha256='a' * 64, size_bytes=1, created_at=None)
        assert pointer.uri == 'db://report_case_snapshots/' + 'a' * 64

    def test_payload_built_from_raw_values_without_falsy_normalisation(self):
        """metrics / results 为 [] 时必须原样进 payload（折成 {} 就破坏冻结）。"""
        payload = store.build_payload({
            'name': None, 'metrics': [], 'results': [], 'reference_params': {},
            'algorithm_results': [], 'tags': None,
        })
        assert payload['metrics'] == []
        assert payload['results'] == []
        assert payload['algorithm_results'] == []
        assert payload['reference_params'] == {}
        assert payload['tags'] is None
        assert payload['name'] is None


# ------------------------------------------------------------------ 2. 双写

class TestDualWrite:
    def test_add_case_writes_snapshot_and_pointer_columns(self, session_factory,
                                                          repository):
        data = _case_payload()
        case_id = repository.add_case(REPORT_ID, data)

        from report_service.infrastructure.persistence.models import (
            ReportCase, ReportCaseSnapshot,
        )
        session = session_factory()
        try:
            po = session.query(ReportCase).filter(ReportCase.id == case_id).one()
            # INT-1995（M1）：内容列已 DROP，行上只有五列 + 指针列
            assert po.test_case_id == data['test_case_id']
            assert po.algorithm_type == data['algorithm_type']
            assert po.logs == data['logs']
            for field in store.PAYLOAD_FIELDS:
                assert not hasattr(po, field), f'内容列 {field} 不应还在行上'
            # 指针四列齐全
            payload = store.build_payload(data)
            sha = store.payload_sha(payload)
            assert po.snapshot_sha256 == sha
            assert po.snapshot_uri == f'db://report_case_snapshots/{sha}'
            assert po.snapshot_bytes and po.snapshot_bytes > 0
            assert po.snapshot_created_at is not None
            # 快照行在，压缩后字节数与指针一致
            snap = session.query(ReportCaseSnapshot).filter(
                ReportCaseSnapshot.sha256 == sha).one()
            assert snap.payload_bytes == po.snapshot_bytes
            assert json.loads(
                store.decompress(bytes(snap.payload_gz)).decode('utf-8')) == payload
        finally:
            session.close()

    def test_same_payload_across_cases_produces_one_snapshot(self, session_factory,
                                                             repository):
        repository.add_case(REPORT_ID, _case_payload(test_case_id='C1'))
        repository.add_case(REPORT_ID, _case_payload(test_case_id='C2'))
        repository.add_case(REPORT_ID, _case_payload(test_case_id='C2', name='另一个'))

        from report_service.infrastructure.persistence.models import ReportCase
        session = session_factory()
        try:
            assert session.query(ReportCase).count() == 3
        finally:
            session.close()
        # 前两行 payload 相同 → 1 个快照；第三行不同 → 再加 1 个
        assert _snapshot_count(session_factory) == 2

    def test_put_is_idempotent(self, session_factory):
        payload = store.build_payload(_case_payload())
        session = session_factory()
        try:
            first = store.put(session, payload)
            second = store.put(session, payload)
            session.commit()
        finally:
            session.close()
        assert first.sha256 == second.sha256
        assert first.size_bytes == second.size_bytes
        assert _snapshot_count(session_factory) == 1


# ------------------------------------------------------------------ 3. 解引用（恒走快照）

class TestDereference:
    def test_load_cases_and_get_cases_resolve_snapshot_payload(self, session_factory,
                                                               repository):
        """M1：内容列已 DROP，读侧必须经快照解引用出九字段 payload。"""
        repository.add_case(REPORT_ID, _case_payload())
        repository.add_case(REPORT_ID, _case_payload(
            test_case_id='CASE-2', name='空指标用例', metrics=[], results=[],
            algorithm_results=[], tags=[]))

        entities = repository.load_cases(REPORT_ID)
        rows = repository.get_cases_by_report_id(REPORT_ID)

        assert len(entities) == len(rows) == 2
        expected = {c['test_case_id']: c for c in [_case_payload(),
                                                   _case_payload(
                                                       test_case_id='CASE-2',
                                                       name='空指标用例',
                                                       metrics=[], results=[],
                                                       algorithm_results=[],
                                                       tags=[])]}
        for entity, row in zip(entities, rows):
            summary = entity.result_summary
            for field in store.PAYLOAD_FIELDS:
                assert summary[field] == expected[row.test_case_id][field], field
                assert getattr(row, field) == expected[row.test_case_id][field], field
            # 行上保留字段透传
            assert summary['algorithm_type'] == 'asr'
            assert row.logs == 'ok'

    def test_empty_list_payload_survives_roundtrip(self, session_factory, repository):
        repository.add_case(REPORT_ID, _case_payload(
            test_case_id='CASE-E', metrics=[], results=[], algorithm_results=[]))
        entity = repository.load_cases(REPORT_ID)[0]
        assert entity.result_summary['metrics'] == []
        assert entity.result_summary['results'] == []
        assert entity.result_summary['algorithm_results'] == []

    def test_column_env_ignored_after_m1(self, monkeypatch):
        """M1：内容列已删，REPORT_CASE_SNAPSHOT_SOURCE=column 不再生效，恒走快照。"""
        monkeypatch.setenv(store.SOURCE_ENV, 'column')
        assert store.read_source() == store.SOURCE_SNAPSHOT

    def test_default_source_is_snapshot(self, monkeypatch):
        monkeypatch.delenv(store.SOURCE_ENV, raising=False)
        assert store.read_source() == store.SOURCE_SNAPSHOT
        monkeypatch.setenv(store.SOURCE_ENV, 'COLUMN')  # 大小写不敏感也不生效
        assert store.read_source() == store.SOURCE_SNAPSHOT
        monkeypatch.setenv(store.SOURCE_ENV, 'nonsense')
        assert store.read_source() == store.SOURCE_SNAPSHOT


# ------------------------------------------------------------------ 4. 失败语义

class TestFailureSemantics:
    def test_missing_snapshot_row_raises_instead_of_empty_cases(self, session_factory,
                                                                repository):
        from report_service.infrastructure.persistence.models import ReportCase

        repository.add_case(REPORT_ID, _case_payload())
        session = session_factory()
        try:
            row = session.query(ReportCase).one()
            row.snapshot_sha256 = 'deadbeef' * 8  # 指针悬空
            session.commit()
        finally:
            session.close()

        with pytest.raises(store.ReportCaseSnapshotMissingError) as excinfo:
            repository.load_cases(REPORT_ID)
        assert 'deadbeef' in str(excinfo.value)
        assert str(REPORT_ID) in str(excinfo.value)

        with pytest.raises(store.ReportCaseSnapshotMissingError):
            repository.get_cases_by_report_id(REPORT_ID)

    def test_null_pointer_raises_with_gate_hint(self, session_factory, repository):
        from report_service.infrastructure.persistence.models import ReportCase

        repository.add_case(REPORT_ID, _case_payload())
        session = session_factory()
        try:
            row = session.query(ReportCase).one()
            row.snapshot_sha256 = None
            session.commit()
        finally:
            session.close()

        with pytest.raises(store.ReportCaseSnapshotMissingError) as excinfo:
            repository.load_cases(REPORT_ID)
        # M1：无内容列可回退，提示回到 --gate 归零
        assert '`--gate`' in str(excinfo.value)

    def test_sha_mismatch_raises_corrupt(self, session_factory, repository):
        from report_service.infrastructure.persistence.models import ReportCaseSnapshot

        repository.add_case(REPORT_ID, _case_payload())
        session = session_factory()
        try:
            snap = session.query(ReportCaseSnapshot).one()
            # 改一字节 → 解压后 sha 与主键不符
            snap.payload_gz = store.compress(b'{"tampered":true}')
            session.commit()
        finally:
            session.close()

        with pytest.raises(store.ReportCaseSnapshotCorruptError) as excinfo:
            repository.load_cases(REPORT_ID)
        assert 'sha256 校验失败' in str(excinfo.value)


# ------------------------------------------------------------------ 6. 原始 payload 只读出口（INT-1996）

class TestRawPayloadExport:
    """INT-1996：报告用例原始九字段 payload 只读出口（task_service 发布冻结 M1 前置）。

    与 handle_get_report_cases 的区别：不经响应装配层（build_case_dict_from_entity /
    build_case_item 的 null/[] 归一与 algorithmResults/referenceParams 展开），
    直接由快照解引用出口给出原始列值。
    """

    def _handler(self, repository):
        from report_service.application.handlers.report_handlers import ReportQueryHandler
        return ReportQueryHandler(repository=repository)

    def test_handler_returns_raw_values_without_assembly(self, session_factory,
                                                         repository, monkeypatch):
        repository.add_case(REPORT_ID, _case_payload(
            test_case_id='CASE-RAW', metrics=[], results=[], algorithm_results=[],
            tags=None, reference_params={}))
        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_SNAPSHOT)

        cases = self._handler(repository).handle_get_report_cases_raw_payload(REPORT_ID)['cases']
        assert len(cases) == 1
        c = cases[0]
        # 原始值：[]/None/{} 原样保留，不被 build_case_item 折成 {} / [] / 展开
        assert c['metrics'] == []
        assert c['results'] == []
        assert c['algorithm_results'] == []
        assert c['tags'] is None
        assert c['reference_params'] == {}
        # 行上字段透传
        assert c['test_case_id'] == 'CASE-RAW'
        assert c['algorithm_type'] == 'asr'
        assert c['logs'] == 'ok'

    def test_handler_resolves_payload_from_snapshot_source(self, session_factory,
                                                           repository, monkeypatch):
        """M1：快照读源解出原始九字段值，与写入入参逐项相等（发布冻结的前提）。"""
        repository.add_case(REPORT_ID, _case_payload())
        repository.add_case(REPORT_ID, _case_payload(
            test_case_id='CASE-2', metrics=[], results=[], algorithm_results=[], tags=[]))

        cases = self._handler(repository).handle_get_report_cases_raw_payload(REPORT_ID)['cases']
        by_id = {c['test_case_id']: c for c in cases}
        assert set(by_id) == {'CASE-1', 'CASE-2'}
        for test_case_id, c in by_id.items():
            payload = store.build_payload(_case_payload(
                test_case_id=test_case_id,
                **(dict(metrics=[], results=[], algorithm_results=[], tags=[])
                   if test_case_id == 'CASE-2' else {})))
            for field in store.PAYLOAD_FIELDS:
                assert c[field] == payload[field], f'{test_case_id}.{field}'
            assert c['algorithm_type'] == 'asr'
            assert c['logs'] == 'ok'

    def test_handler_propagates_corrupt_snapshot_error(self, session_factory,
                                                       repository, monkeypatch):
        from report_service.infrastructure.persistence.models import ReportCaseSnapshot

        repository.add_case(REPORT_ID, _case_payload())
        session = session_factory()
        try:
            snap = session.query(ReportCaseSnapshot).one()
            snap.payload_gz = store.compress(b'{"tampered":true}')
            session.commit()
        finally:
            session.close()
        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_SNAPSHOT)

        with pytest.raises(store.ReportCaseSnapshotCorruptError):
            self._handler(repository).handle_get_report_cases_raw_payload(REPORT_ID)


class TestRawPayloadGrpcLoopback:
    """INT-1996：GetReportCasesRawPayload 回环 gRPC 验证（真实 server + 真实 channel）。

    不启本地栈：进程内起 report_service gRPC server（同 test_int141 先例），
    把 task_service ACL 的 stub 工厂指向它，验证 proto 再生成后的全链路——
    序列化 / 反序列化 / servicer 分发 / JSON 载荷往返。
    """

    def test_acl_roundtrips_raw_payload_via_grpc(self, session_factory, repository,
                                                 monkeypatch):
        from concurrent import futures

        import grpc

        from shared.proto import report_service_pb2 as report_pb
        from shared.proto import report_service_pb2_grpc as report_grpc
        from report_service.interfaces.grpc.servicers import ReportServicer
        from task_service.infrastructure.acl.report_acl_repository import (
            report_acl_repository,
        )

        repository.add_case(REPORT_ID, _case_payload(
            test_case_id='CASE-RPC', metrics=[], results=[], algorithm_results=[],
            tags=None, reference_params={}))
        monkeypatch.setenv(store.SOURCE_ENV, store.SOURCE_SNAPSHOT)

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        report_grpc.add_ReportConfigServiceServicer_to_server(ReportServicer(), server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                monkeypatch.setattr(
                    'shared.clients.grpc_clients.get_report_config_service_stub',
                    lambda: report_grpc.ReportConfigServiceStub(channel),
                )
                cases = report_acl_repository.get_report_cases_raw_payload(REPORT_ID)
        finally:
            server.stop(0)

        assert len(cases) == 1
        c = cases[0]
        assert c['test_case_id'] == 'CASE-RPC'
        # 原始值跨 gRPC JSON 往返后原样保留（不经 build_case_item 归一）
        assert c['metrics'] == []
        assert c['results'] == []
        assert c['algorithm_results'] == []
        assert c['tags'] is None
        assert c['reference_params'] == {}
        assert c['logs'] == 'ok'


# ------------------------------------------------------------------ 7. 导入 / 替换不悬空

class TestImportRecompute:
    def test_apply_to_row_overwrites_dangling_pointer(self, session_factory):
        row = dict(_case_payload())
        row.update({'report_id': REPORT_ID,
                    'snapshot_sha256': 'f' * 64,          # 源环境的悬空 sha
                    'snapshot_uri': 'db://report_case_snapshots/' + 'f' * 64,
                    'snapshot_bytes': 1,
                    'created_at': '2026-01-02T03:04:05'})
        session = session_factory()
        try:
            prepared = store.apply_to_row(session, row)
            session.commit()
        finally:
            session.close()

        expected_sha = store.payload_sha(store.build_payload(_case_payload()))
        assert prepared['snapshot_sha256'] == expected_sha
        assert prepared['snapshot_uri'] == f'db://report_case_snapshots/{expected_sha}'
        assert prepared['snapshot_bytes'] > 0
        # 内容生成时间沿用源行，不回退成导入时刻
        assert prepared['snapshot_created_at'] == '2026-01-02T03:04:05'
        assert _snapshot_count(session_factory) == 1

    def test_apply_to_row_is_idempotent(self, session_factory):
        session = session_factory()
        try:
            row = dict(_case_payload(), report_id=REPORT_ID)
            first = store.apply_to_row(session, row)
            second = store.apply_to_row(session, first)
            session.commit()
        finally:
            session.close()
        assert first['snapshot_sha256'] == second['snapshot_sha256']
        assert _snapshot_count(session_factory) == 1

    def test_old_package_without_content_columns_left_untouched(self, session_factory):
        """纯指针包（M1 之后才会出现）：九字段内容列一个都没有 → 原样保留。"""
        session = session_factory()
        try:
            row = {'report_id': REPORT_ID, 'test_case_id': 'C1',
                   'snapshot_sha256': 'a' * 64}
            assert store.apply_to_row(session, row) == row
        finally:
            session.close()
        assert _snapshot_count(session_factory) == 0

    def test_report_transfer_import_recomputes_case_pointers(self, session_factory):
        """R1 旧包（带内容列）导入 M1 库：按内容列重算指针，内容列不落库。"""
        from report_service.infrastructure.persistence.report_transfer_repository import (
            ReportTransferRepository,
        )

        repo = ReportTransferRepository()
        case_row = dict(_case_payload())
        case_row.update({'id': 501, 'report_id': 700,
                         'snapshot_sha256': 'b' * 64,
                         'created_at': '2026-02-03T04:05:06' + '+08:00'})
        tables_rows = {
            'test_reports': [{'id': 700, 'name': 'R', 'type': 'task',
                              'status': 'published', 'task_id': 42,
                              'created_at': '2026-02-03T04:00:00+08:00'}],
            'report_cases': [case_row],
        }
        mapping, _pks = repo.import_reports(tables_rows, {})

        from report_service.infrastructure.persistence.models import (
            ReportCase, ReportCaseSnapshot,
        )
        session = session_factory()
        try:
            imported = session.query(ReportCase).one()
            expected = store.payload_sha(store.build_payload(_case_payload()))
            assert imported.report_id == mapping[700]
            assert imported.snapshot_sha256 == expected
            assert session.query(ReportCaseSnapshot).filter(
                ReportCaseSnapshot.sha256 == expected).count() == 1
            # M1 库：内容列不落库，行上只剩保留字段 + 指针
            for field in store.PAYLOAD_FIELDS:
                assert not hasattr(imported, field), f'内容列 {field} 不应还在行上'
            assert imported.test_case_id == 'CASE-1'
            assert imported.algorithm_type == 'asr'
            assert imported.logs == 'ok'
        finally:
            session.close()

    def test_report_transfer_export_includes_base64_snapshots(self, session_factory,
                                                              repository):
        """导出：快照行随包携带（只带被引用 sha），payload_gz 按 base64 进 JSON。"""
        import base64

        from report_service.infrastructure.persistence.models import Report
        from report_service.infrastructure.persistence.report_transfer_repository import (
            ReportTransferRepository,
        )

        session = session_factory()
        try:
            session.add(Report(id=700, name='R', type='task', status='published',
                               task_id=42))
            session.commit()
        finally:
            session.close()

        payload = store.build_payload(_case_payload())
        gz = store.compress(store.canonical_bytes(payload))
        repository.add_case(700, _case_payload())
        repository.add_case(700, _case_payload(test_case_id='C2'))

        exported = ReportTransferRepository().export_by_report_ids([700])
        case_rows = exported['report_cases']
        snap_rows = exported['report_case_snapshots']
        # 两个用例同 payload → 1 个快照行；payload_gz 是 base64 串（非 bytes）
        assert len(snap_rows) == 1
        assert isinstance(snap_rows[0]['payload_gz'], str)
        assert base64.b64decode(snap_rows[0]['payload_gz']) == gz
        assert snap_rows[0]['payload_bytes'] == len(gz)
        shas = {r['snapshot_sha256'] for r in case_rows}
        assert {r['sha256'] for r in snap_rows} == shas

    def test_report_transfer_import_m1_package_carries_snapshots(self, session_factory):
        """M1 包（快照行 + 纯指针用例行）：先建快照行再建用例行，导入后门禁为 0。"""
        import base64

        from report_service.infrastructure.persistence.report_transfer_repository import (
            ReportTransferRepository,
        )

        repo = ReportTransferRepository()
        payload = store.build_payload(_case_payload())
        raw = store.canonical_bytes(payload)
        sha = store.sha256_of_bytes(raw)
        gz = store.compress(raw)
        case_row = {'id': 501, 'report_id': 700, 'test_case_id': 'CASE-1',
                    'algorithm_type': 'asr', 'logs': 'ok',
                    'snapshot_sha256': sha,
                    'snapshot_uri': f'db://report_case_snapshots/{sha}',
                    'snapshot_bytes': len(gz),
                    'snapshot_created_at': '2026-02-03T04:05:06+08:00'}
        snapshot_row = {'sha256': sha,
                        'payload_gz': base64.b64encode(gz).decode('ascii'),
                        'payload_bytes': len(gz),
                        'created_at': '2026-02-03T04:05:06+08:00'}
        tables_rows = {
            'test_reports': [{'id': 700, 'name': 'R', 'type': 'task',
                              'status': 'published', 'task_id': 42,
                              'created_at': '2026-02-03T04:00:00+08:00'}],
            'report_cases': [case_row],
            'report_case_snapshots': [snapshot_row],
        }
        mapping, _pks = repo.import_reports(tables_rows, {})

        from report_service.infrastructure.persistence.models import (
            ReportCase, ReportCaseSnapshot,
        )
        session = session_factory()
        try:
            imported = session.query(ReportCase).one()
            assert imported.report_id == mapping[700]
            assert imported.snapshot_sha256 == sha
            snap = session.query(ReportCaseSnapshot).filter(
                ReportCaseSnapshot.sha256 == sha).one()
            assert snap.payload_bytes == len(gz)
            assert store.decompress(bytes(snap.payload_gz)) == raw
            # 幂等：同包再导一次，快照不重复、指针不变
            repo.import_reports(tables_rows, {})
            assert session.query(ReportCaseSnapshot).count() == 1
        finally:
            session.close()


# ------------------------------------------------------------------ 8. 回填脚本口径

class TestBackfillScript:
    @staticmethod
    def _module():
        import importlib.util
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'scripts', 'migrations', '202610',
            'backfill_report_case_snapshots_int1994.py')
        spec = importlib.util.spec_from_file_location('int1994_backfill', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_payload_fields_cover_nine_and_match_snapshot_fields(self):
        module = self._module()
        assert tuple(module.PAYLOAD_FIELDS) == tuple(store.PAYLOAD_FIELDS)
        assert set(module.JSON_FIELDS) | set(module.TEXT_FIELDS) == set(module.PAYLOAD_FIELDS)

    def test_json_columns_keep_empty_list_shape(self):
        module = self._module()
        assert module._parse_json('[]', 'metrics') == []
        assert module._parse_json('{}', 'reference_params') == {}
        assert module._parse_json(None, 'metrics') is None
        with pytest.raises(ValueError):
            module._parse_json('not json', 'metrics')

    def test_gate_and_pointer_update_guards(self):
        module = self._module()
        # 门禁必须同时抓「没指针」与「指针悬空」，且子查询显式比对主键
        assert 'IS NULL' in module.GATE_SQL
        assert 'NOT EXISTS' in module.GATE_SQL
        source = open(module.__file__, encoding='utf-8').read()
        # 重复执行不覆写已有指针
        assert 'AND snapshot_sha256 IS NULL' in source
        # 同值只写一行快照
        assert 'ON CONFLICT (sha256) DO NOTHING' in source
        # 回填的 snapshot_created_at 取源行 created_at（不是 now()）
        assert 'rc.created_at' in source
        assert 'snapshot_created_at = %s' in source


# ------------------------------------------------------------------ 9. 登记

class TestRegistration:
    def test_new_table_and_columns_in_schema_baseline(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'tests', 'data', 'schema_baseline.json'),
                  encoding='utf-8') as f:
            baseline = json.load(f)
        assert set(baseline['report_case_snapshots']) == {
            'sha256', 'payload_gz', 'payload_bytes', 'created_at'}
        assert set(store.POINTER_COLUMNS) <= set(baseline['report_cases'])
        assert not {'deleted', 'report_id'} & set(baseline['report_case_snapshots'])
        # INT-1995（M1）：九字段内容列已 DROP，基线不再含它们
        assert not set(store.PAYLOAD_FIELDS) & set(baseline['report_cases'])

    def test_create_all_registers_snapshot_table_and_bootstrap_runs_migration(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import importlib.util

        def _load(rel, name):
            spec = importlib.util.spec_from_file_location(name, os.path.join(root, *rel))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        create_all = _load(('scripts', 'create_all_tables.py'), 'int1994_create_all')
        create_all._import_all_models()
        from shared.models.database import Base
        assert 'report_case_snapshots' in Base.metadata.tables

        bootstrap = _load(('docker', 'db_bootstrap_entrypoint.py'), 'int1994_bootstrap')
        steps = [list(step) for step in bootstrap.BOOTSTRAP_STEPS]
        rel = 'scripts/migrations/202610/add_report_case_snapshots_int1994.py'
        assert any(rel in step for step in steps)
        assert any(rel in step and '--apply' in step for step in steps)
        # DDL 步骤必须排在 ANALYZE 之前（INT-1741 口径）
        names = [step[1] for step in steps]
        assert names.index(rel) < names.index(
            'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
