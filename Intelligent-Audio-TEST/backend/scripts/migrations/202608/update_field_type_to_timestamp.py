# -*- coding: utf-8 -*-
"""将绝对时间戳类型的参数 field_type 从 number/text 更新为 timestamp

涉及的 param_code 均为绝对 Unix 毫秒时间戳（非时延/时长/间隙）：
  - start_ms, end_ms, pcm_first_ms, pcm_first_ms_out
  - noise_start_ms, noise_end_ms
  - model_recovery_abs_ms
  - tl_user_last_word_end_ms, tl_ai_first_word_start_ms
  - first_frame_ms
"""
import psycopg2

conn = psycopg2.connect(
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)
cur = conn.cursor()

# evaluation_dimension_params 表
cur.execute("""
    UPDATE evaluation_dimension_params
    SET field_type = 'timestamp'
    WHERE param_code IN (
        'start_ms', 'end_ms', 'pcm_first_ms', 'pcm_first_ms_out',
        'noise_start_ms', 'noise_end_ms',
        'model_recovery_abs_ms',
        'tl_user_last_word_end_ms', 'tl_ai_first_word_start_ms'
    )
      AND deleted = false
""")
print(f"evaluation_dimension_params: updated {cur.rowcount} rows")

# algorithm_device_params 表 (voice_llm 的 start_ms/end_ms/first_frame_ms)
cur.execute("""
    UPDATE algorithm_device_params
    SET param_type = 'timestamp'
    WHERE param_code IN ('start_ms', 'end_ms', 'first_frame_ms')
      AND deleted = false
""")
print(f"algorithm_device_params: updated {cur.rowcount} rows")

conn.commit()
conn.close()
