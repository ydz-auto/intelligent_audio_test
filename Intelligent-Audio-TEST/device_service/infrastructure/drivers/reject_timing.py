# -*- coding: utf-8 -*-
"""拒识轮 timing 词表与打断型判定的共享口径（INT-2402）。

小艺（harmony_xiaoyi_reject.XiaoyiLivechatReject）与豆包
（harmony_doubaolivechat.DoubaoReject）两个拒识驱动共用本 mixin，
保证「一轮拒识音频算打断型还是静默型」只有一份词表与判定实现，
不产生第三份口径。

词表口径（INT-2363 定稿）：
- 打断型：response / 回复过程中；
- 非打断型：silence / 静默 / 空（含 None、纯空白）；
- 未知取值：记 WARNING 后按非打断型处理，不抛错。
"""


class RejectTimingMixin:
    """拒识轮 timing → 是否打断型（显式 is_interruption 优先）。"""

    # timing 词表（strip 后比较；英文小写归一）
    INTERRUPTION_TIMING_VALUES = ('response', '回复过程中')
    NON_INTERRUPTION_TIMING_VALUES = ('silence', '静默', '')

    def _resolve_timing_is_interruption(self, timing, task_id=None,
                                       test_case_id=None) -> bool:
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

    def _effective_is_interruption(self, kwargs, task_id=None,
                                   test_case_id=None) -> bool:
        """当轮等待策略用的打断型判定：显式 is_interruption 优先，缺省才由 timing 推导。

        只读不写——kwargs['is_interruption'] 是打断族评估的轮次口径，驱动不得改写。
        """
        raw = kwargs.get('is_interruption')
        if raw is not None:
            return self._as_bool(raw)
        return self._resolve_timing_is_interruption(
            kwargs.get('timing'), task_id=task_id, test_case_id=test_case_id)


__all__ = ['RejectTimingMixin']
