import time

from device_service.infrastructure.drivers.harmony.xiaoyi_translation import HarmonyXiaoyiTranslationDriver
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers.registry import register_driver
from device_service.infrastructure.drivers.utils import By, with_rpc_retry
from device_service.infrastructure.drivers.driver_constants import NORMAL_WAIT


@register_driver
class XiaoyiFace2FaceDriver(HarmonyXiaoyiTranslationDriver):
    """小艺面对面翻译专用驱动"""

    # —— 驱动元数据 ——
    app_type = "xiaoyi_face2face"
    version = "v1"
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.xiaoyi_face2face.v1"
    display_name = "小艺面对面翻译 v1"
    dependencies = ["hypium"]

    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        initialize_success = super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
        if not initialize_success:
            return False
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...", task_id=task_id, test_case_id=test_case_id)
        # INT-312：读 super().initialize 的 explicit_degrade 分流结论；
        # 降级时 driver 为 None，后续 UI 导航步骤显式跳过
        driver, proceed = self._resume_driver_after_super_initialize(
            device_sn, task_id=task_id, test_case_id=test_case_id)
        if not proceed:
            return False
        if driver is None:
            self._log(level='WARNING',
                      content="UI 抓取层降级（explicit_degrade）: 面对面翻译 UI 导航步骤跳过",
                      task_id=task_id, test_case_id=test_case_id)
            return True
        try:
            mode_text = '面对面翻译'
            mode_btn = driver.find_component(By.text(mode_text))
            if mode_btn:
                self._log(level='DEBUG', content=f"Clicking Mode...{mode_text}", task_id=task_id, test_case_id=test_case_id)
                mode_btn.click()
                time.sleep(NORMAL_WAIT)
            self._log(level='INFO', content=f"Mode: {mode_text}", task_id=task_id, test_case_id=test_case_id)
            if driver.find_component(By.text('点击下方按钮说话')):
                self._log(level='INFO', content=f"成功打开面对面翻译", task_id=task_id, test_case_id=test_case_id)
                return True
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to get mode for device {device_sn}: {e}", task_id=task_id, test_case_id=test_case_id)
            return False

    @with_rpc_retry()
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_sn)
        translation_direction = kwargs.get('translation_direction', 'zh2en')
        if 'en2zh' in translation_direction:
            driver.touch((939, 2624))
        elif 'zh2en' in translation_direction:
            driver.touch((336, 2624))
        self._log(level='INFO', content=f"成功进行面对面翻译pre_process步骤", task_id=task_id, test_case_id=test_case_id)

    @with_rpc_retry()
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_sn)
        translation_direction = kwargs.get('translation_direction', 'zh2en')
        if 'en2zh' in translation_direction:
            driver.touch((939, 2624))
        elif 'zh2en' in translation_direction:
            driver.touch((336, 2624))
        self._log(level='INFO', content=f"成功进行面对面翻译post_process步骤", task_id=task_id, test_case_id=test_case_id)

    @with_rpc_retry()
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        driver = self._get_driver(device_sn)
        ori_text_list = driver.find_all_component(By.id("conv_item_input_text"))
        ori_text = '无内容'
        trans_text = '无内容'
        if len(ori_text_list) > 0:
            ori_text = ori_text_list[-1].getText()
        trans_text_list = driver.find_all_component(By.id("conv_item_translated_text"))
        if len(trans_text_list) > 0:
            trans_text = trans_text_list[-1].getText()
        self._log(level='INFO', content=f'成功抓取结果：ori_text={ori_text}, trans_text={trans_text}', task_id=task_id, test_case_id=test_case_id)
        return {'success': True, 'message': 'Success', 'asr': ori_text, 'translation': trans_text}
