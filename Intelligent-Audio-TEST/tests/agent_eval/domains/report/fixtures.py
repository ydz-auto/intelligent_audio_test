# -*- coding: utf-8 -*-
"""INT-2463 报告域样例数据（形状取自 docker 栈 http://localhost:15000 实测）。

只保留断言需要的字段；字段名与 ``api_gateway/schemas/report.py`` 的
``ReportListItem`` / ``ReportDetailData`` 一致（服务端 snake_case）。
样例报告 426 是任务报告、395 是对比报告、424 是二次对比报告——与实测库一致。
"""

# 报告列表项（GET /api/v1/reports -> data.items[]）
LIST_ITEM = {
    'id': 426,
    'task_id': 460,
    'name': '全类型覆盖报告_task460_20261031-100112',
    'description': '3 类 API + 3 台实体设备全链路测试报告',
    'type': 'task',
    'report_type': 'task',
    'status': 'published',
    'config': {'name': '全类型覆盖报告_task460_20261031-100112',
               'description': '3 类 API + 3 台实体设备全链路测试报告'},
    'analysis': '',
    'conclusion': '',
    'created_at': '2026-10-31 18:01:13.784679',
    'visibility': 'shared',
    'created_by_user_id': 1,
    'deleted': False,
    'deleted_at': None,
    'deleted_by_user_id': None,
    'is_favorite': False,
    'task_name': '全类型覆盖任务',
    'summary': {
        'total_cases': 2,
        'completed_cases': 2,
        'failed_cases': 0,
        'pass_rate': 100.0,
        'review_count': 0,
        'task_count': 0,
    },
    'summaries': [],
    'cases': [],
    'metric_stats': [],
    'raw_data': [],
}

# 指标定义（summary.all_metrics[]）
ALL_METRICS = [
    {'id': 72, 'name': '逐轮话轮评估', 'unit': '%', 'decimal_places': 2,
     'statistic_method': 'ratio', 'agg_denominator': 'round',
     'sort_order': 1, 'dimension_type': 'main',
     'parent_dimension_id': None, 'parent_dimension_name': None},
    {'id': 88, 'name': '接管内容平均分', 'unit': '%', 'decimal_places': 2,
     'statistic_method': 'average', 'agg_denominator': 'case',
     'sort_order': 2, 'dimension_type': 'sub',
     'parent_dimension_id': 72, 'parent_dimension_name': '逐轮话轮评估'},
]

RESOURCE_HEADERS = [
    {'key': '10-pura90豆包-1.0.0', 'label': '10-pura90豆包-1.0.0',
     'type': 'device', 'id': 10, 'name': 'pura90豆包', 'version': '1.0.0',
     'editable': True},
    {'key': '9-pura90小艺-1.0.0', 'label': '9-pura90小艺-1.0.0',
     'type': 'device', 'id': 9, 'name': 'pura90小艺', 'version': '1.0.0',
     'editable': True},
]

SUMMARY = {
    'total_cases': 2,
    'completed_cases': 2,
    'failed_cases': 0,
    'pass_rate': 100.0,
    'resources': ['10-pura90豆包-1.0.0', '9-pura90小艺-1.0.0'],
    'resource_headers': RESOURCE_HEADERS,
    'all_metrics': ALL_METRICS,
    'metric_data': [
        {'resource': '10-pura90豆包-1.0.0',
         'metrics': [{'id': 72, 'metric': '逐轮话轮评估', 'value': 100.0},
                     {'id': 88, 'metric': '接管内容平均分', 'value': 0.85}]},
        {'resource': '9-pura90小艺-1.0.0',
         'metrics': [{'id': 72, 'metric': '逐轮话轮评估', 'value': 100.0},
                     {'id': 88, 'metric': '接管内容平均分', 'value': 0.85}]},
    ],
    'tag_metric_data': [
        {'resource': '10-pura90豆包-1.0.0',
         'tags': [{'tag_id': 'default_tag', 'tag_name': 'default_tag',
                   'metrics': [{'id': 88, 'metric': '接管内容平均分',
                                'value': 0.85}]}]},
    ],
    'tag_category_metric_data': [],
    'case_type_stats': [
        {'group_id': 'bee889ee-8c56-467a-a60f-353acccf441a',
         'group_name': '话轮接管',
         'metrics': [{'id': 72, 'metric': '逐轮话轮评估', 'value': 100.0}]},
    ],
    'device_stats': [
        {'id': 10, 'name': 'pura90豆包', 'model': 'Harmony Device',
         'type': 'phone', 'system': 'HarmonyOS', 'system_version': '1.0.0',
         'status': 'online',
         'metrics': {'逐轮话轮评估': 100.0, '接管内容平均分': 0.85},
         'total_cases': 2, 'completed_cases': 2, 'failed_cases': 0,
         'success_rate': 100.0},
    ],
    'api_stats': [],
    'devices': [{'id': 10, 'name': 'pura90豆包', 'model': 'Harmony Device',
                 'type': 'phone', 'system': 'HarmonyOS',
                 'system_version': '1.0.0', 'status': 'online'}],
    'apis': [],
    'raw_data': [
        {'resource': '10-pura90豆包-1.0.0',
         'metrics': [{'metric': '接管内容平均分', 'values': [0.85, 0.85]}]},
    ],
    'case_categories': [{'id': 'bee889ee-8c56-467a-a60f-353acccf441a',
                         'name': '话轮接管'}],
    'all_case_tags': [{'id': 74, 'name': '话轮接管', 'category_id': None,
                       'category_name': None}],
    'field_mappings': {},
}

# 报告详情（GET /api/v1/reports/{report_id} -> data）
DETAIL = dict(
    LIST_ITEM,
    summary=SUMMARY,
    summaries=[{'id': 426, 'report_id': 426, 'metric_name': 'summary',
                'metric_value': 100.0,
                'metadata': {'task_ids': [], 'total_cases': 2,
                             'completed_cases': 2, 'failed_cases': 0,
                             'pass_rate': 100.0, 'review_count': 0,
                             'duration': 573.0}}],
)

# 对比报告详情（type=comparison）：summary 里是指标矩阵
COMPARISON_DETAIL = dict(
    DETAIL,
    id=395,
    task_id=0,
    name='任务对比报告_豆包-话轮接管_小艺E2E测试任务',
    type='comparison',
    report_type='comparison',
    status='draft',
    visibility='shared',
    summary=dict(
        SUMMARY,
        total_cases=774,
        completed_cases=774,
        failed_cases=0,
        pass_rate=84.24,
        metric_data=[
            {'resource': '10-pura90豆包-1.0.0',
             'metrics': [{'id': 66, 'metric': '停止指令遵循', 'value': 67.74},
                         {'id': 69, 'metric': '响应时延',
                          'value': 1550.645790909091}]},
        ],
    ),
    summaries=[{'id': 395, 'report_id': 395, 'metric_name': 'summary',
                'metric_value': 84.24,
                'metadata': {'task_ids': [402, 407], 'total_cases': 774,
                             'pass_rate': 84.24}}],
)

# 二次对比报告详情（type=secondary_comparison）
SECONDARY_DETAIL = dict(
    DETAIL,
    id=424,
    task_id=0,
    name='二次对比报告_20261029163619',
    type='secondary_comparison',
    report_type='secondary_comparison',
    status='draft',
    summary=dict(SUMMARY, total_cases=775, completed_cases=726,
                 failed_cases=31, pass_rate=93.68),
    summaries=[{'id': 424, 'report_id': 424, 'metric_name': 'summary',
                'metric_value': 93.68,
                'metadata': {'task_ids': [402, 407], 'total_cases': 775,
                             'completed_cases': 726, 'failed_cases': 31,
                             'pass_rate': 93.68}}],
)

# 报告内用例（GET /api/v1/reports/{id}/cases -> data.items[]）
CASE_ITEM = {
    'id': '964adf95-6d88-456f-ae9f-834c0ef7d1d5',
    'name': '测试用例_JG0080_单轮接管-正常接管_silence.wav',
    'description': '自动从音频创建的测试用例',
    'category': '话轮接管',
    'tags': [{'name': None}],
    'algorithmType': 'voice_llm',
    'audios': [],
    'referenceParams': [],
    'results': [],
    'logs': [],
    'algorithmResults': [],
    'metrics': [
        {'resource': '9-pura90小艺-1.0.0',
         'metrics': [
             {'id': 72, 'value': 0.85, 'metric': '逐轮话轮评估',
              'round_number': None, 'dimension_type': 'main',
              'parent_dimension_id': None, 'parent_dimension_name': None},
             {'id': 88, 'value': 0.85, 'metric': '接管内容平均分',
              'round_number': None, 'dimension_type': 'sub',
              'parent_dimension_id': 72,
              'parent_dimension_name': '逐轮话轮评估'},
         ]},
    ],
}

# 页签计数（GET /api/v1/reports/tab-counts -> data）
TAB_COUNTS = {
    'all': 60, 'draft': 55, 'published': 5, 'comparison': 4,
    'types': {'task': 56, 'comparison': 1, 'secondary_comparison': 3,
              'benchmark': 0},
    'favorite': 0,
}

# 统计分析（GET /api/v1/reports/statistics -> data）
STATISTICS = {
    'dimension': 'time',
    'overview': {'report_count': 60, 'completed_reports': 5,
                 'total_cases': 4825, 'completed_cases': 3111,
                 'failed_cases': 584, 'pass_rate': 61.95,
                 'duration': 63237.0},
    'detail': [{'group': '2026-10-31', 'report_count': 2,
                'completed_reports': 1, 'total_cases': 318,
                'completed_cases': 312, 'failed_cases': 3,
                'pass_rate': 98.11, 'duration': 2668.0}],
    'chart': {'categories': ['2026-10-31'],
              'series': [{'name': '报告数', 'data': [2]}]},
    'anomaly': [{'type': 'low_pass_rate', 'report_id': 258,
                 'report_name': '低通过率报告', 'message': '通过率偏低',
                 'value': 14.29}],
    'time_range': {'start_time': '2026-08-15T20:31:42.111844',
                   'end_time': None},
}

# 趋势（GET /api/v1/reports/statistics/trend -> data）
TREND = {
    'trend_type': 'time',
    'time_trend': [
        {'date': '2026-10-31', 'report_count': 2, 'total_cases': 318,
         'pass_rate': 98.11, 'duration': 2668.0},
        {'date': '2026-10-29', 'report_count': 4, 'total_cases': 205,
         'pass_rate': 77.78, 'duration': 1088.0},
    ],
    'dimension_trend': [],
    'time_range': {'start_time': '2026-08-15T20:31:42.263511',
                   'end_time': None},
}

# 用例指标均值（POST /api/v1/reports/case-averages -> data）
CASE_AVERAGES = {
    'total_cases': 2,
    'total_results': 12,
    'overall_averages': [
        {'id': 72, 'metric': '逐轮话轮评估', 'value': 100.0},
        {'id': 88, 'metric': '接管内容平均分', 'value': 0.8499999999999998},
    ],
    'overall_averages_map': {'逐轮话轮评估': 100.0,
                             '接管内容平均分': 0.8499999999999998},
    'metric_data': [
        {'resource': '1-mock http 单轮 dut',
         'categories': [{'categoryId': '话轮接管', 'categoryName': '话轮接管',
                         'metrics': [{'id': 88, 'metric': '接管内容平均分',
                                      'value': 0.85}]}]},
    ],
    'tag_metric_data': [],
    'raw_data': [],
    'normal_distribution': {},
    'resources': ['1-mock http 单轮 dut'],
    'resource_headers': [{'key': '1-mock http 单轮 dut',
                          'label': 'mock http 单轮 dut', 'type': 'api',
                          'id': 1, 'name': 'mock http 单轮 dut',
                          'version': None, 'editable': True}],
    'filters': {'category': '', 'tags': []},
    'partial': False,
    'missing_case_ids': [],
    'aggregation_degraded': False,
    'aggregation_coverage': {},
}

# 生成进度（GET /api/v1/reports/{report_id}/progress -> data）
PROGRESS = {'report_id': 426, 'task_id': 460, 'status': 'completed',
            'progress': 100, 'report_status': 'published'}


def enveloped(items, page=1, per_page=20):
    """列表接口统一分页信封（INT-297）。"""
    total = len(items)
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {'success': True, 'code': 0, 'message': 'Success',
            'data': {'items': list(items), 'total': total, 'page': page,
                     'per_page': per_page, 'pages': pages}}


def ok(data):
    return {'success': True, 'code': 0, 'message': 'Success', 'data': data}


REPORT_LIST = enveloped([LIST_ITEM], per_page=10)
CASES_PAGE = enveloped([CASE_ITEM], per_page=20)

# 10 条报告域任务：口语 query → 期望动作 / 参数 / 需要断言的返回字段。
# 取数 6 条（report_query）+ 对比 4 条（report_compare），与卡面可测标准 1 一致。
# 同一张表离线（FakeRestClient）与实测（docker 网关）共用。
DOMAIN_TASKS = [
    {
        'name': '列出草稿报告',
        'query': '现在有哪些草稿报告？',
        'tool': 'report_query',
        'arguments': {'action': 'list', 'status': 'draft',
                      'page': 1, 'per_page': 10},
        'merged': {'status': 'draft', 'page': 1, 'per_page': 10},
        'mcp': 'report_list',
        'checks': ('items', 'total', 'page', 'per_page', 'pages'),
    },
    {
        'name': '按任务查报告',
        'query': '任务 460 的报告在哪？',
        'tool': 'report_query',
        'arguments': {'action': 'by_task', 'task_id': 460},
        'merged': {'task_id': 460},
        'mcp': 'report_by_task',
        'checks': ('id', 'name', 'type', 'status'),
    },
    {
        'name': '看报告详情指标',
        'query': '报告 426 的指标和通过率是多少？',
        'tool': 'report_query',
        'arguments': {'action': 'detail', 'report_id': 426},
        'merged': {'report_id': 426},
        'mcp': 'report_get',
        'checks': ('id', 'name', 'summary', 'analysis', 'conclusion'),
    },
    {
        'name': '查页签计数',
        'query': '报告中心各个页签有多少条？',
        'tool': 'report_query',
        'arguments': {'action': 'tab_counts'},
        'merged': {},
        'mcp': 'report_tab_counts',
        'checks': ('all', 'draft', 'published', 'comparison', 'types',
                   'favorite'),
    },
    {
        'name': '按设备类型看统计',
        'query': '按设备类型统计一下报告通过率',
        'tool': 'report_query',
        'arguments': {'action': 'statistics', 'dimension': 'device_type'},
        'merged': {'dimension': 'device_type'},
        'mcp': 'report_statistics',
        'checks': ('dimension', 'overview', 'detail', 'chart', 'anomaly'),
    },
    {
        'name': '看报告内用例',
        'query': '报告 426 里的用例列一下，只看话轮接管的',
        'tool': 'report_query',
        'arguments': {'action': 'cases', 'report_id': 426,
                      'category': '话轮接管', 'page': 1, 'per_page': 20},
        'merged': {'report_id': 426, 'category': '话轮接管',
                   'page': 1, 'per_page': 20},
        'mcp': 'report_cases',
        'checks': ('items', 'total', 'page', 'per_page', 'pages'),
    },
    {
        'name': '两份报告并排对比',
        'query': '帮我对比一下报告 426 和 425',
        'tool': 'report_compare',
        'arguments': {'action': 'compare', 'report_ids': [426, 425]},
        'checks': ('action', 'report_count', 'reports', 'missing'),
    },
    {
        'name': '三份报告并排对比',
        'query': '把 426、425、423 三份报告的指标并排列出来',
        'tool': 'report_compare',
        'arguments': {'action': 'compare', 'report_ids': [426, 425, 423]},
        'checks': ('report_count', 'reports'),
    },
    {
        'name': '二次对比已有对比报告',
        'query': '这两份对比报告再做一次二次对比',
        'tool': 'report_compare',
        'arguments': {'action': 'secondary_compare', 'report_ids': [424, 395]},
        'checks': ('action', 'reports'),
    },
    {
        'name': '看报告趋势',
        'query': '最近一个月的通过率趋势怎么走？',
        'tool': 'report_compare',
        'arguments': {'action': 'trend', 'trend_type': 'time',
                      'metric': 'pass_rate'},
        'checks': ('trend_type', 'time_trend', 'dimension_trend',
                   'time_range'),
    },
]

# Skill 触发评测：报告取数类 query 必须命中 report-studio，
# 对比 / 趋势类必须命中 report-compare；域外 query 不得命中这两个 Skill。
STUDIO_POSITIVE = [task['query'] for task in DOMAIN_TASKS
                   if task['tool'] == 'report_query'] + [
    '报告 426 的描述和分析写了什么？',
    '报告里「接管内容平均分」的单位和小数位是什么？',
    '这份报告生成到哪一步了？',
    '按时间统计一下报告数量和通过率',
    '报告 426 的用例平均值是多少？',
]

COMPARE_POSITIVE = [task['query'] for task in DOMAIN_TASKS
                    if task['tool'] == 'report_compare'] + [
    '这几份报告通过率差异在哪？',
    '报告趋势图的数据从哪取？',
    '哪份报告通过率异常偏低？',
]

TRIGGER_NEGATIVE = [
    '帮我创建一个任务并启动',
    '校准这台设备的 SPL',
    '音频导入失败怎么办',
    '评估维度 121 的评分口径是什么？',
    'voice_llm 的算法参数怎么配？',
    '把这条测试复制到另一个分组',
]
