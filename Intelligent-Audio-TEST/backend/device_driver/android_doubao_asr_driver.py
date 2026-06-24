import re
import subprocess
import time
from .android_driver import AndroidDriver
from .utils import check_stop


def is_locked(self, device_sn):
    """
    判断设备是否锁屏
    """
    driver = self._drivers.get(device_sn)
    if driver:
        try:
            driver.screen_on()
            time.sleep(0.5)
            result = subprocess.run(
                ['adb', '-s', device_sn, 'shell', 'dumpsys', 'window'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                if 'mDreamingLockscreen=true' in result.stdout or 'isStatusBarKeyguard=true' in result.stdout:
                    self._log(level='INFO', content=f"设备{device_sn} 处于锁屏状态")
                    return True
            self._log(level='INFO', content=f"设备{device_sn} 已解锁")
            return False
        except Exception as e:
            self._log(level='ERROR', content=f"检查锁屏状态失败：{e}")
            return False
    self._log(level='INFO', content=f"获取设备{device_sn}驱动失败")
    return False

class DouBaoAndroidAsrDriver(AndroidDriver):

    def __init__(self):
        super().__init__()
        self.app_name = "com.larus.nova"
        self._pre_user_msgs = {}
        self._pre_msg_count = {}

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
        pre_msgs = self._collect_user_messages(driver)
        self._pre_user_msgs[device_sn] = set(m['text'] for m in pre_msgs)
        self._pre_msg_count[device_sn] = len(pre_msgs)
        self._log(level='DEBUG', content=f"pre_process 快照已有用户消息数: {len(pre_msgs)}", task_id=task_id, test_case_id=test_case_id)
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

    def _scroll_to_bottom(self, driver):
        """滚动到消息列表底部，确保最新消息可见"""
        try:
            msg_list = driver.xpath(r'//*[@resource-id="com.larus.nova:id/message_list_parent"]')
            if msg_list.exists:
                msg_list.scroll.toEnd()
                time.sleep(0.5)
        except Exception:
            pass

    def _collect_user_messages(self, driver):
        """收集消息列表中所有用户右侧消息，返回 [{'text': str, 'top': int}, ...]"""
        user_msgs = []
        try:
            width, height = driver.window_size()
            half_width = width / 2
            msg_list_xpath = r'//*[@resource-id="com.larus.nova:id/message_list_parent"]//android.widget.TextView'
            all_text_elems = driver.xpath(msg_list_xpath).all()
            for elem in all_text_elems:
                try:
                    text = elem.text
                    if not text or len(text.strip()) == 0:
                        continue
                    bounds = elem.info.get('bounds', {})
                    left = bounds.get('left', 0)
                    top = bounds.get('top', 0)
                    if left > half_width:
                        user_msgs.append({'text': text.strip(), 'top': top})
                except Exception:
                    continue
        except Exception:
            pass
        return user_msgs

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        self._log(level='DEBUG', content=f'Getting results from android device: {device_sn}', task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Driver not available for device: {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return {'success': False, 'message': 'Driver not available', 'asr': '', 'translation': ''}

        pre_count = self._pre_msg_count.pop(device_sn, 0)
        pre_texts = self._pre_user_msgs.pop(device_sn, set())

        try:
            max_retries = 5
            retry_interval = 0.5
            user_msg_list = []
            latest_user_text = ''
            prev_candidate = None
            stable_hits = 0

            for attempt in range(max_retries):
                if self._check_stop("get_results"):
                    return {'success': False, 'message': 'Stopped', 'asr': '', 'translation': ''}

                self._scroll_to_bottom(driver)
                user_msg_list = self._collect_user_messages(driver)

                count_changed = len(user_msg_list) > pre_count
                new_msgs = [m for m in user_msg_list if m['text'] not in pre_texts]
                text_changed = len(new_msgs) > 0
                self._log(level='DEBUG', content=f"第{attempt + 1}次轮询: 消息总数={len(user_msg_list)}(快照={pre_count}) 数量变化={count_changed} 文本变化={text_changed}", task_id=task_id, test_case_id=test_case_id)

                if new_msgs:
                    user_msg_sorted = sorted(new_msgs, key=lambda x: x['top'], reverse=True)
                    candidate = user_msg_sorted[0]['text']

                    if candidate:
                        if candidate == prev_candidate:
                            stable_hits += 1
                        else:
                            stable_hits = 1
                            prev_candidate = candidate

                        self._log(level='DEBUG', content=f"候选文本: '{candidate}' 稳定计数: {stable_hits}", task_id=task_id, test_case_id=test_case_id)

                        if stable_hits >= 2:
                            latest_user_text = candidate
                            self._log(level='INFO', content=f"抓取到最新用户消息: {latest_user_text}", task_id=task_id, test_case_id=test_case_id)
                            return {'success': True, 'message': 'Success', 'asr': latest_user_text, 'translation': ''}

                time.sleep(retry_interval)

            self._log(level='WARNING', content=f"轮询{max_retries}次未检测到稳定新消息", task_id=task_id, test_case_id=test_case_id)
            self._scroll_to_bottom(driver)
            user_msg_list = self._collect_user_messages(driver)
            new_msgs = [m for m in user_msg_list if m['text'] not in pre_texts]
            if not new_msgs:
                self._log(level='WARNING', content="未检测到新用户消息，语音可能未被识别", task_id=task_id, test_case_id=test_case_id)
                return {'success': False, 'message': 'No new message detected, speech may not be recognized', 'asr': '', 'translation': ''}

            user_msg_sorted = sorted(new_msgs, key=lambda x: x['top'], reverse=True)
            latest_user_text = user_msg_sorted[0]['text']
            self._log(level='INFO', content=f"回退抓取到新用户消息: {latest_user_text}", task_id=task_id, test_case_id=test_case_id)
            return {'success': True, 'message': 'Success', 'asr': latest_user_text, 'translation': ''}

        except Exception as e:
            self._log(level='ERROR', content=f'Android get_results 捕获全局异常 device {device_sn}: {str(e)}', task_id=task_id, test_case_id=test_case_id)
            return {'success': False, 'message': str(e), 'asr': '', 'translation': ''}
