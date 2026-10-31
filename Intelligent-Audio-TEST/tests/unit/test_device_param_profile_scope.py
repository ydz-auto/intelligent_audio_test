# -*- coding: utf-8 -*-
"""设备级参数策略（device_param_bindings）解析与绑定单测。

语义（与 API 实例作用域同构）：
1. 设备参数解析三层：设备覆盖（device_id 行）> 设备绑定策略（scope=device）
   > 算法类型级默认（device_id IS NULL）；
2. 映射分桶同样三层：设备覆盖 > 设备绑定策略 > 算法级默认；
3. 绑定只接受 scope='device' 的策略，profile_id 空 = 解绑。

解析用例用 ``object.__new__(AlgorithmConfigCache)`` 直接安装快照，不连库；
绑定用例走 conftest 的文件型 SQLite（与 test_param_profile_crud 同口径）。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)
from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from algorithm_service.infrastructure.persistence.models import (  # noqa: E402
    DeviceParamBinding,
    ParamProfile,
    ParamProfileMapping,
    ParamProfileParam,
)
from algorithm_service.infrastructure.persistence._param_profile_repositories \
    import ParamProfileCommandRepository  # noqa: E402

ALGO = 'ut_device_profile'
PROFILE = 21
DEVICE_BOUND = 501
DEVICE_OTHER = 502
DIM_1 = 1
DIM_2 = 2

PROFILE_PARAMS = [
    {'param_code': 'audio_in', 'param_name': '策略音频', 'param_type': 'audio_stream',
     'direction': 'input', 'ui_order': 1},
    {'param_code': 'policy_only', 'param_name': '策略独有', 'param_type': 'text',
     'direction': 'input', 'ui_order': 2},
]

ALGO_LEVEL_PARAMS = [
    {'param_code': 'audio_in', 'param_name': '算法级音频', 'param_type': 'audio_stream',
     'direction': 'input', 'ui_order': 1},
    {'param_code': 'asr_text', 'param_name': '算法级文本', 'param_type': 'text',
     'direction': 'output', 'ui_order': 2},
]

DEVICE_OVERRIDES = [
    {'param_code': 'audio_in', 'param_name': '设备5音频', 'param_type': 'audio_stream',
     'direction': 'input', 'device_id': DEVICE_BOUND, 'ui_order': 1},
    {'param_code': 'audio_in', 'param_name': '设备6音频', 'param_type': 'audio_stream',
     'direction': 'input', 'device_id': DEVICE_OTHER, 'ui_order': 1},
]

# 算法级映射：case 桶 2 行 + evaluation 桶 2 行
ALGO_MAPPINGS = [
    {'algorithm_type': ALGO, 'source': 'case', 'source_direction': 'input',
     'source_param': 'asr_result', 'target_param': 'audio_in', 'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'case', 'source_direction': 'input',
     'source_param': 'tts_text', 'target_param': 'audio_in', 'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'device', 'source_direction': 'output',
     'source_param': 'dev_out', 'target_param': 'wer', 'dimension_id': DIM_1,
     'dimension_name': '识别准确率'},
]

# 设备覆盖映射：改 asr_result 的目标 + 覆盖维度 1 的目标
DEVICE_MAPPINGS = [
    {'algorithm_type': ALGO, 'device_id': DEVICE_BOUND, 'source': 'case',
     'source_direction': 'input', 'source_param': 'asr_result',
     'target_param': 'audio_in_v2', 'dimension_id': None},
    {'algorithm_type': ALGO, 'device_id': DEVICE_OTHER, 'source': 'case',
     'source_direction': 'input', 'source_param': 'asr_result',
     'target_param': 'audio_in_dev6', 'dimension_id': None},
    {'algorithm_type': ALGO, 'device_id': DEVICE_BOUND, 'source': 'device',
     'source_direction': 'output', 'source_param': 'dev_out',
     'target_param': 'wer_v2', 'dimension_id': DIM_1, 'dimension_name': '识别准确率'},
]

# 策略映射：case 桶覆盖 asr_result + 策略独有源；evaluation 桶新增维度 2
PROFILE_MAPPINGS = [
    {'algorithm_type': ALGO, 'source': 'case', 'source_direction': 'input',
     'source_param': 'asr_result', 'target_param': 'audio_in_policy',
     'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'case', 'source_direction': 'input',
     'source_param': 'policy_src', 'target_param': 'audio_in', 'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'device', 'source_direction': 'output',
     'source_param': 'dev_out', 'target_param': 'wer_policy', 'dimension_id': DIM_1,
     'dimension_name': '识别准确率'},
    {'algorithm_type': ALGO, 'source': 'device', 'source_direction': 'output',
     'source_param': 'dev_out', 'target_param': 'wer_dim2', 'dimension_id': DIM_2,
     'dimension_name': '响应延迟'},
]


def _cache() -> AlgorithmConfigCache:
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = {
        'algorithms': {},
        'device_params': {
            ALGO: AlgorithmConfigCache._serialize_params(
                ALGO_LEVEL_PARAMS + DEVICE_OVERRIDES),
        },
        'api_params': {ALGO: []},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'evaluation_dimension_params': {},
        'mappings': {
            ALGO: AlgorithmConfigCache._serialize_mappings(
                ALGO_MAPPINGS + DEVICE_MAPPINGS, None, ALGO),
        },
        'profile_params': {
            PROFILE: AlgorithmConfigCache._serialize_params(PROFILE_PARAMS),
        },
        'profile_mappings': {
            PROFILE: AlgorithmConfigCache._serialize_mappings(
                PROFILE_MAPPINGS, None, ALGO),
        },
        'api_bindings': {},
        'device_bindings': {DEVICE_BOUND: PROFILE},
    }
    return cache


def _params_by_code(rows):
    return {row['code']: row for row in rows}


# ---------------------------------------------------------------- 参数三层解析

def test_device_params_without_device_id_only_algorithm_level():
    rows = _cache().get_device_params(ALGO)
    assert {row['code'] for row in rows} == {'audio_in', 'asr_text'}
    # 其它设备的覆盖行不会串进来
    assert _params_by_code(rows)['audio_in']['name'] == '算法级音频'


def test_device_params_bound_device_prefers_device_then_profile_then_level():
    rows = _cache().get_device_params(ALGO, DEVICE_BOUND)
    by_code = _params_by_code(rows)
    assert by_code['audio_in']['name'] == '设备5音频'   # 设备覆盖最优先
    assert 'policy_only' in by_code                        # 策略独有行保留
    assert by_code['asr_text']['name'] == '算法级文本'  # 未被覆盖的算法级行保留


def test_device_params_unbound_device_falls_back_to_level_and_overrides():
    rows = _cache().get_device_params(ALGO, DEVICE_OTHER)
    by_code = _params_by_code(rows)
    assert by_code['audio_in']['name'] == '设备6音频'
    assert 'policy_only' not in by_code


# ---------------------------------------------------------------- 映射三层解析

def _case_bucket(cache, device_id):
    return {
        row['source_param']: row['target_param']
        for row in cache.get_param_mapping(ALGO, 'case', device_id=device_id)
        if row.get('source') == 'case'
    }


def _eval_bucket(cache, device_id):
    return {
        (row['source_param'], row['dimension_id']): row['target_param']
        for row in cache.get_param_mapping(ALGO, 'evaluation', device_id=device_id)
        if row.get('source') == 'device'
    }


def test_mappings_without_device_id_exclude_profile_rows():
    cache = _cache()
    assert _case_bucket(cache, None) == {
        'asr_result': 'audio_in', 'tts_text': 'audio_in'}
    assert _eval_bucket(cache, None) == {('dev_out', DIM_1): 'wer'}


def test_mappings_bound_device_priority_device_gt_profile_gt_level():
    cache = _cache()
    # 设备覆盖 > 策略 > 算法级
    assert _case_bucket(cache, DEVICE_BOUND) == {
        'asr_result': 'audio_in_v2',
        'tts_text': 'audio_in',
        'policy_src': 'audio_in',
    }
    assert _eval_bucket(cache, DEVICE_BOUND) == {
        ('dev_out', DIM_1): 'wer_v2',
        ('dev_out', DIM_2): 'wer_dim2',
    }


def test_mappings_unbound_device_ignores_profile():
    cache = _cache()
    assert _case_bucket(cache, DEVICE_OTHER) == {
        'asr_result': 'audio_in_dev6', 'tts_text': 'audio_in'}
    assert _eval_bucket(cache, DEVICE_OTHER) == {('dev_out', DIM_1): 'wer'}


# ---------------------------------------------------------------- 绑定写仓储

_TABLES = (
    ParamProfile, ParamProfileParam, ParamProfileMapping, DeviceParamBinding,
)


@pytest.fixture(scope='module')
def db():
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'设备绑定仓储测试需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    Base.metadata.create_all(bind=engine, tables=[po.__table__ for po in _TABLES])
    yield engine
    remove_db_session()


def _purge():
    session = get_db_session()
    for po in _TABLES:
        session.query(po).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


@pytest.fixture()
def clean_db(db):
    _purge()
    yield
    _purge()


def _create_profile(repo, name, scope):
    return repo.save({
        'scope': scope,
        'algorithm_type': ALGO,
        'name': name,
        'status': 'online',
        'params': [{'param_code': 'audio_in', 'param_type': 'text', 'direction': 'input'}],
        'mappings': [],
    })


def test_bind_device_accepts_device_scope_profile(clean_db):
    repo = ParamProfileCommandRepository()
    profile = _create_profile(repo, 'device-default', 'device')
    result = repo.bind_device(DEVICE_BOUND, profile['id'])
    assert result == {'device_id': DEVICE_BOUND, 'profile_id': profile['id']}
    assert repo.get_device_binding(DEVICE_BOUND) == profile['id']

    # 解绑
    assert repo.bind_device(DEVICE_BOUND, None) == {
        'device_id': DEVICE_BOUND, 'profile_id': None}
    assert repo.get_device_binding(DEVICE_BOUND) is None


def test_bind_device_rejects_api_scope_profile(clean_db):
    repo = ParamProfileCommandRepository()
    profile = _create_profile(repo, 'api-default', 'api')
    with pytest.raises(ValueError, match='不能绑定到设备'):
        repo.bind_device(DEVICE_BOUND, profile['id'])
    assert repo.get_device_binding(DEVICE_BOUND) is None
