from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_voice_conversion_driver import DouBaoAndroidTranslationDriver
from .harmony_driver import HarmonyDriver
from .harmony_translation_driver import (
    XiaoyiFace2FaceDriver,
    XiaoyiSimultaneousInterpretationDriver
)
from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
from .utils import log_and_emit


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
            'HarmonyOS': HarmonyDriver()
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
            DouBaoAndroidTranslationDriver(),
            ['doubao', '豆包', 'nova'],
            'Android',
            '安卓豆包翻译专用驱动'
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
            
            for kw in keywords_lower:
                if kw in entry['keywords']:
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
                
                for kw in keywords_lower:
                    if kw in entry['keywords']:
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
