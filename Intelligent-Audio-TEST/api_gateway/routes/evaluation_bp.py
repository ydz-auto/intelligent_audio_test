from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.evaluation_controller import EvaluationController
from api_gateway.routes._response import to_response

router = APIRouter()

@router.post('/task/reevaluate')
def reevaluate_task():
    result = EvaluationController.reevaluate_task_results()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/dimensions/options')
def get_dimension_options():
    result = EvaluationController.get_dimension_options()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/dimensions')
def get_all():
    result = EvaluationController.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/dimensions')
def create():
    result = EvaluationController.create()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/dimensions/{dim_id}')
def update(dim_id: int):
    result = EvaluationController.update(dim_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/dimensions/{dim_id}')
def delete(dim_id: int):
    result = EvaluationController.delete(dim_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.api_route('/dimensions/{dim_id}/health', methods=['GET', 'POST'])
def health_check(dim_id: int):
    result = EvaluationController.health_check(dim_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/dimensions/{dim_id}/calculate')
def calculate_score(dim_id: int):
    result = EvaluationController.calculate_score(dim_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/dimensions/batch')
def batch_action():
    result = EvaluationController.batch_action()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/dimensions/export')
def export_dimensions():
    result = EvaluationController.export_to_file()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/dimensions/import')
def import_dimensions():
    result = EvaluationController.import_from_file()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

# --- 分类管理 (Category Management) ---

@router.get('/categories')
def get_categories():
    result = EvaluationController.get_categories()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/categories')
def create_category():
    result = EvaluationController.create_category()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/categories/{cat_id}')
def update_category(cat_id: int):
    result = EvaluationController.update_category(cat_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/categories/{cat_id}')
def delete_category(cat_id: int):
    result = EvaluationController.delete_category(cat_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
