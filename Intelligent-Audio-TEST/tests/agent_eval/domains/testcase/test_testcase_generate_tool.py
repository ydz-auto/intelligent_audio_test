# -*- coding: utf-8 -*-
"""INT-2460 标注 → 用例草案（testcase_generate，只读推导）。

验收锚点（卡面 1、4）：
1. 10 条域任务走通的同时，草案生成**不写库**（只回源 GET，`persisted=false`）；
4. 不编造用例 ID / 轮次数：轮次号取自标注 `round_number`，草案没有用例 ID。
"""
import json

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND, SharedToolGateway,
)
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import intent_tools, testcase_tools
from tests.agent_eval.domains.testcase import fixtures


class FakeReadOnlyRest:
    """按工具名返回实测形状响应；非 GET 直接判失败（草案不允许写）。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        assert tool['method'] == 'GET', f'草案生成调用了写接口：{tool["name"]}'
        name = tool['name']
        if name == 'audio_get':
            if arguments.get('audio_id') != fixtures.AUDIO_DETAIL['id']:
                payload = {'success': False, 'code': 404,
                           'message': '未找到音频'}
                return RestResult(status=404, payload=payload,
                                  text=json.dumps(payload, ensure_ascii=False))
            payload = fixtures.AUDIO_DETAIL_ENVELOPE
        elif name == 'algorithm_case_param_list':
            payload = fixtures.CASE_PARAM_LIST
        elif name == 'group_list':
            payload = fixtures.GROUP_LIST
        else:  # pragma: no cover - 草案只走这三类只读工具
            payload = {'success': True, 'data': {}}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeReadOnlyRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('testcase:read', 'audio:read', 'algorithm:read',
                     'group:read'), run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name='testcase_generate',
                           arguments=arguments)


def generate(arguments, **kwargs):
    rest = kwargs.pop('rest', None) or FakeReadOnlyRest()
    result = make_gateway(rest).execute(call(arguments), kwargs.pop('context', None) or ctx())
    return result, rest


# ---------------------------------------------------------------- 注册口径

def test_testcase_generate_is_enabled_readonly_local():
    tool = intent_tools.INTENT_TOOL_BY_NAME['testcase_generate']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'local'
    assert tool.permissions == ('testcase:read',)
    assert 'testcase_generate' in intent_tools.ENABLED_TOOLS
    assert tool.parameters['required'] == ['audio_ids']


def test_generate_schema_enums_match_fact_sources():
    from shared.models.common_enums import DeviceType

    properties = intent_tools.INTENT_TOOL_BY_NAME[
        'testcase_generate'].parameters['properties']
    assert set(properties['device_type']['enum']) == {
        item.value for item in DeviceType}
    assert set(properties['dimension_round_scope']['enum']) == set(
        testcase_tools.ROUND_SCOPES)


def test_generate_is_not_a_rest_action():
    """本地推导工具不进 REST 动作表，避免被当成 1:1 接口透传。"""
    assert 'testcase_generate' not in intent_tools._REST_ACTION_MAP


# ---------------------------------------------------------------- 纯函数推导

def test_draft_round_comes_from_annotation_not_invented():
    result = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL],
        case_params=fixtures.CASE_PARAMS,
        algorithm_type='voice_llm',
        device_type='http_api',
    )
    draft = result['drafts'][0]
    rounds = draft['config']['rounds']
    assert [item['round_number'] for item in rounds] == [2]
    assert draft['derived_from']['rounds'] == [2]
    # 草案没有用例 ID（未落库），名字沿用创建服务的 naming
    assert 'id' not in draft
    assert draft['name'] == f"测试用例_{fixtures.AUDIO_DETAIL['name']}"


def test_draft_audio_entry_carries_annotation_spl_and_device_name():
    result = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL], device_type='physical',
        algorithm_type='voice_llm')
    entry = result['drafts'][0]['config']['rounds'][0]['audios'][0]
    assert entry['audio_id'] == fixtures.AUDIO_DETAIL['id']
    assert entry['spl'] == 65.0
    assert entry['play_order'] == 0
    # 名 → ID 解析属写侧：草案保留名字并注明未解析，不伪造 ID
    assert entry['playback_device_name'] == '设备正面（0.5m+0°）'
    assert 'playback_device_id' not in entry
    assert any('未解析为 ID' in note
               for note in result['drafts'][0]['notes'])


def test_draft_case_params_follow_scope_and_annotation_code():
    # http_api：common 作用域参数参与（is_reject），physical 专属的 interferers 不参与
    common_only = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL], case_params=fixtures.CASE_PARAMS,
        algorithm_type='voice_llm', device_type='http_api')
    params = common_only['drafts'][0]['algorithm_params'][0]
    assert params['round_number'] == 2
    codes = {p['field_code']: p['field_value'] for p in params['params']}
    assert codes.get('is_reject') is True
    assert 'interferers' not in codes

    # 没有 algorithm_type 就不抽参数（口径与创建服务一致）
    no_algo = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL], case_params=fixtures.CASE_PARAMS,
        device_type='http_api')
    assert no_algo['drafts'][0]['algorithm_params'] is None


def test_dimension_partition_follows_round_scope_and_device_type():
    per_round, overall = testcase_tools.partition_dimensions(
        [{'id': 121, 'round_scope': 'single'},
         {'id': 122, 'round_scope': 'multi'},
         {'id': 123, 'device_type': 'physical'}],
        device_type='http_api', default_round_scope='single')
    assert [dim['id'] for dim in per_round] == [121]
    assert [dim['id'] for dim in overall] == [122]

    drafts = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL],
        dimensions=[{'id': 121}, {'id': 122, 'round_scope': 'multi'}],
        device_type='http_api')['drafts'][0]
    assert [dim['id'] for dim in drafts['config']['rounds'][0]['evaluation']['dimensions']] == [121]
    assert [dim['id'] for dim in drafts['config']['dimensions']] == [122]


def test_audio_without_annotations_falls_back_to_round_one():
    audio = dict(fixtures.AUDIO_DETAIL, annotations=[])
    draft = testcase_tools.build_case_drafts(
        audios=[audio], device_type='http_api')['drafts'][0]
    assert [item['round_number'] for item in draft['config']['rounds']] == [1]
    assert draft['algorithm_params'] is None


def test_annotation_field_path_extraction_reuses_segments_convention():
    data = {'segments': [{'correct_answer': '枪声'},
                         {'correct_answer': '关门声', 'spl': 70}]}
    assert testcase_tools.extract_annotation_value(
        data, 'correct_answer') == ['枪声', '关门声']
    assert testcase_tools.extract_annotation_value(
        data, 'segments[].spl') == 70
    assert testcase_tools.extract_annotation_value(data, 'missing') is None


# ---------------------------------------------------------------- 网关端到端

def test_generate_through_gateway_is_read_only_and_not_persisted():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'algorithm_type': 'voice_llm',
        'dimension_ids': [121],
    })
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['mode'] == 'draft'
    assert payload['persisted'] is False
    assert payload['writes'] == 0
    assert len(payload['drafts']) == 1
    assert payload['drafts'][0]['config']['rounds']

    # 只回源 GET，且没有多余的写调用
    assert [c['tool']['method'] for c in rest.calls] == ['GET', 'GET']
    assert [c['tool']['name'] for c in rest.calls] == [
        'algorithm_case_param_list', 'audio_get']
    assert rest.calls[0]['arguments'] == {'algorithm_type': 'voice_llm'}
    assert rest.calls[1]['arguments'] == {'audio_id': fixtures.AUDIO_DETAIL['id']}


def test_generate_validates_group_existence_before_deriving():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'group_id': 'no-such-group',
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert 'group_id' in result.content
    names = [c['tool']['name'] for c in rest.calls]
    assert names == ['group_list']  # 没有继续回源音频


def test_generate_accepts_existing_group():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'group_id': fixtures.GROUP_ITEM['id'],
    })
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['drafts'][0]['group_id'] == fixtures.GROUP_ITEM['id']


def test_generate_fails_whole_batch_on_missing_audio():
    result, rest = generate({'audio_ids': [999999]})
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert [c['tool']['name'] for c in rest.calls] == ['audio_get']


@pytest.mark.parametrize('arguments,needle', [
    ({'audio_ids': []}, 'audio_ids'),
    ({'audio_ids': [0]}, '正整数'),
    ({'audio_ids': ['x']}, '正整数'),
    ({'audio_ids': list(range(1, 22))}, '最多'),
    ({'audio_ids': [1], 'device_type': 'phone'}, 'device_type'),
    ({'audio_ids': [1], 'dimension_round_scope': 'overall'},
     'dimension_round_scope'),
])
def test_generate_rejects_invalid_arguments_before_rest(arguments, needle):
    result, rest = generate(arguments)
    assert result.error_code == INVALID_ARGUMENTS
    assert needle in result.content
    assert rest.calls == []


def test_generate_requires_testcase_read_permission():
    result, rest = generate({'audio_ids': [1]},
                            context=ctx(permissions=('audio:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert rest.calls == []


def test_generate_does_not_swallow_upstream_failure():
    class BrokenRest(FakeReadOnlyRest):
        def call(self, tool, arguments, **kwargs):
            self.calls.append({'tool': tool, 'arguments': arguments})
            assert tool['method'] == 'GET'
            return RestResult(status=500, payload={'message': 'boom'}, text='boom')

    result, rest = generate(
        {'audio_ids': [fixtures.AUDIO_DETAIL['id']], 'algorithm_type': 'voice_llm'},
        rest=BrokenRest())
    assert not result.ok
    assert result.error_code == 'UPSTREAM_ERROR'
    assert '500' in result.content


def test_gateway_exposes_generate_as_read():
    gateway = make_gateway()
    assert gateway.risk_of('testcase_generate') is ToolRisk.READ
    descriptor = gateway.describe(['testcase_generate'])[0]
    assert descriptor.enabled is True


# ---------------------------------------------------------------- 无落库证据

def test_generate_never_targets_a_write_route():
    """所有可被草案生成回源的工具都必须是 GET（静态保证不写库）。"""
    names = {'audio_get', 'algorithm_case_param_list', 'group_list'}
    for name in names:
        tool = intent_tools._lookup_rest_tool(name)
        assert tool is not None, name
        assert tool['method'] == 'GET', name
