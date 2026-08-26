import time
import subprocess

from .harmony_xiaoyichat import Xiaoyilivechat
from .harmony_driver import HarmonyDriver
from .utils import By, log_and_emit, with_rpc_retry
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
      3. 回复完成检测基于 cap_client 的 client_in 尾部 RMS 能量（AI 说话=高能量/静默≈0），
         不依赖 Compose 转写文本（语音态透传性不稳定且无气泡）；问答文本走 user_wav/ai_wav 的 ASR
      4. cap_client 音频采集已在设备后台运行，驱动无需启停，仅按需清理/拉取 PCM

    TODO（需真实播放音频流程联调确认）：
      - hypium 能否透传 Compose 的 android.widget.TextView（回复检测/文本提取依赖此）
      - 回复结束判定（当前用 client_in 尾部 RMS 能量，已实现；转写文本稳定秒数方案已弃用）
      - 退出语音：返回键被 App 吞掉、idle 态无结束按钮，case 模式不依赖退出；round 模式
        退语音需在“通话进行中”探到结束按钮坐标（需真实通话联调）
    """

    # ChatGPT 包名（鸿蒙 Android 兼容层）
    APP_PACKAGE = 'com.openai.chatgpt'

    # 聊天首页底部输入栏按钮坐标（屏幕 1280x2832；实测 2026-08-13 ChatGPT 改版后输入栏上移至 y≈1607，
    # 旧版 y=2650 已失效）。四件套结构不变：[+] / EditText / 麦克风 / 蓝色语音(最右)。
    #   [+]     : (126, 1607)
    #   输入框   : EditText, bounds≈(210,1523,916,1691), center (563,1607)
    #   麦克风   : (1000, 1607)
    #   蓝色语音 : (1154, 1607)  <- 语音通话入口（最右侧按钮）
    # pre_process 用 EditText.getBounds() 动态取中心 y、x 固定 1147；1147∈右侧按钮 x[1098,1210]，故
    # (1147, edit_center_y) 仍命中蓝色语音按钮（实测 (1154,1607) 可进入语音全屏）。
    HOME_BTN_VOICE = (1147, 1607)      # 蓝色语音按钮（语音通话入口，fallback；实际靠 EditText 取 y）
    HOME_BTN_TOPRIGHT = (1154, 261)    # 右上角（临时聊天/新对话面板）
    HOME_BTN_MIC = (1000, 1607)        # 麦克风（语音输入，非通话）

    # 语音全屏 orb：实测改版后 orb 移至屏幕下方，385×385，center≈(640,2247)，clickable。
    # ⚠️ 驱动不再点击 orb：通话进行中点 orb 会触发相机/视频界面（运行期“每轮结束开相机”bug 的来源），
    # 且语音态本无转写气泡（hierarchy 只有时钟/电量/通话计时），该路径本就不可靠，故移除点击。
    VOICE_ORB_CENTER = (640, 2247)

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
        """发送返回键（keyevent 4）。

        正确语法为 `hdc shell uinput -K -d 4 -u 4`（键盘按下即抬起）；
        旧实现 `uinput keyevent 4` 是错误语法，会报 "too few arguments" 实际不执行，
        导致 _exit_voice 的返回键从未真正发送过。
        （注：即便语法修正，ChatGPT 语音全屏仍会吞掉返回键不退语音，见 _exit_voice。）
        """
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-K', '-d', '4', '-u', '4'],
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
        """从转写气泡中提取本轮用户输入与 AI 回复。

        气泡只在【聊天首页】可见；语音全屏态无气泡（实测 hierarchy 只有时钟/电量/通话计时）。
        故本方法仅在已退回聊天首页（round 模式 _exit_voice 成功后）能读到文本；case 模式
        全程在语音态、或 _exit_voice 未退回首页时返回 None/None，问答文本交由 user_wav/ai_wav 的 ASR。

        ⚠️ 不再点击中央 orb 显现气泡：旧 orb 坐标已随 ChatGPT 改版失效（orb 实际移至屏幕下方
        且 clickable），且通话进行中点 orb 会触发相机/视频界面（运行期“每轮结束开相机”bug），
        转写气泡路径本就不可靠，故移除该点击。
        """
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

    # ------------------------------------------------------------------
    # AI 回复完成检测（基于 cap_client client_in 尾部 RMS 能量,不依赖 Compose 转写文本）
    # ------------------------------------------------------------------
    def _find_ai_pcm_remote(self, device_sn, task_id=None, test_case_id=None):
        """找 AI 回复 PCM,返回设备上路径(无匹配返回 None)。

        与 _pull_pcm 用【同一后缀 + 同一选法】,确保回复检测监控的文件 == 后续转 ai_wav
        的文件,避免两者选到不同流导致"检测判未回复、但 wav 其实有声"或反之的错配。

        旧实现用子串 'client_in' + 文件名排序取 [-1]:子串同时命中 capturer_client_in.pcm
        与 client_in..pcm 等多个流,且名字排序取最后会选中静音探针(如实测 311KB 的
        100368_..._client_in..pcm 探针,tail RMS≈149 近静默),导致 _wait_ai_reply_end_via_pcm
        误判"ChatGPT 未回复"。改为复用父类 _pick_pcm:按设备文件 size 取最大、自动排除
        小尺寸探针(size 全 0 退回名字排序取最后,保持旧行为)。与 08-18 的 user_wav 静音
        修复同一类病,此处补上 AI 侧回复检测路径。
        """
        cfg = self.PCM_APP_CONFIG.get(getattr(self, '_pcm_app', 'chatgpt'), {})
        cache_dirs = cfg.get('cache_dirs', ['/data/local/tmp'])
        ai_suffix = cfg.get('ai_suffix', 'client_in..pcm')
        files = []
        for d in cache_dirs:
            files.extend(self._list_dir_pcm(device_sn, d))
        return self._pick_pcm(device_sn, files, ai_suffix,
                              task_id=task_id, test_case_id=test_case_id)

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

    def _wait_ai_reply_start_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                     start_timeout=25, energy_thr=300, interval=1.0):
        """等 AI 开始回复(阶段A)：基于 client_in 尾部 1s RMS>energy_thr 判定 AI 开始说话。

        用于 barge-in 门：问题轮 post_process 检测到 AI 开始回复后即放下一轮打断音频，
        让打断发生在 AI 回复期间(而非 AI 说完之后)。

        返回 (status, remote):
          'fresh'  = 刚检测到 AI 开始说话(barge-in 窗口打开)，remote=当前 pcm 路径
          'ended'  = start_timeout 内未检测到新语音，但近 15s 曾有语音(post_process 起得晚，
                     回复已结束)→视作已回复，但 barge-in 窗口已错过
          'none'   = 未回复(无任何语音)
        """
        tail_bytes = 192000  # 1s @ 48000*2ch*2bytes
        remote = None
        deadline_start = time.time() + start_timeout
        saw_speech = False
        while time.time() < deadline_start:
            if self._check_stop("post_process_等AI回复开始"):
                return 'none', remote
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
        if saw_speech:
            return 'fresh', remote
        # 兜底: post_process 起得晚、回复可能已结束——扫最后 15s 是否曾有语音
        if remote and self._scan_remote_for_speech(device_sn, remote, seconds=15,
                                                   energy_thr=energy_thr,
                                                   task_id=task_id, test_case_id=test_case_id):
            self._log(level='INFO',
                      content="AI回复已结束(post_process起得晚,尾部虽静默但近15s曾有语音)",
                      task_id=task_id, test_case_id=test_case_id)
            return 'ended', remote
        self._log(level='INFO',
                  content=f"ChatGPT未回复({start_timeout}s 内 client_in 尾部无语音能量)",
                  task_id=task_id, test_case_id=test_case_id)
        return 'none', remote

    def _wait_ai_reply_end_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                   start_timeout=25, end_timeout=60,
                                   energy_thr=300, silence_seconds=8, interval=1.0):
        """等 AI 回复完成(阶段A开始 + 阶段B说完)。

        cap_client 在语音会话期间持续写 *_client_in..pcm: AI 说话=高能量, AI 静默=纯零 rms≈0。
          阶段A: 等尾部 1s RMS>energy_thr(AI 开始说话)，复用 _wait_ai_reply_start_via_pcm。
                 超时则扫最后 15s 历史:曾有语音→回复已结束(起得晚)→True；否则未回复→False。
          阶段B: AI 开说过后,等连续 silence_seconds 秒 RMS<energy_thr(说完回静默)。
        实测: 回复中停顿≤6s, 回复后静默很长, silence_seconds=8 不误触发。

        返回: True=回复结束(或超时但已说过,视为已回复); False=未回复。
        """
        tail_bytes = 192000  # 1s @ 48000*2ch*2bytes
        # 阶段A: 等 AI 开始说话
        status, remote = self._wait_ai_reply_start_via_pcm(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            start_timeout=start_timeout, energy_thr=energy_thr, interval=interval)
        if status == 'none':
            return False
        if status == 'ended':
            # post_process 起得晚，回复已结束→视作已回复
            return True
        # status == 'fresh': AI 刚开始说话，进入阶段B 等说完

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
        """退出语音全屏（best-effort）。

        实测结论（2026-08-13，设备 5SM0125613000197）：
          1. 返回键(keyevent 4) 被 ChatGPT 语音态吞掉，不退语音（已修正 _back 的 uinput
             语法，确认非语法问题，是 App 行为）。
          2. idle 语音态无“结束通话”按钮节点暴露（clickable 全 false、无 accessibility 描述）；
             结束按钮很可能只在通话进行中才出现，本驱动无法在 post_process 的 idle 态点中。
        故退出策略：先试返回键一次（顺带可关闭弹层），仍退不出则 press_home 回桌面
        （气泡页丢失，本轮 _extract_qa 读不到文本，问答文本交由 ASR）。

        注：case 模式（新默认）全程不调用本方法，仅在 teardown force-stop；round 模式才会走到
        这里，而 round+ChatGPT 多轮重入语音本就不可靠，建议用 case 模式。
        """
        # 返回键 best-effort 试一次（顺带关闭弹层）；实测对 ChatGPT 语音态不生效（App 吞），
        # 多次重试+长等待属无效空转，故只试一次即转 press_home 兜底。
        self._back(device_sn)
        time.sleep(0.5)
        try:
            if driver.find_component(By.type('android.widget.EditText')):
                self._log(level='DEBUG', content="返回键已退出语音,落回聊天首页",
                          task_id=task_id, test_case_id=test_case_id)
                return
        except Exception as e:
            self._log(level='DEBUG', content=f"退出语音校验异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
        self._log(level='INFO',
                  content="返回键未退出 ChatGPT 语音(被App吞掉),press_home 回桌面(气泡不可读,文本交ASR)",
                  task_id=task_id, test_case_id=test_case_id)
        try:
            driver.press_home()
            time.sleep(1)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @with_rpc_retry()
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
        self._record_mode = kwargs.get('record_mode', 'round')
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_pulled = False
        self._pcm_app = kwargs.get('pcm_app', 'chatgpt')
        self.question_text = None
        self.answer_text = None
        driver.shell("mount -o rw,remount /")
        driver.shell("param set sys.audio.dump.writeserver.enable w")
        driver.shell("param set sys.audio.dump.writehdi.enable w")
        driver.shell("param set sys.audio.dump.writeclient.enable a")
        driver.shell("chmod 777 /data/local/tmp")
        return True

    @with_rpc_retry()
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

        # 开局清掉可能残留的华为音乐(上轮/上个用例误识别"播放音乐"拉起的),
        # 防止其播放声污染本轮录屏/pcm。放在所有分支之前,每轮都清。方法继承自父类。
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)
        # 清理 pcm 缓存: round 每轮清(上轮拉取后残留)、case 仅首轮清(中间轮不能清,
        # 会破坏连续通话已积累的音频)。打断轮不清(pcm 可能仍在写入/尚未拉取)。
        # 必须在 _snapshot_ai_pcm_sizes 之前清,保证基线干净。
        is_interruption = kwargs.get('is_interruption') in (True, 'true', '1', 1)
        if (record_mode != 'case' or is_first) and not is_interruption:
            self._clear_pcm(device_sn, app=getattr(self, '_pcm_app', 'chatgpt'),
                            task_id=task_id, test_case_id=test_case_id)
        # ai PCM 首帧基准：轮首快照当前 ai 后缀文件 size，供 post_process 检测首帧增长
        self._ai_first_frame_ms = None
        self._ai_pcm_size_base = self._snapshot_ai_pcm_sizes(
            device_sn, app=getattr(self, '_pcm_app', 'chatgpt'))

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

    @with_rpc_retry()
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

        # 等 AI 回复：
        # - 打断轮(is_interruption=True): 只等 AI 开始回复(phase A)即放下一轮,
        #   不等 AI 说完(phase B)→ 让下一轮打断音频在 AI 回复期间播出(真 barge-in)
        # - 其它: 等 AI 回复完成(phase A+B)
        if kwargs.get('is_interruption') in (True, 'true', '1', 1):
            # 打断轮：只等 AI 开始回复(phase A)即放下一轮，让打断发生在 AI 回复期间(真 barge-in)
            self._ai_first_frame_ms = self._detect_ai_pcm_first_frame(
                device_sn, app=getattr(self, '_pcm_app', 'chatgpt'),
                task_id=task_id, test_case_id=test_case_id)
            _status, _ = self._wait_ai_reply_start_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                start_timeout=kwargs.get('ai_start_timeout', 25))
            replied = _status in ('fresh', 'ended')
            self._log(level='INFO',
                      content=f"[post_process] is_interruption,等AI开始回复后即放下一轮(barge-in): status={_status}",
                      task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = 'ChatGPT识别为空'
                self.answer_text = 'ChatGPT回复为空'
        else:
            # 检测 ai PCM 首帧(模型回复起始时刻,替代录屏 first_frame)
            self._ai_first_frame_ms = self._detect_ai_pcm_first_frame(
                device_sn, app=getattr(self, '_pcm_app', 'chatgpt'),
                task_id=task_id, test_case_id=test_case_id)
            replied = self._wait_ai_reply_end_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                start_timeout=kwargs.get('ai_start_timeout', 25),
                end_timeout=kwargs.get('ai_end_timeout', 60))
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
                if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(2)  # 给录屏落盘 finalizes mp4 的时间(参考 doubao 2s)
        else:
            # round 模式：每轮独立——停录屏 + 退出语音回聊天首页(返回键 best-effort) + 提取气泡。
            # 注:返回键对 ChatGPT 语音态常不生效(press_home 兜底回桌面),round 模式多轮重入语音
            #    依赖成功退回聊天首页;失败则下轮 pre_process 难以点中蓝按钮。case 模式无此问题。
            if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(2)
            self._exit_voice(device_sn, driver, task_id=task_id, test_case_id=test_case_id)

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
                if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
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

        # 2.5 兜底清掉华为音乐(本轮中途可能误识别"播放音乐"拉起的,防跨用例残留)
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 3. 停止 ChatGPT APP（彻底释放）
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'aa', 'force-stop', self.app_name],
                           check=False, capture_output=True, text=True, timeout=10)
            self._log(level='DEBUG', content="teardown: 已停止 ChatGPT APP",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止 ChatGPT APP 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 4. 清理 pcm 缓存(get_results 已拉取完毕,此处清设备残留,防止下个用例干扰)
        self._clear_pcm(device_sn, app=getattr(self, '_pcm_app', 'chatgpt'),
                        task_id=task_id, test_case_id=test_case_id)

        return True
