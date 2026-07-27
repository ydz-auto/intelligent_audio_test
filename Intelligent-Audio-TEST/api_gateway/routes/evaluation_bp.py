from flask import Blueprint
from api_gateway.controllers.evaluation_controller import EvaluationController

evaluation_bp = Blueprint('evaluation', __name__)

@evaluation_bp.route('/task/reevaluate', methods=['POST'])
def reevaluate_task():
    return EvaluationController.reevaluate_task_results()

@evaluation_bp.route('/dimensions/options', methods=['GET'])
def get_dimension_options():
    return EvaluationController.get_dimension_options()

@evaluation_bp.route('/dimensions', methods=['GET'])
def get_all():
    return EvaluationController.get_all()

@evaluation_bp.route('/dimensions', methods=['POST'])
def create():
    return EvaluationController.create()

@evaluation_bp.route('/dimensions/<int:dim_id>', methods=['PUT'])
def update(dim_id):
    return EvaluationController.update(dim_id)

@evaluation_bp.route('/dimensions/<int:dim_id>', methods=['DELETE'])
def delete(dim_id):
    return EvaluationController.delete(dim_id)

@evaluation_bp.route('/dimensions/<int:dim_id>/health', methods=['GET', 'POST'])
def health_check(dim_id):
    return EvaluationController.health_check(dim_id)

@evaluation_bp.route('/dimensions/<int:dim_id>/calculate', methods=['POST'])
def calculate_score(dim_id):
    return EvaluationController.calculate_score(dim_id)

@evaluation_bp.route('/dimensions/batch', methods=['POST'])
def batch_action():
    return EvaluationController.batch_action()

@evaluation_bp.route('/dimensions/export', methods=['GET'])
def export_dimensions():
    return EvaluationController.export_to_file()

@evaluation_bp.route('/dimensions/import', methods=['POST'])
def import_dimensions():
    return EvaluationController.import_from_file()

# --- 分类管理 (Category Management) ---

@evaluation_bp.route('/categories', methods=['GET'])
def get_categories():
    return EvaluationController.get_categories()

@evaluation_bp.route('/categories', methods=['POST'])
def create_category():
    return EvaluationController.create_category()

@evaluation_bp.route('/categories/<int:cat_id>', methods=['PUT'])
def update_category(cat_id):
    return EvaluationController.update_category(cat_id)

@evaluation_bp.route('/categories/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    return EvaluationController.delete_category(cat_id)
