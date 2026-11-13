# -*- coding: utf-8 -*-
"""INT-2464 算法域只读评测（agent_eval / domains / algorithm）。

评测对象两层：

1. **意图工具** ``algorithm_query``：动作 → MCP 只读工具 → 网关真实路由；
   10 条 golden tasks（``golden_tasks.json``）逐条解析出目标工具与 REST 路径；
2. **Skill** ``algorithm-config``：L1 description 触发覆盖、L2 正文与实际接口
   口径一致、``allowed-tools`` 只含已启用的只读工具、不编造可选项与默认值。

卡面验收锚点（INT-2464）：
1. 该域 10 条任务走通（golden tasks 全部解析到预期工具 / 路由）；
2. 参数默认值 / 表单 Schema 与真实接口一致（默认值原样透传，字段名取自真实
   builder；表单 Schema 是 camelCase，参数行是 snake_case）；
3. Skill 触发准确率 ≥ 90%（正样本命中 + 负样本不误命中）；
4. 不编造参数可选项（状态 / 作用域 / 映射源类型 / 算法类型都来自代码或接口，
   算法类型不枚举、只认 ``options`` 返回）。

默认离线执行：不连 Docker 栈、不连数据库。需要真机核对契约时设
``AGENT_EVAL_LIVE=1`` 再跑（默认连本机 docker 网关 15000，可用
``AGENT_EVAL_BASE`` / ``AGENT_EVAL_USER`` / ``AGENT_EVAL_PASSWORD`` 覆盖）。
"""
import json
import os
import re
import urllib.parse

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.agent_tools import contract, intent_tools, mcp_registry
from shared.agent_tools.intent_tools import ALGORITHM_QUERY_ACTIONS

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(
    os.path.join(_HERE, '..', '..', '..', '..'))
_SKILLS_ROOT = os.path.join(_PROJECT_ROOT, 'skills')
_SKILL_NAME = 'algorithm-config'

with open(os.path.join(_HERE, 'golden_tasks.json'), encoding='utf-8') as _handle:
    GOLDEN = json.load(_handle)

CASES = GOLDEN['cases']
NEGATIVES = GOLDEN['negatives']

# 表单 Schema 是当前真实接口（POST 侧 GetFormSchema → 网关 form-schema）产出的
# 字段契约；参数接口是 snake_case，两者不能混用（Skill Gotcha 4）。
FORM_TOP_KEYS = {
    'algorithmType', 'algorithmName', 'description', 'groups', 'fields',
}
FORM_FIELD_KEYS = {
    'fieldCode', 'fieldName', 'fieldType', 'required', 'defaultValue',
    'component', 'helpText', 'hidden', 'uiOrder', 'scope',
}


def _split_url(path):
    parts = urllib.parse.urlsplit(path)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    return parts.path, query


def _normalize(path_template):
    return re.sub(r'\{[^}]+\}', '{}', path_template)


def _load_skill_registry():
    from agent_service.application.skill_registry import SkillRegistry
    from agent_service.infrastructure.skill.fs_skill_repository import (
        FsSkillRepository,
    )
    return SkillRegistry(
        FsSkillRepository(_SKILLS_ROOT),
        known_tools=lambda: [t.name for t in intent_tools.INTENT_TOOLS]).load()


def _skill():
    return _load_skill_registry().get(_SKILL_NAME)


def _trigger_words(description):
    """从 L1 description 的「触发词：…。」段解析触发词（含换行折叠）。"""
    text = ' '.join((description or '').split())
    marker = '触发词：'
    start = text.find(marker)
    if start < 0:
        return ()
    segment = text[start + len(marker):]
    end = segment.find('。')
    if end >= 0:
        segment = segment[:end]
    return tuple(t.strip() for t in segment.split('、') if t.strip())


# ---------------------------------------------------------------- 1. 工具契约

def test_algorithm_query_is_enabled_readonly_with_algorithm_read():
    tool = intent_tools.INTENT_TOOL_BY_NAME['algorithm_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.permissions == ('algorithm:read',)
    assert 'algorithm_query' in intent_tools.ENABLED_TOOLS
    assert intent_tools.risk_of('algorithm_query') == 'READ'


def test_action_enum_matches_action_mapping():
    schema = intent_tools.INTENT_TOOL_BY_NAME['algorithm_query'].parameters
    assert schema['required'] == ['action']
    assert set(schema['properties']['action']['enum']) == set(
        ALGORITHM_QUERY_ACTIONS)


def test_every_action_maps_to_readonly_mcp_tool():
    for action, mcp_name in ALGORITHM_QUERY_ACTIONS.items():
        tool = mcp_registry.get_tool(mcp_name)
        assert tool is not None, f'{action} -> {mcp_name} 未注册'
        assert tool['method'] == 'GET', mcp_name
        assert tool['permissions'] == ['algorithm:read'], mcp_name
        assert tool['path'].startswith('/api/v1/algorithm/'), mcp_name


def test_every_action_targets_a_registered_gateway_get_route():
    """动作 → MCP 路径必须能在网关 algorithm 路由表里找到对应 GET 路由。"""
    from api_gateway.routes.algorithm_bp import router

    registered = {
        (_normalize(route.path), 'GET') for route in router.routes
        if route.methods and 'GET' in route.methods
    }
    prefix = '/api/v1/algorithm'
    for action, mcp_name in ALGORITHM_QUERY_ACTIONS.items():
        path = mcp_registry.get_tool(mcp_name)['path']
        assert path.startswith(prefix), mcp_name
        relative = path[len(prefix):] or '/'
        assert (_normalize(relative), 'GET') in registered, (
            f'{action} -> {mcp_name} 的 {path} 在网关上没有 GET 路由')


def test_status_enum_matches_algorithm_service_source():
    """状态取值锁到 algorithm_service 的 PO 口径映射（接口值 online/offline/draft）。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        _STATUS_STR_TO_ENUM,
    )

    schema = intent_tools.INTENT_TOOL_BY_NAME['algorithm_query'].parameters
    assert set(schema['properties']['status']['enum']) == set(_STATUS_STR_TO_ENUM)
    assert set(contract.ALGORITHM_STATUS_VALUES) == set(_STATUS_STR_TO_ENUM)


def test_param_type_and_source_type_match_gateway_schema():
    """param_type / source_type 取值锁到网关查询 schema（device / api）。"""
    from api_gateway.schemas.algorithm import (
        AlgorithmParamListQuery, ParamMappingCreate,
    )
    from api_gateway.application.services.algorithm import (
        algorithm_query_service as gateway_service,
    )

    source = open(gateway_service.__file__, encoding='utf-8').read()
    for value in contract.ALGORITHM_PARAM_TYPE_VALUES:
        assert f"'{value}'" in source, f'param_type={value} 不在网关分支里'
    assert AlgorithmParamListQuery.model_fields['param_type'].default == 'device'
    description = ParamMappingCreate.model_fields['source_type'].description or ''
    for value in contract.ALGORITHM_MAPPING_SOURCE_VALUES:
        assert value in description, f'source_type={value} 不在网关 schema 描述里'


def test_conditional_required_guards_match_gateway_rules():
    # 设备三层解析：带 device_id 必须带 algorithm_type
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'device_id': 10})
    assert error and 'algorithm_type' in error
    # API 实例作用域：param_type=api 必须带 api_id
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'param_type': 'api'})
    assert error and 'api_id' in error
    # 设备作用域映射同样要 algorithm_type
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'mappings', 'device_id': 10})
    assert error and 'algorithm_type' in error
    # 带全参数通过
    tool, merged, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'param_type': 'device',
                            'device_id': 10, 'algorithm_type': 'voice_llm'})
    assert error is None and tool['name'] == 'algorithm_param_list'
    assert merged['device_id'] == 10


def test_params_api_id_requires_param_type_api():
    """INT-2525 P1-1：api_id 缺 param_type 时网关静默忽略，工具层必须拒绝。"""
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'api_id': 1,
                            'algorithm_type': 'voice_llm'})
    assert error and 'param_type' in error
    # 非 api 作用域传 api_id 同样拒绝（网关按 param_type 走，api_id 被丢弃）
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'param_type': 'device',
                            'api_id': 1, 'algorithm_type': 'voice_llm'})
    assert error and 'param_type=api' in error
    # 正确用法正常解析：参数原样进入算法参数 REST
    tool, merged, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'param_type': 'api',
                            'api_id': 1, 'algorithm_type': 'voice_llm'})
    assert error is None and tool['name'] == 'algorithm_param_list'
    assert merged == {'param_type': 'api', 'api_id': 1,
                      'algorithm_type': 'voice_llm'}


def test_params_device_id_and_api_scope_are_mutually_exclusive():
    """设备作用域与 API 作用域互斥（网关对 device_id + param_type=api 返回 400）。"""
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'params', 'param_type': 'api', 'api_id': 1,
                            'device_id': 10, 'algorithm_type': 'voice_llm'})
    assert error and 'device_id' in error and 'param_type=device' in error


def test_definitions_rejects_unsupported_algorithm_type_filter():
    """INT-2525 P2-1：网关 AlgorithmListQuery 只认 status / group_id。"""
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'definitions', 'algorithm_type': 'asr'})
    assert error and 'definitions' in error and 'status' in error
    for arguments in ({'action': 'definitions', 'status': 'online'},
                      {'action': 'definitions', 'group_id': 3}):
        tool, _, error = intent_tools.resolve_rest_call(
            'algorithm_query', arguments)
        assert error is None, error
        assert tool['name'] == 'algorithm_definition_list'


def test_reference_params_requires_algorithm_type():
    """网关 GET /reference-params 无 algorithm_type 直接 400（不是空列表）。"""
    _, _, error = intent_tools.resolve_rest_call(
        'algorithm_query', {'action': 'reference_params'})
    assert error and 'algorithm_type' in error


@pytest.mark.parametrize('query,expected', [
    ('算法参数', 'algorithm_param_list'),
    ('算法定义', 'algorithm_definition_list'),
    ('表单 Schema', 'algorithm_form_schema'),
    ('参数映射', 'algorithm_mapping_list'),
])
def test_tool_search_surfaces_algorithm_readonly_tools(query, expected):
    from shared.agent_tools.search import search
    names = [t['name'] for t in search(query, ['algorithm:read'])['tools']]
    assert expected in names, f'{query} -> {names}'


# ---------------------------------------------------------------- 2. golden tasks

def test_golden_tasks_are_ten_and_unique():
    assert len(CASES) == 10
    assert len({case['id'] for case in CASES}) == 10
    assert len({case['action'] for case in CASES}) == 10


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_golden_task_resolves_to_expected_tool_and_path(case):
    schema = intent_tools.INTENT_TOOL_BY_NAME['algorithm_query'].parameters
    assert intent_tools.validate_arguments(schema, case['arguments']) is None

    tool, merged, error = intent_tools.resolve_rest_call(
        'algorithm_query', case['arguments'])
    assert error is None, error
    assert tool['name'] == case['expected_tool']
    assert tool['method'] == case['expected_method']

    path, query = _split_url(mcp_registry.build_path(tool, merged))
    expected_path, expected_query = _split_url(case['expected_path'])
    assert path == expected_path
    assert query == expected_query


def test_golden_task_arguments_only_use_declared_schema_fields():
    """golden tasks 里出现的参数名都必须在工具 Schema 里声明（不编造参数）。"""
    properties = intent_tools.INTENT_TOOL_BY_NAME[
        'algorithm_query'].parameters['properties']
    for case in CASES:
        for name in case['arguments']:
            assert name in properties, f"{case['id']} 未声明参数 {name}"


# ---------------------------------------------------------------- 3. Skill L1/L2

def test_algorithm_config_skill_loads_without_errors():
    registry = _load_skill_registry()
    skill = registry.get(_SKILL_NAME)
    assert skill is not None, [i.message for i in registry.issues]
    assert not [i for i in registry.issues_for(_SKILL_NAME)
                if i.severity.value == 'ERROR']
    assert skill.meta.version
    assert skill.meta.owner
    assert skill.has_section('Gotchas')
    assert skill.has_section('验收')
    assert skill.body_line_count <= 500


def test_skill_allowed_tools_are_enabled_readonly():
    skill = _skill()
    assert skill.meta.allowed_tools
    by_name = {t.name: t for t in intent_tools.INTENT_TOOLS}
    for name in skill.meta.allowed_tools:
        tool = by_name.get(name)
        assert tool is not None, f'allowed-tools 引用了未注册工具：{name}'
        assert tool.enabled is True, f'allowed-tools 引用了未启用工具：{name}'
        assert tool.risk == 'READ', f'allowed-tools 引用了写工具：{name}'
    assert 'algorithm_manage' not in skill.meta.allowed_tools
    assert set(skill.meta.permissions) <= {'algorithm:read'}


def test_skill_l2_documents_every_action():
    body = _skill().body
    for action in ALGORITHM_QUERY_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'


def test_skill_documents_real_response_shapes_and_permissions():
    body = _skill().body
    # 表单 Schema camelCase 与参数行 snake_case 两种口径都要写明
    for key in ('algorithmType', 'fieldCode', 'defaultValue'):
        assert key in body
    for key in ('param_code', 'default_value', 'resolved_from'):
        assert key in body
    # 权限码用真实值，不出现 algorithm:write
    assert 'algorithm:read' in body and 'algorithm:definition_manage' in body
    assert 'algorithm:write' not in body
    # case param scope 是真实枚举值
    from shared.models.common_enums import CaseParamScope
    for value in ('physical', 'common'):
        assert value in body
        assert value in {s.value for s in CaseParamScope}


def test_skill_trigger_accuracy_at_least_90_percent():
    triggers = _trigger_words(_skill().description)
    assert triggers, 'L1 description 缺少「触发词：」段'
    positives = [case['utterance'] for case in CASES]
    hit = [u for u in positives if any(t in u for t in triggers)]
    false_positive = [u for u in NEGATIVES if any(t in u for t in triggers)]
    total = len(positives) + len(NEGATIVES)
    correct = len(hit) + (len(NEGATIVES) - len(false_positive))
    accuracy = correct / total
    misses = [u for u in positives if u not in hit]
    assert accuracy >= 0.9, (
        f'触发准确率 {accuracy:.0%} < 90%；未命中={misses}；误命中={false_positive}')


# ---------------------------------------------------------------- 4. 真实接口口径

class _StubRepo:
    """喂给真实表单 Schema builder 的最小仓储（不连库）。"""

    def __init__(self, algorithm, params):
        self._algorithm = algorithm
        self._params = params

    def find_algorithm_by_type(self, algorithm_type):
        if self._algorithm is None:
            return None
        return type('Algo', (), {
            'name': self._algorithm['name'],
            'description': self._algorithm.get('description'),
        })()

    def list_case_params_for_schema(self, algorithm_type):
        return [type('Param', (), p)() for p in self._params]


def _build_form_schema(algorithm, params):
    """调用真实 builder（task_service GetFormSchema 的实现，网关 form-schema 即它）。"""
    from task_service.application.algorithm.algorithm_param_query_service import (
        AlgorithmParamQueryService,
    )

    service = AlgorithmParamQueryService()
    service.repo = _StubRepo(algorithm, params)
    return service.get_form_schema('voice_llm')


def test_form_schema_keys_match_real_builder_and_defaults_pass_through():
    """表单 Schema 字段名与默认值口径取自真实 builder，不是文档臆造。"""
    algorithm = {'name': '语音大模型', 'description': '端到端语音模型'}
    params = [
        {'param_code': 'interferers', 'param_name': '干扰器列表',
         'param_type': 'json', 'required': False, 'default_value': {},
         'help_text': '干扰器列表', 'hidden': False, 'ui_order': 0,
         'scope': 'physical'},
        {'param_code': 'record_mode', 'param_name': '录制模式',
         'param_type': 'text', 'required': False, 'default_value': 0,
         'help_text': '', 'hidden': False, 'ui_order': 1, 'scope': 'common'},
        {'param_code': 'type', 'param_name': '标识类型',
         'param_type': 'text', 'required': False, 'default_value': None,
         'help_text': '标识类型', 'hidden': False, 'ui_order': 2,
         'scope': 'common'},
    ]
    result = _build_form_schema(algorithm, params)
    assert result['success'] is True
    data = result['data']
    assert set(data) == FORM_TOP_KEYS
    assert data['algorithmType'] == 'voice_llm'
    assert len(data['groups']) == 1
    group = data['groups'][0]
    assert set(group) >= {'name', 'label', 'fields'}
    for field in group['fields']:
        assert set(field) == FORM_FIELD_KEYS
        assert field['fieldCode'] and field['component']

    defaults = {f['fieldCode']: f['defaultValue'] for f in group['fields']}
    # 默认值原样透传：{}、0、None 都不被工具/文档改写
    assert defaults == {'interferers': {}, 'record_mode': 0, 'type': None}
    components = {f['fieldCode']: f['component'] for f in group['fields']}
    assert components['interferers'] == 'code-editor'
    assert components['record_mode'] == 'input'


def test_form_schema_missing_algorithm_is_reported_not_invented():
    result = _build_form_schema(None, [])
    assert result['success'] is False
    assert result['code'] == 404
    assert 'No algorithm found' in result['message']


# ---------------------------------------------------------------- 5. 真机契约（可选）

_LIVE = os.environ.get('AGENT_EVAL_LIVE') == '1'


@pytest.mark.skipif(not _LIVE, reason='AGENT_EVAL_LIVE!=1：默认离线，真机契约核对按需开启')
def test_live_algorithm_contracts_match_documented_shapes():
    """连 docker 网关核对：状态取值、表单 Schema 键、参数两种形态、参考参数必填。"""
    from tests.ui.utils.api_client import ApiClient, ApiError

    base = os.environ.get('AGENT_EVAL_BASE', 'http://127.0.0.1:15000')
    client = ApiClient(base)
    client.login(os.environ.get('AGENT_EVAL_USER', 'dev_user'),
                 os.environ.get('AGENT_EVAL_PASSWORD', 'dev_password'))

    def get(path):
        return client.request('GET', path)

    options = get('/algorithm/options')['data']['algorithms']
    assert options, 'options 返回空，无法核对算法类型'
    algo_type = options[0]['value']

    definitions = get('/algorithm/definitions')['data']['items']
    for item in definitions:
        assert 'type' in item and 'algorithm_type' not in item
        assert item['status'] in contract.ALGORITHM_STATUS_VALUES

    schema = get(f'/algorithm/form-schema/{algo_type}')['data']
    assert set(schema) == FORM_TOP_KEYS
    for group in schema['groups']:
        for field in group['fields']:
            assert set(field) == FORM_FIELD_KEYS

    envelope = get('/algorithm/params')['data']
    assert 'items' in envelope

    device_params = get(
        f'/algorithm/params?param_type=device&device_id=10&algorithm_type={algo_type}'
    )['data']
    if isinstance(device_params, list):
        assert device_params and 'resolved_from' in device_params[0]

    with pytest.raises(ApiError) as exc:
        get('/algorithm/reference-params')
    assert exc.value.status == 400
