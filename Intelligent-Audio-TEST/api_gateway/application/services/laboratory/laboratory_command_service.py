# -*- coding: utf-8 -*-
"""api_gateway 应用层 —— 实验室写操作服务（CQRS Command Side，INT-493/INT-537 拆分①）

命令侧写库（经 infrastructure 仓储直连共享库 laboratories 表，设计文档 §7.2 授权）
并发布 CONFIG_EVENTS（实验室属配置域）。事务由本服务管理：成功 commit、失败 rollback。
"""
import logging

from shared.infrastructure.user_context import get_current_user_id
from shared.models.database import get_db_session
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.repositories.laboratory_repository import (
    LaboratoryRepositoryImpl,
)
from api_gateway.infrastructure.read_models.laboratory_resource_read_model import (
    LaboratoryResourceReadModel,
)
from api_gateway.schemas.laboratory import (
    LaboratoryCreateRequest,
    LaboratoryUpdateRequest,
    LaboratoryIdData,
)

logger = logging.getLogger(__name__)

_laboratory_repo = LaboratoryRepositoryImpl()


def _operator_user_id():
    return get_current_user_id()


def _publish_lab_config_event(action: str, lab_id: int, code: str) -> None:
    """发布 CONFIG_EVENTS 实验室配置变更事件（Redis 不可用仅记日志不阻塞业务）。"""
    EventBus().publish(
        EventChannel.CONFIG_EVENTS,
        EventType.LABORATORY_CONFIG_CHANGED,
        {'action': action, 'lab_id': lab_id, 'code': code},
    )


class LaboratoryCommandService:
    """实验室写操作服务（create/update/delete）。"""

    @staticmethod
    def create():
        try:
            validated = LaboratoryCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {e}", code=ErrorCode.INVALID_PARAMS)

        session = get_db_session()
        try:
            # code 唯一校验（含软删行冲突返回 409 —— laboratories.code 唯一索引
            # 未过滤 deleted，重建同名需先清软删或迁移调整，本卡按 409 处理）
            existing = _laboratory_repo.get_by_code(validated.code)
            if existing is not None:
                return error_response(
                    f"实验室代码 {validated.code} 已存在（含软删记录），无法创建",
                    code=ErrorCode.CONFLICT,
                    http_code=409,
                )

            created = _laboratory_repo.create({
                'code': validated.code,
                'name': validated.name,
                'building': validated.building,
                'floor': validated.floor,
                'room_number': validated.room_number,
                'description': validated.description,
                'status': validated.status.value,
                'created_by_user_id': _operator_user_id(),
            })
            session.commit()
            _publish_lab_config_event('create', created.id, created.code)
            return success_response(
                LaboratoryIdData(id=created.id), '实验室创建成功', http_code=201)
        except Exception as e:
            session.rollback()
            # DB 唯一约束竞态兜底（并发同名创建）：统一按 409 表达
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                return error_response(
                    f"实验室代码 {validated.code} 已存在", code=ErrorCode.CONFLICT, http_code=409)
            logger.exception('创建实验室失败: lab code=%s', validated.code)
            return error_response(f"创建实验室失败: {e}")

    @staticmethod
    def update(lab_id: int):
        try:
            validated = LaboratoryUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {e}", code=ErrorCode.INVALID_PARAMS)

        session = get_db_session()
        try:
            lab = _laboratory_repo.get(lab_id)
            if lab is None:
                return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)

            # 变更 code 时校验唯一（含软删行冲突 409）
            if validated.code is not None and validated.code != lab.code:
                existing = _laboratory_repo.get_by_code(validated.code)
                if existing is not None:
                    return error_response(
                        f"实验室代码 {validated.code} 已存在（含软删记录），无法更新",
                        code=ErrorCode.CONFLICT,
                        http_code=409,
                    )

            data = {}
            for col in ('code', 'name', 'building', 'floor', 'room_number', 'description'):
                value = getattr(validated, col)
                if value is not None:
                    data[col] = value
            if validated.status is not None:
                data['status'] = validated.status.value
            data['updated_by_user_id'] = _operator_user_id()

            updated = _laboratory_repo.update(lab_id, data)
            session.commit()
            _publish_lab_config_event('update', lab_id, updated.code if updated else lab.code)
            return success_response(
                LaboratoryIdData(id=lab_id), '实验室更新成功')
        except Exception as e:
            session.rollback()
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                return error_response(
                    f"实验室代码已存在", code=ErrorCode.CONFLICT, http_code=409)
            logger.exception('更新实验室失败: lab_id=%s', lab_id)
            return error_response(f"更新实验室失败: {e}")

    @staticmethod
    def delete(lab_id: int):
        session = get_db_session()
        try:
            lab = _laboratory_repo.get(lab_id)
            if lab is None:
                return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)

            # 删除前校验设备/播放设备/用例引用（counts 经 gRPC 聚合，未就绪容错为 0）
            counts = LaboratoryResourceReadModel.counts(lab_id)
            if counts['device_count'] > 0 or counts['playback_device_count'] > 0 \
                    or counts['test_case_count'] > 0:
                return error_response(
                    '实验室下存在设备/播放设备/用例资源，无法删除',
                    code=ErrorCode.CONFLICT,
                    http_code=409,
                )

            _laboratory_repo.delete(lab_id, deleted_by_user_id=_operator_user_id())
            session.commit()
            _publish_lab_config_event('delete', lab_id, lab.code)
            return success_response(None, '实验室已删除')
        except Exception as e:
            session.rollback()
            logger.exception('删除实验室失败: lab_id=%s', lab_id)
            return error_response(f"删除实验室失败: {e}")
