# -*- coding: utf-8 -*-
"""device_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 device_service owned 的表：
  1. devices 及其子表（device_tags）
  2. spl_mappings

注：playback_devices 使用 is_deleted（无 deleted_at），不在此清理。

保护策略：硬删除前检查待删 devices 是否仍被活跃 task 通过
          task_device_relations 引用。若被引用则跳过，并刷新 deleted_at
          为当前时间，重置 60 天保留期，给引用方窗口自然清理。

启动方式：在 device_service 的 gRPC server 启动时调用 start()，关闭时调用 stop()。
"""
import logging

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class DeviceServiceCleaner(SoftDeleteCleanerBase):
    """device_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。"""
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids
        rda = self.refresh_deleted_at

        # ================================================================
        # 1. devices 及其子表（device_tags）
        # ================================================================
        device_ids = cei(session, 'devices', threshold_dt)
        if device_ids:
            # 跳过仍被 task_device_relations 引用的设备
            # （关联表无 deleted 列，引用方 task 可能已软删但关联行仍存在；
            #   等 task_service cleaner 硬删 task 时会清理 task_device_relations）
            referenced = self.filter_referenced_ids(
                session, 'task_device_relations', 'device_id', device_ids,
                exclude_deleted=False)
            if referenced:
                rda(session, 'devices', list(referenced))
                logger.info(
                    f"[软删除清理:device_service] 跳过 {len(referenced)} 条 "
                    f"仍被 task_device_relations 引用的 devices，已刷新 deleted_at")
                device_ids = [i for i in device_ids if i not in referenced]
            if device_ids:
                # 1.1 device_tags（关联表，无 deleted_at）
                bd(session, "DELETE FROM device_tags WHERE device_id IN :ids", device_ids)
                # 1.2 devices
                bd(session, "DELETE FROM devices WHERE id IN :ids", device_ids)
                counts['devices'] = len(device_ids)
                logger.info(f"[软删除清理:device_service] 硬删除 devices: {len(device_ids)} 条")

        # ================================================================
        # 2. spl_mappings
        # ================================================================
        spl_ids = cei(session, 'spl_mappings', threshold_dt)
        if spl_ids:
            bd(session, "DELETE FROM spl_mappings WHERE id IN :ids", spl_ids)
            counts['spl_mappings'] = len(spl_ids)
            logger.info(f"[软删除清理:device_service] 硬删除 spl_mappings: {len(spl_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: DeviceServiceCleaner | None = None


def get_cleaner() -> DeviceServiceCleaner:
    """获取 device_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = DeviceServiceCleaner(service_name='device_service')
    return _cleaner
