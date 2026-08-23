# -*- coding: utf-8 -*-
"""
话轮接管维度种子数据（turn_taking 主维度 + 三个子维度）

功能：
1. 软删除 id=2 的 xiaoyi_metrics（历史单维度多指标方案，已被子维度方案替代）
2. 注册/更新 turn_taking 主维度（dimension_type='main'）：
   - 配置全部 input params、api_settings、body_template、param_mappings
   - 不配 output params（主维度不直接参与评估，只作容器）
3. 注册/更新三个子维度（dimension_type='sub'，parent_dimension_id 指向主维度）：
   - tor              → output field_path = tor.tor
   - false_takeover   → output field_path = false_takeover.tor
   - takeover_latency → output field_path = takeover_latency.takeover_latency_ms
   - 子维度不重复 input params / param_mappings，由 evaluation_service._load_dimension_data
     的继承逻辑从父维度合并 input_params；param_mappings 不按 dimension_id 过滤
     （主调用路径 dimension_ids=None），挂在主维度 id 下即可被三个子维度共用
4. 注册 voice_llm 算法与主维度 + 三个子维度的关联（algorithm_dimension_relations）
5. 注册 voice_llm → 主维度的参数映射（param_mappings.dimension_id = 主维度id）

执行链路：
   用例选三个子维度 → 三者继承父维度 task_type_code/api 配置 → 被
   (endpoint_url, task_type_code) 分到同一组 → 调一次 eval_server
   → process_group_dimension_results 把同一份响应按各自 output field_path 分发提取

对应 eval_server 服务：
   - xiaoyi_turn_taking.py 一次返回包含 tor/false_takeover/takeover_latency 三块的 JSON

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_xiaoyi_dimensions

或直接：
    python backend/scripts/migrations/202606/seed_xiaoyi_dimensions.py

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

# ============================================================
# 主维度定义：turn_taking（只配 input + api_settings + param_mappings，不配 output）
# ============================================================
MAIN_DIMENSION = {
    'task_type_code': 'turn_taking',
    'name': '话轮接管',
    'keywords': 'turn_taking,话轮,接管,tor,接话,误接管,抢话,接管时延,延迟',
    'description': '话轮接管主维度：调双路 ASR（user_wav + ai_wav）一次，共享结果给子维度（tor/false_takeover/takeover_latency/高频轮换/高频LLM裁判）。主维度只配 input 和映射，不配 output。',
    'type': 'auto',
    'result_type': 0,
    'result_min': 0.0,
    'result_max': 1.0,
    'decimal_places': 0,
    'weight': 1,
    'estimated_exec_time': 30,
    'score_unit': '',
    'statistic_method': 'average',
    'body_template': {
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
            }
        ]
    },
    'params': [
        # ─── 输入参数（挂在主维度 id 下，子维度通过继承机制使用）───
        ('user_wav', '用户通道音频', '用户通道音频', 'audio', 'input',
         None, None, None, True,
         False, None, '用户通道 wav 路径（cap_client_process_out.wav）', 1),
        ('ai_wav', 'AI回复通道音频', 'AI回复通道音频', 'audio', 'input',
         None, None, None, True,
         False, None, 'AI 回复通道 wav 路径（cap_client_ec_out.wav）', 2),
        # 主维度不配 output 参数
    ],
    'param_mappings': [
        ('device', 'output', 'user_wav', 'user_wav', 'none'),
        ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
    ],
}

# ============================================================
# 三个子维度定义：各自只配自己的 output 参数
# ============================================================
# params 元组顺序：
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order, pass_threshold)
# pass_threshold 可选，pass_rate 策略时用，默认 None

SUB_DIMENSIONS = [
    {
        'task_type_code': 'turn_taking',  # 与主维度相同，保证被分到同一组
        'name': '接话率(TOR)',
        'keywords': 'tor,接话率,takeoff',
        'description': '子维度：打断后接话率。output field_path = tor.tor',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '',
        'statistic_method': 'pass_rate',
        'params': [
            # ─── tor 子维度的 output 参数 ───
            ('tor', 'TOR接话率', 'TOR接话率', 'number', 'output',
             'tor.tor', 'pass_eq', 'main', True,
             False, None, '接话率(0=没接话, 1=接话)', 60, 1.0),
            ('tor_n_words', 'TOR命中词数', 'TOR命中词数', 'number', 'output',
             'tor.n_words', None, 'aux', False,
             False, None, 'tor: 命中词总数', 61),
            ('tor_duration', 'TOR命中词时长', 'TOR命中词时长', 'number', 'output',
             'tor.duration', None, 'aux', False,
             False, None, 'tor: 命中词总跨度(秒)', 62),
            ('tor_hit_words', 'TOR命中词列表', 'TOR命中词列表', 'json', 'output',
             'tor.hit_words', None, 'aux', False,
             False, None, 'tor: 命中词列表', 63),
            ('tor_user_last_word_end_s', 'TOR用户末词结束', 'TOR用户末词结束', 'number', 'output',
             'tor.user_last_word_end_s', None, 'aux', False,
             False, None, 'tor: user 最后一词结束时间(秒)', 64),
        ],
    },
    {
        'task_type_code': 'turn_taking',
        'name': '误接管率',
        'keywords': 'false_takeover,误接管,抢话',
        'description': '子维度：用户停顿期间模型是否抢话。output field_path = false_takeover.tor',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '',
        'statistic_method': 'pass_rate',
        'params': [
            # ─── false_takeover 子维度的 output 参数 ───
            ('false_takeover', '误接管率', '误接管率', 'number', 'output',
             'false_takeover.tor', 'pass_eq', 'main', True,
             False, None, '误接管率(0=未抢话, 1=抢话)', 70, 0.0),
            ('ft_n_words', '误接管命中词数', '误接管命中词数', 'number', 'output',
             'false_takeover.n_words', None, 'aux', True,
             False, None, 'false_takeover: 所有 pause 区间内命中词总数', 71),
            ('ft_duration', '误接管命中词时长', '误接管命中词时长', 'number', 'output',
             'false_takeover.duration', None, 'aux', True,
             False, None, 'false_takeover: 命中词的总跨度(秒)', 72),
            ('ft_total_pauses', '误接管Pause总数', '误接管Pause总数', 'number', 'output',
             'false_takeover.total_pauses', None, 'aux', True,
             False, None, 'false_takeover: pause 区间总数', 73),
            ('ft_hit_words', '误接管命中词列表', '误接管命中词列表', 'json', 'output',
             'false_takeover.hit_words', None, 'aux', True,
             False, None, 'false_takeover: 所有 pause 区间内命中的模型词列表', 74),
            ('ft_details', '误接管逐区间详情', '误接管逐区间详情', 'json', 'output',
             'false_takeover.details', None, 'aux', True,
             False, None, 'false_takeover: 每个 pause 区间的命中情况', 75),
            ('ft_llm_eval', '误接管LLM语义判断', 'LLM语义判断结果', 'json', 'output',
             'false_takeover.llm_eval', None, 'aux', True,
             False, None, 'false_takeover: LLM语义判断结果 {false_takeover, reason, evidence}', 76),
        ],
    },
    {
        'task_type_code': 'turn_taking',
        'name': '接管时延',
        'keywords': 'takeover_latency,接管时延,延迟',
        'description': '子维度：模型回复第一词时刻 - 音频结束时刻。output field_path = takeover_latency.takeover_latency_ms',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': 'ms',
        'statistic_method': 'average',
        'params': [
            # ─── takeover_latency 子维度的 output 参数 ───
            ('takeover_latency_ms', '接管时延', '接管时延', 'number', 'output',
             'takeover_latency.takeover_latency_ms', 'value', 'main', True,
             False, None, '接管时延(毫秒)，正=AI后回复，负=抢话', 80),
            ('tl_user_last_word_end_ms', '用户末词结束时刻', '用户末词结束时刻', 'timestamp', 'output',
             'takeover_latency.user_last_word_end_ms', None, 'aux', False,
             False, None, 'takeover_latency: user 末词结束时间(毫秒)', 81),
            ('tl_ai_first_word_start_ms', '模型首词开始时刻', '模型首词开始时刻', 'timestamp', 'output',
             'takeover_latency.ai_first_word_start_ms', None, 'aux', False,
             False, None, 'takeover_latency: AI 首词开始时间(毫秒)', 82),
            ('latency_message', '时延说明', '时延说明', 'text', 'output',
             'takeover_latency.message', None, 'aux', False,
             False, None, 'takeover_latency: 错误/成功说明', 84),
        ],
    },
    # ────────────────────────────────────────────────────────────
    # 高频轮换子维度：task_type_code='turn_taking'（与主维度同）
    # 由 calculate_xiaoyi_metrics 统一入口返回，嵌套在 results['high_freq_turn_taking']
    # output field_path 前缀为 high_freq_turn_taking.<key>
    # ────────────────────────────────────────────────────────────
    {
        'task_type_code': 'turn_taking',
        'name': '高频轮换时延',
        'keywords': 'high_freq,高频轮换,飞花令,成语接龙,快问快答,时延',
        'description': '子维度：高频轮换场景每轮回复时延（飞花令/成语接龙/快问快答）。由 calculate_xiaoyi_metrics 统一入口返回，field_path 前缀 high_freq_turn_taking.',
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
            # ─── output 参数（嵌套在 results['high_freq_turn_taking'] 下）───
            ('avg_response_latency_ms', '平均回复时延', '平均回复时延', 'number', 'output',
             'high_freq_turn_taking.avg_response_latency_ms', 'value', 'main', True,
             False, None, '平均回复时延(毫秒)', 90),
            ('avg_response_latency_s', '平均回复时延(秒)', '平均回复时延(秒)', 'number', 'output',
             'high_freq_turn_taking.avg_response_latency_s', None, 'aux', False,
             False, None, '平均回复时延(秒)', 91),
            ('min_response_latency_s', '最小回复时延', '最小回复时延', 'number', 'output',
             'high_freq_turn_taking.min_response_latency_s', None, 'aux', False,
             False, None, '最小回复时延(秒)', 92),
            ('max_response_latency_s', '最大回复时延', '最大回复时延', 'number', 'output',
             'high_freq_turn_taking.max_response_latency_s', None, 'aux', False,
             False, None, '最大回复时延(秒)', 93),
            ('n_rounds', '总轮数', '总轮数', 'number', 'output',
             'high_freq_turn_taking.n_rounds', None, 'aux', False,
             False, None, '用户段总数(=轮数)', 94),
            ('n_matched_rounds', '匹配轮数', '匹配轮数', 'number', 'output',
             'high_freq_turn_taking.n_matched_rounds', None, 'aux', False,
             False, None, '成功匹配到AI回复的轮数', 95),
            ('n_missed_rounds', '未匹配轮数', '未匹配轮数', 'number', 'output',
             'high_freq_turn_taking.n_missed_rounds', None, 'aux', False,
             False, None, '未匹配到AI回复的轮数', 96),
            ('n_unmatched_ai_segments', '未消费AI段', '未消费AI段', 'number', 'output',
             'high_freq_turn_taking.n_unmatched_ai_segments', None, 'aux', False,
             False, None, '未被消费的AI段数(开场白/结束语等)', 97),
            ('per_round', '每轮明细', '每轮明细', 'json', 'output',
             'high_freq_turn_taking.per_round', None, 'aux', False,
             False, None, '每轮匹配结果(轮次/用户段/AI段/时延)', 98),
            ('hftt_message', '说明', '说明', 'text', 'output',
             'high_freq_turn_taking.message', None, 'aux', False,
             False, None, '错误/成功说明', 99),
        ],
    },
    # ────────────────────────────────────────────────────────────
    # 高频LLM裁判子维度：task_type_code='turn_taking'（与主维度同）
    # 由 calculate_xiaoyi_metrics 统一入口返回，嵌套在 results['high_freq_llm_judge']
    # output field_path 前缀为 high_freq_llm_judge.<key>
    # ────────────────────────────────────────────────────────────
    {
        'task_type_code': 'turn_taking',
        'name': '高频LLM裁判',
        'keywords': 'high_freq,高频轮换,llm,judge,裁判,飞花令,成语接龙,快问快答',
        'description': '子维度：高频轮换场景 LLM 逐轮裁判问答内容是否符合预期。由 calculate_xiaoyi_metrics 统一入口返回，field_path 前缀 high_freq_llm_judge.',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 120,
        'score_unit': '',
        'statistic_method': 'average',
        'params': [
            # ─── output 参数（嵌套在 results['high_freq_llm_judge'] 下）───
            ('overall_pass_rate', '通过率', '通过率', 'number', 'output',
             'high_freq_llm_judge.overall_pass_rate', 'value', 'main', True,
             False, None, '通过轮数/总轮数(0.0-1.0)', 100),
            ('n_passed', '通过轮数', '通过轮数', 'number', 'output',
             'high_freq_llm_judge.n_passed', None, 'aux', False,
             False, None, '符合预期的轮数', 101),
            ('n_failed', '未通过轮数', '未通过轮数', 'number', 'output',
             'high_freq_llm_judge.n_failed', None, 'aux', False,
             False, None, '不符合预期的轮数', 102),
            ('n_rounds', '总轮数', '总轮数', 'number', 'output',
             'high_freq_llm_judge.n_rounds', None, 'aux', False,
             False, None, '评估的总轮数', 103),
            ('per_round', '每轮裁判', '每轮裁判', 'json', 'output',
             'high_freq_llm_judge.per_round', None, 'aux', False,
             False, None, '每轮 pass/fail + reason', 104),
            ('summary', '总结', '总结', 'text', 'output',
             'high_freq_llm_judge.summary', None, 'aux', False,
             False, None, '自然语言总结', 105),
            ('hflj_message', '说明', '说明', 'text', 'output',
             'high_freq_llm_judge.message', None, 'aux', False,
             False, None, '错误/成功说明', 106),
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
            # 如果旧记录 task_type_code 与当前定义不一致，说明是改名场景，
            # 软删旧记录的从属数据（params/mappings/relations），避免新旧并存
            old_tc = conn.execute(text(
                "SELECT task_type_code FROM dimensions WHERE id = :did"
            ), {'did': existing[0]}).scalar()
            if old_tc and old_tc != task_code:
                print(f"  ! 检测到子维度 '{name}' task_type_code 变更: {old_tc} → {task_code}，软删旧记录 id={existing[0]} 并新建")
                conn.execute(text(
                    "UPDATE dimensions SET deleted = TRUE, updated_at = NOW() WHERE id = :did"
                ), {'did': existing[0]})
                conn.execute(text(
                    "UPDATE evaluation_dimension_params SET deleted = TRUE, updated_at = NOW() WHERE dimension_id = :did"
                ), {'did': existing[0]})
                conn.execute(text(
                    "UPDATE param_mappings SET deleted = TRUE, updated_at = NOW() WHERE dimension_id = :did"
                ), {'did': existing[0]})
                conn.execute(text(
                    "UPDATE algorithm_dimension_relations SET deleted = TRUE, updated_at = NOW() WHERE dimension_id = :did"
                ), {'did': existing[0]})
                existing = None
    else:
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = :tc AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        ), {'tc': task_code}).fetchone()

    # api_settings + body_template
    body_template = dim_def.get('body_template', {
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
            }
        ]
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


def seed_turn_taking():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 0: 软删除历史 xiaoyi_metrics（id=2）
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 0: 软删除历史 xiaoyi_metrics")
        print(f"{'=' * 60}")
        legacy = conn.execute(text(
            "SELECT id, name, task_type_code FROM dimensions "
            "WHERE task_type_code = 'xiaoyi_metrics' AND deleted = FALSE"
        )).fetchall()
        if legacy:
            for dim_id, name, tc in legacy:
                print(f"  软删历史维度: id={dim_id}, name={name}, task_type_code={tc}")
                _soft_delete_dimension_tree(conn, dim_id, "被 turn_taking 子维度方案替代")
        else:
            print("  无 xiaoyi_metrics 需清理")

        # ============================================================
        # Step 1: 注册/更新 turn_taking 主维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 1: 注册 turn_taking 主维度")
        print(f"{'=' * 60}")
        main_id = _upsert_dimension(conn, MAIN_DIMENSION, dimension_type='main', parent_id=None)
        print(f"  主维度 id = {main_id}")
        _upsert_params(conn, main_id, MAIN_DIMENSION)
        _upsert_relation(conn, main_id)
        _upsert_param_mappings(conn, main_id, MAIN_DIMENSION)

        # ============================================================
        # Step 2: 注册三个子维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 2: 注册三个子维度（parent_dimension_id={main_id}）")
        print(f"{'=' * 60}")
        for sub_def in SUB_DIMENSIONS:
            print(f"\n  -- 子维度: {sub_def['name']} --")
            sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
            print(f"  子维度 id = {sub_id}")
            _upsert_params(conn, sub_id, sub_def)
            _upsert_relation(conn, sub_id)
            # 子维度不配 param_mappings，共用主维度的 mappings

        print(f"\n{'=' * 60}")
        print(f"  话轮接管维度种子数据注册完成")
        print(f"  主维度 turn_taking id={main_id}（无 output）")
        print(f"  三个子维度（各自 output field_path）:")
        print(f"    - tor              → tor.tor")
        print(f"    - false_takeover   → false_takeover.tor")
        print(f"    - takeover_latency → takeover_latency.takeover_latency_ms")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("话轮接管（turn_taking）维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print("1. 软删除历史 xiaoyi_metrics 维度（id=2，被替代）")
    print("2. 注册/更新 turn_taking 主维度（dimension_type=main，无 output）")
    print("   配置 input params + api_settings + param_mappings")
    print("3. 注册/更新三个子维度（dimension_type=sub，parent_dimension_id=主维度id）：")
    print("   - 接话率(TOR)        → output field_path = tor.tor")
    print("   - 误接管率           → output field_path = false_takeover.tor")
    print("   - 接管时延           → output field_path = takeover_latency.takeover_latency_ms")
    print("4. 子维度不重复 input params / param_mappings：")
    print("   - input_params 通过 evaluation_service._load_dimension_data 继承父维度")
    print("   - param_mappings 挂主维度 id 下，子维度共用（dimension_ids=None 不过滤）")
    print("5. 注册 voice_llm → 主维度 + 三个子维度的关联")
    print()
    print("执行链路：用例选三个子维度 → 继承父维度 task_type_code/api 配置")
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
        seed_turn_taking()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
