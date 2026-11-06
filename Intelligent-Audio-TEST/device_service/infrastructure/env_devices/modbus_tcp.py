# -*- coding: utf-8 -*-
"""
Modbus TCP 环境设备模块

通过 Modbus TCP 协议与环境设备通信，支持：
    - 保持寄存器读写（FC03 读 / FC06 写单 / FC10 写多）
    - 线圈读写（FC01 读 / FC05 写单 / FC0F 写多）
    - 输入寄存器读取（FC04）
    - 离散输入读取（FC02）

两种使用模式：
    1. 直接地址读写：通过 read_holding_registers / write_holding_registers 等方法直接操作地址
    2. 参数名映射：在配置中定义 register_map，通过业务参数名自动映射到地址

配置示例：
    {
        "device_type": "modbus_tcp",
        "name": "环境设备1号",
        "host": "192.168.1.100",
        "port": 502,
        "slave_id": 1,
        "timeout": 5,
        "register_map": {
            "volume":     {"address": 0,  "type": "holding",  "count": 1, "data_type": "int16"},
            "temperature": {"address": 10, "type": "input",    "count": 1, "data_type": "float32"},
            "power":      {"address": 20, "type": "coil",     "count": 1}
        }
    }
"""

import logging
import struct
from device_service.domain.ports.env_device_port import BaseEnvDevice

logger = logging.getLogger(__name__)


class ModbusTcpEnvDevice(BaseEnvDevice):
    """Modbus TCP 环境设备

    通过 pymodbus 库与支持 Modbus TCP 协议的设备通信。
    支持参数名映射表，实现业务参数与寄存器地址的解耦。
    """

    device_type = 'modbus_tcp'

    def __init__(self, config=None):
        super().__init__(config)
        self._client = None
        self._host = self.config.get('host', '127.0.0.1')
        self._port = self.config.get('port', 502)
        self._slave_id = self.config.get('slave_id', 1)
        self._timeout = self.config.get('timeout', 5)
        self._register_map = self.config.get('register_map', {})

    def is_available(self):
        """检查 Modbus TCP 连接是否可用"""
        return self._connected and self._client is not None

    def connect(self):
        """连接 Modbus TCP 设备

        Returns:
            bool: 是否连接成功
        """
        try:
            from pymodbus.client import ModbusTcpClient
            self._client = ModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout
            )
            self._connected = self._client.connect()
            if self._connected:
                logger.info("Modbus TCP 已连接: %s:%d (slave_id=%d)",
                            self._host, self._port, self._slave_id)
            else:
                logger.error("Modbus TCP 连接失败: %s:%d", self._host, self._port)
                self._client = None
            return self._connected
        except ImportError:
            logger.error("pymodbus 未安装，请执行: pip install pymodbus")
            return False
        except Exception as e:
            logger.error("Modbus TCP 连接异常 (%s:%d): %s", self._host, self._port, e)
            self._client = None
            self._connected = False
            return False

    def disconnect(self):
        """断开 Modbus TCP 连接"""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning("Modbus TCP 关闭失败: %s", e)
            self._client = None
        self._connected = False

    def save_state(self):
        """保存所有映射参数的当前值"""
        state = {}
        for param_name in self._register_map:
            try:
                state[param_name] = self.read_param(param_name)
            except Exception as e:
                logger.warning("保存参数 %s 失败: %s", param_name, e)
        return state

    def apply_settings(self, settings):
        """应用设备设置

        Args:
            settings: 参数名→值的字典，通过 register_map 自动映射到寄存器地址
        """
        for param_name, value in (settings or {}).items():
            if param_name in self._register_map:
                try:
                    self.write_param(param_name, value)
                except Exception as e:
                    logger.error("设置参数 %s=%s 失败: %s", param_name, value, e)
            else:
                logger.warning("参数 %s 不在 register_map 中，跳过", param_name)

    def restore_state(self, state):
        """恢复参数到之前保存的值"""
        for param_name, value in (state or {}).items():
            try:
                self.write_param(param_name, value)
            except Exception as e:
                logger.error("恢复参数 %s=%s 失败: %s", param_name, value, e)

    # ========== 直接地址读写（底层 Modbus 操作封装） ==========

    def read_holding_registers(self, address, count=1):
        """读取保持寄存器（FC03）

        Args:
            address: 起始寄存器地址
            count: 读取数量（1-125）

        Returns:
            list[int]: 寄存器值列表

        Raises:
            RuntimeError: 设备未连接或读取失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        result = self._client.read_holding_registers(
            address=address,
            count=count,
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取保持寄存器失败 (addr={address}, count={count}): {result}")
        return result.registers

    def write_holding_registers(self, address, values):
        """写保持寄存器（FC10 写多个，自动支持单个）

        Args:
            address: 起始寄存器地址
            values: 要写入的值列表

        Raises:
            RuntimeError: 设备未连接或写入失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        if isinstance(values, (int, float)):
            values = [int(values)]
        result = self._client.write_registers(
            address=address,
            values=values,
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"写保持寄存器失败 (addr={address}, values={values}): {result}")

    def read_input_registers(self, address, count=1):
        """读取输入寄存器（FC04）

        Args:
            address: 起始寄存器地址
            count: 读取数量（1-125）

        Returns:
            list[int]: 寄存器值列表

        Raises:
            RuntimeError: 设备未连接或读取失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        result = self._client.read_input_registers(
            address=address,
            count=count,
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取输入寄存器失败 (addr={address}, count={count}): {result}")
        return result.registers

    def read_coils(self, address, count=1):
        """读取线圈状态（FC01）

        Args:
            address: 起始线圈地址
            count: 读取数量（1-2000）

        Returns:
            list[bool]: 线圈状态列表

        Raises:
            RuntimeError: 设备未连接或读取失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        result = self._client.read_coils(
            address=address,
            count=count,
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取线圈失败 (addr={address}, count={count}): {result}")
        return result.bits

    def write_coil(self, address, value):
        """写单个线圈（FC05）

        Args:
            address: 线圈地址
            value: True/False

        Raises:
            RuntimeError: 设备未连接或写入失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        result = self._client.write_coil(
            address=address,
            value=bool(value),
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"写线圈失败 (addr={address}, value={value}): {result}")

    def read_discrete_inputs(self, address, count=1):
        """读取离散输入（FC02）

        Args:
            address: 起始地址
            count: 读取数量

        Returns:
            list[bool]: 离散输入状态列表

        Raises:
            RuntimeError: 设备未连接或读取失败
        """
        if not self.is_available():
            raise RuntimeError("Modbus TCP 未连接")
        result = self._client.read_discrete_inputs(
            address=address,
            count=count,
            slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取离散输入失败 (addr={address}, count={count}): {result}")
        return result.bits

    # ========== 参数名映射读写（业务功能封装） ==========

    def read_param(self, param_name):
        """按参数名读取设备参数

        通过 register_map 配置将参数名映射到寄存器地址，自动根据类型读取并解析。

        Args:
            param_name: 参数名（需在 register_map 中定义）

        Returns:
            解析后的参数值（int/float/bool）

        Raises:
            KeyError: 参数名未在 register_map 中定义
            RuntimeError: 读取失败
        """
        mapping = self._register_map.get(param_name)
        if not mapping:
            raise KeyError(f"参数 '{param_name}' 不在 register_map 中")

        addr = mapping['address']
        reg_type = mapping.get('type', 'holding')
        count = mapping.get('count', 1)
        data_type = mapping.get('data_type', 'int16')

        if reg_type == 'holding':
            raw = self.read_holding_registers(addr, count)
        elif reg_type == 'input':
            raw = self.read_input_registers(addr, count)
        elif reg_type == 'coil':
            raw = self.read_coils(addr, count)
            return raw[0] if count == 1 else raw[:count]
        elif reg_type == 'discrete':
            raw = self.read_discrete_inputs(addr, count)
            return raw[0] if count == 1 else raw[:count]
        else:
            raise ValueError(f"不支持的寄存器类型: {reg_type}")

        return self._decode_registers(raw, data_type)

    def write_param(self, param_name, value):
        """按参数名写入设备参数

        通过 register_map 配置将参数名映射到寄存器地址，自动根据类型编码并写入。

        Args:
            param_name: 参数名（需在 register_map 中定义）
            value: 要写入的值

        Raises:
            KeyError: 参数名未在 register_map 中定义
            RuntimeError: 写入失败
        """
        mapping = self._register_map.get(param_name)
        if not mapping:
            raise KeyError(f"参数 '{param_name}' 不在 register_map 中")

        addr = mapping['address']
        reg_type = mapping.get('type', 'holding')
        data_type = mapping.get('data_type', 'int16')

        if reg_type == 'coil':
            self.write_coil(addr, value)
            logger.info("已写入线圈 %s (%s) = %s", param_name, addr, value)
            return

        if reg_type != 'holding':
            raise ValueError(f"参数 '{param_name}' 类型 {reg_type} 不支持写入")

        values = self._encode_value(value, data_type)
        self.write_holding_registers(addr, values)
        logger.info("已写入保持寄存器 %s (addr=%s) = %s", param_name, addr, value)

    # ========== 数据编解码 ==========

    @staticmethod
    def _decode_registers(registers, data_type):
        """将寄存器原始值解码为指定数据类型

        支持的类型：int16, uint16, int32, uint32, float32, float64
        """
        if data_type in ('int16', 'uint16'):
            if not registers:
                return 0
            val = registers[0]
            if data_type == 'int16' and val > 32767:
                val -= 65536
            return val

        if data_type in ('int32', 'uint32'):
            if len(registers) < 2:
                return 0
            combined = (registers[0] << 16) | registers[1]
            if data_type == 'int32' and combined > 2147483647:
                combined -= 4294967296
            return combined

        if data_type == 'float32':
            if len(registers) < 2:
                return 0.0
            combined = (registers[0] << 16) | registers[1]
            return struct.unpack('>f', struct.pack('>I', combined))[0]

        if data_type == 'float64':
            if len(registers) < 4:
                return 0.0
            combined = (registers[0] << 48) | (registers[1] << 32) | \
                       (registers[2] << 16) | registers[3]
            return struct.unpack('>d', struct.pack('>Q', combined))[0]

        logger.warning("未知数据类型 %s，返回原始寄存器值", data_type)
        return registers

    @staticmethod
    def _encode_value(value, data_type):
        """将值编码为保持寄存器可写入的 16 位整数列表"""
        if data_type in ('int16', 'uint16'):
            val = int(value)
            if val < 0:
                val += 65536
            return [val]

        if data_type in ('int32', 'uint32'):
            val = int(value)
            if val < 0:
                val += 4294967296
            return [(val >> 16) & 0xFFFF, val & 0xFFFF]

        if data_type == 'float32':
            packed = struct.pack('>f', float(value))
            combined = struct.unpack('>I', packed)[0]
            return [(combined >> 16) & 0xFFFF, combined & 0xFFFF]

        if data_type == 'float64':
            packed = struct.pack('>d', float(value))
            combined = struct.unpack('>Q', packed)[0]
            return [
                (combined >> 48) & 0xFFFF,
                (combined >> 32) & 0xFFFF,
                (combined >> 16) & 0xFFFF,
                combined & 0xFFFF,
            ]

        logger.warning("未知数据类型 %s，直接转 int16", data_type)
        val = int(value)
        if val < 0:
            val += 65536
        return [val]
