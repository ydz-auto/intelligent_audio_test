# -*- coding: utf-8 -*-
"""播放历史回写重试队列（执行机 audio_agent 侧）。

拆分后播放历史只能由服务器数据面写库。agent 通过 RecordPlaybackHistory RPC 回写：

- 正常路径：同步发送，服务器成功即结束；
- 失败路径：记录带幂等键落盘到 JSONL 队列，后台线程按固定间隔重试；
  服务器按幂等键去重（Redis SET NX），重试不会产生重复历史。

队列目录：``PLAYBACK_HISTORY_QUEUE_DIR``，缺省 ``<cwd>/logs/playback_history_queue``。
"""
import json
import logging
import os
import threading
import time
import uuid

logger = logging.getLogger(__name__)

_FILE_NAME = 'pending.jsonl'
_RETRY_INTERVAL_SECONDS = float(os.environ.get('PLAYBACK_HISTORY_RETRY_INTERVAL', '30'))
_RPC_TIMEOUT_SECONDS = float(os.environ.get('PLAYBACK_HISTORY_RPC_TIMEOUT', '10'))

_lock = threading.Lock()
_worker = None


def _queue_dir() -> str:
    base = os.environ.get('PLAYBACK_HISTORY_QUEUE_DIR')
    if not base:
        base = os.path.join(os.getcwd(), 'logs', 'playback_history_queue')
    os.makedirs(base, exist_ok=True)
    return base


def _queue_path() -> str:
    return os.path.join(_queue_dir(), _FILE_NAME)


def _send(record: dict) -> bool:
    """发送一条记录；返回服务器是否成功受理（含幂等命中）。"""
    from shared.clients.grpc_clients import get_audio_config_service_stub
    from shared.proto import audio_service_pb2 as audio_pb
    from shared.utils.grpc_json import dumps

    stub = get_audio_config_service_stub()
    resp = stub.RecordPlaybackHistory(
        audio_pb.RecordPlaybackHistoryRequest(
            data=dumps(record.get('data') or {}),
            idempotency_key=record.get('idempotency_key') or '',
        ),
        timeout=_RPC_TIMEOUT_SECONDS,
    )
    return bool(resp.success)


def _append(record: dict) -> None:
    with _lock:
        with open(_queue_path(), 'a', encoding='utf-8') as fp:
            fp.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')


def _read_all() -> list:
    path = _queue_path()
    if not os.path.exists(path):
        return []
    records = []
    with open(path, 'r', encoding='utf-8') as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                logger.warning("丢弃损坏的播放历史队列记录: %s", line[:200])
    return records


def _rewrite(records: list) -> None:
    path = _queue_path()
    with _lock:
        if not records:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            return
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            for record in records:
                fp.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        os.replace(tmp, path)


def flush_pending() -> int:
    """尝试回放全部积压记录，返回仍未成功的条数。"""
    records = _read_all()
    if not records:
        return 0
    remaining = []
    for record in records:
        try:
            if _send(record):
                continue
        except Exception as exc:
            logger.debug("播放历史回放失败，保留待重试: %s", exc)
        remaining.append(record)
    if len(remaining) != len(records):
        _rewrite(remaining)
        logger.info("播放历史队列回放：成功 %d 条，剩余 %d 条",
                    len(records) - len(remaining), len(remaining))
    return len(remaining)


def _worker_loop() -> None:
    while True:
        time.sleep(_RETRY_INTERVAL_SECONDS)
        try:
            if flush_pending() == 0 and not _read_all():
                return
        except Exception:
            logger.warning("播放历史队列后台回放异常", exc_info=True)


def _ensure_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _worker = threading.Thread(target=_worker_loop, name='playback-history-retry', daemon=True)
    _worker.start()


def submit_playback_history(data: dict) -> bool:
    """回写一条播放历史；服务器不可达时落盘并交由后台线程重试。

    Returns:
        True 表示已同步写入服务器；False 表示已进入本地重试队列。
    """
    record = {
        'idempotency_key': uuid.uuid4().hex,
        'data': data or {},
        'created_at': time.time(),
    }
    try:
        if _send(record):
            _ensure_worker()
            return True
    except Exception as exc:
        logger.warning("播放历史回写失败，转入本地重试队列: %s", exc)
    try:
        _append(record)
    except Exception:
        logger.error("播放历史落盘失败，记录丢失", exc_info=True)
    _ensure_worker()
    return False
