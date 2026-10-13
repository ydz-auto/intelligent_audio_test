# -*- coding: utf-8 -*-
"""AI 输出音频归档（INT-300）：adapter 侧收集的被测 API 输出音频统一落存储。

被测 API 返回的输出音频（PCM 字节）经统一存储层归档，返回带 scheme 前缀的
存储引用（raw_response.output_audio_path 契约）。执行侧（api_test_service）
按该引用经同一存储层读回字节，计算输出侧实测口径 ai_output_rms_dbfs /
ai_output_spl_db，与 Realtime（websocket_api）口径对称（三口径对称验证 F3）。

归档失败返回 None（输出侧证据缺失不应导致轮次失败，被测请求本身已成功）。
"""
import logging

logger = logging.getLogger(__name__)


def save_output_audio(pcm: bytes, task_id, session_id: str = '',
                      round_number: int = 0, sample_rate: int = 24000) -> 'str | None':
    """输出音频 PCM(s16) → wav → 存储归档，返回存储引用（失败返回 None）。

    与 api_test_service RealtimeSessionExecutor._save_ai_audio 同语义
    （audios/{task}/adapter 归档区），容器统一 wav 便于读侧探测格式。
    """
    if not pcm:
        return None
    try:
        import io
        import time as _time
        import wave

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sample_rate))
            w.writeframes(pcm)
        from shared.infrastructure.storage import storage
        key = f"{task_id}/{session_id or 'adapter'}/adapter_output/" \
              f"ai_output_{int(round_number)}_{int(_time.time() * 1000)}.wav"
        return storage.save_bytes(buf.getvalue(), 'audios', key,
                                  content_type='audio/wav') or None
    except Exception:
        logger.warning("AI 输出音频归档失败（输出侧证据缺失，不影响请求结果）",
                       exc_info=True)
        return None
