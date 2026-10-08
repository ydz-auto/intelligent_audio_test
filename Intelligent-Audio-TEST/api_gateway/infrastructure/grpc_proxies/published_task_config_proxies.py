# -*- coding: utf-8 -*-
"""已发布任务配置代理（Published Task Config Proxy）

封装 task_service.PublishedTaskConfigService 的 gRPC 调用，作为 api_gateway 的
ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}
"""
import json

from shared.clients.grpc_clients import get_published_task_config_service_stub

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _PublishedTaskConfigProxy:
    """已发布任务配置 CRUD 代理：把方法调用转发到 gRPC PublishedTaskConfigService"""

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
            'code': resp.success and 0 or (resp.message and 400 or 500),
        }

    @property
    def stub(self):
        """获取 PublishedTaskConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_published_task_config_service_stub()

    # ---- 写操作 ----

    def publish(self, data):
        """发布：日常任务 → 已发布任务 v1"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.PublishTask(task_pb.PublishTaskRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'发布已发布任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='发布已发布任务失败',
        )

    def execute(self, published_task_id):
        """执行：按快照创建新的日常任务"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.ExecutePublishedTask(task_pb.ExecutePublishedTaskRequest(
                published_task_id=int(published_task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'执行已发布任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='执行已发布任务失败',
        )

    def create_version(self, published_task_id, data):
        """创建新版本：不可变版本 vN → vN+1"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.CreatePublishedTaskVersion(task_pb.CreatePublishedTaskVersionRequest(
                published_task_id=int(published_task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建已发布任务新版本失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建已发布任务新版本失败',
        )

    def archive(self, published_task_id):
        """归档（幂等）"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.ArchivePublishedTask(task_pb.ArchivePublishedTaskRequest(
                published_task_id=int(published_task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'归档已发布任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='归档已发布任务失败',
        )

    def rename(self, published_task_id, data):
        """重命名（作用于整个版本链）"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.RenamePublishedTask(task_pb.RenamePublishedTaskRequest(
                published_task_id=int(published_task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重命名已发布任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='重命名已发布任务失败',
        )

    # ---- 读操作 ----

    def get_list(self, page=1, per_page=10, status='', keyword='',
                 task_type='', start_date='', end_date=''):
        """当前版本列表（分页 + 筛选）"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.ListPublishedTasks(task_pb.ListPublishedTasksRequest(
                page=int(page),
                per_page=int(per_page),
                status=status or '',
                keyword=keyword or '',
                type=task_type or '',
                start_date=start_date or '',
                end_date=end_date or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询已发布任务列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询已发布任务列表失败',
        )

    def get_detail(self, published_task_id):
        """详情（版本历史 + 来源摘要 + 执行历史）"""
        def _call():
            stub = get_published_task_config_service_stub()
            resp = stub.GetPublishedTaskDetail(task_pb.GetPublishedTaskDetailRequest(
                published_task_id=int(published_task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询已发布任务详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询已发布任务详情失败',
        )


# 已发布任务配置代理模块级单例
published_task_config_service = _PublishedTaskConfigProxy()
