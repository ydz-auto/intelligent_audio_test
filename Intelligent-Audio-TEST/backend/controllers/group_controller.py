from flask import request
from backend.models.models import TestCaseGroup, TestCase
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.schemas.group import GroupItem, GroupListData, GroupCreateRequest, GroupUpdateRequest, GroupMoveCasesRequest
from sqlalchemy import func
import uuid
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst

class GroupController:
    # 获取所有用例分组（支持分页）
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', None, type=int) or request.args.get('page_size', 100, type=int)
        algorithm_type = request.args.get('algorithm_type')
        keyword = request.args.get('keyword')
        test_type = request.args.get('type')
        dimension_id = request.args.get('dimension_id', type=int)

        query = TestCaseGroup.query

        # 构建用例计数过滤条件
        case_filters = [TestCase.deleted == False]
        if algorithm_type:
            case_filters.append(TestCase.algorithm_type == algorithm_type)
        if test_type and test_type in ['api', 'e2e']:
            case_filters.append(TestCase.test_type == test_type)
        if dimension_id:
            dim_str = str(dimension_id)
            case_filters.append(
                TestCase.config.cast(db.Text).like(f'"id": {dim_str}') |
                TestCase.config.cast(db.Text).like(f'"id":{dim_str}')
            )
        if keyword:
            case_filters.append(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        case_counts = {}
        if algorithm_type or test_type or keyword or dimension_id:
            # 按筛选条件统计各分组下匹配的用例数
            counts_query = db.session.query(
                TestCase.group_id,
                func.count(TestCase.id)
            ).filter(*case_filters).group_by(TestCase.group_id).all()

            case_counts = {str(gid): count for gid, count in counts_query}
            query = query.filter(TestCaseGroup.id.in_(list(case_counts.keys())))

        total = query.count()

        groups = query.order_by(TestCaseGroup.created_at.desc())
        groups = groups.paginate(page=page, per_page=per_page, error_out=False)

        if not (algorithm_type or test_type or keyword or dimension_id):
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

    # 创建新的用例分组
    @staticmethod
    def create():
        try:
            validated_data = GroupCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        existing = TestCaseGroup.query.filter_by(name=validated_data.name).first()
        if existing:
            return error_response(f"已存在名为 '{validated_data.name}' 的分组")

        try:
            from backend.schemas.common import StringIdData
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

    # 更新分组信息
    @staticmethod
    def update(group_id):
        group = db.session.get(TestCaseGroup, group_id)
        if not group:
            return error_response("未找到分组", 1, 404)

        try:
            validated_data = GroupUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        try:
            from backend.schemas.common import StringIdData
            if validated_data.name is not None and validated_data.name != group.name:
                existing = TestCaseGroup.query.filter(
                    TestCaseGroup.name == validated_data.name,
                    TestCaseGroup.id != group_id
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

    # 删除分组
    @staticmethod
    def delete(group_id):
        group = db.session.get(TestCaseGroup, group_id)
        if not group:
            return error_response("未找到分组", 1, 404)

        # 获取cascade参数，默认为False
        cascade = request.args.get('cascade', 'false').lower() == 'true'

        if group.test_cases:
            if not cascade:
                return error_response("该分组下存在测试用例，无法删除")
            
            try:
                # 级联删除分组下的所有测试用例
                from backend.models.models import TestCase
                for test_case in group.test_cases:
                    db.session.delete(test_case)
            except Exception as e:
                db.session.rollback()
                return error_response(f"删除分组下的测试用例失败: {str(e)}")

        try:
            db.session.delete(group)
            db.session.commit()
            return success_response(None, "分组已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量移动用例到指定分组
    @staticmethod
    def move_cases():
        try:
            validated_data = GroupMoveCasesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        target_group = db.session.get(TestCaseGroup, validated_data.target_group_id)
        if not target_group:
            return error_response("目标分组不存在", 1, 404)

        case_ids = validated_data.case_ids
        if not case_ids:
            return success_response(None, "没有需要移动的用例")

        try:
            from backend.models.models import TestCase
            TestCase.query.filter(TestCase.id.in_(case_ids)).update(
                {TestCase.group_id: validated_data.target_group_id},
                synchronize_session=False
            )
            db.session.commit()
            return success_response(None, f"成功移动 {len(case_ids)} 个用例到分组 '{target_group.name}'")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
