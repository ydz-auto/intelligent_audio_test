# -*- coding: utf-8 -*-
"""标签及标签分类 CRUD 代理（从 task_config_proxies.py 拆分，P4-4）。

Tag/TagCategory 的 gRPC 代理类及模块级单例，作为 api_gateway 的 ACL 层。
"""
import json

from shared.clients.grpc_clients import get_tag_config_service_stub

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _TagConfigProxy:
    """标签及标签分类 CRUD 代理：把方法调用转发到 gRPC TagConfigService

    所有方法返回 dict: {success, message, data, code}
    """

    def _resp(self, resp):
        """统一解析 TagConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    @property
    def stub(self):
        """获取 TagConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_tag_config_service_stub()

    # ---- TagCategory 写操作 ----

    def create_category(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.CreateTagCategory(task_pb.CreateTagCategoryRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建标签分类失败',
        )

    def update_category(self, category_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.UpdateTagCategory(task_pb.UpdateTagCategoryRequest(
                category_id=int(category_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新标签分类失败',
        )

    def delete_category(self, category_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.DeleteTagCategory(task_pb.DeleteTagCategoryRequest(
                category_id=int(category_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除标签分类失败',
        )

    # ---- Tag 写操作 ----

    def create_tag(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.CreateTag(task_pb.CreateTagRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建标签失败',
        )

    def update_tag(self, tag_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.UpdateTag(task_pb.UpdateTagRequest(
                tag_id=int(tag_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新标签失败',
        )

    def delete_tag(self, tag_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.DeleteTag(task_pb.DeleteTagRequest(
                tag_id=int(tag_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除标签失败',
        )

    def batch_update_category(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.BatchUpdateTagCategory(task_pb.BatchUpdateTagCategoryRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量更新标签分类失败',
        )

    # ---- 读操作 ----

    def list_categories(self, page=1, per_page=20, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTagCategories(task_pb.ListTagCategoriesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签分类列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签分类列表失败',
        )

    def get_category(self, category_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTagCategory(task_pb.GetTagCategoryRequest(
                category_id=int(category_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取标签分类失败',
        )

    def list_tags(self, page=1, per_page=20, category_id=None, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTags(task_pb.ListTagsRequest(
                page=int(page),
                per_page=int(per_page),
                category_id=int(category_id) if category_id else 0,
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签列表失败',
        )

    def list_tag_names(self, page=1, per_page=100, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTagNames(task_pb.ListTagNamesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签名称列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签名称列表失败',
        )

    def get_tag(self, tag_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTag(task_pb.GetTagRequest(
                tag_id=int(tag_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取标签失败',
        )

    def get_tags_by_category(self):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTagsByCategory(task_pb.GetTagsByCategoryRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取按分类分组的标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取按分类分组的标签失败',
        )


# 标签配置 CRUD 模块级单例
tag_config_service = _TagConfigProxy()
