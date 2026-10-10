# -*- coding: utf-8 -*-
"""TestCaseBatchService — 测试用例批量操作应用服务。

从 testcase_crud_service 拆分，承担所有批量动作（删除/移动/复制/参数更新/
播放设备/声压/维度/噪声/自动命名/标签增删改/参考参数刷新）。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 保留软删除模式（deleted=True + deleted_at）

按职责拆分为 Mixin 组合（对外 API 不变，导入路径保持本模块）：
- testcase_batch_reference_mixin.TestCaseReferenceRefreshMixin: 参考参数刷新（含模块级辅助函数）
- testcase_batch_copy_move_mixin.TestCaseCopyMoveMixin: 删除/移动/复制/自动命名
- testcase_batch_config_update_mixin.TestCaseConfigUpdateMixin: 专属参数/播放设备/声压/维度/噪声更新
- testcase_batch_tag_mixin.TestCaseTagMixin: 标签批量操作
- 本文件保留 batch_action 动作调度入口与依赖注入。
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Tuple

from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

from task_service.application.testcase.testcase_batch_reference_mixin import (
    TestCaseReferenceRefreshMixin,
    _REF_PARAMS_BUCKET,
    _build_ref_params_key,
    _apply_reference_params_to_config,
)
from task_service.application.testcase.testcase_batch_copy_move_mixin import TestCaseCopyMoveMixin
from task_service.application.testcase.testcase_batch_config_update_mixin import TestCaseConfigUpdateMixin
from task_service.application.testcase.testcase_batch_tag_mixin import TestCaseTagMixin

logger = logging.getLogger(__name__)

# 内容指纹计算时剔除的请求键：幂等键本身不参与指纹
_IDEMPOTENCY_EXCLUDED_KEYS = {'idempotency_key'}

# 模块级公共符号再导出（保持向后兼容：_REF_PARAMS_BUCKET / _build_ref_params_key /
# _apply_reference_params_to_config 仍可从本模块导入）
__all__ = [
    'TestCaseBatchService',
    '_REF_PARAMS_BUCKET',
    '_build_ref_params_key',
    '_apply_reference_params_to_config',
]


class TestCaseBatchService(
    TestCaseReferenceRefreshMixin,
    TestCaseCopyMoveMixin,
    TestCaseConfigUpdateMixin,
    TestCaseTagMixin,
):
    """测试用例批量操作应用服务。

    职责拆分为四个 Mixin 组合：
    - TestCaseReferenceRefreshMixin: 参考参数刷新
    - TestCaseCopyMoveMixin: 删除/移动/复制/自动命名
    - TestCaseConfigUpdateMixin: 配置更新（参数/设备/声压/维度/噪声）
    - TestCaseTagMixin: 标签批量操作
    """

    def __init__(self, repo: TestCaseGroupRepositoryABC = None, idempotency_store=None):
        self.repo = repo or testcase_repository
        # 幂等键仓储（INT-75）：默认 Redis 实现，测试可注入假实现
        if idempotency_store is None:
            from task_service.infrastructure.persistence.idempotency_store import redis_idempotency_store
            idempotency_store = redis_idempotency_store
        self.idempotency_store = idempotency_store

    # ---------- 幂等防护（INT-75） ----------

    @staticmethod
    def _resolve_idempotency_key(data: dict) -> Tuple[str, int]:
        """解析幂等键与回放 TTL：客户端幂等键优先，缺省回退请求内容指纹。

        指纹 = sha256(action + 排序后 ids + 其余参数的稳定 JSON)，对 ids 排序
        归一化以忽略提交顺序差异。同一指纹在窗口期内重复提交视为同批次。

        Returns:
            (幂等键, 回放 TTL 秒)
        """
        from task_service.config.config import Config

        client_key = str(data.get('idempotency_key') or '').strip()
        if client_key:
            return f'client:{client_key}', Config.IDEMPOTENCY_CLIENT_KEY_TTL_SECONDS

        payload = {k: v for k, v in data.items() if k not in _IDEMPOTENCY_EXCLUDED_KEYS}
        ids = payload.get('ids')
        if isinstance(ids, list):
            payload['ids'] = sorted(str(i) for i in ids)
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        return f'fp:{digest}', Config.IDEMPOTENCY_FINGERPRINT_TTL_SECONDS

    def _idempotency_guard(self, key: str, ttl_seconds: int) -> dict:
        """重复提交判定：completed 回放上次响应，processing 返回冲突，否则占位放行。

        占位 TTL 取回放 TTL 与保留上限的较小值：执行进程崩溃后占位到期自愈，
        不会永久卡死同键重试；执行成功后 complete 以完整回放 TTL 覆盖。
        Redis 不可用时仓储内部降级放行，不阻塞主流程。
        """
        from task_service.config.config import Config
        record = self.idempotency_store.lookup(key)
        if record is None and not self.idempotency_store.reserve(
                key, min(ttl_seconds, Config.IDEMPOTENCY_RESERVE_TTL_SECONDS)):
            # 占位失败：同批次正在执行或刚完成，重读分类
            record = self.idempotency_store.lookup(key)
            if record is None:
                return None
        if not record:
            return None
        if record.get('status') == 'completed':
            response = dict(record.get('response') or {})
            data = response.get('data')
            replay_marker = {'idempotent_replay': True}
            response['data'] = {**data, **replay_marker} if isinstance(data, dict) else replay_marker
            logger.info("[batch_action] 幂等回放 key=%s", key)
            return response
        return {
            'success': False,
            'message': '相同批量操作正在处理中，请勿重复提交',
            'data': None,
            'code': 409,
        }

    def _idempotency_complete(self, key: str, ttl_seconds: int, response: dict) -> None:
        """执行成功后以完整回放 TTL 落响应，供窗口内重复提交回放。"""
        try:
            self.idempotency_store.complete(key, response, ttl_seconds)
        except Exception:
            logger.warning("[batch_action] 幂等响应落库失败 key=%s", key, exc_info=True)

    def _idempotency_release(self, key: str) -> None:
        """执行失败释放占位，允许客户端重试。"""
        try:
            self.idempotency_store.release(key)
        except Exception:
            logger.warning("[batch_action] 幂等占位释放失败 key=%s", key, exc_info=True)

    # ---------- CASE_EVENTS 领域事件（INT-75） ----------

    @staticmethod
    def _publish_batch_event(action: str, ids, message: str, idempotency_key: str = '',
                             status: str = 'completed', async_task_id: str = '') -> None:
        """批量操作成功后发布 CASE_EVENTS / case_batch_action_completed 领域事件。

        降级：Redis 不可用时 EventBus.publish 内部只打日志，不影响操作结果。
        """
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            from task_service.domain.events.testcase_events import TestCaseBatchAction
            event = TestCaseBatchAction(
                action=action,
                case_ids=list(ids or []),
                success_count=len(ids or []),
                message=message,
                idempotency_key=idempotency_key,
                status=status,
                async_task_id=async_task_id,
            )
            EventBus().publish(EventChannel.CASE_EVENTS, EventType.CASE_BATCH_ACTION_COMPLETED, event.to_dict())
        except Exception:
            logger.warning("发布用例批量操作事件失败，降级忽略 (action=%s)", action, exc_info=True)

    def batch_action(self, data: dict) -> dict:
        """批量操作。

        Args:
            data: {action, ids, ...} — 已通过网关 Pydantic 校验

        Returns:
            {success, message, data, code?}
        """
        from shared.utils import testcase_helpers as common

        action = data.get('action')
        ids = data.get('ids', [])

        handlers = {
            'delete': self._batch_delete,
            'move_to_group': self._batch_move_to_group,
            'copy_to_group': self._batch_copy_to_group,
            'copy': self._batch_copy,
            'copy_by_group': self._batch_copy_by_group,
            'copy_by_tag': self._batch_copy_by_tag,
            'update_algorithm_params': self._batch_update_algorithm_params,
            'update_playback_devices': self._batch_update_playback_devices,
            'update_spl': self._batch_update_spl,
            'update_dimensions': self._batch_update_dimensions,
            'update_noise': self._batch_update_noise,
            'auto_generate_name': self._batch_auto_generate_name,
            'add_tags': self._batch_add_tags,
            'remove_tags': self._batch_remove_tags,
            'rename_tag': self._batch_rename_tag,
            'refresh_reference': self._batch_refresh_reference,
        }

        handler = handlers.get(action)
        if not handler:
            return {'success': False, 'message': f"不支持的操作类型: {action}", 'data': None, 'code': 400}

        # 幂等防护：客户端幂等键 / 请求内容指纹，窗口内重复提交直接回放上次响应
        idem_key, idem_ttl = self._resolve_idempotency_key(data)
        try:
            replay = self._idempotency_guard(idem_key, idem_ttl)
        except Exception:
            logger.warning("[batch_action] 幂等防护异常，降级放行 key=%s", idem_key, exc_info=True)
            replay = None
        if replay is not None:
            return replay

        try:
            result = handler(data, common=common)
            # handler 返回 dict 表示提前返回（如异步任务提交）
            if isinstance(result, dict):
                response = {'success': True, 'message': result.get('message', ''), 'data': result, 'code': 0}
                self._idempotency_complete(idem_key, idem_ttl, response)
                self._publish_batch_event(
                    action, ids, response['message'], idempotency_key=idem_key,
                    status='submitted', async_task_id=result.get('task_id', ''),
                )
                return response
            # handler 返回 (message, is_error) tuple
            if isinstance(result, tuple) and len(result) == 2:
                message, is_error = result
                if is_error:
                    self._idempotency_release(idem_key)
                    return {'success': False, 'message': message, 'data': None, 'code': 400}
                # 正常 message，继续 commit
                message = result[0]
            else:
                message = result

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                logger.warning("批量操作后刷新统计缓存失败", exc_info=True)

            response = {'success': True, 'message': message, 'data': None}
            self._idempotency_complete(idem_key, idem_ttl, response)
            self._publish_batch_event(action, ids, message, idempotency_key=idem_key)
            return response
        except Exception as e:
            self._idempotency_release(idem_key)
            logger.error(f"批量操作失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}
