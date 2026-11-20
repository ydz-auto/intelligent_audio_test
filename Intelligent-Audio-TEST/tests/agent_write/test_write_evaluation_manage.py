# -*- coding: utf-8 -*-
"""INT-2469 评估写意图工具的端到端审批流（共享基座 INT-2466）。

验收锚点（卡面可测标准 1、2、3）：
1. 维度 / 分类写动作提案 → 审批 → 执行，落到真实网关路由；
2. 重评估的「已在队列 / 正在重评估」拒绝原样回灌模型，不重复提交；
3. 同一提案重复结算 / 重复投递只执行一次；无审批凭据不产生副作用。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import RunStatus, ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_write.helpers import (
    FakeLlm, decide, make_container, pending_approval, start_run, text_turn,
    tool_turn,
)


class FakeEvaluationRest:
    def __init__(self, status=200, payload=None):
        self.calls = []
        self._status = status
        self._payload = payload or {'success': True, 'code': 0,
                                    'message': 'Success',
                                    'data': {'id': 42}}

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        return RestResult(status=self._status, payload=self._payload,
                          text=json.dumps(self._payload, ensure_ascii=False))


def _stack(tmp_path, llm, rest):
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())
    return make_container(tmp_path, llm, gateway=gateway)


def _scenario(tmp_path, rest, call, permissions=('*',)):
    llm = FakeLlm([tool_turn([call]), text_turn('评估配置已处理')])
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = start_run(container, permissions=permissions)
    return container, llm, run


# ---------------------------------------------------------------- 提案

def test_dimension_create_proposes_without_side_effect(tmp_path):
    rest = FakeEvaluationRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'dimension_create',
                   'body': {'name': '接线测试_维度', 'weight': 8}})
    container, _llm, run = _scenario(tmp_path, rest, call)

    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['tool'] == 'evaluation_manage'
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['kind'] == 'evaluation_config'
    assert approval.diff['operation'] == 'dimension_create'
    assert approval.diff['changes'] == {'name': '接线测试_维度', 'weight': 8}
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL

    # 重复投递（仍在等待审批）：只保留一张单，不执行
    container.orchestrator.execute(run.id)
    from tests.agent_write.helpers import approvals_of
    assert len(approvals_of(container, run.id)) == 1
    assert rest.calls == []


def test_approved_dimension_create_executes_once_and_resumes(tmp_path):
    rest = FakeEvaluationRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'dimension_create',
                   'body': {'name': '接线测试_维度'}})
    container, llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'evaluation_dimension_create'
    assert sent['tool']['method'] == 'POST'
    assert sent['tool']['path'] == '/api/v1/evaluation/dimensions'
    assert sent['arguments'] == {'body': {'name': '接线测试_维度'}}
    assert sent['permissions'] == ('*',)
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert len(llm.requests) == 2

    # 幂等：重复结算 / 重复投递不再产生第二次副作用
    container.orchestrator.execute(run.id)
    container.orchestrator.execute(run.id)
    assert len(rest.calls) == 1


def test_approved_soft_delete_uses_delete_route(tmp_path):
    rest = FakeEvaluationRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'category_delete', 'cat_id': 3})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    assert '软删' in approval.diff['effect']

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'evaluation_category_delete'
    assert sent['tool']['method'] == 'DELETE'
    assert sent['arguments'] == {'cat_id': 3}


# ---------------------------------------------------------------- 拒绝 / 权限

def test_rejected_proposal_never_executes(tmp_path):
    rest = FakeEvaluationRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'dimension_delete', 'dim_id': 12})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'REJECT', permissions=['*'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_REJECTED'


def test_permission_revoked_between_proposal_and_execution(tmp_path):
    rest = FakeEvaluationRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'reevaluate', 'body': {'task_id': 9001}})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    # 审批时只剩只读权限：evaluation:execute 已收回
    decide(container, approval.id, 'APPROVE', permissions=['evaluation:read'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'
    assert container.repositories['runs'].get(run.id).status is RunStatus.FAILED


# ---------------------------------------------------------------- 重评估去重

def test_duplicate_reevaluate_rejection_is_returned_to_model(tmp_path):
    payload = {'success': False, 'code': 400,
               'message': '任务已在重新评估队列中'}
    rest = FakeEvaluationRest(status=400, payload=payload)
    call = ToolCallRequest(
        tool_call_id='c1', name='evaluation_manage',
        arguments={'action': 'reevaluate', 'body': {'task_id': 9001}})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert len(rest.calls) == 1
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.result_code == 'UPSTREAM_ERROR'
    assert '任务已在重新评估队列中' in (record.result or {}).get('content', '')
    # 上游拒绝是业务结论，不是 run 级崩溃：模型继续答复后正常结束
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
