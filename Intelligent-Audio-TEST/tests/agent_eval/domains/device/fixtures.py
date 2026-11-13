# -*- coding: utf-8 -*-
"""INT-2459 设备 / SPL 域样例数据（形状取自 docker 栈 http://localhost:15000 实测）。

只保留断言需要的字段；字段名与网关真实返回一致（服务端 snake_case，
None 字段按 ``exclude_none`` 口径省略）。物理域 SPL 的 ``device_id`` 是
**播放设备** ID，数字域用 ``api_id``（被测 API），两者不可混用。
"""

# 被测设备列表项（GET /api/v1/test-devices -> data.items[]）
DEVICE_ITEM = {
    'id': 10,
    'name': 'pura90',
    'model': 'Harmony Device',
    'description': None,
    'type': 'phone',
    'system': 'HarmonyOS',
    'system_version': '1.0.0',
    'app_name': 'Default App',
    'app_version': '1.0.0',
    'location': None,
    'max_audio_duration': None,
    'needs_prompt_audio': False,
    'prompt_config': None,
    'connection_type': 'usb',
    'keywords': 'harmony.doubao.v1',
    'serial_number': '5SM0125701000448',
    'ip': None,
    'status': 'offline',
    'last_online_at': '2026-11-02T20:04:00.385002',
    'created_at': '2026-08-28T14:26:45.697479',
    'updated_at': '2026-11-04T04:40:13.141545',
    'supported_algorithms': ['voice_llm'],
    'lab_id': 1,
    'lab_name': 'LAB-A',
    'driver_name': None,
    'occupied_status': 'occupied',
    'occupied_task_id': 447,
}

# 设备详情（GET /api/v1/test-devices/{id} -> data），少 created_at/updated_at
DEVICE_DETAIL = {key: value for key, value in DEVICE_ITEM.items()
                 if key not in ('created_at', 'updated_at')}

# 设备状态（GET /api/v1/test-devices/status -> data.items[]）
STATUS_ITEM = {
    'id': 10,
    'name': 'pura90',
    'status': 'offline',
    'last_online_at': '2026-11-02T20:04:00.385002',
}
STATUS_ITEM_11 = dict(STATUS_ITEM, id=11, name='pura90gpt')

# 状态历史事件（GET /api/v1/test-devices/status-history -> data.items[]）
STATUS_EVENT = {
    'id': 4988,
    'device_id': 10,
    'device_kind': 'test',
    'event_type': 'health_check',
    'from_status': 'offline',
    'to_status': 'offline',
    'source': 'health_check',
    'success': False,
    'detail': {'serial_number': '5SM0125701000448'},
    'created_at': '2026-11-04T04:40:40.297587',
}

# 设备分组（GET /api/v1/test-devices/device-groups -> data.items[]）
GROUP_ITEM = {
    'id': '3f1c2a9e-0b7d-4a51-9c2e-1a2b3c4d5e6f',
    'name': '实验室 A 设备组',
    'parent_id': None,
    'description': '',
    'group_type': 'test',
    'created_by_user_id': 1,
    'updated_by_user_id': None,
    'created_at': '2026-08-28T14:26:45.697479',
    'updated_at': '2026-08-28T14:26:45.697479',
    'device_ids': [10, 11],
    'device_count': 2,
}

# 告警规则（GET /api/v1/test-devices/alarm-rules -> data.items[]）
ALARM_RULE_ITEM = {
    'id': 7,
    'name': '离线超过 10 分钟',
    'metric_type': 'offline_duration',
    'threshold_value': 600.0,
    'severity': 'warning',
    'notify_email': True,
    'enabled': True,
    'created_by_user_id': 1,
    'updated_by_user_id': None,
    'created_at': '2026-08-28T14:26:45.697479',
    'updated_at': '2026-08-28T14:26:45.697479',
}

# 告警（GET /api/v1/test-devices/alarms -> data.items[]）
ALARM_ITEM = {
    'id': 31,
    'rule_id': 7,
    'rule_name': '离线超过 10 分钟',
    'device_id': 10,
    'device_name': 'pura90',
    'metric_type': 'offline_duration',
    'severity': 'warning',
    'status': 'active',
    'trigger_value': 1200.0,
    'threshold_value': 600.0,
    'content': '设备 pura90 离线 20 分钟',
    'email_sent': False,
    'email_error': None,
    'triggered_at': '2026-11-04T04:40:40.297587',
    'acknowledged_at': None,
    'acknowledged_by': None,
    'resolved_at': None,
}
ALARM_STATS = {'active': 1, 'acknowledged': 0, 'resolved': 0, 'total': 1}

# 可用序列号（GET /api/v1/test-devices/serials -> data[]）
SERIAL_ITEM = {
    'serial': '5SM0125701000448',
    'model': 'Harmony Device',
    'system': 'HarmonyOS',
    'system_version': '1.0.0',
    'ip': None,
    'status': 'offline',
}

# 驱动关键词（GET /api/v1/test-devices/driver-keywords -> data[]）
DRIVER_KEYWORD_ITEM = {
    'name': 'HarmonyOS 基础驱动',
    'keywords': 'harmony.base.v1',
    'system': 'Harmonyos',
}

# 物理域 SPL 映射（GET /api/v1/spl -> data.items[]）
SPL_MAPPING = {
    'id': 3,
    'name': '设备右斜角（1m-90 度）',
    'description': None,
    'device_id': 6,
    'device': {'id': 6, 'name': '设备右斜角（1m+90 度）'},
    'device_name': '设备右斜角（1m+90 度）',
    'device_model': 'Analog (7+8) (RME Fireface 802) [Ch 2]',
    'device_type': None,
    'distance': 1.0,
    'target_spl': 79.0,
    'digital_gain': None,
    'calibration_status': 'calibrated',
    'test_frequency': 1000,
    'calibration_data': None,
    'is_current': True,
    'created_at': '2026-08-19T15:02:05.288577',
    'updated_at': '2026-08-20T10:45:14.269931',
}

SPL_POINTS = [
    {'spl': 79, 'gainOffset': -10, 'baseLevel': -30, 'finalLevel': -40},
    {'spl': 69, 'gainOffset': -20, 'baseLevel': -30, 'finalLevel': -50},
    {'spl': 59, 'gainOffset': -30, 'baseLevel': -30, 'finalLevel': -60},
    {'spl': 52, 'gainOffset': -40, 'baseLevel': -30, 'finalLevel': -70},
]
SPL_MAPPING_DETAIL = dict(SPL_MAPPING,
                          calibration_data={'points': SPL_POINTS})
SPL_STATS = {'total': 3, 'calibrated': 3, 'uncalibrated': 0,
             'associated_devices': 3}
SPL_HISTORY_ITEM = {
    'id': 11,
    'mapping_id': 3,
    'device_id': 6,
    'distance': 1.0,
    'target_spl': 79.0,
    'test_frequency': 1000,
    'calibration_data': {'points': SPL_POINTS},
    'operator': 'dev_user',
    'created_at': '2026-08-20T10:45:14.269931',
}

# 数字域映射（GET /api/v1/digital-spl -> data.items[]）
DIGITAL_SPL_MAPPING = {
    'id': 5,
    'api_id': 2,
    'name': 'Mock WebSocket 映射',
    'vendor': 'mock',
    'protocol': 'websocket',
    'reference_spl': 65.0,
    'reference_gain_linear': 1.0,
    'calibration_status': 'calibrated',
    'calibration_points': [
        {'target_spl': 65.0, 'gain_linear': 1.0, 'rms_dbfs': -35.0},
        {'target_spl': 75.0, 'gain_linear': 3.1623, 'rms_dbfs': -25.0},
    ],
    'min_gain_linear': 0.001,
    'max_gain_linear': 10.0,
    'is_calibrated': True,
    'created_at': '2026-09-01T10:00:00.000000',
    'updated_at': '2026-09-02T10:00:00.000000',
}


def enveloped(items, page=1, per_page=10):
    """列表接口统一分页信封（INT-297）。"""
    total = len(items)
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {'success': True, 'code': 0, 'message': 'Success',
            'data': {'items': list(items), 'total': total, 'page': page,
                     'per_page': per_page, 'pages': pages}}


def single_page(items):
    """无分页语义的单页全量信封（spl_history / spl_by_device）。"""
    total = len(items)
    return {'success': True, 'code': 0, 'message': 'Success',
            'data': {'items': list(items), 'total': total, 'page': 1,
                     'per_page': total or 1, 'pages': 1}}


# ---------------------------------------------------------------- 10 条域任务
# 6 条设备查询 + 4 条 SPL 查询；``tool`` 是解析后的目标工具名，``merged`` 是
# 工具层层归一后真正发给 REST 的参数（与 FakeRest / 真实网关共用同一张表）。
DOMAIN_TASKS = [
    {
        'name': '设备列表分页',
        'query': '看一下设备列表，第 1 页每页 10 条',
        'arguments': {'action': 'list', 'page': 1, 'per_page': 10},
        'tool': 'device_list',
        'merged': {'page': 1, 'per_page': 10},
        'checks': ('items', 'total', 'page', 'per_page', 'pages'),
    },
    {
        'name': '查设备详情',
        'query': '设备 10 的型号、系统版本和实验室是什么',
        'arguments': {'action': 'detail', 'device_id': 10},
        'tool': 'device_get',
        'merged': {'device_id': 10},
        'checks': ('id', 'name', 'model', 'system', 'system_version',
                   'lab_name'),
    },
    {
        'name': '查设备分组',
        'query': '设备分组里有哪些组，各有多少台设备',
        'arguments': {'action': 'groups', 'page': 1, 'per_page': 50},
        'tool': 'device_group_list',
        'merged': {'page': 1, 'per_page': 50},
        'checks': ('items', 'total', 'pages'),
    },
    {
        'name': '查设备状态与占用',
        'query': '设备 10、11 现在是在线还是离线，有没有被占用',
        'arguments': {'action': 'status', 'ids': [10, 11]},
        'tool': 'device_status_list',
        # 数组按服务端契约转逗号串（重复参数会被 request.args 只留最后一个值）
        'merged': {'ids': '10,11'},
        'checks': ('items', 'total'),
    },
    {
        'name': '查状态历史 / 健康检查事件',
        'query': '设备 10 最近一次健康检查的状态',
        'arguments': {'action': 'status_history', 'device_id': 10,
                      'page': 1, 'per_page': 3},
        'tool': 'device_get_status_history',
        'merged': {'device_id': 10, 'page': 1, 'per_page': 3},
        'checks': ('items', 'total'),
    },
    {
        'name': '查告警列表',
        'query': '有哪些未确认的设备告警',
        'arguments': {'action': 'alarms', 'status': 'active', 'page': 1,
                      'per_page': 10},
        'tool': 'device_alarm_list',
        'merged': {'status': 'active', 'page': 1, 'per_page': 10},
        'checks': ('items', 'total', 'stats'),
    },
    {
        'name': '查 SPL 映射列表',
        'query': '看一下已校准的 SPL 映射',
        'arguments': {'action': 'spl_mappings', 'calibration_status':
                      'calibrated', 'page': 1, 'per_page': 10},
        'tool': 'spl_mapping_list',
        'merged': {'calibration_status': 'calibrated', 'page': 1,
                   'per_page': 10},
        'checks': ('items', 'total', 'pages'),
    },
    {
        'name': '查 SPL 映射详情',
        'query': 'SPL 映射 3 的目标声压级和校准状态',
        'arguments': {'action': 'spl_mapping', 'mapping_id': 3},
        'tool': 'spl_mapping_get',
        'merged': {'mapping_id': 3},
        'checks': ('id', 'target_spl', 'calibration_status', 'device_name'),
    },
    {
        'name': '查 SPL 校准历史',
        'query': '映射 3 的校准历史给我',
        'arguments': {'action': 'spl_history', 'mapping_id': 3},
        'tool': 'spl_mapping_history',
        'merged': {'mapping_id': 3},
        'checks': ('items', 'total'),
    },
    {
        'name': '查 SPL 最新校准点集',
        'query': '映射 3 的校准点集（测试音校准点）是什么',
        'arguments': {'action': 'spl_calibration_data', 'mapping_id': 3},
        'tool': 'spl_mapping_calibration_data',
        'merged': {'mapping_id': 3},
        'checks': ('points',),
    },
]

# ---------------------------------------------------------------- Skill 触发评测
# 正例：每个 Skill 各 10+ 条口语 query；负例：其它域的问题不得误命中本 Skill。

DEVICE_TRIGGER_POSITIVE = [
    '看一下设备列表，第 1 页每页 10 条',
    '设备 10 的详情、系统版本和绑定的实验室是什么',
    '设备分组里有哪些组',
    '设备 10、11 现在是在线还是离线',
    '最近有哪些设备告警，级别分别是什么',
    '告警规则里离线时长的阈值是多少',
    '可用设备序列号有哪些',
    '设备驱动关键词有哪些',
    '设备 10 最近一次健康检查状态',
    '怎么连接和重启这台设备',
    '设备状态历史最近 7 天',
    '设备扫描能发现哪些设备',
]

SPL_TRIGGER_POSITIVE = [
    '看一下 SPL 映射列表，只要已校准的',
    'SPL 映射 3 的详情和目标声压级是多少',
    '映射 3 的校准历史给我',
    '这个映射的最新校准点集和测试音数据',
    '数字域 RMS→SPL 映射有哪些',
    '按 API 查数字 SPL 映射',
    '这台设备的 SPL 校准状态怎么样',
    'SPL 统计里有多少条已校准',
    '播放设备的声压级校准怎么配',
    '测试音播放前需要满足什么校准条件',
    '增益偏移和 dB 怎么换算',
    '未校准的 SPL 映射有哪些',
]

DRIVER_TRIGGER_POSITIVE = [
    '帮我把这个 App 的页面元素生成驱动代码提案',
    'UiAutoDev 导出的元素树能提一份 AppDriver 驱动提案吗',
    '为这个厂商 API 生成 ApiVendorAdapter 适配器代码',
    '现有的驱动能不能复用，帮我出一版驱动提案',
    '这个 App 的元素和操作步骤整理成驱动提案，先不要发布',
    'UiAutoDev 元素到驱动代码的映射规则是什么',
    '生成 AppDriver 需要哪些元素信息',
    '驱动提案会直接发布吗，还是只出草案',
    '帮我为这个新 App 准备驱动代码和适配器',
    'ApiVendorAdapter 适配器要覆盖哪些端点',
]

OFF_DOMAIN = [
    '帮我创建一个任务并启动',
    '导出这份 PDF 报告',
    '音频导入失败怎么办',
    '评估维度 121 的权重怎么配',
]

# 每个 Skill 的负例：其它两个域各取 2 条 + 域外问题
TRIGGER_NEGATIVE = {
    'device-operations': (SPL_TRIGGER_POSITIVE[0], SPL_TRIGGER_POSITIVE[1],
                          DRIVER_TRIGGER_POSITIVE[0], OFF_DOMAIN[0],
                          OFF_DOMAIN[2]),
    'spl-calibration': (DEVICE_TRIGGER_POSITIVE[0], DEVICE_TRIGGER_POSITIVE[3],
                        DRIVER_TRIGGER_POSITIVE[1], OFF_DOMAIN[1],
                        OFF_DOMAIN[3]),
    'driver-proposal': (DEVICE_TRIGGER_POSITIVE[4], DEVICE_TRIGGER_POSITIVE[6],
                        SPL_TRIGGER_POSITIVE[0], SPL_TRIGGER_POSITIVE[2],
                        OFF_DOMAIN[0]),
}
