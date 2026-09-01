from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver
from .utils import log_and_emit

# HarmonyDriver 的 scan() 仅依赖 hdc 命令，不需要 hypium，始终可用
from .harmony_driver import HarmonyDriver

# 注册表（新体系入口）
from .driver_types import AppType, AppVersion, DevicePlatform
from .registry import driver_registry

# 专用驱动依赖 hypium（华为内部测试框架，非 PyPI 包）
# hypium 不可时跳过这些专用驱动，不影响基础扫描功能
try:
    from .harmony_translation_driver import (
        XiaoyiFace2FaceDriver,
        XiaoyiSimultaneousInterpretationDriver
    )
    from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
    from .harmony_xiaoyichat import Xiaoyilivechat
    from .harmony_xiaoyilivechat import XiaoyilivechatV2
    from .harmony_asr_driver import HarmonyHardenXiaoyi_Input_MethodDriver
    _HYPium_AVAILABLE = True
except ImportError:
    XiaoyiFace2FaceDriver = None
    XiaoyiSimultaneousInterpretationDriver = None
    HarmonyHardenXiaoyiHuiJiDriver = None
    Xiaoyilivechat = None
    XiaoyilivechatV2 = None
    HarmonyHardenXiaoyi_Input_MethodDriver = None
    _HYPium_AVAILABLE = False


class DeviceDriverFactory:
    """设备驱动工厂

    兼容层：同时支持新体系（DriverRegistry + AppType/AppVersion/DevicePlatform）
    和旧体系（关键字匹配 keywords）。新调用方应优先使用 get_driver_typed()。
    """

    def __init__(self):
        # 尝试从配置加载mock模式设置
        try:
            from device_service.infrastructure.drivers.device_config import get_device_driver_config
            driver_config = get_device_driver_config()
            self._mock_mode = driver_config.get('mock_mode', False)
        except:
            self._mock_mode = False

        self._base_drivers = {
            'Android': AndroidDriver(),
            'HarmonyOS': HarmonyDriver(),
        }

        self._specialized_drivers = []
        self._task_device_map = {}  # task_id -> [device_sn, ...]

        # 设置所有基础驱动的模拟模式
        for driver in self._base_drivers.values():
            if hasattr(driver, 'set_mock_mode'):
                driver.set_mock_mode(self._mock_mode)

        self._register_defaults()

    def set_mock_mode(self, mock_mode: bool):
        """设置所有驱动的模拟模式
        
        Args:
            mock_mode: 是否启用模拟模式，启用后所有步骤返回True
        """
        self._mock_mode = mock_mode
        # 设置所有基础驱动的模拟模式
        for driver in self._base_drivers.values():
            if hasattr(driver, 'set_mock_mode'):
                driver.set_mock_mode(mock_mode)
        # 设置所有专用驱动的模拟模式
        for entry in self._specialized_drivers:
            driver = entry['driver']
            if hasattr(driver, 'set_mock_mode'):
                driver.set_mock_mode(mock_mode)

    def get_mock_mode(self) -> bool:
        """获取当前模拟模式状态
        
        Returns:
            bool: 当前是否处于模拟模式
        """
        return self._mock_mode

    def _register_defaults(self):
        """注册默认的专用驱动"""

        self.register_specialized_driver(
            PlaudDriver(),
            ['plaud', 'ai录音', 'ai record'],
            'Android',
            'Plaud AI 录音专用驱动'
        )

        # 鸿蒙专用驱动仅在 hypium 可用时注册
        if _HYPium_AVAILABLE:
            self.register_specialized_driver(
                XiaoyiFace2FaceDriver(),
                ['face2face', '面对面', 'face'],
                'HarmonyOS',
                '小艺面对面翻译专用驱动'
            )

            self.register_specialized_driver(
                XiaoyiSimultaneousInterpretationDriver(),
                ['simultaneous', '同传', 'interpretation'],
                'HarmonyOS',
                '小艺同传专用驱动'
            )

            self.register_specialized_driver(
                HarmonyHardenXiaoyiHuiJiDriver(),
                ['harden', 'huiji', '慧记'],
                'HarmonyOS',
                '鸿蒙harden小艺慧记专用驱动'
            )

            self.register_specialized_driver(
                Xiaoyilivechat(),
                ['xiaoyilivechat', '小艺通话', 'livechat'],
                'HarmonyOS',
                '小艺通话聊天专用驱动'
            )

            self.register_specialized_driver(
                HarmonyHardenXiaoyi_Input_MethodDriver(),
                ['input_method', '输入法', 'asr'],
                'HarmonyOS',
                '鸿蒙小艺输入法ASR专用驱动'
            )

        self.register_specialized_driver(
            DouBaoAndroidAsrDriver(),
            ['doubao', '豆包', 'asr'],
            'Android',
            '豆包Android语音识别专用驱动'
        )

    def register_specialized_driver(self, driver, keywords, system=None, name=None):
        """注册专用驱动"""
        # 设置新注册驱动的模拟模式
        if hasattr(driver, 'set_mock_mode'):
            driver.set_mock_mode(self._mock_mode)
        self._specialized_drivers.append({
            'driver': driver,
            'keywords': [k.lower() for k in keywords],
            'system': system.lower() if system else None,
            'original_keywords': keywords,
            'name': name or driver.__class__.__name__
        })

    def get_registered_keywords(self):
        """获取所有已注册的专用驱动关键字及其信息"""
        keywords_list = []
        for entry in self._specialized_drivers:
            keywords_list.append({
                'name': entry['name'],
                'keywords': entry['original_keywords'],
                'system': entry['system'].capitalize() if entry['system'] else 'All'
            })
        return keywords_list

    def get_driver_name_by_keywords(self, system, keywords):
        """根据系统和关键字获取驱动名称"""
        if not system or not keywords:
            return None
        
        system_lower = system.lower()
        keywords_lower = [k.lower() for k in keywords]
        
        for entry in self._specialized_drivers:
            if entry['system'] and entry['system'] != system_lower:
                continue
            
            # 所有关键字都必须匹配
            if all(kw in entry['keywords'] for kw in keywords_lower):
                return entry['name']
        
        return None

    def get_driver_by_system(self, system):
        """根据系统获取基础驱动"""
        if not system:
            return None
        system_lower = system.lower()
        for key, driver in self._base_drivers.items():
            key_lower = key.lower()
            if key_lower == system_lower or system_lower in key_lower or key_lower in system_lower:
                return driver
        return None

    def get_driver_by_sn(self, device_sn, task_id=None):
        """根据设备 SN 查找已注册的 driver 实例

        遍历所有基础驱动和专用驱动，返回持有该 device_sn 的 driver。
        """
        # 先从专用驱动找：仅当 device_sn 确实在该 driver._drivers 中时返回
        for entry in self._specialized_drivers:
            driver = entry['driver']
            if hasattr(driver, '_drivers') and device_sn in driver._drivers:
                return driver

        # 再从基础驱动找
        for key, driver in self._base_drivers.items():
            if hasattr(driver, '_drivers') and device_sn in driver._drivers:
                # 专用驱动继承基础驱动时会共用同一 _drivers dict（通过 super().__init__）
                # 检查是否有专用驱动与该基础 driver 共享 _drivers 实例
                for entry in self._specialized_drivers:
                    spec_driver = entry['driver']
                    if (hasattr(spec_driver, '_drivers')
                            and spec_driver._drivers is driver._drivers):
                        return spec_driver
                return driver

        # 如果设备已注册到 task_device_map，返回对应系统的基础 driver 作为兜底
        if task_id and task_id in self._task_device_map:
            if device_sn in self._task_device_map[task_id]:
                return self._base_drivers.get('HarmonyOS')
        return None

    # —— 新体系：基于注册表的类型化入口 ——

    # 旧关键字 → AppType 映射表（供 get_driver 内部降级使用）
    _KEYWORD_TO_APP_TYPE: dict[str, AppType] = {
        'plaud': AppType.PLAUD,
        'doubao': AppType.DOUBAO_ASR,
        'face2face': AppType.XIAOYI_FACE2FACE,
        'simultaneous': AppType.XIAOYI_SIMULTANEOUS,
        'huiji': AppType.XIAOYI_HUIJI,
        'livechat': AppType.XIAOYI_LIVECHAT,
        'input_method': AppType.XIAOYI_INPUT_METHOD,
    }

    _SYSTEM_TO_PLATFORM: dict[str, DevicePlatform] = {
        'android': DevicePlatform.ANDROID,
        'harmonyos': DevicePlatform.HARMONYOS,
        'ios': DevicePlatform.IOS,
    }

    def get_driver_typed(
        self,
        app_type: AppType,
        platform: DevicePlatform,
        version: AppVersion = AppVersion.V1,
    ):
        """新体系入口：通过 Enum 精确定位驱动实例

        优先走注册表 resolve（含版本降级 + 依赖检测），
        resolve 返回的是类，从 _specialized_drivers / _base_drivers 中取已实例化的单例。

        Args:
            app_type: 应用类型
            platform: 设备平台
            version: 应用版本（默认 V1）

        Returns:
            BaseDeviceDriver 实例（未命中注册表时返回 None）
        """
        try:
            driver_cls = driver_registry.resolve(app_type, version, platform)
        except Exception:
            return None

        # 从已实例化的驱动中查找匹配的类
        for entry in self._specialized_drivers:
            if isinstance(entry['driver'], driver_cls):
                return entry['driver']
        for driver in self._base_drivers.values():
            if isinstance(driver, driver_cls):
                return driver
        return None

    def list_registered_drivers(self) -> list[dict]:
        """列出注册表中所有驱动（代理给 DriverRegistry）"""
        return driver_registry.list_drivers()

    # —— 热更新：不停服增删改驱动 ——

    def unregister_driver(
        self, app_type: AppType, version: AppVersion, platform: DevicePlatform
    ) -> bool:
        """热删：从注册表和工厂实例列表中同时移除一个驱动

        已在执行中的用例持有旧实例引用，不受影响；
        新请求 resolve 将找不到该驱动。

        Returns:
            True 如果成功移除
        """
        entry = driver_registry.unregister(app_type, version, platform)
        if not entry:
            return False

        # 同步移除工厂持有的实例
        old_cls = entry.driver_cls
        self._specialized_drivers = [
            e for e in self._specialized_drivers
            if not isinstance(e['driver'], old_cls)
        ]
        # 基础驱动不从 _base_drivers 移除（平台基类不可删）
        return True

    def reload_driver_module(self, module_name: str) -> list[dict]:
        """热改：reload 一个驱动模块

        流程:
            1. driver_registry.reload_module 重载注册表
            2. 对该模块的每个驱动类，在工厂中重新实例化并替换旧实例
            3. 新实例继承 mock_mode 设置

        Returns:
            reload 后的驱动信息列表
        """
        new_entries = driver_registry.reload_module(module_name)

        # 在工厂中同步替换实例
        for entry in new_entries:
            new_cls = entry.driver_cls
            new_instance = new_cls()
            if hasattr(new_instance, 'set_mock_mode'):
                new_instance.set_mock_mode(self._mock_mode)

            # 先移除旧实例
            self._specialized_drivers = [
                e for e in self._specialized_drivers
                if not isinstance(e['driver'], new_cls)
            ]
            # 加入新实例（保留旧体系的关键字映射）
            old_entry = None
            for e in self._specialized_drivers:
                if isinstance(e['driver'], new_cls):
                    old_entry = e
                    break
            if old_entry:
                old_entry['driver'] = new_instance

        return [e.to_dict() for e in new_entries]

    def register_driver_class(self, driver_cls, keywords=None, system=None, name=None):
        """热增：动态注册一个驱动类到注册表和工厂

        Args:
            driver_cls: 驱动类（必须有 app_type/version/platform 元数据）
            keywords: 旧体系关键字（可选，默认从 app_type 生成）
            system: 旧体系系统名（可选，默认从 platform 生成）
            name: 显示名（可选，默认用 display_name）
        """
        # 注册到注册表
        driver_registry.register(driver_cls)

        # 注册到工厂实例列表
        instance = driver_cls()
        if hasattr(instance, 'set_mock_mode'):
            instance.set_mock_mode(self._mock_mode)

        # 旧体系兼容：自动生成关键字和系统名
        if keywords is None:
            keywords = [driver_cls.app_type.value]
        if system is None:
            system = driver_cls.platform.value
        if name is None:
            name = getattr(driver_cls, 'display_name', driver_cls.__name__)

        self.register_specialized_driver(instance, keywords, system, name)

    # —— 旧体系：关键字匹配（保持兼容）——

    def get_driver(self, system, keywords=None, device_sn=None):
        """获取驱动实例

        Args:
            system: 系统类型
            keywords: 关键字列表
            device_sn: 设备序列号

        Returns:
            BaseDeviceDriver: 驱动实例
        """
        # 首先尝试获取专用驱动
        if keywords:
            system_lower = system.lower() if system else ''
            if isinstance(keywords, str):
                keywords_lower = [k.strip().lower() for k in keywords.split(',') if k.strip()]
            else:
                keywords_lower = [k.lower() for k in keywords]
            
            for entry in self._specialized_drivers:
                if entry['system']:
                    if entry['system'] != system_lower and system_lower not in entry['system']:
                        continue
                
                # 所有关键字都必须匹配
                if all(kw in entry['keywords'] for kw in keywords_lower):
                    driver = entry['driver']
                    if device_sn and hasattr(driver, 'set_task_id'):
                        # 这里可以设置task_id，需要根据实际情况调整
                        pass
                    return driver
        
        # 如果没有找到专用驱动，返回基础驱动
        return self.get_driver_by_system(system)

    def get_all_drivers(self):
        """获取所有驱动"""
        drivers = list(self._base_drivers.values())
        for entry in self._specialized_drivers:
            drivers.append(entry['driver'])
        return drivers
    def register_task_devices(self, task_id, device_info_list):
        """记录任务使用的设备，用于停止时清理
        
        Args:
            task_id: 任务ID
            device_info_list: 设备信息列表 [{device_id, device_sn, device_name, driver, ...}, ...]
        """
        device_sns = []
        for info in device_info_list:
            device_sn = info.get("device_sn")
            if device_sn:
                device_sns.append(device_sn)

        if device_sns:
            self._task_device_map[task_id] = device_sns
            log_and_emit(level='DEBUG', module='DeviceDriverFactory',
                         content=f"Registered devices for task {task_id}: {device_sns}",
                         task_id=task_id)

    def cleanup_devices(self, task_id):
        """清理任务使用的设备驱动连接，并关闭 APP
        
        Args:
            task_id: 任务ID
        """
        if task_id not in self._task_device_map:
            return

        device_sns = self._task_device_map.pop(task_id)
        log_and_emit(level='INFO', module='DeviceDriverFactory',
                     content=f"Cleaning up devices for task {task_id}: {device_sns}",
                     task_id=task_id)

        for device_sn in device_sns:
            for driver_key, driver in self._base_drivers.items():
                if device_sn in driver._drivers:
                    conn = driver._drivers[device_sn]

                    try:
                        app_name = driver.app_name

                        if driver_key == 'Android' and hasattr(conn, 'app_stop'):
                            conn.app_stop(app_name)
                            log_and_emit(level='DEBUG', module='DeviceDriverFactory',
                                         content=f"Stopped Android app {app_name} on device {device_sn}",
                                         task_id=task_id)
                        elif driver_key == 'HarmonyOS':
                            import subprocess
                            subprocess.run(['hdc', '-t', device_sn, 'shell', 'aa', 'force-stop', app_name],
                                           check=False, timeout=5)
                            log_and_emit(level='DEBUG', module='DeviceDriverFactory',
                                         content=f"Stopped Harmony app {app_name} on device {device_sn}",
                                         task_id=task_id)
                    except Exception as e:
                        log_and_emit(level='WARNING', module='DeviceDriverFactory',
                                     content=f"Failed to stop app on device {device_sn}: {e}",
                                     task_id=task_id)

                    try:
                        if hasattr(conn, 'quit'):
                            conn.quit()
                        elif hasattr(conn, 'close'):
                            conn.close()
                        log_and_emit(level='DEBUG', module='DeviceDriverFactory',
                                     content=f"Closed connection for device {device_sn} ({driver_key})",
                                     task_id=task_id)
                    except Exception as e:
                        log_and_emit(level='WARNING', module='DeviceDriverFactory',
                                     content=f"Failed to close device {device_sn}: {e}",
                                     task_id=task_id)
                    finally:
                        if device_sn in driver._drivers:
                            del driver._drivers[device_sn]

                driver._current_task_id = None

        log_and_emit(level='INFO', module='DeviceDriverFactory',
                     content=f"Cleanup completed for task {task_id}",
                     task_id=task_id)

    def scan_devices(self):
        """扫描所有设备"""
        devices = []
        for driver in self._base_drivers.values():
            try:
                driver_devices = driver.scan()
                devices.extend(driver_devices)
            except Exception as e:
                print(f"Error scanning devices with {driver.__class__.__name__}: {e}")
        return devices


# 全局单例
driver_factory = DeviceDriverFactory()
