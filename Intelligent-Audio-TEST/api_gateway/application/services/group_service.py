"""测试用例分组服务

读写操作均已改用 gRPC（list/create/update/delete_testcase_group）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import TestCaseConfigAclRepositoryImpl
from api_gateway.schemas.group import (
    GroupCreateRequest,
    GroupDeleteQuery,
    GroupItem,
    GroupListData,
    GroupListQuery,
    GroupMoveCasesRequest,
    GroupSummaryItem,
    GroupSummaryListData,
    GroupUpdateRequest,
)
import uuid


# INT-1470：分组列表默认页大小。原默认 100 —— 每项约 214B（含 description），
# 单次响应 21.4KB；默认页取 40 后约 8.9KB，且分页信封（total/page/pages）不变。
# 现有前端均显式传 per_page（React 200 / 新 Vue 100~1000），不受默认值影响。
_DEFAULT_PAGE_SIZE = 40


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


_testcase_acl = TestCaseConfigAclRepositoryImpl()


def _group_data(group_id):
    """预取分组详情 data（含 visibility/created_by_user_id），供写路径审计旁路判定。"""
    try:
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        return task_data_service.get_testcase_group_by_id(group_id) or {}
    except Exception:
        return {}


def _delete_message(result):
    """删除分组回执（INT-2243）：级联实删/跳过条数与实际一致，跳过时明示原因。"""
    deleted = result.get('deleted_case_count')
    skipped = result.get('skipped_case_count')
    if not result.get('cascade') or (deleted is None and skipped is None):
        return "分组已删除"
    message = f"分组已删除，级联删除用例 {deleted or 0} 条"
    if skipped:
        message += f"，{skipped} 条非本人私有用例未删除"
    return message


class GroupService:
    """测试用例分组 CRUD 服务"""

    @staticmethod
    def get_all():
        query = _parse_query_params(GroupListQuery)
        # 非法分页参数（<=0）按默认口径处理：分页下推要求 page/per_page 为正，
        # 否则 task_service 会当作「不分页」返回全量，与响应信封不一致
        page = query.page if query.page and query.page > 0 else 1
        per_page = (query.per_page if query.per_page and query.per_page > 0
                    else _DEFAULT_PAGE_SIZE)
        summary_only = (query.fields or '').strip().lower() == 'summary'
        algorithm_type = query.algorithm_type
        keyword = query.keyword
        dimension_id = query.dimension_id
        # INT-528：收藏 / 回收站口径（与 TestCaseListQuery 一致，双视图贯通）
        favorite = query.favorite or False
        only_deleted = query.only_deleted or False
        # 分组列表按"分组下匹配用例数"筛选（V9.7.10 对齐，INT-146）：
        # 用例级筛选（keyword/dimension）需先用例聚合确定分组集合，不能下推分页
        has_case_filters = bool(keyword or dimension_id)
        # INT-1470：默认口径与 algorithm_type 筛选口径可直接下推分页——分组集合
        # 由 SQL 直接确定，列表 RPC 只返回当前页、计数只算当前页；收藏/回收站仍
        # 需先按用例过滤分组，保持原路径（全量列表 + 内存切片 + 聚合 RPC）
        pushdown = not has_case_filters and not favorite and not only_deleted

        # 通过 gRPC 查询 TestCaseGroup 列表（替代直连 PO）
        from api_gateway.infrastructure.grpc_proxies import task_data_service

        case_counts = {}
        if pushdown:
            try:
                data = task_data_service.list_testcase_groups(
                    algorithm_type=algorithm_type, page=page, per_page=per_page)
            except Exception:
                data = {}
            page_groups = data.get('items') or []
            total = int(data.get('total') if data.get('total') is not None
                        else len(page_groups))
            # 计数随列表一次带回（task_service ListTestCaseGroups，口径同
            # GetTestCaseStats group_by=group_id），不再发第二次聚合 RPC
            case_counts = {str(g.get('id')): int(g.get('test_case_count') or 0)
                           for g in page_groups}
        else:
            try:
                data = task_data_service.list_testcase_groups(
                    algorithm_type=algorithm_type)
                all_groups = data.get('items') or []
            except Exception:
                all_groups = []

            if has_case_filters:
                # gRPC GetTestCaseStats 支持用例级筛选 + group_by='group_id'
                # INT-528：收藏/回收站口径随筛选项下推，回收站态 keyword 命中已删用例
                stats = task_data_service.get_testcase_stats(
                    algorithm_type=algorithm_type, group_by='group_id',
                    keyword=keyword, dimension_id=dimension_id,
                    favorite=favorite, deleted=only_deleted,
                )
                items = stats.get('items') or []
                case_counts = {item.get('key', ''): item.get('count', 0) for item in items}
                all_groups = [g for g in all_groups if str(g.get('id')) in case_counts]
                total = len(all_groups)
            else:
                total = len(all_groups)

            # 用例级筛选/收藏/回收站口径保持客户端分页（gRPC 侧不分页下推）
            start = (page - 1) * per_page
            page_groups = all_groups[start:start + per_page]

            if not has_case_filters and (favorite or only_deleted):
                # INT-528：收藏/回收站口径需用例级过滤，只能走聚合统计 RPC，
                # 且只保留当前页分组
                group_ids = [str(g.get('id')) for g in page_groups]
                if group_ids:
                    stats = task_data_service.get_testcase_stats(
                        group_by='group_id', favorite=favorite, deleted=only_deleted)
                    items = stats.get('items') or []
                    case_counts = {item.get('key', ''): item.get('count', 0)
                                   for item in items}
                    case_counts = {k: v for k, v in case_counts.items()
                                   if k in group_ids}

        pages = (total + per_page - 1) // per_page if per_page else 1

        if summary_only:
            # INT-1470：精简投影——仅 facet/组头行需要的 id/name/test_case_count
            summary_items = [
                GroupSummaryItem(
                    id=group.get('id'),
                    name=group.get('name'),
                    test_case_count=case_counts.get(str(group.get('id')), 0),
                )
                for group in page_groups
            ]
            return success_response(
                GroupSummaryListData(
                    items=summary_items,
                    total=total,
                    page=page,
                    per_page=per_page,
                    pages=pages,
                )
            )

        data = []
        for group in page_groups:
            data.append(
                GroupItem(
                    id=group.get('id'),
                    name=group.get('name'),
                    description=group.get('description') or '',
                    algorithm_type=group.get('algorithm_type') or '',
                    created_at='',
                    updated_at='',
                    test_case_count=case_counts.get(str(group.get('id')), 0),
                    # INT-423/466：资源可见性与归属人（read model 透出，此处透传）
                    visibility=group.get('visibility'),
                    created_by_user_id=group.get('created_by_user_id'),
                )
            )

        return success_response(
            GroupListData(
                items=data,
                total=total,
                page=page,
                per_page=per_page,
                pages=pages,
            )
        )

    @staticmethod
    def create():
        try:
            validated_data = GroupCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            from api_gateway.schemas.common import StringIdData

            existing = task_data_service.get_testcase_group_by_name(validated_data.name)
            if existing:
                return error_response(f"已存在名为 '{validated_data.name}' 的分组")

            group_id = validated_data.id or str(uuid.uuid4())
            new_group = task_data_service.create_testcase_group(
                name=validated_data.name,
                description=validated_data.description or '',
                algorithm_type=validated_data.algorithm_type or '',
                group_id=group_id,
                # INT-566：新建分组透传可见性（shared/private；None 服务端默认 shared）
                visibility=validated_data.visibility,
            )
            if not new_group or not new_group.get('id'):
                return error_response("创建分组失败：服务未确认创建结果")
            return success_response(StringIdData(id=new_group['id']), "分组创建成功", 0, 201)
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def update(group_id):
        """通过 gRPC 更新 TestCaseGroup"""
        try:
            validated_data = GroupUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        # INT-466：admin 修改私有分组落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(lambda: _group_data(group_id))

        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            from api_gateway.schemas.common import StringIdData

            updated = task_data_service.update_testcase_group(
                group_id=group_id,
                name=validated_data.name or '',
                description=validated_data.description or '',
                algorithm_type=validated_data.algorithm_type or '',
            )
            if not updated or not updated.get('id'):
                return error_response("更新分组失败：服务未确认更新结果")
            maybe_audit_private_write('group', group_id, 'update', pre_data)
            return success_response(StringIdData(id=updated['id']), "分组信息更新成功")
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def delete(group_id):
        """通过 gRPC 软删除 TestCaseGroup（守卫：分组下有未删除用例且不带级联时拒绝删除）"""
        query = _parse_query_params(GroupDeleteQuery)
        cascade = query.cascade

        from api_gateway.infrastructure.grpc_proxies import task_data_service
        # 删除前守卫：确认分组下无未删除用例。stats 查询失败必须拒绝删除（fail-closed），
        # 不得把「查询失败」静默降级为「无用例」绕过守卫（INT-468）。
        try:
            stats = task_data_service.get_testcase_stats(group_id=group_id, reraise=True)
            active_cases = stats.get('total', 0) if stats else 0
        except Exception as e:
            return error_response(f"删除分组失败：无法查询分组用例统计（{e}）")
        if active_cases > 0 and not cascade:
            return error_response("该分组下存在测试用例，无法删除")

        # INT-466：admin 删除私有分组落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(lambda: _group_data(group_id))

        try:
            from api_gateway.schemas.common import StringIdData
            result = task_data_service.delete_testcase_group(group_id, cascade=cascade)
            if not result or not result.get('id'):
                return error_response("删除分组失败：服务未确认删除结果")
            maybe_audit_private_write('group', group_id, 'delete', pre_data)
            return success_response(
                StringIdData(id=group_id), _delete_message(result))
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def move_cases():
        try:
            validated_data = GroupMoveCasesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        # 通过 gRPC 校验目标分组存在
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        try:
            target_group = task_data_service.get_testcase_group_by_id(validated_data.target_group_id)
            if not target_group:
                return error_response("目标分组不存在", 1, 404)
            target_group_name = target_group.get('name', validated_data.target_group_id)
        except Exception as e:
            return error_response(f"查询目标分组失败: {str(e)}")

        case_ids = validated_data.case_ids
        if not case_ids:
            return success_response(None, "没有需要移动的用例")

        try:
            # 通过 ACL 批量移动 TestCase 到目标分组
            result = _testcase_acl.batch_action({
                'action': 'move_to_group',
                'ids': case_ids,
                'target_group_id': validated_data.target_group_id,
            })
            if not result.get('success'):
                return error_response(result.get('message', '移动用例失败'))
            return success_response(None, f"成功移动 {len(case_ids)} 个用例到分组 '{target_group_name}'")
        except Exception as e:
            return error_response(str(e))
