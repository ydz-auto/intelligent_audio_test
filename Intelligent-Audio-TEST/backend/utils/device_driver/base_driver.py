from .utils import get_task_events, log_and_emit

class BaseDeviceDriver:
    """基础设备驱动类"""

    def __init__(self):
        """初始化基础驱动"""
        self._task_id = None
        self._test_case_id = None
        self._device_id = None
        self._mock_mode = False
        # 弹窗处理相关配置
        self._close_buttons = ['确定', '取消', '关闭', 'Done', 'Cancel', 'Close']
        self._popup_keywords = ['权限', 'permission', '授权', 'authorize']

    def set_mock_mode(self, mock_mode: bool):
        """设置模拟模式
        
        Args:
            mock_mode: 是否启用模拟模式
        """
        self._mock_mode = mock_mode

    def get_mock_mode(self) -> bool:
        """获取模拟模式状态
        
        Returns:
            bool: 是否启用模拟模式
        """
        return self._mock_mode

    def set_task_id(self, task_id):
        """设置任务ID
        
        Args:
            task_id: 任务ID
        """
        self._task_id = task_id

    def set_test_case_id(self, test_case_id):
        """设置测试用例ID
        
        Args:
            test_case_id: 测试用例ID
        """
        self._test_case_id = test_case_id

    def set_device_id(self, device_id):
        """设置设备数据库ID（用于日志记录）
        
        Args:
            device_id: 设备在数据库中的ID（整数）
        """
        self._device_id = device_id

    def _get_events(self):
        """获取任务事件
        
        Returns:
            dict: 任务事件字典
        """
        if not self._task_id:
            return None
        return get_task_events(self._task_id)

    def scan(self):
        """扫描设备
        
        Returns:
            list: 设备列表
        """
        return []

    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """初始化设备
        
        Args:
            device_sn: 设备序列号
            task_id: 任务ID
            test_case_id: 测试用例ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否初始化成功
        """
        return True

    def unlock(self, device_sn, **kwargs) -> None:
        """解锁设备
        
        Args:
            device_sn: 设备序列号
            **kwargs: 其他参数
        """
        pass

    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """获取设备结果
        
        Args:
            device_sn: 设备序列号
            task_id: 任务ID
            test_case_id: 测试用例ID
            **kwargs: 其他参数
            
        Returns:
            dict: 结果字典
        """
        return {}

    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """预处理设备
        
        Args:
            device_sn: 设备序列号
            task_id: 任务ID
            test_case_id: 测试用例ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否预处理成功
        """
        return True

    def is_locked(self, device_sn):
        """检查设备是否锁屏
        
        Args:
            device_sn: 设备序列号
            
        Returns:
            bool: 是否锁屏
        """
        return False

    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """后处理设备
        
        Args:
            device_sn: 设备序列号
            task_id: 任务ID
            test_case_id: 测试用例ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否后处理成功
        """
        return True

    def extract_results_from_archive(self, task_id=None, test_case_id=None, device_sn=None, **kwargs):
        """从存档文件提取设备输出结果

        当设备结果不是实时获取、而是先拉取存档文件再解析时，
        子类可重写此方法实现非实时结果的提取逻辑。

        Args:
            task_id: 任务ID
            test_case_id: 用例ID
            device_sn: 设备序列号
            **kwargs: 其他参数

        Returns:
            list: 结果列表，每项为包含 result_type / success / message 等字段的 dict；
                  默认返回空列表表示无需存档提取
        """
        return []

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束后清理设备状态（与 initialize 对称）

        在每轮循环结束或整个用例结束时调用，用于退出功能页面、
        停止录音、关闭 APP 等资源释放操作。

        Args:
            device_sn: 设备序列号
            task_id: 任务ID
            test_case_id: 测试用例ID
            **kwargs: 其他参数

        Returns:
            bool: 是否清理成功
        """
        return True

    def set_volume(self, device_sn, level: int) -> bool:
        """设置设备系统音量(0-100)，默认不操作
        
        Args:
            device_sn: 设备序列号
            level: 音量级别(0-100)
            
        Returns:
            bool: 是否设置成功
        """
        self._log(level='DEBUG', content=f"设备 {device_sn} 不支持音量控制")
        return True

    def get_volume(self, device_sn) -> int:
        """获取设备系统音量(0-100)
        
        Args:
            device_sn: 设备序列号
            
        Returns:
            int: 当前音量(0-100)，不支持返回 -1
        """
        return -1

    def _log(self, level='INFO', content='', test_case_id=None, task_id=None, **kwargs):
        """记录日志
        
        Args:
            level: 日志级别
            content: 日志内容
            test_case_id: 测试用例ID
            task_id: 任务ID
            **kwargs: 其他参数
        """
        final_test_case_id = test_case_id or self._test_case_id
        final_task_id = task_id or self._task_id
        final_device_id = self._device_id
        log_and_emit(level=level, module='DeviceDriver', content=content, task_id=final_task_id, test_case_id=final_test_case_id, device_id=final_device_id, **kwargs)

    def _check_stop(self, operation_name=""):
        """检查是否需要停止操作
        
        Args:
            operation_name: 操作名称
            
        Returns:
            bool: 是否需要停止
        """
        events = self._get_events()
        if events is None:
            return False
        
        stop_event = events.get('stop_event')
        if stop_event and stop_event.is_set():
            self._log(level='INFO', content=f"Task stopped during {operation_name} operation")
            return True
        
        pause_event = events.get('pause_event')
        if pause_event and not pause_event.is_set():
            self._log(level='INFO', content=f"Task paused during {operation_name} operation")
            import time
            while pause_event.is_set():
                time.sleep(0.1)
                # 检查是否同时被停止
                if stop_event and stop_event.is_set():
                    self._log(level='INFO', content=f"Task stopped during {operation_name} operation")
                    return True
        
        return False

    def _wait_for_condition(self, condition_fn, timeout=30, interval=1.0, operation_name=""):
        """等待条件满足，带超时和停止检查

        Args:
            condition_fn: 无参可调用对象，返回 True 表示条件满足
            timeout: 最大等待秒数
            interval: 轮询间隔秒数
            operation_name: 操作名称（用于日志）

        Returns:
            bool: True 表示条件满足，False 表示超时或被停止
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self._check_stop(operation_name):
                return False
            try:
                if condition_fn():
                    return True
            except Exception:
                pass
            time.sleep(interval)
        self._log(
            level='WARNING',
            content=f"等待条件超时: {operation_name or 'condition'}, timeout={timeout}s"
        )
        return False
