# -*- coding: utf-8 -*-
"""软删除硬清理基类 - 共享技术基础设施

提供通用的定时清理守护线程、Redis 分布式锁、批量删除/收集工具。
各微服务继承本类，实现 ``hard_delete_expired()`` 只清理本服务 owned 表。

DDD 分层定位：本模块是 shared/utils 下的技术基础设施（线程管理、Redis 锁、
SQL 工具），不含任何业务规则。各服务的业务规则在自己的
infrastructure/persistence/soft_delete_cleaner.py 中实现。

使用方式（各微服务）::

    from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

    class TaskServiceCleaner(SoftDeleteCleanerBase):
        def hard_delete_expired(self, session, threshold_dt):
            # 只删本服务 owned 表
            ...

    cleaner = TaskServiceCleaner(service_name='task_service')
    cleaner.start()  # 在 lifespan / gRPC server 启动时调用
    cleaner.stop()   # 在 lifespan 关闭时调用
"""
import logging
import threading
from datetime import timedelta

from sqlalchemy import text, bindparam

from shared.models.database import init_db, get_db_session, remove_db_session
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

# 软删除后多少天执行硬删除
RETENTION_DAYS = 60
# 扫描间隔（秒），默认 24 小时
SCAN_INTERVAL_SECONDS = 24 * 60 * 60


class SoftDeleteCleanerBase:
    """软删除硬清理守护基类。

    子类需实现 ``hard_delete_expired(session, threshold_dt)``，
    只清理本服务 owned 的表，遵循子→父删除顺序。

    Args:
        service_name: 服务名，用于 Redis 锁 key 隔离和日志标识
        retention_days: 软删除保留天数，默认 60
        scan_interval: 扫描间隔秒数，默认 24 小时
    """

    def __init__(self, service_name: str, retention_days: int = RETENTION_DAYS,
                 scan_interval: int = SCAN_INTERVAL_SECONDS):
        self.service_name = service_name
        self.retention_days = retention_days
        self.scan_interval = scan_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 子类实现
    # ------------------------------------------------------------------
    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除本服务 owned 的过期记录。

        子类必须实现。删除顺序遵循子→父依赖关系。
        返回 {表名: 删除条数} 字典。
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # SQL 工具（子类可直接调用）
    # ------------------------------------------------------------------
    @staticmethod
    def collect_expired_ids(session, table_name: str, threshold_dt) -> list:
        """收集指定表中 deleted_at 已过期的记录 id。

        Args:
            session: 数据库会话
            table_name: 表名，必须在白名单中
            threshold_dt: 过期阈值时间
        Returns:
            过期记录的 id 列表
        """
        if table_name not in _ALLOWED_TABLES:
            raise ValueError(f"非法表名: {table_name}，不在白名单中")
        rows = session.execute(text(
            f"SELECT id FROM {table_name} "
            "WHERE deleted = TRUE AND deleted_at IS NOT NULL AND deleted_at < :thr"
        ), {"thr": threshold_dt}).all()
        return [r[0] for r in rows]

    @staticmethod
    def batch_delete(session, sql_template: str, ids: list) -> None:
        """批量删除，ids 为空时跳过。

        Args:
            session: 数据库会话
            sql_template: 带 :ids 占位符的 DELETE/SELECT 语句
            ids: 待删除/查询的 id 列表
        """
        if not ids:
            return
        session.execute(text(sql_template).bindparams(
            bindparam('ids', expanding=True)), {"ids": ids})

    @staticmethod
    def filter_referenced_ids(session, table_name: str, column_name: str,
                              ids: list, exclude_deleted: bool = True) -> list:
        """过滤出仍被活跃记录引用的 id，供子类跳过硬删除。

        检查指定表的指定列中是否仍存在待删 id 的引用行。
        默认只检查未删除（deleted=FALSE 或无 deleted 列）的活跃行，
        如果发现引用则返回这些 id，子类应跳过这些 id 的硬删除。

        Args:
            session: 数据库会话
            table_name: 引用方表名，必须在白名单中
            column_name: 引用方表中指向被引用表的列名
            ids: 被引用方待删 id 列表
            exclude_deleted: 是否排除已软删除的引用行，默认 True
        Returns:
            仍被引用的 id 子集；ids 为空时返回空列表
        """
        if not ids:
            return []
        if table_name not in _ALLOWED_TABLES:
            raise ValueError(f"非法表名: {table_name}，不在白名单中")
        where_deleted = " AND deleted = FALSE" if exclude_deleted else ""
        rows = session.execute(text(
            f"SELECT DISTINCT {column_name} FROM {table_name} "
            f"WHERE {column_name} IN :ids{where_deleted}"
        ).bindparams(bindparam('ids', expanding=True)), {"ids": ids}).all()
        return {r[0] for r in rows}

    @staticmethod
    def refresh_deleted_at(session, table_name: str, ids: list) -> None:
        """刷新待删记录的 deleted_at 为当前时间，重置 60 天保留期。

        供子类在跳过硬删除时调用：被引用记录的 deleted_at 重置为 now，
        下次扫描时不再满足过期条件，避免反复无用的 JOIN 查询和跳过日志。
        给引用方 60 天窗口自然清理，解除引用后下次扫描即可硬删除。

        Args:
            session: 数据库会话
            table_name: 被引用方表名，必须在白名单中
            ids: 需刷新的记录 id 列表
        """
        if not ids:
            return
        if table_name not in _ALLOWED_TABLES:
            raise ValueError(f"非法表名: {table_name}，不在白名单中")
        session.execute(text(
            f"UPDATE {table_name} SET deleted_at = :now "
            f"WHERE id IN :ids"
        ).bindparams(bindparam('ids', expanding=True)), {"ids": ids, "now": now_cst()})

    # ------------------------------------------------------------------
    # 单次清理执行（带 Redis 分布式锁）
    # ------------------------------------------------------------------
    def run_once(self) -> dict:
        """执行一次清理。供定时线程或手动调用。

        使用 Redis 分布式锁，确保多实例部署时只有一个实例执行清理。
        Returns:
            counts: dict，key 为表名，value 为删除条数。失败时返回空 dict。
        """
        lock_key = f'soft_delete_cleaner:{self.service_name}:lock'
        lock_ttl = self.scan_interval
        store = None
        session = None
        try:
            from shared.utils.redis_pubsub import RedisStore
            store = RedisStore()
            acquired = store.redis_client.set(lock_key, '1', nx=True, ex=lock_ttl)
            if not acquired:
                logger.debug(f"[软删除清理:{self.service_name}] 其他实例正在执行，跳过")
                return {}
            init_db()
            session = get_db_session()
            threshold_dt = now_cst() - timedelta(days=self.retention_days)
            counts = self.hard_delete_expired(session, threshold_dt)
            session.commit()
            if counts:
                summary = ", ".join(f"{k}={v}" for k, v in counts.items())
                logger.info(f"[软删除清理:{self.service_name}] 完成：{summary}")
            return counts
        except Exception as e:
            logger.error(f"[软删除清理:{self.service_name}] 失败: {e}", exc_info=True)
            try:
                if session is not None:
                    session.rollback()
            except Exception:
                logger.debug("软删除清理 rollback 失败", exc_info=True)
            return {}
        finally:
            try:
                remove_db_session()
            except Exception:
                logger.debug("软删除清理 remove_db_session 失败", exc_info=True)
            try:
                if store is not None:
                    store.redis_client.delete(lock_key)
            except Exception:
                logger.debug("软删除清理 释放 Redis 锁失败 key=%s", lock_key, exc_info=True)

    # ------------------------------------------------------------------
    # 守护线程
    # ------------------------------------------------------------------
    def _loop(self):
        """定时清理循环，间隔由 scan_interval 控制。"""
        logger.info(
            f"[软删除清理:{self.service_name}] 后台任务启动，"
            f"每 {self.scan_interval}s 扫描一次，保留期 {self.retention_days} 天"
        )
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"[软删除清理:{self.service_name}] 循环异常: {e}", exc_info=True)
            self._stop_event.wait(timeout=self.scan_interval)

    def start(self):
        """启动守护线程（幂等，重复调用不会创建多个线程）。"""
        if self._thread is not None and self._thread.is_alive():
            logger.info(f"[软删除清理:{self.service_name}] 线程已在运行，跳过")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"soft-delete-cleaner-{self.service_name}", daemon=True)
        self._thread.start()
        logger.info(f"[软删除清理:{self.service_name}] 守护线程已启动")

    def stop(self):
        """停止守护线程。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info(f"[软删除清理:{self.service_name}] 守护线程已停止")


# 允许操作的表名白名单（防止 SQL 注入）
# 包含主表（硬删除目标）和关联表（引用检查目标）
_ALLOWED_TABLES = frozenset({
    # 主表（硬删除目标）
    'test_cases', 'test_case_groups', 'audios', 'devices', 'apis',
    'test_tasks', 'test_reports', 'spl_mappings', 'dimensions',
    'categories', 'tags', 'tag_categories',
    # 关联表（用于引用检查；无 deleted 列，直接物理删除）
    'test_case_tags', 'task_tags', 'task_case_relations',
    'task_device_relations', 'task_api_relations',
    'audio_tags', 'device_tags', 'audio_algorithm_relations',
    'audio_annotations',
    # 子表（硬删除目标或引用检查）
    'test_results', 'logs',
    'report_summaries', 'report_summary_meta', 'report_raw_data',
    'report_cases', 'report_metric_stats', 'report_comparison_matrix',
    'test_result_dimensions',
})
