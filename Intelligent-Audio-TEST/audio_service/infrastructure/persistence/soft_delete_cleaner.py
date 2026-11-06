# -*- coding: utf-8 -*-
"""audio_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 audio_service owned 的表：
  1. audios 及其子表（audio_annotations / audio_tags / audio_algorithm_relations）

启动方式：在 audio_service 的 gRPC server 启动时调用 start()，关闭时调用 stop()。
"""
import logging

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class AudioServiceCleaner(SoftDeleteCleanerBase):
    """audio_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。"""
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids

        # ================================================================
        # 1. audios 及其子表
        # ================================================================
        audio_ids = cei(session, 'audios', threshold_dt)
        if audio_ids:
            # 1.1 audio_annotations
            bd(session, "DELETE FROM audio_annotations WHERE audio_id IN :ids", audio_ids)
            # 1.2 audio_tags（关联表，无 deleted_at）
            bd(session, "DELETE FROM audio_tags WHERE audio_id IN :ids", audio_ids)
            # 1.3 audio_algorithm_relations
            bd(session, "DELETE FROM audio_algorithm_relations WHERE audio_id IN :ids", audio_ids)
            # 1.4 audios
            bd(session, "DELETE FROM audios WHERE id IN :ids", audio_ids)
            counts['audios'] = len(audio_ids)
            logger.info(f"[软删除清理:audio_service] 硬删除 audios: {len(audio_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: AudioServiceCleaner | None = None


def get_cleaner() -> AudioServiceCleaner:
    """获取 audio_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = AudioServiceCleaner(service_name='audio_service')
    return _cleaner
