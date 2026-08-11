# -*- coding: utf-8 -*-
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class TagConfigServiceServicer(task_grpc.TagConfigServiceServicer):
    """标签及标签分类 CRUD servicer，委托给 TaskCommandHandler / TaskQueryHandler。

    写操作（create/update/delete/batch_update_category）通过 CQRS Command
    委托 task_command_handler；读操作通过 CQRS Query 委托 task_query_handler。
    handler 内部过渡期仍委托 tag_crud_service。
    """

    def __init__(self):
        self._cmd = None
        self._qry = None

    @property
    def cmd(self):
        """延迟加载命令处理器（CQRS 写侧入口）。"""
        if self._cmd is None:
            from task_service.application.handlers import task_command_handler
            self._cmd = task_command_handler
        return self._cmd

    @property
    def qry(self):
        """延迟加载查询处理器（CQRS 读侧入口）。"""
        if self._qry is None:
            from task_service.application.handlers import task_query_handler
            self._qry = task_query_handler
        return self._qry

    @staticmethod
    def _resp(result):
        """统一包装返回结果为 TagConfigResponse"""
        return task_pb.TagConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- TagCategory 写操作 ----

    def CreateTagCategory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import CreateTagCategoryCommand
            return self._resp(self.cmd.handle_create_tag_category(CreateTagCategoryCommand(data=data)))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def UpdateTagCategory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTagCategoryCommand
            return self._resp(self.cmd.handle_update_tag_category(
                UpdateTagCategoryCommand(category_id=request.category_id, data=data)
            ))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def DeleteTagCategory(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import DeleteTagCategoryCommand
            return self._resp(self.cmd.handle_delete_tag_category(
                DeleteTagCategoryCommand(category_id=request.category_id)
            ))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    # ---- Tag 写操作 ----

    def CreateTag(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import CreateTagCommand
            return self._resp(self.cmd.handle_create_tag(CreateTagCommand(data=data)))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def UpdateTag(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTagCommand
            return self._resp(self.cmd.handle_update_tag(
                UpdateTagCommand(tag_id=request.tag_id, data=data)
            ))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def DeleteTag(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import DeleteTagCommand
            return self._resp(self.cmd.handle_delete_tag(DeleteTagCommand(tag_id=request.tag_id)))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def BatchUpdateTagCategory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import BatchUpdateTagCategoryCommand
            return self._resp(self.cmd.handle_batch_update_tag_category(
                BatchUpdateTagCategoryCommand(data=data)
            ))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListTagCategories(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListTagCategoriesQuery
            query = ListTagCategoriesQuery(
                page=request.page,
                per_page=request.per_page,
                keyword=request.keyword or None,
            )
            return self._resp(self.qry.handle_list_tag_categories(query))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def GetTagCategory(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTagCategoryQuery
            return self._resp(self.qry.handle_get_tag_category(
                GetTagCategoryQuery(category_id=request.category_id)
            ))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def ListTags(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListTagsQuery
            query = ListTagsQuery(
                page=request.page,
                per_page=request.per_page,
                category_id=request.category_id or None,
                keyword=request.keyword or None,
            )
            return self._resp(self.qry.handle_list_tags(query))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def ListTagNames(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListTagNamesQuery
            query = ListTagNamesQuery(
                page=request.page,
                per_page=request.per_page,
                keyword=request.keyword or None,
            )
            return self._resp(self.qry.handle_list_tag_names(query))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def GetTag(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTagQuery
            return self._resp(self.qry.handle_get_tag(GetTagQuery(tag_id=request.tag_id)))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")

    def GetTagsByCategory(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTagsByCategoryQuery
            return self._resp(self.qry.handle_get_tags_by_category(GetTagsByCategoryQuery()))
        except Exception as e:
            return task_pb.TagConfigResponse(success=False, message=str(e), data="")
