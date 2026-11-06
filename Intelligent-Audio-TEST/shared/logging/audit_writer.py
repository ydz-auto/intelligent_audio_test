# -*- coding: utf-8 -*-
"""审计日志文件写入器（INT-1793 契约 §3.1/§3.2，卡片 1 写入侧）。

审计事件从「服务文件 + logs 表」改为「审计 JSONL，一条事件恰好一行」：
    audit/{YYYY-MM-DD}/{category}.{service}.{hostname}-{pid}.jsonl

契约要点（本文件负责写侧全部）：
- **单写者（H4）**：审计文件只由 task_service 落盘——跨进程审计事件经既有
  `BatchCreateLogs` gRPC 通道送来（worker 侧带 `sink='audit_file'`），
  task_service 内的直写仓储（S4）直接调用本写入器（同进程同一日志根）。
- **显式标记（H1）**：条目必须带 `event`（AuditEvent 枚举值），缺省不算审计，
  写入器直接丢弃，绝不把同 category 的运维日志灌进审计语料。
- **操作人写侧提取（H2）**：从 `content` JSON 提取 operator_id / operator /
  target_type / target_id / action / result 落到 JSONL 顶层，`user_id` = operator_id
  （不依赖 contextvar：worker 线程不继承请求上下文）。
- **游标（H3）**：`cursor` = 事件时间 epoch 微秒，进程内严格递增（同微秒 +1，
  并与上次写盘游标取 max），不用内容哈希；< 2^53 前端无损。
- 按天（日期目录）+ 按大小（`audit_max_bytes` 切分 `-NNN`）双条件轮转；
  句柄按 (目录, 文件名) 缓存并 LRU 上限，防止刷爆句柄数。
"""
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from shared.logging.config import LogSettings, get_log_settings, resolve_service_name
from shared.logging.enums import AUDIT_FILE_SUFFIX, AuditLogCategory
from shared.logging.identity import process_identity
from shared.logging.path_builder import AuditLogPathBuilder

# 打开句柄缓存上限（超出后关闭最久未写的文件句柄）
_MAX_OPEN_HANDLES = 64

_CST = timezone(timedelta(hours=8))
_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)

# JSONL 条目字段白名单（显式白名单，拒绝任意 kwargs 落盘）：
# 不落 mark（文件日志不可标记）、不落 id（读侧 id = cursor）
_AUDIT_ENTRY_FIELDS = (
    'cursor', 'time', 'level', 'category', 'module', 'source', 'service',
    'event', 'operator_id', 'operator', 'target_type', 'target_id', 'action',
    'result', 'user_id', 'detail', 'content',
    'task_id', 'device_id', 'api_id', 'test_case_id', 'thread_id', 'algorithm_type',
)

# content JSON 里操作人字段的取值顺序（H2：写侧提取，不依赖 contextvar）
_OPERATOR_ID_KEYS = ('operator_id', 'operator_user_id', 'published_by', 'user_id')
_TARGET_ID_KEYS = ('target_id', 'published_task_id', 'alarm_id', 'resource_id',
                   'review_id', 'result_id')
_TARGET_TYPE_KEYS = ('target_type', 'resource_type')

_AUDIT_CATEGORY_VALUES = frozenset(item.value for item in AuditLogCategory)


def _as_int(value) -> Optional[int]:
    """操作人/目标 ID 归一为 int（bool、空串、非数字一律 None）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    try:
        text = str(value).strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _as_text(value) -> Optional[str]:
    """文本字段归一：空值/纯空白返回 None。"""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _coerce_datetime(value) -> Optional[datetime]:
    """事件时间归一：datetime 原样、字符串按 ISO 解析（含空格/带时区），失败 None。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def epoch_micros(moment: datetime) -> int:
    """事件时间 → epoch 微秒（纯整数运算，避免 float 精度损失）。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_CST)
    delta = moment.astimezone(timezone.utc) - _EPOCH_UTC
    return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


def _parse_detail(content: str) -> dict:
    """content 字符串解析为 detail dict；非 JSON 对象时返回空 dict（content 原样保留）。"""
    if not content or not content.strip():
        return {}
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class AuditLogFileWriter:
    """审计 JSONL 落盘写入器（task_service 进程内单实例，单写者 H4）。"""

    def __init__(self, settings: LogSettings = None, service_name: str = None,
                 path_builder: AuditLogPathBuilder = None, process_id=None):
        self._settings = settings or get_log_settings()
        # 写盘进程（task_service）名称与进程标识：service 段取条目透传的
        # 产生进程，进程标识段固定为本写盘进程，两者不同语义（契约 §3.1）
        self._service_name = service_name or resolve_service_name()
        self._process_id = process_identity() if process_id is None else process_id
        self._path_builder = path_builder or AuditLogPathBuilder()
        self._lock = threading.Lock()
        self._handles: Dict[Tuple[str, str], Tuple] = {}
        self._handle_order = []
        self._last_cursor = 0

    # ---- 条目归一（白名单 + H2 提取 + H3 游标）----

    def build_record(self, entry: dict) -> Optional[dict]:
        """把原始条目归一为审计 JSONL 行；缺 event 或开关关闭返回 None。"""
        if not self._settings.audit_enabled:
            return None
        content = entry.get('content')
        content = '' if content is None else str(content)
        detail = entry.get('detail')
        if not isinstance(detail, dict):
            detail = _parse_detail(content)

        event = _as_text(entry.get('event')) or _as_text(detail.get('event'))
        if not event:
            # H1：没有显式 event 的条目不是审计事件，直接丢弃
            return None

        category = _as_text(entry.get('category')) or ''
        category = category.lower()
        if category not in _AUDIT_CATEGORY_VALUES:
            category = AuditLogCategory.SYSTEM.value

        moment = _coerce_datetime(entry.get('time')) or datetime.now(_CST)

        operator_id = None
        for key in _OPERATOR_ID_KEYS:
            operator_id = _as_int(detail.get(key))
            if operator_id is not None:
                break
        operator = _as_text(detail.get('operator')) or _as_text(detail.get('operator_name'))

        target_id = None
        for key in _TARGET_ID_KEYS:
            if detail.get(key) not in (None, ''):
                target_id = detail.get(key)
                if not isinstance(target_id, (int, str)):
                    target_id = _as_text(target_id)
                break
        target_type = None
        for key in _TARGET_TYPE_KEYS:
            target_type = _as_text(detail.get(key))
            if target_type:
                break

        if detail.get('result') not in (None, ''):
            result = _as_text(detail.get('result')) or 'success'
        elif detail.get('success') is False:
            result = 'failure'
        else:
            result = 'success'

        time_text = moment.strftime('%Y-%m-%d %H:%M:%S.%f')
        record = {key: entry.get(key) for key in _AUDIT_ENTRY_FIELDS}
        record.update({
            'time': time_text,
            'level': str(entry.get('level') or 'INFO').upper(),
            'category': category,
            'module': _as_text(entry.get('module')) or 'unknown',
            'source': _as_text(entry.get('source')) or 'backend',
            'service': entry.get('service') or self._service_name,
            'event': event,
            'operator_id': operator_id,
            'operator': operator,
            'target_type': target_type,
            'target_id': target_id,
            'action': _as_text(detail.get('action')),
            'result': result,
            'user_id': operator_id,
            'detail': detail,
            'content': content,
        })
        return record

    def _allocate_cursor(self, record: dict) -> int:
        """游标分配：事件时间微秒，进程内严格递增（需在锁内调用）。"""
        moment = datetime.strptime(record['time'], '%Y-%m-%d %H:%M:%S.%f')
        candidate = epoch_micros(moment)
        cursor = max(candidate, self._last_cursor + 1)
        self._last_cursor = cursor
        return cursor

    # ---- 写入 ----

    def write(self, entry: dict) -> Optional[int]:
        """写入一条审计事件，返回 cursor；非审计/开关关闭返回 None。"""
        record = self.build_record(entry)
        if record is None:
            return None
        with self._lock:
            cursor = self._allocate_cursor(record)
            record['cursor'] = cursor
            self._append(record)
        return cursor

    def _append(self, record: dict) -> None:
        """按事件日期目录追加一行（句柄缓存 + 超限切分，需在锁内调用）。"""
        date_seg = record['time'][:10]
        rel_path = self._path_builder.build_rel_path(
            category=record['category'],
            service_name=record['service'],
            date_seg=date_seg,
            process_id=self._process_id,
        )
        abs_path = os.path.join(self._settings.root_dir, rel_path)
        dir_path = os.path.dirname(abs_path)
        base_name = os.path.basename(abs_path)
        line = json.dumps(record, ensure_ascii=False, default=str)

        handle, size = self._get_handle(dir_path, base_name)
        payload = (line + '\n').encode('utf-8')
        handle.write(payload)
        size += len(payload)
        # 立即刷盘：读取侧与进程异常退出时不能丢已确认写入的行
        handle.flush()
        self._update_handle_size(dir_path, base_name, size)
        if self._settings.audit_max_bytes > 0 and size >= self._settings.audit_max_bytes:
            self._rotate(dir_path, base_name)

    # ---- 句柄管理 ----

    def _get_handle(self, dir_path: str, base_name: str) -> Tuple:
        key = (dir_path, base_name)
        if key in self._handles:
            self._handle_order.remove(key)
            self._handle_order.append(key)
            return self._handles[key]
        os.makedirs(dir_path, exist_ok=True)
        handle = open(os.path.join(dir_path, base_name), 'ab')
        try:
            size = handle.tell()
        except OSError:
            size = 0
        self._evict_if_needed()
        self._handles[key] = (handle, size)
        self._handle_order.append(key)
        return handle, size

    def _update_handle_size(self, dir_path: str, base_name: str, size: int) -> None:
        key = (dir_path, base_name)
        if key in self._handles:
            handle, _ = self._handles[key]
            self._handles[key] = (handle, size)

    def _evict_if_needed(self) -> None:
        while len(self._handles) >= _MAX_OPEN_HANDLES:
            key = self._handle_order.pop(0)
            handle, _ = self._handles.pop(key)
            self._close_quietly(handle)

    @staticmethod
    def _close_quietly(handle) -> None:
        try:
            handle.close()
        except Exception:
            pass

    def _rotate(self, dir_path: str, base_name: str) -> None:
        """超限切分：关闭活跃文件，改名 -NNN 序号文件，下次写入重建。"""
        key = (dir_path, base_name)
        if key not in self._handles:
            return
        handle, _ = self._handles.pop(key)
        self._handle_order.remove(key)
        self._close_quietly(handle)
        active_path = os.path.join(dir_path, base_name)
        target = self._path_builder.next_split_path(dir_path, base_name)
        try:
            if os.path.exists(active_path):
                os.replace(active_path, target)
        except OSError:
            # 改名失败（占用等）：保留活跃文件继续写，不中断审计
            pass

    def close_all(self) -> None:
        """关闭全部句柄（测试与进程退出用）。"""
        with self._lock:
            for handle, _ in self._handles.values():
                self._close_quietly(handle)
            self._handles.clear()
            self._handle_order.clear()


# ---- 进程级单例 + 便捷函数 ----

_WRITER: Optional[AuditLogFileWriter] = None
_WRITER_LOCK = threading.Lock()


def get_audit_writer() -> AuditLogFileWriter:
    """获取进程级审计写入器（首次调用时按配置快照创建）。"""
    global _WRITER
    if _WRITER is None:
        with _WRITER_LOCK:
            if _WRITER is None:
                _WRITER = AuditLogFileWriter()
    return _WRITER


def reset_audit_writer() -> None:
    """丢弃进程级写入器（测试注入临时配置后用）。"""
    global _WRITER
    with _WRITER_LOCK:
        if _WRITER is not None:
            _WRITER.close_all()
        _WRITER = None


def write_audit_event(*, event, category, module, source, content,
                      level: str = 'INFO', time=None, service: str = None,
                      **fields) -> Optional[int]:
    """写一条审计事件到审计文件，返回 cursor（task_service 内直写路径，S4）。

    Args:
        event: AuditEvent 枚举成员或事件名（必填，缺省不写）
        category: AuditLogCategory 枚举成员或五值之一
        module/source/content: 与 log_not_emit 同义（content 为原 JSON 字符串）
        service: 产生事件的进程名（默认本进程）
        fields: 额外上下文（device_id/api_id/task_id/... 白名单内字段）
    """
    writer = get_audit_writer()
    entry = {
        'event': getattr(event, 'value', event),
        'category': getattr(category, 'value', category),
        'module': module,
        'source': source,
        'content': content,
        'level': level,
        'time': time,
    }
    if service:
        entry['service'] = service
    for key in _AUDIT_ENTRY_FIELDS:
        if key in fields and key not in entry:
            entry[key] = fields[key]
    return writer.write(entry)


__all__ = [
    'AUDIT_FILE_SUFFIX',
    'AuditLogFileWriter',
    'epoch_micros',
    'get_audit_writer',
    'reset_audit_writer',
    'write_audit_event',
]
