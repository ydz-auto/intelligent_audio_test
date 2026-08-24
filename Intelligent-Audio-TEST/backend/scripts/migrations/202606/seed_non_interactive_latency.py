# -*- coding: utf-8 -*-
"""
非交互意图时延维度种子数据

功能：
1. 注册一个评估维度（dimension）：
   - non_interactive_latency (用户在模型回复期间说话的时延)
2. 注册该维度的输入/输出参数（evaluation_dimension_params）
3. 注册 voice_llm 算法与该维度的关联（algorithm_dimension_relations）
4. 注册 voice_llm → 该维度的参数映射（param_mappings）

对应 eval_server 服务：
   - eval_server/app/services/xiaoyi_metrics/rejection_scene_awareness/non_interactive_latency.py
   - 入口：compute_non_interactive_latency(user_wav, ai_wav, ...)
   - task_type：non_interactive_latency

输入（eval_server 内部调 ASR 服务转词级时间戳）：
   - user_wav  : 用户语音 wav 路径
   - ai_wav    : 模型语音 wav 路径

输出子指标：
   - 停止时延      (stop_latency_s)       用户开始讲话 → 模型停止回复
   - 恢复时延      (recovery_latency_s)   用户讲完 → 模型开始回复
   - 静默时长      (silence_gap_s)        模型第一次回复结束 → 再次回复
   - 重叠时长      (overlap_s)            用户与模型同时说话的时长

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_non_interactive_latency

或直接：
    python backend/scripts/migrations/202606/seed_non_interactive_latency.py

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
DIMENSIONS = [
    {
        'task_type_code': 'non_interactive_latency',
        'name': '非交互意图时延',
        'keywords': 'non_interactive,非交互,意图,时延,stop_latency,recovery_latency,停止时延,恢复时延',
        'description': (
            '用户在模型回复期间说话（非交互意图），衡量模型停得下、恢复得来。'
            '入参为两路 wav（user_wav + ai_wav），eval_server 内部调 ASR 服务转词级时间戳，'
            '计算停止时延（用户开始讲话→模型停止）和恢复时延（用户讲完→模型开始回复）。'
        ),
        'type': 'auto',
        'result_type': 1,
        'result_min': 0.0,
        'result_max': None,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 10,
        'score_unit': 's',
        'statistic_method': 'average',
        'params': [
            # ─── 输入参数 ───
            ('user_wav', '用户通道音频', '用户通道音频', 'audio', 'input',
             None, None, None, True,
             False, None, '用户通道 wav 路径（eval_server 内部调 ASR 服务转词级时间戳）', 5),
            ('ai_wav', 'AI回复通道音频', 'AI回复通道音频', 'audio', 'input',
             None, None, None, True,
             False, None, 'AI 回复通道 wav 路径（eval_server 内部调 ASR 服务转词级时间戳）', 6),
            ('seg_merge_gap_s', '词合并间隙', '词合并为段的间隙阈值(秒)', 'number', 'input',
             None, None, None, False,
             False, '0.7', '相邻词时间戳间隙小于该值则合并为同一段(秒)', 11),
            ('target_segment_index', '目标段索引', '目标用户段索引(0-based)', 'number', 'input',
             None, None, None, False,
             False, '1', '目标用户段索引(默认 1=第 2 段，即模型回复期间用户说话段)', 12),

            # ─── 输出参数: 停止时延（主分）───
            ('stop_latency_s', '停止时延', '停止时延(秒)', 'number', 'output',
             'stop_latency_s', 'value', 'main', True,
             False, None, '用户开始讲话→模型停止回复(秒)', 60),
            # ─── 输出参数: 恢复时延 ───
            ('recovery_latency_s', '恢复时延', '恢复时延(秒)', 'number', 'output',
             'recovery_latency_s', None, 'aux', True,
             False, None, '用户讲完→模型开始回复(秒)', 70),
            # ─── 输出参数: 静默时长 ───
            ('silence_gap_s', '静默时长', '静默时长(秒)', 'number', 'output',
             'silence_gap_s', None, 'aux', True,
             False, None, '模型第一次回复结束→再次回复的静默(秒)', 80),
            # ─── 输出参数: 重叠时长 ───
            ('overlap_s', '重叠时长', '双方同时说话时长(秒)', 'number', 'output',
             'overlap_s', None, 'aux', True,
             False, None, '用户与模型同时说话的时长(秒，越短越好)', 81),
            # ─── 输出参数: 段信息 ───
            ('user_segment', '用户段', '目标用户段', 'json', 'output',
             'user_segment', None, 'aux', True,
             False, None, '目标用户段 [start, end, text]', 90),
            ('model_active_segment', '模型回复段', '被打断的模型回复段', 'json', 'output',
             'model_active_segment', None, 'aux', True,
             False, None, '被打断时模型正在说的段 [start, end, text]', 91),
            ('model_recovery_segment', '模型恢复段', '模型恢复回复段', 'json', 'output',
             'model_recovery_segment', None, 'aux', True,
             False, None, '模型恢复回复段 [start, end, text]', 92),
            # ─── 输出参数: 统计 ───
            ('n_user_segments', '用户段数', '用户语音段总数', 'number', 'output',
             'n_user_segments', None, 'aux', True,
             False, None, '用户语音段总数', 93),
            ('n_model_segments', '模型段数', '模型语音段总数', 'number', 'output',
             'n_model_segments', None, 'aux', True,
             False, None, '模型语音段总数', 94),
            ('nil_message', '非交互意图时延说明', '非交互意图时延说明', 'text', 'output',
             'message', None, 'aux', True,
             False, None, '非交互意图时延错误/成功说明', 99),
        ],
        'param_mappings': [
            ('device', 'output', 'user_wav', 'user_wav', 'none'),
            ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
        ],
    },
]


def seed_non_interactive_latency():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        for dim_def in DIMENSIONS:
            task_code = dim_def['task_type_code']
            print(f"\n{'=' * 60}")
            print(f"  处理维度: {task_code} ({dim_def['name']})")
            print(f"{'=' * 60}")

            # ============================================================
            # Step 1: 注册维度
            # ============================================================
            print(f"\n--- Step 1: 注册 {task_code} 维度 (dimensions) ---")

            existing_dim = conn.execute(text(
                "SELECT id FROM dimensions "
                "WHERE task_type_code = :tc AND deleted = FALSE"
            ), {'tc': task_code}).fetchone()

            api_settings = json.dumps({
                'method': 'POST',
                'headers': {},
                'body_template': {
                    'seg_merge_gap_s': '{{seg_merge_gap_s}}',
                    'target_segment_index': '{{target_segment_index}}',
                    'rounds': [
                        {
                            'user_wav': '{{user_wav}}',
                            'ai_wav': '{{ai_wav}}',
                        }
                    ],
                },
                'timeout': 30000
            }, ensure_ascii=False)
            rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

            if existing_dim:
                dim_id = existing_dim[0]
                print(f"  - {task_code} 维度已存在 (id={dim_id})，更新描述")
                conn.execute(text(
                    "UPDATE dimensions SET "
                    "  name = :name, keywords = :kw, description = :desc, "
                    "  type = :type, result_type = :rt, result_min = :rmin, "
                    "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                    "  estimated_exec_time = :et, score_unit = :su, "
                    "  statistic_method = :sm, api_settings = :apis, "
                    "  rule = :rule, api_url = :api_url, "
                    "  updated_at = NOW() "
                    "WHERE id = :did"
                ), {
                    'name': dim_def['name'], 'kw': dim_def['keywords'],
                    'desc': dim_def['description'], 'type': dim_def['type'],
                    'rt': dim_def['result_type'], 'rmin': dim_def['result_min'],
                    'rmax': dim_def['result_max'], 'dp': dim_def['decimal_places'],
                    'w': dim_def['weight'], 'et': dim_def['estimated_exec_time'],
                    'su': dim_def['score_unit'], 'sm': dim_def['statistic_method'],
                    'apis': api_settings, 'rule': rule, 'api_url': API_URL,
                    'did': dim_id,
                })
            else:
                result = conn.execute(text(
                    "INSERT INTO dimensions "
                    "  (name, keywords, dimension_type, task_type_code, description, "
                    "   type, result_type, result_min, result_max, decimal_places, "
                    "   weight, estimated_exec_time, rule, api_settings, status, "
                    "   api_status, score_unit, statistic_method, api_url, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:name, :kw, 'main', :tc, :desc, "
                    "   :type, :rt, :rmin, :rmax, :dp, "
                    "   :w, :et, :rule, :apis, TRUE, "
                    "   'online', :su, :sm, :api_url, "
                    "   FALSE, NOW(), NOW()) "
                    "RETURNING id"
                ), {
                    'name': dim_def['name'], 'kw': dim_def['keywords'],
                    'tc': task_code, 'desc': dim_def['description'],
                    'type': dim_def['type'], 'rt': dim_def['result_type'],
                    'rmin': dim_def['result_min'], 'rmax': dim_def['result_max'],
                    'dp': dim_def['decimal_places'], 'w': dim_def['weight'],
                    'et': dim_def['estimated_exec_time'],
                    'rule': rule, 'apis': api_settings,
                    'su': dim_def['score_unit'], 'sm': dim_def['statistic_method'],
                    'api_url': API_URL,
                })
                dim_id = result.fetchone()[0]
                print(f"  + {task_code} 维度已插入 (id={dim_id})")

            # ============================================================
            # Step 2: 注册输入/输出参数
            # ============================================================
            print(f"\n--- Step 2: 注册 {task_code} 参数 (evaluation_dimension_params) ---")

            param_inserted = 0
            param_skipped = 0
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
                    print(f"  - {param_code} ({param_direction}) 已存在，已更新")
                    param_skipped += 1
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
                    print(f"  + {param_code} ({field_type}, {param_direction})")
                    param_inserted += 1

            print(f"  插入 {param_inserted} 条，跳过/更新 {param_skipped} 条")

            # ============================================================
            # Step 3: 注册 voice_llm → 维度关联
            # ============================================================
            print(f"\n--- Step 3: 注册 voice_llm → {task_code} 关联 ---")

            existing_rel = conn.execute(text(
                "SELECT id FROM algorithm_dimension_relations "
                "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
            ), {'did': dim_id}).fetchone()

            if existing_rel:
                print(f"  - 关联已存在 (voice_llm → {task_code} id={dim_id})，跳过")
            else:
                conn.execute(text(
                    "INSERT INTO algorithm_dimension_relations "
                    "  (algorithm_type, dimension_id, is_default, weight, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
                ), {'did': dim_id})
                print(f"  + 关联已插入 (voice_llm → {task_code} id={dim_id})")

            # ============================================================
            # Step 4: 注册参数映射
            # ============================================================
            print(f"\n--- Step 4: 注册 voice_llm → {task_code} 参数映射 ---")

            map_inserted = 0
            map_skipped = 0
            for m in dim_def['param_mappings']:
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
                    ), {
                        'tp': target_param, 'tt': transform_type,
                        'id': existing[0],
                    })
                    print(f"  - {source}.{source_param} → {target_param} 已存在，已更新")
                    map_skipped += 1
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
                    print(f"  + {source}.{source_param} → {target_param}")
                    map_inserted += 1

            print(f"  插入 {map_inserted} 条，跳过/更新 {map_skipped} 条")

        print(f"\n{'=' * 60}")
        print("  非交互意图时延维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("非交互意图时延维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. non_interactive_latency 维度 — 非交互意图时延")
    print("   入参: user_wav(用户音频), ai_wav(模型音频), seg_merge_gap_s, target_segment_index")
    print()
    print("   主分: 停止时延 (stop_latency_s)")
    print("   辅助: 恢复时延 / 静默时长 / 重叠时长 / 段信息 / 段数")
    print()
    print("   两路 wav 由 eval_server 内部调 ASR 服务转词级时间戳")
    print()
    print("脚本可重复执行（幂等）")
    print()

    if '--yes' not in sys.argv:
        confirm = input("是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            sys.exit(0)

    try:
        seed_non_interactive_latency()
    except Exception as e:
        print(f"\n注册失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
