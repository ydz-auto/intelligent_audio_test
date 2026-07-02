# -*- coding: utf-8 -*-
from flask import Blueprint
from backend.controllers.algorithm_controller import (
    list_algorithms, get_algorithm, create_algorithm, update_algorithm,
    delete_algorithm, list_params, get_param, create_param, update_param,
    delete_param, list_mappings, create_mapping, update_mapping, delete_mapping,
    get_algorithm_options, get_form_schema,
    get_algorithm_dimensions, associate_dimensions, reload_config,
    import_algorithms, bulk_delete, extract_params, get_dimension_params,
    list_reference_params, create_reference_param, update_reference_param, delete_reference_param,
    create_dimension_relation, update_dimension_relation, delete_dimension_relation,
    list_case_params, get_case_param, create_case_param, update_case_param, delete_case_param
)
from backend.controllers.algorithm_group_controller import AlgorithmGroupController

algorithm_bp = Blueprint('algorithm', __name__)

# 算法定义相关路由
@algorithm_bp.route('/definitions', methods=['GET'])
def get_definitions():
    return list_algorithms()

@algorithm_bp.route('/definitions/<algo_type>', methods=['GET'])
def get_definition(algo_type):
    return get_algorithm(algo_type)

@algorithm_bp.route('/definitions', methods=['POST'])
def post_definition():
    return create_algorithm()

@algorithm_bp.route('/definitions/<algo_type>', methods=['PUT'])
def put_definition(algo_type):
    return update_algorithm(algo_type)

@algorithm_bp.route('/definitions/<algo_type>', methods=['DELETE'])
def delete_definition(algo_type):
    return delete_algorithm(algo_type)

# 算法分组相关路由
@algorithm_bp.route('/groups', methods=['GET'])
def get_groups():
    return AlgorithmGroupController.get_all()

@algorithm_bp.route('/groups/<int:group_id>', methods=['GET'])
def get_group(group_id):
    return AlgorithmGroupController.get_by_id(group_id)

@algorithm_bp.route('/groups', methods=['POST'])
def post_group():
    return AlgorithmGroupController.create()

@algorithm_bp.route('/groups/<int:group_id>', methods=['PUT'])
def put_group(group_id):
    return AlgorithmGroupController.update(group_id)

@algorithm_bp.route('/groups/<int:group_id>', methods=['DELETE'])
def delete_group(group_id):
    return AlgorithmGroupController.delete(group_id)

# 参数相关路由
@algorithm_bp.route('/params', methods=['GET'])
def get_params():
    return list_params()

@algorithm_bp.route('/params/<int:param_id>', methods=['GET'])
def get_param_by_id(param_id):
    return get_param(param_id)

@algorithm_bp.route('/params', methods=['POST'])
def post_param():
    return create_param()

@algorithm_bp.route('/params/<int:param_id>', methods=['PUT'])
def put_param(param_id):
    return update_param(param_id)

@algorithm_bp.route('/params/<int:param_id>', methods=['DELETE'])
def delete_param_by_id(param_id):
    return delete_param(param_id)

# 用例专属参数相关路由
@algorithm_bp.route('/case-params', methods=['GET'])
def get_case_params():
    return list_case_params()

@algorithm_bp.route('/case-params/<int:param_id>', methods=['GET'])
def get_case_param_by_id(param_id):
    return get_case_param(param_id)

@algorithm_bp.route('/case-params', methods=['POST'])
def post_case_param():
    return create_case_param()

@algorithm_bp.route('/case-params/<int:param_id>', methods=['PUT'])
def put_case_param(param_id):
    return update_case_param(param_id)

@algorithm_bp.route('/case-params/<int:param_id>', methods=['DELETE'])
def delete_case_param_by_id(param_id):
    return delete_case_param(param_id)

# 参考参数相关路由
@algorithm_bp.route('/reference-params', methods=['GET'])
def get_reference_params():
    return list_reference_params()

@algorithm_bp.route('/reference-params', methods=['POST'])
def post_reference_param():
    return create_reference_param()

@algorithm_bp.route('/reference-params/<int:param_id>', methods=['PUT'])
def put_reference_param(param_id):
    return update_reference_param(param_id)

@algorithm_bp.route('/reference-params/<int:param_id>', methods=['DELETE'])
def delete_reference_param_by_id(param_id):
    return delete_reference_param(param_id)

# 映射相关路由
@algorithm_bp.route('/mappings', methods=['GET'])
def get_mappings():
    return list_mappings()

@algorithm_bp.route('/mappings', methods=['POST'])
def post_mapping():
    return create_mapping()

@algorithm_bp.route('/mappings/<int:mapping_id>', methods=['PUT'])
def put_mapping(mapping_id):
    return update_mapping(mapping_id)

@algorithm_bp.route('/mappings/<int:mapping_id>', methods=['DELETE'])
def delete_mapping_by_id(mapping_id):
    return delete_mapping(mapping_id)

# 其他功能路由
@algorithm_bp.route('/options', methods=['GET'])
def get_options():
    return get_algorithm_options()

@algorithm_bp.route('/form-schema/<algo_type>', methods=['GET'])
def get_algo_form_schema(algo_type):
    return get_form_schema(algo_type)

@algorithm_bp.route('/dimensions/<algo_type>', methods=['GET'])
def get_dimensions(algo_type):
    return get_algorithm_dimensions(algo_type)

@algorithm_bp.route('/dimensions/<algo_type>', methods=['POST'])
def post_dimensions(algo_type):
    return associate_dimensions(algo_type)

@algorithm_bp.route('/dimension-relations', methods=['POST'])
def post_dimension_relation():
    return create_dimension_relation()

@algorithm_bp.route('/dimension-relations/<int:relation_id>', methods=['PUT'])
def put_dimension_relation(relation_id):
    return update_dimension_relation(relation_id)

@algorithm_bp.route('/dimension-relations/<int:relation_id>', methods=['DELETE'])
def delete_dimension_relation_by_id(relation_id):
    return delete_dimension_relation(relation_id)

@algorithm_bp.route('/reload', methods=['POST'])
def reload():
    return reload_config()

@algorithm_bp.route('/import', methods=['POST'])
def import_algo():
    return import_algorithms()

@algorithm_bp.route('/bulk-delete', methods=['POST'])
def bulk_delete_algos():
    return bulk_delete()

@algorithm_bp.route('/extract-params', methods=['POST'])
def extract():
    return extract_params()

@algorithm_bp.route('/dimension-params/<int:dimension_id>', methods=['GET'])
def get_dim_params(dimension_id):
    return get_dimension_params(dimension_id)
