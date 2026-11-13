# -*- coding: utf-8 -*-
"""意图级工具注册表 —— 内部 Agent 的唯一事实源（方案 §6.1，INT-2453）。

按用户意图分组，不按 REST 1:1。全表 31 个（含 ``tool_search``、2 个记忆工具、
3 个探索工具；业务意图工具 25 个），与方案 §6.1 表逐条对应。

本卡（M0）实现 3 个业务意图工具 + ``tool_search``，M1 音频域卡（INT-2458）
追加 ``audio_query``，评估域卡（INT-2462）追加 ``evaluation_query``，
算法域卡（INT-2464）追加 ``algorithm_query``，设备 / SPL 域卡（INT-2459）
追加 ``device_query``（SPL 只读是该工具的子集，见 ``device_tools``），
报告域卡（INT-2463）扩全 ``report_query`` 并启用 ``report_compare``：

- ``platform_contract``：平台口径（服务 / 接口前缀 / 枚举 / 权限码 / 工具 Schema）；
- ``task_query``：任务只读子集（映射 MCP ``task_*`` 只读工具）；
- ``report_query``：报告只读子集（映射 MCP ``report_*`` 只读工具）；
- ``report_compare``：多报告 / 二次对比与趋势（只读；本地组合，不生成平台报告）；
- ``audio_query``：音频只读子集（映射 MCP ``audio_*`` 只读工具）；
- ``evaluation_query``：评估维度 / 分类只读子集（映射 MCP ``evaluation_*`` 只读工具）；
- ``algorithm_query``：算法定义 / 参数 / 映射 / 表单 Schema 只读子集（映射 MCP ``algorithm_*`` 只读工具）；
- ``memory_search`` / ``memory_write``：文件式长期记忆（INT-2490，§8.6）；
  检索走 ``rg``、写入需审批，路径由服务端按 tenant/owner 构造；两项都是
  ``kind='local'``，不经 REST 回源；
- ``tool_search``：对 205 个 MCP 工具 + 意图工具建索引，按关键词返回 Schema。
  其中宿主语境专用工具（``AGENT_UNEXPOSED_MCP_TOOLS``，当前为
  ``audio_get_by_ids``）不进索引、不可被 Agent 调用（INT-2530）。

M1 各域卡按域启用自己的只读意图工具（已完成：``audio_query`` INT-2458、
``evaluation_query`` INT-2462、``algorithm_query`` INT-2464、
``device_query`` INT-2459 —— 含 SPL 只读子集、
``testcase_query`` / ``testcase_generate`` INT-2460、
``task_query`` / ``task_diagnose`` / ``log_diagnose`` / ``dashboard_query``
INT-2461、``report_query`` / ``report_compare`` INT-2463）；
每个域工具 = 动作 → MCP 只读工具的映射，REST 路径 / 查询参数
仍由 ``mcp_registry`` 的共享构造器决定，不复制 Schema。
用例域少量只读路由（统计 / 轮次参考参数 / 导出作业状态 / 刷新状态）不在
外部 MCP 表里，映射到 ``testcase_tools.TESTCASE_READ_TOOLS``（同形工具项）。

``task_diagnose`` / ``log_diagnose.diagnose`` 是本地只读聚合：由 ToolGateway
用同一份 MCP 定义组合多个只读接口，纯函数汇总在
``shared/agent_tools/diagnostics.py``，输出带来源 ID，不估算数值。

``report_compare`` 是唯一的**本地组合**域工具（``kind='local'``，与
``tool_search`` / ``platform_contract`` 同层）：平台的对接口径
（``POST /reports/compare`` / ``POST /reports/secondary-compare``）会**落库生成
新报告**，属写操作，不能作为只读工具暴露；本工具改为按报告 ID 逐个读
``GET /reports/{id}`` 的权威字段并排列出，对比结论由模型基于返回原文叙述，
数值不重算、不落报告（大结果由上下文压缩落 ``context_tool_result`` artifact）。

M2 写意图（``testcase_write`` / ``tag_group_manage`` / ``task_run``，INT-2468）
已启用：动作表 / 参数白名单 / 条件必填 / 动作级权限与风险在
``testcase_write_tools`` / ``tag_group_tools`` / ``task_write_tools``，本文件
只做分发（``WRITE_RESOLVERS``）。写工具一律经 M2 基座（INT-2466）的
提案 → 审批 → 幂等执行，工具层本身不执行任何未经审批的写；删除类动作在动作
层记 ``DESTRUCTIVE``（``risk_for``）。

其余意图工具在本注册表**预留名称与 Schema**（``enabled=False``），调用返回
``TOOL_NOT_ENABLED``；实现分别归 M1 / M2 各域卡。预留名称进入 Skill
allowed-tools 校验与 tool_search 索引，启动时不会出现 ``UNKNOWN_TOOL``。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.agent_tools import contract as platform_contract_catalog
from shared.agent_tools import device_tools
from shared.agent_tools import tag_group_tools
from shared.agent_tools import task_write_tools
from shared.agent_tools import testcase_tools as case_tools
from shared.agent_tools import testcase_write_tools as case_write_tools
from shared.agent_tools.diagnostics import (
    DEFAULT_LOG_ROWS as LOG_DIAGNOSE_DEFAULT_MAX_ROWS,
    MAX_LOG_ROWS as LOG_DIAGNOSE_MAX_ROWS,
)
from shared.agent_tools.mcp_registry import TOOLS as MCP_TOOLS, get_tool
from shared.agent_tools.pagination import (
    PAGE_MIN,
    PER_PAGE_MAX,
    check_page_bounds,
)
from shared.models.common_enums import DeviceType

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


def _page_prop(description: str) -> dict:
    """``page`` 参数 Schema：下界与工具层共用 ``pagination.PAGE_MIN``。"""
    return _prop('integer', description, minimum=PAGE_MIN)


def _per_page_prop(description: str) -> dict:
    """``per_page`` 参数 Schema：上下界与工具层共用 ``pagination`` 常量。"""
    return _prop('integer', f'{description}，最大 {PER_PAGE_MAX}',
                 minimum=PAGE_MIN, maximum=PER_PAGE_MAX)


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

# 报告只读动作 → MCP 工具名（INT-2463 扩全字段）
#
# 覆盖卡面「三类报告事实 / 指标 / 用例 / 统计 / 进度 / 页签计数」：
# list / detail / by_task 取报告事实与指标矩阵，cases / cases_search 取用例与
# 异常下钻，case_averages 取用例级指标均值，statistics 取维度统计，
# tab_counts 取页签计数，progress 取生成进度。
#
# 刻意不放进来：
# - ``report_statistics_trend``：趋势按方案 §4.3 / §6.1 归 ``report_compare``
#   的 ``trend`` 动作（同一个 MCP 工具不挂两个意图动作，避免双口径）；
# - ``report_statistics_report`` / ``report_export_get`` / ``report_export``：
#   返回二进制文件流（csv/excel/pdf/html），工具层只承载 JSON，二进制通道
#   由产品页下载（mcp_registry 顶部的「非 JSON 文本通道」边界）；
# - ``report_cases_logs`` / ``logs/download``：用例日志下载同上；
# - ``report_compare`` / ``report_secondary_compare``：POST 会落库生成新报告，
#   属写操作，Agent 侧改走只读组合工具 ``report_compare``（见下方注释）。
REPORT_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'report_list',
    'detail': 'report_get',
    'by_task': 'report_by_task',
    'tab_counts': 'report_tab_counts',
    'statistics': 'report_statistics',
    'progress': 'report_progress',
    'cases': 'report_cases',
    'cases_search': 'report_cases_search',
    'case_averages': 'report_case_averages',
}

# 报告只读动作的可用参数（动作独立口径）。
# 动作不支持的参数在工具层直接报错：网关查询 Schema 基类 ``extra='ignore'``，
# 传错参数会被**静默丢弃**并返回全量，模型会把「全量」当成「过滤结果」
# （INT-2529 / INT-2524 同型教训）。
#
# 参数名逐字对齐网关查询 Schema（api_gateway/schemas/report.py）：
# - ``ReportListQuery``：page / per_page / keyword / report_type（别名 type）/
#   status / task_id / algorithm_type / start_time / end_time / favorite /
#   deleted；``sort_by`` / ``order`` 网关不往 gRPC 传，故不暴露；
# - ``ReportCaseListQuery``：page / per_page / keyword / category；
#   **``tags`` 不暴露**——网关按查询串取到的是字符串，pydantic 要求 List[str]，
#   带 tags 恒 400（实测），带标签过滤请走 ``cases_search``（JSON body）；
# - ``ReportStatisticsQuery``：dimension / start_time / end_time / algorithm_type；
# - ``ReportSearchCasesRequest`` / ``GetCaseAveragesRequest``：POST body，
#   字段名与 REST 逐字一致。
REPORT_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'list': ('page', 'per_page', 'keyword', 'report_type', 'status', 'task_id',
             'algorithm_type', 'start_time', 'end_time', 'favorite', 'deleted'),
    'detail': (),
    'by_task': (),
    'tab_counts': ('keyword', 'favorite', 'deleted'),
    'statistics': ('dimension', 'start_time', 'end_time', 'algorithm_type'),
    'progress': (),
    'cases': ('report_id', 'page', 'per_page', 'keyword', 'category'),
    'cases_search': ('report_id', 'keyword', 'category', 'categories', 'tags',
                     'include_untagged', 'metrics', 'sort_by', 'sort_metric',
                     'sort_resource', 'sort_order', 'page', 'per_page'),
    'case_averages': ('report_id', 'task_id', 'category', 'categories', 'tags',
                      'include_untagged'),
}

# 分页边界：网关对 page=0 与超大 per_page **不报错**（实测 page=0 返回首页、
# per_page=1000 一次返回全量），放过去会让模型用一次调用拉全表。
# 常量集中在 ``shared.agent_tools.pagination``（INT-2552 起全部查询类意图工具
# 与 Schema 共用同一份）；这里保留报告域先落地时的旧名，指向同一对象。
REPORT_PAGE_MIN = PAGE_MIN
REPORT_PER_PAGE_MAX = PER_PAGE_MAX

# 报告对比的只读动作（INT-2463，本地组合实现，见模块 docstring）
# - ``compare``：按报告 ID 逐个读权威字段并排（任意报告类型）；
# - ``secondary_compare``：二次对比，源报告必须是平台已有的对比 / 二次对比报告；
# - ``trend``：统计趋势序列（映射 MCP ``report_statistics_trend``，GET 只读）。
REPORT_COMPARE_ACTIONS: Tuple[str, ...] = (
    'compare', 'secondary_compare', 'trend')

REPORT_COMPARE_TREND_PARAMS: Tuple[str, ...] = (
    'trend_type', 'metric', 'start_time', 'end_time')

# 一次并排的报告数量上限：平台对比报告按 2~N 个任务聚合，这里取 10 作为
# 单次上下文可承载的上限，超过请分批（多轮对比结果由 artifact 承载）。
REPORT_COMPARE_MAX_REPORTS = 10
REPORT_COMPARE_MIN_REPORTS = 2

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

# 用例只读动作 → 工具名（INT-2460）。
# list / detail 直接复用 MCP 只读工具；统计 / 轮次参考参数 / 导出作业状态 /
# 刷新状态在网关有只读路由但外部 MCP 表未登记，取
# ``testcase_tools.TESTCASE_READ_TOOLS``（同形工具项、同一构造器）。
TESTCASE_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'testcase_list',
    'detail': 'testcase_get',
    'stats': 'testcase_stats',
    'round_ref_params': 'testcase_round_ref_params',
    'export_status': 'testcase_export_job_status',
    'refresh_status': 'testcase_refresh_status',
}

# 各动作可用的可选参数（动作独立口径）。网关 TestCaseListQuery 是
# ``extra='ignore'``，传不认识的参数不会报错、只会静默返回全量——工具层必须先拒。
# 注意：用例列表**没有** ``status`` 过滤（MCP ``testcase_list`` 声明的 ``status``
# 在网关被静默丢弃），状态相关属任务域；``view=tag`` 的标签聚合视图输出是
# camelCase 的另一套字段，本工具不收，标签口径走 tag-group Skill。
TESTCASE_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'list': ('page', 'per_page', 'keyword', 'tag', 'group_id', 'algorithm_type',
             'dimension_id', 'lab_id', 'visibility', 'favorite', 'only_deleted',
             'include_deleted'),
    'detail': (),
    'stats': (),
    'round_ref_params': (),
    'export_status': (),
    'refresh_status': (),
}

# 用例列表可见性取值（网关 TestCaseListQuery.visibility，空=全部）
TESTCASE_VISIBILITY_VALUES: Tuple[str, ...] = ('shared', 'private')

# 用例可见性与回收站口径的接口取值见 ``contract.ENUMS``（单一事实源）。

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
        'cases_search': ('report_id',),
        # case_averages 是「report_id 或 task_id 二选一」，由
        # ``_normalize_report_query_arguments`` 做 one-of 校验：
        # 单列 report_id 会把「按任务查均值」误判为缺参。
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
    'testcase_query': {
        'detail': ('tc_id',),
        'round_ref_params': ('tc_id', 'round_number'),
        'export_status': ('task_id',),
        'refresh_status': ('task_id',),
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
    # 设备 / SPL 只读动作（INT-2459）；动作表、参数白名单与动作级权限
    # 集中在 ``device_tools``，此处只登记条件必填，避免两套口径。
    'device_query': device_tools.DEVICE_QUERY_REQUIRED,
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
            'page': _page_prop('页码（list，默认 1）'),
            'per_page': _per_page_prop('每页条数（list）'),
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
            'page': _page_prop('页码（search，默认 1）'),
            'per_page': _per_page_prop('每页条数（search，默认 50）'),
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
        description=('报告只读查询：列表（类型 / 状态 / 任务 / 算法 / 时间 / 收藏 / '
                     '回收站过滤）、详情（指标矩阵、设备 / API 统计、用例分类统计）、'
                     '按任务查、页签计数、维度统计、生成进度、用例列表 / 用例搜索、'
                     '用例指标均值。字段口径与 REST /api/v1/reports 一致，'
                     '数值一律取接口返回值，不重新计算、不四舍五入。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(REPORT_QUERY_ACTIONS)),
            'report_id': _prop('integer', '报告 ID（detail / progress / cases / '
                                          'cases_search 必填；case_averages 需与 '
                                          'task_id 二选一）'),
            'task_id': _prop('integer', '任务 ID（by_task 必填；case_averages 需与 '
                                        'report_id 二选一；list 可按任务过滤）'),
            'keyword': _prop('string', '关键词过滤（list / tab_counts / cases / '
                                       'cases_search）'),
            'report_type': _prop('string', '报告类型过滤（list）',
                                 enum=list(platform_contract_catalog.REPORT_TYPE_VALUES)),
            'status': _prop('string', '发布状态过滤（list），只表达 draft / published；'
                                      '生成进度看 progress 动作',
                            enum=list(platform_contract_catalog.REPORT_STATUS_VALUES)),
            'algorithm_type': _prop('string', '算法类型过滤（list / statistics）'),
            'start_time': _prop('string', '起始时间过滤（list / statistics，如 '
                                          '2026-10-01 或 ISO 8601）'),
            'end_time': _prop('string', '结束时间过滤（list / statistics，如 '
                                        '2026-11-30 或 ISO 8601）'),
            'favorite': _prop('boolean', '仅当前用户收藏（list / tab_counts）'),
            'deleted': _prop('boolean', '仅回收站软删除项（list / tab_counts）'),
            'dimension': _prop('string', '统计维度（statistics）',
                               enum=list(platform_contract_catalog.REPORT_STATISTICS_DIMENSIONS)),
            'page': _page_prop('页码，从 1 开始（list / cases / cases_search）'),
            'per_page': _per_page_prop('每页条数（list / cases / cases_search）'),
            'category': _prop('string', '用例分类过滤（cases / cases_search / '
                                        'case_averages；单分类）'),
            'categories': _prop('array', '用例分类多选过滤（cases_search / '
                                         'case_averages，与 category 并存时按 IN 过滤）',
                                items={'type': 'string'}),
            'tags': _prop('array', '标签过滤（cases_search / case_averages）；'
                                   'GET cases 不支持 tags（网关按字符串校验会 400）',
                          items={'type': 'string'}),
            'include_untagged': _prop('boolean', '未打标签用例口径（cases_search / '
                                                 'case_averages）：与 tags 同用时取'
                                                 '「命中标签 + 未打标签」并集，单独使用时'
                                                 '等于「只看未打标签用例」'),
            'metrics': _prop('array', '按指标名筛选用例（cases_search，用例 metrics 中'
                                      '包含该指标名）', items={'type': 'string'}),
            'sort_by': _prop('string', '用例排序字段（cases_search）',
                             enum=['name', 'category', 'createdat', 'metric']),
            'sort_metric': _prop('string', '按指标排序时的指标名（cases_search，'
                                           'sort_by=metric 时用）'),
            'sort_resource': _prop('string', '按指标排序时限定资源（cases_search，'
                                             '设备 / API 名，缺省聚合所有资源）'),
            'sort_order': _prop('string', '排序方向（cases_search）',
                                enum=['asc', 'desc']),
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
            'page': _page_prop('页码（list / playback_history，默认 1）'),
            'per_page': _per_page_prop('每页条数（list / playback_history）'),
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
            'page': _page_prop('页码（dimensions，默认 1）'),
            'per_page': _per_page_prop('每页条数（dimensions）'),
        }, required=('action',)),
        risk='READ', permissions=('evaluation:read',), enabled=True,
        kind='intent_rest'),

    # ---------------- M1 已实现（INT-2460 用例 / 标签域只读） ----------------
    IntentTool(
        name='testcase_query',
        description=('用例只读查询：列表（关键词 / 标签 / 分组 / 算法 / 维度 / '
                     '实验室 / 可见性 / 收藏 / 回收站过滤、分页）、详情（含轮次配置 '
                     'config.rounds、评估维度、音频、参数）、统计、指定轮次参考参数、'
                     '导出作业状态、参考参数刷新状态。字段口径与 REST '
                     '/api/v1/testcases 一致，缺失就是缺失，不编造用例 ID、轮次或数值。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(TESTCASE_QUERY_ACTIONS)),
            'tc_id': _prop('string', '用例 ID（detail / round_ref_params 必填）'),
            'round_number': _prop('integer', '轮次号，从 1 开始（round_ref_params 必填）'),
            'task_id': _prop('string', '作业 / 刷新任务 ID（export_status / '
                                       'refresh_status 必填）'),
            'page': _page_prop('页码（list，默认 1）'),
            'per_page': _per_page_prop('每页条数（list）'),
            'keyword': _prop('string', '关键词过滤（list，匹配用例名 / 描述）'),
            'tag': _prop('string', '标签名过滤（list）'),
            'group_id': _prop('string', '用例分组 ID 过滤（list）'),
            'algorithm_type': _prop('string', '算法类型过滤（list）'),
            'dimension_id': _prop('integer', '评估维度 ID 过滤（list）'),
            'lab_id': _prop('integer', '实验室 ID 过滤（list，含通用用例）'),
            'visibility': _prop('string', '可见性过滤（list）',
                                enum=list(TESTCASE_VISIBILITY_VALUES)),
            'favorite': _prop('boolean', '仅当前用户收藏（list）'),
            'only_deleted': _prop('boolean', '仅回收站（list）'),
            'include_deleted': _prop('boolean', '包含回收站（list）'),
        }, required=('action',)),
        risk='READ', permissions=('testcase:read',), enabled=True,
        kind='intent_rest'),
    IntentTool(
        name='testcase_generate',
        description=('由音频标注推导用例草案（**只读生成，不落库**）：复用音频标注的 '
                     '轮次 / 声压 / 播放设备与算法用例参数口径，产出可直接照抄到'
                     '「新建用例」的草案（含 config.rounds、algorithm_params、'
                     'evaluation.dimensions）。引用资源（算法类型 / 评估维度 / '
                     '播放设备 / 分组）先回源校验存在性，非法参数显式失败。草案'
                     '没有真实用例 ID，返回后不会写库；确认后创建请用 '
                     'testcase_write（提案 + 审批）。'),
        parameters=_schema({
            'audio_ids': _prop('array', '源音频 ID 列表（必填，单次最多 '
                                       f'{case_tools.MAX_GENERATE_AUDIOS} 条）',
                               items={'type': 'integer'}),
            'algorithm_type': _prop('string', '算法类型（用于挑选用例参数与标注 code）'),
            'device_type': _prop('string', '目标设备类型（缺省 http_api）',
                                 enum=[d.value for d in DeviceType]),
            'dimension_ids': _prop(
                'array', '评估维度列表：正整数 ID 或 {id, round_scope?, '
                         'device_type?} 对象（逐项校验存在性，非法项显式失败）',
                items={'type': ['integer', 'object']}),
            'dimension_round_scope': _prop(
                'string', '评估维度口径：single/per_round 逐轮、multi 多轮整体',
                enum=list(case_tools.ROUND_SCOPES)),
            'group_id': _prop('string', '目标用例分组 ID（校验存在性，仅回显不落库）'),
            'spl': _prop('number', '播放声压（显式值覆盖标注；缺省取标注，'
                                   '标注没有按 65.0）'),
            'playback_device_id': _prop(
                'integer', '播放设备 ID（显式值覆盖标注，校验存在性；缺省取标注）'),
            'inherit_tags': _prop('boolean', '是否继承音频标签（默认 true）'),
        }, required=('audio_ids',)),
        risk='READ', permissions=('testcase:read',), enabled=True,
        kind='local'),

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
    # ---------------- M1 已实现（INT-2490 长期记忆：文件树 + rg，无向量 RAG） ----------------
    # 权限口径：记忆域没有 RBAC 权限码（INT-2501 待规格名单），且隔离由服务端
    # 按登录身份构造路径 + 审批占位保证，因此两项都只要求登录（permissions 为空）。
    # 模型入参里没有任何 tenant / owner / 路径字段（§8.6.1）。
    IntentTool(
        name='memory_search',
        description=('检索长期记忆与 Skill references（rg 关键词检索，'
                     'tenant / owner 严格隔离，无向量 RAG）。只能看到调用者自己的'
                     '用户偏好与项目记忆；跨用户 / 跨租户返回空。细节一律以检索结果为准，'
                     '不编造记忆内容。'),
        parameters=_schema({
            'query': _prop('string', '检索关键词（按字面匹配，不是正则）',
                           required=True),
            'scope': _prop('string', '检索范围：USER 全部个人记忆 / '
                                     'PROJECT 单个项目 / SKILL_REFERENCES 共享只读知识',
                           enum=['USER', 'PROJECT', 'SKILL_REFERENCES']),
            'project_id': _prop('string', '项目标识（scope=PROJECT 必填）'),
            'limit': _prop('integer', '返回条数上限（受服务端上限约束）'),
        }, required=('query',)),
        risk='READ', permissions=(), enabled=True, kind='local'),
    IntentTool(
        name='memory_write',
        description=('写入用户偏好或项目规则（需审批）。只生成待审批提案，'
                     '审批通过后才会落盘；敏感信息（Key / 密码 / token / PII）'
                     '会被拦截或脱敏。只能写调用者自己的记忆目录。'),
        parameters=_schema({
            'section': _prop('string', '写入区段：用户偏好 / 项目规则 / 话题记录',
                             required=True,
                             enum=['USER_PROFILE', 'PROJECT_MEMORY', 'TOPIC']),
            'content': _prop('string', '要记住的内容（用户明确要求记住的事实，'
                                       '不得写入模型猜测）', required=True),
            'project_id': _prop('string', '项目标识（PROJECT_MEMORY / TOPIC 必填）'),
            'reason': _prop('string', '为什么值得长期记住（进审批信息，不落正文）'),
        }, required=('section', 'content')),
        risk='WRITE', permissions=(), enabled=True, kind='local'),

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
    # ---------------- M2 已实现（INT-2468 用例 / 标签 / 任务写意图） ----------------
    IntentTool(
        name='testcase_write',
        description=('用例写操作（需提案 + 审批，批准后才执行）：create 新建、'
                     'update 修改、copy 复制、delete 删除（软删进回收站，按破坏性'
                     '动作审批）、tag 给单条用例加 / 去标签。用例字段一律用 body '
                     '透传网关用例载荷（字段口径同 testcase-authoring 的字段表）；'
                     '加标签对不存在的标签名会由服务端自动登记标签字典'
                     '（get-or-create，与产品页一致），要指定颜色 / 分类 / 可见性'
                     '请先用 tag_group_manage 建标签。删除后可到产品回收站恢复，'
                     '本工具不提供恢复 / 彻底删除。'),
        parameters=_schema({
            'action': _prop('string', '写动作', required=True,
                            enum=list(case_write_tools.ACTION_NAMES)),
            'tc_id': _prop('string', '用例 ID（update / copy / delete / tag 必填）'),
            'body': _prop('object', '用例字段：create 至少含 name 与 group_id（或 group）；'
                                    'update 只放要改的字段；形状同 REST 创建 / 修改载荷'
                                    '（snake_case）'),
            'tag_mode': _prop('string', '打标签方式（tag 必填）',
                              enum=list(case_write_tools.TAG_MODES)),
            'tags': _prop('array', '标签名数组（tag 必填、非空；不存在的名字会被'
                                   '服务端自动登记为标签）', items={'type': 'string'}),
        }, required=('action',)),
        risk='WRITE',
        permissions=('testcase:create', 'testcase:update', 'testcase:copy',
                     'testcase:delete'),
        enabled=True, kind='intent_rest'),
    IntentTool(
        name='tag_group_manage',
        description=('标签与用例分组写操作（需提案 + 审批）：target_kind=tag / group '
                     '的 create / update / delete，以及 batch_tag 批量打标'
                     '（add_tags / remove_tags / rename_tag）。删除与 rename_tag 按'
                     '破坏性动作审批；分组下仍有未删除用例时 delete 必须显式 '
                     'cascade=true（会连带把分组下的用例软删进回收站），否则接口'
                     '拒绝。add_tags 对不存在的标签名由服务端自动登记标签字典'
                     '（get-or-create，与产品页一致）。'),
        parameters=_schema({
            'action': _prop('string', '写动作', required=True,
                            enum=list(tag_group_tools.ACTION_NAMES)),
            'target_kind': _prop('string', '目标类型（create / update / delete 必填）',
                                 enum=list(tag_group_tools.TARGET_KINDS)),
            'tag_id': _prop('integer', '标签 ID（target_kind=tag 的 update / delete 必填）'),
            'group_id': _prop('string', '分组 ID（UUID 字符串；target_kind=group 的 '
                                        'update / delete 必填）'),
            'body': _prop('object', '标签 / 分组字段：create 至少含 name；update 只放'
                                    '要改的字段（snake_case）'),
            'cascade': _prop('boolean', '是否级联删除（delete；分组下有用例时缺省会'
                                        '被接口拒绝）'),
            'batch_action': _prop('string', '批量打标子动作（batch_tag 必填）',
                                  enum=list(tag_group_tools.BATCH_ACTIONS)),
            'ids': _prop('array', '用例 ID 数组（add_tags / remove_tags 必填）',
                         items={'type': 'string'}),
            'tags': _prop('array', '标签名数组（add_tags / remove_tags 必填）',
                          items={'type': 'string'}),
            'old_tag_name': _prop('string', '原标签名（rename_tag 必填）'),
            'new_tag_name': _prop('string', '新标签名（rename_tag 必填）'),
        }, required=('action',)),
        risk='WRITE',
        permissions=('tag:create', 'tag:update', 'tag:delete',
                     'group:create', 'group:update', 'group:delete',
                     'testcase:update', 'testcase:delete'),
        enabled=True, kind='intent_rest'),
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
    # ---------------- M1 已实现（INT-2459 设备与 SPL 域只读） ----------------
    # SPL 没有独立意图工具（§6.1 只有写工具 spl_calibrate）：物理域
    # /api/v1/spl 与数字域 /api/v1/digital-spl 的只读端点都是本工具的动作，
    # 目标定义见 ``device_tools``。工具级 permission 是三个域的并集（只决定
    # 可见性），调用时按 action 收窄到 device:read / spl:read /
    # digital_spl:read（``permissions_for``）。
    IntentTool(
        name='device_query',
        description=('设备与 SPL 只读查询：被测设备列表 / 详情 / 分组 / 分组详情 / '
                     '状态 / 状态历史（含健康检查事件）/ 告警 / 告警规则 / '
                     '可用序列号 / 驱动关键词；SPL 物理域与数字域的映射 / 统计 / '
                     '按设备或 API 查 / 校准历史 / 最新校准点集（测试音校准点）。'
                     '只读，不连接 / 重启 / 扫描 / 安装设备，不执行校准、不播放测试音。'),
        parameters=_schema({
            'action': _prop('string', '查询动作', required=True,
                            enum=list(device_tools.DEVICE_QUERY_ACTION_NAMES)),
            'device_id': _prop('integer', '设备 ID（detail 必填；status_history 可选，'
                                         '给了就查单设备；spl_by_device 必填，'
                                         '但那是**播放设备** ID，不是被测设备 ID）'),
            'group_id': _prop('string', '设备分组 ID（group 必填）'),
            'mapping_id': _prop('integer', 'SPL 映射 ID（spl_mapping / spl_history / '
                                           'spl_calibration_data / digital_spl_mapping 必填）'),
            'api_id': _prop('integer', '被测 API ID（digital_spl_by_api 必填；'
                                       'digital_spl_mappings 可作过滤）'),
            'ids': _prop('array', '被测设备 ID 列表（status 过滤；服务端按逗号串接收）',
                         items={'type': 'integer'}),
            'device_ids': _prop('array', '被测设备 ID 列表（status_history 全量口径）',
                                items={'type': 'integer'}),
            'page': _page_prop('页码（列表类动作，默认 1）'),
            'per_page': _per_page_prop('每页条数（列表类动作）'),
            'keyword': _prop('string', '关键词过滤（list 匹配设备名 / 序列号等；'
                                       'groups 匹配分组名；spl_mappings 匹配映射名）'),
            'status': _prop('string', '状态过滤：list 按设备状态原值（如 online / offline），'
                                      'alarms 按告警状态 ' +
                                      '/'.join(device_tools.ALARM_STATUS_VALUES)),
            'device_type': _prop('string', '设备类型过滤（list，接口原值，如 phone）'),
            'algorithm_type': _prop('string', '算法类型过滤（list，算法类型取值以算法 options 为准）'),
            'lab_id': _prop('integer', '实验室 ID 过滤（list）'),
            'group_type': _prop('string', '设备分组类型过滤（groups）',
                                enum=list(device_tools.GROUP_TYPE_VALUES)),
            'severity': _prop('string', '告警级别过滤（alarms）',
                              enum=list(device_tools.ALARM_SEVERITY_VALUES)),
            'metric_type': _prop('string', '告警指标过滤（alarm_rules）',
                                 enum=list(device_tools.ALARM_METRIC_VALUES)),
            'enabled': _prop('boolean', '告警规则启用状态过滤（alarm_rules）'),
            'event_type': _prop('string', '状态事件类型过滤（status_history）',
                                enum=list(device_tools.STATUS_EVENT_TYPE_VALUES)),
            'start_time': _prop('string', '起始时间（status_history，接口原样透传，'
                                          '如 2026-11-01 00:00:00）'),
            'end_time': _prop('string', '结束时间（status_history，接口原样透传）'),
            'calibration_status': _prop('string', '校准状态过滤（spl_mappings / '
                                                  'digital_spl_mappings）',
                                        enum=list(device_tools.CALIBRATION_STATUS_VALUES)),
        }, required=('action',)),
        risk='READ', permissions=device_tools.DEVICE_QUERY_PERMISSIONS,
        enabled=True, kind='intent_rest'),
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
        name='task_run',
        description=('任务写操作（需提案 + 审批，批准后才执行）：create 创建、'
                     'start 启动、stop 停止、retry 重新执行、merge 合并已完成任务、'
                     'reextract 重新提取设备输出。start / stop 是幂等的（已运行 / '
                     '已在队列时接口返回成功并说明），不会重复建任务或重复执行；'
                     'merge 至少两个任务；retry 指定 case_ids 时必须同时给 '
                     'mode=selected。'),
        parameters=_schema({
            'action': _prop('string', '写动作', required=True,
                            enum=list(task_write_tools.ACTION_NAMES)),
            'task_id': _prop('integer', '任务 ID（start / stop / retry / reextract 必填）'),
            'body': _prop('object', '任务字段：create 至少含 name（同 REST 创建载荷）；'
                                    'retry 可放 {case_ids, mode}；merge 放 {task_ids}'),
            'execution_status': _prop(
                'string', '重新提取时执行线状态（reextract，缺省 completed）',
                enum=list(task_write_tools.EXECUTION_STATUS_VALUES)),
            'evaluation_status': _prop(
                'string', '重新提取时评估线状态（reextract，可选）',
                enum=list(task_write_tools.EVALUATION_STATUS_VALUES)),
        }, required=('action',)),
        risk='WRITE',
        permissions=('task:create', 'task:execute', 'task:merge',
                     'task:reextract'),
        enabled=True, kind='intent_rest'),
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
        name='report_compare',
        description=('报告对比（只读）：多报告并排取数（指标矩阵 / 设备与 API 统计 / '
                     '用例分类统计）、二次对比（源报告须为已有对比报告）、'
                     '统计趋势序列。逐报告返回接口原文数值，不做二次计算、'
                     '不生成平台对比报告（生成对比报告是写操作，M2 走审批）。'),
        parameters=_schema({
            'action': _prop('string', '对比动作', required=True,
                            enum=list(REPORT_COMPARE_ACTIONS)),
            'report_ids': _prop('array', f'参与并排的报告 ID（compare / '
                                         f'secondary_compare 必填，'
                                         f'{REPORT_COMPARE_MIN_REPORTS}~'
                                         f'{REPORT_COMPARE_MAX_REPORTS} 个）',
                                items={'type': 'integer'}),
            'trend_type': _prop('string', '趋势类型（trend，缺省 time）',
                                enum=list(platform_contract_catalog.REPORT_TREND_TYPES)),
            'metric': _prop('string', '趋势指标过滤（trend，取值以接口返回为准）'),
            'start_time': _prop('string', '趋势起始时间（trend）'),
            'end_time': _prop('string', '趋势结束时间（trend）'),
        }, required=('action',)),
        risk='READ', permissions=('report:compare',), enabled=True, kind='local'),
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

# Harness 级常驻工具：与具体 Skill 无关，激活任何 Skill 都保持可用
# （长期记忆读写只作用于调用者自己的私有记忆，不改变平台业务能力）。
# 组装与执行期范围校验都并上这个集合，否则「先激活业务 Skill 再用记忆」会被
# allowed-tools 拦掉。
ALWAYS_AVAILABLE_TOOLS = frozenset({'memory_search', 'memory_write'})

# 宿主语境专用工具：REST 端点在用（用例回填 / 批量标注匹配），但 Agent 侧
# 一律不暴露 —— 不进 tool_search 索引、platform_contract 不返回、解析层拒绝。
# 理由见 AUDIO_QUERY_ACTIONS 上方注释（INT-2530 / INT-2523 P1-1）：这类批量
# 读通道不做归属 / 可见性校验，模型可借用户 Authorization 越过行级可见性。
AGENT_UNEXPOSED_MCP_TOOLS: Dict[str, str] = {
    'audio_get_by_ids': '按 ID 批量读是宿主语境通道（不做归属校验），Agent 侧不可调用',
}

# 审计脱敏：这些工具的参数正文不落 agent_tool_call / 事件（§8.6：审计不落记忆
# 正文）。值替换成 {redacted, sha256, length}，模型侧仍有 args_hash 可追溯。
AUDIT_REDACTED_ARGUMENTS: Dict[str, Tuple[str, ...]] = {
    'memory_write': ('content',),
}


def redact_for_audit(name: str,
                     arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """按工具名脱敏审计参数；未登记的工具原样返回。"""
    payload = dict(arguments or {})
    keys = AUDIT_REDACTED_ARGUMENTS.get(name)
    if not keys:
        return payload
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        raw = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, sort_keys=True, default=str)
        payload[key] = {
            'redacted': True,
            'sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            'length': len(raw),
        }
    return payload

# tool_search 索引：205 个 MCP 工具 + 意图工具（含 5 个预留名称）。
# MCP 与意图工具存在同名项（report_compare / report_export）：
# - 已启用的意图工具优先 —— 否则索引里留下的是 MCP 那条 1:1 写接口
#   （``POST /reports/compare`` 会落库生成报告，risk=WRITE、Schema 是 body 包），
#   模型按它调用会撞上意图 Schema 的 INVALID_ARGUMENTS，且语义上是写操作
#   （INT-2463：Agent 侧 report_compare 是只读组合工具）；
# - 未启用的意图工具（如 report_export）仍保留 MCP 条目（可直接调用）。
# 宿主语境工具（AGENT_UNEXPOSED_MCP_TOOLS）不计入索引。
_MCP_NAMES = frozenset(t['name'] for t in MCP_TOOLS)
_ENABLED_INTENT_NAMES = frozenset(t.name for t in INTENT_TOOLS if t.enabled)

TOOL_INDEX: List[dict] = [
    {'name': t['name'], 'description': t['description'],
     'inputSchema': t['inputSchema'], 'permissions': list(t['permissions']),
     'risk': 'READ' if t['method'] == 'GET' else 'WRITE', 'kind': 'mcp'}
    for t in MCP_TOOLS
    if t['name'] not in AGENT_UNEXPOSED_MCP_TOOLS
    and t['name'] not in _ENABLED_INTENT_NAMES
] + [
    {'name': t.name, 'description': t.description,
     'inputSchema': t.parameters, 'permissions': list(t.permissions),
     'risk': t.risk, 'kind': t.kind, 'enabled': t.enabled}
    for t in INTENT_TOOLS
    if t.name not in _MCP_NAMES or t.name in _ENABLED_INTENT_NAMES
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
    'testcase_query': TESTCASE_QUERY_ACTIONS,
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

# 写意图工具的动作级解析（INT-2468，M2）：三个域的动作表、参数白名单、
# 条件必填与 body 注入都在各自模块（testcase_write_tools / tag_group_tools /
# task_write_tools），本文件只做分发，不复制第二套动作口径。
WRITE_RESOLVERS: Dict[str, Any] = {
    'testcase_write': case_write_tools.resolve,
    'tag_group_manage': tag_group_tools.resolve,
    'task_run': task_write_tools.resolve,
}

# 动作级权限 / 风险的分发：testcase_write / task_run 按动作表，tag_group_manage
# 还要看 target_kind 与 batch_action（见其模块的 permissions_for / risk_for）。
WRITE_ACTION_TABLES: Dict[str, Dict[str, Any]] = {
    'testcase_write': case_write_tools.ACTIONS,
    'task_run': task_write_tools.ACTIONS,
}


def _lookup_rest_tool(name: str) -> Optional[dict]:
    """按工具名取 REST 工具定义：MCP 注册表优先，其次用例域只读表。"""
    return get_tool(name) or case_tools.get_tool(name)


def permissions_for(name: str,
                    arguments: Optional[Dict[str, Any]] = None
                    ) -> Optional[Tuple[str, ...]]:
    """按调用参数解析所需权限（OR 语义）；未知工具返回 None。

    绝大多数工具是「工具 = 一个权限域」，直接用工具级声明。``device_query``
    横跨 device / spl / digital_spl 三个域，工具级声明只表达可见性，调用时按
    ``action`` 收窄，避免持有 device:read 的用户读 SPL 映射（反之亦然）。
    M2 写意图工具同理按动作收窄（``task_run.start`` 要 ``task:execute``，
    ``task_run.merge`` 要 ``task:merge``；``tag_group_manage.delete`` 按
    target_kind 分别要 ``tag:delete`` / ``group:delete``），避免持有单一权限码
    的用户执行其它写动作。动作非法时回落到工具级权限，由解析层给出明确的
    action 错误。
    """
    tool = INTENT_TOOL_BY_NAME.get(name)
    if tool is None:
        if name in AGENT_UNEXPOSED_MCP_TOOLS:
            return None
        mcp = get_tool(name)
        return tuple(mcp['permissions']) if mcp is not None else None
    if isinstance(arguments, dict):
        if name == 'device_query':
            by_action = device_tools.action_permissions(arguments.get('action'))
            if by_action is not None:
                return by_action
        elif name == 'tag_group_manage':
            by_action = tag_group_tools.permissions_for(
                arguments.get('action'), arguments)
            if by_action is not None:
                return by_action
        else:
            actions = WRITE_ACTION_TABLES.get(name)
            if actions is not None:
                spec = actions.get(arguments.get('action')) \
                    if isinstance(arguments.get('action'), str) else None
                if spec is not None:
                    return tuple(spec.permissions)
    return tuple(tool.permissions)


def risk_for(name: str,
             arguments: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """按调用参数解析工具风险（动作级优先）；未知工具返回 ``None``。

    写意图工具的工具级风险是 ``WRITE``（与方案 §6.1 表一致），但删除类动作
    （``testcase_write.delete`` / ``tag_group_manage.delete`` /
    ``batch_tag.rename_tag``）在动作层是 ``DESTRUCTIVE``。审批单与
    ``agent_tool_call.risk`` 记录动作级值，审批人能看到「这条提案会删什么」；
    审批门禁不变（WRITE / DESTRUCTIVE 都要先提案）。
    """
    tool = INTENT_TOOL_BY_NAME.get(name)
    if tool is None:
        return risk_of(name)
    if isinstance(arguments, dict):
        if name == 'tag_group_manage':
            by_action = tag_group_tools.risk_for(
                arguments.get('action'), arguments)
            if by_action is not None:
                return by_action
        else:
            actions = WRITE_ACTION_TABLES.get(name)
            if actions is not None:
                spec = actions.get(arguments.get('action')) \
                    if isinstance(arguments.get('action'), str) else None
                if spec is not None:
                    return spec.risk
    return tool.risk


# 本地实现的意图工具（不映射 REST）：tool_search / platform_contract 在网关
# 内部完成；report_compare 由 ToolGateway 组合只读 REST（见模块 docstring）。
LOCAL_INTENT_TOOL_NAMES = frozenset(
    {'tool_search', 'platform_contract', 'report_compare'})


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


def _normalize_testcase_query_arguments(action: str,
                                       merged: Dict[str, Any]
                                       ) -> Optional[str]:
    """按动作校验 testcase_query 参数，返回错误文本或 None。

    网关 TestCaseListQuery 基类 ``extra='ignore'``：不认识的过滤参数不会报错、
    只会返回全量，模型会把「没过滤」当成「没有匹配」。所以这里先拒掉动作
    不支持的参数（例如 ``status``——用例列表没有状态过滤），再补网关会 422
    的边界（``page`` < 1、``round_number`` < 1）提前给出可读错误。
    """
    allowed = set(TESTCASE_QUERY_PARAMS.get(action, ()))
    allowed |= set(required_for_action('testcase_query', action))
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return f'action={action} 不支持参数：{"、".join(unknown)}'

    if action == 'round_ref_params':
        round_number = merged.get('round_number')
        if round_number is not None and (not isinstance(round_number, int)
                                         or isinstance(round_number, bool)
                                         or round_number < 1):
            return '参数 round_number 必须是 ≥ 1 的整数（轮次从 1 开始）'
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


def _normalize_report_query_arguments(action: str,
                                     merged: Dict[str, Any]) -> Optional[str]:
    """按动作校验 / 归一 report_query 参数，返回错误文本或 None。

    - 动作不支持的参数直接拒绝（网关查询 Schema ``extra='ignore'``，传错参数
      会被静默丢弃并返回全量）；
    - ``page`` / ``per_page`` 边界由 ``pagination.check_page_bounds`` 统一校验；
    - ``case_averages`` 的 ``report_id`` / ``task_id`` 二选一。
    """
    allowed = set(REPORT_QUERY_PARAMS.get(action, ()))
    allowed |= set(required_for_action('report_query', action))
    unknown = sorted(name for name in merged
                     if name not in allowed and merged[name] is not None)
    if unknown:
        return f'action={action} 不支持参数：{"、".join(unknown)}'

    if action == 'case_averages':
        if merged.get('report_id') is None and merged.get('task_id') is None:
            return ('action=case_averages 需要 report_id 或 task_id 之一'
                    '（接口按报告或任务聚合用例指标均值）')
        if merged.get('report_id') is not None and merged.get('task_id') is not None:
            return ('action=case_averages 的 report_id 与 task_id 只能二选一；'
                    '按报告聚合会从对比矩阵解析源任务集合，同时传任务口径会产生歧义')
    return None


def validate_report_compare(action: str,
                            arguments: Dict[str, Any]) -> Optional[str]:
    """校验 report_compare 的动作 / 参数组合，返回错误文本或 None。

    compare / secondary_compare：
    - ``report_ids`` 必填、元素为非零整数、去重后 2~10 个（平台对比至少 2 份）；
    - 其余参数只允许 trend 的三个时间 / 类型参数，传别的一律拒绝。
    trend：只允许 ``trend_type`` / ``metric`` / ``start_time`` / ``end_time``。
    """
    if action not in REPORT_COMPARE_ACTIONS:
        return f'action 取值必须是 {"/".join(REPORT_COMPARE_ACTIONS)} 之一'

    if action == 'trend':
        unknown = sorted(name for name in arguments
                         if name != 'action'
                         and name not in REPORT_COMPARE_TREND_PARAMS
                         and arguments[name] is not None)
        if unknown:
            return f'action=trend 不支持参数：{"、".join(unknown)}'
        return None

    unknown = sorted(name for name in arguments
                     if name != 'action' and name != 'report_ids'
                     and arguments[name] is not None)
    if unknown:
        return f'action={action} 不支持参数：{"、".join(unknown)}'

    raw_ids = arguments.get('report_ids')
    if not raw_ids:
        return f'action={action} 缺少必填参数：report_ids'
    if not isinstance(raw_ids, list):
        return '参数 report_ids 必须是整数数组'
    ids: List[int] = []
    for value in raw_ids:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return f'参数 report_ids 只能包含正整数报告 ID（收到 {value!r}）'
        if value in ids:
            return f'参数 report_ids 含重复报告 ID：{value}'
        ids.append(value)
    if len(ids) < REPORT_COMPARE_MIN_REPORTS:
        return (f'action={action} 至少需要 {REPORT_COMPARE_MIN_REPORTS} 个报告，'
                f'当前 {len(ids)} 个')
    if len(ids) > REPORT_COMPARE_MAX_REPORTS:
        return (f'action={action} 单次最多 {REPORT_COMPARE_MAX_REPORTS} 个报告，'
                f'当前 {len(ids)} 个；请分批对比')
    return None


def resolve_rest_call(name: str, arguments: Dict[str, Any]
                      ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把意图工具 / 长尾 MCP 工具解析为 ``(MCP 工具, 合并参数, 错误文本)``。

    - ``task_query`` / ``report_query`` / ``evaluation_query`` / ``audio_query`` /
      ``algorithm_query``：按 ``action`` 映射到对应 MCP 只读工具，去掉 ``action``
      后其余参数原样透传（路径 / 查询 / body 由共享构造器决定）；
    - ``device_query``：设备动作映射 MCP ``device_*`` GET 工具，SPL 动作映射
      ``device_tools`` 的 Agent 专用只读目标（该域没有对外 MCP 工具）；
    - M2 写意图工具（``testcase_write`` / ``tag_group_manage`` / ``task_run``）：
      交给各域模块的动作表解析（``WRITE_RESOLVERS``），动作级权限 / 风险 /
      条件必填 / body 注入都在那边；
    - 其他 MCP 工具名（tool_search 命中后直接调用）：原样透传参数；
    - 本地实现的工具（``LOCAL_INTENT_TOOL_NAMES``，含 ``report_compare``）不走
      REST 映射：返回错误文本，避免同名 MCP 的写接口被当成本地只读工具执行；
    - 未知名称或动作非法：返回错误文本，由 ToolGateway 收敛为普通失败结果。
    """
    if name == 'device_query':
        return device_tools.resolve_call(arguments or {})
    write_resolver = WRITE_RESOLVERS.get(name)
    if write_resolver is not None:
        return write_resolver(arguments or {})
    if name in LOCAL_INTENT_TOOL_NAMES:
        return None, None, f'工具 {name} 由本地实现，不映射 REST 接口'
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
        mcp = _lookup_rest_tool(mapping[action])
        if mcp is None:  # pragma: no cover - 注册表内部一致性防御
            return None, None, f'工具映射失效：{name}.{action}'
        if mcp['name'] in AGENT_UNEXPOSED_MCP_TOOLS:  # pragma: no cover - 同上
            return None, None, (
                f'工具 {mcp["name"]} 不在 Agent 可用通道内：'
                f'{AGENT_UNEXPOSED_MCP_TOOLS[mcp["name"]]}')
        merged = {k: v for k, v in arguments.items() if k != 'action'}
        # 分页边界：全部查询类意图工具同口径（Schema 的 minimum / maximum 同源），
        # 网关本身对 page=0 / 超大 per_page 不报错（INT-2552）。
        bounds_error = check_page_bounds(action, merged)
        if bounds_error:
            return None, None, bounds_error
        if name == 'audio_query':
            normalize_error = _normalize_audio_query_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'algorithm_query':
            normalize_error = _normalize_algorithm_query_arguments(action, merged)
            if normalize_error:
                return None, None, normalize_error
        if name == 'testcase_query':
            normalize_error = _normalize_testcase_query_arguments(action, merged)
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
        if name == 'report_query':
            normalize_error = _normalize_report_query_arguments(action, merged)
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
    'ALWAYS_AVAILABLE_TOOLS',
    'AUDIO_QUERY_ACTIONS', 'AUDIT_REDACTED_ARGUMENTS',
    'CONDITIONAL_REQUIRED', 'DASHBOARD_QUERY_ACTIONS',
    'DASHBOARD_QUERY_PARAMS', 'ENABLED_TOOLS', 'EVALUATION_QUERY_ACTIONS',
    'INTENT_TOOL_BY_NAME', 'INTENT_TOOLS', 'IntentTool',
    'LOCAL_INTENT_TOOL_NAMES', 'LOCAL_TOOL_NAMES', 'LOG_DIAGNOSE_ACTIONS',
    'LOG_DIAGNOSE_ALL_ACTIONS', 'LOG_DIAGNOSE_DEFAULT_MAX_ROWS',
    'LOG_DIAGNOSE_LOCAL_ACTIONS', 'LOG_DIAGNOSE_MAX_ROWS',
    'LOG_DIAGNOSE_PARAMS', 'LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS', 'MCP_TOOLS',
    'REPORT_COMPARE_ACTIONS', 'REPORT_COMPARE_MAX_REPORTS',
    'PAGE_MIN', 'PER_PAGE_MAX',
    'REPORT_COMPARE_MIN_REPORTS', 'REPORT_PAGE_MIN', 'REPORT_PER_PAGE_MAX',
    'REPORT_QUERY_ACTIONS', 'REPORT_QUERY_PARAMS',
    'TASK_DOMAIN_STATS_GRANULARITIES',
    'TASK_QUERY_ACTIONS', 'TASK_QUERY_PARAMS', 'TESTCASE_QUERY_ACTIONS',
    'TESTCASE_QUERY_PARAMS', 'TESTCASE_VISIBILITY_VALUES', 'TOOL_INDEX',
    'TOOL_INDEX_BY_NAME', 'WRITE_ACTION_TABLES', 'WRITE_RESOLVERS',
    'action_params', 'conditional_required',
    'permissions_for', 'risk_for',
    'platform_contract', 'redact_for_audit',
    'required_for_action', 'resolve_rest_call', 'risk_of', 'tool_search',
    'validate_arguments', 'validate_report_compare',
]
