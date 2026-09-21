# -*- coding: utf-8 -*-
"""
拒识裁判 v2 维度种子数据（reject_judge 主维度 + 行为/评级子维度）

功能：
1. 注册一个主维度（dimension_type='main'）：
   - reject_judge  拒识裁判 v2（非目标人拒识/目标人非交互意图/环境噪声/用户BC）
2. 注册主维度的输入/输出参数（evaluation_dimension_params）
   输入：ai_wav, user_wav, is_single_round, timing, model, max_tokens, temperature
   输出：evaluations, ej_behavior, ej_timing, ej_rate, ej_reason,
         ej_interaction, ej_query, ej_answer,
         rate_success_count, rate_inquiry_count, rate_failure_count
3. 注册子维度（dimension_type='sub'）：
   - 3 个父级子维度：拒识成功率/拒识询问率/拒识失败率 占比
   - 9 个子级子维度：按 timing+behavior 细分
   子维度 statistic_method='pass_rate'，agg_role='pass_eq'，pass_threshold=1
4. 注册 voice_llm 算法与主维度的关联（algorithm_dimension_relations）
5. 注册 voice_llm → 主维度的参数映射（param_mappings）

对应 eval_server 服务：
   - eval_server/app/services/calculators/xiaoyi_metrics/env_judge/rejection_judge.py
   - 入口：evaluate_rejection_judge
   - task_type：reject_judge（复用 RejectionJudgeCalculator）

与旧版 rejection_judge 的区别：
   - 新增 is_single_round（单轮/多轮拒识）、timing（拒识时机）输入参数
   - 场景更新为：非目标人拒识/目标人非交互意图/环境噪声/用户BC（去掉环境回溯）
   - 行为类别从 4 种改为 5 种（回应/恢复/不确定询问/无关回复/静默）
   - 新增 rate 评级输出（0=拒识成功, 1=拒识询问, 2=拒识失败）
   - user_wav 音频直接发给 LLM（不仅是 ASR 时间线）

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202609.seed_reject_judge

或直接：
    python backend/scripts/migrations/202609/seed_reject_judge.py

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

# eval_server 微服务地址
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:8888')

# ============================================================
# 维度定义
# ============================================================

# ── 输入参数 ──
_PARAMS = [
    # ─── 输入参数 ───
    ('ai_wav', '模型回复音频', '模型回复音频路径(被判定对象)', 'audio', 'input',
     None, None, None, True,
     False, None, '模型回复音频路径，裁判模型直接听回复音频判断行为', 5),
    ('user_wav', '用户通道音频', '用户通道音频路径', 'audio', 'input',
     None, None, None, False,
     False, None, '用户通道音频(可选)，直接发给LLM + 经ASR转写生成时间线上下文', 6),
    ('is_single_round', '单轮拒识', '是否为单轮拒识模式', 'boolean', 'input',
     None, None, None, False,
     False, 'false', 'True=单轮拒识(user_wav直接为拒识内容)，False=多轮拒识(user_wav包含意图交互+拒识干扰)', 7),
    ('timing', '拒识时机', '拒识发生时机', 'text', 'input',
     None, None, None, False,
     False, None, '拒识发生时机(回复过程中/静默)，决定行为类别定义和rate计算规则', 8),
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
    ('evaluations', '裁判结果', 'LLM 裁判结果', 'json', 'output',
     'evaluations', None, 'aux', True,
     False, None, 'LLM 裁判结果列表 [{behavior, reason}, ...]', 60),
    ('ej_behavior', '裁判行为', 'LLM裁判行为类别', 'text', 'output',
     'evaluations.0.behavior', None, 'aux', True,
     False, None, 'LLM裁判行为类别(回应/恢复/不确定询问/无关回复/静默; 取evaluations首条)', 62),
    ('ej_timing', '拒识时机', '拒识发生时机', 'text', 'output',
     'timing', None, 'aux', True,
     False, None, '拒识干扰内容发生时机(回复过程中/静默)', 63),
    ('ej_rate', '拒识评级', '拒识结果评级', 'text', 'output',
     'rate', None, 'aux', True,
     False, None, '拒识结果评级(0=拒识成功, 1=拒识询问, 2=拒识失败, "拒识成功"=特殊)', 64),
    ('ej_reason', '裁判理由', 'LLM裁判判定理由', 'text', 'output',
     'evaluations.0.reason', None, 'aux', True,
     False, None, 'LLM裁判判定理由(取evaluations首条)', 65),
    ('ej_interaction', '交互内容', '完整交互文字(带时间戳)', 'text', 'output',
     'interaction_text', None, 'aux', True,
     False, None, '用例完整交互文字，query/answer 按时间排序，含时间戳', 67),
    ('ej_query', '用户ASR', '用户侧ASR文本', 'text', 'output',
     'query', None, 'aux', True,
     False, None, '用户侧ASR转写文本', 68),
    ('ej_answer', '模型ASR', '模型侧ASR文本', 'text', 'output',
     'answer', None, 'aux', True,
     False, None, '模型侧ASR转写文本', 69),
    ('rate_success_count', '拒识成功统计', '拒识成功数量统计(按timing+behavior分组)', 'json', 'output',
     'rate_success_count', None, 'aux', True,
     False, None, '拒识成功数量统计字典，含总数及各timing+behavior组合命中数', 73),
    ('rate_inquiry_count', '拒识询问统计', '拒识询问数量统计(按timing+behavior分组)', 'json', 'output',
     'rate_inquiry_count', None, 'aux', True,
     False, None, '拒识询问数量统计字典，含总数及各timing+behavior组合命中数', 74),
    ('rate_failure_count', '拒识失败统计', '拒识失败数量统计(按timing+behavior分组)', 'json', 'output',
     'rate_failure_count', None, 'aux', True,
     False, None, '拒识失败数量统计字典，含总数及各timing+behavior组合命中数', 75),
]

# ── 请求体模板 ──
_BODY_TEMPLATE = {
    'model': '{{model}}',
    'max_tokens': '{{max_tokens}}',
    'temperature': '{{temperature}}',
    'is_single_round': '{{is_single_round}}',
    'timing': '{{timing}}',
    'rounds': [
        {
            'ai_wav': '{{ai_wav}}',
            'user_wav': '{{user_wav}}',
            'is_single_round': '{{is_single_round}}',
            'timing': '{{timing}}',
        }
    ],
}

# ── 参数映射 ──
_PARAM_MAPPINGS = [
    ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
    ('device', 'output', 'user_wav', 'user_wav', 'none'),
    ('reference', 'output', 'is_single_round', 'is_single_round', 'none'),
    ('reference', 'output', 'timing', 'timing', 'none'),
]

# ── 主维度定义 ──
DIMENSIONS = [
    {
        'task_type_code': 'reject_judge',
        'legacy_task_type_codes': [],
        'name': '拒识裁判v2',
        'keywords': 'reject,judge,拒识,裁判,非目标人,目标人非交互意图,环境噪声,用户BC,单轮,多轮,timing,rate',
        'description': (
            '拒识裁判 v2：评估模型在拒识场景下的行为。'
            '以模型回复音频(ai_wav)为主输入，裁判模型直接听回复，'
            '用户通道音频(user_wav)也直接发给裁判模型（不仅是ASR时间线）。'
            '场景包括非目标人拒识/目标人非交互意图/环境噪声/用户BC，'
            '支持单轮(is_single_round=true)和多轮(is_single_round=false)拒识模式，'
            '由裁判模型对语音大模型的行为进行评判（回应/恢复/不确定询问/无关回复/静默），'
            '并给出拒识时机（回复过程中/静默）和拒识评级（0=拒识成功/1=拒识询问/2=拒识失败）。'
        ),
        'type': 'auto',
        'result_type': 1,  # 文本型，LLM 裁判输出为 JSON，evaluations 为 main
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
# 子维度定义（3个父级 + 9个子级）
# 父级：拒识成功率/拒识询问率/拒识失败率 占比
# 子级：按 timing+behavior 细分
# ============================================================

_SUB_DIMENSIONS_DEF = [
    {
        'name': '拒识成功率占比',
        'field': 'rate_success',
        'help': 'rate=拒识成功的占比',
        'children': [
            ('success_silent_recover',  '静默时拒识恢复行为占比', '静默期间behavior=恢复或静默，拒识成功'),
            ('success_reply_recover',    '回复时拒识恢复行为占比', '回复过程中behavior=恢复，拒识成功'),
        ],
    },
    {
        'name': '拒识询问率占比',
        'field': 'rate_inquiry',
        'help': 'rate=拒识询问的占比',
        'children': [
            ('inquiry_silent',  '静默时拒识询问行为占比', '静默期间behavior=不确定询问'),
            ('inquiry_reply',    '回复时拒识询问行为占比', '回复过程中behavior=不确定询问'),
        ],
    },
    {
        'name': '拒识失败率占比',
        'field': 'rate_failure',
        'help': 'rate=拒识失败的占比',
        'children': [
            ('failure_silent_respond',    '静默时拒识回应行为占比',   '静默期间behavior=回应'),
            ('failure_reply_respond',      '回复时拒识回应行为占比',   '回复过程中behavior=回应'),
            ('failure_silent_irrelevant',  '静默时拒识无关行为占比',   '静默期间behavior=无关回复'),
            ('failure_reply_irrelevant',   '回复时拒识无关行为占比',   '回复过程中behavior=无关回复'),
            ('failure_reply_silent',       '回复时拒识静默行为占比',   '回复过程中behavior=静默'),
        ],
    },
]


def _build_parent_dim(task_type_code, name, field, help):
    return {
        'task_type_code': task_type_code,
        'name': name,
        'keywords': f'{task_type_code},{field},{name}',
        'description': f'父级子维度：{name}。output field_path = {field}',
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
            (field, name, name,
             'number', 'output',
             field, 'pass_eq', 'main', True,
             False, '0', help, 60, 1),
        ],
    }


def _build_child_dim(task_type_code, name, field, help, ui_order):
    return {
        'task_type_code': task_type_code,
        'name': name,
        'keywords': f'{task_type_code},{field},{name}',
        'description': f'子维度：{name}。output field_path = {field}',
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
            (field, name, name,
             'number', 'output',
             field, 'pass_eq', 'main', True,
             False, '0', help, ui_order, 1),
        ],
    }


SUB_DIMENSIONS = {
    'reject_judge': [
        {
            'parent': _build_parent_dim('reject_judge', p['name'], p['field'], p['help']),
            'children': [
                _build_child_dim('reject_judge', cname, cfield, chelp, 61 + j)
                for j, (cfield, cname, chelp) in enumerate(p['children'])
            ],
        }
        for p in _SUB_DIMENSIONS_DEF
    ],
}


# ============================================================
# 数据库操作函数（从 seed_env_sound_judge.py 复用）
# ============================================================

def _upsert_dimension(conn, dim_def, dimension_type, parent_id=None):
    """注册/更新一个维度，返回 dim_id。dimension_type: 'main' or 'sub'。"""
    task_code = dim_def['task_type_code']
    name = dim_def['name']

    if dimension_type == 'sub':
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE name = :name "
            "AND dimension_type = 'sub' AND deleted = FALSE"
        ), {'name': name}).fetchone()
        if existing:
            old_tc = conn.execute(text(
                "SELECT task_type_code FROM dimensions WHERE id = :did"
            ), {'did': existing[0]}).scalar()
            if old_tc != task_code:
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


def seed_reject_judge():
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

            # Step 0: 旧 code 改名
            if legacy_codes:
                print(f"\n--- Step 0: 迁移旧 code {legacy_codes} → {task_code} ---")
                for old_code in legacy_codes:
                    rows = conn.execute(text(
                        "SELECT id, name FROM dimensions "
                        "WHERE task_type_code = :oc AND deleted = FALSE"
                    ), {'oc': old_code}).fetchall()
                    if not rows:
                        print(f"  - 无 {old_code} 记录，跳过")
                        continue
                    for rid, rname in rows:
                        conflict = conn.execute(text(
                            "SELECT id FROM dimensions "
                            "WHERE task_type_code = :nc AND deleted = FALSE "
                            "AND id <> :rid"
                        ), {'nc': task_code, 'rid': rid}).fetchone()
                        if conflict:
                            print(f"  ! {old_code}(id={rid}) 与 {task_code}(id={conflict[0]}) 冲突，软删旧记录")
                            conn.execute(text(
                                "UPDATE dimensions SET deleted = TRUE, "
                                "updated_at = NOW() WHERE id = :rid"
                            ), {'rid': rid})
                        else:
                            print(f"  - {old_code}(id={rid}, name={rname}) "
                                  f"→ rename task_type_code = {task_code}")
                            conn.execute(text(
                                "UPDATE dimensions SET task_type_code = :nc, "
                                "updated_at = NOW() WHERE id = :rid"
                            ), {'nc': task_code, 'rid': rid})

            # Step 1: 注册主维度
            print(f"\n--- Step 1: 注册 {task_code} 主维度 ---")
            main_id = _upsert_dimension(conn, dim_def, dimension_type='main', parent_id=None)
            print(f"  主维度 id = {main_id}")
            _upsert_params(conn, main_id, dim_def)
            _upsert_relation(conn, main_id)
            _upsert_param_mappings(conn, main_id, dim_def)

            # Step 2: 注册子维度（3个父级 + 9个子级）
            sub_groups = SUB_DIMENSIONS.get(task_code, [])
            total_subs = sum(len(g['children']) for g in sub_groups) + len(sub_groups)
            print(f"\n--- Step 2: 注册 {len(sub_groups)} 个父级 + {sum(len(g['children']) for g in sub_groups)} 个子级子维度 ---")
            for group in sub_groups:
                parent_def = group['parent']
                print(f"\n  -- 父级子维度: {parent_def['name']} --")
                parent_sub_id = _upsert_dimension(conn, parent_def, dimension_type='sub', parent_id=main_id)
                print(f"  父级子维度 id = {parent_sub_id}")
                _upsert_params(conn, parent_sub_id, parent_def)
                _upsert_relation(conn, parent_sub_id)

                for child_def in group['children']:
                    print(f"    -- 子级: {child_def['name']} --")
                    child_id = _upsert_dimension(conn, child_def, dimension_type='sub', parent_id=parent_sub_id)
                    print(f"    子级 id = {child_id}")
                    _upsert_params(conn, child_id, child_def)
                    _upsert_relation(conn, child_id)

        print(f"\n{'=' * 60}")
        print("  拒识裁判v2(reject_judge) 维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("拒识裁判v2维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. reject_judge 主维度 — 拒识裁判v2")
    print("   场景: 非目标人拒识/目标人非交互意图/环境噪声/用户BC")
    print("   模式: 单轮(is_single_round=true)/多轮(is_single_round=false)")
    print("   时机: timing(回复过程中/静默)")
    print("2. 3 个父级子维度（拒识成功率/拒识询问率/拒识失败率 占比）")
    print("3. 9 个子级子维度（按 timing+behavior 细分）")
    print()
    print("   入参: ai_wav, user_wav, is_single_round, timing, model, max_tokens, temperature")
    print()
    seed_reject_judge()
    print()
    print("完成！")
