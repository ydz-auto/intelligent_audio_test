# -*- coding: utf-8 -*-
"""VEGA-85：零判定 1.0 假通过修复（F1 首值兜底收紧 + F2 组级零产出收口）。

钉死的不变量（不连库、不碰真实 OSS：内存 sqlite + 内存对象存储）：
1. **F1 首值兜底收紧**：``_fallback_extract`` 末级「取响应首值」仅限单键且值为
   标量（非 bool）的简单响应；多键复杂响应（裁判族 enabled/message/per_round…）
   及 bool / 嵌套 dict 首值一律 None——float(True)=1.0 会把「零产出」伪装成满分
   （VEGA-83 生产实证：任务 470 TRD 453331-453342 全部假 1.0）。
2. **F2 组级零产出收口**：组内全部维度主路径提取与兜底均无值、且逐轮 per_round
   投影亦无产出时，不逐维写 completed，改走既有组失败路径
   update_all_dimensions_in_group_failed：TRD failed、error 含
   「评估响应无可提取指标值: 」+ 响应 message，并推进用例终态
   （update_task_case_status）。
3. **正常路径零回归**：含 n_* 数量字段的真实裁判聚合响应（计数 0 也恒写，
   strategy.py 聚合段）照常逐维 completed；部分维度有值的混合组维持现状；
   原生 per_round 投影流（整体无聚合值但逐轮有值）不误伤。
"""
import os
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
from shared.infrastructure.raw_payload_store import KIND_RESPONSE

from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()

_RESULT = 470  # 生产实证任务号（任务 470 十二维假 1.0，TRD 453331-453342）

# 拒识族 12 维主输出字段（生产 evaluation_dimension_params 实查口径：
# n_<field> 数量字段，VEGA-84 证据链第 6 步）
_JUDGE_FIELDS = (
    'rate_success', 'rate_inquiry', 'rate_failure',
    'success_silent_recover', 'success_reply_recover',
    'inquiry_silent', 'inquiry_reply',
    'failure_silent_respond', 'failure_reply_respond',
    'failure_silent_irrelevant', 'failure_reply_irrelevant',
    'failure_reply_silent',
)


# ==================== 内存对象存储 / 内存库 ====================

class _MemoryObjects:
    """内存对象存储：uploader 存字节，downloader 取字节。"""

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
        from shared.infrastructure.raw_payload_store import RawPayloadStore
        return RawPayloadStore(uploader=self.upload, downloader=self.download)


@pytest.fixture()
def objects():
    return _MemoryObjects()


@pytest.fixture()
def trd_db(monkeypatch, objects):
    """内存 SQLite：test_result_dimensions；三处会话/存储全部注入。"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable
    from evaluation_service.infrastructure.persistence.orm_models import (
        TestResultDimension,
    )

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)

    def _ddl(model):
        ddl = str(CreateTable(model.__table__).compile(engine))
        return ddl.replace('id BIGINT NOT NULL', 'id INTEGER NOT NULL', 1)

    with engine.connect() as conn:
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
    """真实解析链（parse_dimension_result 不覆写，钉的就是它）。

    仅桩化跨服务收尾（gRPC 快照/状态推进）；失败路径对 update_task_case_status
    的调用被记录，作为用例终态推进的断言依据。
    """

    def __init__(self):
        self.logs = []
        self.case_status_calls = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def update_task_case_status(self, result_id, current_result_all_completed,
                                task_id, test_case_id):
        self.case_status_calls.append(
            (result_id, current_result_all_completed, task_id, test_case_id))

    def _build_and_store_algorithm_results(self, *args, **kwargs):
        return None

    def check_all_dimensions_completed(self, result_id, task_id=None):
        return False


def _judge_group(field, count=1, start_id=121):
    """拒识族维度 + 对应 TRD 行 id（生产任务 470：dim 121-132 十二维）"""
    dims = [{'id': start_id + i,
             'name': f'拒识维度{field}',
             'api_settings': {},
             'output_params': [{'output_role': 'main', 'field_path': f'n_{field}'}],
             'rule': {'type': 'direct'}}
            for i in range(count)]
    return dims


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
            status=po.status, evaluation_status=po.evaluation_status,
            error_message=po.error_message,
            api_raw_response_uri=po.api_raw_response_uri,
            api_raw_response_sha256=po.api_raw_response_sha256)
    finally:
        session.close()


def _seed_group(trd_db, dims):
    """按维度列表预置 pending TRD 行，返回 group_items=[(dim_data, trd_id), ...]"""
    group_items = []
    for dim in dims:
        trd_id = _insert_trd(trd_db.factory, dimension_id=dim['id'],
                             round_number=None, evaluation_status='pending')
        group_items.append((dim, trd_id))
    return group_items


def _run_group(host, group_items, resp_data, task_id=470, test_case_id='C-470'):
    host.process_group_dimension_results(
        resp_data=resp_data, group_items=group_items, task_id=task_id,
        test_case_id=test_case_id, result_id=_RESULT,
        api_request_body={'model': 'judge-model', 'query': '干扰问题'},
    )


# 任务 470 零产出形态（VEGA-84 证据链：judge 上游 ASR 失败早退被
# strategy._run_overall_text 包装成聚合 dict，首键 enabled=True、无 n_* 字段）
_ZERO_OUTPUT_RESP = {
    'enabled': True,
    'message': '用户侧 ASR 无词级结果，无法轮次切分',
    'rate': None,
    'per_round': [
        {'round_number': 0, 'message': '跳过: 非拒识轮(is_reject=false)'},
        {'round_number': 1, 'message': '拒识裁判输出解析/校验失败，未生成该轮结果，不计入统计'},
    ],
    'round_alignment': [],
    'audio_info': {},
    'prompt_version': '',
    'n_unjudgeable_rounds': 0,
    'per_round_native': True,
}


# ==================== 1. F1：首值兜底收紧 ====================

class TestFallbackExtractFirstValueGuard:

    def test_multi_key_enabled_first_returns_none(self):
        """多键复杂响应（VEGA-83 零产出形态，首键 enabled=True）不取首值。"""
        resp = {'enabled': True, 'message': '用户侧 ASR 无词级结果', 'rate': None}
        assert ParseDimensionMixin._fallback_extract(resp, '拒识成功率') is None

    def test_multi_key_scalar_first_returns_none(self):
        """多键即使首值是标量也不取（守卫先看键数）。"""
        assert ParseDimensionMixin._fallback_extract({'wer': 0.05, 'ser': 0.1}, '别的维度') is None

    def test_single_key_scalar_still_extracted(self):
        """单键标量（更老 WER/SER 简单形态）仍取首值。"""
        assert ParseDimensionMixin._fallback_extract({'value': 0.05}, 'x') == 0.05
        assert ParseDimensionMixin._fallback_extract({'value': '3.2'}, 'x') == '3.2'
        assert ParseDimensionMixin._fallback_extract({'value': 2}, 'x') == 2

    def test_single_key_bool_not_extracted(self):
        """单键 bool 不取——float(True)=1.0 假满分正是 VEGA-83 缺陷形态。"""
        assert ParseDimensionMixin._fallback_extract({'enabled': True}, 'x') is None
        assert ParseDimensionMixin._fallback_extract({'enabled': False}, 'x') is None

    def test_single_key_dict_not_extracted(self):
        """单键嵌套 dict 不取（非标量）。"""
        assert ParseDimensionMixin._fallback_extract({'data': {'a': 1}}, 'x') is None

    def test_empty_and_non_dict_return_none(self):
        assert ParseDimensionMixin._fallback_extract({}, 'x') is None
        assert ParseDimensionMixin._fallback_extract(None, 'x') is None
        assert ParseDimensionMixin._fallback_extract([1, 2], 'x') is None

    def test_dim_name_and_results_matching_unchanged(self):
        """前两级兜底（维度名 / results 匹配）不受本次收紧影响。"""
        assert ParseDimensionMixin._fallback_extract({'wer': 0.12}, 'wer') == 0.12
        assert ParseDimensionMixin._fallback_extract(
            {'results': {'wer': {'value': 3}}}, 'wer') == 3


# ==================== 2. F2：组级零产出收口 ====================

class TestZeroOutputGroupFails:

    def test_task470_zero_output_fails_group_not_false_pass(self, trd_db):
        """生产形态重放：12 维全组收口 failed，绝不出现假满分 1.0。"""
        dims = _judge_group('rate_success', count=12)
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        _run_group(host, group_items, dict(_ZERO_OUTPUT_RESP))

        for _dim, trd_id in group_items:
            row = _row(trd_db.factory, trd_id)
            assert row.evaluation_status == 'failed'
            assert row.status == 'failed'
            assert row.dimension_value is None, '零产出不得落假值 1.0'
            assert row.score == 0
            assert row.error_message == (
                '评估响应无可提取指标值: 用户侧 ASR 无词级结果，无法轮次切分')
        # 失败路径保存了原始响应（可事后取证 ASR 失败原文）
        first_row = _row(trd_db.factory, group_items[0][1])
        assert first_row.api_raw_response_uri is not None
        assert trd_db.store.load(
            KIND_RESPONSE, first_row.api_raw_response_uri,
            first_row.api_raw_response_sha256)['message'] == (
                '用户侧 ASR 无词级结果，无法轮次切分')
        # 用例终态推进（组失败路径内 update_task_case_status 被调用）
        assert host.case_status_calls
        assert all(c[1] is False for c in host.case_status_calls)

    def test_wrapped_zero_output_unwraps_message(self, trd_db):
        """异步轮询到达形态（code/data/result 包装）：message 剥包后取到。"""
        dims = _judge_group('rate_success', count=2)
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        resp = {'code': 200, 'msg': 'ok',
                'data': {'result': dict(_ZERO_OUTPUT_RESP)}}
        _run_group(host, group_items, resp)

        for _dim, trd_id in group_items:
            row = _row(trd_db.factory, trd_id)
            assert row.evaluation_status == 'failed'
            assert row.error_message == (
                '评估响应无可提取指标值: 用户侧 ASR 无词级结果，无法轮次切分')

    def test_config_skip_whole_case_fails_group(self, trd_db):
        """配置性整例跳过（全轮 is_reject=false）统一按显式 failed 收口（裁决口径）。"""
        dims = _judge_group('rate_success', count=2)
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        resp = {
            'enabled': True,
            'message': '跳过: 非拒识轮(is_reject=false)',
            'rate': None,
            'per_round': [{'round_number': 0, 'message': '跳过: 非拒识轮(is_reject=false)'}],
            'per_round_native': True,
        }
        _run_group(host, group_items, resp)

        for _dim, trd_id in group_items:
            row = _row(trd_db.factory, trd_id)
            assert row.evaluation_status == 'failed'
            assert '评估响应无可提取指标值: 跳过: 非拒识轮(is_reject=false)' \
                in row.error_message

    def test_zero_output_without_message_uses_bare_prefix(self, trd_db):
        """无 message 字段的零产出：error 只剩前缀（不带悬空冒号）。"""
        dims = _judge_group('rate_success', count=1)
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        _run_group(host, group_items, {'enabled': True, 'rate': None})

        row = _row(trd_db.factory, group_items[0][1])
        assert row.evaluation_status == 'failed'
        assert row.error_message == '评估响应无可提取指标值'


# ==================== 3. 正常路径零回归 ====================

class TestNormalPathsUnchanged:

    def test_normal_judge_aggregate_response_completed(self, trd_db):
        """正常聚合响应（n_* 计数恒写，含 0）→ 照常逐维 completed，值/分一致。"""
        resp = {
            'enabled': True,
            'message': 'OK',
            'rate': '拒识成功',
            'n_reject_rounds': 3,
            'n_rate_success': 2,
            'n_rate_failure': 1,
            'n_success_silent_recover': 0,  # 计数 0 也恒写（strategy 聚合段）
            'rate_success': 0.667,
            'rate_failure': 0.333,
            'per_round_native': True,
            'per_round': [],
        }
        dims = [
            _judge_group('rate_success', count=1)[0],
            _judge_group('rate_failure', count=1, start_id=131)[0],
        ]
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        _run_group(host, group_items, resp)

        by_field = {dim['output_params'][0]['field_path']: trd_id
                    for dim, trd_id in group_items}
        row_succ = _row(trd_db.factory, by_field['n_rate_success'])
        row_fail = _row(trd_db.factory, by_field['n_rate_failure'])
        assert row_succ.evaluation_status == 'completed'
        assert row_succ.status == 'completed'
        assert row_succ.dimension_value == 2.0
        assert row_succ.score == 2.0
        assert row_fail.evaluation_status == 'completed'
        assert row_fail.dimension_value == 1.0
        assert row_fail.error_message is None
        # 正常路径不触发组失败收口
        assert host.case_status_calls == []

    def test_partial_value_group_keeps_current_behavior(self, trd_db):
        """部分维度有值 → 维持现状：全部逐维 completed（无值维度 value=None/score=0）。"""
        resp = {'enabled': True, 'n_rate_success': 2, 'rate': '拒识成功'}
        dims = [
            _judge_group('rate_success', count=1)[0],
            _judge_group('rate_inquiry', count=1, start_id=131)[0],  # 响应中无 n_rate_inquiry
        ]
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        _run_group(host, group_items, resp)

        by_field = {dim['output_params'][0]['field_path']: trd_id
                    for dim, trd_id in group_items}
        row_hit = _row(trd_db.factory, by_field['n_rate_success'])
        row_miss = _row(trd_db.factory, by_field['n_rate_inquiry'])
        assert row_hit.evaluation_status == 'completed'
        assert row_hit.dimension_value == 2.0
        assert row_miss.evaluation_status == 'completed'
        assert row_miss.dimension_value is None
        assert row_miss.score == 0
        assert host.case_status_calls == []

    def test_native_per_round_only_not_misclassified(self, trd_db):
        """原生投影流：整体无聚合值但逐轮有值 → 不走组失败（int176 同款形态）。"""
        dims = [{
            'id': 11, 'name': '打断成功数量', 'api_settings': {},
            'output_params': [{'output_role': 'main',
                               'field_path': 'interruption.success_count'}],
            'rule': {'type': 'direct'},
        }]
        group_items = _seed_group(trd_db, dims)
        host = _Host()
        resp = {
            'per_round': [
                {'round_number': 1, 'interruption': {'success_count': 1.0}},
                {'round_number': 2, 'interruption': {'success_count': 0.0}},
            ],
            'per_round_native': True,
        }
        _run_group(host, group_items, resp)

        # 整体行维持既有行为（completed、无值），逐轮行正常落库
        overall = _row(trd_db.factory, group_items[0][1])
        assert overall.evaluation_status == 'completed'
        assert overall.dimension_value is None
        assert host.case_status_calls == []
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )
        session = trd_db.factory()
        try:
            round_rows = session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == _RESULT,
                TestResultDimension.round_number.isnot(None)).all()
            assert sorted(r.round_number for r in round_rows) == [1, 2]
            assert all(r.evaluation_status == 'completed' for r in round_rows)
            assert {r.round_number: r.dimension_value for r in round_rows} == {1: 1.0, 2: 0.0}
        finally:
            session.close()
