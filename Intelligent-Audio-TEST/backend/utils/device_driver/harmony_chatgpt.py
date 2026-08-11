import time
import subprocess

from .harmony_xiaoyichat import Xiaoyilivechat
from .harmony_driver import HarmonyDriver
from .utils import By, log_and_emit
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT


class ChatGptVoiceChat(Xiaoyilivechat):
    """ChatGPT 语音通话专用驱动。

    仿照 harmony_xiaoyichat.Xiaoyilivechat 实现，功能要求与小艺通话一致：
      - 录屏(screenrecorder) + 抓取 cap_client PCM(用户输入/AI回复) + 转 wav
      - initialize/pre_process/post_process/get_results/teardown 生命周期
      - 多轮 round/case 录屏模式、首帧时延、问答文本提取、结果格式

    继承 Xiaoyilivechat 可直接复用：mp4→wav / pcm→wav / hdc 封装 / 录屏启停 /
    PCM 清理与拉取 / PCM_APP_CONFIG['chatgpt'] / get_results 结果拼装。

    差异点（本类覆盖）：
      1. 目标 App 为 com.openai.chatgpt（鸿蒙 Android 兼容层运行，Compose UI）
      2. 语音通话入口为聊天首页输入栏右侧的蓝色按钮（无稳定 text/key，用坐标点击）
      3. 回复检测与问答文本提取基于语音界面实时转写文本（左侧=AI / 右侧=用户）
      4. cap_client 音频采集已在设备后台运行，驱动无需启停，仅按需清理/拉取 PCM

    TODO（需真实播放音频流程联调确认）：
      - hypium 能否透传 Compose 的 android.widget.TextView（回复检测/文本提取依赖此）
      - 回复结束判定阈值（转写文本稳定秒数）
      - 退出语音模式的方式（当前用 press_home 兜底，可改回退键/关闭按钮）
    """

    # ChatGPT 包名（鸿蒙 Android 兼容层）
    APP_PACKAGE = 'com.openai.chatgpt'

    # 聊天首页底部输入栏按钮坐标（屏幕 1280x2832）
    #   [+]     : (126, 2650)
    #   输入框   : EditText, 中部
    #   麦克风   : (979, 2650)
    #   蓝色语音 : (1147, 2650)  <- 语音通话入口
    HOME_BTN_VOICE = (1147, 2650)      # 蓝色语音按钮（语音通话入口）
    HOME_BTN_TOPRIGHT = (1154, 261)    # 右上角（临时聊天/新对话面板）
    HOME_BTN_MIC = (979, 2650)         # 麦克风（语音输入，非通话）

    # 语音界面：中央 orb（点击可显现/隐藏实时转写气泡,不挂断通话,实测 PCM 持续增长）
    VOICE_ORB_REGION = (203, 1015, 1078, 1890)  # 中央 orb 大致区域
    VOICE_ORB_TAP = (640, 1452)                 # orb 中心(=区域中心),点此显现转写气泡

    def __init__(self):
        super().__init__()
        # 覆盖小艺的 app_name，指向 ChatGPT
        self.app_name = self.APP_PACKAGE
        # PCM 抓取目标固定为 chatgpt（cap_client 写 /data/local/tmp）
        self._pcm_app = 'chatgpt'

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _tap_xy(self, driver, x, y):
        """坐标点击（ChatGPT 的 Compose 按钮多无 text/key，只能按坐标点击）。"""
        try:
            driver.click(x, y)
            return True
        except Exception as e:
            self._log(level='DEBUG', content=f"坐标点击失败 ({x},{y}): {e}")
            return False

    def _back(self, device_sn):
        """发送返回键（退出语音模式兜底）。"""
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', 'keyevent', '4'],
                            check=False, capture_output=True, text=True, timeout=10)
        except Exception:
            pass

    def _get_transcript(self, driver):
        """提取语音界面实时转写文本组件列表，返回 [(text, x0), ...]。

        ChatGPT 语音模式会把对话以转写气泡形式叠加：用户在右(x0 偏大)、AI 在左(x0≈56)。
        Compose 的 TextView 选择器透传性未确认，故采用多策略兜底。
        """
        comps = []
        # 策略1: xpath 匹配 android.widget.TextView
        try:
            found = driver.find_all_components(By.xpath('//android.widget.TextView'))
            if found:
                comps = found
        except Exception:
            pass
        # 策略2: type 匹配
        if not comps:
            try:
                found = driver.find_all_components(By.type('android.widget.TextView'))
                if found:
                    comps = found
            except Exception:
                pass
        result = []
        for c in comps:
            try:
                txt = (c.getText() or '').strip()
                if not txt:
                    continue
                # 过滤状态栏时钟/电量等噪声文本
                if txt in ('07', '08', '09', ':', '100') or len(txt) <= 1:
                    continue
                bounds = c.getBounds()
                x0 = bounds[0] if bounds else 0
                result.append((txt, x0))
            except Exception:
                continue
        return result

    def _extract_qa(self, driver, task_id=None, test_case_id=None):
        """从转写文本中提取本轮用户输入与 AI 回复。

        依据气泡 x 起点区分：x0 偏大(右)→用户；x0 偏小(左)→AI。取各自最后一条作本轮问答。

        关键：语音全屏态下气泡默认不可见,点中央 orb(VOICE_ORB_TAP)可显现实时转写气泡
        (实测不挂断通话,client_in PCM 持续增长)。聊天首页气泡本就可见,无需点 orb。
        为避免 orb 是 toggle 反复点隐,仅当【语音全屏 且 当前无气泡】时才点 orb。
        """
        items = self._get_transcript(driver)
        if not items:
            # 无气泡：若在语音全屏(无 EditText),点 orb 显现转写;聊天首页本应有气泡,空则放弃
            try:
                edit = driver.find_component(By.type('android.widget.EditText'))
            except Exception:
                edit = None
            if edit is None:
                self._log(level='DEBUG', content="语音态无气泡,点 orb 显现转写",
                          task_id=task_id, test_case_id=test_case_id)
                self._tap_xy(driver, *self.VOICE_ORB_TAP)
                driver.wait(2)
                items = self._get_transcript(driver)
        if not items:
            self.question_text = None
            self.answer_text = None
            return
        user_items = [t for (t, x0) in items if x0 >= 300]
        ai_items = [t for (t, x0) in items if x0 < 300]
        self.question_text = user_items[-1] if user_items else None
        self.answer_text = ai_items[-1] if ai_items else None
        self._log(level='DEBUG',
                  content=f"转写提取 user={self.question_text!r} ai={self.answer_text!r} (共{len(items)}条)",
                  task_id=task_id, test_case_id=test_case_id)

    def _wait_reply_end(self, driver, task_id=None, test_case_id=None,
                        timeout=90, stable_seconds=3, interval=1.0):
        """等待 AI 回复结束：转写文本总长度连续 stable_seconds 秒不变视为结束。"""
        last_len = -1
        stable_since = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._check_stop("post_process_等待回复结束"):
                return False
            items = self._get_transcript(driver)
            cur_len = sum(len(t) for (t, _) in items)
            now = time.time()
            if cur_len != last_len:
                last_len = cur_len
                stable_since = now
            elif stable_since and (now - stable_since) >= stable_seconds and cur_len > 0:
                self._log(level='INFO', content=f"回复结束(转写稳定 {stable_seconds}s, len={cur_len})",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            time.sleep(interval)
        self._log(level='WARNING', content=f"等待回复结束超时 {timeout}s", task_id=task_id, test_case_id=test_case_id)
        return False

    # ------------------------------------------------------------------
    # AI 回复完成检测（基于 cap_client client_in 尾部 RMS 能量,不依赖 Compose 转写文本）
    # ------------------------------------------------------------------
    def _find_ai_pcm_remote(self, device_sn, task_id=None, test_case_id=None):
        """在 /data/local/tmp 找 AI 回复 PCM(client_in),排除 dump_process 文件。
        多个匹配取最后一个(最新流)。无匹配返回 None。"""
        r = self._hdc_shell(device_sn, 'find', '/data/local/tmp',
                            '-name', '*.pcm', '-type', 'f')
        files = [line.strip() for line in (r.stdout or '').splitlines() if line.strip()]

        # AI 回复文件名含 client_in,排除 dump_process_client_play_audio
        ai_files = [f for f in files if 'client_in' in f and 'dump_process' not in f]
        if not ai_files:
            return None
        ai_files.sort()
        return ai_files[-1]

    def _read_tail_rms(self, device_sn, remote, tail_bytes=192000,
                       task_id=None, test_case_id=None):
        """读 client_in 最后 tail_bytes 字节(经 base64 文本传输,二进制安全)算左声道 RMS。
        默认 192000 字节 = 1s @ 48000*2ch*2bytes。
        返回 (rms, size);文件不存在/不足尾部/读取失败返回 (None, size 或 None)。"""
        import base64 as _b64, struct as _struct
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < tail_bytes:
            return None, (size if size >= 0 else None)
        # hdc shell stdout 非二进制安全(可能 CRLF 篡改),用 base64 走文本通道
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=20,
            )
            raw = _b64.b64decode(r.stdout)
            if len(raw) < 4:
                return None, size
            samples = _struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::2]  # 2ch 取左声道
            rms = (sum(s * s for s in mono) / len(mono)) ** 0.5 if mono else 0
            return rms, size
        except Exception as e:
            self._log(level='DEBUG', content=f"_read_tail_rms 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None, size

    def _scan_remote_for_speech(self, device_sn, remote, seconds=15,
                                energy_thr=300, task_id=None, test_case_id=None):
        """读 client_in 最后 N 秒,按 0.5s 窗算 RMS,若任一窗>阈值视为近期有语音。
        用于"回复已结束但 post_process 起得晚"的兜底判定。返回 True/False。"""
        import base64 as _b64, struct as _struct
        tail_bytes = int(seconds * 48000 * 2 * 2)  # 48000*2ch*2bytes/s
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < 192000:
            return False
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=40,
            )
            raw = _b64.b64decode(r.stdout)
            samples = _struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::2]
            win = int(0.5 * 48000)
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
                                   start_timeout=60, end_timeout=120,
                                   energy_thr=300, silence_seconds=8, interval=1.0):
        """等 AI 回复完成: 基于 client_in 尾部 RMS 能量判定(不依赖 Compose 转写文本)。

        cap_client 在语音会话期间持续写 *_client_in..pcm: AI 说话=高能量, AI 静默=纯零 rms≈0。
        故 "size 稳定" 不可用(静默也写零帧→size 线性增长);改用尾部能量:
          阶段A: 等尾部 1s RMS>energy_thr(AI 开始说话),start_timeout 内。
                 ——必须先看到说话,避免在用户提问期(AI 通道静默)误判"说完"。
                 超时则扫最后 15s 历史:曾有语音→回复已结束(起得晚)→True;否则未回复→False。
          阶段B: AI 开说过后,等连续 silence_seconds 秒 RMS<energy_thr(说完回静默)。
        实测: 回复中停顿≤6s, 回复后静默很长, silence_seconds=8 不误触发。

        返回: True=回复结束(或超时但已说过,视为已回复); False=未回复。
        """
        tail_bytes = 192000  # 1s @ 48000*2ch*2bytes
        remote = None
        # 阶段A: 等 AI 开始说话
        deadline_start = time.time() + start_timeout
        saw_speech = False
        while time.time() < deadline_start:
            if self._check_stop("post_process_等AI回复开始"):
                return False
            remote = self._find_ai_pcm_remote(device_sn, task_id=task_id, test_case_id=test_case_id)
            if remote:
                rms, size = self._read_tail_rms(device_sn, remote, tail_bytes=tail_bytes,
                                                task_id=task_id, test_case_id=test_case_id)
                if rms is not None and rms > energy_thr:
                    saw_speech = True
                    self._log(level='INFO',
                              content=f"AI回复开始: {remote} size={size} tail_rms={rms:.0f}",
                              task_id=task_id, test_case_id=test_case_id)
                    break
            time.sleep(interval)
        if not saw_speech:
            # 兜底: post_process 起得晚、回复可能已结束——扫最后 15s 是否曾有语音
            if remote and self._scan_remote_for_speech(device_sn, remote, seconds=15,
                                                       energy_thr=energy_thr,
                                                       task_id=task_id, test_case_id=test_case_id):
                self._log(level='INFO',
                          content="AI回复已结束(post_process起得晚,尾部虽静默但近15s曾有语音)",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            self._log(level='INFO',
                      content=f"ChatGPT未回复({start_timeout}s 内 client_in 尾部无语音能量)",
                      task_id=task_id, test_case_id=test_case_id)
            return False

        # 阶段B: 等 AI 说完(连续 silence_seconds 秒 RMS<阈值)
        silence_since = None
        deadline_end = time.time() + end_timeout
        while time.time() < deadline_end:
            if self._check_stop("post_process_等AI回复结束"):
                return False
            rms, size = self._read_tail_rms(device_sn, remote, tail_bytes=tail_bytes,
                                           task_id=task_id, test_case_id=test_case_id)
            now = time.time()
            if rms is None:
                time.sleep(interval)
                continue
            if rms >= energy_thr:
                silence_since = None  # 还在说,重置
            else:
                if silence_since is None:
                    silence_since = now
                elif (now - silence_since) >= silence_seconds:
                    self._log(level='INFO',
                              content=f"AI回复结束(尾部静默 {silence_seconds}s, size={size} rms={rms:.0f})",
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            time.sleep(interval)
        # 超时: 已开说过但未等到静默(回复过长被截断),视为已回复
        self._log(level='WARNING',
                  content=f"等待AI回复结束超时 {end_timeout}s(已说过但未静默,视为已回复可能截断)",
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def _exit_voice(self, device_sn, driver, task_id=None, test_case_id=None):
        """退出语音全屏，落回 ChatGPT 聊天首页。

        必须用【返回键】(keyevent 4)退出语音全屏——落点是 ChatGPT 聊天首页,转写气泡在此页
        才可见,_extract_qa 才能读到。press_home 会回桌面丢气泡页。
        实测 Compose 聊天首页渲染需时间,单次返回键+短等待常误判"未回首页"→改重试(最多3次,
        每次3s),任一次见到 EditText 即成功。全部失败才 press_home 兜底(回桌面,此路气泡不可读)。
        """
        for attempt in (1, 2, 3):
            self._back(device_sn)
            time.sleep(3)
            try:
                edit = driver.find_component(By.type('android.widget.EditText'))
                if edit:
                    self._log(level='DEBUG',
                              content=f"返回键已退出语音,落回聊天首页(EditText 存在,第{attempt}次)",
                              task_id=task_id, test_case_id=test_case_id)
                    return
            except Exception as e:
                self._log(level='DEBUG', content=f"退出语音校验异常(第{attempt}次): {e}",
                          task_id=task_id, test_case_id=test_case_id)
        self._log(level='WARNING', content="返回键3次未回聊天首页,press_home 兜底退出(气泡不可读)",
                  task_id=task_id, test_case_id=test_case_id)
        try:
            driver.press_home()
            time.sleep(1)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化：解锁→清弹窗→回桌面→停 ChatGPT→aa start 启动 ChatGPT→清残留 PCM。

        注意1：不调用 Xiaoyilivechat.initialize（其内部含小艺专属的清上下文/删对话记录 UI，
        在 ChatGPT 上会因找不到 SymbolGlyph 而抛异常）。
        注意2：也不复用 HarmonyDriver.initialize 的图标点击路径——其 app_icon_key 默认是小艺
        图标 key(AppIconCommonView_com.huawei.hmos.vassistant.launcher.VoiceAbility)，会在桌面
        误点小艺图标启动小艺而非 ChatGPT（且行为不稳定：仅当桌面找不到小艺图标时才走 aa start
        兜底）。这里直接 aa start 启动 ChatGPT，不依赖图标 key。
        """
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"无法获取设备驱动: {device_sn}",
                      task_id=task_id, test_case_id=test_case_id)
            return False

        if self._check_stop("initialize"):
            return False
        self.unlock(device_sn)
        if self._check_stop("initialize"):
            return False
        self.close_popups(device_sn)
        if self._check_stop("initialize"):
            return False
        try:
            driver.swipe_to_home()
        except Exception:
            driver.press_home()
        time.sleep(2)

        # 停掉残留 ChatGPT（避免上次实例残留）
        try:
            driver.stop_app(self.app_name)
        except Exception as e:
            self._log(level='DEBUG', content=f"stop_app ChatGPT 失败(忽略): {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 直接 aa start 启动 ChatGPT（不依赖图标 key，避免误点小艺）
        # 指定 MainActivity：仅 -b 不带 -a 时 Android 兼容层应用会 "failed to start ability"
        main_activity = f"{self.app_name}.MainActivity"
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'aa', 'start',
                 '-b', self.app_name, '-a', main_activity],
                check=False, capture_output=True, text=True, timeout=15,
            )
            self._log(level='DEBUG',
                      content=f"aa start {self.app_name}/{main_activity}: rc={r.returncode} out={r.stdout.strip()[:200]}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='ERROR', content=f"aa start ChatGPT 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        time.sleep(5)
        self.close_popups(device_sn)

        # 重置跨用例残留状态（驱动单例复用）
        self._recording = False
        self._record_mode = 'round'
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_pulled = False
        self._pcm_app = kwargs.get('pcm_app', 'chatgpt')
        self.question_text = None
        self.answer_text = None

        # 用例开始前清理设备上 cap_client 残留 PCM，避免上个用例文件干扰本轮匹配
        self._clear_pcm(device_sn, app=self._pcm_app, task_id=task_id, test_case_id=test_case_id)
        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """预处理：进入语音通话 + 开启录屏。

        录屏模式: round=每轮一段(默认); case=整用例一段。
        首轮：点击聊天首页蓝色语音按钮进入语音通话，再开启录屏。
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

        # 首轮：点击蓝色语音按钮进入语音通话
        # 蓝色按钮位于输入栏最右侧、EditText 同高；输入栏 y 随布局变化，故由 EditText
        # bounds 动态取中心 y，x 取屏幕最右侧(该设备 1280 宽 → 1147)以稳定命中蓝按钮
        tap_x, tap_y = self.HOME_BTN_VOICE
        try:
            edit = driver.find_component(By.type('android.widget.EditText'))
            if edit:
                b = edit.getBounds()  # (left, right, top, bottom)
                tap_y = (b[2] + b[3]) // 2
        except Exception as e:
            self._log(level='DEBUG', content=f"定位 EditText 失败,用默认坐标: {e}")
        self._tap_xy(driver, tap_x, tap_y)
        driver.wait(4)
        # 校验是否进入语音界面：聊天首页的输入框 EditText 应消失
        # （语音全屏界面无 EditText；Compose 元素透传性已验证可用）
        try:
            edit = driver.find_component(By.type('android.widget.EditText'))
            entered = edit is None
        except Exception:
            entered = True
        self._log(level='INFO',
                  content="已点击蓝色语音按钮,进入语音通话" if entered else "进入语音通话校验未通过(继续)",
                  task_id=task_id, test_case_id=test_case_id)

        # 开启录屏
        if record_mode == 'case':
            self._record_file_name = f"{test_case_id}.mp4"
        else:
            self._record_file_name = f"{test_case_id}_r{round_number}.mp4"
        if not self._start_recorder(device_sn, file_name=self._record_file_name):
            self._log(level='ERROR', content=f"启动录屏失败,服务未运行: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        self._recording = True
        self._log(level='INFO', content=f"启动录屏成功: {self._record_file_name}",
                  task_id=task_id, test_case_id=test_case_id)
        time.sleep(2)
        return True

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理：等 AI 回复结束 → 按模式收尾 → 提取气泡文本(best-effort)。

        回复完成判定基于 cap_client 的 client_in 尾部 RMS 能量(AI 说话=高能量/静默≈0),
        不依赖 Compose 转写文本(语音态透传性不稳定,实测漏判)。

        - case 模式(多轮连续通话)：中间轮仅等回复完成即返回(不停录屏/不退语音/不提取,
          保持一次连续通话/一个录屏/一个连续 PCM)；末轮停录屏+退语音回聊天首页+提取气泡。
        - round 模式(每轮独立)：停录屏+退语音回聊天首页+提取本轮气泡。
        """
        driver = self._get_driver(device_sn)
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']})",
                  task_id=task_id, test_case_id=test_case_id)

        # 等 AI 回复完成：client_in PCM 尾部 RMS(平台流:音频紧接 pre_process 后播,start_timeout=60 够;
        # 手动测试:用户随时播,可经 kwargs 传更大 ai_start_timeout 防提前超时)
        replied = self._wait_ai_reply_end_via_pcm(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            start_timeout=kwargs.get('ai_start_timeout', 60),
            end_timeout=kwargs.get('ai_end_timeout', 120))
        if not replied:
            self.question_text = 'ChatGPT识别为空'
            self.answer_text = 'ChatGPT回复为空'

        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        if record_mode == 'case':
            # case 模式：一次连续语音通话 / 一个录屏 / 一个连续 PCM,对话间不退出语音。
            # 中间轮：不停录屏、不退出语音；点 orb 显现转写即可提取本轮气泡(不挂断通话)。
            # 末轮：停录屏 + 提取气泡；不主动退语音——teardown 的 aa force-stop 即退出,
            #       满足"整体测完才退出语音"。返回键对 ChatGPT 语音态不生效,故不依赖。
            if not is_last:
                self._log(level='DEBUG',
                          content=f"case模式中间轮,保持语音/录屏进行中: r{round_number}/{total_rounds}",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                if not self._stop_recorder(device_sn):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(5)
        else:
            # round 模式：每轮独立——停录屏 + 退出语音回聊天首页(返回键 best-effort) + 提取气泡。
            # 注:返回键对 ChatGPT 语音态常不生效(press_home 兜底回桌面),round 模式多轮重入语音
            #    依赖成功退回聊天首页;失败则下轮 pre_process 难以点中蓝按钮。case 模式无此问题。
            if not self._stop_recorder(device_sn):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(2)
            self._exit_voice(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
            driver.wait(3)

        if not replied:
            return True

        # 提取问答文本：_extract_qa 在语音态会点 orb 显现转写再读(case 中间/末轮均适用),
        # 在聊天首页(round 模式退语音成功后)气泡已可见直接读。取最后一条 Q/A(best-effort)。
        # case 多轮完整/分轮文本以 ai_wav 的 ASR(按 playback 时间戳切段)为准。
        self._extract_qa(driver, task_id=task_id, test_case_id=test_case_id)
        return True

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束清理：兜底停录屏→退出语音→回桌面→停止 ChatGPT。"""
        # 1. 兜底停止录屏
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

        # case 模式兜底：末轮 post_process 异常未拉取时，补拉一次完整录屏
        if getattr(self, '_record_mode', 'round') == 'case' and not getattr(self, '_record_pulled', False):
            pulled = self._pull_record_file(device_sn, task_id=task_id, test_case_id=test_case_id)
            if pulled:
                self._log(level='INFO', content=f"teardown: 兜底拉取录屏成功: {pulled}",
                          task_id=task_id, test_case_id=test_case_id)
                self._record_pulled = True

        driver = self._get_driver(device_sn)
        if driver:
            # 2. 兜底退出语音模式
            try:
                driver.press_home()
                time.sleep(1)
                self._log(level='DEBUG', content="teardown: 兜底退出语音/回桌面",
                          task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level='DEBUG', content=f"teardown: 退出语音失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)

        # 3. 停止 ChatGPT APP（彻底释放）
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'aa', 'force-stop', self.app_name],
                           check=False, capture_output=True, text=True, timeout=10)
            self._log(level='DEBUG', content="teardown: 已停止 ChatGPT APP",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止 ChatGPT APP 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        return True
