# -*- coding: utf-8 -*-
"""命令对象 — 应用层用例输入，纯数据载体。"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CreateAPITestCommand:
    """创建（启动）API 测试会话命令

    与 APITestService.start_task 的签名对齐。
    """

    task_id: int
    case_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class StartAPITestCommand:
    """启动 API 测试命令（执行域 P0 分发通道，INT-71）

    task_service 逐用例领取后的分发经 StartAPITest 下发：case_ids 为
    精确用例集合，device_type/device_id 为调度侧路由决策随请求传递
    （空值时执行侧回退 TaskCase 行值，兼容不携带路由决策的调用方）。
    """

    task_id: int
    case_ids: List[int] = field(default_factory=list)
    device_type: str = ''
    device_id: str = ''


@dataclass(frozen=True)
class StopAPITestCommand:
    """停止 API 测试会话命令"""

    task_id: int


@dataclass(frozen=True)
class CreateAPICommand:
    """创建 API 配置命令

    通过 repository 创建 APIAggregate 聚合根。
    data 为 API 配置参数字典（name/meta/endpoints 等）。
    """

    data: Dict


@dataclass(frozen=True)
class UpdateAPICommand:
    """更新 API 配置命令

    通过 repository 更新指定 API 的字段。
    """

    api_id: int
    data: Dict


@dataclass(frozen=True)
class DeleteAPICommand:
    """删除 API 配置命令（软删除）

    通过 repository 软删除指定 API。
    """

    api_id: int


# ==================== UC-0902 API RMS→SPL 映射命令 ====================

@dataclass(frozen=True)
class CreateRmsSplMappingCommand:
    """创建被测 API RMS→SPL 映射命令

    data 为已按服务契约裁剪的参数字典（api_id/name/reference_spl/...）。
    """

    data: Dict


@dataclass(frozen=True)
class UpdateRmsSplMappingCommand:
    """更新被测 API RMS→SPL 映射命令"""

    mapping_id: int
    data: Dict


@dataclass(frozen=True)
class DeleteRmsSplMappingCommand:
    """删除（软删除）被测 API RMS→SPL 映射命令"""

    mapping_id: int


@dataclass(frozen=True)
class CalibrateRmsSplMappingCommand:
    """执行校准命令（UC-0902 步骤4）

    同一 API 的并发校准经分布式锁 lock:spl:calibration:{api_id} 互斥。
    calibration_data 为 {"points": [{target_spl, gain_linear, rms_dbfs}, ...]}。
    """

    mapping_id: int
    calibration_data: Dict


@dataclass(frozen=True)
class SetDefaultRmsSplMappingCommand:
    """设置 API 当前默认映射命令（apis.rms_spl_mapping_id，UC-0901 步骤7 / UC-0902 步骤6）

    mapping_id=None 表示清除默认映射（执行期回退最新映射 → 线性近似）。
    """

    api_id: int
    mapping_id: Optional[int]
