from ..harmony_driver import HarmonyDriver
from ..driver_types import AppType, AppVersion, DevicePlatform
from ..registry import register_driver
from ._lock_mixin import LockMixin
from ._lifecycle_mixin import LifecycleMixin
from ._results_mixin import ResultsMixin
from ._constants import LOG_DEVICE_PATH

__all__ = ["HarmonyHardenXiaoyiHuiJiDriver", "LOG_DEVICE_PATH"]


@register_driver
class HarmonyHardenXiaoyiHuiJiDriver(LockMixin, LifecycleMixin, ResultsMixin, HarmonyDriver):
    """鸿蒙harden小艺慧记驱动"""

    # —— 驱动元数据 ——
    app_type = AppType.XIAOYI_HUIJI
    version = AppVersion.V1
    platform = DevicePlatform.HARMONYOS
    display_name = "鸿蒙小艺慧记 v1"
    dependencies = ["hypium"]
