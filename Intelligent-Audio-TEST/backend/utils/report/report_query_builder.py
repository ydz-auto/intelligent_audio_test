from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Query
from backend.models.database import db
from backend.models.models import (
    Task, TaskCase, TestCase, Tag, TestResult, TestResultDimension,
    Dimension, Device, API, TaskDevice, TaskAPI, Audio
)
from backend.utils.common.query_utils import escape_like_pattern, sanitize_keyword

class ReportQueryBuilder:
    @staticmethod
    def build_test_case_query(
        task_id: int,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        include_untagged: bool = False
    ) -> tuple:
        """
        构建测试用例查询
        
        Returns:
            (test_cases, test_case_ids, task_cases)
        """
        task_cases = TaskCase.query.filter_by(task_id=task_id).all()
        test_case_ids = [tc.test_case_id for tc in task_cases]
        
        query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
        
        if category and category != 'all':
            query = query.filter(TestCase.group.has(name=category))
        
        if categories and len(categories) > 0:
            from backend.models.models import TestCaseGroup
            query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
        
        if include_untagged:
            if tags and len(tags) > 0:
                query = query.filter(
                    db.or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any())
                )
            else:
                query = query.filter(~TestCase.tags.any())
        elif tags and len(tags) > 0:
            query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
        
        test_cases = query.all()
        return test_cases, test_case_ids, task_cases

    @staticmethod
    def build_merged_task_test_case_query(
        source_task_ids: List[int],
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        include_untagged: bool = False
    ) -> tuple:
        task_cases = TaskCase.query.filter(TaskCase.task_id.in_(source_task_ids)).all()
        test_case_ids = [tc.test_case_id for tc in task_cases]
        
        query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
        
        if category and category != 'all':
            query = query.filter(TestCase.group.has(name=category))
        
        if categories and len(categories) > 0:
            from backend.models.models import TestCaseGroup
            query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
        
        if include_untagged:
            if tags and len(tags) > 0:
                query = query.filter(
                    db.or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any())
                )
            else:
                query = query.filter(~TestCase.tags.any())
        elif tags and len(tags) > 0:
            query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
        
        test_cases = query.all()
        return test_cases, test_case_ids, task_cases

    @staticmethod
    def get_test_results_batch(
        test_case_ids: List[int],
        task_ids: Optional[List[int]] = None
    ) -> List[TestResult]:
        if not test_case_ids:
            return []
        
        query = TestResult.query.filter(TestResult.test_case_id.in_(test_case_ids))
        if task_ids:
            if len(task_ids) == 1:
                query = query.filter(TestResult.task_id == task_ids[0])
            else:
                query = query.filter(TestResult.task_id.in_(task_ids))
        
        return query.all()

    @staticmethod
    def get_dimension_results_batch(
        result_ids: List[int]
    ) -> Dict[int, List[Any]]:
        if not result_ids:
            return {}
        
        dim_results = db.session.query(
            TestResultDimension.test_result_id,
            TestResultDimension.dimension_id,
            TestResultDimension.dimension_value,
            TestResultDimension.api_raw_response,
            Dimension.name.label('dimension_name')
        ).join(Dimension, TestResultDimension.dimension_id == Dimension.id)\
         .filter(TestResultDimension.test_result_id.in_(result_ids)).all()
        
        dim_results_map: Dict[int, List[Any]] = {}
        for dr in dim_results:
            if dr.test_result_id not in dim_results_map:
                dim_results_map[dr.test_result_id] = []
            dim_results_map[dr.test_result_id].append(dr)
        
        return dim_results_map

    @staticmethod
    def get_task_devices_apis(task_id: int) -> tuple:
        task_devices = TaskDevice.query.filter_by(task_id=task_id).all()
        task_apis = TaskAPI.query.filter_by(task_id=task_id).all()
        
        device_ids = [td.device_id for td in task_devices]
        api_ids = [ta.api_id for ta in task_apis]
        
        devices = Device.query.filter(Device.id.in_(device_ids)).all() if device_ids else []
        apis = API.query.filter(API.id.in_(api_ids)).all() if api_ids else []
        
        return devices, apis, task_devices, task_apis

    @staticmethod
    def get_result_types_batch(
        task_id: int,
        device_ids: List[int],
        api_ids: List[int]
    ) -> tuple:
        device_result_types = {}
        api_result_types = {}
        
        if device_ids:
            device_results = TestResult.query.filter(
                TestResult.task_id == task_id,
                TestResult.device_id.in_(device_ids)
            ).all()
            
            for result in device_results:
                if result.device_id and result.result_data:
                    import json
                    try:
                        if isinstance(result.result_data, str) and result.result_data.strip():
                            result_data = json.loads(result.result_data)
                        elif isinstance(result.result_data, dict):
                            result_data = result.result_data
                        else:
                            result_data = {}
                        result_type = result_data.get('result_type', 'default') if isinstance(result_data, dict) else 'default'
                    except Exception:
                        result_type = 'default'
                    device_result_types[result.device_id] = result_type
        
        if api_ids:
            api_results = TestResult.query.filter(
                TestResult.task_id == task_id,
                TestResult.api_id.in_(api_ids)
            ).all()
            
            for result in api_results:
                if result.api_id and result.result_data:
                    import json
                    try:
                        if isinstance(result.result_data, str) and result.result_data.strip():
                            result_data = json.loads(result.result_data)
                        elif isinstance(result.result_data, dict):
                            result_data = result.result_data
                        else:
                            result_data = {}
                        result_type = result_data.get('result_type', 'default') if isinstance(result_data, dict) else 'default'
                    except Exception:
                        result_type = 'default'
                    api_result_types[result.api_id] = result_type
        
        return device_result_types, api_result_types

    @staticmethod
    def extract_case_categories_and_tags(test_cases: List[TestCase]) -> tuple:
        case_categories_list = []
        case_tags_list = []
        seen_categories = set()
        seen_tags = set()
        
        for test_case in test_cases:
            if test_case.group:
                cat_key = test_case.group.id
                if cat_key not in seen_categories:
                    seen_categories.add(cat_key)
                    case_categories_list.append({
                        "id": test_case.group.id,
                        "name": test_case.group.name or "未命名分组"
                    })
            
            tc_tags = getattr(test_case, 'tags', []) or []
            for tag in tc_tags:
                tag_key = tag.id
                if tag_key not in seen_tags:
                    seen_tags.add(tag_key)
                    case_tags_list.append({
                        "id": tag.id,
                        "name": tag.name or "未命名标签"
                    })
        
        if not case_categories_list:
            case_categories_list.append({"id": "default_group", "name": "未分类"})
        
        if not case_tags_list:
            case_tags_list.append({"id": "default_tag", "name": "无标签"})
        
        return case_categories_list, case_tags_list

    @staticmethod
    def safe_keyword_filter(query: Query, model_class, field_name: str, keyword: Optional[str]) -> Query:
        if not keyword:
            return query
        
        safe_keyword = sanitize_keyword(keyword)
        if not safe_keyword:
            return query
        
        escaped = escape_like_pattern(safe_keyword)
        field = getattr(model_class, field_name)
        return query.filter(field.like(f"%{escaped}%"))
