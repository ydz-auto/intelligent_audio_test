# -*- coding: utf-8 -*-
"""设备 UI 探索端口（INT-2492，方案 §6.6「UI 探索会话」）。

两类端口，均在 infrastructure 实现、application 只依赖抽象：

- ``DeviceLeasePort``：设备租用 / 锁定。实现复用平台既有的物理设备互斥
  （``RedisKeyPrefix.TASK_PHYSICAL_LOCK``，与任务派发同一把锁、按设备 SN 归一），
  因此「探索中的设备」和「跑任务的设备」互斥，不需要另建一套租约系统。
  **必须 fail-closed**：``acquire`` 返回 ``None``（被占用 / 不可租用）就拒绝探索。
  实现还应在租约句柄上带 ``lease_mode``（``DISTRIBUTED`` / ``SINGLE_INSTANCE``
  / ``DEGRADED``）与 ``degraded``：平台底层锁在 Redis 不可用时会降级放行，
  那种情况必须如实标注（``DEGRADED``）并写进工具结果 / 轨迹，不能看起来像
  「已锁定设备」。
- ``UiDevicePort``：从设备读取裁剪 UI 树 / 执行 UI 动作 / 取截图引用。
  平台格式差异（Android uiautomator XML / HarmonyOS hypium 组件）由实现层解析成
  共享节点结构（``shared.agent_tools.ui_exploration``），application 不碰原始格式。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence


class UiDeviceError(RuntimeError):
    """设备侧操作失败（不可用 / 平台不支持 / 元素不存在）。"""

    def __init__(self, message: str, *, code: str = 'DEVICE_UNAVAILABLE'):
        super().__init__(message)
        self.code = code


class DeviceLeasePort(ABC):
    """设备租用端口：成功返回可释放的租约句柄，失败返回 ``None``。"""

    @abstractmethod
    def acquire(self, device_id: int, *, holder: str
                ) -> Optional[Any]:
        """非阻塞抢占设备；被占用 / 不可租用返回 ``None``（fail-closed）。"""

    @abstractmethod
    def release(self, lease: Any) -> None:
        """释放租约（幂等；持有者崩溃时由租约 TTL 兜底）。"""


class UiDevicePort(ABC):
    """设备 UI 读取 / 动作端口（真实设备通道由设备服务提供）。"""

    @abstractmethod
    def platform(self, device_id: int) -> str:
        """设备平台（``ANDROID`` / ``HARMONYOS`` / ...）。"""

    @abstractmethod
    def dump_nodes(self, device_id: int, *, max_nodes: int
                   ) -> Dict[str, Any]:
        """读取一页 UI 树 → ``{'nodes': [...], 'coverage': {...}}``。

        实现负责把平台原始格式（XML / 组件列表）解析成共享节点结构；
        解析失败抛 ``UiDeviceError``（不返回空树冒充「页面没有元素」）。
        """

    @abstractmethod
    def perform(self, device_id: int, action_type: str, *,
                node: Optional[Dict[str, Any]] = None,
                params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行一个 ``UiActionType`` 动作（调用方已做审批 / 预算 / 安全校验）。"""

    def screenshot(self, device_id: int, *, label: str = ''
                   ) -> Optional[str]:
        """取截图引用（对象存储 URI）；平台不支持时返回 ``None``。"""
        return None

    def screenshot_refs(self, device_id: int) -> Sequence[str]:
        """本次会话已产生的截图引用（实现可覆盖；缺省空列表）。"""
        return ()


__all__ = ['DeviceLeasePort', 'UiDeviceError', 'UiDevicePort']
