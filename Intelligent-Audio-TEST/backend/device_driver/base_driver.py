from .utils import get_task_events, log_and_emit

class BaseDeviceDriver:
    """基础设备驱动类"""

    def __init__(self):
        """初始化基础驱动"""
        self._task_id = None
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

    def initialize(self, device_id, **kwargs) -> bool:
        """初始化设备
        
        Args:
            device_id: 设备ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否初始化成功
        """
        return True

    def unlock(self, device_id, **kwargs) -> None:
        """解锁设备
        
        Args:
            device_id: 设备ID
            **kwargs: 其他参数
        """
        pass

    def get_results(self, device_id, task_id=None, case_id=None, **kwargs) -> dict:
        """获取设备结果
        
        Args:
            device_id: 设备ID
            task_id: 任务ID
            **kwargs: 其他参数
            
        Returns:
            dict: 结果字典
        """
        return {}

    def pre_process(self, device_id, **kwargs) -> bool:
        """预处理设备
        
        Args:
            device_id: 设备ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否预处理成功
        """
        return True

    def is_locked(self, device_id):
        """检查设备是否锁屏
        
        Args:
            device_id: 设备ID
            
        Returns:
            bool: 是否锁屏
        """
        return False

    def post_process(self, device_id, **kwargs) -> bool:
        """后处理设备
        
        Args:
            device_id: 设备ID
            **kwargs: 其他参数
            
        Returns:
            bool: 是否后处理成功
        """
        return True

    def _log(self, level='INFO', content='', **kwargs):
        """记录日志
        
        Args:
            level: 日志级别
            content: 日志内容
            **kwargs: 其他参数
        """
        log_and_emit(level=level, module='DeviceDriver', content=content, **kwargs)

    def _check_stop(self, device_id=None, operation_name=""):
        """检查是否需要停止操作
        
        Args:
            device_id: 设备ID
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