# -*- coding: utf-8 -*-
"""
导轨环境设备模块

提供导轨控制器的默认实现和串口实现：
    - RailEnvDevice: 默认 no-op 实现（无硬件时使用）
    - SerialRailEnvDevice: 串口通信实现（连接真实导轨硬件）

导轨用于控制被测设备与声源之间的物理距离，是 E2E 测试中的重要环境设备。

配置示例（串口导轨）：
    {
        "device_type": "serial_rail",
        "name": "1号导轨",
        "port": "COM3",
        "baud_rate": 115200,
        "timeout": 5,
        "max_distance_cm": 200.0,
        "min_distance_cm": 10.0
    }
"""

import logging
import time
from device_service.domain.ports.env_device_port import BaseEnvDevice

logger = logging.getLogger(__name__)


class RailEnvDevice(BaseEnvDevice):
    """导轨环境设备 - 默认 no-op 实现

    无实际硬件连接时使用，所有操作仅打印 warning 日志。
    子类（如 SerialRailEnvDevice）可覆盖 move_to() 实现真实控制。
    """

    device_type = 'rail'

    def __init__(self, config=None):
        super().__init__(config)
        self._position = 0.0

    def is_available(self):
        """默认实现始终返回 False（无硬件）"""
        return False

    def save_state(self):
        """保存当前导轨位置"""
        return {'position': self.get_position()}

    def apply_settings(self, settings):
        """应用导轨设置

        Args:
            settings: 包含 distance_cm（目标距离，单位：厘米）
        """
        distance_cm = settings.get('distance_cm')
        if distance_cm is not None:
            self.move_to(float(distance_cm))

    def restore_state(self, state):
        """恢复导轨到之前保存的位置

        Args:
            state: save_state() 返回的状态快照，包含 position 字段
        """
        position = state.get('position')
        if position is not None:
            self.move_to(float(position))

    def move_to(self, distance_cm):
        """移动导轨到指定距离

        默认实现仅打印 warning。子类应覆盖此方法实现真实控制。

        Args:
            distance_cm: 目标距离（厘米）
        """
        logger.warning("导轨未配置，跳过移动到 %s cm", distance_cm)

    def get_position(self):
        """获取当前导轨位置

        Returns:
            float: 当前位置（厘米）
        """
        return self._position

    def reset(self):
        """复位导轨到初始位置（0cm）"""
        self.move_to(0.0)


class SerialRailEnvDevice(BaseEnvDevice):
    """导轨环境设备 - 串口通信实现

    通过串口（RS232/USB转串口）与导轨硬件通信。
    支持自定义指令格式，默认使用简单的文本协议：
        - 移动指令: "MOVE {distance_cm}\\r\\n"
        - 查询位置: "POS?\\r\\n"
        - 复位指令: "HOME\\r\\n"

    配置参数：
        port: 串口号（如 "COM3", "/dev/ttyUSB0"）
        baud_rate: 波特率（默认 115200）
        timeout: 串口超时时间（秒，默认 5）
        max_distance_cm: 最大移动距离（厘米，默认 200）
        min_distance_cm: 最小移动距离（厘米，默认 10）
        move_cmd_format: 移动指令格式（默认 "MOVE {distance}\\r\\n"）
        pos_cmd: 查询位置指令（默认 "POS?\\r\\n"）
        home_cmd: 复位指令（默认 "HOME\\r\\n"）
    """

    device_type = 'serial_rail'

    def __init__(self, config=None):
        super().__init__(config)
        self._serial = None
        self._position = 0.0
        self._port = self.config.get('port', '')
        self._baud_rate = self.config.get('baud_rate', 115200)
        self._timeout = self.config.get('timeout', 5)
        self._max_distance = self.config.get('max_distance_cm', 200.0)
        self._min_distance = self.config.get('min_distance_cm', 10.0)
        self._move_cmd_format = self.config.get('move_cmd_format', 'MOVE {distance}\r\n')
        self._pos_cmd = self.config.get('pos_cmd', 'POS?\r\n')
        self._home_cmd = self.config.get('home_cmd', 'HOME\r\n')

    def is_available(self):
        """检查串口是否已连接且可用"""
        return self._connected and self._serial is not None

    def connect(self):
        """连接串口导轨

        Returns:
            bool: 是否连接成功
        """
        if not self._port:
            logger.warning("导轨未配置串口端口（config.port），跳过连接")
            return False

        try:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                timeout=self._timeout
            )
            self._connected = True
            logger.info("导轨已连接: %s @ %d baud", self._port, self._baud_rate)
            return True
        except ImportError:
            logger.error("pyserial 未安装，无法使用串口导轨。请执行: pip install pyserial")
            return False
        except Exception as e:
            logger.error("导轨串口连接失败 (%s): %s", self._port, e)
            self._serial = None
            self._connected = False
            return False

    def disconnect(self):
        """断开串口连接"""
        if self._serial:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning("导轨串口关闭失败: %s", e)
            self._serial = None
        self._connected = False

    def save_state(self):
        """保存当前导轨位置"""
        return {'position': self.get_position()}

    def apply_settings(self, settings):
        """应用导轨设置

        Args:
            settings: 包含 distance_cm（目标距离，单位：厘米）
        """
        distance_cm = settings.get('distance_cm')
        if distance_cm is not None:
            self.move_to(float(distance_cm))

    def restore_state(self, state):
        """恢复导轨到之前保存的位置

        Args:
            state: save_state() 返回的状态快照，包含 position 字段
        """
        position = state.get('position')
        if position is not None:
            self.move_to(float(position))

    def move_to(self, distance_cm):
        """移动导轨到指定距离

        通过串口发送移动指令，并等待导轨到位确认。

        Args:
            distance_cm: 目标距离（厘米）

        Raises:
            RuntimeError: 串口未连接或移动失败
        """
        if not self.is_available():
            logger.warning("导轨未连接，跳过移动到 %s cm", distance_cm)
            return

        distance_cm = max(self._min_distance, min(self._max_distance, distance_cm))

        cmd = self._move_cmd_format.format(distance=distance_cm)
        try:
            self._serial.write(cmd.encode())
            self._serial.flush()
            time.sleep(0.5)
            self._position = distance_cm
            logger.info("导轨已移动到 %s cm", distance_cm)
        except Exception as e:
            logger.error("导轨移动失败: %s", e)

    def get_position(self):
        """查询当前导轨位置

        通过串口发送查询指令获取实时位置。
        如果查询失败，返回上次已知位置。

        Returns:
            float: 当前位置（厘米）
        """
        if not self.is_available():
            return self._position

        try:
            self._serial.write(self._pos_cmd.encode())
            self._serial.flush()
            response = self._serial.readline().decode().strip()
            if response:
                self._position = float(response)
        except Exception as e:
            logger.warning("导轨位置查询失败: %s，使用缓存值 %s cm", e, self._position)

        return self._position

    def reset(self):
        """复位导轨到初始位置

        发送 HOME 指令让导轨回到机械零点。
        """
        if not self.is_available():
            logger.warning("导轨未连接，跳过复位")
            return

        try:
            self._serial.write(self._home_cmd.encode())
            self._serial.flush()
            time.sleep(1.0)
            self._position = 0.0
            logger.info("导轨已复位")
        except Exception as e:
            logger.error("导轨复位失败: %s", e)
