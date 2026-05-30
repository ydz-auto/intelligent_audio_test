import time
import subprocess
import os
import re
from .base_driver import BaseDeviceDriver
from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from config.config import Config

# 日志目录路径
LOG_DEVICE_PATH = "/data/app/el2/100/base/com.huawei.hmos.vassistant/haps/voice_pc/files/log"


class HarmonyHardenXiaoyiHuiJiDriver(HarmonyDriver):
    """鸿蒙harden小艺慧记驱动"""

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
        """初始化小艺慧记设备"""
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...", task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False
_device_id
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
            time.sleep(0.1)
            driver.click(By.key('PluginRootComponent_Stack_status_bar_control_center'))
            # 点击小艺慧记
            driver.click(By.key('Ctrl.NewToggleBaseComponent_Image_meeting'))
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"打开{device_sn}小艺慧记失败：{e}", task_id=task_id, test_case_id=test_case_id)
            return False

    @check_stop("pre_process")
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
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """结束处理：清理或日志记录"""
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False
        try:
            driver.click(By.xpath('//Row/__Common__/Row/Button[2]/Image'))
            time.sleep(0.1)
            driver.click(By.xpath('//Dialog/Column/Column/Column[1]/Row[2]/Checkbox'))
            driver.click(By.text('结束并保存'))
            while driver.find_component(By.text('正在保存')):
                time.sleep(1)
            return True

        except Exception as e:
            self._log(level='INFO', content=f": 结束{device_sn} 小艺慧记 失败{e}", task_id=task_id, test_case_id=test_case_id)
            return False

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """
        获取设备输出结果 - 返回原始文本、音频列表
        """
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False

        def sanitize_path(s):
            return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))

        case_name = sanitize_path(kwargs.get('case_name', 'default_case'))
        task_id_path = sanitize_path(task_id or kwargs.get('task_id', 'default_task_id'))
        test_case_id_path = test_case_id or kwargs.get('test_case_id', 'default_id')

        local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result', f'{task_id_path}', f'{test_case_id_path}', f'{device_sn}')

        while driver.find_component(By.text('正在保存')):
            time.sleep(1)
        time.sleep(3)
        # 点击记录
        driver.click(By.xpath('//Row/__Common__/__Common__/Row/Column/Row'))
        # 点击工具栏
        while driver.find_component(
                By.xpath('//NavDestinationContent/Stack/Column/Row/__Common__[2]/Column/Image')) is None:
            time.sleep(1)
        driver.click(By.xpath('//NavDestinationContent/Stack/Column/Row/__Common__[2]/Column/Image'))
        # 点击导出文件至本地
        time.sleep(1)
        driver.click(By.text('导出文件至本地'))
        time.sleep(1)
        if driver.find_component(By.text('同意')):
            driver.click(By.text('同意'))
        time.sleep(1)
        # file_name_ele.inputText(f'{test_case_id}_{file_name[-18:]}')
        # 获取文件路径
        # driver.find_component(By.xpath('//SideBarContainer/Column/Row[2]/Row[3]/Row[1]/Flex/Row/Blank')).click()
        # file_root_path = driver.find_component(By.xpath('//Column/Row[1]/Row[3]/Row[1]/TextInput')).text
        file_real_path = '/storage/media/100/local/files/Docs/Desktop'

        while not driver.find_component(By.text('安全访问文件')):
            time.sleep(1)
        file_name_ele = driver.find_component(By.key(
            'pickerFileNameTextInput'))
        file_name = file_name_ele.getText()
        self._log(level='INFO', content=f"新文件名: {file_name}", task_id=task_id, test_case_id=test_case_id)
        # 点击 保存
        driver.click(By.text('保存'))

        # 拉取文件到本地
        def file_pull(device_sn, file_name, file_real_path, case_name, test_case_id):
            try:
                os.makedirs(local_dir, exist_ok=True)

                self._log(level='INFO', content=f"拉取日志，源: {LOG_DEVICE_PATH}", task_id=task_id, test_case_id=test_case_id)

                recv_result = subprocess.run(
                    ['hdc', '-t', device_sn, 'file', 'recv', LOG_DEVICE_PATH, local_dir],
                    check=False, capture_output=True, text=True
                )

                if 'Fail' in recv_result.stdout:
                    self._log(level='ERROR', content=f"日志拉取失败：{recv_result.stderr}", task_id=task_id, test_case_id=test_case_id)
                    return None

                self._log(level='INFO', content=f"日志拉取成功: {recv_result.stdout}", task_id=task_id, test_case_id=test_case_id)

                clean_result = subprocess.run(
                    ['hdc', '-t', device_sn, 'shell', 'rm', '-rf', f'{LOG_DEVICE_PATH}/*'],
                    check=False, capture_output=True, text=True
                )
                self._log(level='INFO', content=f"清理设备日志: {clean_result.stdout}", task_id=task_id, test_case_id=test_case_id)

                self._log(level='INFO', content=f"文件名", task_id=task_id, test_case_id=test_case_id)
                shell_commands = f"cp {file_real_path}/*{file_name[-18:]} /data/local/tmp/test.zip"
                self._log(level='INFO', content=f"复制最新的小艺慧记zip文件到临时目录:{shell_commands}", task_id=task_id, test_case_id=test_case_id)
                result = subprocess.run(['hdc', '-t', device_sn, 'shell', 'sh', '-c', shell_commands], check=False,
                                        capture_output=True, text=True)

                if 'bad' in result.stdout:
                    self._log(level='WARNING', content=f"文件复制到临时目录失败：{result.stdout}", task_id=task_id, test_case_id=test_case_id)
                    shell_commands = f"cp {file_real_path}/{file_name} /data/local/tmp/test.zip"
                    subprocess.run(['hdc', '-t', device_sn, 'shell', 'sh', '-c', shell_commands], check=False,
                                   capture_output=True, text=True)

                if case_name and test_case_id:
                    local_file_name = f"{test_case_id}.zip"
                else:
                    local_file_name = "test.zip"
                local_file_path = os.path.join(local_dir, local_file_name)
                local_file_path = os.path.abspath(local_file_path)
                self._log(level='INFO', content=f"拉取文件，源: /data/local/tmp/test.zip, 目标: {local_file_path}", task_id=task_id, test_case_id=test_case_id)

                recv_result = subprocess.run(
                    ['hdc', '-t', device_sn, 'file', 'recv', '/data/local/tmp/test.zip', local_file_path],
                    check=False, capture_output=True, text=True)
                if 'Fail' in recv_result.stdout:
                    self._log(level='ERROR', content=f"文件拉取失败：{recv_result.stderr}", task_id=task_id, test_case_id=test_case_id)
                    return None
                else:
                    self._log(level='INFO', content=f"文件拉取成功：{file_name} -> {local_file_path}", task_id=task_id, test_case_id=test_case_id)

                subprocess.run(['hdc', '-t', device_sn, 'shell', 'rm', '/data/local/tmp/test.zip'], check=False,
                               capture_output=True, text=True)

                return local_dir
            except Exception as e:
                import traceback
                self._log(level='ERROR', content=f"文件拉取失败：{e}, traceback: {traceback.format_exc()}", task_id=task_id, test_case_id=test_case_id)
                return None

        pull_result = file_pull(device_sn, file_name, file_real_path, case_name, test_case_id)

        if pull_result is None:
            return [{
                "result_type": "real-time",
                "success": False,
                "message": "文件拉取失败",
            }, {
                "result_type": "non-real-time",
                "success": False,
                "message": "文件拉取失败",
            }]

        process_results = self.extract_results_from_archive(task_id, test_case_id, device_sn, **kwargs)
        return process_results

    def extract_results_from_archive(self, task_id, test_case_id, device_sn, **kwargs):
        """从存档日志文件提取设备输出结果

        Args:
            task_id: 任务ID
            test_case_id: 用例ID
            device_sn: 设备序列号

        Returns:
            dict: 包含提取结果的字典，格式如下:
                {
                    'recording_stm_content': str,
                    'recording_rttm_content': str,
                    'fix_stm_content': str,
                    'fix_rttm_content': str,
                    'fix_asr_content': str,
                    'local_dir': str,
                    'success': bool,
                    'message': str
                }
        """
        import json
        import re
        from pathlib import Path

        def sanitize_path(s):
            return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))

        task_id_sanitized = sanitize_path(task_id)
        case_id_sanitized = sanitize_path(test_case_id)

        local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result', f'{task_id_sanitized}', f'{case_id_sanitized}', f'{device_sn}')
        log_dir = Path(local_dir) / "log"

        self._log(level='INFO', content=f"从存档提取结果，路径: {log_dir}", task_id=task_id, test_case_id=test_case_id)

        if not log_dir.exists():
            self._log(level='ERROR', content=f"存档日志目录不存在: {log_dir}", task_id=task_id, test_case_id=test_case_id)
            return {
                'success': False,
                'message': f'存档日志目录不存在: {log_dir}',
                'local_dir': local_dir
            }

        asr_files = list(log_dir.glob("asr-*.txt"))

        def select_best_file(files):
            if not files:
                return None
            if len(files) == 1:
                return files[0]
            files_sorted = sorted(files, key=lambda f: f.stat().st_size, reverse=True)
            for f in files_sorted:
                if f.stat().st_size > 0:
                    try:
                        with open(f, "r", encoding="utf-8") as fp:
                            content = fp.read().strip()
                        if content and content != "[]":
                            return f
                    except:
                        pass
            return files_sorted[0] if files_sorted else None

        def ms10_to_seconds(ms):
            return ms / 100.0

        def ms_to_seconds(ms):
            return ms / 1000.0

        def extract_stm_from_asr(filepath, file_id, asr_type="final"):
            stm_lines = []
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\s*pauseTime:\d+   parseAsrResponse:\s*\n\s*(\s*\{[\s\S]*?\})\s*(?=\n|$)'
            matches = re.finditer(pattern, content)
            for match in matches:
                log_ts_str = match.group(1).strip()
                json_str = match.group(2).strip()
                try:
                    json_obj = json.loads(json_str)
                    json_asr_type = json_obj.get("asrType", "")
                    if asr_type == "final":
                        if json_asr_type != "final":
                            continue
                        directives = json_obj.get("asrResult", {}).get("directives", [])
                        for directive in directives:
                            payload = directive.get("payload", {})
                            speaker_info = payload.get("speakerInfo", [])
                            for item in speaker_info:
                                speaker = item.get("speaker", "unknown")
                                word = item.get("word", "").strip()
                                vad_info = item.get("vadInfo", {})
                                start_ms = int(vad_info.get("start_of_speech", 0))
                                end_ms = int(vad_info.get("end_of_speech", 0))
                                if word and end_ms > start_ms:
                                    start_sec = ms10_to_seconds(start_ms)
                                    end_sec = ms10_to_seconds(end_ms)
                                    stm_line = f"{file_id} 1 speaker{speaker} {start_sec:.3f} {end_sec:.3f} {word}"
                                    stm_lines.append(stm_line)
                    elif asr_type == "vprFix":
                        if json_asr_type != "vprFix":
                            continue
                        directives = json_obj.get("asrResult", {}).get("directives", [])
                        for directive in directives:
                            payload = directive.get("payload", {})
                            speak_info = payload.get("content", {}).get("speakInfo", [])
                            if not speak_info:
                                speak_info = payload.get("speakInfo", [])
                            for item in speak_info:
                                speaker = item.get("speaker", "unknown")
                                word = item.get("word", "").strip()
                                vad_info = item.get("vadInfo", {})
                                start_ms = int(vad_info.get("start_of_speech", 0))
                                end_ms = int(vad_info.get("end_of_speech", 0))
                                if word and end_ms > start_ms:
                                    start_sec = ms10_to_seconds(start_ms)
                                    end_sec = ms10_to_seconds(end_ms)
                                    stm_line = f"{file_id} 1 speaker{speaker} {start_sec:.3f} {end_sec:.3f} {word}"
                                    stm_lines.append(stm_line)
                except:
                    pass
            return stm_lines

        def extract_rttm_from_asr(filepath, file_id, asr_type="final"):
            rttm_lines = []
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\s*pauseTime:\d+   parseAsrResponse:\s*\n\s*(\s*\{[\s\S]*?\})\s*(?=\n|$)'
            matches = re.finditer(pattern, content)
            for match in matches:
                log_ts_str = match.group(1).strip()
                json_str = match.group(2).strip()
                try:
                    json_obj = json.loads(json_str)
                    json_asr_type = json_obj.get("asrType", "")
                    if asr_type == "final":
                        if json_asr_type != "final":
                            continue
                        directives = json_obj.get("asrResult", {}).get("directives", [])
                        for directive in directives:
                            payload = directive.get("payload", {})
                            speaker_info = payload.get("speakerInfo", [])
                            for item in speaker_info:
                                speaker = item.get("speaker", "unknown")
                                word = item.get("word", "").strip()
                                vad_info = item.get("vadInfo", {})
                                start_ms = int(vad_info.get("start_of_speech", 0))
                                end_ms = int(vad_info.get("end_of_speech", 0))
                                if word and end_ms > start_ms:
                                    start_sec = ms10_to_seconds(start_ms)
                                    duration = ms10_to_seconds(end_ms - start_ms)
                                    rttm_line = f"SPEAKER {file_id} 1 {start_sec:.3f} {duration:.3f} <NA> <NA> speaker{speaker} <NA>"
                                    rttm_lines.append(rttm_line)
                    elif asr_type == "vprFix":
                        if json_asr_type != "vprFix":
                            continue
                        directives = json_obj.get("asrResult", {}).get("directives", [])
                        for directive in directives:
                            payload = directive.get("payload", {})
                            speak_info = payload.get("content", {}).get("speakInfo", [])
                            if not speak_info:
                                speak_info = payload.get("speakInfo", [])
                            for item in speak_info:
                                speaker = item.get("speaker", "unknown")
                                word = item.get("word", "").strip()
                                vad_info = item.get("vadInfo", {})
                                start_ms = int(vad_info.get("start_of_speech", 0))
                                end_ms = int(vad_info.get("end_of_speech", 0))
                                if word and end_ms > start_ms:
                                    start_sec = ms10_to_seconds(start_ms)
                                    duration = ms10_to_seconds(end_ms - start_ms)
                                    rttm_line = f"SPEAKER {file_id} 1 {start_sec:.3f} {duration:.3f} <NA> <NA> speaker{speaker} <NA>"
                                    rttm_lines.append(rttm_line)
                except:
                    pass
            return rttm_lines

        def extract_idmap_from_asr(filepath):
            """从asr文件中提取vprFix的idMap"""
            id_map = []
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\s*pauseTime:\d+   parseAsrResponse:\s*\n\s*(\s*\{[\s\S]*?\})\s*(?=\n|$)'
            matches = re.finditer(pattern, content)
            for match in matches:
                json_str = match.group(2).strip()
                try:
                    json_obj = json.loads(json_str)
                    if json_obj.get("asrType") == "vprFix":
                        directives = json_obj.get("asrResult", {}).get("directives", [])
                        for directive in directives:
                            payload = directive.get("payload", {})
                            content_data = payload.get("content", {})
                            id_map = content_data.get("idMap", [])
                            if id_map:
                                return id_map
                except:
                    pass
            return id_map

        def collect_all_speaker_ids(asr_files_list):
            """收集所有asr文件中的speaker id"""
            all_ids = set()
            for asr_file in asr_files_list:
                with open(asr_file, "r", encoding="utf-8") as f:
                    content = f.read()
                pattern = r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\s*pauseTime:\d+   parseAsrResponse:\s*\n\s*(\s*\{[\s\S]*?\})\s*(?=\n|$)'
                matches = re.finditer(pattern, content)
                for match in matches:
                    json_str = match.group(2).strip()
                    try:
                        json_obj = json.loads(json_str)
                        asr_type = json_obj.get("asrType", "")
                        if asr_type in ["final", "vprFix"]:
                            directives = json_obj.get("asrResult", {}).get("directives", [])
                            for directive in directives:
                                payload = directive.get("payload", {})
                                if asr_type == "final":
                                    speaker_info = payload.get("speakerInfo", [])
                                    for item in speaker_info:
                                        old_id = int(item.get("speaker", 1))
                                        all_ids.add(old_id)
                                elif asr_type == "vprFix":
                                    speak_info = payload.get("content", {}).get("speakInfo", [])
                                    if not speak_info:
                                        speak_info = payload.get("speakInfo", [])
                                    for item in speak_info:
                                        old_id = int(item.get("speaker", 1))
                                        all_ids.add(old_id)
                    except:
                        pass
            return sorted(all_ids)

        def build_complete_idmap(all_ids, idmap):
            """构建完整的id映射，包含idMap中没有的id"""
            if not idmap:
                return {id_: id_ for id_ in all_ids}
            mapping = {item["oldId"]: item["newId"] for item in idmap}
            used_new_ids = set(mapping.values())
            next_id = max(used_new_ids) + 1 if used_new_ids else 1
            for old_id in all_ids:
                if old_id not in mapping:
                    while next_id in used_new_ids:
                        next_id += 1
                    mapping[old_id] = next_id
                    used_new_ids.add(next_id)
                    next_id += 1
            return mapping

        def apply_idmap_to_stm(stm_lines, id_mapping):
            """根据idMap替换STM行中的speaker id"""
            if not id_mapping:
                return stm_lines
            result = []
            for line in stm_lines:
                parts = line.split()
                if len(parts) >= 3:
                    speaker = parts[2]
                    if speaker.startswith("speaker"):
                        old_id = int(speaker[7:])
                        new_id = id_mapping.get(old_id, old_id)
                        parts[2] = f"speaker{new_id}"
                        result.append(" ".join(parts))
                    else:
                        result.append(line)
                else:
                    result.append(line)
            return result

        def apply_idmap_to_rttm(rttm_lines, id_mapping):
            """根据idMap替换RTTM行中的speaker id"""
            if not id_mapping:
                return rttm_lines
            result = []
            for line in rttm_lines:
                parts = line.split()
                if len(parts) >= 8:
                    speaker = parts[7]
                    if speaker.startswith("speaker"):
                        old_id = int(speaker[7:])
                        new_id = id_mapping.get(old_id, old_id)
                        parts[7] = f"speaker{new_id}"
                        result.append(" ".join(parts))
                    else:
                        result.append(line)
                else:
                    result.append(line)
            return result

        def parse_filename_timestamp(filename):
            """从文件名解析时间戳，返回当天秒数"""
            import re
            match = re.match(r'asr-(\d+)', filename)
            if match:
                ts_str = match.group(1)
                self._log(level='DEBUG', content=f"解析文件名时间戳: {filename} -> ts_str={ts_str}, len={len(ts_str)}", task_id=task_id, test_case_id=test_case_id)
                if len(ts_str) == 13:
                    hour = int(ts_str[7:9])
                    minute = int(ts_str[9:11])
                    second = int(ts_str[11:13])
                    return hour * 3600 + minute * 60 + second
                elif len(ts_str) == 12:
                    hour = int(ts_str[6:8])
                    minute = int(ts_str[8:10])
                    second = int(ts_str[10:12])
                    return hour * 3600 + minute * 60 + second
                elif len(ts_str) == 14:
                    hour = int(ts_str[8:10])
                    minute = int(ts_str[10:12])
                    second = int(ts_str[12:14])
                    return hour * 3600 + minute * 60 + second
            return 0

        def parse_log_timestamp(log_timestamp_str):
            """解析日志中的时间戳字符串，返回当天秒数
            格式如: 3/25/2026, 3:55:52 PM 或 3/20/2026, 5:46:50 PM
            """
            from datetime import datetime
            try:
                dt = datetime.strptime(log_timestamp_str.strip(), "%m/%d/%Y, %I:%M:%S %p")
                seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
                self._log(level='DEBUG', content=f"解析日志时间戳: {log_timestamp_str} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} -> {seconds}s", task_id=task_id, test_case_id=test_case_id)
                return seconds
            except Exception as e:
                self._log(level='WARNING', content=f"解析日志时间戳失败: {log_timestamp_str}, error: {e}", task_id=task_id, test_case_id=test_case_id)
                return 0

        def get_first_log_timestamp(filepath):
            """从日志文件中获取第一个parseAsrResponse的时间戳，返回当天秒数"""
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                pattern = r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\s*pauseTime:\d+   parseAsrResponse:'
                match = re.search(pattern, content)
                if match:
                    log_ts_str = match.group(1)
                    return parse_log_timestamp(log_ts_str)
            except Exception as e:
                self._log(level='WARNING', content=f"获取日志文件时间戳失败: {filepath}, error: {e}", task_id=task_id, test_case_id=test_case_id)
            return None

        def get_first_timestamp(stm_lines):
            if not stm_lines:
                return None
            parts = stm_lines[0].split()
            if len(parts) >= 4:
                return float(parts[3])
            return None

        def get_last_timestamp(stm_lines):
            if not stm_lines:
                return None
            parts = stm_lines[-1].split()
            if len(parts) >= 5:
                return float(parts[4])
            return None

        def add_offset_to_stm(stm_lines, offset):
            """给STM行添加时间偏移"""
            result = []
            for line in stm_lines:
                parts = line.split()
                if len(parts) >= 5:
                    new_start = float(parts[3]) + offset
                    new_end = float(parts[4]) + offset
                    parts[3] = f"{new_start:.3f}"
                    parts[4] = f"{new_end:.3f}"
                    result.append(" ".join(parts))
                else:
                    result.append(line)
            return result

        def add_offset_to_rttm(rttm_lines, offset):
            """给RTTM行添加时间偏移"""
            result = []
            for line in rttm_lines:
                parts = line.split()
                if len(parts) >= 5:
                    new_start = float(parts[3]) + offset
                    duration = float(parts[4])
                    parts[3] = f"{new_start:.3f}"
                    result.append(" ".join(parts))
                else:
                    result.append(line)
            return result

        asr_files_with_ts = []
        for f in asr_files:
            log_ts = get_first_log_timestamp(str(f))
            filename_ts = parse_filename_timestamp(f.name)
            self._log(level='DEBUG', content=f"文件时间戳: {f.name} -> 文件名={filename_ts}s, 日志={log_ts}s", task_id=task_id, test_case_id=test_case_id)
            ts = log_ts if log_ts is not None else filename_ts
            size = f.stat().st_size
            asr_files_with_ts.append({'file': f, 'timestamp': ts, 'filename_ts': filename_ts, 'size': size})

        asr_files_with_ts.sort(key=lambda x: x['filename_ts'])

        asr_files_dedup = []
        i = 0
        while i < len(asr_files_with_ts):
            if i + 1 < len(asr_files_with_ts) and asr_files_with_ts[i]['filename_ts'] == asr_files_with_ts[i + 1]['filename_ts']:
                smaller = asr_files_with_ts[i] if asr_files_with_ts[i]['size'] < asr_files_with_ts[i + 1]['size'] else asr_files_with_ts[i + 1]
                larger = asr_files_with_ts[i] if smaller == asr_files_with_ts[i + 1] else asr_files_with_ts[i + 1]
                self._log(level='INFO', content=f"移除重复时间戳文件: {smaller['file'].name} (文件名时间戳相同，文件更小)", task_id=task_id, test_case_id=test_case_id)
                asr_files_dedup.append(larger)
                i += 2
            else:
                asr_files_dedup.append(asr_files_with_ts[i])
                i += 1
        asr_files_dedup.sort(key=lambda x: x['timestamp'])
        offsets = {}
        if len(asr_files_dedup) >= 2:
            ts_base = asr_files_dedup[0]['timestamp']
            for idx in range(1, len(asr_files_dedup)):
                ts_current = asr_files_dedup[idx]['timestamp']
                offsets[idx] = float(ts_current - ts_base)
                self._log(level='INFO', content=f"ASR{idx}相对ASR0时间戳差值: {ts_current} - {ts_base} = {offsets[idx]}s", task_id=task_id, test_case_id=test_case_id)

        recording_stm_lines = []
        recording_rttm_lines = []
        recording_asr_lines = []
        asr_parsed = []

        for idx, asr_info in enumerate(asr_files_dedup):
            asr_file = asr_info['file']
            stm_lines = extract_stm_from_asr(asr_file, asr_file.stem, "final")
            rttm_lines = extract_rttm_from_asr(asr_file, asr_file.stem, "final")

            if idx in offsets and offsets[idx] > 0:
                stm_lines = add_offset_to_stm(stm_lines, offsets[idx])
                rttm_lines = add_offset_to_rttm(rttm_lines, offsets[idx])
                self._log(level='INFO', content=f"ASR{idx}已添加offset: {offsets[idx]}s", task_id=task_id, test_case_id=test_case_id)

            first_ts = get_first_timestamp(stm_lines) if stm_lines else None
            last_ts = get_last_timestamp(stm_lines) if stm_lines else None
            asr_parsed.append({
                'idx': idx,
                'first_ts': first_ts,
                'last_ts': last_ts,
                'stm_lines': list(stm_lines),
                'rttm_lines': list(rttm_lines)
            })

            recording_stm_lines.extend(stm_lines)
            recording_rttm_lines.extend(rttm_lines)


        if len(asr_files_dedup) > 1:
            for i in range(len(recording_stm_lines) - 1):
                gap = get_first_timestamp([recording_stm_lines[i + 1]]) - get_last_timestamp([recording_stm_lines[i]])
                if gap and gap > 10:
                    self._log(level='WARNING', content=f"ASR拼接后间隙>{gap}s", task_id=task_id, test_case_id=test_case_id)

        recording_stm_content = "\n".join(recording_stm_lines)
        recording_rttm_content = "\n".join(recording_rttm_lines)


        all_speaker_ids = collect_all_speaker_ids([info['file'] for info in asr_files_dedup])
        self._log(level='INFO', content=f"收集到所有speaker id: {all_speaker_ids}", task_id=task_id, test_case_id=test_case_id)

        global_idmap = []
        for asr_info in asr_files_dedup:
            asr_file = asr_info['file']
            file_idmap = extract_idmap_from_asr(asr_file)
            if file_idmap:
                global_idmap = file_idmap
                self._log(level='INFO', content=f"从{asr_file.name}获取到idMap: {global_idmap}", task_id=task_id, test_case_id=test_case_id)
                break

        complete_idmap = build_complete_idmap(all_speaker_ids, global_idmap)
        self._log(level='INFO', content=f"完整speaker id映射: {complete_idmap}", task_id=task_id, test_case_id=test_case_id)

        fix_stm_lines = []
        fix_rttm_lines = []
        fix_asr_content = ""

        for idx, asr_info in enumerate(asr_files_dedup):
            asr_file = asr_info['file']

            stm_lines = extract_stm_from_asr(asr_file, asr_file.stem, "vprFix")

            if stm_lines:
                file_id = "fix_" + asr_file.stem[4:]
                asr_type = "vprFix"
                self._log(level='INFO', content=f"Fix ASR{idx} 使用vprFix数据，file_id: {file_id}", task_id=task_id, test_case_id=test_case_id)
            else:
                file_id = asr_file.stem
                asr_type = "final"
                self._log(level='INFO', content=f"Fix ASR{idx} 无vprFix数据，使用final填充，file_id: {file_id}", task_id=task_id, test_case_id=test_case_id)

            stm_lines = extract_stm_from_asr(asr_file, file_id, asr_type)
            rttm_lines = extract_rttm_from_asr(asr_file, file_id, asr_type)

            stm_lines = apply_idmap_to_stm(stm_lines, complete_idmap)
            rttm_lines = apply_idmap_to_rttm(rttm_lines, complete_idmap)

            if idx in offsets and offsets[idx] > 0:
                stm_lines = add_offset_to_stm(stm_lines, offsets[idx])
                rttm_lines = add_offset_to_rttm(rttm_lines, offsets[idx])
                self._log(level='INFO', content=f"Fix ASR{idx}已添加offset: {offsets[idx]}s", task_id=task_id, test_case_id=test_case_id)

            fix_stm_lines.extend(stm_lines)
            fix_rttm_lines.extend(rttm_lines)

        fix_stm_content = "\n".join(fix_stm_lines)
        fix_rttm_content = "\n".join(fix_rttm_lines)

        self._log(level='INFO', content=f"最终ASR STM: {len(recording_stm_lines)} 条", task_id=task_id, test_case_id=test_case_id)
        self._log(level='INFO', content=f"最终Fix STM: {len(fix_stm_lines)} 条", task_id=task_id, test_case_id=test_case_id)

        recording_stm_path = os.path.join(local_dir, 'recording.stm')
        recording_rttm_path = os.path.join(local_dir, 'recording.rttm')
        fix_stm_path = os.path.join(local_dir, 'fix.stm')
        fix_rttm_path = os.path.join(local_dir, 'fix.rttm')


        with open(recording_stm_path, "w", encoding="utf-8") as f:
            f.write(recording_stm_content)
        with open(recording_rttm_path, "w", encoding="utf-8") as f:
            f.write(recording_rttm_content)

        with open(fix_stm_path, "w", encoding="utf-8") as f:
            f.write(fix_stm_content)
        with open(fix_rttm_path, "w", encoding="utf-8") as f:
            f.write(fix_rttm_content)


        recording_result = {
            "result_type": "real-time",
            "success": True,
            "message": "Success",
            "meeting_minutes_path": "dummy/meeting_minutes.txt",
            "meeting_minutes_content": "会议纪要内容",
            "recording_stm_path": recording_stm_path,
            "recording_stm_content": recording_stm_content,
            "recording_rttm_path": recording_rttm_path,
            "recording_rttm_content": recording_rttm_content,
            "recording_asr_path": '',
            "recording_asr_content": '',
            "log_path": local_dir,
        }

        fix_result = {
            "result_type": "non-real-time",
            "success": True,
            "message": "Success",
            "meeting_minutes_path": "dummy/meeting_minutes.txt",
            "meeting_minutes_content": "会议纪要内容",
            "fix_stm_path": fix_stm_path,
            "fix_stm_content": fix_stm_content,
            "fix_rttm_path": fix_rttm_path,
            "fix_rttm_content": fix_rttm_content,
            "fix_asr_path": '',
            "fix_asr_content": '',
            "log_path": local_dir,
        }

        process_results = [recording_result, fix_result]

        return process_results
