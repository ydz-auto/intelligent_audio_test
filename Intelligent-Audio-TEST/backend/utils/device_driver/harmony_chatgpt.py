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

    # 语音界面：底部圆形打断/结束按钮（回复进行中与空态位置会移动，按可点击 View 兜底定位）
    VOICE_ORB_REGION = (203, 1015, 1078, 1890)  # 中央 orb 大致区域

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

        依据气泡 x 起点区分：x0 偏大(右)→用户；x0 偏小(左)→AI。
        取各自最后一条作为本轮问答。
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

    def _exit_voice(self, device_sn, driver, task_id=None, test_case_id=None):
        """退出语音模式回聊天首页：先 home 退出全屏语音，再确保回首页。"""
        try:
            driver.press_home()
            time.sleep(1)
            self._log(level='DEBUG', content="已 press_home 退出语音模式",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='DEBUG', content=f"press_home 退出语音失败，尝试返回键: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            self._back(device_sn)
            time.sleep(1)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化：解锁→清弹窗→启动 ChatGPT→清理残留 PCM。

        注意：不调用 Xiaoyilivechat.initialize（其内部含小艺专属的清上下文/删对话记录 UI，
        在 ChatGPT 上会因找不到 SymbolGlyph 而抛异常），改为直接调用祖父类
        HarmonyDriver.initialize：解锁、关弹窗、stop_app + aa start 启动 ChatGPT。
        """
        # 跳过 Xiaoyilivechat.initialize，直接用 HarmonyDriver.initialize
        if not HarmonyDriver.initialize(self, device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs):
            return False
        driver = self._get_driver(device_sn)
        if not driver:
            return False

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

        # 确保在聊天首页（HarmonyDriver.initialize 已 aa start ChatGPT）
        # 右上角按钮可呼出“临时聊天/新对话”面板；如需清空上下文可在此扩展
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
        """后处理：等待 AI 回复结束→(round模式)停录屏+退出语音→提取问答文本。

        回复检测依赖语音界面转写文本：出现转写=回复开始；转写稳定=回复结束。
        """
        driver = self._get_driver(device_sn)
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']})",
                  task_id=task_id, test_case_id=test_case_id)

        # 等待回复开始：转写文本出现
        started = self._wait_for_condition(
            lambda: bool(self._get_transcript(driver)),
            timeout=60, interval=1, operation_name='等待回复开始'
        )
        if not started:
            self._log(level='INFO', content='ChatGPT未回复(无转写文本)', task_id=task_id, test_case_id=test_case_id)
            self.question_text = 'ChatGPT识别为空'
            self.answer_text = 'ChatGPT回复为空'
        else:
            self._log(level='INFO', content='模型开始回复', task_id=task_id, test_case_id=test_case_id)
            # 等待回复结束：转写文本稳定
            self._wait_reply_end(driver, task_id=task_id, test_case_id=test_case_id)

        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        if record_mode == 'case':
            # case 模式：中间轮不停录屏、不退出语音；仅末轮停录屏以便 get_results 拉取
            if is_last:
                if not self._stop_recorder(device_sn):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(5)
        else:
            # round 模式：每轮停录屏 + 退出语音
            if not self._stop_recorder(device_sn):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(2)
            self._exit_voice(device_sn, driver, task_id=task_id, test_case_id=test_case_id)
            driver.wait(3)

        if not started:
            return True

        # 提取本轮问答文本（语音界面转写）
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
