# -*- coding: utf-8 -*-
"""INT-2467 域写工具：提案 → 审批 → 执行（真实网关注册表 + 假回源）。

验收锚点：
- 审批前不回源、无副作用；批准后按目标 REST 执行一次；
- 重复提交 / 重复唤醒不会重复执行（幂等）；
- 审批后权限被收回 → 不执行；
- `device_control`（DESTRUCTIVE）批准必须二次确认（confirm=true）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ApprovalDecision, RunStatus, ToolCallStatus
from agent_service.domain.exceptions import ApprovalConfirmationRequired
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_write.helpers import (
    FakeLlm, OWNER_ID, TENANT_ID, decide, pending_approval, text_turn, tool_turn,
)
from tests.unit.int2451_agent_fakes import build_stack


class FakeRestClient:
    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        payload = {'data': {'id': 99}, 'success': True}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _stack(tmp_path, llm, rest, name='int2467.db'):
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())
    return build_stack(
        tmp_path / name, llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))


def _start(container, message='执行写操作', permissions=('*',)):
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='INT-2467',
        permissions=list(permissions))
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, message=message,
        permissions=list(permissions))
    assert created
    container.executor.submit(run.id)
    return run


def _approve(container, approval_id, *, permissions=('*',), confirm=False):
    return container.run_service.decide_approval(
        approval_id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        decision=ApprovalDecision.APPROVE, permissions=permissions,
        confirm=confirm)


# ---------------------------------------------------------------- 音频导入

def test_audio_import_proposes_then_executes_once(tmp_path):
    call = ToolCallRequest(
        tool_call_id='a1', name='audio_import',
        arguments={'action': 'url_import', 'url': 'http://example/接线测试_a.wav',
                   'audio_type': 'dry'})
    llm = FakeLlm([tool_turn([call]), text_turn('已生成提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = _start(container)

    assert rest.calls == []          # 审批前无副作用
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.proposal['arguments']['action'] == 'url_import'
    assert approval.diff['method'] == 'POST'
    assert approval.diff['path'] == '/api/v1/audios/url-import'
    record = container.repositories['tool_calls'].find(run.id, 'a1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL

    _approve(container, approval.id)
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'audio_url_import'
    assert sent['tool']['method'] == 'POST'
    assert sent['tool']['path'] == '/api/v1/audios/url-import'
    # build_body 只把请求体发出去（意图层的 action 不进 body）
    assert sent['tool']['inputSchema'] is not None
    record = container.repositories['tool_calls'].find(run.id, 'a1')
    assert record.status is ToolCallStatus.COMPLETED

    # 再提交一次（重复唤醒）：不重复回源
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


# ---------------------------------------------------------------- 音频标注

def test_audio_annotate_requires_permission_and_executes(tmp_path):
    call = ToolCallRequest(
        tool_call_id='n1', name='audio_annotate',
        arguments={'action': 'batch_annotate',
                   'items': [{'audio_id': 5, 'tags': ['接线测试_标签']}]})
    llm = FakeLlm([tool_turn([call]), text_turn('已生成提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest, 'annotate.db')
    run = _start(container)

    approval = pending_approval(container, run.id)
    assert approval.diff['path'] == '/api/v1/audios/batch/annotations'
    # 审批时只保留只读权限：audio:update 已收回 → 不执行
    _approve(container, approval.id, permissions=['audio:read'])
    container.executor.submit(run.id)
    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'n1')
    assert record.result_code == 'PERMISSION_DENIED'
    assert container.repositories['runs'].get(run.id).status is RunStatus.FAILED


# ---------------------------------------------------------------- 设备控制

def test_device_control_destructive_requires_second_confirmation(tmp_path):
    call = ToolCallRequest(
        tool_call_id='d1', name='device_control',
        arguments={'action': 'reboot', 'device_id': 10})
    llm = FakeLlm([tool_turn([call]), text_turn('提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest, 'device.db')
    run = _start(container)

    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'DESTRUCTIVE'
    assert approval.diff['second_confirmation']['required'] is True
    assert approval.diff['second_confirmation']['confirm_field'] == 'confirm'

    # 只发 APPROVE、不带 confirm → 拒绝决策，且不执行
    with pytest.raises(ApprovalConfirmationRequired):
        _approve(container, approval.id, confirm=False)
    assert rest.calls == []
    still = pending_approval(container, run.id)
    assert still.status.value == 'PENDING'

    # 带 confirm=true → 批准并执行一次
    _approve(container, approval.id, confirm=True)
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['path'] == '/api/v1/test-devices/{device_id}/reboot'
    assert sent['arguments'] == {'device_id': 10}
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


def test_device_control_batch_executes_renamed_body(tmp_path):
    call = ToolCallRequest(
        tool_call_id='d2', name='device_control',
        arguments={'action': 'batch', 'operation': 'connect',
                   'device_ids': [10, 11]})
    llm = FakeLlm([tool_turn([call]), text_turn('提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest, 'device_batch.db')
    run = _start(container)

    approval = pending_approval(container, run.id)
    _approve(container, approval.id, confirm=True)
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['path'] == '/api/v1/test-devices/batch'
    assert sent['arguments'] == {'body': {'action': 'connect',
                                          'device_ids': [10, 11]}}


# ---------------------------------------------------------------- SPL 校准

def test_spl_calibrate_proposes_then_executes(tmp_path):
    call = ToolCallRequest(
        tool_call_id='s1', name='spl_calibrate',
        arguments={'action': 'calibrate', 'mapping_id': 7})
    llm = FakeLlm([tool_turn([call]), text_turn('提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest, 'spl.db')
    run = _start(container)

    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['path'] == '/api/v1/spl/{mapping_id}/calibrate'
    _approve(container, approval.id)
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    assert rest.calls[0]['arguments'] == {'mapping_id': 7}
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


# ---------------------------------------------------------------- 参数前置校验

def test_invalid_write_arguments_do_not_create_approval(tmp_path):
    call = ToolCallRequest(
        tool_call_id='bad1', name='device_control',
        arguments={'action': 'install', 'device_id': 10, 'params': {}})
    llm = FakeLlm([tool_turn([call]), text_turn('未执行')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest, 'bad.db')
    run = _start(container)

    assert rest.calls == []
    assert container.repositories['approvals'].list_by_run(run.id) == []
    record = container.repositories['tool_calls'].find(run.id, 'bad1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'INVALID_ARGUMENTS'
    assert 'file_path' in record.result['content']
