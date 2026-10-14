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


def strip_wav_container(data: bytes) -> bytes:
    """剥除 RIFF/WAVE 容器头返回 PCM 载荷；非容器字节原样返回。

    供应商输出音频的线上形态存在两种可能：裸 PCM 或 WAV 容器（如 volc_ast
    请求声明 target_audio.format='wav'，响应 data 的实际格式未经实机确认）。
    收集时逐块剥头，保证归档是单头 wav——二次包装会落档「WAV 套 WAV」，
    读侧单次剥头后内层 44B 头按样本解析，短片段 RMS 严重失真（INT-300
    审计缺陷 2 同款病根）。流式容器的 data chunk 声明长度可能未定
    （0xFFFFFFFF），此时取声明头之后的全部字节为载荷。
    """
    if len(data) >= 12 and data[0:4] == b'RIFF' and data[8:12] == b'WAVE':
        pos = 12
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos + 4]
            chunk_size = int.from_bytes(data[pos + 4:pos + 8], 'little')
            if chunk_id == b'data':
                end = pos + 8 + chunk_size
                if end <= len(data):
                    return data[pos + 8:end]
                return data[pos + 8:]
            pos += 8 + chunk_size + (chunk_size & 1)
    return data


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
