# -*- coding: utf-8 -*-
"""
拒识裁判维度层级重构：3 级 → 2 级

变更前（3 级）：
  拒识裁判v2 (main)
    ├── 拒识成功率占比 (sub, parent=拒识裁判v2)
    │     ├── 静默时拒识恢复行为占比 (sub, parent=拒识成功率占比)
    │     └── 回复时拒识恢复行为占比 (sub, parent=拒识成功率占比)
    ├── 拒识询问率占比 (sub, parent=拒识裁判v2)
    │     ├── 静默时拒识询问行为占比 (sub, parent=拒识询问率占比)
    │     └── 回复时拒识询问行为占比 (sub, parent=拒识询问率占比)
    └── 拒识失败率占比 (sub, parent=拒识裁判v2)
          ├── 静默时拒识回应行为占比 (sub, parent=拒识失败率占比)
          ├── 回复时拒识回应行为占比 (sub, parent=拒识失败率占比)
          ├── 静默时拒识无关行为占比 (sub, parent=拒识失败率占比)
          ├── 回复时拒识无关行为占比 (sub, parent=拒识失败率占比)
          └── 回复时拒识静默行为占比 (sub, parent=拒识失败率占比)

变更后（2 级）：
  拒识成功率占比 (main)
    ├── 静默时拒识恢复行为占比 (sub, parent=拒识成功率占比)
    └── 回复时拒识恢复行为占比 (sub, parent=拒识成功率占比)
  拒识询问率占比 (main)
    ├── 静默时拒识询问行为占比 (sub, parent=拒识询问率占比)
    └── 回复时拒识询问行为占比 (sub, parent=拒识询问率占比)
  拒识失败率占比 (main)
    ├── 静默时拒识回应行为占比 (sub, parent=拒识失败率占比)
    ├── 回复时拒识回应行为占比 (sub, parent=拒识失败率占比)
    ├── 静默时拒识无关行为占比 (sub, parent=拒识失败率占比)
    ├── 回复时拒识无关行为占比 (sub, parent=拒识失败率占比)
    └── 回复时拒识静默行为占比 (sub, parent=拒识失败率占比)

操作：
1. 将 3 个父级子维度（拒识成功率/询问率/失败率占比）改为 dimension_type='main'，parent_dimension_id=NULL
2. 从原主维度（拒识裁判v2）复制 API 配置、输入参数、aux 输出参数、param_mappings 到各 rate 维度
3. 软删除原主维度（拒识裁判v2）
4. 9 个子级子维度（行为细分）不变，parent_dimension_id 仍指向各 rate 维度

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202609.restructure_reject_judge_dimensions

或直接：
    python backend/scripts/migrations/202609/restructure_reject_judge_dimensions.py
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def restructure():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ── Step 1: 找到原主维度 ──
        main_dim = conn.execute(text(
            "SELECT id, name, api_url, api_settings, api_endpoints, task_type_code "
            "FROM dimensions "
            "WHERE task_type_code = 'reject_judge' AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        )).fetchone()

        if not main_dim:
            print("  ! 未找到 reject_judge 主维度（拒识裁判v2），可能已迁移过，跳过")
            return

        main_id = main_dim[0]
        main_name = main_dim[1]
        main_api_url = main_dim[2]
        main_api_settings = main_dim[3]
        main_api_endpoints = main_dim[4]
        main_task_type_code = main_dim[5]

        print(f"  原主维度: id={main_id}, name={main_name}")

        # ── Step 2: 找到 3 个父级子维度 ──
        rate_dims = conn.execute(text(
            "SELECT id, name FROM dimensions "
            "WHERE parent_dimension_id = :main_id AND dimension_type = 'sub' AND deleted = FALSE "
            "ORDER BY name"
        ), {'main_id': main_id}).fetchall()

        if not rate_dims:
            print("  ! 未找到 reject_judge 的父级子维度，跳过")
            return

        print(f"  找到 {len(rate_dims)} 个父级子维度:")
        for rd in rate_dims:
            print(f"    - id={rd[0]}, name={rd[1]}")

        # ── Step 3: 从原主维度复制 API 配置到各 rate 维度 ──
        print("\n--- Step 3: 复制 API 配置到各 rate 维度 ---")
        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            conn.execute(text(
                "UPDATE dimensions SET "
                "  api_url = :api_url, "
                "  api_settings = :api_settings, "
                "  api_endpoints = :api_endpoints "
                "WHERE id = :rid"
            ), {
                'api_url': main_api_url,
                'api_settings': main_api_settings,
                'api_endpoints': main_api_endpoints,
                'rid': rate_id,
            })
            print(f"  - {rate_name} (id={rate_id}): API 配置已复制")

        # ── Step 4: 复制输入参数 ──
        print("\n--- Step 4: 复制输入参数 ---")
        main_input_params = conn.execute(text(
            "SELECT param_code, param_name, label, field_type, field_path, "
            "       agg_role, output_role, visible_in_report, required, default_value, "
            "       pass_threshold, help_text, ui_order "
            "FROM evaluation_dimension_params "
            "WHERE dimension_id = :main_id AND param_direction = 'input' AND deleted = FALSE"
        ), {'main_id': main_id}).fetchall()

        print(f"  原主维度有 {len(main_input_params)} 个输入参数")

        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            for p in main_input_params:
                # 检查是否已存在（避免重复）
                existing = conn.execute(text(
                    "SELECT id FROM evaluation_dimension_params "
                    "WHERE dimension_id = :rid AND param_code = :pc AND param_direction = 'input'"
                ), {'rid': rate_id, 'pc': p[0]}).fetchone()

                if existing:
                    # 更新
                    conn.execute(text(
                        "UPDATE evaluation_dimension_params SET "
                        "  param_name = :pn, label = :lb, field_type = :ft, field_path = :fp, "
                        "  agg_role = :ar, output_role = :or, visible_in_report = :vir, "
                        "  required = :req, default_value = :dv, pass_threshold = :pt, "
                        "  help_text = :ht, ui_order = :uo, deleted = FALSE, updated_at = NOW() "
                        "WHERE id = :id"
                    ), {
                        'pn': p[1], 'lb': p[2], 'ft': p[3], 'fp': p[4],
                        'ar': p[5], 'or': p[6], 'vir': p[7],
                        'req': p[8], 'dv': p[9], 'pt': p[10],
                        'ht': p[11], 'uo': p[12], 'id': existing[0],
                    })
                else:
                    # 插入
                    conn.execute(text(
                        "INSERT INTO evaluation_dimension_params "
                        "  (dimension_id, param_code, param_name, label, field_type, "
                        "   param_direction, field_path, agg_role, output_role, "
                        "   visible_in_report, required, default_value, pass_threshold, help_text, "
                        "   ui_order, deleted, created_at, updated_at) "
                        "VALUES "
                        "  (:rid, :pc, :pn, :lb, :ft, 'input', :fp, :ar, :or, "
                        "   :vir, :req, :dv, :pt, :ht, :uo, FALSE, NOW(), NOW())"
                    ), {
                        'rid': rate_id, 'pc': p[0], 'pn': p[1], 'lb': p[2], 'ft': p[3],
                        'fp': p[4], 'ar': p[5], 'or': p[6], 'vir': p[7],
                        'req': p[8], 'dv': p[9], 'pt': p[10], 'ht': p[11], 'uo': p[12],
                    })
            print(f"  - {rate_name} (id={rate_id}): {len(main_input_params)} 个输入参数已复制")

        # ── Step 5: 复制 aux 输出参数 ──
        print("\n--- Step 5: 复制 aux 输出参数 ---")
        main_aux_params = conn.execute(text(
            "SELECT param_code, param_name, label, field_type, field_path, "
            "       agg_role, output_role, visible_in_report, required, default_value, "
            "       pass_threshold, help_text, ui_order "
            "FROM evaluation_dimension_params "
            "WHERE dimension_id = :main_id AND param_direction = 'output' "
            "AND output_role = 'aux' AND deleted = FALSE"
        ), {'main_id': main_id}).fetchall()

        print(f"  原主维度有 {len(main_aux_params)} 个 aux 输出参数")

        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            for p in main_aux_params:
                existing = conn.execute(text(
                    "SELECT id FROM evaluation_dimension_params "
                    "WHERE dimension_id = :rid AND param_code = :pc AND param_direction = 'output'"
                ), {'rid': rate_id, 'pc': p[0]}).fetchone()

                if existing:
                    conn.execute(text(
                        "UPDATE evaluation_dimension_params SET "
                        "  param_name = :pn, label = :lb, field_type = :ft, field_path = :fp, "
                        "  agg_role = :ar, output_role = :or, visible_in_report = :vir, "
                        "  required = :req, default_value = :dv, pass_threshold = :pt, "
                        "  help_text = :ht, ui_order = :uo, deleted = FALSE, updated_at = NOW() "
                        "WHERE id = :id"
                    ), {
                        'pn': p[1], 'lb': p[2], 'ft': p[3], 'fp': p[4],
                        'ar': p[5], 'or': p[6], 'vir': p[7],
                        'req': p[8], 'dv': p[9], 'pt': p[10],
                        'ht': p[11], 'uo': p[12], 'id': existing[0],
                    })
                else:
                    conn.execute(text(
                        "INSERT INTO evaluation_dimension_params "
                        "  (dimension_id, param_code, param_name, label, field_type, "
                        "   param_direction, field_path, agg_role, output_role, "
                        "   visible_in_report, required, default_value, pass_threshold, help_text, "
                        "   ui_order, deleted, created_at, updated_at) "
                        "VALUES "
                        "  (:rid, :pc, :pn, :lb, :ft, 'output', :fp, :ar, :or, "
                        "   :vir, :req, :dv, :pt, :ht, :uo, FALSE, NOW(), NOW())"
                    ), {
                        'rid': rate_id, 'pc': p[0], 'pn': p[1], 'lb': p[2], 'ft': p[3],
                        'fp': p[4], 'ar': p[5], 'or': p[6], 'vir': p[7],
                        'req': p[8], 'dv': p[9], 'pt': p[10], 'ht': p[11], 'uo': p[12],
                    })
            print(f"  - {rate_name} (id={rate_id}): {len(main_aux_params)} 个 aux 输出参数已复制")

        # ── Step 6: 复制 param_mappings ──
        print("\n--- Step 6: 复制 param_mappings ---")
        main_mappings = conn.execute(text(
            "SELECT source, source_direction, source_param, target_param, transform_type "
            "FROM param_mappings "
            "WHERE dimension_id = :main_id AND algorithm_type = 'voice_llm' AND deleted = FALSE"
        ), {'main_id': main_id}).fetchall()

        print(f"  原主维度有 {len(main_mappings)} 个 param_mappings")

        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            for m in main_mappings:
                existing = conn.execute(text(
                    "SELECT id FROM param_mappings "
                    "WHERE algorithm_type = 'voice_llm' AND source = :src "
                    "AND source_param = :sp AND dimension_id = :rid"
                ), {'src': m[0], 'sp': m[2], 'rid': rate_id}).fetchone()

                if not existing:
                    conn.execute(text(
                        "INSERT INTO param_mappings "
                        "  (algorithm_type, source, source_direction, source_param, "
                        "   dimension_id, target_param, transform_type, "
                        "   deleted, created_at, updated_at) "
                        "VALUES "
                        "  ('voice_llm', :src, :sd, :sp, :rid, :tp, :tt, FALSE, NOW(), NOW())"
                    ), {
                        'src': m[0], 'sd': m[1], 'sp': m[2],
                        'rid': rate_id, 'tp': m[3], 'tt': m[4],
                    })
            print(f"  - {rate_name} (id={rate_id}): param_mappings 已复制")

        # ── Step 7: 注册 algorithm_dimension_relations ──
        print("\n--- Step 7: 注册 algorithm_dimension_relations ---")
        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            existing = conn.execute(text(
                "SELECT id FROM algorithm_dimension_relations "
                "WHERE algorithm_type = 'voice_llm' AND dimension_id = :rid"
            ), {'rid': rate_id}).fetchone()
            if not existing:
                conn.execute(text(
                    "INSERT INTO algorithm_dimension_relations "
                    "  (algorithm_type, dimension_id, is_default, weight, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  ('voice_llm', :rid, FALSE, 1.0, FALSE, NOW(), NOW())"
                ), {'rid': rate_id})
                print(f"  + {rate_name} (id={rate_id}): 关联已创建")
            else:
                print(f"  - {rate_name} (id={rate_id}): 关联已存在")

        # ── Step 8: 将 3 个 rate 维度改为 dimension_type='main' ──
        print("\n--- Step 8: 将 rate 维度改为 dimension_type='main' ---")
        for rate_dim in rate_dims:
            rate_id = rate_dim[0]
            rate_name = rate_dim[1]
            conn.execute(text(
                "UPDATE dimensions SET "
                "  dimension_type = 'main', parent_dimension_id = NULL, "
                "  updated_at = NOW() "
                "WHERE id = :rid"
            ), {'rid': rate_id})
            print(f"  - {rate_name} (id={rate_id}): dimension_type → main, parent → NULL")

        # ── Step 9: 软删除原主维度 ──
        print("\n--- Step 9: 软删除原主维度 ---")
        conn.execute(text(
            "UPDATE dimensions SET "
            "  deleted = TRUE, status = FALSE, updated_at = NOW() "
            "WHERE id = :main_id"
        ), {'main_id': main_id})
        print(f"  - {main_name} (id={main_id}): 已软删除 (deleted=TRUE, status=FALSE)")

        # ── Step 10: 验证结果 ──
        print("\n--- Step 10: 验证结果 ---")
        result = conn.execute(text(
            "SELECT id, name, dimension_type, parent_dimension_id, deleted, status "
            "FROM dimensions "
            "WHERE task_type_code = 'reject_judge' AND deleted = FALSE "
            "ORDER BY sort_order, name"
        )).fetchall()

        print(f"\n  拒识裁判维度结构（共 {len(result)} 个活跃维度）:")
        for r in result:
            dim_id, name, dtype, parent_id, deleted, status = r
            parent_name = ""
            if parent_id:
                p = conn.execute(text(
                    "SELECT name FROM dimensions WHERE id = :pid"
                ), {'pid': parent_id}).fetchone()
                parent_name = f" → parent: {p[0]}" if p else f" → parent_id: {parent_id}"
            print(f"    [{dtype:4s}] id={dim_id:4d}  {name}{parent_name}")

        print(f"\n{'=' * 60}")
        print("  拒识裁判维度层级重构完成：3 级 → 2 级")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("拒识裁判维度层级重构：3 级 → 2 级")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("操作内容：")
    print("1. 将 3 个父级子维度（拒识成功率/询问率/失败率占比）改为 dimension_type='main'")
    print("2. 从原主维度复制 API 配置、输入参数、aux 输出参数、param_mappings")
    print("3. 软删除原主维度（拒识裁判v2）")
    print("4. 9 个子级子维度（行为细分）不变")
    print()
    restructure()
    print()
    print("完成！")
