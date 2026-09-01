# -*- coding: utf-8 -*-
"""device_service gRPC servicer 实现（聚合导出模块，P4-4 大文件拆分）。

原单文件 949 行，已按职责拆分为 4 个内部模块，本文件保持
`from device_service.interfaces.grpc.servicers import ...` 的全部导入路径不变：

- device_runtime_servicers.py：设备驱动 / 结果采集 / 环境设备（运行时操作）
- device_config_servicers.py：设备配置 CRUD（CQRS：DeviceCommandService / DeviceQueryService）
- playback_config_servicers.py：播放设备配置 CRUD（CQRS）
- spl_config_servicers.py：SPL 映射配置 CRUD（CQRS）

约定：
- 复杂参数通过 JSON string 传递，方法内 _loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False

说明：proto 已拆分为 device_service_pb2。
"""

from device_service.interfaces.grpc.device_runtime_servicers import (
    DeviceServiceServicer,
    DeviceResultServiceServicer,
    EnvDeviceServiceServicer,
)
from device_service.interfaces.grpc.device_config_servicers import (
    DeviceConfigServiceServicer,
)
from device_service.interfaces.grpc.playback_config_servicers import (
    PlaybackConfigServiceServicer,
)
from device_service.interfaces.grpc.spl_config_servicers import (
    SPLConfigServiceServicer,
)

__all__ = [
    "DeviceServiceServicer",
    "DeviceResultServiceServicer",
    "EnvDeviceServiceServicer",
    "DeviceConfigServiceServicer",
    "PlaybackConfigServiceServicer",
    "SPLConfigServiceServicer",
]
