"""设备驱动常量 — 集中管理时序参数和设备路径，消除魔法数字"""

from shared.utils.config_manager import config_manager

# 时序参数（秒）— UI 操作间隔、动画等待等
UI_WAIT = config_manager.get_value('device_timing', 'ui_wait', 0.2)
SHORT_WAIT = config_manager.get_value('device_timing', 'short_wait', 0.1)
NORMAL_WAIT = config_manager.get_value('device_timing', 'normal_wait', 1.0)
LONG_WAIT = config_manager.get_value('device_timing', 'long_wait', 2.0)
EXTRA_LONG_WAIT = config_manager.get_value('device_timing', 'extra_long_wait', 5.0)
# 解锁滑动等待（秒）
UNLOCK_SWIPE_WAIT = config_manager.get_value('device_timing', 'unlock_swipe_wait', 0.5)
# 弹窗关闭等待（秒）
POPUP_CLOSE_WAIT = config_manager.get_value('device_timing', 'popup_close_wait', 0.5)
# 翻译服务启用等待（秒）
TRANSLATION_WAIT = config_manager.get_value('device_timing', 'translation_wait', 1.5)
# 应用启动等待（秒）
APP_LAUNCH_WAIT = config_manager.get_value('device_timing', 'app_launch_wait', 3)

# 超时参数（秒）— subprocess / hdc 命令超时
ADB_TIMEOUT = config_manager.get_value('device_timing', 'adb_timeout', 10)
HDC_TIMEOUT = config_manager.get_value('device_timing', 'hdc_timeout', 30)
LONG_HDC_TIMEOUT = config_manager.get_value('device_timing', 'long_hdc_timeout', 300)
EXTRA_LONG_HDC_TIMEOUT = config_manager.get_value('device_timing', 'extra_long_hdc_timeout', 120)

# 设备路径
DEVICE_TMP_DIR = '/data/local/tmp'
