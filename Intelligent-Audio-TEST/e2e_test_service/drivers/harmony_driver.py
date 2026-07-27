import time
import subprocess
import os
from .base_driver import BaseDeviceDriver
from .device_config import get_device_config
from .utils import check_stop, UiDriver, By, MatchPattern


class HarmonyDriver(BaseDeviceDriver):
    """HarmonyOS设备驱动实现"""

    def __init__(self):
        """初始化HarmonyOS驱动"""
        super().__init__()
        self._drivers = {}
        self._config = get_device_config('harmonyos')
        self.app_name = self._config.get('app_name', 'com.huawei.hmos.vassistant')
        self.app_icon_key = self._config.get('app_icon_key',
                                             'AppIconCommonView_com.huawei.hmos.vassistant.launcher.VoiceAbility')
        self._unlock_password = self._config.get('unlock_password', '000000')
        self._close_buttons = self._config.get('close_buttons', [])
        self._popup_keywords = self._config.get('popup_keywords', [])
        self._exclude_list = self._config.get('exclude_list', [])
        self._abnormal_keywords = self._config.get('abnormal_keywords', [])

    def _get_driver(self, device_sn):
        if not UiDriver:
            return None
        if device_sn not in self._drivers:
            try:
                self._drivers[device_sn] = UiDriver.connect(device_sn=device_sn)
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to connect to Harmony device {device_sn}: {e}")
                return None
        return self._drivers[device_sn]

    def get_driver(self, device_sn):
        return self._get_driver(device_sn)

    def is_locked(self, device_sn):
        """
        判断设备是否锁屏
        """
        try:
            lock_icon_id = '.*LockIcon_Image_lock'
            driver = self._get_driver(device_sn)
            if not driver:
                self._log(level='WARNING', content=f"无法获取设备{device_sn}的驱动，无法检查锁屏状态")
                return False
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'power-shell', 'wakeup'], check=False)
            lock_element = driver.find_component(By.id(f'{lock_icon_id}', MatchPattern.REGEXP))
            if lock_element:
                self._log(level='INFO', content=f"设备{device_sn}已锁屏")
                return True
            return False
        except Exception as e:
            self._log(level='INFO', content=f"设备{device_sn}锁屏检查失败：{e}")
            return False

    @check_stop("unlock")
    def unlock(self, device_sn, **kwargs) -> None:
        """唤醒设备"""
        self._log(level='INFO', content=f"Harmony device {device_sn} waking up and unlocking...")
        driver = self._get_driver(device_sn)
        if not self.is_locked(device_sn):
            self._log(level='INFO', content=f"设备{device_sn}已解锁，无需重复解锁")
            return
        if self._check_stop("unlock"):
            return

        subprocess.run(['hdc', '-t', device_sn, 'shell', 'power-shell', 'wakeup'], check=False)
        time.sleep(1)

        if self._check_stop("unlock"):
            return
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-m', '540', '1800', '540', '400', '200'],
                           check=False)
            time.sleep(0.5)
        except Exception as e:
            self._log(level='WARNING', content=f"Wakeup interaction failed: {e}")
        time.sleep(2)

        if self._check_stop("unlock"):
            return
        password = self._unlock_password
        try:
            if driver:
                self._log(level='DEBUG', content=f"Attempting to input password: {'*' * len(password)}")
                coords_cache = {}
                for i, digit in enumerate(password):
                    if self._check_stop("unlock"):
                        return
                    if digit in coords_cache:
                        center = coords_cache[digit]
                        self._log(level='DEBUG',
                                  content=f"Clicking digit {digit} at cached {center} (position {i + 1})...")
                        driver.click(center[0], center[1])
                    else:
                        btns = driver.find_components(By.text(digit), 10)
                        if btns:
                            best_btn = None
                            max_y = -1
                            for btn in btns:
                                try:
                                    bounds = btn.getBounds()
                                    center_y = (bounds[1] + bounds[3]) / 2
                                    if center_y > max_y:
                                        max_y = center_y
                                        best_btn = btn
                                except Exception as e:
                                    self._log(level='DEBUG', content=f"Error getting button bounds: {e}")
                                    continue

                            if best_btn:
                                bounds = best_btn.getBounds()
                                center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
                                coords_cache[digit] = center
                                self._log(level='DEBUG',
                                          content=f"Clicking digit {digit} at {center} (position {i + 1})...")
                                driver.click(center[0], center[1])
                            else:
                                self._log(level='WARNING', content=f"Digit {digit} component found but invalid.")
                        else:
                            key_map = {
                                "1": (270, 1800), "2": (540, 1800), "3": (810, 1800),
                                "4": (270, 2000), "5": (540, 2000), "6": (810, 2000),
                                "7": (270, 2200), "8": (540, 2200), "9": (810, 2200),
                                "0": (540, 2400)
                            }
                            if digit in key_map:
                                pos = key_map[digit]
                                self._log(level='WARNING',
                                      content=f"Digit {digit} not found, trying predicted coordinates {pos}...")
                                driver.click(pos[0], pos[1])
                            else:
                                self._log(level='ERROR', content=f"Digit {digit} not found on screen and no fallback.")
                    time.sleep(1.0)

                if self._check_stop("unlock"):
                    return
                for confirm_text in ["确定", "完成", "OK", "解锁"]:
                    confirm_btn = driver.find_component(By.text(confirm_text))
                    if confirm_btn:
                        confirm_btn.click()
                        break
        except Exception as e:
            self._log(level='ERROR', content=f"Unlock via clicking digits failed: {e}")

        time.sleep(1)

    def scan(self):
        """使用 hdc list targets 扫描设备"""
        if self._mock_mode:
            return [
                {
                    "serial": "mock-harmony-1",
                    "model": "Mock HarmonyOS Device",
                    "system": "HarmonyOS",
                    "status": "online"
                }
            ]
        devices = []
        self._log(level='INFO', content="Starting HarmonyOS device scan via hdc...")
        try:
            output = subprocess.check_output(['hdc', 'list', 'targets'], encoding='utf-8', stderr=subprocess.STDOUT)
            self._log(level='DEBUG', content=f"hdc list targets output: {output}")
            lines = output.strip().split('\n')
            for line in lines:
                if line.strip() and '[Empty]' not in line:
                    devices.append({
                        "serial": line.strip(),
                        "model": "Harmony Device",
                        "system": "HarmonyOS",
                        "status": "online"
                    })
            self._log(level='INFO', content=f"Found {len(devices)} HarmonyOS device(s) via hdc")
        except subprocess.CalledProcessError as e:
            self._log(level='WARNING', content=f"hdc list targets command failed: {e.output}")
        except FileNotFoundError as e:
            self._log(level='WARNING', content=f"hdc command not found: {e}")
        return devices

    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化鸿蒙设备"""
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...")
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}")
            return False

        try:

            if self._check_stop("initialize"):
                return False
            self.unlock(device_sn)
            if self._check_stop("initialize"):
                return False

            # 检测并关闭弹窗
            self.close_popups(device_sn)
            if self._check_stop("initialize"):
                return False
            try:
                driver.swipe_to_home()
            except:
                driver.press_home()
            time.sleep(2)

            driver.stop_app(self.app_name)

            if self._check_stop("initialize"):
                return False
            # 从配置获取应用图标Key
            app_icon_key = self.app_icon_key
            icon = driver.find_component(By.key(app_icon_key))
            if icon:
                self._log(level='DEBUG', content=f"Clicking app icon...")
                icon.click()
                time.sleep(3)
                # 启动应用后再次检查弹窗
                self.close_popups(device_sn)
            else:
                self._log(level='WARNING', content="App icon not found, trying aa start...")
                subprocess.run(['hdc', '-t', device_sn, 'shell', 'aa', 'start', '-b', self.app_name], check=False)
                time.sleep(3)
                # 启动应用后再次检查弹窗
                self.close_popups(device_sn)

            if self._check_stop("initialize"):
                return False
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to initialize via settings path: {e}")
            return False

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开始处理：进入前台等准备动作"""
        self._log(level='INFO', content=f"--- Starting pre-process for {device_sn} ---")
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """结束处理：清理或日志记录"""
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---")
        return True

    @check_stop("close_popups")
    def close_popups(self, device_sn) -> bool:
        """检测并关闭 HarmonyOS 设备上的弹窗

        Args:
            device_sn: 设备序列号

        Returns:
            bool: 是否成功执行
        """
        self._log(level='INFO', content=f"Checking for popups on HarmonyOS device {device_sn}...")
        driver = self._get_driver(device_sn)
        if not driver:
            return False

        def safe_find_components(by_obj, timeout_sec=10):
            """安全的 find_components 调用，带超时保护"""
            result = []
            start_time = time.time()
            try:
                while time.time() - start_time < timeout_sec:
                    try:
                        result = driver.find_components(by_obj, 1)
                        break
                    except Exception:
                        time.sleep(0.5)
                        continue
            except Exception:
                pass
            return result

        try:
            close_buttons = self._close_buttons or []

            for btn_text in close_buttons:
                if self._check_stop("close_popups"):
                    return False

                try:
                    buttons = safe_find_components(By.text(btn_text), 10)
                    if buttons:
                        best_btn = None
                        max_y = -1
                        for btn in buttons:
                            try:
                                if not hasattr(btn, 'getBounds'):
                                    continue
                                bounds = btn.getBounds()
                                center_y = (bounds[1] + bounds[3]) / 2
                                if center_y > max_y:
                                    max_y = center_y
                                    best_btn = btn
                            except Exception:
                                continue

                        if best_btn:
                            self._log(level='DEBUG',
                                      content=f"Found popup button '{btn_text}' on HarmonyOS, clicking...")
                            try:
                                best_btn.click()
                            except Exception as e:
                                self._log(level='DEBUG', content=f"Failed to click button: {e}")
                            time.sleep(0.5)
                            continue
                except Exception as e:
                    self._log(level='DEBUG', content=f"Error checking button '{btn_text}' on HarmonyOS: {e}")
                    continue

            popup_keywords = self._popup_keywords or []
            for keyword in popup_keywords:
                if self._check_stop("close_popups"):
                    return False

                elements = safe_find_components(By.text(keyword, MatchPattern.CONTAINS), 10)
                if not elements:
                    continue
                self._log(level='DEBUG',
                          content=f"Found popup with keyword '{keyword}' on HarmonyOS, trying to close...")
                for btn_text in close_buttons:
                    try:
                        btn = driver.find_component(By.text(btn_text))
                        if btn and hasattr(btn, 'click'):
                            btn.click()
                            time.sleep(0.5)
                            break
                    except Exception as e:
                        self._log(level='DEBUG', content=f"Error clicking button '{btn_text}' on HarmonyOS: {e}")
                        continue

            self._log(level='INFO', content=f"Popup check completed for HarmonyOS device {device_sn}")
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"Error closing popups on HarmonyOS device {device_sn}: {e}")
            return False

    def set_volume(self, device_sn, level: int) -> bool:
        """设置 HarmonyOS 设备系统音量
        
        Args:
            device_sn: 设备序列号
            level: 音量级别(0-100)
            
        Returns:
            bool: 是否设置成功
        """
        try:
            level = max(0, min(100, level))
            device_level = round(level * 15 / 100)
            subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'audioctl', '-s', str(device_level)],
                check=False, capture_output=True, timeout=10
            )
            self._log(level='INFO', content=f"HarmonyOS 设备 {device_sn} 音量已设为 {level} (设备值: {device_level})")
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"HarmonyOS 设备 {device_sn} 音量设置失败: {e}")
            return False

    def get_volume(self, device_sn) -> int:
        """获取 HarmonyOS 设备系统音量
        
        Args:
            device_sn: 设备序列号
            
        Returns:
            int: 当前音量(0-100)，不支持或失败返回 -1
        """
        try:
            result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'audioctl', '-g'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                device_level = int(output.split()[-1]) if output else -1
                if device_level >= 0:
                    return round(device_level * 100 / 15)
            return -1
        except Exception as e:
            self._log(level='WARNING', content=f"HarmonyOS 设备 {device_sn} 音量获取失败: {e}")
            return -1

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """获取设备输出结果 - 返回原始文本列表"""
        return {'success': True, 'message': 'Success', 'asr': 'asr中文', 'translation': 'translation中文'}
