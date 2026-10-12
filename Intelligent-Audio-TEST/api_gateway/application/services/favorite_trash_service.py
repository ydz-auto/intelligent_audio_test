# -*- coding: utf-8 -*-
"""收藏 / 回收站 BFF Service（INT-141，CQRS Command/Query Side）。

收藏按服务分治路由：task|testcase → task_service，report → report_service；
操作人 user_id / admin 标志由 AuthMiddleware 注入上下文后经
ClientUserContextInterceptor 自动透传（x-user-id / x-user-is-admin），
本层不显式传 user_id（红线：不得由客户端自报充当操作人）。
"""
import logging

from api_gateway.infrastructure.grpc_proxies import report_config_service
from api_gateway.infrastructure.grpc_proxies.task_testcase_config_proxies import (
    task_config_service,
    testcase_config_service,
)
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# EntityType 枚举值（shared.models.common_enums.EntityType）
_ENTITY_TYPES = frozenset({'task', 'report', 'testcase'})


def _report_resp(stub_resp) -> dict:
    """report 域 stub 响应统一解析为 dict（与 task/testcase 代理 _resp 同口径）。

    失败响应的业务码经 data JSON 透传（proto 仅 success/message/data 三字段），
    提升到顶层供路由映射 HTTP 状态码（INT-141 F2）。
    """
    data = _loads(stub_resp.data, None) if stub_resp.data else None
    result = {'success': stub_resp.success, 'message': stub_resp.message, 'data': data}
    if not stub_resp.success and isinstance(data, dict) and isinstance(data.get('code'), int):
        result['code'] = data['code']
    return result


class FavoriteTrashService:
    """收藏 / 回收站 BFF Service：参数校验 → gRPC 分治路由 → 响应组装"""

    # ------------------------------------------------------------------
    # 收藏
    # ------------------------------------------------------------------

    @staticmethod
    def favorite(entity_type: str, entity_id):
        """收藏（幂等：重复收藏返回成功 + already_favorited=true）。"""
        entity_type = (entity_type or '').lower()
        if entity_type not in _ENTITY_TYPES:
            return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
        try:
            if entity_type == 'report':
                resp = _report_resp(report_config_service.stub.FavoriteReport(
                    report_pb.FavoriteReportRequest(report_id=int(entity_id))))
                data = resp.get('data') or {}
            elif entity_type == 'task':
                resp = task_config_service.favorite('task', entity_id)
                data = resp.get('data') or {}
            else:  # testcase
                resp = testcase_config_service.favorite('testcase', entity_id)
                data = resp.get('data') or {}
            if not resp.get('success'):
                return {'code': resp.get('code', 500), 'message': resp.get('message', '收藏失败')}
            return {'data': {'entity_type': entity_type,
                             'entity_id': str(entity_id), **(data if isinstance(data, dict) else {})}}
        except ValueError:
            return {'code': 400, 'message': '实体 ID 格式错误'}
        except Exception as e:
            logger.error(f"收藏失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'收藏失败: {e}'}

    @staticmethod
    def unfavorite(entity_type: str, entity_id):
        """取消收藏（幂等：未收藏同样成功）。"""
        entity_type = (entity_type or '').lower()
        if entity_type not in _ENTITY_TYPES:
            return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
        try:
            if entity_type == 'report':
                resp = _report_resp(report_config_service.stub.UnfavoriteReport(
                    report_pb.FavoriteReportRequest(report_id=int(entity_id))))
                if not resp.get('success'):
                    return {'code': resp.get('code', 500), 'message': resp.get('message', '取消收藏失败')}
                data = resp.get('data') or {}
            elif entity_type == 'task':
                resp = task_config_service.unfavorite('task', entity_id)
                if not resp.get('success'):
                    return {'code': resp.get('code', 500), 'message': resp.get('message', '取消收藏失败')}
                data = resp.get('data') or {}
            else:
                resp = testcase_config_service.unfavorite('testcase', entity_id)
                if not resp.get('success'):
                    return {'code': resp.get('code', 500), 'message': resp.get('message', '取消收藏失败')}
                data = resp.get('data') or {}
            return {'data': {'entity_type': entity_type,
                             'entity_id': str(entity_id), **(data if isinstance(data, dict) else {})}}
        except ValueError:
            return {'code': 400, 'message': '实体 ID 格式错误'}
        except Exception as e:
            logger.error(f"取消收藏失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'取消收藏失败: {e}'}

    @staticmethod
    def list_favorite_ids(entity_type: str):
        """当前用户收藏的实体 ID 列表（entity_type 空 = 返回 task/testcase 两类）。"""
        entity_type = (entity_type or '').lower()
        if entity_type and entity_type not in _ENTITY_TYPES:
            return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
        result = {'task': [], 'report': [], 'testcase': []}
        try:
            if entity_type in ('', 'task', 'testcase'):
                for et in ('task', 'testcase'):
                    resp = task_config_service.list_favorite_ids(et)
                    if resp.get('success'):
                        result[et] = (resp.get('data') or {}).get('ids', [])
            if entity_type in ('', 'report'):
                resp = report_config_service.stub.ListFavoriteReportIds(
                    report_pb.ListFavoriteReportIdsRequest())
                if resp.success:
                    result['report'] = (_loads(resp.data, {}) or {}).get('ids', [])
            return {'data': result if not entity_type else {entity_type: result[entity_type]}}
        except Exception as e:
            logger.error(f"查询收藏列表失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'查询收藏列表失败: {e}'}

    # ------------------------------------------------------------------
    # 回收站
    # ------------------------------------------------------------------

    @staticmethod
    def trash_list(entity_type: str, page: int = 1, per_page: int = 20, search=None):
        """回收站列表（已删项 + 删除人/删除时间）。"""
        entity_type = (entity_type or '').lower()
        try:
            if entity_type == 'task':
                resp = task_config_service.list_deleted_tasks(page, per_page, search)
            elif entity_type == 'testcase':
                resp = testcase_config_service.list_deleted_testcases(page, per_page, search)
            elif entity_type == 'report':
                resp = _report_resp(report_config_service.stub.ListDeletedReports(
                    report_pb.ListDeletedReportsRequest(
                        page=int(page), per_page=int(per_page), search=search or '')))
            else:
                return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
            if not resp.get('success'):
                return {'code': resp.get('code', 500), 'message': resp.get('message', '查询回收站失败')}
            return {'data': resp.get('data')}
        except Exception as e:
            logger.error(f"查询回收站失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'查询回收站失败: {e}'}

    @staticmethod
    def restore(entity_type: str, ids: list):
        """恢复（单个+批量统一入口）。"""
        entity_type = (entity_type or '').lower()
        if not ids:
            return {'code': 400, 'message': '缺少 ids'}
        try:
            if entity_type == 'task':
                resp = task_config_service.restore_tasks(ids)
            elif entity_type == 'testcase':
                resp = testcase_config_service.restore_testcases(ids)
            elif entity_type == 'report':
                resp = _report_resp(report_config_service.stub.RestoreReports(
                    report_pb.RestoreReportsRequest(report_ids=[int(i) for i in ids])))
            else:
                return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
            if not resp.get('success'):
                return {'code': resp.get('code', 500), 'message': resp.get('message', '恢复失败')}
            return {'data': resp.get('data')}
        except ValueError:
            return {'code': 400, 'message': 'ID 格式错误'}
        except Exception as e:
            logger.error(f"恢复失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'恢复失败: {e}'}

    @staticmethod
    def purge(entity_type: str, ids: list):
        """彻底删除（物理删除；权限 admin/owner 由服务端按 metadata 校验）。"""
        entity_type = (entity_type or '').lower()
        if not ids:
            return {'code': 400, 'message': '缺少 ids'}
        try:
            if entity_type == 'task':
                resp = task_config_service.purge_tasks(ids)
            elif entity_type == 'testcase':
                resp = testcase_config_service.purge_testcases(ids)
            elif entity_type == 'report':
                resp = _report_resp(report_config_service.stub.PurgeReports(
                    report_pb.PurgeReportsRequest(report_ids=[int(i) for i in ids])))
            else:
                return {'code': 400, 'message': f'非法实体类型: {entity_type}'}
            if not resp.get('success'):
                return {'code': resp.get('code', 500), 'message': resp.get('message', '彻底删除失败')}
            return {'data': resp.get('data')}
        except ValueError:
            return {'code': 400, 'message': 'ID 格式错误'}
        except Exception as e:
            logger.error(f"彻底删除失败: {e}", exc_info=True)
            return {'code': 500, 'message': f'彻底删除失败: {e}'}
