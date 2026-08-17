import os
import time
import struct
import base64
import subprocess

from hypium import BY
from .harmony_xiaoyichat import Xiaoyilivechat
from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from config.config import Config
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT


class DoubaoChat(Xiaoyilivechat):
    """豆包(HarmonyOS)设备驱动 — 复用 Xiaoyilivechat 全部基础设施
    (_hdc_shell / _clear_pcm / PCM_APP_CONFIG / _mp4_to_wav / _pcm_to_wav /
    _start_recorder / _stop_recorder / _pull_record_file / get_results 等)，
    仅 initialize 用 hdc aa start 命令拉起豆包 app(替代小艺的 UI 点击)。

    录屏模式与 ChatGPT/小艺通话一致(record_mode 格式):
      - round=每轮一段(默认): 每轮独立启停录屏 + 挂断 + 提取本轮气泡
      - case=整用例一段: 一次连续通话 / 一个录屏 / 一个连续 PCM,中间轮不停录屏
        不挂断,末轮停录屏 + 挂断 + 提取气泡;teardown 兜底拉取完整录屏

    回复完成检测基于 cap_client 的 client_in.. PCM 尾部 RMS 能量(双阶段+历史兜底),
    不依赖控件文本(说话或点击打断/正在听…),后者在语音态透传性不稳定。
    """

    DOUBAO_BUNDLE = 'com.larus.nova.hm'
    DOUBAO_ABILITY = 'MainAbility'

    # 覆盖父类 PCM_APP_CONFIG['doubao'] 的后缀配置
    # 实测设备(nova.hm cache) AI 回复文件为 *_client_in..pcm(双点,无 cap_ 前缀),
    # 与 ChatGPT 一致;Fast_client_out.pcm 在现版本已不存在。
    PCM_APP_CONFIG = {
        **Xiaoyilivechat.PCM_APP_CONFIG,
        'doubao': {
            'cache_dirs': ['/data/app/el2/100/base/com.larus.nova.hm/cache'],
            'user_suffix': 'cap_client_out.pcm',      # 100154_48000_2_1_cap_client_out.pcm
            'ai_suffix': 'client_in..pcm',            # 100155_48000_2_1_client_in..pcm
        },
    }

    # RMS 检测参数
    PCM_CACHE_DIR = '/data/app/el2/100/base/com.larus.nova.hm/cache'
    AI_PCM_SUFFIX = 'client_in..pcm'   # 模型回复音频采集流(与用户输入 cap_client_out 对应)
    RMS_THRESHOLD = 300                       # RMS 阈值，低于此值视为静音
    RMS_SILENCE_SECONDS = 8                   # 连续静默秒数（实测回复中停顿≤6s，8s 不误触发）
    RMS_START_TIMEOUT = 60                    # 等 AI 开始说话的超时
    RMS_END_TIMEOUT = 120                     # 等 AI 说完的超时
    RMS_SCAN_SECONDS = 15                     # 阶段A超时后扫最后 N 秒历史
    RMS_SAMPLE_RATE = 48000
    RMS_CHANNELS = 2
    RMS_SAMPLE_WIDTH = 2                      # 16-bit
    # 1s PCM 字节数 = 48000 * 2ch * 2bytes
    RMS_TAIL_BYTES = RMS_SAMPLE_RATE * RMS_CHANNELS * RMS_SAMPLE_WIDTH

    def __init__(self):
        super().__init__()
        # 覆盖小艺的 app_name，指向豆包
        self.app_name = self.DOUBAO_BUNDLE
        # PCM 抓取目标固定为 doubao
        self._pcm_app = 'doubao'

    # ------------------------------------------------------------------
    # AI 回复完成检测（基于 client_in.. 尾部 RMS 能量，双阶段+历史兜底）
    # ------------------------------------------------------------------
    def _find_ai_pcm_remote(self, device_sn, task_id=None, test_case_id=None):
        """在 PCM_CACHE_DIR 找 AI 回复 PCM(client_in..pcm)。
        多个匹配取最后一个(最新流)。无匹配返回 None。"""
        r = self._hdc_shell(device_sn, 'find', self.PCM_CACHE_DIR,
                            '-name', f'*{self.AI_PCM_SUFFIX}', '-type', 'f')
        files = [line.strip() for line in (r.stdout or '').splitlines() if line.strip()]
        if not files:
            return None
        files.sort()
        return files[-1]

    def _read_tail_rms(self, device_sn, remote, tail_bytes=None,
                       task_id=None, test_case_id=None):
        """读 client_in..pcm 最后 tail_bytes 字节(经 base64 文本传输,二进制安全)算左声道 RMS。
        默认 1s = 48000*2ch*2bytes = 192000 字节。
        返回 (rms, size);文件不存在/不足尾部/读取失败返回 (None, size 或 None)。"""
        if tail_bytes is None:
            tail_bytes = self.RMS_TAIL_BYTES
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < tail_bytes:
            return None, (size if size >= 0 else None)
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=20,
            )
            raw = base64.b64decode(r.stdout)
            if len(raw) < 4:
                return None, size
            samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::2]  # 2ch 取左声道
            rms = (sum(s * s for s in mono) / len(mono)) ** 0.5 if mono else 0
            return rms, size
        except Exception as e:
            self._log(level='DEBUG', content=f"_read_tail_rms 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None, size

    def _scan_remote_for_speech(self, device_sn, remote, seconds=None,
                                energy_thr=None, task_id=None, test_case_id=None):
        """读最后 N 秒,按 0.5s 窗算 RMS,若任一窗>阈值视为近期有语音。
        用于"回复已结束但 post_process 起得晚"的兜底判定。返回 True/False。"""
        if seconds is None:
            seconds = self.RMS_SCAN_SECONDS
        if energy_thr is None:
            energy_thr = self.RMS_THRESHOLD
        tail_bytes = int(seconds * self.RMS_SAMPLE_RATE * self.RMS_CHANNELS * self.RMS_SAMPLE_WIDTH)
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < self.RMS_TAIL_BYTES:
            return False
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=40,
            )
            raw = base64.b64decode(r.stdout)
            samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::2]
            win = int(0.5 * self.RMS_SAMPLE_RATE)
            for i in range(0, len(mono), win):
                c = mono[i:i + win]
                if not c:
                    break
                rms = (sum(s * s for s in c) / len(c)) ** 0.5
                if rms > energy_thr:
                    return True
        except Exception as e:
            self._log(level='DEBUG', content=f"_scan_remote_for_speech 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
        return False

    def _wait_ai_reply_end_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                   interval=1.0):
        """等 AI 回复完成: 基于 client_in.. 尾部 RMS 能量判定(双阶段+历史兜底)。

        阶段A: 等尾部 1s RMS>阈值(AI 开始说话), start_timeout 内。
               ——必须先看到说话,避免在用户提问期(AI 通道静默)误判"说完"。
               超时则扫最后 15s 历史:曾有语音→回复已结束(起得晚)→True;否则未回复→False。
        阶段B: AI 开说过后,等连续 silence_seconds 秒 RMS<阈值(说完回静默)。
        实测: 回复中停顿≤6s, 回复后静默很长, silence_seconds=8 不误触发。

        返回: True=回复结束(或超时但已说过,视为已回复); False=未回复。
        """
        remote = None
        # 阶段A: 等 AI 开始说话
        deadline_start = time.time() + self.RMS_START_TIMEOUT
        saw_speech = False
        while time.time() < deadline_start:
            if self._check_stop("post_process_等AI回复开始"):
                return False
            remote = self._find_ai_pcm_remote(device_sn, task_id=task_id, test_case_id=test_case_id)
            if remote:
                rms, size = self._read_tail_rms(device_sn, remote,
                                                task_id=task_id, test_case_id=test_case_id)
                if rms is not None and rms > self.RMS_THRESHOLD:
                    saw_speech = True
                    self._log(level='INFO',
                              content=f"AI回复开始: {remote} size={size} tail_rms={rms:.0f}",
                              task_id=task_id, test_case_id=test_case_id)
                    break
            time.sleep(interval)
        if not saw_speech:
            # 兜底: post_process 起得晚、回复可能已结束——扫最后 15s 是否曾有语音
            if remote and self._scan_remote_for_speech(device_sn, remote,
                                                        task_id=task_id, test_case_id=test_case_id):
                self._log(level='INFO',
                          content="AI回复已结束(post_process起得晚,尾部虽静默但近15s曾有语音)",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            self._log(level='INFO',
                      content=f"豆包未回复({self.RMS_START_TIMEOUT}s 内 client_in.. 尾部无语音能量)",
                      task_id=task_id, test_case_id=test_case_id)
            return False

        # 阶段B: 等 AI 说完(连续 silence_seconds 秒 RMS<阈值)
        silence_since = None
        deadline_end = time.time() + self.RMS_END_TIMEOUT
        while time.time() < deadline_end:
            if self._check_stop("post_process_等AI回复结束"):
                return False
            rms, size = self._read_tail_rms(device_sn, remote,
                                            task_id=task_id, test_case_id=test_case_id)
            now = time.time()
            if rms is None:
                time.sleep(interval)
                continue
            if rms >= self.RMS_THRESHOLD:
                silence_since = None  # 还在说,重置
            else:
                if silence_since is None:
                    silence_since = now
                elif (now - silence_since) >= self.RMS_SILENCE_SECONDS:
                    self._log(level='INFO',
                              content=(f"AI回复结束(尾部静默 {self.RMS_SILENCE_SECONDS}s, "
                                       f"size={size} rms={rms:.0f})"),
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            time.sleep(interval)
        # 超时: 已开说过但未等到静默(回复过长被截断),视为已回复
        self._log(level='WARNING',
                  content=(f"等待AI回复结束超时 {self.RMS_END_TIMEOUT}s"
                           f"(已说过但未静默,视为已回复可能截断)"),
                  task_id=task_id, test_case_id=test_case_id)
        return True

    # ------------------------------------------------------------------
    # 录屏停止修补(豆包录屏时序 bug)
    # ------------------------------------------------------------------
    def _force_stop_recorder(self, device_sn, task_id=None, test_case_id=None):
        """aa force-stop 硬停 screenrecorder(幂等)。用于避免 toggle 状态错位 + teardown 兜底。"""
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'aa', 'force-stop', self.RECORDER_BUNDLE],
                check=False, capture_output=True, text=True, timeout=10,
            )
            self._log(level='DEBUG',
                      content=(f"[录屏] force-stop screenrecorder: rc={r.returncode} "
                               f"out={(r.stdout or '').strip()[:120]}"),
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"[录屏] force-stop 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)

    def _stop_recorder(self, device_sn, task_id=None, test_case_id=None):
        """覆盖父类:避免 toggle 状态错位导致"停变开"(豆包录屏 bug 根因,推断)。

        父类 _stop_recorder 是 blind toggle(再发一次 aa start)。豆包场景下 pre_process 的
        aa start 有时未真正开始捕获(first_frame_ms=None),blind toggle 因此不是停而是开,
        录屏在结束时才开始且不再停止。

        策略按 first_frame_ms 判断是否真正在录:
          - 有首帧(真正在录): 走父类 graceful toggle(能 finalizes mp4),留 2s 落盘后再硬停兜底;
          - 无首帧(从未真正捕获): 跳过 toggle(避免停变开),直接 force-stop 清残留态。
        两条路径末尾都 force-stop 一次(幂等),保证 screenrecorder 不残留。
        """
        first_frame = getattr(self, '_recorder_first_frame_ms', None)
        if first_frame is not None:
            self._log(level='INFO',
                      content=f"[录屏] _stop_recorder: 首帧已记录({first_frame}),graceful toggle + force-stop 兜底",
                      task_id=task_id, test_case_id=test_case_id)
            super()._stop_recorder(device_sn)
            time.sleep(2)  # 给 graceful toggle 落盘 finalizes mp4 的时间
        else:
            self._log(level='WARNING',
                      content="[录屏] _stop_recorder: 首帧为 None(录屏未真正启动),跳过 toggle 直接 force-stop(避免停变开)",
                      task_id=task_id, test_case_id=test_case_id)
        self._force_stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)
        return True

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """打开豆包 app(纯命令行拉起，不调用 HarmonyDriver.initialize，避免基类点小艺图标):
        解锁/关弹窗/回桌面 → 停豆包 → aa start 拉起豆包 → 清 pcm → 重置录屏状态 → 清聊天记录
        """
        self._log(level='INFO', content=f"Initializing Doubao on HarmonyOS device {device_sn}...",
                  task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}",
                      task_id=task_id, test_case_id=test_case_id)
            return False

        # 解锁设备
        self.unlock(device_sn)
        if self._check_stop("initialize"):
            return False
        # 关闭弹窗 + 回桌面
        self.close_popups(device_sn)
        if self._check_stop("initialize"):
            return False
        try:
            driver.swipe_to_home()
        except Exception:
            driver.press_home()
        time.sleep(2)

        # 停掉可能残留的豆包进程(不碰小艺)
        driver.stop_app(self.DOUBAO_BUNDLE)
        if self._check_stop("initialize"):
            return False

        # 命令行拉起豆包 app(小艺用 UI 点击 find_component(By.text("小艺"))，豆包用 aa start)
        r = self._hdc_shell(device_sn, 'aa', 'start',
                            '-b', self.DOUBAO_BUNDLE, '-a', self.DOUBAO_ABILITY)
        if r.returncode != 0:
            self._log(level='ERROR', content=f"启动豆包失败: {r.stderr or r.stdout}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        self._log(level='INFO', content="豆包 app 已启动",
                  task_id=task_id, test_case_id=test_case_id)
        time.sleep(3)
        # 启动后再次关闭弹窗
        self.close_popups(device_sn)

        # 重置跨用例残留的录屏状态（驱动单例复用）
        self._recording = False
        self._record_mode = kwargs.get('record_mode', 'round')
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_pulled = False
        self._pcm_app = kwargs.get('pcm_app', 'doubao')
        self.question_text = None
        self.answer_text = None

        # 用例开始前清理设备上豆包的 pcm 缓存，避免上个用例残留文件干扰本轮匹配
        self._clear_pcm(device_sn, app='doubao', task_id=task_id, test_case_id=test_case_id)

        # 清除聊天记录以及上下文(开启新话题)
        # 豆包聊天首页右上角菜单按钮: 先尝试语义查找(SymbolGlyph), 找不到则回退坐标
        driver.wait(3)
        try:
            # 第1步: 点击右上角菜单/设置按钮(打开侧边栏或菜单面板)
            menu_btn = None
            try:
                menu_btn = driver.find_component(BY.type('SymbolGlyph'))
            except Exception:
                pass
            if menu_btn:
                menu_btn.click()
            else:
                driver.touch((1161, 234))
                driver.wait(1)
                driver.touch((1175,234))
            driver.wait(1)

            # 第2步: 点击"删除聊天记录"(或"删除对话记录",豆包不同版本文案可能不同)
            delete_chat = None
            for label in ('删除聊天记录', '删除对话记录'):
                try:
                    delete_chat = driver.find_component(BY.text(label))
                    if delete_chat:
                        break
                except Exception:
                    continue
            if delete_chat:
                delete_chat.click()
                driver.wait(1)
                # 第3步: 确认删除
                confirm_btn = None
                try:
                    confirm_btn = driver.find_component(BY.text('删除'))
                except Exception:
                    pass
                if confirm_btn:
                    confirm_btn.click()
                    driver.wait(1)
                # 第4步: 开启新话题(按钮可能不存在,删除后已自动重置)
                try:
                    new_topic = driver.find_component(BY.text('开启新话题'))
                    if new_topic:
                        new_topic.click()
                        driver.wait(1)
                except Exception:
                    pass
                self._log(level='INFO', content="已清除上下文",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='WARNING', content="未找到'删除聊天记录'按钮(跳过)",
                          task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"清除聊天记录失败(跳过继续): {e}",
                      task_id=task_id, test_case_id=test_case_id)
        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """预处理：进入语音通话 + 开启录屏。

        录屏模式: round=每轮一段(默认); case=整用例一段。
        首轮：点击通话入口进入语音通话，再开启录屏。
        case 模式非首轮：通话与录屏进行中，跳过重复启动。
        """
        driver = self._get_driver(device_sn)
        record_mode = kwargs.get('record_mode', 'round')
        total_rounds = kwargs.get('total_rounds', 1)
        round_number = kwargs.get('round_number', 0)
        self._record_mode = record_mode
        self._total_rounds = total_rounds
        self._round_number = round_number
        is_first = not getattr(self, '_recording', False)

        # case 模式非首轮：通话与录屏已在进行，无需重复启动
        if record_mode == 'case' and not is_first:
            self._log(level='DEBUG',
                      content=f"case模式非首轮,跳过启动(语音/录屏进行中): r{round_number}/{total_rounds}",
                      task_id=task_id, test_case_id=test_case_id)
            return True

        # 开启通话聊天（首轮）
        try:
            driver.touch((853, 234))
            driver.wait(0.5)
            driver.wait(2)
        except Exception as e:
            self._log(level='WARNING', content=f"点击通话入口失败,尝试备用方式: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            try:
                alt = driver.find_component(By.text("对话"))
                if alt:
                    alt.click()
                    driver.wait(2)
            except Exception as e2:
                self._log(level='ERROR', content=f"通话入口未找到: {e2}",
                          task_id=task_id, test_case_id=test_case_id)
                return False

        try:
            if driver.find_component(By.text("选择情景")):
                self._log(level='DEBUG', content="成功进行通话", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='ERROR', content="通话失败", task_id=task_id, test_case_id=test_case_id)
                return False
        except Exception:
            self._log(level='ERROR', content="通话失败", task_id=task_id, test_case_id=test_case_id)
            return False

        # 开启录屏
        if record_mode == 'case':
            # 整用例一个文件，不带轮次后缀
            self._record_file_name = f"{test_case_id}.mp4"
        else:
            # 每轮一个文件，文件名含轮次号避免多轮冲突
            self._record_file_name = f"{test_case_id}_r{round_number}.mp4"
        if not self._start_recorder(device_sn, file_name=self._record_file_name):
            self._log(level='ERROR', content=f"启动录屏失败,服务未运行: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        self._recording = True
        self._log(level='INFO',
                  content=(f"启动录屏成功: {self._record_file_name} "
                           f"first_frame_ms={getattr(self, '_recorder_first_frame_ms', None)} "
                           f"(None=未真正捕获首帧,_stop_recorder 将走 force-stop 避免停变开)"),
                  task_id=task_id, test_case_id=test_case_id)
        time.sleep(2)
        return True

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理：等 AI 回复结束 → 按模式收尾 → (round 模式) 提取问答文本。

        回复完成检测基于 client_in.. PCM 尾部 RMS 能量(双阶段+历史兜底),
        不依赖控件文本(说话或点击打断/正在听…),后者在语音态透传性不稳定。

        核心是【不挂断逻辑】——case 模式全程不挂断,保持一次连续通话:
        - case 模式(多轮连续通话): 中间轮仅等回复完成即返回(不停录屏/不挂断/不提取)；
          末轮停录屏供 get_results 拉取,但仍【不挂断】——通话挂断交给 teardown.stop_app,
          以保证多轮间 AI 上下文连续(挂断会重置对话上下文)。case 模式不做气泡文本提取
          (全程在通话页无聊天列表),本轮文本以 ai_wav/user_wav 的 ASR 为准。
        - round 模式(每轮独立): 停录屏 + 挂断 + 提取本轮气泡(每轮独立,可挂断)。
        """
        driver = self._get_driver(device_sn)
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']} "
                          f"detail_count={len(ts['detail']) if ts['detail'] else 0})",
                  task_id=task_id, test_case_id=test_case_id)

        # 等 AI 回复完成：client_in.. 尾部 RMS 双阶段判定
        # 打断轮(is_interruption=True):不等 AI 回复完成,直接收尾进入下一轮 pre_process
        if kwargs.get('is_interruption') in (True, 'true', '1', 1):
            self._log(level='INFO',
                      content=f"[post_process] is_interruption=True,跳过等待 AI 回复完成,直接收尾",
                      task_id=task_id, test_case_id=test_case_id)
            replied = True
        else:
            replied = self._wait_ai_reply_end_via_pcm(device_sn, task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = '豆包识别为空'
                self.answer_text = '豆包回复为空'

        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        if record_mode == 'case':
            # case 模式：一次连续语音通话 / 一个录屏 / 一个连续 PCM,【全程不挂断】。
            # 中间轮：不停录屏、不挂断、不提取,直接返回(通话与录屏继续进行)。
            if not is_last:
                self._log(level='DEBUG',
                          content=f"case模式中间轮,不挂断保持语音/录屏进行中: r{round_number}/{total_rounds}",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            # 末轮：停录屏供 get_results 拉取,但仍【不挂断】——通话交给 teardown.stop_app 兜底结束,
            # 避免挂断重置 AI 上下文。case 模式全程在通话页,无聊天列表,不做气泡文本提取。
            if not self._stop_recorder(device_sn):
                self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(5)
            self._log(level='INFO',
                      content="case模式末轮不挂断,通话交给 teardown 结束(保持上下文连续)",
                      task_id=task_id, test_case_id=test_case_id)
            return True

        # round 模式：每轮独立——停录屏 + 挂断 + 提取气泡。
        if not self._stop_recorder(device_sn):
            self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
        self._recording = False
        time.sleep(5)
        try:
            driver.touch((1084, 2440))
            self._log(level='DEBUG', content="已挂断通话", task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"挂断通话失败: {e}", task_id=task_id, test_case_id=test_case_id)
        driver.wait(5)

        if not replied:
            return True

        # round 模式挂断后落回聊天列表,提取本轮问答文本(取最后一条,未识别到返回 None)
        question_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Row/Text'))
        self._log(level='DEBUG',
                  content=f"question_components count={len(question_components) if question_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if question_components:
            for i, comp in enumerate(question_components):
                self._log(level='DEBUG', content=f"question_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.question_text = question_components[-1].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Column//Stack/Text'))
        self._log(level='DEBUG',
                  content=f"answer_components count={len(answer_components) if answer_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if answer_components:
            for i, comp in enumerate(answer_components):
                self._log(level='DEBUG', content=f"answer_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.answer_text = answer_components[-1].getText() if answer_components else None

        return True

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束清理（与 initialize 对称）

        做以下清理：
        1. 确保录屏已停止（兜底，防止 post_process 异常残留）
        2. case 模式兜底：末轮未拉取时补拉一次完整录屏
        3. 确保通话已挂断（兜底）
        4. 退出豆包聊天界面，回桌面
        5. 停止豆包 APP（彻底释放）
        """
        # 1. 兜底停止录屏（仅在仍在录屏时执行，避免 toggle 把已停止的录屏又打开）
        if getattr(self, '_recording', False):
            try:
                if not self._stop_recorder(device_sn):
                    self._log(level='WARNING', content="teardown: 兜底停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='DEBUG', content="teardown: 兜底停止录屏成功",
                              task_id=task_id, test_case_id=test_case_id)
                self._recording = False
            except Exception as e:
                self._log(level='WARNING', content=f"teardown: 停止录屏失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)

        # 2. case 模式兜底：末轮 post_process 异常未拉取时，补拉一次完整录屏，避免整段录屏丢失
        if getattr(self, '_record_mode', 'round') == 'case' and not getattr(self, '_record_pulled', False):
            pulled = self._pull_record_file(device_sn, task_id=task_id, test_case_id=test_case_id)
            if pulled:
                self._log(level='INFO', content=f"teardown: 兜底拉取录屏成功: {pulled}",
                          task_id=task_id, test_case_id=test_case_id)
                self._record_pulled = True

        driver = self._get_driver(device_sn)
        if not driver:
            return True

        # 3. 兜底挂断通话
        try:
            driver.touch((1084, 2440))
            self._log(level='DEBUG', content="teardown: 兜底挂断通话",
                      task_id=task_id, test_case_id=test_case_id)
            time.sleep(2)
        except Exception as e:
            self._log(level='DEBUG', content=f"teardown: 无残留通话或挂断失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 4. 回桌面（退出豆包聊天界面）
        try:
            driver.press_home()
            time.sleep(1)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 回桌面失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 5. 停止豆包 APP（彻底释放）
        try:
            driver.stop_app(self.DOUBAO_BUNDLE)
            self._log(level='DEBUG', content="teardown: 已停止豆包 APP",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止豆包 APP 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 6. 无条件硬停 screenrecorder 兜底(幂等):无论前面 _recording 标志真假,
        #    保证"录屏不停止"残留不可能跨用例存活(豆包录屏 bug 的核心修复兜底)。
        self._force_stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)

        return True
