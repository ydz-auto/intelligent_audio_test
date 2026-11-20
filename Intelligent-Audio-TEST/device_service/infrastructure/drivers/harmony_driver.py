import io
import json
import time
import shutil
import subprocess
import os
import tempfile
import logging
from .base_driver import BaseDeviceDriver
from .harmony_collection_mixin import HarmonyCollectionMixin
from .device_config import get_device_config
from .driver_types import DevicePlatform
from .registry import register_driver
from .utils import (
    check_stop, UiDriver, By, MatchPattern, with_rpc_retry,
    is_rpc_not_running_error, restart_uitest_daemon,
)
from .driver_constants import *
from shared.utils.config_manager import config_manager
from shared.constants.ui_capture import (
    UiActionNotAllowed,
    UiActionType,
    UiCaptureDegradeReason,
    UiCaptureMode,
    UiCapturePlatform,
    UiCaptureUnavailable,
    UiElementNotFound,
    UiTreeFormat,
    normalize_ui_capture_mode,
)

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
    app_type = "harmony_base"
    version = "v1"
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

    def _ui_unavailable_reason(self):
        """判定 UI 自动化层不可用的结构化原因（None = 可用）"""
        if not UiDriver:
            return UiCaptureDegradeReason.HYPIUM_MISSING
        return None

    def _connect_ui_driver(self, device_sn, raise_rpc_error=True):
        """建立 UiDriver 连接并缓存；失败返回 None（不判断降级模式，由调用方分流）

        RPC 类错误（设备端 uitest 守护不可达）默认向上抛出（V9.7.10 语义）：
        只有冒泡到 @with_rpc_retry 才能触发「重启守护 + 重连」自愈；若在此吞掉，
        装饰器永远收不到异常，守护一死就只能降级/失败。
        """
        if device_sn not in self._drivers:
            try:
                self._drivers[device_sn] = UiDriver.connect(device_sn=device_sn)
            except Exception as e:
                if raise_rpc_error and is_rpc_not_running_error(e):
                    raise
                self._log(level='ERROR', content=f"Failed to connect to Harmony device {device_sn}: {e}")
                return None
        return self._drivers[device_sn]

    def _get_driver(self, device_sn):
        if not UiDriver:
            # hypium 导入失败 → UiDriver 为 None，无法连接鸿蒙设备
            # 根因请见 utils.py 中 "Failed to import hypium" 的 ERROR 日志
            self._log(level='ERROR',
                      content=f"UiDriver is None (hypium 未成功导入)，无法获取设备 {device_sn} 的驱动")
            return None
        return self._connect_ui_driver(device_sn)

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

    # ==================== 设备 UI 探索三能力（INT-2577） ====================
    # 树：UiTree.dump_to_file（layout JSON）→ 组件树 JSON 文本；解析在 agent 侧
    # （parse_harmony_components）。失败一律 UiCaptureUnavailable 显式降级，不返回空树。

    def _require_ui_driver(self, device_sn):
        """取 hypium UiDriver；hypium 缺失 / 守护不可达分别给出结构化降级原因。"""
        if not UiDriver:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 不可用：运行环境无 hypium（UiDriver 导入失败）',
                reason=UiCaptureDegradeReason.HYPIUM_MISSING)
        try:
            driver = self._get_driver(device_sn)
        except Exception as e:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} UI 驱动连接失败：{e}',
                reason=UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE) from e
        if driver is None:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} UI 驱动不可用（设备端 uitest 守护不可达）',
                reason=UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE)
        return driver

    @staticmethod
    def _flatten_layout_node(node, out) -> int:
        """hypium layout 树（attributes/children）→ 组件数组（扁平属性 + children）。

        只做结构解包：属性名原样保留，字段归一化仍由 agent 侧
        ``parse_harmony_components`` 负责（不实现第二份归一化）。

        Returns:
            int: 本次递归处理的节点数（含子节点），用于 ``node_count`` 上报。
        """
        if not isinstance(node, dict):
            return 0
        attrs = node.get('attributes')
        flat = dict(attrs) if isinstance(attrs, dict) else {
            k: v for k, v in node.items() if k != 'children'}
        count = 1
        children = node.get('children')
        if isinstance(children, list):
            child_flats = []
            for child in children:
                count += HarmonyDriver._flatten_layout_node(child, child_flats)
            if child_flats:
                flat['children'] = child_flats
        out.append(flat)
        return count

    def dump_ui_tree(self, device_sn, **kwargs) -> dict:
        """读当前页 UI 树：``UiTree.dump_to_file`` → layout JSON → 组件树 JSON 文本。"""
        driver = self._require_ui_driver(device_sn)
        work_dir = tempfile.mkdtemp(prefix='device-ui-tree-')
        tree_file = os.path.join(work_dir, 'layout.json')
        try:
            try:
                driver.UiTree.dump_to_file(tree_file)
            except Exception as e:
                raise UiCaptureUnavailable(
                    f'HarmonyOS 设备 {device_sn} 读取控件树失败：{e}',
                    reason=UiCaptureDegradeReason.DRIVER_UNAVAILABLE) from e
            try:
                with open(tree_file, 'r', encoding='utf-8', errors='ignore') as f:
                    layout = json.load(f)
            except (OSError, ValueError) as e:
                raise UiCaptureUnavailable(
                    f'HarmonyOS 设备 {device_sn} 控件树不可解析：{e}',
                    reason=UiCaptureDegradeReason.TREE_UNREADABLE) from e
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        components = []
        node_count = self._flatten_layout_node(layout, components)
        if not components or node_count <= 0:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 控件树没有任何节点',
                reason=UiCaptureDegradeReason.TREE_UNREADABLE)
        return {
            'platform': UiCapturePlatform.HARMONYOS.value,
            'format': UiTreeFormat.HARMONY_COMPONENTS.value,
            'payload': json.dumps(components, ensure_ascii=False),
            'node_count': node_count,
        }

    def _resolve_ui_component(self, driver, device_sn, node):
        """定位待操作组件：按 id / key / text 查（``find_component``）。"""
        node = node if isinstance(node, dict) else {}
        selector = None
        if node.get('resource_id'):
            selector = By.id(str(node['resource_id']))
        elif node.get('key'):
            selector = By.key(str(node['key']))
        elif node.get('text'):
            selector = By.text(str(node['text']))
        if selector is None:
            raise UiElementNotFound(
                f'HarmonyOS 设备 {device_sn} 动作缺少可用定位键'
                f'（resource_id / key / text 均为空）')
        try:
            component = driver.find_component(selector)
        except Exception as e:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 查找目标组件失败：{e}',
                reason=UiCaptureDegradeReason.DRIVER_UNAVAILABLE) from e
        if component is None:
            raise UiElementNotFound(
                f'HarmonyOS 设备 {device_sn} 上未定位到目标组件'
                f'（resource_id={node.get("resource_id")!r} key={node.get("key")!r}'
                f' text={node.get("text")!r}）')
        return component

    def perform_ui_action(self, device_sn, action_type, *, node=None,
                          params=None) -> dict:
        """下发一个已校验的 UiActionType 动作（hypium UiDriver 原生能力）。"""
        driver = self._require_ui_driver(device_sn)
        params = params if isinstance(params, dict) else {}
        action = self._normalize_action(action_type)
        try:
            if action is UiActionType.TAP:
                driver.click(self._resolve_ui_component(driver, device_sn, node))
            elif action is UiActionType.LONG_PRESS:
                component = self._resolve_ui_component(driver, device_sn, node)
                press_time = float(params.get('duration') or UI_EXPLORE_LONG_PRESS_SECONDS)
                driver.long_click(component, press_time=press_time)
            elif action is UiActionType.INPUT_TEXT:
                component = self._resolve_ui_component(driver, device_sn, node)
                driver.input_text(component, str(params.get('text') or ''))
            elif action is UiActionType.SWIPE:
                self._slide(driver, params)
            elif action is UiActionType.BACK:
                driver.press_back()
            elif action is UiActionType.HOME:
                driver.press_home()
            elif action is UiActionType.WAIT:
                seconds = min(float(params.get('seconds') or UI_EXPLORE_WAIT_DEFAULT_SECONDS),
                              UI_EXPLORE_WAIT_MAX_SECONDS)
                driver.wait(seconds)
        except (UiElementNotFound, UiActionNotAllowed):
            raise
        except Exception as e:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 下发动作 {action.value} 失败：{e}',
                reason=UiCaptureDegradeReason.DRIVER_UNAVAILABLE) from e
        return {'action_type': action.value, 'performed': True}

    @staticmethod
    def _normalize_action(action_type):
        """动作名 → UiActionType（非七枚举一律 ACTION_NOT_ALLOWED，拒绝魔法字符串）。"""
        try:
            return UiActionType(str(action_type or '').strip().upper())
        except ValueError:
            raise UiActionNotAllowed(f'不支持的 UI 动作：{action_type!r}')

    def _slide(self, driver, params):
        """按方向计算起止点并滑动（hypium ``slide``，以屏幕中心为基准）。"""
        direction = str(params.get('direction') or 'up').lower()
        if direction not in UI_EXPLORE_SWIPE_DIRECTIONS:
            raise UiActionNotAllowed(f'不支持的滑动方向：{direction!r}')
        width, height = driver.get_display_size()
        cx, cy = width // 2, height // 2
        span = int(params.get('distance') or min(width, height) * UI_EXPLORE_SWIPE_SPAN_RATIO)
        half = max(1, span) // 2
        delta = {
            'up': (0, -half), 'down': (0, half),
            'left': (-half, 0), 'right': (half, 0),
        }[direction]
        duration = float(params.get('duration') or UI_EXPLORE_SWIPE_DURATION_SECONDS)
        driver.slide((cx - delta[0], cy - delta[1]), (cx + delta[0], cy + delta[1]),
                     slide_time=duration)

    def capture_ui_screenshot(self, device_sn, **kwargs) -> dict:
        """截取当前屏 → PNG 字节（上传对象存储由 servicer 负责）。"""
        driver = self._require_ui_driver(device_sn)
        work_dir = tempfile.mkdtemp(prefix='device-ui-shot-')
        shot_path = os.path.join(work_dir, 'screenshot.png')
        try:
            try:
                driver.capture_screen(shot_path)
            except Exception as e:
                raise UiCaptureUnavailable(
                    f'HarmonyOS 设备 {device_sn} 截图失败：{e}',
                    reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE) from e
            try:
                with open(shot_path, 'rb') as f:
                    png = f.read()
            except OSError as e:
                raise UiCaptureUnavailable(
                    f'HarmonyOS 设备 {device_sn} 截图未落盘：{e}',
                    reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE) from e
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        if not png:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 截图内容为空',
                reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE)
        width, height = 0, 0
        try:
            from PIL import Image
            with Image.open(io.BytesIO(png)) as image:
                width, height = image.size
        except Exception as e:
            raise UiCaptureUnavailable(
                f'HarmonyOS 设备 {device_sn} 截图不可解析：{e}',
                reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE) from e
        return {'png': png, 'format': 'PNG',
                'width': int(width), 'height': int(height)}

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

    def supports_device_watch(self):
        """hdc 可用即可做设备表变更监听。"""
        return shutil.which('hdc') is not None

    def watch_device_snapshots(self, stop_event=None):
        """``hdc list targets`` 变更检测流：设备表变化时 yield ``{serial: 'device'}``。

        hdc 3.2.0c（``hdc help verbose`` 实测）没有设备变更 track 命令（只有
        track-jpid），因此这里用短周期（默认 1s，配置
        ``device_presence.hdc_scan_interval_seconds``）比对设备表，仅在变化时
        产出快照；上层消费方式与 adb 事件流一致，无需区分。扫描失败（hdc
        server 未就绪等）跳过本轮，不产出空快照，避免误判整批离线。
        """
        if not self.supports_device_watch():
            return
        interval = float(config_manager.get_value(
            'device_presence', 'hdc_scan_interval_seconds', 1))
        previous = None
        while not (stop_event and stop_event.is_set()):
            snapshot = self._scan_target_snapshot()
            if snapshot is not None and snapshot != previous:
                previous = snapshot
                yield snapshot
            if stop_event is not None:
                if stop_event.wait(interval):
                    break
            else:
                time.sleep(interval)

    def _scan_target_snapshot(self):
        """执行一次 ``hdc list targets``，返回在线目标集合；失败返回 None。"""
        try:
            output = subprocess.check_output(
                ['hdc', 'list', 'targets'],
                encoding='utf-8', errors='replace', stderr=subprocess.STDOUT,
                timeout=HDC_TIMEOUT,
            )
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired):
            logger.warning("执行 hdc list targets 失败，跳过本轮设备快照", exc_info=True)
            return None
        return {
            line.strip(): 'device'
            for line in output.splitlines()
            if line.strip() and '[Empty]' not in line
        }

    @check_stop("initialize")
    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化鸿蒙设备

        UI 抓取层不可用时的行为由 UI_CAPTURE_MODE 配置分流（INT-296）：
        - strict（默认）：显式失败（INT-158 语义，错误透传真因）
        - explicit_degrade：跳过 UI 抓取层初始化，返回成功 + ui_capture_available=false
          + degrade_reason 结构化标记；录屏/采集链自检不降级（失败仍失败）
        分流统一收口在 _initialize_ui_guard（INT-312：子类自定义 initialize 复用同一模板）。
        """
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_sn} for...")

        driver, proceed = self._initialize_ui_guard(device_sn, task_id=task_id,
                                                    test_case_id=test_case_id)
        if not proceed:
            return False

        try:

            if self._check_stop("initialize"):
                return False
            if driver is not None:
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
                    # 小艺只能通过桌面图标启动（aa start 实测无效：ability 不产生
                    # 前台界面，且旧实现的 aa start -b 缺 ability 参数必然失败）。
                    # 图标找不到说明设备环境异常（未解锁/桌面未就绪），显式失败，
                    # 不再静默吞掉，避免问题延迟到 pre_process 才以"找不到组件"暴露。
                    self._log(level='ERROR',
                              content=(f"App 图标未找到，无法启动 {self.app_name}："
                                       f"请确认设备已解锁且桌面已加载完成"),
                              task_id=task_id, test_case_id=test_case_id)
                    return False

                if self._check_stop("initialize"):
                    return False
            return True
        except Exception as e:
            # 守护在 UI 步骤中途死亡（设备内存压力下反复发生）时必须向上抛出：
            # 吞掉会绕过 @with_rpc_retry 的自愈重试，initialize 只能干等几百秒后
            # 失败（真机实测 248~363s 后报 UI RPC listening port is not found）。
            if is_rpc_not_running_error(e):
                raise
            self._log(level='ERROR', content=f"Failed to initialize via settings path: {e}")
            return False

    def _recover_ui_rpc(self, device_sn):
        """守护不可达时重启设备端 uitest 守护并重连（V9.7.10 自愈语义）

        Returns:
            UiDriver 实例（恢复成功）；None（恢复失败）
        """
        try:
            if not restart_uitest_daemon(device_sn):
                return None
            self._reconnect_driver(device_sn)
            driver = self._drivers.get(device_sn)
            if driver is not None:
                self._log(level='INFO',
                          content=f"UI RPC 自愈成功（uitest 守护已重启并重连）: {device_sn}")
            return driver
        except Exception as e:
            self._log(level='WARNING', content=f"UI RPC 自愈失败: {device_sn}（{e}）")
            return None

    def _get_driver_for_initialize(self, device_sn):
        """initialize 专用取驱动：区分「环境缺 hypium」与「连接失败」两种不可用形态

        守护不可达时先尝试自愈（重启设备端 uitest 守护 + 重连，恢复 V9.7.10
        的自愈语义），自愈仍失败才返回结构化不可用原因，由调用方按
        UI_CAPTURE_MODE 分流（strict 显式失败 / explicit_degrade 降级留痕）。

        Returns:
            (UiDriver 实例, None)（可用）；
            (None, 结构化不可用原因)（不可用，原因仅由调用方决定是否落状态）
        """
        reason = self._ui_unavailable_reason()
        if reason is not None:
            return None, reason.value
        try:
            driver = self._connect_ui_driver(device_sn)
        except Exception as e:
            if not is_rpc_not_running_error(e):
                raise
            self._log(level='WARNING',
                      content=f"UI RPC 守护不可达，尝试自动恢复: {device_sn}（{e}）")
            driver = self._recover_ui_rpc(device_sn)
        if driver is None:
            return None, UiCaptureDegradeReason.UITEST_DAEMON_UNAVAILABLE.value
        return driver, None

    def _degrade_ui_capture(self, unavailable_reason):
        """按 UI_CAPTURE_MODE 分流 UI 层不可用（INT-296）

        Args:
            unavailable_reason: _get_driver_for_initialize 返回的结构化不可用原因

        Returns:
            True: explicit_degrade 模式，已标记降级，调用方继续非 UI 初始化并返回成功
            False: strict 模式（默认），调用方按现状显式失败（状态保持无降级）
        """
        from device_service.config.config import Config
        mode = normalize_ui_capture_mode(getattr(Config, 'UI_CAPTURE_MODE', None))
        if mode == UiCaptureMode.EXPLICIT_DEGRADE.value:
            self.mark_ui_capture_degraded(UiCaptureDegradeReason(unavailable_reason))
            return True
        return False

    def _initialize_ui_guard(self, device_sn, task_id=None, test_case_id=None):
        """initialize 入口统一 UI 分流模板（INT-296 降级逻辑唯一实现，INT-312 下沉复用）

        自带 initialize 覆写的子类驱动（不调 super().initialize 的自定义入口）在
        入口调用本方法替代裸 _get_driver，使 explicit_degrade 语义全驱动一致：
        - UI 层可用 → (driver, True)，子类照常执行全部步骤
        - explicit_degrade 且 UI 层不可用 → 已标记 ui_capture_available=false +
          degrade_reason，返回 (None, True)；子类跳过依赖 driver 的 UI 步骤、
          仅执行 hdc 等非 UI 步骤后返回成功
        - strict（默认）且 UI 层不可用 → 已记 ERROR（错误透传真因），返回
          (None, False)，子类显式失败（INT-158 语义）

        Returns:
            (driver, proceed) 元组，语义见上
        """
        self.reset_ui_capture_state()
        driver, unavailable_reason = self._get_driver_for_initialize(device_sn)
        if driver is not None:
            return driver, True
        if self._degrade_ui_capture(unavailable_reason):
            # explicit_degrade：UI 抓取层不可用 → 留痕跳过，录屏链照常初始化
            self._log(level='WARNING',
                      content=(f"UI 抓取层降级（explicit_degrade）: device {device_sn} "
                               f"reason={self.ui_degrade_reason}，"
                               f"UI 步骤将按环境排除显式跳过；录屏/采集链不受影响"),
                      task_id=task_id, test_case_id=test_case_id)
            return None, True
        reason = unavailable_reason
        if isinstance(reason, UiCaptureDegradeReason):
            reason = reason.value
        self._log(level='ERROR',
                  content=(f"Failed to get driver for device {device_sn} "
                           f"（UI 抓取层不可用: {reason}；"
                           f"hypium/devicetest 未安装或设备端 uitest 守护不可达）"),
                  task_id=task_id, test_case_id=test_case_id)
        return None, False

    def _resume_driver_after_super_initialize(self, device_sn, task_id=None, test_case_id=None):
        """子类 initialize 在 super().initialize() 成功后的取驱动收尾（INT-312）

        供链式调用 super().initialize() 的子类驱动使用：基类已通过
        _initialize_ui_guard 完成分流（strict 失败时子类早已 return False），
        本方法只读其结论，不重复分流、不重复记日志：
        - UI 层可用 → (driver, True)
        - explicit_degrade 已降级 → (None, True)，子类跳过依赖 driver 的 UI 步骤
        - 防御分支：基类成功但驱动不可取（不应发生）→ 按 strict 语义显式失败

        Returns:
            (driver, proceed) 元组，语义见 _initialize_ui_guard
        """
        if not getattr(self, 'ui_capture_available', True):
            return None, True
        driver = self._get_driver(device_sn)
        if driver is None:
            self._log(level='ERROR',
                      content=(f"Failed to get driver for device {device_sn} "
                               f"（super().initialize 成功但驱动不可取，按 strict 语义显式失败）"),
                      task_id=task_id, test_case_id=test_case_id)
            return None, False
        return driver, True

    def _device_shell(self, device_sn, driver, cmd):
        """设备 shell 命令：driver 可用走 UiDriver.shell；explicit_degrade 无驱动时
        走 hdc 直连（INT-312：UI 抓取层降级不连带 fwk 采集参数设置降级）"""
        if driver is not None:
            return driver.shell(cmd)
        return self._hdc_shell(device_sn, cmd)

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """开始处理：唤醒/解锁 → 按轮启动录屏（round 模式，每轮一段 mp4）

        每轮唤醒+解锁：多轮间隔可能超屏灭时间，屏幕熄灭状态下录屏收尾
        （moov 写入）与 UI 抓取都不可靠——这是实机验收发现 moov 缺失 mp4 的
        关联因素（INT-158 验收问题 1）。
        """
        self._log(level='INFO', content=f"--- Starting pre-process for {device_sn} ---",
                  task_id=task_id, test_case_id=test_case_id)
        try:
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'power-shell', 'wakeup'],
                           check=False, capture_output=True, timeout=HDC_TIMEOUT)
            if self.is_locked(device_sn):
                self.unlock(device_sn)
        except Exception as e:
            self._log(level='WARNING', content=f"轮首唤醒/解锁失败(继续): {e}",
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
                      content=f"录屏已启动但轮询未发现新 mp4 文件（get_results 将按新增文件 diff/mediatool 兜底发现）: {self._record_file_name}",
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

