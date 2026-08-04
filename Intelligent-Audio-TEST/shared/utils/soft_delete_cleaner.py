# -*- coding: utf-8 -*-
"""
软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除（硬删除）。
按依赖关系（子→父）覆盖所有带 deleted_at 的实体及其关联表，
不依赖数据库外键级联，由应用层显式清理关联数据。

覆盖的实体（删除顺序）：
  1. test_cases 及其子表（test_result_dimensions / test_results / task_case_relations / test_case_tags / logs）
  2. test_case_groups
  3. audios 及其子表（audio_annotations / audio_tags / audio_algorithm_relations）
  4. devices 及其子表（device_tags）
  5. apis
  6. test_tasks 及其关联表（task_tags / task_case_relations / task_device_relations / task_api_relations）
  7. test_reports 及其子表（report_summaries / report_summary_meta / report_raw_data / report_cases /
     report_metric_stats / report_comparison_matrix）
  8. spl_mappings
  9. dimensions（子维度先删）
  10. categories
  11. tags（关联表 test_case_tags / audio_tags / device_tags / task_tags 已随父记录清理）
  12. tag_categories

注：playback_devices 使用 is_deleted（无 deleted_at），其清理由 spl_mappings 联动处理，本任务跳过。

启动方式：在 API Gateway 的 lifespan 中调用 start_soft_delete_cleaner()。
默认每 24 小时执行一次扫描。
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

_cleaner_thread = None
_stop_event = threading.Event()


def _collect_expired_ids(session, table_name, threshold_dt):
    """收集指定表中 deleted_at 已过期的记录 id。

    Args:
        session: 数据库会话
        table_name: 表名（不含 schema）
        threshold_dt: 过期阈值时间

    Returns:
        过期记录的 id 列表
    """
    rows = session.execute(text(
        f"SELECT id FROM {table_name} "
        "WHERE deleted = TRUE AND deleted_at IS NOT NULL AND deleted_at < :thr"
    ), {"thr": threshold_dt}).all()
    return [r[0] for r in rows]


def _batch_delete(session, sql_template, ids):
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


def _hard_delete_expired(session, threshold_dt):
    """硬删除超过保留期的逻辑删除记录及其关联数据。

    删除顺序严格遵循依赖关系（子→父），避免违反引用完整性。
    返回各实体的删除计数字典，key 为表名，value 为删除条数。
    """
    counts = {}

    # ================================================================
    # 1. test_cases 及其关联子表
    # ================================================================
    case_ids = _collect_expired_ids(session, 'test_cases', threshold_dt)
    if case_ids:
        # 1.1 test_result_dimensions（依赖 test_results）
        tr_rows = session.execute(text(
            "SELECT id FROM test_results WHERE test_case_id IN :ids"
        ).bindparams(bindparam('ids', expanding=True)), {"ids": case_ids}).all()
        tr_id_list = [r[0] for r in tr_rows]
        if tr_id_list:
            _batch_delete(session,
                "DELETE FROM test_result_dimensions WHERE test_result_id IN :ids",
                tr_id_list)
            counts['test_result_dimensions'] = len(tr_id_list)
        # 1.2 test_results
        _batch_delete(session,
            "DELETE FROM test_results WHERE test_case_id IN :ids", case_ids)
        # 1.3 task_case_relations（关联表，无 deleted_at，随父删除）
        _batch_delete(session,
            "DELETE FROM task_case_relations WHERE test_case_id IN :ids", case_ids)
        # 1.4 test_case_tags
        _batch_delete(session,
            "DELETE FROM test_case_tags WHERE test_case_id IN :ids", case_ids)
        # 1.5 logs（注意：logs 有自己的 TTL 清理，这里只清理 deleted_at 过期关联）
        _batch_delete(session,
            "DELETE FROM logs WHERE test_case_id IN :ids", case_ids)
        # 1.6 test_cases
        _batch_delete(session,
            "DELETE FROM test_cases WHERE id IN :ids", case_ids)
        counts['test_cases'] = len(case_ids)
        logger.info(f"[软删除清理] 硬删除 test_cases: {len(case_ids)} 条")

    # ================================================================
    # 2. test_case_groups
    # ================================================================
    group_ids = _collect_expired_ids(session, 'test_case_groups', threshold_dt)
    if group_ids:
        _batch_delete(session,
            "DELETE FROM test_case_groups WHERE id IN :ids", group_ids)
        counts['test_case_groups'] = len(group_ids)
        logger.info(f"[软删除清理] 硬删除 test_case_groups: {len(group_ids)} 条")

    # ================================================================
    # 3. audios 及其子表（audio_annotations / audio_tags / audio_algorithm_relations）
    # ================================================================
    audio_ids = _collect_expired_ids(session, 'audios', threshold_dt)
    if audio_ids:
        # 3.1 audio_annotations（有自己的 deleted_at，但随父 audio 硬删除时一并清理）
        _batch_delete(session,
            "DELETE FROM audio_annotations WHERE audio_id IN :ids", audio_ids)
        # 3.2 audio_tags（关联表，无 deleted_at）
        _batch_delete(session,
            "DELETE FROM audio_tags WHERE audio_id IN :ids", audio_ids)
        # 3.3 audio_algorithm_relations（有自己的 deleted_at）
        _batch_delete(session,
            "DELETE FROM audio_algorithm_relations WHERE audio_id IN :ids", audio_ids)
        # 3.4 audios
        _batch_delete(session,
            "DELETE FROM audios WHERE id IN :ids", audio_ids)
        counts['audios'] = len(audio_ids)
        logger.info(f"[软删除清理] 硬删除 audios: {len(audio_ids)} 条")

    # ================================================================
    # 4. devices 及其子表（device_tags）
    # ================================================================
    device_ids = _collect_expired_ids(session, 'devices', threshold_dt)
    if device_ids:
        # 4.1 device_tags（关联表，无 deleted_at）
        _batch_delete(session,
            "DELETE FROM device_tags WHERE device_id IN :ids", device_ids)
        # 4.2 devices
        _batch_delete(session,
            "DELETE FROM devices WHERE id IN :ids", device_ids)
        counts['devices'] = len(device_ids)
        logger.info(f"[软删除清理] 硬删除 devices: {len(device_ids)} 条")

    # ================================================================
    # 5. apis
    # ================================================================
    api_ids = _collect_expired_ids(session, 'apis', threshold_dt)
    if api_ids:
        _batch_delete(session,
            "DELETE FROM apis WHERE id IN :ids", api_ids)
        counts['apis'] = len(api_ids)
        logger.info(f"[软删除清理] 硬删除 apis: {len(api_ids)} 条")

    # ================================================================
    # 6. test_tasks 及其关联表（task_tags / task_device_relations / task_api_relations）
    #    注：task_case_relations 已随 test_cases 清理，但任务硬删除时仍需清理残留关联
    # ================================================================
    task_ids = _collect_expired_ids(session, 'test_tasks', threshold_dt)
    if task_ids:
        # 6.1 task_tags
        _batch_delete(session,
            "DELETE FROM task_tags WHERE task_id IN :ids", task_ids)
        # 6.2 task_case_relations
        _batch_delete(session,
            "DELETE FROM task_case_relations WHERE task_id IN :ids", task_ids)
        # 6.3 task_device_relations
        _batch_delete(session,
            "DELETE FROM task_device_relations WHERE task_id IN :ids", task_ids)
        # 6.4 task_api_relations
        _batch_delete(session,
            "DELETE FROM task_api_relations WHERE task_id IN :ids", task_ids)
        # 6.5 test_tasks
        _batch_delete(session,
            "DELETE FROM test_tasks WHERE id IN :ids", task_ids)
        counts['test_tasks'] = len(task_ids)
        logger.info(f"[软删除清理] 硬删除 test_tasks: {len(task_ids)} 条")

    # ================================================================
    # 7. test_reports 及其子表
    # ================================================================
    report_ids = _collect_expired_ids(session, 'test_reports', threshold_dt)
    if report_ids:
        # 7.1 report_summaries
        _batch_delete(session,
            "DELETE FROM report_summaries WHERE report_id IN :ids", report_ids)
        # 7.2 report_summary_meta
        _batch_delete(session,
            "DELETE FROM report_summary_meta WHERE report_id IN :ids", report_ids)
        # 7.3 report_raw_data
        _batch_delete(session,
            "DELETE FROM report_raw_data WHERE report_id IN :ids", report_ids)
        # 7.4 report_cases
        _batch_delete(session,
            "DELETE FROM report_cases WHERE report_id IN :ids", report_ids)
        # 7.5 report_metric_stats
        _batch_delete(session,
            "DELETE FROM report_metric_stats WHERE report_id IN :ids", report_ids)
        # 7.6 report_comparison_matrix
        _batch_delete(session,
            "DELETE FROM report_comparison_matrix WHERE report_id IN :ids", report_ids)
        # 7.7 test_reports
        _batch_delete(session,
            "DELETE FROM test_reports WHERE id IN :ids", report_ids)
        counts['test_reports'] = len(report_ids)
        logger.info(f"[软删除清理] 硬删除 test_reports: {len(report_ids)} 条")

    # ================================================================
    # 8. spl_mappings
    # ================================================================
    spl_ids = _collect_expired_ids(session, 'spl_mappings', threshold_dt)
    if spl_ids:
        _batch_delete(session,
            "DELETE FROM spl_mappings WHERE id IN :ids", spl_ids)
        counts['spl_mappings'] = len(spl_ids)
        logger.info(f"[软删除清理] 硬删除 spl_mappings: {len(spl_ids)} 条")

    # ================================================================
    # 9. dimensions（子维度先删，再删主维度）
    # ================================================================
    dim_ids = _collect_expired_ids(session, 'dimensions', threshold_dt)
    if dim_ids:
        # 9.1 先删子维度（parent_dimension_id 指向待删主维度）
        _batch_delete(session,
            "DELETE FROM dimensions WHERE parent_dimension_id IN :ids", dim_ids)
        # 9.2 删维度本体
        _batch_delete(session,
            "DELETE FROM dimensions WHERE id IN :ids", dim_ids)
        counts['dimensions'] = len(dim_ids)
        logger.info(f"[软删除清理] 硬删除 dimensions: {len(dim_ids)} 条")

    # ================================================================
    # 10. categories
    # ================================================================
    cat_ids = _collect_expired_ids(session, 'categories', threshold_dt)
    if cat_ids:
        _batch_delete(session,
            "DELETE FROM categories WHERE id IN :ids", cat_ids)
        counts['categories'] = len(cat_ids)
        logger.info(f"[软删除清理] 硬删除 categories: {len(cat_ids)} 条")

    # ================================================================
    # 11. tags（关联表 test_case_tags / audio_tags / device_tags / task_tags 已随父记录清理）
    # ================================================================
    tag_ids = _collect_expired_ids(session, 'tags', threshold_dt)
    if tag_ids:
        _batch_delete(session,
            "DELETE FROM tags WHERE id IN :ids", tag_ids)
        counts['tags'] = len(tag_ids)
        logger.info(f"[软删除清理] 硬删除 tags: {len(tag_ids)} 条")

    # ================================================================
    # 12. tag_categories
    # ================================================================
    tc_ids = _collect_expired_ids(session, 'tag_categories', threshold_dt)
    if tc_ids:
        _batch_delete(session,
            "DELETE FROM tag_categories WHERE id IN :ids", tc_ids)
        counts['tag_categories'] = len(tc_ids)
        logger.info(f"[软删除清理] 硬删除 tag_categories: {len(tc_ids)} 条")

    return counts


def run_cleanup_once():
    """执行一次清理。供定时线程或手动调用。

    Returns:
        counts: dict，key 为表名，value 为删除条数。失败时返回空 dict。
    """
    try:
        init_db()
        session = get_db_session()
        threshold_dt = now_cst() - timedelta(days=RETENTION_DAYS)
        counts = _hard_delete_expired(session, threshold_dt)
        session.commit()
        if counts:
            summary = ", ".join(f"{k}={v}" for k, v in counts.items())
            logger.info(f"[软删除清理] 完成：{summary}")
        return counts
    except Exception as e:
        logger.error(f"[软删除清理] 失败: {e}", exc_info=True)
        try:
            session.rollback()
        except Exception:
            pass
        return {}
    finally:
        try:
            remove_db_session()
        except Exception:
            pass


def _cleaner_loop():
    """定时清理循环，间隔由 SCAN_INTERVAL_SECONDS 控制。"""
    logger.info(f"[软删除清理] 后台任务启动，每 {SCAN_INTERVAL_SECONDS}s 扫描一次，保留期 {RETENTION_DAYS} 天")
    while not _stop_event.is_set():
        try:
            run_cleanup_once()
        except Exception as e:
            logger.error(f"[软删除清理] 循环异常: {e}", exc_info=True)
        # 等待间隔或被停止信号唤醒
        _stop_event.wait(timeout=SCAN_INTERVAL_SECONDS)


def start_soft_delete_cleaner():
    """启动软删除清理守护线程（幂等，重复调用不会创建多个线程）。"""
    global _cleaner_thread
    if _cleaner_thread is not None and _cleaner_thread.is_alive():
        logger.info("[软删除清理] 线程已在运行，跳过")
        return
    _stop_event.clear()
    _cleaner_thread = threading.Thread(target=_cleaner_loop, name="soft-delete-cleaner", daemon=True)
    _cleaner_thread.start()
    logger.info("[软删除清理] 守护线程已启动")


def stop_soft_delete_cleaner():
    """停止软删除清理守护线程。"""
    global _cleaner_thread
    _stop_event.set()
    if _cleaner_thread is not None:
        _cleaner_thread.join(timeout=5)
        _cleaner_thread = None
    logger.info("[软删除清理] 守护线程已停止")
