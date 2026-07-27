# -*- coding: utf-8 -*-
"""
环境设备基类模块

定义所有环境设备（导轨、声压计、人工嘴等）的统一接口。
与 device_driver（被测设备驱动）平行，管理测试环境中的辅助设备。

核心生命周期：
    connect() → setup(settings) → ... 测试执行 ... → teardown(state) → disconnect()

状态管理模式：
    setup() 内部调用 save_state() 保存当前状态，再调用 apply_settings() 应用新设置，
    返回状态快照供 teardown() 恢复。确保每轮测试结束后设备环境还原。
"""

import logging

logger = logging.getLogger(__name__)


class BaseEnvDevice:
    """环境设备基类

    子类需覆盖的方法：
        - is_available(): 检查设备是否可用
        - connect() / disconnect(): 连接/断开设备
        - save_state(): 保存当前设备状态
        - apply_settings(settings): 应用新的设备设置
        - restore_state(state): 恢复到之前保存的状态

    子类可选覆盖的方法：
        - setup(settings): 自定义设置流程（默认 save_state + apply_settings）
        - teardown(state): 自定义恢复流程（默认 restore_state）
    """

    # 设备类型标识，子类必须覆盖（如 'rail', 'spl_meter', 'mouth'）
    device_type = 'generic'

    def __init__(self, config=None):
        """初始化环境设备

        Args:
            config: 设备配置字典，包含连接参数和设备特有参数。
                    常见字段：name, protocol, address, timeout 等。
        """
        self.config = config or {}
        self.name = self.config.get('name', self.device_type)
        self._connected = False

    def is_available(self):
        """检查设备是否可用（硬件已连接且就绪）

        Returns:
            bool: 设备是否可用
        """
        return False

    def connect(self):
        """连接设备

        Returns:
            bool: 是否连接成功
        """
        self._connected = True
        return True

    def disconnect(self):
        """断开设备连接"""
        self._connected = False

    def save_state(self):
        """保存当前设备状态，返回状态快照字典

        在 setup() 中自动调用，返回的快照将传给 teardown() 用于恢复。
        子类应覆盖此方法，返回需要恢复的状态信息。

        Returns:
            dict: 状态快照，格式由子类定义
        """
        return {}

    def apply_settings(self, settings):
        """应用设备设置

        在 setup() 中自动调用（save_state 之后）。
        子类应覆盖此方法，实现具体的设备控制逻辑。

        Args:
            settings: 设置参数字典，格式由子类定义
        """
        pass

    def restore_state(self, state):
        """恢复设备到之前保存的状态

        在 teardown() 中自动调用。
        子类应覆盖此方法，根据 save_state() 返回的快照恢复设备。

        Args:
            state: save_state() 返回的状态快照字典
        """
        pass

    def setup(self, settings):
        """一步完成设备设置：保存状态 + 应用设置

        典型用法：在每轮测试开始时调用，返回状态快照供 teardown 恢复。

        Args:
            settings: 设置参数字典

        Returns:
            dict: 保存的状态快照，传给 teardown() 使用
        """
        state = self.save_state()
        self.apply_settings(settings)
        return state

    def teardown(self, state):
        """一步完成设备恢复：恢复到 setup 前的状态

        典型用法：在每轮测试结束时调用，传入 setup() 返回的状态快照。

        Args:
            state: setup() 返回的状态快照字典
        """
        self.restore_state(state)
