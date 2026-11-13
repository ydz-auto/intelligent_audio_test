# -*- coding: utf-8 -*-
"""INT-2471 报告写意图工具（report_generate / report_export）契约。

验收锚点（卡面可测标准 1、3、4）：
1. 生成 / 草稿 / 编辑 / 恢复 / 导出都映射到平台既有接口，工具层不重算指标；
3. 重复调用不产生重复报告 / 重复文件（幂等在服务端与编排层同时生效）；
4. 参数（含固定文档版本与格式）完整进审批 / 审计记录。

本文件只覆盖契约（注册口径 / 参数校验 / 动作→REST 映射 / 审批预览）；
审批流与导出编排在 ``tests/agent_write/test_write_report_generate_export.py``。
"""
import pytest

from shared.agent_tools import intent_tools, mcp_registry, report_tools
from shared.models.common_enums import StudioExportFormat


# ---------------------------------------------------------------- 注册口径

def test_both_tools_are_enabled_write_local():
    for name in ('report_generate', 'report_export'):
        tool = intent_tools.INTENT_TOOL_BY_NAME[name]
        assert tool.enabled is True, name
        assert tool.risk == 'WRITE', name
        assert tool.kind == 'local', name
        assert name in intent_tools.ENABLED_TOOLS
        assert name in intent_tools.LOCAL_INTENT_TOOL_NAMES


def test_generate_permissions_are_action_narrowed():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_generate']
    assert set(tool.permissions) == {
        report_tools.REPORT_CREATE, report_tools.STUDIO_CREATE,
        report_tools.STUDIO_EDIT, report_tools.STUDIO_UNDO}
    assert intent_tools.permissions_for(
        'report_generate', {'action': 'generate'}) == ('report:create',)
    assert intent_tools.permissions_for(
        'report_generate', {'action': 'studio_draft'}) == ('report:studio:create',)
    assert intent_tools.permissions_for(
        'report_generate', {'action': 'studio_edit'}) == ('report:studio:edit',)
    assert intent_tools.permissions_for(
        'report_generate', {'action': 'studio_restore'}) == ('report:studio:undo',)
    # 非法动作回落到工具级权限，由解析层报明确错误
    assert set(intent_tools.permissions_for(
        'report_generate', {'action': 'nope'})) == set(tool.permissions)


def test_export_requires_studio_export_permission():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_export']
    assert tool.permissions == (report_tools.STUDIO_EXPORT,)
    assert intent_tools.permissions_for('report_export', {}) == (
        report_tools.STUDIO_EXPORT,)


def test_export_formats_come_from_enum_and_schema():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_export']
    enum = tool.parameters['properties']['format']['enum']
    assert set(enum) == {f.value for f in StudioExportFormat}
    assert set(report_tools.REPORT_EXPORT_FORMATS) == set(enum)


def test_action_enum_covers_generate_chain():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_generate']
    enum = tool.parameters['properties']['action']['enum']
    assert set(enum) == {'generate', 'regenerate', 'studio_draft',
                         'studio_edit', 'studio_restore'}
    assert set(report_tools.REPORT_GENERATE_ACTIONS) == set(enum)


def test_tool_search_index_prefers_intent_over_same_name_mcp_write():
    """同名 MCP ``report_export``（POST /reports/export）不能盖住意图工具。"""
    entry = intent_tools.TOOL_INDEX_BY_NAME['report_export']
    assert entry['kind'] == 'local'
    assert entry['risk'] == 'WRITE'
    names = [t['name'] for t in intent_tools.TOOL_INDEX]
    assert names.count('report_export') == 1
    # 外部 MCP 契约不因本卡变化
    assert mcp_registry.get_tool('report_export')['method'] == 'POST'
    assert len(mcp_registry.TOOLS) == 207


def test_agent_only_studio_targets_not_in_mcp_contract():
    mcp_names = {tool['name'] for tool in mcp_registry.TOOLS}
    for name in ('report_studio_restore_version', 'report_studio_export_job',
                 'report_studio_documents_list'):
        assert report_tools.get_tool(name) is not None, name
        assert name not in mcp_names, name


def test_local_tools_never_resolve_to_mcp_write_targets():
    tool, merged, error = intent_tools.resolve_rest_call(
        'report_generate', {'action': 'generate', 'task_id': 1})
    assert tool is None and merged is None and error
    tool, merged, error = intent_tools.resolve_rest_call(
        'report_export', {'doc_id': 'd', 'format': 'pdf'})
    assert tool is None and merged is None and error


# ---------------------------------------------------------------- 动作 → REST

@pytest.mark.parametrize('arguments,tool_name,method,path,merged', [
    ({'action': 'generate', 'task_id': 460},
     'report_generate_task', 'POST', '/api/v1/reports/generate-task',
     {'body': {'task_id': 460}}),
    ({'action': 'generate', 'task_id': 460,
      'body': {'name': '接线测试_报告', 'description': 'd'}},
     'report_generate_task', 'POST', '/api/v1/reports/generate-task',
     {'body': {'task_id': 460, 'name': '接线测试_报告', 'description': 'd'}}),
    ({'action': 'regenerate', 'report_id': 426},
     'report_regenerate', 'POST', '/api/v1/reports/{report_id}/regenerate',
     {'report_id': 426, 'body': {}}),
    ({'action': 'studio_draft', 'report_id': 426,
      'body': {'markdown_content': '# 草稿'}},
     'report_studio_create_document', 'POST',
     '/api/v1/report-studio/documents',
     {'body': {'markdown_content': '# 草稿', 'report_id': 426}}),
    ({'action': 'studio_edit', 'doc_id': 'doc-1',
      'body': {'expected_version': 1, 'markdown_content': '# v2'}},
     'report_studio_update_document', 'PUT',
     '/api/v1/report-studio/documents/{doc_id}',
     {'doc_id': 'doc-1',
      'body': {'expected_version': 1, 'markdown_content': '# v2'}}),
    ({'action': 'studio_restore', 'doc_id': 'doc-1',
      'body': {'version': 1, 'expected_version': 2}},
     'report_studio_restore_version', 'POST',
     '/api/v1/report-studio/documents/{doc_id}/restore',
     {'doc_id': 'doc-1', 'body': {'version': 1, 'expected_version': 2}}),
])
def test_resolve_call_maps_to_real_gateway_route(arguments, tool_name, method,
                                                 path, merged):
    tool, actual_merged, error = report_tools.resolve_call(arguments)
    assert error is None, error
    assert tool['name'] == tool_name
    assert tool['method'] == method
    assert tool['path'] == path
    assert actual_merged == merged


def test_resolve_call_path_params_exist_in_merged():
    for action, key in (('regenerate', 'report_id'),
                        ('studio_edit', 'doc_id'),
                        ('studio_restore', 'doc_id')):
        arguments = {'action': action, key: 5 if key == 'report_id' else 'doc-1'}
        if action != 'regenerate':
            arguments['body'] = ({'expected_version': 1, 'markdown_content': 'x'}
                                 if action == 'studio_edit'
                                 else {'version': 1, 'expected_version': 2})
        tool, merged, error = report_tools.resolve_call(arguments)
        assert error is None
        for name in tool['path_params']:
            assert merged.get(name) is not None, (action, name)


# ---------------------------------------------------------------- 参数校验

@pytest.mark.parametrize('arguments,needle', [
    ({}, 'action 取值'),
    ({'action': 'nope'}, 'action 取值'),
    ({'action': 'generate'}, 'task_id'),
    ({'action': 'regenerate'}, 'report_id'),
    ({'action': 'studio_draft', 'report_id': 1},
     'markdown_content'),
    ({'action': 'studio_draft', 'report_id': 1,
      'body': {'markdown_content': '  '}}, '不能为空'),
    ({'action': 'studio_draft', 'report_id': 1,
      'body': {'markdown_content': '# x', 'unknown': 1}}, '不支持字段'),
    ({'action': 'studio_edit', 'doc_id': 'd',
      'body': {'markdown_content': 'x'}}, 'expected_version'),
    ({'action': 'studio_edit', 'doc_id': 'd',
      'body': {'expected_version': 1, 'markdown_content': 'x',
               'idempotency_key': 'k'}}, '不支持字段'),
    ({'action': 'studio_restore', 'doc_id': 'd',
      'body': {'expected_version': 2}}, 'version'),
    ({'action': 'generate', 'task_id': 1, 'doc_id': 'd'}, '不接受参数'),
    ({'action': 'generate', 'task_id': 0}, 'task_id'),
    ({'action': 'regenerate', 'report_id': 'x'}, 'report_id'),
    ({'action': 'generate', 'task_id': 1, 'extra': 1}, '不支持参数'),
])
def test_validate_arguments_rejects_invalid_inputs(arguments, needle):
    error = report_tools.validate_arguments(arguments)
    assert error and needle in error, error


def test_validate_arguments_accepts_minimal_valid_calls():
    assert report_tools.validate_arguments({'action': 'generate', 'task_id': 1}) is None
    assert report_tools.validate_arguments(
        {'action': 'studio_draft', 'report_id': 1,
         'body': {'markdown_content': '# x', 'title': 't'}}) is None
    assert report_tools.validate_arguments(
        {'action': 'studio_edit', 'doc_id': 'd',
         'body': {'expected_version': 1, 'markdown_content': ''}}) is None


@pytest.mark.parametrize('arguments,needle', [
    ({}, 'format'),
    ({'doc_id': 'd', 'format': 'exe'}, 'format 取值'),
    ({'format': 'pdf'}, 'doc_id 或 report_id'),
    ({'doc_id': 'd', 'report_id': 1, 'format': 'pdf', 'version': 0}, 'version'),
    ({'doc_id': 'd', 'format': 'pdf', 'theme': ''}, 'theme'),
    ({'doc_id': 'd', 'format': 'pdf', 'extra': 1}, '不支持参数'),
])
def test_validate_export_rejects_invalid_inputs(arguments, needle):
    error = report_tools.validate_export(arguments)
    assert error and needle in error, error


def test_validate_export_accepts_doc_or_report_id():
    assert report_tools.validate_export({'doc_id': 'd', 'format': 'pdf'}) is None
    assert report_tools.validate_export(
        {'report_id': 426, 'format': 'pptx', 'version': 2, 'theme': 'default'}) is None


# ---------------------------------------------------------------- 审批预览

def test_proposal_diff_is_field_level_and_explains_effects():
    diff = report_tools.proposal_diff({
        'action': 'regenerate', 'report_id': 426})
    assert diff['kind'] == 'report_generation'
    assert diff['operation'] == 'regenerate'
    assert diff['report_id'] == 426
    assert '软删' in diff['effect']

    diff = report_tools.proposal_diff({
        'action': 'studio_edit', 'doc_id': 'doc-1',
        'body': {'expected_version': 3, 'markdown_content': '# 新正文'}})
    assert diff['doc_id'] == 'doc-1'
    assert diff['expected_version'] == 3
    assert diff['markdown_length'] == len('# 新正文')
    # 审批预览不重复整段正文（原文在 tool call 审计参数里）
    assert 'markdown_content' not in diff


def test_proposal_diff_export_fixes_version_and_format():
    diff = report_tools.proposal_diff_export(
        {'doc_id': 'doc-1', 'version': 2, 'format': 'pptx'})
    assert diff['kind'] == 'report_export'
    assert diff['doc_id'] == 'doc-1'
    assert diff['version'] == 2
    assert diff['format'] == 'pptx'
    assert '复用' in diff['effect']


def test_proposal_diff_returns_none_for_invalid_arguments():
    assert report_tools.proposal_diff({'action': 'nope'}) is None
    assert report_tools.proposal_diff_export({'format': 'pdf'}) is None
