from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.tag_controller import TagCategoryController, TagController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/categories')
def get_categories():
    return to_response(TagCategoryController.get_all())


@router.get('/categories/{category_id}')
def get_category(category_id: int):
    return to_response(TagCategoryController.get_one(category_id))


@router.post('/categories')
def create_category():
    return to_response(TagCategoryController.create())


@router.put('/categories/{category_id}')
def update_category(category_id: int):
    return to_response(TagCategoryController.update(category_id))


@router.delete('/categories/{category_id}')
def delete_category(category_id: int):
    return to_response(TagCategoryController.delete(category_id))


@router.get('')
def get_tags():
    return to_response(TagController.get_all())


@router.get('/names')
def get_tag_names():
    return to_response(TagController.get_all_names())


@router.get('/by-category')
def get_tags_by_category():
    return to_response(TagController.get_tags_by_category())


@router.get('/{tag_id}')
def get_tag(tag_id: int):
    return to_response(TagController.get_one(tag_id))


@router.post('')
def create_tag():
    return to_response(TagController.create())


@router.put('/{tag_id}')
def update_tag(tag_id: int):
    return to_response(TagController.update(tag_id))


@router.delete('/{tag_id}')
def delete_tag(tag_id: int):
    return to_response(TagController.delete(tag_id))


@router.put('/batch-category')
def batch_update_category():
    return to_response(TagController.batch_update_category())
