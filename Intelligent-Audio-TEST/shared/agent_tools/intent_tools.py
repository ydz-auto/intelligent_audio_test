# -*- coding: utf-8 -*-
"""意图级工具注册表 —— 内部 Agent 的唯一事实源（方案 §6.1，INT-2453）。

按用户意图分组，不按 REST 1:1。全表 31 个（含 ``tool_search``、2 个记忆工具、
3 个探索工具；业务意图工具 25 个），与方案 §6.1 表逐条对应。

本卡（M0）实现 3 个业务意图工具 + ``tool_search``，M1 音频域卡（INT-2458）
追加 ``audio_query``，评估域卡（INT-2462）追加 ``evaluation_query``，
算法域卡（INT-2464）追加 ``algorithm_query``：

- ``platform_contract``：平台口径（服务 / 接口前缀 / 枚举 / 权限码 / 工具 Schema）；
- ``task_query``：任务只读子集（映射 MCP ``task_*`` 只读工具）；
- ``report_query``：报告只读子集（映射 MCP ``report_*`` 只读工具）；
- ``audio_query``：音频只读子集（映射 MCP ``audio_*`` 只读工具）；
- ``evaluation_query``：评估维度 / 分类只读子集（映射 MCP ``evaluation_*`` 只读工具）；
- ``algorithm_query``：算法定义 / 参数 / 映射 / 表单 Schema 只读子集（映射 MCP ``algorithm_*`` 只读工具）；
- ``tool_search``：对 205 个 MCP 工具 + 意图工具建索引，按关键词返回 Schema。
  其中宿主语境专用工具（``AGENT_UNEXPOSED_MCP_TOOLS``，当前为
  ``audio_get_by_ids``）不进索引、不可被 Agent 调用（INT-2530）。

M1 各域卡按域启用自己的只读意图工具（已完成：``audio_query`` INT-2458、
``evaluation_query`` INT-2462、``algorithm_query`` INT-2464、
``task_query`` / ``task_diagnose`` / ``log_diagnose`` / ``dashboard_query``
INT-2461）；每个域工具 = 动作 → MCP 只读工具的映射，REST 路径 / 查询参数
仍由 ``mcp_registry`` 的共享构造器决定，不复制 Schema。

``task_diagnose`` / ``log_diagnose.diagnose`` 是本地只读聚合：由 ToolGateway
用同一份 MCP 定义组合多个只读接口，纯函数汇总在
``shared/agent_tools/diagnostics.py``，输出带来源 ID，不估算数值。

其余意图工具在本注册表**预留名称与 Schema**（``enabled=False``），调用返回
``TOOL_NOT_ENABLED``；实现分别归 M1 / M2 各域卡。预留名称进入 Skill
allowed-tools 校验与 tool_search 索引，启动时不会出现 ``UNKNOWN_TOOL``。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.agent_tools import contract as platform_contract_catalog
from shared.agent_tools.diagnostics import (
    DEFAULT_LOG_ROWS as LOG_DIAGNOSE_DEFAULT_MAX_ROWS,
    MAX_LOG_ROWS as LOG_DIAGNOSE_MAX_ROWS,
)
from shared.agent_tools.mcp_registry import TOOLS as MCP_TOOLS, get_tool

# ---------------------------------------------------------------- schema 辅助


def _prop(kind, description: str, *, required: bool = False,
          enum: Optional[Sequence[str]] = None,
          items: Optional[dict] = None,
          minimum: Optional[int] = None,
          maximum: Optional[int] = None) -> dict:
    """构造参数 Schema；``kind`` 可以是单个类型或类型元组（联合类型）。"""
    prop_type = list(kind) if isinstance(kind, (list, tuple)) else kind
    prop: Dict[str, Any] = {'type': prop_type, 'description': description}
    if enum:
        prop['enum'] = list(enum)
    if items:
        prop['items'] = items
    if minimum is not None:
        prop['minimum'] = minimum
    if maximum is not None:
        prop['maximum'] = maximum
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

# 各动作可用的可选参数（动作独立口径，INT-2461）。
# 网关查询 Schema 基类 APIModel 是 ``extra='ignore'``：未声明的参数被静默
# 丢弃，放过去会让模型把「全量」当成「过滤结果」，因此在工具层直接拒绝。
# list 的过滤字段与网关 TaskListQuery 逐字一致（api_gateway/schemas/task.py）。
TASK_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'list': ('search', 'status', 'execution_status', 'evaluation_status',
             'algorithm_type', 'start_date', 'end_date', 'favorite', 'deleted',
             'merged', 'cherry_pick', 'merge_type', 'visibility', 'stats',
             'page', 'per_page'),
    'detail': (),
    'progress': (),
    'stats': (),
    # GET /api/v1/tasks/stats 的 TaskDomainStatsQuery 只有 granularity
    'domain_stats': ('granularity',),
    'case_detail': (),
    'case_results': (),
    'labs': (),
}

# 任务域聚合统计的分桶粒度（TaskDomainStatsQuery.granularity 的接口取值，
# 非法值由 task_service 返回 400）。
TASK_DOMAIN_STATS_GRANULARITIES: Tuple[str, ...] = (
    'day', 'week', 'month', 'year')

# 日志诊断动作 → MCP 只读工具（INT-2461）。
# ``diagnose`` 不映射 REST：它是本地聚合（日志统计 + 错误日志行 → 来源归因），
# 由 ToolGateway 组合执行，见 ``LOG_DIAGNOSE_LOCAL_ACTIONS``。
LOG_DIAGNOSE_ACTIONS: Dict[str, str] = {
    'search': 'log_list',
    'stats': 'log_stats',
}
LOG_DIAGNOSE_LOCAL_ACTIONS: Tuple[str, ...] = ('diagnose',)
LOG_DIAGNOSE_ALL_ACTIONS: Tuple[str, ...] = (
    tuple(LOG_DIAGNOSE_ACTIONS) + LOG_DIAGNOSE_LOCAL_ACTIONS)
# 各动作可用的可选参数（对齐 LogListQuery / LogStatsQuery 的真实字段）。
# stats 端点没有 test_case_id / page / per_page，工具层不声明。
# diagnose 额外接受取样上限（默认 / 上限取自 diagnostics 模块，Schema 用
# minimum / maximum 校验，不支持静默截断）。
LOG_DIAGNOSE_PARAMS: Dict[str, Tuple[str, ...]] = {
    'search': ('keyword', 'level', 'module', 'category', 'task_id',
               'test_case_id', 'start_time', 'end_time', 'page', 'per_page'),
    'stats': ('keyword', 'level', 'module', 'category', 'task_id',
              'start_time', 'end_time'),
    'diagnose': ('keyword', 'level', 'module', 'category', 'task_id',
                 'test_case_id', 'start_time', 'end_time', 'max_rows'),
}

# ``diagnose`` 里只作用于日志取样、不能进入级别统计的参数（INT-2461 P2）：
# ``GET /api/v1/logs/stats`` 的 ``LogStatsQuery`` 没有 ``test_case_id``
# （``APIModel`` 是 ``extra='ignore'``，会静默丢弃）。若整体带进
# ``stats_filters``，统计值会被误标成「按用例过滤」，实际是任务 / 全局口径；
# 因此该参数只进 ``list_filters``，诊断输出的 ``notes`` 写明统计口径。
LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS: Tuple[str, ...] = ('test_case_id',)

# 首页统计只读动作 → MCP 工具名（INT-2461；缓存刷新是写侧，留 M2）
DASHBOARD_QUERY_ACTIONS: Dict[str, str] = {
    'details': 'home_stats_details',
    'summary': 'home_stats_summary',
}
DASHBOARD_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'details': (),
    'summary': (),
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

# 音频只读动作 → MCP 工具名（映射 MCP audio_* 只读子集，INT-2458）
#
# INT-2530（INT-2523 P1-1）：不暴露 ``by_ids``。该动作是无归属校验的批量读
# 通道（INT-564 规划师裁定为宿主语境专用：用例回填 / 批量标注匹配），而 Agent
# 工具调用沿用**用户自己的** Authorization，不是宿主语境——有 ``audio:read``
# 的用户即可用任意 id 枚举他人 ``private`` 音频的元数据 / 标签 / 标注。
# 宿主侧 REST ``/api/v1/audios/by-ids`` 行为不变，只是不进 Agent 动作表，
# 见 ``AGENT_UNEXPOSED_MCP_TOOLS``。
AUDIO_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'audio_list',
    'detail': 'audio_get',
    'by_md5': 'audio_get_by_md5',
    'tags': 'audio_list_tags',
    'folder_tree': 'audio_folder_tree',
    'features': 'audio_features',
    'quality': 'audio_quality',
    'algorithms': 'audio_get_algorithms',
    'playback_history': 'audio_playback_history',
}

# 各动作可用的可选参数（动作独立口径）。
# 动作不支持的参数在工具层直接报错——服务端对这些参数是静默忽略的，
# 放过去会让模型把「全量」当成「过滤结果」。
AUDIO_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'list': ('keyword', 'page', 'per_page', 'format', 'audio_type',
             'sample_rate', 'duration', 'tags', 'direction',
             'algorithm_type', 'visibility'),
    'detail': (),
    'by_md5': (),
    'tags': (),
    'folder_tree': ('keyword', 'format', 'audio_type', 'sample_rate',
                    'duration', 'tags', 'direction', 'algorithm_type',
                    'parent_path', 'depth'),
    'features': (),
    'quality': (),
    'algorithms': (),
    'playback_history': ('page', 'per_page'),
}

# 时长过滤只认档位（audio_service/_audio_query_filters._DURATION_BUCKETS）：
# short ≤30s、medium 30~300s、long >300s；传区间字符串会被服务端静默忽略。
AUDIO_DURATION_BUCKETS: Tuple[str, ...] = ('short', 'medium', 'long')

# 评估只读动作 → MCP 工具名（INT-2462）。
# 评分口径 / 可见性 / 输入输出参数都是维度详情的字段，不另设端点；
# 健康探测与维度选项属维护 / UI 下拉数据源，M1 未开放为意图动作。
EVALUATION_QUERY_ACTIONS: Dict[str, str] = {
    'dimensions': 'evaluation_dimension_list',
    'dimension': 'evaluation_dimension_get',
    'categories': 'evaluation_category_list',
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

# 算法定义列表的网关查询 Schema 只有 status / group_id
# （api_gateway/schemas/_algorithm_param_schemas.py AlgorithmListQuery，基类
# APIModel ``extra='ignore'``）：其余过滤参数会被静默丢弃。
ALGORITHM_DEFINITIONS_FILTERS: Tuple[str, ...] = ('status', 'group_id')

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
    # 参数名与目标 REST 逐字一致（ids / md5_list 直接作为请求体字段）：
    # 不在这里做改名映射，避免意图层与 REST 出现两套字段口径。
    'audio_query': {
        'detail': ('audio_id',),
        'by_md5': ('md5_list',),
        'features': ('audio_id',),
        'quality': ('audio_id',),
        'algorithms': ('audio_id',),
        'playback_history': ('audio_id',),
    },
    'evaluation_query': {
        'dimension': ('dim_id',),
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
# '*' 表示「该参数出现即触发」。
# params 的三条护栏分两类：
# - param_type=api 必须带 api_id、device_id 必须带 algorithm_type 是网关校验，
#   缺参网关直接 400，工具层提前拦下省一次调用；
# - api_id 出现即要求 param_type：缺 param_type 时网关**不报错**，按默认
#   device 走算法级列表并静默忽略 api_id，返回的不是 API 作用域行。
# 取值冲突（param_type 非 api / 非 device）的详细报错见
# ``_normalize_algorithm_query_arguments``。
# mappings 的 device_id → algorithm_type 也只是工具层护栏：网关对不带
# algorithm_type 的 /mappings?device_id= 返回 200 + 空数组，**不会报错**，
# 放过去模型会把「没查到」当成「设备没有映射」。
CONDITIONAL_REQUIRED: Dict[str, Dict[str, Tuple[Tuple[str, str, Tuple[str, ...]], ...]]] = {
    'algorithm_query': {
        'params': (
            ('param_type', 'api', ('api_id',)),
            ('api_id', '*', ('param_type',)),
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
        description=('任务只读查询：列表（状态 / 执行状态 / 评估状态 / 时间 / 可见性 / '
                     '收藏 / 回收站 / 合并容器过滤）、详情、进度、用例统计、任务域聚合'
                     '统计、用例详情 / 结果、实验室关系。字段口径与 REST /api/v1/tasks '
                     '一致，不估算、不编造数值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(TASK_QUERY_ACTIONS)),
            'task_id': _prop('integer', '任务 ID（detail / progress / stats / 用例动作 / labs 必填）'),
            'case_id': _prop('string', '用例 ID（用例详情 / 结果动作必填）'),
            'search': _prop('string', '关键词过滤（list）'),
            'status': _prop('string', '任务状态过滤（list，取值见 platform_contract 的 task_status）'),
            'execution_status': _prop('string', '执行状态过滤（list）'),
            'evaluation_status': _prop('string', '评估状态过滤（list）'),
            'algorithm_type': _prop('string', '算法类型过滤（list）'),
            'start_date': _prop('string', '创建时间下界（list，ISO 8601）'),
            'end_date': _prop('string', '创建时间上界（list，ISO 8601）'),
            'favorite': _prop('boolean', '仅当前用户收藏（list）'),
            'deleted': _prop('boolean', '仅回收站（list）'),
            'merged': _prop('boolean', '仅合并容器任务（list）'),
            'cherry_pick': _prop('boolean', '仅挑选合并容器任务（list）'),
            'merge_type': _prop('string', '合并方式快捷筛选（list）',
                                enum=['whole', 'picked']),
            'visibility': _prop('string', '可见性过滤（list）',
                                enum=['shared', 'private']),
            'stats': _prop('boolean', '返回合并容器统计块（list）'),
            'granularity': _prop('string', '趋势分桶粒度（domain_stats，默认 day）',
                                 enum=list(TASK_DOMAIN_STATS_GRANULARITIES)),
            'page': _prop('integer', '页码（list，默认 1）'),
            'per_page': _prop('integer', '每页条数（list）'),
        }, required=('action',)),
        risk='READ', permissions=('task:read',), enabled=True, kind='intent_rest'),
    IntentTool(
        name='task_diagnose',
        description=('任务失败诊断（只读聚合）：读真实执行进度 / 用例统计 / 失败用例，'
                     '并按任务拉取 ERROR / CRITICAL 日志做来源归因，输出带来源 ID 的'
                     '失败清单、日志行与重测建议。只读，不触发重跑、不改任务状态。'),
        parameters=_schema({
            'task_id': _prop('integer', '任务 ID', required=True),
            'case_id': _prop('string', '只诊断该用例（可选；不给则诊断全部失败用例）'),
            'keyword': _prop('string', '日志关键词过滤（可选）'),
        }, required=('task_id',)),
        risk='READ', permissions=('task:read', 'log:read'), enabled=True,
        kind='local'),
    IntentTool(
        name='log_diagnose',
        description=('日志只读查询与诊断：search 按级别 / 模块 / 任务 / 用例 / 时间'
                     '检索日志行，stats 取真实级别统计，diagnose 聚合错误日志的来源与'
                     '样本（带日志 ID）。不导出、不清除、不刷新。'),
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=list(LOG_DIAGNOSE_ALL_ACTIONS)),
            'keyword': _prop('string', '关键词过滤（三个动作都支持）'),
            'level': _prop('string', '日志级别（可逗号分隔多级别，如 error,critical）'),
            'module': _prop('string', '模块过滤（all = 不过滤）'),
            'category': _prop('string', '分类过滤（all = 不过滤）'),
            'task_id': _prop('integer', '任务 ID 过滤'),
            'test_case_id': _prop(
                'string', '用例 ID 过滤（search；按用例检索需同时带 task_id。'
                          'diagnose 只用它取样，级别统计不支持按用例过滤）'),
            'start_time': _prop('string', '开始时间（ISO 8601）'),
            'end_time': _prop('string', '结束时间（ISO 8601）'),
            'page': _prop('integer', '页码（search，默认 1）'),
            'per_page': _prop('integer', '每页条数（search，默认 50）'),
            'max_rows': _prop('integer',
                              f'diagnose 取样行数上限（默认 '
                              f'{LOG_DIAGNOSE_DEFAULT_MAX_ROWS}，最大 '
                              f'{LOG_DIAGNOSE_MAX_ROWS}）',
                              minimum=1, maximum=LOG_DIAGNOSE_MAX_ROWS),
        }, required=('action',)),
        risk='READ', permissions=('log:read',), enabled=True, kind='local'),
    IntentTool(
        name='dashboard_query',
        description=('首页统计只读查询：details 取用例 / 任务 / 设备 / 音频 / API / '
                     '报告 / 评估维度汇总，summary 取最近任务 / TOP 分组 / 设备在线'
                     '状态。数值原样来自接口；缓存刷新是写侧（M2），本工具不刷新。'),
        parameters=_schema({
            'action': _prop('string', '统计动作', required=True,
                            enum=list(DASHBOARD_QUERY_ACTIONS)),
        }, required=('action',)),
        risk='READ', permissions=('home:read',), enabled=True,
        kind='intent_rest'),
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
    IntentTool(
        name='audio_query',
        description=('音频只读查询：列表 / 详情 / 按 MD5 查重 / 标签 / '
                     '目录树 / 特征分析 / 质量评估 / 已配算法 / 播放历史。'
                     '字段口径与 REST /api/v1/audios 一致，缺失就是缺失，不编造数值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(AUDIO_QUERY_ACTIONS)),
            'audio_id': _prop('integer', '音频 ID（detail / features / quality / '
                                         'algorithms / playback_history 必填）'),
            'md5_list': _prop('array', 'MD5 列表（by_md5 必填）',
                              items={'type': 'string'}),
            'keyword': _prop('string', '关键词过滤（list 匹配文件名 / 原名，'
                                       'folder_tree 额外匹配 asr_text）'),
            'page': _prop('integer', '页码（list / playback_history，默认 1）'),
            'per_page': _prop('integer', '每页条数（list / playback_history）'),
            'format': _prop('string', '音频格式过滤（list / folder_tree，如 wav / mp3）'),
            'audio_type': _prop('string', '音频类型过滤（list / folder_tree，如 dry / noise）'),
            'sample_rate': _prop(('string', 'number'),
                                 '采样率过滤（list / folder_tree）。可传 48、48000、'
                                 '"48 kHz"：工具统一按 Hz 归一，list 转 kHz 精确匹配，'
                                 'folder_tree 按 Hz ±100 容差'),
            'duration': _prop('string', '时长档位过滤（list / folder_tree），'
                                        '不是任意区间',
                              enum=list(AUDIO_DURATION_BUCKETS)),
            'tags': _prop('array', '标签过滤：list 只收字符串数组（AND）；'
                                   'folder_tree 另支持 {name, mode: "or"} 对象',
                          items={'type': ['string', 'object']}),
            'direction': _prop('string', '语种方向过滤（list / folder_tree）'),
            'algorithm_type': _prop('string', '算法类型过滤（list / folder_tree）'),
            'visibility': _prop('string', '可见性过滤（list）',
                                enum=['shared', 'private']),
            'parent_path': _prop('string', '目录树父路径（folder_tree，缺省为根）'),
            'depth': _prop('integer', '目录树展开深度（folder_tree，默认 1）'),
        }, required=('action',)),
        risk='READ', permissions=('audio:read',), enabled=True, kind='intent_rest'),

    # ---------------- M1 已实现（INT-2462 评估域只读） ----------------
    IntentTool(
        name='evaluation_query',
        description=('评估只读查询：维度列表（可按分类 / 关键词过滤、分页）、'
                     '维度详情（评分口径、可见性、输入输出参数、关联算法）、'
                     '评估分类列表。字段口径与 REST /api/v1/evaluation 一致，'
                     '评分口径解释必须引用接口返回原文，不得二次计算。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(EVALUATION_QUERY_ACTIONS)),
            'dim_id': _prop('integer', '维度 ID（dimension 动作必填）'),
            'category_id': _prop('integer', '分类 ID 过滤（dimensions）'),
            'search': _prop('string', '关键词过滤（dimensions）'),
            'page': _prop('integer', '页码（dimensions，默认 1）'),
            'per_page': _prop('integer', '每页条数（dimensions）'),
        }, required=('action',)),
        risk='READ', permissions=('evaluation:read',), enabled=True,
        kind='intent_rest'),

    # ---------------- 探索 / 记忆（预留，M1 / M2 实现） ----------------
    # 权限码口径（INT-2501）：一律取 RBAC 事实源
    # （scripts/migrations/202608/seed_rbac.py）与同能力 MCP 工具
    # （mcp_registry.py）实际使用的码，多码按 OR 判定；不自己拼不存在的码。
    # memory_write / driver_propose 在 RBAC 尚无对应权限码（memory 域未建、
    # 驱动生成无码），暂保留原声明（不存在即恒拒绝，fail-closed），
    # 标「待规格」由需求规划师定码后再改。
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
        risk='WRITE', permissions=('memory:write',),  # 待规格（INT-2501）：RBAC 无 memory 域
        enabled=False, kind='reserved'),

    # ---------------- 其余业务意图工具（预留，M1 / M2 实现） ----------------
    IntentTool(
        name='audio_import', description='URL 导入、上传初始化/合并、OSS 直传确认（写）。',
        parameters=_schema({
            'action': _prop('string', '导入动作', required=True,
                            enum=['url_import', 'upload_init', 'upload_merge', 'confirm']),
            'urls': _prop('array', '音频 URL 列表', items={'type': 'string'}),
            'upload_id': _prop('string', '上传会话 ID'),
        }, required=('action',)),
        risk='WRITE', permissions=('audio:upload',), enabled=False, kind='reserved'),
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
        risk='WRITE', permissions=('tag:create', 'tag:update', 'tag:delete',
                                   'group:create', 'group:update',
                                   'group:delete'),
        enabled=False, kind='reserved'),
    IntentTool(
        name='evaluation_manage', description='维度/分类 CRUD、触发重评估（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['dimension_create', 'dimension_update',
                                  'category_create', 'category_update', 'reevaluate']),
            'body': _prop('object', '维度 / 分类字段'),
        }, required=('action',)),
        risk='WRITE', permissions=('evaluation:dim_manage',
                                   'evaluation:category_manage',
                                   'evaluation:execute'),
        enabled=False, kind='reserved'),
    IntentTool(
        name='algorithm_query',
        description=('算法配置只读查询（INT-2464）：定义 / 草稿 / 分组、设备与 API 参数、'
                     '参考参数、参数映射、用例专属参数、表单 Schema、下拉选项、'
                     '关联评估维度。字段与默认值一律以接口返回为准，不编造可选值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(ALGORITHM_QUERY_ACTIONS)),
            'algo_type': _prop('string', '算法类型（如 voice_llm；取值以 options 动作为准）'),
            'algorithm_type': _prop('string', '算法类型过滤（params / mappings / '
                                               'reference_params / case_params 用；'
                                               'definitions 不支持，只认 status / group_id）'),
            'param_id': _prop('integer', '参数 ID（param / reference_param / case_param 必填）'),
            'group_id': _prop('integer', '算法分组 ID（group 必填）'),
            'dimension_id': _prop('integer', '评估维度 ID（dimension_params 必填）'),
            'status': _prop('string', '算法定义状态过滤（definitions）',
                            enum=list(platform_contract_catalog.ALGORITHM_STATUS_VALUES)),
            'param_type': _prop('string', '参数作用域（params；缺省 device）',
                                enum=list(platform_contract_catalog.ALGORITHM_PARAM_TYPE_VALUES)),
            'api_id': _prop('integer', 'API 实例 ID（params 必须同时给 param_type=api，'
                                       '否则网关静默忽略；映射用于 API 作用域行）'),
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
        risk='WRITE', permissions=('algorithm:definition_manage',
                                   'algorithm:param_manage',
                                   'algorithm:group_manage'),
        enabled=False, kind='reserved'),
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
        name='spl_calibrate', description='SPL 映射、校准、测试音、历史（写）。',
        parameters=_schema({
            'action': _prop('string', '动作', required=True,
                            enum=['mapping', 'calibrate', 'test_tone', 'history']),
            'device_id': _prop('integer', '设备 ID'),
            'body': _prop('object', '校准参数'),
        }, required=('action',)),
        risk='WRITE', permissions=('spl:create', 'spl:update', 'spl:test_tone'),
        enabled=False, kind='reserved'),
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
        risk='WRITE', permissions=('report:read',), enabled=False, kind='reserved'),
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
        risk='WRITE', permissions=('algorithm:update',),  # 待规格（INT-2501）：RBAC 无对应码
        enabled=False, kind='reserved'),
]

INTENT_TOOL_BY_NAME: Dict[str, IntentTool] = {t.name: t for t in INTENT_TOOLS}

# 已启用的工具集合（执行前判定；预留工具返回 TOOL_NOT_ENABLED）
ENABLED_TOOLS = frozenset(t.name for t in INTENT_TOOLS if t.enabled)

# 宿主语境专用工具：REST 端点在用（用例回填 / 批量标注匹配），但 Agent 侧
# 一律不暴露 —— 不进 tool_search 索引、platform_contract 不返回、解析层拒绝。
# 理由见 AUDIO_QUERY_ACTIONS 上方注释（INT-2530 / INT-2523 P1-1）：这类批量
# 读通道不做归属 / 可见性校验，模型可借用户 Authorization 越过行级可见性。
AGENT_UNEXPOSED_MCP_TOOLS: Dict[str, str] = {
    'audio_get_by_ids': '按 ID 批量读是宿主语境通道（不做归属校验），Agent 侧不可调用',
}

# tool_search 索引：205 个 MCP 工具 + 意图工具（含 5 个预留名称）。
# MCP 与意图工具存在同名项（report_compare / report_export）：保留 MCP 条目
# （可直接调用），同名意图条目不再重复进索引，避免同一 name 出现两次。
# 宿主语境工具（AGENT_UNEXPOSED_MCP_TOOLS）不计入索引。
_MCP_NAMES = frozenset(t['name'] for t in MCP_TOOLS)

TOOL_INDEX: List[dict] = [
    {'name': t['name'], 'description': t['description'],
     'inputSchema': t['inputSchema'], 'permissions': list(t['permissions']),
     'risk': 'READ' if t['method'] == 'GET' else 'WRITE', 'kind': 'mcp'}
    for t in MCP_TOOLS if t['name'] not in AGENT_UNEXPOSED_MCP_TOOLS
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
        if isinstance(expected, (list, tuple)):
            # 联合类型（如 sample_rate 的 string | number）：任一匹配即通过
            checkers = [_TYPE_CHECKS.get(t) for t in expected]
            if not any(c is not None and c(value) for c in checkers):
                return f'参数 {name} 类型应为 {" 或 ".join(expected)}'
        else:
            checker = _TYPE_CHECKS.get(expected)
            if checker is not None and not checker(value):
                return f'参数 {name} 类型应为 {expected}'
        enum = spec.get('enum')
        if enum and value not in enum:
            return f'参数 {name} 取值必须是 {"/".join(map(str, enum))} 之一'
        minimum = spec.get('minimum')
        maximum = spec.get('maximum')
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if minimum is not None and value < minimum:
                return f'参数 {name} 不能小于 {minimum}'
            if maximum is not None and value > maximum:
                return f'参数 {name} 不能大于 {maximum}'
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
    'audio_query': AUDIO_QUERY_ACTIONS,
    'evaluation_query': EVALUATION_QUERY_ACTIONS,
    'algorithm_query': ALGORITHM_QUERY_ACTIONS,
    # log_diagnose 只有 search / stats 走 REST；diagnose 是本地下游聚合
    'log_diagnose': LOG_DIAGNOSE_ACTIONS,
    'dashboard_query': DASHBOARD_QUERY_ACTIONS,
}

# 动作级参数白名单：动作不支持的参数在工具层直接报错（服务端静默忽略）。
_ACTION_PARAM_TABLE: Dict[str, Dict[str, Tuple[str, ...]]] = {
    'task_query': TASK_QUERY_PARAMS,
    'log_diagnose': LOG_DIAGNOSE_PARAMS,
    'dashboard_query': DASHBOARD_QUERY_PARAMS,
}

# 本地工具：不直接解析为目标 REST（tool_search / platform_contract 纯本地；
# task_diagnose 与 log_diagnose.diagnose 组合多个只读接口，由 ToolGateway 执行）。
LOCAL_TOOL_NAMES = frozenset({'tool_search', 'platform_contract',
                              'task_diagnose', 'log_diagnose'})


def risk_of(name: str) -> Optional[str]:
    """工具风险：意图工具取声明值；MCP 工具 GET=READ、其余=WRITE。

    宿主语境专用 MCP 工具（``AGENT_UNEXPOSED_MCP_TOOLS``）返回 ``None``，
    与「两份注册表都查不到」同口径 —— 调用方按未注册 / 不可用 fail-closed。
    """
    tool = INTENT_TOOL_BY_NAME.get(name)
    if tool is not None:
        return tool.risk
    if name in AGENT_UNEXPOSED_MCP_TOOLS:
        return None
    mcp = get_tool(name)
    if mcp is None:
        return None
    return 'READ' if mcp['method'] == 'GET' else 'WRITE'


def _sample_rate_hz(value: Any) -> Optional[float]:
    """采样率入参归一到 Hz（数值）。无法解析返回 None。

    接受 48000 / "48000" / "48 kHz" / "48khz" / 48；无单位的纯数值 < 1000
    按 kHz 解释（与列表 REST 的 kHz 口径一致），≥ 1000 按 Hz。
    """
    if isinstance(value, bool):
        return None
    text = str(value).strip().lower().replace(' ', '')
    if not text:
        return None
    if text.endswith('khz'):
        number, multiplier = text[:-3], 1000.0
    elif text.endswith('hz'):
        number, multiplier = text[:-2], 1.0
    else:
        number, multiplier = text, None
    try:
        amount = float(number)
    except ValueError:
        return None
    if amount <= 0:
        return None
    if multiplier is not None:
        return amount * multiplier
    return amount * 1000.0 if amount < 1000 else amount


def _format_khz(hz: float) -> str:
    """Hz → 列表 REST 的 kHz 字符串口径（48000 → "48"，44100 → "44.1"）。"""
    return f'{hz / 1000:g}'


def _normalize_audio_query_arguments(action: str,
                                     merged: Dict[str, Any]) -> Optional[str]:
    """按动作归一 audio_query 参数，返回错误文本或 None。

    - 动作不支持的参数直接拒绝（服务端会静默忽略，放过去等于返回全量）；
    - ``sample_rate`` 统一归一：list 发 kHz 字符串，folder_tree 发 Hz 整数；
    - ``duration`` 只接受档位（short / medium / long）；
    - ``tags`` 在 list 只接受字符串（AND），对象 OR 只在 folder_tree 有效。
    """
    allowed = set(AUDIO_QUERY_PARAMS.get(action, ()))
    allowed |= set(required_for_action('audio_query', action))
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return f'action={action} 不支持参数：{"、".join(unknown)}'

    if merged.get('sample_rate') is not None:
        hz = _sample_rate_hz(merged['sample_rate'])
        if hz is None:
            return (f'参数 sample_rate 无法解析：{merged["sample_rate"]}'
                    '（示例：48、48000、48 kHz）')
        merged['sample_rate'] = _format_khz(hz) if action == 'list' else int(hz)

    duration = merged.get('duration')
    if duration is not None and duration not in AUDIO_DURATION_BUCKETS:
        return (f'参数 duration 取值必须是 '
                f'{"/".join(AUDIO_DURATION_BUCKETS)} 之一（时长档位）')

    tags = merged.get('tags')
    if tags:
        for tag in tags:
            if isinstance(tag, dict):
                if action == 'list':
                    return ('参数 tags 在 list 只支持字符串数组（AND）；'
                            'OR 语义请用 folder_tree')
                if not str(tag.get('name') or '').strip():
                    return '参数 tags 对象必须含非空 name'
    return None


def _normalize_algorithm_query_arguments(action: str,
                                        merged: Dict[str, Any]
                                        ) -> Optional[str]:
    """按动作校验 algorithm_query 参数，返回错误文本或 None。

    网关查询 Schema 基类 ``extra='ignore'``：不认识的参数被静默丢弃，
    不会报错。工具层必须拦下「传了但不会生效」的组合，否则模型会把
    算法级 / 未过滤的结果当成目标作用域的回答。

    - ``definitions``：网关只认 ``status`` / ``group_id``，``algorithm_type``
      静默无效（``/definitions?algorithm_type=asr`` 仍返回全量）；
    - ``params``：``api_id`` 只在 ``param_type=api`` 时生效，``device_id``
      只在 ``param_type=device`` 时生效（网关对后者的冲突组合直接 400）。
    """
    if action == 'definitions' and merged.get('algorithm_type') is not None:
        supported = ' / '.join(ALGORITHM_DEFINITIONS_FILTERS)
        return (f'action=definitions 不支持 algorithm_type 过滤（网关只支持 {supported}，'
                '其余参数会被静默忽略）；需要按算法类型过滤请对返回行自行筛选')

    if action == 'params':
        param_type = merged.get('param_type')
        if merged.get('api_id') is not None and param_type != 'api':
            current = f'param_type={param_type}' if param_type else '未传 param_type'
            return ('参数 api_id 只在 param_type=api 时生效（当前 '
                    f'{current}），网关会静默忽略 api_id 并返回算法级原始行。'
                    '正确用法：param_type=api&api_id=<id>（可带 algorithm_type）')
        if merged.get('device_id') is not None and param_type not in (None, 'device'):
            return (f'参数 device_id 只支持 param_type=device（当前 param_type={param_type}）。'
                    '查 API 实例作用域请用 param_type=api&api_id=<id>')
    return None


def _normalize_action_arguments(name: str, action: str,
                               merged: Dict[str, Any]) -> Optional[str]:
    """按动作参数白名单拒绝「传了但不会生效」的参数。

    网关查询 Schema 基类 ``extra='ignore'``：不认识的参数被静默丢弃，
    不会报错。放过去会让模型把全量结果当成过滤结果（INT-2461）。
    """
    allowed = set(action_params(name, action) or ())
    unknown = sorted(key for key in merged if key not in allowed)
    if unknown:
        return (f'action={action} 不支持参数：{"、".join(unknown)}'
                '（网关会静默忽略这些参数）')
    return None


def action_params(name: str, action: str) -> Optional[Tuple[str, ...]]:
    """动作级参数白名单（含该动作的必填参数）；无此工具 / 动作返回 None。

    没有白名单的意图工具（audio_query / algorithm_query / report_query 等）
    返回 None，由各自的归一函数处理。
    """
    table = _ACTION_PARAM_TABLE.get(name)
    if table is None or action not in table:
        return None
    return tuple(table[action]) + required_for_action(name, action)


def _normalize_task_query_arguments(action: str,
                                    merged: Dict[str, Any]) -> Optional[str]:
    error = _normalize_action_arguments('task_query', action, merged)
    if error:
        return error
    granularity = merged.get('granularity')
    if granularity is not None and \
            granularity not in TASK_DOMAIN_STATS_GRANULARITIES:
        return (f'参数 granularity 取值必须是 '
                f'{"/".join(TASK_DOMAIN_STATS_GRANULARITIES)} 之一')
    return None


def _normalize_log_diagnose_arguments(action: str,
                                      merged: Dict[str, Any]) -> Optional[str]:
    """动作参数白名单；``max_rows`` 的上下界由参数 Schema 的
    minimum / maximum 统一校验（validate_arguments，本地 diagnose 同样经过）。"""
    return _normalize_action_arguments('log_diagnose', action, merged)


def resolve_rest_call(name: str, arguments: Dict[str, Any]
                      ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把意图工具 / 长尾 MCP 工具解析为 ``(MCP 工具, 合并参数, 错误文本)``。

    - ``task_query`` / ``report_query`` / ``evaluation_query``：按 ``action``
      映射到对应 MCP 只读工具，去掉 ``action`` 后其余参数原样透传（路径 /
      查询 / body 由共享构造器决定）；
    - 其他 MCP 工具名（tool_search 命中后直接调用）：原样透传参数；
    - 未知名称或动作非法：返回错误文本，由 ToolGateway 收敛为普通失败结果。
    """
    mapping = _REST_ACTION_MAP.get(name)
    if mapping is not None:
        action = arguments.get('action')
        if name == 'log_diagnose' and action in LOG_DIAGNOSE_LOCAL_ACTIONS:
            return None, None, (
                'action=diagnose 由本地日志聚合执行（ToolGateway 组合 log_stats + '
                'log_list），不解析为目标 REST')
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
        if mcp['name'] in AGENT_UNEXPOSED_MCP_TOOLS:  # pragma: no cover - 同上
            return None, None, (
                f'工具 {mcp["name"]} 不在 Agent 可用通道内：'
                f'{AGENT_UNEXPOSED_MCP_TOOLS[mcp["name"]]}')
        merged = {k: v for k, v in arguments.items() if k != 'action'}
        if name == 'audio_query':
            normalize_error = _normalize_audio_query_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'algorithm_query':
            normalize_error = _normalize_algorithm_query_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'task_query':
            normalize_error = _normalize_task_query_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'log_diagnose':
            normalize_error = _normalize_log_diagnose_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'dashboard_query':
            normalize_error = _normalize_action_arguments(name, action, merged)
            if normalize_error:
                return None, None, normalize_error
        return mcp, merged, None
    if name in AGENT_UNEXPOSED_MCP_TOOLS:
        return None, None, (
            f'工具 {name} 不在 Agent 可用通道内：'
            f'{AGENT_UNEXPOSED_MCP_TOOLS[name]}')
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
    if query in {t['name'] for t in MCP_TOOLS} \
            and query not in AGENT_UNEXPOSED_MCP_TOOLS:
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
    'ACTION_REQUIRED', 'AGENT_UNEXPOSED_MCP_TOOLS', 'ALGORITHM_QUERY_ACTIONS',
    'AUDIO_QUERY_ACTIONS', 'CONDITIONAL_REQUIRED', 'DASHBOARD_QUERY_ACTIONS',
    'DASHBOARD_QUERY_PARAMS', 'ENABLED_TOOLS', 'EVALUATION_QUERY_ACTIONS',
    'INTENT_TOOL_BY_NAME', 'INTENT_TOOLS', 'IntentTool',
    'LOCAL_TOOL_NAMES', 'LOG_DIAGNOSE_ACTIONS', 'LOG_DIAGNOSE_ALL_ACTIONS',
    'LOG_DIAGNOSE_DEFAULT_MAX_ROWS', 'LOG_DIAGNOSE_LOCAL_ACTIONS',
    'LOG_DIAGNOSE_MAX_ROWS', 'LOG_DIAGNOSE_PARAMS',
    'LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS', 'MCP_TOOLS',
    'REPORT_QUERY_ACTIONS', 'TASK_DOMAIN_STATS_GRANULARITIES',
    'TASK_QUERY_ACTIONS', 'TASK_QUERY_PARAMS', 'TOOL_INDEX',
    'TOOL_INDEX_BY_NAME', 'action_params', 'conditional_required',
    'platform_contract',
    'required_for_action', 'resolve_rest_call', 'risk_of', 'tool_search',
    'validate_arguments',
]
