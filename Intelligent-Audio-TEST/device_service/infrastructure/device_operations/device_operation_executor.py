# -*- coding: utf-8 -*-
"""设备操作执行器（INT-80 设备操作端点底层能力）。

按设备系统（Android/iOS/HarmonyOS）构造系统命令并执行：
- Android:    adb -s {serial} ...
- HarmonyOS:  hdc -t {serial} ...
- iOS:        当前无命令行工具链，返回明确不支持
- mock 模式:  模拟成功（对齐既有驱动 mock 行为）

enum 化：操作与参数键一律走 DeviceOperation / 显式常量，拒绝魔法字符串散落。
"""
from __future__ import annotations

import logging
import subprocess
from typing import Optional

from shared.models.common_enums import DeviceOperation
from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)

# 单条命令执行超时（秒）
_COMMAND_TIMEOUT_SECONDS = 30


class DeviceOperationError(Exception):
    """设备操作失败（携带用户可读信息）"""


class DeviceOperationExecutor:
    """设备操作执行器：operation + 设备 → 命令执行/模拟"""

    def __init__(self, command_runner=None):
        # command_runner 可注入替换（测试用）；签名: (cmd_list, timeout) -> (returncode, output)
        self._command_runner = command_runner or self._default_run_command

    # ---------- 命令执行 ----------

    @staticmethod
    def _default_run_command(cmd: list, timeout: int = _COMMAND_TIMEOUT_SECONDS):
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        output = (result.stdout or '') + (result.stderr or '')
        return result.returncode, output.strip()

    def _run(self, cmd: list) -> str:
        try:
            returncode, output = self._command_runner(cmd)
        except FileNotFoundError as e:
            raise DeviceOperationError(f"命令工具不可用: {cmd[0]} ({e})") from e
        except subprocess.TimeoutExpired as e:
            raise DeviceOperationError(f"命令执行超时: {' '.join(cmd[:4])}") from e
        if returncode != 0:
            raise DeviceOperationError(f"命令执行失败 (code={returncode}): {output[:500]}")
        return output

    # ---------- 命令构造（按系统） ----------

    def _android_cmd(self, base, device, op: DeviceOperation, params: dict) -> list:
        serial = device.serial_number or device.ip
        if not serial:
            raise DeviceOperationError('设备缺少序列号/IP，无法构造 adb 命令')
        cmd = ['adb']
        if device.connection_type == 'remote' and device.ip:
            cmd += ['-s', device.ip]
        else:
            cmd += ['-s', serial]
        if op == DeviceOperation.CONNECT:
            if device.connection_type == 'remote' and device.ip:
                return ['adb', 'connect', device.ip]
            # USB 设备：唤醒屏幕即视为建立会话
            return cmd + ['shell', 'input', 'keyevent', 'KEYCODE_WAKEUP']
        if op == DeviceOperation.DISCONNECT:
            if device.connection_type == 'remote' and device.ip:
                return ['adb', 'disconnect', device.ip]
            raise DeviceOperationError('USB 连接的设备无法远程断开，请物理断开')
        if op == DeviceOperation.REBOOT:
            return cmd + ['shell', 'reboot']
        if op == DeviceOperation.SHUTDOWN:
            return cmd + ['shell', 'reboot', '-p']
        if op == DeviceOperation.INSTALL_APP:
            file_path = str(params.get('file_path') or '').strip()
            if not file_path:
                raise DeviceOperationError('install_app 需要 params.file_path（服务器侧 APK 路径）')
            return cmd + ['install', '-r', '-t', file_path]
        if op == DeviceOperation.UNINSTALL_APP:
            package = self._require_package(params)
            return cmd + ['uninstall', package]
        raise DeviceOperationError(f'Android 不支持的操作: {op.value}')

    def _harmony_cmd(self, device, op: DeviceOperation, params: dict) -> list:
        serial = device.serial_number or device.ip
        if not serial:
            raise DeviceOperationError('设备缺少序列号/IP，无法构造 hdc 命令')
        base = ['hdc', '-t', serial]
        if op == DeviceOperation.CONNECT:
            return base + ['shell', 'power-shell', 'wakeup']
        if op == DeviceOperation.DISCONNECT:
            raise DeviceOperationError('HarmonyOS 设备暂不支持远程断开，请物理断开')
        if op == DeviceOperation.REBOOT:
            return base + ['shell', 'reboot']
        if op == DeviceOperation.SHUTDOWN:
            raise DeviceOperationError('HarmonyOS 设备暂不支持远程关机')
        if op == DeviceOperation.INSTALL_APP:
            file_path = str(params.get('file_path') or '').strip()
            if not file_path:
                raise DeviceOperationError('install_app 需要 params.file_path（服务器侧 HAP 路径）')
            return ['hdc', '-t', serial, 'install', '-r', file_path]
        if op == DeviceOperation.UNINSTALL_APP:
            package = self._require_package(params)
            return base + ['shell', 'bm', 'uninstall', '-n', package]
        raise DeviceOperationError(f'HarmonyOS 不支持的操作: {op.value}')

    @staticmethod
    def _require_package(params: dict) -> str:
        package = str(params.get('package_name') or '').strip()
        if not package:
            raise DeviceOperationError('uninstall_app 需要 params.package_name（应用包名）')
        return package

    # ---------- 对外入口 ----------

    def execute(self, device, operation: str, params: Optional[dict] = None) -> dict:
        """执行设备操作。

        Args:
            device: DeviceAggregate（须含 system/serial_number/ip/connection_type）
            operation: DeviceOperation 枚举值字符串
            params: 操作参数（install_app: file_path；uninstall_app: package_name）

        Returns:
            {output, operation, mock}
        Raises:
            DeviceOperationError: 操作失败
        """
        from device_service.infrastructure.drivers.device_driver import device_driver_factory

        try:
            op = DeviceOperation(operation)
        except ValueError:
            raise DeviceOperationError(f'不支持的操作类型: {operation}')

        params = params or {}
        mock_mode = False
        try:
            mock_mode = device_driver_factory.get_mock_mode()
        except Exception:
            logger.debug("查询 mock 模式失败，按非 mock 处理", exc_info=True)

        if mock_mode:
            log_not_emit('INFO', 'DeviceOperation',
                         f"[MOCK] 设备操作模拟执行: device={device.id} op={op.value}",
                         category='device', source='backend')
            return {'output': f'[mock] {op.value} 执行成功', 'operation': op.value, 'mock': True}

        system = (device.system or '').lower()
        if 'android' in system:
            cmd = self._android_cmd(None, device, op, params)
        elif 'harmony' in system:
            cmd = self._harmony_cmd(device, op, params)
        elif 'ios' in system:
            raise DeviceOperationError('iOS 设备暂不支持远程操作（无命令行工具链）')
        else:
            raise DeviceOperationError(f'未知设备系统: {device.system}')

        output = self._run(cmd)
        return {'output': output[:2000], 'operation': op.value, 'mock': False}


device_operation_executor = DeviceOperationExecutor()
