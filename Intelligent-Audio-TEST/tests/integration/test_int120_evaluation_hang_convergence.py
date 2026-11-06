# -*- coding: utf-8 -*-
"""INT-120 真实链路验收：评估挂起时忙等不洪泛、任务自动仲裁收敛。

复现 INT-95 复跑事故场景：评估端点受理任务后 get_status 永不返回
completed（等价「评估端点不可达/评估挂起」），task_case_relations 停留
evaluating。修复前主循环 _handle_no_pending_case 每轮固定间隔刷
「等待 N 个执行中/评估中的用例完成」且无最大等待上限 —— 任务永不收敛，
需验收侧手工 UPDATE 解锁引擎。

修复后（INT-120，EvaluationArbiterMixin）：忙等按退避间隔轮询且等待日志
按 wait_max_interval 节流；无进展达 evaluation_hang_timeout（本用例压到
5s）且执行侧已无活跃用例时，仲裁将挂起用例判 failed（evaluation_status=
FAILED、原因写 error_message、逐用例 CASE_FAILED + 任务级 TASK_FAILED
事件），任务自动收敛 failed —— 无需人工干预。

验收标准对应（INT-120）：
1. 日志不洪泛：等待日志按 wait_max_interval 节流，本用例窗口内条数
   ≤ 窗口秒数/30 + 2（等价 5 分钟 < 20 条的验收口径；完整 5 分钟假
   时钟守卫由 tests/unit/test_int120_evaluation_hang_arbitration.py 承载）；
2. 任务在配置的超时阈值后自动收敛终态，无需人工 UPDATE；
3. 正常评估路径不受影响：由 test_task_execute_real_chain 的 happy path
   回归承载（评估秒级完成时不触发仲裁）。

终态口径：exec=completed（执行真实成功）/ eval=failed（INT-107 口径，
评估挂起判失败）/ status=failed + 评估挂起超时原因落 error_message。
"""
import time
import uuid

import pytest

from tests.integration.test_task_execute_real_chain import (
    _dump_chain_state,
    _query,
    _seed_execute_scenario,
    _start_double,
    _TERMINAL_STATUSES,
    api_double,
    gateway,
    grpc_mesh,
    int35_quarantine,
    oss_fast_fail,
    pg_db,
    storage_env,
)


def _eval_hang_responder(method, path):
    """评估算法服务挂起替身：create_task 正常受理，get_status 永远 running。

    与「评估端点不可达」等价的挂起形态：评估发起成功但永不完成，
    task_case_relations.evaluation_status 停留活跃集合，引擎无限等待。
    """
    if method == 'POST' and path == '/api/create_task':
        return True, {'code': 0, 'msg': 'success',
                      'data': {'eval_task_id': f'eval-{uuid.uuid4().hex[:8]}'}}, 200
    if method == 'GET' and path.startswith('/api/get_status/'):
        return True, {'code': 0, 'msg': 'success',
                      'data': {'status': 'running', 'progress': 10}}, 200
    return False, None, 404


@pytest.fixture(scope='module')
def eval_hang_double():
    server, thread = _start_double(_eval_hang_responder)
    server.requests = []
    yield server
    server.shutdown()
    server.server_close()


class TestInt120EvaluationHangConvergence:
    """评估挂起 → 忙等退避 + 超时仲裁 → 任务自动收敛（无需人工 UPDATE）。"""

    def test_evaluation_hang_auto_converges_without_manual_update(
            self, gateway, api_double, eval_hang_double, int35_quarantine,
            monkeypatch):
        from task_service.core.execution_engine import execution_engine

        # 仲裁阈值压到 5s（生产默认 600s，配置化；真实评估轮询窗口 ~120s
        # 内评估侧不会自行写终态，保证挂起由引擎仲裁收敛而非评估失败路径）
        monkeypatch.setattr(execution_engine, 'evaluation_hang_timeout', 5)

        ids = _seed_execute_scenario(api_double, eval_hang_double)
        task_id = ids['task_id']

        resp = gateway.post(f'/api/v1/tasks/{task_id}/start')
        assert resp.status_code == 200, resp.text[:400]
        assert resp.json().get('success') is True, resp.text[:400]

        # 核心验收：任务在仲裁阈值 + 余量内自动收敛终态（修复前永不收敛）。
        # 真实链路里执行本身需 ~60s（替身轮询节奏），窗口对齐 INT-35 套件的 180s。
        from datetime import datetime as _dt
        t0 = _dt.now()
        t0_str = t0.strftime('%Y-%m-%d %H:%M:%S')
        deadline = time.time() + 180
        row = None
        samples = []
        while time.time() < deadline:
            rows = _query_task_rows(task_id)
            row = rows[0] if rows else None
            if row is not None and row.status in _TERMINAL_STATUSES:
                break
            from task_service.infrastructure.persistence.models import TaskCase
            _tcs = _query(TaskCase, task_id=task_id)
            if _tcs:
                _tc = _tcs[0]
                samples.append((round(time.time() - t0.timestamp(), 1), row.status if row else None,
                                _tc.execution_status, _tc.evaluation_status))
            time.sleep(1.0)
        elapsed = round(time.time() - t0.timestamp(), 1)
        assert row is not None and row.status in _TERMINAL_STATUSES, \
            'INT-120 回归：评估挂起任务未自动收敛终态（需人工 UPDATE），现场:\n' \
            f'{_dump_chain_state(task_id)}\ncase timeline: {samples}'
        assert row.status == 'failed', \
            f'评估挂起仲裁后任务终态应为 failed: {row.status}，现场:\n' \
            f'{_dump_chain_state(task_id)}'
        assert row.completed_at is not None, '终态任务应写入 completed_at'
        assert row.actual_duration is not None, '终态任务应写入实际执行时长'
        assert row.failed_cases == 1 and row.completed_cases == 0, \
            f'挂起用例应计入 failed_cases: completed={row.completed_cases}, failed={row.failed_cases}'

        # 用例落库终态（INT-107 口径）：exec=completed（执行真实成功）/ eval=failed / status=failed
        from task_service.infrastructure.persistence.models import TaskCase
        tcs = _query(TaskCase, task_id=task_id)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.execution_status == 'completed', \
            f'执行侧真实成功应保持 completed: {tc.execution_status}'
        assert tc.evaluation_status == 'failed', \
            f'评估挂起应仲裁为 evaluation_status=failed: {tc.evaluation_status}'
        assert tc.status == 'failed', f'status 应推导为 failed: {tc.status}'
        assert '评估挂起超时' in (tc.error_message or ''), \
            f'仲裁原因应落 error_message: {tc.error_message!r}'

        # 执行真实发生：被测 API 替身收到完整异步任务协议
        hit = {r['path'] for r in api_double.requests}
        assert '/health' in hit and '/api/create_task' in hit, \
            f'被测 API 替身命中异常: {sorted(hit)}'
        # 评估真实发起并挂起：评估替身受理了任务且状态被持续轮询
        eval_hit = {r['path'] for r in eval_hang_double.requests}
        assert '/api/create_task' in eval_hit, f'评估任务未发起: {sorted(eval_hit)}'
        assert any(p.startswith('/api/get_status/') for p in eval_hit), \
            f'评估状态未被轮询: {sorted(eval_hit)}'

        # 验收标准 1：忙等等待日志按 wait_max_interval（30s）节流，不随轮询刷屏。
        # 断言节流速率：窗口内条数 ≤ 窗口秒数/30 + 2（首拍 + 快照变化边界），
        # 等价 5 分钟窗口 < 20 条的验收口径（完整 5 分钟假时钟守卫在单测文件）。
        from shared.logging.business_reader import BusinessLogReader
        wait_logs = BusinessLogReader().read_entries(
            task_id=task_id, start_time=t0_str,
            content_include='个执行中/评估中的用例完成')
        max_allowed = int(elapsed / 30) + 2
        assert len(wait_logs) <= max_allowed, \
            f'忙等等待日志超过节流速率（{len(wait_logs)} 条 / {elapsed}s，上限 {max_allowed}）: ' \
            f'{[e.get("content", "")[:80] for e in wait_logs[:5]]}'

        # 等待状态随任务收尾清理（不残留内存泄漏）
        deadline = time.time() + 10
        while time.time() < deadline and task_id in execution_engine.task_wait_states:
            time.sleep(0.2)
        assert task_id not in execution_engine.task_wait_states, \
            '任务收尾应清理等待退避状态'


def _query_task_rows(task_id):
    from task_service.infrastructure.persistence.models import Task
    return _query(Task, id=task_id)
