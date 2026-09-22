# -*- coding: utf-8 -*-
"""
环境理解裁判维度种子数据（单主维度 + task_type 参数 + 两个子维度）

注册 1 个主维度：
  env_judge  环境理解裁判
    — 通过 task_type 输入参数区分无语义/有语义：
      task_type=0 → 无语义（环境声为噪声，判断声音类型识别）
      task_type=1 → 有语义（环境声含语义内容，判断内容理解）
    — 输出 understand_correct (True/False) + response_latency_ms

注册 2 个子维度（理解正确率 pass_rate）：
  - 无语义脚本理解正确率
  - 有语义脚本理解正确率

对应 eval_server 服务：
   - eval_server/app/services/calculators/xiaoyi_metrics/env_judge/env_judge.py
   - 入口：evaluate_env_judge（task_type → script_type 映射）
   - task_type：env_judge

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202609.seed_env_judge

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

API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:8888')


# ============================================================
# 输入/输出参数定义
# ============================================================

_PARAMS = [
    # ─── 输入参数 ───
    ('ai_wav', '模型回复音频', '模型回复音频路径(被判定对象)', 'audio', 'input',
     None, None, None, True,
     False, None, '模型回复音频路径，裁判模型直接听回复音频判断理解是否正确', 5),
    ('user_wav', '用户通道音频', '用户通道音频路径(含环境声+用户询问)', 'audio', 'input',
     None, None, None, True,
     False, None, '用户通道音频，含环境声播放 + 用户询问，用于时延计算和ASR时间线', 6),
    ('play_audio', '环境声音频', '原始环境声音频路径(干净音源)', 'audio', 'input',
     None, None, None, True,
     False, None, '原始环境声音频(干净音源)，用于FFT互相关定位环境声在user_wav中的起止时间', 7),
    ('correctAnswer', '正确答案', '环境音参考内容文本(正确答案)', 'text', 'input',
     None, None, None, True,
     False, None, '环境音参考内容文本(正确答案)，作为评估模型理解准确性的参考标准', 8),
    ('task_type', '脚本类型', '脚本类型(0=无语义/1=有语义)', 'number', 'input',
     None, None, None, False,
     False, '0', '脚本类型: 0=无语义(non_semantic, 环境声为噪声判断声音类型) 或 1=有语义(semantic, 环境声含语义内容判断内容理解)', 9),
    ('model', 'LLM模型', 'LLM 模型名(覆盖默认)', 'text', 'input',
     None, None, None, False,
     False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认(注意:默认gpt-4o-mini不支持音频)', 10),
    ('max_tokens', '最大token', '最大输出 token 数', 'number', 'input',
     None, None, None, False,
     False, '4096', 'LLM 最大输出 token 数', 15),
    ('temperature', '采样温度', '采样温度', 'number', 'input',
     None, None, None, False,
     False, '0.1', '采样温度，评判场景建议低温 0.1', 20),

    # ─── 输出参数 ───
    ('understand_correct', '理解正确', '模型是否正确理解环境音(True/False)', 'text', 'output',
     'understand_correct', None, 'main', True,
     False, None, '模型是否正确理解环境音内容(True/False)，score>=4为True', 60),
    ('understand_correct_pass', '理解正确(数值)', '理解正确(1=True/0=False)', 'number', 'output',
     'understand_correct_pass', 'pass_eq', 'main', True,
     False, '0', '理解正确数值化(1=正确, 0=错误)，供子维度pass_rate聚合', 61, 1),
    ('score', 'LLM评分', 'LLM评分(1-5)', 'number', 'output',
     'score', None, 'aux', True,
     False, None, 'LLM评分(1-5)，无语义: 5=完全正确识别声音类型; 有语义: 5=完全一致理解全部关键信息', 62),
    ('reason', '判定理由', 'LLM判定理由', 'text', 'output',
     'reason', None, 'aux', True,
     False, None, 'LLM判定理由', 63),
    ('response_latency_ms', '回复时延', '用户询问到模型回复的时延(ms)', 'number', 'output',
     'response_latency_ms', None, 'aux', True,
     False, None, '用户询问结束到模型首字的时延(ms)，FFT互相关定位环境声+ASR时间戳计算', 64),
    ('ai_answer', '模型ASR', '模型侧ASR转写文本', 'text', 'output',
     'ai_answer', None, 'aux', True,
     False, None, '模型侧ASR转写文本', 65),
    ('env_sound_start_ms', '环境声起点', '环境声在user_wav中的起点(ms)', 'number', 'output',
     'env_sound_start_ms', None, 'aux', True,
     False, None, '环境声在user_wav中的起点(ms)，FFT互相关定位结果', 70),
    ('env_sound_end_ms', '环境声终点', '环境声在user_wav中的终点(ms)', 'number', 'output',
     'env_sound_end_ms', None, 'aux', True,
     False, None, '环境声在user_wav中的终点(ms)，FFT互相关定位结果', 71),
    ('user_question_end_ms', '用户询问结束', '用户询问结束时间(ms)', 'number', 'output',
     'user_question_end_ms', None, 'aux', True,
     False, None, '用户询问结束时间(ms)，从user_wav ASR chunks中获取', 72),
    ('model_first_word_start_ms', '模型首字', '模型首字起始时间(ms)', 'number', 'output',
     'model_first_word_start_ms', None, 'aux', True,
     False, None, '模型首字起始时间(ms)，从ai_wav ASR chunks中获取', 73),
    ('ncc', '互相关系数', 'FFT互相关峰值系数', 'number', 'output',
     'ncc', None, 'aux', True,
     False, None, 'FFT互相关峰值系数(NCC)，反映对齐置信度', 74),
    ('ej_model', '裁判模型', '使用的 LLM 模型', 'text', 'output',
     'model', None, 'aux', True,
     False, None, '本次裁判使用的 LLM 模型名', 80),
    ('ej_enabled', '是否启用', '裁判是否正常执行', 'text', 'output',
     'enabled', None, 'aux', True,
     False, None, '裁判是否正常执行(True/False)', 81),
    ('tokens_used', 'token用量', '总 token 用量', 'number', 'output',
     'tokens_used', None, 'aux', True,
     False, None, 'LLM 调用总 token 用量', 85),
    ('input_token', '输入token', '输入 token 数', 'number', 'output',
     'input_token', None, 'aux', True,
     False, None, 'LLM 输入 token 数', 86),
    ('output_token', '输出token', '输出 token 数', 'number', 'output',
     'output_token', None, 'aux', True,
     False, None, 'LLM 输出 token 数', 87),
    ('ej_message', '裁判说明', '裁判结果说明', 'text', 'output',
     'message', None, 'aux', True,
     False, None, '裁判错误/成功说明', 99),
]


# ── 请求体模板 ──
_BODY_TEMPLATE = {
    'model': '{{model}}',
    'max_tokens': '{{max_tokens}}',
    'temperature': '{{temperature}}',
    'task_type': '{{task_type}}',
    'rounds': [
        {
            'ai_wav': '{{ai_wav}}',
            'user_wav': '{{user_wav}}',
            'play_audio': '{{play_audio}}',
            'correctAnswer': '{{correctAnswer}}',
            'task_type': '{{task_type}}',
        }
    ],
}

# ── 参数映射 ──
_PARAM_MAPPINGS = [
    ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
    ('device', 'output', 'user_wav', 'user_wav', 'none'),
    ('device', 'output', 'play_audio', 'play_audio', 'none'),
    ('reference', 'output', 'correctAnswer', 'correctAnswer', 'none'),
]


# ============================================================
# 主维度定义
# ============================================================

DIMENSIONS = [
    {
        'task_type_code': 'env_judge',
        'legacy_task_type_codes': ['env_judge_non_semantic', 'env_judge_semantic'],
        'name': '环境理解裁判',
        'keywords': 'env_judge,环境理解,无语义,有语义,噪声,门铃,电话,警报,新闻广播,公共广播,电视节目,correctAnswer,understand,latency,互相关,task_type',
        'description': (
            '环境理解裁判：评估模型对环境音内容的理解是否正确。'
            '通过 task_type 输入参数区分两种场景：\n'
            '  task_type=0（无语义）：环境声为噪声(门铃/电话/警报等)，用户询问"刚刚是什么声音"，判断模型是否正确识别声音类型；\n'
            '  task_type=1（有语义）：环境声含语义内容(新闻/广播/电视等)，用户询问"刚刚电视说了什么"，判断模型是否正确理解内容。\n'
            '以模型回复音频(ai_wav)为判定对象，裁判模型直接听回复音频，'
            '与环境音参考内容文本(correctAnswer)比对。'
            '同时计算用户询问到模型回复的时延(FFT互相关定位环境声+ASR时间戳)。'
            'LLM评分1-5分，4分及以上为理解正确(True)。'
        ),
        'type': 'auto',
        'result_type': 1,  # 文本型
        'result_min': 0.0,
        'result_max': 0.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 120,
        'score_unit': '',
        'statistic_method': 'average',
        'params': _PARAMS,
        'param_mappings': _PARAM_MAPPINGS,
        'body_template': _BODY_TEMPLATE,
    },
]


# ============================================================
# 子维度定义（2个理解正确率子维度）
# ============================================================

SUB_DIMENSIONS = {
    'env_judge': [
        {
            'task_type_code': 'env_judge',
            'name': '无语义脚本理解正确率',
            'keywords': 'env_judge,non_semantic,无语义,理解正确率,pass_rate',
            'description': '子维度：无语义脚本(task_type=0)理解正确率。output field_path = understand_correct_pass',
            'type': 'auto',
            'result_type': 0,
            'result_min': 0.0,
            'result_max': 1.0,
            'decimal_places': 2,
            'weight': 1,
            'estimated_exec_time': 120,
            'score_unit': '%',
            'statistic_method': 'pass_rate',
            'params': [
                ('non_semantic_correct', '无语义理解正确率', '无语义脚本理解正确率(1=正确/0=错误)',
                 'number', 'output',
                 'understand_correct_pass', 'pass_eq', 'main', True,
                 False, '0', '无语义脚本(task_type=0)理解正确率', 60, 1),
            ],
        },
        {
            'task_type_code': 'env_judge',
            'name': '有语义脚本理解正确率',
            'keywords': 'env_judge,semantic,有语义,理解正确率,pass_rate',
            'description': '子维度：有语义脚本(task_type=1)理解正确率。output field_path = understand_correct_pass',
            'type': 'auto',
            'result_type': 0,
            'result_min': 0.0,
            'result_max': 1.0,
            'decimal_places': 2,
            'weight': 1,
            'estimated_exec_time': 120,
            'score_unit': '%',
            'statistic_method': 'pass_rate',
            'params': [
                ('semantic_correct', '有语义理解正确率', '有语义脚本理解正确率(1=正确/0=错误)',
                 'number', 'output',
                 'understand_correct_pass', 'pass_eq', 'main', True,
                 False, '0', '有语义脚本(task_type=1)理解正确率', 60, 1),
            ],
        },
    ],
}


# ============================================================
# 数据库操作函数
# ============================================================

def _upsert_dimension(conn, dim_def, dimension_type, parent_id=None):
    """注册/更新一个维度，返回 dim_id。"""
    task_code = dim_def['task_type_code']
    name = dim_def['name']

    if dimension_type == 'sub':
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE name = :name "
            "AND dimension_type = 'sub' AND deleted = FALSE"
        ), {'name': name}).fetchone()
    else:
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = :tc AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        ), {'tc': task_code}).fetchone()

    api_settings = json.dumps({
        'method': 'POST',
        'headers': {},
        'body_template': dim_def.get('body_template', _BODY_TEMPLATE),
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
    """软清理 DB 中当前 dim_def.params 不再出现的 param_code。"""
    current_output_codes = {p[0] for p in dim_def['params'] if p[4] == 'output'}
    current_input_codes = {p[0] for p in dim_def['params'] if p[4] == 'input'}
    for direction, current_codes in (
        ('output', current_output_codes),
        ('input', current_input_codes),
    ):
        if not current_codes:
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
    """注册 voice_llm → 维度的 param_mappings（幂等）。"""
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


def seed_env_judge():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        for dim_def in DIMENSIONS:
            task_code = dim_def['task_type_code']
            legacy_codes = dim_def.get('legacy_task_type_codes', [])
            print(f"\n{'=' * 60}")
            print(f"  处理维度: {task_code} ({dim_def['name']})")
            if legacy_codes:
                print(f"  legacy codes 将被改名: {legacy_codes}")
            print(f"{'=' * 60}")

            # Step 0: 旧 code 改名/清理
            if legacy_codes:
                print(f"\n--- Step 0: 清理旧 code {legacy_codes} ---")
                for old_code in legacy_codes:
                    rows = conn.execute(text(
                        "SELECT id, name FROM dimensions "
                        "WHERE task_type_code = :oc AND deleted = FALSE"
                    ), {'oc': old_code}).fetchall()
                    if not rows:
                        print(f"  - 无 {old_code} 记录，跳过")
                        continue
                    for rid, rname in rows:
                        print(f"  - 软删除旧维度 {old_code}(id={rid}, name={rname})")
                        conn.execute(text(
                            "UPDATE dimensions SET deleted = TRUE, "
                            "updated_at = NOW() WHERE id = :rid"
                        ), {'rid': rid})

            # Step 1: 注册主维度
            print(f"\n--- Step 1: 注册 {task_code} 主维度 ---")
            main_id = _upsert_dimension(conn, dim_def, dimension_type='main', parent_id=None)
            print(f"  主维度 id = {main_id}")
            _upsert_params(conn, main_id, dim_def)
            _upsert_relation(conn, main_id)
            _upsert_param_mappings(conn, main_id, dim_def)

            # Step 2: 注册子维度
            sub_defs = SUB_DIMENSIONS.get(task_code, [])
            print(f"\n--- Step 2: 注册 {len(sub_defs)} 个子维度（parent_dimension_id={main_id}） ---")
            for sub_def in sub_defs:
                print(f"\n  -- 子维度: {sub_def['name']} --")
                sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
                print(f"  子维度 id = {sub_id}")
                _upsert_params(conn, sub_id, sub_def)
                _upsert_relation(conn, sub_id)

        print(f"\n{'=' * 60}")
        print("  环境理解裁判维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("环境理解裁判维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册 1 个主维度 + 2 个子维度：")
    print("  env_judge  环境理解裁判")
    print("    task_type=0 → 无语义(噪声识别), task_type=1 → 有语义(内容理解)")
    print("    输出: understand_correct(True/False) + response_latency_ms")
    print("  子维度: 无语义脚本理解正确率 / 有语义脚本理解正确率")
    print()
    print("  入参: ai_wav, user_wav, play_audio, correctAnswer, task_type, model, max_tokens, temperature")
    print()
    seed_env_judge()
    print()
    print("完成！")
