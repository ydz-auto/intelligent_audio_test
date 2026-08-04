from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.tag_query_service import (
    TagCategoryQueryService,
    TagQueryService,
)
from api_gateway.application.services.tag_command_service import (
    TagCategoryCommandService,
    TagCommandService,
)
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/categories')
def get_categories():
    return to_response(TagCategoryQueryService.get_all())


@router.get('/categories/{category_id}')
def get_category(category_id: int):
    return to_response(TagCategoryQueryService.get_one(category_id))


@router.post('/categories')
def create_category():
    return to_response(TagCategoryCommandService.create())


@router.put('/categories/{category_id}')
def update_category(category_id: int):
    return to_response(TagCategoryCommandService.update(category_id))


@router.delete('/categories/{category_id}')
def delete_category(category_id: int):
    return to_response(TagCategoryCommandService.delete(category_id))


@router.get('')
def get_tags():
    return to_response(TagQueryService.get_all())


@router.get('/names')
def get_tag_names():
    return to_response(TagQueryService.get_all_names())


@router.get('/by-category')
def get_tags_by_category():
    return to_response(TagQueryService.get_tags_by_category())


@router.get('/{tag_id}')
def get_tag(tag_id: int):
    return to_response(TagQueryService.get_one(tag_id))


@router.post('')
def create_tag():
    return to_response(TagCommandService.create())


@router.put('/{tag_id}')
def update_tag(tag_id: int):
    return to_response(TagCommandService.update(tag_id))


@router.delete('/{tag_id}')
def delete_tag(tag_id: int):
    return to_response(TagCommandService.delete(tag_id))


@router.put('/batch-category')
def batch_update_category():
    return to_response(TagCommandService.batch_update_category())
