"""测试用例分组服务

读写操作均已改用 gRPC（list/create/update/delete_testcase_group）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import TestCaseConfigAclRepositoryImpl
from api_gateway.schemas.group import GroupItem, GroupListData, GroupCreateRequest, GroupUpdateRequest, GroupMoveCasesRequest
import uuid

_testcase_acl = TestCaseConfigAclRepositoryImpl()


class GroupService:
    """测试用例分组 CRUD 服务"""

    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', None, type=int) or request.args.get('page_size', 100, type=int)
        algorithm_type = request.args.get('algorithm_type')
        test_type = request.args.get('type') or request.args.get('test_type')

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
        if algorithm_type or test_type:
            # gRPC GetTestCaseStats 支持 algorithm_type 过滤 + group_by='group_id'
            # test_type 过滤暂无对应 gRPC 参数，在客户端按 test_type 过滤（如需要）
            stats = _tds.get_testcase_stats(algorithm_type=algorithm_type, group_by='group_id')
            items = stats.get('items') or []
            case_counts = {item.get('key', ''): item.get('count', 0) for item in items}
            all_groups = [g for g in all_groups if str(g.get('id')) in case_counts]

        total = len(all_groups)

        # 客户端分页（gRPC ListTestCaseGroups 不支持分页）
        start = (page - 1) * per_page
        end = start + per_page
        page_groups = all_groups[start:end]

        if not algorithm_type and not test_type:
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
        cascade = request.args.get('cascade', 'false').lower() == 'true'

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
            task_data_service.delete_testcase_group(group_id, cascade=cascade)
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
