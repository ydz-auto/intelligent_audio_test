# -*- coding: utf-8 -*-
"""
环境音/拒识场景裁判维度种子数据

功能：
1. 注册一个评估维度（dimension）：
   - env_judge (录屏文件 LLM 裁判：拒识与环境理解)
2. 注册该维度的输入/输出参数（evaluation_dimension_params）
3. 注册 voice_llm 算法与该维度的关联（algorithm_dimension_relations）
4. 注册 voice_llm → 该维度的参数映射（param_mappings）

对应 eval_server 服务：
   - eval_server/app/services/xiaoyi_metrics/env_judge/env_judge.py
   - 入口：evaluate_env_judge(video_path, task_type, env_type, ...)
   - task_type：env_judge

输入：
   - video_path : 录屏/视频文件路径（LLM 直接看视频做裁判）
   - env_type   : 环境子场景类型（如'旁人交谈''环境噪声''环境回溯'等）
   - model      : LLM 模型名（可选，缺省读 config.LLM_JUDGE.default_model）

输出：
   - evaluations : LLM 裁判结果列表 [{scene, behavior, reason}, ...]

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
DIMENSIONS = [
    {
        'task_type_code': 'env_judge',
        'legacy_task_type_codes': ['env_sound_judge'],
        'name': '环境音裁判',
        'keywords': 'env_sound,judge,环境音,拒识,场景理解,裁判,旁人交谈,环境噪声,反馈词,生理声,环境事件回溯',
        'description': (
            '录屏文件 LLM 裁判：拒识与环境理解。'
            '场景包括旁人交谈静默/环境噪声/反馈词/生理声/环境事件回溯，'
            '由裁判模型对语音大模型的行为进行评判（回应/恢复/询问/无关回复/沉默）。'
        ),
        'type': 'auto',
        'result_type': 1,  # 文本型，LLM 裁判输出为纯文本，无法数值统计
        'result_min': 0.0,
        'result_max': 0.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 120,  # LLM 调用
        'score_unit': '',
        'statistic_method': 'none',
        'params': [
            # ─── 输入参数 ───
            ('video_path', '录屏文件', '录屏文件路径', 'text', 'input',
             None, None, None, True,
             False, None, '录屏/视频文件路径，LLM 直接看视频做裁判', 5),
            ('env_type', '环境子场景', '环境子场景类型', 'text', 'input',
             None, None, None, False,
             False, None, '环境子场景类型(如 旁人交谈/环境噪声/环境回溯 等)', 10),
            ('model', 'LLM模型', 'LLM 模型名(覆盖默认)', 'text', 'input',
             None, None, None, False,
             False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认', 15),
            ('max_tokens', '最大token', '最大输出 token 数', 'number', 'input',
             None, None, None, False,
             False, '4096', 'LLM 最大输出 token 数', 20),
            ('temperature', '采样温度', '采样温度', 'number', 'input',
             None, None, None, False,
             False, '0.1', '采样温度，评判场景建议低温 0.1', 25),

            # ─── 输出参数 ───
            ('evaluations', '裁判结果', 'LLM 裁判结果', 'text', 'output',
             'evaluations', None, 'main', True,
             False, None, 'LLM 裁判原始输出(纯文本，不做数值统计)', 60),
            ('esj_model', '裁判模型', '使用的 LLM 模型', 'text', 'output',
             'model', None, 'aux', False,
             False, None, '本次裁判使用的 LLM 模型名', 61),
            ('esj_task_type', '裁判类型', '裁判任务类型', 'text', 'output',
             'task_type', None, 'aux', False,
             False, None, '裁判任务类型(env_judge/interruption_judge)', 62),
            ('esj_env_type', '环境场景', '环境子场景类型', 'text', 'output',
             'env_type', None, 'aux', False,
             False, None, '环境子场景类型', 63),
            ('tokens_used', 'token用量', '总 token 用量', 'number', 'output',
             'tokens_used', None, 'aux', False,
             False, None, 'LLM 调用总 token 用量', 70),
            ('input_token', '输入token', '输入 token 数', 'number', 'output',
             'input_token', None, 'aux', False,
             False, None, 'LLM 输入 token 数', 71),
            ('output_token', '输出token', '输出 token 数', 'number', 'output',
             'output_token', None, 'aux', False,
             False, None, 'LLM 输出 token 数', 72),
            ('esj_message', '裁判说明', '裁判结果说明', 'text', 'output',
             'message', None, 'aux', False,
             False, None, '裁判错误/成功说明', 99),
        ],
        'param_mappings': [
            ('device', 'output', 'video_path', 'video_path', 'none'),
            ('reference', 'output', 'env_type', 'env_type', 'none'),
        ],
    },
]


def seed_env_sound_judge():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        for dim_def in DIMENSIONS:
            task_code = dim_def['task_type_code']
            # 旧 code → 新 code 迁移（env_sound_judge → env_judge）
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
                        # 若已存在同 id 的新 code 记录则直接软删旧记录
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
                    'model': '{{model}}',
                    'max_tokens': '{{max_tokens}}',
                    'temperature': '{{temperature}}',
                    'rounds': [
                        {
                            'video_path': '{{video_path}}',
                            'env_type': '{{env_type}}',
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

            # 清理已废弃的参数
            current_codes = {p[0] for p in dim_def['params']}
            stale = conn.execute(text(
                "SELECT param_code FROM evaluation_dimension_params "
                "WHERE dimension_id = :did AND param_code NOT IN :codes "
                "AND deleted = FALSE"
            ), {'did': dim_id, 'codes': tuple(current_codes) if current_codes else ('',)}).fetchall()
            if stale:
                stale_codes = [r[0] for r in stale]
                print(f"  ! 清理已废弃参数: {stale_codes}")
                conn.execute(text(
                    "UPDATE evaluation_dimension_params SET "
                    "  deleted = TRUE, updated_at = NOW() "
                    "WHERE dimension_id = :did AND param_code IN :codes"
                ), {'did': dim_id, 'codes': tuple(stale_codes)})

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
        print("  环境音裁判维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("环境音裁判维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. env_judge 维度 — 环境音/拒识场景裁判")
    print("   入参: video_path(录屏文件), env_type(环境子场景), model, max_tokens, temperature")
    print()
    print("   主分: 裁判结果 (evaluations)")
    print("   辅助: 模型名 / 裁判类型 / 环境场景 / token 用量 / 说明")
    print()
    print("   场景: 旁人交谈静默/环境噪声/反馈词/生理声/环境事件回溯")
    print("   行为: 回应/恢复/询问/无关回复/沉默")
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
