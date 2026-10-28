# -*- coding: utf-8 -*-
"""豆包 Android 语音通话驱动离线回归测试。

不依赖真机：覆盖可离线验证的纯逻辑与状态机，
- wav 解析 / 尾部 RMS / 语音扫描（回复完成检测的信号层）
- 录屏拉取的跨用例防护（文件名一致性 + 用例纪元 + *.part 原子替换）
- initialize 跨用例状态复位与“清聊天记录/清设备录屏目录”步骤真实发生
- pre_process 的 case 模式非首轮短路（不动通话/录屏，只重启本轮音频抓取）
- get_results 的 case 模式录屏进行中分支 / mock 分支
- 问答气泡提取的左右分栏启发式
"""
import os
import struct
import wave

import pytest


def _make_driver():
    from backend.utils.device_driver.android_doubaochat import DoubaoAndroidChat

    driver = DoubaoAndroidChat()
    driver._log = lambda **kw: None
    return driver


def _write_wav(path, seconds=2.0, rate=48000, channels=2, tone_seconds=1.0,
               amplitude=5000):
    """写一个「前面静音、最后 tone_seconds 秒方波」的 16bit wav。"""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        total = int(seconds * rate)
        tone_frames = int(tone_seconds * rate)
        frames = bytearray()
        for i in range(total):
            if i < total - tone_frames:
                sample = 0
            else:
                sample = amplitude if (i // 24) % 2 == 0 else -amplitude
            for _ in range(channels):
                frames += struct.pack("<h", sample)
        w.writeframes(bytes(frames))


# ──────────────────────────────────────────────
#  wav 解析 / RMS / 语音扫描
# ──────────────────────────────────────────────

def test_wav_info_parses_scrcpy_like_header(tmp_path):
    path = tmp_path / "a.wav"
    _write_wav(path)
    info = _make_driver()._wav_info(str(path))
    assert info["rate"] == 48000
    assert info["channels"] == 2
    assert info["width"] == 2
    assert info["data_offset"] > 0


def test_tail_rms_detects_voice_in_last_second(tmp_path):
    path = tmp_path / "voice.wav"
    _write_wav(path, seconds=3.0, tone_seconds=1.0)
    driver = _make_driver()
    rms = driver._read_tail_rms(str(path), seconds=1.0)
    assert rms is not None and rms > driver.RMS_THRESHOLD


def test_tail_rms_silence_file_is_low(tmp_path):
    path = tmp_path / "silence.wav"
    _write_wav(path, seconds=2.0, tone_seconds=0.0)
    driver = _make_driver()
    rms = driver._read_tail_rms(str(path), seconds=1.0)
    assert rms is not None and rms < driver.RMS_THRESHOLD


def test_tail_rms_missing_or_empty_file_returns_none(tmp_path):
    driver = _make_driver()
    assert driver._read_tail_rms(str(tmp_path / "nope.wav")) is None
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert driver._read_tail_rms(str(empty)) is None


def test_scan_wav_for_speech_finds_recent_voice(tmp_path):
    path = tmp_path / "scan.wav"
    _write_wav(path, seconds=4.0, tone_seconds=1.0)
    driver = _make_driver()
    assert driver._scan_wav_for_speech(str(path), seconds=2.0) is True
    # 全静音文件应判无语音
    silence = tmp_path / "scan_silence.wav"
    _write_wav(silence, seconds=2.0, tone_seconds=0.0)
    assert driver._scan_wav_for_speech(str(silence), seconds=2.0) is False


# ──────────────────────────────────────────────
#  录屏拉取：跨用例防护 + 原子落盘
# ──────────────────────────────────────────────

def _fake_adb(driver, content=b"MP4DATA", mutate_epoch_to=None):
    def fake_adb(device_sn, *args, **kwargs):
        if args and args[0] == "pull":
            target = args[-1]
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(content)
            if mutate_epoch_to is not None:
                driver._case_epoch = mutate_epoch_to
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_adb


def _patch_static_base(monkeypatch, tmp_path):
    from config.config import Config
    monkeypatch.setattr(Config, "STATIC_BASE_PATH", str(tmp_path))


def test_pull_record_file_atomic_replace(tmp_path, monkeypatch):
    _patch_static_base(monkeypatch, tmp_path)
    driver = _make_driver()
    driver._case_epoch = "E1"
    driver._record_file_name = "case-A_r0.mp4"
    driver._record_device_path = "/sdcard/Movies/DoubaoAutoTest/case-A_r0.mp4"
    driver._adb = _fake_adb(driver)

    got = driver._pull_record_file("SN", task_id=407, test_case_id="case-A")
    assert got and os.path.exists(got)
    assert open(got, "rb").read() == b"MP4DATA"
    assert not os.path.exists(got + driver.PART_FILE_SUFFIX)


def test_pull_record_file_rejects_foreign_case(tmp_path, monkeypatch):
    """驱动录屏名属于别的用例（滞留任务）→ 拒绝拉取，不创建用例目录"""
    _patch_static_base(monkeypatch, tmp_path)
    driver = _make_driver()
    driver._case_epoch = "E1"
    driver._record_file_name = "case-B_r0.mp4"
    driver._record_device_path = "/sdcard/x/case-B_r0.mp4"

    def boom(*a, **k):
        raise AssertionError("不能触达设备")

    driver._adb = boom
    got = driver._pull_record_file("SN", task_id=407, test_case_id="case-A")
    assert got is None
    assert not os.path.exists(os.path.join(str(tmp_path), "case_result", "407", "case-A"))


def test_pull_record_file_discards_when_case_switched(tmp_path, monkeypatch):
    _patch_static_base(monkeypatch, tmp_path)
    driver = _make_driver()
    driver._case_epoch = "E1"
    driver._record_file_name = "case-A_r0.mp4"
    driver._record_device_path = "/sdcard/x/case-A_r0.mp4"
    driver._adb = _fake_adb(driver, mutate_epoch_to="E2")

    got = driver._pull_record_file("SN", task_id=407, test_case_id="case-A")
    assert got is None
    local_dir = os.path.join(str(tmp_path), "case_result", "407", "case-A", "SN")
    assert not os.path.exists(os.path.join(local_dir, "case-A_r0.mp4"))


# ──────────────────────────────────────────────
#  initialize 状态复位
# ──────────────────────────────────────────────

def test_initialize_resets_state_and_clears_history(monkeypatch):
    driver = _make_driver()
    driver._record_device_path = "/sdcard/stale.mp4"
    driver._recorder_first_frame_ms = 1234567
    driver._ai_first_frame_ms = 999
    driver._case_epoch = "EPOCH-OLD"
    driver._pcm_baseline = {"/cache/stale.pcm": 1}
    driver._recording = True
    driver.question_text = "旧问题"
    driver.answer_text = "旧回答"

    fake = type("FakeUi", (), {"press": lambda self, *a: None,
                               "app_stop": lambda self, *a: None})()
    driver._get_u2 = lambda sn: fake
    driver.unlock = lambda sn, **kw: None
    driver.close_popups = lambda sn: None
    driver._launch_app = lambda sn, drv: True
    called = {}
    driver._ensure_chat_page = lambda *a, **kw: True
    driver._clear_chat_history = lambda *a, **kw: called.setdefault("chat", True)
    driver._clear_device_recordings = lambda *a, **kw: called.setdefault("rec", True)

    import backend.utils.device_driver.android_doubaochat as adc
    monkeypatch.setattr(adc.time, "sleep", lambda s: None)

    ok = driver.initialize("SN", task_id=407, test_case_id="case-A")
    assert ok is True
    assert called.get("chat") is True
    assert called.get("rec") is True
    assert driver._record_device_path is None
    assert driver._recorder_first_frame_ms is None
    assert driver._ai_first_frame_ms is None
    assert driver._case_epoch not in (None, "EPOCH-OLD")
    assert driver._pcm_baseline == {}
    assert driver._recording is False
    assert driver.question_text is None and driver.answer_text is None


# ──────────────────────────────────────────────
#  pre_process：case 非首轮短路
# ──────────────────────────────────────────────

def test_pre_process_case_non_first_skips_call_and_recorder(monkeypatch):
    driver = _make_driver()
    driver._recording = True
    fake = type("FakeUi", (), {"xpath": lambda self, x: None})()
    driver._get_u2 = lambda sn: fake
    driver._stop_music_app = lambda *a, **kw: None
    called = {}
    driver._start_audio_capture = lambda *a, **kw: called.setdefault("audio", True)
    driver._enter_voice_call = lambda *a, **kw: called.setdefault("call", True)
    driver._start_recorder = lambda *a, **kw: called.setdefault("rec", True)

    import backend.utils.device_driver.android_doubaochat as adc
    monkeypatch.setattr(adc.time, "sleep", lambda s: None)

    ok = driver.pre_process("SN", task_id=407, test_case_id="case-A",
                            record_mode="case", total_rounds=2, round_number=1)
    assert ok is True
    assert called.get("audio") is True
    assert "call" not in called and "rec" not in called


# ──────────────────────────────────────────────
#  get_results：mock / case 录屏进行中
# ──────────────────────────────────────────────

def test_get_results_mock_mode_returns_mock_payload():
    driver = _make_driver()
    driver._mock_mode = True
    res = driver.get_results("SN", task_id=407, test_case_id="case-A")
    assert isinstance(res, list) and res[0]["success"] is True


def test_get_results_case_round_in_progress_defers_mp4(tmp_path, monkeypatch):
    _patch_static_base(monkeypatch, tmp_path)
    driver = _make_driver()
    driver._record_mode = "case"
    driver._recording = True
    driver._audio_stopped = True
    driver._audio_paths = {"user": "/tmp/u.wav", "ai": "/tmp/a.wav"}
    driver._record_device_path = "/sdcard/Movies/DoubaoAutoTest/case-A.mp4"
    driver._record_file_name = "case-A.mp4"

    res = driver.get_results("SN", task_id=407, test_case_id="case-A")[0]
    assert res["success"] is True
    assert res["record_path"] == ""
    assert res["wav_path"] == ""
    assert res["user_wav"] == "/tmp/u.wav"
    assert res["ai_wav"] == "/tmp/a.wav"


# ──────────────────────────────────────────────
#  问答气泡提取（左右分栏 + clickable 过滤）
# ──────────────────────────────────────────────

def test_wav_peak_scans_whole_file(tmp_path):
    """长录音的语音可能在 40s 后才出现，峰值扫描不能只看开头"""
    path = tmp_path / "late_voice.wav"
    _write_wav(path, seconds=3.0, tone_seconds=1.0)
    driver = _make_driver()
    assert driver._wav_peak(str(path)) > 0


def test_wav_first_speech_offset(tmp_path):
    path = tmp_path / "onset.wav"
    _write_wav(path, seconds=3.0, tone_seconds=1.0)   # 前 2s 静音 + 后 1s 有声
    driver = _make_driver()
    onset = driver._wav_first_speech_offset(str(path))
    assert onset is not None and 1.9 <= onset <= 2.2


def test_align_audio_channels_trims_to_recorder_start():
    """两路音频先后启动、录屏再晚于音频：应裁到录屏起点作为共同 t=0"""
    driver = _make_driver()
    driver._audio_start_ts = {"ai": 100.0, "user": 100.4}
    driver._recorder_start_ts = 100.5
    driver._audio_paths = {"ai": "/tmp/ai.wav", "user": "/tmp/user.wav"}
    calls = []

    def fake_trim(path, offset, **kw):
        calls.append((path, round(offset, 3)))
        return True

    driver._trim_wav_leading = fake_trim
    driver._align_audio_channels(record_mode="round")
    assert calls == [("/tmp/ai.wav", 0.5), ("/tmp/user.wav", 0.1)]
    assert driver._audio_start_ts == {"ai": 100.5, "user": 100.5}


def test_align_audio_channels_case_mode_uses_latest_channel():
    driver = _make_driver()
    driver._audio_start_ts = {"ai": 200.0, "user": 200.3}
    driver._recorder_start_ts = 100.0          # case 模式录屏是整段，不能拿它当锚点
    driver._audio_paths = {"ai": "/tmp/ai.wav", "user": "/tmp/user.wav"}
    calls = []
    driver._trim_wav_leading = lambda path, offset, **kw: calls.append(
        (path, round(offset, 3))) or True
    driver._align_audio_channels(record_mode="case")
    assert calls == [("/tmp/ai.wav", 0.3)]


class _BubbleText:
    def __init__(self, text):
        self._text = text

    @property
    def exists(self):
        return bool(self._text)

    def get_text(self):
        return self._text


class _Bubble:
    def __init__(self, text, left, top=0):
        self._text = text or ""
        self.info = {"bounds": {"left": left, "top": top}}

    def child(self, className=None):
        return _BubbleText(self._text)


class _BubbleSet:
    def __init__(self, items):
        self._items = items

    @property
    def count(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]


class _FakeChatDriver:
    def __init__(self, items):
        self._items = items

    def window_size(self):
        return 1264, 2800

    def __call__(self, resourceId=None, **kw):
        return _BubbleSet(self._items)


def test_extract_chat_bubbles_picks_last_user_and_ai():
    driver = _make_driver()
    items = [
        _Bubble("欢迎语", 39, top=100),          # AI：欢迎气泡
        _Bubble("推荐问题chips", 0, top=200),     # chips 行（left=0）→ 排除
        _Bubble("第一个问题", 351, top=300),      # 用户
        _Bubble("第一个回答", 39, top=400),       # AI
        _Bubble("第二个问题", 351, top=500),      # 用户（最后一次）
        _Bubble("第二个回答", 39, top=600),       # AI（最后一次，在该用户消息下方）
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q == "第二个问题"
    assert a == "第二个回答"


def test_extract_chat_bubbles_ignores_empty_bubbles():
    driver = _make_driver()
    items = [
        _Bubble("", 39),
        _Bubble("  ", 39),
        _Bubble("", 351),
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q is None and a is None


def test_extract_chat_bubbles_no_user_message_returns_none():
    """通话挂断后若聊天列表只有欢迎语（没有本轮用户气泡），不得把欢迎语当成回答"""
    driver = _make_driver()
    items = [
        _Bubble("欢迎语", 39, top=100),
        _Bubble("历史回答", 39, top=200),
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q is None and a is None


def test_extract_chat_bubbles_answer_must_be_below_user():
    """AI 回复取该条用户消息下方最近的一条，避免拿到上一条历史回复"""
    driver = _make_driver()
    items = [
        _Bubble("历史回答", 39, top=100),
        _Bubble("本轮问题", 351, top=500),
        _Bubble("本轮回答", 39, top=700),
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q == "本轮问题" and a == "本轮回答"


def test_extract_chat_bubbles_generating_ai_returns_no_answer():
    """AI 气泡只有打字动画（无文本）时不能把上一条历史回复当本轮回答"""
    driver = _make_driver()
    items = [
        _Bubble("历史回答", 39, top=100),
        _Bubble("本轮问题", 351, top=500),
        _Bubble("", 39, top=700),          # 生成中：无 TextView 文本
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q == "本轮问题" and a is None


def test_extract_chat_bubbles_skips_search_status_bubble():
    """“搜索 N 个关键词/参考 N 篇资料”是过程态，不能当最终回答"""
    driver = _make_driver()
    items = [
        _Bubble("本轮问题", 351, top=500),
        _Bubble("搜索 1 个关键词，参考 4 篇资料", 39, top=600),
        _Bubble("最常见的“0618”指 6 月 18 日电商大促。", 39, top=700),
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q == "本轮问题"
    assert a == "最常见的“0618”指 6 月 18 日电商大促。"


def test_extract_chat_bubbles_only_status_returns_no_answer():
    driver = _make_driver()
    items = [
        _Bubble("本轮问题", 351, top=500),
        _Bubble("参考 4 篇资料", 39, top=600),
    ]
    q, a = driver._extract_chat_bubbles(_FakeChatDriver(items))
    assert q == "本轮问题" and a is None
