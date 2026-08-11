"""DatabaseLogHandler 工作线程与数据库批次写入相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。

P0-3 DDD 改造：日志写入改为通过 gRPC 调用 task_service.BatchCreateLogs，
不再直接 import task_service PO 或操作 DB session。
"""

import time
import queue
from datetime import datetime, timezone, timedelta

from . import _state


class _WorkerMixin:
    """后台工作线程、数据库组件初始化、批次写入。"""

    def _worker(self):
        batch = []
        last_flush = time.time()

        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Worker thread started with batch mode (gRPC).")

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
                    self._process_batch(batch)

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
                        self._check_and_archive()
                        self._last_archive_check = current_time
                else:
                    # batch 未满且未超时：暂不推送，等入库后再推（保证前端拿到合法 id）
                    pass

            except Exception as e:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - CRITICAL ERROR - {str(e)}")
                time.sleep(0.5)

    def _process_batch(self, batch):
        """通过 gRPC 批量写入日志（P0-3: 替代直连 DB session）"""
        try:
            from shared.clients.grpc_clients import batch_create_logs
            # 将 batch 中的 data 序列化为 JSON 兼容格式（datetime → ISO 字符串）
            logs_payload = []
            for data in batch:
                t = data.get('time')
                if hasattr(t, 'isoformat'):
                    t = t.isoformat()
                logs_payload.append({
                    'time': t,
                    'level': data.get('level', ''),
                    'category': data.get('category', ''),
                    'module': data.get('module', ''),
                    'source': data.get('source', ''),
                    'content': data.get('content', ''),
                    'task_id': data.get('task_id'),
                    'device_id': data.get('device_id'),
                    'api_id': data.get('api_id'),
                    'test_case_id': data.get('test_case_id'),
                    'thread_id': data.get('thread_id'),
                    'algorithm_type': data.get('algorithm_type'),
                })
            ids = batch_create_logs(logs_payload)
            for i, data in enumerate(batch):
                if i < len(ids) and ids[i] is not None:
                    data['id'] = ids[i]
                    data['_ws_time'] = data['time'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(data.get('time'), 'strftime') else None
                else:
                    data['id'] = None
                    data['_db_failed'] = True
            if self.enable_console_log:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - DEBUG - Batch saved {len(batch)} logs via gRPC.")
        except Exception as e:
            for data in batch:
                data['id'] = None
                data['_db_failed'] = True
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - gRPC ERROR - {str(e)}")
