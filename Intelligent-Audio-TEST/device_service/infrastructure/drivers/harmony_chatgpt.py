"""ChatGPT(HarmonyOS Android 兼容层) 语音通话驱动 — 继承小艺通话驱动。

V31 版相对 V10 的差异:
- 父类 _find_ai_pcm_remote/_read_tail_rms/_scan_remote_for_speech/_wait_ai_reply_*
  已按 PCM_APP_CONFIG['chatgpt'] + 文件名自适应采样率/声道 + _pick_pcm(size 最大,
  排除静音探针流),RMS 检测与 PCM 定位方法无需覆盖,全部继承;
- 采集文件统一上传 OSS(父类 get_results/_pull_record_file V31 语义);
- 时序魔法数字全部替换为 driver_constants 常量(config_manager 可配)。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .driver_types import AppType, AppVersion, DevicePlatform
from .registry import register_driver
from .utils import By, with_rpc_retry
from .driver_constants import *
from shared.utils.time_utils import ms_to_utc8_str, MS_FMT


@register_driver
class ChatGptVoiceChat(Xiaoyilivechat):
    """ChatGPT 语音通话专用驱动。

    仿照 harmony_xiaoyichat.Xiaoyilivechat 实现，功能要求与小艺通话一致：
      - 录屏(screenrecorder) + 抓取 cap_client PCM(用户输入/AI回复) + 转 wav
      - initialize/pre_process/post_process/get_results/teardown 生命周期
      - 多轮 round/case 录屏模式、首帧时延、问答文本提取、结果格式

    继承 Xiaoyilivechat 可直接复用：mp4→wav / pcm→wav / hdc 封装 / 录屏启停 /
    PCM 清理与拉取 / PCM_APP_CONFIG['chatgpt'] / get_results 结果拼装 / RMS 回复检测。

    差异点（本类覆盖）：
      1. 目标 App 为 com.openai.chatgpt（鸿蒙 Android 兼容层运行，Compose UI）
      2. 语音通话入口为聊天首页输入栏右侧的蓝色按钮（无稳定 text/key，用坐标点击）
      3. 回复完成检测继承父类: cap_client 的 client_in 尾部 RMS 能量（AI 说话=高能量/
         静默≈0），不依赖 Compose 转写文本（语音态透传性不稳定且无气泡）；问答文本
         走 user_wav/ai_wav 的 ASR
      4. cap_client 音频采集已在设备后台运行，驱动无需启停，仅按需清理/拉取 PCM
    """

    # —— 驱动元数据 ——
    app_type = AppType.CHATGPT
    version = AppVersion.V1
    platform = DevicePlatform.HARMONYOS
    display_name = "ChatGPT语音通话 v1"
    dependencies = ["hypium"]

    # ChatGPT 包名（鸿蒙 Android 兼容层）
    APP_PACKAGE = 'com.openai.chatgpt'
    # PCM 抓取目标(PCM_APP_CONFIG['chatgpt'] 已由父类定义)
    PCM_APP = 'chatgpt'

    # —— UI 定位常量 ——
    # 聊天首页底部输入栏按钮(屏幕 1280x2832;实测 2026-08-13 ChatGPT 改版后输入栏
    # 上移至 y≈1607,旧版 y=2650 已失效)。四件套结构不变: [+] / EditText / 麦克风 / 蓝色语音(最右)。
    #   [+]     : (126, 1607)
    #   输入框   : EditText, bounds≈(210,1523,916,1691), center (563,1607)
    #   麦克风   : (1000, 1607)
    #   蓝色语音 : (1154, 1607)  <- 语音通话入口（最右侧按钮）
    # pre_process 用 EditText.getBounds() 动态取中心 y、x 固定 1147；1147∈右侧按钮
    # x[1098,1210]，故 (1147, edit_center_y) 仍命中蓝色语音按钮。
    HOME_BTN_VOICE = (1147, 1607)   # 蓝色语音按钮(语音通话入口;实际 y 由 EditText 动态取)
    # 语音全屏 orb(改版后移至屏幕下方,clickable)。⚠️ 驱动不再点击 orb:通话进行中点 orb
    # 会触发相机/视频界面(运行期"每轮结束开相机"bug 的来源),故此坐标仅作文档记录,不落代码。
    EDIT_TEXT_TYPE = 'android.widget.EditText'   # 聊天首页输入框类型(Compose 透传)
    TRANSCRIPT_TEXT_TYPE = 'android.widget.TextView'  # 转写气泡文本类型(策略2 type 匹配)
    TRANSCRIPT_XPATH = '//android.widget.TextView'
    # 转写文本噪声过滤:状态栏时钟/电量等(单字符一律过滤)
    TRANSCRIPT_NOISE_TEXTS = ('07', '08', '09', ':', '100')
    # 问答分类: x0>=300 视为右侧用户气泡,否则左侧 AI 气泡
    QA_USER_X0_THRESHOLD = 300
    # 未回复时的占位文本
    EMPTY_QUESTION_TEXT = 'ChatGPT识别为空'
    EMPTY_ANSWER_TEXT = 'ChatGPT回复为空'

    def __init__(self):
        super().__init__()
        # 覆盖小艺的 app_name，指向 ChatGPT
        self.app_name = self.APP_PACKAGE
        # PCM 抓取目标固定为 chatgpt（cap_client 写 /data/local/tmp）
        self._pcm_app = self.PCM_APP

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
            self._hdc_shell(device_sn, 'uinput', '-K', '-d', '4', '-u', '4')
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
            found = driver.find_all_components(By.xpath(self.TRANSCRIPT_XPATH))
            if found:
                comps = found
        except Exception:
            pass
        # 策略2: type 匹配
        if not comps:
            try:
                found = driver.find_all_components(By.type(self.EDIT_TEXT_TYPE))
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
                if txt in self.TRANSCRIPT_NOISE_TEXTS or len(txt) <= 1:
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
        且 clickable），且通话进行中点 orb 会触发相机/视频界面（运行期"每轮结束开相机"bug），
        转写气泡路径本就不可靠，故移除该点击。
        """
        items = self._get_transcript(driver)
        if not items:
            self.question_text = None
            self.answer_text = None
            return
        user_items = [t for (t, x0) in items if x0 >= self.QA_USER_X0_THRESHOLD]
        ai_items = [t for (t, x0) in items if x0 < self.QA_USER_X0_THRESHOLD]
        self.question_text = user_items[-1] if user_items else None
        self.answer_text = ai_items[-1] if ai_items else None
        self._log(level='DEBUG',
                  content=f"转写提取 user={self.question_text!r} ai={self.answer_text!r} (共{len(items)}条)",
                  task_id=task_id, test_case_id=test_case_id)

    def _exit_voice(self, device_sn, driver, task_id=None, test_case_id=None):
        """退出语音全屏（best-effort）。

        实测结论（2026-08-13，设备 5SM0125613000197）：
          1. 返回键(keyevent 4) 被 ChatGPT 语音态吞掉，不退语音（已修正 _back 的 uinput
             语法，确认非语法问题，是 App 行为）。
          2. idle 语音态无"结束通话"按钮节点暴露（clickable 全 false、无 accessibility 描述）；
             结束按钮很可能只在通话进行中才出现，本驱动无法在 post_process 的 idle 态点中。
        故退出策略：先试返回键一次（顺带可关闭弹层），仍退不出则 press_home 回桌面
        （气泡页丢失，本轮 _extract_qa 读不到文本，问答文本交由 ASR）。

        注：case 模式（新默认）全程不调用本方法，仅在 teardown force-stop；round 模式才会走到
        这里，而 round+ChatGPT 多轮重入语音本就不可靠，建议用 case 模式。
        """
        # 返回键 best-effort 试一次（顺带关闭弹层）；实测对 ChatGPT 语音态不生效（App 吞），
        # 多次重试+长等待属无效空转，故只试一次即转 press_home 兜底。
        self._back(device_sn)
        time.sleep(CHECK_STOP_POLL_INTERVAL)
        try:
            if driver.find_component(By.type(self.EDIT_TEXT_TYPE)):
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
            time.sleep(NORMAL_WAIT)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化：解锁→清弹窗→回桌面→停 ChatGPT→aa start 启动 ChatGPT→清残留 PCM。

        注意1：不调用父类 initialize（其内部含小艺专属的清上下文/删对话记录 UI，
        在 ChatGPT 上会因找不到 SymbolGlyph 而抛异常）。
        注意2：也不复用 HarmonyDriver.initialize 的图标点击路径——其 app_icon_key 默认是小艺
        图标 key，会在桌面误点小艺图标启动小艺而非 ChatGPT。这里直接 aa start 启动 ChatGPT，
        不依赖图标 key。
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
        time.sleep(LONG_WAIT)

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
            r = self._hdc_shell(device_sn, 'aa', 'start',
                                '-b', self.app_name, '-a', main_activity)
            self._log(level='DEBUG',
                      content=f"aa start {self.app_name}/{main_activity}: rc={r.returncode} out={(r.stdout or '').strip()[:200]}",
                      task_id=task_id, test_case_id=test_case_id)
            if r.returncode != 0:
                self._log(level='ERROR', content=f"aa start ChatGPT 失败: {r.stderr or r.stdout}",
                          task_id=task_id, test_case_id=test_case_id)
                return False
        except Exception as e:
            self._log(level='ERROR', content=f"aa start ChatGPT 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        time.sleep(EXTRA_LONG_WAIT)
        self.close_popups(device_sn)

        # 重置跨用例残留状态（驱动单例复用）
        self._recording = False
        self._record_mode = kwargs.get('record_mode', 'round')
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_pulled = False
        self._record_device_path = None  # 重置: 避免上个用例的 VID 路径残留
        self._pcm_app = kwargs.get('pcm_app', self.PCM_APP)
        self.question_text = None
        self.answer_text = None
        # 开启抓取 pcm 权限(fwk 层,豆包/ChatGPT 共用;小艺走 DSP 层不在此列)
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
            self._clear_pcm(device_sn, app=self._pcm_app,
                            task_id=task_id, test_case_id=test_case_id)
        # ai PCM 首帧基准：轮首快照当前 ai 后缀文件 size，供 post_process 检测首帧增长
        self._ai_first_frame_ms = None
        self._ai_pcm_size_base = self._snapshot_ai_pcm_sizes(
            device_sn, app=self._pcm_app)

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
            edit = driver.find_component(By.type(self.EDIT_TEXT_TYPE))
            if edit:
                b = edit.getBounds()  # (left, right, top, bottom)
                tap_y = (b[2] + b[3]) // 2
        except Exception as e:
            self._log(level='DEBUG', content=f"定位 EditText 失败,用默认坐标: {e}")
        self._tap_xy(driver, tap_x, tap_y)
        driver.wait(EXTRA_LONG_WAIT)
        # 校验是否进入语音界面：聊天首页的输入框 EditText 应消失
        # （语音全屏界面无 EditText；Compose 元素透传性已验证可用）
        try:
            edit = driver.find_component(By.type(self.EDIT_TEXT_TYPE))
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
        time.sleep(LONG_WAIT)
        return True

    @with_rpc_retry()
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理：等 AI 回复结束 → 按模式收尾 → 提取气泡文本(best-effort)。

        回复完成判定继承父类: cap_client 的 client_in 尾部 RMS 能量(AI 说话=高能量/静默≈0),
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

        # 等 AI 回复(继承父类 RMS 双阶段判定)：
        # - 打断轮(is_interruption=True): 只等 AI 开始回复(phase A)即放下一轮,
        #   不等 AI 说完(phase B)→ 让下一轮打断音频在 AI 回复期间播出(真 barge-in)
        # - 其它: 等 AI 回复完成(phase A+B)
        if kwargs.get('is_interruption') in (True, 'true', '1', 1):
            self._ai_first_frame_ms = self._detect_ai_pcm_first_frame(
                device_sn, app=self._pcm_app,
                task_id=task_id, test_case_id=test_case_id)
            _status, _ = self._wait_ai_reply_start_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                start_timeout=kwargs.get('ai_start_timeout', None))
            replied = _status in ('fresh', 'ended')
            self._log(level='INFO',
                      content=f"[post_process] is_interruption,等AI开始回复后"
                              f"延迟{BARGE_IN_DELAY_SECONDS}s放下一轮(barge-in): status={_status}",
                      task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = self.EMPTY_QUESTION_TEXT
                self.answer_text = self.EMPTY_ANSWER_TEXT
        else:
            # 检测 ai PCM 首帧(模型回复起始时刻,替代录屏 first_frame)
            self._ai_first_frame_ms = self._detect_ai_pcm_first_frame(
                device_sn, app=self._pcm_app,
                task_id=task_id, test_case_id=test_case_id)
            replied = self._wait_ai_reply_end_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = self.EMPTY_QUESTION_TEXT
                self.answer_text = self.EMPTY_ANSWER_TEXT

        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        # 打断轮: 检测到 AI 开始回复后延迟 BARGE_IN_DELAY_SECONDS 再放下一轮打断音频,
        # 让 AI 先说一会(真 barge-in 落在回复中段而非刚开口);仅 case 模式非末轮有
        # "下一轮"才需延迟。分片轮询,可被停止/暂停打断。
        if (kwargs.get('is_interruption') in (True, 'true', '1', 1)
                and replied and record_mode == 'case' and not is_last):
            self._log(level='INFO',
                      content=(f"[post_process] 检测到AI开始回复,等{BARGE_IN_DELAY_SECONDS}s"
                               f"再放下一轮打断音频(barge-in落回复中段): r{round_number}/{total_rounds}"),
                      task_id=task_id, test_case_id=test_case_id)
            poll = CHECK_STOP_POLL_INTERVAL
            for _ in range(max(1, int(round(BARGE_IN_DELAY_SECONDS / poll)))):
                if self._check_stop(f'AI回复后延迟{BARGE_IN_DELAY_SECONDS}s'):
                    return True
                time.sleep(poll)

        if record_mode == 'case':
            # case 模式：一次连续语音通话 / 一个录屏 / 一个连续 PCM,对话间不退出语音。
            # 中间轮：不停录屏、不退出语音、不提取(全程语音态无气泡)。
            # 末轮：停录屏；不主动退语音——teardown 的 aa force-stop 即退出,
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
                time.sleep(LONG_WAIT)  # 给录屏落盘 finalizes mp4 的时间
        else:
            # round 模式：每轮独立——停录屏 + 退出语音回聊天首页(返回键 best-effort) + 提取气泡。
            # 注:返回键对 ChatGPT 语音态常不生效(press_home 兜底回桌面),round 模式多轮重入语音
            #    依赖成功退回聊天首页;失败则下轮 pre_process 难以点中蓝按钮。case 模式无此问题。
            if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(LONG_WAIT)
            self._exit_voice(device_sn, driver, task_id=task_id, test_case_id=test_case_id)

        if not replied:
            return True

        # 提取问答文本：_extract_qa 在语音态会点 orb 显现转写再读(case 中间/末轮均适用),
        # 在聊天首页(round 模式退语音成功后)气泡已可见直接读。取最后一条 Q/A(best-effort)。
        # case 多轮完整/分轮文本以 ai_wav 的 ASR(按 playback 时间戳切段)为准。
        self._extract_qa(driver, task_id=task_id, test_case_id=test_case_id)
        return True

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束清理：兜底停录屏→(case)兜底拉取录屏→退出语音→回桌面→停止 ChatGPT→清 PCM。"""
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
                time.sleep(NORMAL_WAIT)
                self._log(level='DEBUG', content="teardown: 兜底退出语音/回桌面",
                          task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                self._log(level='DEBUG', content=f"teardown: 退出语音失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)

        # 3. 兜底清掉华为音乐(本轮中途可能误识别"播放音乐"拉起的,防跨用例残留)
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 4. 停止 ChatGPT APP（彻底释放）
        try:
            r = self._hdc_shell(device_sn, 'aa', 'force-stop', self.app_name)
            self._log(level='DEBUG', content=f"teardown: 已停止 ChatGPT APP: rc={r.returncode}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止 ChatGPT APP 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 5. 清理 pcm 缓存(get_results 已拉取完毕,此处清设备残留,防止下个用例干扰)
        self._clear_pcm(device_sn, app=self._pcm_app,
                        task_id=task_id, test_case_id=test_case_id)

        return True