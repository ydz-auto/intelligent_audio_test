# -*- coding: utf-8 -*-
"""API RMS→SPL 映射配置应用服务（UC-0902 数据基座）

与 APICrudService 对称的应用层写侧+读侧服务：
- 命令侧只写并发布事件（CONFIG_EVENTS / SPL_MAPPING_CONFIG_CHANGED）
- 查询侧只读（含执行期 spl_to_gain(api_id, spl) 查询）
- 并发校准互斥：DistributedLock lock:spl:calibration:{api_id}（UC-0902）

servicer 层把 gRPC JSON 参数构造成命令/查询对象后委托给本服务。
"""
import logging
import math
from typing import Optional

from shared.models.common_enums import CalibrationStatus, DeviceType, RedisKeyPrefix
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from shared.utils.distributed_coordinator import DistributedLock
from api_test_service.domain.entities.api_rms_spl_mapping import CalibrationPoint
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
    ApiRmsSplRepositoryImpl,
)

logger = logging.getLogger(__name__)

# 参考声压级合理区间（dB SPL），防止配置错误导致增益爆炸
_MIN_REFERENCE_SPL = 30.0
_MAX_REFERENCE_SPL = 120.0


def _mapping_to_dict(mapping) -> dict:
    """领域实体 → 序列化 dict（camelCase 由前端 Infrastructure 层转换）"""
    return {
        'id': mapping.id,
        'api_id': mapping.api_id,
        'name': mapping.name,
        'vendor': mapping.vendor,
        'protocol': mapping.protocol,
        'reference_spl': mapping.reference_spl,
        'reference_gain_linear': mapping.reference_gain_linear,
        'calibration_status': mapping.calibration_status,
        'calibration_points': [
            {
                'target_spl': p.target_spl,
                'gain_linear': p.gain_linear,
                'rms_dbfs': p.rms_dbfs,
            }
            for p in mapping.calibration_points
        ],
        'min_gain_linear': mapping.min_gain_linear,
        'max_gain_linear': mapping.max_gain_linear,
        'is_calibrated': mapping.is_calibrated(),
    }


class ApiRmsSplConfigService:
    """被测 API RMS→SPL 映射配置应用服务（写侧 + 读侧）"""

    def __init__(self, repository=None):
        self._repository = repository

    @property
    def repository(self):
        if self._repository is None:
            self._repository = ApiRmsSplRepositoryImpl()
        return self._repository

    # ========== 校验 ==========

    @staticmethod
    def _validate_mapping_data(data: dict, require_api_id: bool = True) -> Optional[str]:
        """校验映射配置数据，返回错误消息或 None"""
        if require_api_id and not data.get('api_id'):
            return "缺少必要字段: api_id"

        reference_spl = data.get('reference_spl')
        if reference_spl is not None:
            if not isinstance(reference_spl, (int, float)) or not (_MIN_REFERENCE_SPL <= reference_spl <= _MAX_REFERENCE_SPL):
                return (f"参考声压级 (reference_spl) 必须在 "
                        f"{_MIN_REFERENCE_SPL:g}-{_MAX_REFERENCE_SPL:g} dB 之间")

        for field_name in ('reference_gain_linear', 'min_gain_linear', 'max_gain_linear'):
            value = data.get(field_name)
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                return f"{field_name} 必须为正数"

        min_gain = data.get('min_gain_linear')
        max_gain = data.get('max_gain_linear')
        if min_gain is not None and max_gain is not None and min_gain >= max_gain:
            return "min_gain_linear 必须小于 max_gain_linear"

        calibration_status = data.get('calibration_status') or data.get('calibrationStatus')
        if calibration_status is not None and calibration_status not in {s.value for s in CalibrationStatus}:
            return (f"非法的校准状态 (calibration_status): {calibration_status}，"
                    f"仅支持: {', '.join(s.value for s in CalibrationStatus)}")

        points = (data.get('calibration_data') or {}).get('points')
        if points is not None:
            if not isinstance(points, list):
                return "校准数据 (calibration_data.points) 必须是数组"
            for i, p in enumerate(points):
                if not isinstance(p, dict) or 'target_spl' not in p or 'gain_linear' not in p:
                    return (f"校准点[{i}] 缺少 target_spl/gain_linear 字段")

        return None

    # ========== 事件 ==========

    @staticmethod
    def _publish_config_changed(action: str, mapping_id=None, api_id=None) -> None:
        """映射配置变更后发布事件（Redis 不可用时降级只打日志）"""
        try:
            payload = {'action': action}
            if mapping_id is not None:
                payload['mapping_id'] = mapping_id
            if api_id is not None:
                payload['api_id'] = api_id
            EventBus().publish(
                EventChannel.CONFIG_EVENTS,
                EventType.SPL_MAPPING_CONFIG_CHANGED,
                payload,
            )
        except Exception as e:
            logger.warning(f"发布 SPL 映射配置变更事件失败，降级忽略: {e}")

    # ========== 写操作 ==========

    def create(self, data: dict) -> dict:
        error = self._validate_mapping_data(data)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        try:
            mapping = self.repository.create_mapping(data)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

        self._publish_config_changed('created', mapping_id=mapping.id, api_id=mapping.api_id)
        return {
            'success': True,
            'message': 'RMS→SPL 映射创建成功',
            'data': {'id': mapping.id},
            'code': 201,
        }

    def update(self, mapping_id: int, data: dict) -> dict:
        error = self._validate_mapping_data(data, require_api_id=False)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        try:
            mapping = self.repository.update_mapping(mapping_id, data)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        if mapping is None:
            return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}

        self._publish_config_changed('updated', mapping_id=mapping.id, api_id=mapping.api_id)
        return {
            'success': True,
            'message': 'RMS→SPL 映射更新成功',
            'data': _mapping_to_dict(mapping),
            'code': 200,
        }

    def delete(self, mapping_id: int) -> dict:
        try:
            mapping = self.repository.get_mapping(mapping_id)
            if mapping is None:
                return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
            self.repository.delete_mapping(mapping_id)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

        self._publish_config_changed('deleted', mapping_id=mapping.id, api_id=mapping.api_id)
        return {'success': True, 'message': 'RMS→SPL 映射已删除', 'data': None, 'code': 200}

    def calibrate(self, mapping_id: int, calibration_data: dict) -> dict:
        """执行校准（UC-0902 步骤4）：以请求点集全量替换校准点 + 置已校准。

        同一 API 并发校准互斥：抢不到 lock:spl:calibration:{api_id} 直接拒绝。
        Redis 不可用时 DistributedLock 降级放行（与锁实现承诺一致）。
        写入点集完全来自本次请求（锁内重读映射后替换），不依赖抢锁前的
        陈旧读，消除读-改-写窗口溢出锁外的覆盖风险。
        """
        try:
            mapping = self.repository.get_mapping(mapping_id)
            if mapping is None:
                return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}

            points = (calibration_data or {}).get('points')
            if not isinstance(points, list) or not points:
                return {'success': False, 'message': '校准数据必须包含非空 points 数组', 'data': None, 'code': 400}
            for i, p in enumerate(points):
                if not isinstance(p, dict) or 'target_spl' not in p or 'gain_linear' not in p:
                    return {'success': False, 'message': f'校准点[{i}] 缺少 target_spl/gain_linear 字段',
                            'data': None, 'code': 400}
                target_spl = p['target_spl']
                gain_linear = p['gain_linear']
                if not isinstance(target_spl, (int, float)) or not math.isfinite(target_spl):
                    return {'success': False, 'message': f'校准点[{i}] target_spl 必须为有限数值',
                            'data': None, 'code': 400}
                if not isinstance(gain_linear, (int, float)) or not math.isfinite(gain_linear) or gain_linear <= 0:
                    return {'success': False, 'message': f'校准点[{i}] gain_linear 必须为正的有限数值',
                            'data': None, 'code': 400}

            lock = DistributedLock(
                f"{RedisKeyPrefix.SPL_CALIBRATION_LOCK.value}:{mapping.api_id}"
            )
            if not lock.acquire(blocking=False):
                return {
                    'success': False,
                    'message': f'API {mapping.api_id} 正在执行校准，请稍后再试',
                    'data': None,
                    'code': 409,
                }
            try:
                # 锁内重读：抢锁前 read 的快照可能已被并发校准提交覆盖
                mapping = self.repository.get_mapping(mapping_id)
                if mapping is None:
                    return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
                mapping.replace_calibration_points(CalibrationPoint(
                    target_spl=float(p['target_spl']),
                    gain_linear=float(p['gain_linear']),
                    rms_dbfs=p.get('rms_dbfs'),
                ) for p in points)
                updated = self.repository.update_mapping(mapping.id, {
                    'calibration_status': CalibrationStatus.CALIBRATED.value,
                    'calibration_data': {
                        'points': [
                            {
                                'target_spl': cp.target_spl,
                                'gain_linear': cp.gain_linear,
                                'rms_dbfs': cp.rms_dbfs,
                            }
                            for cp in mapping.calibration_points
                        ]
                    },
                })
            finally:
                lock.release()
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

        self._publish_config_changed('calibrated', mapping_id=mapping_id, api_id=mapping.api_id)
        return {
            'success': True,
            'message': '校准完成',
            'data': _mapping_to_dict(updated),
            'code': 200,
        }

    def set_default(self, api_id: int, mapping_id: Optional[int]) -> dict:
        """设置 API 当前默认映射（apis.rms_spl_mapping_id，UC-0902 步骤6）

        mapping_id=None/0 清除默认映射。
        """
        from api_test_service.infrastructure.persistence.api_test_repository import api_test_repository

        try:
            if mapping_id:
                mapping = self.repository.get_mapping(mapping_id)
                if mapping is None:
                    return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
                if mapping.api_id != int(api_id):
                    return {'success': False, 'message': '映射不属于该 API', 'data': None, 'code': 400}

            updated = api_test_repository.update_api(api_id, {
                'rms_spl_mapping_id': int(mapping_id) if mapping_id else None,
            })
            if updated is None:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

        self._publish_config_changed('default_set', mapping_id=mapping_id, api_id=api_id)
        return {
            'success': True,
            'message': '默认映射已更新',
            'data': {'api_id': api_id, 'rms_spl_mapping_id': mapping_id},
            'code': 200,
        }

    # ========== 读操作（无副作用） ==========

    def get_one(self, mapping_id: int) -> dict:
        try:
            mapping = self.repository.get_mapping(mapping_id)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        if mapping is None:
            return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': _mapping_to_dict(mapping), 'code': 200}

    def get_all(self, page: int = 1, per_page: int = 10,
                api_id=None, calibration_status=None) -> dict:
        try:
            result = self.repository.list_mappings(
                page=page, per_page=per_page,
                api_id=api_id, calibration_status=calibration_status,
            )
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        return {
            'success': True,
            'message': 'Success',
            'data': {
                'items': [_mapping_to_dict(m) for m in result['items']],
                'total': result['total'],
                'page': result['page'],
                'per_page': result['per_page'],
                'pages': result['pages'],
            },
            'code': 200,
        }

    def get_by_api(self, api_id: int) -> dict:
        try:
            mappings = self.repository.list_by_api(api_id)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        return {
            'success': True,
            'message': 'Success',
            'data': {'items': [_mapping_to_dict(m) for m in mappings], 'total': len(mappings)},
            'code': 200,
        }

    def get_spl_gain(self, api_id: int, target_spl: float) -> dict:
        """执行期查询：目标 SPL → 推送线性增益（与校准点一致，UC-0902 验收）"""
        try:
            gain = ApiRmsSplService(self.repository).spl_to_gain(api_id, target_spl)
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        return {
            'success': True,
            'message': 'Success',
            'data': {'api_id': api_id, 'target_spl': target_spl, 'gain_linear': gain},
            'code': 200,
        }


# 模块级实例
api_rms_spl_config_service = ApiRmsSplConfigService()
