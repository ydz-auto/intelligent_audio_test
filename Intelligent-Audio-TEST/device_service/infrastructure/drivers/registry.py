"""驱动注册表 — 装饰器注册 + 依赖检测 + 版本降级 resolve。

核心入口:
    from .registry import register_driver, driver_registry, DriverRegistry

贡献者使用:
    @register_driver
    class MyDriver(AppDriver):
        app_type = AppType.MY_APP
        ...

调度器使用:
    driver_cls = driver_registry.resolve(AppType.PLAUD, AppVersion.V1, DevicePlatform.ANDROID)
"""

import importlib.util
from typing import Optional, Union

from .driver_types import AppType, AppVersion, DevicePlatform, DriverStatus


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

    def __init__(self, driver_cls, status: DriverStatus, missing_dep: str = ""):
        self.driver_cls = driver_cls
        self.app_type: AppType = driver_cls.app_type
        self.version: AppVersion = driver_cls.version
        self.platform: DevicePlatform = driver_cls.platform
        self.display_name: str = getattr(driver_cls, "display_name", driver_cls.__name__)
        self.dependencies: list[str] = getattr(driver_cls, "dependencies", [])
        self.status = status
        self.missing_dep = missing_dep

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
        }


class DriverRegistry:
    """驱动注册表 — 调度器唯一依赖

    Key = (AppType, AppVersion, DevicePlatform) 三元组
    同一 key 只能注册一个驱动，后注册覆盖先注册（并告警）。
    """

    def __init__(self):
        self._table: dict[tuple, DriverEntry] = {}

    # —— 注册 ——

    def register(self, driver_cls) -> type:
        """注册一个驱动类

        自动检测依赖，缺失时标记为 MISSING_DEPENDENCY 但仍注册（供 list_drivers 展示）。
        可作为装饰器使用。
        """
        # 校验元数据
        self._validate_metadata(driver_cls)

        # 依赖检测
        deps = getattr(driver_cls, "dependencies", [])
        is_ok, missing = _check_dependencies(deps)
        status = DriverStatus.AVAILABLE if is_ok else DriverStatus.MISSING_DEPENDENCY

        key = (driver_cls.app_type, driver_cls.version, driver_cls.platform)
        entry = DriverEntry(driver_cls, status, missing)

        if key in self._table:
            old = self._table[key]
            # 静默覆盖（可能是 reload 场景）
            import logging
            logging.getLogger(__name__).warning(
                "Driver overwritten: %s → %s (was %s)",
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

    # —— 查询 ——

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
        return [entry.to_dict() for entry in self._table.values()]

    def list_available(self, platform: Optional[DevicePlatform] = None) -> list[dict]:
        """列出可用驱动"""
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
