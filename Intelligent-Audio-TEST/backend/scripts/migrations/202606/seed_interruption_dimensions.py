# -*- coding: utf-8 -*-
"""
打断指标维度种子数据（打断成功率主维度 + 两个时延子维度）

功能：
1. 软删除历史单维度 interruption_metrics（name='打断指标'，已被主+子维度方案替代）
2. 注册/更新打断成功率主维度（dimension_type='main'）：
   - 配置全部 input params、api_settings、body_template、param_mappings
   - 配置打断成功率 output params（interruption_success_rate 等）
   - 包含 LLM 评估 output params
3. 注册/更新5个子维度（dimension_type='sub'，parent_dimension_id 指向主维度）：
   - 打断检查时延 → output field_path = avg_stop_latency_s
   - 打断恢复时延 → output field_path = avg_recovery_latency_s
   - 子维度不重复 input params / param_mappings，由 evaluation_service._load_dimension_data
     的继承逻辑从父维度合并 input_params；param_mappings 不按 dimension_id 过滤
     （主调用路径 dimension_ids=None），挂在主维度 id 下即可被子维度共用
4. 注册 voice_llm 算法与主维度 + 5个子维度的关联（algorithm_dimension_relations）
5. 注册 voice_llm → 主维度的参数映射（param_mappings.dimension_id = 主维度id）

执行链路：
   用例选主维度 + 5个子维度 → 继承父维度 task_type_code/api 配置 → 被
   (endpoint_url, task_type_code) 分到同一组 → 调一次 eval_server
   → process_group_dimension_results 把同一份响应按各自 output field_path 分发提取

对应 eval_server 服务：
   - eval_server/app/services/xiaoyi_metrics/turn_taking/__init__.py
   - 入口：calculate_interruption_metrics(task_params)
   - 一次返回包含 success_rate/stop_latency/recovery_latency 的 JSON

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_interruption_dimensions

或直接：
    python backend/scripts/migrations/202606/seed_interruption_dimensions.py

注意：此脚本可重复执行（幂等）
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# eval_server 微服务地址（本机 5002，见 eval_server/app/config.py PORT=5002）
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:5000')

# ============================================================
# 主维度定义：打断成功率（配 input + output + api_settings + param_mappings）
# ============================================================
MAIN_DIMENSION = {
    'task_type_code': 'interruption_metrics',
    'name': '打断成功率',
    'keywords': '打断,interruption,success_rate,打断成功率,barge-in',
    'description': (
        '打断成功率主维度：用户打断小艺时衡量停得下、恢复得来。'
        '入参为两路 wav（user_wav + ai_wav），eval_server 内部调 asr_server 转成 ASR 词级时间戳后，'
        '计算打断成功率、打断检查时延、打断恢复时延。'
        '主维度配 input params + 打断成功率 output params + LLM 评估 output params。'
        '参考 Full-Duplex-Bench v1.5 get_timing.py 与 v1.0 eval_user_interruption.py'
    ),
    'type': 'auto',
    'result_type': 0,
    'result_min': 0.0,
    'result_max': 1.0,
    'decimal_places': 3,
    'weight': 1,
    'estimated_exec_time': 30,
    'score_unit': '',
    'statistic_method': 'average',
    'body_template': {
        'seg_merge_gap_s': '{{seg_merge_gap_s}}',
        'enable_llm_eval': '{{enable_llm_eval}}',
        'llm_model': '{{llm_model}}',
        'original_topic': '{{original_topic}}',
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
                'query': '{{query}}',
                'answer': '{{answer}}',
                'is_return_to_topic': '{{is_return_to_topic}}',
            }
        ],
    },
    'params': [
        # ─── 输入参数：两路 wav（eval_server 内部调 asr_server 转 chunks）───
        ('user_wav', '用户打断音频', '用户打断语音 wav', 'audio', 'input',
         None, None, None, True,
         False, None, '用户打断语音 wav 路径；eval_server 内部调 asr_server 转 ASR 词级时间戳', 5),
        ('ai_wav', '模型恢复音频', '模型恢复语音 wav', 'audio', 'input',
         None, None, None, True,
         False, None, '模型恢复语音 wav 路径；与 user_wav 各调一次 ASR 后对齐算打断', 6),
        ('seg_merge_gap_s', '词合并间隙', '词合并为段的间隙阈值(秒)', 'number', 'input',
         None, None, None, False,
         False, '3.0', '相邻词时间戳间隙小于该值则合并为同一段(秒)', 11),

        # ─── 输入参数: 大模型评估（可选）───
        ('rounds', '多轮文本', '多轮对话文本结构(用于大模型评估)', 'json', 'input',
         None, None, None, False,
         False, None,
         '多轮文本结构 [{query, answer, is_return_to_topic}]，'
         '与 user_wav/ai_wav 解耦；enable_llm_eval=True 时才使用', 12),
        ('enable_llm_eval', '启用LLM评估', '是否启用大模型评估', 'boolean', 'input',
         None, None, None, False,
         False, 'true', '默认开启：对每轮打断后回复与回到原话题行为做 LLM 评估；'
         '显式传 false 才关闭(需配置 LLM_JUDGE_API_KEY)', 13),
        ('llm_model', 'LLM模型', 'LLM 模型名称(覆盖默认)', 'text', 'input',
         None, None, None, False,
         False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认', 14),
        ('original_topic', '原始话题', '原始话题文本', 'text', 'input',
         None, None, None, False,
         False, None, '原始话题文本，供回到原话题行为判断/打分使用', 15),

        # ─── 输出参数: 打断成功率（主分）───
        ('interruption_success_rate', '打断成功率', '打断成功率', 'number', 'output',
         'interruption.interruption_success_rate', 'value', 'main', True,
         False, None, '打断成功率(0~1，让出且恢复 / 有效打断事件)', 60),
        ('interruption_stop_rate', '让出率', '让出率', 'number', 'output',
         'interruption.stop_rate', None, 'aux', True,
         False, None, '让出率: 模型没说穿整个打断区间的事件占比', 61),
        ('interruption_resume_rate', '恢复率', '恢复率', 'number', 'output',
         'interruption.resume_rate', None, 'aux', True,
         False, None, '停下后恢复的打断事件占比', 62),
        ('interruption_n_events', '打断事件数', '打断事件数', 'number', 'output',
         'interruption.n_events', None, 'aux', True,
         False, None, '有效打断事件数(模型当时在说话)', 63),
        ('interruption_n_user_segments', '用户段数', '用户段数', 'number', 'output',
         'interruption.n_user_segments', None, 'aux', True,
         False, None, '用户语音段总数', 64),
        ('interruption_n_recovery_only', '退化事件数', '退化事件数', 'number', 'output',
         'interruption.n_recovery_only', None, 'aux', True,
         False, None, '只算到恢复时延的事件数(ai_wav 可能只含恢复段)', 65),
        ('interruption_n_no_model_speech', '无模型语音段数', '无模型语音段数', 'number', 'output',
         'interruption.n_no_model_speech', None, 'aux', True,
         False, None, '模型全程未说话的用户段数', 66),
        ('interruption_avg_stop_latency_s', '平均打断检查时延', '平均打断检查时延(秒)', 'number', 'output',
         'interruption.avg_stop_latency_s', None, 'aux', True,
         False, None, '平均打断检查时延(秒): 用户开始打断→模型停下', 67),
        ('interruption_avg_recovery_latency_s', '平均打断恢复时延', '平均打断恢复时延(秒)', 'number', 'output',
         'interruption.avg_recovery_latency_s', None, 'aux', True,
         False, None, '平均打断恢复时延(秒): 用户说完→模型重新开口', 68),
        ('interruption_avg_overlap_s', '平均重叠时长', '平均双方同时说话时长(秒)', 'number', 'output',
         'interruption.avg_overlap_s', None, 'aux', True,
         False, None, '平均双方同时说话时长(秒，越短越好)', 69),
        ('interruption_avg_silence_gap_s', '平均静默时长', '平均静默时长(秒)', 'number', 'output',
         'interruption.avg_silence_gap_s', None, 'aux', True,
         False, None, '平均模型停下到恢复的静默时长(秒)', 70),
        ('interruption_per_event', '逐事件详情', '逐事件详情', 'json', 'output',
         'interruption.per_event', None, 'aux', True,
         False, None, '每个用户打断段的结果列表', 90),
        ('interruption_message', '打断指标说明', '打断指标说明', 'text', 'output',
         'interruption.message', None, 'aux', True,
         False, None, '打断指标错误/成功说明', 99),

        # ─── 输出参数: 大模型评估（可选，enable_llm_eval=True 时才有值）───
        ('llm_recovery_avg_coherence', '回复连贯性', '打断后回复连贯性(用例级单值)', 'number', 'output',
         'interruption.llm_recovery_avg_coherence', None, 'aux', True,
         False, None, '打断后回复连贯性(0-5，用例级单值，对标 Full-Duplex-Bench GPT-4o Score)', 100),
        ('llm_recovery_avg_relevance', '回复相关性', '打断后回复相关性(用例级单值)', 'number', 'output',
         'interruption.llm_recovery_avg_relevance', None, 'aux', True,
         False, None, '打断后回复相关性(0-5，用例级单值)', 101),
        ('llm_recovery_avg_adaptability', '回复适应性', '打断后回复适应性(用例级单值)', 'number', 'output',
         'interruption.llm_recovery_avg_adaptability', None, 'aux', True,
         False, None, '打断后回复适应性(0-5，用例级单值)', 102),
        ('llm_recovery_coherence_reason', '连贯性理由', '连贯性评分理由', 'text', 'output',
         'interruption.llm_recovery_coherence_reason', None, 'aux', True,
         False, None, '连贯性评分简短理由', 103),
        ('llm_recovery_relevance_reason', '相关性理由', '相关性评分理由', 'text', 'output',
         'interruption.llm_recovery_relevance_reason', None, 'aux', True,
         False, None, '相关性评分简短理由', 104),
        ('llm_recovery_adaptability_reason', '适应性理由', '适应性评分理由', 'text', 'output',
         'interruption.llm_recovery_adaptability_reason', None, 'aux', True,
         False, None, '适应性评分简短理由', 105),
        ('llm_interaction_behavior_summary', '交互行为分布', '交互过程行为分类计数', 'json', 'output',
         'interruption.llm_interaction_behavior_summary', None, 'aux', True,
         False, None, '每轮模型收到指令后的回复行为计数{回应/恢复/询问/无关回复/沉默或无视}（5 类）', 107),
        ('llm_interaction_per_round', '交互逐轮行为', '交互过程逐轮行为', 'json', 'output',
         'interruption.llm_interaction_per_round', None, 'aux', True,
         False, None, '每轮交互行为明细[{round,is_interrupted,reaction_behavior,reaction_reason}]', 108),
        ('llm_recovery_per_round', '逐轮明细', '打断逐轮明细', 'json', 'output',
         'interruption.llm_recovery_per_round', None, 'aux', True,
         False, None, '每轮打断明细(is_interrupted/success/stop/recovery/reaction 及各 reason + segments)', 110),
        ('llm_eval', 'LLM评估块', 'LLM评估完整结果', 'json', 'output',
         'interruption.llm_eval', None, 'aux', True,
         False, None, 'LLM 评估完整结果(含 enabled/model/timing_comparison/per_round/audio_dropped/fallback)', 113),
    ],
    'param_mappings': [
        ('device', 'output', 'user_wav', 'user_wav', 'none'),
        ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
        ('reference', 'output', 'query', 'query', 'none'),
        ('device', 'output', 'answer', 'answer', 'none'),
        ('reference', 'output', 'is_return_to_topic', 'is_return_to_topic', 'none'),
    ],
}

# ============================================================
# 子维度定义：各自只配自己的 output 参数（2 时延 + 3 LLM 三维均分）
# ============================================================
# params 元组顺序：
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order, pass_threshold)
# pass_threshold 可选，pass_rate 策略时用，默认 None

SUB_DIMENSIONS = [
    {
        'task_type_code': 'interruption_metrics',  # 与主维度相同，保证被分到同一组
        'name': '打断检查时延',
        'keywords': 'interruption,stop_latency,打断检查时延,停下时延',
        'description': '子维度：用户开始打断 → 模型停下的时延。output field_path = avg_stop_latency_s',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': None,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': 's',
        'statistic_method': 'average',
        'params': [
            # ─── 打断检查时延子维度的 output 参数 ───
            ('avg_stop_latency_s', '打断检查时延', '打断检查时延(秒)', 'number', 'output',
             'interruption.avg_stop_latency_s', 'value', 'main', True,
             False, None, '平均打断检查时延(秒): 用户开始打断 → 模型停下', 70),
        ],
    },
    {
        'task_type_code': 'interruption_metrics',
        'name': '打断恢复时延',
        'keywords': 'interruption,recovery_latency,打断恢复时延,恢复时延',
        'description': '子维度：用户说完 → 模型重新开口的时延。output field_path = avg_recovery_latency_s',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': None,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': 's',
        'statistic_method': 'average',
        'params': [
            # ─── 打断恢复时延子维度的 output 参数 ───
            ('avg_recovery_latency_s', '打断恢复时延', '打断恢复时延(秒)', 'number', 'output',
             'interruption.avg_recovery_latency_s', 'value', 'main', True,
             False, None, '平均打断恢复时延(秒): 用户说完 → 模型重新开口', 80),
            ('avg_overlap_s', '同时说话时长', '双方同时说话时长(秒)', 'number', 'output',
             'interruption.avg_overlap_s', None, 'aux', True,
             False, None, '平均双方同时说话时长(秒，越短越好)', 81),
            ('avg_silence_gap_s', '静默时长', '静默时长(秒)', 'number', 'output',
             'interruption.avg_silence_gap_s', None, 'aux', True,
             False, None, '平均模型停下到恢复的静默时长(秒)', 82),
        ],
    },
    # ─── LLM 评估子维度：打断后回复质量三维均分(0-5) ───
    {
        'task_type_code': 'interruption_metrics',
        'name': '平均连贯性',
        'keywords': 'interruption,coherence,连贯性,平均连贯性,llm_coherence',
        'description': '子维度：打断后回复连贯性均分(0-5)。output field_path = llm_recovery_avg_coherence',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '分',
        'statistic_method': 'average',
        'params': [
            ('llm_recovery_avg_coherence', '平均连贯性', '打断后回复连贯性均分(0-5)', 'number', 'output',
             'interruption.llm_recovery_avg_coherence', 'value', 'main', True,
             False, None, '每轮打断后回复连贯性打分均值(0-5，对标 Full-Duplex-Bench GPT-4o Score)', 100),
        ],
    },
    {
        'task_type_code': 'interruption_metrics',
        'name': '平均相关性',
        'keywords': 'interruption,relevance,相关性,平均相关性,llm_relevance',
        'description': '子维度：打断后回复相关性均分(0-5)。output field_path = llm_recovery_avg_relevance',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '分',
        'statistic_method': 'average',
        'params': [
            ('llm_recovery_avg_relevance', '平均相关性', '打断后回复相关性均分(0-5)', 'number', 'output',
             'interruption.llm_recovery_avg_relevance', 'value', 'main', True,
             False, None, '每轮打断后回复相关性打分均值(0-5)', 101),
        ],
    },
    {
        'task_type_code': 'interruption_metrics',
        'name': '平均适应性',
        'keywords': 'interruption,adaptability,适应性,平均适应性,llm_adaptability',
        'description': '子维度：打断后回复适应性均分(0-5)。output field_path = llm_recovery_avg_adaptability',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '分',
        'statistic_method': 'average',
        'params': [
            ('llm_recovery_avg_adaptability', '平均适应性', '打断后回复适应性均分(0-5)', 'number', 'output',
             'interruption.llm_recovery_avg_adaptability', 'value', 'main', True,
             False, None, '每轮打断后回复适应性打分均值(0-5)', 102),
        ],
    },
]


def _upsert_dimension(conn, dim_def, dimension_type, parent_id=None):
    """注册/更新一个维度，返回 dim_id。dimension_type: 'main' or 'sub'。"""
    task_code = dim_def['task_type_code']
    name = dim_def['name']

    # 子维度用 name 做唯一性匹配（同 task_type_code 下多个子维度）
    if dimension_type == 'sub':
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = :tc AND name = :name "
            "AND dimension_type = 'sub' AND deleted = FALSE"
        ), {'tc': task_code, 'name': name}).fetchone()
    else:
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = :tc AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        ), {'tc': task_code}).fetchone()

    # api_settings + body_template
    body_template = dim_def.get('body_template', {
        'seg_merge_gap_s': '{{seg_merge_gap_s}}',
        'enable_llm_eval': '{{enable_llm_eval}}',
        'llm_model': '{{llm_model}}',
        'original_topic': '{{original_topic}}',
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
                'query': '{{query}}',
                'answer': '{{answer}}',
                'is_return_to_topic': '{{is_return_to_topic}}',
            }
        ],
    })
    api_settings = json.dumps({
        'method': 'POST',
        'headers': {},
        'body_template': body_template,
        'timeout': 30000
    }, ensure_ascii=False)
    rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

    common_fields = {
        'name': name,
        'kw': dim_def['keywords'],
        'desc': dim_def['description'],
        'type': dim_def['type'],
        'rt': dim_def['result_type'],
        'rmin': dim_def['result_min'],
        'rmax': dim_def['result_max'],
        'dp': dim_def['decimal_places'],
        'w': dim_def['weight'],
        'et': dim_def['estimated_exec_time'],
        'su': dim_def['score_unit'],
        'sm': dim_def['statistic_method'],
        'apis': api_settings,
        'rule': rule,
        'dtype': dimension_type,
        'pid': parent_id,
    }

    if existing:
        dim_id = existing[0]
        print(f"  - {dimension_type} 维度已存在 (id={dim_id}, name={name})，更新")
        if dimension_type == 'main':
            conn.execute(text(
                "UPDATE dimensions SET "
                "  name = :name, keywords = :kw, description = :desc, "
                "  type = :type, result_type = :rt, result_min = :rmin, "
                "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                "  estimated_exec_time = :et, score_unit = :su, "
                "  statistic_method = :sm, api_settings = :apis, "
                "  rule = :rule, dimension_type = :dtype, "
                "  parent_dimension_id = :pid, api_url = :api_url, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :did"
            ), {**common_fields, 'api_url': API_URL, 'did': dim_id})
        else:
            conn.execute(text(
                "UPDATE dimensions SET "
                "  name = :name, keywords = :kw, description = :desc, "
                "  type = :type, result_type = :rt, result_min = :rmin, "
                "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                "  estimated_exec_time = :et, score_unit = :su, "
                "  statistic_method = :sm, api_settings = :apis, "
                "  rule = :rule, dimension_type = :dtype, "
                "  parent_dimension_id = :pid, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :did"
            ), {**common_fields, 'did': dim_id})
    else:
        if dimension_type == 'main':
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, api_url, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, :api_url, "
                "   FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code, 'api_url': API_URL})
        else:
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, "
                "   FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code})
        dim_id = result.fetchone()[0]
        print(f"  + {dimension_type} 维度已插入 (id={dim_id}, name={name})")
    return dim_id


def _cleanup_stale_params(conn, dim_id, dim_def):
    """软清理 DB 中当前 dim_def.params 不再出现的 param_code（按 direction 分组）。"""
    current_output_codes = {p[0] for p in dim_def['params'] if p[4] == 'output'}
    current_input_codes = {p[0] for p in dim_def['params'] if p[4] == 'input'}
    for direction, current_codes in (
        ('output', current_output_codes),
        ('input', current_input_codes),
    ):
        if not current_codes:
            # 当前定义里这个方向没有 param_code，把 DB 里该方向所有非 deleted 记录软删
            stale = conn.execute(text(
                "SELECT param_code FROM evaluation_dimension_params "
                "WHERE dimension_id = :did AND param_direction = :dir "
                "AND deleted = FALSE"
            ), {'did': dim_id, 'dir': direction}).fetchall()
            if stale:
                stale_codes = [r[0] for r in stale]
                print(f"  ! 清理已废弃 {direction} 参数: {stale_codes}")
                conn.execute(text(
                    "UPDATE evaluation_dimension_params SET "
                    "  deleted = TRUE, updated_at = NOW() "
                    "WHERE dimension_id = :did AND param_direction = :dir"
                ), {'did': dim_id, 'dir': direction})
            continue
        placeholders = ','.join(f':c{i}' for i in range(len(current_codes)))
        bind = {f'c{i}': code for i, code in enumerate(current_codes)}
        stale = conn.execute(text(
            "SELECT param_code FROM evaluation_dimension_params "
            "WHERE dimension_id = :did AND param_direction = :dir "
            f"AND param_code NOT IN ({placeholders}) "
            "AND deleted = FALSE"
        ), {'did': dim_id, 'dir': direction, **bind}).fetchall()
        if stale:
            stale_codes = [r[0] for r in stale]
            print(f"  ! 清理已废弃 {direction} 参数: {stale_codes}")
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET "
                "  deleted = TRUE, updated_at = NOW() "
                "WHERE dimension_id = :did AND param_direction = :dir "
                f"AND param_code IN ({placeholders})"
            ), {'did': dim_id, 'dir': direction, **bind})


def _upsert_params(conn, dim_id, dim_def):
    """注册/更新维度的 params。"""
    print(f"  --- 注册参数 (dimension_id={dim_id}) ---")
    _cleanup_stale_params(conn, dim_id, dim_def)

    inserted = 0
    updated = 0
    for dp in dim_def['params']:
        (param_code, param_name, label, field_type, param_direction,
         field_path, agg_role, output_role, visible_in_report,
         required, default_value, help_text, ui_order, *rest) = dp
        pass_threshold = rest[0] if rest else None

        existing = conn.execute(text(
            "SELECT id FROM evaluation_dimension_params "
            "WHERE dimension_id = :did AND param_code = :pc "
            "AND param_direction = :dir"
        ), {'did': dim_id, 'pc': param_code, 'dir': param_direction}).fetchone()

        if existing:
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET "
                "  param_name = :pn, label = :lb, field_type = :ft, "
                "  field_path = :fp, agg_role = :ar, output_role = :or, "
                "  visible_in_report = :vir, required = :req, "
                "  default_value = :dv, pass_threshold = :pt, help_text = :ht, ui_order = :uo, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {
                'pn': param_name, 'lb': label, 'ft': field_type,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order,
                'id': existing[0],
            })
            updated += 1
        else:
            conn.execute(text(
                "INSERT INTO evaluation_dimension_params "
                "  (dimension_id, param_code, param_name, label, field_type, "
                "   param_direction, field_path, agg_role, output_role, "
                "   visible_in_report, required, default_value, pass_threshold, help_text, "
                "   ui_order, deleted, created_at, updated_at) "
                "VALUES "
                "  (:did, :pc, :pn, :lb, :ft, "
                "   :dir, :fp, :ar, :or, "
                "   :vir, :req, :dv, :pt, :ht, "
                "   :uo, FALSE, NOW(), NOW())"
            ), {
                'did': dim_id, 'pc': param_code, 'pn': param_name,
                'lb': label, 'ft': field_type, 'dir': param_direction,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order,
            })
            inserted += 1
    print(f"  插入 {inserted} 条，更新 {updated} 条")


def _upsert_relation(conn, dim_id):
    """注册 voice_llm → 维度关联（幂等）。"""
    existing = conn.execute(text(
        "SELECT id FROM algorithm_dimension_relations "
        "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
    ), {'did': dim_id}).fetchone()
    if existing:
        print(f"  - 关联 voice_llm → dim {dim_id} 已存在，跳过")
    else:
        conn.execute(text(
            "INSERT INTO algorithm_dimension_relations "
            "  (algorithm_type, dimension_id, is_default, weight, "
            "   deleted, created_at, updated_at) "
            "VALUES "
            "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
        ), {'did': dim_id})
        print(f"  + 关联 voice_llm → dim {dim_id} 已插入")


def _upsert_param_mappings(conn, dim_id, dim_def):
    """注册 voice_llm → 维度的 param_mappings（幂等）。只在主维度配。"""
    print(f"  --- 注册 param_mappings (dimension_id={dim_id}) ---")
    inserted = 0
    updated = 0
    for m in dim_def.get('param_mappings', []):
        (source, source_direction, source_param, target_param,
         transform_type) = m
        existing = conn.execute(text(
            "SELECT id FROM param_mappings "
            "WHERE algorithm_type = 'voice_llm' AND source = :src "
            "AND source_param = :sp AND dimension_id = :did"
        ), {'src': source, 'sp': source_param, 'did': dim_id}).fetchone()
        if existing:
            conn.execute(text(
                "UPDATE param_mappings SET "
                "  target_param = :tp, transform_type = :tt, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'tp': target_param, 'tt': transform_type, 'id': existing[0]})
            updated += 1
        else:
            conn.execute(text(
                "INSERT INTO param_mappings "
                "  (algorithm_type, source, source_direction, source_param, "
                "   dimension_id, target_param, transform_type, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  ('voice_llm', :src, :sd, :sp, :did, :tp, :tt, "
                "   FALSE, NOW(), NOW())"
            ), {
                'src': source, 'sd': source_direction, 'sp': source_param,
                'did': dim_id, 'tp': target_param, 'tt': transform_type,
            })
            inserted += 1
    print(f"  插入 {inserted} 条，更新 {updated} 条")


def _soft_delete_dimension_tree(conn, dim_id, reason):
    """软删除一个维度及其 params / mappings / 子维度。"""
    # 子维度
    subs = conn.execute(text(
        "SELECT id, name FROM dimensions "
        "WHERE parent_dimension_id = :pid AND deleted = FALSE"
    ), {'pid': dim_id}).fetchall()
    for sub_id, sub_name in subs:
        _soft_delete_dimension_tree(conn, sub_id, f"父维度 {dim_id} 被软删")

    conn.execute(text(
        "UPDATE dimensions SET deleted = TRUE, updated_at = NOW() "
        "WHERE id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE evaluation_dimension_params SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE param_mappings SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE algorithm_dimension_relations SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    print(f"  ! 软删维度 id={dim_id}（{reason}）：dimensions/params/mappings/relations 已置 deleted=TRUE")


def seed_interruption_dimensions():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 0: 软删除历史单维度 interruption_metrics（name='打断指标'）
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 0: 软删除历史单维度 interruption_metrics")
        print(f"{'=' * 60}")
        legacy = conn.execute(text(
            "SELECT id, name, task_type_code FROM dimensions "
            "WHERE task_type_code = 'interruption_metrics' "
            "AND dimension_type = 'main' AND parent_dimension_id IS NULL "
            "AND name != '打断成功率' AND deleted = FALSE"
        )).fetchall()
        if legacy:
            for dim_id, name, tc in legacy:
                print(f"  软删历史维度: id={dim_id}, name={name}, task_type_code={tc}")
                _soft_delete_dimension_tree(conn, dim_id, "被 主+子维度方案替代")
        else:
            print("  无历史单维度需清理")

        # ============================================================
        # Step 1: 注册/更新打断成功率主维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 1: 注册打断成功率主维度")
        print(f"{'=' * 60}")
        main_id = _upsert_dimension(conn, MAIN_DIMENSION, dimension_type='main', parent_id=None)
        print(f"  主维度 id = {main_id}")
        _upsert_params(conn, main_id, MAIN_DIMENSION)
        _upsert_relation(conn, main_id)
        _upsert_param_mappings(conn, main_id, MAIN_DIMENSION)

        # ============================================================
        # Step 2: 注册5个子维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 2: 注册5个子维度（parent_dimension_id={main_id}）")
        print(f"{'=' * 60}")
        for sub_def in SUB_DIMENSIONS:
            print(f"\n  -- 子维度: {sub_def['name']} --")
            sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
            print(f"  子维度 id = {sub_id}")
            _upsert_params(conn, sub_id, sub_def)
            _upsert_relation(conn, sub_id)
            # 子维度不配 param_mappings，共用主维度的 mappings

        print(f"\n{'=' * 60}")
        print(f"  打断指标维度种子数据注册完成")
        print(f"  主维度 打断成功率 id={main_id}")
        print(f"  5个子维度（各自 output field_path）:")
        print(f"    - 打断检查时延 → avg_stop_latency_s")
        print(f"    - 打断恢复时延 → avg_recovery_latency_s")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("打断指标维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print("1. 软删除历史单维度 interruption_metrics（name='打断指标'，被替代）")
    print("2. 注册/更新打断成功率主维度（dimension_type=main）")
    print("   配置 input params + 打断成功率 output params + LLM 评估 output params")
    print("   + api_settings + param_mappings")
    print("3. 注册/更新5个子维度（dimension_type=sub，parent_dimension_id=主维度id）：")
    print("   - 打断检查时延 → output field_path = avg_stop_latency_s")
    print("   - 打断恢复时延 → output field_path = avg_recovery_latency_s")
    print("4. 子维度不重复 input params / param_mappings：")
    print("   - input_params 通过 evaluation_service._load_dimension_data 继承父维度")
    print("   - param_mappings 挂主维度 id 下，子维度共用（dimension_ids=None 不过滤）")
    print("5. 注册 voice_llm → 主维度 + 5个子维度的关联")
    print()
    print("执行链路：用例选主维度 + 5个子维度 → 继承父维度 task_type_code/api 配置")
    print("→ 按 (endpoint_url, task_type_code) 分到同一组 → 调一次 eval_server")
    print("→ process_group_dimension_results 按各自 output field_path 分发提取")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_interruption_dimensions()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)