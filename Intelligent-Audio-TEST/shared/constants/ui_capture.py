# -*- coding: utf-8 -*-
"""UI 抓取层显式降级枚举（INT-296）—— 模式 / 降级原因 / 步骤跳过口径的单一取值来源。

背景：验收基线（hypium 6.1.0.210）下，手机端 uitest 守护在本机环境不可用
（固件级自愈不能，已穷尽实测），小艺 UI 文本抓取层按环境排除项记入验收口径。
设备驱动 initialize 支持两种模式（device_service Config.UI_CAPTURE_MODE）：

- strict：UI 自动化层不可用 → initialize 显式失败（INT-158 语义，默认值）
- explicit_degrade：UI 层不可用 → initialize 成功并携带结构化降级标记
  （ui_capture_available=false + degrade_reason），e2e 侧将 UI 抓取步骤显式
  标记 skipped（环境排除）并留痕；采集/放音/录屏/回传/评估/报告链不受影响。

审计红线：任何隐式默认降级 = 缺陷——降级必须由配置显式开启，严禁无痕跳过。
"""
from enum import Enum


class UiCaptureMode(str, Enum):
    """UI 抓取层可用性模式（device_service Config.UI_CAPTURE_MODE 取值）"""

    STRICT = 'strict'
    EXPLICIT_DEGRADE = 'explicit_degrade'


UI_CAPTURE_MODE_VALUES = tuple(mode.value for mode in UiCaptureMode)


def normalize_ui_capture_mode(value) -> str:
    """校验并归一 UI_CAPTURE_MODE 取值，非法值抛 ValueError（启动即自曝，拒绝魔法字符串）。"""
    if isinstance(value, UiCaptureMode):
        return value.value
    if value not in UI_CAPTURE_MODE_VALUES:
        raise ValueError(
            f'UI_CAPTURE_MODE="{value}" 不是合法取值，允许：{" | ".join(UI_CAPTURE_MODE_VALUES)}')
    return value


class UiCaptureDegradeReason(str, Enum):
    """UI 抓取层降级原因（结构化透传到任务/轮次记录；取值可扩展）"""

    HYPIUM_MISSING = 'hypium_missing'                        # 运行环境无 hypium（UiDriver=None 短路）
    UITEST_DAEMON_UNAVAILABLE = 'uitest_daemon_unavailable'  # UiDriver RPC 建立失败（设备端 uitest 守护不可达）


class UiCaptureStepStatus(str, Enum):
    """UI 抓取步骤终态（写入轮次记录 round_data.ui_capture.status）"""

    SKIPPED = 'skipped'


class UiCaptureSkipReason(str, Enum):
    """UI 抓取步骤跳过原因"""

    ENVIRONMENT_EXCLUDED = 'environment_excluded'
