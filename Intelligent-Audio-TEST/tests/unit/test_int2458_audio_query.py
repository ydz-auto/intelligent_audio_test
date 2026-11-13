# -*- coding: utf-8 -*-
"""INT-2458 M1 音频域只读：audio_query 意图工具 + audio-import Skill + golden tasks。

验收锚点（卡面可测标准 1~5）：
1. 列表 / 详情 / 按 MD5 / 目录树 / 特征 / 质量等 9 个动作全部可解析到真实 REST；
2. 返回字段口径以真实 REST 为准（MCP 映射与 REST 字段逐字一致，见 by_md5）；
   ``by_ids`` 为宿主语境通道，Agent 侧不暴露（INT-2530，见文件末尾用例）；
3. Skill 触发数据（tests/agent_eval/domains/audio）覆盖全部动作，统一评测归 m1-08；
4. 越权 / 不存在资源返回普通拒绝文本，不泄漏存在性；
5. 每次调用落 agent_tool_call（在 audit 用例与 INT-2453 通用审计用例中覆盖）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.skill_registry import SkillRegistry
from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND, SharedToolGateway,
    TOOL_NOT_ENABLED, UNKNOWN_TOOL,
)
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import SkillIssueSeverity, ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import intent_tools, mcp_registry
from shared.agent_tools.intent_tools import (
    ACTION_REQUIRED, AUDIO_QUERY_ACTIONS, AUDIO_QUERY_PARAMS, ENABLED_TOOLS,
    INTENT_TOOL_BY_NAME, INTENT_TOOLS,
)
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, text_turn, tool_turn,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')
AUDIO_GOLDEN = os.path.join(
    PROJECT_ROOT, 'tests', 'agent_eval', 'domains', 'audio',
    'golden_tasks.json')

AUDIO_READ_TOOLS = frozenset(AUDIO_QUERY_ACTIONS.values())
AUDIO_WRITE_PERMISSIONS = frozenset({
    'audio:upload', 'audio:update', 'audio:delete', 'audio:convert'})


# ---------------------------------------------------------------- 注册表

def test_audio_query_enabled_with_nine_actions():
    tool = INTENT_TOOL_BY_NAME['audio_query']
    assert tool.enabled is True and tool.kind == 'intent_rest'
    assert tool.risk == 'READ'
    assert 'audio_query' in ENABLED_TOOLS
    enum = tool.parameters['properties']['action']['enum']
    assert enum == list(AUDIO_QUERY_ACTIONS)
    assert len(set(enum)) == 9
    assert 'by_ids' not in enum


def test_action_mappings_are_existing_audio_readonly_mcp_tools():
    for action, mcp_name in AUDIO_QUERY_ACTIONS.items():
        assert mcp_name.startswith('audio_'), action
        mcp = mcp_registry.get_tool(mcp_name)
        assert mcp is not None, f'{action} -> {mcp_name} 不存在'
        assert mcp['path'].startswith('/api/v1/audios'), mcp_name
        assert not (set(mcp['permissions']) & AUDIO_WRITE_PERMISSIONS), mcp_name
        assert set(mcp['permissions']) <= {'audio:read', 'audio:folder'}


def test_action_required_fields_match_rest_contract():
    assert ACTION_REQUIRED['audio_query'] == {
        'detail': ('audio_id',),
        'by_md5': ('md5_list',),
        'features': ('audio_id',),
        'quality': ('audio_id',),
        'algorithms': ('audio_id',),
        'playback_history': ('audio_id',),
    }
    for params in ACTION_REQUIRED['audio_query'].values():
        for name in params:
            assert name in INTENT_TOOL_BY_NAME[
                'audio_query'].parameters['properties']


def test_by_md5_mcp_schema_uses_rest_body_field():
    """真实 REST 读 body.md5_list；MCP Schema 不得再声明无效的 md5 单值。"""
    schema = mcp_registry.get_tool('audio_get_by_md5')['inputSchema']
    assert 'md5' not in schema['properties']
    assert schema['properties']['md5_list']['type'] == 'array'
    assert schema['required'] == ['md5_list']


def test_audio_list_and_playback_history_expose_real_filters():
    """只暴露服务端真正生效的过滤参数（folder 未实现，不得声明）。"""
    listing = mcp_registry.get_tool('audio_list')
    for name in ('format', 'audio_type', 'sample_rate', 'duration',
                 'tags', 'direction', 'algorithm_type', 'visibility'):
        assert name in listing['inputSchema']['properties'], name
        assert name in listing['query_params'], name
    assert 'folder' not in listing['inputSchema']['properties']
    assert 'folder' not in listing['query_params']
    assert listing['inputSchema']['properties']['duration']['enum'] == \
        ['short', 'medium', 'long']
    history = mcp_registry.get_tool('audio_playback_history')
    assert history['inputSchema']['properties']['page']['type'] == 'integer'
    assert history['query_params'] == ['page', 'per_page']


def test_mcp_tool_count_unchanged():
    assert len(mcp_registry.TOOLS) == 205


# ---------------------------------------------------------------- 参数解析

def _resolve(action, **kwargs):
    return intent_tools.resolve_rest_call(
        'audio_query', {'action': action, **kwargs})


def test_resolve_list_builds_query_string_with_filters():
    tool, merged, error = _resolve(
        'list', page=2, per_page=20, format='wav', tags=['noise', 'dry'])
    assert error is None and tool['name'] == 'audio_list'
    assert merged == {'page': 2, 'per_page': 20, 'format': 'wav',
                      'tags': ['noise', 'dry']}
    path = mcp_registry.build_path(tool, merged)
    assert path.startswith('/api/v1/audios?')
    assert 'page=2' in path and 'format=wav' in path
    assert path.count('tags=') == 2  # doseq：多标签不压成单值


def test_resolve_detail_and_path_param():
    tool, merged, error = _resolve('detail', audio_id=12)
    assert error is None and tool['name'] == 'audio_get'
    assert mcp_registry.build_path(tool, merged) == '/api/v1/audios/12'


def test_by_ids_action_is_not_callable():
    """INT-2530：by_ids 是宿主语境批量读通道，Agent 侧口径上不可调用。"""
    assert 'by_ids' not in INTENT_TOOL_BY_NAME[
        'audio_query'].parameters['properties']['action']['enum']
    # 动作表 / 参数表里都不再有它
    assert 'by_ids' not in AUDIO_QUERY_ACTIONS
    assert 'by_ids' not in ACTION_REQUIRED['audio_query']
    assert 'by_ids' not in AUDIO_QUERY_PARAMS
    assert 'ids' not in INTENT_TOOL_BY_NAME['audio_query'].parameters['properties']
    # 直调解析层也被拒（模型可能凭记忆编 action）
    tool, merged, error = _resolve('by_ids', ids=[11, 12, 13])
    assert tool is None and merged is None
    assert error is not None and '取值必须是' in error


def test_by_ids_mcp_tool_not_exposed_to_agent_channel():
    """INT-2530：MCP 长尾同名工具也不得经 tool_search / 直呼回到 Agent 通道。

    REST ``/api/v1/audios/by-ids`` 与对外 MCP 注册表保持不变（宿主语境），
    只是 Agent 侧的索引 / 解析层把它排除。
    """
    from shared.agent_tools import search
    # 注册表本身仍在（REST / 外部 MCP surface 不变）
    assert mcp_registry.get_tool('audio_get_by_ids') is not None
    # tool_search 不返回
    for query in ('按 ID 批量获取音频', 'audio_get_by_ids', '批量 音频'):
        names = [t['name'] for t in
                 search.search(query, ['*'], limit=30)['tools']]
        assert 'audio_get_by_ids' not in names, (query, names)
    assert 'audio_get_by_ids' not in intent_tools.TOOL_INDEX_BY_NAME
    # platform_contract 精确命中也不返回它的 Schema
    result = intent_tools.platform_contract('audio_get_by_ids')
    assert result.get('tool') is None or \
        result['tool'].get('name') != 'audio_get_by_ids'
    # 直呼被解析层拒绝
    tool, merged, error = intent_tools.resolve_rest_call(
        'audio_get_by_ids', {'ids': [11]})
    assert tool is None and error is not None
    assert '不在 Agent 可用通道内' in error


def test_resolve_by_md5_posts_md5_list_body():
    tool, merged, error = _resolve('by_md5', md5_list=['abc'])
    assert error is None and tool['name'] == 'audio_get_by_md5'
    assert mcp_registry.build_body(tool, merged) == {'md5_list': ['abc']}


def test_resolve_folder_tree_posts_flat_filters():
    tool, merged, error = _resolve(
        'folder_tree', parent_path='test_data', depth=2, keyword='noise')
    assert error is None and tool['name'] == 'audio_folder_tree'
    body = mcp_registry.build_body(tool, merged)
    assert body == {'parent_path': 'test_data', 'depth': 2, 'keyword': 'noise'}


def test_resolve_playback_history_query_params():
    tool, merged, error = _resolve('playback_history', audio_id=12,
                                   page=2, per_page=5)
    assert error is None and tool['name'] == 'audio_playback_history'
    assert mcp_registry.build_path(tool, merged) == \
        '/api/v1/audios/12/playback-history?page=2&per_page=5'


# ------------------------------------------------ 参数口径（复核打回 1~4）

def test_audio_query_schema_has_no_unimplemented_folder_filter():
    schema = INTENT_TOOL_BY_NAME['audio_query'].parameters
    assert 'folder' not in schema['properties']
    _, _, error = _resolve('list', folder='环境理解')
    assert error is not None and '不支持参数' in error


def test_unsupported_param_per_action_is_rejected():
    """动作不支持的可选参数不能静默透传（服务端会静默忽略过滤条件）。"""
    _, _, error = _resolve('detail', audio_id=1, page=2)
    assert error is not None and '不支持参数' in error
    _, _, error = _resolve('folder_tree', depth=1, visibility='shared')
    assert error is not None and '不支持参数' in error
    # 必填参数不受「动作可选参数」限制
    assert _resolve('playback_history', audio_id=1, page=2)[2] is None


def test_sample_rate_normalized_to_hz_for_folder_tree():
    for value, expected in [(48000, 48000), ('48000', 48000), ('48 Hz', 48),
                            (44100, 44100), ('44100', 44100)]:
        tool, merged, error = _resolve('folder_tree', sample_rate=value)
        assert error is None, value
        assert mcp_registry.build_body(tool, merged) == {
            'sample_rate': expected}, value


def test_sample_rate_khz_string_normalized_for_folder_tree():
    for value in ('48', '48 kHz', '48kHz', ' 48 kHz '):
        tool, merged, error = _resolve('folder_tree', sample_rate=value)
        assert error is None, value
        assert mcp_registry.build_body(tool, merged) == {
            'sample_rate': 48000}, value


def test_sample_rate_normalized_to_khz_for_list():
    """列表 REST 只认 kHz 数值（"48 kHz" → 48）；工具层统一归一后再发。"""
    for value in (48000, '48000', '48 kHz', '48', 48):
        tool, merged, error = _resolve('list', sample_rate=value)
        assert error is None, value
        path = mcp_registry.build_path(tool, merged)
        assert 'sample_rate=48' in path, (value, path)


def test_sample_rate_unparsable_is_explicit_error():
    _, _, error = _resolve('list', sample_rate='高采样率')
    assert error is not None and '无法解析' in error


def test_duration_must_be_bucket():
    schema = INTENT_TOOL_BY_NAME['audio_query'].parameters
    assert schema['properties']['duration']['enum'] == [
        'short', 'medium', 'long']
    for bucket in ('short', 'medium', 'long'):
        assert _resolve('list', duration=bucket)[2] is None
    assert '取值必须是' in intent_tools.validate_arguments(
        schema, {'action': 'list', 'duration': '0-60'})
    # 绕过 Schema 直调解析层也要拦住（服务端会静默忽略区间写法）
    _, _, error = _resolve('list', duration='0-60')
    assert error is not None and '档位' in error


def test_list_tags_only_accept_strings():
    tool, merged, error = _resolve('list', tags=['noise', 'dry'])
    assert error is None
    assert 'tags=noise' in mcp_registry.build_path(tool, merged)

    _, _, error = _resolve('list', tags=[{'name': 'noise', 'mode': 'or'}])
    assert error is not None and '只支持字符串' in error


def test_folder_tree_tags_accept_or_objects():
    tool, merged, error = _resolve(
        'folder_tree', tags=[{'name': 'noise', 'mode': 'or'}, 'dry'])
    assert error is None
    body = mcp_registry.build_body(tool, merged)
    assert body['tags'] == [{'name': 'noise', 'mode': 'or'}, 'dry']

    _, _, error = _resolve('folder_tree', tags=[{'mode': 'or'}])
    assert error is not None and 'name' in error


def test_sample_rate_schema_accepts_string_or_number():
    schema = INTENT_TOOL_BY_NAME['audio_query'].parameters
    assert schema['properties']['sample_rate']['type'] == ['string', 'number']
    assert intent_tools.validate_arguments(
        schema, {'action': 'list', 'sample_rate': 48000}) is None
    assert intent_tools.validate_arguments(
        schema, {'action': 'list', 'sample_rate': '48 kHz'}) is None
    assert '类型应为' in intent_tools.validate_arguments(
        schema, {'action': 'list', 'sample_rate': True})


@pytest.mark.parametrize('action', ['detail', 'features', 'quality',
                                    'algorithms', 'playback_history'])
def test_actions_require_audio_id(action):
    _, _, error = _resolve(action)
    assert error is not None and '缺少必填参数' in error


def test_invalid_action_is_rejected():
    _, _, error = _resolve('tree')
    assert error is not None and '取值必须是' in error


def test_validation_rejects_wrong_enum_and_type():
    schema = INTENT_TOOL_BY_NAME['audio_query'].parameters
    assert '取值必须是' in intent_tools.validate_arguments(
        schema, {'action': 'tree'})
    assert '类型应为 array' in intent_tools.validate_arguments(
        schema, {'action': 'list', 'tags': 'noise'})
    assert intent_tools.validate_arguments(schema, {'action': 'list'}) is None


def test_tool_search_and_platform_contract_expose_audio_query():
    from shared.agent_tools import search
    names = [t['name'] for t in search.search('音频质量', ['audio:read'])['tools']]
    assert 'audio_query' in names
    result = intent_tools.platform_contract('audio_query')
    assert result['tool']['name'] == 'audio_query'
    assert result['tool']['inputSchema']['required'] == ['action']


def test_skill_and_template_no_longer_teach_by_ids():
    """INT-2530 验收 2：Skill 文本与对外模板不得再出现 by_ids 用法示例。"""
    with open(os.path.join(SKILLS_ROOT, 'audio-import', 'SKILL.md'),
              encoding='utf-8') as handle:
        skill_text = handle.read()
    assert 'by_ids' not in skill_text and 'by-ids' not in skill_text
    with open(os.path.join(PROJECT_ROOT, 'api_gateway', 'skill_templates',
                           'SKILL.md'), encoding='utf-8') as handle:
        template = handle.read()
    assert '-d \'{"md5_list":["d41d8cd98f00b204e9800998ecf8427e"]}\'' in template
    assert '-d \'{"md5":"' not in template


# ---------------------------------------------------------------- 网关

class FakeRestClient:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {'ok': True}
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        text = json.dumps(self.payload, ensure_ascii=False)
        return RestResult(status=self.status, payload=self.payload, text=text)


def _gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest or FakeRestClient(),
        credentials=credentials or RunCredentialRegistry())


def _ctx(permissions=('audio:read',)):
    return ToolInvocationContext(
        run_id='r1', session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def _call(action, **arguments):
    return ToolCallRequest(tool_call_id='c1', name='audio_query',
                          arguments={'action': action, **arguments})


def test_gateway_requires_audio_read_permission():
    rest = FakeRestClient()
    result = _gateway(rest).execute(_call('list'), _ctx(permissions=('task:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content
    assert rest.calls == []


def test_gateway_detail_forwards_credentials_and_args():
    rest = FakeRestClient(payload={'success': True, 'data': {'id': 5}})
    credentials = RunCredentialRegistry()
    credentials.put('r1', 'Bearer user-token')
    result = _gateway(rest, credentials).execute(
        _call('detail', audio_id=5), _ctx())
    assert result.ok and result.error_code == 'OK'
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'audio_get'
    assert sent['arguments'] == {'audio_id': 5}
    assert sent['authorization'] == 'Bearer user-token'
    assert sent['permissions'] == ('audio:read',)


def test_gateway_quality_action_maps_to_rest_tool():
    rest = FakeRestClient(payload={'data': {'quality_score': 80}})
    result = _gateway(rest).execute(_call('quality', audio_id=7), _ctx())
    assert result.ok and rest.calls[0]['tool']['name'] == 'audio_quality'


@pytest.mark.parametrize('status,code,needle', [
    (403, PERMISSION_DENIED, '无权访问'),
    (404, RESOURCE_NOT_FOUND, '不存在或无权访问'),
])
def test_gateway_denial_text_does_not_leak_existence(status, code, needle):
    result = _gateway(FakeRestClient(status=status)).execute(
        _call('detail', audio_id=999999), _ctx())
    assert not result.ok and result.error_code == code
    assert needle in result.content
    assert '999999' not in result.content


def test_gateway_rejects_missing_required_before_rest():
    rest = FakeRestClient()
    result = _gateway(rest).execute(_call('detail'), _ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert rest.calls == []


def test_gateway_rejects_by_ids_direct_call_without_calling_rest():
    """INT-2530：即使模型直呼 MCP 工具名，也不得回源 by-ids 枚举他人音频。"""
    rest = FakeRestClient()
    result = _gateway(rest).execute(
        ToolCallRequest('c2', 'audio_get_by_ids', {'ids': [11, 12]}), _ctx())
    assert not result.ok
    assert result.error_code == UNKNOWN_TOOL
    assert rest.calls == []


def test_gateway_write_tools_still_disabled():
    for name, args in [
        ('audio_import', {'action': 'url_import', 'urls': ['http://x/a.wav']}),
        ('audio_annotate', {'action': 'update_meta', 'audio_ids': [1]}),
    ]:
        result = _gateway().execute(
            ToolCallRequest('c2', name, args), _ctx(permissions=('*',)))
        assert result.error_code == TOOL_NOT_ENABLED, name


# ---------------------------------------------------------------- Skill

def _audio_skill():
    registry = SkillRegistry(
        FsSkillRepository(SKILLS_ROOT),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()
    return registry, registry.get('audio-import')


def test_audio_import_skill_loads_without_issues():
    registry, skill = _audio_skill()
    assert skill is not None
    issues = registry.issues_for('audio-import')
    assert [i for i in issues if i.severity is SkillIssueSeverity.ERROR] == []
    assert [i for i in issues if i.severity is SkillIssueSeverity.WARNING] == []


def test_audio_import_skill_contract():
    _, skill = _audio_skill()
    meta = skill.meta
    assert meta.allowed_tools == ('audio_query', 'platform_contract', 'tool_search')
    assert meta.permissions == ('audio:read',)
    assert '触发词' in meta.description and '不适用' in meta.description
    assert skill.has_section('Gotchas') and skill.has_section('验收')
    assert skill.body_line_count <= 500
    # allowed-tools 只声明只读工具（写工具留 M2）
    for name in meta.allowed_tools:
        tool = INTENT_TOOL_BY_NAME[name]
        assert tool.risk == 'READ', name
        assert tool.enabled is True, name


def test_audio_import_skill_is_visible_only_with_permission():
    registry, skill = _audio_skill()
    assert registry.get_visible('audio-import', ['audio:read']) is not None
    assert registry.get_visible('audio-import', ['task:read']) is None


def test_skill_l1_discloses_audio_import():
    registry, _ = _audio_skill()
    block = registry.l1_block(['audio:read'])
    assert 'audio-import：' in block


# ---------------------------------------------------------------- golden tasks

def _golden():
    with open(AUDIO_GOLDEN, encoding='utf-8') as handle:
        return json.load(handle)


def test_golden_tasks_cover_every_action_and_have_negatives():
    data = _golden()
    tasks = data['tasks']
    assert data['skill'] == 'audio-import'
    assert len(tasks) >= 10
    assert len({t['id'] for t in tasks}) == len(tasks)

    covered = set()
    for task in tasks:
        for action in task.get('expected_actions') or ():
            covered.add(action)
    assert covered == set(AUDIO_QUERY_ACTIONS)

    positives = [t for t in tasks if t['expect_skill']]
    negatives = [t for t in tasks if not t['expect_skill']]
    assert len(positives) >= 10 and negatives

    known = {t.name for t in INTENT_TOOLS} | {
        t['name'] for t in mcp_registry.TOOLS}
    for task in tasks:
        if task.get('expected_tool'):
            assert task['expected_tool'] in known, task['id']
        for name in task.get('must_not_call') or ():
            assert name in known, task['id']


# ---------------------------------------------------------------- audit

def _tool_names(request):
    return [t['function']['name'] for t in request.tools]


def test_audio_query_call_is_audited_and_skill_scoped(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'audio_query',
                                   {'action': 'detail', 'audio_id': 9})]),
        text_turn('已查到'),
    ])
    rest = FakeRestClient(payload={'success': True, 'data': {'id': 9}})
    container = build_stack(
        tmp_path / 'audio.db', llm,
        gateway=_gateway(rest),
        executor_factory=lambda orch: InlineRunExecutor(orch))[0]

    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='t', active_skill='audio-import',
        permissions=['audio:read'])
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='查音频 9',
        permissions=['audio:read'], active_skill='audio-import')
    assert created
    container.executor.submit(run.id)

    # 激活 Skill 后只装配其 allowed-tools；记忆工具是 harness 级常驻
    # （INT-2490：不属于任何业务域，激活 Skill 时仍可用）
    assert set(_tool_names(llm.requests[0])) == {
        'audio_query', 'platform_contract', 'tool_search',
        'memory_search', 'memory_write'}

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.tool == 'audio_query'
    assert record.result_code == 'OK'
    assert record.permission_decision == 'allow'
    assert record.status is ToolCallStatus.COMPLETED
    assert len(record.args_hash) == 64
    assert rest.calls[0]['tool']['name'] == 'audio_get'
