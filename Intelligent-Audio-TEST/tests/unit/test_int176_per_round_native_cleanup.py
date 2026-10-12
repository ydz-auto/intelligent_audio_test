# -*- coding: utf-8 -*-
"""INT-176 回归守卫：打断族 per_round 幽灵行自愈（native 门控清理）+ 端点并发取最大

对齐 V9.7.10 6fb171e4（主服务侧 evaluation_result_processor 部分）+ 5d309ac4
主服务侧（evaluation_api_client 端点 max_process 取各维度最大）：

1. native 标记判定：_per_round_is_native 兼容同步 HTTP 包装（code/data→result）
   与裸 calc result 两种到达形态；标记缺失/非严格布尔 True → False
   （切片 fallback / 旧版子服务绝不误触发清理）；
2. 族标识配置化：打断族按 task_type_code 枚举集合判定（不硬编码维度 id、
   无魔法字符串）；interruption_judge（环境音裁判族）同前缀不同族不误捕；
3. native 清理矩阵（真实 SQLite TRD 表）：重评落库后 round-0 幽灵行/超出
   产出轮的孤儿切片行删除；某维度本次 0 产出 → 其逐轮行全为孤儿全删；
   overall 整体行（round_number IS NULL）豁免；接管族等非打断族维度与
   跨 result 行不触碰；本次产出 (dim, round) 对保留；重复落库幂等；
4. 不清理门控：upserted=0（judge 降级全跳过项）/ 切片路径（is_native=False）/
   空 per_round / 非打断族组 → 不删任何行；
5. 组处理接线：process_group_dimension_results 按 per_round_native 判定并
   传参 is_native（有标记→清理、无标记→只覆盖）；
6. 端点 max_process 取最大：同端点多维度引用取各维度最大消费能力
   （音频 5 vs 非音频 30 → 30），不缩水已加载配置，缺省字段用默认值。

数据卫生：全部写入进程内 sqlite://（StaticPool 内存库），不触共享库。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.infrastructure.persistence import _result_group_mixin as grm_module
from evaluation_service.infrastructure.persistence._result_dimension_mixin import DimensionResultMixin
from evaluation_service.infrastructure.persistence._result_group_mixin import GroupResultMixin
from evaluation_service.infrastructure.persistence._result_parse_mixin import ParseDimensionMixin
from evaluation_service.domain.value_objects.dimension_families import (
    INTERRUPTION_FAMILY_TASK_TYPES,
    InterruptionFamilyTaskType,
    interruption_family_dim_ids,
    is_interruption_family_task_type,
)

# 导入 evaluation_service 相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


# ==================== 公共构造 ====================

_RESULT_A = 101
_RESULT_B = 202

_DIM = {
    'success': (11, '打断成功数量', 'interruption_metrics', 'interruption.success_count'),
    'latency': (12, '打断响应时延', 'interruption_stop_latency', 'interruption.response_latency_avg_ms'),
    'stopc': (13, '停止遵从率', 'interruption_adaptability', 'interruption.stop_compliance_rate'),
    'turn': (14, '接管指标', 'turn_taking', 'turn.some_metric'),
}

_GHOST_DIM = {'success_r0': 11, 'latency_r0': 12, 'success_r5': 11,
              'latency_r2': 12, 'stopc_r1': 13, 'turn_r1': 14}


def _dim_data(key):
    dim_id, name, task_type_code, field_path = _DIM[key]
    return {
        'id': dim_id,
        'name': name,
        'task_type_code': task_type_code,
        'rule': {'type': 'direct'},
        'api_settings': {},
        'output_params': [{'param_code': 'main', 'field_path': field_path,
                           'output_role': 'main', 'visible_in_report': True}],
    }


def _per_round_items():
    """模拟原生投影产出：轮1成功、轮2失败（仅成功数量落 0）、轮0 跳过项（无值）。"""
    return [
        {'round_number': 1, 'interruption': {'success_count': 1.0,
                                             'response_latency_avg_ms': 300.0}},
        {'round_number': 2, 'interruption': {'success_count': 0.0}},
        {'round_number': 0, 'message': '跳过: 非计时轮(无打断时序)'},
    ]


class _ProcHost(GroupResultMixin, DimensionResultMixin, ParseDimensionMixin):
    def __init__(self):
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


@pytest.fixture()
def trd_db():
    """真实内存 SQLite 引擎 + 仅建 test_result_dimensions 表。

    SQLite 仅对 INTEGER PRIMARY KEY 做行ID别名自增（生产库 BIGINT 无此约束），
    故按表定义编译 DDL 后仅将 id 列替换为 INTEGER，其余列保持原样（INT-169 同款）。
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    from shared.models.database import Base

    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    ddl = str(CreateTable(TestResultDimension.__table__).compile(engine))
    ddl = ddl.replace('id BIGINT NOT NULL', 'id INTEGER NOT NULL', 1)
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()
    return sessionmaker(bind=engine)


def _insert_trd(factory, **kwargs):
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    s = factory()
    try:
        po = TestResultDimension(**kwargs)
        s.add(po)
        s.commit()
        return po.id
    finally:
        s.close()


def _round_trd_ids(factory, result_id, dim_id):
    """逐轮行（round_number IS NOT NULL）→ [(round, id, value)]，overall 整体行排除"""
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    s = factory()
    try:
        rows = s.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result_id,
            TestResultDimension.dimension_id == dim_id,
            TestResultDimension.round_number.isnot(None),
        ).all()
        return sorted((r.round_number, r.id, r.dimension_value) for r in rows)
    finally:
        s.close()


def _trd_exists(factory, trd_id):
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    s = factory()
    try:
        return s.get(TestResultDimension, trd_id) is not None
    finally:
        s.close()


@pytest.fixture()
def clean_env(trd_db):
    """打断族(success/latency/stopc) + 接管族(turn) 两 result 的清理测试环境。

    预置：round-0 幽灵行、超产出轮孤儿切片行、stopc 泄漏行（native 从不投影）、
    接管族逐轮行、各维度 overall 整体行、另一 result 的同维度逐轮行。
    """
    factory = trd_db
    overall_ids = {}
    for key in _DIM:
        dim_id = _DIM[key][0]
        overall_ids[key] = _insert_trd(
            factory, test_result_id=_RESULT_A, dimension_id=dim_id,
            algorithm_type='voice_llm', round_number=None,
            dimension_value=1.0, evaluation_status='completed')

    ghosts = {
        # round-0 幽灵行（切片把 round0 也独立重评的幻影）
        'success_r0': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=11,
                                  round_number=0, dimension_value=1.0, evaluation_status='completed'),
        'latency_r0': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=12,
                                  round_number=0, dimension_value=99.0, evaluation_status='completed'),
        # 超出本次产出轮的孤儿切片行
        'success_r5': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=11,
                                  round_number=5, dimension_value=9.9, evaluation_status='completed'),
        'latency_r2': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=12,
                                  round_number=2, dimension_value=888.0, evaluation_status='completed'),
        # stopc 泄漏行：native 从不投影 stop_compliance → 产出 0 → 全删
        'stopc_r1': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=13,
                                round_number=1, dimension_value=1.0, evaluation_status='completed'),
        # 接管族逐轮行：非打断族 → 保留
        'turn_r1': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=14,
                               round_number=1, dimension_value=5.0, evaluation_status='completed'),
        # success round1 pending 行（应被覆盖而非新建）
        'success_r1_pending': _insert_trd(factory, test_result_id=_RESULT_A, dimension_id=11,
                                          round_number=1, dimension_value=None,
                                          evaluation_status='pending'),
    }
    # result_b 同维度逐轮行——跨 result 隔离，清理必须不触碰
    other_result_row = _insert_trd(factory, test_result_id=_RESULT_B, dimension_id=11,
                                   round_number=1, dimension_value=7.0,
                                   evaluation_status='completed')

    group_items = [(_dim_data('success'), overall_ids['success']),
                   (_dim_data('latency'), overall_ids['latency']),
                   (_dim_data('stopc'), overall_ids['stopc']),
                   (_dim_data('turn'), overall_ids['turn'])]
    return {
        'factory': factory, 'host': _ProcHost(),
        'overall_ids': overall_ids, 'ghosts': ghosts,
        'other_result_row': other_result_row, 'group_items': group_items,
    }


def _run_overwrite(env, per_round, is_native, result_id=_RESULT_A, group_items=None):
    factory = env['factory']
    session = factory()
    try:
        n = env['host']._overwrite_round_results(
            result_id, per_round, group_items or env['group_items'], session,
            is_native=is_native)
        session.commit()
    finally:
        session.close()
    return n


def _assert_ghosts_intact(env, keys):
    for key in keys:
        assert _trd_exists(env['factory'], env['ghosts'][key]), f'{key} 被误删'


# ==================== 1. native 标记判定 ====================

class TestPerRoundIsNativeShapes:

    def test_sync_http_wrapper_true(self):
        """同步 HTTP 包装：code/data → result → per_round_native"""
        assert _ProcHost()._per_round_is_native(
            {'code': 0, 'data': {'result': {'per_round': [{'round_number': 1}],
                                            'per_round_native': True}}}) is True

    def test_bare_calc_result_true(self):
        """异步轮询取数后/事件回调：裸 calc result"""
        assert _ProcHost()._per_round_is_native(
            {'per_round': [{'round_number': 1}], 'per_round_native': True}) is True

    def test_missing_marker_false(self):
        """切片 fallback / 旧版子服务无标记 → False"""
        assert _ProcHost()._per_round_is_native(
            {'per_round': [{'round_number': 1}]}) is False

    def test_wrapped_missing_marker_false(self):
        assert _ProcHost()._per_round_is_native(
            {'code': 0, 'data': {'result': {}}}) is False

    def test_non_bool_true_values_false(self):
        """非严格布尔 True 一律视为无标记（字符串/数字不打标）"""
        assert _ProcHost()._per_round_is_native({'per_round_native': 'true'}) is False
        assert _ProcHost()._per_round_is_native({'per_round_native': 1}) is False

    def test_none_and_non_dict_false(self):
        assert _ProcHost()._per_round_is_native(None) is False
        assert _ProcHost()._per_round_is_native('text') is False

    def test_unwrap_calc_result_shapes(self):
        assert GroupResultMixin._unwrap_calc_result(
            {'code': 0, 'data': {'result': {'per_round': 1}}}) == {'per_round': 1}
        assert GroupResultMixin._unwrap_calc_result({'a': 1}) == {'a': 1}
        assert GroupResultMixin._unwrap_calc_result(None) == {}
        assert GroupResultMixin._unwrap_calc_result({'code': 0, 'data': None}) == {}


# ==================== 2. 族标识配置化 ====================

class TestInterruptionFamilyIdentification:

    def test_family_task_types_exact_set(self):
        assert InterruptionFamilyTaskType.METRICS.value == 'interruption_metrics'
        assert len(INTERRUPTION_FAMILY_TASK_TYPES) == 6

    def test_family_codes_match(self):
        for code in INTERRUPTION_FAMILY_TASK_TYPES:
            assert is_interruption_family_task_type(code) is True

    def test_judge_family_same_prefix_not_captured(self):
        """环境音裁判族 interruption_judge 同前缀不同族——前缀匹配会误捕，必须排除"""
        assert is_interruption_family_task_type('interruption_judge') is False
        assert is_interruption_family_task_type('rejection_judge') is False

    def test_other_families_not_captured(self):
        assert is_interruption_family_task_type('turn_taking') is False
        assert is_interruption_family_task_type('tor') is False
        assert is_interruption_family_task_type('turn_eval') is False
        assert is_interruption_family_task_type('reject_judge') is False
        assert is_interruption_family_task_type(None) is False
        assert is_interruption_family_task_type('') is False

    def test_group_items_family_dim_ids(self):
        items = [(_dim_data('success'), 901), (_dim_data('latency'), 902),
                 (_dim_data('turn'), 903)]
        assert interruption_family_dim_ids(items) == [11, 12]

    def test_group_items_without_family_returns_empty(self):
        assert interruption_family_dim_ids([(_dim_data('turn'), 903)]) == []
        assert interruption_family_dim_ids([]) == []
        assert interruption_family_dim_ids(None) == []

    def test_malformed_dim_id_skipped(self):
        items = [({'name': 'x', 'task_type_code': 'interruption_metrics'}, 901),
                 ({'id': None, 'name': 'y', 'task_type_code': 'interruption_metrics'}, 902)]
        assert interruption_family_dim_ids(items) == []


# ==================== 3. native 清理矩阵（真实 DB） ====================

class TestNativeCleanupMatrix:

    def test_native_cleanup_removes_ghosts_orphans_and_leak(self, clean_env):
        """场景 a+b：round-0 幽灵行/孤儿切片行/0 产出泄漏行被删；overall、
        非打断族、跨 result、本次产出轮均不受影响。"""
        env = clean_env
        n = _run_overwrite(env, _per_round_items(), is_native=True)
        # 写入计数 = success(轮1,轮2) + latency(轮1) = 3
        assert n == 3

        # 场景 a：幽灵行/孤儿行/泄漏行删除，仅产出轮保留
        rounds_success = _round_trd_ids(env['factory'], _RESULT_A, 11)
        assert sorted(r[0] for r in rounds_success) == [1, 2]
        rounds_latency = _round_trd_ids(env['factory'], _RESULT_A, 12)
        assert sorted(r[0] for r in rounds_latency) == [1]
        assert _round_trd_ids(env['factory'], _RESULT_A, 13) == []  # stopc 0 产出 → 全删

        # 产出轮值正确：r1 pending 行被原地覆盖（同 id）
        by_round = {r[0]: r for r in rounds_success}
        assert by_round[1][1] == env['ghosts']['success_r1_pending']
        assert by_round[1][2] == 1.0
        assert by_round[2][2] == 0.0
        assert rounds_latency[0][2] == 300.0

        # 场景 b：overall 整体行豁免（round_number=None 行仍在且未变）
        assert all(_trd_exists(env['factory'], trd_id)
                   for trd_id in env['overall_ids'].values())

        # 场景 b：接管族（非打断族）逐轮行不受影响
        assert _round_trd_ids(env['factory'], _RESULT_A, 14) == [
            (1, env['ghosts']['turn_r1'], 5.0)]

        # 场景 b：另一 result 的同维度逐轮行不受影响（跨 result 隔离）
        assert _round_trd_ids(env['factory'], _RESULT_B, 11) == [
            (1, env['other_result_row'], 7.0)]

    def test_native_cleanup_idempotent_no_extra_log(self, clean_env):
        """重复原生落库：不新增行、计数一致；无孤儿可删时清理静默（不重复记日志）。"""
        env = clean_env
        n1 = _run_overwrite(env, _per_round_items(), is_native=True)
        logs_after_first = sum(1 for l in env['host'].logs if '原生清旧' in str(l.get('content', '')))
        assert n1 == 3
        assert logs_after_first == 1

        n2 = _run_overwrite(env, _per_round_items(), is_native=True)
        assert n2 == n1
        assert sorted(r[0] for r in _round_trd_ids(env['factory'], _RESULT_A, 11)) == [1, 2]
        logs_after_second = sum(1 for l in env['host'].logs if '原生清旧' in str(l.get('content', '')))
        assert logs_after_second == 1  # 无删除 → 不记清理日志

    def test_no_cleanup_when_nothing_produced(self, clean_env):
        """场景 c：judge 失败/降级 → per_round 全为跳过项（upserted=0）→ 不清理。"""
        env = clean_env
        skip_only = [{'round_number': 0, 'message': '跳过: 非计时轮(无打断时序)'},
                     {'round_number': 1, 'message': '跳过: 无时序数据'}]
        n = _run_overwrite(env, skip_only, is_native=True)
        assert n == 0

        _assert_ghosts_intact(env, ('success_r0', 'latency_r0', 'success_r5',
                                    'latency_r2', 'stopc_r1', 'turn_r1'))
        assert _trd_exists(env['factory'], env['other_result_row'])

    def test_slice_path_no_cleanup(self, clean_env):
        """场景 c：切片 fallback（is_native=False）即便有产出也不清理。"""
        env = clean_env
        n = _run_overwrite(env, _per_round_items(), is_native=False)
        assert n == 3  # 覆盖照常发生

        _assert_ghosts_intact(env, ('success_r0', 'latency_r0', 'success_r5',
                                    'latency_r2', 'stopc_r1', 'turn_r1'))
        assert _trd_exists(env['factory'], env['other_result_row'])

    def test_empty_per_round_no_cleanup(self, clean_env):
        """per_round 为空 → 提前返回 0，不触发任何清理。"""
        env = clean_env
        n = _run_overwrite(env, [], is_native=True)
        assert n == 0
        _assert_ghosts_intact(env, ('success_r0', 'stopc_r1', 'turn_r1'))

    def test_non_family_group_native_no_cleanup(self, clean_env):
        """非打断族组（裁判族 interruption_judge）即便带 native 标记也不删既有行。"""
        env = clean_env
        judge_dim = {
            'id': 21, 'name': '打断场景裁判', 'task_type_code': 'interruption_judge',
            'rule': {'type': 'direct'}, 'api_settings': {},
            'output_params': [{'param_code': 'main', 'field_path': 'interruption_judge.rate',
                               'output_role': 'main', 'visible_in_report': True}],
        }
        per_round = [{'round_number': 1, 'interruption_judge': {'rate': 0.8}}]
        n = _run_overwrite(env, per_round, is_native=True,
                           group_items=[(judge_dim, env['overall_ids']['turn'])])
        assert n == 1  # judge 维度自身 upsert 正常
        # 打断族既有行未被触碰（judge 族不在清理范围）
        _assert_ghosts_intact(env, ('success_r0', 'latency_r0', 'success_r5',
                                    'latency_r2', 'stopc_r1', 'turn_r1'))
        assert _trd_exists(env['factory'], env['other_result_row'])


# ==================== 4. 组处理接线（is_native 判定并传参） ====================

class TestProcessGroupWiring:

    @staticmethod
    def _bare_resp(native):
        resp = {'per_round': _per_round_items()}
        if native:
            resp['per_round_native'] = True
        return resp

    def _run_process(self, monkeypatch, clean_env, resp):
        env = clean_env
        host = env['host']
        monkeypatch.setattr(grm_module, 'get_db_session', env['factory'])
        acl = MagicMock()
        acl.get_test_result_by_id.return_value = None
        monkeypatch.setattr(grm_module, 'task_acl_repository', acl)
        host._build_and_store_algorithm_results = MagicMock()
        host.check_all_dimensions_completed = MagicMock(return_value=False)

        host.process_group_dimension_results(
            resp_data=resp, group_items=env['group_items'],
            task_id=1, test_case_id='c1', result_id=_RESULT_A,
            api_request_body={'req': 1})
        return env

    def test_native_resp_triggers_cleanup(self, monkeypatch, clean_env):
        env = self._run_process(monkeypatch, clean_env, self._bare_resp(native=True))
        # 幽灵行/孤儿行/泄漏行被清理
        assert sorted(r[0] for r in _round_trd_ids(env['factory'], _RESULT_A, 11)) == [1, 2]
        assert sorted(r[0] for r in _round_trd_ids(env['factory'], _RESULT_A, 12)) == [1]
        assert _round_trd_ids(env['factory'], _RESULT_A, 13) == []
        # overall 与非打断族不受影响
        assert _trd_exists(env['factory'], env['overall_ids']['success'])
        assert _round_trd_ids(env['factory'], _RESULT_A, 14) == [
            (1, env['ghosts']['turn_r1'], 5.0)]

    def test_non_native_resp_only_overwrites(self, monkeypatch, clean_env):
        env = self._run_process(monkeypatch, clean_env, self._bare_resp(native=False))
        # 覆盖发生（产出轮保留），但幽灵行/孤儿行/泄漏行全部保留
        rounds_success = _round_trd_ids(env['factory'], _RESULT_A, 11)
        assert {r[0] for r in rounds_success} == {0, 1, 2, 5}
        assert _trd_exists(env['factory'], env['ghosts']['latency_r2'])
        assert _trd_exists(env['factory'], env['ghosts']['stopc_r1'])


# ==================== 5. 端点 max_process 取最大 ====================

def _dim_with_endpoints(endpoints):
    return SimpleNamespace(snapshot=SimpleNamespace(api_endpoints=endpoints))


class TestEndpointMaxProcess:

    @staticmethod
    def _client():
        from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import evaluationApiClient
        client = evaluationApiClient()
        client.logs = []
        client._log = lambda **kwargs: client.logs.append(kwargs)
        return client

    def test_same_endpoint_takes_max(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 5}]),
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 30}]),
        ])
        assert client.endpoint_configs['http://ep-a'] == 30

    def test_same_endpoint_max_first_no_shrink(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 30}]),
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 5}]),
        ])
        assert client.endpoint_configs['http://ep-a'] == 30

    def test_three_dims_takes_global_max(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 5}]),
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 10}]),
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 30}]),
        ])
        assert client.endpoint_configs['http://ep-a'] == 30

    def test_camel_case_field_beats_default(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'endpoint': 'http://ep-b', 'maxProcess': 30}]),
            _dim_with_endpoints([{'url': 'http://ep-b'}]),  # 缺省 → default_max_concurrent
        ])
        assert client.endpoint_configs['http://ep-b'] == 30

    def test_missing_field_alone_uses_default(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-c'}]),
        ])
        assert client.endpoint_configs['http://ep-c'] == client.default_max_concurrent

    def test_different_endpoints_independent(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 5}]),
            _dim_with_endpoints([{'url': 'http://ep-b', 'max_process': 30}]),
        ])
        assert client.endpoint_configs['http://ep-a'] == 5
        assert client.endpoint_configs['http://ep-b'] == 30

    def test_take_max_log_emitted(self):
        client = self._client()
        client.load_endpoint_configs([
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 5}]),
            _dim_with_endpoints([{'url': 'http://ep-a', 'max_process': 30}]),
        ])
        assert any('取最大并发' in str(l.get('content', '')) for l in client.logs)
