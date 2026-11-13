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
    """按工具名返回实测形状响应；非 GET 直接判失败（草案不允许写）。

    可注入分组 / 维度 / 播放设备 / 算法选项集合，用于覆盖存在性校验与分页。
    """

    def __init__(self, groups=None, dimensions=None, playback_devices=None,
                 algorithms=None):
        self.calls = []
        self.groups = list(fixtures.GROUP_LIST['data']['items']
                           if groups is None else groups)
        self.dimensions = set(fixtures.DIMENSION_IDS
                              if dimensions is None else dimensions)
        self.playback_devices = set(fixtures.PLAYBACK_DEVICE_IDS
                                    if playback_devices is None else playback_devices)
        self.algorithms = set(['voice_llm'] if algorithms is None else algorithms)

    @staticmethod
    def _envelope(data):
        return {'success': True, 'code': 0, 'message': 'Success', 'data': data}

    def _group_page(self, arguments):
        page = int(arguments.get('page') or 1)
        per_page = int(arguments.get('per_page') or 40)
        start = (page - 1) * per_page
        items = self.groups[start:start + per_page]
        total = len(self.groups)
        pages = (total + per_page - 1) // per_page if per_page else 0
        return self._envelope({'items': items, 'total': total, 'page': page,
                               'per_page': per_page, 'pages': pages})

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
        elif name == 'algorithm_options':
            payload = self._envelope({'algorithms': [
                {'value': value, 'name': value, 'group_id': None,
                 'group_name': None, 'icon': None}
                for value in sorted(self.algorithms)]})
        elif name == 'group_list':
            payload = self._group_page(arguments)
        elif name == 'evaluation_dimension_get':
            dim_id = arguments.get('dim_id')
            if dim_id in self.dimensions:
                payload = self._envelope(dict(fixtures.DIMENSION_ITEM, id=dim_id))
            else:
                payload = {'success': False, 'code': 404,
                           'message': '未找到评估维度'}
                return RestResult(status=404, payload=payload,
                                  text=json.dumps(payload, ensure_ascii=False))
        elif name == 'playback_device_get':
            device_id = arguments.get('device_id')
            if device_id in self.playback_devices:
                payload = self._envelope(
                    dict(fixtures.PLAYBACK_DEVICE_ITEM, id=device_id))
            else:
                payload = {'success': False, 'code': 203,
                           'message': '未找到播放设备'}
                return RestResult(status=400, payload=payload,
                                  text=json.dumps(payload, ensure_ascii=False))
        else:  # pragma: no cover - 草案只走这些只读工具
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
                     'group:read', 'evaluation:read', 'playback:read'),
        run_id='r1'):
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


def test_explicit_spl_overrides_annotation_in_pure_derivation():
    default = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL], device_type='physical')['drafts'][0]
    assert default['config']['rounds'][0]['audios'][0]['spl'] == 65.0

    overridden = testcase_tools.build_case_drafts(
        audios=[fixtures.AUDIO_DETAIL], device_type='physical', spl=70,
        playback_device_id=8)['drafts'][0]
    entry = overridden['config']['rounds'][0]['audios'][0]
    assert entry['spl'] == 70.0
    assert entry['playback_device_id'] == 8
    assert not any('未解析为 ID' in note for note in overridden['notes'])


def test_dimension_partition_rejects_invalid_items():
    """纯函数也不静默丢弃非法维度项（与网关校验同一口径）。"""
    for bad in ([0], ['abc'], [{}], [{'round_scope': 'multi'}]):
        with pytest.raises(ValueError):
            testcase_tools.partition_dimensions(bad, device_type='http_api')


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
    assert all(c['tool']['method'] == 'GET' for c in rest.calls)
    assert [c['tool']['name'] for c in rest.calls] == [
        'algorithm_options', 'algorithm_case_param_list',
        'evaluation_dimension_get', 'audio_get']
    assert rest.calls[0]['arguments'] == {}
    assert rest.calls[1]['arguments'] == {'algorithm_type': 'voice_llm'}
    assert rest.calls[2]['arguments'] == {'dim_id': 121}
    assert rest.calls[3]['arguments'] == {'audio_id': fixtures.AUDIO_DETAIL['id']}


def test_generate_validates_group_existence_before_deriving():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'group_id': 'no-such-group',
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert 'group_id' in result.content
    # 分组列表按页查全（不只查第一页），失败后不再回源音频
    assert [c['tool']['name'] for c in rest.calls] == ['group_list']
    assert rest.calls[0]['arguments'] == {
        'page': 1, 'per_page': rest.calls[0]['arguments']['per_page']}
    assert rest.calls[0]['arguments']['per_page'] > 40


def test_generate_finds_group_beyond_first_page():
    """分组数超过单页时，第二页的合法 ID 不能被误判为不存在（INT-2530）。"""
    filler = [dict(fixtures.GROUP_ITEM, id=f'group-{index}')
              for index in range(250)]
    target = fixtures.GROUP_ITEM['id']
    rest = FakeReadOnlyRest(groups=filler + [fixtures.GROUP_ITEM])
    result, _ = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'group_id': target,
    }, rest=rest)
    assert result.ok, result.content
    pages = [c['arguments'].get('page') for c in rest.calls
             if c['tool']['name'] == 'group_list']
    assert pages == [1, 2]


def test_generate_accepts_existing_group():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'group_id': fixtures.GROUP_ITEM['id'],
    })
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['drafts'][0]['group_id'] == fixtures.GROUP_ITEM['id']


def test_explicit_spl_and_device_override_annotation():
    """入参覆盖标注（P2-1）：显式 spl / 播放设备压过 segments 原值。"""
    result, _ = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'spl': 70,
        'playback_device_id': 8,
    })
    assert result.ok, result.content
    draft = json.loads(result.content)['drafts'][0]
    entry = draft['config']['rounds'][0]['audios'][0]
    assert entry['spl'] == 70.0          # 标注 segment 是 65
    assert entry['playback_device_id'] == 8
    assert entry['playback_device_name'] == '设备正面（0.5m+0°）'
    # 设备已解析出 ID，不再报告「未解析」
    assert not any('未解析为 ID' in note for note in draft['notes'])


def test_spl_and_device_fall_back_to_annotation_without_explicit_values():
    result, _ = generate({'audio_ids': [fixtures.AUDIO_DETAIL['id']]})
    assert result.ok, result.content
    entry = json.loads(result.content)['drafts'][0]['config']['rounds'][0]['audios'][0]
    assert entry['spl'] == 65.0
    assert 'playback_device_id' not in entry
    assert entry['playback_device_name'] == '设备正面（0.5m+0°）'


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
    # INT-2529/2531：数组元素同样要校验，非法项不得静默丢弃
    ({'audio_ids': [1], 'dimension_ids': [0]}, 'dimension_ids'),
    ({'audio_ids': [1], 'dimension_ids': ['abc']}, 'dimension_ids'),
    ({'audio_ids': [1], 'dimension_ids': [{'round_scope': 'multi'}]},
     'dimension_ids'),
    ({'audio_ids': [1], 'dimension_ids': [{'id': 121, 'round_scope': 'overall'}]},
     'round_scope'),
    ({'audio_ids': [1], 'dimension_ids': [{'id': 121, 'device_type': 'phone'}]},
     'device_type'),
    ({'audio_ids': [1], 'spl': -1}, 'spl'),
    ({'audio_ids': [1], 'spl': 'loud'}, 'spl'),
    ({'audio_ids': [1], 'playback_device_id': 0}, 'playback_device_id'),
])
def test_generate_rejects_invalid_arguments_before_rest(arguments, needle):
    result, rest = generate(arguments)
    assert result.error_code == INVALID_ARGUMENTS
    assert needle in result.content
    assert rest.calls == []


def test_generate_rejects_unknown_dimension_ids():
    """P2-2：维度必须存在（INT-2530），不存在显式失败而不是带进草案。"""
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'dimension_ids': [999999],
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert 'dimension_ids' in result.content and '999999' in result.content
    assert [c['tool']['name'] for c in rest.calls] == ['evaluation_dimension_get']


def test_generate_rejects_unknown_playback_device():
    """P2-4：播放设备必须存在（INT-2530）。"""
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'playback_device_id': 999999,
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert 'playback_device_id' in result.content
    assert [c['tool']['name'] for c in rest.calls] == ['playback_device_get']


def test_generate_rejects_unknown_algorithm_type():
    """P3：不存在的算法类型显式失败，不产出「未配置 case-params」的草案。"""
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'algorithm_type': 'no_such_algo',
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert 'algorithm_type' in result.content
    assert [c['tool']['name'] for c in rest.calls] == ['algorithm_options']


def test_generate_rejects_unknown_dimension_with_object_form():
    result, rest = generate({
        'audio_ids': [fixtures.AUDIO_DETAIL['id']],
        'dimension_ids': [{'id': 999999, 'round_scope': 'multi'}],
    })
    assert result.error_code == INVALID_ARGUMENTS
    assert '999999' in result.content
    assert [c['tool']['name'] for c in rest.calls] == ['evaluation_dimension_get']


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
    names = {'audio_get', 'algorithm_case_param_list', 'group_list',
             'algorithm_options', 'evaluation_dimension_get'}
    for name in names:
        tool = intent_tools._lookup_rest_tool(name)
        assert tool is not None, name
        assert tool['method'] == 'GET', name
    # 播放设备存在性校验走内部工具项（不进对外工具表），同样只读
    playback = testcase_tools.PLAYBACK_DEVICE_GET_TOOL
    assert playback['method'] == 'GET'
    assert playback['permissions'] == ['playback:read']
