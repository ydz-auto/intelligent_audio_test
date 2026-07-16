# -*- coding: utf-8 -*-
"""
voice_llm 算法种子数据

功能：
1. 注册 voice_llm 算法定义（algorithm_definitions）
2. 注册 voice_llm 用例专属参数（case_algorithm_params），含 scope 字段
3. 注册 voice_llm 设备输出字段（algorithm_device_params）
4. 注册 voice_llm API 输入/输出字段（algorithm_api_params）
5. 注册 voice_llm 参考参数定义（algorithm_reference_params）
6. 注册 voice_llm 参数映射（param_mappings）
7. 注册 voice_llm 算法-维度关联（algorithm_dimension_relations）

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202506.seed_voice_llm

或直接：
    python backend/scripts/migrations/202506/seed_voice_llm.py

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
                "  ('voice_llm', 'Voice LLM', '语音大模型交互测试', 'online', 100, false, NOW(), NOW())"
            ))
            print("  + voice_llm 算法定义已插入")

        # ============================================================
        # Step 3: 注册用例专属参数（case_algorithm_params）
        # ============================================================
        print("\n=== Step 3: 注册 voice_llm 用例参数 (case_algorithm_params) ===")

        # 清理 inputAudio（后端自动用音频 ID 填入，不需要作为用例参数定义）
        deleted_inputAudio = conn.execute(text(
            "DELETE FROM case_algorithm_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code = 'inputAudio'"
        )).rowcount
        if deleted_inputAudio:
            print(f"  清理 {deleted_inputAudio} 条 inputAudio（后端自动填入，无需定义）")

        case_params = [
            # (algo_type, param_code, param_name, label, param_type, scope,
            #  required, default_value, help_text, ui_order, hidden, deleted,
            #  min_value, max_value, step, unit,
            #  annotation_code, field_path)
            #  annotation_code 默认=algorithm_type, field_path 默认=param_code

            # --- 通用参数（scope=common） ---
            ('voice_llm', 'promptAudioId', 'Prompt 音频', 'Prompt 音频', 'audio_select', 'common',
             False, None, '在干声播放之前播放的引导音频', 30, False, False,
             None, None, None, None,
             None, None),  # 不从标注提取

            # --- E2E 专用参数（scope=e2e） ---
            ('voice_llm', 'interferers', '干扰人列表', '干扰人', 'json', 'e2e',
             False, '[]', '干扰人配置列表，支持多路独立干扰', 20, False, False,
             None, None, None, None,
             None, None),  # 默认 annotation_code=voice_llm, field_path=interferers
            ('voice_llm', 'railDistance', '导轨距离(cm)', '导轨距离', 'slider', 'e2e',
             False, None, '导轨距离，本轮结束后自动复位。不填则不控制导轨', 40, False, False,
             10, 200, 5, 'cm',
             None, None),  # 默认 annotation_code=voice_llm, field_path=railDistance
            ('voice_llm', 'volumeLevel', '被测设备音量', '设备音量', 'slider', 'e2e',
             False, None, '被测设备音量(0-100)，本轮结束后自动恢复。不填则不控制音量', 41, False, False,
             0, 100, 1, None,
             None, None),  # 默认 annotation_code=voice_llm, field_path=volumeLevel
            ('voice_llm', 'voiceprintEnabled', '声纹注册', '声纹注册', 'switch', 'e2e',
             False, 'false', '是否在本轮播放声纹注册音频', 50, False, False,
             None, None, None, None,
             None, None),
            ('voice_llm', 'voiceprintAudioId', '声纹注册音频', '声纹音频', 'audio_select', 'e2e',
             False, None, '声纹注册音频文件', 51, False, False,
             None, None, None, None,
             None, None),
            ('voice_llm', 'voiceprintPlaybackDeviceId', '声纹播放设备', '播放设备', 'device_select', 'e2e',
             False, None, '声纹注册音频播放设备', 52, False, False,
             None, None, None, None,
             None, None),
            ('voice_llm', 'voiceprintSpl', '声纹播放声压级', '声压级', 'number', 'e2e',
             False, '70.0', '声纹注册音频播放声压级', 53, False, False,
             20, 100, 1, 'dB',
             None, None),
            ('voice_llm', 'voiceprintWaitTime', '声纹等待时间(秒)', '等待时间', 'number', 'e2e',
             False, '5.0', '声纹注册后等待时间', 54, False, False,
             0, 60, 1, 's',
             None, None),

            # --- API 专用参数（scope=api） ---
            ('voice_llm', 'inputText', '输入文本', '输入文本', 'text', 'api',
             False, None, '发送给 API 的文本内容（可与输入音频共存）', 70, False, False,
             None, None, None, None,
             None, 'query'),  # annotation_code 默认=voice_llm, field_path=query（标注 JSON 里字段名是 query）
            # inputAudio 不作为用例参数定义，后端创建用例时自动用音频本身 ID 填入 algorithmParams
        ]

        inserted_count = 0
        skipped_count = 0
        for p in case_params:
            (algo_type, param_code, param_name, label, param_type, scope,
             required, default_value, help_text, ui_order, hidden, deleted,
             min_value, max_value, step, unit,
             ann_code, f_path) = p

            # annotation_code 默认 = algorithm_type, field_path 默认 = param_code
            effective_ann_code = ann_code if ann_code is not None else algo_type
            effective_f_path = f_path if f_path is not None else param_code

            existing = conn.execute(text(
                "SELECT id FROM case_algorithm_params "
                "WHERE algorithm_type = :at AND param_code = :pc"
            ), {'at': algo_type, 'pc': param_code}).fetchone()

            if existing:
                conn.execute(text(
                    "UPDATE case_algorithm_params SET "
                    "  param_type = :pt, scope = :scope, min_value = :mn, max_value = :mx, "
                    "  step = :st, unit = :un, annotation_code = :ac, field_path = :fp "
                    "WHERE id = :id"
                ), {'pt': param_type, 'scope': scope, 'mn': min_value, 'mx': max_value,
                    'st': step, 'un': unit, 'ac': effective_ann_code, 'fp': effective_f_path,
                    'id': existing[0]})
                print(f"  - {param_code} 已存在，已更新 param_type/scope/min/max/step/unit/annotation_code/field_path")
                skipped_count += 1
            else:
                conn.execute(text(
                    "INSERT INTO case_algorithm_params "
                    "  (algorithm_type, param_code, param_name, label, param_type, scope, "
                    "   required, default_value, help_text, ui_order, hidden, deleted, "
                    "   min_value, max_value, step, unit, annotation_code, field_path, "
                    "   created_at, updated_at) "
                    "VALUES "
                    "  (:at, :pc, :pn, :lb, :pt, :scope, "
                    "   :req, :dv, :ht, :uo, :hid, :del, "
                    "   :mn, :mx, :st, :un, :ac, :fp, "
                    "   NOW(), NOW())"
                ), {
                    'at': algo_type, 'pc': param_code, 'pn': param_name, 'lb': label,
                    'pt': param_type, 'scope': scope, 'req': required, 'dv': default_value,
                    'ht': help_text, 'uo': ui_order, 'hid': hidden, 'del': deleted,
                    'mn': min_value, 'mx': max_value, 'st': step, 'un': unit,
                    'ac': effective_ann_code, 'fp': effective_f_path
                })
                print(f"  + {param_code} (scope={scope}, ann_code={effective_ann_code}, field_path={effective_f_path})")
                inserted_count += 1

        print(f"  插入 {inserted_count} 条，跳过/更新 {skipped_count} 条")

        # 清理不在当前定义里的旧残留字段（软删除）
        valid_codes = [p[1] for p in case_params]  # p[1] = param_code
        placeholders = ','.join([f"'{c}'" for c in valid_codes])
        deleted_old = conn.execute(text(
            f"UPDATE case_algorithm_params SET deleted = true, updated_at = NOW() "
            f"WHERE algorithm_type = 'voice_llm' AND deleted = false "
            f"AND param_code NOT IN ({placeholders})"
        )).rowcount
        if deleted_old:
            print(f"  清理 {deleted_old} 条旧残留字段（NOT IN {valid_codes}）")

        # ============================================================
        # Step 4: 注册设备输出字段（algorithm_device_params）
        # ============================================================
        print("\n=== Step 4: 注册 voice_llm 设备输出字段 (algorithm_device_params) ===")

        # 清理旧的 asr_text/asr_rttm/asr_stm（voice_llm 不使用这些字段）
        obsolete_device_codes = ['asr_text', 'asr_rttm', 'asr_stm']
        deleted_dev = conn.execute(text(
            "DELETE FROM algorithm_device_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(obsolete_device_codes)}).rowcount
        if deleted_dev:
            print(f"  清理 {deleted_dev} 条旧设备输出字段（asr_text/asr_rttm/asr_stm）")

        device_params = [
            ('voice_llm', 'record_path', '录屏文件', 'text', 'output', False, None, 10, False),
            ('voice_llm', 'question', '用户提问', 'text', 'output', False, None, 11, False),
            ('voice_llm', 'answer', '小艺回答', 'text', 'output', False, None, 12, False),
            ('voice_llm', 'device_status', '设备状态', 'json', 'output', False, None, 13, False),
        ]

        dev_inserted = 0
        dev_skipped = 0
        for dp in device_params:
            (algo_type, param_code, param_name, param_type, direction,
             required, default_value, ui_order, hidden) = dp

            existing = conn.execute(text(
                "SELECT id FROM algorithm_device_params "
                "WHERE algorithm_type = :at AND param_code = :pc AND direction = :dir"
            ), {'at': algo_type, 'pc': param_code, 'dir': direction}).fetchone()

            if existing:
                print(f"  - {param_code} 已存在")
                dev_skipped += 1
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

        print(f"  插入 {dev_inserted} 条，跳过 {dev_skipped} 条")

        # ============================================================
        # Step 5: 注册 API 输入/输出字段（algorithm_api_params）
        # ============================================================
        print("\n=== Step 5: 注册 voice_llm API 字段 (algorithm_api_params) ===")

        api_params = [
            # 输入字段（仅算法本身的输入，会话协议字段由执行引擎管理）
            ('voice_llm', 'input_text', '输入文本', 'text', 'input', False, None, 10, False),
            ('voice_llm', 'input_audio', '输入音频', 'audio_file', 'input', False, None, 11, False),
            # 输出字段（仅算法本身的输出，response_latency 等由执行引擎采集）
            ('voice_llm', 'response_audio', '回复音频', 'audio_file', 'output', False, None, 21, False),
        ]

        # 清理旧的 llm_response 字段（voice_llm 不使用此 API 输出字段，由设备驱动 answer 提供）
        obsolete_api_codes = ['llm_response']
        deleted_api = conn.execute(text(
            "DELETE FROM algorithm_api_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(obsolete_api_codes)}).rowcount
        if deleted_api:
            print(f"  清理 {deleted_api} 条旧 API 输出字段（llm_response）")

        api_inserted = 0
        api_skipped = 0
        for ap in api_params:
            (algo_type, param_code, param_name, param_type, direction,
             required, default_value, ui_order, hidden) = ap

            existing = conn.execute(text(
                "SELECT id FROM algorithm_api_params "
                "WHERE algorithm_type = :at AND param_code = :pc AND direction = :dir"
            ), {'at': algo_type, 'pc': param_code, 'dir': direction}).fetchone()

            if existing:
                print(f"  - {param_code} 已存在")
                api_skipped += 1
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

        print(f"  插入 {api_inserted} 条，跳过 {api_skipped} 条")

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

        ref_params = [
            ('voice_llm', 'correct_answer', '参考答案', 'text',
             'correct_answer', 'text', 'correct_answer', 'join',
             'LLM Judge 评估的标准答案，从音频标注提取或手动填写'),
            ('voice_llm', 'query', '用户提问', 'text',
             'query', 'text', 'query', 'join',
             '用户提问文本，从音频标注提取或手动填写'),
        ]

        ref_inserted = 0
        ref_skipped = 0
        for rp in ref_params:
            (algo_type, code, name, param_type,
             annotation_code, annotation_format, field_path, merge_mode,
             help_text) = rp

            existing = conn.execute(text(
                "SELECT id FROM algorithm_reference_params "
                "WHERE algorithm_type = :at AND code = :code"
            ), {'at': algo_type, 'code': code}).fetchone()

            if existing:
                print(f"  - {code} 已存在")
                ref_skipped += 1
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

        print(f"  插入 {ref_inserted} 条，跳过 {ref_skipped} 条")

        # ============================================================
        # Step 7: 注册参数映射（param_mappings）
        # ============================================================
        print("\n=== Step 7: 注册 voice_llm 参数映射 (param_mappings) ===")

        mappings = [
            # 参考答案（从音频标注提取）
            ('voice_llm', 'reference', 'output', 'correct_answer', 'asr_ref', 'none'),
            # 用户提问（从音频标注提取）
            ('voice_llm', 'reference', 'output', 'query', 'query_ref', 'none'),
            # 设备输出映射
            ('voice_llm', 'device', 'output', 'answer', 'output_text', 'none'),
            ('voice_llm', 'device', 'output', 'question', 'question_text', 'none'),
            ('voice_llm', 'device', 'output', 'record_path', 'record_path', 'none'),
        ]

        map_inserted = 0
        map_skipped = 0
        for m in mappings:
            (algo_type, source, source_direction, source_param, target_param,
             transform_type) = m

            existing = conn.execute(text(
                "SELECT id FROM param_mappings "
                "WHERE algorithm_type = :at AND source = :src "
                "AND source_param = :sp AND dimension_id IS NULL"
            ), {'at': algo_type, 'src': source, 'sp': source_param}).fetchone()

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
                    "  (:at, :src, :sd, :sp, NULL, :tp, :tt, false, NOW(), NOW())"
                ), {
                    'at': algo_type, 'src': source, 'sd': source_direction,
                    'sp': source_param, 'tp': target_param, 'tt': transform_type
                })
                print(f"  + {source}.{source_param} → {target_param}")
                map_inserted += 1

        print(f"  插入 {map_inserted} 条，跳过 {map_skipped} 条")

        # ============================================================
        # Step 8: 注册算法-维度关联（algorithm_dimension_relations）
        # ============================================================
        print("\n=== Step 8: 注册 voice_llm 算法-维度关联 (algorithm_dimension_relations) ===")

        dim_rows = conn.execute(text(
            "SELECT id, name FROM dimensions "
            "WHERE task_type_code = 'llm_judge' AND deleted = FALSE"
        )).fetchall()

        rel_inserted = 0
        rel_skipped = 0
        if not dim_rows:
            print("  未找到 task_type_code='llm_judge' 的维度，跳过")
        else:
            for dim_id, dim_name in dim_rows:
                existing = conn.execute(text(
                    "SELECT id FROM algorithm_dimension_relations "
                    "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
                ), {'did': dim_id}).fetchone()

                if existing:
                    print(f"  - 维度 '{dim_name}' (id={dim_id}) 关联已存在")
                    rel_skipped += 1
                else:
                    conn.execute(text(
                        "INSERT INTO algorithm_dimension_relations "
                        "  (algorithm_type, dimension_id, is_active, deleted, "
                        "   created_at, updated_at) "
                        "VALUES "
                        "  ('voice_llm', :did, TRUE, FALSE, NOW(), NOW())"
                    ), {'did': dim_id})
                    print(f"  + 关联维度 '{dim_name}' (id={dim_id})")
                    rel_inserted += 1

        print(f"  插入 {rel_inserted} 条，跳过 {rel_skipped} 条")

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
    print("2. 用例参数（scope=common/api/e2e，含 min/max/step/unit）")
    print("3. 4 个设备输出字段（record_path/question/answer/device_status）")
    print("4. 3 个 API 输入/输出字段（会话协议字段由执行引擎管理）")
    print("5. 2 个参考参数定义（correct_answer/query，从音频标注提取）")
    print("6. 5 条参数映射（reference/device → evaluation input）")
    print("7. 算法-维度关联（llm_judge 维度）")
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
