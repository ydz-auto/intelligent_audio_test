# -*- coding: utf-8 -*-
"""INT-305 回归守卫：任务执行详情模态窗删除用例（四阶段全允许）

覆盖四层（均纯单测，不触真实 DB/gRPC/Redis）：

1. task_service task_lifecycle_service.remove_case 阶段语义——
   - 404：任务/用例不存在；
   - 幂等：移除留痕行重复删除返回成功；
   - 执行中（running）：置用例级中断信号 + 联动取消评估（case_deleted）
     + 软删 + recount + 进度推送 + 审计事件；
   - 待执行（pending/queued 任务）：queued 用例照常中断信号（pending
     用例无执行中的语义差——以 tc.execution_status 判定）；
   - 终态（completed）：触发报告重算（GenerateTaskReport）+ excluded 处置；
   - 报告重算 gRPC 失败降级：删除主链不失败。
2. 仓储 remove_task_case——pending 无结果 → purge（物理删）；有结果/已执行
   → 软删留痕 + TestResult.excluded=1（操作人透传）。
3. 网关 TaskLifecycleService.remove_case——ACL 信封转 HTTP 响应：
   404 → NOT_FOUND；成功 → camelCase data（taskId/caseId/purged/reportRequeued）。
4. evaluation_cancel_handler 命令语义（case_deleted）：回读评估产出
   completed → 由删除方标记 excluded（返回 completed=true）；
   active → 摘除在途（对齐 INT-308 既有语义在本卡的复用契约）。
"""
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.status_constants import EvaluationStatus, ExecutionStatus

import api_gateway.application.services.task.task_lifecycle_service as gw_task_lifecycle_mod
from api_gateway.infrastructure.request_adapter import set_current_request

import evaluation_service.application.handlers.evaluation_cancel_handler as evaluation_cancel_handler

# 导入相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


# ==================== 公共构造 ====================

def _tc(case_id, exec_st=ExecutionStatus.PENDING, eval_st=EvaluationStatus.PENDING,
        error_message=None, row_id=1):
    """TaskCase ORM 形状的对象（remove_case 消费）"""
    return SimpleNamespace(
        id=row_id,
        task_id=5,
        test_case_id=case_id,
        execution_status=exec_st,
        evaluation_status=eval_st,
        status='pending',
        error_message=error_message,
    )


def _task(status='running'):
    return SimpleNamespace(id=5, status=status)


def _fake_request(json_body=None, query=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {})


REMOVED_MSG = '用例已被移除'


# ==================== 1. task_service remove_case 阶段语义 ====================

class TestRemoveCaseLifecycle:
    """TaskLifecycleService.remove_case：四阶段语义 + 审计 + 幂等"""

    def _run(self, task_status, tc, removal=None, cancel_data=None, tcs=None):
        """公共编排：mock 仓储/引擎/评估取消/报告重算，跑 remove_case

        `tcs`：多路由场景（INT-2233）下 find_task_cases 返回的全部路由行；
        缺省按单行 `[tc]`。
        """
        calls = {'case_stop': [], 'cancel': [], 'recount': 0, 'audit': [],
                 'progress': 0, 'report': 0, 'remove': 0}
        if removal is None:
            removal = {'removed': True, 'had_result': True, 'purged': False}

        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo, \
             patch('task_service.core.execution_engine.execution_engine') as engine, \
             patch('shared.clients.grpc_clients.cancel_case_evaluations') as cancel, \
             patch('shared.utils.distributed_coordinator.set_task_case_stop') as set_stop, \
             patch.object(
                 __import__('task_service.application.task.task_lifecycle_service',
                           fromlist=['TaskLifecycleService']).TaskLifecycleService,
                 '_publish_removal_audit',
                 side_effect=lambda *a, **k: calls['audit'].append((a, k))):
            repo.get_task_orm.return_value = _task(task_status)
            repo.find_task_cases.return_value = list(tcs) if tcs is not None else [tc]
            repo.remove_task_case.return_value = removal
            repo.expire_progress_cache.return_value = None
            engine.notify_case_completed.return_value = None
            engine._emit_progress.side_effect = lambda *a, **k: calls.__setitem__('progress', calls['progress'] + 1)
            cancel.return_value = cancel_data or {
                'success': True, 'message': 'ok',
                'data': {'results': [{'test_case_id': tc.test_case_id, 'cancelled': True,
                                      'completed': False, 'inflight_removed': 1,
                                      'subservice_notified': 0}],
                         'cancelled_inflight': 1, 'subservice_notified': 0}}

            def _recount(tid):
                calls['recount'] += 1

            def _set_stop(tid, cid):
                calls['case_stop'].append((tid, cid))

            def _remove(tid, cid, deleted_by_user_id=None):
                calls['remove'] += 1
                return removal

            repo.recount_task_cases.side_effect = _recount
            repo.remove_task_case.side_effect = _remove
            set_stop.side_effect = _set_stop

            svc = __import__('task_service.application.task.task_lifecycle_service',
                             fromlist=['TaskLifecycleService']).TaskLifecycleService()
            svc._trigger_report_recalculate = MagicMock(
                side_effect=lambda tid: (calls.__setitem__('report', calls['report'] + 1), True)[1])
            result = svc.remove_case(5, tc.test_case_id)

        return result, calls

    def test_task_not_found(self):
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = None
            result = TaskLifecycleService().remove_case(5, 'c1')
        assert result['success'] is False and result['code'] == 404

    def test_case_not_found(self):
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = _task()
            repo.find_task_cases.return_value = []
            result = TaskLifecycleService().remove_case(5, 'c1')
        assert result['success'] is False and result['code'] == 404

    def test_idempotent_on_removed_trace(self):
        """重复删除：留痕行返回幂等成功，不再触发任何副作用"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = _task()
            repo.find_task_cases.return_value = [_tc('c1', error_message=REMOVED_MSG)]
            result = TaskLifecycleService().remove_case(5, 'c1')
        assert result['success'] is True
        assert result['data']['idempotent'] is True
        repo.remove_task_case.assert_not_called()
        repo.recount_task_cases.assert_not_called()

    def test_running_case_interrupted_then_removed(self):
        """执行中删除：中断信号 + 联动取消评估 + recount + 进度推送 + 审计"""
        result, calls = self._run('running', _tc('c1', ExecutionStatus.RUNNING, EvaluationStatus.RUNNING))
        assert result['success'] is True
        assert calls['case_stop'] == [(5, 'c1')]
        assert calls['recount'] == 1
        assert calls['progress'] >= 1
        assert len(calls['audit']) == 1
        assert result['data']['purged'] is False
        assert calls['report'] == 0  # 执行中不触发报告重算

    def test_pending_queued_task_direct_removal(self):
        """待执行任务删除：不置中断信号（pending 用例无在途执行）、recount、审计"""
        result, calls = self._run('pending', _tc('c1', ExecutionStatus.PENDING, EvaluationStatus.PENDING))
        assert result['success'] is True
        assert calls['case_stop'] == []
        assert calls['recount'] == 1
        assert len(calls['audit']) == 1

    def test_queued_case_in_running_task_sets_interrupt(self):
        """执行中任务的排队用例删除：同样置中断信号（在途领取防御）"""
        result, calls = self._run('running', _tc('c1', ExecutionStatus.QUEUED, EvaluationStatus.PENDING))
        assert result['success'] is True
        assert calls['case_stop'] == [(5, 'c1')]

    def test_completed_task_triggers_report_recalc(self):
        """已完成任务删除：触发报告重算，不置中断信号"""
        result, calls = self._run('completed', _tc('c1', ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED))
        assert result['success'] is True
        assert calls['case_stop'] == []
        assert calls['report'] == 1
        assert result['data']['report_requeued'] is True

    def test_purged_pending_case_no_results(self):
        """待执行且无结果：purge 语义（purged=true 透出）"""
        result, calls = self._run(
            'pending', _tc('c1'),
            removal={'removed': True, 'had_result': False, 'purged': True})
        assert result['success'] is True
        assert result['data']['purged'] is True

    def test_report_recalc_failure_degrades(self):
        """报告重算失败降级：删除主链仍成功，report_requeued=False"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo, \
             patch('task_service.core.execution_engine.execution_engine') as engine, \
             patch('task_service.infrastructure.acl.report_acl_repository.report_acl_repository') as report_acl:
            repo.get_task_orm.return_value = _task('completed')
            repo.find_task_cases.return_value = [_tc('c1', ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED)]
            repo.remove_task_case.return_value = {'removed': True, 'had_result': True, 'purged': False}
            repo.expire_progress_cache.return_value = None
            report_acl.recalculate_task_report.side_effect = RuntimeError('report svc down')
            with patch.object(TaskLifecycleService, '_publish_removal_audit'):
                result = TaskLifecycleService().remove_case(5, 'c1')
        assert result['success'] is True
        assert result['data']['report_requeued'] is False

    # ---------- INT-2233：多路由用例移除（全量行收敛） ----------

    def test_multi_route_calls_removal_once_for_all_rows(self):
        """多路由：用例级移除只调用一次仓储全量处置（不是按行重复删）"""
        row1 = _tc('c1', ExecutionStatus.PENDING, EvaluationStatus.PENDING, row_id=11)
        row2 = _tc('c1', ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED, row_id=12)
        result, calls = self._run('running', row1, tcs=[row1, row2])
        assert result['success'] is True
        assert calls['remove'] == 1      # 全量行一次收敛
        assert calls['recount'] == 1
        assert len(calls['audit']) == 1
        assert result['data']['idempotent'] is False

    def test_multi_route_active_row_sets_interrupt(self):
        """多路由：任一路由行在途即置用例级中断信号（不能只看首行 pending）"""
        row1 = _tc('c1', ExecutionStatus.PENDING, EvaluationStatus.PENDING, row_id=11)
        row2 = _tc('c1', ExecutionStatus.RUNNING, EvaluationStatus.RUNNING, row_id=12)
        result, calls = self._run('running', row1, tcs=[row1, row2])
        assert result['success'] is True
        assert calls['case_stop'] == [(5, 'c1')]

    def test_multi_route_idempotent_when_all_rows_traced(self):
        """多路由：全量行均已留痕 → 幂等成功且无任何副作用"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        rows = [_tc('c1', error_message=REMOVED_MSG, row_id=11),
                _tc('c1', error_message=REMOVED_MSG, row_id=12)]
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = _task()
            repo.find_task_cases.return_value = rows
            result = TaskLifecycleService().remove_case(5, 'c1')
        assert result['success'] is True
        assert result['data']['idempotent'] is True
        repo.remove_task_case.assert_not_called()
        repo.recount_task_cases.assert_not_called()

    def test_multi_route_partial_trace_still_removes_live_rows(self):
        """多路由：历史残留半删状态（部分行已留痕）→ 仍按存活行执行移除"""
        row1 = _tc('c1', error_message=REMOVED_MSG, row_id=11)
        row2 = _tc('c1', ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED, row_id=12)
        result, calls = self._run('completed', row2, tcs=[row1, row2])
        assert result['success'] is True
        assert calls['remove'] == 1
        assert result['data']['idempotent'] is False


# ==================== 2. 仓储 remove_task_case ====================

class TestRemoveTaskCaseRepository:
    """task_repository.remove_task_case：purge/软删分流 + excluded 处置"""

    def _setup_sqlite(self):
        """进程内临时 sqlite 库建表（仅本卡相关表）"""
        from shared.models.database import remove_db_session as _rm, init_db
        _rm()
        init_db(pool_size=3)
        from shared.models.database import Base, get_engine
        import task_service.infrastructure.persistence.models as tmodels  # noqa: F401 注册 PO
        engine = get_engine()
        Base.metadata.create_all(
            bind=engine,
            tables=[
                tmodels.Task.__table__, tmodels.TaskCase.__table__,
                tmodels.TestResult.__table__,
            ],
        )

    def test_purge_pending_case_without_results(self):
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=101, name='t', status='pending', total_cases=1,
                             completed_cases=0, failed_cases=0))
            session.add(TaskCase(task_id=101, test_case_id='c-purge',
                                 execution_status=ExecutionStatus.PENDING,
                                 evaluation_status=EvaluationStatus.PENDING))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(101, 'c-purge', deleted_by_user_id=9)
        assert result == {'removed': True, 'had_result': False, 'purged': True}

        session = get_db_session()
        try:
            assert session.query(TaskCase).filter_by(task_id=101).count() == 0
        finally:
            session.close()

    def test_soft_delete_with_excluded_results(self):
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=102, name='t', status='completed', total_cases=1,
                             completed_cases=1, failed_cases=0))
            session.add(TaskCase(task_id=102, test_case_id='c-done',
                                 status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TestResult(task_id=102, test_case_id='c-done',
                                   execution_status=ExecutionStatus.COMPLETED))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(102, 'c-done', deleted_by_user_id=7)
        assert result == {'removed': True, 'had_result': True, 'purged': False}

        session = get_db_session()
        try:
            tc = session.query(TaskCase).filter_by(task_id=102, test_case_id='c-done').first()
            assert tc is not None  # 软删留痕行仍在
            assert tc.error_message == REMOVED_MSG
            assert tc.updated_by_user_id == 7
            tr = session.query(TestResult).filter_by(task_id=102, test_case_id='c-done').first()
            assert tr is not None  # 结果不物理删（保审计）
            assert int(tr.excluded) == 1  # excluded 标记
            assert tr.excluded_by_user_id == 7
            assert tr.excluded_at is not None  # 排除时间盖写（软删留痕的库内落点）
        finally:
            session.close()

    def test_missing_case_returns_none(self):
        self._setup_sqlite()
        from task_service.infrastructure.persistence.task_repository import task_repository
        assert task_repository.remove_task_case(999, 'c-x') is None

    def test_recount_excludes_removed_rows(self):
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=103, name='t', status='completed', total_cases=2,
                             completed_cases=2, failed_cases=0))
            session.add(TaskCase(task_id=103, test_case_id='c-a', status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TaskCase(task_id=103, test_case_id='c-b', status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED,
                                 error_message=REMOVED_MSG))
            session.commit()
        finally:
            session.close()

        task_repository.recount_task_cases(103)
        session = get_db_session()
        try:
            task = session.get(Task, 103)
            assert task.total_cases == 1  # 移除留痕行不计入
            assert task.completed_cases == 1
        finally:
            session.close()

    # ---------- INT-2233：多路由（同一用例 × 多目标多行） ----------

    def test_multi_route_pending_rows_all_purged(self):
        """多路由未执行：全部路由行物理删除（不是只删首行）"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=201, name='t', status='pending', total_cases=1,
                             completed_cases=0, failed_cases=0))
            for dev_id in (11, 12):
                session.add(TaskCase(task_id=201, test_case_id='c-multi', device_id=dev_id,
                                     execution_status=ExecutionStatus.PENDING,
                                     evaluation_status=EvaluationStatus.PENDING))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(201, 'c-multi', deleted_by_user_id=9)
        assert result == {'removed': True, 'had_result': False, 'purged': True}

        session = get_db_session()
        try:
            assert session.query(TaskCase).filter_by(task_id=201).count() == 0
        finally:
            session.close()

    def test_multi_route_soft_delete_covers_all_rows(self):
        """多路由已执行：全部路由行留痕软删 + 结果 excluded（保审计）"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=202, name='t', status='completed', total_cases=1,
                             completed_cases=1, failed_cases=0))
            for dev_id in (21, 22):
                session.add(TaskCase(task_id=202, test_case_id='c-multi', device_id=dev_id,
                                     status='completed',
                                     execution_status=ExecutionStatus.COMPLETED,
                                     evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TestResult(task_id=202, test_case_id='c-multi', device_id=21,
                                   execution_status=ExecutionStatus.COMPLETED))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(202, 'c-multi', deleted_by_user_id=7)
        assert result == {'removed': True, 'had_result': True, 'purged': False}

        session = get_db_session()
        try:
            rows = session.query(TaskCase).filter_by(task_id=202, test_case_id='c-multi').all()
            assert len(rows) == 2                       # 留痕保审计，不物理删
            assert all(r.error_message == REMOVED_MSG for r in rows)  # 两行都盖上移除留痕
            assert all(r.updated_by_user_id == 7 for r in rows)
            tr = session.query(TestResult).filter_by(task_id=202, test_case_id='c-multi').first()
            assert tr is not None and int(tr.excluded) == 1
        finally:
            session.close()

        # 详情/统计按留痕行剔除 → 该用例已不可见
        assert task_repository.count_task_cases_excluding_removed(202) == 0

    def test_multi_route_mixed_pending_and_completed_soft_deletes_all(self):
        """多路由混合状态（一行未开始、一行已完成）：存在产出即整体软删留痕"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=203, name='t', status='running', total_cases=1,
                             completed_cases=0, failed_cases=0))
            session.add(TaskCase(task_id=203, test_case_id='c-mixed', device_id=31,
                                 execution_status=ExecutionStatus.PENDING,
                                 evaluation_status=EvaluationStatus.PENDING))
            session.add(TaskCase(task_id=203, test_case_id='c-mixed', device_id=32,
                                 status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TestResult(task_id=203, test_case_id='c-mixed', device_id=32,
                                   execution_status=ExecutionStatus.COMPLETED))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(203, 'c-mixed', deleted_by_user_id=7)
        assert result == {'removed': True, 'had_result': True, 'purged': False}

        session = get_db_session()
        try:
            rows = session.query(TaskCase).filter_by(task_id=203).all()
            assert len(rows) == 2
            assert all(r.error_message == REMOVED_MSG for r in rows)
        finally:
            session.close()

    def test_multi_route_partial_trace_purges_remaining_live_rows(self):
        """多路由历史半删（首行已留痕）：移除仍清理剩余存活行"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=204, name='t', status='pending', total_cases=1,
                             completed_cases=0, failed_cases=0))
            session.add(TaskCase(task_id=204, test_case_id='c-half', device_id=41,
                                 execution_status=ExecutionStatus.PENDING,
                                 evaluation_status=EvaluationStatus.PENDING,
                                 error_message=REMOVED_MSG))
            session.add(TaskCase(task_id=204, test_case_id='c-half', device_id=42,
                                 execution_status=ExecutionStatus.PENDING,
                                 evaluation_status=EvaluationStatus.PENDING))
            session.commit()
        finally:
            session.close()

        result = task_repository.remove_task_case(204, 'c-half', deleted_by_user_id=7)
        assert result == {'removed': True, 'had_result': False, 'purged': True}

        session = get_db_session()
        try:
            rows = session.query(TaskCase).filter_by(task_id=204).all()
            assert len(rows) == 1 and str(rows[0].device_id) == '41'  # 只留历史留痕行
        finally:
            session.close()
        assert task_repository.count_task_cases_excluding_removed(204) == 0

    def test_recount_is_case_level_not_row_level(self):
        """INT-2233：计数按用例去重（一个用例 × 2 路由 = 1 条用例）"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=205, name='t', status='completed', total_cases=2,
                             completed_cases=2, failed_cases=0))
            for dev_id in (51, 52):  # 同一用例两条路由
                session.add(TaskCase(task_id=205, test_case_id='c-two-routes', device_id=dev_id,
                                     status='completed',
                                     execution_status=ExecutionStatus.COMPLETED,
                                     evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TaskCase(task_id=205, test_case_id='c-single', device_id=53,
                                 status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED))
            session.commit()
        finally:
            session.close()

        task_repository.recount_task_cases(205)
        session = get_db_session()
        try:
            task = session.get(Task, 205)
            assert task.total_cases == 2       # 去重用例数（不是 3 行）
            assert task.completed_cases == 2
        finally:
            session.close()

    def test_acceptance_multi_route_remove_then_counts_and_idempotent(self):
        """验收：用例 × 2 目标 → 移除后详情/统计 0 条、total_cases 减 1、重复移除幂等"""
        self._setup_sqlite()
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
        from task_service.infrastructure.persistence.task_repository import task_repository

        session = get_db_session()
        try:
            session.add(Task(id=206, name='t', status='completed', total_cases=2,
                             completed_cases=2, failed_cases=0))
            # 用例 c-multi × 2 目标；另一用例 c-keep
            for dev_id in (61, 62):
                session.add(TaskCase(task_id=206, test_case_id='c-multi', device_id=dev_id,
                                     status='completed',
                                     execution_status=ExecutionStatus.COMPLETED,
                                     evaluation_status=EvaluationStatus.COMPLETED))
            session.add(TaskCase(task_id=206, test_case_id='c-keep', device_id=63,
                                 status='completed',
                                 execution_status=ExecutionStatus.COMPLETED,
                                 evaluation_status=EvaluationStatus.COMPLETED))
            for dev_id in (61, 62):
                session.add(TestResult(task_id=206, test_case_id='c-multi', device_id=dev_id,
                                       execution_status=ExecutionStatus.COMPLETED))
            session.commit()
        finally:
            session.close()

        task_repository.remove_task_case(206, 'c-multi', deleted_by_user_id=7)
        task_repository.recount_task_cases(206)

        session = get_db_session()
        try:
            task = session.get(Task, 206)
            assert task.total_cases == 1          # 移除后减 1（用例级口径）
            live = session.query(TaskCase).filter(
                TaskCase.task_id == 206,
                TaskCase.test_case_id == 'c-multi',
                TaskCase.error_message != REMOVED_MSG,
            ).count()
            assert live == 0                      # 详情/列表不再出现该用例
        finally:
            session.close()

        # 重复移除幂等：不再产生副作用
        again = task_repository.remove_task_case(206, 'c-multi', deleted_by_user_id=7)
        assert again == {'removed': True, 'had_result': True, 'purged': False}
        session = get_db_session()
        try:
            assert session.query(TaskCase).filter_by(task_id=206).count() == 3  # 2 留痕 + 1 保留
        finally:
            session.close()


# ==================== 3. 网关 remove_case 入口 ====================

class TestGatewayRemoveCase:
    """网关 TaskLifecycleService.remove_case：ACL 信封 → HTTP 响应"""

    def test_success_camel_case(self, monkeypatch):
        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', SimpleNamespace(
            remove_case=lambda tid, cid: {
                'success': True, 'message': '用例已移除',
                'data': {'task_id': 5, 'case_id': 'c1', 'removed': True,
                         'idempotent': False, 'purged': False,
                         'report_requeued': True}}))
        set_current_request(_fake_request())
        try:
            body, http_code = gw_task_lifecycle_mod.TaskLifecycleService.remove_case(5, 'c1')
        finally:
            set_current_request(None)
        assert http_code == 200
        assert body['data']['taskId'] == '5'
        assert body['data']['caseId'] == 'c1'
        assert body['data']['removed'] is True
        assert body['data']['idempotent'] is False
        assert body['data']['purged'] is False
        assert body['data']['reportRequeued'] is True

    def test_idempotent_marker_passthrough(self, monkeypatch):
        """幂等重复删除：removed/idempotent 经 BFF 透传不丢失（INT-305 P4）"""
        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', SimpleNamespace(
            remove_case=lambda tid, cid: {
                'success': True, 'message': '用例已被移除',
                'data': {'removed': True, 'idempotent': True}}))
        set_current_request(_fake_request())
        try:
            body, http_code = gw_task_lifecycle_mod.TaskLifecycleService.remove_case(5, 'c1')
        finally:
            set_current_request(None)
        assert http_code == 200
        assert body['data']['removed'] is True
        assert body['data']['idempotent'] is True
        assert body['data']['purged'] is False  # 幂等路径无 purge/report 语义
        assert body['data']['reportRequeued'] is False

    def test_not_found_maps_404(self, monkeypatch):
        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', SimpleNamespace(
            remove_case=lambda tid, cid: {
                'success': False, 'message': '未找到该任务关联的用例', 'code': 404}))
        set_current_request(_fake_request())
        try:
            body, http_code = gw_task_lifecycle_mod.TaskLifecycleService.remove_case(5, 'c1')
        finally:
            set_current_request(None)
        assert http_code == 404

    def test_business_error_maps_code(self, monkeypatch):
        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', SimpleNamespace(
            remove_case=lambda tid, cid: {
                'success': False, 'message': '删除失败', 'code': 500}))
        set_current_request(_fake_request())
        try:
            body, http_code = gw_task_lifecycle_mod.TaskLifecycleService.remove_case(5, 'c1')
        finally:
            set_current_request(None)
        # 非 404 失败按既有 control/retry 口径：HTTP 400 + 业务码透传
        assert http_code == 400
        assert body['code'] == 500


# ==================== 4. 评估取消联动（INT-308 复用契约） ====================

class TestCancelEvaluationsForRemoval:
    """cancel_case_evaluations(reason='case_deleted')：本卡复用契约

    - 命令语义信任请求方：评估中 → 摘除在途（cancelled=true）；
    - 评估已实际产出（completed/failed）→ completed=true 由删除方
      remove_task_case 标记 excluded（本卡仓储路径承接）。
    """

    def _run(self, eval_status, reason='case_deleted'):
        tcs = [SimpleNamespace(test_case_id='c1', evaluation_status=eval_status)]
        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', return_value=tcs), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case', return_value=[('e1', 'http://ep')]) as cancel, \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=1), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit'):
            return evaluation_cancel_handler.cancel_case_evaluations(5, ['c1'], reason=reason), cancel

    def test_active_evaluation_cancelled(self):
        result, cancel = self._run(EvaluationStatus.RUNNING)
        item = result['results'][0]
        assert item['cancelled'] is True and item['completed'] is False
        assert result['cancelled_inflight'] == 1
        assert cancel.call_count == 1

    def test_completed_evaluation_returns_excluded_marker(self):
        """评估已产出 → completed=true（删除方据此以 excluded 处置，不重复取消）"""
        result, cancel = self._run(EvaluationStatus.COMPLETED)
        item = result['results'][0]
        assert item['cancelled'] is False and item['completed'] is True
        assert result['cancelled_inflight'] == 0
        cancel.assert_not_called()  # 已完成不可取消
