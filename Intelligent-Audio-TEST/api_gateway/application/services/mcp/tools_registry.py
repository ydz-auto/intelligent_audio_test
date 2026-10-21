# -*- coding: utf-8 -*-
"""MCP tools 注册表（INT-1150 / INT-1140 覆盖能力清单）。

每个工具 = 平台既有 REST 能力的一个 MCP 映射：
  - ``name``：MCP 工具名（snake_case，对外可见）
  - ``description``：给外部 agent 的用途说明
  - ``inputSchema``：JSON Schema（arguments 对象；additionalProperties=True，
    目标端点仍由网关 pydantic 二次校验，422 语义透传）
  - ``permissions``：所需权限码（OR 语义；空 = 仅需登录）。生效权限由
    AuthMiddleware 注入 request.state.permissions —— JWT=用户快照权限、
    access token=用户当前权限 ∩ token scopes（BE2 INT-1149），天然支持
    「token scopes 不含所需权限 → 拒绝」。
  - ``method`` / ``path``：目标网关 REST 路径模板（{placeholder} = 路径参数）
  - ``path_params``：取自 arguments 的路径参数名（占位符同名）
  - ``query_params``：显式放查询串的参数名；GET/DELETE 未列入的剩余参数
    也进查询串，POST/PUT/PATCH 剩余参数进 JSON body

覆盖边界（INT-1140 能力覆盖清单，负责人验收核对）：
  - 覆盖：task / testcase / audio / device / evaluation / report / algorithm /
    tag / group 业务接口、*:share 数据可见性分享点、data-transfer
    （task:export/import）、favorites / trash（INT-141）、benchmarks、
    report-studio、logs 只读（log:read，倾向覆盖）。
  - 除外：auth users/roles/permissions/oauth-providers（系统设置）、
    auth me/self/change-password/OAuth 绑定（个人信息）、option（系统设置）、
    system health/status、log:manage / log:websocket（倾向除外）、
    SSE /api/v1/sse（倾向除外，长连接推送）。
"""
from __future__ import annotations

from typing import Dict, List

# ========================================================================
# 工具构造辅助
# ========================================================================


def _tool(name: str, description: str, input_schema: dict, permissions: List[str],
          method: str, path: str, path_params: List[str] = None,
          query_params: List[str] = None) -> dict:
    """构造一个工具注册项并做字段校验。"""
    schema = {
        'type': 'object',
        'properties': dict(input_schema),
        'additionalProperties': True,
    }
    if input_schema:
        required = [k for k, v in input_schema.items()
                    if isinstance(v, dict) and v.get('required')]
        if required:
            schema['required'] = required
    return {
        'name': name,
        'description': description,
        'inputSchema': schema,
        'permissions': list(permissions or []),
        'method': method.upper(),
        'path': path,
        'path_params': list(path_params or []),
        'query_params': list(query_params or []),
    }


def _str(desc: str, required: bool = False, enum: List[str] = None) -> dict:
    return {'type': 'string', 'description': desc, 'required': required,
            'enum': enum}


def _int(desc: str, required: bool = False) -> dict:
    return {'type': 'integer', 'description': desc, 'required': required}


def _bool(desc: str, required: bool = False) -> dict:
    return {'type': 'boolean', 'description': desc, 'required': required}


# ========================================================================
# 注册表（数据驱动；新增工具只需加一条记录）
# ========================================================================

TOOLS: List[dict] = [
    # ---------------- 任务 task（/api/v1/tasks） ----------------
    _tool('task_list', '列出任务（支持 keyword/status 等过滤参数）',
          {'keyword': _str('关键词过滤'), 'status': _str('任务状态'),
           'page': _int('页码'), 'page_size': _int('每页条数')},
          ['task:read'], 'GET', '/api/v1/tasks',
          query_params=['keyword', 'status', 'page', 'page_size']),
    _tool('task_get', '获取任务详情',
          {'task_id': _int('任务 ID', True)},
          ['task:read'], 'GET', '/api/v1/tasks/{task_id}',
          path_params=['task_id']),
    _tool('task_create', '创建任务（body 按任务字段，如 name/type/case_ids 等）',
          {'body': {'type': 'object', 'description': '任务创建参数（name、case_ids 等）'}},
          ['task:create'], 'POST', '/api/v1/tasks'),
    _tool('task_update', '修改任务',
          {'task_id': _int('任务 ID', True),
           'body': {'type': 'object', 'description': '任务修改字段'}},
          ['task:update'], 'PUT', '/api/v1/tasks/{task_id}',
          path_params=['task_id']),
    _tool('task_delete', '删除任务',
          {'task_id': _int('任务 ID', True)},
          ['task:delete'], 'DELETE', '/api/v1/tasks/{task_id}',
          path_params=['task_id']),
    _tool('task_start', '启动任务执行',
          {'task_id': _int('任务 ID', True)},
          ['task:execute'], 'POST', '/api/v1/tasks/{task_id}/start',
          path_params=['task_id']),
    _tool('task_stop', '停止任务执行',
          {'task_id': _int('任务 ID', True)},
          ['task:execute'], 'POST', '/api/v1/tasks/{task_id}/stop',
          path_params=['task_id']),
    _tool('task_control', '控制任务（暂停/继续等控制指令）',
          {'task_id': _int('任务 ID', True),
           'body': {'type': 'object', 'description': '控制指令参数'}},
          ['task:execute'], 'POST', '/api/v1/tasks/{task_id}/control',
          path_params=['task_id']),
    _tool('task_retry', '重试任务',
          {'task_id': _int('任务 ID', True)},
          ['task:execute'], 'POST', '/api/v1/tasks/{task_id}/retry',
          path_params=['task_id']),
    _tool('task_reextract', '重新提取任务结果',
          {'task_id': _int('任务 ID', True)},
          ['task:reextract'], 'POST', '/api/v1/tasks/{task_id}/reextract',
          path_params=['task_id']),
    _tool('task_merge', '合并任务（挑选合并）',
          {'body': {'type': 'object', 'description': '合并参数（来源任务/用例选择等）'}},
          ['task:merge'], 'POST', '/api/v1/tasks/merge'),
    _tool('task_stats', '任务域全量聚合统计',
          {}, ['task:read'], 'GET', '/api/v1/tasks/stats'),
    _tool('task_get_progress', '获取任务执行进度',
          {'task_id': _int('任务 ID', True)},
          ['task:read'], 'GET', '/api/v1/tasks/{task_id}/progress',
          path_params=['task_id']),
    _tool('task_batch_action', '任务批量操作',
          {'body': {'type': 'object', 'description': '批量操作参数（ids/action 等）'}},
          ['task:batch'], 'POST', '/api/v1/tasks/batch-action'),

    # ---------------- 已发布任务 published_task ----------------
    _tool('published_task_list', '列出已发布任务',
          {'page': _int('页码'), 'page_size': _int('每页条数')},
          ['published_task:read'], 'GET', '/api/v1/published-tasks',
          query_params=['page', 'page_size']),
    _tool('published_task_get', '获取已发布任务详情',
          {'published_task_id': _int('已发布任务 ID', True)},
          ['published_task:read'], 'GET', '/api/v1/published-tasks/{published_task_id}',
          path_params=['published_task_id']),
    _tool('published_task_execute', '执行已发布任务',
          {'published_task_id': _int('已发布任务 ID', True)},
          ['published_task:execute'], 'POST',
          '/api/v1/published-tasks/{published_task_id}/execute',
          path_params=['published_task_id']),

    # ---------------- 测试用例 testcase（/api/v1/testcases） ----------------
    _tool('testcase_list', '列出测试用例（支持 keyword/status 等过滤参数）',
          {'keyword': _str('关键词过滤'), 'status': _str('用例状态'),
           'page': _int('页码'), 'page_size': _int('每页条数')},
          ['testcase:read'], 'GET', '/api/v1/testcases',
          query_params=['keyword', 'status', 'page', 'page_size']),
    _tool('testcase_get', '获取测试用例详情',
          {'tc_id': _str('用例 ID', True)},
          ['testcase:read'], 'GET', '/api/v1/testcases/{tc_id}',
          path_params=['tc_id']),
    _tool('testcase_create', '创建测试用例',
          {'body': {'type': 'object', 'description': '用例创建参数（name/type/参数等）'}},
          ['testcase:create'], 'POST', '/api/v1/testcases'),
    _tool('testcase_update', '修改测试用例',
          {'tc_id': _str('用例 ID', True),
           'body': {'type': 'object', 'description': '用例修改字段'}},
          ['testcase:update'], 'PUT', '/api/v1/testcases/{tc_id}',
          path_params=['tc_id']),
    _tool('testcase_delete', '删除测试用例',
          {'tc_id': _str('用例 ID', True)},
          ['testcase:delete'], 'DELETE', '/api/v1/testcases/{tc_id}',
          path_params=['tc_id']),
    _tool('testcase_copy', '复制测试用例',
          {'tc_id': _str('用例 ID', True)},
          ['testcase:copy'], 'POST', '/api/v1/testcases/{tc_id}/copy',
          path_params=['tc_id']),
    _tool('testcase_export', '导出测试用例',
          {'body': {'type': 'object', 'description': '导出参数（ids 等）'}},
          ['testcase:import_export'], 'POST', '/api/v1/testcases/export'),
    _tool('testcase_import', '导入测试用例（multipart file，MCP 场景建议直接调接口）',
          {'body': {'type': 'object', 'description': '导入参数'}},
          ['testcase:import_export'], 'POST', '/api/v1/testcases/import'),

    # ---------------- 音频 audio（/api/v1/audios） ----------------
    _tool('audio_list', '列出音频（支持 keyword 等过滤参数）',
          {'keyword': _str('关键词过滤'), 'page': _int('页码'),
           'page_size': _int('每页条数')},
          ['audio:read'], 'GET', '/api/v1/audios',
          query_params=['keyword', 'page', 'page_size']),
    _tool('audio_get', '获取音频详情',
          {'audio_id': _int('音频 ID', True)},
          ['audio:read'], 'GET', '/api/v1/audios/{audio_id}',
          path_params=['audio_id']),
    _tool('audio_get_by_ids', '按 ID 列表批量获取音频',
          {'ids': {'type': 'array', 'items': {'type': 'integer'},
                   'description': '音频 ID 列表', 'required': True}},
          ['audio:read'], 'POST', '/api/v1/audios/by-ids'),
    _tool('audio_update_metadata', '更新音频元数据',
          {'audio_id': _int('音频 ID', True),
           'body': {'type': 'object', 'description': '元数据字段（name 等）'}},
          ['audio:update'], 'PUT', '/api/v1/audios/{audio_id}/metadata',
          path_params=['audio_id']),
    _tool('audio_convert', '音频转码',
          {'audio_id': _int('音频 ID', True),
           'body': {'type': 'object', 'description': '转码参数（目标格式等）'}},
          ['audio:convert'], 'POST', '/api/v1/audios/{audio_id}/convert',
          path_params=['audio_id']),
    _tool('audio_delete', '删除音频',
          {'audio_id': _int('音频 ID', True)},
          ['audio:delete'], 'DELETE', '/api/v1/audios/{audio_id}',
          path_params=['audio_id']),

    # ---------------- 被测设备 device（/api/v1/test-devices） ----------------
    _tool('device_list', '列出被测设备',
          {'page': _int('页码'), 'page_size': _int('每页条数'),
           'status': _str('设备状态过滤')},
          ['device:read'], 'GET', '/api/v1/test-devices',
          query_params=['page', 'page_size', 'status']),
    _tool('device_get', '获取被测设备详情',
          {'device_id': _int('设备 ID', True)},
          ['device:read'], 'GET', '/api/v1/test-devices/{device_id}',
          path_params=['device_id']),
    _tool('device_create', '创建被测设备',
          {'body': {'type': 'object', 'description': '设备创建参数'}},
          ['device:create'], 'POST', '/api/v1/test-devices'),
    _tool('device_update', '修改被测设备',
          {'device_id': _int('设备 ID', True),
           'body': {'type': 'object', 'description': '设备修改字段'}},
          ['device:update'], 'PUT', '/api/v1/test-devices/{device_id}',
          path_params=['device_id']),
    _tool('device_delete', '删除被测设备',
          {'device_id': _int('设备 ID', True)},
          ['device:delete'], 'DELETE', '/api/v1/test-devices/{device_id}',
          path_params=['device_id']),
    _tool('device_connect', '连接被测设备',
          {'device_id': _int('设备 ID', True)},
          ['device:control'], 'POST', '/api/v1/test-devices/{device_id}/connect',
          path_params=['device_id']),
    _tool('device_disconnect', '断开被测设备',
          {'device_id': _int('设备 ID', True)},
          ['device:control'], 'POST', '/api/v1/test-devices/{device_id}/disconnect',
          path_params=['device_id']),
    _tool('device_reboot', '重启被测设备',
          {'device_id': _int('设备 ID', True)},
          ['device:control'], 'POST', '/api/v1/test-devices/{device_id}/reboot',
          path_params=['device_id']),
    _tool('device_health_check', '被测设备健康检查',
          {'body': {'type': 'object', 'description': '健康检查参数（设备 ID 列表等）'}},
          ['device:control'], 'POST', '/api/v1/test-devices/health-check'),

    # ---------------- 评估 evaluation（/api/v1/evaluation） ----------------
    _tool('evaluation_dimension_list', '列出评估维度',
          {'page': _int('页码'), 'page_size': _int('每页条数'),
           'keyword': _str('关键词过滤')},
          ['evaluation:read'], 'GET', '/api/v1/evaluation/dimensions',
          query_params=['page', 'page_size', 'keyword']),
    _tool('evaluation_dimension_get', '获取评估维度详情',
          {'dim_id': _int('维度 ID', True)},
          ['evaluation:read'], 'GET', '/api/v1/evaluation/dimensions/{dim_id}',
          path_params=['dim_id']),
    _tool('evaluation_dimension_create', '创建评估维度',
          {'body': {'type': 'object', 'description': '维度创建参数'}},
          ['evaluation:dim_manage'], 'POST', '/api/v1/evaluation/dimensions'),
    _tool('evaluation_dimension_update', '修改评估维度',
          {'dim_id': _int('维度 ID', True),
           'body': {'type': 'object', 'description': '维度修改字段'}},
          ['evaluation:dim_manage'], 'PUT',
          '/api/v1/evaluation/dimensions/{dim_id}', path_params=['dim_id']),
    _tool('evaluation_dimension_delete', '删除评估维度',
          {'dim_id': _int('维度 ID', True)},
          ['evaluation:dim_manage'], 'DELETE',
          '/api/v1/evaluation/dimensions/{dim_id}', path_params=['dim_id']),
    _tool('evaluation_category_list', '列出评估分类',
          {}, ['evaluation:read'], 'GET', '/api/v1/evaluation/categories'),
    _tool('evaluation_category_create', '创建评估分类',
          {'body': {'type': 'object', 'description': '分类创建参数'}},
          ['evaluation:category_manage'], 'POST', '/api/v1/evaluation/categories'),
    _tool('evaluation_task_reevaluate', '触发任务重新评估',
          {'body': {'type': 'object', 'description': '任务评估参数（task_id 等）'}},
          ['evaluation:execute'], 'POST', '/api/v1/evaluation/task/reevaluate'),

    # ---------------- 报告 report（/api/v1/reports） ----------------
    _tool('report_list', '列出报告',
          {'page': _int('页码'), 'page_size': _int('每页条数'),
           'keyword': _str('关键词过滤')},
          ['report:read'], 'GET', '/api/v1/reports',
          query_params=['page', 'page_size', 'keyword']),
    _tool('report_get', '获取报告详情',
          {'report_id': _int('报告 ID', True)},
          ['report:read'], 'GET', '/api/v1/reports/{report_id}',
          path_params=['report_id']),
    _tool('report_by_task', '按任务获取报告',
          {'task_id': _int('任务 ID', True)},
          ['report:read'], 'GET', '/api/v1/reports/by_task/{task_id}',
          path_params=['task_id']),
    _tool('report_generate_task', '按任务生成报告',
          {'body': {'type': 'object', 'description': '报告生成参数（task_id 等）'}},
          ['report:create'], 'POST', '/api/v1/reports/generate-task'),
    _tool('report_update', '修改报告',
          {'report_id': _int('报告 ID', True),
           'body': {'type': 'object', 'description': '报告修改字段'}},
          ['report:update'], 'PUT', '/api/v1/reports/{report_id}',
          path_params=['report_id']),
    _tool('report_delete', '删除报告',
          {'report_id': _int('报告 ID', True)},
          ['report:delete'], 'DELETE', '/api/v1/reports/{report_id}',
          path_params=['report_id']),
    _tool('report_publish', '发布报告',
          {'report_id': _int('报告 ID', True)},
          ['report:publish'], 'POST', '/api/v1/reports/{report_id}/publish',
          path_params=['report_id']),
    _tool('report_compare', '报告对比',
          {'body': {'type': 'object', 'description': '对比参数（报告 ID 列表等）'}},
          ['report:compare'], 'POST', '/api/v1/reports/compare'),

    # ---------------- 算法 algorithm（/api/v1/algorithm） ----------------
    _tool('algorithm_definition_list', '列出算法定义',
          {}, ['algorithm:read'], 'GET', '/api/v1/algorithm/definitions'),
    _tool('algorithm_definition_get', '获取算法定义详情',
          {'algo_type': _str('算法类型', True)},
          ['algorithm:read'], 'GET', '/api/v1/algorithm/definitions/{algo_type}',
          path_params=['algo_type']),
    _tool('algorithm_definition_create', '创建算法定义',
          {'body': {'type': 'object', 'description': '算法定义创建参数'}},
          ['algorithm:definition_manage'], 'POST', '/api/v1/algorithm/definitions'),
    _tool('algorithm_definition_update', '修改算法定义',
          {'algo_type': _str('算法类型', True),
           'body': {'type': 'object', 'description': '算法定义修改字段'}},
          ['algorithm:definition_manage'], 'PUT',
          '/api/v1/algorithm/definitions/{algo_type}', path_params=['algo_type']),
    _tool('algorithm_definition_delete', '删除算法定义',
          {'algo_type': _str('算法类型', True)},
          ['algorithm:definition_manage'], 'DELETE',
          '/api/v1/algorithm/definitions/{algo_type}', path_params=['algo_type']),
    _tool('algorithm_group_list', '列出算法分组',
          {}, ['algorithm:read'], 'GET', '/api/v1/algorithm/groups'),
    _tool('algorithm_group_create', '创建算法分组',
          {'body': {'type': 'object', 'description': '算法分组创建参数'}},
          ['algorithm:group_manage'], 'POST', '/api/v1/algorithm/groups'),
    _tool('algorithm_param_list', '列出算法参数',
          {}, ['algorithm:read'], 'GET', '/api/v1/algorithm/params'),
    _tool('algorithm_param_create', '创建算法参数',
          {'body': {'type': 'object', 'description': '算法参数创建参数'}},
          ['algorithm:param_manage'], 'POST', '/api/v1/algorithm/params'),

    # ---------------- 标签 tag（/api/v1/tags） ----------------
    _tool('tag_list', '列出标签',
          {'page': _int('页码'), 'page_size': _int('每页条数'),
           'keyword': _str('关键词过滤')},
          ['tag:read'], 'GET', '/api/v1/tags',
          query_params=['page', 'page_size', 'keyword']),
    _tool('tag_get', '获取标签详情',
          {'tag_id': _int('标签 ID', True)},
          ['tag:read'], 'GET', '/api/v1/tags/{tag_id}',
          path_params=['tag_id']),
    _tool('tag_create', '创建标签',
          {'body': {'type': 'object', 'description': '标签创建参数（name/category 等）'}},
          ['tag:create'], 'POST', '/api/v1/tags'),
    _tool('tag_update', '修改标签',
          {'tag_id': _int('标签 ID', True),
           'body': {'type': 'object', 'description': '标签修改字段'}},
          ['tag:update'], 'PUT', '/api/v1/tags/{tag_id}',
          path_params=['tag_id']),
    _tool('tag_delete', '删除标签',
          {'tag_id': _int('标签 ID', True)},
          ['tag:delete'], 'DELETE', '/api/v1/tags/{tag_id}',
          path_params=['tag_id']),

    # ---------------- 用例分组 group（/api/v1/groups） ----------------
    _tool('group_list', '列出用例分组',
          {}, ['group:read'], 'GET', '/api/v1/groups'),
    _tool('group_create', '创建用例分组',
          {'body': {'type': 'object', 'description': '分组创建参数（name 等）'}},
          ['group:create'], 'POST', '/api/v1/groups'),
    _tool('group_update', '修改用例分组',
          {'group_id': _int('分组 ID', True),
           'body': {'type': 'object', 'description': '分组修改字段'}},
          ['group:update'], 'PUT', '/api/v1/groups/{group_id}',
          path_params=['group_id']),
    _tool('group_delete', '删除用例分组',
          {'group_id': _int('分组 ID', True)},
          ['group:delete'], 'DELETE', '/api/v1/groups/{group_id}',
          path_params=['group_id']),

    # ---------------- 数据可见性分享点 *:share（INT-423） ----------------
    _tool('task_set_visibility', '设置任务可见性分享（public/team/private 等）',
          {'task_id': _int('任务 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['task:share'], 'PATCH', '/api/v1/tasks/{task_id}/visibility',
          path_params=['task_id']),
    _tool('testcase_set_visibility', '设置测试用例可见性分享',
          {'tc_id': _str('用例 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['testcase:share'], 'PATCH', '/api/v1/testcases/{tc_id}/visibility',
          path_params=['tc_id']),
    _tool('report_set_visibility', '设置报告可见性分享',
          {'report_id': _int('报告 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['report:share'], 'PATCH', '/api/v1/reports/{report_id}/visibility',
          path_params=['report_id']),
    _tool('tag_set_visibility', '设置标签可见性分享',
          {'tag_id': _int('标签 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['tag:share'], 'PATCH', '/api/v1/tags/{tag_id}/visibility',
          path_params=['tag_id']),
    _tool('group_set_visibility', '设置用例分组可见性分享',
          {'group_id': _int('分组 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['group:share'], 'PATCH', '/api/v1/groups/{group_id}/visibility',
          path_params=['group_id']),
    _tool('evaluation_dimension_set_visibility',
          '设置评估维度可见性分享',
          {'dim_id': _int('维度 ID', True),
           'visibility': _str('可见性取值', True,
                             enum=['private', 'team', 'public'])},
          ['evaluation:share'], 'PATCH',
          '/api/v1/evaluation/dimensions/{dim_id}/visibility',
          path_params=['dim_id']),

    # ---------------- 数据转移 data-transfer（task:export/import） ----------------
    _tool('data_transfer_export', '导出任务数据（ZIP）',
          {'body': {'type': 'object', 'description': '导出参数（task_id 等）'}},
          ['task:export'], 'POST', '/api/v1/data-transfer/export'),
    _tool('data_transfer_import_preview', '导入预检',
          {'body': {'type': 'object', 'description': '导入预检参数'}},
          ['task:import'], 'POST', '/api/v1/data-transfer/import/preview'),
    _tool('data_transfer_import', '执行任务数据导入',
          {'body': {'type': 'object', 'description': '导入参数'}},
          ['task:import'], 'POST', '/api/v1/data-transfer/import'),

    # ---------------- 收藏 / 回收站 favorites-trash（INT-141） ----------------
    _tool('favorites_list', '列出当前用户收藏 ID 列表',
          {'entity_type': _str('实体类型：task/testcase/report，空=全部')},
          [], 'GET', '/api/v1/favorites', query_params=['entity_type']),
    _tool('task_favorite', '收藏任务',
          {'task_id': _int('任务 ID', True)},
          ['task:read'], 'POST', '/api/v1/tasks/{task_id}/favorite',
          path_params=['task_id']),
    _tool('task_restore', '从回收站恢复任务',
          {'task_id': _int('任务 ID', True)},
          ['task:delete'], 'POST', '/api/v1/tasks/{task_id}/restore',
          path_params=['task_id']),
    _tool('task_purge', '彻底删除任务（purge）',
          {'task_id': _int('任务 ID', True)},
          ['task:delete'], 'DELETE', '/api/v1/tasks/{task_id}/purge',
          path_params=['task_id']),
    _tool('testcase_favorite', '收藏测试用例',
          {'tc_id': _str('用例 ID', True)},
          ['testcase:read'], 'POST', '/api/v1/testcases/{tc_id}/favorite',
          path_params=['tc_id']),
    _tool('report_favorite', '收藏报告',
          {'report_id': _int('报告 ID', True)},
          ['report:read'], 'POST', '/api/v1/reports/{report_id}/favorite',
          path_params=['report_id']),

    # ---------------- Benchmark 排行（INT-429） ----------------
    _tool('benchmark_ranking', '查看 Benchmark 排行',
          {'page': _int('页码'), 'page_size': _int('每页条数')},
          ['benchmark:ranking:read'], 'GET', '/api/v1/benchmarks/ranking',
          query_params=['page', 'page_size']),
    _tool('benchmark_ranking_compute', '触发 Benchmark 排行计算',
          {'body': {'type': 'object', 'description': '计算参数'}},
          ['benchmark:ranking:compute'], 'POST',
          '/api/v1/benchmarks/ranking/compute'),
    _tool('benchmark_baselines', '查看 Benchmark 基线',
          {}, ['benchmark:baseline:read'], 'GET', '/api/v1/benchmarks/baselines'),
    _tool('benchmark_reports', '查看 Benchmark 报告',
          {}, ['benchmark:report:read'], 'GET', '/api/v1/benchmarks/reports'),

    # ---------------- Report Studio（INT-673） ----------------
    _tool('report_studio_create_document', '创建 Report Studio 文档草稿',
          {'body': {'type': 'object', 'description': '文档创建参数'}},
          ['report:studio:create'], 'POST', '/api/v1/report-studio/documents'),
    _tool('report_studio_get_document', '获取 Report Studio 文档',
          {'doc_id': _str('文档 ID', True)},
          ['report:read'], 'GET', '/api/v1/report-studio/documents/{doc_id}',
          path_params=['doc_id']),
    _tool('report_studio_update_document', '编辑 Report Studio 文档',
          {'doc_id': _str('文档 ID', True),
           'body': {'type': 'object', 'description': '文档修改字段'}},
          ['report:studio:edit'], 'PUT',
          '/api/v1/report-studio/documents/{doc_id}', path_params=['doc_id']),
    _tool('report_studio_export_document', 'Report Studio 导出作业',
          {'doc_id': _str('文档 ID', True),
           'body': {'type': 'object', 'description': '导出参数'}},
          ['report:studio:export'], 'POST',
          '/api/v1/report-studio/documents/{doc_id}/exports',
          path_params=['doc_id']),

    # ---------------- 日志只读 log:read（倾向覆盖，负责人验收核对） ----------------
    _tool('log_list', '查看测试执行日志',
          {'page': _int('页码'), 'page_size': _int('每页条数'),
           'keyword': _str('关键词过滤'), 'level': _str('日志级别过滤')},
          ['log:read'], 'GET', '/api/v1/logs',
          query_params=['page', 'page_size', 'keyword', 'level']),
    _tool('log_stats', '日志统计',
          {}, ['log:read'], 'GET', '/api/v1/logs/stats'),
]

# 注册表索引（name → tool）
_TOOL_BY_NAME: Dict[str, dict] = {t['name']: t for t in TOOLS}


def get_tool(name: str) -> dict | None:
    """按工具名取注册项，不存在返回 None。"""
    return _TOOL_BY_NAME.get(name)


def list_tools() -> List[dict]:
    """MCP tools/list 输出（仅暴露 MCP 视角字段）。"""
    return [{'name': t['name'], 'description': t['description'],
             'inputSchema': t['inputSchema']} for t in TOOLS]
