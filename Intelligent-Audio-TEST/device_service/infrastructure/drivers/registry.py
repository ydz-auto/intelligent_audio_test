"""驱动注册表 — 装饰器注册 + 依赖检测 + 版本降级 resolve + 热更新。

核心入口:
    from .registry import register_driver, driver_registry, DriverRegistry

贡献者使用:
    @register_driver
    class MyDriver(AppDriver):
        app_type = AppType.MY_APP
        ...

调度器使用:
    driver_cls = driver_registry.resolve(AppType.PLAUD, AppVersion.V1, DevicePlatform.ANDROID)

热更新:
    driver_registry.reload_module('device_service.infrastructure.drivers.android_plaud')
    driver_registry.unregister(AppType.PLAUD, AppVersion.V1, DevicePlatform.ANDROID)
    driver_registry.register(NewDriverClass)
"""

import importlib
import importlib.util
import logging
import threading
from typing import Optional

from .driver_types import AppType, AppVersion, DevicePlatform, DriverStatus

logger = logging.getLogger(__name__)


class DriverNotFoundError(Exception):
    """请求的驱动不存在或依赖缺失"""

    def __init__(self, app_type, version, platform, reason: str = ""):
        self.app_type = app_type
        self.version = version
        self.platform = platform
        self.reason = reason
        super().__init__(
            f"Driver not found: app={app_type}, version={version}, platform={platform}"
            + (f" — {reason}" if reason else "")
        )


def _check_dependencies(dependencies: list[str]) -> tuple[bool, str]:
    """检测依赖包是否可用

    Returns:
        (is_available, missing_module_name)
    """
    for dep in dependencies:
        try:
            if importlib.util.find_spec(dep) is None:
                return False, dep
        except (ImportError, ValueError):
            return False, dep
    return True, ""


class DriverEntry:
    """注册表中单个驱动条目"""

    def __init__(self, driver_cls, status: DriverStatus, missing_dep: str = "",
                 module_name: str = ""):
        self.driver_cls = driver_cls
        self.app_type: AppType = driver_cls.app_type
        self.version: AppVersion = driver_cls.version
        self.platform: DevicePlatform = driver_cls.platform
        self.display_name: str = getattr(driver_cls, "display_name", driver_cls.__name__)
        self.dependencies: list[str] = getattr(driver_cls, "dependencies", [])
        self.status = status
        self.missing_dep = missing_dep
        # 记录来源模块，供 hot_reload 定位
        self.module_name = module_name or driver_cls.__module__

    @property
    def is_available(self) -> bool:
        return self.status == DriverStatus.AVAILABLE

    def to_dict(self) -> dict:
        """自描述信息（供管理界面/调试用）"""
        return {
            "app_type": self.app_type.value,
            "version": self.version.value,
            "platform": self.platform.value,
            "display_name": self.display_name,
            "status": self.status.value,
            "missing_dependency": self.missing_dep or None,
            "dependencies": self.dependencies,
            "module": self.module_name,
            "class": self.driver_cls.__name__,
        }


class DriverRegistry:
    """驱动注册表 — 调度器唯一依赖

    Key = (AppType, AppVersion, DevicePlatform) 三元组
    同一 key 只能注册一个驱动，后注册覆盖先注册（并告警）。
    线程安全：所有写操作加锁，读操作走快照。
    """

    def __init__(self):
        self._table: dict[tuple, DriverEntry] = {}
        self._lock = threading.RLock()

    # —— 注册 ——

    def register(self, driver_cls) -> type:
        """注册一个驱动类

        自动检测依赖，缺失时标记为 MISSING_DEPENDENCY 但仍注册（供 list_drivers 展示）。
        可作为装饰器使用。
        """
        self._validate_metadata(driver_cls)

        deps = getattr(driver_cls, "dependencies", [])
        is_ok, missing = _check_dependencies(deps)
        status = DriverStatus.AVAILABLE if is_ok else DriverStatus.MISSING_DEPENDENCY

        key = (driver_cls.app_type, driver_cls.version, driver_cls.platform)
        entry = DriverEntry(driver_cls, status, missing,
                            module_name=driver_cls.__module__)

        with self._lock:
            old = self._table.get(key)
            if old:
                logger.info(
                    "驱动覆盖: %s → %s (旧: %s)",
                    key, driver_cls.__name__, old.driver_cls.__name__
                )
            self._table[key] = entry

        return driver_cls

    def _validate_metadata(self, driver_cls):
        """校验类属性完整性"""
        required = ["app_type", "version", "platform"]
        for attr in required:
            val = getattr(driver_cls, attr, None)
            if val is None:
                raise TypeError(
                    f"{driver_cls.__name__} 缺少必需的类属性 '{attr}'，"
                    f"请声明 app_type / version / platform"
                )
            if not isinstance(val, (AppType, AppVersion, DevicePlatform)):
                raise TypeError(
                    f"{driver_cls.__name__}.{attr} 必须是 Enum 类型，"
                    f"而不是 {type(val).__name__}"
                )

    # —— 注销 ——

    def unregister(
        self, app_type: AppType, version: AppVersion, platform: DevicePlatform
    ) -> Optional[DriverEntry]:
        """从注册表移除一个驱动（热删）

        Returns:
            被移除的 DriverEntry；不存在时返回 None
        """
        key = (app_type, version, platform)
        with self._lock:
            entry = self._table.pop(key, None)
        if entry:
            logger.info("驱动注销: %s (%s)", key, entry.driver_cls.__name__)
        return entry

    def unregister_module(self, module_name: str) -> list[DriverEntry]:
        """移除指定模块注册的所有驱动（热删整个文件）

        Args:
            module_name: 模块全限定名

        Returns:
            被移除的条目列表
        """
        removed = []
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._table.items()
                if entry.module_name == module_name
            ]
            for key in keys_to_remove:
                removed.append(self._table.pop(key))
        if removed:
            logger.info("按模块注销 %d 个驱动: %s", len(removed), module_name)
        return removed

    # —— 热重载 ——

    def reload_module(self, module_name: str) -> list[DriverEntry]:
        """热重载一个驱动模块（热改）

        流程:
            1. 先注销该模块的旧驱动
            2. importlib.reload 重新加载模块
            3. 扫描 reload 后的模块中所有带 @register_driver 标记的类
               （reload 会自动触发装饰器重新注册）

        Returns:
            reload 后该模块注册的驱动条目列表
        """
        with self._lock:
            # 1. 先记录旧条目
            old_entries = self.unregister_module(module_name)

            # 2. reload 模块（装饰器会在 reload 过程中自动注册新类）
            try:
                mod = importlib.import_module(module_name)
                mod = importlib.reload(mod)
            except Exception as e:
                # reload 失败：恢复旧条目
                for entry in old_entries:
                    key = (entry.app_type, entry.version, entry.platform)
                    self._table[key] = entry
                logger.error("模块 %s reload 失败，已恢复旧驱动: %s", module_name, e)
                raise

            # 3. 收集 reload 后新注册的条目
            new_entries = [
                entry for entry in self._table.values()
                if entry.module_name == module_name
            ]

        logger.info(
            "模块 %s 热重载完成: 旧 %d 个 → 新 %d 个",
            module_name, len(old_entries), len(new_entries)
        )
        return new_entries

    # —— 查询（无锁，走 dict 快照）——

    def resolve(
        self,
        app_type: AppType,
        version: AppVersion,
        platform: DevicePlatform,
        *,
        fallback_v1: bool = True,
    ) -> type:
        """精确匹配 → 版本降级 → 抛 DriverNotFoundError

        Args:
            app_type: 应用类型
            version: 期望版本
            platform: 设备平台
            fallback_v1: 找不到精确版本时是否降级到 V1

        Returns:
            驱动类（type，未实例化）
        """
        # 1. 精确匹配
        key = (app_type, version, platform)
        entry = self._table.get(key)
        if entry and entry.is_available:
            return entry.driver_cls

        # 2. 类自身声明的 fallback
        if entry and not entry.is_available:
            raise DriverNotFoundError(app_type, version, platform,
                                      reason=f"依赖缺失: {entry.missing_dep}")

        # 3. 自动降级到 V1
        if fallback_v1 and version != AppVersion.V1:
            key_v1 = (app_type, AppVersion.V1, platform)
            entry_v1 = self._table.get(key_v1)
            if entry_v1 and entry_v1.is_available:
                return entry_v1.driver_cls

        # 4. 同 app_type + platform 下任意可用版本
        for (a, v, p), e in self._table.items():
            if a == app_type and p == platform and e.is_available:
                return e.driver_cls

        raise DriverNotFoundError(app_type, version, platform)

    def get_by_key(
        self, app_type: AppType, version: AppVersion, platform: DevicePlatform
    ) -> Optional[DriverEntry]:
        """精确查一个条目（不降级），返回原始 entry"""
        return self._table.get((app_type, version, platform))

    def list_drivers(self) -> list[dict]:
        """列出所有已注册驱动（供管理界面/调试）"""
        with self._lock:
            return [entry.to_dict() for entry in self._table.values()]

    def list_available(self, platform: Optional[DevicePlatform] = None) -> list[dict]:
        """列出可用驱动"""
        with self._lock:
            return [
                entry.to_dict()
                for entry in self._table.values()
                if entry.is_available
                and (platform is None or entry.platform == platform)
            ]

    def is_available(
        self, app_type: AppType, version: AppVersion, platform: DevicePlatform
    ) -> bool:
        """检查驱动是否可用"""
        entry = self._table.get((app_type, version, platform))
        return entry is not None and entry.is_available


# —— 模块级单例 ——

driver_registry = DriverRegistry()


def register_driver(driver_cls=None, *, registry: DriverRegistry = None):
    """装饰器：注册驱动到注册表

    用法:
        @register_driver
        class MyDriver(AppDriver): ...

        @register_driver(registry=custom_registry)
        class MyDriver(AppDriver): ...
    """
    reg = registry or driver_registry

    def _wrap(cls):
        return reg.register(cls)

    if driver_cls is not None:
        # 无参数装饰器: @register_driver
        return _wrap(driver_cls)
    # 带参数装饰器: @register_driver(registry=...)
    return _wrap
