# -*- coding: utf-8 -*-
"""服务运行日志文件处理器（INT-81）。

各微服务运行日志统一落 logs/{service_name}/，按天 + 按大小双条件轮转：
- 每天午夜轮转一次
- 单文件超过 max_bytes 即刻轮转
- 轮转文件命名 {base_name}-{YYYYMMDD}-{NNN}.log（同日多次超限切分序号递增，
  不再复用 TimedRotatingFileHandler 默认的纯日期后缀，避免同日覆盖）
- 保留 N 天由 retention 清扫器按 mtime 清理（backupCount 仅作兜底）

多进程/多副本安全（审计问题 1 修复）：活跃文件名含进程 PID
（app-{pid}.log）——compose 共享日志卷 + deploy.replicas 场景下同一服务的
多个副本进程各有独立活跃文件，轮转 os.replace 只触碰本进程文件：跨天/
超限同时轮转也不会 rename 他副本正写入的文件、不会以同序号互相覆盖。
PID 复用（容器重启）时同名活跃文件追加续写，切分序号扫描接续不丢行。
"""
import logging
import os
import time
from datetime import datetime

from shared.logging.config import LogSettings, get_log_settings, resolve_service_name

_DAY_FORMAT = '%Y%m%d'
_DATE_SUFFIX_LEN = len('YYYYMMDD') + len('-')
_SEQ_SUFFIX_LEN = len('-001')


def default_service_base_name() -> str:
    """默认活跃文件名：app-{pid}.log（进程独立，多副本共享卷互不冲突）。"""
    return f'app-{os.getpid()}.log'


class ServiceRotatingFileHandler(logging.Handler):
    """按天 + 按大小双条件轮转的服务日志处理器。

    相比 logging.handlers.TimedRotatingFileHandler 的组合改造点：
    - 轮转目标名带同日序号（app-20261010-001.log），同日多次超限不互相覆盖
    - Windows 下目标文件被占用时重试后放弃本条轮转（不中断日志写入）
    """

    def __init__(self, dir_path: str, base_name: str = None,
                 max_bytes: int = 50 * 1024 * 1024,
                 settings: LogSettings = None):
        super().__init__()
        self._dir_path = dir_path
        self._base_name = base_name or default_service_base_name()
        self._max_bytes = max_bytes
        self._settings = settings or get_log_settings()
        self._stream = None
        self._current_path = None
        self._current_day = self._today()
        os.makedirs(dir_path, exist_ok=True)
        self._open_stream()

    # ---- 流管理 ----

    def _stream_path(self) -> str:
        return os.path.join(self._dir_path, self._base_name)

    def _open_stream(self):
        self._current_path = self._stream_path()
        self._stream = open(self._current_path, 'a', encoding='utf-8')

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime(_DAY_FORMAT)

    # ---- 轮转判定与执行 ----

    def _needs_rollover(self) -> bool:
        if self._today() != self._current_day:
            return True
        if self._max_bytes > 0 and self._stream is not None:
            try:
                if self._stream.tell() >= self._max_bytes:
                    return True
            except (OSError, ValueError):
                return False
        return False

    def _next_rollover_target(self) -> str:
        stem = self._base_name[:-len('.log')]
        day = self._current_day
        max_seq = 0
        prefix = f'{stem}-{day}-'
        try:
            names = os.listdir(self._dir_path)
        except OSError:
            names = []
        for name in names:
            if name.startswith(prefix) and name.endswith('.log'):
                seq_part = name[len(prefix):-len('.log')]
                if seq_part.isdigit():
                    max_seq = max(max_seq, int(seq_part))
        return os.path.join(self._dir_path, f'{stem}-{day}-{max_seq + 1:03d}.log')

    def _rollover(self):
        self._close_stream()
        target = self._next_rollover_target()
        current = self._stream_path()
        try:
            if os.path.exists(current):
                os.replace(current, target)
        except OSError:
            # Windows 文件被占用：短暂等待重试一次，仍失败则放弃该轮转文件
            time.sleep(0.1)
            try:
                if os.path.exists(current):
                    os.replace(current, target)
            except OSError:
                pass
        self._current_day = self._today()
        self._open_stream()

    # ---- logging.Handler 接口 ----

    def emit(self, record):
        try:
            if self._stream is None:
                self._open_stream()
            if self._needs_rollover():
                self._rollover()
            msg = self.format(record) + '\n'
            self._stream.write(msg)
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        self._close_stream()
        super().close()


def setup_service_file_logging(settings: LogSettings = None,
                               service_name: str = None,
                               base_name: str = None) -> logging.Handler:
    """构建当前服务的运行日志文件处理器（logs/{service_name}/app-{pid}.log）。

    活跃文件名默认含进程 PID（多副本共享日志卷互不冲突）；base_name 显式
    传入时按传入名轮转（仅测试/单进程场景使用）。由 shared.utils.log_handler
    统一调用，各服务禁止自造文件 handler。
    """
    resolved_settings = settings or get_log_settings()
    name = service_name or resolve_service_name()
    dir_path = os.path.join(resolved_settings.root_dir, name)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(module)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    handler = ServiceRotatingFileHandler(
        dir_path, base_name=base_name or default_service_base_name(),
        max_bytes=resolved_settings.service_max_bytes,
        settings=resolved_settings,
    )
    handler.setFormatter(formatter)
    return handler
