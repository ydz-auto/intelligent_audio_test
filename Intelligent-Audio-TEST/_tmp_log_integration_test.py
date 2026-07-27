"""集成测试：用 mock 验证真实代码路径（不连真 DB/SocketIO）。"""
import sys, os, time, json, queue
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 确保 conda env site-packages 可用
sys.path.insert(0, r'D:\00_env\conda_envs\intelligent_audio_test\Lib\site-packages')

passed = 0
failed = 0
def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  OK  {name}')
    else:
        failed += 1
        print(f'  FAIL {name}  {detail}')

print('=== 1. DatabaseLogHandler.emit 入队 + 去重指纹带上下文 ===')
from shared.utils.log_handler import DatabaseLogHandler, get_db_handler
import logging

# 重置单例
import shared.utils.log_handler as lh
lh._global_db_handler = None
handler = DatabaseLogHandler()
handler.enable_console_log = False
# 模拟 socketio 未就绪，避免 worker 线程真的去连 DB
handler.socketio_instance = None
handler.flask_app = MagicMock()

# 构造两条同结构不同用例的 record
def make_record(level, module, msg, task_id=None, test_case_id=None, category='execution'):
    r = logging.LogRecord(name=module, level=getattr(logging, level.upper()), pathname='', lineno=0, msg=msg, args=(), exc_info=None)
    r.module = module
    r.category = category
    r.source = 'backend'
    r.task_id = task_id
    r.test_case_id = test_case_id
    r.algorithm_type = None
    r.device_id = None
    r.api_id = None
    r.thread_id = 't1'
    r.push_to_websocket = True
    r.from_log_and_emit = True
    return r

# 清空队列便于观察
while not handler.queue.empty():
    handler.queue.get_nowait()

r1 = make_record('INFO', 'Evaluation', 'build payload', task_id=1, test_case_id='case_A')
r2 = make_record('INFO', 'Evaluation', 'build payload', task_id=1, test_case_id='case_B')  # 同结构不同用例
r3 = make_record('INFO', 'Evaluation', 'build payload', task_id=1, test_case_id='case_A')  # 完全相同（应被去重）

handler.emit(r1)
handler.emit(r2)
handler.emit(r3)

qsize = handler.queue.qsize()
check('同结构不同用例都入队（不被误去重）', qsize == 2, f'qsize={qsize} 期望2')
# 注意：r3 与 r1 完全相同，应被去重，所以队列里是 r1+r2=2 条

print()
print('=== 2. _process_batch 失败时清空 id + 标记 _db_failed ===')
batch = [
    {'time': datetime.now(timezone(timedelta(hours=8))), 'level': 'INFO', 'category': 'system',
     'module': 'Test', 'source': 'backend', 'content': 'msg1', 'task_id': None,
     'device_id': None, 'api_id': None, 'test_case_id': None, 'thread_id': 't',
     'algorithm_type': None, 'push_to_websocket': True},
]
# 模拟一个会失败的 session
mock_session = MagicMock()
#