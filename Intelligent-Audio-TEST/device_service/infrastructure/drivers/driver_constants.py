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

# 安卓驱动缓存设备连接上限(条)：超过后按 LRU 淘汰最久未用的设备连接,
# 防止长跑服务中 _drivers 连接只增不减导致内存泄漏
MAX_CACHED_DEVICES = config_manager.get_value('device_timing', 'max_cached_devices', 10)

# —— 语音通话驱动（小艺/豆包/ChatGPT）参数 ——
# AI 回复检测（RMS 能量法，基于 AI PCM 尾部能量）
RMS_THRESHOLD = config_manager.get_value('device_timing', 'rms_threshold', 300)
RMS_SILENCE_SECONDS = config_manager.get_value('device_timing', 'rms_silence_seconds', 8)
RMS_START_TIMEOUT = config_manager.get_value('device_timing', 'rms_start_timeout', 25)
RMS_END_TIMEOUT = config_manager.get_value('device_timing', 'rms_end_timeout', 60)
RMS_SCAN_SECONDS = config_manager.get_value('device_timing', 'rms_scan_seconds', 15)
# PCM 尾部读取 hdc 超时（1s 音频 base64 传输 / 15s 历史扫描传输）
RMS_READ_TIMEOUT = config_manager.get_value('device_timing', 'rms_read_timeout', 20)
RMS_SCAN_HDC_TIMEOUT = config_manager.get_value('device_timing', 'rms_scan_hdc_timeout', 40)
# ai PCM 首帧检测超时（毫秒）
AI_PCM_FIRST_FRAME_TIMEOUT_MS = config_manager.get_value('device_timing', 'ai_pcm_first_frame_timeout_ms', 15000)
# 小艺 UI 法回复检测超时（秒）：等回复开始 / 等"说话可打断"重现 / 等"正在听…"出现
REPLY_START_TIMEOUT = config_manager.get_value('device_timing', 'reply_start_timeout', 300)
REPLY_STATE_TIMEOUT = config_manager.get_value('device_timing', 'reply_state_timeout', 10)
REPLY_LISTEN_TIMEOUT = config_manager.get_value('device_timing', 'reply_listen_timeout', 300)
# barge-in 打断轮轮间延迟（秒）：检测到 AI 开口后延迟再放下一轮打断音频
BARGE_IN_DELAY_SECONDS = config_manager.get_value('device_timing', 'barge_in_delay_seconds', 1)
CASE_BARGE_IN_DELAY_SECONDS = config_manager.get_value('device_timing', 'case_barge_in_delay_seconds', 5)
# 停止检查轮询间隔（秒）：长延迟分片 sleep，每片检查一次任务是否被停止/暂停（可随时打断）
CHECK_STOP_POLL_INTERVAL = config_manager.get_value('device_timing', 'check_stop_poll_interval', 0.5)

# 设备路径
DEVICE_TMP_DIR = '/data/local/tmp'
