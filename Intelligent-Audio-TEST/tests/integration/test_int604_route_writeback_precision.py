# -*- coding: utf-8 -*-
"""INT-604 集成验收（真实 Postgres + 进程内 gRPC mesh）。

覆盖验收标准 2 的集成面 + 评审「必改」写侧回写精确性：
1. 写侧状态回写按路由行精确命中（tc_rel_id）：单用例双路由并发时，回写只动
   目标行，兄弟路由不被 (task_id, test_case_id) 全量更新打成同一终态；
2. 评估仅回写（execution_status 不回写）不动兄弟路由执行状态；
3. GetTestResultsByTaskAndCase 路由过滤（device_type/device_id）；
4. serial 门控真实 DB 选行：Task.config 读取 + 真实 SQLAlchemy 查询
   （逐用例时序纯逻辑分支已由 tests/unit/test_int604_serial_gating.py 覆盖，
   本文件验证真实 DB/gRPC 链路）。
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
    EvaluationStatus, ExecutionStatus,
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
    """serial 门控真实 DB 选行：Task.config 读取 + 真实 SQLAlchemy 查询。"""

    def _engine(self):
        from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
        eng = TaskDispatchMixin()
        eng._log = lambda **kw: None
        return eng

    def _new_case_rows(self, config, side1, side2):
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase

        case_id = f'INT604-serial-{uuid.uuid4().hex[:10]}'
        s = get_db_session()
        task = Task(name=f'int604-serial-{uuid.uuid4().hex[:8]}', status='running',
                    total_cases=2, algorithm_type='translation', config=config)
        s.add(task)
        s.flush()
        now = datetime.now()
        r1 = TaskCase(task_id=task.id, test_case_id=case_id, status='pending',
                      execution_status=ExecutionStatus.PENDING,
                      evaluation_status=EvaluationStatus.PENDING,
                      device_type=side1[0], device_id=side1[1], created_at=now)
        r2 = TaskCase(task_id=task.id, test_case_id=case_id, status='pending',
                      execution_status=ExecutionStatus.PENDING,
                      evaluation_status=EvaluationStatus.PENDING,
                      device_type=side2[0], device_id=side2[1], created_at=now)
        s.add_all([r1, r2])
        s.commit()
        s.refresh(r1)
        s.refresh(r2)
        task_id = task.id
        rid1, rid2 = r1.id, r2.id
        s.close()
        return task_id, case_id, rid1, rid2

    def test_serial_first_device_dispatches_device_first(self, pg_db, oss_fast_fail):
        task_id, case_id, rid1, rid2 = self._new_case_rows(
            {'execution_mode': 'serial', 'serial_first': 'device'},
            ('physical', '101'), ('http_api', '202'))
        eng = self._engine()
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'physical', \
                'serial_first=device 时新用例应先派发设备侧行'
        finally:
            s.close()

    def test_serial_first_api_dispatches_api_first(self, pg_db, oss_fast_fail):
        task_id, case_id, rid1, rid2 = self._new_case_rows(
            {'execution_mode': 'serial', 'serial_first': 'api'},
            ('physical', '101'), ('http_api', '202'))
        eng = self._engine()
        s = __import__('shared.models.database', fromlist=['get_db_session']).get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'http_api', \
                'serial_first=api 时新用例应先派发 API 侧行'
        finally:
            s.close()

    def test_serial_blocks_other_side_until_preferred_terminal(
            self, pg_db, oss_fast_fail):
        """优先侧 RUNNING 未终态：另一侧 PENDING 行不得派发（返回 None 等待）。"""
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase

        case_id = f'INT604-gate-{uuid.uuid4().hex[:10]}'
        s = get_db_session()
        task = Task(name=f'int604-gate-{uuid.uuid4().hex[:8]}', status='running',
                    total_cases=2, algorithm_type='translation',
                    config={'execution_mode': 'serial', 'serial_first': 'device'})
        s.add(task)
        s.flush()
        now = datetime.now()
        dev = TaskCase(task_id=task.id, test_case_id=case_id, status='running',
                       execution_status=ExecutionStatus.RUNNING,
                       evaluation_status=EvaluationStatus.RUNNING,
                       device_type='physical', device_id='101', created_at=now)
        api = TaskCase(task_id=task.id, test_case_id=case_id, status='pending',
                       execution_status=ExecutionStatus.PENDING,
                       evaluation_status=EvaluationStatus.PENDING,
                       device_type='http_api', device_id='202', created_at=now)
        s.add_all([dev, api])
        s.commit()
        task_id = task.id
        s.close()

        eng = self._engine()
        s = get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is None, '设备侧未终态时 API 侧不得派发'
        finally:
            s.close()

    def test_parallel_behavior_unchanged(self, pg_db, oss_fast_fail):
        """parallel 模式维持现行为：取最早 PENDING 行（不按侧门控）。"""
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase

        case_id = f'INT604-para-{uuid.uuid4().hex[:10]}'
        s = get_db_session()
        task = Task(name=f'int604-para-{uuid.uuid4().hex[:8]}', status='running',
                    total_cases=2, algorithm_type='translation',
                    config={'execution_mode': 'parallel'})
        s.add(task)
        s.flush()
        now = datetime.now()
        # API 行先创建（created_at 更早）→ parallel 下应取 API 行（不因 device 优先）
        api = TaskCase(task_id=task.id, test_case_id=case_id, status='pending',
                       execution_status=ExecutionStatus.PENDING,
                       evaluation_status=EvaluationStatus.PENDING,
                       device_type='http_api', device_id='202', created_at=now)
        dev = TaskCase(task_id=task.id, test_case_id=case_id, status='pending',
                       execution_status=ExecutionStatus.PENDING,
                       evaluation_status=EvaluationStatus.PENDING,
                       device_type='physical', device_id='101',
                       created_at=now.replace(microsecond=now.microsecond + 1))
        s.add_all([api, dev])
        s.commit()
        task_id = task.id
        s.close()

        eng = self._engine()
        s = get_db_session()
        try:
            got = eng._get_next_pending_case(task_id, s)
            assert got is not None and got.device_type == 'http_api', \
                'parallel 模式取最早 PENDING 行（API 行先创建应被选中）'
        finally:
            s.close()
