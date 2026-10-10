# -*- coding: utf-8 -*-
"""INT-42 真实链路验收：引擎分发侧失败任务必须收敛 failed，不再卡 running。

复现原缺陷场景：api_test_service gRPC 入口不可达（CreateAPITest 抛 RpcError），
失败发生在 api_test_service 接手之前。修复前分发侧兜底只置 execution_status=FAILED、
evaluation_status 恒留 pending —— pending 计入 ACTIVE_EVALUATION_STATUSES，
_handle_no_pending_case 判定 evaluating>0 → 死等 _wait_completion_event →
任务永久卡 running（实测 120s+ 不收敛）。

修复（commit 8c50339b）：TaskDispatchMixin._finalize_dispatch_failure 在评估尚未
启动（pending/queued/None）时同步补写 evaluation_status=completed，用例 status 由
derive_task_case_status 推导为 failed（终态）→ 主循环退出 → 任务收敛 failed。

本文件验证端到端收敛与落库终态契约；兜底语义矩阵与两条失败路径的单测守卫在
tests/unit/test_int42_dispatch_failure_evaluation_status.py。

已知缺陷隔离：沿用本目录 INT-35 套件的 int35_quarantine —— INT-38/39/41/43 已修复
（探针通过、替身自动失效）；INT-40 仍在开发（backlog 卡），_emit_progress 脱管守卫
保持生效，确保本测试只针对 INT-42 单一缺陷面。
"""
import time

import pytest

from tests.integration.test_task_execute_real_chain import (
    _dump_chain_state,
    _seed_execute_scenario,
    _task_row,
    _wait_task_terminal,
    api_double,
    eval_double,
    gateway,
    grpc_mesh,
    int35_quarantine,
    oss_fast_fail,
    pg_db,
    storage_env,
)


@pytest.fixture
def api_grpc_unreachable():
    """把 api_test_service gRPC 入口指向不可达端口并清 channel/stub 缓存。

    引擎分发侧 CreateAPITest 即刻 UNAVAILABLE（与「停掉 api_test_service」等价），
    评估/报告/任务配置等其余服务入口不受影响。结束恢复 grpc_mesh 重定向值并清缓存，
    不污染模块内其他用例。
    """
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(channels_mod, 'API_TEST_GRPC_ADDR', 'localhost:1')
    channels_mod._get_api_test_channel.cache_clear()
    stubs_mod.get_api_test_service_stub.cache_clear()
    yield
    mp.undo()
    channels_mod._get_api_test_channel.cache_clear()
    stubs_mod.get_api_test_service_stub.cache_clear()


class TestInt42DispatchFailureConvergence:
    """验收标准：分发侧失败后任务收敛 failed（不再卡 running），用例落库终态正确。"""

    def test_dispatch_side_failure_converges_task_to_failed(
            self, gateway, api_double, eval_double, int35_quarantine,
            api_grpc_unreachable):
        ids = _seed_execute_scenario(api_double, eval_double)
        task_id = ids['task_id']

        resp = gateway.post(f'/api/v1/tasks/{task_id}/start')
        assert resp.status_code == 200, resp.text[:400]
        body = resp.json()
        assert body.get('success') is True, body

        # 核心验收：任务在等待窗口内收敛终态。修复前 evaluation_status 恒留
        # pending → 引擎死等，本断言在窗口内只会看到 running 超时失败。
        reached, row = _wait_task_terminal(task_id)
        assert reached, f'INT-42 回归：任务未收敛终态（卡 running），现场:\n' \
                        f'{_dump_chain_state(task_id)}'
        assert row.status == 'failed', \
            f'分发侧失败任务终态应为 failed: {row.status}，现场:\n{_dump_chain_state(task_id)}'

        # 终态收敛契约
        assert row.completed_at is not None, '终态任务应写入 completed_at'
        assert row.actual_duration is not None, '终态任务应写入实际执行时长'
        assert row.total_cases == 1
        assert row.failed_cases == 1 and row.completed_cases == 0, \
            f'失败用例应计入 failed_cases: completed={row.completed_cases}, failed={row.failed_cases}'

        # 用例落库终态：exec=failed / eval=completed（修复核心）/ status=failed
        from task_service.infrastructure.persistence.models import TaskCase
        tcs = _query_task_cases(task_id)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.execution_status == 'failed', \
            f'exec 应 failed: {tc.execution_status}，err={tc.error_message!r}'
        assert tc.evaluation_status == 'completed', \
            f'INT-42 核心断言：分发侧失败必须补写 evaluation_status=completed，实际 {tc.evaluation_status}'
        assert tc.status == 'failed', f'status 应推导为 failed: {tc.status}'
        assert tc.completed_at is not None, '失败用例应写入 completed_at'
        assert tc.error_message, '分发侧失败应落 error_message'

        # 失败发生在 api_test_service 接手之前：被测 API 替身不应收到任何真实请求
        assert not api_double.requests, \
            f'分发侧失败不应触达被测 API，实际命中: {sorted({r["path"] for r in api_double.requests})}'

        # 分发失败不产生执行结果
        from task_service.infrastructure.persistence.models import TestResult
        from tests.integration.test_task_execute_real_chain import _query
        assert _query(TestResult, task_id=task_id) == [], \
            '分发侧失败不应产出 TestResult'

        # 任务日志可观测（INT-81 日志三分流：带 task_id 的业务日志落业务
        # 日志文件，logs 表仅收审计/无任务上下文系统日志）
        from shared.logging.business_reader import BusinessLogReader
        entries = BusinessLogReader().read_entries(task_id=task_id)
        assert entries, '执行链路应写任务日志（业务日志文件）'


def _query_task_cases(task_id):
    from task_service.infrastructure.persistence.models import TaskCase
    from tests.integration.test_task_execute_real_chain import _query
    rows = _query(TaskCase, task_id=task_id)
    assert rows, '任务用例关系行应存在'
    return rows
