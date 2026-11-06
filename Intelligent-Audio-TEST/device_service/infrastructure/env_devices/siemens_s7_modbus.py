# -*- coding: utf-8 -*-
"""
西门子 S7 Modbus TCP 环境设备模块

针对西门子 S7-1200/S7-1500/S7-300/S7-400/S7-200 Smart PLC 的 Modbus TCP 通信。

西门子 S7 Modbus TCP 地址映射规则：
    Modbus 功能码    S7 数据区           Modbus 地址范围
    FC01/05/0F       Q 区（过程映像输出）  00001~49999   → 偏移 = 地址 - 1
    FC02             I 区（过程映像输入）  10001~19999   → 偏移 = 地址 - 10001
    FC03/06/10       DB 区/M 区           40001~49999   → 偏移 = 地址 - 40001
    FC04             模拟量输入           30001~39999   → 偏移 = 地址 - 30001

支持西门子地址格式：
    - 寄存器地址: 40001, 30001, 00001, 10001
    - PLC 地址: DB1.DBW0, DB1.DBD0, DB1.DBX0.0, M0.0, I0.0, Q0.0, V100

配置示例：
    {
        "device_type": "siemens_s7_modbus",
        "name": "1号PLC",
        "host": "192.168.1.100",
        "port": 502,
        "slave_id": 1,
        "timeout": 5,
        "register_map": {
            "volume":      {"address": "DB1.DBW0",   "data_type": "int16"},
            "temperature": {"address": "DB1.DBD2",   "data_type": "float32"},
            "power":       {"address": "Q0.0",        "type": "coil"},
            "status":      {"address": "I0.0",        "type": "discrete"},
            "pressure":    {"address": "MW10",        "data_type": "int16"}
        }
    }
"""

import logging
import re
import struct
from device_service.domain.ports.env_device_port import BaseEnvDevice

logger = logging.getLogger(__name__)


class SiemensS7ModbusEnvDevice(BaseEnvDevice):
    """西门子 S7 Modbus TCP 环境设备

    继承通用 Modbus TCP 通信能力，增加西门子 S7 地址格式解析。

    与通用 ModbusTcpEnvDevice 的区别：
        1. 支持西门子 PLC 地址格式（DB1.DBW0, M0.0, I0.0, Q0.0, V100）
        2. 自动处理 Modbus 5 位地址偏移（40001→0, 30001→0, 00001→0, 10001→0）
        3. 西门子保持寄存器按字访问，寄存器偏移自动换算
    """

    device_type = 'siemens_s7_modbus'

    # Modbus 地址基址
    _COIL_BASE = 1            # 0xxxx: Q 区
    _DISCRETE_BASE = 10001    # 1xxxx: I 区
    _INPUT_REG_BASE = 30001  # 3xxxx: 模拟量输入
    _HOLDING_REG_BASE = 40001  # 4xxxx: DB/M 区

    def __init__(self, config=None):
        super().__init__(config)
        self._client = None
        self._host = self.config.get('host', '127.0.0.1')
        self._port = self.config.get('port', 502)
        self._slave_id = self.config.get('slave_id', 1)
        self._timeout = self.config.get('timeout', 5)
        self._register_map = self.config.get('register_map', {})

    def is_available(self):
        return self._connected and self._client is not None

    def connect(self):
        """连接西门子 S7 PLC Modbus TCP"""
        try:
            from pymodbus.client import ModbusTcpClient
            self._client = ModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout
            )
            self._connected = self._client.connect()
            if self._connected:
                logger.info("西门子 S7 Modbus TCP 已连接: %s:%d (slave_id=%d)",
                            self._host, self._port, self._slave_id)
            else:
                logger.error("西门子 S7 Modbus TCP 连接失败: %s:%d", self._host, self._port)
                self._client = None
            return self._connected
        except ImportError:
            logger.error("pymodbus 未安装，请执行: pip install pymodbus")
            return False
        except Exception as e:
            logger.error("西门子 S7 Modbus TCP 连接异常 (%s:%d): %s", self._host, self._port, e)
            self._client = None
            self._connected = False
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning("西门子 S7 Modbus TCP 关闭失败: %s", e)
            self._client = None
        self._connected = False

    def save_state(self):
        state = {}
        for param_name in self._register_map:
            try:
                state[param_name] = self.read_param(param_name)
            except Exception as e:
                logger.warning("保存参数 %s 失败: %s", param_name, e)
        return state

    def apply_settings(self, settings):
        for param_name, value in (settings or {}).items():
            if param_name in self._register_map:
                try:
                    self.write_param(param_name, value)
                except Exception as e:
                    logger.error("设置参数 %s=%s 失败: %s", param_name, value, e)
            else:
                logger.warning("参数 %s 不在 register_map 中，跳过", param_name)

    def restore_state(self, state):
        for param_name, value in (state or {}).items():
            try:
                self.write_param(param_name, value)
            except Exception as e:
                logger.error("恢复参数 %s=%s 失败: %s", param_name, value, e)

    # ========== 西门子地址解析 ==========

    @classmethod
    def _parse_siemens_address(cls, address):
        """解析西门子 PLC 地址或 Modbus 标准地址

        支持的格式：
            - Modbus 标准地址: "40001", "30001", "00001", "10001"
            - 西门子 PLC 地址:
              DB1.DBW0  → DB 块保持寄存器, 偏移=0 (字)
              DB1.DBD0  → DB 块保持寄存器, 偏移=0 (双字)
              DB1.DBX0.0 → DB 块线圈, 偏移=0 (位)
              M0.0      → M 区线圈, 偏移=0 (位)
              MW0       → M 区保持寄存器, 偏移=0 (字)
              MD0       → M 区保持寄存器, 偏移=0 (双字)
              I0.0      → I 区离散输入, 偏移=0 (位)
              IW0       → I 区输入寄存器, 偏移=0 (字)
              Q0.0      → Q 区线圈, 偏移=0 (位)
              QW0       → Q 区线圈, 偏移=0 (字)
              V100      → V 区保持寄存器, 偏移=50 (字, 200Smart DB1)

        Returns:
            dict: {reg_type, offset, data_size}
            reg_type: 'holding', 'input', 'coil', 'discrete'
            offset: Modbus 寄存器/线圈偏移地址
            data_size: 该地址占用的寄存器/线圈数量
        """
        addr_str = str(address).strip().upper()

        # ---- Modbus 标准地址（纯数字） ----
        if re.match(r'^\d+$', addr_str):
            return cls._parse_modbus_address(int(addr_str))

        # ---- 西门子 PLC 地址 ----
        return cls._parse_plc_address(addr_str)

    @classmethod
    def _parse_modbus_address(cls, modbus_addr):
        """解析 Modbus 标准地址（5 位数字）

        00001~09999 → 线圈 (Q区)
        10001~19999 → 离散输入 (I区)
        30001~39999 → 输入寄存器 (模拟量输入)
        40001~49999 → 保持寄存器 (DB/M区)
        """
        if modbus_addr < 10000:
            return {'reg_type': 'coil', 'offset': modbus_addr - cls._COIL_BASE, 'data_size': 1}
        elif modbus_addr < 20000:
            return {'reg_type': 'discrete', 'offset': modbus_addr - cls._DISCRETE_BASE, 'data_size': 1}
        elif modbus_addr < 40000:
            return {'reg_type': 'input', 'offset': modbus_addr - cls._INPUT_REG_BASE, 'data_size': 1}
        elif modbus_addr < 50000:
            return {'reg_type': 'holding', 'offset': modbus_addr - cls._HOLDING_REG_BASE, 'data_size': 1}
        elif modbus_addr >= 400001:
            # 扩展地址 400001~465535
            return {'reg_type': 'holding', 'offset': modbus_addr - 400001, 'data_size': 1}
        else:
            raise ValueError(f"无效的 Modbus 地址: {modbus_addr}")

    @classmethod
    def _parse_plc_address(cls, addr_str):
        """解析西门子 PLC 地址格式"""

        # DB 块地址: DB1.DBW0, DB1.DBD0, DB1.DBX0.0
        # 也支持简写: D1.0.0
        db_match = re.match(
            r'^DB?(\d+)\.?DB?([XWD])(\d+)(?:\.(\d+))?$', addr_str
        )
        if db_match:
            db_num, type_char, byte_offset, bit_offset = db_match.groups()
            byte_offset = int(byte_offset)
            bit_offset = int(bit_offset) if bit_offset else 0
            # DB 块默认映射到保持寄存器（4xxxx 区）
            reg_offset = byte_offset // 2  # 字节偏移转寄存器偏移
            if type_char == 'X':
                # 位地址 → 线圈
                coil_offset = (byte_offset * 8) + bit_offset
                return {'reg_type': 'coil', 'offset': coil_offset, 'data_size': 1}
            elif type_char == 'W':
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 1}
            elif type_char == 'D':
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 2}

        # M 区: M0.0, MW0, MD0
        m_match = re.match(r'^M([XWD])?(\d+)(?:\.(\d+))?$', addr_str)
        if m_match:
            type_char, byte_offset, bit_offset = m_match.groups()
            type_char = type_char or 'X'
            byte_offset = int(byte_offset)
            bit_offset = int(bit_offset) if bit_offset else 0
            reg_offset = byte_offset // 2
            if type_char == 'X':
                coil_offset = (byte_offset * 8) + bit_offset
                return {'reg_type': 'coil', 'offset': coil_offset, 'data_size': 1}
            elif type_char == 'W':
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 1}
            elif type_char == 'D':
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 2}

        # I 区: I0.0, IW0
        i_match = re.match(r'^I([XWD])?(\d+)(?:\.(\d+))?$', addr_str)
        if i_match:
            type_char, byte_offset, bit_offset = i_match.groups()
            type_char = type_char or 'X'
            byte_offset = int(byte_offset)
            bit_offset = int(bit_offset) if bit_offset else 0
            if type_char == 'X':
                coil_offset = (byte_offset * 8) + bit_offset
                return {'reg_type': 'discrete', 'offset': coil_offset, 'data_size': 1}
            else:
                reg_offset = byte_offset // 2
                return {'reg_type': 'input', 'offset': reg_offset, 'data_size': 1}

        # Q 区: Q0.0, QW0
        q_match = re.match(r'^Q([XWD])?(\d+)(?:\.(\d+))?$', addr_str)
        if q_match:
            type_char, byte_offset, bit_offset = q_match.groups()
            type_char = type_char or 'X'
            byte_offset = int(byte_offset)
            bit_offset = int(bit_offset) if bit_offset else 0
            if type_char == 'X':
                coil_offset = (byte_offset * 8) + bit_offset
                return {'reg_type': 'coil', 'offset': coil_offset, 'data_size': 1}
            else:
                reg_offset = byte_offset // 2
                return {'reg_type': 'coil', 'offset': reg_offset, 'data_size': 1}

        # V 区 (S7-200 Smart): V100, VW100, VD100
        # V 区对应 DB1，V100 → DB1.DBB100, VW100 → DB1.DBW100
        v_match = re.match(r'^V([XWD])?(\d+)(?:\.(\d+))?$', addr_str)
        if v_match:
            type_char, byte_offset, bit_offset = v_match.groups()
            type_char = type_char or 'B'
            byte_offset = int(byte_offset)
            bit_offset = int(bit_offset) if bit_offset else 0
            reg_offset = byte_offset // 2
            if type_char == 'X':
                coil_offset = (byte_offset * 8) + bit_offset
                return {'reg_type': 'coil', 'offset': coil_offset, 'data_size': 1}
            elif type_char in ('B', 'W'):
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 1}
            elif type_char == 'D':
                return {'reg_type': 'holding', 'offset': reg_offset, 'data_size': 2}

        raise ValueError(f"无法解析西门子 PLC 地址: {addr_str}")

    # ========== 直接地址读写 ==========

    def read_holding_registers(self, address, count=1):
        """读取保持寄存器（FC03）

        Args:
            address: 寄存器偏移地址（西门子地址解析后的偏移）
            count: 读取数量
        """
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        result = self._client.read_holding_registers(
            address=address, count=count, slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取保持寄存器失败 (addr={address}, count={count}): {result}")
        return result.registers

    def write_holding_registers(self, address, values):
        """写保持寄存器（FC10）"""
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        if isinstance(values, (int, float)):
            values = [int(values)]
        result = self._client.write_registers(
            address=address, values=values, slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"写保持寄存器失败 (addr={address}, values={values}): {result}")

    def read_input_registers(self, address, count=1):
        """读取输入寄存器（FC04）"""
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        result = self._client.read_input_registers(
            address=address, count=count, slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取输入寄存器失败 (addr={address}, count={count}): {result}")
        return result.registers

    def read_coils(self, address, count=1):
        """读取线圈（FC01）"""
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        result = self._client.read_coils(
            address=address, count=count, slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取线圈失败 (addr={address}, count={count}): {result}")
        return result.bits

    def write_coil(self, address, value):
        """写单个线圈（FC05）"""
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        result = self._client.write_coil(
            address=address, value=bool(value), slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"写线圈失败 (addr={address}, value={value}): {result}")

    def read_discrete_inputs(self, address, count=1):
        """读取离散输入（FC02）"""
        if not self.is_available():
            raise RuntimeError("西门子 S7 Modbus TCP 未连接")
        result = self._client.read_discrete_inputs(
            address=address, count=count, slave=self._slave_id
        )
        if result.isError():
            raise RuntimeError(f"读取离散输入失败 (addr={address}, count={count}): {result}")
        return result.bits

    # ========== 参数名映射读写 ==========

    def read_param(self, param_name):
        """按参数名读取设备参数

        自动解析西门子地址格式，根据数据类型读取并解码。
        """
        mapping = self._register_map.get(param_name)
        if not mapping:
            raise KeyError(f"参数 '{param_name}' 不在 register_map 中")

        address = mapping['address']
        data_type = mapping.get('data_type', 'int16')
        explicit_type = mapping.get('type')

        parsed = self._parse_siemens_address(address)
        reg_type = explicit_type or parsed['reg_type']
        offset = parsed['offset']

        # 根据数据类型确定读取数量
        if reg_type in ('holding', 'input'):
            count = self._get_register_count(data_type, parsed['data_size'])
        else:
            count = 1

        if reg_type == 'holding':
            raw = self.read_holding_registers(offset, count)
        elif reg_type == 'input':
            raw = self.read_input_registers(offset, count)
        elif reg_type == 'coil':
            raw = self.read_coils(offset, count)
            return raw[0] if count == 1 else raw[:count]
        elif reg_type == 'discrete':
            raw = self.read_discrete_inputs(offset, count)
            return raw[0] if count == 1 else raw[:count]
        else:
            raise ValueError(f"不支持的寄存器类型: {reg_type}")

        return self._decode_registers(raw, data_type)

    def write_param(self, param_name, value):
        """按参数名写入设备参数

        自动解析西门子地址格式，根据数据类型编码并写入。
        """
        mapping = self._register_map.get(param_name)
        if not mapping:
            raise KeyError(f"参数 '{param_name}' 不在 register_map 中")

        address = mapping['address']
        data_type = mapping.get('data_type', 'int16')
        explicit_type = mapping.get('type')

        parsed = self._parse_siemens_address(address)
        reg_type = explicit_type or parsed['reg_type']
        offset = parsed['offset']

        if reg_type == 'coil':
            self.write_coil(offset, value)
            logger.info("已写入线圈 %s (%s) = %s", param_name, address, value)
            return

        if reg_type not in ('holding',):
            raise ValueError(f"参数 '{param_name}' 类型 {reg_type} 不支持写入")

        values = self._encode_value(value, data_type)
        self.write_holding_registers(offset, values)
        logger.info("已写入保持寄存器 %s (%s) = %s", param_name, address, value)

    # ========== 辅助方法 ==========

    @staticmethod
    def _get_register_count(data_type, default=1):
        """根据数据类型返回所需寄存器数量"""
        if data_type in ('int16', 'uint16'):
            return 1
        elif data_type in ('int32', 'uint32', 'float32'):
            return 2
        elif data_type == 'float64':
            return 4
        return default

    @staticmethod
    def _decode_registers(registers, data_type):
        """解码寄存器值

        支持类型: int16, uint16, int32, uint32, float32, float64
        注意: 西门子 PLC 使用大端序（Big-endian）
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
        """编码值为保持寄存器可写入的 16 位整数列表"""
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
