# -*- coding: utf-8 -*-
"""INT-2471 报告写意图工具的端到端审批流（共享基座 INT-2466）。

验收锚点（卡面可测标准 2、3、4）：
1. 生成 / Studio 起草 / 导出都是「提案 → 审批 → 执行」，提案阶段零副作用；
2. 同一提案重复结算 / 重复投递只执行一次；无审批凭据不产生副作用；
3. 导出编排把「固定文档版本 + 格式」落成一次作业调用，重复导出复用同一作业；
4. 审计可还原输入（工具参数含任务 / 报告 / 文档 / 版本 / 格式）与操作者
   （审批单 requested_by / session_id）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import RunStatus, ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_write.helpers import (
    FakeLlm, approvals_of, decide, make_container, pending_approval,
    start_run, text_turn, tool_turn,
)


def _payload(data, status=200, success=True):
    body = {'success': success, 'code': 0 if success else status,
            'message': 'Success' if success else 'failed', 'data': data}
    return RestResult(status=status, payload=body,
                      text=json.dumps(body, ensure_ascii=False))


class FakeReportRest:
    """按工具名返回报告域 REST 响应，并记录每次回源。"""

    def __init__(self, *, export_job_status='done', reused=False):
        self.calls = []
        self._export_job_status = export_job_status
        self._reused = reused

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'report_generate_task':
            return _payload({'id': 426, 'status': 'exists'})
        if name == 'report_regenerate':
            return _payload({'taskId': 460, 'status': 'generating'})
        if name == 'report_studio_create_document':
            body = arguments.get('body') or {}
            return _payload({
                'doc_id': 'doc-1', 'report_id': body.get('report_id'),
                'title': body.get('title') or '草稿', 'current_version': 1,
                'markdown_content': body.get('markdown_content'),
                'agent_session_id': body.get('agent_session_id'),
                'reused': False,
            })
        if name == 'report_studio_update_document':
            body = arguments.get('body') or {}
            return _payload({'doc_id': arguments['doc_id'],
                             'current_version': int(body['expected_version']) + 1})
        if name == 'report_studio_restore_version':
            body = arguments.get('body') or {}
            return _payload({'doc_id': arguments['doc_id'],
                             'current_version': int(body['expected_version']) + 1})
        if name == 'report_studio_documents_list':
            return _payload({'items': [{'doc_id': 'doc-1',
                                        'report_id': arguments.get('report_id'),
                                        'current_version': 2}], 'total': 1})
        if name == 'report_studio_get_document':
            return _payload({'doc_id': arguments['doc_id'], 'report_id': 426,
                             'title': '导出D', 'current_version': 2})
        if name == 'report_studio_export_document':
            body = arguments.get('body') or {}
            return _payload({
                'export_id': 'export-1', 'doc_id': arguments['doc_id'],
                'version': body.get('version'), 'format': body.get('format'),
                'theme': body.get('theme') or 'default',
                'status': 'done' if self._reused else 'pending',
                'progress': 100 if self._reused else 0,
                'download_ref': '/api/v1/report-studio/exports/export-1/download',
                'reused': self._reused,
            })
        if name == 'report_studio_export_job':
            return _payload({
                'export_id': arguments['export_id'], 'doc_id': 'doc-1',
                'version': 2, 'format': 'html', 'theme': 'default',
                'status': self._export_job_status,
                'progress': 100 if self._export_job_status == 'done' else 50,
                'error': '渲染失败：字体缺失'
                if self._export_job_status == 'failed' else None,
                'download_ref': '/api/v1/report-studio/exports/export-1/download',
            })
        raise AssertionError(f'未预期的回源工具：{name}')


def _gateway(rest):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())


def _scenario(tmp_path, rest, call, permissions=('*',)):
    llm = FakeLlm([tool_turn([call]), text_turn('报告操作已处理')])
    container, _engine, _sf = make_container(
        tmp_path, llm, gateway=_gateway(rest))
    run = start_run(container, permissions=permissions)
    return container, llm, run


def _tool_names(rest):
    return [sent['tool']['name'] for sent in rest.calls]


# ---------------------------------------------------------------- 提案

def test_studio_draft_proposes_without_side_effect(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_generate',
        arguments={'action': 'studio_draft', 'report_id': 426,
                   'body': {'markdown_content': '# 对接草稿'}})
    container, _llm, run = _scenario(tmp_path, rest, call)

    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['tool'] == 'report_generate'
    assert approval.proposal['risk'] == 'WRITE'
    # 审计：输入完整保留（正文 / 报告 ID / 操作者 / 会话）
    assert approval.proposal['arguments']['report_id'] == 426
    assert approval.proposal['arguments']['body']['markdown_content'] == '# 对接草稿'
    assert approval.proposal['requested_by'] == run.owner_id
    assert approval.proposal['session_id'] == run.session_id
    assert approval.diff['kind'] == 'report_generation'
    assert approval.diff['operation'] == 'studio_draft'
    assert approval.diff['markdown_length'] == len('# 对接草稿')
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL

    # 重复投递（仍在等待审批）：只保留一张单，不执行
    container.orchestrator.execute(run.id)
    assert len(approvals_of(container, run.id)) == 1
    assert rest.calls == []


def test_approved_studio_draft_creates_document_once(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_generate',
        arguments={'action': 'studio_draft', 'report_id': 426,
                   'body': {'markdown_content': '# 对接草稿', 'title': '接线测试_草稿'}})
    container, llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert _tool_names(rest) == ['report_studio_create_document']
    sent = rest.calls[0]
    assert sent['tool']['method'] == 'POST'
    assert sent['tool']['path'] == '/api/v1/report-studio/documents'
    body = sent['arguments']['body']
    assert body['report_id'] == 426
    assert body['markdown_content'] == '# 对接草稿'
    # agent_session_id 由服务端按 run 注入，模型参数里没有
    assert body['agent_session_id'] == run.session_id
    assert container.repositories['runs'].get(run.id).status is RunStatus.SUCCEEDED
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert len(llm.requests) == 2

    # 幂等：重复结算 / 重复投递不再产生第二次副作用
    container.orchestrator.execute(run.id)
    container.orchestrator.execute(run.id)
    assert len(rest.calls) == 1


def test_generate_maps_to_task_report_route_and_relays_exists(tmp_path):
    """重复生成不产生重复报告：平台返回 exists 时原样回给模型。"""
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_generate',
        arguments={'action': 'generate', 'task_id': 460})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    sent = rest.calls[0]
    assert sent['tool']['name'] == 'report_generate_task'
    assert sent['tool']['path'] == '/api/v1/reports/generate-task'
    assert sent['arguments'] == {'body': {'task_id': 460}}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert '"status": "exists"' in record.result['content']


def test_regenerate_maps_to_report_id_route(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_generate',
        arguments={'action': 'regenerate', 'report_id': 426})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    assert '软删' in approval.diff['effect']
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    sent = rest.calls[0]
    assert sent['tool']['name'] == 'report_regenerate'
    assert sent['tool']['path'] == '/api/v1/reports/{report_id}/regenerate'
    assert sent['arguments'] == {'report_id': 426, 'body': {}}


# ---------------------------------------------------------------- 导出编排

def test_export_resolves_document_version_and_polls_to_done(tmp_path):
    rest = FakeReportRest(export_job_status='done')
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'doc_id': 'doc-1', 'format': 'html'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    assert approval.diff['kind'] == 'report_export'
    assert approval.diff['format'] == 'html'

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    names = _tool_names(rest)
    assert names[0] == 'report_studio_get_document'
    assert 'report_studio_export_document' in names
    assert 'report_studio_export_job' in names
    export_call = next(s for s in rest.calls
                       if s['tool']['name'] == 'report_studio_export_document')
    # 版本缺省取文档当前版本（2），格式固定进作业请求
    assert export_call['arguments'] == {
        'doc_id': 'doc-1', 'body': {'version': 2, 'format': 'html'}}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['status'] == 'done'
    assert payload['download_ref'].endswith('/export-1/download')
    assert payload['version'] == 2


def test_export_reuses_finished_job_without_rendering_twice(tmp_path):
    rest = FakeReportRest(reused=True)
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'report_id': 426, 'format': 'pdf', 'version': 2})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    names = _tool_names(rest)
    # 按 report_id 定位文档 → 读文档 → 建作业（复用）；作业已完成不再轮询
    assert names == ['report_studio_documents_list',
                     'report_studio_get_document',
                     'report_studio_export_document']
    export_call = next(s for s in rest.calls
                       if s['tool']['name'] == 'report_studio_export_document')
    assert export_call['arguments']['body'] == {'version': 2, 'format': 'pdf'}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['reused'] is True
    assert payload['status'] == 'done'


def test_export_pending_is_reported_as_pending(tmp_path, monkeypatch):
    rest = FakeReportRest(export_job_status='running')
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'doc_id': 'doc-1', 'format': 'md'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=['*'])

    # 轮询上限内一直是 running → 如实返回 pending，不谎报已完成
    from shared.agent_tools import report_tools
    monkeypatch.setattr(report_tools, 'EXPORT_POLL_MAX_ATTEMPTS', 2)
    container.executor.submit(run.id)

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['status'] == 'running'
    assert payload['export_id'] == 'export-1'
    assert '稍后' in payload['note']


def test_export_failed_job_relays_error(tmp_path):
    rest = FakeReportRest(export_job_status='failed')
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'doc_id': 'doc-1', 'format': 'pptx'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['status'] == 'failed'
    assert '渲染失败' in payload['note']


# ---------------------------------------------------------------- 拒绝 / 权限

def test_rejected_proposal_never_executes(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'doc_id': 'doc-1', 'format': 'pdf'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'REJECT', permissions=['*'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_REJECTED'


def test_permission_revoked_between_proposal_and_execution(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_generate',
        arguments={'action': 'regenerate', 'report_id': 426})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    # 审批时只剩只读权限：report:create 已收回
    decide(container, approval.id, 'APPROVE', permissions=['report:read'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'
    assert container.repositories['runs'].get(run.id).status is RunStatus.FAILED


@pytest.mark.parametrize('arguments,code', [
    ({'action': 'studio_draft', 'report_id': 426},
     'INVALID_ARGUMENTS'),
    ({'action': 'regenerate'}, 'INVALID_ARGUMENTS'),
])
def test_invalid_write_arguments_rejected_before_proposal(tmp_path, arguments,
                                                          code):
    rest = FakeReportRest()
    call = ToolCallRequest(tool_call_id='c1', name='report_generate',
                           arguments=arguments)
    container, _llm, run = _scenario(tmp_path, rest, call)
    assert approvals_of(container, run.id) == []
    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == code


def test_export_without_studio_export_permission_is_denied(tmp_path):
    rest = FakeReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export',
        arguments={'doc_id': 'doc-1', 'format': 'pdf'})
    container, _llm, run = _scenario(tmp_path, rest, call,
                                     permissions=('report:read',))
    assert approvals_of(container, run.id) == []
    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'
