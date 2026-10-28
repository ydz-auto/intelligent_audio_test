"""豆包 Android 语音通话专用驱动。

对标鸿蒙 ``harmony_doubaochat.py`` / ``harmony_xiaoyichat.py``（豆包语音通话）的功能，
用 adb + uiautomator2 在 Android 手机上复刻同一套用例流程：

    initialize   解锁 / 关弹窗 / 回桌面 / 停豆包 / 拉起豆包 / 清聊天记录与上下文 /
                 复位跨用例状态（录屏标志、纪元、基线）
    pre_process  进入语音通话（首轮）→ 启动系统录屏（adb screenrecord）→
                 启动 scrcpy 双通道音频抓取（playback=AI 通道，mic=用户通道）
                 round=每轮一段 / case=整用例一段；支持 is_interruption 打断轮
    post_process 等 AI 回复完成（scrcpy playback wav 尾部 RMS 能量，双阶段+历史兜底；
                 音频不可用时回退 dumpsys media.audio_flinger 播放轨状态）；
                 打断轮只等 AI 开始回复；round 模式停录屏+挂断+提取本轮问答气泡；
                 case 模式中间轮不停不挂断（保持上下文连续），末轮停录屏但不挂断
    get_results  停止音频抓取并落盘 wav；拉取本轮 mp4 到本地并转 wav（无音轨时为 None）；
                 返回 record_path / wav_path / user_wav / ai_wav / question / answer /
                 first_frame_ms / start_ms / end_ms（与鸿蒙驱动字段一致）
    teardown     兜底停录屏 / 停音频抓取 / 挂断 / 回桌面 / 停豆包 / 清理设备残留

设计要点（与鸿蒙版的差异及原因）：
- 安卓未 root，读不到 App 私有 PCM（/data/data/com.larus.nova），因此用户/AI 双通道
  改用 scrcpy 抓取：``--audio-source=playback`` 拿模型播放音频，
  ``--audio-source=mic-voice-communication``（优先，带 AEC）或 ``mic`` 拿手机麦克风。
- 安卓 ``screenrecord`` 只能录画面没有音轨，录屏 mp4 仅作留痕；评估音频走 user_wav/ai_wav，
  故 wav_path 复用 ai_wav（与鸿蒙“无录屏”分支一致）。
- 回复完成检测沿用鸿蒙的 RMS 能量法（阈值/静默时长/超时参数一致），只是把“从设备拉 PCM”
  换成“直接读本机 scrcpy 正在写的 wav 尾部”，语义与 ``_wait_ai_reply_end_via_pcm`` 对齐。
"""

import os
import re
import struct
import subprocess
import time
import uuid

from .android_driver import AndroidDriver
from .utils import check_stop
from config.config import Config
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT
from .driver_types import DevicePlatform
from .registry import register_driver

# scrcpy 音频抓取模块（由 audio-scout 提供）。缺失时驱动降级为“无音频”模式，
# 不影响录屏/通话/问答提取等其它能力，也不会让平台启动失败。
try:
    from .android_scrcpy_audio import (
        ScrcpyAudioRecorder, resolve_scrcpy_path, kill_all_scrcpy,
    )
except Exception:  # pragma: no cover - 依赖缺失时降级
    ScrcpyAudioRecorder = None
    resolve_scrcpy_path = None
    kill_all_scrcpy = None


@register_driver
class DoubaoAndroidChat(AndroidDriver):
    """豆包 Android 语音通话专用驱动（对标鸿蒙豆包通话 DoubaoChat）"""

    app_type = "doubao"
    version = "v1"
    platform = DevicePlatform.ANDROID
    keywords = "android.doubao.v1"
    display_name = "豆包Android语音通话专用驱动"

    # 豆包 App 包名 / 首页 Activity（实测 nubia P0110 Android16 / 豆包 15.3.0.1）
    APP_NAME = "com.larus.nova"
    HOME_ACTIVITY = "com.larus.home.impl.alias.AliasActivity1"

    # 设备端录屏目录（驱动专用，initialize/teardown 会整体清理，不碰用户其它录像）
    RECORD_DIR = "/sdcard/Movies/DoubaoAutoTest"
    SCREENREC_BITRATE = 8000000

    # UI 资源 id（实测）
    MESSAGE_LIST_RES_ID = "com.larus.nova:id/message_list"
    REAL_CALL_RES_ID = "com.larus.nova:id/real_time_call_ic_container"
    REAL_CALL_ICON_RES_ID = "com.larus.nova:id/real_time_call"
    CALL_ROOT_RES_ID = "com.larus.nova:id/realtime_call_root"
    HANGUP_RES_ID = "com.larus.nova:id/voice_call_hangup"
    CALL_STATUS_RES_ID = "com.larus.nova:id/voice_call_status_text"
    SUBTITLE_RES_ID = "com.larus.nova:id/subtitleText"
    SETTINGS_ENTRY_RES_ID = "com.larus.nova:id/main_container"
    MENU_ENTRY_RES_ID = "com.larus.nova:id/back_icon"
    SPEAK_BUTTON_RES_ID = "com.larus.nova:id/speak_normal"
    CHAT_INPUT_RES_ID = "com.larus.nova:id/input_text"
    CHAT_SEND_RES_ID = "com.larus.nova:id/action_send"
    CALL_ENTRY_CONTAINER_RES_ID = "com.larus.nova:id/real_time_call_ic_container"
    DRAWER_RES_ID = "com.larus.nova:id/side_bar_container"
    NEW_CHAT_HINT_RES_ID = "com.larus.nova:id/tv_item_hint"
    CONV_TITLE_RES_ID = "com.larus.nova:id/tv_title"
    MENU_REMOVE_RES_ID = "com.larus.nova:id/fl_menu_remove"
    DIALOG_TITLE_RES_ID = "com.larus.nova:id/dialog_title"
    DIALOG_CONFIRM_RES_ID = "com.larus.nova:id/confirm"
    DIALOG_CANCEL_RES_ID = "com.larus.nova:id/cancel"
    SETTINGS_PAGE_RES_ID = "com.larus.nova:id/container_layout"
    SETTINGS_BACK_RES_ID = "com.larus.nova:id/left_img"
    BUBBLE_RES_ID = "com.larus.nova:id/content_view"
    MESSAGE_LEFT_RES_ID = "com.larus.nova:id/message_left_container"

    # 清聊天记录/上下文候选文案（不同版本文案可能不同）
    CLEAR_HISTORY_TEXTS = [
        "删除对话记录", "删除聊天记录", "清空聊天记录", "清空对话记录",
        "清除上下文", "清空上下文", "删除全部对话", "清空对话",
    ]
    CLEAR_CONFIRM_TEXTS = ["删除", "确定", "清空", "确认删除", "确认"]

    # 可能被豆包误识别指令拉起的音乐类 App（防音频污染，pre_process/teardown 兜底停止）
    MUSIC_PACKAGES = [
        "com.obric.music", "com.tencent.qqmusic", "com.luna.music",
        "com.netease.cloudmusic", "com.kugou.android",
    ]

    # 回复完成检测（RMS 能量法）参数：与鸿蒙豆包驱动保持一致
    RMS_THRESHOLD = 300          # RMS 阈值，低于此值视为静音
    RMS_SILENCE_SECONDS = 8      # 连续静默秒数（回复中停顿≤6s，8s 不误触发）
    RMS_START_TIMEOUT = 25       # 等 AI 开始说话的超时
    RMS_END_TIMEOUT = 60         # 等 AI 说完的超时
    RMS_SCAN_SECONDS = 15        # 阶段A超时后扫最后 N 秒历史
    RMS_TAIL_SECONDS = 1.0       # 单次尾部 RMS 采样窗口
    # scrcpy 每 1.365s 才落 256KiB（见 .tmp_probe/audio_probe_report.md §8），
    # 开始说话需连续 N 次采样超阈值，避免把上一块语音的尾巴/单次抖动当开始
    RMS_START_CONSECUTIVE = 2

    # 用例纪元/临时文件（防跨用例污染，与鸿蒙 VEGA-10 一致）
    PART_FILE_SUFFIX = ".part"

    # 问答气泡判定：用户气泡右对齐（left 较大），AI 气泡左对齐（left 较小）
    USER_BUBBLE_LEFT_RATIO = 0.12

    # AI 气泡里的“过程态/搜索态”文案（不能当最终回答）
    AI_STATUS_PATTERNS = (
        r"^搜索\s*\d+\s*个关键词",
        r"^参考\s*\d*\s*篇资料",
        r"^正在搜索", r"^已搜索", r"^检索", r"^正在生成", r"^思考中", r"^正在思考",
    )

    def __init__(self):
        super().__init__()
        self.app_name = self.APP_NAME
        # 录屏状态
        self._recording = False
        self._record_mode = "round"
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_device_path = None
        self._record_pulled = False
        self._recorder_first_frame_ms = None
        self._screenrec_proc = None
        # 音频抓取状态
        self._audio_recorders = {}
        self._audio_paths = {}
        self._audio_start_ts = {}
        self._ai_capture_birth_ts = None
        self._ai_capture_path = None
        self._recorder_start_ts = None
        self._ai_first_frame_ms = None
        self._round_audio_start_ms = None
        # 用例纪元（拉取/落盘跨用例防护）
        self._case_epoch = None
        self._pcm_baseline = {}
        # 问答文本
        self.question_text = None
        self.answer_text = None
        # 本轮是否已经停止过音频抓取（幂等）
        self._audio_stopped = True
        # 本轮音频是否已完成通道时间轴对齐
        self._audio_aligned = True

    # ------------------------------------------------------------------
    # 通用小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _as_bool(value):
        """兼容配置里 snake/camel 的布尔值（与 e2e_aggregator._as_bool 一致）。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "y", "是")
        return False

    def _adb(self, device_sn, *args, timeout=15):
        """执行 adb 命令（非 shell 子命令也走这里，例如 pull）。"""
        try:
            return subprocess.run(
                ["adb", "-s", device_sn] + [str(a) for a in args],
                check=False, capture_output=True, text=True, timeout=timeout,
            )
        except Exception as e:
            self._log(level="WARNING", content=f"adb 命令异常: {args} -> {e}")
            return subprocess.CompletedProcess(args, returncode=-1, stdout="", stderr=str(e))

    def _adb_shell(self, device_sn, *args, timeout=15):
        """执行 adb shell 命令；支持远程 shell 语法（如 $(pidof screenrecord)）。"""
        return self._adb(device_sn, "shell", *args, timeout=timeout)

    def _device_file_size(self, device_sn, device_path):
        """获取设备文件大小（字节），不存在返回 -1。"""
        r = self._adb_shell(device_sn, "stat", "-c", "%s", device_path, timeout=10)
        try:
            return int((r.stdout or "").strip())
        except Exception:
            return -1

    @staticmethod
    def _case_local_dir(task_id, test_case_id, device_sn):
        """用例本地结果目录（与平台/鸿蒙驱动一致的目录结构）。"""
        return os.path.join(
            Config.STATIC_BASE_PATH, "case_result",
            str(task_id) if task_id else "default_task_id",
            str(test_case_id) if test_case_id else "default_id",
            str(device_sn),
        )

    @staticmethod
    def _remove_quietly(path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _get_u2(self, device_sn):
        """获取 uiautomator2 设备对象（取不到就记日志返回 None）。"""
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level="ERROR", content=f"获取设备 {device_sn} uiautomator2 驱动失败")
        return driver

    @staticmethod
    def _xpath_exists(element):
        try:
            return bool(element and element.exists)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # wav 读取 / RMS（本地 scrcpy 录制文件）
    # ------------------------------------------------------------------
    @staticmethod
    def _wav_info(path):
        """解析 wav 头，返回 {channels, rate, width, data_offset}；失败返回 None。

        录制中的 wav 头 data size 可能是占位值，这里不依赖它，只取格式与 data 起点。
        """
        try:
            with open(path, "rb") as f:
                head = f.read(64 * 1024)
        except OSError:
            return None
        if len(head) < 12 or head[:4] not in (b"RIFF", b"RIFX") or head[8:12] != b"WAVE":
            return None
        rate = channels = width = 0
        data_offset = None
        i = 12
        while i + 8 <= len(head):
            chunk_id = head[i:i + 4]
            size = int.from_bytes(head[i + 4:i + 8], "little")
            body = i + 8
            if chunk_id == b"fmt " and body + 16 <= len(head):
                channels = int.from_bytes(head[body + 2:body + 4], "little")
                rate = int.from_bytes(head[body + 4:body + 8], "little")
                bits = int.from_bytes(head[body + 14:body + 16], "little")
                width = max(1, bits // 8)
            elif chunk_id == b"data":
                data_offset = body
                break
            # 跳过奇数长度 padding，避免死循环
            i = body + size + (size & 1)
        if not (rate and channels and width and data_offset is not None):
            return None
        return {"rate": rate, "channels": channels, "width": width,
                "data_offset": data_offset}

    @staticmethod
    def _rms_from_pcm(raw, channels):
        """16bit little-endian PCM 左声道 RMS；数据不足返回 None。"""
        if not raw or channels <= 0:
            return None
        usable = len(raw) - (len(raw) % 2)
        if usable < 2 * channels:
            return None
        samples = struct.unpack("<" + "h" * (usable // 2), raw[:usable])
        mono = samples[0::channels]
        if not mono:
            return None
        return (sum(s * s for s in mono) / len(mono)) ** 0.5

    def _read_wav_tail(self, path, seconds=None):
        """读取 wav 末尾 seconds 秒的原始 PCM 字节；失败返回 None。"""
        if not path or not os.path.exists(path) or seconds is None:
            return None
        info = self._wav_info(path)
        if not info:
            return None
        try:
            size = os.path.getsize(path)
            frame = info["rate"] * info["channels"] * info["width"]
            tail_bytes = int(seconds * frame)
            start = max(info["data_offset"], size - tail_bytes)
            if size <= start:
                return None
            with open(path, "rb") as f:
                f.seek(start)
                return f.read(size - start)
        except OSError:
            return None

    def _read_tail_rms(self, path, seconds=None):
        """读 wav 尾部 seconds 秒的左声道 RMS；失败返回 None。"""
        if seconds is None:
            seconds = self.RMS_TAIL_SECONDS
        info = self._wav_info(path) if path and os.path.exists(path) else None
        if not info:
            return None
        raw = self._read_wav_tail(path, seconds)
        if raw is None:
            return None
        return self._rms_from_pcm(raw, info["channels"])

    def _wav_peak(self, path, chunk_bytes=4 * 1024 * 1024, stop_at=30):
        """分段扫描 wav，返回样本绝对值峰值（用于判断整段是否全静音）。

        长录音里 AI 回复可能在 40s 之后才开始（文件前 4MB 是静音），所以不能只看开头；
        一旦峰值达到 stop_at（默认 30，远低于语音电平）即可提前返回，避免全量扫描。
        """
        info = self._wav_info(path) if path and os.path.exists(path) else None
        if not info:
            return None
        peak = 0
        try:
            with open(path, "rb") as f:
                f.seek(info["data_offset"])
                while True:
                    raw = f.read(chunk_bytes)
                    if not raw:
                        break
                    usable = len(raw) - (len(raw) % 2)
                    if usable <= 0:
                        continue
                    samples = struct.unpack("<" + "h" * (usable // 2), raw[:usable])
                    chunk_peak = max(abs(s) for s in samples)
                    if chunk_peak > peak:
                        peak = chunk_peak
                    if peak >= stop_at:
                        return peak
        except OSError:
            return None
        return peak

    def _wav_first_speech_offset(self, path, threshold=None, window=0.02):
        """返回 wav 中第一段“有声”窗口的起点（秒）；全静音返回 None。

        用于把 first_frame_ms 从“轮询检测时刻”修正为“AI 音频真实起始时刻”，
        消除 scrcpy 1.365s 落盘缓冲 + 1s 轮询带来的 1~2s 误差。
        """
        if threshold is None:
            threshold = self.RMS_THRESHOLD
        info = self._wav_info(path) if path and os.path.exists(path) else None
        if not info:
            return None
        frame_bytes = info["channels"] * info["width"]
        win_frames = max(1, int(window * info["rate"]))
        win_bytes = win_frames * frame_bytes
        frame_base = 0
        buf = b""
        try:
            with open(path, "rb") as f:
                f.seek(info["data_offset"])
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    buf += chunk
                    while len(buf) >= win_bytes:
                        seg, buf = buf[:win_bytes], buf[win_bytes:]
                        rms = self._rms_from_pcm(seg, info["channels"])
                        if rms is not None and rms > threshold:
                            return frame_base / float(info["rate"])
                        frame_base += win_frames
        except OSError:
            return None
        return None

    def _update_ai_first_frame_from_audio(self, task_id=None, test_case_id=None):
        """对齐后用音频真实起声点修正 first_frame_ms（失败时保留检测时刻）。"""
        path = self._audio_paths.get("ai")
        start_ts = (self._audio_start_ts or {}).get("ai")
        if not path or not start_ts:
            return
        onset = self._wav_first_speech_offset(path)
        if onset is None:
            return
        self._ai_first_frame_ms = int((start_ts + onset) * 1000)
        self._log(level="INFO",
                  content=(f"first_frame 修正为音频起声点: start_ts={start_ts:.3f} "
                           f"onset={onset:.3f}s -> {self._ai_first_frame_ms}"),
                  task_id=task_id, test_case_id=test_case_id)

    def _scan_wav_for_speech(self, path, seconds=None, energy_thr=None):
        """读最后 N 秒，按 0.5s 窗算 RMS，任一窗超阈值视为近期有语音。"""
        if seconds is None:
            seconds = self.RMS_SCAN_SECONDS
        if energy_thr is None:
            energy_thr = self.RMS_THRESHOLD
        info = self._wav_info(path) if path and os.path.exists(path) else None
        if not info:
            return False
        raw = self._read_wav_tail(path, seconds)
        if not raw:
            return False
        win_bytes = int(0.5 * info["rate"]) * info["channels"] * info["width"]
        win_bytes = max(win_bytes, info["channels"] * info["width"] * 2)
        for i in range(0, len(raw), win_bytes):
            chunk = raw[i:i + win_bytes]
            rms = self._rms_from_pcm(chunk, info["channels"])
            if rms is not None and rms > energy_thr:
                return True
        return False

    # ------------------------------------------------------------------
    # AI 回复检测：RMS 主信号 + audio_flinger 兜底
    # ------------------------------------------------------------------
    def _wait_ai_reply_start_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                    start_timeout=None, energy_thr=None, interval=1.0,
                                    min_consecutive=1):
        """等 AI 开始回复（阶段A）。返回 (status, path)：
        'fresh'=刚检测到开始说话；'ended'=超时但近 15s 曾有语音；'none'=未回复。

        min_consecutive：连续多少次采样超阈值才认开始。正常轮建议 2（覆盖 scrcpy
        1.365s 落盘节拍）；打断轮建议 1（barge-in 时效优先，早放下一轮可接受）。
        """
        if start_timeout is None:
            start_timeout = self.RMS_START_TIMEOUT
        if energy_thr is None:
            energy_thr = self.RMS_THRESHOLD
        path = self._audio_paths.get("ai")
        if not path or not os.path.exists(path) or not self._wav_info(path):
            # 音频不可用：用 audio_flinger 活跃播放轨兜底
            status = self._wait_reply_start_via_flinger(
                device_sn, start_timeout=start_timeout,
                task_id=task_id, test_case_id=test_case_id)
            return status, path
        deadline = time.time() + start_timeout
        saw_speech = False
        consecutive = 0
        while time.time() < deadline:
            if self._check_stop("post_process_等AI回复开始"):
                return "none", path
            rms = self._read_tail_rms(path)
            if rms is not None and rms > energy_thr:
                consecutive += 1
                if consecutive >= max(1, int(min_consecutive)):
                    saw_speech = True
                    self._ai_first_frame_ms = int(time.time() * 1000)
                    self._log(level="INFO",
                              content=f"AI回复开始: tail_rms={rms:.0f} (scrcpy playback)",
                              task_id=task_id, test_case_id=test_case_id)
                    break
            else:
                consecutive = 0
            time.sleep(interval)
        if saw_speech:
            return "fresh", path
        if self._scan_wav_for_speech(path, seconds=self.RMS_SCAN_SECONDS,
                                     energy_thr=energy_thr):
            self._log(level="INFO",
                      content="AI回复已结束(post_process起得晚,尾部静默但近15s曾有语音)",
                      task_id=task_id, test_case_id=test_case_id)
            return "ended", path
        self._log(level="INFO",
                  content=f"豆包未回复({start_timeout}s 内 playback 尾部无语音能量)",
                  task_id=task_id, test_case_id=test_case_id)
        return "none", path

    def _wait_ai_reply_end_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                   interval=1.0):
        """等 AI 回复完成（双阶段 + 历史兜底）。True=已回复，False=未回复。"""
        path = self._audio_paths.get("ai")
        if not path or not os.path.exists(path) or not self._wav_info(path):
            return self._wait_ai_reply_end_via_flinger(
                device_sn, task_id=task_id, test_case_id=test_case_id)
        # 阶段A：等 AI 开始说话（连续 2 次采样，覆盖 scrcpy 1.365s 落盘节拍）
        status, _ = self._wait_ai_reply_start_via_pcm(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            interval=interval, min_consecutive=self.RMS_START_CONSECUTIVE)
        if status == "none":
            self._log(level="INFO",
                      content=f"豆包未回复({self.RMS_START_TIMEOUT}s 内 playback 无语音能量)",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        if status == "ended":
            self._log(level="INFO",
                      content="AI回复已结束(post_process起得晚,近15s曾有语音)",
                      task_id=task_id, test_case_id=test_case_id)
            return True
        # 阶段B：等连续静默
        silence_since = None
        deadline_end = time.time() + self.RMS_END_TIMEOUT
        while time.time() < deadline_end:
            if self._check_stop("post_process_等AI回复结束"):
                return False
            rms = self._read_tail_rms(path)
            now = time.time()
            if rms is None:
                time.sleep(interval)
                continue
            if rms >= self.RMS_THRESHOLD:
                silence_since = None
            else:
                if silence_since is None:
                    silence_since = now
                elif (now - silence_since) >= self.RMS_SILENCE_SECONDS:
                    self._log(level="INFO",
                              content=(f"AI回复结束(尾部静默 {self.RMS_SILENCE_SECONDS}s, "
                                       f"rms={rms:.0f})"),
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            time.sleep(interval)
        self._log(level="WARNING",
                  content=(f"等待AI回复结束超时 {self.RMS_END_TIMEOUT}s"
                           f"(已说过但未静默,视为已回复可能截断)"),
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def _audio_flinger_playing(self, device_sn):
        """解析 dumpsys media.audio_flinger，判断设备是否正在播放音频（兜底信号）。"""
        r = self._adb_shell(device_sn, "dumpsys", "media.audio_flinger", timeout=15)
        out = r.stdout or ""
        for line in out.splitlines():
            m = re.search(r"Tracks of which\s+(\d+)\s+are active", line)
            if m:
                try:
                    if int(m.group(1)) > 0:
                        return True
                except ValueError:
                    continue
        return False

    def _wait_reply_start_via_flinger(self, device_sn, start_timeout=None,
                                      task_id=None, test_case_id=None, interval=1.0):
        """兜底：用播放轨状态等 AI 开始说话。"""
        if start_timeout is None:
            start_timeout = self.RMS_START_TIMEOUT
        deadline = time.time() + start_timeout
        while time.time() < deadline:
            if self._check_stop("post_process_等AI回复开始(audio_flinger)"):
                return "none"
            if self._audio_flinger_playing(device_sn):
                self._ai_first_frame_ms = int(time.time() * 1000)
                self._log(level="INFO", content="AI回复开始(audio_flinger 播放轨活跃)",
                          task_id=task_id, test_case_id=test_case_id)
                return "fresh"
            time.sleep(interval)
        return "none"

    def _wait_ai_reply_end_via_flinger(self, device_sn, task_id=None, test_case_id=None,
                                       interval=1.0):
        """兜底：用播放轨状态等 AI 回复完成。True=已回复，False=未回复。"""
        if not self._audio_flinger_playing(device_sn):
            if self._wait_reply_start_via_flinger(
                    device_sn, task_id=task_id, test_case_id=test_case_id) != "fresh":
                self._log(level="WARNING",
                          content="音频抓取不可用且 audio_flinger 无播放轨，判定未回复",
                          task_id=task_id, test_case_id=test_case_id)
                return False
        silence_since = None
        deadline = time.time() + self.RMS_END_TIMEOUT
        while time.time() < deadline:
            if self._check_stop("post_process_等AI回复结束(audio_flinger)"):
                return False
            if self._audio_flinger_playing(device_sn):
                silence_since = None
            else:
                if silence_since is None:
                    silence_since = time.time()
                elif (time.time() - silence_since) >= self.RMS_SILENCE_SECONDS:
                    self._log(level="INFO", content="AI回复结束(audio_flinger 播放轨静默)",
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            time.sleep(interval)
        self._log(level="WARNING", content="audio_flinger 等待回复结束超时，视为已回复",
                  task_id=task_id, test_case_id=test_case_id)
        return True

    # ------------------------------------------------------------------
    # 录屏（adb screenrecord）
    # ------------------------------------------------------------------
    def _ensure_record_dir(self, device_sn):
        self._adb_shell(device_sn, "mkdir", "-p", self.RECORD_DIR, timeout=10)

    def _clear_device_recordings(self, device_sn, task_id=None, test_case_id=None):
        """清空驱动专用录屏目录（不碰用户其它录像）。"""
        try:
            self._adb_shell(device_sn, "rm", "-rf", self.RECORD_DIR, timeout=10)
            self._adb_shell(device_sn, "mkdir", "-p", self.RECORD_DIR, timeout=10)
            self._log(level="DEBUG", content=f"已清理设备录屏目录: {self.RECORD_DIR}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level="WARNING", content=f"清理设备录屏目录失败(忽略): {e}",
                      task_id=task_id, test_case_id=test_case_id)

    def _start_recorder(self, device_sn, file_name=None):
        """启动 adb screenrecord（无音轨，仅留痕），返回是否启动成功。"""
        if not file_name:
            return False
        self._ensure_record_dir(device_sn)
        remote = f"{self.RECORD_DIR}/{file_name}"
        self._adb_shell(device_sn, "rm", "-f", remote, timeout=10)
        cmd = [
            "adb", "-s", device_sn, "shell", "screenrecord",
            "--time-limit", "0",
            "--bit-rate", str(self.SCREENREC_BITRATE),
            remote,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._screenrec_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=creationflags)
        except Exception as e:
            self._log(level="ERROR", content=f"启动 screenrecord 失败: {e}")
            self._screenrec_proc = None
            self._record_device_path = None
            self._recorder_first_frame_ms = None
            self._recorder_start_ts = None
            return False
        self._record_device_path = remote
        # screenrecord 启动即创建文件，首帧时刻近似取启动成功时刻
        self._recorder_first_frame_ms = int(time.time() * 1000)
        self._recorder_start_ts = time.time()
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._device_file_size(device_sn, remote) > 0:
                return True
            time.sleep(0.3)
        self._log(level="ERROR", content=f"screenrecord 文件未创建: {remote}")
        self._stop_recorder(device_sn)
        return False

    def _stop_recorder(self, device_sn, task_id=None, test_case_id=None):
        """停止 screenrecord：先发 SIGINT 让设备端 finalize mp4，再回收本地 adb 进程。"""
        try:
            self._adb_shell(device_sn, "pkill", "-INT", "screenrecord", timeout=10)
        except Exception as e:
            self._log(level="DEBUG", content=f"pkill screenrecord 失败(忽略): {e}",
                      task_id=task_id, test_case_id=test_case_id)
        try:
            self._adb_shell(device_sn, "kill", "-INT", "$(pidof screenrecord)", timeout=10)
        except Exception as e:
            self._log(level="DEBUG", content=f"kill -INT screenrecord 失败(忽略): {e}",
                      task_id=task_id, test_case_id=test_case_id)
        proc = self._screenrec_proc
        self._screenrec_proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._recording = False
        # 等文件落盘
        if self._record_device_path:
            deadline = time.time() + 15
            stable = 0
            last = -2
            while time.time() < deadline:
                size = self._device_file_size(device_sn, self._record_device_path)
                if size > 0 and size == last:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                last = size
                time.sleep(0.5)
        self._log(level="DEBUG", content="screenrecord 已停止", task_id=task_id,
                  test_case_id=test_case_id)
        return True

    def _mp4_to_wav(self, mp4_path, task_id=None, test_case_id=None):
        """mp4 转 wav（pcm_s16le 44.1k 双声道）；无音轨/失败返回 None。"""
        if not mp4_path or not os.path.exists(mp4_path):
            return None
        wav_path = os.path.splitext(mp4_path)[0] + ".wav"
        cmd = [Config.FFMPEG_PATH, "-y", "-i", mp4_path,
               "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", wav_path]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 44:
                self._log(level="DEBUG",
                          content=f"mp4转wav无音轨/失败(忽略): {r.stderr[-300:] if r.stderr else ''}",
                          task_id=task_id, test_case_id=test_case_id)
                self._remove_quietly(wav_path)
                return None
            self._log(level="INFO", content=f"mp4转wav成功: {wav_path}",
                      task_id=task_id, test_case_id=test_case_id)
            return wav_path
        except Exception as e:
            self._log(level="WARNING", content=f"mp4转wav异常(忽略): {e}",
                      task_id=task_id, test_case_id=test_case_id)
            self._remove_quietly(wav_path)
            return None

    def _pull_record_file(self, device_sn, task_id=None, test_case_id=None):
        """把本轮录屏 mp4 拉到本地（*.part 原子替换 + 用例纪元校验）。返回本地路径。"""
        record_file_name = getattr(self, "_record_file_name", None)
        device_path = getattr(self, "_record_device_path", None)
        if not record_file_name or not device_path:
            return None
        if test_case_id is not None and str(test_case_id) not in str(record_file_name):
            self._log(level="ERROR",
                      content=(f"录屏拉取被拒绝: 当前录屏名 {record_file_name} 不属于用例 "
                               f"{test_case_id}(疑似跨用例滞留任务)"),
                      task_id=task_id, test_case_id=test_case_id)
            return None
        epoch = self._case_epoch
        local_dir = self._case_local_dir(task_id, test_case_id, device_sn)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, record_file_name)
        part_path = local_path + self.PART_FILE_SUFFIX
        r = self._adb(device_sn, "pull", device_path, part_path, timeout=180)
        if not os.path.exists(part_path):
            self._log(level="WARNING",
                      content=f"拉取录屏失败: {device_path} err={r.stderr}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        if epoch is not None and self._case_epoch != epoch:
            self._remove_quietly(part_path)
            self._log(level="ERROR",
                      content=f"录屏拉取被丢弃: 拉取期间用例已切换(epoch {epoch} -> {self._case_epoch})",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        os.replace(part_path, local_path)
        self._record_pulled = True
        return local_path

    # ------------------------------------------------------------------
    # 音频抓取（scrcpy：playback=AI 通道，mic=用户通道）
    # ------------------------------------------------------------------
    @staticmethod
    def _audio_capture_kwargs(kwargs):
        """只透传音频抓取需要的参数，避免与位置参数/其它轮次参数冲突。"""
        keys = ("mic_source", "user_audio_source")
        return {k: v for k, v in (kwargs or {}).items() if k in keys}

    @staticmethod
    def _wav_birth_ts(path, fallback=None):
        """wav 文件创建时刻（Windows 上 = 第一帧附近）；取不到时用 fallback。

        scrcpy 的 ``start()`` 返回时已经晚于第一帧约 0.08~0.6s（server push + 等待
        Recording started），拿它当时间轴起点会引入系统性偏移；文件创建时刻与第一帧
        只差几十毫秒，更适合做双通道/音画对齐的锚点。
        """
        try:
            st = os.stat(path)
            ts = getattr(st, "st_birthtime", None) or st.st_ctime
            if ts and ts > 0:
                return float(ts)
        except OSError:
            pass
        return fallback

    def _start_audio_capture(self, device_sn, test_case_id, round_number,
                             task_id=None, **kwargs):
        """启动本轮双通道音频抓取；返回是否至少 AI 通道可用。"""
        self._audio_paths = {}
        self._audio_recorders = {}
        self._audio_start_ts = {}
        self._ai_capture_birth_ts = None
        self._ai_capture_path = None
        self._audio_stopped = False
        self._audio_aligned = False
        if ScrcpyAudioRecorder is None:
            self._log(level="WARNING",
                      content="scrcpy 音频模块不可用，本轮无 user_wav/ai_wav（降级为 audio_flinger 检测）",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        local_dir = self._case_local_dir(task_id, test_case_id, device_sn)
        os.makedirs(local_dir, exist_ok=True)
        base = f"{test_case_id}_r{round_number}"
        mic_source = kwargs.get("mic_source",
                                kwargs.get("user_audio_source", "voice-call-uplink"))
        plan = [("ai", "playback", f"{base}_ai.wav")]
        # 合成方案：用户音频由平台播放时间轴生成，不再抓麦克风（通话中本来也抓不到）
        if str(mic_source).startswith("synth"):
            self._log(level="INFO",
                      content=f"user_audio_source={mic_source}，跳过用户麦克风抓取，"
                              "get_results 时按播放时间戳合成 user_wav",
                      task_id=task_id, test_case_id=test_case_id)
        else:
            plan.append(("user", mic_source, f"{base}_user.wav"))
        ai_ok = False
        for role, source, file_name in plan:
            out_path = os.path.join(local_dir, file_name)
            self._remove_quietly(out_path)
            try:
                rec = ScrcpyAudioRecorder(device_sn, scrcpy_path=resolve_scrcpy_path()
                                          if resolve_scrcpy_path else None,
                                          log_dir=local_dir)
                ok = rec.start(source, out_path)
            except Exception as e:
                ok = False
                rec = None
                self._log(level="WARNING", content=f"启动 {source} 音频抓取异常: {e}",
                          task_id=task_id, test_case_id=test_case_id)
            if ok:
                start_ts = self._wav_birth_ts(out_path, fallback=time.time())
                self._audio_recorders[role] = rec
                self._audio_paths[role] = out_path
                self._audio_start_ts[role] = start_ts
                if role == "ai":
                    self._ai_capture_birth_ts = start_ts
                    self._ai_capture_path = out_path
                    ai_ok = True
                self._log(level="INFO",
                          content=f"音频抓取已启动: role={role} source={source} -> {out_path}",
                          task_id=task_id, test_case_id=test_case_id)
                continue
            # mic-voice-communication 失败时回退 mic
            if role == "user" and source != "mic":
                try:
                    rec = ScrcpyAudioRecorder(device_sn, scrcpy_path=resolve_scrcpy_path()
                                              if resolve_scrcpy_path else None,
                                              log_dir=local_dir)
                    ok = rec.start("mic", out_path)
                except Exception:
                    ok = False
                if ok:
                    start_ts = self._wav_birth_ts(out_path, fallback=time.time())
                    self._audio_recorders[role] = rec
                    self._audio_paths[role] = out_path
                    self._audio_start_ts[role] = start_ts
                    if role == "ai":
                        self._ai_capture_birth_ts = start_ts
                        self._ai_capture_path = out_path
                    self._log(level="INFO",
                              content=f"音频抓取已启动(回退 mic): role={role} -> {out_path}",
                              task_id=task_id, test_case_id=test_case_id)
                    continue
            self._log(level="WARNING",
                      content=f"音频抓取启动失败: role={role} source={source}",
                      task_id=task_id, test_case_id=test_case_id)
        return ai_ok

    def _trim_wav_leading(self, path, offset, task_id=None, test_case_id=None):
        """把 wav 开头裁掉 offset 秒（重编码为同格式 PCM），用于双通道时间轴对齐。"""
        if not path or offset <= 0.01 or not os.path.exists(path):
            return False
        info = self._wav_info(path)
        if not info:
            return False
        tmp = path + ".aligned.wav"
        cmd = [Config.FFMPEG_PATH, "-y", "-i", path, "-af",
               f"atrim=start={offset:.3f},asetpts=PTS-STARTPTS",
               "-acodec", "pcm_s16le", "-f", "wav", tmp]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=180)
        except Exception as e:
            self._log(level="WARNING", content=f"音频对齐裁剪异常({path}): {e}",
                      task_id=task_id, test_case_id=test_case_id)
            self._remove_quietly(tmp)
            return False
        if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) <= 44:
            self._log(level="WARNING",
                      content=f"音频对齐裁剪失败({path}): {r.stderr[-200:] if r.stderr else ''}",
                      task_id=task_id, test_case_id=test_case_id)
            self._remove_quietly(tmp)
            return False
        os.replace(tmp, path)
        return True

    def _align_audio_channels(self, task_id=None, test_case_id=None,
                              record_mode="round"):
        """把 user/ai 两路 wav 对齐到同一时间轴（默认对齐到录屏起点）。

        安卓两路 scrcpy 是先后启动的（实测相差 0.3~0.6s），录屏又晚于音频启动
        （~0.5s）。不对齐时 user_wav/ai_wav 的 t=0 各指各的，逐轮打断/话轮时延会漂。
        这里取“最后启动的那一路”为锚点：round 模式优先录屏起点，case 模式取两路中较晚者，
        裁掉各通道开头的 offset，保证共用同一 t=0。
        """
        ts = dict(self._audio_start_ts or {})
        if len(ts) < 2:
            return
        candidates = list(ts.values())
        if record_mode != "case" and self._recorder_start_ts:
            candidates.append(self._recorder_start_ts)
        anchor = max(candidates)
        for role, start_ts in ts.items():
            offset = anchor - start_ts
            if offset <= 0.01:
                continue
            path = self._audio_paths.get(role)
            if self._trim_wav_leading(path, offset, task_id=task_id,
                                      test_case_id=test_case_id):
                self._audio_start_ts[role] = anchor
                self._log(level="INFO",
                          content=(f"音频通道对齐: role={role} trim={offset:.3f}s "
                                   f"(anchor={anchor:.3f})"),
                          task_id=task_id, test_case_id=test_case_id)

    def _stop_audio_capture(self, task_id=None, test_case_id=None):
        """停止本轮音频抓取（幂等），保留本地 wav 路径供 get_results 使用。"""
        if self._audio_stopped:
            return True
        self._audio_stopped = True
        for role, rec in list(self._audio_recorders.items()):
            try:
                final = rec.stop()
                if final:
                    self._audio_paths[role] = final
                self._log(level="DEBUG", content=f"音频抓取已停止: role={role} -> {final}",
                          task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level="WARNING", content=f"停止音频抓取失败({role}): {e}",
                          task_id=task_id, test_case_id=test_case_id)
        self._audio_recorders = {}
        return True

    # ------------------------------------------------------------------
    # 合成音频（平台播放的 user 音频 -> user_wav，与 AI 通道共用 T0）
    # ------------------------------------------------------------------
    SYNTH_SAMPLE_RATE = 48000
    SYNTH_TAIL_MS = 500

    @staticmethod
    def _wav_duration(path):
        """返回 wav 的音频时长（秒）；头损坏/空文件返回 None。"""
        info = DoubaoAndroidChat._wav_info(path) if path else None
        if not info:
            return None
        try:
            size = os.path.getsize(path)
        except OSError:
            return None
        data_bytes = max(0, size - info["data_offset"])
        frame = info["rate"] * info["channels"] * info["width"]
        return data_bytes / float(frame) if frame else None

    def _decode_audio_to_pcm(self, path, sample_rate=None, task_id=None,
                             test_case_id=None):
        """用 ffmpeg 把任意音频解码成 48k/16bit/双声道 int32 数组（立体声）。"""
        try:
            import numpy as np
        except Exception as e:  # pragma: no cover - 环境缺 numpy
            self._log(level="WARNING", content=f"合成音频需要 numpy，当前不可用: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        sr = sample_rate or self.SYNTH_SAMPLE_RATE
        cmd = [
            Config.FFMPEG_PATH, "-v", "error", "-i", path,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(sr), "-ac", "2",
            "pipe:1",
        ]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, timeout=180)
        except Exception as e:
            self._log(level="WARNING", content=f"解码音频异常({path}): {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        if r.returncode != 0 or not r.stdout:
            msg = (r.stderr or b"")[-300:].decode("utf-8", "ignore")
            self._log(level="WARNING", content=f"解码音频失败({path}): {msg}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        usable = len(r.stdout) - (len(r.stdout) % 4)
        if usable <= 0:
            return None
        return np.frombuffer(r.stdout[:usable], dtype="<i2").reshape(-1, 2).astype(np.int32)

    @staticmethod
    def _write_pcm_wav(path, samples, sample_rate=None):
        """把 int32 立体声数组写成 16bit PCM wav。"""
        import wave
        import numpy as np
        sr = sample_rate or DoubaoAndroidChat.SYNTH_SAMPLE_RATE
        pcm = np.clip(samples, -32768, 32767).astype("<i2")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())
        return path

    def _synthesize_user_wav(self, played_audios, out_path, t0_ms=None,
                             duration_ms=None, include_types=("dry", "interferer"),
                             task_id=None, test_case_id=None):
        """按播放时间戳把平台播放的音频拼成一条 user_wav。

        played_audios: [{file_path, start_ms, end_ms, audio_type}, ...]
        时间轴 t=0 由调用方指定（通常 = min(播放起点, ai_wav 创建时刻)）。
        噪声默认不拼入（H1 方案：评估音频只含用户+干扰人；噪声另行评估）。
        """
        try:
            import numpy as np
        except Exception:
            return None
        entries = []
        for item in played_audios or []:
            if not isinstance(item, dict):
                continue
            path = item.get("file_path") or item.get("file") or item.get("path")
            start_ms = item.get("start_ms")
            if start_ms is None:
                start_ms = item.get("playback_start_time_ms")
            end_ms = item.get("end_ms")
            if end_ms is None:
                end_ms = item.get("playback_end_time_ms")
            audio_type = item.get("audio_type") or "dry"
            if not path or start_ms is None:
                continue
            if include_types is not None and audio_type not in include_types:
                continue
            if not os.path.exists(path):
                self._log(level="WARNING", content=f"合成 user_wav 跳过不存在的文件: {path}",
                          task_id=task_id, test_case_id=test_case_id)
                continue
            entries.append({
                "path": path,
                "start_ms": int(start_ms),
                "end_ms": int(end_ms) if end_ms is not None else None,
                "audio_type": audio_type,
            })
        if not entries:
            self._log(level="WARNING", content="合成 user_wav 跳过：没有可用的播放音频",
                      task_id=task_id, test_case_id=test_case_id)
            return None

        sr = self.SYNTH_SAMPLE_RATE
        if t0_ms is None:
            t0_ms = min(e["start_ms"] for e in entries)
        if duration_ms is None:
            latest = max((e["end_ms"] or e["start_ms"]) for e in entries)
            duration_ms = latest - t0_ms + self.SYNTH_TAIL_MS
        total = max(1, int(round(duration_ms / 1000.0 * sr)))
        mix = np.zeros((total, 2), dtype=np.int32)
        placed = 0
        for e in entries:
            pcm = self._decode_audio_to_pcm(e["path"], sr, task_id=task_id,
                                            test_case_id=test_case_id)
            if pcm is None or len(pcm) == 0:
                continue
            if e["end_ms"] is not None and e["end_ms"] > e["start_ms"]:
                want = int(round((e["end_ms"] - e["start_ms"]) / 1000.0 * sr))
                pcm = pcm[:max(1, want)]
            dst = int(round((e["start_ms"] - t0_ms) / 1000.0 * sr))
            src = 0
            if dst < 0:
                src = -dst
                dst = 0
            if src >= len(pcm) or dst >= total:
                continue
            take = min(len(pcm) - src, total - dst)
            if take <= 0:
                continue
            mix[dst:dst + take] += pcm[src:src + take]
            placed += 1
        if placed == 0:
            return None
        self._write_pcm_wav(out_path, mix, sr)
        self._log(level="INFO",
                  content=(f"合成 user_wav: {out_path} entries={placed}/{len(entries)} "
                           f"t0={t0_ms} duration={duration_ms}ms"),
                  task_id=task_id, test_case_id=test_case_id)
        return out_path

    def _align_ai_wav_to_timeline(self, ai_wav, out_path, t0_ms, duration_ms,
                                  ai_birth=None, task_id=None, test_case_id=None):
        """把 AI 通道 wav 放到与 user_wav 相同的 T0 时间轴上（裁头/补静音）。"""
        import numpy as np
        sr = self.SYNTH_SAMPLE_RATE
        pcm = self._decode_audio_to_pcm(ai_wav, sr, task_id=task_id,
                                        test_case_id=test_case_id)
        if pcm is None:
            return None
        ai_birth = ai_birth or self._wav_birth_ts(ai_wav)
        offset_ms = (ai_birth * 1000.0 - t0_ms) if ai_birth else 0.0
        total = max(1, int(round(duration_ms / 1000.0 * sr)))
        out = np.zeros((total, 2), dtype=np.int32)
        dst = int(round(offset_ms / 1000.0 * sr))
        src = 0
        if dst < 0:
            src = -dst
            dst = 0
        if src < len(pcm) and dst < total:
            take = min(len(pcm) - src, total - dst)
            out[dst:dst + take] = pcm[src:src + take]
        self._write_pcm_wav(out_path, out, sr)
        self._log(level="INFO",
                  content=(f"AI wav 对齐到 T0: {out_path} ai_birth={ai_birth} "
                           f"offset={offset_ms:.1f}ms duration={duration_ms}ms"),
                  task_id=task_id, test_case_id=test_case_id)
        return out_path

    def _synthesize_from_played(self, device_sn, played_audios, task_id=None,
                                test_case_id=None):
        """把平台播放音频合成 user_wav，并把 AI wav 对齐到同一 T0；成功返回 True。"""
        # 优先用未对齐的原始 AI 抓取文件；对齐后的文件 ctime/时长都变了，
        # 重复调用会漂移（幂等）。
        ai_wav = (getattr(self, "_ai_capture_path", None)
                  or self._audio_paths.get("ai"))
        if not ai_wav or not os.path.exists(ai_wav):
            self._log(level="WARNING", content="合成音频跳过：AI wav 不存在",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        entries = []
        for item in played_audios or []:
            if not isinstance(item, dict):
                continue
            start_ms = item.get("start_ms")
            if start_ms is None:
                start_ms = item.get("playback_start_time_ms")
            end_ms = item.get("end_ms")
            if end_ms is None:
                end_ms = item.get("playback_end_time_ms")
            audio_type = item.get("audio_type") or "dry"
            if audio_type == "noise":
                continue
            if start_ms is None:
                continue
            entries.append({"start_ms": int(start_ms),
                            "end_ms": int(end_ms) if end_ms is not None else None})
        # 注意：对齐后的 ai 文件 ctime 会变成“写文件时刻”，不能再用它当时间锚点；
        # 优先用录制启动时记下的原始创建时刻（_ai_capture_birth_ts）。
        ai_birth = (getattr(self, "_ai_capture_birth_ts", None)
                    or (self._audio_start_ts or {}).get("ai")
                    or self._wav_birth_ts(ai_wav))
        ai_duration = self._wav_duration(ai_wav) or 0.0
        starts = [e["start_ms"] for e in entries]
        ends = [(e["end_ms"] or e["start_ms"]) for e in entries]
        if ai_birth:
            starts.append(int(ai_birth * 1000))
            ends.append(int(ai_birth * 1000 + ai_duration * 1000))
        if not starts:
            self._log(level="WARNING", content="合成音频跳过：无播放时间戳且无 AI 起点",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        t0_ms = min(starts)
        duration_ms = max(ends) - t0_ms + self.SYNTH_TAIL_MS
        base = ai_wav[:-len("_ai.wav")] if ai_wav.endswith("_ai.wav") else os.path.splitext(ai_wav)[0]
        user_out = base + "_user_synth.wav"
        ai_out = base + "_ai_aligned.wav"
        if not self._synthesize_user_wav(played_audios, user_out, t0_ms=t0_ms,
                                         duration_ms=duration_ms,
                                         task_id=task_id, test_case_id=test_case_id):
            return False
        if not self._align_ai_wav_to_timeline(ai_wav, ai_out, t0_ms, duration_ms,
                                              ai_birth=ai_birth,
                                              task_id=task_id, test_case_id=test_case_id):
            return False
        self._audio_paths["user"] = user_out
        self._audio_paths["ai"] = ai_out
        self._audio_start_ts = {"user": t0_ms / 1000.0, "ai": t0_ms / 1000.0}
        self._audio_aligned = True
        return True

    # ------------------------------------------------------------------
    # App / 页面操作
    # ------------------------------------------------------------------
    def _launch_app(self, device_sn, driver):
        """拉起豆包到聊天首页（优先显式 Activity，回退 monkey/u2）。"""
        activity = f"{self.APP_NAME}/{self.HOME_ACTIVITY}"
        r = self._adb(device_sn, "shell", "am", "start", "-n", activity, timeout=15)
        if r.returncode == 0:
            return True
        try:
            driver.app_start(self.APP_NAME)
            return True
        except Exception as e:
            self._log(level="ERROR", content=f"拉起豆包失败: {e}")
            return False

    @staticmethod
    def _bounds_dict(info):
        """u2 的 bounds 可能是 dict，也可能是 '[l,t][r,b]' 字符串，统一成 dict。"""
        if not info:
            return {}
        b = info.get("bounds")
        if isinstance(b, dict):
            return b
        if isinstance(b, str):
            m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", b)
            if m:
                return {"left": int(m.group(1)), "top": int(m.group(2)),
                        "right": int(m.group(3)), "bottom": int(m.group(4))}
        return {}

    def _ui_state(self, driver):
        """判定当前落点：call / drawer / settings / chat / unknown（冷启动落点不确定）。"""
        try:
            if driver(resourceId=self.HANGUP_RES_ID).exists:
                return "call"
            if driver(resourceId=self.DRAWER_RES_ID).exists:
                return "drawer"
            if driver(resourceId=self.SETTINGS_PAGE_RES_ID).exists:
                return "settings"
            if driver(resourceId=self.REAL_CALL_RES_ID).exists:
                return "chat"
        except Exception:
            pass
        return "unknown"

    def _is_call_page(self, driver):
        return self._ui_state(driver) == "call"

    def _is_chat_page(self, driver):
        return self._ui_state(driver) == "chat"

    def _ensure_chat_page(self, device_sn, driver, task_id=None, test_case_id=None):
        """把豆包校正到聊天页（冷启动可能落到设置页/抽屉；抽屉按 BACK 会直接退 App）。"""
        for _ in range(6):
            if self._check_stop("initialize_落点校正"):
                return False
            state = self._ui_state(driver)
            if state == "chat":
                return True
            try:
                if state == "call":
                    self._hangup(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
                elif state == "settings":
                    el = driver(resourceId=self.SETTINGS_BACK_RES_ID)
                    if el.exists:
                        el.click()
                elif state == "drawer":
                    titles = driver(resourceId=self.CONV_TITLE_RES_ID)
                    if int(titles.count) > 0:
                        titles[0].click()
                    else:
                        self._launch_app(device_sn, driver)
                else:
                    self._launch_app(device_sn, driver)
            except Exception as e:
                self._log(level="DEBUG", content=f"落点校正点击失败(忽略): {e}",
                          task_id=task_id, test_case_id=test_case_id)
            time.sleep(1.5)
        state = self._ui_state(driver)
        self._log(level="WARNING" if state != "chat" else "DEBUG",
                  content=f"初始化落点校正结束: state={state}",
                  task_id=task_id, test_case_id=test_case_id)
        return state == "chat"

    def _open_drawer(self, device_sn, driver, task_id=None, test_case_id=None):
        """打开对话列表抽屉；已在抽屉直接返回 True。"""
        if self._ui_state(driver) == "drawer":
            return True
        if self._is_call_page(driver):
            self._hangup(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
        el = driver(resourceId=self.MENU_ENTRY_RES_ID)
        if not el.exists:
            el = driver(resourceId=self.SETTINGS_ENTRY_RES_ID)
        if el.exists:
            try:
                el.click()
            except Exception:
                return False
        deadline = time.time() + 8
        while time.time() < deadline:
            if self._ui_state(driver) == "drawer":
                return True
            time.sleep(0.5)
        return False

    def _count_bubbles(self, driver):
        try:
            return int(driver(resourceId=self.BUBBLE_RES_ID).count)
        except Exception:
            return 0

    def _is_status_text(self, text):
        """AI 气泡是否为“搜索/生成中”等过程态文案。"""
        if not text:
            return False
        t = text.strip()
        return any(re.match(p, t) for p in self.AI_STATUS_PATTERNS)

    def _read_bubbles(self, driver):
        """读取消息列表气泡，返回 (最后一条用户文本, 该用户消息下方最后一条 AI 正文, 是否生成中)。

        实测规则（ui_probe_report §5）：``content_view`` 是气泡行；左边界 == 39 为 AI 气泡，
        > 39 为用户气泡；左边界 == 0 是推荐问题 chips 行（排除）。气泡内第一个 TextView
        是正文；AI 生成中（v_dot 动画）时气泡里没有 TextView。
        过滤“搜索 N 个关键词/参考 N 篇资料”等过程态气泡，避免把搜索状态当最终回答。
        """
        question = answer = None
        user_items, ai_items = [], []
        try:
            cvs = driver(resourceId=self.BUBBLE_RES_ID)
            count = int(cvs.count)
        except Exception:
            return None, None, False
        for i in range(count):
            try:
                elem = cvs[i]
                info = elem.info or {}
                bounds = self._bounds_dict(info)
                left = bounds.get("left", -1)
                top = bounds.get("top", 0)
                if left <= 0:
                    continue  # 推荐问题 chips 行
                tv = elem.child(className="android.widget.TextView")
                if not tv.exists:
                    continue  # AI 生成中（v_dot）或空气泡
                text = (tv.get_text() or "").strip()
                if not text:
                    continue
                if left <= 45:
                    ai_items.append((top, text))
                else:
                    user_items.append((top, text))
            except Exception:
                continue
        if user_items:
            user_top, question = max(user_items, key=lambda x: x[0])
            below = [text for top, text in ai_items if top > user_top]
            answer = None
            for text in reversed(below):
                if not self._is_status_text(text):
                    answer = text
                    break
        generating = bool(question and not answer)
        return question, answer, generating

    def _extract_chat_bubbles(self, driver, task_id=None, test_case_id=None):
        """从消息列表提取本轮“最后一条用户消息”和“最后一条 AI 回复”。"""
        question, answer, generating = self._read_bubbles(driver)
        self._log(level="DEBUG",
                  content=(f"气泡提取: question={question!r} answer={answer!r} "
                           f"generating={generating}"),
                  task_id=task_id, test_case_id=test_case_id)
        return question, answer

    def _wait_chat_bubbles(self, driver, baseline_count=None, timeout=60,
                           task_id=None, test_case_id=None):
        """等本轮通话气泡落表、并等 AI 文本生成完，再取最后一条问答。"""
        deadline = time.time() + max(5, int(timeout))
        start_ts = time.time()
        last_answer = None
        stable = 0
        question = answer = None
        while time.time() < deadline:
            if self._check_stop("post_process_等气泡"):
                break
            count = self._count_bubbles(driver)
            question, answer, _generating = self._read_bubbles(driver)
            fresh = baseline_count is None or count > baseline_count
            if fresh and answer:
                if answer == last_answer:
                    stable += 1
                else:
                    last_answer = answer
                    stable = 1
                if stable >= 2:
                    break
            # 通话没有产生转写（无用户气泡且气泡数没增加）：无需干等
            if (not question and not fresh
                    and (time.time() - start_ts) >= 20):
                break
            time.sleep(1.0)
        self._log(level="INFO",
                  content=(f"气泡落表: question={question!r} answer={answer!r} "
                           f"baseline={baseline_count} timeout={timeout}"),
                  task_id=task_id, test_case_id=test_case_id)
        return question, answer

    def _enter_voice_call(self, device_sn, driver, task_id=None, test_case_id=None):
        """点击右上角“打电话”进入语音通话（点可点的父容器；图标本身 clickable=false）。"""
        entry = driver(resourceId=self.CALL_ENTRY_CONTAINER_RES_ID)
        if not entry.exists:
            entry = driver(resourceId=self.REAL_CALL_ICON_RES_ID)
        if not entry.exists:
            entry = driver(description="打电话")
        if not entry.exists:
            self._log(level="ERROR", content="未找到通话入口(real_time_call)",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        try:
            entry.click()
        except Exception as e:
            self._log(level="WARNING", content=f"点击通话入口失败，尝试坐标兜底: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            try:
                width, height = driver.window_size()
                driver.click(width * 0.81, height * 0.084)
            except Exception as e2:
                self._log(level="ERROR", content=f"通话入口点击失败: {e2}",
                          task_id=task_id, test_case_id=test_case_id)
                return False
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._check_stop("initialize_进入通话"):
                return False
            if self._ui_state(driver) == "call":
                self._log(level="INFO", content="已进入豆包语音通话页",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            time.sleep(0.5)
        self._log(level="ERROR", content="进入语音通话页超时",
                  task_id=task_id, test_case_id=test_case_id)
        return False

    def _hangup(self, device_sn, driver, task_id=None, test_case_id=None):
        """挂断通话；通话页不存在时视为成功。"""
        if not self._is_call_page(driver):
            return True
        btn = driver(resourceId=self.HANGUP_RES_ID)
        try:
            if btn.exists:
                btn.click()
            else:
                width, height = driver.window_size()
                driver.click(width * 0.5, height * 0.886)
        except Exception as e:
            self._log(level="WARNING", content=f"挂断点击失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if not btn.exists:
                    self._log(level="DEBUG", content="通话已挂断",
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        self._log(level="WARNING", content="挂断后通话页仍存在",
                  task_id=task_id, test_case_id=test_case_id)
        return False

    def _start_new_conversation(self, device_sn, driver, task_id=None, test_case_id=None):
        """抽屉 →「新对话」：开启全新会话，等价鸿蒙里“开启新话题/清除上下文”，可逆。"""
        if not self._open_drawer(device_sn, driver, task_id=task_id, test_case_id=test_case_id):
            return False
        hints = driver(resourceId=self.NEW_CHAT_HINT_RES_ID)
        try:
            if int(hints.count) <= 0:
                return False
            hints[0].click()
        except Exception as e:
            self._log(level="WARNING", content=f"点击「新对话」失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        deadline = time.time() + 8
        while time.time() < deadline:
            if (self._ui_state(driver) == "chat"
                    and not driver(resourceId=self.MESSAGE_LEFT_RES_ID).exists):
                self._log(level="INFO", content="已开启新对话(上下文已清空)",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            time.sleep(0.5)
        return self._ui_state(driver) == "chat"

    def _delete_conversation(self, device_sn, driver, task_id=None, test_case_id=None):
        """抽屉 → 长按会话 →「从对话列表删除」→ 确认删除（不可恢复，谨慎使用）。"""
        if not self._open_drawer(device_sn, driver, task_id=task_id, test_case_id=test_case_id):
            return False
        titles = driver(resourceId=self.CONV_TITLE_RES_ID)
        try:
            if int(titles.count) <= 0:
                return False
            titles[0].long_click(duration=0.9)
        except Exception as e:
            self._log(level="WARNING", content=f"长按会话失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        time.sleep(1.8)
        rm = driver(resourceId=self.MENU_REMOVE_RES_ID)
        if not rm.exists:
            rm = driver(text="从对话列表删除")
        if not rm.exists:
            self._log(level="WARNING", content="长按菜单里未找到「从对话列表删除」",
                      task_id=task_id, test_case_id=test_case_id)
            try:
                driver.press("back")
            except Exception:
                pass
            return False
        rm.click()
        time.sleep(1.5)
        title = driver(resourceId=self.DIALOG_TITLE_RES_ID)
        title_text = ""
        try:
            if title.exists:
                title_text = title.get_text() or ""
        except Exception:
            pass
        if title.exists and "删除" not in title_text:
            cancel = driver(resourceId=self.DIALOG_CANCEL_RES_ID)
            if cancel.exists:
                cancel.click()
            self._log(level="WARNING", content=f"删除确认弹窗文案不符，已取消: {title_text!r}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        confirm = driver(resourceId=self.DIALOG_CONFIRM_RES_ID)
        if confirm.exists:
            confirm.click()
            time.sleep(1.5)
            self._log(level="INFO", content="已删除当前对话记录",
                      task_id=task_id, test_case_id=test_case_id)
            return True
        return False

    def _clear_chat_history(self, device_sn, driver, task_id=None, test_case_id=None,
                            mode="new"):
        """清上下文/清记录（Android 等价实现）。

        mode='new'（默认，可逆）：抽屉 →「新对话」，等价鸿蒙的“开启新话题”；
        mode='delete'：先删当前会话（不可恢复），再开新对话。
        """
        try:
            if mode == "delete":
                if not self._delete_conversation(device_sn, driver, task_id=task_id,
                                                 test_case_id=test_case_id):
                    self._log(level="WARNING",
                              content="删除对话失败，继续用新对话隔离上下文",
                              task_id=task_id, test_case_id=test_case_id)
            ok = self._start_new_conversation(device_sn, driver, task_id=task_id,
                                              test_case_id=test_case_id)
            if not ok:
                self._log(level="WARNING",
                          content="新建对话失败(可能沿用旧会话上下文)",
                          task_id=task_id, test_case_id=test_case_id)
            return ok
        except Exception as e:
            self._log(level="WARNING", content=f"清聊天记录失败(跳过继续): {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化：解锁 → 关弹窗 → 回桌面 → 停豆包 → 拉起 → 清聊天记录 → 复位状态。"""
        self._log(level="INFO",
                  content=f"Initializing Doubao on Android device {device_sn}...",
                  task_id=task_id, test_case_id=test_case_id)
        driver = self._get_u2(device_sn)
        if not driver:
            return False
        # 清理上个用例可能残留的 screenrecord / scrcpy 进程（异常路径兜底，失败忽略）
        try:
            self._adb_shell(device_sn, "pkill", "-INT", "screenrecord", timeout=10)
        except Exception:
            pass
        try:
            if kill_all_scrcpy is not None:
                kill_all_scrcpy()
            else:
                subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"],
                               check=False, capture_output=True, timeout=10)
        except Exception:
            pass
        try:
            self.unlock(device_sn, **kwargs)
            if self._check_stop("initialize"):
                return False
            self.close_popups(device_sn)
            try:
                driver.press("home")
                time.sleep(1)
            except Exception:
                pass
            # 停豆包（不碰其它 App）
            try:
                driver.app_stop(self.APP_NAME)
            except Exception as e:
                self._log(level="DEBUG", content=f"app_stop 失败(忽略): {e}",
                          task_id=task_id, test_case_id=test_case_id)
            if self._check_stop("initialize"):
                return False
            if not self._launch_app(device_sn, driver):
                return False
            time.sleep(3)
            self.close_popups(device_sn)
            # 冷启动落点不确定（可能落在设置页/抽屉），校正到聊天页
            if not self._ensure_chat_page(device_sn, driver, task_id=task_id,
                                          test_case_id=test_case_id):
                self._log(level="WARNING", content="初始化未能校正到豆包聊天页(继续尝试)",
                          task_id=task_id, test_case_id=test_case_id)
            # 复位跨用例状态（驱动单例复用）
            self._case_epoch = uuid.uuid4().hex
            self._pcm_baseline = {}
            self._recording = False
            self._record_mode = kwargs.get("record_mode", "round")
            self._total_rounds = 1
            self._round_number = 0
            self._record_file_name = None
            self._record_device_path = None
            self._record_pulled = False
            self._recorder_first_frame_ms = None
            self._recorder_start_ts = None
            self._ai_first_frame_ms = None
            self._round_audio_start_ms = None
            self._audio_recorders = {}
            self._audio_paths = {}
            self._audio_start_ts = {}
            self._ai_capture_birth_ts = None
            self._ai_capture_path = None
            self._audio_stopped = True
            self._audio_aligned = True
            self._screenrec_proc = None
            self.question_text = None
            self.answer_text = None
            self._bubble_count_base = None
            # 清理设备端驱动录屏目录（防跨用例残留/上轮大文件占空间）
            self._clear_device_recordings(device_sn, task_id=task_id, test_case_id=test_case_id)
            # 清理本地残留临时文件
            local_dir = self._case_local_dir(task_id, test_case_id, device_sn)
            if os.path.isdir(local_dir):
                for name in os.listdir(local_dir):
                    if name.endswith(self.PART_FILE_SUFFIX):
                        self._remove_quietly(os.path.join(local_dir, name))
            # 清聊天记录/上下文（失败不阻断）
            self._clear_chat_history(
                device_sn, driver, task_id=task_id, test_case_id=test_case_id,
                mode=kwargs.get("clear_history_mode", "new"))
            # scrcpy 可用性预检（不可用时仅降级，不阻断）
            if ScrcpyAudioRecorder is None:
                self._log(level="WARNING",
                          content="scrcpy 音频模块缺失：本轮无 user_wav/ai_wav，回复检测走 audio_flinger",
                          task_id=task_id, test_case_id=test_case_id)
            return True
        except Exception as e:
            self._log(level="ERROR", content=f"初始化豆包失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """每轮预处理：进通话（首轮）→ 启动录屏 → 启动双通道音频抓取。"""
        driver = self._get_u2(device_sn)
        if not driver:
            return False
        record_mode = kwargs.get("record_mode", "round")
        total_rounds = kwargs.get("total_rounds", 1)
        round_number = kwargs.get("round_number", 0)
        is_interruption = self._as_bool(kwargs.get("is_interruption"))
        self._record_mode = record_mode
        self._total_rounds = total_rounds
        self._round_number = round_number
        is_first = not getattr(self, "_recording", False)
        self.question_text = None
        self.answer_text = None
        self._ai_first_frame_ms = None
        self._log(level="DEBUG",
                  content=(f"pre_process: mode={record_mode} r{round_number}/{total_rounds} "
                           f"is_interruption={is_interruption} first={is_first}"),
                  task_id=task_id, test_case_id=test_case_id)

        # 防音频污染：停掉可能被误拉起的音乐 App（每轮都清，与鸿蒙版一致）
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)

        # case 模式非首轮：通话与录屏持续中，只需重启本轮音频抓取
        if record_mode == "case" and not is_first:
            self._start_audio_capture(device_sn, test_case_id, round_number,
                                      task_id=task_id,
                                      **self._audio_capture_kwargs(kwargs))
            self._round_audio_start_ms = int(time.time() * 1000)
            return True

        # 首轮（round 模式每轮都算首轮）：确保在豆包聊天首页（冷启动落点可能漂移），
        # 记录本轮气泡基数（挂断后判断“本轮新增气泡”），再进通话
        if not self._is_call_page(driver):
            if not self._is_chat_page(driver):
                self._ensure_chat_page(device_sn, driver, task_id=task_id,
                                       test_case_id=test_case_id)
            self._bubble_count_base = self._count_bubbles(driver)
        if not self._is_call_page(driver):
            if not self._enter_voice_call(device_sn, driver, task_id=task_id,
                                          test_case_id=test_case_id):
                return False
        # 录屏文件命名：case=整用例一段；round=每轮一段
        if record_mode == "case":
            self._record_file_name = f"{test_case_id}.mp4"
        else:
            self._record_file_name = f"{test_case_id}_r{round_number}.mp4"
        # 先启动音频抓取（AI 可能在通话连接后立即开口），再开录屏
        self._start_audio_capture(device_sn, test_case_id, round_number,
                                  task_id=task_id,
                                  **self._audio_capture_kwargs(kwargs))
        if not self._start_recorder(device_sn, file_name=self._record_file_name):
            self._log(level="ERROR",
                      content=f"启动录屏失败: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            # 录屏失败不直接判死：音频/问答仍可继续（与鸿蒙“服务未运行”判失败不同，
            # 安卓 screenrecord 不可用时降级为无 mp4，避免整条用例被录制能力拖垮）
        else:
            self._recording = True
        self._round_audio_start_ms = int(time.time() * 1000)
        time.sleep(2)
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理：等 AI 回复结束 → 收尾（停录屏/挂断/提取问答），按 round/case 分流。"""
        driver = self._get_u2(device_sn)
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level="INFO",
                  content=(f"[post_process] 播放时间戳 "
                           f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                           f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                           f"(detail_count={len(ts['detail']) if ts['detail'] else 0})"),
                  task_id=task_id, test_case_id=test_case_id)
        if not driver:
            return False

        # 等 AI 回复
        if self._as_bool(kwargs.get("is_interruption")):
            status, _ = self._wait_ai_reply_start_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                start_timeout=kwargs.get("ai_start_timeout", None))
            replied = status in ("fresh", "ended")
            self._log(level="INFO",
                      content=(f"[post_process] is_interruption,等AI开始回复后放下一轮"
                               f"(barge-in): status={status}"),
                      task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = "豆包识别为空"
                self.answer_text = "豆包回复为空"
        else:
            replied = self._wait_ai_reply_end_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = "豆包识别为空"
                self.answer_text = "豆包回复为空"

        # 本轮音频抓取收尾（round/case 均每轮独立抓取）
        self._stop_audio_capture(task_id=task_id, test_case_id=test_case_id)
        # 两路音频先后启动/录屏又晚于音频，收尾时统一裁到同一 t=0（见 _align_audio_channels）
        if not getattr(self, "_audio_aligned", True):
            self._align_audio_channels(task_id=task_id, test_case_id=test_case_id,
                                       record_mode=getattr(self, "_record_mode", "round"))
            self._audio_aligned = True
        # 用对齐后的音频真实起声点修正 first_frame_ms（消除轮询/落盘缓冲误差）
        self._update_ai_first_frame_from_audio(task_id=task_id, test_case_id=test_case_id)

        record_mode = getattr(self, "_record_mode", "round")
        round_number = getattr(self, "_round_number", 0)
        total_rounds = getattr(self, "_total_rounds", 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        # case 模式打断轮非末轮：检测到 AI 开始回复后延迟 1s 再放下一轮（真 barge-in）
        if (self._as_bool(kwargs.get("is_interruption")) and replied
                and record_mode == "case" and not is_last):
            self._log(level="INFO",
                      content=f"[post_process] 检测到AI开始回复,等1s后进入下一轮播放: "
                              f"r{round_number}/{total_rounds}",
                      task_id=task_id, test_case_id=test_case_id)
            for _ in range(2):
                if self._check_stop("AI回复后延迟1s"):
                    return True
                time.sleep(0.5)

        if record_mode == "case":
            # case 模式：一次连续通话 / 一个录屏 / 全程不挂断
            if not is_last:
                self._log(level="DEBUG",
                          content=f"case模式中间轮,不挂断保持语音/录屏进行中: "
                                  f"r{round_number}/{total_rounds}",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            if getattr(self, "_recording", False):
                if not self._stop_recorder(device_sn, task_id=task_id,
                                           test_case_id=test_case_id):
                    self._log(level="WARNING", content="末轮停止录屏失败",
                              task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(3)
            self._log(level="INFO",
                      content="case模式末轮不挂断,通话交给 teardown 结束(保持上下文连续)",
                      task_id=task_id, test_case_id=test_case_id)
            return True

        # round 模式：每轮独立——停录屏 + 挂断 + 提取气泡
        if getattr(self, "_recording", False):
            if not self._stop_recorder(device_sn, task_id=task_id,
                                       test_case_id=test_case_id):
                self._log(level="WARNING", content="停止录屏失败",
                          task_id=task_id, test_case_id=test_case_id)
        self._recording = False
        time.sleep(3)
        self._hangup(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
        time.sleep(2)
        if not replied:
            return True
        # 挂断后气泡落表需要时间（AI 先显示 v_dot 打字态、十几秒后才出文本），
        # 这里等本轮新增气泡且 AI 文本稳定后再取，避免抓到欢迎语/上一条历史回复
        self.question_text, self.answer_text = self._wait_chat_bubbles(
            driver, baseline_count=getattr(self, "_bubble_count_base", None),
            timeout=kwargs.get("bubble_timeout", 60),
            task_id=task_id, test_case_id=test_case_id)
        return True

    def _compute_turn_latency(self, played_audios, fallback_start_ms=None,
                              fallback_end_ms=None, ai_start_ms=None):
        """计算本轮“用户问题播放 → AI 起声”的时延（毫秒）。

        只统计 dry/interferer；noise 是背景声，不计入问题窗口。若没有
        dry/interferer 明细，退回本轮整体 playback_start/end。AI 起声点用
        对齐后的 first_frame_ms（内部已按 AI 音频真实 onset 修正）。
        """
        entries = []
        for item in played_audios or []:
            if not isinstance(item, dict):
                continue
            start = item.get("playback_start_time_ms", item.get("start_ms"))
            end = item.get("playback_end_time_ms", item.get("end_ms"))
            audio_type = str(item.get("audio_type") or "dry").lower()
            try:
                start = int(start) if start is not None else None
                end = int(end) if end is not None else None
            except (TypeError, ValueError):
                continue
            if start is None or end is None or end < start:
                continue
            entries.append((audio_type, start, end))

        question_entries = [e for e in entries if e[0] in ("dry", "interferer")]
        if not question_entries:
            question_entries = entries
        if question_entries:
            question_start_ms = min(e[1] for e in question_entries)
            question_end_ms = max(e[2] for e in question_entries)
        else:
            try:
                question_start_ms = int(fallback_start_ms) if fallback_start_ms is not None else None
                question_end_ms = int(fallback_end_ms) if fallback_end_ms is not None else None
            except (TypeError, ValueError):
                question_start_ms = question_end_ms = None

        try:
            ai_start_ms = int(ai_start_ms) if ai_start_ms is not None else None
        except (TypeError, ValueError):
            ai_start_ms = None

        result = {
            "question_start_ms": question_start_ms,
            "question_end_ms": question_end_ms,
            "ai_start_ms": ai_start_ms,
            "question_to_ai_ms": None,
            "question_end_to_ai_ms": None,
            "played_count": len(entries),
        }
        if ai_start_ms is not None and question_start_ms is not None:
            result["question_to_ai_ms"] = ai_start_ms - question_start_ms
        if ai_start_ms is not None and question_end_ms is not None:
            result["question_end_to_ai_ms"] = ai_start_ms - question_end_ms
        return result

    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> list:
        """采集本轮结果：mp4（留痕）+ user_wav/ai_wav（评估音频）+ 问答文本。"""
        if self._mock_mode:
            return [{
                "success": True, "message": "Mock", "record_path": "",
                "record_device_path": "", "wav_path": "",
                "start_ms": None, "end_ms": None, "first_frame_ms": None,
                "question": "Mock question", "answer": "Mock answer",
                "user_wav": "", "ai_wav": "",
            }]
        ts = self._extract_playback_timestamps(kwargs)
        # 幂等收尾音频（正常已在 post_process 停掉；异常路径兜底）
        self._stop_audio_capture(task_id=task_id, test_case_id=test_case_id)
        # 合成方案：用户音频来自平台实际播放的文件 + 时间戳，而不是手机麦克风
        user_audio_source = str(kwargs.get("user_audio_source") or "")
        played_audios = kwargs.get("played_audios") or []
        if isinstance(played_audios, str):
            import json
            try:
                played_audios = json.loads(played_audios)
            except Exception:
                played_audios = []
        if user_audio_source.startswith("synth") and played_audios:
            if self._synthesize_from_played(device_sn, played_audios,
                                            task_id=task_id,
                                            test_case_id=test_case_id):
                self._log(level="INFO", content="已按 played_audios 合成 user_wav 并对齐 AI 通道",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level="WARNING", content="合成 user_wav 失败，回退到原有通道对齐",
                          task_id=task_id, test_case_id=test_case_id)
        if not getattr(self, "_audio_aligned", True):
            self._align_audio_channels(task_id=task_id, test_case_id=test_case_id,
                                       record_mode=getattr(self, "_record_mode", "round"))
            self._audio_aligned = True
        if not self._ai_first_frame_ms:
            self._update_ai_first_frame_from_audio(task_id=task_id, test_case_id=test_case_id)
        user_wav = self._audio_paths.get("user")
        ai_wav = self._audio_paths.get("ai")
        # 全静音告警：安卓在豆包通话中会静音普通麦克风捕获，且豆包可能静音播放，
        # 这里显式提示，避免用例“成功”但音频为空而无人察觉
        for _role, _path in (("user", user_wav), ("ai", ai_wav)):
            peak = self._wav_peak(_path) if _path else None
            if peak is not None and peak < 30:
                self._log(level="WARNING",
                          content=(f"{_role}_wav 全静音(peak={peak}): 检查音频源"
                                   f"(user_audio_source/mic_source)以及豆包是否实际出声"),
                          task_id=task_id, test_case_id=test_case_id)
        question_text = getattr(self, "question_text", None)
        answer_text = getattr(self, "answer_text", None)
        first_frame_ms = getattr(self, "_ai_first_frame_ms", None) \
            or getattr(self, "_recorder_first_frame_ms", None)
        latency_ms = self._compute_turn_latency(
            played_audios or ts.get("detail") or [],
            fallback_start_ms=ts.get("start_ms"),
            fallback_end_ms=ts.get("end_ms"),
            ai_start_ms=first_frame_ms,
        )
        record_mode = getattr(self, "_record_mode", "round")
        recording = getattr(self, "_recording", False)

        base_result = {
            "start_ms": ts["start_ms"],
            "end_ms": ts["end_ms"],
            "first_frame_ms": first_frame_ms,
            "ai_audio_start_ts": (self._audio_start_ts or {}).get("ai"),
            "latency_ms": latency_ms,
            "question": question_text or "",
            "answer": answer_text or "",
            "user_wav": user_wav or "",
            "ai_wav": ai_wav or "",
        }

        # case 模式且录屏仍在进行（非末轮）：mp4 是整段文件，中途拉是半截，留到末轮；
        # 但对话音频每轮都要给（打断/话轮指标需要逐轮音频）
        if record_mode == "case" and recording:
            self._log(level="DEBUG",
                      content=f"case模式录屏进行中,跳过录屏mp4,仍给对话音频: "
                              f"user_wav={user_wav} ai_wav={ai_wav}",
                      task_id=task_id, test_case_id=test_case_id)
            return [dict(base_result, success=True,
                         message="recording in progress (audio ready, mp4 deferred to final round)",
                         record_path="",
                         record_device_path=getattr(self, "_record_device_path", "") or "",
                         wav_path="")]

        # 录屏已停：拉取 mp4（若录屏能力不可用则 record_path 为空）
        record_path = ""
        device_path = getattr(self, "_record_device_path", "") or ""
        if device_path and getattr(self, "_record_file_name", None):
            local_path = self._pull_record_file(device_sn, task_id=task_id,
                                                test_case_id=test_case_id)
            if local_path:
                record_path = local_path
                # screenrecord 无音轨，mp4→wav 通常失败；wav_path 复用 ai_wav 供评估/试听
                self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
        wav_path = ai_wav or ""
        self._log(level="INFO",
                  content=(f"[get_results] record_path={record_path} wav_path={wav_path} "
                           f"user_wav={user_wav} ai_wav={ai_wav} "
                           f"question={question_text!r} answer={answer_text!r}"),
                  task_id=task_id, test_case_id=test_case_id)
        return [dict(base_result, success=True, message="Success",
                     record_path=record_path,
                     record_device_path=device_path,
                     wav_path=wav_path)]

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束清理（与 initialize 对称）：停录屏/停音频/挂断/回桌面/停 App/清残留。"""
        # 1. 兜底停止录屏
        if getattr(self, "_recording", False):
            try:
                self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level="WARNING", content=f"teardown: 停止录屏失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
        self._recording = False
        # 2. 兜底停止音频抓取
        try:
            self._stop_audio_capture(task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level="WARNING", content=f"teardown: 停止音频抓取失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
        driver = self._get_u2(device_sn)
        if driver:
            # 3. 兜底挂断残留通话
            try:
                self._hangup(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level="DEBUG", content=f"teardown: 无残留通话或挂断失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
            # 4. 回桌面
            try:
                driver.press("home")
                time.sleep(1)
            except Exception as e:
                self._log(level="WARNING", content=f"teardown: 回桌面失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
            # 5. 停音乐 App（防跨用例残留）
            self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)
            # 6. 停止豆包
            try:
                driver.app_stop(self.APP_NAME)
                self._log(level="DEBUG", content="teardown: 已停止豆包 APP",
                          task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level="WARNING", content=f"teardown: 停止豆包失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
        # 7. 清设备录屏目录 + 本地临时文件
        self._clear_device_recordings(device_sn, task_id=task_id, test_case_id=test_case_id)
        local_dir = self._case_local_dir(task_id, test_case_id, device_sn)
        if os.path.isdir(local_dir):
            for name in os.listdir(local_dir):
                if name.endswith(self.PART_FILE_SUFFIX):
                    self._remove_quietly(os.path.join(local_dir, name))
        return True

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def _stop_music_app(self, device_sn, task_id=None, test_case_id=None):
        """停止可能被误拉起的音乐类 App（失败仅告警，不阻断主流程）。"""
        for pkg in self.MUSIC_PACKAGES:
            try:
                self._adb_shell(device_sn, "am", "force-stop", pkg, timeout=5)
            except Exception:
                continue
        self._log(level="DEBUG", content="已兜底停止音乐类 App",
                  task_id=task_id, test_case_id=test_case_id)
