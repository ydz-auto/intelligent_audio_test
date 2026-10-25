# -*- coding: utf-8 -*-
"""INT-1811 返工：维度导入的 JSON 列必须落 SQL NULL，不能落 JSON 字面量 null

门禁（C2 读写切换的验收口径，卡面验收 #2）::

    api_raw_response IS NOT NULL AND api_raw_response_uri IS NULL   → 0
    api_request_body  IS NOT NULL AND api_request_body_uri IS NULL  → 0

`Column(JSON)` 默认 ``none_as_null=False``：显式传 Python ``None`` 会被序列化成
JSON 字面量 ``null``（``api_raw_response::text = 'null'``），``IS NOT NULL`` 为真；
于是「本来就没有报文」的行（整体评估行，源库两列都是 SQL NULL）导入后被门禁
判成悬空指针。修法：``_coerce_row`` 对值为 None 的 JSON 列不放进 INSERT，
由 ORM 缺省该列 → 落 SQL NULL。

不连真库：SQLite 临时库 + 真实 ORM / 仓储（整包 ``import_rows`` 与增量
``merge`` 共用同一个 ``_coerce_row``）。
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger, create_engine, text  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    # 与 test_data_transfer_roundtrip 同口径：SQLite 下 BIGINT 主键编译为
    # INTEGER 才能作为 rowid 别名自增（生产为 Postgres BIGSERIAL）
    return 'INTEGER'


@pytest.fixture()
def db():
    import shared.models.database as database
    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    try:
        yield database
    finally:
        database.remove_db_session()
        engine.dispose()
        os.remove(path)


_GATE_SQL = (
    "SELECT count(*) FROM test_result_dimensions "
    "WHERE {json_col} IS NOT NULL AND {uri_col} IS NULL")


def _gate(db, json_col: str, uri_col: str) -> int:
    session = db.get_db_session()
    try:
        return session.execute(text(
            _GATE_SQL.format(json_col=json_col, uri_col=uri_col))).scalar()
    finally:
        session.close()


def test_coerce_row_drops_none_json_columns():
    from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
        _coerce_row,
        _JSON_FIELDS,
    )

    assert {'api_raw_response', 'api_request_body'} <= _JSON_FIELDS

    row = _coerce_row({
        'api_raw_response': None,
        'api_request_body': None,
        'api_raw_response_uri': 'oss://case_result/raw/resp/aa/aa.json.gz',
        'round_number': None,
    })
    # JSON 列置空 = 不放进 INSERT（ORM 缺省 → SQL NULL）
    assert 'api_raw_response' not in row
    assert 'api_request_body' not in row
    # 非 JSON 列仍显式写 None（round_number NULL = 整体评估行，语义依赖它）
    assert 'round_number' in row and row['round_number'] is None
    assert row['api_raw_response_uri'].startswith('oss://')

    # 有内容时原样保留（1.0 旧包物化前 / 正常报文）
    kept = _coerce_row({'api_raw_response': {'reasoning': 'x'}})
    assert kept['api_raw_response'] == {'reasoning': 'x'}


def test_merge_repository_shares_the_same_coercion():
    """增量回导（merge）与整包导入共用 _coerce_row，修一处即两条链路同修"""
    from evaluation_service.infrastructure.persistence import (
        dimension_merge_repository,
        dimension_transfer_repository,
    )
    assert (dimension_merge_repository._coerce_row
            is dimension_transfer_repository._coerce_row)


def test_import_rows_lands_sql_null_and_gate_is_zero(db):
    from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
        DimensionTransferRepository,
    )

    repo = DimensionTransferRepository()
    rows = [
        # 无报文行（整体评估行）：指针有值、内联两列 None —— 返工前落成 JSON null
        {
            'id': 1, 'test_result_id': 1, 'dimension_id': 1,
            'round_number': None, 'score': 0.9,
            'api_raw_response': None, 'api_request_body': None,
            'api_raw_response_uri': 'oss://case_result/raw/resp/aa/aa.json.gz',
            'api_request_body_uri': 'oss://case_result/raw/req/bb/bb.json.gz',
            'api_raw_response_sha256': 'a' * 64,
            'api_request_body_sha256': 'b' * 64,
        },
        # 正常行：uri 有值 + 内联已置空
        {
            'id': 2, 'test_result_id': 1, 'dimension_id': 2,
            'round_number': 0, 'score': 0.8,
            'api_raw_response': None, 'api_request_body': None,
            'api_raw_response_uri': 'oss://case_result/raw/resp/cc/cc.json.gz',
            'api_request_body_uri': 'oss://case_result/raw/req/dd/dd.json.gz',
        },
    ]
    repo.import_rows(rows, {})

    session = db.get_db_session()
    try:
        # 无报文行：两列必须是 SQL NULL（门禁的「内联非空」不能命中它）
        raw_null = session.execute(text(
            "SELECT api_raw_response IS NULL, api_request_body IS NULL "
            "FROM test_result_dimensions WHERE id = 1")).one()
        assert tuple(raw_null) == (1, 1)
        # 非报文列不受影响
        round_number = session.execute(text(
            "SELECT round_number FROM test_result_dimensions WHERE id = 1")).scalar()
        assert round_number is None
        score = session.execute(text(
            "SELECT score FROM test_result_dimensions WHERE id = 2")).scalar()
        assert score == pytest.approx(0.8)
        # 指针列照常写入
        uri = session.execute(text(
            "SELECT api_raw_response_uri FROM test_result_dimensions WHERE id = 2")).scalar()
        assert uri.endswith('cc.json.gz')
    finally:
        session.close()

    assert _gate(db, 'api_raw_response', 'api_raw_response_uri') == 0
    assert _gate(db, 'api_request_body', 'api_request_body_uri') == 0
