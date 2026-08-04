import time
import subprocess
import os
import re

from nacl.pwhash import PASSWD_MAX

from .base_driver import BaseDeviceDriver
from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
try:
    from hypium import UiDriver, BY
except Exception:
    UiDriver = None
    BY = None


# 日志目录路径
LOG_DEVICE_PATH = "/data/app/el2/100/base/com.huawei.hmos.vassistant/haps/voice_pc/files/log"


class HarmonyHardenXiaoyi_Input_MethodDriver(HarmonyDriver):
    """鸿蒙小艺输入法驱动"""

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
        time.sleep(1)

        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-m', '540', '1800', '540', '400', '200'],
                           check=False)
            time.sleep(0.5)
            # 点击屏幕即解锁
            driver.click((1560, 1040))
            return
        except Exception as e:
            self._log(level='WARNING', content=f"Wakeup interaction failed: {e}")

        time.sleep(1)

    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """打开备忘录"""
        package_name = 'com.huawei.hmos.notepad'
        try:
            # 检查应用是否已打开
            check_result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'pidof', package_name],
                capture_output=True,
                text=True,
                check=False
            )
            
            if check_result.stdout.strip():
                # 应用已打开，先关闭
                self._log(level='INFO', content=f"备忘录应用已打开(PID: {check_result.stdout.strip()})，先关闭再打开")
                subprocess.run(
                    ['hdc', '-t', device_sn, 'shell', 'aa', 'force-stop', package_name],
                    check=False
                )
                time.sleep(1)  # 等待应用关闭
            
            # 启动应用
            result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'aa', 'start', '-a', 'MainAbility', '-b', package_name],
                capture_output=True,
                text=True,
                check=False
            )
            self._log(level='INFO', content=f"启动备忘录应用结果: {result.stdout}")
            time.sleep(2)  # 等待应用启动
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"启动备忘录应用失败: {e}")
            return False

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        # 创建备忘录
        # 根据条件点击控件
        driver.touch(BY.key('createNote'))
        driver.wait(0.5)
        subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-d', '656', '2520'], check=False)
        self._log(level='INFO', content=f"开始按下坐标 (656, 2520)")
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        # 释放 (-u = up)
        subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-u', '656', '2520'], check=False)
        self._log(level='INFO', content=f"释放坐标 (656, 2520)")
        time.sleep(0.5)
        return True

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        driver = self._get_driver(device_sn)
        if driver:
            element = driver.find_component(BY.key('content_area_NoteEditorManager'))
            if element:
                text_content = element.getText()
                self._log(level='INFO', content=f"控件文本内容: {text_content}")
                return [{"success": True, "message": "Success", "text": text_content}]
            else:
                self._log(level='WARNING', content=f"未找到控件 content_area_NoteEditorManager")
                return [{"success": False, "message": "未找到控件 content_area_NoteEditorManager", "text": ""}]
        return [{"success": False, "message": "无法获取设备驱动", "text": ""}]
