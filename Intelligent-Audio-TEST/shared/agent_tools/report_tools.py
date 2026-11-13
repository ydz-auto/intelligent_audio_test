# -*- coding: utf-8 -*-
"""报告域写意图工具分组（INT-2471，M2，方案 §6.1 / §6.2 / §9）。

两个写工具覆盖「生成 → 起草 → 版本 → 导出」的完整链路：

``report_generate``（WRITE，提案 + 审批 + 幂等）
  - ``generate``：按任务生成标准报告（``POST /api/v1/reports/generate-task``）；
    平台侧已有报告时返回 ``status=exists``，正在生成时返回 ``status=generating``，
    **重复调用不会产生第二份报告**；
  - ``regenerate``：重生成任务报告（``POST /api/v1/reports/{report_id}/regenerate``）；
    旧报告软删进回收站后重建，指标重新计算；
  - ``studio_draft``：用已取数的报告创建 Studio 文档草稿（版本 1），
    ``agent_session_id`` 由 ToolGateway 按 run 注入（模型不可传），
    同一报告 + 同一操作人 + 完全相同正文再次起草时复用原文档（不重复建文档）；
  - ``studio_edit``：编辑 Studio 文档生成新版本（``expected_version`` 乐观锁，
    冲突 409 + 差异原样回给模型，不覆盖他人改动）；
  - ``studio_restore``：把历史版本恢复为**新版本**（历史版本只读不可变）。

``report_export``（WRITE，本地编排，方案 §6.1「导出 PDF/PPTX/HTML/MD」）
  1. 文档来源：显式 ``doc_id``，或按 ``report_id`` 取该报告最近更新的平台文档
     （``GET /api/v1/report-studio/documents``，只读）；找不到时明确提示先起草；
  2. ``version`` 缺省取文档当前版本（导出固定 ``docId + version + format``）；
  3. 创建异步导出作业（``POST .../documents/{doc_id}/exports``）；服务端对
     「同文档版本 + 同格式 + 同主题」的进行中 / 已完成作业复用，不重复产文件；
  4. 短轮询作业至终态，返回 ``export_id`` / ``status`` / ``download_ref``；
     未完成时如实返回 ``pending``（再调一次同一入参即继续复用/查询该作业），
     不把「提交成功」说成「已导出」。

本模块只回答「这个动作落到哪个接口、要什么权限、参数合不合法、审批人该看到
什么」；提案 / 审批 / 幂等 / 审计由 Loop 与审批服务（INT-2466）统一承担，
本模块不落任何业务副作用。

工具项形状与 ``mcp_registry`` 完全一致：能在 MCP 表里找到的写目标直接复用
（``report_generate_task`` / ``report_regenerate`` / ``report_studio_create_document``
/ ``report_studio_update_document`` / ``report_studio_export_document``），
MCP 表未登记的三个通道（版本恢复、导出作业查询、文档列表）以 Agent 专用目标
声明，**不外扩外部 MCP ``tools/list`` 契约**（仍是 207 条）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from shared.agent_tools.mcp_registry import get_tool as get_mcp_tool
from shared.agent_tools.mcp_registry import tool_entry
from shared.models.common_enums import StudioExportFormat

# ---------------------------------------------------------------- 权限码
# 口径：RBAC 事实源（scripts/migrations/202608/seed_rbac.py）与同能力 MCP 工具
# 实际使用的码，多码按 OR 判定；不自己拼不存在的码。
REPORT_CREATE = 'report:create'
STUDIO_CREATE = 'report:studio:create'
STUDIO_EDIT = 'report:studio:edit'
STUDIO_UNDO = 'report:studio:undo'
STUDIO_EXPORT = 'report:studio:export'

# ---------------------------------------------------------------- 动作表

# 写动作 → 目标工具名。前 3 项来自 ``mcp_registry``；studio_restore /
# report_studio_export_job / report_studio_documents_list 是 Agent 专用通道
# （网关有路由，MCP 表未登记），见模块 docstring。
REPORT_GENERATE_ACTIONS: Dict[str, str] = {
    'generate': 'report_generate_task',
    'regenerate': 'report_regenerate',
    'studio_draft': 'report_studio_create_document',
    'studio_edit': 'report_studio_update_document',
    'studio_restore': 'report_studio_restore_version',
}

# 动作级权限（OR 语义）：工具级声明只表达可见性，调用时按 action 收窄，
# 避免「能起草」的用户重生成平台报告或恢复历史版本。
REPORT_GENERATE_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    'generate': (REPORT_CREATE,),
    'regenerate': (REPORT_CREATE,),
    'studio_draft': (STUDIO_CREATE,),
    'studio_edit': (STUDIO_EDIT,),
    'studio_restore': (STUDIO_UNDO,),
}

# 动作级必填的顶层 ID 参数（body 之外的路径 / 关联参数）
REPORT_GENERATE_REQUIRED_PARAMS: Dict[str, Tuple[str, ...]] = {
    'generate': ('task_id',),
    'regenerate': ('report_id',),
    'studio_draft': ('report_id',),
    'studio_edit': ('doc_id',),
    'studio_restore': ('doc_id',),
}

# body 字段白名单：网关 / gRPC 侧对不认识的字段是静默丢弃（或忽略），
# 工具层先拦下「传了但不会生效」的字段，避免模型误以为改成功了。
_GENERATE_BODY_FIELDS: Tuple[str, ...] = ('name', 'description')
_STUDIO_DRAFT_BODY_FIELDS: Tuple[str, ...] = (
    'markdown_content', 'title', 'chart_refs', 'style_prefs')
_STUDIO_EDIT_BODY_FIELDS: Tuple[str, ...] = (
    'expected_version', 'markdown_content', 'chart_refs', 'style_prefs')
_STUDIO_RESTORE_BODY_FIELDS: Tuple[str, ...] = ('version', 'expected_version')

REPORT_GENERATE_BODY_FIELDS: Dict[str, Optional[Tuple[str, ...]]] = {
    'generate': _GENERATE_BODY_FIELDS,
    'regenerate': _GENERATE_BODY_FIELDS,
    'studio_draft': _STUDIO_DRAFT_BODY_FIELDS,
    'studio_edit': _STUDIO_EDIT_BODY_FIELDS,
    'studio_restore': _STUDIO_RESTORE_BODY_FIELDS,
}

# body 条件必填：起草必须带正文（空草稿没有意义）、编辑必须带乐观锁基准、
# 恢复必须指定目标版本。
REPORT_GENERATE_BODY_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'studio_draft': ('markdown_content',),
    'studio_edit': ('expected_version', 'markdown_content'),
    'studio_restore': ('version', 'expected_version'),
}

# 顶层允许的参数（其余一律报错，避免「传了但被静默忽略」）
_GENERATE_ALLOWED_KEYS = frozenset({'action', 'task_id', 'report_id', 'doc_id',
                                    'body'})

# 导出格式：取值以 ``StudioExportFormat`` 为唯一事实源（pdf / pptx / html / md）
REPORT_EXPORT_FORMATS: Tuple[str, ...] = tuple(f.value for f in StudioExportFormat)

# 导出作业复用 / 轮询口径：
# - 服务端对「同 doc_id + version + format + theme」的进行中 / 已完成作业复用，
#   重复导出不会产生第二个文件；
# - 工具层短轮询给模型一个可直接使用的结论，超时如实返回 pending。
EXPORT_POLL_INTERVAL_SECONDS = 0.5
EXPORT_POLL_MAX_ATTEMPTS = 20
EXPORT_TERMINAL_STATUSES: Tuple[str, ...] = ('done', 'failed')

# ---------------------------------------------------------------- Agent 专用目标

# 与 ``mcp_registry`` 同形（name / description / inputSchema / permissions /
# method / path / path_params / query_params），复用同一构造器。
REPORT_WRITE_TOOLS: List[dict] = [
    tool_entry(
        'report_studio_restore_version', '把 Studio 文档历史版本恢复为新版本',
        {'doc_id': {'type': 'string', 'description': 'Studio 文档 ID',
                    'required': True},
         'body': {'type': 'object',
                  'description': '恢复参数（version / expected_version）',
                  'required': True}},
        [STUDIO_UNDO], 'POST',
        '/api/v1/report-studio/documents/{doc_id}/restore',
        path_params=['doc_id']),
]

# Agent 专用只读目标：不属于对外 MCP 清单，只供本模块的编排与校验回源。
REPORT_READ_TOOLS: List[dict] = [
    tool_entry(
        'report_studio_export_job', '查询 Report Studio 导出作业状态',
        {'export_id': {'type': 'string', 'description': '导出作业 ID',
                       'required': True}},
        [STUDIO_EXPORT], 'GET',
        '/api/v1/report-studio/exports/{export_id}',
        path_params=['export_id']),
    tool_entry(
        'report_studio_documents_list', '列出 Report Studio 文档（按报告 / 来源过滤）',
        {'report_id': {'type': 'integer', 'description': '平台报告 ID'},
         'source_type': {'type': 'string',
                         'description': '文档来源：platform_report / uploaded_file'},
         'limit': {'type': 'integer', 'description': '返回条数（服务端上限 500）'},
         'offset': {'type': 'integer', 'description': '偏移量'}},
        ['report:read'], 'GET', '/api/v1/report-studio/documents',
        query_params=['report_id', 'source_type', 'limit', 'offset']),
]

_WRITE_TOOL_BY_NAME: Dict[str, dict] = {
    tool['name']: tool for tool in REPORT_WRITE_TOOLS + REPORT_READ_TOOLS}

# 导出编排用到的目标工具名（MCP 表里的 Studio 导出作业创建）
EXPORT_CREATE_TOOL = 'report_studio_export_document'
EXPORT_JOB_TOOL = 'report_studio_export_job'
DOCUMENTS_LIST_TOOL = 'report_studio_documents_list'


def get_tool(name: str) -> Optional[dict]:
    """按名取本模块的 Agent 专用目标；非本模块工具返回 None。"""
    return _WRITE_TOOL_BY_NAME.get(name)


def _lookup(action: str) -> Optional[dict]:
    """动作 → 目标工具定义：MCP 注册表优先，其次本模块 Agent 专用目标。"""
    name = REPORT_GENERATE_ACTIONS[action]
    return get_mcp_tool(name) or get_tool(name)


def action_permissions(action: Any) -> Optional[Tuple[str, ...]]:
    """动作所需权限；非法动作返回 None（由解析层给出明确的 action 错误）。"""
    return REPORT_GENERATE_PERMISSIONS.get(action)


# ---------------------------------------------------------------- 参数校验


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_body(action: str, body: Any) -> Optional[str]:
    """body 字段白名单 / 条件必填 / 类型校验；返回错误文本或 None。"""
    allowed = REPORT_GENERATE_BODY_FIELDS[action]
    if allowed is None:
        if body is not None:
            return f'action={action} 不接受 body'
        return None
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return f'action={action} 的 body 必须是对象'
    unknown = sorted(key for key in body if key not in allowed)
    if unknown:
        return (f'action={action} 的 body 不支持字段：{"、".join(unknown)}'
                '（网关会静默忽略这些字段）')
    for name in REPORT_GENERATE_BODY_REQUIRED.get(action, ()):
        if body.get(name) is None:
            return f'action={action} 的 body 缺少必填字段：{name}'

    if action in ('generate', 'regenerate'):
        for key in ('name', 'description'):
            value = body.get(key)
            if value is not None and not isinstance(value, str):
                return f'body.{key} 必须是字符串'
        return None

    if action in ('studio_draft', 'studio_edit'):
        markdown = body.get('markdown_content')
        if markdown is not None and not isinstance(markdown, str):
            return 'body.markdown_content 必须是字符串'
        if action == 'studio_draft' and isinstance(markdown, str) \
                and not markdown.strip():
            return 'action=studio_draft 的 body.markdown_content 不能为空'
        title = body.get('title')
        if title is not None and not _non_empty_str(title):
            return 'body.title 必须是非空字符串'
        chart_refs = body.get('chart_refs')
        if chart_refs is not None and (
                not isinstance(chart_refs, list)
                or any(not isinstance(item, str) for item in chart_refs)):
            return 'body.chart_refs 必须是字符串数组'
        style_prefs = body.get('style_prefs')
        if style_prefs is not None and not isinstance(style_prefs, dict):
            return 'body.style_prefs 必须是对象'
    if action == 'studio_edit':
        if not _positive_int(body.get('expected_version')):
            return (f'action=studio_edit 的 body.expected_version 必须是正整数：'
                    f'{body.get("expected_version")}')
    if action == 'studio_restore':
        if not _positive_int(body.get('version')):
            return (f'action=studio_restore 的 body.version 必须是正整数：'
                    f'{body.get("version")}')
        if not _positive_int(body.get('expected_version')):
            return (f'action=studio_restore 的 body.expected_version 必须是正整数：'
                    f'{body.get("expected_version")}')
    return None


def validate_arguments(arguments: Dict[str, Any]) -> Optional[str]:
    """``report_generate`` 动作级参数校验；返回错误文本或 None。"""
    if not isinstance(arguments, dict):
        return '工具参数必须是对象'
    action = arguments.get('action')
    if action not in REPORT_GENERATE_ACTIONS:
        return f'action 取值必须是 {"/".join(REPORT_GENERATE_ACTIONS)} 之一'
    unknown = sorted(key for key in arguments if key not in _GENERATE_ALLOWED_KEYS)
    if unknown:
        return f'不支持参数：{"、".join(unknown)}'
    if arguments.get('task_id') is not None and not _positive_int(
            arguments.get('task_id')):
        return f'task_id 必须是正整数：{arguments.get("task_id")}'
    if arguments.get('report_id') is not None and not _positive_int(
            arguments.get('report_id')):
        return f'report_id 必须是正整数：{arguments.get("report_id")}'
    if arguments.get('doc_id') is not None and not _non_empty_str(
            arguments.get('doc_id')):
        return f'doc_id 必须是非空字符串：{arguments.get("doc_id")}'
    for name in REPORT_GENERATE_REQUIRED_PARAMS[action]:
        if arguments.get(name) is None:
            return f'action={action} 缺少必填参数：{name}'
    # 不需要的 ID 参数显式报错（避免模型以为另一个参数生效了）
    for name, actions in (
            ('task_id', ('generate',)),
            ('report_id', ('regenerate', 'studio_draft')),
            ('doc_id', ('studio_edit', 'studio_restore'))):
        if arguments.get(name) is not None and action not in actions:
            return f'action={action} 不接受参数 {name}'
    return _check_body(action, arguments.get('body'))


def _build_body(action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """按动作构造目标 REST 的 body（顶层 ID 参数折进各自接口的字段）。"""
    body = dict(arguments.get('body') or {})
    if action == 'generate':
        body['task_id'] = arguments['task_id']
    elif action == 'studio_draft':
        body['report_id'] = arguments['report_id']
    return body


def resolve_call(arguments: Dict[str, Any]
                 ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把 ``report_generate`` 调用解析为 ``(目标工具, 合并参数, 错误文本)``。"""
    error = validate_arguments(arguments or {})
    if error:
        return None, None, error
    action = arguments['action']
    tool = _lookup(action)
    if tool is None:  # pragma: no cover - 注册表内部一致性防御
        return None, None, f'工具映射失效：report_generate.{action}'
    merged: Dict[str, Any] = {}
    if action == 'regenerate':
        merged['report_id'] = arguments['report_id']
    elif action in ('studio_edit', 'studio_restore'):
        merged['doc_id'] = arguments['doc_id']
    merged['body'] = _build_body(action, arguments)
    return tool, merged, None


def proposal_diff(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """审批人可见的字段级变更预览（不预判后端结果，不编造前后值）。"""
    action = (arguments or {}).get('action')
    if action not in REPORT_GENERATE_ACTIONS:
        return None
    diff: Dict[str, Any] = {
        'kind': 'report_generation',
        'operation': action,
        'request': REPORT_GENERATE_ACTIONS[action],
    }
    for key in ('task_id', 'report_id', 'doc_id'):
        if arguments.get(key) is not None:
            diff[key] = arguments[key]
    body = arguments.get('body')
    if isinstance(body, dict):
        # 正文只给长度，不在审批预览里重复整段 markdown（审计原文在 tool call
        # 参数里，审批人需要时可展开）。
        markdown = body.get('markdown_content')
        if isinstance(markdown, str):
            diff['markdown_length'] = len(markdown)
        for key in ('title', 'expected_version', 'version'):
            if body.get(key) is not None:
                diff[key] = body[key]
        if body.get('chart_refs') is not None:
            diff['chart_refs'] = list(body['chart_refs'])
    diff['effect'] = {
        'generate': '按任务生成标准报告；任务已有报告时复用（不新建第二份），'
                    '正在生成时如实返回 generating',
        'regenerate': '旧报告软删进回收站后重建任务报告，指标重新计算',
        'studio_draft': '创建 Studio 文档草稿（版本 1）；同报告同正文同操作人'
                        '再次起草时复用原文档',
        'studio_edit': '在 optimistic lock 下生成新版本；版本冲突 409 不覆盖他人改动',
        'studio_restore': '把历史版本恢复为新版本（历史版本只读不可变）',
    }[action]
    return diff


# ---------------------------------------------------------------- 导出

_EXPORT_ALLOWED_KEYS = frozenset({'doc_id', 'report_id', 'version', 'format',
                                  'theme'})


def validate_export(arguments: Dict[str, Any]) -> Optional[str]:
    """``report_export`` 参数校验；返回错误文本或 None。"""
    if not isinstance(arguments, dict):
        return '工具参数必须是对象'
    unknown = sorted(key for key in arguments if key not in _EXPORT_ALLOWED_KEYS)
    if unknown:
        return f'不支持参数：{"、".join(unknown)}'
    fmt = arguments.get('format')
    if fmt is None:
        return '缺少必填参数：format'
    if fmt not in REPORT_EXPORT_FORMATS:
        return (f'format 取值必须是 {" / ".join(REPORT_EXPORT_FORMATS)} 之一：'
                f'{fmt}')
    doc_id = arguments.get('doc_id')
    report_id = arguments.get('report_id')
    if not doc_id and report_id is None:
        return '需要 doc_id 或 report_id（doc_id 优先）'
    if doc_id is not None and not _non_empty_str(doc_id):
        return f'doc_id 必须是非空字符串：{doc_id}'
    if report_id is not None and not _positive_int(report_id):
        return f'report_id 必须是正整数：{report_id}'
    version = arguments.get('version')
    if version is not None and not _positive_int(version):
        return f'version 必须是正整数：{version}'
    theme = arguments.get('theme')
    if theme is not None and not _non_empty_str(theme):
        return 'theme 必须是非空字符串'
    return None


def proposal_diff_export(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """导出提案的字段级预览（固定版本 + 格式 + 主题，异步作业）。"""
    error = validate_export(arguments or {})
    if error:
        return None
    diff: Dict[str, Any] = {
        'kind': 'report_export',
        'operation': 'studio_export',
        'request': EXPORT_CREATE_TOOL,
        'format': arguments.get('format'),
    }
    for key in ('doc_id', 'report_id', 'version', 'theme'):
        if arguments.get(key) is not None:
            diff[key] = arguments[key]
    diff['effect'] = ('按固定文档版本异步渲染导出产物；同文档版本 + 同格式 + 同主题的'
                      '进行中 / 已完成作业复用，不重复产生文件')
    return diff


__all__ = [
    'DOCUMENTS_LIST_TOOL', 'EXPORT_CREATE_TOOL', 'EXPORT_JOB_TOOL',
    'EXPORT_POLL_INTERVAL_SECONDS', 'EXPORT_POLL_MAX_ATTEMPTS',
    'EXPORT_TERMINAL_STATUSES',
    'REPORT_CREATE', 'REPORT_EXPORT_FORMATS', 'REPORT_GENERATE_ACTIONS',
    'REPORT_GENERATE_BODY_FIELDS', 'REPORT_GENERATE_BODY_REQUIRED',
    'REPORT_GENERATE_PERMISSIONS', 'REPORT_GENERATE_REQUIRED_PARAMS',
    'REPORT_READ_TOOLS', 'REPORT_WRITE_TOOLS', 'STUDIO_CREATE', 'STUDIO_EDIT',
    'STUDIO_EXPORT', 'STUDIO_UNDO', 'action_permissions', 'get_tool',
    'proposal_diff', 'proposal_diff_export', 'resolve_call', 'validate_arguments',
    'validate_export',
]
