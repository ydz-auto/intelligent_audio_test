"""评估维度写操作 Service（CQRS Command Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 evaluation_service。
保留 Pydantic schema 校验与文件导入/导出所需的本地 I/O 逻辑。
"""
import json
import io
import pandas as pd
from datetime import datetime

from shared.utils.status_constants import TaskStatus
from api_gateway.infrastructure.request_adapter import request
from fastapi.responses import FileResponse
from api_gateway.utils.response import success_response, error_response
# 跨服务调用：通过 ACL 仓储调用各微服务
from api_gateway.infrastructure.acl import (
    EvaluationConfigAclRepositoryImpl,
    ReevaluationAclRepositoryImpl,
    TaskConfigAclRepositoryImpl,
)
from api_gateway.schemas.common import IdData
from api_gateway.schemas.evaluation import (
    CategoryCreateInput,
    CategoryUpdateInput,
    DimensionCreateInput,
    DimensionUpdateInput,
    DimensionImportResult,
    BatchActionInput,
    FileImportInput,
    TaskReevaluateInput,
    TaskReevaluateResult,
    ScoreCalculateInput,
    ScoreData,
    DimensionExportQuery,
)


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


_evaluation_acl = EvaluationConfigAclRepositoryImpl()
_task_acl = TaskConfigAclRepositoryImpl()
_reevaluation_acl = ReevaluationAclRepositoryImpl()


class EvaluationCommandService:
    """评估维度写操作 Service（CQRS Command Side）。"""

    # --- 分类管理 (Category Management) ---

    @staticmethod
    def create_category():
        try:
            req = CategoryCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _evaluation_acl.create_category(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分类创建成功'), http_code=201)
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_category(cat_id):
        try:
            req = CategoryUpdateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _evaluation_acl.update_category(cat_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分类更新成功'))
        code = result.get('code', 400)
        if code == 404:
            return error_response("未找到分类", 404)
        return error_response(result.get('message', '操作失败'), code)

    @staticmethod
    def delete_category(cat_id):
        result = _evaluation_acl.delete_category(cat_id)

        if result.get('success'):
            return success_response(None, result.get('message', '分类已删除'))
        code = result.get('code', 400)
        if code == 404:
            return error_response("未找到分类", 404)
        return error_response(result.get('message', '操作失败'), code)

    # --- 维度管理 (Dimension Management) ---

    # 创建新的评分维度
    @staticmethod
    def create():
        data = request.get_json()
        try:
            validated = DimensionCreateInput.model_validate(data)
            data = validated.model_dump(exclude_none=True, by_alias=False)
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        # 处理评分规则（将字符串解析为字典并做结构校验）
        rule = data.get('rule')
        if rule and isinstance(rule, str):
            try:
                rule = json.loads(rule)
                data['rule'] = rule
            except json.JSONDecodeError:
                return error_response("规则格式错误: 无效的 JSON 字符串")
        if rule and isinstance(rule, dict):
            is_valid, msg = EvaluationCommandService.validate_rule_structure(rule)
            if not is_valid:
                return error_response(f"规则格式错误: {msg}")

        result = _evaluation_acl.create_dimension(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '评分维度创建成功'), http_code=201)
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # 更新评分维度信息
    @staticmethod
    def update(dim_id):
        data = request.get_json()
        try:
            validated = DimensionUpdateInput.model_validate(data)
            data = validated.model_dump(exclude_none=True, by_alias=False)
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        # 处理评分规则（将字符串解析为字典并做结构校验）
        if 'rule' in data:
            rule = data['rule']
            if isinstance(rule, str):
                try:
                    rule = json.loads(rule)
                    data['rule'] = rule
                except json.JSONDecodeError:
                    return error_response("规则格式错误: 无效的 JSON 字符串")
            if rule and isinstance(rule, dict):
                is_valid, msg = EvaluationCommandService.validate_rule_structure(rule)
                if not is_valid:
                    return error_response(f"规则格式错误: {msg}")

        result = _evaluation_acl.update_dimension(dim_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '评分维度更新成功'))
        code = result.get('code', 400)
        if code == 404:
            return error_response("未找到评分维度", 404)
        return error_response(result.get('message', '操作失败'), code)

    @staticmethod
    def validate_rule_structure(rule):
        """验证评分规则的 JSON 结构"""
        if not isinstance(rule, dict):
            return False, "规则必须是一个 JSON 对象"

        if 'rules' not in rule:
            return False, "规则对象必须包含 'rules' 字段"

        rules_list = rule['rules']
        if not isinstance(rules_list, list):
            return False, "'rules' 字段必须是一个列表"

        valid_conditions = ['>', '>=', '<', '<=', '==', '!=']
        for idx, r in enumerate(rules_list):
            if not isinstance(r, dict):
                return False, f"第 {idx + 1} 条规则必须是一个对象"

            if 'condition' not in r or 'value' not in r or 'score' not in r:
                return False, f"第 {idx + 1} 条规则缺少必要字段 (condition, value, score)"

            if r['condition'] not in valid_conditions:
                return False, f"第 {idx + 1} 条规则的条件无效: {r['condition']}"

            if not isinstance(r['value'], (int, float)):
                return False, f"第 {idx + 1} 条规则的阈值必须是数字"

            if not isinstance(r['score'], (int, float)):
                return False, f"第 {idx + 1} 条规则的得分必须是数字"

        return True, "验证通过"

    # 计算分值（根据维度规则对输入值评分）
    @staticmethod
    def calculate_score(dim_id):
        try:
            req = ScoreCalculateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _evaluation_acl.calculate_score(dim_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分值计算完成'))
        code = result.get('code', 400)
        if code == 404:
            return error_response("维度不存在", 404)
        return error_response(result.get('message', '操作失败'), code)

    # 删除评分维度 (逻辑删除)
    @staticmethod
    def delete(dim_id):
        result = _evaluation_acl.delete_dimension(dim_id)

        if result.get('success'):
            return success_response(None, result.get('message', '评分维度已删除'))
        code = result.get('code', 400)
        if code == 404:
            return error_response("未找到评分维度", 404)
        return error_response(result.get('message', '操作失败'), code)

    # 批量操作
    @staticmethod
    def batch_action():
        try:
            req = BatchActionInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data = req.model_dump(by_alias=False)
        result = _evaluation_acl.batch_action(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量操作执行成功'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # 导出到文件
    @staticmethod
    def export_to_file():
        query = _parse_query_params(DimensionExportQuery)
        format_type = query.format.lower()
        ids = query.ids

        # 通过 gRPC 代理获取维度数据，避免直接访问 DB
        result = _evaluation_acl.list_dimensions()
        if not result.get('success'):
            return error_response(result.get('message', '获取维度列表失败'))

        raw = result.get('data') or {}
        dimensions = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])

        if ids:
            id_list = [int(i) for i in ids.split(',')]
            dimensions = [d for d in dimensions if d.get('id') in id_list]

        data = []
        for d in dimensions:
            rule = d.get('rule')
            api_settings = d.get('api_settings') or d.get('apiSettings')
            if format_type == 'excel':
                data.append({
                    "名称": d.get('name'),
                    "描述": d.get('description'),
                    "分类ID": d.get('category_id', d.get('categoryId')),
                    "类型": d.get('type'),
                    "Master入口URL": d.get('api_url', d.get('apiUrl')),
                    "结果类型": d.get('result_type', d.get('resultType')),
                    "权重": d.get('weight'),
                    "分数单位": d.get('score_unit', d.get('scoreUnit')),
                    "规则": json.dumps(rule, ensure_ascii=False) if rule is not None else '',
                    "API配置": json.dumps(api_settings, ensure_ascii=False) if api_settings is not None else '',
                    "状态": "启用" if d.get('status') else "禁用"
                })
            else:
                data.append({
                    "name": d.get('name'),
                    "description": d.get('description'),
                    "category_id": d.get('category_id', d.get('categoryId')),
                    "type": d.get('type'),
                    "api_url": d.get('api_url', d.get('apiUrl')),
                    "result_type": d.get('result_type', d.get('resultType')),
                    "weight": d.get('weight'),
                    "score_unit": d.get('score_unit', d.get('scoreUnit')),
                    "rule": rule,
                    "api_settings": api_settings,
                    "status": d.get('status')
                })

        if format_type == 'excel':
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='评估维度')
            output.seek(0)
            return FileResponse(
                output,
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={"Content-Disposition": f"attachment; filename=evaluation_dimensions_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"}
            )
        else:
            # 默认导出 JSON
            return success_response(data)

    # 从文件导入
    @staticmethod
    def import_from_file():
        if 'file' not in request.files:
            return error_response("未上传文件")

        file = request.files['file']

        form_data = {}
        for key in request.form:
            form_data[key] = request.form.get(key)

        try:
            req = FileImportInput.model_validate(form_data)
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        update_existing = req.update_existing

        try:
            if file.filename.endswith('.xlsx') or file.filename.endswith('.xls'):
                df = pd.read_excel(file)
            elif file.filename.endswith('.json'):
                df = pd.read_json(file)
            else:
                return error_response("不支持的文件格式，请使用 Excel 或 JSON")

            import_count = 0
            update_count = 0

            for _, row in df.iterrows():
                name = row.get('名称') or row.get('name')
                if not name:
                    continue

                rule_str = row.get('规则') or row.get('rule', '{}')
                if isinstance(rule_str, str):
                    rule = json.loads(rule_str)
                else:
                    rule = rule_str

                api_settings_str = row.get('API配置') or row.get('api_settings') or row.get('api_settings', '{}')
                if isinstance(api_settings_str, str):
                    api_settings = json.loads(api_settings_str)
                else:
                    api_settings = api_settings_str

                api_url_value = row.get('API链接') or row.get('api_url') or row.get('api_url')
                api_endpoints = [{'url': api_url_value}] if api_url_value else []

                # 通过代理查找现有维度
                existing_dim_id = None
                search_result = _evaluation_acl.list_dimensions(search=name, page=1, per_page=1)
                if search_result.get('success'):
                    raw = search_result.get('data') or {}
                    items = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
                    for item in items:
                        if item.get('name') == name:
                            existing_dim_id = item.get('id')
                            break

                if existing_dim_id and update_existing:
                    data = {
                        "name": name,
                        "description": row.get('描述') or row.get('description'),
                        "category_id": int(row.get('分类ID') or row.get('category_id') or row.get('category_id', 1)),
                        "type": row.get('类型') or row.get('type', '性能指标'),
                        "api_endpoints": api_endpoints,
                        "result_type": int(row.get('结果类型') or row.get('result_type') or row.get('result_type', 1)),
                        "score_unit": row.get('分数单位') or row.get('score_unit') or row.get('scoreUnit'),
                        "rule": rule,
                        "api_settings": api_settings,
                    }
                    data = {k: v for k, v in data.items() if v is not None}
                    update_result = _evaluation_acl.update_dimension(existing_dim_id, data)
                    if update_result.get('success'):
                        update_count += 1
                elif not existing_dim_id:
                    data = {
                        "name": name,
                        "description": row.get('描述') or row.get('description'),
                        "category_id": int(row.get('分类ID') or row.get('category_id') or row.get('category_id', 1)),
                        "type": row.get('类型') or row.get('type', '性能指标'),
                        "api_endpoints": api_endpoints,
                        "result_type": int(row.get('结果类型') or row.get('result_type') or row.get('result_type', 1)),
                        "score_unit": row.get('分数单位') or row.get('score_unit') or row.get('scoreUnit'),
                        "rule": rule,
                        "api_settings": api_settings,
                        "status": True
                    }
                    data = {k: v for k, v in data.items() if v is not None}
                    create_result = _evaluation_acl.create_dimension(data)
                    if create_result.get('success'):
                        import_count += 1

            return success_response(
                DimensionImportResult(imported=import_count, updated=update_count),
                f"导入成功: 新增 {import_count} 条, 更新 {update_count} 条",
            )

        except Exception as e:
            return error_response(f"导入失败: {str(e)}")

    @staticmethod
    def reevaluate_task_results():
        try:
            req = TaskReevaluateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        task_id = req.task_id
        reevaluate_type = req.reevaluate_type
        reextract_device_output = req.reextract_device_output

        # 通过 task_config_service 获取任务信息（替代 get_db_session().get(Task, task_id)）
        task_result = _task_acl.get_task_detail(task_id)
        if not task_result.get('success'):
            return error_response("未找到任务", 404)

        task_data = task_result.get('data') or {}
        task_status = task_data.get('status')

        if task_status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.PAUSED, TaskStatus.SKIPPED]:
            return error_response("只有已完成/失败/停止/暂停/跳过的任务才能重新评估")

        # 跨服务调用：通过 ACL 仓储重新评估
        reeval_result = _reevaluation_acl.submit(
            task_id=task_id,
            reextract_device_output=reextract_device_output,
            reevaluate_type=reevaluate_type
        )
        success = reeval_result.success
        message = reeval_result.message

        if success:
            # 实际的重新评估用例数由执行服务处理，网关侧无法直接查询 TestResult
            queued_count = 0
            return success_response(
                TaskReevaluateResult(
                    total_cases=queued_count,
                    queued_cases=queued_count,
                    reextracted_cases=0,
                    message=message
                ),
                message
            )
        else:
            return error_response(message)
