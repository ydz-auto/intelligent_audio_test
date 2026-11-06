import time
import subprocess

from ..utils import check_stop, By, MatchPattern
from ..driver_constants import *
from ._constants import LOG_DEVICE_PATH


class LockMixin:
    """锁屏与解锁相关方法"""

    def is_locked(self, device_sn):
        """
        判断设备是否锁屏
        """
        try:
            lock_icon_id = '.*ScreenLock-PowerIcon_Image_power'
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

        subprocess.run(['hdc', '-t', device_sn, 'shell', 'power-shell', 'wakeup'], check=False)
        time.sleep(NORMAL_WAIT)

        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-m', '540', '1800', '540', '400', '200'],
                           check=False)
            time.sleep(UNLOCK_SWIPE_WAIT)
            # 点击屏幕即解锁
            driver.click((1560, 1040))
            return
        except Exception as e:
            self._log(level='WARNING', content=f"Wakeup interaction failed: {e}")

        time.sleep(NORMAL_WAIT)
