import time
import subprocess
import os
import logging
from .base_driver import BaseDeviceDriver
from .harmony_collection_mixin import HarmonyCollectionMixin
from .device_config import get_device_config
from .driver_types import AppType, AppVersion, DevicePlatform
from .registry import register_driver
from .utils import check_stop, UiDriver, By, MatchPattern, with_rpc_retry
from .driver_constants import *

logger = logging.getLogger(__name__)


@register_driver
class HarmonyDriver(HarmonyCollectionMixin, BaseDeviceDriver):
    """HarmonyOS设备驱动实现 — HarmonyOS 平台基础驱动

    结果采集为真实链路：每轮录屏（round 模式）+ 小艺聊天页问题/回答文本，
    get_results 按 voice_llm 设备输出字段（wav_path/input_text/question/answer）
    组织返回；采集不到任何真实内容时 success=False（不再返回固定串）。
    采集能力由 HarmonyCollectionMixin 提供。
    """

    # —— 驱动元数据 ——
    app_type = AppType.HARMONY_BASE
    version = AppVersion.V1
    platform = DevicePlatform.HARMONYOS
    keywords = "harmony.base.v1"
    display_name = "HarmonyOS 基础驱动"

    def __init__(self):
        """初始化HarmonyOS驱动"""
        super().__init__()
        self._drivers = {}
        self._config = get_device_config('harmonyos')
        self.app_name = self._config.get('app_name', 'com.huawei.hmos.vassistant')
        self.app_icon_key = 'AppIcon_Image_com.huawei.hmos.vassistant.launcherVoiceAbilityentry0_undefined_0'
        self._unlock_password = self._config.get('unlock_password', '000000')
        self._close_buttons = self._config.get('close_buttons', [])
        self._popup_keywords = self._config.get('popup_keywords', [])
        self._exclude_list = self._config.get('exclude_list', [])
        self._abnormal_keywords = self._config.get('abnormal_keywords', [])
        # 采集状态（每轮由 pre/post_process 维护）
        self._recording = False
        self._record_file_name = None
        self._record_device_path = None
        self._recorder_first_frame_ms = None
        self._round_number = 0
        self.question_text = None
        self.answer_text = None

    def _get_driver(self, device_sn):
        if not UiDriver:
            # hypium 导入失败 → UiDriver 为 None，无法连接鸿蒙设备
            # 根因请见 utils.py 中 "Failed to import hypium" 的 ERROR 日志
            self._log(level='ERROR',
                      content=f"UiDriver is None (hypium 未成功导入)，无法获取设备 {device_sn} 的驱动")
            return None
        if device_sn not in self._drivers:
            try:
                self._drivers[device_sn] = UiDriver.connect(device_sn=device_sn)
            except Exception as e:
                self._log(level='ERROR', content=f"Failed to connect to Harmony device {device_sn}: {e}")
                return None
        return self._drivers[device_sn]

    def _reconnect_driver(self, device_sn):
        """RPC 服务重启后重新建立 UiDriver 连接"""
        try:
            if device_sn in self._drivers:
                old = self._drivers.pop(device_sn, None)
                if old and hasattr(old, 'close'):
                    try:
                        old.close()
                    except Exception:
                        pass
            self._drivers[device_sn] = UiDriver.connect(device_sn=device_sn)
            self._log(level='INFO', content=f"Reconnected UiDriver for {device_sn}")
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to reconnect UiDriver for {device_sn}: {e}")

    def get_driver(self, device_sn):
        return self._get_driver(device_sn)

    def is_locked(self, device_sn):
        """
        判断设备是否锁屏
        """
        try:
            lock_icon_id = '.*LockIcon_Image_lock'
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
        if self._check_stop("unlock"):
            return

        subprocess.run(['hdc', '-t', device_sn, 'shell', 'power-shell', 'wakeup'], check=False)
        time.sleep(NORMAL_WAIT)

        if self._check_stop("unlock"):
            return
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'uinput', '-T', '-m', '540', '1800', '540', '400', '200'],
                           check=False)
            time.sleep(UNLOCK_SWIPE_WAIT)
        except Exception as e:
            self._log(level='WARNING', content=f"Wakeup interaction failed: {e}")
        time.sleep(LONG_WAIT)

        if self._check_stop("unlock"):
            return
        password = self._unlock_password
        try:
            if driver:
                self._log(level='DEBUG', content=f"Attempting to input password: {'*' * len(password)}")
                coords_cache = {}
                for i, digit in enumerate(password):
                    if self._check_stop("unlock"):
                        return
                    if digit in coords_cache:
                        center = coords_cache[digit]
                        self._log(level='DEBUG',
                                  content=f"Clicking digit {digit} at cached {center} (position {i + 1})...")
                        driver.click(center[0], center[1])
                    else:
                        btns = driver.find_components(By.text(digit), 10)
                        if btns:
                            best_btn = None
                            max_y = -1
                            for btn in btns:
                                try:
                                    bounds = btn.getBounds()
                                    center_y = (bounds[1] + bounds[3]) / 2
                                    if center_y > max_y:
                                        max_y = center_y
                                        best_btn = btn
                                except Exception as e:
                                    self._log(level='DEBUG', content=f"Error getting button bounds: {e}")
                                    continue

                            if best_btn:
                                bounds = best_btn.getBounds()
                                center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
                                coords_cache[digit] = center
                                self._log(level='DEBUG',
                                          content=f"Clicking digit {digit} at {center} (position {i + 1})...")
                                driver.click(center[0], center[1])
                            else:
                                self._log(level='WARNING', content=f"Digit {digit} component found but invalid.")
                        else:
                            key_map = {
                                "1": (270, 1800), "2": (540, 1800), "3": (810, 1800),
                                "4": (270, 2000), "5": (540, 2000), "6": (810, 2000),
                                "7": (270, 2200), "8": (540, 2200), "9": (810, 2200),
                                "0": (540, 2400)
                            }
                            if digit in key_map:
                                pos = key_map[digit]
                                self._log(level='WARNING',
                                      content=f"Digit {digit} not found, trying predicted coordinates {pos}...")
                                driver.click(pos[0], pos[1])
                            else:
                                self._log(level='ERROR', content=f"Digit {digit} not found on screen and no fallback.")
                    time.sleep(NORMAL_WAIT)

                if self._check_stop("unlock"):
                    return
                for confirm_text in ["确定", "完成", "OK", "解锁"]:
                    confirm_btn = driver.find_component(By.text(confirm_text))
                    if confirm_btn:
                        confirm_btn.click()
                        break
        except Exception as e:
            self._log(level='ERROR', content=f"Unlock via clicking digits failed: {e}")

        time.sleep(NORMAL_WAIT)

    def scan(self):
        """使用 hdc list targets 扫描设备"""
        if self._mock_mode:
            return [
                {
                    "serial": "mock-harmony-1",
                    "model": "Mock HarmonyOS Device",
                    "system": "HarmonyOS",
                    "status": "online"
                }
            ]
        devices = []
        self._log(level='INFO', content="Starting HarmonyOS device scan via hdc...")
        try:
            output = subprocess.check_output(['hdc', 'list', 'targets'], encoding='utf-8', stderr=subprocess.STDOUT)
            self._log(level='DEBUG', content=f"hdc list targets output: {output}")
            lines = output.strip().split('\n')
            for line in lines:
                if line.strip() and '[Empty]' not in line:
                    devices.append({
                        "serial": line.strip(),
                        "model": "Harmony Device",
                        "system": "HarmonyOS",
                        "status": "online"
                    })
            self._log(level='INFO', content=f"Found {len(devices)} HarmonyOS device(s) via hdc")
        except subprocess.CalledProcessError as e:
            self._log(level='WARNING', content=f"hdc list targets command failed: {e.output}")
        except FileNotFoundError as e:
            self._log(level='WARNING', content=f"hdc command not found: {e}")
        return devices

    @check_stop("initialize")
    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化鸿蒙设备"""
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...")
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR',
                      content=f"Failed to get driver for device {device_sn}（原因：hypium/devicetest 未安装导致 UiDriver=None）")
            return False

        try:

            if self._check_stop("initialize"):
                return False
            self.unlock(device_sn)
            if self._check_stop("initialize"):
                return False

            # 检测并关闭弹窗
            self.close_popups(device_sn)
            if self._check_stop("initialize"):
                return False
            try:
                driver.swipe_to_home()
            except:
                driver.press_home()
            time.sleep(LONG_WAIT)

            driver.stop_app(self.app_name)

            if self._check_stop("initialize"):
                return False
            # 从配置获取应用图标Key
            app_icon_key = self.app_icon_key
            icon = driver.find_component(By.key(app_icon_key))
            if icon:
                self._log(level='DEBUG', content=f"Clicking app icon...")
                icon.click()
                time.sleep(APP_LAUNCH_WAIT)
                # 启动应用后再次检查弹窗
                self.close_popups(device_sn)
            else:
                self._log(level='WARNING', content="App icon not found, trying aa start...")
                subprocess.run(['hdc', '-t', device_sn, 'shell', 'aa', 'start', '-b', self.app_name], check=False)
                time.sleep(APP_LAUNCH_WAIT)
                # 启动应用后再次检查弹窗
                self.close_popups(device_sn)

            if self._check_stop("initialize"):
                return False
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to initialize via settings path: {e}")
            return False

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开始处理：按轮启动录屏（round 模式，每轮一段 mp4）"""
        self._log(level='INFO', content=f"--- Starting pre-process for {device_sn} ---",
                  task_id=task_id, test_case_id=test_case_id)
        round_number = kwargs.get('round_number', 0)
        self._round_number = round_number
        self._record_file_name = f"{test_case_id or task_id or 'case'}_r{round_number}.mp4"
        self._record_device_path = None
        self._recorder_first_frame_ms = None
        started, self._record_device_path, self._recorder_first_frame_ms = \
            self._start_recorder(device_sn, file_name=self._record_file_name)
        self._recording = started
        if not started:
            self._log(level='ERROR', content=f"启动录屏失败: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        if self._record_device_path:
            self._log(level='INFO',
                      content=f"启动录屏成功: {self._record_file_name} ({self._record_device_path})",
                      task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='WARNING',
                      content=f"录屏已启动但未发现新 mp4 文件（get_results 将回退 mediatool 查询）: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
        return True

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """结束处理：等待小艺回复完成 → 抓取问题/回答文本 → 停止录屏"""
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---",
                  task_id=task_id, test_case_id=test_case_id)
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 start_ms={ts['start_ms']} end_ms={ts['end_ms']}",
                  task_id=task_id, test_case_id=test_case_id)
        driver = self._get_driver(device_sn)
        replied, self.question_text, self.answer_text = self._wait_reply_settled(
            driver, device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
        self._log(level='INFO',
                  content=f"[post_process] replied={replied} question={self.question_text!r} answer={self.answer_text!r}",
                  task_id=task_id, test_case_id=test_case_id)
        if self._recording:
            if self._stop_recorder(device_sn):
                self._log(level='INFO', content="停止录屏成功",
                          task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='WARNING', content="停止录屏失败",
                          task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(EXTRA_LONG_WAIT)
        return True

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """获取设备输出结果 - 录屏文件上 OSS + 小艺问题/回答文本

        按 voice_llm 设备输出字段（wav_path=录音文件/input_text=录屏文件/
        question/answer）组织；附 asr 键兼容非 voice_llm 算法类型的透传映射。
        所有值为真实采集结果，采集不到任何内容时 success=False。
        """
        ts = self._extract_playback_timestamps(kwargs)
        pull_error = None
        wav_note = None
        try:
            record_oss, wav_oss, pull_error, wav_note = self._pull_record_to_oss(
                device_sn, task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            record_oss = wav_oss = None
            pull_error = f'录屏拉取异常: {e}'
            self._log(level='ERROR', content=pull_error,
                      task_id=task_id, test_case_id=test_case_id)
        question_text = getattr(self, 'question_text', None) or ''
        answer_text = getattr(self, 'answer_text', None) or ''
        has_content = bool(record_oss or wav_oss or question_text or answer_text)
        # 降级口径显式外溢：拉取失败 / wav 缺失回退 / OSS 不可用本地降级，均在 message 标注
        notes = []
        if pull_error:
            notes.append(f'录屏拉取失败: {pull_error}')
        if wav_note:
            notes.append(wav_note)
        if any(p and p.startswith('local://') for p in (record_oss, wav_oss)):
            notes.append('OSS 不可用，产物本地降级存储（local://）')
        if not has_content:
            message = pull_error or '未采集到任何设备结果（无录屏文件、无回复文本）'
        else:
            message = 'Success' if not notes else f'Success ({"; ".join(notes)})'
        result = {
            'success': has_content,
            'message': message,
            'record_path': record_oss or '',
            'record_device_path': getattr(self, '_record_device_path', '') or '',
            # wav 转换失败时回退 mp4，保证评估侧仍有音频可取（降级原因见 message）
            'wav_path': wav_oss or record_oss or '',
            'input_text': record_oss or '',
            'start_ms': ts['start_ms'],
            'end_ms': ts['end_ms'],
            'first_frame_ms': getattr(self, '_recorder_first_frame_ms', None),
            'question': question_text,
            'answer': answer_text,
            'asr': question_text,
        }
        self._log(level='INFO',
                  content=(f"[get_results] success={result['success']} wav_path={result['wav_path']} "
                           f"question={question_text!r} answer={answer_text!r} message={message}"),
                  task_id=task_id, test_case_id=test_case_id)
        return result

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束后清理：兜底停止残留录屏（仅仍在录屏时），再走基类关 APP 清理"""
        if getattr(self, '_recording', False):
            try:
                if self._stop_recorder(device_sn):
                    self._log(level='INFO', content="teardown: 兜底停止录屏成功",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='WARNING', content="teardown: 兜底停止录屏失败",
                              task_id=task_id, test_case_id=test_case_id)
                self._recording = False
            except Exception as e:
                self._log(level='WARNING', content=f"teardown: 停止录屏失败: {e}",
                          task_id=task_id, test_case_id=test_case_id)
        return super().teardown(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

    @check_stop("close_popups")
    def close_popups(self, device_sn) -> bool:
        """检测并关闭 HarmonyOS 设备上的弹窗

        Args:
            device_sn: 设备序列号

        Returns:
            bool: 是否成功执行
        """
        self._log(level='INFO', content=f"Checking for popups on HarmonyOS device {device_sn}...")
        driver = self._get_driver(device_sn)
        if not driver:
            return False

        def safe_find_components(by_obj, timeout_sec=10):
            """安全的 find_components 调用，带超时保护"""
            result = []
            start_time = time.time()
            try:
                while time.time() - start_time < timeout_sec:
                    try:
                        result = driver.find_components(by_obj, 1)
                        break
                    except Exception:
                        time.sleep(POPUP_CLOSE_WAIT)
                        continue
            except Exception:
                logger.debug("safe_find_components 查找组件时发生异常 device_sn=%s", device_sn, exc_info=True)
            return result

        try:
            close_buttons = self._close_buttons or []

            for btn_text in close_buttons:
                if self._check_stop("close_popups"):
                    return False

                try:
                    buttons = safe_find_components(By.text(btn_text), 10)
                    if buttons:
                        best_btn = None
                        max_y = -1
                        for btn in buttons:
                            try:
                                if not hasattr(btn, 'getBounds'):
                                    continue
                                bounds = btn.getBounds()
                                center_y = (bounds[1] + bounds[3]) / 2
                                if center_y > max_y:
                                    max_y = center_y
                                    best_btn = btn
                            except Exception:
                                continue

                        if best_btn:
                            self._log(level='DEBUG',
                                      content=f"Found popup button '{btn_text}' on HarmonyOS, clicking...")
                            try:
                                best_btn.click()
                            except Exception as e:
                                self._log(level='DEBUG', content=f"Failed to click button: {e}")
                            time.sleep(POPUP_CLOSE_WAIT)
                            continue
                except Exception as e:
                    self._log(level='DEBUG', content=f"Error checking button '{btn_text}' on HarmonyOS: {e}")
                    continue

            popup_keywords = self._popup_keywords or []
            for keyword in popup_keywords:
                if self._check_stop("close_popups"):
                    return False

                elements = safe_find_components(By.text(keyword, MatchPattern.CONTAINS), 10)
                if not elements:
                    continue
                self._log(level='DEBUG',
                          content=f"Found popup with keyword '{keyword}' on HarmonyOS, trying to close...")
                for btn_text in close_buttons:
                    try:
                        btn = driver.find_component(By.text(btn_text))
                        if btn and hasattr(btn, 'click'):
                            btn.click()
                            time.sleep(POPUP_CLOSE_WAIT)
                            break
                    except Exception as e:
                        self._log(level='DEBUG', content=f"Error clicking button '{btn_text}' on HarmonyOS: {e}")
                        continue

            self._log(level='INFO', content=f"Popup check completed for HarmonyOS device {device_sn}")
            return True
        except Exception as e:
            self._log(level='ERROR', content=f"Error closing popups on HarmonyOS device {device_sn}: {e}")
            return False

    def set_volume(self, device_sn, level: int) -> bool:
        """设置 HarmonyOS 设备系统音量
        
        Args:
            device_sn: 设备序列号
            level: 音量级别(0-100)
            
        Returns:
            bool: 是否设置成功
        """
        try:
            level = max(0, min(100, level))
            device_level = round(level * 15 / 100)
            subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'audioctl', '-s', str(device_level)],
                check=False, capture_output=True, timeout=HDC_TIMEOUT
            )
            self._log(level='INFO', content=f"HarmonyOS 设备 {device_sn} 音量已设为 {level} (设备值: {device_level})")
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"HarmonyOS 设备 {device_sn} 音量设置失败: {e}")
            return False

    def get_volume(self, device_sn) -> int:
        """获取 HarmonyOS 设备系统音量
        
        Args:
            device_sn: 设备序列号
            
        Returns:
            int: 当前音量(0-100)，不支持或失败返回 -1
        """
        try:
            result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'audioctl', '-g'],
                capture_output=True, text=True, timeout=HDC_TIMEOUT
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                device_level = int(output.split()[-1]) if output else -1
                if device_level >= 0:
                    return round(device_level * 100 / 15)
            return -1
        except Exception as e:
            self._log(level='WARNING', content=f"HarmonyOS 设备 {device_sn} 音量获取失败: {e}")
            return -1

