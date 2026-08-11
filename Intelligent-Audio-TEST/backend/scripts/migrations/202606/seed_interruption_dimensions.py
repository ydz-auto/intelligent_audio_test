# -*- coding: utf-8 -*-
"""
打断评估维度种子数据

功能：
1. 注册一个评估维度（dimension）：
   - interruption_metrics (打断指标：用户打断小艺时衡量停得下、恢复得来)
2. 注册该维度的输入/输出参数（evaluation_dimension_params）
3. 注册 voice_llm 算法与该维度的关联（algorithm_dimension_relations）
4. 注册 voice_llm → 该维度的参数映射（param_mappings）

对应 eval_server 服务：
   - eval_server/app/services/xiaoyi_metrics/interruption.py
   - 入口：calculate_interruption_metrics(task_params)
   - task_type：interruption_metrics

输入（由调用方直接传两路已对齐的 ASR 词级时间戳，不内部调 ASR）：
   - user_asr  : 用户提问/打断 ASR（chunks 或 {text, chunks}）
   - model_asr : 模型恢复 ASR（同上，与 user_asr 等长、同一时间轴）

输出子指标：
   - 打断成功率    (interruption_success_rate)
   - 打断检查时延  (avg_stop_latency_s)
   - 打断恢复时延  (avg_recovery_latency_s)
   - 停下率/恢复率/双方同时说话时长/静默时长/逐事件详情

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

# ============================================================
# 维度定义
# ============================================================
# interruption_metrics 维度：两路 ASR（用户 + 模型恢复）直接算三项打断指标
# 子指标: 打断成功率 / 打断检查时延 / 打断恢复时延
DIMENSIONS = [
    {
        'task_type_code': 'interruption_metrics',
        'name': '打断指标',
        'keywords': '打断,interruption,stop,recovery,打断成功率,打断检查时延,打断恢复时延,barge-in',
        'description': (
            '用户打断小艺时衡量停得下、恢复得来。'
            '入参为两路已对齐的 ASR 词级时间戳（user_asr + model_asr），'
            '计算打断成功率、打断检查时延、打断恢复时延。'
            '参考 Full-Duplex-Bench v1.5 get_timing.py 与 v1.0 eval_user_interruption.py'
        ),
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 3,
        'weight': 1,
        'estimated_exec_time': 10,  # 纯计算，不调 ASR
        'score_unit': '',
        'statistic_method': 'average',
        'params': [
            # ─── 输入参数 ───
            ('user_asr', '用户打断ASR', '用户提问/打断 ASR', 'json', 'input',
             None, None, None, True,
             False, None, '用户打断语音的 ASR 词级时间戳(chunks 或 {text, chunks})', 5),
            ('model_asr', '模型恢复ASR', '模型恢复 ASR', 'json', 'input',
             None, None, None, True,
             False, None, '模型恢复语音的 ASR 词级时间戳(与 user_asr 等长、同一时间轴)', 6),
            ('seg_merge_gap_s', '词合并间隙', '词合并为段的间隙阈值(秒)', 'number', 'input',
             None, None, None, False,
             False, '0.3', '相邻词时间戳间隙小于该值则合并为同一段(秒)', 11),

            # ─── 输入参数: 大模型评估（可选）───
            ('rounds', '多轮文本', '多轮对话文本结构(用于大模型评估)', 'json', 'input',
             None, None, None, False,
             False, None,
             '多轮文本结构 [{query, answer, is_return_to_topic}]，'
             '与 user_asr/model_asr 解耦；enable_llm_eval=True 时才使用', 12),
            ('enable_llm_eval', '启用LLM评估', '是否启用大模型评估', 'boolean', 'input',
             None, None, None, False,
             False, 'false', '为 true 时对每轮打断后回复与回到原话题行为做 LLM 评估'
             '(需配置 LLM_JUDGE_API_KEY)', 13),
            ('llm_model', 'LLM模型', 'LLM 模型名称(覆盖默认)', 'text', 'input',
             None, None, None, False,
             False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认', 14),
            ('original_topic', '原始话题', '原始话题文本', 'text', 'input',
             None, None, None, False,
             False, None, '原始话题文本，供回到原话题行为判断/打分使用', 15),

            # ─── 输出参数: 打断成功率（主分）───
            ('interruption_success_rate', '打断成功率', '打断成功率', 'number', 'output',
             'interruption_success_rate', 'value', 'main', True,
             False, None, '打断成功率(0~1，让出且恢复 / 有效打断事件)', 60),
            ('interruption_stop_rate', '让出率', '让出率', 'number', 'output',
             'stop_rate', None, 'aux', False,
             False, None, '让出率: 模型没说穿整个打断区间的事件占比', 61),
            ('interruption_resume_rate', '恢复率', '恢复率', 'number', 'output',
             'resume_rate', None, 'aux', False,
             False, None, '停下后恢复的打断事件占比', 62),
            ('interruption_n_events', '打断事件数', '打断事件数', 'number', 'output',
             'n_events', None, 'aux', False,
             False, None, '有效打断事件数(模型当时在说话)', 63),
            ('interruption_n_user_segments', '用户段数', '用户段数', 'number', 'output',
             'n_user_segments', None, 'aux', False,
             False, None, '用户语音段总数', 64),
            ('interruption_n_recovery_only', '退化事件数', '退化事件数', 'number', 'output',
             'n_recovery_only', None, 'aux', False,
             False, None, '只算到恢复时延的事件数(model_asr 可能只含恢复段)', 65),
            ('interruption_n_no_model_speech', '无模型语音段数', '无模型语音段数', 'number', 'output',
             'n_no_model_speech', None, 'aux', False,
             False, None, '模型全程未说话的用户段数', 66),

            # ─── 输出参数: 打断检查时延 ───
            ('avg_stop_latency_s', '打断检查时延', '打断检查时延(秒)', 'number', 'output',
             'avg_stop_latency_s', None, 'aux', False,
             False, None, '平均打断检查时延(秒): 用户开始打断 → 模型停下', 70),
            # ─── 输出参数: 打断恢复时延 ───
            ('avg_recovery_latency_s', '打断恢复时延', '打断恢复时延(秒)', 'number', 'output',
             'avg_recovery_latency_s', None, 'aux', False,
             False, None, '平均打断恢复时延(秒): 用户说完 → 模型重新开口', 80),
            ('avg_overlap_s', '同时说话时长', '双方同时说话时长(秒)', 'number', 'output',
             'avg_overlap_s', None, 'aux', False,
             False, None, '平均双方同时说话时长(秒，越短越好)', 81),
            ('avg_silence_gap_s', '静默时长', '静默时长(秒)', 'number', 'output',
             'avg_silence_gap_s', None, 'aux', False,
             False, None, '平均模型停下到恢复的静默时长(秒)', 82),
            ('interruption_per_event', '逐事件详情', '逐事件详情', 'json', 'output',
             'per_event', None, 'aux', False,
             False, None, '每个用户打断段的结果列表', 90),
            ('interruption_message', '打断指标说明', '打断指标说明', 'text', 'output',
             'message', None, 'aux', False,
             False, None, '打断指标错误/成功说明', 99),

            # ─── 输出参数: 大模型评估（可选，enable_llm_eval=True 时才有值）───
            ('llm_recovery_avg_coherence', '回复连贯性均分', '打断后回复连贯性均分', 'number', 'output',
             'llm_recovery_avg_coherence', None, 'aux', False,
             False, None, '每轮打断后回复连贯性打分均值(1-5)', 100),
            ('llm_recovery_avg_relevance', '回复相关性均分', '打断后回复相关性均分', 'number', 'output',
             'llm_recovery_avg_relevance', None, 'aux', False,
             False, None, '每轮打断后回复相关性打分均值(1-5)', 101),
            ('llm_recovery_avg_adaptability', '回复适应性均分', '打断后回复适应性均分', 'number', 'output',
             'llm_recovery_avg_adaptability', None, 'aux', False,
             False, None, '每轮打断后回复适应性打分均值(1-5)', 102),
            ('llm_return_behavior_summary', '回原话题行为分布', '回到原话题行为分类计数', 'json', 'output',
             'llm_return_behavior_summary', None, 'aux', False,
             False, None, '回到原话题后模型回复行为计数{回应/恢复/询问/无关恢复/沉默}', 103),
            ('llm_return_avg_coherence', '回原话题连贯性均分', '回到原话题回复连贯性均分', 'number', 'output',
             'llm_return_avg_coherence', None, 'aux', False,
             False, None, '回到原话题后回复连贯性打分均值(1-5)', 104),
            ('llm_return_avg_relevance', '回原话题相关性均分', '回到原话题回复相关性均分', 'number', 'output',
             'llm_return_avg_relevance', None, 'aux', False,
             False, None, '回到原话题后回复相关性打分均值(1-5)', 105),
            ('llm_return_avg_adaptability', '回原话题适应性均分', '回到原话题回复适应性均分', 'number', 'output',
             'llm_return_avg_adaptability', None, 'aux', False,
             False, None, '回到原话题后回复适应性打分均值(1-5)', 106),
            ('llm_recovery_per_round', '回复逐轮打分', '打断后回复逐轮打分', 'json', 'output',
             'llm_recovery_per_round', None, 'aux', False,
             False, None, '每轮打断后回复的打分明细列表', 110),
            ('llm_return_per_round', '回原话题逐轮行为', '回到原话题逐轮行为', 'json', 'output',
             'llm_return_per_round', None, 'aux', False,
             False, None, '回到原话题轮的行为判断明细列表', 111),
            ('llm_return_scores_per_round', '回原话题逐轮打分', '回到原话题逐轮打分', 'json', 'output',
             'llm_return_scores_per_round', None, 'aux', False,
             False, None, '回到原话题轮的回复打分明细列表', 112),
            ('llm_eval', 'LLM评估块', 'LLM评估完整结果', 'json', 'output',
             'llm_eval', None, 'aux', False,
             False, None, 'LLM 评估完整结果(含 enabled/message/model 及明细)', 113),
        ],
        # user_asr / model_asr 由调用方（主服务/用例）直接提供，来源待主服务侧确认
        # 这里给出默认映射：reference 用例输出 → 入参，可按主服务实际来源调整
        # rounds（多轮文本结构，含 is_return_to_topic 打标）同样来自用例 reference 输出
        # is_return_to_topic 走 reference_params 体系（seed_voice_llm 注册，从 segments[].is_return_to_topic 派生），
        # 经 source='reference' 映射：_build_rounds_list 按轮读入 rounds_list[i].is_return_to_topic
        # original_topic（用例级纯文本，无标注来源）不走 reference，由 evaluate_case 从 config 注入 kwargs → payload
        'param_mappings': [
            ('reference', 'output', 'user_asr', 'user_asr', 'none'),
            ('reference', 'output', 'model_asr', 'model_asr', 'none'),
            ('reference', 'output', 'rounds', 'rounds', 'none'),
            ('reference', 'output', 'is_return_to_topic', 'is_return_to_topic', 'none'),
        ],
    },
]


def seed_interruption_dimensions():
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
                    'user_asr': '{{user_asr}}',
                    'model_asr': '{{model_asr}}',
                    'seg_merge_gap_s': '{{seg_merge_gap_s}}',
                    'rounds': '{{rounds}}',
                    'enable_llm_eval': '{{enable_llm_eval}}',
                    'llm_model': '{{llm_model}}',
                    'original_topic': '{{original_topic}}',
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
                    "  rule = :rule, "
                    "  updated_at = NOW() "
                    "WHERE id = :did"
                ), {
                    'name': dim_def['name'], 'kw': dim_def['keywords'],
                    'desc': dim_def['description'], 'type': dim_def['type'],
                    'rt': dim_def['result_type'], 'rmin': dim_def['result_min'],
                    'rmax': dim_def['result_max'], 'dp': dim_def['decimal_places'],
                    'w': dim_def['weight'], 'et': dim_def['estimated_exec_time'],
                    'su': dim_def['score_unit'], 'sm': dim_def['statistic_method'],
                    'apis': api_settings, 'rule': rule, 'did': dim_id,
                })
            else:
                result = conn.execute(text(
                    "INSERT INTO dimensions "
                    "  (name, keywords, dimension_type, task_type_code, description, "
                    "   type, result_type, result_min, result_max, decimal_places, "
                    "   weight, estimated_exec_time, rule, api_settings, status, "
                    "   api_status, score_unit, statistic_method, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:name, :kw, 'main', :tc, :desc, "
                    "   :type, :rt, :rmin, :rmax, :dp, "
                    "   :w, :et, :rule, :apis, TRUE, "
                    "   'online', :su, :sm, "
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
                 required, default_value, help_text, ui_order) = dp

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
                        "  default_value = :dv, help_text = :ht, ui_order = :uo, "
                        "  updated_at = NOW() "
                        "WHERE id = :id"
                    ), {
                        'pn': param_name, 'lb': label, 'ft': field_type,
                        'fp': field_path, 'ar': agg_role, 'or': output_role,
                        'vir': visible_in_report, 'req': required,
                        'dv': default_value, 'ht': help_text, 'uo': ui_order,
                        'id': existing[0],
                    })
                    print(f"  - {param_code} ({param_direction}) 已存在，已更新")
                    param_skipped += 1
                else:
                    conn.execute(text(
                        "INSERT INTO evaluation_dimension_params "
                        "  (dimension_id, param_code, param_name, label, field_type, "
                        "   param_direction, field_path, agg_role, output_role, "
                        "   visible_in_report, required, default_value, help_text, "
                        "   ui_order, deleted, created_at, updated_at) "
                        "VALUES "
                        "  (:did, :pc, :pn, :lb, :ft, "
                        "   :dir, :fp, :ar, :or, "
                        "   :vir, :req, :dv, :ht, "
                        "   :uo, FALSE, NOW(), NOW())"
                    ), {
                        'did': dim_id, 'pc': param_code, 'pn': param_name,
                        'lb': label, 'ft': field_type, 'dir': param_direction,
                        'fp': field_path, 'ar': agg_role, 'or': output_role,
                        'vir': visible_in_report, 'req': required,
                        'dv': default_value, 'ht': help_text, 'uo': ui_order,
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
                        "  updated_at = NOW() "
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
        print("  打断评估维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("打断评估维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. interruption_metrics 维度 — 打断指标（用户打断小艺）")
    print("   入参: user_asr(用户打断ASR), model_asr(模型恢复ASR), seg_merge_gap_s")
    print()
    print("   子指标1: 打断成功率 (interruption_success_rate)")
    print("   子指标2: 打断检查时延 (avg_stop_latency_s)")
    print("   子指标3: 打断恢复时延 (avg_recovery_latency_s)")
    print()
    print("   两路 ASR 由调用方直接传入（不内部调 ASR），需等长、同一时间轴")
    print()
    print("同时注册：")
    print("- voice_llm → interruption_metrics 关联(algorithm_dimension_relations)")
    print("- voice_llm → interruption_metrics 参数映射(param_mappings)")
    print()
    try:
        seed_interruption_dimensions()
    except Exception as e:
        print(f"\n❌ 注册失败: {e}")
        sys.exit(1)
