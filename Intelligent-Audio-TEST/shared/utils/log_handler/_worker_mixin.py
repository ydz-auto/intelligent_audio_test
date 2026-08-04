"""DatabaseLogHandler 工作线程与数据库批次写入相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import time
import queue
from datetime import datetime, timezone, timedelta

from . import _state


class _WorkerMixin:
    """后台工作线程、数据库组件初始化、批次写入。"""

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
                    if Log and SessionLocal:
                        self._process_batch(batch, Log, SessionLocal)
                    else:
                        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - _init_db_components returned None, Log={Log is not None}, SessionLocal={SessionLocal is not None}")

                    # flush 后 batch 中每条 data 已带上数据库 id（或 _db_failed 标记），再推送 WebSocket
                    # 仅推送成功入库的日志，失败批次由 _emit_websocket 内部跳过
                    for data in batch:
                        if data.get('push_to_websocket') and data.get('id') is not None:
                            self._emit_websocket(data)
                        else:
                            # 调试：跳过原因
                            if data.get('push_to_websocket'):
                                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - Skip WS push: push_to_websocket={data.get('push_to_websocket')}, id={data.get('id')}, _db_failed={data.get('_db_failed')}")

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
        if self.socketio_instance is None:
            if _state._cached_socketio:
                self.socketio_instance = _state._cached_socketio

        try:
            from shared.models.models import Log as LogModel
            from shared.models.database import get_engine
            from sqlalchemy.orm import sessionmaker
            Log = LogModel
            engine = get_engine()
            if engine is not None:
                SessionLocal = sessionmaker(bind=engine)
                return Log, db, SessionLocal
            # 调试：engine 为 None 时打印
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - get_engine() returned None")
            return None, None, None
        except ImportError:
            try:
                from models.models import Log as LogModel
                from models.database import _engine_ref
                from sqlalchemy.orm import sessionmaker
                Log = LogModel
                engine = _engine_ref[0]
                if engine is not None:
                    SessionLocal = sessionmaker(bind=engine)
                    return Log, db, SessionLocal
                return None, None, None
            except Exception as e:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - IMPORT ERROR - {str(e)}")
                return None, None, None
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INIT ERROR - {str(e)}")
            return None, None, None

    def _process_batch(self, batch, Log, SessionLocal):
        if not Log or not SessionLocal:
            return

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
