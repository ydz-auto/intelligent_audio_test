"""设备驱动包统一入口。

驱动按「平台 / 应用 / 版本」组织：
    drivers/android/<app>/<version>/
    drivers/harmony/<app>/<version>/
新增版本只需创建对应版本目录，无需改动本文件。
"""

from .utils import (
    register_task_events,
    get_task_events,
    unregister_task_events,
    check_stop,
)
from .base_driver import BaseDeviceDriver
from .android.base.v1 import AndroidDriver
from .android.plaud.v1 import PlaudDriver
from .android.doubao_asr.v1 import DouBaoAndroidAsrDriver
from .driver_types import DevicePlatform, DriverStatus
from .registry import DriverRegistry, DriverNotFoundError, driver_registry, register_driver
from .contracts import AppDriver, DriverContext

# 非驱动的基础设施/共享模块，不参与自动发现（避免导入期副作用与循环依赖）
_INFRA_MODULES = {
    'adb_track', 'base_driver', 'common', 'contracts', 'device_config',
    'device_metrics_collector', 'driver_constants', 'driver_factory',
    'driver_types', 'registry', 'utils',
}


def load_all_drivers():
    """递归发现并导入本包内全部驱动模块，完成 @register_driver 注册。

    新增驱动/版本只要放进本包（平台/应用/版本目录）即可，无需再手工改 import
    （漏注册会导致驱动链断裂）。单个驱动缺少可选依赖（如 hypium 非 PyPI 包）
    时只跳过该模块，不影响其他驱动与基础扫描能力；已导入模块会被 importlib
    缓存，不会重复执行注册。
    """
    import importlib
    import logging
    import pkgutil

    logger = logging.getLogger(__name__)

    def _walk(pkg_name, pkg_path):
        for module_info in pkgutil.iter_modules(pkg_path):
            name = module_info.name
            if name.startswith('_'):
                continue
            if pkg_name == __name__ and name in _INFRA_MODULES:
                continue
            module_name = f"{pkg_name}.{name}"
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                # 可选依赖缺失（典型：hypium）：该驱动不可用，跳过
                logger.debug("跳过驱动模块 %s（依赖缺失: %s）", module_name, exc)
                continue
            except Exception as exc:  # 单个驱动异常不应拖垮整个设备服务启动
                logger.warning("驱动模块 %s 导入失败，已跳过: %s", module_name, exc)
                continue
            if module_info.ispkg:
                _walk(module_name, module.__path__)

    _walk(__name__, __path__)


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
