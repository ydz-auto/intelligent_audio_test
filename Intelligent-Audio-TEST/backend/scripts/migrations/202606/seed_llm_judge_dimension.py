# -*- coding: utf-8 -*-
"""
llm_judge 评估维度种子数据

功能：
1. 注册 llm_judge 评估维度（dimensions）
2. 注册 llm_judge 维度的输入参数（evaluation_dimension_params）
3. 注册 voice_llm 算法与 llm_judge 维度的关联（algorithm_dimension_relations）

llm_judge 输入参数：
- record_file: 录屏文件路径（对应 device 输出 record_path）
- correct_answer: 参考答案（对应 reference correct_answer）
- query: 用户提问（对应 reference query）
- question: 设备识别的用户提问（对应 device question）
- answer: 设备回答（对应 device answer）
- prompt: 评估提示词（映射到 eval_server 的 prompt）

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_llm_judge_dimension

或直接：
    python backend/scripts/migrations/202606/seed_llm_judge_dimension.py

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


def seed_llm_judge_dimension():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 1: 注册 llm_judge 评估维度
        # ============================================================
        print("=== Step 1: 注册 llm_judge 评估维度 (dimensions) ===")

        existing_dim = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE task_type_code = 'llm_judge' AND deleted = FALSE"
        )).fetchone()

        if existing_dim:
            dim_id = existing_dim[0]
            print(f"  - llm_judge 维度已存在 (id={dim_id})，跳过")

            # 更新已有维度的 api_settings，确保 body_template 包含 prompt 字段映射
            default_api_settings = json.dumps({
                'method': 'POST',
                'headers': {'content_type': 'application/json'},
                'body_template': {
                    'model': '{{model}}',
                    'prompt': '{{prompt}}',
                    'rounds': [
                        {
                            'answer': '{{answer}}',
                            'correct_answer': '{{correct_answer}}',
                            'question': '{{question}}',
                            'query': '{{query}}',
                            'record_file': '{{record_file}}',
                            'prompt': '{{prompt}}'
                        }
                    ]
                },
                'timeout': 30000
            }, ensure_ascii=False)
            default_rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)
            conn.execute(text(
                "UPDATE dimensions SET api_settings = :settings, rule = :rule, "
                "  api_url = :api_url, updated_at = NOW() "
                "WHERE id = :did"
            ), {'settings': default_api_settings, 'rule': default_rule,
                'api_url': API_URL, 'did': dim_id})
            print(f"  + 已更新 llm_judge 维度 api_settings/rule/api_url (body_template 含 rounds 结构)")
        else:
            # 默认 body_template：rounds 外放维度级配置，rounds 内放数据字段
            default_api_settings = json.dumps({
                'method': 'POST',
                'headers': {'content_type': 'application/json'},
                'body_template': {
                    'model': '{{model}}',
                    'prompt': '{{prompt}}',
                    'rounds': [
                        {
                            'answer': '{{answer}}',
                            'correct_answer': '{{correct_answer}}',
                            'question': '{{question}}',
                            'query': '{{query}}',
                            'record_file': '{{record_file}}',
                            'prompt': '{{prompt}}'
                        }
                    ]
                },
                'timeout': 30000
            }, ensure_ascii=False)
            default_rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, api_url, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  ('LLM语义评分', 'llm_judge,语义,评分', 'main', 'llm_judge', "
                "   '使用大语言模型对对话输出进行语义级评分，评估准确性、流畅度、相关性', "
                "   'auto', 1, 0.0, 5.0, 2, "
                "   1, 120, "
                "   :rule, :api_settings, TRUE, "
                "   'online', '分', 'average', :api_url, "
                "   FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {
                'rule': default_rule,
                'api_settings': default_api_settings,
                'api_url': API_URL
            })
            dim_id = result.fetchone()[0]
            print(f"  + llm_judge 维度已插入 (id={dim_id})")

        # ============================================================
        # Step 2: 注册 llm_judge 维度的输入参数
        # ============================================================
        print("\n=== Step 2: 注册 llm_judge 输入参数 (evaluation_dimension_params) ===")

        dim_params = [
            # (param_code, param_name, label, field_type, param_direction,
            #  field_path, agg_role, output_role, visible_in_report,
            #  required, default_value, help_text, ui_order)
            ('record_file', '录屏文件', '录屏文件', 'text', 'input',
             None, None, None, True,
             False, None, '录屏文件路径', 10),
            ('correct_answer', '参考答案', '参考答案', 'text', 'input',
             None, None, None, True,
             False, None, 'LLM Judge 评估的标准答案', 20),
            ('query', '用户提问', '用户提问', 'text', 'input',
             None, None, None, True,
             False, None, '用户提问文本', 30),
            ('question', '设备识别提问', '设备识别提问', 'text', 'input',
             None, None, None, True,
             False, None, '设备识别到的用户提问', 40),
            ('answer', '设备回答', '设备回答', 'text', 'input',
             None, None, None, True,
             False, None, '设备/被测系统的回答文本', 50),
            ('prompt', '评估提示词', '评估提示词', 'text', 'input',
             None, None, None, True,
             False, None, 'LLM Judge 评估提示词模板，可含 {hypothesis} 和 {reference} 占位符', 55),
            # 输出字段：LLM 评分结果
            ('llm_judge_score', 'LLM评分', 'LLM评分', 'number', 'output',
             'llm_judge_score', 'value', 'main', True,
             False, None, 'LLM Judge 综合评分(0-5)', 60),
            ('criteria_scores', '维度评分', '维度评分', 'json', 'output',
             'criteria_scores', None, 'aux', True,
             False, None, '各评分维度详情(accuracy/fluency/relevance)', 61),
            ('reasoning', '评分理由', '评分理由', 'text', 'output',
             'reasoning', None, 'aux', False,
             False, None, 'LLM 评分理由', 62),
            ('llm_judge_enabled', '是否启用', 'LLM评估是否启用', 'boolean', 'output',
             'enabled', None, 'aux', True,
             False, None, 'LLM 评估是否正常执行(True/False)', 63),
            ('llm_judge_model', 'LLM模型', '使用的LLM模型', 'text', 'output',
             'model', None, 'aux', True,
             False, None, '本次评估使用的 LLM 模型名', 64),
        ]

        param_inserted = 0
        param_skipped = 0
        for dp in dim_params:
            (param_code, param_name, label, field_type, param_direction,
             field_path, agg_role, output_role, visible_in_report,
             required, default_value, help_text, ui_order, *rest) = dp
            pass_threshold = rest[0] if rest else None

            existing = conn.execute(text(
                "SELECT id FROM evaluation_dimension_params "
                "WHERE dimension_id = :did AND param_code = :pc AND param_direction = :dir"
            ), {'did': dim_id, 'pc': param_code, 'dir': param_direction}).fetchone()

            if existing:
                print(f"  - {param_code} ({param_direction}) 已存在")
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
                    'did': dim_id, 'pc': param_code, 'pn': param_name, 'lb': label,
                    'ft': field_type, 'dir': param_direction, 'fp': field_path,
                    'ar': agg_role, 'or': output_role, 'vir': visible_in_report,
                    'req': required, 'dv': default_value, 'pt': pass_threshold,
                    'ht': help_text, 'uo': ui_order
                })
                print(f"  + {param_code} ({field_type}, {param_direction})")
                param_inserted += 1

        print(f"  插入 {param_inserted} 条，跳过 {param_skipped} 条")

        # ============================================================
        # Step 3: 注册 voice_llm 算法与 llm_judge 维度的关联
        # ============================================================
        print("\n=== Step 3: 注册 voice_llm → llm_judge 关联 (algorithm_dimension_relations) ===")

        existing_rel = conn.execute(text(
            "SELECT id FROM algorithm_dimension_relations "
            "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
        ), {'did': dim_id}).fetchone()

        if existing_rel:
            print(f"  - 关联已存在 (voice_llm → llm_judge id={dim_id})，跳过")
        else:
            conn.execute(text(
                "INSERT INTO algorithm_dimension_relations "
                "  (algorithm_type, dimension_id, is_default, weight, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
            ), {'did': dim_id})
            print(f"  + 关联已插入 (voice_llm → llm_judge id={dim_id})")

        # ============================================================
        # Step 4: 补充 voice_llm param_mappings（设备输出 → llm_judge 输入）
        # ============================================================
        print("\n=== Step 4: 补充 voice_llm → llm_judge 参数映射 (param_mappings) ===")

        # param_mappings 表的 dimension_id 现在指向 llm_judge 维度
        # 这样 evaluation_service 能按维度提取对应的输入参数
        judge_mappings = [
            # (source, source_direction, source_param, target_param, transform_type)
            ('reference', 'output', 'correct_answer', 'correct_answer', 'none'),
            ('reference', 'output', 'query', 'query', 'none'),
            ('device', 'output', 'question', 'question', 'none'),
            ('device', 'output', 'answer', 'answer', 'none'),
        ]

        map_inserted = 0
        map_skipped = 0
        for m in judge_mappings:
            (source, source_direction, source_param, target_param,
             transform_type) = m

            existing = conn.execute(text(
                "SELECT id FROM param_mappings "
                "WHERE algorithm_type = 'voice_llm' AND source = :src "
                "AND source_param = :sp AND dimension_id = :did"
            ), {'src': source, 'sp': source_param, 'did': dim_id}).fetchone()

            if existing:
                print(f"  - {source}.{source_param} → {target_param} 已存在")
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
                    'did': dim_id, 'tp': target_param, 'tt': transform_type
                })
                print(f"  + {source}.{source_param} → {target_param}")
                map_inserted += 1

        print(f"  插入 {map_inserted} 条，跳过 {map_skipped} 条")

        print("\n=== llm_judge 维度种子数据注册完成 ===")


if __name__ == '__main__':
    print("=" * 60)
    print("llm_judge 评估维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. llm_judge 评估维度（dimensions）")
    print("2. 9 个维度输入/输出参数（evaluation_dimension_params）")
    print("3. voice_llm → llm_judge 关联（algorithm_dimension_relations）")
    print("4. 5 条参数映射（device/reference → llm_judge 输入）+ prompt 参数")
    print()
    print("llm_judge 输入：record_file, correct_answer, query, question, answer, prompt")
    print("llm_judge 输出：llm_judge_score, criteria_scores, reasoning")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_llm_judge_dimension()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
