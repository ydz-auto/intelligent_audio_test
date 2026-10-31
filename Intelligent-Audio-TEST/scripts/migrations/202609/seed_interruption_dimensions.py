# -*- coding: utf-8 -*-
"""
旧代打断指标维度清理（INT-2293 收敛：本脚本不再创建「打断成功率」树）

功能（现状）：
1. 软删除历史单维度 interruption_metrics（旧代 name 集合：'打断指标'），
   连同其子维度 / params / mappings / relations 一并软删。

INT-2293 变更背景：
   本脚本原先还会注册「打断成功率」主维度 + 5 个子维度，但该族已被
   202610/seed_interruption_v2.py 的打断指标 v2（11 主维度 + 「打断时延」容器）
   整体取代：v2 的 Step 0 每次引导都把「打断成功率」树物理删除（连 test_result_dimensions
   历史结果行一起删）。两代在引导链里一建一删的对冲会让「每次部署删一次历史结果行」，
   故按卡内要求收敛为「202609 不再建」：本脚本只做旧代清理，不再创建该族。
   下面的维度/参数定义与 helper 保留（INT-2292 单测引用 _upsert_relation；
   历史版本形态可追溯），但已不参与引导链写入。

使用方法：
    cd Intelligent-Audio-TEST
    python scripts/migrations/202609/seed_interruption_dimensions.py

注意：此脚本可重复执行（幂等）
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

# INT-2249：评估端点缺省与 docker-compose 同源（shared/config/eval_endpoint.py）；
# 脚本可脱离 compose 手工执行，仓库根入 sys.path 才能 import shared。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.eval_endpoint import resolve_eval_server_url  # noqa: E402

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# eval_server 微服务地址（本机 5002，见 eval_server/app/config.py PORT=5002）
API_URL = resolve_eval_server_url()

# INT-2293：旧代 interruption_metrics 单维度 name 集合（只这些行允许被本脚本软删）。
# 202610/seed_interruption_v2 的现行 15 个维度名一律不在集合内，故不会被误删。
LEGACY_MAIN_NAMES = ('打断指标',)

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
    'decimal_places': 2,
    'weight': 1,
    'estimated_exec_time': 30,
    'score_unit': '%',
    'statistic_method': 'pass_rate',
    'body_template': {
        'user_seg_merge_gap_s': '{{user_seg_merge_gap_s}}',
        'model_seg_merge_gap_s': '{{model_seg_merge_gap_s}}',
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
        ('user_seg_merge_gap_s', '用户侧合并间隙', '用户侧词合并为段的间隙阈值(秒)', 'number', 'input',
         None, None, None, False,
         False, '1.5', '用户侧相邻词时间戳间隙小于该值则合并为同一段(秒)，默认1.5', 11),
        ('model_seg_merge_gap_s', '模型侧合并间隙', '模型侧词合并为段的间隙阈值(秒)', 'number', 'input',
         None, None, None, False,
         False, '0.7', '模型侧合并间隙(秒)，默认0.7，更敏感以识别打断后短停顿+恢复', 12),

        # ─── 输入参数: 大模型评估（可选）───
        ('rounds', '多轮文本', '多轮对话文本结构(已废弃,LLM改吃per_event)', 'json', 'input',
         None, None, None, False,
         False, None,
         '多轮文本结构 [{query, answer, is_return_to_topic}]，'
         '已废弃：LLM 现改吃 per_event 字词级 ASR，传入忽略', 13),
        ('enable_llm_eval', '启用LLM评估', '是否启用大模型评估(语义判定成功打断+回复打分)', 'boolean', 'input',
         None, None, None, False,
         False, 'true', '默认开启：LLM 语义判定是否成功打断(覆盖本地时序成功率)+三维打分；'
         '显式传 false 才关闭(回退本地时序启发式,需配置 LLM_JUDGE_API_KEY)', 14),
        ('llm_model', 'LLM模型', 'LLM 模型名称(覆盖默认)', 'text', 'input',
         None, None, None, False,
         False, 'gemini-3.7-flash', '覆盖 config.LLM_JUDGE.default_model，留空用默认', 15),
        ('original_topic', '原始话题', '原始话题文本', 'text', 'input',
         None, None, None, False,
         False, None, '原始话题文本，供 LLM 打分作上下文', 16),

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
        ('interruption_avg_stop_latency_s', '平均打断检查时延', '平均打断检查时延(毫秒)', 'number', 'output',
         'interruption.avg_stop_latency_s', None, 'aux', True,
         False, None, '平均打断检查时延(毫秒，字段名保留 _s 后缀): 用户开始打断→模型停下', 67),
        ('interruption_avg_recovery_latency_s', '平均打断恢复时延', '平均打断恢复时延(毫秒)', 'number', 'output',
         'interruption.avg_recovery_latency_s', None, 'aux', True,
         False, None, '平均打断恢复时延(毫秒): 用户说完→模型重新开口', 68),
        ('interruption_avg_overlap_s', '平均重叠时长', '平均双方同时说话时长(毫秒)', 'number', 'output',
         'interruption.avg_overlap_s', None, 'aux', True,
         False, None, '平均双方同时说话时长(毫秒，越短越好)', 69),
        ('interruption_avg_silence_gap_s', '平均静默时长', '平均静默时长(毫秒)', 'number', 'output',
         'interruption.avg_silence_gap_s', None, 'aux', True,
         False, None, '平均模型停下到恢复的静默时长(毫秒)', 70),
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
        'task_type_code': 'interruption_stop_latency',
        'name': '打断检查时延',
        'keywords': 'interruption,stop_latency,打断检查时延,停下时延',
        'description': '子维度：用户开始打断 → 模型停下的时延(毫秒)。output field_path = avg_stop_latency_s',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': None,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': 'ms',
        'statistic_method': 'average',
        'params': [
            # ─── 打断检查时延子维度的 output 参数 ───
            ('avg_stop_latency_s', '打断检查时延', '打断检查时延(毫秒)', 'number', 'output',
             'interruption.avg_stop_latency_s', 'value', 'main', True,
             False, None, '平均打断检查时延(毫秒，字段名保留 _s 后缀): 用户开始打断 → 模型停下', 70),
        ],
    },
    {
        'task_type_code': 'interruption_recovery_latency',
        'name': '打断恢复时延',
        'keywords': 'interruption,recovery_latency,打断恢复时延,恢复时延',
        'description': '子维度：用户说完 → 模型重新开口的时延(毫秒)。output field_path = avg_recovery_latency_s',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': None,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': 'ms',
        'statistic_method': 'average',
        'params': [
            # ─── 打断恢复时延子维度的 output 参数 ───
            ('avg_recovery_latency_s', '打断恢复时延', '打断恢复时延(毫秒)', 'number', 'output',
             'interruption.avg_recovery_latency_s', 'value', 'main', True,
             False, None, '平均打断恢复时延(毫秒): 用户说完 → 模型重新开口', 80),
            ('avg_overlap_s', '同时说话时长', '双方同时说话时长(毫秒)', 'number', 'output',
             'interruption.avg_overlap_s', None, 'aux', True,
             False, None, '平均双方同时说话时长(毫秒，越短越好)', 81),
            ('avg_silence_gap_s', '静默时长', '静默时长(毫秒)', 'number', 'output',
             'interruption.avg_silence_gap_s', None, 'aux', True,
             False, None, '平均模型停下到恢复的静默时长(毫秒)', 82),
        ],
    },
    # ─── LLM 评估子维度：打断后回复质量三维均分(0-5) ───
    {
        'task_type_code': 'interruption_coherence',
        'name': '平均连贯性',
        'keywords': 'interruption,coherence,连贯性,平均连贯性,llm_coherence',
        'description': '子维度：打断后回复连贯性均分(0-5)。output field_path = llm_recovery_avg_coherence',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 2,
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
        'task_type_code': 'interruption_relevance',
        'name': '平均相关性',
        'keywords': 'interruption,relevance,相关性,平均相关性,llm_relevance',
        'description': '子维度：打断后回复相关性均分(0-5)。output field_path = llm_recovery_avg_relevance',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 2,
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
        'task_type_code': 'interruption_adaptability',
        'name': '平均适应性',
        'keywords': 'interruption,adaptability,适应性,平均适应性,llm_adaptability',
        'description': '子维度：打断后回复适应性均分(0-5)。output field_path = llm_recovery_avg_adaptability',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 5.0,
        'decimal_places': 2,
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

    # 子维度用 name 做唯一性匹配（不限定 task_type_code，保证改名后能复用旧记录）
    if dimension_type == 'sub':
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE name = :name "
            "AND dimension_type = 'sub' AND deleted = FALSE"
        ), {'name': name}).fetchone()
        if existing:
            # 如果旧记录 task_type_code 与当前定义不一致，原地更新 task_type_code
            # 不软删+新建，避免 test_result_dimensions 里的 dimension_id 失效
            old_tc = conn.execute(text(
                "SELECT task_type_code FROM dimensions WHERE id = :did"
            ), {'did': existing[0]}).scalar()
            if old_tc and old_tc != task_code:
                print(f"  ! 检测到子维度 '{name}' task_type_code 变更: {old_tc} → {task_code}，原地更新 id={existing[0]}")
                conn.execute(text(
                    "UPDATE dimensions SET task_type_code = :tc, updated_at = NOW() WHERE id = :did"
                ), {'tc': task_code, 'did': existing[0]})
    else:
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = :tc AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        ), {'tc': task_code}).fetchone()

    # api_settings + body_template
    body_template = dim_def.get('body_template', {
        'user_seg_merge_gap_s': '{{user_seg_merge_gap_s}}',
        'model_seg_merge_gap_s': '{{model_seg_merge_gap_s}}',
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
            # 用 stale_codes(要删的) 建 IN 列表，勿用 current_codes(要留的)——否则删错+被upsert复活
            stale_placeholders = ','.join(f':s{i}' for i in range(len(stale_codes)))
            stale_bind = {f's{i}': code for i, code in enumerate(stale_codes)}
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET "
                "  deleted = TRUE, updated_at = NOW() "
                "WHERE dimension_id = :did AND param_direction = :dir "
                f"AND param_code IN ({stale_placeholders})"
            ), {'did': dim_id, 'dir': direction, **stale_bind})


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
    """注册 voice_llm → 维度关联（幂等）。

    INT-2292：`uq_algorithm_dimension` 是 `WHERE deleted = false` 的部分唯一索引，
    按唯一键 (algorithm_type, dimension_id) 全量判，禁止「取任意行当存在」：
      1. 有生效行 → 直接复用，不复活任何软删行；
      2. 无生效行 → 复活 id 最新的一条（同键其余软删行保持软删态）；
      3. 复活前先把同键残留的生效行显式置软删（历史脏数据兜底，防撞索引）。
    """
    active = conn.execute(text(
        "SELECT id FROM algorithm_dimension_relations "
        "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did "
        "AND deleted = FALSE ORDER BY id DESC LIMIT 1"
    ), {'did': dim_id}).fetchone()
    if active:
        print(f"  - 关联 voice_llm → dim {dim_id} 已存在，跳过")
        return

    revive = conn.execute(text(
        "SELECT id FROM algorithm_dimension_relations "
        "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did "
        "AND deleted = TRUE ORDER BY id DESC LIMIT 1"
    ), {'did': dim_id}).fetchone()
    if revive:
        conn.execute(text(
            "UPDATE algorithm_dimension_relations SET deleted = TRUE, updated_at = NOW() "
            "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did "
            "AND deleted = FALSE AND id <> :id"
        ), {'did': dim_id, 'id': revive[0]})
        conn.execute(text(
            "UPDATE algorithm_dimension_relations SET deleted = FALSE, updated_at = NOW() "
            "WHERE id = :id"
        ), {'id': revive[0]})
        print(f"  ~ 关联 voice_llm → dim {dim_id} 已软删，重新激活 (id={revive[0]})")
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


def _cleanup_legacy_main_dims(conn):
    """Step 0：软删旧代单维度（LEGACY_MAIN_NAMES），整棵树级联软删。返回处理行数。

    INT-2293：只按「旧代 name 集合」判定，不再 `name != '打断成功率'` 一把抓
    ——那会把 202610/seed_interruption_v2 的现行 15 个维度每轮软删一遍。
    """
    placeholders = ', '.join(f':n{i}' for i in range(len(LEGACY_MAIN_NAMES)))
    legacy = conn.execute(text(
        "SELECT id, name, task_type_code FROM dimensions "
        "WHERE task_type_code = 'interruption_metrics' "
        "AND dimension_type = 'main' AND parent_dimension_id IS NULL "
        f"AND name IN ({placeholders}) AND deleted = FALSE"
    ), {f'n{i}': n for i, n in enumerate(LEGACY_MAIN_NAMES)}).fetchall()
    for dim_id, name, tc in legacy:
        print(f"  软删旧代维度: id={dim_id}, name={name}, task_type_code={tc}")
        _soft_delete_dimension_tree(conn, dim_id, "旧代单维度，已由打断指标 v2 替代")
    return len(legacy)


def seed_interruption_dimensions():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 0: 软删除旧代单维度 interruption_metrics
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 0: 软删除旧代单维度 interruption_metrics（name in {LEGACY_MAIN_NAMES}）")
        print(f"{'=' * 60}")
        if not _cleanup_legacy_main_dims(conn):
            print("  无旧代单维度需清理")

        # ============================================================
        # Step 1: （INT-2293 收敛）不再创建「打断成功率」树
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 1: 跳过 —— 「打断成功率」族已由 202610/seed_interruption_v2.py 取代")
        print("          （本脚本不再创建，避免与 v2 的旧代清理一建一删对冲）")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("旧代打断指标维度清理（INT-2293：不再创建「打断成功率」树）")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print(f"1. 软删除旧代单维度 interruption_metrics（name in {LEGACY_MAIN_NAMES}），")
    print("   连同其子维度 / params / mappings / relations 一并软删")
    print("2. 不再注册「打断成功率」主维度与 5 个子维度 —— 该族已由")
    print("   202610/seed_interruption_v2.py（打断指标 v2）整体取代")
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