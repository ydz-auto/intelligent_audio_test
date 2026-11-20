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


class UiActionType(str, Enum):
    """设备 UI 动作（卡面七种，接口值即枚举值；INT-2492 / INT-2569 唯一事实源）。

    定义在本模块而非 ``shared.agent_tools.ui_exploration``：设备服务的
    ``DeviceUiService`` 只做白名单校验，不应为取这七个值把 agent 工具注册表
    一起导进来（INT-2577）。agent 侧仍经 ``ui_exploration.UiActionType`` 引用。
    """

    TAP = 'TAP'
    LONG_PRESS = 'LONG_PRESS'
    SWIPE = 'SWIPE'
    INPUT_TEXT = 'INPUT_TEXT'
    BACK = 'BACK'
    HOME = 'HOME'
    WAIT = 'WAIT'

    @property
    def needs_target(self) -> bool:
        """需要元素定位的动作（其余是全局手势 / 系统动作）。"""
        return self in (UiActionType.TAP, UiActionType.LONG_PRESS,
                        UiActionType.INPUT_TEXT)


UI_ACTION_TYPE_VALUES = tuple(action.value for action in UiActionType)


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
    # —— INT-2577 设备 UI 探索通道（servicer 透传到响应 data.degrade_reason）——
    PLATFORM_NOT_SUPPORTED = 'platform_not_supported'        # 驱动未覆写该能力 / 平台不在支持范围
    DRIVER_UNAVAILABLE = 'driver_unavailable'                # 设备连接不可用（adb/hdc 断连、驱动建链失败）
    TREE_UNREADABLE = 'tree_unreadable'                      # 取到树但结构不可解析（不返回空树冒充成功）
    SCREENSHOT_UNAVAILABLE = 'screenshot_unavailable'        # 截图失败（编码 / 落盘 / 设备侧取屏异常）


class UiCaptureErrorCode(str, Enum):
    """设备 UI RPC / 网关端点的显式业务码（INT-2569「错误码」，INT-2578 按此映射 HTTP）。

    响应信封的 ``code`` 字段取本枚举值，调用方按 ``code`` 判型，**不得靠 message 字符串**。
    """

    DEVICE_NOT_FOUND = 'DEVICE_NOT_FOUND'
    PLATFORM_UNSUPPORTED = 'PLATFORM_UNSUPPORTED'
    UI_CAPTURE_UNAVAILABLE = 'UI_CAPTURE_UNAVAILABLE'
    TREE_TOO_LARGE = 'TREE_TOO_LARGE'
    ELEMENT_NOT_FOUND = 'ELEMENT_NOT_FOUND'
    ACTION_NOT_ALLOWED = 'ACTION_NOT_ALLOWED'
    BUSY = 'BUSY'


class UiCaptureUnavailable(RuntimeError):
    """UI 抓取能力不可用 —— 显式失败异常（INT-2577）。

    驱动层默认三个能力方法（读树 / 动作 / 截图）一律抛本异常，平台驱动按平台覆写；
    调用方（``DeviceUiService``）据此返回 ``UI_CAPTURE_UNAVAILABLE`` /
    ``PLATFORM_UNSUPPORTED`` 并带上结构化 ``degrade_reason``。
    **永不返回空树 / 空结果冒充成功**（审计红线，同 INT-296）。
    """

    def __init__(self, message, *, reason: 'UiCaptureDegradeReason' = None):
        super().__init__(message)
        self.reason = (reason.value if isinstance(reason, UiCaptureDegradeReason)
                       else reason)
        #: 显式业务码（UiCaptureErrorCode 值）；None 表示由调用方按 reason 归类
        self.code = None


class UiElementNotFound(UiCaptureUnavailable):
    """目标元素定位不到（``code`` = ``ELEMENT_NOT_FOUND``，不静默成功）。"""

    def __init__(self, message):
        super().__init__(message, reason=UiCaptureDegradeReason.DRIVER_UNAVAILABLE)
        self.code = UiCaptureErrorCode.ELEMENT_NOT_FOUND.value


class UiActionNotAllowed(UiCaptureUnavailable):
    """动作 / 参数不在白名单（``code`` = ``ACTION_NOT_ALLOWED``）。"""

    def __init__(self, message):
        super().__init__(message, reason=UiCaptureDegradeReason.PLATFORM_NOT_SUPPORTED)
        self.code = UiCaptureErrorCode.ACTION_NOT_ALLOWED.value


class UiCapturePlatform(str, Enum):
    """``DumpUiTree.data.platform`` 取值（响应口径，与落库 DeviceSystem 值区分）"""

    ANDROID = 'ANDROID'
    HARMONYOS = 'HARMONYOS'


class UiTreeFormat(str, Enum):
    """``DumpUiTree.data.format`` 取值 —— 平台原始结构格式（解析在 agent 侧）"""

    ANDROID_XML = 'ANDROID_XML'
    HARMONY_COMPONENTS = 'HARMONY_COMPONENTS'


#: 单次读树 payload 上限（8 MB，INT-2569 D7）：超限返回 TREE_TOO_LARGE，
#: 不截断冒充完整树（裁剪只在 agent 侧 crop_nodes 生效）。
UI_TREE_PAYLOAD_MAX_BYTES = 8 * 1024 * 1024

#: 动作下发结构化日志标签（验收卡 INT-2580 的 dry_run 计数口径：
#: device_service 每下发一个动作写一行，dry_run 下条数 = 0）。
DEVICE_UI_ACTION_LOG_TAG = 'device.ui.action'


class UiCaptureStepStatus(str, Enum):
    """UI 抓取步骤终态（写入轮次记录 round_data.ui_capture.status）"""

    SKIPPED = 'skipped'


class UiCaptureSkipReason(str, Enum):
    """UI 抓取步骤跳过原因"""

    ENVIRONMENT_EXCLUDED = 'environment_excluded'
