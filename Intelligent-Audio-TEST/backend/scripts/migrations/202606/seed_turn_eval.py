# -*- coding: utf-8 -*-
"""
turn_eval 维度种子数据（turn_eval 主维度 + turn_evaluation 子维度）

功能：
1. 注册/更新 turn_eval 主维度（dimension_type='main'）：
   - 配置 input params（user_wav, ai_wav, played_audios, query）
   - 配置 api_settings、body_template、param_mappings
   - 不配 output params（主维度只作容器，output 挂在子维度上）
2. 注册/更新 turn_evaluation 子维度（dimension_type='sub', parent_dimension_id 指向主维度）：
   - output field_path 映射 turn_eval JSON 响应结构：
     - turn_classification.summary / .normal_takeover_count / .no_takeover_count
       / .false_takeover_count / .total_turns / .turns
     - tor.tor（兼容末轮）
     - false_takeover.tor / .reason（兼容末轮）
     - takeover_latency.takeover_latency_ms（兼容末轮）
     - reply_quality.score（兼容末轮）
     - interaction_text
3. 注册 voice_llm 算法与主维度 + 子维度的关联（algorithm_dimension_relations）
4. 注册 voice_llm → 主维度的参数映射（param_mappings.dimension_id = 主维度id）

执行链路：
   用例选 turn_evaluation 子维度 → 平台按 (api_url, parent_dimension_id) 分组
   → task_type 用主维度的 turn_eval，payload 注入 sub_tasks=['turn_evaluation']
   → 调一次 eval_server，TurnEvalCalculator 计算逐轮三分类 + 时延 + 质量
   → process_group_dimension_results 按 output field_path 分发提取

对应 eval_server 服务：
   - turn_eval/strategy.py 一次返回包含 turn_classification/tor/false_takeover/
     takeover_latency/reply_quality/interaction_text 的 JSON

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_turn_eval

或直接：
    python backend/scripts/migrations/202606/seed_turn_eval.py

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
# 主维度定义：turn_eval（只配 input + api_settings + param_mappings，不配 output）
# ============================================================
MAIN_DIMENSION = {
    'task_type_code': 'turn_eval',
    'name': '逐轮话轮评估',
    'keywords': 'turn_eval,逐轮,三分类,误解管,接管,未接管,turn_evaluation,接管时延,回复质量',
    'description': '逐轮话轮评估主维度：调双路 ASR（user_wav + ai_wav）一次，切分轮次后逐轮三分类（误解管/接管/未接管），仅对"接管"轮计算接管时延和回复质量。主维度只配 input 和映射，不配 output。',
    'type': 'auto',
    'result_type': 0,
    'result_min': 0.0,
    'result_max': 1.0,
    'decimal_places': 2,
    'weight': 1,
    'estimated_exec_time': 60,
    'score_unit': '',
    'statistic_method': 'pass_rate',
    'body_template': {
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
                'played_audios': '{{played_audios}}',
                'background_noise': '{{background_noise}}',
                'interferers': '{{interferers}}',
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
        ('played_audios', '用例干净音源', '用例干净音源', 'audio', 'input',
         None, None, None, False,
         False, None, '用例干净音源 wav 路径（音频对齐 + 回复质量子维度用）', 3),
        ('query', '用户提问', '用户提问', 'text', 'input',
         None, None, None, False,
         False, None, '用户提问文本（回复质量评分参考）', 4),
        # 主维度不配 output 参数
    ],
    'param_mappings': [
        ('device', 'output', 'user_wav', 'user_wav', 'none'),
        ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
        ('case_config', 'output', 'audios', 'played_audios', 'none'),
        ('device', 'output', 'query', 'query', 'none'),
    ],
}

# ============================================================
# 子维度定义：turn_evaluation（只配 output 参数）
# ============================================================
# params 元组顺序：
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order, pass_threshold)
# pass_threshold 可选，pass_rate 策略时用，默认 None

SUB_DIMENSIONS = [
    {
        'task_type_code': 'turn_evaluation',  # 子维度独立类型，平台提取后注入 sub_tasks
        'name': '逐轮三分类评估',
        'keywords': 'turn_evaluation,三分类,误解管,接管,未接管,接管时延,回复质量',
        'description': '子维度：逐轮三分类（误解管/接管/未接管）+ 接管时延 + 回复质量。output field_path 映射 turn_eval JSON 响应各字段。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '',
        'statistic_method': 'pass_rate',
        'params': [
            # ─── 主评分：误解管数（pass when 0，即无误解管时通过）───
            ('false_takeover_count', '误解管数', '误解管数', 'number', 'output',
             'turn_classification.false_takeover_count', 'pass_eq', 'main', True,
             False, None, '误解管轮次数（0=无误解管=通过）', 10, 0),
            # ─── 三分类汇总 ───
            ('tc_summary', '三分类汇总', '三分类汇总', 'text', 'output',
             'turn_classification.summary', None, 'aux', True,
             False, None, '三分类自然语言汇总（如：正常接管N，未接管M，误解管K）', 11),
            ('normal_takeover_count', '正常接管数', '正常接管数', 'number', 'output',
             'turn_classification.normal_takeover_count', None, 'aux', True,
             False, None, '正常接管轮次数', 12),
            ('no_takeover_count', '未接管数', '未接管数', 'number', 'output',
             'turn_classification.no_takeover_count', None, 'aux', True,
             False, None, '未接管轮次数', 13),
            ('total_turns', '总轮数', '总轮数', 'number', 'output',
             'turn_classification.total_turns', None, 'aux', True,
             False, None, '总轮次数', 14),
            ('tc_turns', '逐轮详情', '逐轮详情', 'json', 'output',
             'turn_classification.turns', None, 'aux', True,
             False, None, '逐轮分类详情（含分类/时延/质量/时间戳）', 15),
            # ─── 兼容旧字段（取最后一轮结果）───
            ('te_tor', '接话率(末轮)', '接话率(末轮)', 'number', 'output',
             'tor.tor', None, 'aux', True,
             False, None, '兼容字段：末轮接话率(0=没接话, 1=接话)', 20),
            ('te_false_takeover', '误接管率(末轮)', '误接管率(末轮)', 'number', 'output',
             'false_takeover.tor', None, 'aux', True,
             False, None, '兼容字段：末轮误接管率(0=未抢话, 1=抢话)', 21),
            ('te_false_takeover_reason', '误接管理由(末轮)', '误接管理由(末轮)', 'text', 'output',
             'false_takeover.reason', None, 'aux', True,
             False, None, '兼容字段：末轮误接管判定理由', 22),
            ('te_takeover_latency_ms', '接管时延(末轮)', '接管时延(末轮)', 'number', 'output',
             'takeover_latency.takeover_latency_ms', None, 'aux', True,
             False, None, '兼容字段：末轮接管时延(毫秒)，正=AI后回复，负=抢话', 23),
            ('te_reply_quality_score', '回复质量得分(末轮)', '回复质量得分(末轮)', 'number', 'output',
             'reply_quality.score', None, 'aux', True,
             False, None, '兼容字段：末轮回复质量评分(1-5分)', 24),
            # ─── 交互内容 ───
            ('te_interaction', '交互内容', '完整交互文字(带时间戳)', 'text', 'output',
             'interaction_text', None, 'aux', True,
             False, None, '用例完整交互文字，query/answer 按时间排序，含 [m:ss; m:ss] 时间戳', 30),
        ],
    },
]


# ============================================================
# 辅助函数（与 seed_xiaoyi_dimensions.py 一致）
# ============================================================

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
                'played_audios': '{{played_audios}}',
                'background_noise': '{{background_noise}}',
                'interferers': '{{interferers}}',
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


def seed_turn_eval():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 1: 注册/更新 turn_eval 主维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 1: 注册 turn_eval 主维度")
        print(f"{'=' * 60}")
        main_id = _upsert_dimension(conn, MAIN_DIMENSION, dimension_type='main', parent_id=None)
        print(f"  主维度 id = {main_id}")
        _upsert_params(conn, main_id, MAIN_DIMENSION)
        _upsert_relation(conn, main_id)
        _upsert_param_mappings(conn, main_id, MAIN_DIMENSION)

        # ============================================================
        # Step 2: 注册子维度 turn_evaluation
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 2: 注册子维度（parent_dimension_id={main_id}）")
        print(f"{'=' * 60}")
        for sub_def in SUB_DIMENSIONS:
            print(f"\n  -- 子维度: {sub_def['name']} --")
            sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
            print(f"  子维度 id = {sub_id}")
            _upsert_params(conn, sub_id, sub_def)
            _upsert_relation(conn, sub_id)
            # 子维度不配 param_mappings，共用主维度的 mappings

        print(f"\n{'=' * 60}")
        print(f"  turn_eval 维度种子数据注册完成")
        print(f"  主维度 turn_eval id={main_id}（无 output）")
        print(f"  子维度 turn_evaluation:")
        print(f"    - false_takeover_count  → turn_classification.false_takeover_count (main)")
        print(f"    - tc_summary            → turn_classification.summary")
        print(f"    - normal_takeover_count → turn_classification.normal_takeover_count")
        print(f"    - no_takeover_count     → turn_classification.no_takeover_count")
        print(f"    - total_turns           → turn_classification.total_turns")
        print(f"    - tc_turns              → turn_classification.turns")
        print(f"    - te_tor                → tor.tor")
        print(f"    - te_false_takeover     → false_takeover.tor")
        print(f"    - te_takeover_latency   → takeover_latency.takeover_latency_ms")
        print(f"    - te_reply_quality      → reply_quality.score")
        print(f"    - te_interaction        → interaction_text")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("逐轮话轮评估（turn_eval）维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print("1. 注册/更新 turn_eval 主维度（dimension_type=main，无 output）")
    print("   配置 input params + api_settings + param_mappings")
    print("2. 注册/更新 turn_evaluation 子维度（dimension_type=sub）：")
    print("   - 主评分: 误解管数 → turn_classification.false_takeover_count (pass when 0)")
    print("   - 辅助: 三分类汇总/逐轮详情/兼容旧字段/交互内容")
    print("3. 注册 voice_llm → 主维度 + 子维度的关联")
    print()
    print("执行链路：用例选 turn_evaluation 子维度 → 继承父维度 task_type_code/api 配置")
    print("→ 按 (endpoint_url, task_type_code) 分到同一组 → 调一次 eval_server")
    print("→ TurnEvalCalculator 逐轮三分类 + 时延 + 质量 → 按 output field_path 分发提取")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_turn_eval()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
