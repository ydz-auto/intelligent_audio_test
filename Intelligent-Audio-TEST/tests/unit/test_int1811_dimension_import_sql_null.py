# -*- coding: utf-8 -*-
"""维度导入的原始报文口径：从「JSON 列落 SQL NULL」到「列已删、只留指针」（M1）

INT-1811 返工时代的契约：``Column(JSON)`` 默认 ``none_as_null=False`` 会把 Python
``None`` 落成 JSON 字面量 ``null``，``IS NOT NULL`` 为真，于是「本来就没有报文」的行
导入后被 C1 门禁（内联非空而 uri 为空）判成悬空指针；修法是 ``_coerce_row`` 对值为
None 的 JSON 列不放进 INSERT。

M1（INT-1813）删掉两列后，这套 SQL NULL 判据随列一起消失，本文件改为守住**新**契约：

1. 两列既不在 ORM 映射里、也不在库里（``_JSON_FIELDS`` 为空集，旧包里的这两个键
   走 ``_RETIRED_COLUMNS`` 静默丢弃——不按「未知列」报警）；
2. 导入只写指针五列，报文本身在对象里；
3. 整包 ``import_rows`` 与增量 ``merge`` 仍共用同一个 ``_coerce_row``。

不连真库：SQLite 临时库 + 真实 ORM / 仓储。
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


def session_gate(db, uri_col: str, sha_col: str) -> int:
    """M1 后的等价门禁：有指针却没 sha（断链）的行数。"""
    session = db.get_db_session()
    try:
        return session.execute(text(
            f"SELECT count(*) FROM test_result_dimensions "
            f"WHERE {uri_col} IS NOT NULL AND {sha_col} IS NULL")).scalar()
    finally:
        session.close()


def test_coerce_row_drops_retired_json_columns():
    """M1：两列已删——旧包带来的这两个键（有值或 None）一律不进 INSERT。"""
    from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
        _RETIRED_COLUMNS,
        _JSON_FIELDS,
        _coerce_row,
    )

    assert {'api_raw_response', 'api_request_body'} == _RETIRED_COLUMNS
    assert not ({'api_raw_response', 'api_request_body'} & _JSON_FIELDS)

    row = _coerce_row({
        'api_raw_response': None,
        'api_request_body': None,
        'api_raw_response_uri': 'oss://case_result/raw/resp/aa/aa.json.gz',
        'round_number': None,
    })
    assert 'api_raw_response' not in row
    assert 'api_request_body' not in row
    # 非 JSON 列仍显式写 None（round_number NULL = 整体评估行，语义依赖它）
    assert 'round_number' in row and row['round_number'] is None
    assert row['api_raw_response_uri'].startswith('oss://')

    # 1.0 旧包里的内联报文在搬运侧已物化成对象（写指针），行上不再带该值
    retired = _coerce_row({'api_raw_response': {'reasoning': 'x'}})
    assert 'api_raw_response' not in retired


def test_merge_repository_shares_the_same_coercion():
    """增量回导（merge）与整包导入共用 _coerce_row，修一处即两条链路同修"""
    from evaluation_service.infrastructure.persistence import (
        dimension_merge_repository,
        dimension_transfer_repository,
    )
    assert (dimension_merge_repository._coerce_row
            is dimension_transfer_repository._coerce_row)


def test_import_rows_lands_pointers_without_retired_columns(db):
    from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
        DimensionTransferRepository,
    )

    repo = DimensionTransferRepository()
    rows = [
        # 1.0 旧包行：带着已删列（None），搬运侧已写好指针 —— 导入只认指针
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
            'api_raw_response_sha256': 'c' * 64,
            'api_request_body_sha256': 'd' * 64,
        },
    ]
    repo.import_rows(rows, {})

    session = db.get_db_session()
    try:
        # 已删列不在表里（导入不会尝试写它们）
        columns = {row[0] for row in session.execute(text(
            "SELECT name FROM pragma_table_info('test_result_dimensions')"))}
        assert 'api_raw_response' not in columns
        assert 'api_request_body' not in columns
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

    # M1 后 C1 门禁不适用（列已删）；等价的不变量是「有 uri 必有 sha256」
    for uri_col, sha_col in (('api_raw_response_uri', 'api_raw_response_sha256'),
                             ('api_request_body_uri', 'api_request_body_sha256')):
        broken = session_gate(db, uri_col, sha_col)
        assert broken == 0, (uri_col, broken)
