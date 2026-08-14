# -*- coding: utf-8 -*-
"""task_service.TagConfigService 防腐层仓储 — gRPC ACL 适配层。

封装 audio_service 对 task_service.TagConfigService 的跨域 gRPC 调用，
替代 audio_service/infrastructure/persistence/audio_repository.py 中
直接 import shared.clients.grpc_clients.get_tag_config_service_stub。

- 读操作通过 gRPC 完成，返回 dict / list，不返回 ORM 对象。
- 采用具体类 + 模块级单例。
"""
import logging
from typing import Dict, List

from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


class _TagProxy:
    """标签轻量代理对象（供 add_audio_tag 使用 tag.id / tag.name）"""

    def __init__(self, id, name):
        self.id = id
        self.name = name


class TagAclRepository:
    """task_service.TagConfigService 防腐层仓储

    封装 gRPC 调用，提供 audio_service persistence 层可用的返回值。
    所有方法返回纯 dict / list，不返回 ORM 对象。
    """

    def _list_tags_page(self, page: int = 1, per_page: int = 500, keyword: str = ''):
        """查询单页标签列表，返回 (items, total_pages) 或 ([], 0)。"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_tag_config_service_stub()
            resp = stub.ListTags(task_pb.ListTagsRequest(
                page=page, per_page=per_page, keyword=keyword,
            ))
            if not resp.success:
                return [], 0
            data = _loads(resp.data, {})
            if not isinstance(data, dict):
                return [], 0
            items = data.get('items', []) or []
            return items, data.get('pages', 1)
        except Exception:
            return [], 0

    def get_tag_name_to_id_map(self, tag_names: List[str]) -> Dict[str, int]:
        """通过 gRPC 查询标签名 → ID 映射（Tag 属于 task_service 域）"""
        if not tag_names:
            return {}
        result = {}
        try:
            target_names = set(tag_names)
            page = 1
            per_page = 500
            while target_names:
                items, total_pages = self._list_tags_page(page, per_page)
                if not items:
                    break
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid and name in target_names:
                        result[name] = tid
                        target_names.discard(name)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            logger.debug("通过 gRPC 查询标签名→ID映射失败: tag_names=%s", tag_names, exc_info=True)
        return result

    def get_all_tag_name_to_id_map(self) -> Dict[str, int]:
        """通过 gRPC 查询所有标签名 → ID 映射"""
        result = {}
        try:
            page = 1
            per_page = 500
            while True:
                items, total_pages = self._list_tags_page(page, per_page)
                if not items:
                    break
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid:
                        result[name] = tid
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            logger.debug("通过 gRPC 查询所有标签名→ID映射失败", exc_info=True)
        return result

    def get_all_tag_names(self) -> List[str]:
        """查询所有不重复的标签名"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_tag_config_service_stub()
            resp = stub.ListTagNames(task_pb.ListTagNamesRequest(
                page=1, per_page=500,
            ))
            if not resp.success:
                return []
            data = _loads(resp.data, {})
            if isinstance(data, dict):
                return data.get('items', []) or []
            return []
        except Exception:
            return []

    def get_or_create_tag(self, tag_name: str):
        """查找或创建标签，返回含 id 和 name 的对象（供 add_audio_tag 使用 tag.id）"""
        try:
            page = 1
            per_page = 500
            while True:
                items, total_pages = self._list_tags_page(page, per_page, keyword=tag_name)
                if not items:
                    break
                for item in items:
                    if item.get('name') == tag_name:
                        return _TagProxy(id=item.get('id'), name=item.get('name'))
                if page >= total_pages or not items:
                    break
                page += 1
            # 创建
            from shared.clients.grpc_clients import get_tag_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            stub = get_tag_config_service_stub()
            create_resp = stub.CreateTag(task_pb.CreateTagRequest(
                data=_dumps({'name': tag_name}),
            ))
            if create_resp.success:
                data = _loads(create_resp.data, {})
                if isinstance(data, dict) and data.get('id'):
                    return _TagProxy(id=data.get('id'), name=data.get('name', tag_name))
        except Exception:
            logger.debug("通过 gRPC 查找或创建标签失败: tag_name=%s", tag_name, exc_info=True)
        return _TagProxy(id=None, name=tag_name)

    def get_tag_id_to_name_map(self, tag_ids: List[int]) -> Dict[int, str]:
        """通过 gRPC 查询标签 ID → 名映射（Tag 属于 task_service 域）"""
        if not tag_ids:
            return {}
        result = {}
        try:
            remaining = set(tag_ids)
            page = 1
            per_page = 500
            while remaining:
                items, total_pages = self._list_tags_page(page, per_page)
                if not items:
                    break
                for item in items:
                    tid = item.get('id')
                    name = item.get('name')
                    if tid and name and tid in remaining:
                        result[tid] = name
                        remaining.discard(tid)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            logger.debug("通过 gRPC 查询标签ID→名映射失败: tag_ids=%s", tag_ids, exc_info=True)
        return result

    def get_tag_config_stub(self):
        """获取 TagConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_tag_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_tag_config_service_stub
        return get_tag_config_service_stub()


# 模块级单例
tag_acl_repository = TagAclRepository()
