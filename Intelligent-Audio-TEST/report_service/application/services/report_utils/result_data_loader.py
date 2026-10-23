# -*- coding: utf-8 -*-
"""结果文件读取（带「对象缺失」负缓存，INT-1572 返工二轮）。

报告聚合按每条测试结果去 OSS 读 result_data 结果文件（`case_result/{task}/{tc}/…`
/result_data.json`）。历史数据里这些对象大量不存在（结果文件缺失，DB 只留轻量
载荷），每次读都是一次 HEAD + 一次必失败的 GET 重试；138 条用例的一轮统计会把
同一批缺失对象反复读多轮（资源 key / 资源表头 / result_type 派生各读一次），
复测日志 15 分钟内 642 条 `result_data_store: object not found`。

这里把「这个对象不存在」的判定按路径缓存一小段时间：同一报告请求（以及短时间
内的相邻请求）只付一次探测代价，读取失败时直接回落 DB 轻量载荷。Z 只缓存失败，
成功结果不进缓存（读成功已经返回文件内容，不需要再缓存一次）。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

from report_service.config.config import Config
from shared.utils.result_data_store import read_result_data_file

logger = logging.getLogger(__name__)

# {path: 过期时刻 monotonic}
_missing_paths: "OrderedDict[str, float]" = OrderedDict()
_missing_lock = threading.Lock()


def _is_known_missing(path: str) -> bool:
    ttl = Config.REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS
    if ttl <= 0:
        return False
    now = time.monotonic()
    with _missing_lock:
        expiry = _missing_paths.get(path)
        if expiry is None:
            return False
        if now >= expiry:
            _missing_paths.pop(path, None)
            return False
        _missing_paths.move_to_end(path)
        return True


def _mark_missing(path: str) -> None:
    ttl = Config.REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS
    if ttl <= 0:
        return
    max_entries = max(int(Config.REPORT_RESULT_FILE_NEGATIVE_CACHE_MAX_ENTRIES), 1)
    with _missing_lock:
        _missing_paths[path] = time.monotonic() + ttl
        _missing_paths.move_to_end(path)
        while len(_missing_paths) > max_entries:
            _missing_paths.popitem(last=False)


def clear_missing_cache() -> None:
    """清空缺失负缓存（单测使用）。"""
    with _missing_lock:
        _missing_paths.clear()


def load_full_result_data_cached(result_data_from_db, result_data_path) -> dict:
    """等价于 result_data_store.load_full_result_data，但缓存「对象不存在」判定。

    Args:
        result_data_from_db: DB 中的轻量结果载荷（dict 或 None）
        result_data_path: 结果文件路径（可为空）

    Returns:
        完整结果数据；结果文件缺失时回落 DB 载荷。
    """
    try:
        if result_data_path and not _is_known_missing(result_data_path):
            file_data = read_result_data_file(result_data_path)
            if file_data:
                return file_data
            _mark_missing(result_data_path)
    except Exception:  # pragma: no cover - 读取工具自身已兜底，这里只防意外
        logger.debug("读取结果文件失败 path=%s", result_data_path, exc_info=True)
    if isinstance(result_data_from_db, dict) and result_data_from_db:
        return result_data_from_db
    return {}
