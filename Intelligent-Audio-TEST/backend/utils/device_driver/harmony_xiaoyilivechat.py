# -*- coding: utf-8 -*-
"""小艺通话拒识轮驱动（试验实现）。

继承原 Xiaoyilivechat，避免直接改动稳定驱动。当前实现：
- is_interruption 由 executor 按配置注入，本驱动不再用 timing 覆盖。
- 静默拒识轮（is_reject 且 timing=静默）：
  * 播放前不做额外等待（input_gap_ms 统一挂到播放后）。
  * 播放后先等 input_gap_ms 静音间隙，再用 AI PCM RMS 音频检测模型是否回复：
    连续 2s 无语音能量判定「未回复」直接收尾进下一轮，检测到回复则等说完再收尾。
  * 全程不依赖 find_component/UI 做拒识时序，避免 hypium 后端/RPC 断连时卡死。
- 不再依赖下一轮 timing（next_round_is_reject）。

注意：executor 当前仍将轮参数传给 Xiaoyilivechat；如要启用本驱动，
需要在设备配置中选择本驱动（app_type=xiaoyi_livechat_reject）。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .utils import By
from .driver_types import DevicePlatform
from .registry import register_driver


@register_driver
class XiaoyiLivechatReject(Xiaoyilivechat):
    app_type = "xiaoyi_livechat_reject"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.xiaoyi_livechat_reject.v1"
    display_name = "小艺通话聊天拒识试验驱动"

    # 静默拒识轮「播放后」检测模型回复（音频检测 AI PCM RMS，不依赖 UI/hw_params）：
    REJECT_SILENT_NO_REPLY_SECONDS = 2   # 连续 N 秒无语音能量判定「未回复」，直接收尾
    # 拒识轮「等回复完」：覆盖基类 8s 静默确认，模型一静默即视为说完（缩短 gap）。
    # 风险：句间停顿会被误判为「说完」；如需抗停顿改回更大值。
    RMS_SILENCE_SECONDS = 0

    @staticmethod
    def _normalize_timing_to_interruption(timing):
        """拒识参数 timing 与打断标记对齐：静默=false，回复过程中=true。"""
        return (timing or '').strip() == '回复过程中'

    def _wait_input_gap_after(self, device_sn, kwargs,
                              task_id=None, test_case_id=None):
        """静默拒识轮播放后先等 input_gap_ms 静音间隙。"""
        try:
            input_gap_ms = int(float(kwargs.get('input_gap_ms', 0) or 0))
        except (TypeError, ValueError):
            input_gap_ms = 0
            self._log(level='WARNING', content='拒识参数 input_gap_ms 无效，按 0 处理',
                      task_id=task_id, test_case_id=test_case_id)

        if input_gap_ms <= 0:
            return
        self._log(
            level='INFO',
            content=f'静默拒识轮播放后等待 input_gap_ms={input_gap_ms}ms',
            task_id=task_id, test_case_id=test_case_id)
        wait_seconds = input_gap_ms / 1000.0
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._check_stop(f'post_process_拒识input_gap({input_gap_ms}ms)'):
                return
            time.sleep(min(0.5, max(0.1, deadline - time.time())))

    def _wait_silent_reject_reply_start_hw_params(self, device_sn,
                                                  task_id=None, test_case_id=None):
        """RMS 找不到 AI PCM 时的 hw_params 兜底：检测模型是否开始回复。

        返回 True=正在回复（播放流 open）；False=超时内未回复（播放流 closed 或读不到）。
        """
        deadline = time.time() + self.REJECT_SILENT_NO_REPLY_SECONDS
        while time.time() < deadline:
            if self._check_stop('静默拒识_hw_params兜底等回复开始'):
                return False
            state = self._hw_params_replying(device_sn)
            if state is True:
                return True
            time.sleep(0.5)
        return False

    def _post_process_silent_reject(self, device_sn, kwargs,
                                    task_id=None, test_case_id=None):
        """静默拒识轮播放后处理：等 input_gap_ms → 音频检测模型回复。

        连续 REJECT_SILENT_NO_REPLY_SECONDS 秒无语音判定「未回复」直接收尾；
        检测到回复则等说完再收尾。收尾逻辑（停录屏/挂断/提取问答）与稳定驱动一致。
        """
        driver = self._get_driver(device_sn)
        # 1) 播放后先等 input_gap_ms
        self._wait_input_gap_after(device_sn, kwargs,
                                   task_id=task_id, test_case_id=test_case_id)
        # 2) 音频检测模型是否回复（AI PCM 尾部 RMS 主信号；remote 缺失降级 hw_params）
        status, remote = self._wait_ai_reply_start_via_pcm(
            device_sn, task_id=task_id, test_case_id=test_case_id,
            start_timeout=self.REJECT_SILENT_NO_REPLY_SECONDS)
        if status == 'none' and remote is None:
            # RMS 找不到 AI PCM（DSP hook 未起）→ 降级 hw_params 播放流检测兜底
            replied = self._wait_silent_reject_reply_start_hw_params(
                device_sn, task_id=task_id, test_case_id=test_case_id)
            if replied:
                self._wait_ai_reply_end_via_hw_params(
                    device_sn, task_id=task_id, test_case_id=test_case_id)
                self._log(level='INFO', content='静默拒识轮模型已回复(hw_params兜底)',
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self.question_text = '小艺识别为空'
                self.answer_text = '小艺回复为空'
                self._log(level='INFO',
                          content=(f'静默拒识轮未回复(hw_params兜底,'
                                   f'{self.REJECT_SILENT_NO_REPLY_SECONDS}s 内播放流未 open)，直接收尾'),
                          task_id=task_id, test_case_id=test_case_id)
        elif status == 'none':
            replied = False
            self.question_text = '小艺识别为空'
            self.answer_text = '小艺回复为空'
            self._log(level='INFO',
                      content=(f'静默拒识轮未回复({self.REJECT_SILENT_NO_REPLY_SECONDS}s 内 '
                               f'AI PCM 尾部无语音)，直接收尾进下一轮'),
                      task_id=task_id, test_case_id=test_case_id)
        else:
            replied = True
            if status == 'fresh':
                # 刚检测到回复开始 → 等说完
                self._wait_ai_reply_end_via_pcm(
                    device_sn, task_id=task_id, test_case_id=test_case_id)
            # status == 'ended' 表示回复已结束（起得晚），无需再等
            self._log(level='INFO', content='静默拒识轮模型已回复',
                      task_id=task_id, test_case_id=test_case_id)

        # 3) 收尾（与稳定驱动 post_process 一致）
        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        if record_mode == 'case':
            if is_last:
                if not self._stop_recorder(device_sn, task_id=task_id,
                                           test_case_id=test_case_id):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功",
                              task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(5)
        else:
            if not self._stop_recorder(device_sn, task_id=task_id,
                                       test_case_id=test_case_id):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功",
                          task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(5)
            try:
                hangup_btn = driver.find_component(
                    By.isAfter(By.key('live.tool_bar.hangup_button'))
                    .isBefore(By.key('GuideText')).type('SymbolGlyph'))
                if hangup_btn:
                    hangup_btn.click()
            except Exception as e:
                self._log(level='WARNING', content=f"挂断通话失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
            driver.wait(5)
        if not replied:
            return True

        # 提取问答文本
        question_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Row/Text'))
        if question_components:
            for i, comp in enumerate(question_components):
                self._log(level='DEBUG', content=f"question_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.question_text = question_components[-1].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Column//Stack/Text'))
        if answer_components:
            for i, comp in enumerate(answer_components):
                self._log(level='DEBUG', content=f"answer_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.answer_text = answer_components[-1].getText() if answer_components else None
        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None,
                    **kwargs) -> bool:
        """静默拒识轮播放前不做额外等待（input_gap_ms 统一挂到播放后）。"""
        return super().pre_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

    def post_process(self, device_sn, task_id=None, test_case_id=None,
                     **kwargs) -> bool:
        """静默拒识轮：播放后等 input_gap_ms → 音频检测回复；其余轮复用稳定驱动。"""
        is_reject = self._as_bool(kwargs.get('is_reject'))
        timing = kwargs.get('timing') or kwargs.get('trigger_timing') or ''
        is_silent = not self._normalize_timing_to_interruption(timing)
        if is_reject and is_silent:
            return self._post_process_silent_reject(
                device_sn, kwargs, task_id=task_id, test_case_id=test_case_id)
        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
