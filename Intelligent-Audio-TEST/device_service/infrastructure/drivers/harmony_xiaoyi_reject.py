# -*- coding: utf-8 -*-
"""小艺通话拒识轮驱动（V9.7.10 130d03ed1 移植，按 INT-2146 规格重写）。

继承 V9.7.31 的 Xiaoyilivechat（harmony_xiaoyichat.Xiaoyilivechat），只补齐拒识轮
执行能力，不改动稳定驱动的常规行为。与源实现的差异（INT-2146 规格裁定）：

- timing 词表白名单化（strip 后比较、英文小写归一）：response / 回复过程中 → 打断型；
  silence / 静默 / 空 → 非打断型；未知值记 WARNING 后按非打断型，不抛错。
  当轮显式配置了 is_interruption（非 None）时以用户值为准，只有缺省才由 timing 推导；
  任何情况下都不回写 kwargs['is_interruption']（该标记是打断族评估的轮次口径）。
- input_gap_ms 在 V9.7.31 无此参数（缺口 INT-2148），驱动一律按 0 处理，只记日志不等待。
- 回复结束判定以 hw_params 为主信号（连续 HW_PARAMS_CLOSED_CONFIRM=3 次 closed ≈3s），
  连续 3 次读不到才回退 UI 法（"正在听…" 连续 3 次确认）；总等待上限
  REJECT_REPLY_WAIT_TIMEOUT(5s)，超时记 WARNING 后放行。
  不复刻源的 UI 前置检测：拒识轮提示常驻时 find_component 恒命中，整轮会干等满 timeout。
- 拒识轮跳过基类「等回复开始 30s + 等回复结束 300s」两段长等待（base post_process
  的 skip_reply_wait 内部门控，缺省 False，其他驱动零影响）。

触发汇总：is_reject 显式 true 且非打断型 且下一轮非拒识轮 → 执行受限等待；
打断型或下一轮仍是拒识轮 → 不等待，直接进入下一轮。
"""
import time

from .harmony_xiaoyichat import Xiaoyilivechat
from .driver_types import DevicePlatform
from .registry import register_driver
from .utils import By, is_rpc_not_running_error
from .driver_constants import REJECT_REPLY_WAIT_TIMEOUT


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
    # 轮询间隔（秒）：hw_params 主信号与 UI 兜底共用；单测可压小
    REJECT_REPLY_POLL_INTERVAL = 1.0
    # UI 兜底法"正在听…"连续命中次数（interval 1s ≈ 3s，与源实现等价）
    REJECT_UI_CONFIRM_HITS = 3

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
    # 拒识轮受限等待
    # ------------------------------------------------------------------
    def _wait_reject_reply_end_limited(self, device_sn, task_id=None, test_case_id=None):
        """等拒识轮回复结束：hw_params 为主、UI 兜底，总等待上限 REJECT_REPLY_WAIT_TIMEOUT。

        Returns:
            True=判定结束/超时放行/无需再等；False=被停止信号打断。
        """
        deadline = time.time() + REJECT_REPLY_WAIT_TIMEOUT
        interval = self.REJECT_REPLY_POLL_INTERVAL
        closed_hits = read_fails = listening_hits = 0
        ui_driver = None
        while time.time() < deadline:
            if self._check_stop('post_process_拒识等待回复结束'):
                return False
            if ui_driver is None:
                state = self._hw_params_replying(device_sn)
                if state is True:
                    # 播放流打开且有参数内容 = 仍在回复
                    closed_hits = read_fails = 0
                elif state is False:
                    read_fails = 0
                    closed_hits += 1
                    if closed_hits >= self.HW_PARAMS_CLOSED_CONFIRM:
                        self._log(level='INFO',
                                  content=f'拒识轮确认回复结束(hw_params=closed,连续{closed_hits}次)',
                                  task_id=task_id, test_case_id=test_case_id)
                        return True
                else:
                    read_fails += 1
                    if read_fails >= self.HW_PARAMS_CLOSED_CONFIRM:
                        ui_driver = self._get_driver(device_sn)
                        if ui_driver is None or By is None:
                            self._log(level='WARNING',
                                      content=('拒识轮 hw_params 连续读取失败且 UI 抓取层不可用，'
                                               '无法判定回复结束，等待放行'),
                                      task_id=task_id, test_case_id=test_case_id)
                            return True
                        self._log(level='WARNING',
                                  content=(f'hw_params 连续读取失败({read_fails}次，'
                                           f'{self.HW_PARAMS_PATH})，回退UI法检测回复结束'),
                                  task_id=task_id, test_case_id=test_case_id)
            else:
                try:
                    listening = ui_driver.find_component(By.text('正在听…')) is not None
                except Exception as exc:  # noqa: BLE001
                    if is_rpc_not_running_error(exc):
                        raise
                    self._log(level='WARNING',
                              content=f'拒识轮 UI 检测异常，等待放行: {exc}',
                              task_id=task_id, test_case_id=test_case_id)
                    return True
                if listening:
                    listening_hits += 1
                    if listening_hits >= self.REJECT_UI_CONFIRM_HITS:
                        self._log(level='INFO',
                                  content=(f'拒识轮确认回复结束(UI法:"正在听…"连续'
                                           f'{listening_hits}次)'),
                                  task_id=task_id, test_case_id=test_case_id)
                        return True
                else:
                    listening_hits = 0
            time.sleep(interval)
        self._log(level='WARNING',
                  content=f'拒识轮等待回复结束超时({REJECT_REPLY_WAIT_TIMEOUT}s)，直接进入下一轮',
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def _log_input_gap(self, kwargs, task_id=None, test_case_id=None):
        """input_gap_ms 兜底：V9.7.31 无此参数（缺口 INT-2148），一律按 0 处理不等待。"""
        gap = kwargs.get('input_gap_ms')
        provided = gap not in (None, '', 0, '0')
        content = (f'拒识轮 input_gap_ms={gap} 在本版本无对应参数(已登记 INT-2148)，按 0 处理'
                   if provided else
                   '拒识轮 input_gap_ms 未提供(本版本无此参数，已登记 INT-2148)，按 0 处理')
        self._log(level='INFO', content=content,
                  task_id=task_id, test_case_id=test_case_id)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """拒识轮：受限等待后再走基类收尾；非拒识轮完全走原驱动行为。"""
        if not self._as_bool(kwargs.get('is_reject')):
            return super().post_process(
                device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

        is_interruption = self._effective_is_interruption(
            kwargs, task_id=task_id, test_case_id=test_case_id)
        next_round_is_reject = self._as_bool(kwargs.get('next_round_is_reject'))
        self._log(level='INFO',
                  content=(f"拒识轮：timing={kwargs.get('timing')!r} "
                           f"显式is_interruption={kwargs.get('is_interruption')!r} "
                           f"→ 按打断型={is_interruption}；"
                           f"下一轮拒识轮={next_round_is_reject}"),
                  task_id=task_id, test_case_id=test_case_id)
        self._log_input_gap(kwargs, task_id=task_id, test_case_id=test_case_id)

        if not is_interruption and not next_round_is_reject:
            if not self._wait_reject_reply_end_limited(
                    device_sn, task_id=task_id, test_case_id=test_case_id):
                return True  # 已收到停止信号，按既有语义收敛本轮
        else:
            self._log(level='INFO',
                      content='拒识轮不等待回复结束(打断型或下一轮仍为拒识轮)，直接进入下一轮',
                      task_id=task_id, test_case_id=test_case_id)

        # 拒识轮一律跳过基类「等回复开始 30s + 等回复结束 300s」两段长等待；
        # 不改写 kwargs（is_interruption 等轮次口径原样透传）。
        super_kwargs = dict(kwargs)
        super_kwargs['skip_reply_wait'] = True
        return super().post_process(
            device_sn, task_id=task_id, test_case_id=test_case_id, **super_kwargs)
