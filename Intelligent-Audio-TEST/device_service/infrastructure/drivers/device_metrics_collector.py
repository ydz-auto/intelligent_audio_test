# -*- coding: utf-8 -*-
"""设备性能指标采集（INT-1578：健康检查 ``detail.metrics`` 的真实生产者）。

采集口径见《设备监控统计与播放设备控制接口契约》§1.3：

- Android：``dumpsys battery``（电量）、``/proc/meminfo``（内存使用率）、``top -n 1``（CPU 使用率）；
- HarmonyOS：``hdc -t <serial> shell hidumper`` 对应子系统；
- **采不到就不写该键**：返回 dict 只含真正采到的键，严禁写 0 或估算值；
- 单条命令超时 ≤ 5s（``METRICS_COMMAND_TIMEOUT``），任一指标失败只影响该指标，
  不向调用方抛异常——健康检查主流程与 ``is_online`` 判定不受影响。

监控线程与手动健康检查都经 ``DeviceCommandService.health_check`` 调用本模块，
采集逻辑单点实现。
"""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Dict, Optional

from shared.models.common_enums import DeviceSystem
from device_service.infrastructure.drivers.driver_constants import METRICS_COMMAND_TIMEOUT

logger = logging.getLogger(__name__)

# 指标键（与告警指标 AlarmMetricType 的口径一致）
METRIC_CPU = 'cpu'
METRIC_MEMORY = 'memory'
METRIC_BATTERY = 'battery'

# HarmonyOS 电量子系统（OpenHarmony SystemAbility 3302 = BatteryService）
_HARMONY_BATTERY_ABILITY_ID = '3302'

_SIZE_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)', re.IGNORECASE)
_SIZE_UNITS = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4}


def collect_device_metrics(system: str, serial_number: str) -> Dict[str, float]:
    """采集设备性能指标（cpu / memory / battery，百分比 0~100）。

    Args:
        system: 设备系统（Android / HarmonyOS；其它系统不采集）
        serial_number: 设备序列号（adb -s / hdc -t 的目标）

    Returns:
        只含成功采集到的键，例如 ``{'battery': 78.0, 'cpu': 12.5}``；
        全部采不到时返回空 dict（调用方据此不写 ``detail.metrics``）。
    """
    if not serial_number:
        return {}

    normalized_system = _normalize_system(system, serial_number)
    if normalized_system == DeviceSystem.ANDROID.value:
        probes = {
            METRIC_BATTERY: _android_battery,
            METRIC_MEMORY: _android_memory,
            METRIC_CPU: _android_cpu,
        }
    elif normalized_system == DeviceSystem.HARMONYOS.value:
        probes = {
            METRIC_BATTERY: _harmony_battery,
            METRIC_MEMORY: _harmony_memory,
            METRIC_CPU: _harmony_cpu,
        }
    else:
        return {}

    metrics: Dict[str, float] = {}
    for key, probe in probes.items():
        try:
            value = probe(serial_number)
        except Exception:
            # 单个指标异常只丢该指标，绝不影响健康检查
            logger.debug("采集设备指标失败 metric=%s device=%s", key, serial_number, exc_info=True)
            continue
        if value is not None:
            metrics[key] = value
    return metrics


def _normalize_system(system: str, serial_number: str) -> Optional[str]:
    """系统值归一（复用 INT-206 的 ``DeviceSystem.normalize`` 单一入口）。

    主库真实设备存在 'harmony' 等小写别名，驱动工厂按大小写不敏感匹配；
    采集器若用 ``== 'HarmonyOS'`` 精确比较会漏采，故统一走枚举归一。
    """
    try:
        return DeviceSystem.normalize(system).value
    except ValueError:
        logger.debug("设备系统不支持性能指标采集 system=%s device=%s", system, serial_number)
        return None


# ========== 命令执行 ==========

def _run_command(args) -> Optional[str]:
    """执行采集命令；失败/超时/非零退出返回 None（不抛异常）。"""
    try:
        result = subprocess.run(
            list(args), check=False, capture_output=True, text=True,
            timeout=METRICS_COMMAND_TIMEOUT,
        )
    except Exception:
        logger.debug("指标采集命令执行失败 args=%s", args, exc_info=True)
        return None
    if result.returncode != 0:
        logger.debug("指标采集命令非零退出 args=%s code=%s", args, result.returncode)
        return None
    return result.stdout or ''


def _clamp_percent(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)


# ========== Android ==========

def _android_battery(serial_number: str) -> Optional[float]:
    output = _run_command(['adb', '-s', serial_number, 'shell', 'dumpsys', 'battery'])
    return _parse_dumpsys_battery(output or '')


def _parse_dumpsys_battery(output: str) -> Optional[float]:
    """解析 ``dumpsys battery`` 的 ``level`` 与 ``scale``（缺 scale 按 100）。"""
    level = re.search(r'^\s*level:\s*(\d+)\s*$', output, re.MULTILINE | re.IGNORECASE)
    if not level:
        return None
    scale = re.search(r'^\s*scale:\s*(\d+)\s*$', output, re.MULTILINE | re.IGNORECASE)
    scale_value = int(scale.group(1)) if scale else 100
    if scale_value <= 0:
        return None
    return _clamp_percent(int(level.group(1)) * 100.0 / scale_value)


def _android_memory(serial_number: str) -> Optional[float]:
    output = _run_command(['adb', '-s', serial_number, 'shell', 'cat', '/proc/meminfo'])
    return _parse_proc_meminfo(output or '')


def _android_cpu(serial_number: str) -> Optional[float]:
    output = _run_command(['adb', '-s', serial_number, 'shell', 'top', '-n', '1', '-b'])
    return _parse_toybox_top_cpu(output or '')


def _parse_proc_meminfo(output: str) -> Optional[float]:
    """``/proc/meminfo`` → 内存使用率（有 MemAvailable 用可用值，否则退回 MemFree）。"""
    total = re.search(r'^MemTotal:\s*(\d+)\s*kB', output, re.MULTILINE)
    if not total:
        return None
    total_kb = int(total.group(1))
    if total_kb <= 0:
        return None
    available = re.search(r'^MemAvailable:\s*(\d+)\s*kB', output, re.MULTILINE)
    free = re.search(r'^MemFree:\s*(\d+)\s*kB', output, re.MULTILINE)
    if available:
        idle_kb = int(available.group(1))
    elif free:
        idle_kb = int(free.group(1))
    else:
        return None
    return _clamp_percent((total_kb - idle_kb) * 100.0 / total_kb)


def _parse_toybox_top_cpu(output: str) -> Optional[float]:
    """解析 toybox ``top -n 1 -b`` 的汇总行。

    汇总行形如 ``400%cpu  55%user   0%nice  31%sys 308%idle   2%iow ...``，
    前缀 ``400%cpu`` 是多核总和（等于各分项之和），分项求和后按 idle 占比推算使用率。
    """
    for line in output.splitlines():
        if '%cpu' not in line:
            continue
        pairs = re.findall(r'(\d+)%([a-z]+)', line)
        if not pairs:
            continue
        parts = {name: int(value) for value, name in pairs if name != 'cpu'}
        idle = parts.get('idle')
        total = sum(parts.values())
        if idle is None or total <= 0:
            continue
        return _clamp_percent((total - idle) * 100.0 / total)
    return None


# ========== HarmonyOS ==========

def _harmony_battery(serial_number: str) -> Optional[float]:
    output = _run_command([
        'hdc', '-t', serial_number, 'shell',
        'hidumper', '-s', _HARMONY_BATTERY_ABILITY_ID, '-a', '-i',
    ])
    return _parse_hidumper_battery(output or '')


def _parse_hidumper_battery(output: str) -> Optional[float]:
    """从 ``hidumper -s 3302`` 输出中取电量百分比（键名跨版本不固定，按语义匹配）。"""
    match = re.search(
        r'(?:capacity|battery\s*level|batteryLevel|电量)\s*[:：=]?\s*(\d{1,3})',
        output, re.IGNORECASE,
    )
    if not match:
        return None
    return _clamp_percent(int(match.group(1)))


def _harmony_memory(serial_number: str) -> Optional[float]:
    """HarmonyOS 内存使用率：优先 ``/proc/meminfo``（有总量/可用汇总）。

    ``hidumper --mem`` 是逐 PID 明细（无总量/可用汇总行，且输出常达百 KB、易触 5s 超时），
    取不到汇总值；真机实测 ``/proc/meminfo`` 返回 ``MemTotal`` / ``MemAvailable``。
    仅当 /proc/meminfo 命令成功但无汇总行时，才退回 hidumper 汇总口径。
    """
    output = _run_command(['hdc', '-t', serial_number, 'shell', 'cat', '/proc/meminfo'])
    if output is None:
        # 命令失败/超时：不再追加第二条慢命令，避免健康检查时长翻倍
        return None
    value = _parse_proc_meminfo(output)
    if value is not None:
        return value
    fallback = _run_command(['hdc', '-t', serial_number, 'shell', 'hidumper', '--mem'])
    return _parse_hidumper_memory(fallback or '')


def _parse_hidumper_memory(output: str) -> Optional[float]:
    """``hidumper --mem`` 汇总行取总内存与空闲/可用内存，换算为使用率。"""
    total = _find_memory_size(output, ('total memory', 'totalmemory', '总内存'))
    idle = _find_memory_size(
        output, ('free memory', 'available memory', 'availablememory', '可用内存'))
    if not total or idle is None:
        return None
    if total <= 0:
        return None
    return _clamp_percent((total - idle) * 100.0 / total)


def _find_memory_size(output: str, labels) -> Optional[float]:
    """按标签行取内存字节数（跨 KB/MB/GB 统一换算）。"""
    for line in output.splitlines():
        lowered = line.lower()
        if not any(label in lowered for label in labels):
            continue
        size = _SIZE_PATTERN.search(line)
        if not size:
            continue
        return float(size.group(1)) * _SIZE_UNITS[size.group(2).upper()]
    return None


def _harmony_cpu(serial_number: str) -> Optional[float]:
    output = _run_command(['hdc', '-t', serial_number, 'shell', 'hidumper', '--cpuusage'])
    return _parse_hidumper_cpu(output or '')


def _parse_hidumper_cpu(output: str) -> Optional[float]:
    """``hidumper --cpuusage`` 输出中取整体 CPU 使用率（百分比）。

    真机汇总行为 ``Total: 11.00%; User Space: 1.37%; ...; idle: 88.91%``：
    该行不含 "cpu" 字样，必须直接匹配 ``Total:``；无 Total 行时用 ``idle`` 反算。
    末段保留旧的「行内含 cpu 且带百分比」匹配，兼容早期 hidumper 版本。
    """
    total = re.search(r'^\s*Total:\s*(\d+(?:\.\d+)?)\s*%', output, re.MULTILINE)
    if total:
        return _clamp_percent(float(total.group(1)))

    idle = re.search(r'\bidle:\s*(\d+(?:\.\d+)?)\s*%', output, re.IGNORECASE)
    if idle:
        return _clamp_percent(100.0 - float(idle.group(1)))

    for line in output.splitlines():
        if 'cpu' not in line.lower():
            continue
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
        if match:
            return _clamp_percent(float(match.group(1)))
    return None
