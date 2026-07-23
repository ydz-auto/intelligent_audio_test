import requests
import time
import json
import pandas as pd
import io
import threading
from flask import request, send_file
from backend.models.models import Dimension, Category, Task, TaskCase, TestResult, TestResultDimension, Device
from backend.models.algorithm_models import EvaluationDimensionParam, AlgorithmDimensionRelation, ParamMapping
from backend.models.database import db
from sqlalchemy import and_
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_and_emit
from backend.schemas.common import IdData
from backend.schemas.evaluation import (
    CategoryCreateInput,
    CategoryItem,
    CategoryListData,
    CategoryUpdateInput,
    DimensionCreateInput,
    DimensionUpdateInput,
    DimensionHealthCheckData,
    DimensionImportResult,
    DimensionItem,
    DimensionListData,
    HealthCheckResultItem,
    ScoreCalculateInput,
    ScoreData,
    BatchActionInput,
    FileImportInput,
    TaskReevaluateInput,
    TaskReevaluateResult,
)
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst
import re


def _sync_body_template(api_settings, param_codes):
    """
    根据 param_codes 同步 api_settings 中的 body_template。
    - 新增参数：添加 "{{param_code}}" 占位符
    - 删除参数：移除对应的占位符
    - 静态字段（非 {{xxx}} 格式的值）保持不变
    """
    if not param_codes:
        return api_settings

    if api_settings is None:
        api_settings = {}
    if not isinstance(api_settings, dict):
        return api_settings

    body_template = api_settings.get('body_template')

    # 解析 body_template 为 dict
    if body_template is None:
        bt_dict = {}
    elif isinstance(body_template, str):
        try:
            bt_dict = json.loads(body_template) if body_template.strip() else {}
        except json.JSONDecodeError:
            bt_dict = {}
    elif isinstance(body_template, dict):
        bt_dict = dict(body_template)
    else:
        bt_dict = {}

    param_set = set(param_codes)

    # 移除已删除参数对应的占位符（值为 {{xxx}} 且 xxx 不在 param_set 中）
    placeholder_re = re.compile(r'^\{\{(\w+)\}\}$')
    keys_to_remove = []
    for key, value in bt_dict.items():
        if isinstance(value, str):
            match = placeholder_re.match(value)
            if match and match.group(1) not in param_set:
                keys_to_remove.append(key)
    for key in keys_to_remove:
        del bt_dict[key]

    # 添加新参数的占位符
    for code in param_codes:
        if code not in bt_dict:
            bt_dict[code] = f"{{{{{code}}}}}"

    # 写回 body_template（保持与原始类型一致）
    if isinstance(body_template, str):
        api_settings['body_template'] = json.dumps(bt_dict, ensure_ascii=False)
    else:
        api_settings['body_template'] = bt_dict

    return api_settings


def _sync_param_mappings(dimension_id, params, direction='output'):
    """
    同步 ParamMapping：当评估维度的输入/输出字段变更时，
    自动为该维度创建/更新/删除对应的 ParamMapping 记录。

    映射规则：source='evaluation', source_param=param_code,
              dimension_id=dimension_id, target_param=param_code,
              source_direction=direction (input/output)
    """
    if params is None:
        return

    try:
        if isinstance(params, str):
            params = json.loads(params)
    except (json.JSONDecodeError, TypeError):
        return

    if not isinstance(params, list):
        return

    # 当前维度已有的映射（包含软删除的记录，避免唯一约束冲突）
    all_mappings = ParamMapping.query.filter_by(
        dimension_id=dimension_id,
        source='evaluation'
    ).all()
    active_map = {m.source_param: m for m in all_mappings if not m.deleted}
    soft_deleted_map = {m.source_param: m for m in all_mappings if m.deleted}

    # 提交的 param_code 集合
    submitted_codes = set()

    for p in params:
        param_code = p.get('param_code', p.get('key', ''))
        if not param_code:
            continue
        submitted_codes.add(param_code)

        if param_code in active_map:
            # 更新已有映射
            m = active_map[param_code]
            m.target_param = param_code
            m.source_direction = direction
        elif param_code in soft_deleted_map:
            # 复活软删除的记录（避免唯一约束冲突）
            m = soft_deleted_map.pop(param_code)
            m.deleted = False
            m.target_param = param_code
            m.source_direction = direction
            m.algorithm_type = p.get('algorithm_type', 'evaluation')
            m.transform_type = 'none'
            active_map[param_code] = m
        else:
            # 创建新映射
            m = ParamMapping(
                algorithm_type=p.get('algorithm_type', 'evaluation'),
                source='evaluation',
                source_param=param_code,
                source_direction=direction,
                dimension_id=dimension_id,
                target_param=param_code,
                transform_type='none'
            )
            db.session.add(m)
            active_map[param_code] = m

    # 删除不再提交的映射（软删除）
    for code, m in active_map.items():
        if code not in submitted_codes:
            m.deleted = True


class EvaluationController:
    # --- 分类管理 (Category Management) ---

    @staticmethod
    def get_categories():
        categories = Category.query.all()
        data = []
        for cat in categories:
            # Handle datetime conversion safely
            created_at = cat.created_at
            updated_at = cat.updated_at

            # Ensure we're dealing with datetime objects before calling isoformat
            if isinstance(created_at, datetime):
                created_at_iso = created_at.isoformat()
            else:
                # Fallback for invalid datetime values
                created_at_iso = str(created_at)

            if isinstance(updated_at, datetime):
                updated_at_iso = updated_at.isoformat()
            else:
                # Fallback for invalid datetime values
                updated_at_iso = str(updated_at)

            data.append(
                CategoryItem(
                    id=cat.id,
                    name=cat.name,
                    description=cat.description,
                    icon=cat.icon,
                    created_at=created_at_iso,
                    updated_at=updated_at_iso,
                )
            )
        return success_response(CategoryListData(items=data, total=len(data)))

    @staticmethod
    def create_category():
        try:
            req = CategoryCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        try:
            new_cat = Category(
                name=req.name,
                description=req.description,
                icon=req.icon
            )
            db.session.add(new_cat)
            db.session.commit()
            return success_response(IdData(id=new_cat.id), "分类创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def update_category(cat_id):
        cat = db.session.get(Category, cat_id)
        if not cat:
            return error_response("未找到分类", 404)

        try:
            req = CategoryUpdateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        try:
            if req.name is not None:
                cat.name = req.name
            if req.description is not None:
                cat.description = req.description
            if req.icon is not None:
                cat.icon = req.icon

            cat.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "分类更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def delete_category(cat_id):
        cat = db.session.get(Category, cat_id)
        if not cat:
            return error_response("未找到分类", 404)

        try:
            db.session.delete(cat)
            db.session.commit()
            return success_response(None, "分类已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # --- 维度管理 (Dimension Management) ---

    # 获取维度选项列表（用于下拉选择，包含关联的算法信息）
    @staticmethod
    def get_dimension_options():
        algorithm_type = request.args.get('algorithm_type', '')
        query = Dimension.query.filter_by(deleted=False)
        if algorithm_type:
            associated_dim_ids = [r.dimension_id for r in
                                  AlgorithmDimensionRelation.query.filter_by(algorithm_type=algorithm_type,
                                                                             deleted=False).all()]
            if associated_dim_ids:
                query = query.filter(Dimension.id.in_(associated_dim_ids))
            else:
                return success_response({'dimensions': []})
        dimensions = query.order_by(Dimension.id).all()

        # 查询哪些维度需要音频文件参数（field_type='audio' 的输入参数）
        dim_ids = [d.id for d in dimensions]
        audio_dim_ids = set()
        if dim_ids:
            from backend.models.algorithm_models import EvaluationDimensionParam
            audio_params = EvaluationDimensionParam.query.filter(
                EvaluationDimensionParam.dimension_id.in_(dim_ids),
                EvaluationDimensionParam.field_type == 'audio',
                EvaluationDimensionParam.param_direction == 'input',
                EvaluationDimensionParam.deleted == False
            ).all()
            audio_dim_ids = {p.dimension_id for p in audio_params}

        return success_response({
            'dimensions': [
                {
                    'id': d.id,
                    'name': d.name,
                    'description': d.description,
                    'type': d.type,
                    'dimension_type': d.dimension_type,
                    'category_id': d.category_id,
                    'task_type_code': d.task_type_code,
                    'requires_audio': d.id in audio_dim_ids
                }
                for d in dimensions
            ]
        })

    # 获取所有评分维度
    @staticmethod
    def get_all():
        category_id = request.args.get('category_id', request.args.get('category_id', type=int))
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', request.args.get('per_page', 10, type=int), type=int)
        search = request.args.get('search', '')

        query = Dimension.query.filter_by(deleted=False)

        if category_id:
            query = query.filter_by(category_id=category_id)

        if search:
            query = query.filter(
                (Dimension.name.ilike(f'%{search}%')) |
                (Dimension.description.ilike(f'%{search}%')) |
                (Dimension.keywords.ilike(f'%{search}%'))
            )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        dimensions = pagination.items

        data = []
        for dim in dimensions:
            # 从 EvaluationDimensionParam 表获取参数
            dim_params = EvaluationDimensionParam.query.filter_by(
                dimension_id=dim.id, deleted=False
            ).order_by(EvaluationDimensionParam.ui_order).all()
            required_inputs = [p.to_dict() for p in dim_params if p.param_direction == 'input']
            output_fields = [p.to_dict() for p in dim_params if p.param_direction == 'output']

            # 从 algorithm_dimension_relations 表获取关联的算法
            dim_relations = AlgorithmDimensionRelation.query.filter_by(
                dimension_id=dim.id, deleted=False
            ).all()
            associated_algorithms = [
                {
                    'algorithmType': rel.algorithm_type,
                    'isDefault': rel.is_default,
                    'weight': rel.weight
                }
                for rel in dim_relations
            ]

            data.append(
                DimensionItem(
                    id=dim.id,
                    name=dim.name,
                    description=dim.description,
                    keywords=dim.keywords,
                    dimension_type=dim.dimension_type,
                    parent_dimension_id=dim.parent_dimension_id,
                    task_type_code=dim.task_type_code,
                    category_id=dim.category_id,
                    api_url=dim.api_url,
                    api_endpoints=dim.api_endpoints,
                    api_settings=dim.api_settings,
                    api_status=dim.api_status,
                    score_unit=dim.score_unit,
                    type=dim.type,
                    result_type=dim.result_type,
                    result_min=dim.result_min,
                    result_max=dim.result_max,
                    decimal_places=dim.decimal_places,
                    weight=dim.weight,
                    estimated_exec_time=dim.estimated_exec_time,
                    rule=dim.rule,
                    required_inputs=required_inputs,
                    output_fields=output_fields,
                    statistic_method=getattr(dim, 'statistic_method', 'average') or 'average',
                    associated_algorithms=associated_algorithms,
                    status=dim.status,
                    created_at=dim.created_at.isoformat() if dim.created_at else None,
                    updated_at=dim.updated_at.isoformat() if dim.updated_at else None,
                )
            )

        return success_response(
            DimensionListData(
                items=data,
                total=pagination.total,
                page=page,
                per_page=per_page,
                pages=pagination.pages,
            )
        )

    # 创建新的评分维度
    @staticmethod
    def create():
        # 使用 Pydantic Schema 自动处理驼峰转蛇形
        data = request.get_json()

        try:
            validated_data = DimensionCreateInput.model_validate(data)
            data = validated_data.model_dump(exclude_none=True, by_alias=False)
            log_and_emit('DEBUG', 'evaluation', f'DEBUG CREATE data after model_dump: {data}', enable_console_log=True)
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        if not data or 'name' not in data:
            return error_response("缺少名称(name)")

        # 处理评分规则（将字符串解析为字典）
        rule = data.get('rule')
        if rule:
            try:
                if isinstance(rule, str):
                    rule = json.loads(rule)
            except json.JSONDecodeError:
                return error_response("规则格式错误: 无效的 JSON 字符串")

            # 只有当规则对象不为空时才验证结构
            if rule:
                is_valid, msg = EvaluationController.validate_rule_structure(rule)
                if not is_valid:
                    return error_response(f"规则格式错误: {msg}")

            # 更新data中的rule为解析后的字典
            data['rule'] = rule

        # 处理required_inputs（将字符串解析为字典）
        required_inputs = data.get('required_inputs')
        if required_inputs:
            try:
                if isinstance(required_inputs, str):
                    required_inputs = json.loads(required_inputs)
                data['required_inputs'] = required_inputs
            except json.JSONDecodeError:
                return error_response("所需输入配置格式错误: 无效的 JSON 字符串")

        # 处理api_settings（将字符串解析为字典）
        api_settings = data.get('api_settings')
        if api_settings:
            try:
                if isinstance(api_settings, str):
                    api_settings = json.loads(api_settings)
                data['api_settings'] = api_settings
            except json.JSONDecodeError:
                return error_response("API配置格式错误: 无效的 JSON 字符串")

        # 准备创建数据
        model_fields = [
            'name', 'keywords', 'description', 'category_id', 'api_url',
            'api_endpoints', 'type', 'result_type', 'result_min',
            'result_max', 'decimal_places', 'weight', 'estimated_exec_time',
            'rule', 'api_settings', 'status', 'api_status', 'score_unit',
            'dimension_type', 'parent_dimension_id', 'task_type_code',
            'statistic_method'
        ]

        create_data = {}
        for field in model_fields:
            if field in data:
                value = data[field]
                # 处理category_id空字符串，转换为null
                if field == 'category_id' and (value == '' or value is None):
                    value = None
                create_data[field] = value

        try:
            new_dim = Dimension(**create_data)
            db.session.add(new_dim)
            db.session.flush()

            # 保存关联算法到 algorithm_dimension_relations 表
            raw_associated_algorithms = data.get('associatedAlgorithms') or data.get('associated_algorithms') or []
            if raw_associated_algorithms:
                for algo in raw_associated_algorithms:
                    algo_type = algo.get('algorithmType') or algo.get('algorithm_type') if isinstance(algo,
                                                                                                      dict) else algo
                    is_default = algo.get('isDefault', False) if isinstance(algo, dict) else False
                    weight = algo.get('weight', 1.0) if isinstance(algo, dict) else 1.0
                    if algo_type:
                        rel = AlgorithmDimensionRelation(
                            algorithm_type=algo_type,
                            dimension_id=new_dim.id,
                            is_default=is_default,
                            weight=weight
                        )
                        db.session.add(rel)

            # 保存 required_inputs 到 EvaluationDimensionParam 表
            raw_required_inputs = data.get('required_inputs')
            log_and_emit('DEBUG', 'evaluation',
                         f'DEBUG CREATE raw_required_inputs: {raw_required_inputs}, type: {type(raw_required_inputs)}',
                         enable_console_log=True)
            if raw_required_inputs:
                try:
                    if isinstance(raw_required_inputs, str):
                        required_inputs = json.loads(raw_required_inputs)
                    else:
                        required_inputs = raw_required_inputs
                except json.JSONDecodeError:
                    return error_response("所需输入配置格式错误: 无效的 JSON 字符串")

                if isinstance(required_inputs, list):
                    for idx, inp in enumerate(required_inputs):
                        param_code = inp.get('param_code', inp.get('key', ''))
                        if not param_code:
                            continue
                        param = EvaluationDimensionParam(
                            dimension_id=new_dim.id,
                            param_code=param_code,
                            param_name=inp.get('param_name', inp.get('label', '')),
                            label=inp.get('label', inp.get('param_name', '')),
                            field_type=inp.get('field_type', inp.get('type', 'text')),
                            required=inp.get('required', True),
                            default_value=json.dumps(inp.get('default_value')) if inp.get('default_value') else None,
                            help_text=inp.get('help_text', inp.get('description', '')),
                            ui_order=inp.get('ui_order', idx)
                        )
                        db.session.add(param)

            # 同步 ParamMapping：为 input 字段创建/更新映射
            _sync_param_mappings(new_dim.id, data.get('required_inputs'), direction='input')

            # 同步 body_template：根据 required_inputs 中的 param_code 更新 api_settings
            if required_inputs and isinstance(required_inputs, list):
                created_param_codes = []
                for inp in required_inputs:
                    pc = inp.get('param_code', inp.get('key', ''))
                    if pc:
                        created_param_codes.append(pc)
                if created_param_codes:
                    current_api_settings = new_dim.api_settings or {}
                    new_dim.api_settings = _sync_body_template(current_api_settings, created_param_codes)

            # 保存 output_fields（结果提取字段）到 EvaluationDimensionParam 表
            raw_output_fields = data.get('output_fields')
            if raw_output_fields:
                try:
                    if isinstance(raw_output_fields, str):
                        output_fields = json.loads(raw_output_fields)
                    else:
                        output_fields = raw_output_fields
                except json.JSONDecodeError:
                    return error_response("输出字段配置格式错误: 无效的 JSON 字符串")

                if isinstance(output_fields, list):
                    for idx, outp in enumerate(output_fields):
                        param_code = outp.get('param_code', '')
                        if not param_code:
                            continue
                        param = EvaluationDimensionParam(
                            dimension_id=new_dim.id,
                            param_code=param_code,
                            param_name=outp.get('param_name', outp.get('label', '')),
                            label=outp.get('label', outp.get('param_name', '')),
                            field_type=outp.get('field_type', 'number'),
                            param_direction='output',
                            field_path=outp.get('field_path', param_code),
                            agg_role=outp.get('agg_role'),
                            output_role=outp.get('output_role', 'main'),
                            visible_in_report=outp.get('visible_in_report', True),
                            required=False,
                            default_value=json.dumps(outp.get('default_value')) if outp.get('default_value') else None,
                            help_text=outp.get('help_text', ''),
                            ui_order=outp.get('ui_order', idx)
                        )
                        db.session.add(param)

            # 同步 ParamMapping：为 output 字段创建/更新映射
            _sync_param_mappings(new_dim.id, data.get('output_fields'), direction='output')

            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(IdData(id=new_dim.id), "评分维度创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新评分维度信息
    @staticmethod
    def update(dim_id):
        dim = db.session.get(Dimension, dim_id)
        if not dim or dim.deleted:
            return error_response("未找到评分维度", 404)

        # 使用 Pydantic Schema 自动处理驼峰转蛇形
        data = request.get_json()

        try:
            validated_data = DimensionUpdateInput.model_validate(data)
            data = validated_data.model_dump(exclude_none=True, by_alias=False)
            log_and_emit('DEBUG', 'evaluation', f'DEBUG UPDATE data after model_dump: {data}', enable_console_log=True)
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        # 处理评分规则（将字符串解析为字典）
        if 'rule' in data:
            rule = data['rule']
            try:
                if isinstance(rule, str):
                    rule = json.loads(rule)
            except json.JSONDecodeError:
                return error_response("规则格式错误: 无效的 JSON 字符串")

            # 只有当规则对象不为空时才验证结构
            if rule:
                is_valid, msg = EvaluationController.validate_rule_structure(rule)
                if not is_valid:
                    return error_response(f"规则格式错误: {msg}")

            # 更新data中的rule为解析后的字典
            data['rule'] = rule

        # 处理required_inputs（更新 EvaluationDimensionParam 表）
        raw_required_inputs = data.get('required_inputs')
        log_and_emit('DEBUG', 'evaluation',
                     f'DEBUG UPDATE raw_required_inputs: {raw_required_inputs}, type: {type(raw_required_inputs)}',
                     enable_console_log=True)
        required_inputs = None
        if raw_required_inputs:
            try:
                if isinstance(raw_required_inputs, str):
                    required_inputs = json.loads(raw_required_inputs)
                else:
                    required_inputs = raw_required_inputs
            except json.JSONDecodeError:
                return error_response("所需输入配置格式错误: 无效的 JSON 字符串")

        # 处理api_settings（将字符串解析为字典）
        api_settings = data.get('api_settings')
        if api_settings:
            try:
                if isinstance(api_settings, str):
                    api_settings = json.loads(api_settings)
                data['api_settings'] = api_settings
            except json.JSONDecodeError:
                return error_response("API配置格式错误: 无效的 JSON 字符串")

        try:
            model_fields = ['name', 'keywords', 'description', 'category_id', 'api_url', 'api_endpoints', 'type',
                            'result_type', 'result_min', 'result_max', 'decimal_places', 'weight',
                            'estimated_exec_time', 'rule', 'api_settings', 'status', 'api_status', 'score_unit',
                            'dimension_type', 'parent_dimension_id', 'task_type_code', 'statistic_method']

            for field in model_fields:
                if field in data:
                    value = data[field]
                    # 处理category_id空字符串，转换为null
                    if field == 'category_id' and (value == '' or value is None):
                        value = None
                    setattr(dim, field, value)

            # 更新关联算法到 algorithm_dimension_relations 表
            raw_associated_algorithms = data.get('associatedAlgorithms') or data.get('associated_algorithms')
            if raw_associated_algorithms is not None:
                # 删除旧的关联
                AlgorithmDimensionRelation.query.filter_by(dimension_id=dim.id).delete()
                db.session.flush()

                # 添加新的关联
                if isinstance(raw_associated_algorithms, list):
                    for algo in raw_associated_algorithms:
                        algo_type = algo.get('algorithmType') or algo.get('algorithm_type') if isinstance(algo,
                                                                                                          dict) else algo
                        is_default = algo.get('isDefault', False) if isinstance(algo, dict) else False
                        weight = algo.get('weight', 1.0) if isinstance(algo, dict) else 1.0
                        if algo_type:
                            rel = AlgorithmDimensionRelation(
                                algorithm_type=algo_type,
                                dimension_id=dim.id,
                                is_default=is_default,
                                weight=weight
                            )
                            db.session.add(rel)

            # 更新 required_inputs 到 EvaluationDimensionParam 表
            if required_inputs is not None:
                # 只删除旧的 input 参数，保留 output 参数
                EvaluationDimensionParam.query.filter_by(dimension_id=dim.id, param_direction='input').delete()
                db.session.flush()

                # 添加新的参数
                if isinstance(required_inputs, list):
                    for idx, inp in enumerate(required_inputs):
                        param_code = inp.get('param_code', inp.get('key', ''))
                        if not param_code:
                            continue
                        param = EvaluationDimensionParam(
                            dimension_id=dim.id,
                            param_code=param_code,
                            param_name=inp.get('param_name', inp.get('label', '')),
                            label=inp.get('label', inp.get('param_name', '')),
                            field_type=inp.get('field_type', inp.get('type', 'text')),
                            param_direction='input',
                            required=inp.get('required', True),
                            default_value=json.dumps(inp.get('default_value')) if inp.get('default_value') else None,
                            help_text=inp.get('help_text', inp.get('description', '')),
                            ui_order=inp.get('ui_order', idx)
                        )
                        db.session.add(param)

            # 同步 ParamMapping：为 input 字段创建/更新映射
            _sync_param_mappings(dim.id, data.get('required_inputs'), direction='input')

            # 更新 output_fields 到 EvaluationDimensionParam 表
            raw_output_fields = data.get('output_fields')
            if raw_output_fields is not None:
                # 只删除旧的 output 参数
                EvaluationDimensionParam.query.filter_by(dimension_id=dim.id, param_direction='output').delete()
                db.session.flush()

                try:
                    if isinstance(raw_output_fields, str):
                        output_fields = json.loads(raw_output_fields)
                    else:
                        output_fields = raw_output_fields
                except json.JSONDecodeError:
                    return error_response("输出字段配置格式错误: 无效的 JSON 字符串")

                if isinstance(output_fields, list):
                    for idx, outp in enumerate(output_fields):
                        param_code = outp.get('param_code', '')
                        if not param_code:
                            continue
                        param = EvaluationDimensionParam(
                            dimension_id=dim.id,
                            param_code=param_code,
                            param_name=outp.get('param_name', outp.get('label', '')),
                            label=outp.get('label', outp.get('param_name', '')),
                            field_type=outp.get('field_type', 'number'),
                            param_direction='output',
                            field_path=outp.get('field_path', param_code),
                            agg_role=outp.get('agg_role'),
                            output_role=outp.get('output_role', 'main'),
                            visible_in_report=outp.get('visible_in_report', True),
                            required=False,
                            default_value=json.dumps(outp.get('default_value')) if outp.get('default_value') else None,
                            help_text=outp.get('help_text', ''),
                            ui_order=outp.get('ui_order', idx)
                        )
                        db.session.add(param)

            # 同步 ParamMapping：为 output 字段创建/更新映射
            _sync_param_mappings(dim.id, data.get('output_fields'), direction='output')

            # 同步 body_template：根据 required_inputs 中的 param_code 更新 api_settings
            if required_inputs is not None and isinstance(required_inputs, list):
                updated_param_codes = []
                for inp in required_inputs:
                    pc = inp.get('param_code', inp.get('key', ''))
                    if pc:
                        updated_param_codes.append(pc)
                if updated_param_codes:
                    current_api_settings = dim.api_settings or {}
                    dim.api_settings = _sync_body_template(current_api_settings, updated_param_codes)

            dim.updated_at = now_cst()

            if dim.dimension_type == 'main':
                sub_dimensions = Dimension.query.filter(
                    Dimension.parent_dimension_id == dim.id,
                    Dimension.dimension_type == 'sub',
                    Dimension.deleted == False
                ).all()
                for sub_dim in sub_dimensions:
                    if not sub_dim.api_url:
                        sub_dim.api_url = dim.api_url
                    if not sub_dim.api_endpoints:
                        sub_dim.api_endpoints = dim.api_endpoints
                    if not sub_dim.api_settings:
                        sub_dim.api_settings = dim.api_settings
                    if not sub_dim.task_type_code:
                        sub_dim.task_type_code = dim.task_type_code
                    sub_dim.updated_at = now_cst()

            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "评分维度更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

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

    # 删除评分维度 (逻辑删除)
    @staticmethod
    def delete(dim_id):
        dim = db.session.get(Dimension, dim_id)
        if not dim:
            return error_response("未找到评分维度", 404)

        try:
            dim.deleted = True
            dim.updated_at = now_cst()
            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "评分维度已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 维度 API 健康探测
    @staticmethod
    def health_check(dim_id):
        dim = db.session.get(Dimension, dim_id)
        if not dim or dim.deleted:
            return error_response("维度不存在", 404)

        # 检查是否配置了多个API端点
        if dim.api_endpoints and isinstance(dim.api_endpoints, list) and len(dim.api_endpoints) > 0:
            results = []
            all_online = True

            for endpoint in dim.api_endpoints:
                url = endpoint.get('url') or endpoint.get('endpoint')
                if not url:
                    continue

                settings = dim.api_settings or {}
                method = settings.get('method', 'GET').upper()
                headers = settings.get('headers', {})

                health_check_url = url

                start_time = time.time()
                try:
                    if method == 'POST':
                        # 对于 POST 请求，我们使用简单的健康检查 GET 请求替代
                        response = requests.get(health_check_url, headers=headers, timeout=10)
                    else:
                        response = requests.get(health_check_url, headers=headers, timeout=10)

                    duration = (time.time() - start_time) * 1000

                    if 200 <= response.status_code < 400:
                        endpoint_status = 'online'
                        message = "健康探测完成"
                    else:
                        endpoint_status = 'offline'
                        message = f"探测失败，状态码: {response.status_code}"
                        all_online = False

                    results.append(
                        HealthCheckResultItem(
                            url=url,
                            status=endpoint_status,
                            status_code=response.status_code,
                            response_time=f"{duration:.2f}ms",
                            message=message,
                        )
                    )
                except Exception as e:
                    results.append(
                        HealthCheckResultItem(
                            url=url,
                            status="offline",
                            error=str(e),
                            message="健康探测失败",
                        )
                    )
                    all_online = False

            # 更新维度的整体状态
            dim.api_status = 'online' if all_online else 'offline'
            db.session.commit()

            return success_response(
                DimensionHealthCheckData(results=results, overall_status=dim.api_status),
                "健康探测完成",
            )
        else:
            # 未配置任何API端点
            dim.api_status = 'offline'
            db.session.commit()
            return error_response("未配置任何 API 端点")

    # 计算分值
    @staticmethod
    def calculate_score(dim_id):
        dim = db.session.get(Dimension, dim_id)
        if not dim or dim.deleted:
            return error_response("维度不存在", 404)

        try:
            req = ScoreCalculateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        test_value = req.value
        rule = dim.rule

        if not rule or 'rules' not in rule:
            return error_response("未配置评分规则")

        try:
            if isinstance(test_value, str):
                test_value = float(test_value)
                if test_value.is_integer():
                    test_value = int(test_value)

            score = 0
            for r in rule['rules']:
                cond = r.get('condition')
                val = r.get('value')
                s = r.get('score', 0)

                match = False
                if cond == '>':
                    match = test_value > val
                elif cond == '>=':
                    match = test_value >= val
                elif cond == '<':
                    match = test_value < val
                elif cond == '<=':
                    match = test_value <= val
                elif cond == '==':
                    match = test_value == val
                elif cond == '!=':
                    match = test_value != val

                if match:
                    score = s
                    break

            return success_response(ScoreData(score=float(score)), "分值计算完成")
        except Exception as e:
            return error_response(f"规则计算出错: {str(e)}")

    # 批量操作
    @staticmethod
    def batch_action():
        try:
            req = BatchActionInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        ids = req.ids
        action = req.action

        if ids is None or not action:
            return error_response("缺少必要参数: ids/item_ids, action")

        try:
            if action == 'delete':
                Dimension.query.filter(Dimension.id.in_(ids)).update({"deleted": True}, synchronize_session=False)
            elif action == 'enable':
                Dimension.query.filter(Dimension.id.in_(ids)).update({"status": True}, synchronize_session=False)
            elif action == 'disable':
                Dimension.query.filter(Dimension.id.in_(ids)).update({"status": False}, synchronize_session=False)
            elif action == 'export':
                dims = Dimension.query.filter(Dimension.id.in_(ids)).all()
                export_data = []
                for d in dims:
                    export_data.append({
                        "name": d.name,
                        "description": d.description,
                        "category_id": d.category_id,
                        "type": d.type,
                        "rule": d.rule,
                        "api_url": d.api_url,
                        "api_settings": d.api_settings,
                        "result_type": d.result_type,
                        "score_unit": d.score_unit,
                        "status": d.status
                    })
                return success_response(export_data, "数据准备就绪")

            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, f"批量操作 {action} 执行成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 导出到文件
    @staticmethod
    def export_to_file():
        format_type = request.args.get('format', 'json').lower()
        ids = request.args.get('ids')

        query = Dimension.query.filter_by(deleted=False)
        if ids:
            id_list = [int(i) for i in ids.split(',')]
            query = query.filter(Dimension.id.in_(id_list))

        dimensions = query.all()
        data = []
        for d in dimensions:
            if format_type == 'excel':
                data.append({
                    "名称": d.name,
                    "描述": d.description,
                    "分类ID": d.category_id,
                    "类型": d.type,
                    "Master入口URL": d.api_url,
                    "结果类型": d.result_type,
                    "权重": d.weight,
                    "分数单位": d.score_unit,
                    "规则": json.dumps(d.rule, ensure_ascii=False),
                    "API配置": json.dumps(d.api_settings, ensure_ascii=False),
                    "状态": "启用" if d.status else "禁用"
                })
            else:
                data.append({
                    "name": d.name,
                    "description": d.description,
                    "category_id": d.category_id,
                    "type": d.type,
                    "api_url": d.api_url,
                    "result_type": d.result_type,
                    "weight": d.weight,
                    "score_unit": d.score_unit,
                    "rule": d.rule,
                    "api_settings": d.api_settings,
                    "status": d.status
                })

        if format_type == 'excel':
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='评估维度')
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f"evaluation_dimensions_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
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
                if not name: continue

                # 尝试查找现有维度
                dim = Dimension.query.filter_by(name=name, deleted=False).first()

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

                if dim:
                    if update_existing:
                        dim.description = row.get('描述') or row.get('description', dim.description)
                        dim.category_id = int(
                            row.get('分类ID') or row.get('category_id') or row.get('category_id', dim.category_id))
                        dim.type = row.get('类型') or row.get('type', dim.type)
                        # 更新api_endpoints而不是api_url
                        api_url_value = row.get('API链接') or row.get('api_url') or row.get('api_url')
                        if api_url_value:
                            # 如果api_endpoints为空或不是列表，初始化它
                            if not dim.api_endpoints or not isinstance(dim.api_endpoints, list):
                                dim.api_endpoints = []
                            # 如果已存在端点，更新第一个端点的url，否则添加新端点
                            if len(dim.api_endpoints) > 0:
                                dim.api_endpoints[0]['url'] = api_url_value
                            else:
                                dim.api_endpoints.append({'url': api_url_value})
                        dim.result_type = int(
                            row.get('结果类型') or row.get('result_type') or row.get('result_type', dim.result_type))
                        dim.score_unit = row.get('分数单位') or row.get('score_unit') or row.get('scoreUnit',
                                                                                                 dim.score_unit)
                        dim.rule = rule
                        dim.api_settings = api_settings
                        dim.updated_at = now_cst()
                        update_count += 1
                else:
                    new_dim = Dimension(
                        name=name,
                        description=row.get('描述') or row.get('description'),
                        category_id=int(row.get('分类ID') or row.get('category_id') or row.get('category_id', 1)),
                        type=row.get('类型') or row.get('type', '性能指标'),
                        api_endpoints=[{'url': row.get('API链接') or row.get('api_url') or row.get('api_url', '')}] if (
                                row.get('API链接') or row.get('api_url') or row.get('api_url')) else [],
                        result_type=int(row.get('结果类型') or row.get('result_type') or row.get('result_type', 1)),
                        score_unit=row.get('分数单位') or row.get('score_unit') or row.get('scoreUnit'),
                        rule=rule,
                        api_settings=api_settings,
                        status=True
                    )
                    db.session.add(new_dim)
                    import_count += 1

            db.session.commit()
            return success_response(
                DimensionImportResult(imported=import_count, updated=update_count),
                f"导入成功: 新增 {import_count} 条, 更新 {update_count} 条",
            )

        except Exception as e:
            db.session.rollback()
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

        log_and_emit('DEBUG', 'evaluation',
                     f"重新评估参数: task_id={task_id}, reevaluate_type={reevaluate_type}, reextract_device_output={reextract_device_output}",
                     task_id=task_id)

        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", 404)

        if task.status not in ['completed', 'failed', 'stopped', 'paused', 'skipped']:
            return error_response("只有已完成/失败/停止/暂停/跳过的任务才能重新评估")

        from backend.services.execution.reevaluation_executor import ReevaluationExecutor
        executor = ReevaluationExecutor.get_instance()
        success, message = executor.submit(
            task_id=task_id,
            reextract_device_output=reextract_device_output,
            reevaluate_type=reevaluate_type
        )

        if success:
            test_results = db.session.query(TestResult).filter_by(task_id=task_id).all()
            queued_count = len(test_results)
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
