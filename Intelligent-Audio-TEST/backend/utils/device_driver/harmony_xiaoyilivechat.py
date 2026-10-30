# -*- coding: utf-8 -*-
"""小艺通话拒识轮驱动（试验实现）。

继承原 Xiaoyilivechat，避免直接改动稳定驱动。当前实现：
- timing=“回复过程中”映射 is_interruption=true；“静默”映射 false。
- is_reject=true 的轮次播放完成后等待 input_gap_ms。
- 下一轮是非拒识轮时检测 UI：说话可打断→AI 仍在回复；正在听…连续约 3s→回复结束。
- UI 等待 5s 兜底超时，超时后直接放行，避免连续拒识短音频卡死。

注意：executor 当前仍将轮参数传给 Xiaoyilivechat；如要启用本驱动，
需要在设备配置中选择本驱动并在 e2e_executor 中补充 next_round_is_reject 注入。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .utils import By, is_rpc_not_running_error
from .driver_types import DevicePlatform
from .registry import register_driver


@register_driver
class XiaoyiLivechatReject(Xiaoyilivechat):
    app_type = "xiaoyi_livechat_reject"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.xiaoyi_livechat_reject.v1"
    display_name = "小艺通话聊天拒识试验驱动"

    # “正在听…”连续出现时长，确认回复结束
    REJECT_LISTENING_CONFIRM_SECONDS = 3.0
    # 等目标 UI 的兜底超时，避免连续拒识轮卡死
    REJECT_UI_WAIT_TIMEOUT = 5.0

    @staticmethod
    def _normalize_timing_to_interruption(timing):
        """拒识参数 timing 与打断标记对齐：静默=false，回复过程中=true。"""
        return (timing or '').strip() == '回复过程中'

    def _wait_reject_reply_finished(self, driver, device_sn, task_id=None,
                                    test_case_id=None):
        """拒识轮后等待小艺回复结束。

        目标 UI: 说话可打断→AI 仍在回复；正在听…连续约 3s→回复结束。
        连续拒识轮+短音频可能错过“回复中”窗口，故总等待 5s 超时后直接放行。
        """
        deadline = time.time() + self.REJECT_UI_WAIT_TIMEOUT
        stable_listening_since = None
        while time.time() < deadline:
            if self._check_stop('post_process_拒识等待回复结束'):
                return False
            try:
                listening = driver.find_component(By.text('正在听…')) is not None
                replying = listening or (
                    driver.find_component(By.text('说话可打断')) is not None)
            except Exception as exc:
                if is_rpc_not_running_error(exc):
                    raise
                self._log(level='WARNING', content=f'拒识轮 UI 检测异常: {exc}',
                          task_id=task_id, test_case_id=test_case_id)
                return False

            now = time.time()
            if listening:
                if stable_listening_since is None:
                    stable_listening_since = now
                elif now - stable_listening_since >= self.REJECT_LISTENING_CONFIRM_SECONDS:
                    self._log(level='INFO',
                              content=f'拒识轮确认回复结束(“正在听…”稳定{now - stable_listening_since:.1f}s)',
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            else:
                stable_listening_since = None
            if replying:
                # 仍在回复：重置 UI 总兜底，只等待“正在听…”出现并稳定
                deadline = max(deadline,
                               now + self.REJECT_LISTENING_CONFIRM_SECONDS + 1)
            time.sleep(1)

        self._log(level='WARNING',
                  content='拒识轮等待回复结束超时(5s兜底)，直接进入下一轮',
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def post_process(self, device_sn, task_id=None, test_case_id=None,
                     **kwargs) -> bool:
        """在稳定驱动 post_process 前插入拒识轮等待逻辑。"""
        is_reject = self._as_bool(kwargs.get('is_reject'))
        if is_reject:
            driver = self._get_driver(device_sn)
            kwargs['is_interruption'] = self._normalize_timing_to_interruption(
                kwargs.get('timing'))
            self._post_process_reject_wait(
                driver, device_sn, kwargs, task_id=task_id,
                test_case_id=test_case_id)

        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

    def _post_process_reject_wait(self, driver, device_sn, kwargs,
                                  task_id=None, test_case_id=None):
        """拒识轮播放后等待 input_gap_ms，并按下一轮类型确认回复结束。"""
        is_reject = self._as_bool(kwargs.get('is_reject'))
        next_round_is_reject = self._as_bool(kwargs.get('next_round_is_reject'))
        if not is_reject:
            return

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
                content=(f'拒识轮播放完成，等待 input_gap_ms={input_gap_ms}ms '
                         f'(timing={timing_text}) 后检测回复状态'),
                task_id=task_id, test_case_id=test_case_id)
            wait_seconds = input_gap_ms / 1000.0
            wait_deadline = time.time() + wait_seconds
            while time.time() < wait_deadline:
                if self._check_stop(
                        f'post_process_拒识input_gap({input_gap_ms}ms)'):
                    return
                time.sleep(min(0.5, max(0.1, wait_deadline - time.time())))

        if not next_round_is_reject:
            self._wait_reject_reply_finished(
                driver, device_sn, task_id=task_id, test_case_id=test_case_id)

