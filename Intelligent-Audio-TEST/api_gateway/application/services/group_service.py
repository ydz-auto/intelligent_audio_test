"""测试用例分组服务"""
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import TestCaseGroup, TestCase
from shared.models.database import db
from shared.utils.response import success_response, error_response
from api_gateway.schemas.group import GroupItem, GroupListData, GroupCreateRequest, GroupUpdateRequest, GroupMoveCasesRequest
from sqlalchemy import func
import uuid
from shared.utils.query_utils import now_cst


class GroupService:
    """测试用例分组 CRUD 服务"""

    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', None, type=int) or request.args.get('page_size', 100, type=int)
        algorithm_type = request.args.get('algorithm_type')
        test_type = request.args.get('type') or request.args.get('test_type')

        query = TestCaseGroup.query.filter(TestCaseGroup.deleted == False)

        case_filters = [TestCase.deleted == False]
        if algorithm_type:
            case_filters.append(TestCase.algorithm_type == algorithm_type)
        if test_type:
            case_filters.append(TestCase.test_type == test_type)

        case_counts = {}
        if algorithm_type or test_type:
            counts_query = db.session.query(
                TestCase.group_id,
                func.count(TestCase.id)
            ).filter(
                *case_filters
            ).group_by(TestCase.group_id).all()

            case_counts = {str(gid): count for gid, count in counts_query}
            query = query.filter(TestCaseGroup.id.in_(list(case_counts.keys())))

        total = query.count()

        groups = query.order_by(TestCaseGroup.created_at.desc())
        groups = groups.paginate(page=page, per_page=per_page, error_out=False)

        if not algorithm_type and not test_type:
            group_ids = [g.id for g in groups.items]
            if group_ids:
                counts_query = db.session.query(
                    TestCase.group_id,
                    func.count(TestCase.id)
                ).filter(
                    TestCase.group_id.in_(group_ids),
                    TestCase.deleted == False
                ).group_by(TestCase.group_id).all()

                case_counts = {str(gid): count for gid, count in counts_query}

        data = []
        for group in groups.items:
            data.append(
                GroupItem(
                    id=group.id,
                    name=group.name,
                    description=group.description,
                    algorithm_type=group.algorithm_type,
                    created_at=group.created_at.isoformat(),
                    updated_at=group.updated_at.isoformat(),
                    test_case_count=case_counts.get(str(group.id), 0),
                )
            )

        return success_response(
            GroupListData(
                items=data,
                total=total,
                page=page,
                per_page=per_page,
                pages=groups.pages,
            )
        )

    @staticmethod
    def create():
        try:
            validated_data = GroupCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        existing = TestCaseGroup.query.filter_by(name=validated_data.name, deleted=False).first()
        if existing:
            return error_response(f"已存在名为 '{validated_data.name}' 的分组")

        try:
            from api_gateway.schemas.common import StringIdData
            group_id = validated_data.id or str(uuid.uuid4())
            new_group = TestCaseGroup(
                id=group_id,
                name=validated_data.name,
                description=validated_data.description,
                algorithm_type=validated_data.algorithm_type
            )
            db.session.add(new_group)
            db.session.commit()
            return success_response(StringIdData(id=group_id), "分组创建成功", 0, 201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def update(group_id):
        group = TestCaseGroup.query.filter_by(id=group_id, deleted=False).first()
        if not group:
            return error_response("未找到分组", 1, 404)

        try:
            validated_data = GroupUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        try:
            from api_gateway.schemas.common import StringIdData
            if validated_data.name is not None and validated_data.name != group.name:
                existing = TestCaseGroup.query.filter(
                    TestCaseGroup.name == validated_data.name,
                    TestCaseGroup.id != group_id,
                    TestCaseGroup.deleted == False
                ).first()
                if existing:
                    return error_response(f"已存在名为 '{validated_data.name}' 的其他分组")
                group.name = validated_data.name

            if validated_data.description is not None:
                group.description = validated_data.description

            if validated_data.algorithm_type is not None:
                group.algorithm_type = validated_data.algorithm_type

            group.updated_at = now_cst()
            db.session.commit()
            return success_response(StringIdData(id=group_id), "分组信息更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def delete(group_id):
        group = TestCaseGroup.query.filter_by(id=group_id, deleted=False).first()
        if not group:
            return error_response("未找到分组", 1, 404)

        cascade = request.args.get('cascade', 'false').lower() == 'true'

        active_cases = TestCase.query.filter_by(group_id=group_id, deleted=False).count()
        if active_cases > 0 and not cascade:
            return error_response("该分组下存在测试用例，无法删除")

        try:
            now = now_cst()
            group.deleted = True
            group.deleted_at = now
            group.updated_at = now
            if cascade:
                TestCase.query.filter(
                    TestCase.group_id == group_id,
                    TestCase.deleted == False
                ).update({"deleted": True, "updated_at": now}, synchronize_session=False)
            db.session.commit()
            return success_response(None, "分组已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def move_cases():
        try:
            validated_data = GroupMoveCasesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        target_group = TestCaseGroup.query.filter_by(
            id=validated_data.target_group_id, deleted=False
        ).first()
        if not target_group:
            return error_response("目标分组不存在", 1, 404)

        case_ids = validated_data.case_ids
        if not case_ids:
            return success_response(None, "没有需要移动的用例")

        try:
            TestCase.query.filter(TestCase.id.in_(case_ids)).update(
                {TestCase.group_id: validated_data.target_group_id},
                synchronize_session=False
            )
            db.session.commit()
            return success_response(None, f"成功移动 {len(case_ids)} 个用例到分组 '{target_group.name}'")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
