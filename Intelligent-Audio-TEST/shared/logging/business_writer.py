# -*- coding: utf-8 -*-
"""业务日志文件写入器（INT-81）。

业务日志（执行/评估/设备）停止写 logs 表，按路径模板落文件：
    business/{task_id}/{device_id|api_id|common}/{evaluation_id|round|shared}/{log_type}.{service_name}.{hostname}-{pid}.log

- JSON Lines 格式（每行一个 JSON 对象），读取侧按行解析可精确过滤
- 单文件超过 business_max_bytes 切分：活跃文件改名 {base}-NNN.log 后重建
- 文件名含 service_name + hostname+pid 进程标识（shared.logging.identity）：
  同宿主多进程靠 PID 区分；容器多副本（compose deploy.replicas 共享日志
  卷）各副本 PID namespace 独立、入口进程 PID 恒为 1，靠 Docker 注入的
  短容器 ID（主机名）区分——两者合取后各写入方持有独立活跃文件，轮转
  改名只触碰本进程文件，互不冲突；进程标识复用（容器重启）时同名活跃
  文件追加续写，切分序号扫描接续，不丢不覆盖
- 时间字段统一 LOG_TIME_FORMAT 固定 strftime（拒绝 str(datetime) 的
  微秒+时区后缀，保证与 DB/WS 侧时间格式一致可排序）
- 打开句柄按目录缓存 + LRU 上限，防止长任务刷爆句柄数
"""
import json
import os
import threading
from typing import Dict, Optional, Tuple

from shared.logging.config import LogSettings, get_log_settings, resolve_service_name
from shared.logging.enums import BusinessLogType, LOG_TIME_FORMAT, log_type_for_category
from shared.logging.identity import process_identity
from shared.logging.path_builder import BusinessLogPathBuilder

# 打开句柄缓存上限（超出后关闭最久未写的文件句柄）
_MAX_OPEN_HANDLES = 64

# JSON Lines 条目字段（显式白名单，拒绝任意 kwargs 落盘）
_ENTRY_FIELDS = (
    'time', 'level', 'category', 'module', 'source', 'content',
    'task_id', 'device_id', 'api_id', 'test_case_id', 'thread_id',
    'algorithm_type', 'round', 'evaluation_id', 'service', 'log_type',
)


class BusinessLogFileWriter:
    """业务日志落盘写入器（进程内单实例，由 log worker 线程串行调用）。"""

    def __init__(self, settings: LogSettings = None, service_name: str = None,
                 path_builder: BusinessLogPathBuilder = None,
                 process_id=None):
        self._settings = settings or get_log_settings()
        self._service_name = service_name or resolve_service_name()
        # 进程标识（{hostname}-{pid}）进文件名：同宿主多进程靠 PID 区分，
        # 容器多副本（副本内 PID 恒为 1）靠 Docker 注入的短容器 ID 区分
        # （审计问题 1 二次修复）；测试可注入固定 process_id 换取确定性
        # 路径断言
        self._process_id = process_identity() if process_id is None else process_id
        self._path_builder = path_builder or BusinessLogPathBuilder()
        self._lock = threading.Lock()
        # cache key (dir, base_name) -> (file_handle, current_size)
        self._handles: Dict[Tuple[str, str], Tuple] = []
        self._handle_keys = []

    # ---- 路径解析 ----

    def resolve_rel_path(self, entry: dict) -> Tuple[str, BusinessLogType]:
        """按条目上下文解析相对路径与日志类型。"""
        log_type = log_type_for_category(entry.get('category'))
        rel_path = self._path_builder.build_rel_path(
            task_id=entry.get('task_id'),
            log_type=log_type,
            service_name=self._service_name,
            device_id=entry.get('device_id'),
            api_id=entry.get('api_id'),
            evaluation_id=entry.get('evaluation_id'),
            round_value=entry.get('round'),
            process_id=self._process_id,
        )
        return rel_path, log_type

    # ---- 写入 ----

    def write(self, entry: dict) -> Optional[str]:
        """写入一条业务日志，返回写入的相对路径；task_id 缺失或禁用时返回 None。"""
        if not self._settings.business_enabled:
            return None
        if entry.get('task_id') in (None, ''):
            return None

        rel_path, log_type = self.resolve_rel_path(entry)
        record = {key: entry.get(key) for key in _ENTRY_FIELDS}
        record['service'] = self._service_name
        record['log_type'] = log_type.value
        if hasattr(record.get('time'), 'strftime'):
            # 统一固定 strftime 格式（含微秒，固定宽度可字符串排序），
            # 与 DB/WS 时间格式对齐；字符串时间（测试/回放）原样保留
            record['time'] = record['time'].strftime(LOG_TIME_FORMAT)
        if record.get('round') in (None, ''):
            record['round'] = None
        line = json.dumps(record, ensure_ascii=False, default=str)

        abs_path = os.path.join(self._settings.root_dir, rel_path)
        dir_path = os.path.dirname(abs_path)
        base_name = os.path.basename(abs_path)

        with self._lock:
            handle, size = self._get_handle(dir_path, base_name)
            payload = (line + '\n').encode('utf-8')
            handle.write(payload)
            size += len(payload)
            # 立即刷盘：读取侧与进程异常退出时不能丢已确认写入的行
            handle.flush()
            self._update_handle_size(size)
            if self._settings.business_max_bytes > 0 and size >= self._settings.business_max_bytes:
                self._rotate(dir_path, base_name)
        return rel_path

    # ---- 句柄管理 ----

    def _get_handle(self, dir_path: str, base_name: str) -> Tuple:
        key = (dir_path, base_name)
        for idx, cached_key in enumerate(self._handle_keys):
            if cached_key == key:
                handle_entry = self._handles[idx]
                self._handles.pop(idx)
                self._handle_keys.pop(idx)
                self._handles.append(handle_entry)
                self._handle_keys.append(key)
                return handle_entry
        os.makedirs(dir_path, exist_ok=True)
        handle = open(os.path.join(dir_path, base_name), 'ab')
        try:
            size = handle.tell()
        except OSError:
            size = 0
        self._evict_if_needed()
        self._handles.append((handle, size))
        self._handle_keys.append(key)
        return handle, size

    def _update_handle_size(self, size: int):
        if self._handles:
            handle, _ = self._handles[-1]
            self._handles[-1] = (handle, size)

    def _evict_if_needed(self):
        while len(self._handles) >= _MAX_OPEN_HANDLES:
            handle, _ = self._handles.pop(0)
            self._handle_keys.pop(0)
            self._close_quietly(handle)

    @staticmethod
    def _close_quietly(handle):
        try:
            handle.close()
        except Exception:
            pass

    def _rotate(self, dir_path: str, base_name: str):
        """超限切分：关闭活跃文件，改名 -NNN 序号文件，下次写入重建。"""
        key = (dir_path, base_name)
        if key not in self._handle_keys:
            return
        idx = self._handle_keys.index(key)
        handle, _ = self._handles.pop(idx)
        self._handle_keys.pop(idx)
        self._close_quietly(handle)
        active_path = os.path.join(dir_path, base_name)
        target = self._path_builder.next_split_path(dir_path, base_name)
        try:
            if os.path.exists(active_path):
                os.replace(active_path, target)
        except OSError:
            # 改名失败（占用等）：保留活跃文件继续写，不中断日志
            pass

    def close_all(self):
        """关闭全部句柄（测试与进程退出用）。"""
        with self._lock:
            for handle, _ in self._handles:
                self._close_quietly(handle)
            self._handles.clear()
            self._handle_keys.clear()
