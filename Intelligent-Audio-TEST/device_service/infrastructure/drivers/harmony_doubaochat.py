"""豆包(HarmonyOS) 语音通话驱动 — 继承小艺通话驱动,复用全部基础设施。

V31 版相对 V10 的差异:
- 父类 _read_tail_rms/_scan_remote_for_speech/_wait_ai_reply_* 已通过文件名
  自适应采样率/声道(48k 双声道均可解析),RMS 检测方法无需覆盖,全部继承;
- _find_ai_pcm_remote 父类按 PCM_APP_CONFIG['doubao'].ai_suffix + _pick_pcm
  (size 最大者,排除静音探针流)查找,同样继承;
- 录屏拉取/get_results 走 OSS 即传即清(父类 V31 语义);
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
class DoubaoChat(Xiaoyilivechat):
    """豆包(HarmonyOS)设备驱动 — 复用 Xiaoyilivechat 全部基础设施
    (_hdc_shell / _clear_pcm / PCM_APP_CONFIG['doubao'] / _mp4_to_wav /
    _start_recorder / _pull_record_file / get_results / RMS 回复检测等)，
    仅 initialize 用 hdc aa start 命令拉起豆包 app(替代小艺的 UI 点击)。

    录屏模式与 ChatGPT/小艺通话一致(record_mode 格式):
      - round=每轮一段(默认): 每轮独立启停录屏 + 挂断 + 提取本轮气泡
      - case=整用例一段: 一次连续通话 / 一个录屏 / 一个连续 PCM,中间轮不停录屏
        不挂断,末轮停录屏 + 挂断 + 提取气泡;teardown 兜底拉取完整录屏

    回复完成检测继承父类: 基于 cap_client 的 client_in.. PCM 尾部 RMS 能量
    (双阶段+历史兜底),不依赖控件文本(说话或点击打断/正在听…)。
    """

    # —— 驱动元数据 ——
    app_type = AppType.DOUBAO
    version = AppVersion.V1
    platform = DevicePlatform.HARMONYOS
    display_name = "豆包语音通话 v1"
    dependencies = ["hypium"]

    DOUBAO_BUNDLE = 'com.larus.nova.hm'
    DOUBAO_ABILITY = 'MainAbility'
    # PCM 抓取目标(PCM_APP_CONFIG['doubao'] 已由父类定义)
    PCM_APP = 'doubao'

    # —— 豆包 UI 坐标(1280x2832 屏实测;Compose 控件无稳定 text/key 只能坐标) ——
    NAV_TOUCH = (105, 231)        # 聊天首页左侧导航栏入口
    SETTINGS_TOUCH = (959, 2552)  # 设置界面入口
    BACK_TOUCH = (105, 234)       # 设置页返回
    CONFIRM_TOUCH = (990, 266)    # 确认弹窗按钮
    CALL_TOUCH = (1011, 231)      # 通话入口(聊天首页顶部)
    HANGUP_TOUCH = (1060, 2368)   # 通话页挂断按钮
    # 语义文案(有稳定 text 的控件走 By.text)
    TEXT_NEW_TOPIC = '开启新话题'
    TEXT_CHAT_ENTRY = '对话'
    # 未回复时的占位文本
    EMPTY_QUESTION_TEXT = '豆包识别为空'
    EMPTY_ANSWER_TEXT = '豆包回复为空'
    # round 模式挂断后落回聊天列表的问答气泡(xpath)
    QA_QUESTION_XPATH = '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Row/Text'
    QA_ANSWER_XPATH = '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Column//Stack/Text'

    def __init__(self):
        super().__init__()
        # 覆盖小艺的 app_name，指向豆包
        self.app_name = self.DOUBAO_BUNDLE
        # PCM 抓取目标固定为 doubao
        self._pcm_app = self.PCM_APP

    # ------------------------------------------------------------------
    # 录屏停止修补(豆包录屏时序 bug)
    # ------------------------------------------------------------------
    def _force_stop_recorder(self, device_sn, task_id=None, test_case_id=None):
        """aa force-stop 硬停 screenrecorder(幂等)。用于避免 toggle 状态错位 + teardown 兜底。"""
        try:
            r = self._hdc_shell(device_sn, 'aa', 'force-stop', self.RECORDER_BUNDLE)
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
          - 有首帧(真正在录): 走父类 graceful toggle(能 finalizes mp4),留落盘时间后再硬停兜底;
          - 无首帧(从未真正捕获): 跳过 toggle(避免停变开),直接 force-stop 清残留态。
        两条路径末尾都 force-stop 一次(幂等),保证 screenrecorder 不残留。
        """
        first_frame = getattr(self, '_recorder_first_frame_ms', None)
        if first_frame is not None:
            self._log(level='INFO',
                      content=f"[录屏] _stop_recorder: 首帧已记录({first_frame}),graceful toggle + force-stop 兜底",
                      task_id=task_id, test_case_id=test_case_id)
            super()._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)
            time.sleep(LONG_WAIT)  # 给 graceful toggle 落盘 finalizes mp4 的时间
        else:
            self._log(level='WARNING',
                      content="[录屏] _stop_recorder: 首帧为 None(录屏未真正启动),跳过 toggle 直接 force-stop(避免停变开)",
                      task_id=task_id, test_case_id=test_case_id)
        self._force_stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)
        return True

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """打开豆包 app(纯命令行拉起，不调用父类 initialize，避免基类点小艺图标):
        解锁/关弹窗/回桌面 → 停豆包 → aa start 拉起豆包 → 重置录屏状态 →
        fwk 抓取权限 → 清聊天记录以及上下文(开启新话题)
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
        time.sleep(LONG_WAIT)

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
        time.sleep(APP_LAUNCH_WAIT)
        # 启动后再次关闭弹窗
        self.close_popups(device_sn)

        # 重置跨用例残留的录屏状态（驱动单例复用）
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

        # 清除聊天记录以及上下文(开启新话题)
        # 豆包聊天首页右上角菜单按钮: 先尝试语义查找(SymbolGlyph), 找不到则回退坐标
        driver.wait(APP_LAUNCH_WAIT)
        try:
            # 第1步:进入导航栏
            driver.touch(self.NAV_TOUCH)
            driver.wait(NORMAL_WAIT)
            # 进入设置界面
            driver.touch(self.SETTINGS_TOUCH)
            driver.wait(NORMAL_WAIT)
            # 开启新话题
            driver.touch(By.text(self.TEXT_NEW_TOPIC))
            driver.wait(NORMAL_WAIT)
            driver.touch(self.BACK_TOUCH)
            driver.wait(NORMAL_WAIT)
            driver.touch(self.CONFIRM_TOUCH)
        except Exception as e:
            self._log(level='WARNING', content=f"清除聊天记录失败(跳过继续): {e}",
                      task_id=task_id, test_case_id=test_case_id)
        return True

    @with_rpc_retry()
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

        # 开启通话聊天（首轮）
        try:
            driver.touch(self.CALL_TOUCH)
            driver.wait(CHECK_STOP_POLL_INTERVAL)
            driver.wait(LONG_WAIT)
        except Exception as e:
            self._log(level='WARNING', content=f"点击通话入口失败,尝试备用方式: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            try:
                alt = driver.find_component(By.text(self.TEXT_CHAT_ENTRY))
                if alt:
                    alt.click()
                    driver.wait(LONG_WAIT)
            except Exception as e2:
                self._log(level='ERROR', content=f"通话入口未找到: {e2}",
                          task_id=task_id, test_case_id=test_case_id)
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
        # 首帧为 None(录屏未真正启动):先 force-stop 清残留态,再重试一次 aa start
        # 豆包场景下 aa start 有时未真正开始捕获,blind toggle 会导致"停变开",
        # 故在 pre_process 阶段就保证拿到首帧,避免 post_process 时无 mp4 产生
        if getattr(self, '_recorder_first_frame_ms', None) is None:
            self._log(level='WARNING',
                      content=(f"首帧为 None,录屏未真正启动,force-stop 清残留后重试一次: "
                               f"{self._record_file_name}"),
                      task_id=task_id, test_case_id=test_case_id)
            self._force_stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)
            time.sleep(NORMAL_WAIT)
            if not self._start_recorder(device_sn, file_name=self._record_file_name):
                self._log(level='ERROR',
                          content=f"重试启动录屏失败,服务未运行: {self._record_file_name}",
                          task_id=task_id, test_case_id=test_case_id)
                return False
        self._recording = True
        self._log(level='INFO',
                  content=(f"启动录屏成功: {self._record_file_name} "
                           f"first_frame_ms={getattr(self, '_recorder_first_frame_ms', None)} "
                           f"(None=未真正捕获首帧,_stop_recorder 将走 force-stop 避免停变开)"),
                  task_id=task_id, test_case_id=test_case_id)
        time.sleep(LONG_WAIT)
        return True

    @with_rpc_retry()
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理：等 AI 回复结束 → 按模式收尾 → (round 模式) 提取问答文本。

        回复完成检测继承父类: client_in.. PCM 尾部 RMS 能量(双阶段+历史兜底),
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

        # 等 AI 回复完成：client_in.. 尾部 RMS 双阶段判定(父类实现)
        # 打断轮(is_interruption=True): 只等 AI 开始回复(phase A, RMS 能量>阈值)即放下一轮,
        # 让打断发生在 AI 回复期间(真 barge-in)。不再用 size 增长判断——PCM 文件全程匀速
        # 增长,size 增长只代表"文件在写",不代表"AI 在说话"。
        if kwargs.get('is_interruption') in (True, 'true', '1', 1):
            _status, _ = self._wait_ai_reply_start_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                start_timeout=kwargs.get('ai_start_timeout', None))
            replied = _status in ('fresh', 'ended')
            self._log(level='INFO',
                      content=f"[post_process] is_interruption,等AI开始回复(RMS)后"
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
            replied = self._wait_ai_reply_end_via_pcm(device_sn, task_id=task_id, test_case_id=test_case_id)
            if not replied:
                self.question_text = self.EMPTY_QUESTION_TEXT
                self.answer_text = self.EMPTY_ANSWER_TEXT

        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        # case 模式打断轮非末轮：检测到 AI 开始回复后延迟 BARGE_IN_DELAY_SECONDS 再进
        # 下一轮播放（分片轮询,可被停止/暂停打断）。让 AI 先说一会再被打断（真 barge-in
        # 落在回复中段）
        if (kwargs.get('is_interruption') in (True, 'true', '1', 1)
                and replied and record_mode == 'case' and not is_last):
            self._log(level='INFO',
                      content=(f"[post_process] 检测到AI开始回复,等{BARGE_IN_DELAY_SECONDS}s后"
                               f"进入下一轮播放: r{round_number}/{total_rounds}"),
                      task_id=task_id, test_case_id=test_case_id)
            poll = CHECK_STOP_POLL_INTERVAL
            for _ in range(max(1, int(round(BARGE_IN_DELAY_SECONDS / poll)))):
                if self._check_stop(f'AI回复后延迟{BARGE_IN_DELAY_SECONDS}s'):
                    return True
                time.sleep(poll)

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
            if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(EXTRA_LONG_WAIT)
            self._log(level='INFO',
                      content="case模式末轮不挂断,通话交给 teardown 结束(保持上下文连续)",
                      task_id=task_id, test_case_id=test_case_id)
            return True

        # round 模式：每轮独立——停录屏 + 挂断 + 提取气泡。
        if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
            self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
        self._recording = False
        time.sleep(EXTRA_LONG_WAIT)
        try:
            driver.touch(self.HANGUP_TOUCH)
            self._log(level='DEBUG', content="已挂断通话", task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"挂断通话失败: {e}", task_id=task_id, test_case_id=test_case_id)
        driver.wait(EXTRA_LONG_WAIT)

        if not replied:
            return True

        # round 模式挂断后落回聊天列表,提取本轮问答文本(取最后一条,未识别到返回 None)
        question_components = driver.find_all_components(By.xpath(self.QA_QUESTION_XPATH))
        self._log(level='DEBUG',
                  content=f"question_components count={len(question_components) if question_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if question_components:
            for i, comp in enumerate(question_components):
                self._log(level='DEBUG', content=f"question_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.question_text = question_components[-1].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(self.QA_ANSWER_XPATH))
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
        2. case 模式兜底：末轮未拉取时补拉一次完整录屏(OSS URL)
        3. 确保通话已挂断（兜底）
        4. 退出豆包聊天界面，回桌面
        5. 兜底停掉华为音乐(防跨用例残留)
        6. 停止豆包 APP（彻底释放）
        7. 无条件硬停 screenrecorder(幂等,豆包录屏 bug 的核心修复兜底)
        8. 清理 pcm 缓存(get_results 已拉取完毕,此处清设备残留,防止下个用例干扰)
        """
        # 1. 兜底停止录屏（仅在仍在录屏时执行，避免 toggle 把已停止的录屏又打开）
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
            driver.touch(self.HANGUP_TOUCH)
            self._log(level='DEBUG', content="teardown: 兜底挂断通话",
                      task_id=task_id, test_case_id=test_case_id)
            time.sleep(LONG_WAIT)
        except Exception as e:
            self._log(level='DEBUG', content=f"teardown: 无残留通话或挂断失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 4. 回桌面（退出豆包聊天界面）
        try:
            driver.press_home()
            time.sleep(NORMAL_WAIT)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 回桌面失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 5. 兜底清掉华为音乐(本轮中途可能误识别"播放音乐"拉起的,防跨用例残留)
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 6. 停止豆包 APP（彻底释放）
        try:
            driver.stop_app(self.DOUBAO_BUNDLE)
            self._log(level='DEBUG', content="teardown: 已停止豆包 APP",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止豆包 APP 失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 7. 无条件硬停 screenrecorder 兜底(幂等):无论前面 _recording 标志真假,
        #    保证"录屏不停止"残留不可能跨用例存活(豆包录屏 bug 的核心修复兜底)。
        self._force_stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 8. 清理 pcm 缓存(get_results 已拉取完毕,此处清设备残留,防止下个用例干扰)
        self._clear_pcm(device_sn, app=self._pcm_app,
                        task_id=task_id, test_case_id=test_case_id)

        return True
