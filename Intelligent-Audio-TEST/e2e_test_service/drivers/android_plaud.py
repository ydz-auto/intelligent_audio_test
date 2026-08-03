import os
import json
import re
import time
import subprocess
import tempfile
import shutil

try:
    from hypium import MatchPattern
except ImportError:
    MatchPattern = None

from e2e_test_service.config.config import Config
from shared.utils.storage import storage
from .android_driver import AndroidDriver
from .device_config import get_device_config
from .utils import check_stop, u2, log_and_emit, By

LOG_DEVICE_PATH = '/storage/media/100/local/files/Docs/Huawei Share'
LOG_DEVICE_ID = '3QC0124C11000914'


class PlaudDriver(AndroidDriver):
    """Plaud AI 录音应用安卓设备驱动实现"""

    def __init__(self):
        super().__init__()
        self._drivers = {}
        self._config = get_device_config('android')
        self.app_name = 'ai.plaud.android.plaud.zh'
        self._unlock_password = self._config.get('unlock_password', '000000')
        self._close_buttons = self._config.get('close_buttons', [])
        self._popup_keywords = self._config.get('popup_keywords', [])
        self._exclude_list = self._config.get('exclude_list', [])
        self._abnormal_keywords = self._config.get('abnormal_keywords', [])

    def _get_driver(self, device_sn):
        if not u2:
            return None
        if device_sn not in self._drivers:
            try:
                self._drivers[device_sn] = u2.connect(device_sn)
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to connect to android device {device_sn}: {e}")
                return None
        return self._drivers[device_sn]

    def is_locked(self, device_sn):
        """
        判断设备是否锁屏
        """
        try:
            lock_icon_id = "com.android.systemui:id/clock_view_container"
            driver = self._get_driver(device_sn)
            if not driver:
                self._log(level='WARNING', content=f"无法获取设备{device_sn}的驱动，无法检查锁屏状态")
                return False
            driver.screen_on()
            flash_ele = driver(resourceId=f'{lock_icon_id}')

            if flash_ele.exists:
                self._log(level='INFO', content=f"设备{device_sn}已锁屏")
                return True
            return False
        except Exception as e:
            self._log(level='INFO', content=f"设备{device_sn}锁屏检查失败：{e}")
            return False

    @check_stop("unlock")
    def unlock(self, device_sn, **kwargs) -> None:
        """唤醒设备"""
        self._log(level='INFO', content=f"Android device {device_sn} waking up and unlocking...")

        if not self.is_locked(device_sn):
            self._log(level='INFO', content=f"设备{device_sn}已解锁，无需重复解锁")
            return
        if self._check_stop("unlock"):
            return

        self._unlock(device_sn, **kwargs)
        return True

    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化安卓设备"""
        self._log(level='INFO', content=f"Initializing Android device {device_sn} for {self.app_name}...", task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        # 步骤4：清理设备日志
        clean_result = subprocess.run(
            ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'sh', '-c', f"rm -rf '{LOG_DEVICE_PATH}'/*"],
            check=False, capture_output=True, text=True
        )
        self._log(level='INFO', content=f"清理设备日志: {clean_result.stdout}", task_id=task_id, test_case_id=test_case_id)

        if driver:
            try:
                self.unlock(device_sn, **kwargs)
                if self._check_stop("initialize"):
                    return False
                driver.press("home")
                # 检测并关闭弹窗
                self.close_popups(device_sn)
                if self._check_stop("initialize"):
                    return False

                driver.app_stop(self.app_name)
                driver.app_start(self.app_name, stop=True)
                time.sleep(3)
                # 启动应用后再次检查弹窗
                self.close_popups(device_sn)
                self._log(level='INFO', content=f"Android device {device_sn} initialized successfully", task_id=task_id, test_case_id=test_case_id)
                return True
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to start app {self.app_name} on device {device_sn}: {e}", task_id=task_id, test_case_id=test_case_id)
        self._log(level='ERROR', content=f"Failed to initialize Android device {device_sn}: Driver not available", task_id=task_id, test_case_id=test_case_id)
        return False

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开始处理：进入前台等准备动作"""
        self._log(level='INFO', content=f"--- Starting pre-process for Android {device_sn} ---", task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            return False

        driver.click(628, 2617)

        driver.xpath('//*[@content-desc="开始录音"]').click()

        while driver.xpath('//*[@content-desc="开始录音"]').exists and not driver.xpath('//*[@content-desc="录音中"]').exists:
            try:
                driver.xpath('//*[@content-desc="开始录音"]').click(timeout=1)
                time.sleep(0.1)
            except Exception as e:
                self._log(level='INFO', content=f"Failed to click '开始录音' button: {e}", task_id=task_id, test_case_id=test_case_id)

        self._log(level='INFO', content=f"开始录音按钮点击成功", task_id=task_id, test_case_id=test_case_id)

        self.close_popups(device_sn)
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """结束处理"""
        self._log(level='INFO', content=f"--- Finished post-process for Android {device_sn} ---", task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            return False
        driver.xpath('//*[@content-desc="结束"]').click()
        time.sleep(0.1)
        driver.xpath('//*[@content-desc="结束并保存"]').click()
        time.sleep(1)
        while driver.xpath('//*[@content-desc="快传"]').exists:
            time.sleep(1)
        # 点击最新记录
        # driver.xpath(
        #     '//android.view.View[1]/android.view.View[1]/android.view.View[2]/android.widget.ScrollView[1]/android.view.View[1]').click()
        driver.click(1018 / 2, (1256 + 1319) / 2)
        driver.xpath('//*[@content-desc="生成"]').wait(10)
        driver.xpath('//*[@content-desc="生成"]').click()
        driver.xpath('//*[@content-desc="立即生成"]').wait(10)
        while driver.xpath('//*[@content-desc="立即生成"]').exists:
            driver.xpath('//*[@content-desc="立即生成"]').click()
            time.sleep(1)
        driver.app_stop(self.app_name)
        return True

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """获取设备输出结果 - 返回原始文本列表"""
        driver = self._get_driver(device_sn)
        if not driver:
            return False

        time.sleep(2)
        driver.app_start(self.app_name)

        driver.click(1018 / 2, (1256 + 1319) / 2)
        if driver.xpath('//*[@content-desc="生成"]').exists:
            driver.xpath('//*[@content-desc="生成"]').click(timeout=10)
            driver.xpath('//*[@content-desc="立即生成"]').wait(10)
            while driver.xpath('//*[@content-desc="立即生成"]').exists:
                driver.xpath('//*[@content-desc="立即生成"]').click()
                time.sleep(1)

        time.sleep(2)
        last_press_home_time = time.time()
        while driver.xpath('//*[@content-desc="生成还需几分钟，离开页面不会影响进度"]').exists:
            time.sleep(1)
            if time.time() - last_press_home_time >= 5:
                driver.press("home")
                driver.app_stop(self.app_name)
                time.sleep(1)
                driver.app_start(self.app_name)
                time.sleep(1)
                driver.click(1018 / 2, (1256 + 1319) / 2)
                last_press_home_time = time.time()
                driver.xpath('//*[contains(@content-desc,"来源") and contains(@content-desc,"第 1 个标签，共 2 个")]').click()
        driver.xpath('//*[contains(@text, "内容由 AI 生成，仅供参考")]').wait(timeout=5)
        # 要等很久，所以要解锁
        self.unlock(device_sn, **kwargs)
        # 点击导出
        driver.xpath(
            '//android.widget.FrameLayout[1]/android.view.View[1]/android.view.View[1]/android.view.View[1]/android.view.View[1]/android.view.View[1]/android.widget.ImageView[2]').click(
            timeout=10)
        time.sleep(1)
        driver.xpath('(//*[@content-desc="转写"])[2]').click(timeout=10)
        driver.xpath('//*[@content-desc="导出转写"]').wait(timeout=10)

        # driver.xpath('//*[@content-desc="时间戳"]').click()
        # driver.xpath('//*[@content-desc="自动导出说话人"]').click()
        # driver.xpath('//*[@content-desc="导出格式"]').click()
        # driver.xpath('//*[@content-desc="SRT"]').click()
        driver.xpath('//*[@content-desc="导出"]').click(timeout=10)

        #  解锁设备啥的
        from .driver_factory import DeviceDriverFactory
        driver_factory = DeviceDriverFactory()
        share_device = driver_factory.get_driver("harmonyos", ["harden"], device_sn=LOG_DEVICE_ID)
        if not share_device:
            self._log(level='INFO', content=f"分享日志设备未准备: {LOG_DEVICE_ID}", task_id=task_id, test_case_id=test_case_id)
            return False
        # 鸿蒙自动化框架要加载很久
        share_device.unlock(LOG_DEVICE_ID)
        share_device_driver = share_device.get_driver(LOG_DEVICE_ID)
        if share_device_driver.find_component(By.text("华为分享")) and share_device_driver.find_component(
                By.text("接收")):
            share_device_driver.click(By.text('拒绝'))
        # 华为分享到另外的设备
        while not driver.xpath('//*[@text="荣耀分享"]').exists:
            driver.xpath('//*[@content-desc="导出"]').click(timeout=10)
            time.sleep(1)
        driver.xpath('//*[@text="荣耀分享"]').click(timeout=10)

        time.sleep(2)
        element = driver(textContains="MateBook Pro")
        if element.exists:
            element.click(timeout=10)

        if not share_device_driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return None
        while not share_device_driver.find_component(By.text("华为分享")) and not share_device_driver.find_component(
                By.text("接收")):
            time.sleep(1)
        share_device_driver.click(By.text('接收'))

        task_id_path = task_id or kwargs.get('task_id', 'default_task_id')
        test_case_id_path = test_case_id or kwargs.get('test_case_id', 'default_case_id')

        # 改造为 OSS 存储：先写本地临时目录，采集完上传 OSS 后清理本地临时
        local_dir = tempfile.mkdtemp(prefix=f'case_{task_id_path}_{test_case_id_path}_')

        temp_device_path = '/data/local/tmp/srt'
        mkdir_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'mkdir', '-p', temp_device_path]
        self._log(level='INFO', content=f"执行命令: {' '.join(mkdir_cmd)}", task_id=task_id, test_case_id=test_case_id)
        subprocess.run(mkdir_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
        time.sleep(2)
        list_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'sh', '-c', f"ls '{LOG_DEVICE_PATH}'"]
        self._log(level='INFO', content=f"执行命令: {' '.join(list_cmd)}", task_id=task_id, test_case_id=test_case_id)
        list_result = subprocess.run(list_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
        start_time = time.time()
        timeout = 60 * 5
        while list_result.stdout == '' or list_result.stdout is None:
            time.sleep(2)
            list_result = subprocess.run(list_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
            if list_result.returncode != 0:
                self._log(level='ERROR', content=f"列出文件失败：{list_result.stderr}", task_id=task_id, test_case_id=test_case_id)
                return None
            if time.time() - start_time > timeout:
                self._log(level='ERROR', content=f"列出文件超时（{timeout}秒）", task_id=task_id, test_case_id=test_case_id)
                return None

        srt_files = [f.strip() for f in list_result.stdout.split('\n') if f.strip().endswith('.srt')]
        if not srt_files:
            self._log(level='WARNING', content=f"未找到.srt文件", task_id=task_id, test_case_id=test_case_id)
            return None
        temp_srt_name = f'{test_case_id_path}.srt'
        srt_file_path = os.path.join(local_dir, temp_srt_name)

        copy_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'sh', '-c',
                    f"cd '{LOG_DEVICE_PATH}' && cp *.srt {temp_device_path}"]
        self._log(level='INFO', content=f"执行命令: {' '.join(copy_cmd)}", task_id=task_id, test_case_id=test_case_id)
        copy_result = subprocess.run(copy_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
        recv_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'file', 'recv', f'{temp_device_path}/{srt_files[0]}',
                    os.path.join(local_dir, temp_srt_name)]
        self._log(level='INFO', content=f"执行命令: {' '.join(recv_cmd)}", task_id=task_id, test_case_id=test_case_id)
        recv_result = subprocess.run(recv_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
        if 'Fail' in recv_result.stdout or recv_result.returncode != 0:
            self._log(level='ERROR', content=f"日志拉取失败：{recv_result.stderr}", task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='INFO', content=f"日志拉取成功: {temp_srt_name}", task_id=task_id, test_case_id=test_case_id)

        rm_temp_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'rm', '-rf', temp_device_path]
        self._log(level='INFO', content=f"执行命令: {' '.join(rm_temp_cmd)}", task_id=task_id, test_case_id=test_case_id)
        subprocess.run(rm_temp_cmd, check=False, capture_output=True, text=True, encoding='utf-8')

        clean_shell_cmd = f"rm -rf '{LOG_DEVICE_PATH}'/*"
        clean_cmd = ['hdc', '-t', LOG_DEVICE_ID, 'shell', 'sh', '-c', clean_shell_cmd]
        self._log(level='INFO', content=f"执行命令: {' '.join(clean_cmd)}", task_id=task_id, test_case_id=test_case_id)
        clean_result = subprocess.run(clean_cmd, check=False, capture_output=True, text=True, encoding='utf-8')
        self._log(level='INFO', content=f"清理设备日志: {clean_result.stdout}", task_id=task_id, test_case_id=test_case_id)

        recording_stm_content, recording_rttm_content, recording_asr_content = self._parse_srt_to_stm_rttm(
            srt_file_path)

        recording_stm_path = os.path.join(local_dir, "recording.stm")
        recording_rttm_path = os.path.join(local_dir, "recording.rttm")

        with open(recording_stm_path, "w", encoding="utf-8") as f:
            f.write(recording_stm_content)
        with open(recording_rttm_path, "w", encoding="utf-8") as f:
            f.write(recording_rttm_content)

        self._log(level='INFO', content=f"STM/RTTM 文件已保存", task_id=task_id, test_case_id=test_case_id)

        # 采集完后上传到 OSS，然后清理本地临时目录
        oss_key_prefix = f'{task_id_path}/{test_case_id_path}/{device_sn}'
        for fname in os.listdir(local_dir):
            storage.save_file(os.path.join(local_dir, fname), 'case_result',
                             f'{oss_key_prefix}/{fname}')
        shutil.rmtree(local_dir, ignore_errors=True)

        return [
            {
                "result_type": "non-real-time",
                "success": True,
                "message": "Success",
                "recording_stm_path": recording_stm_path,
                "recording_stm_content": recording_stm_content,
                "recording_rttm_path": recording_rttm_path,
                "recording_rttm_content": recording_rttm_content,
                "recording_asr_path": srt_file_path,
                "recording_asr_content": recording_asr_content,
                "log_path": local_dir,
                "oss_prefix": oss_key_prefix,  # OSS key 前缀
                "local_dir": None,  # 已清理本地临时目录，保留字段兼容旧调用
            }
        ]

    def _parse_srt_to_stm_rttm(self, srt_file_path):
        """解析SRT文件，生成STM、RTTM和ASR内容"""
        import re

        stm_lines = []
        rttm_lines = []
        asr_data = []

        file_id = os.path.splitext(os.path.basename(srt_file_path))[0]

        try:
            with open(srt_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self._log(level='ERROR', content=f"读取SRT文件失败: {str(e)}")
            return "", "", ""

        blocks = content.strip().split('\n\n')

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            try:
                index = lines[0].strip()
                time_line = lines[1].strip()
                text = '\n'.join(lines[2:]).strip()
            except:
                continue

            if not text or '【内容由 AI 生成' in text:
                continue

            match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
            if not match:
                continue

            start_h, start_m, start_s, start_ms = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(
                match.group(4))
            end_h, end_m, end_s, end_ms = int(match.group(5)), int(match.group(6)), int(match.group(7)), int(
                match.group(8))

            start_sec = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
            end_sec = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
            duration = end_sec - start_sec

            speaker_match = re.match(r'(Speaker \d+):(.+)', text)
            if speaker_match:
                speaker = speaker_match.group(1).replace('Speaker ', 'speaker')
                text = speaker_match.group(2).strip()
            else:
                speaker = "speaker1"

            stm_line = f"{file_id} 1 {speaker} {start_sec:.3f} {end_sec:.3f} {text}"
            stm_lines.append(stm_line)

            rttm_line = f"SPEAKER {file_id} 1 {start_sec:.3f} {duration:.3f} <NA> <NA> {speaker} <NA>"
            rttm_lines.append(rttm_line)

            asr_data.append({
                "text": text,
                "speakerId": int(speaker.replace('speaker', '')) if speaker.replace('speaker', '').isdigit() else 1,
                "startMilliseconds": int(start_sec * 1000),
                "endMilliseconds": int(end_sec * 1000),
            })

        recording_stm_content = '\n'.join(stm_lines)
        recording_rttm_content = '\n'.join(rttm_lines)
        recording_asr_content = json.dumps(asr_data, ensure_ascii=False)

        return recording_stm_content, recording_rttm_content, recording_asr_content

    def extract_results_from_archive(self, task_id, test_case_id, device_sn, **kwargs):
        """从存档SRT文件提取设备输出结果

        Args:
            task_id: 任务ID
            test_case_id: 用例ID
            device_sn: 设备序列号

        Returns:
            dict: 包含提取结果的字典，格式如下:
                {
                    'recording_stm_content': str,
                    'recording_rttm_content': str,
                    'recording_asr_content': str,
                    'local_dir': str,
                    'success': bool,
                    'message': str
                }
        """
        # 改造为 OSS 存储：从 OSS 下载 srt 到本地临时，解析后写 stm/rttm 上传 OSS，清理本地临时
        oss_key_prefix = f'{task_id}/{test_case_id}/{device_sn}'
        srt_oss_key = f'{oss_key_prefix}/{test_case_id}.srt'
        local_dir = tempfile.mkdtemp(prefix=f'archive_{task_id}_{test_case_id}_')
        srt_file_path = os.path.join(local_dir, f'{test_case_id}.srt')
        try:
            storage.load_file(f'case_result/{srt_oss_key}', srt_file_path)
        except Exception as e:
            shutil.rmtree(local_dir, ignore_errors=True)
            self._log(level='ERROR', content=f"从OSS下载存档SRT失败: {srt_oss_key}, error: {e}", task_id=task_id, test_case_id=test_case_id)
            return {
                'success': False,
                'message': f'存档SRT文件不存在(OSS): {srt_oss_key}',
                'local_dir': None,
                'oss_prefix': oss_key_prefix,
            }

        self._log(level='INFO', content=f"从存档提取SRT结果，OSS key: {srt_oss_key}", task_id=task_id, test_case_id=test_case_id)

        if not os.path.exists(srt_file_path):
            shutil.rmtree(local_dir, ignore_errors=True)
            self._log(level='ERROR', content=f"存档SRT文件不存在: {srt_file_path}", task_id=task_id, test_case_id=test_case_id)
            return {
                'success': False,
                'message': f'存档SRT文件不存在: {srt_file_path}',
                'local_dir': None,
                'oss_prefix': oss_key_prefix,
            }

        recording_stm_content, recording_rttm_content, recording_asr_content = self._parse_srt_to_stm_rttm(srt_file_path)

        if not recording_stm_content:
            shutil.rmtree(local_dir, ignore_errors=True)
            self._log(level='WARNING', content=f"SRT文件解析结果为空: {srt_file_path}", task_id=task_id, test_case_id=test_case_id)
            return {
                'success': False,
                'message': f'SRT文件解析结果为空: {srt_file_path}',
                'local_dir': None,
                'oss_prefix': oss_key_prefix,
            }

        recording_stm_path = os.path.join(local_dir, "recording.stm")
        recording_rttm_path = os.path.join(local_dir, "recording.rttm")

        # 写 stm/rttm 后上传 OSS，再清理本地临时
        with open(recording_stm_path, "w", encoding="utf-8") as f:
            f.write(recording_stm_content)
        with open(recording_rttm_path, "w", encoding="utf-8") as f:
            f.write(recording_rttm_content)

        for fname in os.listdir(local_dir):
            storage.save_file(os.path.join(local_dir, fname), 'case_result',
                             f'{oss_key_prefix}/{fname}')
        shutil.rmtree(local_dir, ignore_errors=True)

        self._log(level='INFO', content=f"成功从存档提取SRT结果，STM行数: {len(recording_stm_content.split(chr(10)))}", task_id=task_id, test_case_id=test_case_id)

        return [{
            'success': True,
            'message': '从存档SRT提取成功',
            'recording_stm_content': recording_stm_content,
            'recording_rttm_content': recording_rttm_content,
            'recording_asr_content': recording_asr_content,
            'local_dir': None,  # 已清理本地临时目录，保留字段兼容旧调用
            'oss_prefix': oss_key_prefix,
            'recording_stm_path': recording_stm_path,
            'recording_rttm_path': recording_rttm_path,
            'recording_asr_path': srt_file_path,
            'stm_res': recording_stm_content,
            'rttm_res': recording_rttm_content,
            'asr_result': recording_asr_content,
        }]
