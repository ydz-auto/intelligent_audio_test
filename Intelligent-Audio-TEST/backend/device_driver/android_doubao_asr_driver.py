import re
import time
from .android_driver import AndroidDriver
from .utils import check_stop


class DouBaoAndroidAsrDriver(AndroidDriver):

    def __init__(self):
        super().__init__()
        self.app_name = "com.larus.nova"

    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        self.unlock(device_sn)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content="Driver not available", task_id=task_id, test_case_id=test_case_id)
            return False
        if self.app_name in driver.app_list_running() and driver(text='按住说话').exists:
            self._log(level='INFO', content=f"app已初始化:{self.app_name}", task_id=task_id, test_case_id=test_case_id)
            return True

        driver.app_stop(self.app_name)
        initialize_success = super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
        if not initialize_success:
            if self.app_name not in driver.app_list_running():
                driver.app_start(self.app_name)
                driver.xpath(r'//*[@resource-id="com.larus.nova:id/back_icon"]').click()
                driver(text='豆包').click()
        return True

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        if not driver:
            return False
        btn = driver.xpath(r'//*[@resource-id="com.larus.nova:id/speak_normal"]')
        if btn.exists:
            x, y = btn.center()
            driver.touch.down(x, y)
            self._log(level='INFO', content=f"按住说话按钮 ({x}, {y})", task_id=task_id, test_case_id=test_case_id)
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        if not driver:
            return False
        btn = driver.xpath(r'//*[@resource-id="com.larus.nova:id/speak_normal"]')
        if btn.exists:
            x, y = btn.center()
            driver.touch.up(x, y)
        return True

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        self._log(level='DEBUG', content=f'Getting results from android device: {device_sn}', task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Driver not available for device: {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return {'success': False, 'message': 'Driver not available', 'asr': '', 'translation': ''}

        try:
            width, height = driver.window_size()
            half_width = width / 2

            msg_list_xpath = r'//*[@resource-id="com.larus.nova:id/message_list_parent"]//android.widget.TextView'
            all_text_elems = driver.xpath(msg_list_xpath).all()
            self._log(level='DEBUG', content=f"消息列表内TextView总数: {len(all_text_elems)}", task_id=task_id, test_case_id=test_case_id)

            user_msg_list = []
            for elem in all_text_elems:
                try:
                    text = elem.text
                    if not text or len(text.strip()) == 0:
                        continue

                    bounds = elem.info.get('bounds', {})
                    left = bounds.get('left', 0)
                    top = bounds.get('top', 0)

                    if left > half_width:
                        user_msg_list.append({
                            'text': text.strip(),
                            'top': top
                        })
                except Exception as inner_e:
                    self._log(level='DEBUG', content=f"单条文本元素解析跳过: {inner_e}", task_id=task_id, test_case_id=test_case_id)
                    continue

            self._log(level='DEBUG', content=f"识别到用户右侧消息数量: {len(user_msg_list)}", task_id=task_id, test_case_id=test_case_id)

            if user_msg_list:
                user_msg_sorted = sorted(user_msg_list, key=lambda x: x['top'], reverse=True)
                latest_user_text = user_msg_sorted[0]['text']
                self._log(level='DEBUG', content=f"抓取到最新用户消息: {latest_user_text}", task_id=task_id, test_case_id=test_case_id)
                return {'success': True, 'message': 'Success', 'asr': latest_user_text, 'translation': ''}

            self._log(level='WARNING', content="消息列表内未找到用户右侧发送消息", task_id=task_id, test_case_id=test_case_id)
            return {'success': True, 'message': 'Success', 'asr': '', 'translation': ''}

        except Exception as e:
            self._log(level='ERROR', content=f'Android get_results 捕获全局异常 device {device_sn}: {str(e)}', task_id=task_id, test_case_id=test_case_id)
            return {'success': False, 'message': str(e), 'asr': '', 'translation': ''}
