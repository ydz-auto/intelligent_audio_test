# -*- coding: utf-8 -*-
"""INT-2491 App/API 接入 onboarding：Skill + 接入包 + 测量路径 + staging 冒烟。

验收锚点（卡面 10 条）：
1. App 入口产包齐全，capabilities 六组字段且指标与采集方式自洽；
2. API 入口产 adapter.py + config.yaml + mock 契约；
3. PAIR 成对交付，manifest 互相引用；
4. 测量路径不可测时明确拒绝 / 降级（只有 UI 文本 / 无音轨录屏不评 TTS）；
5. 同一输入重复生成同 hash / ref；
6. staging 冒烟至少一个可计算指标（mock 明示未覆盖，不假通过）；
7. 迭代 ≤3 轮且失败必须带新证据；
8. 安全：生成代码无凭证 / 无联网，未审批不写生产注册表；
9. 报告含证据 / 已知限制 / 回滚；
10. INT-2467 / INT-2453 回归由各自用例覆盖（本文件另测网关写路径）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json

import pytest

from agent_service.application.driver_proposal_service import (
    DriverProposalError, DriverProposalService, DriverProposalSettings,
)
from agent_service.infrastructure.onboarding.staging_store import (
    OnboardingStagingStore,
)
from shared.agent_tools import driver_tools, onboarding

CAPABILITIES = {
    'stimulus_modes': ['ACOUSTIC_PLAYBACK', 'TEXT_INPUT'],
    'capture_modes': ['UI_TEXT', 'PCM_CAPTURE'],
    'timing_points': ['PLAYBACK_START', 'PLAYBACK_END', 'FIRST_PARTIAL',
                      'FINAL_TEXT', 'REPLY_END'],
    'result_fields': ['success', 'message', 'asr', 'text', 'user_wav',
                      'ai_wav', 'start_ms', 'end_ms', 'latency_ms'],
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


def _app_args(**overrides):
    args = {
        'target_kind': 'DEVICE_DRIVER',
        'app_type': 'doubao', 'version': 'v1', 'platform': 'ANDROID',
        'display_name': '豆包 Android v1',
        'capabilities': dict(CAPABILITIES),
        'ui_trace': dict(UI_TRACE),
    }
    args.update(overrides)
    return args


def _api_args(**overrides):
    args = {
        'target_kind': 'API_ADAPTER',
        'api_id': 42, 'vendor': 'openai', 'protocol': 'realtime',
        'capabilities': dict(CAPABILITIES),
        'contract': dict(CONTRACT),
    }
    args.update(overrides)
    return args


def _pair_args(**overrides):
    args = _app_args(**dict(overrides, target_kind='PAIR'))
    args.update({key: value for key, value in overrides.items()
                 if key in ('api_id', 'vendor', 'protocol', 'contract')})
    args.setdefault('api_id', 42)
    args.setdefault('vendor', 'openai')
    args.setdefault('protocol', 'realtime')
    args.setdefault('contract', dict(CONTRACT))
    return args


def _service(tmp_path=None):
    staging = OnboardingStagingStore(str(tmp_path)) if tmp_path else None
    return DriverProposalService(
        settings=DriverProposalSettings(max_result_chars=200000,
                                        max_diff_chars=20000),
        staging=staging)


def _package_files(payload):
    entries = payload['onboarding']['items']
    files = {item['path'].split('/', 2)[-1]: item.get('content')
             for item in entries}
    return {path: content for path, content in files.items()
            if content is not None}


# ---------------------------------------------------------------- 1 App 入口

def test_app_entry_package_has_all_ten_items_and_consistent_capabilities():
    payload = _service().generate(_app_args())
    package = payload['onboarding']
    assert package['root'] == 'onboarding/doubao'
    assert package['entry'] == 'APP'
    files = _package_files(payload)
    for item in ('driver.py', 'config.yaml', 'capabilities.json',
                 'test_plan.md', 'ui_trace.json', 'smoke_case.json',
                 'manifest.json', 'onboarding_report.md'):
        assert item in files, item
    assert any(path.startswith('tests/') for path in files)

    capabilities = json.loads(files['capabilities.json'])
    assert set(capabilities) == set(driver_tools.CAPABILITY_REQUIRED_KEYS)
    # 指标与采集方式自洽：没有音频采集就不能声明 TTS 音质
    assert driver_tools.validate_capabilities(capabilities) is None
    assert 'TTS_QUALITY' in capabilities['supported_metrics']
    assert set(capabilities['capture_modes']) & {'PCM_CAPTURE', 'SCREEN_RECORD',
                                                'API_RESPONSE'}
    assert onboarding.validate_package_files(files, 'DEVICE_DRIVER') == []


def test_app_entry_does_not_claim_tts_quality_without_audio_capture():
    args = _app_args()
    args['capabilities'] = dict(
        CAPABILITIES, capture_modes=['UI_TEXT'],
        supported_metrics=['WER', 'CER'])
    files = _package_files(_service().generate(args))
    assert 'TTS_QUALITY' not in json.loads(files['capabilities.json'])[
        'supported_metrics']
    plan = json.loads(files['smoke_case.json'])
    assert 'TTS_QUALITY' not in plan['metrics']


# ---------------------------------------------------------------- 2 API 入口

def test_api_entry_package_contains_adapter_config_and_contract_tests():
    payload = _service().generate(_api_args())
    files = _package_files(payload)
    assert payload['onboarding']['root'] == 'onboarding/openai'
    assert payload['onboarding']['entry'] == 'API'
    for item in ('adapter.py', 'config.yaml', 'capabilities.json',
                 'test_plan.md', 'tests/test_contract_openai.py',
                 'smoke_case.json', 'manifest.json',
                 'onboarding_report.md'):
        assert item in files, item
    assert 'ui_trace.json' not in files
    assert onboarding.validate_package_files(files, 'API_ADAPTER') == []
    manifest = json.loads(files['manifest.json'])
    assert manifest['artifacts'][0]['registry_key'] == {
        'protocol': 'realtime', 'vendor': 'openai'}


# ---------------------------------------------------------------- 3 PAIR

def test_pair_package_keeps_both_artifacts_and_cross_references():
    payload = _service().generate(_pair_args())
    files = _package_files(payload)
    assert payload['onboarding']['entry'] == 'PAIR'
    assert 'driver.py' in files and 'adapter.py' in files
    manifest = json.loads(files['manifest.json'])
    by_kind = {item['artifact_kind']: item for item in manifest['artifacts']}
    assert by_kind['DEVICE_DRIVER']['pair_with'] == 'adapter.py'
    assert by_kind['API_ADAPTER']['pair_with'] == 'driver.py'
    assert onboarding.validate_package_files(files, 'PAIR') == []


# ---------------------------------------------------------------- 4 测量路径

def test_measurement_rejects_tts_with_ui_text_only():
    args = _app_args(measurement_profile={'test_goals': ['TTS']})
    args['capabilities'] = dict(CAPABILITIES, capture_modes=['UI_TEXT'],
                                supported_metrics=['WER'])
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    message = str(exc.value)
    assert 'TTS' in message and '降级' in message


def test_measurement_rejects_screen_record_without_audio_for_tts():
    capabilities = {
        'stimulus_modes': ['ACOUSTIC_PLAYBACK'],
        'capture_modes': ['SCREEN_RECORD'],
        'timing_points': ['PLAYBACK_START', 'PLAYBACK_END', 'FIRST_FRAME',
                          'REPLY_END'],
        'result_fields': ['success', 'asr', 'wav_path', 'start_ms', 'end_ms'],
        'supported_metrics': ['TTS_QUALITY', 'WER'],
        'limitations': [],
    }
    args = _app_args(
        capabilities=capabilities,
        measurement_profile={
            'test_goals': ['TTS'],
            'capture_details': {'SCREEN_RECORD': {'audio': False}},
        })
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    message = str(exc.value)
    assert '音轨' in message and 'TTS' in message


def test_measurement_rejects_asr_from_audio_without_recognition_step():
    capabilities = {
        'stimulus_modes': ['ACOUSTIC_PLAYBACK'],
        'capture_modes': ['SCREEN_RECORD'],
        'timing_points': ['PLAYBACK_START', 'FIRST_FRAME', 'FINAL_TEXT'],
        'result_fields': ['success', 'asr', 'wav_path', 'start_ms', 'end_ms'],
        'supported_metrics': ['WER', 'TTS_QUALITY'],
        'limitations': [],
    }
    args = _app_args(capabilities=capabilities,
                     measurement_profile={'test_goals': ['ASR']})
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    assert '识别步骤' in str(exc.value)
    # 补识别步骤后放行
    args['measurement_profile'] = {'test_goals': ['ASR'],
                                   'extra_recognition': True}
    payload = _service().generate(args)
    assert 'ASR' in payload['measurement_plan']['test_goals']


# ---------------------------------------------------------------- 5 可复现

def test_same_input_produces_same_hash_and_package_ref():
    svc = _service()
    first = svc.generate(_pair_args())
    second = svc.generate(_pair_args())
    assert first['code_sha256'] == second['code_sha256']
    assert first['onboarding']['driver_ref'] == second['onboarding']['driver_ref']
    changed = _pair_args()
    changed['capabilities'] = dict(CAPABILITIES, limitations=['只能取 UI 文本'])
    third = svc.generate(changed)
    assert third['onboarding']['driver_ref'] != first['onboarding']['driver_ref']


# ---------------------------------------------------------------- 6 staging 冒烟

def test_staging_smoke_mock_collects_metric_and_lists_uncovered(tmp_path):
    svc = _service(tmp_path)
    payload = svc.generate(_app_args())
    ref = payload['onboarding']['driver_ref']
    result = svc.staging_smoke({
        'driver_ref': ref,
        'case_ref': payload['onboarding']['case_ref'],
    })
    assert result['outcome'] == 'MOCK_PASSED'
    assert result['computable_metrics']
    assert set(result['result_fields']) >= {'success', 'asr'}
    assert result['uncovered']  # 真机未覆盖项必须显式列出
    assert any('真机' in item for item in result['uncovered'])


def test_staging_smoke_with_device_is_not_reported_as_passed(tmp_path):
    svc = _service(tmp_path)
    payload = svc.generate(_app_args())
    result = svc.staging_smoke({
        'driver_ref': payload['onboarding']['driver_ref'],
        'case_ref': payload['onboarding']['case_ref'],
        'device_id': 7,
    })
    assert result['outcome'] == 'NOT_EXECUTED'
    assert result['reason'] == 'DEVICE_EXECUTOR_UNAVAILABLE'
    assert result['result_fields'] == {}
    assert result['uncovered']


def test_staging_smoke_unknown_ref_fails_closed(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.staging_smoke({'driver_ref': 'onboarding-' + '0' * 16,
                           'case_ref': 'missing'})


# ---------------------------------------------------------------- 7 迭代边界

def test_iteration_beyond_three_rounds_must_hand_back():
    rounds = [
        {'round': index, 'outcome': 'FAILED', 'evidence': {'log': f'l{index}'}}
        for index in range(1, 4)
    ]
    result = onboarding.evaluate_iterations(rounds)
    assert result['handback_required'] is True
    assert result['ok'] is False
    assert '交回诊断' in result['error']


def test_iteration_requires_new_evidence():
    same = {'log': 'same'}
    result = onboarding.evaluate_iterations([
        {'round': 1, 'outcome': 'FAILED', 'evidence': same},
        {'round': 2, 'outcome': 'FAILED', 'evidence': dict(same)},
    ])
    assert result['ok'] is False
    assert '新证据' in result['error']


def test_generate_rejects_invalid_iteration_history():
    args = _app_args(iterations=[
        {'round': 1, 'outcome': 'FAILED', 'evidence': {'log': 'a'}},
        {'round': 2, 'outcome': 'FAILED', 'evidence': {'log': 'a'}},
    ])
    with pytest.raises(DriverProposalError) as exc:
        _service().generate(args)
    assert '新证据' in str(exc.value)


# ---------------------------------------------------------------- 8 安全

def test_generated_package_code_has_no_credentials_or_network():
    payload = _service().generate(_pair_args())
    files = _package_files(payload)
    text = files['driver.py'] + files['adapter.py']
    for forbidden in ('requests', 'httpx', 'socket', 'urllib', 'grpc'):
        assert f'import {forbidden}' not in text
    assert 'sk-' not in text and 'AKIA' not in text
    assert onboarding.scan_generated_code(files) == []


def test_publish_stays_blocked_without_approval():
    svc = _service()
    payload = svc.generate(_app_args())
    result = svc.publish_driver_proposal(payload, approval_id='a1',
                                         approval_status='APPROVED')
    assert result['published'] is False


# ---------------------------------------------------------------- 9 报告

def test_report_contains_evidence_limitations_and_rollback():
    payload = _service().generate(_app_args())
    report = _package_files(payload)['onboarding_report.md']
    for section in ('证据', '已知限制', '回滚'):
        assert section in report
    assert 'ui_trace.json' in report


# ---------------------------------------------------------------- Skill 契约

SKILL_NAME = 'app-api-onboarding'
SKILL_TOOLS = {'ui_tree', 'ui_action', 'api_spec', 'driver_propose',
               'device_query', 'testcase_generate', 'task_run', 'tool_search'}


def _skill_registry():
    from agent_service.application.skill_registry import SkillRegistry
    from agent_service.infrastructure.skill.fs_skill_repository import (
        FsSkillRepository,
    )
    from shared.agent_tools import intent_tools
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    return SkillRegistry(
        FsSkillRepository(os.path.join(root, 'skills')),
        known_tools=lambda: [tool.name for tool in intent_tools.INTENT_TOOLS],
    ).load()


def test_skill_loads_with_required_sections_and_tools():
    registry = _skill_registry()
    skill = registry.get(SKILL_NAME)
    assert skill is not None
    assert skill.body_line_count <= 500
    assert '## Gotchas' in skill.body and '## 验收' in skill.body
    assert set(skill.meta.allowed_tools) == SKILL_TOOLS
    for name in skill.meta.allowed_tools:
        assert intent_enabled(name), name


def intent_enabled(name):
    from shared.agent_tools import intent_tools
    tool = intent_tools.INTENT_TOOL_BY_NAME[name]
    return tool.enabled


def test_skill_body_covers_entries_measurement_package_and_staging():
    registry = _skill_registry()
    body = registry.get(SKILL_NAME).body
    for keyword in ('APP', 'API', 'PAIR', '受理', '发现', '计划', '生成', '验证',
                    '迭代', '交付', 'measurement_profile', 'capabilities.json',
                    'ui_trace.json', 'smoke_case.json', 'manifest.json',
                    'onboarding_report.md', 'task_run(mode=SMOKE)',
                    'staging', '3 轮', '不写生产注册表'):
        assert keyword in body, keyword


# ---------------------------------------------------------------- 注册表 resolve

def test_package_resolves_driver_and_adapter_registry(tmp_path):
    """包内 driver.py / adapter.py 按注册键 resolve（API + App + PAIR）。"""
    import subprocess
    import sys

    payload = _service().generate(_pair_args())
    files = _package_files(payload)
    root = tmp_path / 'onboarding' / 'doubao_openai'
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='\n')
    script = (
        'import os, sys\n'
        'root = sys.argv[1]\n'
        'sys.path.insert(0, os.path.join(root, "tests"))\n'
        'import _platform_stubs\n'
        'from _platform_stubs import DRIVERS, VENDOR_ADAPTERS\n'
        'sys.path.insert(0, root)\n'
        'import driver, adapter\n'
        'assert DRIVERS[("doubao", "v1", "ANDROID")] is driver.'
        'DoubaoV1Driver\n'
        'assert VENDOR_ADAPTERS[("realtime", "openai")] is adapter.'
        'OpenaiRealtimeAdapter\n'
        'print("resolve: OK")\n'
    )
    completed = subprocess.run(
        [sys.executable, '-c', script, str(root)],
        cwd=str(root), capture_output=True, text=True, encoding='utf-8')
    assert completed.returncode == 0, completed.stderr
    assert 'resolve: OK' in completed.stdout


# ---------------------------------------------------------------- 10 网关写路径

def test_task_run_mode_smoke_executes_staging_package_after_approval(tmp_path):
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
        def call(self, tool, arguments, **kwargs):  # pragma: no cover
            raise AssertionError('staging 冒烟不应回源 REST')

    service = _service(tmp_path / 'staging')
    payload = service.generate(_app_args())
    driver_ref = payload['onboarding']['driver_ref']
    case_ref = payload['onboarding']['case_ref']

    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=NoRest(),
        credentials=RunCredentialRegistry(),
        driver_proposals=service)
    container, _engine, _sf = build_stack(
        tmp_path / 'smoke.db',
        FakeLlm([tool_turn([ToolCallRequest(
            tool_call_id='smk1', name='task_run',
            arguments={'mode': 'SMOKE', 'driver_ref': driver_ref,
                       'case_ref': case_ref})]),
                  text_turn('冒烟完成')]),
        gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='smoke',
        permissions=['*'])
    run, _created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='跑 staging 冒烟', permissions=['*'])
    container.executor.submit(run.id)

    approval = pending_approval(container, run.id)
    assert approval.diff['kind'] == 'staging_smoke'
    assert approval.diff['writes_production_registry'] is False
    decide(container, approval.id, 'APPROVE')
    container.executor.submit(run.id)
    record = container.repositories['tool_calls'].find(run.id, 'smk1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert 'MOCK_PASSED' in record.result['content']
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


def test_task_run_mode_smoke_requires_driver_and_case_refs():
    from shared.agent_tools import intent_tools
    tool = intent_tools.INTENT_TOOL_BY_NAME['task_run']
    assert intent_tools.validate_arguments(
        tool.parameters, {'mode': 'SMOKE'}) is None
    _tool, _merged, error = intent_tools.resolve_rest_call(
        'task_run', {'mode': 'SMOKE'})
    assert error and 'driver_ref' in error
    assert intent_tools.permissions_for(
        'task_run', {'mode': 'SMOKE'}) == ('device:control',)
