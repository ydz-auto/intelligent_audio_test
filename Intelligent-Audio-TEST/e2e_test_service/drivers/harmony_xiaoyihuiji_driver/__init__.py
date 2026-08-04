from ..harmony_driver import HarmonyDriver
from ._lock_mixin import LockMixin
from ._lifecycle_mixin import LifecycleMixin
from ._results_mixin import ResultsMixin
from ._constants import LOG_DEVICE_PATH

__all__ = ["HarmonyHardenXiaoyiHuiJiDriver", "LOG_DEVICE_PATH"]


class HarmonyHardenXiaoyiHuiJiDriver(LockMixin, LifecycleMixin, ResultsMixin, HarmonyDriver):
    """鸿蒙harden小艺慧记驱动"""
    pass
