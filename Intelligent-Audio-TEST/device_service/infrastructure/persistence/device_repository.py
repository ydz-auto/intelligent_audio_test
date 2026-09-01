# -*- coding: utf-8 -*-
"""设备配置仓储（聚合模块，P4-5 大文件拆分）。

原单文件 972 行，按职责拆分为 5 个内部模块，本文件保持
`from device_service.infrastructure.persistence.device_repository import ...`
的全部导入路径不变（DeviceRepository / PlaybackRepository / SPLRepository /
device_repository / playback_repository / spl_repository）：

- _device_converters.py：PO ↔ Entity 显式转换（各聚合根/实体）+ _now 时间工具
- _device_serializers.py：PO → dict 序列化（上层分页/序列化使用）
- _device_repository_impl.py：DeviceRepository 实现（被测设备）
- _playback_repository_impl.py：PlaybackRepository 实现（播放设备）
- _spl_repository_impl.py：SPLRepository 实现（SPL 映射 / 校准历史）

通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库，
向上层（application/commands/device_command_service、application/queries/device_query_service 等）
提供领域可读的接口。

P5+DOMAIN 改造：移除直接返回 PO 对象的 ORM 包装模式，改为 PO ↔ Entity 显式
转换。仓储方法返回 domain entities（DeviceAggregate / PlaybackDeviceAggregate /
SPLMappingEntity 等），而非 PO；上层不再感知 SQLAlchemy ORM。
"""
from device_service.domain.repositories import (
    DeviceRepositoryInterface,
    PlaybackRepositoryInterface,
    SPLRepositoryInterface,
)
from device_service.infrastructure.persistence._device_repository_impl import (
    DeviceRepository,
)
from device_service.infrastructure.persistence._playback_repository_impl import (
    PlaybackRepository,
)
from device_service.infrastructure.persistence._spl_repository_impl import (
    SPLRepository,
)

# 向后兼容：转换/序列化函数历史上定义在本模块，供潜在外部引用
from device_service.infrastructure.persistence._device_converters import (  # noqa: F401
    _now,
    _device_po_to_entity,
    _apply_device_entity_to_po,
    _device_tag_po_to_entity,
    _playback_po_to_entity,
    _apply_playback_entity_to_po,
    _spl_mapping_po_to_entity,
    _apply_spl_mapping_entity_to_po,
    _calibration_history_po_to_entity,
)
from device_service.infrastructure.persistence._device_serializers import (  # noqa: F401
    _device_to_dict,
    _playback_to_dict,
    _spl_mapping_to_dict,
)


# ========== 模块级单例（供 application 层依赖注入，避免直接实例化具体类） ==========
device_repository = DeviceRepository()
playback_repository = PlaybackRepository()
spl_repository = SPLRepository()
