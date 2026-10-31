# -*- coding: utf-8 -*-
"""INT-2289 回归：设备级参数覆盖行可按作用域判重建出来。

缺陷：`CreateParam` 的判重调用 `FindParamByCode` 不带 `device_id`，仓储只按
`(algorithm_type, param_code, direction)` 查，任何算法级同名行都会命中 →
为已有算法级参数新增设备覆盖一律 400，第三层（设备覆盖 > 绑定策略 > 算法级
默认）无法通过 API/UI 构造。而表上本来就是两条部分唯一索引：

- `uq_algorithm_device_param_algo_level`：`(algorithm_type, param_code,
  direction) WHERE deleted = false AND device_id IS NULL`
- `uq_algorithm_device_param_device_level`：`(algorithm_type, device_id,
  param_code, direction) WHERE deleted = false AND device_id IS NOT NULL`

本文件三段覆盖：
1. 仓储 `find_by_code` 按 device_id 作用域过滤（0 = 算法级、非 0 = 该设备行，
   API 参数忽略 device_id）；
2. `AlgorithmParamCrudService.create_param` 把作用的 device_id 透传给判重；
3. 同名 code 时设备覆盖行覆盖算法级默认值，覆盖行删除后回落到算法级。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)

ALGO = 'voice_llm'
DEVICE_A = 12
DEVICE_B = 13

_TABLES = ('AlgorithmDeviceParam', 'AlgorithmApiParam')


def _models():
    from algorithm_service.infrastructure.persistence import models as _m
    return _m


@pytest.fixture(scope='module')
def db():
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-2289 需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    mods = _models()
    Base.metadata.create_all(
        bind=engine, tables=[getattr(mods, n).__table__ for n in _TABLES])
    # SQLite 会丢掉 postgresql_where 谓词，把两条「作用域内唯一」索引渲染成
    # 整列唯一，算法级与设备级同 natural key 时连播种都插不进去（与 PG 语义
    # 不符）。与 test_int2266 同口径，去掉 SQLite 特有的整列唯一索引。
    if engine.dialect.name == 'sqlite':
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(
                'DROP INDEX IF EXISTS uq_algorithm_device_param_algo_level'))
    yield engine
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    session = get_db_session()
    mods = _models()
    for name in _TABLES:
        session.query(getattr(mods, name)).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()
    yield


def _seed_device_param(device_id, param_code, direction='output',
                       default_value='x', name=None):
    mods = _models()
    session = get_db_session()
    session.add(mods.AlgorithmDeviceParam(
        algorithm_type=ALGO, device_id=device_id, param_code=param_code,
        param_name=name or param_code, direction=direction, param_type='text',
        default_value=default_value, deleted=False,
    ))
    session.commit()
    session.expunge_all()
    remove_db_session()


def _repo():
    from algorithm_service.infrastructure.persistence._algorithm_param_repository \
        import AlgorithmParamRepository
    return AlgorithmParamRepository()


# ---------------------------------------------------------------- 1. 仓储作用域

def test_find_by_code_algorithm_level_ignores_device_rows(clean_tables):
    """算法级判重只认 device_id IS NULL 行，不被设备覆盖行命中/遮蔽。"""
    _seed_device_param(DEVICE_A, 'matrix_dev12_p')
    repo = _repo()

    # 存在设备覆盖行 ≠ 算法级已有同名参数 → 算法级判重应为「无」
    assert repo.find_by_code(ALGO, 'matrix_dev12_p', 'output', 'device') is None

    _seed_device_param(None, 'wav_path', default_value='ALGO-WAV')
    found = repo.find_by_code(ALGO, 'wav_path', 'output', 'device')
    assert found is not None
    assert found['device_id'] is None
    assert found['default_value'] == 'ALGO-WAV'


def test_find_by_code_device_level_isolated_per_device(clean_tables):
    """设备级判重按 (algorithm_type, device_id, param_code, direction)。"""
    _seed_device_param(None, 'wav_path', default_value='ALGO-WAV')
    _seed_device_param(DEVICE_A, 'matrix_dev12_p')

    repo = _repo()
    # 为「已有算法级同名参数」建另一台设备的覆盖：不应被判重命中
    assert repo.find_by_code(ALGO, 'wav_path', 'output', 'device',
                             DEVICE_B) is None
    # 同设备同键重复 → 命中
    assert repo.find_by_code(ALGO, 'matrix_dev12_p', 'output', 'device',
                             DEVICE_A) is not None
    # 换设备 → 不命中
    assert repo.find_by_code(ALGO, 'matrix_dev12_p', 'output', 'device',
                             DEVICE_B) is None


def test_find_by_code_api_params_ignore_device_id(clean_tables):
    """API 参数表无 device_id 作用域，传 device_id 不影响结果。"""
    mods = _models()
    session = get_db_session()
    session.add(mods.AlgorithmApiParam(
        algorithm_type=ALGO, api_id=None, param_code='api_key',
        direction='input', param_type='text', deleted=False,
    ))
    session.commit()
    session.expunge_all()
    remove_db_session()

    repo = _repo()
    assert repo.find_by_code(ALGO, 'api_key', 'input', 'api',
                             DEVICE_B) is not None
    assert repo.find_by_code(ALGO, 'api_key', 'input', 'api') is not None


# ---------------------------------------------------------------- 2. 创建判重透传

class _FakeRepo:
    """记录判重调用的假仓储（不触 gRPC）。"""

    def __init__(self, existing=None):
        self.existing = existing
        self.find_calls = []
        self.created = []

    def find_device_param_by_code(self, algorithm_type, param_code, direction,
                                  device_id=None):
        self.find_calls.append((algorithm_type, param_code, direction, device_id))
        return self.existing

    def find_api_param_by_code(self, algorithm_type, param_code, direction):
        self.find_calls.append((algorithm_type, param_code, direction, 'api'))
        return self.existing

    def create_device_param(self, data):
        self.created.append(dict(data))
        return {'id': 901, **data}

    def create_api_param(self, data):
        self.created.append(dict(data))
        return {'id': 902, **data}

    def commit(self):
        pass

    def rollback(self):
        pass


def _service_with(repo):
    from task_service.application.algorithm.algorithm_param_crud_service import (
        AlgorithmParamCrudService,
    )
    service = object.__new__(AlgorithmParamCrudService)
    service.repo = repo
    return service


def _payload(**overrides):
    payload = {
        'param_type_source': 'device',
        'algorithm_type': ALGO,
        'device_id': DEVICE_B,
        'param_code': 'wav_path',
        'param_type': 'text',
        'direction': 'output',
        'default_value': 'OVERRIDE-WAV',
    }
    payload.update(overrides)
    return payload


def test_create_param_passes_device_id_to_dedupe():
    """设备覆盖创建：判重必须带 device_id，且不被算法级同名行拦截。"""
    repo = _FakeRepo(existing=None)
    result = _service_with(repo).create_param(_payload())

    assert result['success'] is True
    assert repo.find_calls == [(ALGO, 'wav_path', 'output', DEVICE_B)]
    assert repo.created[0]['device_id'] == DEVICE_B


def test_create_param_algorithm_level_dedupes_without_device():
    """算法级创建：不带 device_id（None）判重，口径仍为算法级。"""
    repo = _FakeRepo(existing=None)
    payload = _payload()
    payload.pop('device_id')
    result = _service_with(repo).create_param(payload)

    assert result['success'] is True
    assert repo.find_calls == [(ALGO, 'wav_path', 'output', None)]


def test_create_param_duplicate_same_scope_still_rejected():
    """同作用域重复仍 400，且提示带上设备号。"""
    repo = _FakeRepo(existing={'id': 1, 'device_id': DEVICE_B})
    result = _service_with(repo).create_param(_payload())

    assert result['success'] is False
    assert f"'{DEVICE_B}'" in result['message']


# ---------------------------------------------------------------- 3. 解析覆盖生效

def _cache(rows):
    from algorithm_service.infrastructure.persistence.config_cache import (
        AlgorithmConfigCache,
    )
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = {
        'algorithms': {},
        'device_params': {ALGO: AlgorithmConfigCache._serialize_params(rows)},
        'api_params': {ALGO: []},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'evaluation_dimension_params': {},
        'mappings': {ALGO: []},
        'profile_params': {},
        'profile_mappings': {},
        'api_bindings': {},
        'device_bindings': {},
        'profile_algorithm_types': {},
    }
    return cache


_ALGO_LEVEL = {
    'param_code': 'wav_path', 'param_name': '算法级音频', 'param_type': 'text',
    'direction': 'output', 'ui_order': 1,
}
_DEVICE_OVERRIDE = {
    'param_code': 'wav_path', 'param_name': '设备覆盖音频', 'param_type': 'text',
    'direction': 'output', 'ui_order': 1, 'device_id': DEVICE_B,
}


def test_device_override_wins_over_algorithm_level_then_falls_back():
    """同名 code：设备覆盖行盖掉算法级默认；覆盖行删除（不在快照）即回落。"""
    by_code = lambda c, d: {r['code']: r for r in c.get_device_params(ALGO, d)}

    both = _cache([_ALGO_LEVEL, _DEVICE_OVERRIDE])
    assert by_code(both, DEVICE_B)['wav_path']['name'] == '设备覆盖音频'
    # 其它设备仍是算法级默认
    assert by_code(both, DEVICE_A)['wav_path']['name'] == '算法级音频'

    after_delete = _cache([_ALGO_LEVEL])
    assert by_code(after_delete, DEVICE_B)['wav_path']['name'] == '算法级音频'
