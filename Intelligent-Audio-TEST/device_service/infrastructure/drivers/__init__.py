"""设备驱动包统一入口。"""

from .utils import (
    register_task_events,
    get_task_events,
    unregister_task_events,
    check_stop,
)
from .base_driver import BaseDeviceDriver
from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver
from .driver_types import DevicePlatform, DriverStatus
from .registry import DriverRegistry, DriverNotFoundError, driver_registry, register_driver
from .contracts import AppDriver, DriverContext

# 非驱动的基础设施模块，不参与自动发现（避免导入期副作用与循环依赖）
_INFRA_MODULES = {
    'adb_track', 'base_driver', 'contracts', 'device_config',
    'device_metrics_collector', 'driver_constants', 'driver_factory',
    'driver_types', 'harmony_collection_mixin', 'registry', 'reject_timing',
    'utils',
}


def load_all_drivers():
    """自动发现并导入本包内全部驱动模块，完成 @register_driver 注册。

    新增驱动只要放进本包即可，无需再手工改 import（漏注册会导致驱动链断裂）。
    单个驱动缺少可选依赖（如 hypium 非 PyPI 包）时只跳过该模块，不影响其他
    驱动与基础扫描能力；已导入模块会被 importlib 缓存，不会重复执行注册。
    """
    import importlib
    import logging
    import pkgutil

    logger = logging.getLogger(__name__)
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith('_') or name in _INFRA_MODULES:
            continue
        module_name = f"{__name__}.{name}"
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            # 可选依赖缺失（典型：hypium）：该驱动不可用，跳过
            logger.debug("跳过驱动模块 %s（依赖缺失: %s）", module_name, exc)
        except Exception as exc:  # 单个驱动异常不应拖垮整个设备服务启动
            logger.warning("驱动模块 %s 导入失败，已跳过: %s", module_name, exc)


# 先完成全部驱动注册，driver_factory 再基于完整注册表构建默认驱动实例
load_all_drivers()

# 工厂依赖上面已完成的注册结果，必须放在自动发现之后导入
from .driver_factory import (  # noqa: E402
    DeviceDriverFactory,
    device_driver_factory,
    HarmonyDriver,
)

__all__ = [
    "register_task_events", "get_task_events", "unregister_task_events", "check_stop",
    "BaseDeviceDriver", "AndroidDriver", "PlaudDriver", "DouBaoAndroidAsrDriver",
    "HarmonyDriver", "DeviceDriverFactory",
    "device_driver_factory", "DevicePlatform", "DriverStatus",
    "DriverRegistry", "DriverNotFoundError", "driver_registry", "register_driver",
    "AppDriver", "DriverContext", "load_all_drivers",
]
