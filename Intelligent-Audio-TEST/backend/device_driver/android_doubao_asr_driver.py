"""豆包Android语音识别驱动模块

该模块实现了针对豆包App（com.larus.nova）的语音识别功能，
提供设备初始化、按住说话、松开说话、获取识别结果等完整流程。

主要功能：
- 设备锁屏状态检测
- 豆包App初始化
- 语音录制控制（按住/松开说话按钮）
- 语音识别结果提取
"""

import subprocess
import time
from .android_driver import AndroidDriver
from .utils import check_stop


class DouBaoAndroidAsrDriver(AndroidDriver):
    """豆包Android语音识别驱动类

    继承自AndroidDriver，专门用于控制豆包App进行语音识别操作。
    通过UI自动化操作模拟用户交互，完成语音录制和结果获取。
    """

    # 应用配置常量
    APP_NAME = "com.larus.nova"           # 豆包App的包名

    # 时间配置常量
    SCREEN_ON_DELAY = 0.5                 # 屏幕点亮后等待时间（秒）
    ADB_TIMEOUT = 5                       # ADB命令执行超时时间（秒）
    ASR_MAX_WAIT = 30                     # ASR结果最大等待时间（秒）
    ASR_WAIT_INTERVAL = 1                 # ASR结果轮询间隔（秒）

    # UI元素资源ID常量
    MESSAGE_LIST_RES_ID = "com.larus.nova:id/message_list"        # 消息列表容器
    SPEAK_BUTTON_RES_ID = "com.larus.nova:id/speak_normal"        # 说话按钮
    BACK_ICON_RES_ID = "com.larus.nova:id/back_icon"              # 返回图标
    LOADING_DOT_RES_PREFIX = "com.larus.nova:id/v_dot"            # 加载指示器圆点前缀（v_dot1/v_dot2/v_dot3）

    # 用户消息位置判断阈值
    # 用户消息（右侧蓝色气泡）的 left 值较大（>=40），豆包回复（左侧黄色气泡）的 left 值较小
    USER_MESSAGE_LEFT_THRESHOLD = 40

    def __init__(self):
        """初始化驱动实例"""
        super().__init__()
        self._pre_last_msg = {}           # 存储上一次消息内容，用于去重

    def _get_driver_or_log(self, device_sn, task_id=None, test_case_id=None):
        """获取设备驱动并记录错误日志

        封装了驱动获取逻辑，当驱动不可用时自动记录错误日志，
        减少重复代码，统一错误处理方式。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID（可选）
            test_case_id: 测试用例ID（可选）

        Returns:
            设备驱动对象，如果获取失败返回None
        """
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(
                level='ERROR',
                content=f"Driver not available for device: {device_sn}",
                task_id=task_id,
                test_case_id=test_case_id
            )
        return driver

    def is_locked(self, device_sn):
        """检查Android设备是否处于锁屏状态

        通过ADB命令dumpsys window获取窗口状态，
        判断mDreamingLockscreen或isStatusBarKeyguard标志。

        Args:
            device_sn: 设备序列号

        Returns:
            bool: True表示锁屏状态，False表示已解锁或获取状态失败
        """
        driver = self._drivers.get(device_sn)
        if not driver:
            self._log(level='INFO', content=f"获取设备{device_sn}驱动失败")
            return False

        try:
            # 先点亮屏幕确保能获取到窗口状态
            driver.screen_on()
            time.sleep(self.SCREEN_ON_DELAY)

            # 执行ADB命令获取窗口状态
            result = subprocess.run(
                ['adb', '-s', device_sn, 'shell', 'dumpsys', 'window'],
                capture_output=True,
                text=True,
                timeout=self.ADB_TIMEOUT
            )

            # 解析命令输出判断锁屏状态
            if result.returncode == 0:
                # mDreamingLockscreen: 锁屏界面显示中
                # isStatusBarKeyguard: 状态栏锁屏激活
                if 'mDreamingLockscreen=true' in result.stdout or 'isStatusBarKeyguard=true' in result.stdout:
                    self._log(level='INFO', content=f"设备{device_sn} 处于锁屏状态")
                    return True
            self._log(level='INFO', content=f"设备{device_sn} 已解锁")
            return False

        except subprocess.TimeoutExpired:
            self._log(level='ERROR', content=f"检查锁屏状态超时（{self.ADB_TIMEOUT}s）")
            return False
        except Exception as e:
            self._log(level='ERROR', content=f"检查锁屏状态失败：{e}")
            return False

    @check_stop("initialize")
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化豆包App

        解锁设备后检查豆包App是否已运行，若未运行则启动并切换到豆包对话界面。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID（可选）
            test_case_id: 测试用例ID（可选）
            **kwargs: 其他参数

        Returns:
            bool: True表示初始化成功，False表示失败
        """
        # 先解锁设备
        self.unlock(device_sn)
        driver = self._get_driver_or_log(device_sn, task_id, test_case_id)
        if not driver:
            return False

        # 检查App是否已在运行且界面就绪（显示"按住说话"按钮）
        if self.APP_NAME in driver.app_list_running() and driver(text='按住说话').exists:
            self._log(level='INFO', content=f"app已初始化:{self.APP_NAME}", task_id=task_id, test_case_id=test_case_id)
            return True

        # 停止旧的App进程并重新初始化
        driver.app_stop(self.APP_NAME)
        initialize_success = super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)

        # 如果父类初始化失败，尝试手动启动App并切换到豆包对话
        if not initialize_success:
            if self.APP_NAME not in driver.app_list_running():
                driver.app_start(self.APP_NAME)
                # 点击返回按钮确保回到主界面
                driver.xpath(f'//*[@resource-id="{self.BACK_ICON_RES_ID}"]').click()
                # 点击豆包标签切换到对话界面
                driver(text='豆包').click()

        return True

    @check_stop("pre_process")
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """按住说话按钮开始录音

        通过模拟触摸按下操作，触发豆包App的语音录制功能。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID（可选）
            test_case_id: 测试用例ID（可选）
            **kwargs: 其他参数

        Returns:
            bool: True表示操作成功，False表示失败
        """
        driver = self._get_driver_or_log(device_sn, task_id, test_case_id)
        if not driver:
            return False

        # 定位说话按钮并执行按下操作
        btn = driver.xpath(f'//*[@resource-id="{self.SPEAK_BUTTON_RES_ID}"]')
        if btn.exists:
            x, y = btn.center()
            driver.touch.down(x, y)
            self._log(level='INFO', content=f"按住说话按钮 ({x}, {y})")
            return True
        else:
            self._log(level='WARNING', content=f"未找到说话按钮: {self.SPEAK_BUTTON_RES_ID}")
            return False

    @check_stop("post_process")
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """松开说话按钮结束录音

        通过模拟触摸抬起操作，结束语音录制并触发识别。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID（可选）
            test_case_id: 测试用例ID（可选）
            **kwargs: 其他参数

        Returns:
            bool: True表示操作成功，False表示失败
        """
        driver = self._get_driver_or_log(device_sn, task_id, test_case_id)
        if not driver:
            return False

        # 定位说话按钮并执行抬起操作
        btn = driver.xpath(f'//*[@resource-id="{self.SPEAK_BUTTON_RES_ID}"]')
        if btn.exists:
            x, y = btn.center()
            driver.touch.up(x, y)
            self._log(level='INFO', content="松开说话按钮")
            return True
        else:
            self._log(level='WARNING', content=f"未找到说话按钮: {self.SPEAK_BUTTON_RES_ID}")
            return False

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> list:
        """获取语音识别结果（ASR）

        在消息列表中查找用户发送的消息文本，
        通过resourceId为空的特征筛选用户消息，取最新一条作为识别结果。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID（可选）
            test_case_id: 测试用例ID（可选）
            **kwargs: 其他参数

        Returns:
            list: 包含识别结果字典的列表，如 [{"result_type": "real-time", "success": True, "message": "Success", "asr": "识别到的文本"}]
        """
        driver = self._get_driver_or_log(device_sn, task_id, test_case_id)
        if not driver:
            return [{"result_type": "real-time", "success": False, "message": "Driver not available", "asr": ""}]

        try:
            waited = 0
            # 轮询等待ASR结果，最多等待ASR_MAX_WAIT秒
            while waited < self.ASR_MAX_WAIT:
                # 检查消息列表中是否存在加载指示器圆点（正在思考/输入中）
                # v_dot1/v_dot2/v_dot3 都表示加载状态，只要存在任意一个就说明消息还在生成中
                loading_dots = driver.xpath(
                    f'//*[@resource-id="{self.MESSAGE_LIST_RES_ID}"]//*[contains(@resource-id, "{self.LOADING_DOT_RES_PREFIX}")]'
                ).all()
                if loading_dots:
                    self._log(level='DEBUG', content=f"检测到{len(loading_dots)}个加载指示器圆点，消息生成中...")
                    time.sleep(self.ASR_WAIT_INTERVAL)
                    waited += self.ASR_WAIT_INTERVAL
                    continue

                # 在消息列表中查找所有TextView元素
                elements_list = driver.xpath(
                    f'//*[@resource-id="{self.MESSAGE_LIST_RES_ID}"]//android.widget.TextView'
                ).all()

                # 筛选用户消息：有文本内容、resourceId为空、且left值大于等于阈值的TextView
                # 用户消息（右侧蓝色气泡）的left值较大（>=107），豆包回复（左侧黄色气泡）的left值较小
                user_messages = []
                for elem in elements_list:
                    try:
                        text = elem.text
                        info = elem.info
                        res_id = info.get('resourceId', '')
                        bounds = info.get('bounds', {})
                        left = bounds.get('left', 0)
                        if text and text.strip() and res_id == '' and left >= self.USER_MESSAGE_LEFT_THRESHOLD:
                            user_messages.append(text)
                    except Exception:
                        pass

                # 如果找到用户消息，取最后一条作为最新的ASR结果
                if user_messages:
                    asr_text = user_messages[-1]
                    self._log(level='DEBUG', content=f"获取用户输入的ASR结果: {asr_text}")
                    return [{"result_type": "real-time", "success": True, "message": "Success", "asr": asr_text}]

                # 未找到结果，等待后继续轮询
                time.sleep(self.ASR_WAIT_INTERVAL)
                waited += self.ASR_WAIT_INTERVAL

            # 等待超时
            self._log(level='WARNING', content=f"等待超时({self.ASR_MAX_WAIT}s)，未找到ASR文本元素")
            return [{"result_type": "real-time", "success": False, "message": "Timeout", "asr": ""}]

        except Exception as e:
            self._log(level='ERROR', content=f"获取ASR结果失败：{e}", task_id=task_id, test_case_id=test_case_id)
            return [{"result_type": "real-time", "success": False, "message": str(e), "asr": ""}]