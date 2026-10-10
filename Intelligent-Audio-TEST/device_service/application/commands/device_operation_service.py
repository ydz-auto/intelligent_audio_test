# -*- coding: utf-8 -*-
"""设备操作 Command 应用服务（写侧，INT-80）。

- DeviceOperationService：单设备操作（connect/disconnect/reboot/shutdown/
  install_app/uninstall_app），走既有驱动命令工具（adb/hdc），
  每次操作落状态事件（source=operation）并发布 DEVICE_EVENTS。
- DeviceBatchService：批量操作（复用 16 种批量 action 的幂等模式：
  客户端幂等键 / 请求指纹 → Redis 两态存储 → 回放/409），动作枚举派发。

返回 dict（{success, message, data, code}），由 servicer 层包装 gRPC 响应。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Tuple

from device_service.domain.repositories import DeviceRepositoryInterface
from shared.models.common_enums import DeviceOperation, DeviceStatusEventType
from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)

# 幂等回放窗口（秒）：客户端键 24h，指纹 1h，占位 10min（崩溃自愈）
_IDEMPOTENCY_CLIENT_KEY_TTL = 86400
_IDEMPOTENCY_FINGERPRINT_TTL = 3600
_IDEMPOTENCY_RESERVE_TTL = 600
_IDEMPOTENCY_EXCLUDED_KEYS = {'idempotency_key'}

# 批量动作白名单：设备控制类操作 + 健康检查
BATCH_ACTIONS = (
    DeviceOperation.CONNECT.value,
    DeviceOperation.DISCONNECT.value,
    DeviceOperation.REBOOT.value,
    DeviceOperation.SHUTDOWN.value,
    DeviceOperation.INSTALL_APP.value,
    DeviceOperation.UNINSTALL_APP.value,
    'health_check',
)


class DeviceOperationService:
    """单设备操作应用服务"""

    def __init__(self, repo: DeviceRepositoryInterface = None, executor=None, monitor=None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import device_repository
            repo = device_repository
        self.repo = repo
        if executor is None:
            from device_service.infrastructure.device_operations import device_operation_executor
            executor = device_operation_executor
        self.executor = executor
        self.monitor = monitor

    @property
    def _monitor(self):
        if self.monitor is None:
            from device_service.application.services.device_monitor_service import device_monitor_service
            self.monitor = device_monitor_service
        return self.monitor

    def execute(self, device_id: int, operation: str, params: dict = None) -> dict:
        """执行设备操作并记录状态事件。"""
        try:
            from shared.models.common_enums import DeviceOperation as _Op
            try:
                _Op(operation)
            except ValueError:
                return {'success': False, 'message': f'不支持的操作类型: {operation}',
                        'data': None, 'code': 400}

            device = self.repo.get_device(device_id)
            if not device:
                return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

            result = self.executor.execute(device, operation, params or {})
            self._monitor.record_status_event(
                device_id=device_id,
                event_type=DeviceStatusEventType.OPERATION.value,
                from_status=device.status,
                to_status=device.status,
                source='operation',
                success=True,
                detail={'operation': operation, 'params': params or {}, 'output': result.get('output', '')},
            )
            log_not_emit('INFO', 'DeviceOperation',
                         f"设备操作成功: device={device_id} op={operation}",
                         category='device', source='backend', device_id=device_id)
            return {
                'success': True,
                'message': f'操作 {operation} 执行成功',
                'data': {'id': device_id, 'operation': operation, **result},
                'code': 200,
            }
        except Exception as e:
            # 失败也落事件（success=False），供趋势/告警侧观测
            try:
                self._monitor.record_status_event(
                    device_id=device_id,
                    event_type=DeviceStatusEventType.OPERATION.value,
                    source='operation', success=False,
                    detail={'operation': operation, 'error': str(e)[:500]},
                )
            except Exception:
                logger.debug("操作失败事件落库失败", exc_info=True)
            logger.warning("设备操作失败 device=%s op=%s: %s", device_id, operation, e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


class DeviceBatchService:
    """设备批量操作应用服务（幂等模式对齐 testcase batch，INT-75）"""

    def __init__(self, op_service: DeviceOperationService = None, idempotency_store=None):
        self.op_service = op_service or DeviceOperationService()
        if idempotency_store is None:
            from device_service.infrastructure.persistence.device_idempotency_store import redis_device_idempotency_store
            idempotency_store = redis_device_idempotency_store
        self.idempotency_store = idempotency_store

    # ---------- 幂等防护 ----------

    @staticmethod
    def _resolve_idempotency_key(data: dict) -> Tuple[str, int]:
        """客户端幂等键优先，缺省回退请求内容指纹（action + 排序后 device_ids + 其余参数）"""
        client_key = str(data.get('idempotency_key') or '').strip()
        if client_key:
            return f'client:{client_key}', _IDEMPOTENCY_CLIENT_KEY_TTL

        payload = {k: v for k, v in data.items() if k not in _IDEMPOTENCY_EXCLUDED_KEYS}
        ids = payload.get('device_ids')
        if isinstance(ids, list):
            payload['device_ids'] = sorted(str(i) for i in ids)
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        return f'fp:{digest}', _IDEMPOTENCY_FINGERPRINT_TTL

    def _idempotency_guard(self, key: str, ttl_seconds: int):
        record = self.idempotency_store.lookup(key)
        if record is None and not self.idempotency_store.reserve(
                key, min(ttl_seconds, _IDEMPOTENCY_RESERVE_TTL)):
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
            logger.info("[device_batch] 幂等回放 key=%s", key)
            return response
        return {
            'success': False,
            'message': '相同批量操作正在处理中，请勿重复提交',
            'data': None,
            'code': 409,
        }

    def _idempotency_complete(self, key: str, ttl_seconds: int, response: dict) -> None:
        try:
            self.idempotency_store.complete(key, response, ttl_seconds)
        except Exception:
            logger.warning("[device_batch] 幂等响应落库失败 key=%s", key, exc_info=True)

    def _idempotency_release(self, key: str) -> None:
        try:
            self.idempotency_store.release(key)
        except Exception:
            logger.warning("[device_batch] 幂等占位释放失败 key=%s", key, exc_info=True)

    # ---------- 批量动作 ----------

    def batch_action(self, data: dict) -> dict:
        """批量操作入口：{action, device_ids, params?, idempotency_key?}"""
        action = data.get('action')
        device_ids = data.get('device_ids') or []

        if action not in BATCH_ACTIONS:
            return {'success': False, 'message': f'不支持的批量操作类型: {action}',
                    'data': None, 'code': 400}
        if not device_ids:
            return {'success': False, 'message': 'device_ids 不能为空', 'data': None, 'code': 400}

        idem_key, idem_ttl = self._resolve_idempotency_key(data)
        try:
            replay = self._idempotency_guard(idem_key, idem_ttl)
        except Exception:
            logger.warning("[device_batch] 幂等防护异常，降级放行 key=%s", idem_key, exc_info=True)
            replay = None
        if replay is not None:
            return replay

        try:
            params = data.get('params') or {}
            results = []
            success_count = 0
            if action == 'health_check':
                # 委托既有健康检查命令（其内部落状态事件并发布 DEVICE_EVENTS）
                from device_service.application.commands.device_command_service import device_command_service
                hc = device_command_service.health_check(device_ids=[int(d) for d in device_ids])
                if hc.get('success'):
                    items = hc.get('data') or []
                    online = sum(1 for item in items if item.get('status') == 'online')
                    success_count = online
                    results = [{'id': item.get('id'), 'success': True,
                                'status': item.get('status')} for item in items]
                    message = f'批量健康检查完成: 在线 {online}/{len(items)}'
                else:
                    message = hc.get('message', '批量健康检查失败')
                    response = {'success': False, 'message': message, 'data': None, 'code': 400}
                    self._idempotency_release(idem_key)
                    return response
            else:
                for device_id in device_ids:
                    op_result = self.op_service.execute(int(device_id), action, params)
                    if op_result.get('success'):
                        success_count += 1
                    results.append({
                        'id': device_id,
                        'success': op_result.get('success'),
                        'message': op_result.get('message'),
                    })
                message = f'批量操作 {action} 完成: 成功 {success_count}/{len(device_ids)}'

            log_not_emit('INFO', 'DeviceBatch',
                         f"批量设备操作: action={action} 总数={len(device_ids)} 成功={success_count} "
                         f"idempotency_key={idem_key}",
                         category='device', source='backend')
            response = {
                'success': True,
                'message': message,
                'data': {'action': action, 'total': len(device_ids),
                         'success_count': success_count, 'results': results},
                'code': 200,
            }
            self._idempotency_complete(idem_key, idem_ttl, response)
            self._publish_batch_event(action, device_ids, message, idem_key)
            return response
        except Exception as e:
            self._idempotency_release(idem_key)
            logger.exception("批量设备操作失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    @staticmethod
    def _publish_batch_event(action: str, device_ids, message: str, idempotency_key: str = '') -> None:
        """批量操作成功后发布 DEVICE_EVENTS 领域事件（降级只打日志）。"""
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            EventBus().publish(
                EventChannel.DEVICE_EVENTS, EventType.DEVICE_STATUS_CHANGED,
                {
                    'event_type': 'batch_action',
                    'action': action,
                    'device_ids': list(device_ids or []),
                    'message': message,
                    'idempotency_key': idempotency_key,
                    'timestamp': datetime.now().isoformat(),
                },
            )
        except Exception:
            logger.warning("发布设备批量操作事件失败，降级忽略 (action=%s)", action, exc_info=True)


device_operation_service = DeviceOperationService()
device_batch_service = DeviceBatchService()
