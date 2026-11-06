# -*- coding: utf-8 -*-
"""小艺通话拒识轮驱动（V9.7.10 130d03ed1 / f798f1480 移植，按 INT-2146 + INT-2363 规格重写）。

继承 V9.7.31 的 Xiaoyilivechat（harmony_xiaoyichat.Xiaoyilivechat），只补齐拒识轮
执行能力，不改动稳定驱动的常规行为。与源实现的差异（INT-2146 / INT-2363 规格裁定）：

- timing 词表白名单化（strip 后比较、英文小写归一）：response / 回复过程中 → 打断型；
  silence / 静默 / 空 → 非打断型；未知值记 WARNING 后按非打断型，不抛错。
  当轮显式配置了 is_interruption（非 None）时以用户值为准，只有缺省才由 timing 推导；
  任何情况下都不回写 kwargs['is_interruption']（该标记是打断族评估的轮次口径）。
- 静默拒识轮（is_reject 且非打断型）播放后时序（INT-2363 对齐 V9.7.10 f798f1480）：
  1) 先按 kwargs['input_gap_ms'] 等静音间隙（≤0.5s 切片、响应停止信号）；V9.7.31 无
     此参数（缺口 INT-2148），恒 0 不等待，只记日志；
  2) AI PCM 尾部 RMS 主检测模型是否回复：连续 REJECT_SILENT_NO_REPLY_SECONDS(2s)
     无语音判「未回复」，置 question/answer 为空并跳过问答提取；检测到回复则等说完
     （silence_seconds=0，模型一静默即视为说完）；检测到「起得晚、回复已结束」不再等；
  3) 拿不到 AI PCM（remote is None，DSP hook 未起流）时降级 hw_params 播放流检测：
     2s 窗口内播放流 open 即判已回复，结束等待封顶 REJECT_REPLY_WAIT_TIMEOUT(5s)；
     窗口内未 open 判未回复直接收尾。
     任何情况下不回退 UI（find_component）判定。
- 不再依赖下一轮 timing（next_round_is_reject，INT-2363 删除）。
- 收尾复用基类 post_process（不复制上游停录屏/挂断/提取问答那段代码，避免双口径），
  通过 reply_detected 形参传递判定结果：skip_reply_wait 会把 replied 强制成 True
  并继续提取问答，不能用来传「未回复」。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .driver_types import DevicePlatform
from .registry import register_driver
from .driver_constants import (
    CHECK_STOP_POLL_INTERVAL,
    REJECT_REPLY_WAIT_TIMEOUT,
    REJECT_SILENT_NO_REPLY_SECONDS,
)


@register_driver
class XiaoyiLivechatReject(Xiaoyilivechat):
    """小艺通话拒识轮驱动 v1（仅拒识轮生效，其余轮次完全走基类行为）。"""

    # —— 驱动元数据（同源 V9.7.10 130d03ed1）——
    app_type = "xiaoyi_livechat_reject"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.xiaoyi_livechat_reject.v1"
    display_name = "小艺通话聊天拒识试验驱动"
    dependencies = ["hypium"]

    # timing 词表（strip 后比较；英文小写归一）
    INTERRUPTION_TIMING_VALUES = ('response', '回复过程中')
    NON_INTERRUPTION_TIMING_VALUES = ('silence', '静默', '')
    # hw_params 降级窗口内的轮询间隔（秒）；单测可压小
    REJECT_REPLY_POLL_INTERVAL = 1.0

    # ------------------------------------------------------------------
    # timing / is_interruption 解析
    # ------------------------------------------------------------------
    def _resolve_timing_is_interruption(self, timing, task_id=None, test_case_id=None):
        """timing 词表映射为是否打断型；未知值记 WARNING 并按非打断型。"""
        key = '' if timing is None else str(timing).strip().lower()
        if key in self.INTERRUPTION_TIMING_VALUES:
            return True
        if key in self.NON_INTERRUPTION_TIMING_VALUES:
            return False
        self._log(level='WARNING',
                  content=f'拒识轮 timing 取值未知({timing!r})，按非打断型处理',
                  task_id=task_id, test_case_id=test_case_id)
        return False

    def _effective_is_interruption(self, kwargs, task_id=None, test_case_id=None):
        """当轮等待策略用的打断型判定：显式 is_interruption 优先，缺省才由 timing 推导。

        只读不写——kwargs['is_interruption'] 是打断族评估的轮次口径，驱动不得改写。
        """
        raw = kwargs.get('is_interruption')
        if raw is not None:
            return self._as_bool(raw)
        return self._resolve_timing_is_interruption(
            kwargs.get('timing'), task_id=task_id, test_case_id=test_case_id)

    # ------------------------------------------------------------------
    # 静默拒识轮：播放后时序与回复检测
    # ------------------------------------------------------------------
    def _wait_input_gap_after(self, device_sn, kwargs, task_id=None, test_case_id=None):
        """播放后先等 input_gap_ms 静音间隙，≤0.5s 切片并响应停止信号。

        Returns:
            True=等待完成/无需等待；False=收到停止信号。
        """
        raw = kwargs.get('input_gap_ms')
        try:
            gap_ms = int(float(raw or 0))
        except (TypeError, ValueError):
            gap_ms = 0
            self._log(level='WARNING',
                      content=f'拒识轮 input_gap_ms 取值非法({raw!r})，按 0 处理',
                      task_id=task_id, test_case_id=test_case_id)
        if gap_ms <= 0:
            provided = raw not in (None, '', 0, '0')
            content = (f'拒识轮 input_gap_ms={raw!r} 非正值，按 0 处理不等待'
                       if provided else
                       '拒识轮 input_gap_ms 未提供(本版本无此参数，已登记 INT-2148)，按 0 处理不等待')
            self._log(level='INFO', content=content,
                      task_id=task_id, test_case_id=test_case_id)
            return True

        self._log(level='INFO',
                  content=f'静默拒识轮播放后等待 input_gap_ms={gap_ms}ms',
                  task_id=task_id, test_case_id=test_case_id)
        deadline = time.time() + gap_ms / 1000.0
        while time.time() < deadline:
            if self._check_stop(f'post_process_拒识input_gap({gap_ms}ms)'):
                return False
            time.sleep(min(CHECK_STOP_POLL_INTERVAL, max(0.0, deadline - time.time())))
        return True

    def _wait_hw_params_reply_start_in_window(
            self, device_sn, window_seconds, task_id=None, test_case_id=None):
        """降级：在 window_seconds 内轮询 hw_params，播放流 open（True）即判已回复。

        Returns:
            True=已回复；False=窗口内未 open 或收到停止信号。
        """
        deadline = time.time() + window_seconds
        interval = self.REJECT_REPLY_POLL_INTERVAL
        while time.time() < deadline:
            if self._check_stop('post_process_拒识hw_params兜底等回复开始'):
                return False
            if self._hw_params_replying(device_sn) is True:
                return True
            time.sleep(min(interval, max(0.0, deadline - time.time())))
        return False

    def _mark_no_reply(self, reason, task_id=None, test_case_id=None):
        """未回复：置空问答文案，基类收尾据此跳过问答提取。"""
        self.question_text = '小艺识别为空'
        self.answer_text = '小艺回复为空'
        self._log(level='INFO',
                  content=f'静默拒识轮未回复({reason})，直接收尾(跳过问答提取)',
                  task_id=task_id, test_case_id=test_case_id)

    def _detect_silent_reject_reply(self, device_sn, kwargs,
                                    task_id=None, test_case_id=None):
        """静默拒识轮播放后的回复检测（不依赖 UI）。

        Returns:
            True=模型已回复；False=未回复；None=收到停止信号。
        """
        if not self._wait_input_gap_after(device_sn, kwargs,
                                          task_id=task_id, test_case_id=test_case_id):
            return None

        # 主检测：AI PCM 尾部 RMS，连续 REJECT_SILENT_NO_REPLY_SECONDS 无语音判未回复
        status, remote = self._wait_ai_reply_start_via_pcm(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            start_timeout=REJECT_SILENT_NO_REPLY_SECONDS)
        if self._check_stop('post_process_拒识检测回复'):
            return None

        if status == 'fresh':
            # 已开始回复 → 等说完（silence_seconds=0：模型一静默即视为说完）
            ended = self._wait_ai_reply_end_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id,
                silence_seconds=0)
            if not ended and self._check_stop('post_process_拒识等回复结束'):
                return None
            self._log(level='INFO', content='静默拒识轮模型已回复(AI PCM RMS)',
                      task_id=task_id, test_case_id=test_case_id)
            return True

        if status == 'ended':
            # post_process 起得晚、回复已结束 → 不再等
            self._log(level='INFO',
                      content='静默拒识轮模型已回复(AI PCM RMS，回复已结束不再等待)',
                      task_id=task_id, test_case_id=test_case_id)
            return True

        if remote is not None:
            # 拿得到 AI PCM 但窗口内无语音 → 未回复
            self._mark_no_reply(
                f'{REJECT_SILENT_NO_REPLY_SECONDS}s 内 AI PCM 尾部无语音',
                task_id=task_id, test_case_id=test_case_id)
            return False

        # 拿不到 AI PCM（DSP hook 未起流）→ 降级 hw_params 播放流检测，不回退 UI
        if not self._wait_hw_params_reply_start_in_window(
                device_sn, REJECT_SILENT_NO_REPLY_SECONDS,
                task_id=task_id, test_case_id=test_case_id):
            if self._check_stop('post_process_拒识hw_params兜底'):
                return None
            self._mark_no_reply(
                f'AI PCM 不可用且 {REJECT_SILENT_NO_REPLY_SECONDS}s 内播放流未 open',
                task_id=task_id, test_case_id=test_case_id)
            return False
        self._wait_ai_reply_end_via_hw_params(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            timeout=REJECT_REPLY_WAIT_TIMEOUT)
        if self._check_stop('post_process_拒识hw_params等回复结束'):
            return None
        self._log(level='INFO',
                  content=(f'静默拒识轮模型已回复(hw_params 降级，'
                           f'结束等待封顶 {REJECT_REPLY_WAIT_TIMEOUT}s)'),
                  task_id=task_id, test_case_id=test_case_id)
        return True

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """拒识轮：静默轮播放后检测回复，再走基类收尾；非拒识轮完全走原驱动行为。"""
        if not self._as_bool(kwargs.get('is_reject')):
            return super().post_process(
                device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

        is_interruption = self._effective_is_interruption(
            kwargs, task_id=task_id, test_case_id=test_case_id)
        self._log(level='INFO',
                  content=(f"拒识轮：timing={kwargs.get('timing')!r} "
                           f"显式is_interruption={kwargs.get('is_interruption')!r} "
                           f"→ 按打断型={is_interruption}"),
                  task_id=task_id, test_case_id=test_case_id)

        # 不改写 kwargs（is_interruption 等轮次口径原样透传）
        super_kwargs = dict(kwargs)
        if is_interruption:
            self._log(level='INFO',
                      content='拒识轮不等待回复结束(打断型)，直接收尾进入下一轮',
                      task_id=task_id, test_case_id=test_case_id)
            super_kwargs['skip_reply_wait'] = True
            return super().post_process(
                device_sn, task_id=task_id, test_case_id=test_case_id, **super_kwargs)

        reply_detected = self._detect_silent_reject_reply(
            device_sn, kwargs, task_id=task_id, test_case_id=test_case_id)
        if reply_detected is None:
            self._log(level='INFO',
                      content='拒识轮等待被停止信号中断，本轮直接收敛',
                      task_id=task_id, test_case_id=test_case_id)
            return True
        super_kwargs['reply_detected'] = reply_detected
        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **super_kwargs)
