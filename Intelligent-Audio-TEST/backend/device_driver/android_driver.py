import time
import subprocess
from .base_driver import BaseDeviceDriver
from .device_config import get_device_config
from .utils import check_stop, u2, log_and_emit
import re
class AndroidDriver(BaseDeviceDriver):
    """安卓设备驱动实现"""

    def __init__(self):
        super().__init__()
        self._drivers  = {}
        self._config = get_device_config('android')
        self.app_name = self._config.get('app_name', 'com.larus.nova')
        self._unlock_password = self._config.get('unlock_password', '000000')
        self._close_buttons = self._config.get('close_buttons', [])
        self._popup_keywords = self._config.get('popup_keywords', [])
        self._exclude_list = self._config.get('exclude_list', [])
        self._abnormal_keywords = self._config.get('abnormal_keywords', [])

    def is_locked(self, device_id):
        """
        判断设备是否锁屏
        """
        driver = self._drivers.get(device_id)
        if driver:
            try:
                driver.sceen_on()
                time.sleep(0.5)
                flashlight_elem = driver(resourcId="com.android.systemui:id/flashlight_imageview")
                if flashlight_elem.exists(timeout=1):
                    return True
                unlock_bar_elem = driver(resourcId="com.android.systemui:id/lock_indication")
                if unlock_bar_elem.exists(timeout=1):
                    return True
                self._log(level='INFO', content=f"设备{device_id} 已解锁")
            except Exception as e:
                self._log(level='ERROR', content=f"检查锁屏状态失败：{e}")
                return False
        self._log(level='INFO', content=f"获取设备{device_id}驱动失败")
        return False

    def _get_driver(self, device_id):
        if not u2:
            return None
        if device_id not in self._drivers:
            try:
                self._drivers[device_id] = u2.connect(device_id)
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to connect to android device {device_id}: {e}")
                return None
        return self._drivers[device_id]

    def scan(self):
        """使用 adb devices -l 扫描设备"""
        if self._mock_mode:
            return [
                {
                    "serial": "mock-android-1",
                    "model": "Mock Android Device",
                    "system": "Android",
                    "status": "online"
                }
            ]
        devices = []
        try:
            output = subprocess.check_output(['adb', 'devices', '-l'], encoding='utf-8', stderr=subprocess.STDOUT)
            lines = output.strip().split('\n')
            for line in lines[1:]:
                if not line.strip():
                    continue
                match = re.match(r'^([^\s]+)\s+device\s+.*model:([^\s]+)', line)
                if match:
                    serial = match.group(1)
                    model = match.group(2)
                    devices.append({
                        "serial": serial,
                        "model": model,
                        "system": "Android",
                        "status": "online"
                    })
                elif 'device' in line:
                    parts = line.split()
                    devices.append({
                        "serial": parts[0],
                        "model": "Unknown Android",
                        "system": "Android",
                        "status": "online"
                    })
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return devices

    @check_stop("initialize")
    def initialize(self, device_id, **kwargs) -> bool:
        """初始化安卓设备"""
        self._log(level='INFO', content=f"Initializing Android device {device_id} for {self.app_name}...")
        driver = self._get_driver(device_id)
        if driver:
            try:
                self.unlock(device_id, **kwargs)
                if self._check_stop(device_id, "initialize"):
                    return False
                # 检测并关闭弹窗
                self.close_popups(device_id)
                if self._check_stop(device_id, "initialize"):
                    return False
                driver.app_start(self.app_name, stop=True)
                time.sleep(3)
                # 启动应用后再次检查弹窗
                self.close_popups(device_id)
                self._log(level='INFO', content=f"Android device {device_id} initialized successfully")
                return True
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to start app {self.app_name} on device {device_id}: {e}")
        self._log(level='ERROR', content=f"Failed to initialize Android device {device_id}: Driver not available")
        return False

    @check_stop("unlock")
    def unlock(self, device_id, **kwargs) -> None:
        """唤醒并解锁安卓设备"""
        self._log(level='INFO', content=f"Android device {device_id} waking up...")
        driver = self._get_driver(device_id)
        if not driver:
            return False
        if self._check_stop(device_id, "unlock"):
            return 
        driver.screen_on()
        time.sleep(1)
        self._log(level='DEBUG', content=f"Screen turned on for device {device_id}")

        is_locked = self.is_locked(device_id)
        if not is_locked:
            self._log(level='DEBUG', content=f"Device {device_id} locked has unlocked")
            return


        self._unlock(device_id, **kwargs)
        if self._check_stop(device_id, "unlock"):
            return
        self._log(level='DEBUG', content=f"Device {device_id} unlocked successfully")       



    def _unlock(self, device_id, **kwargs) -> None:
        """解锁安卓设备"""
        self._log(level='INFO', content=f"Android device {device_id} unlocking...")
        driver = self._get_driver(device_id)
        if not driver:
            return False
        try:
            driver.swipe(0.5, 0.8, 0.5, 0.2)
            time.sleep(1)
            self._log(level='DEBUG', content=f"Swiped up to unlock device {device_id}")

            if self._check_stop(device_id, "unlock"):
                return
            self._log(level='DEBUG', content="Entering password digits...")
            password = self._unlock_password
            coords_cache = {}

            for i, digit in enumerate(password):
                if self._check_stop(device_id, "unlock"):
                    return
                if digit in coords_cache:
                    center = coords_cache[digit]
                    self._log(level='DEBUG',
                                content=f"Clicking digit {digit} at cached {center} (position {i + 1})...")
                    driver.click(center[0], center[1])
                else:
                    btns = driver(text=digit)
                    if btns.exists:
                        best_btn = None
                        max_y = -1
                        for b in btns:
                            b_center = b.center()
                            if b_center[1] > max_y:
                                max_y = b_center[1]
                                best_btn = b

                        if best_btn:
                            center = best_btn.center()
                            coords_cache[digit] = center
                            self._log(level='DEBUG',
                                        content=f"Clicking digit {digit} at {center} (position {i + 1})...")
                            driver.click(center[0], center[1])
                        else:
                            self._log(level='WARNING', content=f"Digit {digit} exists but no valid button found.")
                    else:
                        self._log(level='WARNING', content=f"Digit {digit} not found, using keyevent.")
                        keycode = int(digit) + 7
                        subprocess.run(['adb', '-s', device_id, 'shell', 'input', 'keyevent', str(keycode)],
                                        check=False)
                time.sleep(1.0)

            if self._check_stop(device_id, "unlock"):
                return
            self._log(level='DEBUG', content="Clicking confirm/enter...")
            confirm_btns = ["确认", "OK", "Done", "Enter"]
            clicked_confirm = False
            for btn_text in confirm_btns:
                btn = driver(text=btn_text)
                if btn.exists:
                    btn.click()
                    clicked_confirm = True
                    self._log(level='DEBUG', content=f"Clicked confirm button: {btn_text}")
                    break

            if not clicked_confirm:
                self._log(level='DEBUG', content="No confirm button found, sending keyevent 66 (Enter)")
                subprocess.run(['adb', '-s', device_id, 'shell', 'input', 'keyevent', '66'], check=False)

            self._log(level='INFO', content=f"Android device {device_id} woke up successfully")
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to wake up Android device {device_id}: {e}")

    @check_stop("post_process")
    def post_process(self, device_id, **kwargs) -> bool:
        """结束处理"""
        self._log(level='INFO', content=f"--- Finished post-process for Android {device_id} ---")
        return True

    @check_stop("close_popups")
    def close_popups(self, device_id) -> bool:
        """检测并关闭 Android 设备上的弹窗
        
        Args:
            device_id: 设备 ID
            
        Returns:
            bool: 是否成功执行
        """
        self._log(level='INFO', content=f"Checking for popups on Android device {device_id}...")
        driver = self._get_driver(device_id)
        if not driver:
            return False

        try:
            # 从配置获取弹窗按钮文本
            close_buttons = self._close_buttons

            # 检测并关闭弹窗
            for btn_text in close_buttons:
                if self._check_stop(device_id, "close_popups"):
                    return False

                # 查找按钮
                buttons = driver(text=btn_text)
                if buttons.exists:
                    # 找到所有匹配的按钮
                    found_buttons = []
                    for btn in buttons:
                        try:
                            if btn.exists:
                                found_buttons.append(btn)
                        except:
                            continue

                    # 优先点击底部的按钮（通常是确认/关闭按钮）
                    if found_buttons:
                        # 按 y 坐标排序，选择最下面的按钮
                        found_buttons.sort(key=lambda x: x.center()[1], reverse=True)
                        btn = found_buttons[0]
                        btn_center = btn.center()
                        self._log(level='DEBUG',
                                  content=f"Found popup button '{btn_text}' at {btn_center}, clicking...")
                        btn.click()
                        time.sleep(1)
                        # 点击后可能还有其他弹窗，继续检查
                        continue

            # 从配置获取弹窗关键词
            popup_keywords = self._popup_keywords
            for keyword in popup_keywords:
                if self._check_stop(device_id, "close_popups"):
                    return False

                elements = driver(textContains=keyword)
                if elements.exists:
                    self._log(level='DEBUG', content=f"Found popup with keyword '{keyword}', trying to close...")
                    # 尝试点击弹窗中的关闭按钮
                    for btn_text in close_buttons:
                        btn = driver(text=btn_text)
                        if btn.exists:
                            btn.click()
                            time.sleep(1)
                            break

            self._log(level='INFO', content=f"Popup check completed for Android device {device_id}")
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"Error closing popups on Android device {device_id}: {e}")
            return False

    @check_stop("get_results")
    def get_results(self, device_id, task_id=None, case_id=None, **kwargs) -> dict:
        """获取设备输出结果 - 返回原始文本列表"""
        return {'success': True, 'message': 'Success', 'asr': 'asr中文', 'translation': 'translation中文'}
