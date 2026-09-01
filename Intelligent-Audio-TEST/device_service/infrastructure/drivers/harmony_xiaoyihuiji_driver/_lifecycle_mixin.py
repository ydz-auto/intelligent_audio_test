import time
import subprocess

from ..utils import check_stop, By, with_rpc_retry
from ..driver_constants import *
from ._constants import LOG_DEVICE_PATH


class LifecycleMixin:
    """设备初始化与生命周期处理方法（initialize / pre_process / post_process）"""

    @check_stop("initialize")
    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化小艺慧记设备"""
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...", task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False
            
        try:
            # 步骤4：清理设备日志
            clean_result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'rm', '-rf', f'{LOG_DEVICE_PATH}/*'],
                check=False, capture_output=True, text=True
            )
            self._log(level='INFO', content=f"清理设备日志: {clean_result.stdout}", task_id=task_id, test_case_id=test_case_id)
            if self._check_stop("initialize"):
                return False
            self.unlock(device_sn)
            if self._check_stop("initialize"):
                return False
            self._log(level='DEBUG', content="Clicking User Center...", task_id=task_id, test_case_id=test_case_id)
            # 检测并关闭弹窗
            self.close_popups(device_sn)
            # 点击菜单
            driver.click(
                By.key('SmartDock_AppIcon_Container_com.ohos.sceneboard_com.ohos.sceneboard.appcenter.MainAbility'))
            # 点击小艺
            driver.click(By.key('AppIcon_Image_com.huawei.hmos.vassistantVoicePcFreeAbilityvoice_pc0_AppCenterItem_2'))
            # 点击工具栏
            time.sleep(SHORT_WAIT)
            driver.click(By.key('PluginRootComponent_Stack_status_bar_control_center'))
            # 点击小艺慧记
            driver.click(By.key('Ctrl.NewToggleBaseComponent_Image_meeting'))
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"打开{device_sn}小艺慧记失败：{e}", task_id=task_id, test_case_id=test_case_id)
            return False

    @check_stop("pre_process")
    @with_rpc_retry()
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开始处理：进入前台等准备动作"""
        self._log(level='INFO', content=f"--- Starting pre-process for {device_sn} ---", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False
        try:
            driver.click(By.text('开始'))
            if driver.find_component(By.text('智能提醒')):
                self._log(level='INFO', content=f"--- 开启{device_sn} 小艺慧记 成功---", task_id=task_id, test_case_id=test_case_id)
                return True
            self._log(level='INFO', content=f"--- 开启{device_sn} 小艺慧记 失败---", task_id=task_id, test_case_id=test_case_id)
            return False
        except Exception as e:
            self._log(level='INFO', content=f": 开启{device_sn} 小艺慧记 失败{e}", task_id=task_id, test_case_id=test_case_id)
            return False

    @check_stop("post_process")
    @with_rpc_retry()
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """结束处理：清理或日志记录"""
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False
        try:
            driver.click(By.xpath('//Row/__Common__/Row/Button[2]/Image'))
            time.sleep(SHORT_WAIT)
            driver.click(By.xpath('//Dialog/Column/Column/Column[1]/Row[2]/Checkbox'))
            driver.click(By.text('结束并保存'))
            while driver.find_component(By.text('正在保存')):
                time.sleep(NORMAL_WAIT)
            return True

        except Exception as e:
            self._log(level='INFO', content=f": 结束{device_sn} 小艺慧记 失败{e}", task_id=task_id, test_case_id=test_case_id)
            return False
