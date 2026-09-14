from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver
from .utils import log_and_emit
from .driver_types import AppType, AppVersion, DevicePlatform
from .registry import driver_registry

_LEGACY_KEYWORDS = {
    AppType.PLAUD: ['plaud', 'ai录音', 'ai record'],
    AppType.XIAOYI_FACE2FACE: ['face2face', '面对面', 'face'],
    AppType.XIAOYI_SIMULTANEOUS: ['simultaneous', '同传', 'interpretation'],
    AppType.XIAOYI_HUIJI: ['harden', 'huiji', '慧记'],
    AppType.XIAOYI_LIVECHAT: ['xiaoyilivechat', '小艺通话', 'livechat'],
    AppType.CHATGPT: ['chatgpt', 'chatgptvoice', 'chatgpt语音'],
    AppType.DOUBAO: ['doubao', '豆包', 'doubaochat', '豆包通话'],
    AppType.XIAOYI_INPUT_METHOD: ['input_method', '输入法', 'asr'],
    AppType.DOUBAO_ASR: ['doubao', '豆包', 'asr'],
}

# 鸿蒙驱动依赖 hypium（华为内部测试框架，非 PyPI 包）
# hypium 不可时跳过这些驱动，不影响其他功能
try:
    from .harmony_driver import HarmonyDriver
    from .harmony_translation_driver import (
        XiaoyiFace2FaceDriver,
        XiaoyiSimultaneousInterpretationDriver
    )
    from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
    from .harmony_xiaoyichat import Xiaoyilivechat
    from .harmony_chatgpt import ChatGptVoiceChat
    from .harmony_doubaochat import DoubaoChat
    from .harmony_asr_driver import HarmonyHardenXiaoyi_Input_MethodDriver
    _HYPium_AVAILABLE = True
except ImportError:
    HarmonyDriver = None
    XiaoyiFace2FaceDriver = None
    XiaoyiSimultaneousInterpretationDriver = None
    HarmonyHardenXiaoyiHuiJiDriver = None
    Xiaoyilivechat = None
    XiaoyilivechatV2 = None
    ChatGptVoiceChat = None
    DoubaoChat = None
    HarmonyHardenXiaoyi_Input_MethodDriver = None
    _HYPium_AVAILABLE = False


class DeviceDriverFactory:
    """设备驱动工厂"""

    def __init__(self):
        # 尝试从配置加载mock模式设置
        try:
            from device_config import get_device_driver_config
            driver_config = get_device_driver_config()
            self._mock_mode = driver_config.get('mock_mode', False)
        except:
            self._mock_mode = False

        self._base_drivers = {
            'Android': AndroidDriver(),
        }
        # 鸿蒙基础驱动仅在 hypium 可用时注册
        if _HYPium_AVAILABLE and HarmonyDriver is not None:
            self._base_drivers['HarmonyOS'] = HarmonyDriver()

        self._specialized_drivers = []
        self._drivers_by_keyword = {}
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
        """从类型化注册表统一实例化驱动，旧关键字仅用于兼容查询。"""
        base_types = {AppType.ANDROID_BASE, AppType.HARMONY_BASE}
        for driver_cls in driver_registry.get_driver_classes():
            app_type = driver_cls.app_type
            platform = driver_cls.platform
            if platform == DevicePlatform.HARMONYOS and not _HYPium_AVAILABLE:
                continue
            instance = driver_cls()
            keyword = getattr(driver_cls, 'keywords', None)
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError(f"驱动 {driver_cls.__name__} 必须声明唯一 keywords 标识")
            keyword = keyword.strip().lower()
            existing = self._drivers_by_keyword.get(keyword)
            if existing is not None and not isinstance(existing, driver_cls):
                raise ValueError(f"驱动 keywords 重复: {keyword}")
            self._drivers_by_keyword[keyword] = instance
            if app_type in base_types:
                self._base_drivers["Android" if platform == DevicePlatform.ANDROID else "HarmonyOS"] = instance
                if hasattr(instance, 'set_mock_mode'):
                    instance.set_mock_mode(self._mock_mode)
                continue
            self.register_specialized_driver(instance, keyword, platform.value, getattr(driver_cls, 'display_name', driver_cls.__name__))

    def register_specialized_driver(self, driver, keywords, system=None, name=None):
        """注册专用驱动"""
        # 设置新注册驱动的模拟模式
        if hasattr(driver, 'set_mock_mode'):
            driver.set_mock_mode(self._mock_mode)
        if not isinstance(keywords, str) or not keywords.strip():
            raise ValueError("驱动 keywords 必须是非空字符串")
        keyword = keywords.strip().lower()
        existing = self._drivers_by_keyword.get(keyword)
        if existing is not None and existing is not driver:
            raise ValueError(f"驱动 keywords 重复: {keyword}")
        self._drivers_by_keyword[keyword] = driver
        self._specialized_drivers.append({
            'driver': driver,
            'keywords': [keyword],
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

    def get_driver_typed(
        self,
        app_type: AppType,
        platform: DevicePlatform = None,
        version: AppVersion = AppVersion.V1,
    ):
        """按新版三元元数据获取已实例化的驱动。"""
        if platform is None:
            platform = {
                AppType.ANDROID_BASE: DevicePlatform.ANDROID,
                AppType.PLAUD: DevicePlatform.ANDROID,
                AppType.DOUBAO_ASR: DevicePlatform.ANDROID,
            }.get(app_type, DevicePlatform.HARMONYOS)
        driver_cls = driver_registry.resolve(app_type, version, platform)
        for driver in self.get_all_drivers():
            if isinstance(driver, driver_cls):
                return driver
        return None

    def get_driver_for_device(self, system, keywords=None, device_sn=None):
        """按设备字段解析新版驱动元数据并返回驱动实例。"""
        system_key = (system or '').lower()
        platform = {
            'android': DevicePlatform.ANDROID,
            'harmonyos': DevicePlatform.HARMONYOS,
            'ios': DevicePlatform.IOS,
        }.get(system_key)
        if platform is None:
            return None

        values = [keywords] if isinstance(keywords, str) else (keywords or [])
        for value in values:
            token = str(value).strip().lower()
            if not token:
                continue
            driver = self._drivers_by_keyword.get(token)
            if driver is not None:
                if driver.platform != platform:
                    raise ValueError(f"设备平台与驱动不匹配: system={system}, keywords={keywords}")
                return driver

        if isinstance(keywords, str) and keywords.strip():
            raise ValueError(f"未注册驱动 keywords: {keywords}")

        tokens = {str(value).strip().lower() for value in values if str(value).strip()}
        app_type = AppType.ANDROID_BASE if platform == DevicePlatform.ANDROID else AppType.HARMONY_BASE
        for candidate, aliases in _LEGACY_KEYWORDS.items():
            if candidate in (AppType.ANDROID_BASE, AppType.HARMONY_BASE):
                continue
            if tokens.intersection({alias.lower() for alias in aliases}):
                app_type = candidate
                break
        return self.get_driver_typed(app_type, platform)

    def list_registered_drivers(self):
        """返回新版注册表中的驱动元数据。"""
        return driver_registry.list_drivers()

    def register_driver_class(self, driver_cls, keywords=None, system=None, name=None):
        """注册一个带新版元数据的驱动类，并桥接到旧实例工厂。"""
        driver_registry.register(driver_cls)
        instance = driver_cls()
        if keywords is None:
            keywords = [driver_cls.app_type.value]
        if system is None:
            system = driver_cls.platform.value
        self.register_specialized_driver(instance, keywords, system, name)
        return instance

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
