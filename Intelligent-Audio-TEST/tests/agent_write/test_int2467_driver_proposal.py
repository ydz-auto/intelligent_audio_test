# -*- coding: utf-8 -*-
"""INT-2467 `driver_propose`：确定性提案 + 静态检查 + T2 结论 + 发布守卫。

验收锚点（卡面 6~8 / 负责人增补）：
- 同一输入重复生成 hash 相同；产物带 artifact_kind / source_trace / validation_report；
- 静态检查或 T2 失败 → publishable=false（不产生可发布产物）；
- T2 运行时不可用 → T2_RUNTIME_UNAVAILABLE，绝不降级；
- PAIR 成对交付时 manifest 互相引用；
- 未审批不写注册表：发布开关默认关闭、无已批准审批单即拒绝。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.driver_proposal_service import (
    DriverProposalError, DriverProposalService, DriverProposalSettings,
    PUBLISH_APPROVAL_REQUIRED, PUBLISH_DISABLED, PUBLISH_NOT_PUBLISHABLE,
    PUBLISH_UNAVAILABLE, STATIC_FAILED, STATIC_OK, T2_RUNTIME_UNAVAILABLE,
)
from agent_service.application.sandbox_runner import (
    SandboxFailureReason, SandboxOutcome, SandboxResult, T2PhaseResult,
)

CAPABILITIES = {
    'stimulus_modes': ['ACOUSTIC_PLAYBACK', 'TEXT_INPUT'],
    'capture_modes': ['UI_TEXT', 'PCM_CAPTURE'],
    'timing_points': ['PLAYBACK_START', 'PLAYBACK_END', 'FIRST_PARTIAL',
                      'FINAL_TEXT', 'REPLY_END'],
    'result_fields': ['success', 'message', 'asr', 'text', 'user_wav',
                      'ai_wav', 'latency_ms'],
    'supported_metrics': ['WER', 'CER', 'FIRST_TOKEN_LATENCY', 'TTS_QUALITY',
                          'BARGE_IN'],
    'limitations': ['无录屏：仅 UI 文本 + PCM 抓取'],
}

UI_TRACE = {
    'actions': [
        {'step': 1, 'action': 'tap',
         'locator': {'resource_id': 'com.doubao:id/input'}, 'screenshot': 's1'},
        {'step': 2, 'action': 'tap',
         'locator': {'text': '发送', 'fallback_reason': '控件无 resource_id'}},
    ],
    'pages': [{'name': 'chat', 'nodes': [{'text': '发送'}]}],
    'screenshots': ['s1'],
}

CONTRACT = {
    'endpoints': [{'path': '/v1/realtime', 'method': 'POST'}],
    'auth': {'header': 'Authorization', 'type': 'bearer'},
    'samples': [{'request': {'model': 'gpt-realtime'}}],
}


def _pair_args():
    return {
        'target_kind': 'PAIR',
        'app_type': 'doubao', 'version': 'v1', 'platform': 'ANDROID',
        'display_name': '豆包 Android v1',
        'capabilities': dict(CAPABILITIES),
        'ui_trace': dict(UI_TRACE),
        'api_id': 42, 'vendor': 'openai', 'protocol': 'realtime',
        'contract': dict(CONTRACT),
    }


class FakeSandbox:
    """T2 执行器替身：按预置结论返回 SandboxResult。"""

    def __init__(self, succeeded=True):
        self.succeeded = succeeded
        self.requests = []

    def run_untrusted_code(self, request):
        self.requests.append(request)
        outcome = (SandboxOutcome.SUCCEEDED if self.succeeded
                   else SandboxOutcome.FAILED)
        return SandboxResult(
            outcome=outcome,
            reason=(SandboxFailureReason.EXIT_CODE_NONZERO
                    if not self.succeeded else SandboxFailureReason.NONE),
            runtime='runsc',
            code_sha256=request.code_sha256,
            phases=(T2PhaseResult(name='import_compile', outcome=outcome,
                                  exit_code=0 if self.succeeded else 1),),
            detail='fake sandbox',
        )


def _service(sandbox=None, **settings):
    return DriverProposalService(
        sandbox_runner=sandbox,
        settings=DriverProposalSettings(max_result_chars=200000,
                                        **settings))


# ---------------------------------------------------------------- 生成与复现

def test_same_input_produces_same_hash():
    svc = _service()
    first = svc.generate(_pair_args())
    second = svc.generate(_pair_args())
    assert first['code_sha256'] == second['code_sha256']
    # 材料变化 → hash 变化（可解释 diff）
    changed = _pair_args()
    changed['capabilities'] = dict(CAPABILITIES, limitations=['只能取 UI 文本'])
    third = svc.generate(changed)
    assert third['code_sha256'] != first['code_sha256']


def test_pair_proposal_declares_artifacts_trace_and_validation():
    payload = _service().generate(_pair_args())
    assert payload['target_kind'] == 'PAIR'
    assert payload['artifact_kinds'] == ['DEVICE_DRIVER', 'API_ADAPTER']
    # 每个 artifact 带 artifact_kind 与注册键
    by_kind = {item['artifact_kind']: item for item in payload['artifacts']}
    assert by_kind['DEVICE_DRIVER']['registry_key'] == {
        'app_type': 'doubao', 'version': 'v1', 'platform': 'ANDROID'}
    assert by_kind['API_ADAPTER']['registry_key'] == {
        'protocol': 'realtime', 'vendor': 'openai'}
    # 成对交付：manifest 互相引用
    assert by_kind['DEVICE_DRIVER']['pair_with'] == \
        by_kind['API_ADAPTER']['artifact_id']
    assert by_kind['API_ADAPTER']['pair_with'] == \
        by_kind['DEVICE_DRIVER']['artifact_id']
    # 文件级 artifact_kind
    modules = {item['path']: item for item in payload['files']}
    assert modules['drivers/doubao_v1_driver.py']['artifact_kind'] == \
        'DEVICE_DRIVER'
    assert modules['adapters/openai_realtime_adapter.py']['artifact_kind'] == \
        'API_ADAPTER'
    # source_trace：动作数 / 定位质量（文本退化要带原因）
    trace = payload['source_trace']
    assert trace['actions'] == 2
    assert trace['locators']['stable_locators'] == 1
    assert trace['locators']['text_locators'] == 1
    assert trace['locators']['text_fallbacks'][0]['reason'] == '控件无 resource_id'
    # validation_report 结构
    report = payload['validation_report']
    assert report['static_check']['outcome'] == STATIC_OK
    assert report['t2']['reason'] == T2_RUNTIME_UNAVAILABLE
    assert report['publishable'] is False


def test_generated_files_are_deterministic_python_and_json():
    import ast
    import json
    payload = _service().generate(_pair_args())
    files = {item['path']: item['content'] for item in payload['files']}
    for path, content in files.items():
        if path.endswith('.py'):
            ast.parse(content, filename=path)
        if path.endswith('.json'):
            json.loads(content)
    assert 'manifest.json' in files
    assert 'capabilities.json' in files
    assert 'tests/registry_resolve.py' in files


def test_missing_materials_are_rejected():
    args = _pair_args()
    args.pop('ui_trace')
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    assert 'ui_trace' in str(exc.value)

    args = {'target_kind': 'DEVICE_DRIVER', 'capabilities': dict(CAPABILITIES)}
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    assert 'app_type' in str(exc.value)


def test_bad_capabilities_rejected_before_generation():
    args = _pair_args()
    args['capabilities'] = dict(CAPABILITIES, capture_modes=['UI_TEXT'],
                                supported_metrics=['TTS_QUALITY'])
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    assert 'TTS_QUALITY' in str(exc.value)


# ---------------------------------------------------------------- 静态检查

def test_static_check_detects_corrupted_driver_metadata():
    svc = _service()
    args = _pair_args()
    built = svc._build(args, 'PAIR')
    files = dict(built['files'])
    files['drivers/doubao_v1_driver.py'] = files[
        'drivers/doubao_v1_driver.py'].replace('app_type = "doubao"',
                                               'app_type = "other"')
    report = svc._static_check(files, built['expects'])
    assert report['outcome'] == STATIC_FAILED
    assert any('app_type' in error for error in report['errors'])


def test_static_check_detects_missing_decorator():
    svc = _service()
    built = svc._build(_pair_args(), 'DEVICE_DRIVER')
    files = dict(built['files'])
    files['drivers/doubao_v1_driver.py'] = files[
        'drivers/doubao_v1_driver.py'].replace('@register_driver', '')
    report = svc._static_check(files, built['expects'])
    assert report['outcome'] == STATIC_FAILED
    assert any('register_driver' in error for error in report['errors'])


# ---------------------------------------------------------------- T2 与发布

def test_t2_unavailable_makes_claim_not_publishable():
    payload = _service().generate(_pair_args())
    assert payload['validation_report']['t2']['reason'] == \
        T2_RUNTIME_UNAVAILABLE
    assert payload['validation_report']['publishable'] is False


def test_t2_success_makes_claim_publishable_and_passes_code_hash():
    sandbox = FakeSandbox(succeeded=True)
    payload = _service(sandbox).generate(_pair_args())
    assert payload['validation_report']['t2']['outcome'] == 'SUCCEEDED'
    assert payload['validation_report']['publishable'] is True
    request = sandbox.requests[0]
    assert request.code_sha256 == payload['code_sha256']
    assert request.code_source
    assert [phase.name for phase in request.phases] == [
        'import_compile', 'unit_test', 'mock_contract', 'registry_resolve']


def test_t2_failure_blocks_publishable():
    sandbox = FakeSandbox(succeeded=False)
    payload = _service(sandbox).generate(_pair_args())
    assert payload['validation_report']['t2']['outcome'] == 'FAILED'
    assert payload['validation_report']['publishable'] is False


def test_publish_guard_default_disabled_and_requires_approval():
    svc = _service()
    payload = svc.generate(_pair_args())
    disabled = svc.publish_driver_proposal(
        payload, approval_id='a1', approval_status='APPROVED')
    assert disabled['published'] is False
    assert disabled['reason'] == PUBLISH_DISABLED

    enabled = _service(publish_enabled=True)
    payload = enabled.generate(_pair_args())
    # 未审批
    assert enabled.publish_driver_proposal(payload)['reason'] == \
        PUBLISH_APPROVAL_REQUIRED
    # 已审批但 T2 未通过（本机无 runsc）→ 不可发布
    assert enabled.publish_driver_proposal(
        payload, approval_id='a1', approval_status='APPROVED')['reason'] == \
        PUBLISH_NOT_PUBLISHABLE

    sandbox = FakeSandbox(succeeded=True)
    passing = _service(sandbox, publish_enabled=True)
    approved = passing.generate(_pair_args())
    # 通过验证 + 已批准：本期仍无注册表写入通道（不落地）
    result = passing.publish_driver_proposal(
        approved, approval_id='a1', approval_status='APPROVED')
    assert result['published'] is False
    assert result['reason'] == PUBLISH_UNAVAILABLE


# ---------------------------------------------------------------- 网关写路径

def test_gateway_executes_driver_propose_after_approval(tmp_path):
    from agent_service.application.run_worker import InlineRunExecutor
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.enums import RunStatus, ToolCallStatus
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.infrastructure.tools.registry_bridge import (
        RunCredentialRegistry, SharedToolRegistryBridge,
    )
    from tests.agent_write.helpers import (
        FakeLlm, OWNER_ID, TENANT_ID, decide, pending_approval, text_turn,
        tool_turn,
    )
    from tests.unit.int2451_agent_fakes import build_stack

    class NoRest:
        def __init__(self):
            self.calls = []

        def call(self, tool, arguments, **kwargs):  # pragma: no cover - 不应被调用
            self.calls.append((tool, arguments))
            raise AssertionError('driver_propose 不应回源 REST')

    rest = NoRest()
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry(),
        driver_proposals=_service())
    container, _engine, _sf = build_stack(
        tmp_path / 'driver.db',
        FakeLlm([tool_turn([ToolCallRequest(
            tool_call_id='drv1', name='driver_propose',
            arguments={'target_kind': 'DEVICE_DRIVER', 'app_type': 'doubao',
                       'version': 'v1', 'platform': 'ANDROID',
                       'capabilities': dict(CAPABILITIES),
                       'ui_trace': dict(UI_TRACE)})]),
                  text_turn('已生成提案')]),
        gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='driver',
        permissions=['*'])
    run, _created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='生成驱动提案', permissions=['*'])
    container.executor.submit(run.id)

    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.diff['kind'] == 'driver_proposal'
    assert approval.diff['target_kind'] == 'DEVICE_DRIVER'
    assert 'second_confirmation' not in approval.diff  # WRITE 不是 DESTRUCTIVE

    decide(container, approval.id, 'APPROVE')
    container.executor.submit(run.id)
    record = container.repositories['tool_calls'].find(run.id, 'drv1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    content = record.result['content']
    assert 'code_sha256' in content
    assert 'T2_RUNTIME_UNAVAILABLE' in content
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    assert rest.calls == []


def test_device_driver_t2_skips_vendor_contract_phase():
    sandbox = FakeSandbox(succeeded=True)
    _service(sandbox).generate({
        'target_kind': 'DEVICE_DRIVER', 'app_type': 'doubao',
        'version': 'v1', 'platform': 'ANDROID',
        'capabilities': dict(CAPABILITIES), 'ui_trace': dict(UI_TRACE),
    })
    names = [phase.name for phase in sandbox.requests[0].phases]
    assert names == ['import_compile', 'unit_test', 'registry_resolve']


def test_gateway_rejects_missing_materials_before_approval(tmp_path):
    """材料不齐在提案阶段就被拒绝：不建审批单、不回源。"""
    from agent_service.application.run_worker import InlineRunExecutor
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.enums import ToolCallStatus
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.infrastructure.tools.registry_bridge import (
        RunCredentialRegistry, SharedToolRegistryBridge,
    )
    from tests.agent_write.helpers import (
        FakeLlm, OWNER_ID, TENANT_ID, text_turn, tool_turn,
    )
    from tests.unit.int2451_agent_fakes import build_stack

    class NoRest:
        def call(self, tool, arguments, **kwargs):  # pragma: no cover
            raise AssertionError('不应回源')

    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=NoRest(),
        credentials=RunCredentialRegistry(),
        driver_proposals=_service())
    container, _engine, _sf = build_stack(
        tmp_path / 'driver_bad.db',
        FakeLlm([tool_turn([ToolCallRequest(
            tool_call_id='drv-bad', name='driver_propose',
            arguments={'target_kind': 'DEVICE_DRIVER', 'app_type': 'doubao',
                       'version': 'v1', 'platform': 'ANDROID',
                       'capabilities': dict(CAPABILITIES)})]),
                  text_turn('未生成')]),
        gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='driver-bad',
        permissions=['*'])
    run, _created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='生成驱动提案', permissions=['*'])
    container.executor.submit(run.id)

    assert container.repositories['approvals'].list_by_run(run.id) == []
    record = container.repositories['tool_calls'].find(run.id, 'drv-bad')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'INVALID_ARGUMENTS'
    assert 'ui_trace' in record.result['content']
