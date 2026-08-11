from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.tag.tag_query_service import (
    TagCategoryQueryService,
    TagQueryService,
)
from api_gateway.application.services.tag.tag_command_service import (
    TagCategoryCommandService,
    TagCommandService,
)
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('/categories')
def get_categories(_: None = require_permission('tag:read')):
    return to_response(TagCategoryQueryService.get_all())


@router.get('/categories/{category_id}')
def get_category(category_id: int, _: None = require_permission('tag:read')):
    return to_response(TagCategoryQueryService.get_one(category_id))


@router.post('/categories')
def create_category(_: None = require_permission('tag:create')):
    return to_response(TagCategoryCommandService.create())


@router.put('/categories/{category_id}')
def update_category(category_id: int, _: None = require_permission('tag:update')):
    return to_response(TagCategoryCommandService.update(category_id))


@router.delete('/categories/{category_id}')
def delete_category(category_id: int, _: None = require_permission('tag:delete')):
    return to_response(TagCategoryCommandService.delete(category_id))


@router.get('')
def get_tags(_: None = require_permission('tag:read')):
    return to_response(TagQueryService.get_all())


@router.get('/names')
def get_tag_names(_: None = require_permission('tag:read')):
    return to_response(TagQueryService.get_all_names())


@router.get('/by-category')
def get_tags_by_category(_: None = require_permission('tag:read')):
    return to_response(TagQueryService.get_tags_by_category())


@router.get('/{tag_id}')
def get_tag(tag_id: int, _: None = require_permission('tag:read')):
    return to_response(TagQueryService.get_one(tag_id))


@router.post('')
def create_tag(_: None = require_permission('tag:create')):
    return to_response(TagCommandService.create())


@router.put('/{tag_id}')
def update_tag(tag_id: int, _: None = require_permission('tag:update')):
    return to_response(TagCommandService.update(tag_id))


@router.delete('/{tag_id}')
def delete_tag(tag_id: int, _: None = require_permission('tag:delete')):
    return to_response(TagCommandService.delete(tag_id))


@router.put('/batch-category')
def batch_update_category(_: None = require_permission('tag:update')):
    return to_response(TagCommandService.batch_update_category())
