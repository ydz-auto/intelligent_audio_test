# -*- coding: utf-8 -*-
"""
voice_llm 算法种子数据

功能：
1. 注册 voice_llm 算法定义（algorithm_definitions）
2. 注册 voice_llm 用例专属参数（case_algorithm_params），含 scope 字段
   （与库当前非软删状态一致：仅 10 个活跃参数）
3. 注册 voice_llm 设备输出字段（algorithm_device_params）
   （与库当前非软删状态一致：仅 6 个活跃字段）
4. 注册 voice_llm API 输入/输出字段（algorithm_api_params）
   （与库当前非软删状态一致：无活跃 API 字段，仅做清理）
5. 注册 voice_llm 参考参数定义（algorithm_reference_params）
   （与库当前非软删状态一致：query/is_reject/env_type 活跃）
6. 注册 voice_llm 参数映射（param_mappings，仅库中活跃的族）
7. 注册 voice_llm 算法-维度关联（algorithm_dimension_relations）

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_voice_llm

或直接：
    python backend/scripts/migrations/202606/seed_voice_llm.py

注意：此脚本可重复执行（幂等），使用 ON CONFLICT DO NOTHING
"""

import sys
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def seed_voice_llm():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 1: 确保 scope 列存在
        # ============================================================
        print("=== Step 1: 确保 case_algorithm_params.scope 列存在 ===")
        try:
            conn.execute(text(
                "ALTER TABLE case_algorithm_params "
                "ADD COLUMN IF NOT EXISTS scope VARCHAR(10) NOT NULL DEFAULT 'common'"
            ))
            print("  + scope 列已就绪")
        except Exception as e:
            msg = str(e).lower()
            if 'already' in msg or 'exists' in msg:
                print("  - scope 列已存在")
            else:
                raise

        for col_name, col_type in [('min_value', 'FLOAT'), ('max_value', 'FLOAT'), ('step', 'FLOAT'), ('unit', 'VARCHAR(20)')]:
            try:
                conn.execute(text(
                    f"ALTER TABLE case_algorithm_params ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
            except Exception as e:
                msg = str(e).lower()
                if 'already' in msg or 'exists' in msg:
                    pass
                else:
                    raise
        print("  + min_value/max_value/step/unit 列已就绪")

        # ============================================================
        # Step 2: 注册 voice_llm 算法定义
        # ============================================================
        print("\n=== Step 2: 注册 voice_llm 算法定义 ===")
        existing = conn.execute(text(
            "SELECT id FROM algorithm_definitions WHERE type = 'voice_llm' AND deleted = false"
        )).fetchone()

        if existing:
            print("  - voice_llm 算法定义已存在，跳过")
        else:
            conn.execute(text(
                "INSERT INTO algorithm_definitions "
                "  (type, name, description, status, display_order, deleted, created_at, updated_at) "
                "VALUES "
                "  ('voice_llm', '小艺语音大模型', '语音大模型交互测试', 'online', 100, false, NOW(), NOW())"
            ))
            print("  + voice_llm 算法定义已插入")

        # ============================================================
        # Step 3: 注册 voice_llm 用例参数（case_algorithm_params）
        #   幂等 upsert：按 (algorithm_type, param_code) 匹配，已软删记录复用并复活。
        #   这些参数用于用例表单渲染与按轮算法参数采集，
        #   由 algorithm_controller / audio_controller / case_parameter_extractor 消费。
        # ============================================================
        print("\n=== Step 3: 注册 voice_llm 用例参数 (case_algorithm_params) ===")

        # 与库当前非软删状态一致（10 个活跃用例参数；
        # task_type/audios/background_noise 已在库中软删，不再注册）
        # (param_code, param_name, label, param_type, scope, required, default_value,
        #  help_text, ui_order, hidden, min_value, max_value, step, unit,
        #  annotation_code, field_path)
        case_params = [
            ('interferers', '干扰人列表', '干扰人', 'json', 'e2e', False, '{}',
             '干扰人配置列表', 0, False, None, None, None, None,
             'voice_llm', 'interferers'),
            ('record_mode', '录屏模式', '', 'text', 'common', False, '0',
             '', 1, False, None, None, None, None, None, None),
            # 拒识评估族（reject_judge）用例参数：按轮从用例配置取，经 source=case/reference 映射传入
            ('type', '拒识场景', '拒识场景类型', 'text', 'common', False, None,
             '拒识场景(非目标人拒识/目标人非交互意图/环境噪声/用户BC)，按轮从用例取', 2, False, None, None, None, None, None, None),
            ('timing', '拒识时机', '拒识发生时机', 'text', 'common', False, None,
             '拒识发生时机(回复过程中/静默)，决定行为类别定义和rate计算规则', 3, False, None, None, None, None, None, None),
            ('is_interruption', '是否打断', '', 'text', 'common', False, None,
             '', 4, False, None, None, None, None, None, None),
            ('stop_intent', '停止指令意图', '是否为停止指令轮', 'switch', 'common', False, None,
             '显式停止指令标记；模型停止原内容输出即遵从，只回复"好的/我明白了"等确认语同样算遵从', 5, False, None, None, None, None, None, None),
            ('is_return_to_topic', '是否回到原话题', '是否回到原话题', 'switch', 'common', False, None,
             '标注该轮是否回到原话题（用户打断后模型是否拉回原话题），供 interruption_metrics 评估', 6, False, None, None, None, None, None, None),
            ('is_reject', '是否为拒识内容', '是否为拒识内容', 'switch', 'common', False, 'true',
             'True=该轮为拒识内容，参与拒识评估统计；False=非拒识轮，跳过不统计', 7, False, None, None, None, None, None, None),
            ('is_single_round', '单轮拒识', '是否为单轮拒识模式', 'switch', 'common', False, 'false',
             'True=单轮拒识(user_wav直接为拒识内容)，False=多轮拒识(user_wav包含意图交互+拒识干扰)', 8, False, None, None, None, None, None, None),
            # 环境理解族（env_judge）用例参数
            ('correctAnswer', '参考答案', '参考答案', 'text', 'common', False, None,
             '环境理解评估的标准答案（如"开关门"），从用例配置读取', 9, False, None, None, None, None, None, None),
        ]

        inserted_count = 0
        updated_count = 0
        for p in case_params:
            (param_code, param_name, label, param_type, scope, required,
             default_value, help_text, ui_order, hidden,
             min_value, max_value, step, unit, annotation_code, field_path) = p

            # 按 (algorithm_type, param_code) 查找，含已软删记录（复用其 id 复活）
            existing = conn.execute(text(
                "SELECT id, deleted FROM case_algorithm_params "
                "WHERE algorithm_type = 'voice_llm' AND param_code = :pc"
            ), {'pc': param_code}).fetchone()

            if existing:
                conn.execute(text(
                    "UPDATE case_algorithm_params SET "
                    "  param_name = :pn, label = :lb, param_type = :pt, scope = :scope, "
                    "  required = :req, default_value = :dv, help_text = :ht, "
                    "  ui_order = :uo, hidden = :hid, "
                    "  min_value = :mn, max_value = :mx, step = :st, unit = :un, "
                    "  annotation_code = :ac, field_path = :fp, "
                    "  deleted = FALSE, updated_at = NOW() "
                    "WHERE id = :id"
                ), {
                    'pn': param_name, 'lb': label, 'pt': param_type, 'scope': scope,
                    'req': required, 'dv': default_value, 'ht': help_text,
                    'uo': ui_order, 'hid': hidden,
                    'mn': min_value, 'mx': max_value, 'st': step, 'un': unit,
                    'ac': annotation_code, 'fp': field_path, 'id': existing[0],
                })
                if existing[1]:
                    print(f"  ~ {param_code} (scope={scope}) 已软删，重新激活")
                else:
                    print(f"  - {param_code} (scope={scope}) 已存在，已更新")
                updated_count += 1
            else:
                conn.execute(text(
                    "INSERT INTO case_algorithm_params "
                    "  (algorithm_type, param_code, param_name, label, param_type, scope, "
                    "   required, default_value, help_text, ui_order, hidden, "
                    "   min_value, max_value, step, unit, annotation_code, field_path, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  ('voice_llm', :pc, :pn, :lb, :pt, :scope, "
                    "   :req, :dv, :ht, :uo, :hid, "
                    "   :mn, :mx, :st, :un, :ac, :fp, "
                    "   FALSE, NOW(), NOW())"
                ), {
                    'pc': param_code, 'pn': param_name, 'lb': label, 'pt': param_type,
                    'scope': scope, 'req': required, 'dv': default_value,
                    'ht': help_text, 'uo': ui_order, 'hid': hidden,
                    'mn': min_value, 'mx': max_value, 'st': step, 'un': unit,
                    'ac': annotation_code, 'fp': field_path,
                })
                print(f"  + {param_code} (scope={scope})")
                inserted_count += 1

        print(f"  插入 {inserted_count} 条，更新/复活 {updated_count} 条")

        # 软删不在活跃列表中的废弃参数（query/pause/railDistance/voiceprint* 等历史遗留）
        valid_codes = [p[0] for p in case_params]
        placeholders = ','.join(f':c{i}' for i in range(len(valid_codes)))
        bind = {f'c{i}': c for i, c in enumerate(valid_codes)}
        stale = conn.execute(text(
            "SELECT param_code FROM case_algorithm_params "
            "WHERE algorithm_type = 'voice_llm' AND deleted = FALSE "
            f"AND param_code NOT IN ({placeholders})"
        ), bind).fetchall()
        if stale:
            stale_codes = [r[0] for r in stale]
            print(f"  ! 软删废弃用例参数 {stale_codes}")
            stale_placeholders = ','.join(f':s{i}' for i in range(len(stale_codes)))
            stale_bind = {f's{i}': c for i, c in enumerate(stale_codes)}
            conn.execute(text(
                "UPDATE case_algorithm_params SET deleted = TRUE, updated_at = NOW() "
                "WHERE algorithm_type = 'voice_llm' "
                f"AND param_code IN ({stale_placeholders}) AND deleted = FALSE"
            ), stale_bind)
        else:
            print("  无废弃用例参数需清理")

        # ============================================================
        # Step 4: 注册设备输出字段（algorithm_device_params）
        # ============================================================
        print("\n=== Step 4: 注册 voice_llm 设备输出字段 (algorithm_device_params) ===")

        # 清理不再使用的设备输出字段（voice_llm 当前仅保留 6 个活跃字段；
        # start_ms/end_ms/first_frame_ms/case_wav 及旧 asr 系列均为历史遗留，物理清理）
        obsolete_device_codes = ['asr_text', 'asr_rttm', 'asr_stm', 'record_path', 'device_status',
                                 'start_ms', 'end_ms', 'first_frame_ms', 'case_wav']
        deleted_dev = conn.execute(text(
            "DELETE FROM algorithm_device_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(obsolete_device_codes)}).rowcount
        if deleted_dev:
            print(f"  清理 {deleted_dev} 条旧设备输出字段（asr 系列/start_ms/end_ms/first_frame_ms/case_wav）")

        device_params = [
            ('voice_llm', 'wav_path', '录音文件', 'text', 'output', False, None, 0, False),
            ('voice_llm', 'input_text', '录屏文件', 'text', 'output', False, None, 10, False),
            ('voice_llm', 'question', '用户提问', 'text', 'output', False, None, 11, False),
            ('voice_llm', 'answer', '小艺回答', 'text', 'output', False, None, 12, False),
            ('voice_llm', 'user_wav', '用户通道音频', 'text', 'output', False, None, 13, False),
            ('voice_llm', 'ai_wav', '模型通道音频', 'text', 'output', False, None, 14, False),
        ]

        dev_inserted = 0
        dev_updated = 0
        for dp in device_params:
            (algo_type, param_code, param_name, param_type, direction,
             required, default_value, ui_order, hidden) = dp

            existing = conn.execute(text(
                "SELECT id, deleted FROM algorithm_device_params "
                "WHERE algorithm_type = :at AND param_code = :pc AND direction = :dir"
            ), {'at': algo_type, 'pc': param_code, 'dir': direction}).fetchone()

            if existing:
                # 已存在（含软删）则更新字段并复活
                conn.execute(text(
                    "UPDATE algorithm_device_params SET "
                    "  param_name = :pn, param_type = :pt, required = :req, "
                    "  default_value = :dv, ui_order = :uo, hidden = :hid, "
                    "  deleted = FALSE, updated_at = NOW() "
                    "WHERE id = :id"
                ), {'pn': param_name, 'pt': param_type, 'req': required,
                    'dv': default_value, 'uo': ui_order, 'hid': hidden,
                    'id': existing[0]})
                if existing[1]:
                    print(f"  ~ {param_code} 已软删，重新激活")
                else:
                    print(f"  - {param_code} 已存在，已更新")
                dev_updated += 1
            else:
                conn.execute(text(
                    "INSERT INTO algorithm_device_params "
                    "  (algorithm_type, param_code, param_name, param_type, direction, "
                    "   required, default_value, ui_order, hidden, deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:at, :pc, :pn, :pt, :dir, :req, :dv, :uo, :hid, false, NOW(), NOW())"
                ), {
                    'at': algo_type, 'pc': param_code, 'pn': param_name,
                    'pt': param_type, 'dir': direction, 'req': required,
                    'dv': default_value, 'uo': ui_order, 'hid': hidden
                })
                print(f"  + {param_code} ({param_type}, {direction})")
                dev_inserted += 1

        print(f"  插入 {dev_inserted} 条，更新/复活 {dev_updated} 条")

        # ============================================================
        # Step 5: 注册 API 输入/输出字段（algorithm_api_params）
        # ============================================================
        print("\n=== Step 5: 注册 voice_llm API 字段 (algorithm_api_params) ===")

        # 与库当前非软删状态一致：voice_llm 无活跃 API 字段（历史 input_text/input_audio/
        # response_audio 已软删），仅保留清理逻辑，不注册新字段。
        api_params = []

        # 清理旧的 llm_response 字段（voice_llm 不使用此 API 输出字段，由设备驱动 answer 提供）
        obsolete_api_codes = ['llm_response']
        deleted_api = conn.execute(text(
            "DELETE FROM algorithm_api_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(obsolete_api_codes)}).rowcount
        if deleted_api:
            print(f"  清理 {deleted_api} 条旧 API 输出字段（llm_response）")

        api_inserted = 0
        api_updated = 0
        for ap in api_params:
            (algo_type, param_code, param_name, param_type, direction,
             required, default_value, ui_order, hidden) = ap

            existing = conn.execute(text(
                "SELECT id, deleted FROM algorithm_api_params "
                "WHERE algorithm_type = :at AND param_code = :pc AND direction = :dir"
            ), {'at': algo_type, 'pc': param_code, 'dir': direction}).fetchone()

            if existing:
                # 已存在（含软删）则更新字段并复活
                conn.execute(text(
                    "UPDATE algorithm_api_params SET "
                    "  param_name = :pn, param_type = :pt, required = :req, "
                    "  default_value = :dv, ui_order = :uo, hidden = :hid, "
                    "  deleted = FALSE, updated_at = NOW() "
                    "WHERE id = :id"
                ), {'pn': param_name, 'pt': param_type, 'req': required,
                    'dv': default_value, 'uo': ui_order, 'hid': hidden,
                    'id': existing[0]})
                if existing[1]:
                    print(f"  ~ {param_code} 已软删，重新激活")
                else:
                    print(f"  - {param_code} 已存在，已更新")
                api_updated += 1
            else:
                conn.execute(text(
                    "INSERT INTO algorithm_api_params "
                    "  (algorithm_type, param_code, param_name, param_type, direction, "
                    "   required, default_value, ui_order, hidden, deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:at, :pc, :pn, :pt, :dir, :req, :dv, :uo, :hid, false, NOW(), NOW())"
                ), {
                    'at': algo_type, 'pc': param_code, 'pn': param_name,
                    'pt': param_type, 'dir': direction, 'req': required,
                    'dv': default_value, 'uo': ui_order, 'hid': hidden
                })
                print(f"  + {param_code} ({param_type}, {direction})")
                api_inserted += 1

        print(f"  插入 {api_inserted} 条，更新/复活 {api_updated} 条")

        protocol_fields = ['session_id', 'context_history', 'round_number', 'response_latency', 'session_status']
        deleted = conn.execute(text(
            "DELETE FROM algorithm_api_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(protocol_fields)}).rowcount
        if deleted:
            print(f"  清理 {deleted} 条会话协议字段（由执行引擎管理，不属于算法字段）")

        # ============================================================
        # Step 6: 注册参考参数定义（algorithm_reference_params）
        # ============================================================
        print("\n=== Step 6: 注册 voice_llm 参考参数定义 (algorithm_reference_params) ===")

        # 与库当前非软删状态一致（query/is_reject/env_type 活跃；
        # correct_answer/pause/input_lastword/is_return_to_topic/is_single_round/timing 已软删）
        ref_params = [
            ('voice_llm', 'query', '用户提问', 'text',
             'voice_llm', 'text', 'query', 'first',
             '用户提问'),
            ('voice_llm', 'is_reject', '是否为拒识轮次', 'text',
             'voice_llm', 'boolean', 'is_reject', 'first',
             '是否为拒识轮次'),
            ('voice_llm', 'env_type', '环境理解类型', 'text',
             'voice_llm', 'boolean', 'env_type', 'join',
             '环境理解类型'),
        ]

        ref_inserted = 0
        ref_updated = 0
        for rp in ref_params:
            (algo_type, code, name, param_type,
             annotation_code, annotation_format, field_path, merge_mode,
             help_text) = rp

            existing = conn.execute(text(
                "SELECT id, deleted FROM algorithm_reference_params "
                "WHERE algorithm_type = :at AND code = :code"
            ), {'at': algo_type, 'code': code}).fetchone()

            if existing:
                # 已存在（含软删）则更新字段并复活
                conn.execute(text(
                    "UPDATE algorithm_reference_params SET "
                    "  name = :name, param_type = :pt, annotation_code = :ac, "
                    "  annotation_format = :af, field_path = :fp, merge_mode = :mm, "
                    "  help_text = :ht, deleted = FALSE, updated_at = NOW() "
                    "WHERE id = :id"
                ), {'name': name, 'pt': param_type, 'ac': annotation_code,
                    'af': annotation_format, 'fp': field_path, 'mm': merge_mode,
                    'ht': help_text, 'id': existing[0]})
                if existing[1]:
                    print(f"  ~ {code} 已软删，重新激活")
                else:
                    print(f"  - {code} 已存在，已更新")
                ref_updated += 1
            else:
                conn.execute(text(
                    "INSERT INTO algorithm_reference_params "
                    "  (algorithm_type, code, name, param_type, "
                    "   annotation_code, annotation_format, field_path, merge_mode, "
                    "   help_text, deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:at, :code, :name, :pt, "
                    "   :ac, :af, :fp, :mm, "
                    "   :ht, false, NOW(), NOW())"
                ), {
                    'at': algo_type, 'code': code, 'name': name, 'pt': param_type,
                    'ac': annotation_code, 'af': annotation_format,
                    'fp': field_path, 'mm': merge_mode, 'ht': help_text
                })
                print(f"  + {code} ({param_type})")
                ref_inserted += 1

        print(f"  插入 {ref_inserted} 条，更新/复活 {ref_updated} 条")

        # ============================================================
        # Step 7: 注册主维度参数映射（param_mappings）
        #   按 task_type_code 定义各维度映射，统一在此注册（幂等 upsert）。
        #   只在主维度（parent_dimension_id IS NULL）注册：子维度运行时
        #   继承父维度的 api 配置与 input_params（见 evaluation_service.
        #   _load_dimension_data），无需各自挂映射。
        #   主维度额外注册轮次结构化音频映射
        #   （case_config → played_audios/background_noise/interferers）。
        #   先软删子维度上遗留的冗余映射，再 upsert 主维度映射。
        # ============================================================
        print("\n=== Step 7: 注册 voice_llm 主维度参数映射 (param_mappings) ===")

        # task_type_code → 参数映射（algorithm_type 固定 voice_llm）
        # 仅保留库中活跃的族；llm_judge/turn_taking/non_interactive_latency/noise_latency/
        # rejection_judge/interruption_judge/judge_answer/broadcast_score 等族维度已软删，不再注册。
        # 每个主维度在 Step 7b 还会追加 audio_mappings（case_config 轮次音频 3 条）。
        dimension_mappings = {
            'interruption_metrics': [
                ('device', 'output', 'user_wav', 'user_wav', 'none'),
                ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
                ('device', 'output', 'case_wav', 'case_wav', 'none'),
                ('reference', 'output', 'query', 'query', 'none'),
                ('case', 'output', 'is_return_to_topic', 'is_return_to_topic', 'none'),
            ],
        }

        # 轮次结构化音频映射（作用于所有启用中的主维度）
        audio_mappings = [
            ('case_config', 'output', 'audios', 'played_audios', 'none'),
            ('case_config', 'output', 'background_noise', 'background_noise', 'none'),
            ('case_config', 'output', 'interferers', 'interferers', 'none'),
        ]

        dim_rows = conn.execute(text(
            "SELECT id, task_type_code, parent_dimension_id, name FROM dimensions "
            "WHERE deleted = FALSE ORDER BY id"
        )).fetchall()

        # Step 7a: 软删子维度（parent_dimension_id IS NOT NULL）的 voice_llm 冗余映射
        # 子维度运行时继承父维度映射，无需各自注册。
        # 例外：evaluation 源映射（如接管率占比等，由父维度输出经聚合映射到子维度，
        # 由 API 保存维度时 _sync_param_mappings 创建）不是冗余，不能删。
        sub_dims = [(r[0], r[3]) for r in dim_rows if r[2] is not None]
        if sub_dims:
            sub_ids = [d[0] for d in sub_dims]
            placeholders = ','.join(f':s{i}' for i in range(len(sub_ids)))
            bind = {f's{i}': sid for i, sid in enumerate(sub_ids)}
            deleted_sub = conn.execute(text(
                f"UPDATE param_mappings SET deleted = TRUE, updated_at = NOW() "
                f"WHERE algorithm_type = 'voice_llm' AND dimension_id IN ({placeholders}) "
                f"AND source <> 'evaluation' AND deleted = FALSE"
            ), bind).rowcount
            if deleted_sub:
                print(f"  ! 软删子维度冗余映射 {deleted_sub} 条（子维度共 {len(sub_ids)} 个）")
            else:
                print(f"  - 子维度（{len(sub_ids)} 个）无冗余映射")
        else:
            print("  无子维度，跳过")

        # Step 7b: 注册主维度（parent_dimension_id IS NULL）参数映射
        main_dims = [r for r in dim_rows if r[2] is None]
        map_inserted = 0
        map_updated = 0
        for dim_id, task_code, _parent_id, dim_name in main_dims:
            mappings = list(dimension_mappings.get(task_code, []))
            mappings.extend(audio_mappings)
            if not mappings:
                continue
            print(f"  -- 主维度 '{dim_name}' (id={dim_id}, task_type_code={task_code}) --")
            for (source, source_direction, source_param, target_param,
                 transform_type) in mappings:
                existing = conn.execute(text(
                    "SELECT id FROM param_mappings "
                    "WHERE algorithm_type = 'voice_llm' AND source = :src "
                    "AND source_param = :sp AND dimension_id = :did"
                ), {'src': source, 'sp': source_param, 'did': dim_id}).fetchone()

                if existing:
                    conn.execute(text(
                        "UPDATE param_mappings SET "
                        "  target_param = :tp, transform_type = :tt, "
                        "  source_direction = :sd, deleted = FALSE, updated_at = NOW() "
                        "WHERE id = :id"
                    ), {'tp': target_param, 'tt': transform_type,
                        'sd': source_direction, 'id': existing[0]})
                    map_updated += 1
                else:
                    conn.execute(text(
                        "INSERT INTO param_mappings "
                        "  (algorithm_type, source, source_direction, source_param, "
                        "   dimension_id, target_param, transform_type, "
                        "   deleted, created_at, updated_at) "
                        "VALUES "
                        "  ('voice_llm', :src, :sd, :sp, :did, :tp, :tt, "
                        "   FALSE, NOW(), NOW())"
                    ), {'src': source, 'sd': source_direction, 'sp': source_param,
                        'did': dim_id, 'tp': target_param, 'tt': transform_type})
                    map_inserted += 1

        print(f"  插入 {map_inserted} 条，更新 {map_updated} 条")

        # ============================================================
        # Step 8: 注册算法-维度关联（algorithm_dimension_relations）
        #   幂等 upsert：已软删记录重新激活，缺失记录插入
        # ============================================================
        print("\n=== Step 8: 注册 voice_llm 算法-维度关联 (algorithm_dimension_relations) ===")

        rel_inserted = 0
        rel_reactivated = 0
        rel_skipped = 0
        if not dim_rows:
            print("  未找到维度，跳过")
        else:
            for dim_id, task_code, parent_id, dim_name in dim_rows:
                existing = conn.execute(text(
                    "SELECT id, deleted FROM algorithm_dimension_relations "
                    "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
                ), {'did': dim_id}).fetchone()

                if existing:
                    rel_id, is_deleted = existing
                    if is_deleted:
                        conn.execute(text(
                            "UPDATE algorithm_dimension_relations SET "
                            "  deleted = FALSE, updated_at = NOW() "
                            "WHERE id = :id"
                        ), {'id': rel_id})
                        print(f"  ~ 维度 '{dim_name}' (id={dim_id}) 关联已软删，重新激活")
                        rel_reactivated += 1
                    else:
                        print(f"  - 维度 '{dim_name}' (id={dim_id}) 关联已存在")
                        rel_skipped += 1
                else:
                    conn.execute(text(
                        "INSERT INTO algorithm_dimension_relations "
                        "  (algorithm_type, dimension_id, is_default, weight, deleted, "
                        "   created_at, updated_at) "
                        "VALUES "
                        "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
                    ), {'did': dim_id})
                    print(f"  + 关联维度 '{dim_name}' (id={dim_id})")
                    rel_inserted += 1

        print(f"  插入 {rel_inserted} 条，重新激活 {rel_reactivated} 条，跳过 {rel_skipped} 条")

        print("\n=== voice_llm 种子数据注册完成 ===")


if __name__ == '__main__':
    print("=" * 60)
    print("voice_llm 算法种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. voice_llm 算法定义")
    print("2. 10 个用例参数（case_algorithm_params，幂等 upsert，含拒识/环境理解字段）")
    print("3. 6 个设备输出字段（wav_path/input_text/question/answer/user_wav/ai_wav）")
    print("4. API 字段（当前库无活跃字段，仅清理历史遗留）")
    print("5. 3 个参考参数定义（query/is_reject/env_type）")
    print("6. 注册活跃族参数映射（按 task_type_code 分组）")
    print("7. 注册算法-维度关联（所有维度，含软删恢复）")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_voice_llm()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
