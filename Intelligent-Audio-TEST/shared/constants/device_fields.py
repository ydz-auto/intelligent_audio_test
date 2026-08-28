"""设备/API 原始结果字段映射"""

# 设备原始结果字段 → 字段类型
DEVICE_FIELDS = {
    'start_ms': 'timestamp',
    'end_ms': 'timestamp',
    'first_frame_ms': 'timestamp',
    'pcm_first_ms': 'timestamp',
    'record_file': 'audio_file',
    'record_path': 'audio_file',
    'user_wav': 'audio_file',
    'ai_wav': 'audio_file',
    'wav_path': 'audio_file',
    'question': 'text',
    'answer': 'text',
    'success': 'boolean',
    'message': 'text',
}
