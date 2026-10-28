# -*- coding: utf-8 -*-
"""scrcpy 音频抓取基础设施（Android 真机 playback / mic 双通道）。

用途
----
为 Android 语音类驱动（豆包语音通话等）提供两条独立的音频抓取通道：

* ``playback``：抓设备"播放"出来的声音（豆包 TTS / 对方语音），对应鸿蒙驱动里的 ai_wav；
* ``mic`` / ``mic-voice-communication``：抓设备麦克风（用户说话），对应 user_wav。

两者可以同时跑（每路一个 scrcpy 实例，各自独立的 adb 连接与 server socket），
实测 48kHz / 双声道 / s16le 的 wav，可直接喂评估系统。

设计要点
--------
1. **只用标准库**：不依赖 numpy / pydub，驱动线程里 import 也不会拖慢启动。
2. **异常不外抛**：所有公开方法内部吞掉异常，失败返回 False / None 并记录到日志，
   避免把驱动的执行线程带崩（``stop()`` 例外地也不会抛）。
3. **wav 头可修复**：scrcpy 正常结束会回填 wav 头，被强杀时 data chunk 的 size 字段
   是 0 或 0xFFFFFFFF。``stop()`` 会就地打补丁（只改 RIFF size / data size 两个
   字段，不重写数据），必要时退回 ffmpeg 从裸 PCM 重建。
4. **录制中可读尾部**：``read_tail_rms()`` 按 chunk 解析出真正的 data 偏移
   （scrcpy 会写 ``LIST/INFO`` 块，实际偏移是 110 字节而不是 44 字节！不要写死 44），
   再读文件尾部若干秒做左声道 RMS，供"豆包是否在说话"的实时判定用。

典型用法::

    from backend.utils.device_driver.android_scrcpy_audio import ScrcpyAudioRecorder

    rec = ScrcpyAudioRecorder("EP0110MZ0BC050906W", log_dir="./.tmp_probe")
    if rec.start("playback", r"D:\tmp\ai.wav"):
        ...
        rms = rec.read_tail_rms(rec.out_path, seconds=1.0)   # 录制中实时读
        path = rec.stop()                                    # 修复并返回可用路径

命令模板（已在本机 nubia P0110 / Android 16 / scrcpy 4.1 实测）::

    scrcpy.exe -s <sn> --no-window --no-video --no-playback \
        --audio-source=<playback|mic|mic-voice-communication> \
        --audio-codec=raw --record=<out.wav> --record-format=wav --no-cleanup
"""

from __future__ import annotations

import array
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

__all__ = [
    "ScrcpyAudioRecorder",
    "resolve_scrcpy_path",
    "resolve_ffmpeg_path",
    "kill_all_scrcpy",
    "VALID_SOURCES",
    "AUDIO_SAMPLE_RATE",
    "AUDIO_CHANNELS",
    "AUDIO_SAMPLE_WIDTH",
    "AUDIO_BLOCK_ALIGN",
]

# --------------------------------------------------------------------------- #
# 实测常量：设备端 AudioRecord 输出为 48kHz / 立体声 / 16bit little-endian
# --------------------------------------------------------------------------- #
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_SAMPLE_WIDTH = 2                                     # s16le
AUDIO_BLOCK_ALIGN = AUDIO_CHANNELS * AUDIO_SAMPLE_WIDTH     # 4 字节/帧
WAV_DEFAULT_DATA_OFFSET = 44                               # 兜底值（scrcpy 实际是 110）

# 常用音频源。playback/mic/mic-voice-communication 是驱动默认三路；
# voice-call-uplink/downlink 用于“豆包通话中系统静音普通麦克风捕获”的兜底通道
# （uplink≈用户通道，downlink≈AI 通道），是否可用取决于设备/ROM，驱动侧做了回退。
VALID_SOURCES = (
    "playback", "mic", "mic-voice-communication",
    "voice-call-uplink", "voice-call-downlink",
)

# 录制启动成功的判定：日志出现 Recording started，或 wav 里已有真实音频
_START_LOG_PATTERN = re.compile(r"Recording started", re.IGNORECASE)
_NO_WINDOW = 0x08000000          # subprocess.CREATE_NO_WINDOW
_NEW_PROCESS_GROUP = 0x00000200  # subprocess.CREATE_NEW_PROCESS_GROUP

_HERE = Path(__file__).resolve().parent
_VENDORED_SCRCPY_DIR = _HERE / "bin" / "scrcpy"


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def _first_existing(paths: Sequence[Optional[str]]) -> Optional[str]:
    """返回第一个存在的路径（None 安全）。"""
    for p in paths:
        if not p:
            continue
        try:
            if os.path.isfile(p):
                return os.path.abspath(p)
        except Exception:
            continue
    return None


def resolve_scrcpy_path() -> Optional[str]:
    """解析 scrcpy.exe 的绝对路径。

    解析顺序：

    1. 环境变量 ``SCRCPY_PATH``（可以是 exe，也可以是含 scrcpy.exe / scrcpy-server 的目录）；
    2. 仓库内置目录 ``<driver>/bin/scrcpy/scrcpy.exe``；
    3. 系统 ``PATH`` 里的 ``scrcpy``；
    4. 开发机兜底：``D:/work/_android/scrcpy-win64-*/scrcpy.exe``（便携版目录）。

    返回第一个命中的绝对路径；全部落空返回 ``None``（调用方应记录告警而不是抛异常）。
    """
    candidates: List[Optional[str]] = []

    env_path = os.environ.get("SCRCPY_PATH", "").strip().strip('"')
    if env_path:
        candidates.append(env_path)
        candidates.append(os.path.join(env_path, "scrcpy.exe"))

    candidates.append(str(_VENDORED_SCRCPY_DIR / "scrcpy.exe"))

    try:
        which_exe = shutil.which("scrcpy.exe") or shutil.which("scrcpy")
        candidates.append(which_exe)
    except Exception:
        pass

    # 开发机兜底：本机便携版（GitHub 不可达，靠它跑）
    try:
        for pattern in (
            r"D:\work\_android\scrcpy-win64-*\scrcpy.exe",
            r"D:\work\_android\scrcpy\scrcpy.exe",
            os.path.expanduser(r"~\scrcpy\scrcpy.exe"),
        ):
            for hit in sorted(glob.glob(pattern), reverse=True):
                candidates.append(hit)
    except Exception:
        pass

    found = _first_existing(candidates)
    return found


def resolve_ffmpeg_path() -> Optional[str]:
    """解析 ffmpeg.exe（仅在 wav 头彻底损坏、需要重建时使用）。

    顺序：``FFMPEG_PATH`` → ``D:\\work\\ffmpeg\\bin\\ffmpeg.exe`` → PATH。
    """
    env_path = os.environ.get("FFMPEG_PATH", "").strip().strip('"')
    return _first_existing([
        env_path,
        os.path.join(env_path, "ffmpeg.exe") if env_path else None,
        r"D:\work\ffmpeg\bin\ffmpeg.exe",
        shutil.which("ffmpeg.exe") or shutil.which("ffmpeg"),
    ])


def kill_all_scrcpy(extra_image_names: Sequence[str] = ("scrcpy.exe",)) -> None:
    """强杀本机所有 scrcpy 进程（驱动退出/自测收尾用，异常忽略）。"""
    for image in extra_image_names:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                timeout=15,
            )
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# wav 头解析 / 修复
# --------------------------------------------------------------------------- #
def _parse_wav_layout(head: bytes) -> Optional[Tuple[int, int]]:
    """从 wav 文件头里解析出 (data_payload_offset, data_size_field_offset)。

    scrcpy 写的 wav 在 ``fmt `` 之后还有 ``LIST/INFO`` 块（含录制器备注），
    因此 data 的起始偏移通常是 110 而非 44，必须按 chunk 链走。

    返回 None 表示不是可识别的 RIFF/WAVE（可能记录介质还没刷头）。
    """
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return None
    pos = 12
    limit = len(head)
    while pos + 8 <= limit:
        chunk_id = head[pos:pos + 4]
        try:
            chunk_size = int.from_bytes(head[pos + 4:pos + 8], "little")
        except Exception:
            return None
        if chunk_id == b"data":
            return pos + 8, pos + 4
        if chunk_size < 0 or chunk_size > 0x7FFFFFFF:
            # 非法 size（scrcpy 未结束时的占位值），无法继续遍历
            return None
        pos += 8 + chunk_size + (chunk_size & 1)
    return None


def _read_head(path: str, size: int = 4096) -> bytes:
    with open(path, "rb") as f:
        return f.read(size)


def repair_wav(path: str, log=None) -> Optional[str]:
    """修复被强杀 scrcpy 留下的 wav（返回可用路径，失败返回 None）。

    两种策略：

    * **就地打补丁**（首选）：RIFF 结构完好、只是 RIFF/data 的 size 字段为 0 或
      0xFFFFFFFF —— 只改这两个字段，不碰音频数据，100MB 的录像也是毫秒级。
    * **从裸 PCM 重建**（兜底）：文件头彻底缺失/非法时，把整个文件按
      ``s16le 48k 立体声`` 当成裸 PCM，用 ffmpeg 重新封装一段 wav。
    """
    def _log(msg: str) -> None:
        if callable(log):
            try:
                log(msg)
            except Exception:
                pass

    try:
        if not os.path.isfile(path):
            return None
        file_size = os.path.getsize(path)
        if file_size <= 0:
            return None

        head = _read_head(path)
        layout = _parse_wav_layout(head)
        if layout is None:
            # 头还没写出来（极少见）或已损坏 —— 退回裸 PCM 重建
            return _rebuild_wav_from_raw(path, log=_log)

        data_off, size_field_off = layout
        actual = file_size - data_off
        if actual <= 0:
            _log(f"[repair_wav] data 段为空: {path}")
            return None
        actual -= actual % AUDIO_BLOCK_ALIGN          # 丢掉不完整的尾帧
        if actual <= 0:
            return None

        stored_riff = int.from_bytes(head[4:8], "little")
        stored_data = int.from_bytes(head[size_field_off:size_field_off + 4], "little")
        need_riff = data_off + actual - 8
        if stored_riff == need_riff and stored_data == actual:
            return path                                # 已经是好的，不动

        with open(path, "r+b") as f:
            if actual < file_size - data_off:
                f.truncate(data_off + actual)          # 切掉半帧尾巴
            f.seek(4)
            f.write(min(need_riff, 0xFFFFFFFF).to_bytes(4, "little"))
            f.seek(size_field_off)
            f.write(min(actual, 0xFFFFFFFF).to_bytes(4, "little"))
            f.flush()
            os.fsync(f.fileno())
        _log(f"[repair_wav] 头补丁完成 data_off={data_off} bytes={actual} path={path}")
        return path if _wav_readable(path) else _rebuild_wav_from_raw(path, log=_log)
    except Exception as exc:                            # noqa: BLE001
        _log(f"[repair_wav] 异常 {path}: {exc!r}")
        try:
            return _rebuild_wav_from_raw(path, log=_log)
        except Exception:
            return None


def _wav_readable(path: str) -> bool:
    """用 stdlib wave 验证可读且帧数 > 0。"""
    try:
        import wave

        with wave.open(path, "rb") as w:
            return w.getnframes() > 0
    except Exception:
        return False


def _rebuild_wav_from_raw(path: str, log=None) -> Optional[str]:
    """把（可能含头的）文件当成裸 s16le/48k/立体声 PCM，用 ffmpeg 重封装为 wav。"""
    def _log(msg: str) -> None:
        if callable(log):
            try:
                log(msg)
            except Exception:
                pass

    ffmpeg = resolve_ffmpeg_path()
    try:
        head = _read_head(path)
        layout = _parse_wav_layout(head)
        skip = layout[0] if layout else 0
        size = os.path.getsize(path)
        if size - skip < AUDIO_BLOCK_ALIGN:
            return None
        if not ffmpeg:
            _log("[repair_wav] 无 ffmpeg，无法重建")
            return None

        tmp_raw = path + ".raw.pcm"
        tmp_wav = path + ".rebuilt.wav"
        with open(path, "rb") as src, open(tmp_raw, "wb") as dst:
            src.seek(skip)
            shutil.copyfileobj(src, dst, 1024 * 1024)

        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "s16le", "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS),
             "-i", tmp_raw, "-c:a", "pcm_s16le", tmp_wav],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW, timeout=300,
        )
        if os.path.isfile(tmp_wav) and os.path.getsize(tmp_wav) > AUDIO_BLOCK_ALIGN:
            os.replace(tmp_wav, path)
            _log(f"[repair_wav] 裸 PCM 重建成功 {path}")
            return path if _wav_readable(path) else None
        return None
    except Exception as exc:                            # noqa: BLE001
        _log(f"[repair_wav] 重建失败 {path}: {exc!r}")
        return None
    finally:
        for tmp in (path + ".raw.pcm", path + ".rebuilt.wav"):
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# 录制器
# --------------------------------------------------------------------------- #
class ScrcpyAudioRecorder:
    """单设备单通道的 scrcpy 音频录制器（线程安全）。

    每个实例对应一路音频（playback 或 mic）。要同时抓两路就建两个实例、
    用同一个 device_sn 各起一路，scrcpy 自己会分配不同的 scid，互不冲突。

    :param device_sn: adb 序列号（``adb devices`` 里的那一列）。
    :param scrcpy_path: 可选，显式指定 scrcpy.exe；默认走 :func:`resolve_scrcpy_path`。
    :param log_dir: 可选，scrcpy 的 stdout/stderr 日志落盘目录；
        默认 ``<临时目录>/dsh_scrcpy_logs``（驱动侧建议传任务目录便于排错）。
    """

    def __init__(self, device_sn: str, scrcpy_path: Optional[str] = None,
                 log_dir: Optional[str] = None) -> None:
        self.device_sn = str(device_sn or "").strip()
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._log_path: Optional[str] = None
        self._log_handle = None
        self._out_path: Optional[str] = None
        self._source: Optional[str] = None
        self._start_ts: float = 0.0
        self._last_error: str = ""
        self._tag = "scrcpy"

        self._scrcpy_path = scrcpy_path or resolve_scrcpy_path()
        if log_dir:
            self._log_dir = os.path.abspath(str(log_dir))
        else:
            self._log_dir = os.environ.get("SCRCPY_LOG_DIR") or os.path.join(
                tempfile.gettempdir(), "dsh_scrcpy_logs"
            )

    # ---------------------------- 只读属性 ---------------------------- #
    @property
    def scrcpy_path(self) -> Optional[str]:
        """本次实例使用的 scrcpy.exe 路径（None 表示没找到）。"""
        with self._lock:
            return self._scrcpy_path

    @property
    def out_path(self) -> Optional[str]:
        """当前/最近的输出 wav 路径。"""
        with self._lock:
            return self._out_path

    @property
    def log_path(self) -> Optional[str]:
        """当前/最近的 scrcpy 日志路径。"""
        with self._lock:
            return self._log_path

    @property
    def source(self) -> Optional[str]:
        """当前/最近的音频源。"""
        with self._lock:
            return self._source

    @property
    def last_error(self) -> str:
        """最近一次失败原因（人读）。"""
        with self._lock:
            return self._last_error

    @property
    def pid(self) -> Optional[int]:
        """当前 scrcpy 进程 pid（没在录时为 None），便于外部 kill / 排查。"""
        with self._lock:
            proc = self._proc
            return proc.pid if proc is not None else None

    # ---------------------------- 生命周期 ---------------------------- #
    def start(self, source: str = "playback", out_path: Optional[str] = None,
              time_limit: Optional[int] = None,
              extra_args: Optional[Sequence[str]] = None,
              ready_timeout: float = 12.0) -> bool:
        """启动一路 scrcpy 纯音频录制。

        :param source: ``playback`` / ``mic`` / ``mic-voice-communication``。
        :param out_path: 输出 wav 路径（父目录不存在会尝试创建）。
        :param time_limit: 可选，秒；给 ``--time-limit`` 让 scrcpy 自己优雅收尾
            （这样 wav 头完整，不依赖 stop 修复）。给 None 表示不限时。
        :param extra_args: 追加参数（例如 ``["--audio-buffer=100"]``）。
        :param ready_timeout: 等待"真正开始录"的最长秒数。
        :return: 启动成功且已开始写音频返回 True，否则 False（原因见 ``last_error``）。
        """
        with self._lock:
            self._last_error = ""
            if not self.device_sn:
                self._fail("device_sn 为空")
                return False
            if source not in VALID_SOURCES:
                self._fail(f"不支持的 audio-source={source!r}，可选 {VALID_SOURCES}")
                return False
            if self._proc is not None and self._proc.poll() is None:
                self._fail(f"已在录制中（{self._source}），请先 stop()")
                return False
            if not self._scrcpy_path or not os.path.isfile(self._scrcpy_path):
                self._scrcpy_path = resolve_scrcpy_path()
            if not self._scrcpy_path:
                self._fail(
                    "找不到 scrcpy.exe（可设置环境变量 SCRCPY_PATH，或把便携版放到 "
                    f"{_VENDORED_SCRCPY_DIR}）"
                )
                return False
            if not out_path:
                self._fail("out_path 不能为空")
                return False

            out_path = os.path.abspath(str(out_path))
            try:
                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            except Exception as exc:                    # noqa: BLE001
                self._fail(f"创建输出目录失败: {exc!r}")
                return False
            # 清掉上一轮残留，避免读到旧数据
            try:
                if os.path.isfile(out_path):
                    os.remove(out_path)
            except Exception:
                pass

            cmd = self._build_cmd(source, out_path, time_limit, extra_args)
            self._tag = f"scrcpy[{source}]"
            self._log_path = self._next_log_path(source)
            try:
                os.makedirs(self._log_dir, exist_ok=True)
                self._log_handle = open(self._log_path, "wb")
            except Exception:
                self._log_handle = None
                self._log_path = None

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(self._scrcpy_path) or None,
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_handle or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if self._log_handle else subprocess.DEVNULL,
                    creationflags=_NO_WINDOW | _NEW_PROCESS_GROUP,
                    close_fds=True,
                )
            except Exception as exc:                    # noqa: BLE001
                self._proc = None
                self._close_log()
                self._fail(f"启动 scrcpy 失败: {exc!r}")
                return False

            self._out_path = out_path
            self._source = source
            self._start_ts = time.time()

        ok = self._wait_ready(ready_timeout)
        if not ok:
            tail = self.log_tail(12)
            self.stop(timeout=3)
            with self._lock:
                self._fail(f"scrcpy 未在 {ready_timeout:.0f}s 内开始录制; 日志尾部: {tail}")
            return False
        return True

    def stop(self, timeout: float = 10.0, repair: bool = True) -> Optional[str]:
        """停止录制并返回**可直接使用**的 wav 路径（失败返回 None）。

        顺序：``terminate`` → 等 ``timeout`` → ``kill``。scrcpy 在 Windows 上没有可
        靠的优雅信号，被 kill 时 wav 头里的 size 字段是占位值，因此随后调用
        :func:`repair_wav` 就地补头（毫秒级，不重写数据）。

        :param timeout: 等待进程退出的秒数。
        :param repair: 是否自动修复 wav 头（默认 True）。
        :return: 可用 wav 路径；若文件不存在或修复后仍不可读返回 None。
        """
        with self._lock:
            proc = self._proc
            out_path = self._out_path
            self._proc = None

        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=max(1.0, float(timeout) * 0.6))
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            pass
                else:
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                self._close_log()

        if not out_path:
            return None
        # scrcpy 被 kill 后可能仍在刷最后一块，给文件系统一点时间
        deadline = time.time() + 3.0
        last_size = -1
        while time.time() < deadline:
            try:
                size = os.path.getsize(out_path)
            except Exception:
                return None
            if size > 0 and size == last_size:
                break
            last_size = size
            time.sleep(0.1)

        if repair:
            fixed = repair_wav(out_path, log=self._log_line)
            if fixed:
                return fixed
            # 修复失败但文件本身可读（例如 scrcpy 正常收尾）
            return out_path if _wav_readable(out_path) else None
        return out_path if os.path.isfile(out_path) else None

    def is_running(self) -> bool:
        """录制进程是否还活着。"""
        with self._lock:
            proc = self._proc
            return bool(proc is not None and proc.poll() is None)

    # ---------------------------- 实时读数 ---------------------------- #
    def read_tail_rms(self, wav_path: Optional[str] = None, seconds: float = 1.0,
                      retries: int = 3) -> Optional[float]:
        """读录制中 wav 的尾部窗口，返回左声道线性 RMS（0~1），读不到返回 None。

        处理了三个现实问题：

        1. **data chunk 偏移不是 44**：scrcpy 会写 ``LIST/INFO`` 块，实际偏移 110，
           这里按 chunk 链解析（见 :func:`_parse_wav_layout`），解析失败才退回 44。
        2. **写入延迟/文件增长**：末尾可能是不完整的帧或正在追加，读前读后各取一次
           size 并对齐到 4 字节帧；窗口不足 100ms 视为"还没有有效数据"。
        3. **瞬时打不开**（文件被占用/刚重建）：最多重试 ``retries`` 次。

        :param wav_path: 目标 wav，默认本实例的 ``out_path``。
        :param seconds: 尾部窗口长度（秒），默认 1.0。
        :param retries: 失败重试次数（每次间隔 40ms）。
        :return: 线性 RMS（满量程 1.0）；无有效数据返回 None。
        """
        path = wav_path or self.out_path
        if not path:
            return None
        need_bytes = max(
            AUDIO_BLOCK_ALIGN,
            int(max(0.05, float(seconds)) * AUDIO_SAMPLE_RATE) * AUDIO_BLOCK_ALIGN,
        )
        min_bytes = AUDIO_SAMPLE_RATE // 10 * AUDIO_BLOCK_ALIGN      # 至少 100ms

        for attempt in range(max(1, int(retries))):
            try:
                if not os.path.isfile(path):
                    raise FileNotFoundError(path)
                size = os.path.getsize(path)
                if size <= AUDIO_BLOCK_ALIGN:
                    raise ValueError("文件还没有音频数据")
                head = _read_head(path, min(size, 4096))
                layout = _parse_wav_layout(head)
                data_off = layout[0] if layout else WAV_DEFAULT_DATA_OFFSET
                usable = size - data_off
                usable -= usable % AUDIO_BLOCK_ALIGN
                if usable < min_bytes:
                    raise ValueError(f"有效数据不足({usable}B)")
                take = min(usable, need_bytes)
                start = data_off + (usable - take)
                with open(path, "rb") as f:
                    f.seek(start)
                    raw = f.read(take)
                raw = raw[: len(raw) - (len(raw) % AUDIO_BLOCK_ALIGN)]
                if len(raw) < min_bytes:
                    raise ValueError("读到的数据不足")
                return _left_channel_rms(raw)
            except Exception:
                if attempt + 1 >= max(1, int(retries)):
                    return None
                time.sleep(0.04)
        return None

    def read_tail_rms_dbfs(self, wav_path: Optional[str] = None,
                           seconds: float = 1.0) -> Optional[float]:
        """:meth:`read_tail_rms` 的 dBFS 版本（-inf 截到 -120dB）。"""
        rms = self.read_tail_rms(wav_path=wav_path, seconds=seconds)
        if rms is None:
            return None
        return _to_dbfs(rms)

    def log_tail(self, lines: int = 20) -> str:
        """读 scrcpy 日志尾部若干行（排错时贴进驱动日志）。"""
        with self._lock:
            log_path = self._log_path
        if not log_path or not os.path.isfile(log_path):
            return ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return "\n".join(content.strip().splitlines()[-max(1, int(lines)):])
        except Exception:
            return ""

    # ---------------------------- 内部实现 ---------------------------- #
    def _build_cmd(self, source: str, out_path: str, time_limit: Optional[int],
                   extra_args: Optional[Sequence[str]]) -> List[str]:
        """拼 scrcpy 命令行（只抓音频、不开窗、不在 PC 回放）。"""
        cmd = [
            str(self._scrcpy_path),
            "-s", self.device_sn,
            "--no-window",
            "--no-video",
            "--no-playback",
            f"--audio-source={source}",
            "--audio-codec=raw",
            f"--record={out_path}",
            "--record-format=wav",
            "--no-cleanup",
        ]
        if time_limit:
            cmd.append(f"--time-limit={int(time_limit)}")
        if extra_args:
            cmd.extend(str(a) for a in extra_args)
        return cmd

    def _next_log_path(self, source: str) -> str:
        """日志文件名：scrcpy_<source>_<sn>_<时间戳>.log。"""
        safe_sn = re.sub(r"[^0-9A-Za-z_.-]", "_", self.device_sn) or "device"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(
            self._log_dir, f"scrcpy_{source}_{safe_sn}_{stamp}_{os.getpid()}.log"
        )

    def _wait_ready(self, timeout: float) -> bool:
        """等 scrcpy 真正开始写音频：日志出现 Recording started 或出现真实数据。"""
        deadline = time.time() + max(1.0, float(timeout))
        while time.time() < deadline:
            with self._lock:
                proc = self._proc
                out_path = self._out_path
            if proc is None:
                return False
            if proc.poll() is not None:
                return False
            tail = self.log_tail(40)
            if tail and _START_LOG_PATTERN.search(tail):
                return True
            try:
                if out_path and os.path.getsize(out_path) > AUDIO_BLOCK_ALIGN * 64:
                    return True
            except Exception:
                pass
            time.sleep(0.15)
        return False

    def _fail(self, reason: str) -> None:
        """记录失败原因（同时写日志文件，便于事后排错）。"""
        self._last_error = reason
        self._log_line(f"[{self._tag}] {reason}")

    def _log_line(self, msg: str) -> None:
        """把驱动侧消息追加到 scrcpy 日志里（不抛异常）。"""
        try:
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(f"\n[driver {time.strftime('%H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    def _close_log(self) -> None:
        """关闭日志句柄。"""
        handle = self._log_handle
        self._log_handle = None
        try:
            if handle is not None:
                handle.flush()
                handle.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 数学工具
# --------------------------------------------------------------------------- #
def _left_channel_rms(raw: bytes) -> float:
    """按 s16le 立体声取左声道算线性 RMS（0~1）。"""
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if sys.byteorder == "big":
        samples.byteswap()
    left = samples[0::AUDIO_CHANNELS]
    if not left:
        return 0.0
    total = 0
    for value in left:
        total += value * value
    return (total / len(left)) ** 0.5 / 32768.0


def _to_dbfs(rms: float) -> float:
    """线性 RMS → dBFS。"""
    import math

    if rms <= 1e-7:
        return -120.0
    return max(-120.0, 20.0 * math.log10(rms))
