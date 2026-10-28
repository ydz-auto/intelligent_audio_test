# -*- coding: utf-8 -*-
"""合成音频方案离线测试（不依赖真机/平台播放）。

覆盖：
- 按播放时间戳把文件放到 user_wav 的正确偏移
- 默认不拼入 noise、拼入 interferer
- AI wav 对齐到同一 T0（正向偏移/补静音）
- _synthesize_from_played 端到端：user/ai 同时长、可重复调用不漂移
- e2e_executor 把播放文件与时间戳透传给驱动
"""
import os
import struct
import time
import wave

import pytest


RATE = 48000


def _make_driver():
    from backend.utils.device_driver.android_doubaochat import DoubaoAndroidChat

    driver = DoubaoAndroidChat()
    driver._log = lambda **kw: None
    return driver


def _write_tone(path, total_s=2.0, tone_start_s=0.0, tone_len_s=1.0,
                amplitude=10000):
    """写 48k/16bit/双声道 wav；指定区间为方波，其余静音。"""
    frames = int(round(total_s * RATE))
    start = int(round(tone_start_s * RATE))
    end = start + int(round(tone_len_s * RATE))
    buf = bytearray()
    for i in range(frames):
        if start <= i < end and (i // 24) % 2 == 0:
            sample = amplitude
        elif start <= i < end:
            sample = -amplitude
        else:
            sample = 0
        buf += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    return str(path)


def _read_left(path):
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return list(struct.unpack("<%dh" % (len(raw) // 2), raw))[::2]


def _duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _onset(path, threshold=100):
    for i, s in enumerate(_read_left(path)):
        if abs(s) > threshold:
            return i / float(RATE)
    return None


def _max_abs(path, start_s, end_s):
    data = _read_left(path)
    seg = data[int(start_s * RATE):int(end_s * RATE)]
    return max((abs(s) for s in seg), default=0)


def _rms(path, start_s, end_s):
    data = _read_left(path)
    seg = data[int(start_s * RATE):int(end_s * RATE)]
    if not seg:
        return 0.0
    return (sum(s * s for s in seg) / len(seg)) ** 0.5


# ──────────────────────────────────────────────
#  基础合成
# ──────────────────────────────────────────────

def test_synthesize_places_tone_at_playback_offset(tmp_path):
    src = _write_tone(tmp_path / "user.wav", total_s=1.0, tone_len_s=1.0)
    out = str(tmp_path / "user_synth.wav")
    driver = _make_driver()

    result = driver._synthesize_user_wav(
        [{"file_path": src, "start_ms": 2000, "end_ms": 3000, "audio_type": "dry"}],
        out, t0_ms=1000, duration_ms=4000,
    )

    assert result == out
    assert abs(_duration(out) - 4.0) < 0.01
    # start_ms - t0_ms = 1s（tone 在输出 1s 处）
    assert abs(_onset(out) - 1.0) < 0.02
    assert _max_abs(out, 2.2, 3.8) < 50


def test_synthesize_skips_noise_but_keeps_interferer(tmp_path):
    noise = _write_tone(tmp_path / "noise.wav", total_s=0.5, tone_len_s=0.5)
    interferer = _write_tone(tmp_path / "interferer.wav", total_s=0.5, tone_len_s=0.5)
    out = str(tmp_path / "user_synth.wav")
    driver = _make_driver()

    driver._synthesize_user_wav(
        [
            {"file_path": noise, "start_ms": 200, "end_ms": 700, "audio_type": "noise"},
            {"file_path": interferer, "start_ms": 1500, "end_ms": 2000,
             "audio_type": "interferer"},
        ],
        out, t0_ms=0, duration_ms=3000,
    )

    # noise 在 0.2~0.7s，默认不拼入 -> 静音
    assert _max_abs(out, 0.2, 0.7) < 50
    # interferer 在 1.5s -> 拼入
    assert abs(_onset(out) - 1.5) < 0.02


def test_synthesize_returns_none_without_usable_audio(tmp_path):
    driver = _make_driver()
    out = str(tmp_path / "user_synth.wav")
    assert driver._synthesize_user_wav([], out) is None
    assert driver._synthesize_user_wav(
        [{"file_path": str(tmp_path / "nope.wav"), "start_ms": 0}], out) is None


# ──────────────────────────────────────────────
#  AI 对齐
# ──────────────────────────────────────────────

def test_align_ai_wav_shifts_to_t0_and_pads(tmp_path):
    ai = _write_tone(tmp_path / "ai.wav", total_s=5.0, tone_start_s=3.0,
                     tone_len_s=0.5)
    out = str(tmp_path / "ai_aligned.wav")
    driver = _make_driver()
    ai_birth = 1_700_000_000.0
    t0_ms = int((ai_birth - 1.0) * 1000)

    result = driver._align_ai_wav_to_timeline(
        ai, out, t0_ms=t0_ms, duration_ms=6000, ai_birth=ai_birth,
    )

    assert result == out
    assert abs(_duration(out) - 6.0) < 0.01
    # AI 文件内 3s 的 tone，出生时刻比 T0 晚 1s -> 输出 4s
    assert abs(_onset(out) - 4.0) < 0.02
    assert _max_abs(out, 0.0, 3.8) < 50


def test_synthesize_from_played_end_to_end_and_idempotent(tmp_path):
    ai = _write_tone(tmp_path / "case_r0_ai.wav", total_s=5.0,
                     tone_start_s=3.0, tone_len_s=0.5)
    user = _write_tone(tmp_path / "case_r0_user.wav", total_s=2.0,
                       tone_len_s=2.0)
    driver = _make_driver()
    birth = 1_700_000_000.0
    driver._audio_paths = {"ai": ai}
    driver._ai_capture_path = ai
    driver._ai_capture_birth_ts = birth
    driver._audio_start_ts = {"ai": birth}
    played = [{"file_path": user, "start_ms": int((birth + 1.0) * 1000),
               "end_ms": int((birth + 3.0) * 1000), "audio_type": "dry"}]

    assert driver._synthesize_from_played("sn", played) is True
    user_out = driver._audio_paths["user"]
    ai_out = driver._audio_paths["ai"]
    assert user_out.endswith("case_r0_user_synth.wav")
    assert ai_out.endswith("case_r0_ai_aligned.wav")
    assert abs(_duration(user_out) - _duration(ai_out)) < 0.02
    assert abs(_onset(user_out) - 1.0) < 0.02
    assert abs(_onset(ai_out) - 3.0) < 0.02

    # 第二次调用：必须用原始 AI 文件，不能生成 _ai_aligned_ai_aligned.wav
    assert driver._synthesize_from_played("sn", played) is True
    assert driver._audio_paths["user"] == user_out
    assert driver._audio_paths["ai"] == ai_out
    assert not os.path.exists(str(tmp_path / "case_r0_ai_aligned_ai_aligned.wav"))
    assert abs(_duration(user_out) - _duration(ai_out)) < 0.02


def test_synthesize_from_played_requires_ai(tmp_path):
    driver = _make_driver()
    driver._audio_paths = {}
    driver._ai_capture_path = None
    driver._audio_start_ts = {}
    played = [{"file_path": _write_tone(tmp_path / "u.wav"), "start_ms": 1000,
               "end_ms": 2000, "audio_type": "dry"}]
    assert driver._synthesize_from_played("sn", played) is False


# ──────────────────────────────────────────────
#  引擎透传
# ──────────────────────────────────────────────

def test_executor_collects_played_audios_with_file_path(tmp_path):
    from backend.services.execution.e2e_executor import E2EExecutor

    audio = _write_tone(tmp_path / "play.wav")
    executor = E2EExecutor.__new__(E2EExecutor)
    executor._playback_timestamps = {}
    play_result = {
        "audio_timelines": [{
            "config": {"audio_id": 7, "play_order": 0},
            "audio_type": "dry",
            "file": audio,
            "playback_start_time_ms": 1000,
            "playback_end_time_ms": 2000,
            "actual_play_time": time.time(),
        }]
    }

    executor._collect_playback_timestamps(1, play_result, None)

    ts = executor._playback_timestamps[1]
    assert ts["current_round_start_ms"] == 1000
    assert ts["current_round_end_ms"] == 2000
    assert ts["current_round_played_audios"] == [{
        "audio_id": 7, "audio_type": "dry", "file_path": audio,
        "start_ms": 1000, "end_ms": 2000,
    }]
    assert ts["audio_play_times"][0]["file_path"] == audio


# ──────────────────────────────────────────────
#  时延字段
# ──────────────────────────────────────────────

def test_turn_latency_ignores_noise_and_uses_question_window():
    driver = _make_driver()
    played = [
        {"audio_type": "noise", "start_ms": 1000, "end_ms": 9000},
        {"audio_type": "dry", "start_ms": 2000, "end_ms": 5000},
        {"audio_type": "interferer", "start_ms": 3000, "end_ms": 7000},
    ]
    lat = driver._compute_turn_latency(played, ai_start_ms=8200)
    assert lat["question_start_ms"] == 2000
    assert lat["question_end_ms"] == 7000
    assert lat["ai_start_ms"] == 8200
    assert lat["question_to_ai_ms"] == 6200
    assert lat["question_end_to_ai_ms"] == 1200
    assert lat["played_count"] == 3


def test_turn_latency_falls_back_to_round_window():
    driver = _make_driver()
    lat = driver._compute_turn_latency([], fallback_start_ms=1000,
                                       fallback_end_ms=4000,
                                       ai_start_ms=6500)
    assert lat["question_start_ms"] == 1000
    assert lat["question_end_ms"] == 4000
    assert lat["question_to_ai_ms"] == 5500
    assert lat["question_end_to_ai_ms"] == 2500


def test_turn_latency_without_ai_start_keeps_question_only():
    driver = _make_driver()
    lat = driver._compute_turn_latency(
        [{"audio_type": "dry", "start_ms": 1000, "end_ms": 2000}],
        ai_start_ms=None,
    )
    assert lat["question_start_ms"] == 1000
    assert lat["question_end_ms"] == 2000
    assert lat["ai_start_ms"] is None
    assert lat["question_to_ai_ms"] is None
    assert lat["question_end_to_ai_ms"] is None
