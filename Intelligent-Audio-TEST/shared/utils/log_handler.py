import logging
import time
import sys
import threading
import queue
import re
import json
from datetime import datetime, timezone, timedelta
from flask import has_app_context, current_app
import hashlib

LOG_AND_EMIT_CONSOLE_LOG = None

_cached_socketio = None
_cached_app = None
_global_db_handler = None

LOG_ARCHIVE_THRESHOLD = 300000
LOG_HOT_DATA_DAYS = 7
# 归档统一写入 OSS（archives bucket），key 结构与 LogController.archive_logs 保持一致：
#   tasks/{task_id}/{case_id}/{date}.json
#   tasks/{task_id}/{date}.json
#   cases/{case_id}/{date}.json
#   other/{date}.json
LOG_ARCHIVE_RETENTION_DAYS = 90  # 归档文件保留90天（约3个月），过期自动删除
CONSOLE_LOG_MAX_LENGTH = 20000

def set_socketio(socketio):
    """设置全局 SocketIO 实例"""
    global _cached_socketio
    _cached_socketio = socketio
    if _global_db_handler:
        _global_db_handler.set_socketio(socketio)

def set_flask_app(app):
    """设置全局 Flask App 实例"""
    global _cached_app
    _cached_app = app
    if _global_db_handler:
        _global_db_handler.set_flask_app(app)

def get_db_handler():
    """获取或创建全局 DatabaseLogHandler 实例"""
    global _global_db_handler
    if _global_db_handler is None:
        _global_db_handler = DatabaseLogHandler()
        
        # 根据Flask应用的debug模式自动设置控制台日志
        console_log_enabled = LOG_AND_EMIT_CONSOLE_LOG
        if console_log_enabled is None:
            if _cached_app and hasattr(_cached_app, 'debug'):
                console_log_enabled = _cached_app.debug
            else:
                console_log_enabled = False
        
        _global_db_handler.set_console_log(console_log_enabled)
        if _cached_socketio:
            _global_db_handler.set_socketio(_cached_socketio)
        if _cached_app:
            _global_db_handler.set_flask_app(_cached_app)
        
        # 调试信息：确认单例已创建（只在调试模式输出）
        if console_log_enabled:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - get_db_handler - INFO - DatabaseLogHandler singleton created.")
    return _global_db_handler
# 保留log_and_emit作为包装函数，支持外部直接调用
def log_not_emit(level, module, content, category='system', source='backend', task_id=None, device_id=None, api_id=None, test_case_id=None, algorithm_type=None, push_to_websocket=False, enable_console_log=None, **kwargs):

    """核心方法：保存日志到数据库不推送到 WebSocket"""
    log_and_emit(level, module, content, category=category, source=source, task_id=task_id, device_id=device_id, api_id=api_id, test_case_id=test_case_id, algorithm_type=algorithm_type, push_to_websocket=False, enable_console_log=enable_console_log, **kwargs)
    return 
    
# 保留log_and_emit作为包装函数，支持外部直接调用
def log_and_emit(level, module, content, category='system', source='backend', task_id=None, device_id=None, api_id=None, test_case_id=None, algorithm_type=None, push_to_websocket=True, enable_console_log=None, **kwargs):
    """核心方法：保存日志到数据库并推送到 WebSocket"""
    
    # 从配置中获取控制台日志设置
    if enable_console_log is None:
        if _cached_app and hasattr(_cached_app, 'config'):
            enable_console_log = _cached_app.config.get('CONSOLE_LOG_ENABLED', True)
        else:
            enable_console_log = True
    
    # 在生产模式下，自动过滤DEBUG级别日志
    level_upper = level.upper()
    should_filter = False
    
    if level_upper == 'DEBUG' and not enable_console_log:
        should_filter = True
    
    if should_filter:
        return  # 直接返回，不记录DEBUG日志
    
    if enable_console_log:
        # 统一输出到 stdout 确保可见性
        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_and_emit - {level_upper} - [{module}] {content[:CONSOLE_LOG_MAX_LENGTH]}{'...' if len(content) > CONSOLE_LOG_MAX_LENGTH else ''}")
        sys.stdout.flush()
    
    try:
        # 创建日志记录对象
        record = logging.LogRecord(
            name=module,
            level=getattr(logging, level.upper(), logging.INFO),
            pathname='',
            lineno=0,
            msg=content,
            args=(),
            exc_info=None
        )
        record.module = module
        record.category = category
        record.source = source
        record.task_id = task_id
        record.device_id = device_id
        record.api_id = api_id
        record.test_case_id = test_case_id
        record.algorithm_type = algorithm_type
        
        # 将推送标志存入 record
        record.push_to_websocket = push_to_websocket
        
        for key, value in kwargs.items():
            setattr(record, key, value)
        
        if not hasattr(record, 'thread_id'):
            record.thread_id = kwargs.get('thread_id') or str(threading.get_ident())
        
        # 标记来自 log_and_emit，避免在 handler.emit 中重复打印
        record.from_log_and_emit = True
        
        handler = get_db_handler()
        handler.emit(record)
        
    except Exception as e:
        # 如果获取不到 handler，尝试直接打印
        print(f"Error in log_and_emit: {str(e)}", file=sys.stderr)

class DatabaseLogHandler(logging.Handler):
    """
    异步数据库日志处理器，使用队列和后台线程写入数据库并推送 WebSocket
    支持批量写入、冷热数据分离、自动归档
    """
    def __init__(self):
        super().__init__()
        self.recent_logs = {}
        self.max_recent_logs = 200
        self.log_ttl = 10
        self.enable_console_log = False
        self.socketio_instance = None
        self.flask_app = None
        
        self._last_db_warning_time = 0
        self._last_ws_warning_time = 0
        self._warning_throttle = 5
        
        self.queue = queue.Queue(maxsize=50000)
        
        self._batch_size = 100
        self._batch_timeout = 1.0
        self._last_archive_check = 0
        self._archive_check_interval = 300
        
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
    def set_socketio(self, socketio):
        """显式设置 SocketIO 实例"""
        self.socketio_instance = socketio

    def set_flask_app(self, app):
        """显式设置 Flask App 实例"""
        self.flask_app = app

    def _worker(self):
        Log = None
        db = None
        SessionLocal = None
        batch = []
        last_flush = time.time()
        
        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Worker thread started with batch mode.")
        
        while True:
            try:
                try:
                    data = self.queue.get(timeout=0.1)
                    if data is None:
                        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Worker thread received exit signal.")
                        break
                    batch.append(data)
                except queue.Empty:
                    pass
                
                current_time = time.time()
                should_flush = (
                    len(batch) >= self._batch_size or
                    (batch and (current_time - last_flush) >= self._batch_timeout)
                )
                
                if should_flush and batch:
                    Log, db, SessionLocal = self._init_db_components(Log, db, SessionLocal)
                    if Log and SessionLocal and self.flask_app:
                        self._process_batch(batch, Log, SessionLocal)

                    # flush 后 batch 中每条 data 已带上数据库 id（或 _db_failed 标记），再推送 WebSocket
                    # 仅推送成功入库的日志，失败批次由 _emit_websocket 内部跳过
                    for data in batch:
                        if data.get('push_to_websocket') and data.get('id') is not None:
                            self._emit_websocket(data)

                    batch = []
                    last_flush = current_time

                    if current_time - self._last_archive_check >= self._archive_check_interval:
                        if Log and SessionLocal:
                            self._check_and_archive(Log, SessionLocal)
                        self._last_archive_check = current_time
                else:
                    # batch 未满且未超时：暂不推送，等入库后再推（保证前端拿到合法 id）
                    pass
                        
            except Exception as e:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - CRITICAL ERROR - {str(e)}")
                time.sleep(0.5)
    
    def _init_db_components(self, Log, db, SessionLocal):
        if self.flask_app is None:
            global _cached_app
            if _cached_app:
                self.flask_app = _cached_app
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Flask App instance acquired.")
        
        if self.socketio_instance is None:
            global _cached_socketio
            if _cached_socketio:
                self.socketio_instance = _cached_socketio
            elif self.flask_app:
                try:
                    self.socketio_instance = self.flask_app.extensions.get('socketio')
                except:
                    pass
        
        if self.flask_app is None:
            return None, None, None
        
        try:
            with self.flask_app.app_context():
                from shared.models.models import Log as LogModel
                from shared.models.database import db as db_instance
                from sqlalchemy.orm import sessionmaker
                Log = LogModel
                db = db_instance
                if db.engine:
                    SessionLocal = sessionmaker(bind=db.engine)
                    return Log, db, SessionLocal
                return None, None, None
        except ImportError:
            try:
                with self.flask_app.app_context():
                    from models.models import Log as LogModel
                    from models.database import db as db_instance
                    from sqlalchemy.orm import sessionmaker
                    Log = LogModel
                    db = db_instance
                    if db.engine:
                        SessionLocal = sessionmaker(bind=db.engine)
                        return Log, db, SessionLocal
                    return None, None, None
            except Exception as e:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - IMPORT ERROR - {str(e)}")
                return None, None, None
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INIT ERROR - {str(e)}")
            return None, None, None
    
    def _process_batch(self, batch, Log, SessionLocal):
        if not Log or not SessionLocal or not self.flask_app:
            return

        with self.flask_app.app_context():
            session = SessionLocal()
            try:
                for data in batch:
                    log_entry = Log(
                        time=data['time'],
                        level=data['level'],
                        category=data['category'],
                        module=data['module'],
                        source=data['source'],
                        content=data['content'],
                        task_id=data.get('task_id'),
                        device_id=data.get('device_id'),
                        api_id=data.get('api_id'),
                        test_case_id=data.get('test_case_id'),
                        thread_id=data.get('thread_id'),
                        algorithm_type=data.get('algorithm_type')
                    )
                    session.add(log_entry)
                    session.flush()
                    data['id'] = log_entry.id
                    # 记录入库时间，供 WS 推送复用，避免 time 字段漂移
                    data['_ws_time'] = data['time'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(data['time'], 'strftime') else None
                session.commit()
                if self.enable_console_log:
                    print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - DEBUG - Batch saved {len(batch)} logs.")
            except Exception as e:
                session.rollback()
                # 批次失败：清空 id、标记失败，_emit_websocket 会跳过这些条目
                for data in batch:
                    data['id'] = None
                    data['_db_failed'] = True
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - DB ERROR - {str(e)}")
            finally:
                session.close()
    
    def _emit_websocket(self, data):
        """
        推送日志到前端。
        - 全量频道 `/ws/logs`：按 sid 过滤器精准 emit（skip_peer=False 只发给本进程该 sid）。
        - 任务频道 task_{task_id}：用 room 广播给订阅了该 task 的客户端（无过滤器干扰）。
        - 只有在数据库 flush 成功（data 含有效 id）后才推送，避免前端拿到不存在的 id。
        """
        is_ws_ready = (
            self.socketio_instance and
            hasattr(self.socketio_instance, 'server') and
            self.socketio_instance.server is not None
        )

        if not is_ws_ready:
            # 尝试从全局获取 socketio 实例
            global _cached_socketio
            if _cached_socketio:
                self.socketio_instance = _cached_socketio
            elif self.flask_app:
                try:
                    self.socketio_instance = self.flask_app.extensions.get('socketio')
                except Exception:
                    pass
            is_ws_ready = (
                self.socketio_instance and
                hasattr(self.socketio_instance, 'server') and
                self.socketio_instance.server is not None
            )

        if not is_ws_ready:
            return

        # 只有成功入库（拿到 id）才推送，避免前端显示不存在的日志
        if data.get('id') is None and data.get('_db_failed'):
            return

        try:
            utc_plus_8 = timezone(timedelta(hours=8))
            log_time = data.get('_ws_time') or datetime.now(utc_plus_8).strftime('%Y-%m-%d %H:%M:%S')
            log_payload = {
                "id": data.get('id'),
                "time": log_time,
                "level": data['level'],
                "module": data['module'],
                "content": data['content'],
                "mark": "",
                "task_id": data.get('task_id'),
                "test_case_id": data.get('test_case_id'),
                "category": data.get('category'),
                "source": data.get('source'),
            }

            # 1) 全量频道：按 sid 过滤精准下发
            try:
                from api_gateway.controllers.log_controller import log_filter_registry
                matched_sids = log_filter_registry.match(data)
                for sid in matched_sids:
                    self.socketio_instance.emit(
                        'logs',
                        {'type': 'LOG_BATCH', 'data': [log_payload]},
                        namespace='/ws/logs',
                        to=sid,
                    )
            except ImportError:
                # api_gateway 未加载（其他子进程场景），退化为全量广播
                self.socketio_instance.emit('logs', {'type': 'LOG_BATCH', 'data': [log_payload]}, namespace='/ws/logs')

            # 2) 任务频道：room 广播给订阅了该 task 的连接
            if data.get('task_id'):
                self.socketio_instance.emit(
                    'task_log',
                    {'taskId': str(data['task_id']), 'log': log_payload},
                    room=f"task_{data['task_id']}",
                    namespace='/ws/logs',
                )
        except Exception as ws_error:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WS ERROR - {str(ws_error)}")
    
    def _check_and_archive(self, Log, SessionLocal):
        if not Log or not SessionLocal or not self.flask_app:
            return
        
        try:
            with self.flask_app.app_context():
                session = SessionLocal()
                try:
                    total_count = session.query(Log).count()
                    
                    if total_count > LOG_ARCHIVE_THRESHOLD:
                        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Log count {total_count} exceeds threshold {LOG_ARCHIVE_THRESHOLD}, starting archive...")
                        self._archive_old_logs(Log, SessionLocal, session, total_count)

                    # 清理过期归档文件（每次归档检查时都执行）
                    self._clean_expired_archives()
                finally:
                    session.close()
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - ARCHIVE ERROR - {str(e)}")
    
    def _archive_old_logs(self, Log, SessionLocal, session, total_count):
        """
        将冷数据日志归档到 OSS（archives bucket），key 结构与 LogController.archive_logs 一致：
            tasks/{task_id}/{case_id}/{date}.json
            tasks/{task_id}/{date}.json
            cases/{case_id}/{date}.json
            other/{date}.json
        归档完成后从数据库删除对应日志。
        """
        from shared.clients.oss_client import oss

        cutoff_date = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=LOG_HOT_DATA_DAYS)
        old_logs = session.query(Log).filter(Log.time < cutoff_date).order_by(Log.time.asc()).limit(100000).all()

        if not old_logs:
            # 没有冷数据，但总量仍超阈值：直接删除最旧的（无归档价值）
            delete_count = total_count - LOG_ARCHIVE_THRESHOLD
            if delete_count > 0:
                oldest_logs = session.query(Log).order_by(Log.time.asc()).limit(delete_count).all()
                log_ids = [log.id for log in oldest_logs]
                session.query(Log).filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
                session.commit()
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Deleted {len(log_ids)} oldest logs (no archive needed).")
            return

        # 分组（与 LogController.archive_logs 对齐）：
        #   task_case_logs[(task_id, case_id, date)] = [log_data, ...]
        #   task_only_logs[(task_id, date)] = [log_data, ...]
        #   case_only_logs[(case_id, date)] = [log_data, ...]
        #   other_logs[date] = [log_data, ...]
        task_case_logs = {}
        task_only_logs = {}
        case_only_logs = {}
        other_logs = {}

        for log in old_logs:
            log_data = {
                'id': log.id,
                'time': log.time.isoformat() if log.time else None,
                'level': log.level,
                'category': log.category,
                'module': log.module,
                'source': log.source,
                'content': log.content,
                'mark': log.mark,
                'device_id': log.device_id,
                'task_id': log.task_id,
                'test_case_id': log.test_case_id,
                'api_id': log.api_id,
                'thread_id': log.thread_id,
                'algorithm_type': log.algorithm_type,
                'created_at': log.created_at.isoformat() if log.created_at else None
            }
            log_date = (log.time or log.created_at or datetime.now(timezone(timedelta(hours=8)))).strftime('%Y-%m-%d')

            if log.task_id and log.test_case_id:
                key = (log.task_id, log.test_case_id, log_date)
                task_case_logs.setdefault(key, []).append(log_data)
            elif log.task_id:
                key = (log.task_id, log_date)
                task_only_logs.setdefault(key, []).append(log_data)
            elif log.test_case_id:
                key = (log.test_case_id, log_date)
                case_only_logs.setdefault(key, []).append(log_data)
            else:
                other_logs.setdefault(log_date, []).append(log_data)

        def _save_archive_oss(oss_key, logs):
            """上传归档到 OSS（合并已存在文件，按时间排序）"""
            existing_logs = []
            if oss.exists('archives', oss_key):
                try:
                    data = oss.download_bytes('archives', oss_key)
                    existing_logs = json.loads(data)
                except Exception:
                    existing_logs = []
            existing_logs.extend(logs)
            existing_logs.sort(key=lambda x: x.get('time', '') or '')
            oss.upload_bytes(
                json.dumps(existing_logs, ensure_ascii=False, indent=2).encode('utf-8'),
                'archives', oss_key, content_type='application/json'
            )

        archived_count = 0
        for (task_id, case_id, log_date), logs in task_case_logs.items():
            _save_archive_oss(f'tasks/{task_id}/{case_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for (task_id, log_date), logs in task_only_logs.items():
            _save_archive_oss(f'tasks/{task_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for (case_id, log_date), logs in case_only_logs.items():
            _save_archive_oss(f'cases/{case_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for log_date, logs in other_logs.items():
            _save_archive_oss(f'other/{log_date}.json', logs)
            archived_count += len(logs)

        log_ids_to_delete = [log.id for log in old_logs]
        session.query(Log).filter(Log.id.in_(log_ids_to_delete)).delete(synchronize_session=False)
        session.commit()

        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Archived {archived_count} logs to OSS (task+case: {len(task_case_logs)}, task: {len(task_only_logs)}, case: {len(case_only_logs)}, other: {len(other_logs)})")

        remaining_count = session.query(Log).count()
        if remaining_count > LOG_ARCHIVE_THRESHOLD:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Still {remaining_count} logs, will continue archiving next cycle.")

    def _clean_expired_archives(self):
        """清理 OSS 上过期的归档对象（LastModified 超过 LOG_ARCHIVE_RETENTION_DAYS 天）"""
        from shared.clients.oss_client import oss

        bucket = oss._bucket('archives')
        cutoff_time = time.time() - LOG_ARCHIVE_RETENTION_DAYS * 86400
        deleted_count = 0

        # 分页列出全部对象（list_objects_v2 单次最多 1000 条）
        paginator = oss._client.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get('Contents', []):
                    last_modified = obj['LastModified'].timestamp()
                    if last_modified < cutoff_time:
                        try:
                            oss._client.delete_object(Bucket=bucket, Key=obj['Key'])
                            deleted_count += 1
                        except Exception:
                            pass
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - Clean expired archives failed: {str(e)}")
            return

        if deleted_count > 0:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Cleaned {deleted_count} expired archive objects on OSS, older than {LOG_ARCHIVE_RETENTION_DAYS} days.")

    def set_console_log(self, enable):
        self.enable_console_log = enable
    
    def _console_log(self, level, message):
        if self.enable_console_log:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - DatabaseLogHandler - {level} - {message}")
            sys.stdout.flush()
    
    def emit(self, record):
        """将日志记录放入异步队列"""
        try:
            # 跳过内部模块日志
            if hasattr(record, 'module') and record.module in ['log_controller', 'log_handler', 'database']:
                return
            
            log_message = self.format(record)
            
            # 去掉日志内容中的时间戳前缀 [2026-02-10T20:13:25.243757+08:00]
            log_message = re.sub(r'^\[\d{4}-\d{2}-\d{2}T[\d\.:+\-]+\]', '', log_message).strip()
            
            # # 如果是标准的 logging 调用（不是通过 log_and_emit），也打印到控制台
            if not getattr(record, 'from_log_and_emit', False):
                self._console_log(record.levelname.upper(), f"[{record.module}] {log_message[:CONSOLE_LOG_MAX_LENGTH]}{'...' if len(log_message) > CONSOLE_LOG_MAX_LENGTH else ''}")
            
            # 跳过 WebSocket 相关日志
            if 'WebSocket' in log_message or 'socketio' in log_message or 'emitting event' in log_message:
                return
            
            # 去重检查：指纹带上 task_id/test_case_id/category，避免同结构不同用例日志被误吞
            ctx_key = f"{record.levelno}-{record.module}-{getattr(record, 'task_id', None)}-{getattr(record, 'test_case_id', None)}-{getattr(record, 'category', '')}-{log_message}"
            log_fingerprint = hashlib.md5(ctx_key.encode('utf-8')).hexdigest()
            current_time = datetime.now().timestamp()

            if log_fingerprint in self.recent_logs:
                if current_time - self.recent_logs[log_fingerprint] < self.log_ttl:
                    return

            self.recent_logs[log_fingerprint] = current_time
            
            # 清理过期指纹
            if len(self.recent_logs) > self.max_recent_logs:
                self.recent_logs = {fp: ts for fp, ts in self.recent_logs.items() if current_time - ts < self.log_ttl}

            # 准备异步写入的数据
            log_data = {
                'time': datetime.now(timezone(timedelta(hours=8))),
                'level': record.levelname.upper(),
                'module': record.module if hasattr(record, 'module') else 'unknown',
                'category': getattr(record, 'category', 'system').lower(),
                'source': getattr(record, 'source', 'backend').lower(),
                'content': log_message,
                'task_id': getattr(record, 'task_id', None),
                'device_id': getattr(record, 'device_id', None),
                'api_id': getattr(record, 'api_id', None),
                'test_case_id': getattr(record, 'test_case_id', None),
                'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
                'algorithm_type': getattr(record, 'algorithm_type', None),
                'push_to_websocket': getattr(record, 'push_to_websocket', True)
            }
            
            # 放入队列：非阻塞，满时打印 stderr（不被 console_log 开关屏蔽），便于发现丢日志
            try:
                self.queue.put_nowait(log_data)
            except queue.Full:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - WARN - Log queue full (maxsize={self.queue.maxsize}), dropping log: [{log_data.get('level')}] {log_data.get('module')} - {log_data.get('content')[:200]}", file=sys.stderr)
            except Exception as qe:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - put queue failed: {qe}", file=sys.stderr)

        except Exception as e:
            # emit 自身异常总是打印，避免静默失败
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - emit failed: {str(e)}", file=sys.stderr)

