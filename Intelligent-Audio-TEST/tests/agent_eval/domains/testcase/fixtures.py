# -*- coding: utf-8 -*-
"""INT-2460 用例 / 标签域样例数据（形状取自 docker 栈 http://localhost:15000 实测）。

字段名与网关 schema 一致（服务端 snake_case）：
- 用例：``api_gateway/schemas/testcase.py`` 的 ``TestCaseListItem`` /
  ``TestCaseDetailData`` / ``TestCaseConfig`` / ``RoundConfigItem``；
- 标签 / 分组：同文件的 ``TagItem`` 与 ``api_gateway/schemas/group.py`` 的 ``GroupItem``；
- 音频详情（含标注）：``audio_service/application/handlers/audio_query_handler.py``
  的 ``_audio_to_dict``；
- 用例参数：``GET /api/v1/algorithm/case-params`` 的 ``data.items[]``。
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, 'golden_tasks.json'), encoding='utf-8') as _fh:
    GOLDEN = json.load(_fh)

TESTCASE_TASKS = GOLDEN['testcase_tasks']
TAG_TASKS = GOLDEN['tag_tasks']
TESTCASE_NEGATIVES = GOLDEN['testcase_negatives']
TAG_NEGATIVES = GOLDEN['tag_negatives']
TESTCASE_TRIGGER_EXTRA = GOLDEN['testcase_trigger_extra']
TAG_TRIGGER_EXTRA = GOLDEN['tag_trigger_extra']

CASE_ID = 'f50b2c8c-c0e7-4ed7-b582-d065da135269'
GROUP_ID = 'efdce97d-f8a5-497d-85f6-8e74ef877ebd'

# 列表项（GET /api/v1/testcases -> data.items[]）
TESTCASE_ITEM = {
    'id': CASE_ID,
    'name': '接线测试_INT2032_C_1026150329',
    'description': 'INT-2032 自建用例 e2e 批量设备/声压',
    'group_id': '5afaa1c4-9b2b-48dc-af9a-25b8d152ea14',
    'group_name': '接线测试_INT2032_组_1026150329',
    'tags': ['接线测试_INT2032标签_1026150329'],
    'config': {
        'rounds': [
            {
                'round_number': 1,
                'audios': [
                    {'audio_id': '2358', 'audio_name': '音频A.wav', 'spl': 65.0,
                     'play_order': 0, 'playback_speaker_group_id': 1},
                    {'audio_id': '2100',
                     'audio_name': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
                     'spl': 65.0, 'play_order': 1,
                     'playback_speaker_group_id': 4},
                ],
                'evaluation': {'enabled': False, 'dimensions': []},
            },
        ],
        'dimensions': [],
        'source_audio': '音频A.wav',
        'auto_generated': False,
    },
    'algorithm_params': None,
    'reference_params': [],
    'algorithm_type': None,
    'strategy_id': None,
    'strategy_overrides': None,
    'created_at': '2026-10-29T16:16:22.469656',
    'updated_at': '2026-10-31T16:36:25.587934',
    'is_favorite': False,
    'deleted': False,
    'deleted_at': None,
    'deleted_by_user_id': None,
    'total_duration': 3.212,
    'visibility': 'shared',
    'created_by_user_id': 1,
    'lab_id': None,
    'lab_name': None,
}

# 详情（GET /api/v1/testcases/{tc_id} -> data）：多 group / audios / dimensions
TESTCASE_DETAIL = dict(
    TESTCASE_ITEM,
    group={'id': '5afaa1c4-9b2b-48dc-af9a-25b8d152ea14',
           'name': '接线测试_INT2032_组_1026150329'},
    audios=[
        {'id': 0, 'audio_id': '2358', 'audio_name': '音频A.wav', 'spl': 65.0,
         'playback_device_id': None, 'play_order': 0},
        {'id': 1, 'audio_id': '2100',
         'audio_name': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
         'spl': 65.0, 'playback_device_id': None, 'play_order': 1},
    ],
    dimensions=[],
)

# 标签项（GET /api/v1/tags -> data.items[]）
TAG_ITEM = {
    'id': 125,
    'name': '单一环境识别-无语义',
    'description': None,
    'color': None,
    'category_id': 7,
    'category_name': '环境理解',
    'created_at': '2026-09-23T15:43:54.528311',
    'updated_at': '2026-09-23T15:43:54.528311',
    'visibility': 'shared',
    'created_by_user_id': 1,
}

# 分组项（GET /api/v1/groups -> data.items[]）
GROUP_ITEM = {
    'id': GROUP_ID,
    'name': '单一环境识别',
    'description': '通过音频上传自动创建的测试用例分组',
    'algorithm_type': '',
    'created_at': '2026-09-23T15:44:24.078846',
    'updated_at': '2026-09-23T15:44:24.078846',
    'test_case_count': 50,
    'visibility': 'shared',
    'created_by_user_id': 1,
}

# 音频详情（GET /api/v1/audios/{audio_id} -> data），含 voice_llm 标注
AUDIO_DETAIL = {
    'id': 2100,
    'name': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
    'original_filename': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
    'file_path': 'D:/00_static/static/audios/环境理解/环境理解/单一环境识别-无语义/'
                 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
    'duration': 1.606,
    'size': 308390,
    'sample_rate': 48000.0,
    'channels': 1,
    'bitrate': 1536000,
    'format': 'wav',
    'audio_type': 'dry',
    'asr_text': '',
    'description': '',
    'source_language': '',
    'md5': '0d6a1c6d9f2b7e4a8c3f5d1b2e9a7c40',
    'visibility': 'shared',
    'created_by_user_id': 1,
    'tags': ['环境理解', '单一环境识别-无语义'],
    'annotations': [
        {
            'format': 'json',
            'code': 'voice_llm',
            'data': {
                'segments': [
                    {
                        'audio': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav',
                        'query': '用户：刚才是什么声音？',
                        'correct_answer': '枪声',
                        'correctness_type': '',
                        'text': ' ',
                        'spl': 65,
                        'playback_device_name': '设备正面（0.5m+0°）',
                        'rail_distance': 80,
                        'volume_level': 60,
                        'voiceprint_enabled': False,
                        'voiceprint_spl': 70,
                        'voiceprint_wait_time': 5,
                        'input_text': '等等，说说科技圈的新闻吧。',
                        'is_reject': True,
                    },
                ],
                'round_number': 2,
            },
            'source_language': '',
            'target_language': '',
        },
    ],
    'created_at': '2026-09-23T15:44:24.078846',
    'updated_at': '2026-11-02T12:48:50.827442',
}

# 用例参数（GET /api/v1/algorithm/case-params -> data.items[]）
CASE_PARAMS = [
    {'id': 43, 'algorithm_type': 'voice_llm', 'param_code': 'interferers',
     'param_name': '干扰人列表', 'label': '干扰人', 'param_type': 'json',
     'required': False, 'default_value': {}, 'help_text': '干扰人配置列表',
     'ui_order': 0, 'hidden': False, 'scope': 'physical',
     'annotation_code': 'voice_llm', 'field_path': 'interferers'},
    {'id': 50, 'algorithm_type': 'voice_llm', 'param_code': 'is_reject',
     'param_name': '是否为拒识内容', 'label': '是否为拒识内容',
     'param_type': 'switch', 'required': False, 'default_value': True,
     'help_text': 'True=该轮为拒识内容', 'ui_order': 7, 'hidden': False,
     'scope': 'common', 'annotation_code': None, 'field_path': None},
    {'id': 224, 'algorithm_type': 'voice_llm', 'param_code': 'input_gap_ms',
     'param_name': '拒识输入间隔', 'label': '拒识输入间隔', 'param_type': 'number',
     'required': False, 'default_value': 0, 'help_text': '静默拒识轮间隔',
     'ui_order': 8, 'hidden': False, 'scope': 'common',
     'annotation_code': None, 'field_path': 'input_gap_ms'},
]


def enveloped(items, page=1, per_page=10):
    """列表接口统一分页信封（INT-297）。"""
    total = len(items)
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {'success': True, 'code': 0, 'message': 'Success',
            'data': {'items': list(items), 'total': total, 'page': page,
                     'per_page': per_page, 'pages': pages}}


TESTCASE_LIST = enveloped([TESTCASE_ITEM])
TESTCASE_DETAIL_ENVELOPE = {'success': True, 'code': 0,
                            'message': 'Success', 'data': TESTCASE_DETAIL}
TESTCASE_STATS = {
    'success': True, 'code': 0, 'message': 'Success',
    'data': {'total_count': 580,
             'by_group': {'单一环境识别': 50},
             'recent_updates': [{'id': CASE_ID, 'name': TESTCASE_ITEM['name'],
                                 'updated_at': '2026-10-31T16:36:25.587934'}]},
}
TAG_LIST = enveloped([TAG_ITEM], per_page=20)
GROUP_LIST = enveloped([GROUP_ITEM], per_page=40)
AUDIO_DETAIL_ENVELOPE = {'success': True, 'code': 0,
                         'message': 'Success', 'data': AUDIO_DETAIL}
CASE_PARAM_LIST = enveloped(CASE_PARAMS, per_page=11)
EXPORT_JOB_STATUS = {
    'success': True, 'code': 0, 'message': 'Success',
    'data': {'task_id': 'export-20261113-01', 'status': 'running',
             'phase': 'exporting', 'progress': 40},
}
REFRESH_STATUS = {
    'success': True, 'code': 0, 'message': 'Success',
    'data': {'task_id': 'refresh-1024', 'status': 'completed',
             'total': 10, 'updated': 10, 'failed': 0, 'progress': 100},
}
REF_PARAMS_MISSING_TEXT = '第 2 轮未生成参考参数'
