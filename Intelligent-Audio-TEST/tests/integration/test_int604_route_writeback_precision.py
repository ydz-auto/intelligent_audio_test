# -*- coding: utf-8 -*-
"""INT-604/INT-1115 集成验收（真实 Postgres + 进程内 gRPC mesh）。

覆盖验收标准 2/3 的集成面 + 评审「必改」写侧回写精确性：
1. 写侧状态回写按路由行精确命中（tc_rel_id）：单用例双路由并发时，回写只动
   目标行，兄弟路由不被 (task_id, test_case_id) 全量更新打成同一终态；
2. 评估仅回写（execution_status 不回写）不动兄弟路由执行状态；
3. GetTestResultsByTaskAndCase 路由过滤（device_type/device_id）；
4. target_modes 目标级门控真实 DB 选行：Task.config['target_modes'] 读取 +
   真实 SQLAlchemy 查询（双道纯逻辑分支已由 tests/unit/test_int604_serial_gating.py
   覆盖，本文件验证真实 DB/gRPC 链路）。
"""
import uuid
from datetime import datetime

import pytest

from tests.integration.test_task_execute_real_chain import (
    _query,
    grpc_mesh,       # noqa: F401  pytest fixture
    oss_fast_fail,   # noqa: F401  pytest fixture
    pg_db,           # noqa: F401  pytest fixture
    storage_env,     # noqa: F401  pytest fixture（pg_db 依赖）
)

from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus,
)


def _seed_mixed_task(config=None):
    """播种 Task + 同一用例双路由 TaskCase 行（physical + http_api）。

    Returns:
        (task_id, case_id, row1, row2) — row1=physical, row2=http_api，均 RUNNING。
    """
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TaskCase

    case_id = f'INT604-{uuid.uuid4().hex[:12]}'
    s = get_db_session()
    task = Task(name=f'int604-mixed-{uuid.uuid4().hex[:8]}', status='running',
                total_cases=2, algorithm_type='translation', config=config)
    s.add(task)
    s.flush()
    now = datetime.now()
    row1 = TaskCase(task_id=task.id, test_case_id=case_id, status='running',
                    execution_status=ExecutionStatus.RUNNING,
                    evaluation_status=EvaluationStatus.RUNNING,
                    device_type='physical', device_id='101', created_at=now)
    row2 = TaskCase(task_id=task.id, test_case_id=case_id, status='running',
                    execution_status=ExecutionStatus.RUNNING,
                    evaluation_status=EvaluationStatus.RUNNING,
                    device_type='http_api', device_id='202', created_at=now)
    s.add_all([row1, row2])
    s.commit()
    s.refresh(row1)
    s.refresh(row2)
    task_id = task.id
    rid1, rid2 = row1.id, row2.id
    s.close()
    return task_id, case_id, rid1, rid2


def _rows(task_id):
    from task_service.infrastructure.persistence.models import TaskCase
    return _query(TaskCase, task_id=task_id)


class TestRouteWriteBackPrecision:
    """评审「必改」：多路由下写回按路由行精确命中，兄弟路由不被覆盖。"""

    def test_tc_rel_id_hits_only_target_row(self, pg_db, grpc_mesh, oss_fast_fail):
        from shared.clients._grpc_task_data import update_task_case_status

        task_id, case_id, rid1, rid2 = _seed_mixed_task()
        # 设备侧行完成回写（tc_rel_id=rid1）
        ok = update_task_case_status(
            task_id, case_id, execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED, tc_rel_id=rid1)
        assert ok is True
        rows = {r.id: r for r in _rows(task_id)}
        assert rows[rid1].execution_status == ExecutionStatus.COMPLETED, \
            '设备侧行应被精确回写为 completed'
        assert rows[rid2].execution_status == ExecutionStatus.RUNNING, \
            'API 侧兄弟行不得被 (task, case) 全量更新覆盖——INT-604 核心修复'
        assert rows[rid2].evaluation_status == EvaluationStatus.RUNNING

    def test_sibling_completes_independently(self, pg_db, grpc_mesh, oss_fast_fail):
        from shared.clients._grpc_task_data import update_task_case_status

        task_id, case_id, rid1, rid2 = _seed_mixed_task()
        update_task_case_status(
            task_id, case_id, execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED, tc_rel_id=rid1)
        # API 侧行独立完成（即使设备侧先完成，tc_rel_id=rid2 只动 API 行）
        ok = update_task_case_status(
            task_id, case_id, execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED, tc_rel_id=rid2)
        assert ok is True
        rows = {r.id: r for r in _rows(task_id)}
        assert rows[rid1].execution_status == ExecutionStatus.COMPLETED
        assert rows[rid2].execution_status == ExecutionStatus.COMPLETED

    def test_eval_only_writeback_does_not_stomp_sibling_exec(
            self, pg_db, grpc_mesh, oss_fast_fail):
        """评估仅回写（execution_status 空）：目标行 eval 终态，兄弟行 exec 保留。"""
        from shared.clients._grpc_task_data import update_task_case_status

        task_id, case_id, rid1, rid2 = _seed_mixed_task()
        # 模拟评估服务仅回写评估终态（execution_status 空串 → 服务端按行自身推导）
        ok = update_task_case_status(
            task_id, case_id, status='',
            evaluation_status=EvaluationStatus.COMPLETED, tc_rel_id=rid1)
        assert ok is True
        rows = {r.id: r for r in _rows(task_id)}
        assert rows[rid1].evaluation_status == EvaluationStatus.COMPLETED
        # 目标行 exec 仍 RUNNING（未被评估回写覆盖为终态）
        assert rows[rid1].execution_status == ExecutionStatus.RUNNING
        assert rows[rid2].execution_status == ExecutionStatus.RUNNING
        assert rows[rid2].evaluation_status == EvaluationStatus.RUNNING

    def test_legacy_without_tc_rel_id_updates_single_row(
            self, pg_db, grpc_mesh, oss_fast_fail):
        """无 tc_rel_id 旧调用（单行任务）：维持 (task, case) 口径，零回归。"""
        from shared.clients._grpc_task_data import update_task_case_status

        task_id, case_id, _rid1, _rid2 = _seed_mixed_task()
        # 只保留单行任务：手动删掉 API 行，剩单物理行
        from task_service.infrastructure.persistence.models import TaskCase
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            s.query(TaskCase).filter(TaskCase.task_id == task_id,
                                     TaskCase.device_type == 'http_api').delete()
            s.commit()
        finally:
            s.close()
        ok = update_task_case_status(
            task_id, case_id, execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED)
        assert ok is True
        rows = _rows(task_id)
        assert len(rows) == 1
        assert rows[0].execution_status == ExecutionStatus.COMPLETED


class TestGetResultsRouteFilter:
    """GetTestResultsByTaskAndCase 路由过滤（device_type/device_id 可选）。"""

    def test_route_filter_device_and_api(self, pg_db, grpc_mesh, oss_fast_fail):
        from task_service.infrastructure.persistence.models import TestResult
        from shared.proto import task_service_pb2 as task_pb
        from shared.clients._grpc_stubs import get_task_data_service_stub
        from shared.utils.grpc_json import loads as _loads

        task_id, case_id, _r1, _r2 = _seed_mixed_task()
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            s.add_all([
                TestResult(task_id=task_id, test_case_id=case_id, device_id=101,
                           api_id=None, algorithm_type='translation'),
                TestResult(task_id=task_id, test_case_id=case_id, device_id=None,
                           api_id=202, algorithm_type='translation'),
                TestResult(task_id=task_id, test_case_id=case_id, device_id=None,
                           api_id=303, algorithm_type='translation'),
            ])
            s.commit()
        finally:
            s.close()

        stub = get_task_data_service_stub()

        def _fetch(device_type=None, device_id=None):
            req = task_pb.GetTestResultsByTaskAndCaseRequest(
                task_id=task_id, test_case_id=case_id)
            if device_type:
                req.device_type = device_type
            if device_id:
                req.device_id = device_id
            resp = stub.GetTestResultsByTaskAndCase(req)
            assert resp.success, resp.message
            return _loads(resp.data, [])

        # 物理路由过滤：只返回 device_id=101
        dev = _fetch(device_type='physical', device_id='101')
        assert len(dev) == 1 and dev[0]['device_id'] == 101

        # API 路由过滤：只返回 api_id=202
        api = _fetch(device_type='http_api', device_id='202')
        assert len(api) == 1 and api[0]['api_id'] == 202

        # 无过滤：返回全部 3 条
        all_rows = _fetch()
        assert len(all_rows) == 3


class TestSerialGatingRealDb:
    """target_modes 目标级门控真实 DB 选行：Task.config 读取 + 真实 SQLAlchemy 查询。

    双道语义的纯逻辑分支已由 tests/unit/test_int604_serial_gating.py 覆盖，
    本文件验证真实 DB/gRPC 链路（Task.config['target_modes'] + 真实 SQLAlchemy 查询）。
    """

    def _engine(self):
        from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
        eng = TaskDispatchMixin()
        eng._log = lambda **kw: None
        return eng

    def _seed_targets(self, config, rows_spec):
        """播种 Task + 按 (device_type, device_id, exec, eval) 构造 TaskCase 行。

        created_at 按 rows_spec 顺序递增微秒，保证「最早 PENDING」口径确定
        （首行最旧）；并行/历史任务选行断言依赖该顺序。

        Returns: (task_id, rows) — rows 为入库后对象列表（按 rows_spec 顺序）。
        """
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase

        s = get_db_session()
        task = Task(name=f'int1115-{uuid.uuid4().hex[:8]}', status='running',
                    total_cases=len(rows_spec), algorithm_type='translation',
                    config=config)
        s.add(task)
        s.flush()
        base = datetime.now()
        rows = []
        for i, (dev_type, dev_id, exec_st, eval_st) in enumerate(rows_spec):
            r = TaskCase(task_id=task.id,
                         test_case_id=f'INT1115-{uuid.uuid4().hex[:8]}-{i}',
                         status='running' if exec_st == ExecutionStatus.RUNNING else 'pending',
                         execution_status=exec_st, evaluation_status=eval_st,
                         device_type=dev_type, device_id=dev_id,
                         created_at=base.replace(microsecond=base.microsecond + i))
            s.add(r)
            rows.append(r)
        s.commit()
        for r in rows:
            s.refresh(r)
        task_id = task.id
        s.close()
        return task_id, rows

    @staticmethod
    def _complete_row(session, row):
        """将行置为全终态（COMPLETED，FINAL）。"""
        from task_service.infrastructure.persistence.models import TaskCase
        from shared.utils.status_constants import TaskCaseStatus
        r = session.get(TaskCase, row.id)
        r.execution_status = ExecutionStatus.COMPLETED
        r.evaluation_status = EvaluationStatus.COMPLETED
        r.status = TaskCaseStatus.COMPLETED
        session.commit()
        session.refresh(r)
        return r

    def test_same_type_serial_chain_no_overlap(self, pg_db, oss_fast_fail):
        """两个同类型串行目标不重叠：后者在前者全部用例行终态后才派发。"""
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import TaskCase

        task_id, rows = self._seed_targets(
            {'target_modes': [
                {'target_type': 'device', 'target_id': 101, 'mode': 'serial'},
                {'target_type': 'device', 'target_id': 102, 'mode': 'serial'},
            ]},
            [('physical', '101', ExecutionStatus.PENDING, EvaluationStatus.PENDING),
             ('physical', '102', ExecutionStatus.PENDING, EvaluationStatus.PENDING)],
        )
        eng = self._engine()
        s = get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_id == '101', \
                '前序串行目标（无前序）应先派发'
            # 前序串行目标在途（RUNNING）→ 后序串行目标不得派发（不重叠）
            r = s.get(TaskCase, rows[0].id)
            r.execution_status = ExecutionStatus.RUNNING
            r.evaluation_status = EvaluationStatus.RUNNING
            r.status = TaskCaseStatus.RUNNING
            s.commit()
            s.expire_all()
            got = eng._get_next_pending_case(task_id, s)
            assert got is None, '前序串行目标在途时后序不得派发'
            # 前序全终态后 → 后序串行目标派发
            self._complete_row(s, rows[0])
            s.expire_all()
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_id == '102', \
                '前序串行目标全终态后，后序串行目标才派发'
        finally:
            s.close()

    def test_serial_api_independent_of_device_lane(self, pg_db, oss_fast_fail):
        """跨类型独立性：设备道串行目标在途时，API 道串行目标按本道前序派发。"""
        task_id, rows = self._seed_targets(
            {'target_modes': [
                {'target_type': 'device', 'target_id': 101, 'mode': 'serial'},
                {'target_type': 'api', 'target_id': 202, 'mode': 'serial'},
            ]},
            [('physical', '101', ExecutionStatus.RUNNING, EvaluationStatus.RUNNING),
             ('http_api', '202', ExecutionStatus.PENDING, EvaluationStatus.PENDING)],
        )
        eng = self._engine()
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'http_api', \
                '串行 API 不等设备道（跨类型独立）：设备道在途不阻塞 API 道'
        finally:
            s.close()

    def test_serial_blocks_until_same_type_prior_terminal(self, pg_db, oss_fast_fail):
        """前序同类型串行目标在途：后序串行目标不得派发（返回 None 等待）。"""
        from shared.models.database import get_db_session

        task_id, rows = self._seed_targets(
            {'target_modes': [
                {'target_type': 'device', 'target_id': 101, 'mode': 'serial'},
                {'target_type': 'device', 'target_id': 102, 'mode': 'serial'},
            ]},
            [('physical', '101', ExecutionStatus.RUNNING, EvaluationStatus.RUNNING),
             ('physical', '102', ExecutionStatus.PENDING, EvaluationStatus.PENDING)],
        )
        eng = self._engine()
        s = get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is None, '同类型前序串行目标未终态时，后序串行目标不得派发'
        finally:
            s.close()

    def test_parallel_behavior_unchanged(self, pg_db, oss_fast_fail):
        """无串行目标（含 target_modes 缺省）：维持现行为，取最早 PENDING 行。"""
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase

        task_id, rows = self._seed_targets(
            None,
            [('http_api', '202', ExecutionStatus.PENDING, EvaluationStatus.PENDING),
             ('physical', '101', ExecutionStatus.PENDING, EvaluationStatus.PENDING)],
        )
        eng = self._engine()
        s = get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'http_api', \
                '缺省全并行：取最早 PENDING 行（API 行先创建应被选中）'
        finally:
            s.close()

    def test_legacy_execution_fields_ignored_as_parallel(self, pg_db, oss_fast_fail):
        """历史任务旧 execution_mode/serial_first：引擎不再读取，按全并行。"""
        task_id, rows = self._seed_targets(
            {'execution_mode': 'serial', 'serial_first': 'device'},
            [('http_api', '202', ExecutionStatus.PENDING, EvaluationStatus.PENDING),
             ('physical', '101', ExecutionStatus.PENDING, EvaluationStatus.PENDING)],
        )
        eng = self._engine()
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            assert eng._is_serial_task(task_id, s) is False, \
                '旧 execution_mode/serial_first 不触发串行（历史任务按全并行）'
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'http_api'
        finally:
            s.close()
