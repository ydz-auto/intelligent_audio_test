"""应用驱动统一契约。

贡献者只需继承 AppDriver 并声明元数据，无需修改调度器代码。
旧驱动（继承 BaseDeviceDriver 的）保持兼容，通过适配器注册到新体系。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..driver_types import AppType, AppVersion, DevicePlatform


@dataclass
class DriverContext:
    """驱动运行时上下文 — 由调度器注入，驱动不自己 new 工厂/连设备

    Attributes:
        platform_ops: 平台原子能力对象（AndroidPlatform / HarmonyPlatform）
                      提供 unlock / close_popups / connect / scan / set_volume 等
        config: 驱动专属配置 dict（从 config_manager 读取）
        logger: 日志对象
        task_id: 任务 ID
        test_case_id: 用例 ID
        device_id: 设备数据库 ID
        mock_mode: 是否模拟模式
        extra: 扩展字段，向前兼容
    """
    platform_ops: Any = None
    config: dict = field(default_factory=dict)
    logger: Any = None
    task_id: Optional[str] = None
    test_case_id: Optional[str] = None
    device_id: Optional[int] = None
    mock_mode: bool = False
    extra: dict = field(default_factory=dict)


class AppDriver(ABC):
    """应用驱动策略接口 — 版本无关的统一契约

    贡献者实现步骤:
        1. 继承 AppDriver
        2. 声明类属性: app_type / version / platform / display_name
        3. 可选声明: dependencies / fallback_version
        4. 实现 initialize / get_results 等方法
        5. 加 @register_driver 装饰器（见 registry.py）

    示例:
        @register_driver
        class PlaudDriverV1(AppDriver):
            app_type = AppType.PLAUD
            version = AppVersion.V1
            platform = DevicePlatform.ANDROID
            display_name = "Plaud AI 录音 v1"

            def initialize(self, device_sn, **ctx):
                self.platform_ops.unlock(device_sn)
                ...
    """

    # —— 元数据：贡献者在类上声明 ——
    app_type: AppType
    version: AppVersion
    platform: DevicePlatform
    display_name: str = ""

    # 可选：依赖声明，缺失时注册表标记 unavailable
    dependencies: list[str] = []

    # 可选：版本降级目标，resolve 找不到本版本时尝试此版本
    fallback_version: Optional[AppVersion] = None

    def __init__(self, ctx: DriverContext):
        """接收调度器注入的上下文"""
        self.ctx = ctx
        self.platform_ops = ctx.platform_ops
        self.config = ctx.config
        self.logger = ctx.logger
        self._task_id = ctx.task_id
        self._test_case_id = ctx.test_case_id
        self._device_id = ctx.device_id
        self._mock_mode = ctx.mock_mode

    # —— 生命周期方法：子类按需覆写 ——

    @abstractmethod
    def initialize(self, device_sn: str, **kwargs) -> bool:
        """初始化设备（解锁、启动 App 等）"""
        ...

    def pre_process(self, device_sn: str, **kwargs) -> bool:
        """预处理（进入功能页面等）— 默认空实现"""
        return True

    @abstractmethod
    def get_results(self, device_sn: str, **kwargs) -> list[dict]:
        """获取设备输出结果"""
        ...

    def post_process(self, device_sn: str, **kwargs) -> bool:
        """后处理（清理等）— 默认空实现"""
        return True

    def teardown(self, device_sn: str, **kwargs) -> bool:
        """用例结束后清理 — 默认空实现"""
        return True

    # —— 可选能力：不支持的方法返回默认值 ——

    def is_locked(self, device_sn: str) -> bool:
        """检查设备是否锁屏 — 默认委托平台能力"""
        if self.platform_ops:
            return self.platform_ops.is_locked(device_sn)
        return False

    def set_volume(self, device_sn: str, level: int) -> bool:
        """设置设备音量 — 默认委托平台能力"""
        if self.platform_ops:
            return self.platform_ops.set_volume(device_sn, level)
        return True

    def get_volume(self, device_sn: str) -> int:
        """获取设备音量 — 默认委托平台能力"""
        if self.platform_ops:
            return self.platform_ops.get_volume(device_sn)
        return -1

    def scan(self) -> list[dict]:
        """扫描设备 — 默认委托平台能力"""
        if self.platform_ops:
            return self.platform_ops.scan()
        return []

    def extract_results_from_archive(self, **kwargs) -> list[dict]:
        """从存档文件提取结果 — 默认无"""
        return []

    def get_final_results(self, device_sn: str, **kwargs) -> list[dict]:
        """所有轮次完成后获取最终聚合结果 — 默认无"""
        return []

    # —— 工具方法 ——

    def _log(self, level: str = "INFO", content: str = "", **kwargs):
        """统一日志入口"""
        if self.logger:
            log_fn = getattr(self.logger, level.lower(), None) or self.logger.info
            log_fn(content)
