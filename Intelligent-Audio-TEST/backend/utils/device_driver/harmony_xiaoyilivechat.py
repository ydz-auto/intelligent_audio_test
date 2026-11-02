# -*- coding: utf-8 -*-
"""小艺通话拒识轮驱动（试验实现）。

继承原 Xiaoyilivechat，避免直接改动稳定驱动。当前实现：
- is_interruption 由 executor 按配置注入，本驱动不再用 timing 覆盖。
- 静默拒识轮（is_reject 且 timing=静默）在播放前先按 input_gap_ms 静音，再等小艺
  上一句说完（hw_params 主 + AI PCM RMS 备，不依赖 find_component/UI）后播放。
- 等待 10s 兜底超时，超时后直接放行，避免连续拒识短音频卡死。
- 不再依赖下一轮 timing（next_round_is_reject）。

注意：executor 当前仍将轮参数传给 Xiaoyilivechat；如要启用本驱动，
需要在设备配置中选择本驱动（app_type=xiaoyi_livechat_reject）。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .driver_types import DevicePlatform
from .registry import register_driver


@register_driver
class XiaoyiLivechatReject(Xiaoyilivechat):
    app_type = "xiaoyi_livechat_reject"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.xiaoyi_livechat_reject.v1"
    display_name = "小艺通话聊天拒识试验驱动"

    # 静默拒识轮「等上一句回复结束」检测（不依赖 UI/RPC）：
    #   主：hw_params 播放流 closed=说完；备：AI PCM 尾部 RMS 静默。
    REJECT_REPLY_WAIT_TIMEOUT = 10.0       # 总兜底超时，避免连续拒识短音频卡死
    REJECT_REPLY_CLOSED_CONFIRM = 2        # hw_params 连续 N 次 closed 判定结束
    REJECT_REPLY_RMS_SILENCE_CONFIRM = 3   # RMS 备路：连续 N 秒尾部静默判定结束

    @staticmethod
    def _normalize_timing_to_interruption(timing):
        """拒识参数 timing 与打断标记对齐：静默=false，回复过程中=true。"""
        return (timing or '').strip() == '回复过程中'

    def _wait_reject_reply_finished(self, driver, device_sn, task_id=None,
                                    test_case_id=None):
        """静默拒识轮播放前等待小艺回复结束（不依赖 UI/RPC）。

        原 UI 法（find_component 说话可打断/正在听…）在设备 hypium 后端
        std::bad_alloc 或 RPC 断连时会卡死/误判，故改为：
          - 主：轮询 hw_params（播放流 closed=说完），连续 N 次 closed 判定结束。
          - 备：hw_params 连续读不到（路径漂移/无权限）时，改看 AI PCM 尾部 RMS，
                连续静默 N 秒判定结束。
          - 兜底：总等待超时后直接放行，避免连续拒识短音频卡死。
        """
        deadline = time.time() + self.REJECT_REPLY_WAIT_TIMEOUT
        closed_hits = hw_read_fails = rms_silent_hits = 0
        while time.time() < deadline:
            if self._check_stop('pre_process_拒识等待回复结束'):
                return False

            state = self._hw_params_replying(device_sn)
            if state is True:
                # 播放流仍打开 = 上一句还在说，继续等
                closed_hits = hw_read_fails = rms_silent_hits = 0
                time.sleep(1)
                continue
            if state is False:
                # closed = 上一句说完
                hw_read_fails = rms_silent_hits = 0
                closed_hits += 1
                if closed_hits >= self.REJECT_REPLY_CLOSED_CONFIRM:
                    self._log(level='INFO',
                              content=f'拒识轮确认回复结束(hw_params=closed,连续{closed_hits}次)',
                              task_id=task_id, test_case_id=test_case_id)
                    return True
                time.sleep(1)
                continue

            # state is None：hw_params 读不到 → 容忍几次后走 AI PCM RMS 备路
            hw_read_fails += 1
            if hw_read_fails <= 3:
                time.sleep(1)
                continue
            remote = self._find_ai_pcm_remote(device_sn, task_id=task_id,
                                              test_case_id=test_case_id)
            rms = None
            if remote:
                rms, _ = self._read_tail_rms(device_sn, remote, tail_seconds=1.0,
                                             task_id=task_id, test_case_id=test_case_id)
            if rms is None:
                time.sleep(1)
                continue
            if rms < self.RMS_THRESHOLD:
                rms_silent_hits += 1
                if rms_silent_hits >= self.REJECT_REPLY_RMS_SILENCE_CONFIRM:
                    self._log(level='INFO',
                              content=f'拒识轮确认回复结束(AI PCM 尾部静默{self.REJECT_REPLY_RMS_SILENCE_CONFIRM}s)',
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            else:
                rms_silent_hits = 0
            time.sleep(1)

        self._log(level='WARNING',
                  content=f'拒识轮等待回复结束超时({self.REJECT_REPLY_WAIT_TIMEOUT}s兜底)，直接进入本轮播放',
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None,
                    **kwargs) -> bool:
        """静默拒识轮在播放前先按 input_gap_ms 静音，再等小艺上一句说完后播放。"""
        is_reject = self._as_bool(kwargs.get('is_reject'))
        timing = kwargs.get('timing') or kwargs.get('trigger_timing') or ''
        is_silent = not self._normalize_timing_to_interruption(timing)
        if is_reject and is_silent:
            self._pre_process_reject_wait(
                self._get_driver(device_sn), device_sn, kwargs,
                task_id=task_id, test_case_id=test_case_id)

        return super().pre_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

    def _pre_process_reject_wait(self, driver, device_sn, kwargs,
                                 task_id=None, test_case_id=None):
        """静默拒识轮播放前：先等 input_gap_ms 静音间隙，再检测小艺是否结束回复。"""
        try:
            input_gap_ms = int(float(kwargs.get('input_gap_ms', 0) or 0))
        except (TypeError, ValueError):
            input_gap_ms = 0
            self._log(level='WARNING', content='拒识参数 input_gap_ms 无效，按 0 处理',
                      task_id=task_id, test_case_id=test_case_id)

        if input_gap_ms > 0:
            timing_text = kwargs.get('timing') or kwargs.get('trigger_timing') or ''
            self._log(
                level='INFO',
                content=(f'静默拒识轮播放前等待 input_gap_ms={input_gap_ms}ms '
                         f'(timing={timing_text})'),
                task_id=task_id, test_case_id=test_case_id)
            wait_seconds = input_gap_ms / 1000.0
            wait_deadline = time.time() + wait_seconds
            while time.time() < wait_deadline:
                if self._check_stop(
                        f'pre_process_拒识input_gap({input_gap_ms}ms)'):
                    return
                time.sleep(min(0.5, max(0.1, wait_deadline - time.time())))

        self._wait_reject_reply_finished(
            driver, device_sn, task_id=task_id, test_case_id=test_case_id)

    def post_process(self, device_sn, task_id=None, test_case_id=None,
                     **kwargs) -> bool:
        """拒识轮直接复用稳定驱动收尾，is_interruption 由 executor 按配置注入。"""
        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

