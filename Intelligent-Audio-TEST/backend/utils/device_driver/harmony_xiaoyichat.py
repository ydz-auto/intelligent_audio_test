import time
import subprocess
import os
import re

from hypium.model import UiParam

from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from config.config import Config
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT

class Xiaoyilivechat(HarmonyDriver):
    RECORDER_BUNDLE = 'com.huawei.hmos.screenrecorder'
    RECORDER_ABILITY = 'com.huawei.hmos.screenrecorder.ServiceExtAbility'

    def _mp4_to_wav(self, mp4_path, task_id=None, test_case_id=None):
        """将 mp4 无损转换为 wav（pcm_s16le，44.1kHz，双声道）。
        成功返回 wav 绝对路径，失败返回 None。"""
        if not os.path.exists(mp4_path):
            return None
        wav_path = os.path.splitext(mp4_path)[0] + '.wav'
        cmd = [Config.FFMPEG_PATH, '-y', '-i', mp4_path,
               '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav_path]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(wav_path):
                self._log(level='ERROR',
                          content=f"mp4转wav失败: {r.stderr[-500:] if r.stderr else ''}",
                          task_id=task_id, test_case_id=test_case_id)
                return None
            self._log(level='INFO', content=f"mp4转wav成功: {wav_path}",
                      task_id=task_id, test_case_id=test_case_id)
            return wav_path
        except Exception as e:
            self._log(level='ERROR', content=f"mp4转wav异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _hdc_shell(self, device_sn, *args):
        return subprocess.run(
            ['hdc', '-t', device_sn, 'shell'] + list(args),
            check=False, capture_output=True, text=True, timeout=10
        )

    def _list_device_mp4_set(self, device_sn):
        """获取设备录屏目录下所有 mp4 文件路径集合（用于区分新增文件）"""
        r = self._hdc_shell(
            device_sn, 'find', '/storage/media/100/local/files/Photo',
            '-name', '*.mp4', '-type', 'f'
        )
        if r.returncode != 0:
            return set()
        return {line.strip() for line in (r.stdout or '').splitlines() if line.strip()}

    def _get_device_file_size(self, device_sn, device_path):
        """获取设备上指定文件大小（字节），不存在返回 -1"""
        r = self._hdc_shell(device_sn, 'stat', '-c', '%s', device_path)
        if r.returncode != 0:
            return -1
        try:
            return int(r.stdout.strip())
        except Exception:
            return -1

    def _is_recorder_running(self, device_sn):
        """检查 screenrecorder 服务是否正在运行"""
        result = self._hdc_shell(device_sn, 'aa', 'dump', '-l')
        if result.returncode != 0:
            return False
        # 服务运行时 dump 输出会包含 bundle 名称
        return self.RECORDER_BUNDLE in (result.stdout or '')

    def _start_recorder(self, device_sn, file_name=None):
        """启动录屏服务

        说明: aa dump -l 的输出与录屏服务是否真正在前台运行并非严格对应,
        用它做二次校验会把已成功启动的录屏误判为"未运行", 从而导致整个用例失败。
        这里改为以 aa start 命令本身的返回码为准: 命令执行成功即视为启动成功,
        录屏是否真正生效交给后续 post_process 的等待逻辑兜底。

        时延测量:
        - first_frame_ms: 首帧真正写入时刻（轮询文件 size 从 0 变非0）
          录屏录制的即模型回复内容, first_frame_ms 即模型回复起始时刻
        """
        # 记录 aa start 前已存在的 mp4 集合
        existing_paths = self._list_device_mp4_set(device_sn)

        args = ['aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY]
        if file_name:
            args += ['--ps', 'CustomizedFileName', file_name]
        result = self._hdc_shell(device_sn, *args)
        if result.returncode != 0:
            self._recorder_first_frame_ms = None
            return False

        # 轮询：发现新文件 + 等待首帧写入（size 从 0 变非0）
        first_frame_ms = None
        deadline = int(time.time() * 1000) + 30000  # 30 秒超时
        while int(time.time() * 1000) < deadline:
            current_paths = self._list_device_mp4_set(device_sn)
            new_paths = current_paths - existing_paths
            if new_paths:
                new_path = next(iter(new_paths))
                size = self._get_device_file_size(device_sn, new_path)
                if size > 0:
                    first_frame_ms = int(time.time() * 1000)
                    break
            time.sleep(0.1)

        self._recorder_first_frame_ms = first_frame_ms
        return True

    def _stop_recorder(self, device_sn):
        """停止录屏服务

        说明: 与 _start_recorder 同理, aa dump -l 的二次校验不可靠,
        这里直接以 toggle 命令执行成功为准; 真正的兜底放在 teardown 中按
        _recording 标志位判断, 避免对已停止的录屏再次 toggle 反而打开。
        """
        self._hdc_shell(device_sn, 'aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY)
        return True

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


        return True

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
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
        # 开启录屏（文件名含轮次号，避免多轮冲突）
        round_number = kwargs.get('round_number', 0)
        self._record_file_name = f"{test_case_id}_r{round_number}.mp4"
        if not self._start_recorder(device_sn, file_name=self._record_file_name):
            self._log(level='ERROR', content=f"启动录屏失败,服务未运行: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        self._recording = True
        self._log(level='INFO', content=f"启动录屏成功: {self._record_file_name}", task_id=task_id,
                  test_case_id=test_case_id)
        time.sleep(2)
        return True

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        # 打印接收到的播放时间戳（验证链路）
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']} "
                          f"detail_count={len(ts['detail']) if ts['detail'] else 0})",
                  task_id=task_id, test_case_id=test_case_id)
        # 等待小艺回复结束（带超时和停止检查）
        self._wait_for_condition(
            lambda: driver.find_component(By.text('说话可打断')),
            timeout=60, interval=1, operation_name="post_process_说话可打断"
        )
        self._wait_for_condition(
            lambda: driver.find_component(By.text('正在听…')),
            timeout=60, interval=1, operation_name="post_process_正在听"
        )
        # 停止录屏
        if not self._stop_recorder(device_sn):
            self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
        self._recording = False
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
        # 提取聊天文本，取最后一条（本轮），未识别到则返回 None
        question_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Row/Text'))
        self._log(level='DEBUG', content=f"question_components count={len(question_components) if question_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if question_components:
            for i, comp in enumerate(question_components):
                self._log(level='DEBUG', content=f"question_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.question_text = question_components[-1].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Column//Stack/Text'))
        self._log(level='DEBUG', content=f"answer_components count={len(answer_components) if answer_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if answer_components:
            for i, comp in enumerate(answer_components):
                self._log(level='DEBUG', content=f"answer_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.answer_text = answer_components[-1].getText() if answer_components else None

        return True

    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> list:
        # 打印接收到的播放时间戳（验证链路）
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[get_results] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']} "
                          f"detail_count={len(ts['detail']) if ts['detail'] else 0})",
                  task_id=task_id, test_case_id=test_case_id)
        record_file_name = getattr(self, '_record_file_name', 'record.mp4')
        question_text = getattr(self, 'question_text', None)
        answer_text = getattr(self, 'answer_text', None)
        first_frame_ms = getattr(self, '_recorder_first_frame_ms', None)
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
                    'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text or '',
                'answer': answer_text or ''
                }
                return [result]
            # mp4 无损转 wav
            wav_path = self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
            print(f"[录屏] mp4 路径: {local_path}")
            print(f"[录屏] wav 路径: {wav_path}")
            result = {
                'success': True,
                'message': 'Success',
                'record_path': local_path,
                'wav_path': wav_path or '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
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
                'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': "",
                'answer': ""
            }
            return [result]

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束后清理设备状态（与 initialize 对称）

        做以下清理：
        1. 确保录屏已停止（兜底，防止 post_process 异常残留）
        2. 确保通话已挂断（兜底）
        3. 退出小艺聊天界面，回桌面
        """
        # 1. 兜底停止录屏（仅在仍在录屏时执行，避免 toggle 把已停止的录屏又打开）
        if getattr(self, '_recording', False):
            try:
                if not self._stop_recorder(device_sn):
                    self._log(level='WARNING', content="teardown: 兜底停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='DEBUG', content="teardown: 兜底停止录屏成功",
                              task_id=task_id, test_case_id=test_case_id)
                self._recording = False
            except Exception as e:
                self._log(level='WARNING', content=f"teardown: 停止录屏失败: {e}", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            return True

        # 2. 兜底挂断通话
        try:
            hangup_btn = driver.find_component(
                By.isAfter(By.key('live.tool_bar.hangup_button')).isBefore(By.key('GuideText')).type('SymbolGlyph'))
            if hangup_btn:
                hangup_btn.click()
                self._log(level='DEBUG', content="teardown: 挂断残留通话", task_id=task_id, test_case_id=test_case_id)
                time.sleep(2)
        except Exception as e:
            self._log(level='DEBUG', content=f"teardown: 无残留通话或挂断失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # 3. 回桌面（退出小艺聊天界面）
        try:
            driver.press_home(2)
            time.sleep(1)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 回桌面失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # 4. 停止小艺 APP（彻底释放）
        try:
            driver.stop_app(self.app_name)
            self._log(level='DEBUG', content="teardown: 已停止小艺 APP", task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止小艺 APP 失败: {e}", task_id=task_id, test_case_id=test_case_id)

        return True
