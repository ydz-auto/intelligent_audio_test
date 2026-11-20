# -*- coding: utf-8 -*-
"""平台口径事实源（INT-2453，用于 ``platform_contract`` 意图工具）。

回答「平台怎么描述自己」：服务拓扑 / 接口前缀 / 枚举 / 命名规则 / 权限码。
数据要么来自代码事实源（``shared/config/service_ports.py`` /
``shared/models/common_enums.py`` / 工具注册表），要么是跨域固定约定；
不在此处编造业务数值。

维护约定：新增服务端口、接口前缀或枚举词表时先改代码事实源，再同步本文件；
``tests/unit/test_int2453_agent_tools.py`` 会核对服务端口与索引完整性，
``tests/unit/test_int2501_tool_catalog_alignment.py`` 核对接口前缀与网关真实
路由一致、意图工具权限码出自 RBAC 事实源。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from shared.config import service_ports
from shared.models.common_enums import ReportStatus, ReportType, Visibility

# 对外只走网关；业务服务之间走 gRPC（方案 §3.1 / §12.1）
SERVICES: List[Dict[str, Any]] = [
    {'name': 'api_gateway', 'http': service_ports.API_GATEWAY_PORT, 'grpc': None,
     'role': '对外唯一入口、鉴权、租户、限流、审计'},
    {'name': 'task_service', 'http': service_ports.TASK_SERVICE_HTTP_PORT,
     'grpc': service_ports.TASK_SERVICE_GRPC_PORT, 'role': '任务、任务用例、结果'},
    {'name': 'e2e_test_service', 'http': service_ports.E2E_TEST_HTTP_PORT,
     'grpc': service_ports.E2E_TEST_GRPC_PORT, 'role': '端到端执行'},
    {'name': 'api_test_service', 'http': service_ports.API_TEST_HTTP_PORT,
     'grpc': service_ports.API_TEST_SERVICE_GRPC_PORT, 'role': 'API 测试执行'},
    {'name': 'evaluation_service', 'http': service_ports.EVALUATION_SERVICE_HTTP_PORT,
     'grpc': service_ports.EVALUATION_SERVICE_GRPC_PORT, 'role': '评估维度、评分'},
    {'name': 'report_service', 'http': service_ports.REPORT_SERVICE_HTTP_PORT,
     'grpc': service_ports.REPORT_SERVICE_GRPC_PORT, 'role': '报告生成、发布、导出'},
    {'name': 'algorithm_service', 'http': service_ports.ALGORITHM_SERVICE_HTTP_PORT,
     'grpc': service_ports.ALGORITHM_SERVICE_GRPC_PORT, 'role': '算法定义与参数'},
    {'name': 'auth_service', 'http': service_ports.AUTH_SERVICE_HTTP_PORT,
     'grpc': service_ports.AUTH_SERVICE_GRPC_PORT, 'role': '用户、角色、权限、令牌'},
    {'name': 'transfer_agent', 'http': service_ports.TRANSFER_AGENT_HTTP_PORT,
     'grpc': service_ports.TRANSFER_AGENT_GRPC_PORT, 'role': '数据迁移'},
    {'name': 'agent_service', 'http': service_ports.AGENT_SERVICE_HTTP_PORT,
     'grpc': None, 'role': '本 Agent 的 Loop / Run / SSE'},
    {'name': 'audio_service', 'http': None,
     'grpc': service_ports.AUDIO_SERVICE_GRPC_PORT, 'role': '音频（经网关访问）'},
    {'name': 'device_service', 'http': None,
     'grpc': service_ports.DEVICE_SERVICE_GRPC_PORT, 'role': '设备（经网关访问）'},
]

# 网关路由前缀（事实源：api_gateway/app.py 的路由注册）
ENDPOINT_PREFIXES: List[Dict[str, str]] = [
    {'prefix': '/api/v1/auth', 'domain': '登录、用户、角色、OAuth、权限点'},
    {'prefix': '/api/v1/testcases', 'domain': '用例 CRUD、导入导出'},
    {'prefix': '/api/v1/groups', 'domain': '用例分组'},
    {'prefix': '/api/v1/tags', 'domain': '标签、批量打标'},
    {'prefix': '/api/v1/tasks', 'domain': '任务 CRUD、启动、停止、统计'},
    {'prefix': '/api/v1/tasks/cherry-picks', 'domain': '挑选合并'},
    {'prefix': '/api/v1/tasks/results', 'domain': '人工复核'},
    {'prefix': '/api/v1/published-tasks', 'domain': '发布任务'},
    {'prefix': '/api/v1/apis', 'domain': '被测 API 定义'},
    {'prefix': '/api/v1/execution', 'domain': '执行编排'},
    {'prefix': '/api/v1/audios', 'domain': '音频列表 / 详情 / 导入 / 标注'},
    {'prefix': '/api/v1/test-devices', 'domain': '测试设备'},
    {'prefix': '/api/v1/playback-devices', 'domain': '播放设备'},
    {'prefix': '/api/v1/laboratories', 'domain': '实验室'},
    {'prefix': '/api/v1/evaluation', 'domain': '评估维度 / 分类'},
    {'prefix': '/api/v1/evaluation-strategies', 'domain': '评估策略'},
    {'prefix': '/api/v1/reports', 'domain': '报告生成、发布、导出、进度'},
    {'prefix': '/api/v1/report-studio', 'domain': 'Studio 文档 / 版本 / 图表 / 导出'},
    {'prefix': '/api/v1/algorithm', 'domain': '算法定义、参数、映射、热重载'},
    {'prefix': '/api/v1/spl', 'domain': 'SPL 映射与校准'},
    {'prefix': '/api/v1/digital-spl', 'domain': '数字 SPL'},
    {'prefix': '/api/v1/logs', 'domain': '日志搜索 / 统计 / 导出'},
    {'prefix': '/api/v1/home', 'domain': '首页统计'},
    {'prefix': '/api/v1/sse', 'domain': '业务进度推送（与 Agent 事件流不是同一条）'},
    {'prefix': '/api/v1/data-transfer', 'domain': '数据迁移'},
    {'prefix': '/api/v1/benchmarks', 'domain': '基准报告'},
    {'prefix': '/api/v1/system', 'domain': '系统信息'},
    {'prefix': '/api/v1/favorites', 'domain': '收藏'},
    {'prefix': '/api/v1/agent', 'domain': 'Agent sessions / runs / events / skills'},
    {'prefix': '/api/v1/agent/skill', 'domain': '外部 Skill 包 zip 下载（单数）'},
    {'prefix': '/api/v1/mcp', 'domain': '外部 MCP JSON-RPC'},
]

# 算法域接口取值（INT-2464 / INT-2525）。事实源：网关 GET /api/v1/algorithm/* 的
# schema 与 algorithm_service 的 PO 口径——
# - 状态：`handlers/algorithm_handlers.py` 的 `_STATUS_STR_TO_ENUM` 三个键
#   （接口值 → 领域枚举：online→ACTIVE、offline→DEPRECATED、draft→DRAFT）；
# - 参数作用域：`AlgorithmParamListQuery.param_type`（device / api）；
# - 映射源类型：`AlgorithmMappingListQuery.source_type`（device / api）。
ALGORITHM_STATUS_VALUES: Tuple[str, ...] = ('online', 'offline', 'draft')
ALGORITHM_PARAM_TYPE_VALUES: Tuple[str, ...] = ('device', 'api')
ALGORITHM_MAPPING_SOURCE_VALUES: Tuple[str, ...] = ('device', 'api')

# 报告域接口取值（INT-2463）。事实源：
# - 类型 / 发布态：`shared.models.common_enums.ReportType` / `ReportStatus`
#   （网关列表过滤、tab 计数、报告详情都按这套值返回；`report_service/domain/
#   entities/report.py` 的 standard/detailed 是历史词表，不进接口）；
# - 统计维度 / 趋势类型：网关 `ReportStatisticsQuery.dimension` /
#   `ReportStatisticsTrendQuery.trend_type`，服务端对越界值直接 400 并回列可选值。
REPORT_TYPE_VALUES: Tuple[str, ...] = tuple(v.value for v in ReportType)
REPORT_STATUS_VALUES: Tuple[str, ...] = tuple(v.value for v in ReportStatus)
REPORT_STATISTICS_DIMENSIONS: Tuple[str, ...] = (
    'time', 'device_type', 'evaluation_metric')
REPORT_TREND_TYPES: Tuple[str, ...] = ('time', 'dimension')
# 二次对比的源报告类型：平台只允许对「对比 / 二次对比」报告再做二次对比。
REPORT_COMPARABLE_TYPES: Tuple[str, ...] = (
    ReportType.COMPARISON.value, ReportType.SECONDARY_COMPARISON.value)

# 枚举速查：值取「接口里的值」（小写），来源标注在 source
ENUMS: List[Dict[str, Any]] = [
    {'name': 'task_status', 'label': '任务状态',
     'values': ['pending', 'queued', 'running', 'evaluating',
                'reevaluate_queued', 'reevaluating', 'completed', 'failed',
                'stopped', 'paused', 'skipped'],
     'terminal': ['completed', 'failed', 'stopped', 'skipped'],
     'source': 'task_service TaskStatus'},
    {'name': 'report_status', 'label': '报告状态',
     'values': [v.value for v in ReportStatus],
     'source': 'shared.models.common_enums.ReportStatus（只表达发布态）'},
    {'name': 'report_type', 'label': '报告类型',
     'values': [v.value for v in ReportType],
     'source': 'shared.models.common_enums.ReportType'},
    {'name': 'visibility', 'label': '可见性',
     'values': [v.value for v in Visibility],
     'source': 'shared.models.common_enums.Visibility'},
    {'name': 'entity_type', 'label': '可收藏实体类型',
     'values': ['task', 'report', 'testcase'],
     'source': 'shared.models.common_enums.EntityType'},
    {'name': 'tool_risk', 'label': '工具风险等级',
     'values': ['READ', 'WRITE', 'DESTRUCTIVE'],
     'source': 'agent_service.domain.enums.ToolRisk'},
    {'name': 'run_status', 'label': '运行状态',
     'values': ['QUEUED', 'RUNNING', 'WAITING_APPROVAL', 'SUCCEEDED',
                'FAILED', 'CANCELLED', 'BUDGET_EXCEEDED'],
     'source': 'agent_service.domain.enums.RunStatus'},
    {'name': 'algorithm_status', 'label': '算法定义状态',
     'values': list(ALGORITHM_STATUS_VALUES),
     'source': ('algorithm_service AlgorithmStatus（接口值 online/offline/draft '
                '→ ACTIVE/DEPRECATED/DRAFT，见 _STATUS_STR_TO_ENUM）')},
    {'name': 'algorithm_param_type', 'label': '算法参数作用域',
     'values': list(ALGORITHM_PARAM_TYPE_VALUES),
     'source': 'api_gateway AlgorithmParamListQuery.param_type'},
    {'name': 'algorithm_mapping_source', 'label': '参数映射源类型',
     'values': list(ALGORITHM_MAPPING_SOURCE_VALUES),
     'source': 'api_gateway AlgorithmMappingListQuery.source_type'},
    {'name': 'report_statistics_dimension', 'label': '报告统计维度',
     'values': list(REPORT_STATISTICS_DIMENSIONS),
     'source': 'api_gateway ReportStatisticsQuery.dimension'},
    {'name': 'report_trend_type', 'label': '报告趋势类型',
     'values': list(REPORT_TREND_TYPES),
     'source': 'api_gateway ReportStatisticsTrendQuery.trend_type'},
]

NAMING_RULES: List[str] = [
    '服务端一律 snake_case；前端 camelCase 只在 frontend-react/src/infrastructure 的 dto / adapters 层转换。',
    '业务实体主键一般是整数（task_id: 123）；agent_* 表用 UUID 字符串；user_id 是整数，tenant_id 是字符串。',
    '时间：接口返回 ISO 8601 字符串；数据库按 UTC naive 写入。',
    '序列化：datetime → isoformat、Decimal → float、Enum → value。',
    '列表响应形态各域不完全一致（有的 {items, total}，有的裸数组），以接口实际返回为准。',
    '权限码格式固定为「资源:操作」（如 task:read、task:create）；多权限判定是 OR；* 是管理员通配。',
    '金额 / 指标 / 评分一律以接口返回数值为准；缺失就是缺失，不要用 0 或估算值填补。',
]

# 跨域固定口径（Skill / tool_search 使用）
CONVENTIONS: List[str] = [
    '外部访问只走 api_gateway（/api/v1 前缀）；业务服务之间才用 gRPC。',
    '外部 MCP 与内部 Agent 共用工具 Schema（shared/agent_tools），不要复制两份。',
    '写操作一律需要审批：M0/M1 阶段写工具调用返回 APPROVAL_REQUIRED；'
    'memory_write 只生成待审批提案（不落盘），审批通过后才生效。',
    'GET /api/v1/agent/skill（单数）是 Skill 包 zip 下载；/api/v1/agent/skills（复数）是可见 Skill 列表。',
    '报告 status 只表达 draft / published；生成进度看 GET /api/v1/reports/{id}/progress。',
    '回收站没有独立前缀：恢复是 POST /api/v1/{tasks|testcases|reports}/{id}/restore、'
    '彻底删除是 DELETE /api/v1/{tasks|testcases|reports}/{id}/purge（批量走 '
    'POST /api/v1/{tasks|testcases|reports}/restore|purge）；回收站列表走各实体列表'
    '接口的 deleted / only_deleted 过滤参数，收藏列表是 GET /api/v1/favorites。',
]

_SECTIONS = {
    'services': SERVICES,
    'endpoints': ENDPOINT_PREFIXES,
    'enums': ENUMS,
    'naming': NAMING_RULES,
    'conventions': CONVENTIONS,
}

_MATCH_FIELDS = {
    'services': ('name', 'role'),
    'endpoints': ('prefix', 'domain'),
    'enums': ('name', 'label', 'source'),
}


def _hit(item: Any, terms: Sequence[str], fields: Sequence[str]) -> bool:
    if isinstance(item, str):
        text = item
    else:
        text = ' '.join(str(item.get(f, '')) for f in fields)
    lowered = text.lower()
    return any(term in lowered for term in terms)


def lookup(query: str = '', section: str = 'all') -> Dict[str, Any]:
    """按关键词检索平台口径。空 query 返回全部（供模型自查）。"""
    terms = [t for t in (query or '').lower().split() if t]
    wanted = [section] if section and section != 'all' else list(_SECTIONS)
    result: Dict[str, Any] = {'query': query, 'section': section}
    for name in wanted:
        data = _SECTIONS.get(name)
        if data is None:
            continue
        if terms and name in _MATCH_FIELDS:
            result[name] = [item for item in data
                            if _hit(item, terms, _MATCH_FIELDS[name])]
        elif terms:
            result[name] = [item for item in data
                            if any(term in item.lower() for term in terms)]
        else:
            result[name] = list(data)
    return result


__all__ = [
    'ALGORITHM_MAPPING_SOURCE_VALUES', 'ALGORITHM_PARAM_TYPE_VALUES',
    'ALGORITHM_STATUS_VALUES', 'CONVENTIONS', 'ENDPOINT_PREFIXES', 'ENUMS',
    'NAMING_RULES', 'REPORT_COMPARABLE_TYPES', 'REPORT_STATISTICS_DIMENSIONS',
    'REPORT_STATUS_VALUES', 'REPORT_TREND_TYPES', 'REPORT_TYPE_VALUES',
    'SERVICES', 'lookup',
]
