# -*- coding: utf-8 -*-
"""
环境音裁判维度种子数据（拆分为 rejection_judge + interruption_judge 两个主维度 + 8 个行为子维度）

功能：
1. 注册两个主维度（dimension_type='main'）：
   - rejection_judge   拒识场景裁判（旁人交谈/环境噪声/反馈词/生理声/环境回溯）
   - interruption_judge 打断场景裁判（插话打断/停止指令/恢复原话题）
2. 注册每个主维度的输入/输出参数（evaluation_dimension_params）
3. 为每个主维度注册 4 个行为子维度（dimension_type='sub'）：
   - 拒识回应占比 / 拒识恢复占比 / 拒识不确定询问占比 / 拒识未知占比
   - 打断回应占比 / 打断恢复占比 / 打断不确定询问占比 / 打断未知占比
   子维度 statistic_method='pass_rate'，agg_role='pass_eq'，pass_threshold=1
   eval_server 返回 behavior_respond/recover/uncertain/unknown 四个 0/1 字段，
   子维度从同一响应按各自 field_path 提取，pass_rate 聚合后即为占比
4. 注册 voice_llm 算法与主维度的关联（algorithm_dimension_relations）
5. 注册 voice_llm → 主维度的参数映射（param_mappings）

对应 eval_server 服务：
   - eval_server/app/services/calculators/xiaoyi_metrics/env_judge/rejection_judge.py
   - eval_server/app/services/calculators/xiaoyi_metrics/env_judge/interruption_judge.py
   - 入口：evaluate_rejection_judge / evaluate_interruption_judge
   - task_type：rejection_judge / interruption_judge

录屏不再可用后的方案：以模型回复音频 ai_wav 为主输入（裁判直接听回复，不过小 ASR），
用户侧 ASR 转写 + 环境声事件(start_ms/end_ms/pcm_first_ms 换算到模型音频相对秒)作
文本时间线上下文，不合并两路音频。

输入：
   - ai_wav       : 模型回复音频路径（主输入，被判定对象）
   - scene        : 场景名（如'旁人交谈''插话打断'等，兼容旧 env_type 字段）
   - user_wav     : 用户通道音频（可选，走小 ASR 生成时间线）
   - start_ms/end_ms/pcm_first_ms : 环境声播放绝对毫秒 + 模型音频起点毫秒
   - model        : LLM 模型名（可选，缺省读 config.LLM_JUDGE.default_model；
                    注意默认 gpt-4o-mini 不支持音频，音频裁判需指定 gpt-audio/omni 等）

输出：
   - evaluations : LLM 裁判结果列表 [{scene, behavior, reason}, ...]
   - behavior_respond/recover/uncertain/unknown : 四个 0/1 字段（供子维度 pass_rate 聚合）

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_env_sound_judge

或直接：
    python backend/scripts/migrations/202606/seed_env_sound_judge.py

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
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:5000')

# ============================================================
# 维度定义
# ============================================================
# ── 公共参数（两个维度共享的输入+输出参数定义） ──
_COMMON_PARAMS = [
    # ─── 输入参数 ───
    ('ai_wav', '模型回复音频', '模型回复音频路径(被判定对象)', 'audio', 'input',
     None, None, None, True,
     False, None, '模型回复音频路径，裁判模型直接听回复(不过小ASR)；录屏没了的主输入', 5),
    ('scene', '场景', '场景类型(决定使用哪组prompt)', 'text', 'input',
     None, None, None, False,
     False, None, '场景名(如 旁人交谈/环境噪声/插话打断 等)，为空则评估全部场景；兼容旧 env_type 字段', 10),
    ('model', 'LLM模型', 'LLM 模型名(覆盖默认)', 'text', 'input',
     None, None, None, False,
     False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认(注意:默认gpt-4o-mini不支持音频，音频裁判需指定gpt-audio/omni等)', 15),
    ('max_tokens', '最大token', '最大输出 token 数', 'number', 'input',
     None, None, None, False,
     False, '4096', 'LLM 最大输出 token 数', 20),
    ('temperature', '采样温度', '采样温度', 'number', 'input',
     None, None, None, False,
     False, '0.1', '采样温度，评判场景建议低温 0.1', 25),
    ('user_wav', '用户通道音频', '用户通道音频路径', 'audio', 'input',
     None, None, None, False,
     False, None, '用户通道音频(可选)，走小ASR生成时间线上下文', 26),
    ('start_ms', '环境声起点', '环境声播放起点(绝对毫秒)', 'timestamp', 'input',
     None, None, None, False,
     False, None, '环境声播放起点毫秒(与pcm_first_ms同时间轴)，换算成相对秒作时间窗事件', 27),
    ('end_ms', '环境声终点', '环境声播放终点(绝对毫秒)', 'timestamp', 'input',
     None, None, None, False,
     False, None, '环境声播放终点毫秒', 28),
    ('pcm_first_ms', '模型音频起点', '模型音频起点(绝对毫秒)', 'timestamp', 'input',
     None, None, None, False,
     False, None, '模型音频(ai_wav)起点毫秒，把环境声绝对毫秒换算到模型音频相对秒', 29),

    # ─── 输出参数 ───
    ('evaluations', '裁判结果', 'LLM 裁判结果', 'json', 'output',
     'evaluations', None, 'main', True,
     False, None, 'LLM 裁判结果列表 [{scene, behavior, reason}, ...]', 60),
    ('ej_model', '裁判模型', '使用的 LLM 模型', 'text', 'output',
     'model', None, 'aux', True,
     False, None, '本次裁判使用的 LLM 模型名', 61),
    ('ej_scene', '场景', '场景类型', 'text', 'output',
     'scene', None, 'aux', True,
     False, None, '场景类型(兼容旧 env_type)', 63),
    ('ej_enabled', '是否启用', '裁判是否正常执行', 'text', 'output',
     'enabled', None, 'aux', True,
     False, None, '裁判是否正常执行(True/False)', 64),
    ('tokens_used', 'token用量', '总 token 用量', 'number', 'output',
     'tokens_used', None, 'aux', True,
     False, None, 'LLM 调用总 token 用量', 70),
    ('input_token', '输入token', '输入 token 数', 'number', 'output',
     'input_token', None, 'aux', True,
     False, None, 'LLM 输入 token 数', 71),
    ('output_token', '输出token', '输出 token 数', 'number', 'output',
     'output_token', None, 'aux', True,
     False, None, 'LLM 输出 token 数', 72),
    ('ej_message', '裁判说明', '裁判结果说明', 'text', 'output',
     'message', None, 'aux', True,
     False, None, '裁判错误/成功说明', 99),
]

# ── 公共参数映射 ──
_COMMON_PARAM_MAPPINGS = [
    ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
    ('device', 'output', 'user_wav', 'user_wav', 'none'),
    ('device', 'output', 'start_ms', 'start_ms', 'none'),
    ('device', 'output', 'end_ms', 'end_ms', 'none'),
    ('device', 'output', 'pcm_first_ms', 'pcm_first_ms', 'none'),
    ('reference', 'output', 'scene', 'scene', 'none'),
    # 兼容旧 env_type 字段
    ('reference', 'output', 'env_type', 'scene', 'none'),
]

DIMENSIONS = [
    {
        'task_type_code': 'rejection_judge',
        'legacy_task_type_codes': ['env_judge', 'env_sound_judge'],
        'name': '拒识场景裁判',
        'keywords': 'rejection,judge,拒识,场景,裁判,旁人交谈,环境噪声,反馈词,生理声,环境回溯',
        'description': (
            '拒识场景 LLM 裁判：评估模型在拒识场景下的行为。'
            '以模型回复音频(ai_wav)为主输入，裁判模型直接听回复，'
            '用户侧 ASR + 环境声事件作为文本时间线上下文。'
            '场景包括旁人交谈静默/环境噪声不触发/反馈词不误触发/生理声不触发/环境事件被动记录与回溯，'
            '由裁判模型对语音大模型的行为进行评判（回应/恢复/不确定询问/未知）。'
        ),
        'type': 'auto',
        'result_type': 1,  # 文本型，LLM 裁判输出为 JSON，evaluations 为 main
        'result_min': 0.0,
        'result_max': 0.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 120,  # LLM 调用
        'score_unit': '',
        'statistic_method': 'none',
        'params': _COMMON_PARAMS,
        'param_mappings': _COMMON_PARAM_MAPPINGS,
    },
    {
        'task_type_code': 'interruption_judge',
        'legacy_task_type_codes': [],
        'name': '打断场景裁判',
        'keywords': 'interruption,judge,打断,场景,裁判,插话打断,停止指令,恢复原话题',
        'description': (
            '打断场景 LLM 裁判：评估模型在打断场景下的行为。'
            '以模型回复音频(ai_wav)为主输入，裁判模型直接听回复，'
            '用户侧 ASR + 环境声事件作为文本时间线上下文。'
            '场景包括插话打断与重新响应/停止指令响应/多轮对话打断后恢复原话题，'
            '由裁判模型对语音大模型的行为进行评判（回应/恢复/不确定询问/未知）。'
        ),
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': 0.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 120,
        'score_unit': '',
        'statistic_method': 'none',
        'params': _COMMON_PARAMS,
        'param_mappings': _COMMON_PARAM_MAPPINGS,
    },
]

# ============================================================
# 行为子维度定义：每个主维度 4 个子维度
# statistic_method='pass_rate' + agg_role='pass_eq' + pass_threshold=1
# eval_server 返回 0/1，pass_rate 统计 1 的占比即行为占比
# ============================================================
# 子维度用 (param_code, field_path, name, label, help_text, ui_order) 描述
_BEHAVIOR_FIELDS = [
    ('behavior_respond',   '回应',   '模型对重叠内容进行了有意义的回应'),
    ('behavior_recover',   '恢复',   '模型忽略重叠，继续或完成重叠前正在进行的任务'),
    ('behavior_uncertain', '不确定询问', '模型表示不确定或难以听清、缺少信息'),
    ('behavior_unknown',   '未知',   '模型输出语义偏离目标或信息量低'),
]

def _build_sub_dimensions(task_type_code, prefix):
    """为主维度生成 4 个行为占比子维度定义。"""
    subs = []
    for i, (field, label, help) in enumerate(_BEHAVIOR_FIELDS):
        subs.append({
            'task_type_code': task_type_code,
            'name': f'{prefix}{label}占比',
            'keywords': f'{task_type_code},{field},{label},占比',
            'description': f'子维度：{prefix}行为「{label}」的占比。output field_path = {field}',
            'type': 'auto',
            'result_type': 0,  # 数值型
            'result_min': 0.0,
            'result_max': 1.0,
            'decimal_places': 2,
            'weight': 1,
            'estimated_exec_time': 120,
            'score_unit': '%',
            'statistic_method': 'pass_rate',
            'params': [
                (field, f'{label}占比', f'{prefix}{label}行为占比',
                 'number', 'output',
                 field, 'pass_eq', 'main', True,
                 False, '0', help, 60 + i, 1),
            ],
        })
    return subs

SUB_DIMENSIONS = {
    'rejection_judge': _build_sub_dimensions('rejection_judge', '拒识'),
    'interruption_judge': _build_sub_dimensions('interruption_judge', '打断'),
}


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

    api_settings = json.dumps({
        'method': 'POST',
        'headers': {},
        'body_template': {
            'model': '{{model}}',
            'max_tokens': '{{max_tokens}}',
            'temperature': '{{temperature}}',
            'rounds': [
                {
                    'ai_wav': '{{ai_wav}}',
                    'user_wav': '{{user_wav}}',
                    'scene': '{{scene}}',
                    'start_ms': '{{start_ms}}',
                    'end_ms': '{{end_ms}}',
                    'pcm_first_ms': '{{pcm_first_ms}}',
                }
            ],
        },
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


def seed_env_sound_judge():
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

            # ============================================================
            # Step 0: 旧 code 改名（避免残留孤儿记录）
            # ============================================================
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

            # ============================================================
            # Step 1: 注册主维度
            # ============================================================
            print(f"\n--- Step 1: 注册 {task_code} 主维度 ---")
            main_id = _upsert_dimension(conn, dim_def, dimension_type='main', parent_id=None)
            print(f"  主维度 id = {main_id}")
            _upsert_params(conn, main_id, dim_def)
            _upsert_relation(conn, main_id)
            _upsert_param_mappings(conn, main_id, dim_def)

            # ============================================================
            # Step 2: 注册 4 个行为子维度
            # ============================================================
            sub_defs = SUB_DIMENSIONS.get(task_code, [])
            print(f"\n--- Step 2: 注册 {len(sub_defs)} 个行为子维度（parent_dimension_id={main_id}） ---")
            for sub_def in sub_defs:
                print(f"\n  -- 子维度: {sub_def['name']} --")
                sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
                print(f"  子维度 id = {sub_id}")
                _upsert_params(conn, sub_id, sub_def)
                _upsert_relation(conn, sub_id)

        print(f"\n{'=' * 60}")
        print("  拒识场景裁判 + 打断场景裁判维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("环境音裁判维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. rejection_judge 主维度 — 拒识场景裁判")
    print("   场景: 旁人交谈静默/环境噪声/反馈词/生理声/环境事件回溯")
    print("2. interruption_judge 主维度 — 打断场景裁判")
    print("   场景: 插话打断与重新响应/停止指令响应/恢复原话题")
    print("3. 每个主维度 4 个行为子维度（pass_rate 聚合）:")
    print("   - 拒识回应占比 / 拒识恢复占比 / 拒识不确定询问占比 / 拒识未知占比")
    print("   - 打断回应占比 / 打断恢复占比 / 打断不确定询问占比 / 打断未知占比")
    print()
    print("   入参: ai_wav(模型回复音频), scene(场景), user_wav, start_ms/end_ms/pcm_first_ms, model, max_tokens, temperature")
    print()
    print("   主分: 裁判结果 (evaluations)")
    print("   行为 0/1: behavior_respond/recover/uncertain/unknown")
    print()
    print("脚本可重复执行（幂等）")
    print()

    if '--yes' not in sys.argv:
        confirm = input("是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            sys.exit(0)

    try:
        seed_env_sound_judge()
    except Exception as e:
        print(f"\n注册失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
