import time
import subprocess
import os
import re

from hypium.model import UiParam

from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from config.config import Config

_RECORDER_BUNDLE = 'com.huawei.hmos.screenrecorder'
_RECORDER_ABILITY = 'com.huawei.hmos.screenrecorder.ServiceExtAbility'


class Xiaoyilivechat(HarmonyDriver):

    def _hdc_shell(self, device_sn, *args):
        return subprocess.run(
            ['hdc', '-t', device_sn, 'shell'] + list(args),
            check=False, capture_output=True, text=True, timeout=10
        )

    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        if not super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs):
            return False
        driver = self._get_driver(device_sn)
        if not driver:
            return False
        # 点开小艺聊天窗口
        user_center = driver.find_component(By.text("小艺"))
        if user_center:
            user_center.click()
            time.sleep(2)
        # 清除上下文
        # 进入设置界面
        driver.touch(By.isAfter(By.type('Image')).isBefore(By.key('water_mark.build.stack')).type('SymbolGlyph'))
        driver.wait(2)
        clear_text = driver.find_component(By.text('清除上下文'))
        if clear_text:
            clear_text.click()
            time.sleep(2)
        # 进入设置界面删除对话记录
        driver.touch(By.isAfter(By.type('Image')).isBefore(By.key('water_mark.build.stack')).type('SymbolGlyph'))
        driver.wait(2)
        driver.swipe(UiParam.UP, 30, side=UiParam.LEFT)
        clear_chat = driver.find_component(By.text("删除对话记录"))
        if clear_chat:
            clear_chat.click()
            time.sleep(1)
            # 确认删除
            delete_button = driver.find_component(By.text("删除"))
            if delete_button:
                delete_button.click()
                time.sleep(1)

        # 开启通话聊天

        driver.touch(By.isAfter(By.key('ChatTitleMenu')).isBefore(By.key('title_bar.broadcastType.icon')).type(
            'SymbolGlyph'))
        driver.wait(2)
        try:
            if driver.find_component(By.text("小艺")):
                self._log(level='DEBUG', content="成功进行通话", task_id=task_id, test_case_id=test_case_id)
        except Exception:
            self._log(level='ERROR', content="通话失败", task_id=task_id, test_case_id=test_case_id)
            return False
        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)

        # 开启录屏
        self._record_file_name = f"{test_case_id}.mp4"
        self._hdc_shell(device_sn, 'aa', 'start', '-b', _RECORDER_BUNDLE, '-a', _RECORDER_ABILITY,
                        '--ps', 'CustomizedFileName', self._record_file_name)
        self._log(level='INFO', content=f"启动录屏: {self._record_file_name}", task_id=task_id,
                  test_case_id=test_case_id)
        time.sleep(2)
        return True

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        # 等待小艺回复结束（"正在听…"出现表示回复完毕）
        while not driver.find_component(By.text('说话可打断')):
            time.sleep(1)
        while not driver.find_component(By.text('正在听…')):
            time.sleep(1)
        # 停止录屏
        self._hdc_shell(device_sn, 'aa', 'start', '-b', _RECORDER_BUNDLE, '-a', _RECORDER_ABILITY)
        self._log(level='INFO', content="停止录屏", task_id=task_id, test_case_id=test_case_id)
        time.sleep(5)
        # 通话挂断
        try:
            hangup_btn = driver.find_component(
                By.isAfter(By.key('live.tool_bar.hangup_button')).isBefore(By.key('GuideText')).type('SymbolGlyph'))
            if hangup_btn:
                hangup_btn.click()
        except Exception as e:
            self._log(level='WARNING', content=f"挂断通话失败: {e}", task_id=task_id, test_case_id=test_case_id)
        driver.wait(5)
        # 提取聊天文本，未识别到则返回 None
        question_components = driver.find_all_components(By.xpath(
            '/root/Navigation/NavigationContent/NavDestination/NavDestinationContent/Stack/Stack[1]/Column/Stack/Stack/RelativeContainer/__Common__[2]/Column/Stack/Stack/__Common__/Stack/List/ListItem/Row/Row/Row/GridRow/GridCol/Row/__Common__/__Common__/Row/Text'))
        self.question_text = question_components[0].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(
            '/root/Navigation/NavigationContent/NavDestination/NavDestinationContent/Stack/Stack[1]/Column/Stack/Stack/RelativeContainer/__Common__[2]/Column/Stack/Stack/__Common__/Stack/List/ListItem/Row/Row/Row/GridRow/GridCol/Row/__Common__/__Common__/Column/Column/Stack/Stack/Stack/Row/Column/__Common__/Column/List/ListItem/Stack/__Common__/Stack/Text'))
        self.answer_text = answer_components[0].getText() if answer_components else None

        return True

    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> list:
        record_file_name = getattr(self, '_record_file_name', 'record.mp4')
        question_text = getattr(self, 'question_text', None)
        answer_text = getattr(self, 'answer_text', None)
        try:
            query = self._hdc_shell(device_sn, 'mediatool', 'query', record_file_name, '-u')
            lines = query.stdout.strip().split('\n')
            device_path = lines[1].strip() if len(lines) > 1 else ''
            if 'uri' in query.stdout and len(lines) > 2:
                subprocess.run(
                    ['hdc', '-t', device_sn, 'shell', 'mediatool', 'recv', lines[2].strip(), '/data/local/tmp'],
                    check=False, capture_output=True, text=True, timeout=120
                )
                device_path = f'/data/local/tmp/{record_file_name}'
            local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result',
                                     str(task_id) if task_id else 'default_task_id',
                                     str(test_case_id) if test_case_id else 'default_id', device_sn)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, record_file_name)
            recv_result = subprocess.run(['hdc', '-t', device_sn, 'file', 'recv', device_path, local_path],
                                         check=False, capture_output=True, text=True, timeout=120)
            if not os.path.exists(local_path):
                self._log(level='ERROR', content=f"录屏文件拉取失败: {recv_result.stderr}",
                          task_id=task_id, test_case_id=test_case_id)
                result = {
                    'success': False,
                    'message': f'录屏文件拉取失败: {recv_result.stderr}',
                    'record_path': '',
                    'question': question_text or '',
                    'answer': answer_text or ''
                }
                return [result]
            result = {
                'success': True,
                'message': 'Success',
                'record_path': local_path,
                'question': question_text,
                'answer': answer_text
            }
            return [result]
        except Exception as e:
            self._log(level='ERROR', content=f"获取录屏文件失败: {e}", task_id=task_id, test_case_id=test_case_id)
            result = {
                'success': False,
                'message': str(e),
                'record_path': '',
                'question': "",
                'answer': ""
            }
            return [result]
