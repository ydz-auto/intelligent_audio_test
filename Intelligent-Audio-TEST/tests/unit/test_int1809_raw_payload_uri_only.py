# -*- coding: utf-8 -*-
"""INT-1809（C2）：原始报文 uri-only 写路径 + 读路径收口。

钉死的不变量（不连库、不碰真实 OSS：内存 sqlite + 内存对象存储）：
1. **组级一次上传**：一组 N 行同一份 resp/req 只上传一次；逐轮值按**值**去重
   （上传次数 = 不同值数，不是行数）——否则线上写操作被放大 6 倍以上；
2. **uri-only 落库**：五列（uri/sha256/bytes/content_type/created_at）非空、
   JSON 两列一律 **SQL NULL**（`IS NULL` 为真、`json_typeof` 为 NULL；C2 起没有
   代码再写它们，为 M1 DROP 扫清障碍）。判空必须走 SQL 判据：ORM 读回时 JSON
   字面量 `null` 与 SQL NULL 都是 Python None，判不出区别（INT-1809 返工 P1）；
3. **内容等价**：对象解压后与评估时 payload deep-equal，sha256 对规范化字节校验通过；
4. **先对象后库 / 失败方向**：对象写失败（存储不可用 / 拿到 local://）→ 整组不落库、
   不写 uri、不留 local:// 假指针；
5. **快照构建吃内存**：本组刚写入的 payload 按 sha 内存命中，不回读对象；别的组
   写下的行每个唯一 sha 只读一次；行形状从 ORM 换成 dict 后快照逐字段一致；
6. **读路径**：include_body 从对象读（载荷形状不变），对象缺失 / sha256 不符
   **显式报错**，绝不返回空上下文；LLM 复检把原因写进 message；
7. 对象口径只有一份实现：C1 回填脚本与在线读写路径共用
   ``shared.infrastructure.raw_payload_store``（规范化字节 / key / gzip 逐项一致）。
"""
import hashlib
import importlib.util
import json
import os
import sys
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.infrastructure.persistence._result_dimension_mixin as dim_mod
import evaluation_service.infrastructure.persistence._result_group_mixin as grm_mod
import evaluation_service.infrastructure.persistence.evaluation_dimension_repository as repo_mod
from evaluation_service.infrastructure.persistence._result_dimension_mixin import (
    DimensionResultMixin,
)
from evaluation_service.infrastructure.persistence._result_group_mixin import (
    GroupResultMixin,
)
from evaluation_service.infrastructure.persistence._result_parse_mixin import (
    ParseDimensionMixin,
)
from shared.infrastructure import raw_payload_store as payload_mod
from shared.infrastructure.raw_payload_store import (
    KIND_REQUEST,
    KIND_RESPONSE,
    RawPayloadCorruptError,
    RawPayloadStore,
    RawPayloadUnavailableError,
    apply_pointer,
    canonical_bytes,
    compress,
    object_key,
    sha256_hex,
)

from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

_RESULT = 701


# ==================== 内存对象存储 / 内存库 ====================

class _MemoryObjects:
    """内存对象存储：uploader 存字节，downloader 取字节，带上传/下载计数。"""

    def __init__(self):
        self.objects = {}
        self.uploads = []
        self.downloads = []

    def upload(self, data, key):
        self.objects[key] = data
        self.uploads.append(key)
        return f'oss://case_result/{key}'

    def download(self, uri):
        from shared.infrastructure.storage import StorageUnavailableError
        self.downloads.append(uri)
        key = uri.split('case_result/', 1)[1]
        if key not in self.objects:
            raise StorageUnavailableError(f'对象不存在: {uri}')
        return self.objects[key]

    def store(self):
        return RawPayloadStore(uploader=self.upload, downloader=self.download)


@pytest.fixture()
def objects():
    return _MemoryObjects()


@pytest.fixture()
def trd_db(monkeypatch, objects):
    """内存 SQLite：test_result_dimensions + dimensions；三处会话/存储全部注入。"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable
    from evaluation_service.infrastructure.persistence.orm_models import (
        Dimension,
        TestResultDimension,
    )

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)

    def _ddl(model):
        ddl = str(CreateTable(model.__table__).compile(engine))
        return ddl.replace('id BIGINT NOT NULL', 'id INTEGER NOT NULL', 1)

    with engine.connect() as conn:
        conn.execute(text(_ddl(Dimension)))
        conn.execute(text(_ddl(TestResultDimension)))
        conn.commit()
    factory = sessionmaker(bind=engine)

    store = objects.store()
    for module in (grm_mod, dim_mod, repo_mod):
        monkeypatch.setattr(module, 'get_db_session', factory)
        monkeypatch.setattr(module, 'raw_payload_store', store)
    monkeypatch.setattr(payload_mod, 'raw_payload_store', store)
    # 不连真实 gRPC（task_service）：TestResult 读取直接返回 None（只需要 api_id/device_id 为空）
    monkeypatch.setattr(grm_mod, 'task_acl_repository',
                        SimpleNamespace(get_test_result_by_id=lambda rid: None))
    return SimpleNamespace(factory=factory, store=store, objects=objects,
                           engine=engine)


class _Host(GroupResultMixin, DimensionResultMixin, ParseDimensionMixin):
    def __init__(self):
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def parse_dimension_result(self, resp, dim, strict=False):
        return 1.0, 1.0


def _dim(dim_id, name=None):
    return {'id': dim_id, 'name': name or f'dim{dim_id}'}


def _insert_trd(factory, **kwargs):
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    session = factory()
    try:
        kwargs.setdefault('test_result_id', _RESULT)
        po = TestResultDimension(**kwargs)
        session.add(po)
        session.commit()
        return po.id
    finally:
        session.close()


def _row(factory, trd_id):
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    session = factory()
    try:
        po = session.get(TestResultDimension, trd_id)
        return SimpleNamespace(
            dimension_value=po.dimension_value, score=po.score,
            evaluation_status=po.evaluation_status,
            api_raw_response=po.api_raw_response,
            api_request_body=po.api_request_body,
            **{col: getattr(po, col) for col in (
                'api_raw_response_uri', 'api_raw_response_sha256',
                'api_raw_response_bytes', 'api_raw_response_content_type',
                'api_raw_response_created_at', 'api_request_body_uri',
                'api_request_body_sha256', 'api_request_body_bytes',
                'api_request_body_content_type', 'api_request_body_created_at')})
    finally:
        session.close()


def _sql_payload_state(trd_db, trd_id):
    """SQL 级判空：两个 JSON 列是 SQL NULL 还是 JSON 字面量 ``null``。

    返回 ``{列名: (is_null, json_type)}``。只有 ``is_null is True`` / ``json_type is
    None`` 才是真 SQL NULL——ORM 读回时两者都是 Python None，判不出区别，
    而 C1 切换门禁用的是 SQL 判据（``IS NOT NULL``）。
    """
    from sqlalchemy import text
    engine = trd_db.engine
    fn = 'json_type' if engine.dialect.name == 'sqlite' else 'json_typeof'
    columns = ('api_raw_response', 'api_request_body')
    sql = ('SELECT ' + ', '.join(f'{c} IS NULL, {fn}({c})' for c in columns)
           + ' FROM test_result_dimensions WHERE id = :id')
    with engine.connect() as conn:
        row = conn.execute(text(sql), {'id': trd_id}).one()
    return {c: (bool(row[i * 2]), row[i * 2 + 1]) for i, c in enumerate(columns)}


def _assert_sql_null(trd_db, trd_id):
    state = _sql_payload_state(trd_db, trd_id)
    for column, (is_null, json_type) in state.items():
        assert is_null is True, f'{column} 不是 SQL NULL: {state}'
        assert json_type is None, f'{column} 是 JSON 字面量 {json_type!r}: {state}'


def _run_group(host, trd_db, group_items, resp_data, per_round=None, req=None):
    payload = {'answer': '设备回答', 'question': '提问'}
    if req is not None:
        payload = req
    resp = dict(resp_data)
    if per_round is not None:
        resp['per_round'] = per_round
    host._build_and_store_algorithm_results = lambda *a, **k: None
    host.check_all_dimensions_completed = lambda *a, **k: False
    host.process_group_dimension_results(
        resp_data=resp, group_items=group_items, task_id=1, test_case_id='C-1',
        result_id=_RESULT, api_request_body=payload,
    )
    return resp, payload


# ==================== 1. 组级去重 + uri-only 落库 ====================

class TestGroupLevelWrite:

    def test_one_upload_per_distinct_value(self, trd_db):
        """6 维度 × 3 轮共 24 行：上传 5 次（resp / req / 3 个不同轮值），不是 24 次。"""
        ids = [_insert_trd(trd_db.factory, dimension_id=dim_id,
                           round_number=None, evaluation_status='pending')
               for dim_id in (1, 2, 3, 4, 5, 6)]
        group_items = [(_dim(dim_id), trd_id)
                       for dim_id, trd_id in zip((1, 2, 3, 4, 5, 6), ids)]
        per_round = [
            {'round_number': 0, 'interruption': {'success_count': 1.0}},
            {'round_number': 1, 'interruption': {'success_count': 0.0}},
            {'round_number': 2, 'interruption': {'success_count': 1.0}},  # 与 round0 同值
        ]
        host = _Host()
        resp, req = _run_group(host, trd_db, group_items,
                               {'name': 'resp-同值'}, per_round=per_round)

        # 上传次数 = 不同值数（resp 1 + req 1 + 轮值 3），不是行数（6 整体行 + 18 逐轮行）
        assert len(trd_db.objects.uploads) == 5, trd_db.objects.uploads
        assert len(set(trd_db.objects.uploads)) == 5
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        session = trd_db.factory()
        try:
            assert session.query(TestResultDimension).count() == 24
        finally:
            session.close()

    def test_rows_are_uri_only(self, trd_db):
        """整体行：五列指针全非空，JSON 两列 **SQL NULL**（不是 JSON 字面量 null）。"""
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='pending')
        host = _Host()
        _run_group(host, trd_db, [(_dim(1), trd_id)], {'name': 'resp'})

        row = _row(trd_db.factory, trd_id)
        assert row.api_raw_response is None and row.api_request_body is None
        _assert_sql_null(trd_db, trd_id)
        for prefix in ('api_raw_response', 'api_request_body'):
            assert getattr(row, f'{prefix}_uri').startswith('oss://case_result/raw/')
            assert len(getattr(row, f'{prefix}_sha256')) == 64
            assert getattr(row, f'{prefix}_bytes') > 0
            assert getattr(row, f'{prefix}_content_type') == 'application/json+gzip'
            assert getattr(row, f'{prefix}_created_at') is not None
        # 没有任何 local:// 假指针
        assert 'local://' not in row.api_raw_response_uri

    def test_round_rows_get_own_payload_pointers(self, trd_db):
        """逐轮行各取自己的 per_round 值（不同轮 → 不同对象）。"""
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='pending')
        per_round = [{'round_number': 0, 'v': 1}, {'round_number': 1, 'v': 2}]
        host = _Host()
        _run_group(host, trd_db, [(_dim(1), trd_id)], {'name': 'resp'},
                   per_round=per_round)

        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        session = trd_db.factory()
        try:
            rounds = session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == _RESULT,
                TestResultDimension.round_number.isnot(None)).all()
            shas = {r.round_number: r.api_raw_response_sha256 for r in rounds}
            assert set(shas) == {0, 1}
            assert shas[0] != shas[1]
            assert shas[0] == sha256_hex(per_round[0])
            assert shas[1] == sha256_hex(per_round[1])
        finally:
            session.close()

    def test_object_content_equals_payload(self, trd_db):
        """对象解压后与评估 payload deep-equal，sha256 校验通过。"""
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='pending')
        host = _Host()
        resp, req = _run_group(host, trd_db, [(_dim(1), trd_id)],
                               {'name': 'resp', 'data': {'中文': [1, 2]}})
        row = _row(trd_db.factory, trd_id)

        assert trd_db.store.load(KIND_RESPONSE, row.api_raw_response_uri,
                                 row.api_raw_response_sha256) == resp
        assert trd_db.store.load(KIND_REQUEST, row.api_request_body_uri,
                                 row.api_request_body_sha256) == req
        # 对象字节 = 规范化 JSON 的 gzip（内容寻址 key 与 bytes 口径一致）
        key = object_key(KIND_RESPONSE, row.api_raw_response_sha256)
        assert trd_db.objects.objects[key] == compress(canonical_bytes(resp))
        assert row.api_raw_response_bytes == len(trd_db.objects.objects[key])


# ==================== 1b. 置空必须落 SQL NULL（返工 P1） ====================

class TestNullWritesAreSqlNull:
    """``Column(JSON)`` 默认 ``none_as_null=False`` 会把 None 落成 JSON 字面量
    ``null``——``IS NOT NULL`` 为真，C1 切换门禁（内联非空而 uri 为空）会把
    「本来没有报文」的行误判成悬空指针。下面三条是 C2 自己会产生置空的三类写点，
    必须都在 SQL 级判空（ORM 读回判 None 区分不出来）。"""

    def test_apply_pointer_none_clears_to_sql_null(self, trd_db):
        """正常写路径：已有内联 JSON 的行被置空 → 五列 + JSON 两列全 SQL NULL。"""
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        # 历史行（切换前写法）：内联 JSON 有值，这样「置空」才真的产生一次 JSON 列 UPDATE
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='completed',
                             api_raw_response={'legacy': 'inline'},
                             api_request_body={'legacy': 'inline'})
        pointer = trd_db.store.store(KIND_RESPONSE, {'a': 1})
        session = trd_db.factory()
        try:
            po = session.get(TestResultDimension, trd_id)
            apply_pointer(po, KIND_RESPONSE, pointer)
            session.commit()
        finally:
            session.close()

        # 重评清指针（apply_pointer(..., None)）：JSON 列与五列一起置空
        session = trd_db.factory()
        try:
            po = session.get(TestResultDimension, trd_id)
            apply_pointer(po, KIND_RESPONSE, None)
            apply_pointer(po, KIND_REQUEST, None)
            session.commit()
            assert po.api_raw_response_uri is None
        finally:
            session.close()

        _assert_sql_null(trd_db, trd_id)

    def test_group_failed_path_clears_to_sql_null(self, trd_db):
        """失败行路径（不带报文）→ 置空落 SQL NULL，门禁仍为 0/0。"""
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='completed',
                             api_raw_response={'legacy': 'inline'},
                             api_request_body={'legacy': 'inline'})

        _Host().update_all_dimensions_in_group_failed(
            group_items=[(_dim(1), trd_id)], error_message='厂商接口超时',
            task_id=1, test_case_id='C-1')

        row = _row(trd_db.factory, trd_id)
        assert row.evaluation_status == 'failed'
        assert row.api_raw_response_uri is None
        _assert_sql_null(trd_db, trd_id)

    def test_reset_score_to_pending_is_sql_null(self, trd_db):
        """重评重置（Core update）→ 两个 JSON 列落 SQL NULL，指针列一并清空。"""
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        # 模拟切换前的历史行：内联 JSON 有值 + 指针也有值（apply_pointer 会清 JSON，
        # 所以指纹直接赋在行上，保持「两列都非空」的前置）
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='completed', score=88.0,
                             api_raw_response={'legacy': 'inline'},
                             api_request_body={'legacy': 'inline'})
        session = trd_db.factory()
        try:
            po = session.get(TestResultDimension, trd_id)
            po.api_raw_response_uri = 'oss://case_result/raw/resp/aa/aa.json.gz'
            po.api_request_body_uri = 'oss://case_result/raw/req/bb/bb.json.gz'
            session.commit()
        finally:
            session.close()
        # 前置：两个 JSON 列确实非空（否则本用例证明不了「置空」）
        before = _sql_payload_state(trd_db, trd_id)
        assert before['api_raw_response'] == (False, 'object'), before
        assert before['api_request_body'] == (False, 'object'), before

        repo_mod.evaluation_dimension_repository.reset_score_to_pending(trd_id)

        row = _row(trd_db.factory, trd_id)
        assert row.evaluation_status == 'pending' and row.score is None
        assert row.api_raw_response_uri is None
        _assert_sql_null(trd_db, trd_id)


# ==================== 2. 失败方向 ====================

class TestFailureDirection:

    def test_storage_unavailable_aborts_group_without_pointers(self, trd_db, monkeypatch):
        """对象写失败 → 整组不落库：行评分/状态不变、无指针、无 local://。"""
        trd_id = _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                             evaluation_status='pending', dimension_value=None)
        host = _Host()
        host._build_and_store_algorithm_results = lambda *a, **k: None
        host.check_all_dimensions_completed = lambda *a, **k: False

        def _explode(data, key):
            from shared.infrastructure.storage import StorageUnavailableError
            raise StorageUnavailableError(f'OSS 不可用: {key}')

        host.process_group_dimension_results.__func__  # 保留真实实现
        monkeypatch.setattr(
            trd_db.store, '_uploader', _explode, raising=False)
        monkeypatch.setattr(payload_mod.raw_payload_store, '_uploader', _explode,
                            raising=False)

        with pytest.raises(Exception) as exc:
            host.process_group_dimension_results(
                resp_data={'name': 'x'}, group_items=[(_dim(1), trd_id)],
                task_id=1, test_case_id='C-1', result_id=_RESULT,
                api_request_body={'a': 1})

        assert 'StorageUnavailableError' in type(exc.value).__name__
        row = _row(trd_db.factory, trd_id)
        assert row.evaluation_status == 'pending'
        assert row.api_raw_response_uri is None
        assert row.api_request_body_uri is None
        assert not any('local://' in (u or '') for u in trd_db.objects.uploads)

    def test_local_uri_is_rejected(self):
        """uploader 返回 local://（静默落本地盘）→ 视为存储不可用直接失败。"""
        store = RawPayloadStore(uploader=lambda data, key: f'local://case_result/{key}')
        with pytest.raises(Exception) as exc:
            store.store(KIND_RESPONSE, {'a': 1})
        assert 'local://' in str(exc.value)

    def test_group_cache_dedups_and_counts(self):
        cache = RawPayloadStore(
            uploader=lambda data, key: f'oss://case_result/{key}').new_group_cache()
        assert cache.warm(KIND_RESPONSE, {'a': 1}) is not None
        assert cache.warm(KIND_RESPONSE, {'a': 1}) is not None
        assert cache.warm(KIND_RESPONSE, {'a': 2}) is not None
        assert cache.uploaded == 2 and cache.reused == 1
        assert cache.warm(KIND_REQUEST, None) is None


# ==================== 3. 快照构建：吃内存、按 sha 读一次 ====================

class TestSnapshotPayloadSource:

    def _seed(self, trd_db, dim_id, round_number, value, store):
        pointer = store.store(KIND_RESPONSE, value)
        trd_id = _insert_trd(trd_db.factory, dimension_id=dim_id,
                             round_number=round_number, evaluation_status='completed')
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        session = trd_db.factory()
        try:
            po = session.get(TestResultDimension, trd_id)
            apply_pointer(po, KIND_RESPONSE, pointer)
            session.commit()
        finally:
            session.close()
        return trd_id

    def test_current_group_payload_served_from_memory(self, trd_db):
        """本组刚写入的值走内存（0 次对象读）；别的组写下的行按 sha 读一次。"""
        current = {'dim': 'current'}
        other = {'dim': 'other'}
        self._seed(trd_db, dim_id=99, round_number=None, value=other,
                   store=trd_db.store)
        self._seed(trd_db, dim_id=1, round_number=None, value=current,
                   store=trd_db.store)
        # 同值再落两行（同 sha）——对象只应读一次
        self._seed(trd_db, dim_id=2, round_number=None, value=other,
                   store=trd_db.store)

        cache = trd_db.store.new_group_cache()
        cache.warm(KIND_RESPONSE, current)          # 本组内存 payload
        trd_db.objects.downloads.clear()
        trd_db.store.read_count = 0

        rows = _Host()._load_dim_result_rows(_RESULT, cache)

        assert trd_db.store.read_count == 1          # 只有 other 的 sha 读了对象
        assert len(trd_db.objects.downloads) == 1
        by_dim = {r['dimension_id']: r['api_raw_response'] for r in rows}
        assert by_dim[1] == current and by_dim[2] == other and by_dim[99] == other
        # 行形状：只有快照构建需要的三个字段（不带 ORM 实体 / JSON 列）
        assert set(rows[0]) == {'dimension_id', 'round_number', 'api_raw_response'}

    def test_rows_without_pointer_yield_none(self, trd_db):
        _insert_trd(trd_db.factory, dimension_id=1, round_number=None,
                    evaluation_status='completed')
        rows = _Host()._load_dim_result_rows(_RESULT, None)
        assert rows == [{'dimension_id': 1, 'round_number': None,
                         'api_raw_response': None}]

    def test_snapshot_algorithm_results_unchanged_by_row_shape(self):
        """快照内容只取决于 payload 值：dict 行与旧 ORM 行逐字段一致。"""
        from report_service.application.services.report_data_builder import (
            ReportDataBuilder,
        )
        payload = {'interruption': {'success_count': 2.0, 'response_latency_avg_ms': 300}}
        aux_params_map = {
            11: [{'param': {'param_code': 'success_count',
                            'field_path': 'interruption.success_count',
                            'field_type': 'number'},
                  'dimension_name': '打断成功数量'}],
        }
        dict_rows = [{'dimension_id': 11, 'round_number': None,
                      'api_raw_response': payload},
                     {'dimension_id': 11, 'round_number': 0,
                      'api_raw_response': payload}]
        orm_rows = [SimpleNamespace(dimension_id=11, round_number=None,
                                    api_raw_response=payload),
                    SimpleNamespace(dimension_id=11, round_number=0,
                                    api_raw_response=payload)]

        def _build(rows):
            return ReportDataBuilder.build_algorithm_results_for_result(
                SimpleNamespace(), 'dev', {}, {}, aux_params_map, rows, [],
                'interruption_metrics')

        assert _build(dict_rows) == _build(orm_rows)


# ==================== 4. 读路径（include_body 从对象读） ====================

class TestIncludeBodyReadPath:

    def _seed(self, trd_db, resp=None, req=None):
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        session = trd_db.factory()
        try:
            if session.get(Dimension, 7) is None:
                session.add(Dimension(
                    id=7, name='LLM语义评分', dimension_type='main',
                    task_type_code='llm_judge', type='auto', result_type=1,
                    result_min=0.0, result_max=5.0, weight=1, sort_order=0,
                    estimated_exec_time=10, rule={}, api_settings={}, status=True,
                    deleted=False, api_status='online', api_endpoints=[],
                    api_url=None, score_unit='分', statistic_method='average',
                    created_at=None, updated_at=None))
            po = TestResultDimension(
                test_result_id=_RESULT, dimension_id=7, score=4.0,
                evaluation_status='completed')
            if resp is not None:
                apply_pointer(po, KIND_RESPONSE, trd_db.store.store(KIND_RESPONSE, resp))
            if req is not None:
                apply_pointer(po, KIND_REQUEST, trd_db.store.store(KIND_REQUEST, req))
            session.add(po)
            session.commit()
            return po.id
        finally:
            session.close()

    def test_include_body_returns_parsed_payloads(self, trd_db):
        trd_id = self._seed(trd_db, resp={'reasoning': '旧评语'}, req={'answer': 'a'})
        items = repo_mod.evaluation_dimension_repository \
            .get_dimension_results_with_names_by_result_ids([_RESULT], include_body=True)
        assert len(items) == 1
        assert items[0]['id'] == trd_id
        assert items[0]['api_raw_response'] == {'reasoning': '旧评语'}
        assert items[0]['api_request_body'] == {'answer': 'a'}
        assert items[0]['dimension_name'] == 'LLM语义评分'

    def test_default_without_body(self, trd_db):
        self._seed(trd_db, resp={'a': 1}, req={'b': 2})
        items = repo_mod.evaluation_dimension_repository \
            .get_dimension_results_with_names_by_result_ids([_RESULT])
        assert 'api_raw_response' not in items[0]
        assert 'api_request_body' not in items[0]
        assert trd_db.objects.downloads == []   # 不带 body 就不碰对象存储

    def test_corrupt_object_raises_explicitly(self, trd_db):
        self._seed(trd_db, resp={'reasoning': 'x'})
        # 篡改对象字节 → sha256 校验失败
        for key in list(trd_db.objects.objects):
            if key.startswith('raw/resp/'):
                trd_db.objects.objects[key] = compress(b'{"reasoning":"tampered"}')
        with pytest.raises(RawPayloadCorruptError) as exc:
            repo_mod.evaluation_dimension_repository \
                .get_dimension_results_with_names_by_result_ids([_RESULT], include_body=True)
        assert 'sha256' in str(exc.value)

    def test_missing_object_raises_explicitly(self, trd_db):
        self._seed(trd_db, resp={'reasoning': 'x'})
        trd_db.objects.objects.clear()
        with pytest.raises(RawPayloadUnavailableError):
            repo_mod.evaluation_dimension_repository \
                .get_dimension_results_with_names_by_result_ids([_RESULT], include_body=True)

    def test_memory_cache_reads_each_sha_once(self, trd_db):
        for _ in range(3):
            self._seed(trd_db, resp={'same': 'payload'})
        items = repo_mod.evaluation_dimension_repository \
            .get_dimension_results_with_names_by_result_ids([_RESULT], include_body=True)
        assert len(items) == 3
        assert all(it['api_raw_response'] == {'same': 'payload'} for it in items)
        assert trd_db.store.read_count == 1      # 内容寻址：同 sha 只下一次


# ==================== 5. LLM 复检显式报错 ====================

class TestAiReviewExplicitErrors:

    def test_payload_read_error_surfaces_reason(self, monkeypatch):
        from evaluation_service.application.handlers import ai_review_checker as arc
        from evaluation_service.application.queries import evaluation_query_service as qs

        monkeypatch.setattr(
            qs.evaluation_query_service, 'get_dimension_results_by_result_ids',
            lambda ids, include_body=False: {
                'success': False,
                'message': 'resp 对象 sha256 校验失败 oss://case_result/raw/resp/aa/x.json.gz',
            })
        resp = arc.ai_review_checker.execute(result_id=1, dimension_id=7)
        assert resp['success'] is False
        assert '读取维度原始报文失败' in resp['message']
        assert 'sha256' in resp['message']

    def test_no_payload_does_not_score_with_empty_context(self, monkeypatch):
        from evaluation_service.application.handlers import ai_review_checker as arc
        from evaluation_service.application.queries import evaluation_query_service as qs

        monkeypatch.setattr(
            qs.evaluation_query_service, 'get_dimension_results_by_result_ids',
            lambda ids, include_body=False: {'success': True, 'data': {'items': [{
                'id': 1, 'dimension_id': 7, 'dimension_name': 'LLM',
                'score': 3.0, 'evaluation_status': 'completed',
                'round_number': None, 'api_request_body': None,
                'api_raw_response': None,
            }]}})
        monkeypatch.setattr(
            arc.ai_review_checker, '_load_dim_config',
            lambda dim_id: {'id': 7, 'task_type_code': 'llm_judge',
                            'dimension_type': 'main'})
        resp = arc.ai_review_checker.execute(result_id=1, dimension_id=7)
        assert resp['success'] is False
        assert '无原始报文' in resp['message']


# ==================== 6. 对象口径只有一份实现 ====================

class TestCaliberSingleSource:

    def test_backfill_script_shares_caliber(self):
        path = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202610',
                            'backfill_raw_payload_pointers_int1807.py')
        spec = importlib.util.spec_from_file_location('int1807_backfill_caliber', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules['int1807_backfill_caliber'] = module
        spec.loader.exec_module(module)

        value = {'b': [1, 2], '中文': '值', 'a': None}
        assert module.canonical_bytes(value) == canonical_bytes(value)
        assert module.sha256_hex(value) == sha256_hex(value)
        assert module.compress(module.canonical_bytes(value)) == \
            compress(canonical_bytes(value))
        assert module.object_key('resp', 'ab' * 32) == object_key('resp', 'ab' * 32)
        assert module.CONTENT_TYPE == 'application/json+gzip'
        # 规范化字节本身是确定性的：键序不同 → 同一对象
        assert sha256_hex({'x': 1, 'y': 2}) == sha256_hex({'y': 2, 'x': 1})
        assert hashlib.sha256(canonical_bytes(value)).hexdigest() == sha256_hex(value)
