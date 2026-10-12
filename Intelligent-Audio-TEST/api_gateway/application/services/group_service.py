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
    GroupUpdateRequest,
)
import uuid


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


_testcase_acl = TestCaseConfigAclRepositoryImpl()


class GroupService:
    """测试用例分组 CRUD 服务"""

    @staticmethod
    def get_all():
        query = _parse_query_params(GroupListQuery)
        page = query.page
        per_page = query.per_page if query.per_page is not None else 100
        algorithm_type = query.algorithm_type
        keyword = query.keyword
        test_type = query.type
        dimension_id = query.dimension_id
        # 分组列表按"分组下匹配用例数"筛选（V9.7.10 对齐，INT-146）：
        # 任一用例级筛选存在时，仅返回有匹配用例的分组，计数为匹配用例数
        has_case_filters = bool(algorithm_type or test_type or keyword or dimension_id)

        # 通过 gRPC 查询 TestCaseGroup 列表（替代直连 PO）
        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            data = task_data_service.list_testcase_groups(algorithm_type=algorithm_type)
            all_groups = data.get('items') or []
        except Exception:
            all_groups = []

        # 通过 gRPC 聚合统计 TestCase 按 group_id 分组计数（替代直连 PO）
        from api_gateway.infrastructure.grpc_proxies import task_data_service as _tds

        case_counts = {}
        if has_case_filters:
            # gRPC GetTestCaseStats 支持用例级筛选 + group_by='group_id'
            stats = _tds.get_testcase_stats(
                algorithm_type=algorithm_type, group_by='group_id',
                test_type=test_type, keyword=keyword, dimension_id=dimension_id,
            )
            items = stats.get('items') or []
            case_counts = {item.get('key', ''): item.get('count', 0) for item in items}
            all_groups = [g for g in all_groups if str(g.get('id')) in case_counts]

        total = len(all_groups)

        # 客户端分页（gRPC ListTestCaseGroups 不支持分页）
        start = (page - 1) * per_page
        end = start + per_page
        page_groups = all_groups[start:end]

        if not has_case_filters:
            group_ids = [str(g.get('id')) for g in page_groups]
            if group_ids:
                stats = _tds.get_testcase_stats(group_by='group_id')
                items = stats.get('items') or []
                case_counts = {item.get('key', ''): item.get('count', 0) for item in items}
                # 仅保留当前页分组
                case_counts = {k: v for k, v in case_counts.items() if k in group_ids}

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
                )
            )

        return success_response(
            GroupListData(
                items=data,
                total=total,
                page=page,
                per_page=per_page,
                pages=(total + per_page - 1) // per_page if per_page else 1,
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
            )
            return success_response(StringIdData(id=new_group.get('id', group_id)), "分组创建成功", 0, 201)
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def update(group_id):
        """通过 gRPC 更新 TestCaseGroup"""
        try:
            validated_data = GroupUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            from api_gateway.schemas.common import StringIdData

            updated = task_data_service.update_testcase_group(
                group_id=group_id,
                name=validated_data.name or '',
                description=validated_data.description or '',
                algorithm_type=validated_data.algorithm_type or '',
            )
            return success_response(StringIdData(id=updated.get('id', group_id)), "分组信息更新成功")
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def delete(group_id):
        """通过 gRPC 软删除 TestCaseGroup"""
        query = _parse_query_params(GroupDeleteQuery)
        cascade = query.cascade

        from api_gateway.infrastructure.grpc_proxies import task_data_service
        try:
            stats = task_data_service.get_testcase_stats(group_id=group_id)
            active_cases = stats.get('total', 0) if stats else 0
        except Exception:
            active_cases = 0
        if active_cases > 0 and not cascade:
            return error_response("该分组下存在测试用例，无法删除")

        try:
            from api_gateway.schemas.common import StringIdData
            result = task_data_service.delete_testcase_group(group_id, cascade=cascade)
            if not result or not result.get('id'):
                return error_response("删除分组失败：服务未确认删除结果")
            return success_response(StringIdData(id=group_id), "分组已删除")
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
