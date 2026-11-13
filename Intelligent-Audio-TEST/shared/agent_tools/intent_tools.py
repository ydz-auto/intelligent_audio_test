# -*- coding: utf-8 -*-
"""意图级工具注册表 —— 内部 Agent 的唯一事实源（方案 §6.1，INT-2453）。

按用户意图分组，不按 REST 1:1。全表 31 个（含 ``tool_search``、2 个记忆工具、
3 个探索工具；业务意图工具 25 个），与方案 §6.1 表逐条对应。

M0 实现 3 个业务意图工具 + ``tool_search``：

- ``platform_contract``：平台口径（服务 / 接口前缀 / 枚举 / 权限码 / 工具 Schema）；
- ``task_query``：任务只读子集（映射 MCP ``task_*`` 只读工具）；
- ``report_query``：报告只读子集（映射 MCP ``report_*`` 只读工具）；
- ``tool_search``：对 205 个 MCP 工具 + 意图工具建索引，按关键词返回 Schema。

M1 各域卡按域启用自己的只读意图工具（已完成：``algorithm_query``，INT-2464）；
每个域工具 = 动作 → MCP 只读工具的映射，REST 路径 / 查询参数仍由
``mcp_registry`` 的共享构造器决定，不复制 Schema。

其余意图工具在本注册表**预留名称与 Schema**（``enabled=False``），调用返回
``TOOL_NOT_ENABLED``；实现分别归 M1 / M2 各域卡。预留名称进入 Skill
allowed-tools 校验与 tool_search 索引，启动时不会出现 ``UNKNOWN_TOOL``。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.agent_tools import contract as platform_contract_catalog
from shared.agent_tools.mcp_registry import TOOLS as MCP_TOOLS, get_tool

# ---------------------------------------------------------------- schema 辅助


def _prop(kind: str, description: str, *, required: bool = False,
          enum: Optional[Sequence[str]] = None,
          items: Optional[dict] = None) -> dict:
    prop: Dict[str, Any] = {'type': kind, 'description': description}
    if enum:
        prop['enum'] = list(enum)
    if items:
        prop['items'] = items
    if required:
        prop['x-required'] = True
    return prop


def _schema(properties: Dict[str, Any],
            required: Sequence[str] = ()) -> Dict[str, Any]:
    schema: Dict[str, Any] = {
        'type': 'object',
        'properties': dict(properties),
        'additionalProperties': False,
    }
    if required:
        schema['required'] = list(required)
    return schema


# ---------------------------------------------------------------- 工具定义


@dataclass(frozen=True)
class IntentTool:
    """一个意图级工具定义（风险 / 权限 / Schema / 实现状态）。"""

    name: str
    description: str
    parameters: Dict[str, Any]
    risk: str = 'READ'
    permissions: Tuple[str, ...] = ()
    enabled: bool = False
    kind: str = 'intent'  # intent | intent_rest | local | reserved

    @property
    def requires_approval(self) -> bool:
        return self.risk != 'READ'


# 任务只读动作 → MCP 工具名（复用同一份 1:1 Schema 与 REST 路径）
TASK_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'task_list',
    'detail': 'task_get',
    'progress': 'task_get_progress',
    'stats': 'task_get_stats',
    'domain_stats': 'task_stats',
    'case_detail': 'task_get_case_detail',
    'case_results': 'task_get_case_results',
    'labs': 'task_get_labs',
}

# 报告只读动作 → MCP 工具名
REPORT_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'report_list',
    'detail': 'report_get',
    'by_task': 'report_by_task',
    'tab_counts': 'report_tab_counts',
    'statistics': 'report_statistics',
    'statistics_trend': 'report_statistics_trend',
    'progress': 'report_progress',
    'cases': 'report_cases',
    'case_averages': 'report_case_averages',
}

# 算法只读动作 → MCP 工具名（INT-2464；写动作归 M2 algorithm_manage / 热重载）
# 逐条对应网关 GET /api/v1/algorithm/* 的只读路由（routes/algorithm_bp.py）。
ALGORITHM_QUERY_ACTIONS: Dict[str, str] = {
    'definitions': 'algorithm_definition_list',
    'definition': 'algorithm_definition_get',
    'definition_draft': 'algorithm_definition_draft_get',
    'groups': 'algorithm_group_list',
    'group': 'algorithm_group_get',
    'params': 'algorithm_param_list',
    'param': 'algorithm_param_get',
    'reference_params': 'algorithm_reference_param_list',
    'reference_param': 'algorithm_reference_param_get',
    'mappings': 'algorithm_mapping_list',
    'case_params': 'algorithm_case_param_list',
    'case_param': 'algorithm_case_param_get',
    'form_schema': 'algorithm_form_schema',
    'options': 'algorithm_options',
    'dimensions': 'algorithm_dimension_list',
    'dimension_params': 'algorithm_dimension_params',
}

# 算法定义状态 / 参数作用域 / 映射源类型的接口取值见
# ``contract.ALGORITHM_*``（平台口径单一事实源），此处不再重复字面量。

# 动作的必填参数（参数 Schema 无法表达的条件必填）
ACTION_REQUIRED: Dict[str, Dict[str, Tuple[str, ...]]] = {
    'task_query': {
        'detail': ('task_id',),
        'progress': ('task_id',),
        'stats': ('task_id',),
        'case_detail': ('task_id', 'case_id'),
        'case_results': ('task_id', 'case_id'),
        'labs': ('task_id',),
    },
    'report_query': {
        'detail': ('report_id',),
        'by_task': ('task_id',),
        'progress': ('report_id',),
        'cases': ('report_id',),
        'case_averages': ('report_id',),
    },
    'algorithm_query': {
        'definition': ('algo_type',),
        'definition_draft': ('algo_type',),
        # 网关 GET /algorithm/reference-params 无 algorithm_type 直接 400
        'reference_params': ('algorithm_type',),
        'param': ('param_id',),
        'reference_param': ('param_id',),
        'case_param': ('param_id',),
        'group': ('group_id',),
        'form_schema': ('algo_type',),
        'dimensions': ('algo_type',),
        'dimension_params': ('dimension_id',),
    },
}

# 条件必填：同一动作下，某参数出现（或取到某值）时连带必填的参数。
# 结构：tool -> action -> ((触发参数, 触发值 | '*', 连带必填), ...)；
# '*' 表示「该参数出现即触发」。事实源为网关侧校验：
# - AlgorithmQueryService.list_params：param_type=api 必须带 api_id；
#   带 device_id 时必须带 algorithm_type 且 param_type 必须是 device。
# - list_mappings：device_id 需要 algorithm_type 定位算法行。
CONDITIONAL_REQUIRED: Dict[str, Dict[str, Tuple[Tuple[str, str, Tuple[str, ...]], ...]]] = {
    'algorithm_query': {
        'params': (
            ('param_type', 'api', ('api_id',)),
            ('device_id', '*', ('algorithm_type',)),
        ),
        'mappings': (
            ('device_id', '*', ('algorithm_type',)),
        ),
    },
}


INTENT_TOOLS: List[IntentTool] = [
    # ---------------- M0 已实现（3 个业务 + tool_search） ----------------
    IntentTool(
        name='platform_contract',
        description=('查询平台口径：服务与端口、接口前缀、枚举取值、权限码、'
                     '命名规则、工具 Schema。回答「平台怎么描述自己」时先查这里，'
                     '不要凭记忆编造接口、字段或权限码。'),
        parameters=_schema({
            'query': _prop('string', '关键词，如「任务状态」「报告类型」「权限码」'),
            'section': _prop('string', '限定检索范围',
                             enum=['all', 'services', 'endpoints', 'enums',
                                   'naming', 'conventions']),
        }),
        risk='READ', permissions=(), enabled=True, kind='local'),
    IntentTool(
        name='tool_search',
        description=('按关键词检索长尾工具并返回可直接调用的 Schema。'
                     '只调用返回结果中出现过的工具；未返回表示平台没有该能力。'),
        parameters=_schema({
            'query': _prop('string', '意图关键词，如「导出报告」「SPL 校准」「批量标注」',
                           required=True),
            'limit': _prop('integer', '返回条数上限（默认 10，最大 30）'),
        }, required=('query',)),
        risk='READ', permissions=(), enabled=True, kind='local'),
    IntentTool(
        name='task_query',
        description=('任务只读查询：列表、详情、进度、统计、用例详情 / 结果、实验室关系。'
                     '字段口径与 REST /api/v1/tasks 一致，不编造数值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(TASK_QUERY_ACTIONS)),
            'task_id': _prop('integer', '任务 ID（detail / progress / stats / 用例动作必填）'),
            'case_id': _prop('string', '用例 ID（用例详情 / 结果动作必填）'),
            'search': _prop('string', '关键词过滤（list）'),
            'status': _prop('string', '任务状态过滤（list）'),
            'page': _prop('integer', '页码（list，默认 1）'),
            'per_page': _prop('integer', '每页条数（list）'),
        }, required=('action',)),
        risk='READ', permissions=('task:read',), enabled=True, kind='intent_rest'),
    IntentTool(
        name='report_query',
        description=('报告只读查询：列表、详情、按任务查、标签计数、统计 / 趋势、'
                     '生成进度、用例明细 / 平均值。字段口径与 REST /api/v1/reports 一致。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(REPORT_QUERY_ACTIONS)),
            'report_id': _prop('integer', '报告 ID（detail / progress / cases / case_averages 必填）'),
            'task_id': _prop('integer', '任务 ID（by_task 必填）'),
            'keyword': _prop('string', '关键词过滤（list / tab_counts / statistics）'),
            'page': _prop('integer', '页码（list）'),
            'per_page': _prop('integer', '每页条数（list）'),
        }, required=('action',)),
        risk='READ', permissions=('report:read',), enabled=True, kind='intent_rest'),

    # ---------------- 探索 / 记忆（预留，M1 / M2 实现） ----------------
    IntentTool(
        name='ui_tree',
        description=('读取设备 UI 树：裁剪节点、截图引用、与上次快照 diff；'
                     '需要设备租用。实现见 M2 探索层（INT-2492），当前未启用。'),
        parameters=_schema({
            'device_id': _prop('integer', '设备 ID', required=True),
            'max_nodes': _prop('integer', '节点上限（默认 200）'),
            'include_screenshot': _prop('boolean', '是否返回截图引用'),
            'diff_with_last': _prop('boolean', '是否与上次快照 diff'),
        }, required=('device_id',)),
        risk='READ', permissions=('device:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='ui_action',
        description=('设备 UI 动作：点击 / 长按 / 滑动 / 输入 / 返回 / Home / 等待；'
                     '需要设备租用与审批。实现见 M2 探索层（INT-2492），当前未启用。'),
        parameters=_schema({
            'device_id': _prop('integer', '设备 ID', required=True),
            'action': _prop('string', '动作类型', required=True,
                            enum=['tap', 'long_press', 'swipe', 'input',
                                  'back', 'home', 'wait']),
            'x': _prop('integer', '横坐标（tap / long_press / swipe 起点）'),
            'y': _prop('integer', '纵坐标（tap / long_press / swipe 起点）'),
            'to_x': _prop('integer', '滑动终点横坐标'),
            'to_y': _prop('integer', '滑动终点纵坐标'),
            'text': _prop('string', '输入文本（input）'),
            'duration_ms': _prop('integer', '长按 / 等待时长（毫秒）'),
        }, required=('device_id', 'action')),
        risk='WRITE', permissions=('device:control',), enabled=False, kind='reserved'),
    IntentTool(
        name='api_spec',
        description=('解析 OpenAPI / proto / WebSocket 契约：端点、鉴权、请求响应样例。'
                     '实现见 M2 探索层（INT-2492），当前未启用。'),
        parameters=_schema({
            'source': _prop('string', '契约来源：URL / 文件路径 / 被测 API ID'),
            'api_id': _prop('integer', '被测 API ID'),
            'format': _prop('string', '契约格式', enum=['openapi', 'proto', 'ws']),
            'endpoint': _prop('string', '只看某个端点'),
        }),
        risk='READ', permissions=('api_config:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='memory_search',
        description=('检索用户 / 项目长期记忆与 Skill references（rg 封装，'
                     'tenant / owner 严格隔离，无向量 RAG）。实现见 M1（INT-2490），当前未启用。'),
        parameters=_schema({
            'query': _prop('string', '检索关键词', required=True),
            'scope': _prop('string', '检索范围', enum=['user', 'project']),
            'limit': _prop('integer', '返回条数上限'),
        }, required=('query',)),
        risk='READ', permissions=(), enabled=False, kind='reserved'),
    IntentTool(
        name='memory_write',
        description=('写入用户偏好或项目规则；需要审批。'
                     '实现见 M1（INT-2490），当前未启用。'),
        parameters=_schema({
            'content': _prop('string', '要记住的内容', required=True),
            'kind': _prop('string', '记忆类型', enum=['preference', 'project_rule'],
                          required=True),
            'scope': _prop('string', '写入范围', enum=['user', 'project']),
        }, required=('content', 'kind')),
        risk='WRITE', permissions=('memory:write',), enabled=False, kind='reserved'),

    # ---------------- 其余业务意图工具（预留，M1 / M2 实现） ----------------
    IntentTool(
        name='audio_query', description='音频列表、详情、MD5、标签、目录树、特征/质量（只读）。',
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=['list', 'detail', 'tree', 'tags', 'quality']),
            'audio_id': _prop('integer', '音频 ID'),
            'search': _prop('string', '关键词'),
            'page': _prop('integer', '页码'),
            'per_page': _prop('integer', '每页条数'),
        }, required=('action',)),
        risk='READ', permissions=('audio:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='audio_import', description='URL 导入、上传初始化/合并、OSS 直传确认（写）。',
        parameters=_schema({
            'action': _prop('string', '导入动作', required=True,
                            enum=['url_import', 'upload_init', 'upload_merge', 'confirm']),
            'urls': _prop('array', '音频 URL 列表', items={'type': 'string'}),
            'upload_id': _prop('string', '上传会话 ID'),
        }, required=('action',)),
        risk='WRITE', permissions=('audio:create',), enabled=False, kind='reserved'),
    IntentTool(
        name='audio_annotate', description='批量标注、元数据、算法配置（写）。',
        parameters=_schema({
            'action': _prop('string', '标注动作', required=True,
                            enum=['batch_annotate', 'update_meta', 'set_algorithms']),
            'audio_ids': _prop('array', '音频 ID 列表', items={'type': 'integer'}),
            'body': _prop('object', '标注 / 元数据字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('audio:update',), enabled=False, kind='reserved'),
    IntentTool(
        name='testcase_query', description='用例列表、详情、导入导出状态（只读）。',
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=['list', 'detail', 'import_status']),
            'case_id': _prop('string', '用例 ID'),
            'group_id': _prop('integer', '分组 ID'),
            'search': _prop('string', '关键词'),
            'page': _prop('integer', '页码'),
            'per_page': _prop('integer', '每页条数'),
        }, required=('action',)),
        risk='READ', permissions=('testcase:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='testcase_generate', description='标注 → 用例草案（不落库，只读生成）。',
        parameters=_schema({
            'audio_ids': _prop('array', '音频 ID 列表', items={'type': 'integer'}),
            'group_id': _prop('integer', '目标分组 ID'),
            'algorithm_type': _prop('string', '算法类型'),
        }, required=('audio_ids',)),
        risk='READ', permissions=('testcase:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='testcase_write', description='创建、修改、复制、删除、打标签（写）。',
        parameters=_schema({
            'action': _prop('string', '写动作', required=True,
                            enum=['create', 'update', 'copy', 'delete', 'tag']),
            'case_id': _prop('string', '用例 ID'),
            'body': _prop('object', '用例字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('testcase:update',), enabled=False, kind='reserved'),
    IntentTool(
        name='tag_group_manage', description='标签与分组 CRUD、批量打标（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['create', 'update', 'delete', 'batch_tag']),
            'target_kind': _prop('string', '目标类型', enum=['tag', 'group']),
            'body': _prop('object', '标签 / 分组字段'),
        }, required=('action', 'target_kind')),
        risk='WRITE', permissions=('tag:write',), enabled=False, kind='reserved'),
    IntentTool(
        name='evaluation_query', description='评估维度、分类、评分口径（只读）。',
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=['dimensions', 'categories', 'scores']),
            'task_id': _prop('integer', '任务 ID'),
            'case_id': _prop('string', '用例 ID'),
        }, required=('action',)),
        risk='READ', permissions=('evaluation:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='evaluation_manage', description='维度/分类 CRUD、触发重评估（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['dimension_create', 'dimension_update',
                                  'category_create', 'category_update', 'reevaluate']),
            'body': _prop('object', '维度 / 分类字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('evaluation:update',), enabled=False, kind='reserved'),
    IntentTool(
        name='algorithm_query',
        description=('算法配置只读查询（INT-2464）：定义 / 草稿 / 分组、设备与 API 参数、'
                     '参考参数、参数映射、用例专属参数、表单 Schema、下拉选项、'
                     '关联评估维度。字段与默认值一律以接口返回为准，不编造可选值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(ALGORITHM_QUERY_ACTIONS)),
            'algo_type': _prop('string', '算法类型（如 voice_llm；取值以 options 动作为准）'),
            'algorithm_type': _prop('string', '算法类型过滤（列表 / 参数 / 映射 / 参考参数用）'),
            'param_id': _prop('integer', '参数 ID（param / reference_param / case_param 必填）'),
            'group_id': _prop('integer', '算法分组 ID（group 必填）'),
            'dimension_id': _prop('integer', '评估维度 ID（dimension_params 必填）'),
            'status': _prop('string', '算法定义状态过滤（definitions）',
                            enum=list(platform_contract_catalog.ALGORITHM_STATUS_VALUES)),
            'param_type': _prop('string', '参数作用域（params；缺省 device）',
                                enum=list(platform_contract_catalog.ALGORITHM_PARAM_TYPE_VALUES)),
            'api_id': _prop('integer', 'API 实例 ID（param_type=api 或 API 作用域映射）'),
            'device_id': _prop('integer', '设备 ID（设备作用域参数 / 映射）'),
            'source_type': _prop('string', '映射源类型（mappings）',
                                 enum=list(platform_contract_catalog.ALGORITHM_MAPPING_SOURCE_VALUES)),
            'scope': _prop('string', '用例参数作用域（case_params，取值以接口返回为准）'),
        }, required=('action',)),
        risk='READ', permissions=('algorithm:read',), enabled=True, kind='intent_rest'),
    IntentTool(
        name='algorithm_manage', description='定义/参数/映射写操作、热重载（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['definition_upsert', 'param_upsert',
                                  'mapping_upsert', 'reload']),
            'body': _prop('object', '算法配置字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('algorithm:update',), enabled=False, kind='reserved'),
    IntentTool(
        name='task_run', description='创建、启动、停止、重试、合并、重提取（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['create', 'start', 'stop', 'retry', 'merge',
                                  'reextract']),
            'task_id': _prop('integer', '任务 ID'),
            'body': _prop('object', '任务字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('task:execute',), enabled=False, kind='reserved'),
    IntentTool(
        name='task_diagnose', description='失败用例、日志、归因、重测建议（只读）。',
        parameters=_schema({
            'task_id': _prop('integer', '任务 ID', required=True),
            'case_id': _prop('string', '用例 ID'),
            'keyword': _prop('string', '日志关键词'),
        }, required=('task_id',)),
        risk='READ', permissions=('task:read', 'log:read'), enabled=False, kind='reserved'),
    IntentTool(
        name='spl_calibrate', description='SPL 映射、校准、测试音、历史（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['mapping', 'calibrate', 'test_tone', 'history']),
            'device_id': _prop('integer', '设备 ID'),
            'body': _prop('object', '校准参数'),
        }, required=('action',)),
        risk='WRITE', permissions=('spl:write',), enabled=False, kind='reserved'),
    IntentTool(
        name='device_query', description='设备、分组、状态、告警（只读）。',
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=['list', 'detail', 'groups', 'status', 'alarms']),
            'device_id': _prop('integer', '设备 ID'),
            'page': _prop('integer', '页码'),
            'per_page': _prop('integer', '每页条数'),
        }, required=('action',)),
        risk='READ', permissions=('device:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='device_control', description='连接、重启、扫描、安装、批量控制（破坏性写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['connect', 'disconnect', 'reboot', 'scan',
                                  'install', 'batch']),
            'device_id': _prop('integer', '设备 ID'),
            'device_ids': _prop('array', '批量设备 ID', items={'type': 'integer'}),
            'body': _prop('object', '控制参数'),
        }, required=('action',)),
        risk='DESTRUCTIVE', permissions=('device:control',), enabled=False, kind='reserved'),
    IntentTool(
        name='report_generate', description='生成/重生成报告、创建 Studio 草稿（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['generate', 'regenerate', 'studio_draft']),
            'task_id': _prop('integer', '任务 ID'),
            'report_id': _prop('integer', '报告 ID'),
            'body': _prop('object', '生成参数'),
        }, required=('action',)),
        risk='WRITE', permissions=('report:create',), enabled=False, kind='reserved'),
    IntentTool(
        name='report_compare', description='多报告 / 二次对比、趋势（只读）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['compare', 'secondary_compare', 'trend']),
            'report_ids': _prop('array', '报告 ID 列表', items={'type': 'integer'}),
            'body': _prop('object', '对比参数'),
        }, required=('action',)),
        risk='READ', permissions=('report:compare',), enabled=False, kind='reserved'),
    IntentTool(
        name='report_export', description='导出 PDF / PPTX / HTML / MD（写）。',
        parameters=_schema({
            'report_id': _prop('integer', '报告 ID', required=True),
            'format': _prop('string', '导出格式', required=True,
                            enum=['pdf', 'pptx', 'html', 'md']),
        }, required=('report_id', 'format')),
        risk='WRITE', permissions=('report:export',), enabled=False, kind='reserved'),
    IntentTool(
        name='log_diagnose', description='日志搜索、统计、诊断（只读）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['search', 'stats', 'diagnose']),
            'keyword': _prop('string', '关键词'),
            'level': _prop('string', '日志级别'),
            'task_id': _prop('integer', '任务 ID'),
            'page': _prop('integer', '页码'),
            'per_page': _prop('integer', '每页条数'),
        }, required=('action',)),
        risk='READ', permissions=('log:read',), enabled=False, kind='reserved'),
    IntentTool(
        name='driver_propose',
        description=('生成设备驱动（AppDriver）+ 厂商 API 适配器（ApiVendorAdapter）代码提案；'
                     '不执行、不注册、不发布。target_kind = DEVICE_DRIVER / API_ADAPTER / PAIR。'),
        parameters=_schema({
            'target_kind': _prop('string', '提案目标', required=True,
                                 enum=['DEVICE_DRIVER', 'API_ADAPTER', 'PAIR']),
            'app_type': _prop('string', 'App 类型（设备驱动）'),
            'api_id': _prop('integer', '被测 API ID（API 适配器）'),
            'capabilities': _prop('object', '能力画像 capabilities.json'),
            'ui_trace': _prop('object', 'UI 探索轨迹（ui_trace.json）'),
        }, required=('target_kind',)),
        risk='WRITE', permissions=('algorithm:update',), enabled=False, kind='reserved'),
    IntentTool(
        name='dashboard_query', description='首页统计（只读；缓存刷新留 M2）。',
        parameters=_schema({
            'action': _prop('string', '统计动作', required=True,
                            enum=['summary', 'trend', 'recent_tasks']),
        }, required=('action',)),
        risk='READ', permissions=('dashboard:read',), enabled=False, kind='reserved'),
]

INTENT_TOOL_BY_NAME: Dict[str, IntentTool] = {t.name: t for t in INTENT_TOOLS}

# 已启用的工具集合（执行前判定；预留工具返回 TOOL_NOT_ENABLED）
ENABLED_TOOLS = frozenset(t.name for t in INTENT_TOOLS if t.enabled)

# tool_search 索引：205 个 MCP 工具 + 意图工具（含 5 个预留名称）。
# MCP 与意图工具存在同名项（report_compare / report_export）：保留 MCP 条目
# （可直接调用），同名意图条目不再重复进索引，避免同一 name 出现两次。
_MCP_NAMES = frozenset(t['name'] for t in MCP_TOOLS)

TOOL_INDEX: List[dict] = [
    {'name': t['name'], 'description': t['description'],
     'inputSchema': t['inputSchema'], 'permissions': list(t['permissions']),
     'risk': 'READ' if t['method'] == 'GET' else 'WRITE', 'kind': 'mcp'}
    for t in MCP_TOOLS
] + [
    {'name': t.name, 'description': t.description,
     'inputSchema': t.parameters, 'permissions': list(t.permissions),
     'risk': t.risk, 'kind': t.kind, 'enabled': t.enabled}
    for t in INTENT_TOOLS if t.name not in _MCP_NAMES
]

TOOL_INDEX_BY_NAME: Dict[str, dict] = {t['name']: t for t in TOOL_INDEX}


# ---------------------------------------------------------------- 参数校验


_TYPE_CHECKS = {
    'string': lambda v: isinstance(v, str),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
}


def validate_arguments(schema: dict, arguments: Any) -> Optional[str]:
    """校验参数 Schema（required / type / enum）。返回错误文本或 None。

    只做意图工具契约必需的最小校验；目标 REST 端点仍会做 pydantic 二次校验。
    """
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return '工具参数必须是对象'
    properties = schema.get('properties') or {}
    for name in schema.get('required') or ():
        if name not in arguments or arguments[name] is None:
            return f'缺少必填参数：{name}'
    for name, value in arguments.items():
        spec = properties.get(name)
        if spec is None:
            continue
        if value is None:
            continue
        expected = spec.get('type')
        checker = _TYPE_CHECKS.get(expected)
        if checker is not None and not checker(value):
            return f'参数 {name} 类型应为 {expected}'
        enum = spec.get('enum')
        if enum and value not in enum:
            return f'参数 {name} 取值必须是 {"/".join(map(str, enum))} 之一'
    return None


def required_for_action(name: str, action: str) -> Tuple[str, ...]:
    """按动作返回条件必填参数（Schema 无法表达的部分）。"""
    return ACTION_REQUIRED.get(name, {}).get(action, ())


def conditional_required(name: str, action: str,
                         arguments: Dict[str, Any]) -> Tuple[str, ...]:
    """按「触发参数 → 连带必填」规则返回本次调用额外必填的参数。"""
    rules = CONDITIONAL_REQUIRED.get(name, {}).get(action, ())
    missing: List[str] = []
    for trigger, value, needed in rules:
        actual = arguments.get(trigger)
        if actual is None:
            continue
        if value != '*' and actual != value:
            continue
        missing.extend(p for p in needed if arguments.get(p) is None)
    return tuple(missing)


_REST_ACTION_MAP: Dict[str, Dict[str, str]] = {
    'task_query': TASK_QUERY_ACTIONS,
    'report_query': REPORT_QUERY_ACTIONS,
    'algorithm_query': ALGORITHM_QUERY_ACTIONS,
}


def risk_of(name: str) -> Optional[str]:
    """工具风险：意图工具取声明值；MCP 工具 GET=READ、其余=WRITE。"""
    tool = INTENT_TOOL_BY_NAME.get(name)
    if tool is not None:
        return tool.risk
    mcp = get_tool(name)
    if mcp is None:
        return None
    return 'READ' if mcp['method'] == 'GET' else 'WRITE'


def resolve_rest_call(name: str, arguments: Dict[str, Any]
                      ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把意图工具 / 长尾 MCP 工具解析为 ``(MCP 工具, 合并参数, 错误文本)``。

    - ``task_query`` / ``report_query``：按 ``action`` 映射到对应 MCP 只读工具，
      去掉 ``action`` 后其余参数原样透传（路径 / 查询 / body 由共享构造器决定）；
    - 其他 MCP 工具名（tool_search 命中后直接调用）：原样透传参数；
    - 未知名称或动作非法：返回错误文本，由 ToolGateway 收敛为普通失败结果。
    """
    mapping = _REST_ACTION_MAP.get(name)
    if mapping is not None:
        action = arguments.get('action')
        if action not in mapping:
            return None, None, (
                f'action 取值必须是 {"/".join(mapping)} 之一')
        missing = [p for p in required_for_action(name, action)
                   if arguments.get(p) is None]
        missing.extend(conditional_required(name, action, arguments))
        if missing:
            return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'
        mcp = get_tool(mapping[action])
        if mcp is None:  # pragma: no cover - 注册表内部一致性防御
            return None, None, f'工具映射失效：{name}.{action}'
        merged = {k: v for k, v in arguments.items() if k != 'action'}
        return mcp, merged, None
    mcp = get_tool(name)
    if mcp is not None:
        return mcp, dict(arguments), None
    return None, None, f'未知工具：{name}'


def tool_search(query: str, permissions: Sequence[str], limit: int = 10) -> dict:
    """按关键词检索工具索引；只返回当前权限可用的工具 Schema。"""
    from shared.agent_tools.search import search
    return search(query, permissions, limit=limit)


def platform_contract(query: str = '', section: str = 'all') -> dict:
    """平台口径查询；工具名精确命中时直接返回该工具 Schema。"""
    query = (query or '').strip()
    if query in INTENT_TOOL_BY_NAME:
        tool = INTENT_TOOL_BY_NAME[query]
        return {'query': query, 'tool': _serialize_intent(tool)}
    if query in {t['name'] for t in MCP_TOOLS}:
        mcp = next(t for t in MCP_TOOLS if t['name'] == query)
        return {'query': query, 'tool': {
            'name': mcp['name'], 'description': mcp['description'],
            'inputSchema': mcp['inputSchema'],
            'permissions': list(mcp['permissions']),
            'risk': 'READ', 'kind': 'mcp', 'enabled': True}}
    result = platform_contract_catalog.lookup(query, section)
    if query:
        # 工具匹配复用 tool_search 索引（MCP + 意图工具），口径与检索一致
        from shared.agent_tools.search import search
        result['tools'] = search(query, ('*',), limit=20)['tools']
    else:
        result['tools'] = [_serialize_intent(t) for t in INTENT_TOOLS]
    return result


def _serialize_intent(tool: IntentTool) -> dict:
    return {
        'name': tool.name, 'description': tool.description,
        'inputSchema': tool.parameters, 'risk': tool.risk,
        'permissions': list(tool.permissions), 'enabled': tool.enabled,
        'kind': tool.kind,
    }


__all__ = [
    'ACTION_REQUIRED', 'ALGORITHM_QUERY_ACTIONS', 'CONDITIONAL_REQUIRED',
    'ENABLED_TOOLS', 'INTENT_TOOL_BY_NAME', 'INTENT_TOOLS',
    'IntentTool', 'MCP_TOOLS', 'REPORT_QUERY_ACTIONS', 'TASK_QUERY_ACTIONS',
    'TOOL_INDEX', 'TOOL_INDEX_BY_NAME', 'conditional_required', 'platform_contract',
    'required_for_action', 'resolve_rest_call', 'risk_of', 'tool_search',
    'validate_arguments',
]
