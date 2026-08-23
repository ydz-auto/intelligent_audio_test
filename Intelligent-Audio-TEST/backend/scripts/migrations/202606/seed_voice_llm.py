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
        # Step 3: 清理用例专属参数（case_algorithm_params）
        # ============================================================
        print("\n=== Step 3: 清理 voice_llm 用例参数 (case_algorithm_params) ===")

        # 数据库中 voice_llm 的 case_algorithm_params 全部已软删除
        # 用例参数已迁移到其他表管理，这里仅做清理
        deleted_count = conn.execute(text(
            "UPDATE case_algorithm_params SET deleted = true, updated_at = NOW() "
            "WHERE algorithm_type = 'voice_llm' AND deleted = false"
        )).rowcount
        if deleted_count:
            print(f"  清理 {deleted_count} 条残留用例参数（已迁移到其他表管理）")
        else:
            print("  无残留用例参数需要清理")

        # ============================================================
        # Step 4: 注册设备输出字段（algorithm_device_params）
        # ============================================================
        print("\n=== Step 4: 注册 voice_llm 设备输出字段 (algorithm_device_params) ===")

        # 清理旧的 asr_text/asr_rttm/asr_stm/record_path/device_status（voice_llm 不使用这些字段）
        obsolete_device_codes = ['asr_text', 'asr_rttm', 'asr_stm', 'record_path', 'device_status']
        deleted_dev = conn.execute(text(
            "DELETE FROM algorithm_device_params "
            "WHERE algorithm_type = 'voice_llm' AND param_code IN :codes"
        ), {'codes': tuple(obsolete_device_codes)}).rowcount
        if deleted_dev:
            print(f"  清理 {deleted_dev} 条旧设备输出字段（asr_text/asr_rttm/asr_stm/record_path/device_status）")

        device_params = [
            ('voice_llm', 'start_ms', '输入音频开始播放时间', 'timestamp', 'output', False, None, 0, False),
            ('voice_llm', 'end_ms', '输入音频停止播放时间', 'timestamp', 'output', False, None, 0, False),
            ('voice_llm', 'first_frame_ms', '录屏开始世界时间', 'timestamp', 'output', False, None, 0, False),
            ('voice_llm', 'wav_path', '录音文件', 'text', 'output', False, None, 0, False),
            ('voice_llm', 'input_text', '录屏文件', 'text', 'output', False, None, 10, False),
            ('voice_llm', 'question', '用户提问', 'text', 'output', False, None, 11, False),
            ('voice_llm', 'answer', '小艺回答', 'text', 'output', False, None, 12, False),
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
            ('voice_llm', 'pause', '停顿点', 'json',
             'pause', 'json', 'pause', 'first',
             '停顿点'),
            ('voice_llm', 'input_lastword', '输入末尾词时间戳', 'json',
             'input_lastword', 'json', 'input_lastword', 'first',
             '输入末尾词时间戳'),
            # 打断评估（interruption_metrics 维度）参考参数
            # is_return_to_topic: 每轮标注"是否回到原话题"，从音频标注 segments[].is_return_to_topic 派生
            # 经 source='reference' 映射按轮传给 eval（_build_rounds_list 读取）
            ('voice_llm', 'is_return_to_topic', '是否回到原话题', 'boolean',
             'is_return_to_topic', 'boolean', 'segments[].is_return_to_topic', 'first',
             '标注该轮是否回到原话题（用户打断后模型是否拉回原话题），在音频标注编辑器按轮标记，供 interruption_metrics 评估'),
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
        # Step 7: 清理无维度参数映射（param_mappings where dimension_id IS NULL）
        # ============================================================
        print("\n=== Step 7: 清理 voice_llm 无维度参数映射 (param_mappings) ===")

        # 数据库中 dimension_id IS NULL 的 param_mappings 全部已软删除
        # 维度级映射由各维度种子脚本管理（seed_xiaoyi_dimensions / seed_llm_judge_dimension）
        deleted_maps = conn.execute(text(
            "UPDATE param_mappings SET deleted = true, updated_at = NOW() "
            "WHERE algorithm_type = 'voice_llm' AND dimension_id IS NULL AND deleted = false"
        )).rowcount
        if deleted_maps:
            print(f"  清理 {deleted_maps} 条无维度参数映射（已由维度级映射管理）")
        else:
            print("  无无维度参数映射需要清理")

        # ============================================================
        # Step 8: 注册算法-维度关联（algorithm_dimension_relations）
        # ============================================================
        print("\n=== Step 8: 注册 voice_llm 算法-维度关联 (algorithm_dimension_relations) ===")

        dim_rows = conn.execute(text(
            "SELECT id, name FROM dimensions "
            "WHERE deleted = FALSE ORDER BY id"
        )).fetchall()

        rel_inserted = 0
        rel_skipped = 0
        if not dim_rows:
            print("  未找到维度，跳过")
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
                        "  (algorithm_type, dimension_id, is_default, weight, deleted, "
                        "   created_at, updated_at) "
                        "VALUES "
                        "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
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
    print("2. 清理用例参数（case_algorithm_params，已迁移到其他表管理）")
    print("3. 7 个设备输出字段（start_ms/end_ms/first_frame_ms/wav_path/input_text/question/answer）")
    print("4. 3 个 API 输入/输出字段（会话协议字段由执行引擎管理）")
    print("5. 4 个参考参数定义（correct_answer/query/pause/input_lastword，从音频标注提取）")
    print("6. 清理无维度参数映射（已由维度级映射管理）")
    print("7. 算法-维度关联（所有维度）")
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
