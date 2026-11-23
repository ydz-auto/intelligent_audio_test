"""小艺翻译驱动共享基类（非独立注册，供各翻译模式版本目录继承）。"""
import time

from device_service.infrastructure.drivers.harmony.base.v1 import HarmonyDriver
from device_service.infrastructure.drivers.utils import By, with_rpc_retry
from device_service.infrastructure.drivers.driver_constants import LONG_WAIT, TRANSLATION_WAIT

__all__ = ["HarmonyXiaoyiTranslationDriver"]


class HarmonyXiaoyiTranslationDriver(HarmonyDriver):
    """鸿蒙小艺翻译基础驱动（非独立注册，供子类继承）"""

    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        initialize_success = super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
        if not initialize_success:
            return False
        # 2. 尝试通过桌面图标启动 (使用用户提供的 Key)
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...", task_id=task_id, test_case_id=test_case_id)
        # INT-312：读 super().initialize 的 explicit_degrade 分流结论；
        # 降级时 driver 为 None，后续 UI 导航步骤显式跳过
        driver, proceed = self._resume_driver_after_super_initialize(
            device_sn, task_id=task_id, test_case_id=test_case_id)
        if not proceed:
            return False
        if driver is None:
            self._log(level='WARNING',
                      content="UI 抓取层降级（explicit_degrade）: 小艺翻译 UI 导航步骤（用户中心/设置/翻译页）跳过",
                      task_id=task_id, test_case_id=test_case_id)
            return True
        # 3. 点击右上角"用户中心/头像"
        user_center = driver.find_component(By.description("用户中心")) or \
                      driver.find_component(By.type("Image"))
        if user_center:
            self._log(level='DEBUG', content="Clicking User Center...", task_id=task_id, test_case_id=test_case_id)
            user_center.click()
            time.sleep(LONG_WAIT)

        # 4. 点击"设置"
        settings_btn = driver.find_component(By.text("设置"))
        if settings_btn:
            self._log(level='DEBUG', content="Clicking Settings...", task_id=task_id, test_case_id=test_case_id)
            settings_btn.click()
            time.sleep(LONG_WAIT)

        # 5. 点击"小艺翻译"
        trans_setting = driver.find_component(By.text("小艺翻译"))
        if trans_setting:
            self._log(level='DEBUG', content="Clicking Celia Translation...", task_id=task_id, test_case_id=test_case_id)
            trans_setting.click()
            time.sleep(LONG_WAIT)

        # 6. 检查并点击"启用"
        enable_btn = driver.find_component(By.text("启用小艺翻译"))
        if enable_btn:
            self._log(level='DEBUG', content="Enabling service...", task_id=task_id, test_case_id=test_case_id)
            enable_btn.click()
            time.sleep(TRANSLATION_WAIT)

        # 7. 点击"小艺翻译助手"
        assistant_btn = driver.find_component(By.text("小艺翻译助手"))
        if assistant_btn:
            self._log(level='DEBUG', content="Entering Assistant...", task_id=task_id, test_case_id=test_case_id)
            assistant_btn.click()
            time.sleep(LONG_WAIT)
            return True

        return False
