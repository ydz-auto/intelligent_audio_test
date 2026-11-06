# -*- coding: utf-8 -*-
"""豆包通话拒识轮驱动（V9.7.10 412037ea1 移植，按 INT-2402 规格适配 V9.7.31）。

继承 DoubaoChat，复用其豆包 app 拉起 / PCM 配置 / RMS 音频检测基础设施，
只补齐拒识轮（静默型）的播放后时序，不改动稳定驱动的常规行为：

- 静默拒识轮（is_reject 且非打断型）：播放后先等 input_gap_ms 静音间隙，
  再用 AI PCM RMS 音频检测模型是否回复：连续 REJECT_SILENT_NO_REPLY_SECONDS
  秒无语音能量判「未回复」，置空问答并跳过问答提取直接收尾；检测到回复则等说完
  再收尾；拿不到 AI PCM 时降级 hw_params 播放流检测，任何情况下不回退 UI 判定。
- 其余轮（正常轮 / 打断型拒识轮）完全走 DoubaoChat.post_process 行为。

与上游 412037ea1 的适配点（本卡规格）：
- timing 判定复用 V9.7.31 词表（reject_timing.RejectTimingMixin：中文/英文等价、
  显式 is_interruption 优先），不照抄上游 `== 'response'`；上游的 timing 改值
  半不移植（V9.7.31 已由 INT-2363 白名单等价覆盖）。
- 时序常量取 driver_constants（REJECT_SILENT_NO_REPLY_SECONDS /
  REJECT_REPLY_WAIT_TIMEOUT / CHECK_STOP_POLL_INTERVAL），不硬编码。
- DoubaoChat._wait_ai_reply_end_via_pcm 覆写后无 silence_seconds 形参，阶段 B 读
  self.RMS_SILENCE_SECONDS：用子类类属性 RMS_SILENCE_SECONDS=0 实现「模型一静默
  即视为说完」，不改基类签名。
- 收尾段不复制：DoubaoChat.post_process 新增可选 reply_detected 形参传递判定结果
  （缺省 None 时行为与改动前完全一致）。
"""
import time

from .harmony_doubaochat import DoubaoChat
from .reject_timing import RejectTimingMixin
from .driver_types import DevicePlatform
from .registry import register_driver
from .driver_constants import (
    CHECK_STOP_POLL_INTERVAL,
    REJECT_REPLY_WAIT_TIMEOUT,
    REJECT_SILENT_NO_REPLY_SECONDS,
)


@register_driver
class DoubaoReject(RejectTimingMixin, DoubaoChat):
    """豆包通话拒识轮驱动 v1（仅静默拒识轮生效，其余轮次完全走基类行为）。"""

    # —— 驱动元数据（同源 V9.7.10 412037ea1）——
    app_type = "doubao_reject"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.doubao_reject.v1"
    display_name = "豆包通话拒识试验驱动"
    dependencies = ["hypium"]

    # 拒识轮「等说完」：覆盖 DoubaoChat 的 8s 静默确认，模型一静默即视为说完（缩短轮间 gap）。
    # 风险：句间停顿会被误判为「说完」；如需抗停顿改回更大值（与上游口径一致）。
    RMS_SILENCE_SECONDS = 0
    # hw_params 降级窗口内的轮询间隔（秒）；单测可压小
    REJECT_REPLY_POLL_INTERVAL = 1.0

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
        self.question_text = '豆包识别为空'
        self.answer_text = '豆包回复为空'
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
            # 已开始回复 → 等说完（DoubaoChat 覆写无 silence_seconds 形参，
            # 由子类类属性 RMS_SILENCE_SECONDS=0 让模型一静默即视为说完）
            ended = self._wait_ai_reply_end_via_pcm(
                device_sn, task_id=task_id, test_case_id=test_case_id)
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

        if is_interruption:
            # 打断型拒识轮不做静默检测，原样交回 DoubaoChat（显式 is_interruption
            # 由基类走 barge-in 门；不改写 kwargs 的轮次口径字段）。
            self._log(level='INFO',
                      content='拒识轮为打断型，不做静默检测，按豆包常规收尾进入下一轮',
                      task_id=task_id, test_case_id=test_case_id)
            return super().post_process(
                device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

        reply_detected = self._detect_silent_reject_reply(
            device_sn, kwargs, task_id=task_id, test_case_id=test_case_id)
        if reply_detected is None:
            self._log(level='INFO',
                      content='拒识轮等待被停止信号中断，本轮直接收敛',
                      task_id=task_id, test_case_id=test_case_id)
            return True
        super_kwargs = dict(kwargs)
        super_kwargs['reply_detected'] = reply_detected
        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **super_kwargs)
