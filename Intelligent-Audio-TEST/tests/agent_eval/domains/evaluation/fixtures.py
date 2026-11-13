# -*- coding: utf-8 -*-
"""INT-2462 评估域样例数据（形状取自 docker 栈 http://localhost:15000 实测）。

只保留断言需要的字段；字段名与 ``api_gateway/schemas/evaluation.py`` 的
``DimensionItem`` / ``CategoryItem`` 一致（服务端 snake_case，None 字段按
``exclude_none`` 口径省略）。
"""

# 维度列表项（GET /api/v1/evaluation/dimensions -> data.items[]）
DIMENSION_ITEM = {
    'id': 121,
    'name': '拒识成功数量',
    'description': '主维度：拒识成功数量。output field_path = n_rate_success。',
    'keywords': 'reject_judge,n_rate_success,拒识成功数量',
    'dimension_type': 'main',
    'parent_dimension_id': None,
    'task_type_code': 'reject_judge',
    'category_id': 3,
    'api_url': 'http://host.docker.internal:5097',
    'api_endpoints': [
        {'url': '', 'name': '', 'priority': 1, 'max_process': 5,
         'max_timeout': 30, 'max_audio_duration': 60, 'endpoint': ''},
    ],
    'api_settings': {'method': 'POST', 'headers': {},
                     'body_template': {'model': '{{model}}'},
                     'timeout': 30000},
    'api_status': 'online',
    'score_unit': '%',
    'type': 'auto',
    'result_type': 0,
    'llm_judge': False,
    'result_min': 0.0,
    'result_max': 100.0,
    'decimal_places': 0,
    'weight': 1,
    'sort_order': 0,
    'estimated_exec_time': 120,
    'rule': {'rules': [], 'defaultScore': 0},
    'statistic_method': 'weighted_sum_ratio',
    'agg_denominator': 'case',
    'exclude_rounds': [],
    'status': True,
    'visibility': 'shared',
    'created_at': '2026-09-23T09:28:28.637660',
    'updated_at': '2026-11-13T12:41:37.628131',
}

# 维度详情（GET /api/v1/evaluation/dimensions/{id} -> data）
DIMENSION_DETAIL = dict(
    DIMENSION_ITEM,
    required_inputs=[
        {'id': 2469, 'dimension_id': 121, 'param_code': 'ai_wav',
         'param_name': '模型回复音频', 'label': '模型回复音频路径(被判定对象)',
         'field_type': 'audio', 'required': False, 'default_value': None,
         'help_text': '模型回复音频路径', 'ui_order': 5},
        {'id': 2472, 'dimension_id': 121, 'param_code': 'is_reject',
         'param_name': '是否为拒识内容', 'label': '是否为拒识内容',
         'field_type': 'boolean', 'required': False, 'default_value': True,
         'help_text': 'True=该轮为拒识内容', 'ui_order': 8},
    ],
    output_fields=[
        {'id': 2479, 'dimension_id': 121, 'param_code': 'n_rate_success',
         'param_name': '拒识成功数量', 'label': '拒识成功数量',
         'field_path': 'n_rate_success', 'field_type': 'number',
         'output_role': 'main', 'agg_role': 'value',
         'visible_in_report': True, 'ui_order': 1},
    ],
    associated_algorithms=[],
    created_by_user_id=None,
)

# 分类项（GET /api/v1/evaluation/categories -> data.items[]）
CATEGORY_ITEM = {
    'id': 3,
    'name': '拒识',
    'description': '拒识类评估维度（非目标人拒识/目标人非交互意图/环境噪声等）',
    'icon': 'fas fa-user-slash',
    'created_at': '2026-09-24T15:22:31.429684',
    'updated_at': '2026-11-13T12:41:37.628131',
}


def enveloped(items, page=1, per_page=10):
    """列表接口统一分页信封（INT-297）。"""
    total = len(items)
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {'success': True, 'code': 0, 'message': 'Success',
            'data': {'items': list(items), 'total': total, 'page': page,
                     'per_page': per_page, 'pages': pages}}


DIMENSION_LIST = enveloped([DIMENSION_ITEM], per_page=10)
CATEGORY_LIST = enveloped([CATEGORY_ITEM], per_page=4)
DIMENSION_DETAIL_ENVELOPE = {'success': True, 'code': 0,
                             'message': 'Success', 'data': DIMENSION_DETAIL}

# 10 条评估域任务：口语 query → 期望动作 / 参数 / 需要断言的返回字段。
# 同一张表离线（FakeRestClient）与实测（docker 网关）共用。
DOMAIN_TASKS = [
    {
        'name': '列出评估维度',
        'query': '平台现在有哪些评估维度？',
        'arguments': {'action': 'dimensions', 'page': 1, 'per_page': 10},
        'tool': 'evaluation_dimension_list',
        'merged': {'page': 1, 'per_page': 10},
        'checks': ('items', 'total', 'page', 'per_page', 'pages'),
    },
    {
        'name': '按分类筛选维度',
        'query': '拒识分类下有哪些评估维度？',
        'arguments': {'action': 'dimensions', 'category_id': 3},
        'tool': 'evaluation_dimension_list',
        'merged': {'category_id': 3},
        'checks': ('items', 'total'),
    },
    {
        'name': '按关键词搜索维度',
        'query': '搜一下包含「拒识」的评估维度',
        'arguments': {'action': 'dimensions', 'search': '拒识',
                      'page': 1, 'per_page': 10},
        'tool': 'evaluation_dimension_list',
        'merged': {'search': '拒识', 'page': 1, 'per_page': 10},
        'checks': ('items', 'total'),
    },
    {
        'name': '分页查询维度',
        'query': '评估维度第二页，每页 2 条',
        'arguments': {'action': 'dimensions', 'page': 2, 'per_page': 2},
        'tool': 'evaluation_dimension_list',
        'merged': {'page': 2, 'per_page': 2},
        'checks': ('page', 'per_page', 'items'),
    },
    {
        'name': '查维度详情',
        'query': '维度 121 的详细配置是什么？',
        'arguments': {'action': 'dimension', 'dim_id': 121},
        'tool': 'evaluation_dimension_get',
        'merged': {'dim_id': 121},
        'checks': ('id', 'name', 'dimension_type', 'category_id'),
    },
    {
        'name': '解释评分口径',
        'query': '维度 121 的评分口径怎么理解？',
        'arguments': {'action': 'dimension', 'dim_id': 121},
        'tool': 'evaluation_dimension_get',
        'merged': {'dim_id': 121},
        'checks': ('score_unit', 'result_type', 'result_min', 'result_max',
                   'decimal_places', 'weight', 'statistic_method',
                   'agg_denominator', 'exclude_rounds', 'rule'),
    },
    {
        'name': '查维度的输入参数',
        'query': '这个维度评估需要哪些输入参数？',
        'arguments': {'action': 'dimension', 'dim_id': 121},
        'tool': 'evaluation_dimension_get',
        'merged': {'dim_id': 121},
        'checks': ('required_inputs',),
    },
    {
        'name': '查维度的输出字段',
        'query': '维度 121 的输出字段和达标线怎么配的？',
        'arguments': {'action': 'dimension', 'dim_id': 121},
        'tool': 'evaluation_dimension_get',
        'merged': {'dim_id': 121},
        'checks': ('output_fields',),
    },
    {
        'name': '查维度可见性',
        'query': '维度 121 是共享还是私有？',
        'arguments': {'action': 'dimension', 'dim_id': 121},
        'tool': 'evaluation_dimension_get',
        'merged': {'dim_id': 121},
        'checks': ('visibility',),
    },
    {
        'name': '列出评估分类',
        'query': '平台有哪些评估分类？',
        'arguments': {'action': 'categories'},
        'tool': 'evaluation_category_list',
        'merged': {},
        'checks': ('items', 'total'),
    },
]

# Skill 触发评测：10 条评估域 query 必须命中 evaluation-config；
# 4 条域外 query 不得命中（交给对应 Skill）。
TRIGGER_POSITIVE = [task['query'] for task in DOMAIN_TASKS] + [
    '评估维度健康检查怎么看？',
    '重评估前置条件是什么？',
    '维度导出的 Excel 有哪些列？',
]
TRIGGER_NEGATIVE = [
    '帮我创建一个任务并启动',
    '导出这份 PDF 报告',
    '校准这台设备的 SPL',
    '音频导入失败怎么办',
]
