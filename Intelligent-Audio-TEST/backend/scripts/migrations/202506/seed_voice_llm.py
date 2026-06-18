# -*- coding: utf-8 -*-
"""
voice_llm 算法种子数据

功能：
1. 注册 voice_llm 算法定义（algorithm_definitions）
2. 注册 voice_llm 用例专属参数（case_algorithm_params），含 scope 字段
3. 注册 voice_llm 设备输出字段（algorithm_device_params）
4. 注册 voice_llm API 输入/输出字段（algorithm_api_params）

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

        case_params = [
            # (algo_type, param_code, param_name, label, param_type, scope,
            #  required, default_value, help_text, ui_order, hidden, deleted,
            #  min_value, max_value, step, unit)

            # --- 通用参数（scope=common） ---
            ('voice_llm', 'promptAudioId', 'Prompt 音频', 'Prompt 音频', 'audio_select', 'common',
             False, None, '在干声播放之前播放的引导音频', 30, False, False,
             None, None, None, None),

            # --- E2E 专用参数（scope=e2e） ---
            ('voice_llm', 'interferers', '干扰人列表', '干扰人', 'interferer_list', 'e2e',
             False, '[]', '干扰人配置列表，支持多路独立干扰', 20, False, False,
             None, None, None, None),
            ('voice_llm', 'railDistance', '导轨距离(cm)', '导轨距离', 'slider', 'e2e',
             False, None, '导轨距离，本轮结束后自动复位。不填则不控制导轨', 40, False, False,
             10, 200, 5, 'cm'),
            ('voice_llm', 'volumeLevel', '被测设备音量', '设备音量', 'slider', 'e2e',
             False, None, '被测设备音量(0-100)，本轮结束后自动恢复。不填则不控制音量', 41, False, False,
             0, 100, 1, None),
            ('voice_llm', 'voiceprintEnabled', '声纹注册', '声纹注册', 'switch', 'e2e',
             False, 'false', '是否在本轮播放声纹注册音频', 50, False, False,
             None, None, None, None),
            ('voice_llm', 'voiceprintAudioId', '声纹注册音频', '声纹音频', 'audio_select', 'e2e',
             False, None, '声纹注册音频文件', 51, False, False,
             None, None, None, None),
            ('voice_llm', 'voiceprintPlaybackDeviceId', '声纹播放设备', '播放设备', 'device_select', 'e2e',
             False, None, '声纹注册音频播放设备', 52, False, False,
             None, None, None, None),
            ('voice_llm', 'voiceprintSpl', '声纹播放声压级', '声压级', 'number', 'e2e',
             False, '70.0', '声纹注册音频播放声压级', 53, False, False,
             20, 100, 1, 'dB'),
            ('voice_llm', 'voiceprintWaitTime', '声纹等待时间(秒)', '等待时间', 'number', 'e2e',
             False, '5.0', '声纹注册后等待时间', 54, False, False,
             0, 60, 1, 's'),
            ('voice_llm', 'interruptionEnabled', '打断检测', '打断检测', 'switch', 'e2e',
             False, 'false', '是否启用全双工打断检测', 60, False, False,
             None, None, None, None),
            ('voice_llm', 'interruptionSensitivity', '打断灵敏度', '灵敏度', 'slider', 'e2e',
             False, '0.5', '打断检测灵敏度(0~1)', 61, False, False,
             0, 1, 0.1, None),

            # --- API 专用参数（scope=api） ---
            ('voice_llm', 'inputText', '输入文本', '输入文本', 'text', 'api',
             False, None, '发送给 API 的文本内容（可与输入音频共存）', 70, False, False,
             None, None, None, None),
            ('voice_llm', 'inputAudio', '输入音频', '输入音频', 'audio_select', 'api',
             False, None, '发送给 API 的音频文件（可与输入文本共存）', 71, False, False,
             None, None, None, None),
        ]

        inserted_count = 0
        skipped_count = 0
        for p in case_params:
            (algo_type, param_code, param_name, label, param_type, scope,
             required, default_value, help_text, ui_order, hidden, deleted,
             min_value, max_value, step, unit) = p

            existing = conn.execute(text(
                "SELECT id FROM case_algorithm_params "
                "WHERE algorithm_type = :at AND param_code = :pc"
            ), {'at': algo_type, 'pc': param_code}).fetchone()

            if existing:
                conn.execute(text(
                    "UPDATE case_algorithm_params SET "
                    "  scope = :scope, min_value = :mn, max_value = :mx, "
                    "  step = :st, unit = :un "
                    "WHERE id = :id"
                ), {'scope': scope, 'mn': min_value, 'mx': max_value,
                    'st': step, 'un': unit, 'id': existing[0]})
                print(f"  - {param_code} 已存在，已更新 scope/min/max/step/unit")
                skipped_count += 1
            else:
                conn.execute(text(
                    "INSERT INTO case_algorithm_params "
                    "  (algorithm_type, param_code, param_name, label, param_type, scope, "
                    "   required, default_value, help_text, ui_order, hidden, deleted, "
                    "   min_value, max_value, step, unit, created_at, updated_at) "
                    "VALUES "
                    "  (:at, :pc, :pn, :lb, :pt, :scope, "
                    "   :req, :dv, :ht, :uo, :hid, :del, "
                    "   :mn, :mx, :st, :un, NOW(), NOW())"
                ), {
                    'at': algo_type, 'pc': param_code, 'pn': param_name, 'lb': label,
                    'pt': param_type, 'scope': scope, 'req': required, 'dv': default_value,
                    'ht': help_text, 'uo': ui_order, 'hid': hidden, 'del': deleted,
                    'mn': min_value, 'mx': max_value, 'st': step, 'un': unit
                })
                print(f"  + {param_code} (scope={scope})")
                inserted_count += 1

        print(f"  插入 {inserted_count} 条，跳过/更新 {skipped_count} 条")

        # ============================================================
        # Step 4: 注册设备输出字段（algorithm_device_params）
        # ============================================================
        print("\n=== Step 4: 注册 voice_llm 设备输出字段 (algorithm_device_params) ===")

        device_params = [
            ('voice_llm', 'asr_text', '识别文本', 'text', 'output', False, None, 10, False),
            ('voice_llm', 'asr_rttm', '说话人标注', 'rttm', 'output', False, None, 11, False),
            ('voice_llm', 'asr_stm', '分段标注', 'stm', 'output', False, None, 12, False),
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
            ('voice_llm', 'llm_response', 'LLM 回复文本', 'text', 'output', False, None, 20, False),
            ('voice_llm', 'response_audio', '回复音频', 'audio_file', 'output', False, None, 21, False),
        ]

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
    print("2. 13 个用例参数（scope=common/api/e2e，含 min/max/step/unit）")
    print("3. 4 个设备输出字段")
    print("4. 4 个 API 输入/输出字段（会话协议字段由执行引擎管理）")
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
