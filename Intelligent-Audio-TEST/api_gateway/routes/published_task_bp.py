from fastapi import APIRouter

from api_gateway.application.services.published_task.published_task_service import PublishedTaskService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.post('')
def publish(_: None = require_permission('task:publish')):
    result = PublishedTaskService.publish()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.get('')
def get_all(_: None = require_permission('published_task:read')):
    result = PublishedTaskService.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.get('/{published_task_id}')
def get_one(published_task_id: int, _: None = require_permission('published_task:read')):
    result = PublishedTaskService.get_one(published_task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/{published_task_id}/execute')
def execute(published_task_id: int, _: None = require_permission('published_task:execute')):
    result = PublishedTaskService.execute(published_task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/{published_task_id}/versions')
def create_version(published_task_id: int, _: None = require_permission('published_task:version')):
    result = PublishedTaskService.create_version(published_task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/{published_task_id}/archive')
def archive(published_task_id: int, _: None = require_permission('published_task:archive')):
    result = PublishedTaskService.archive(published_task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.put('/{published_task_id}')
def update_name(published_task_id: int, _: None = require_permission('published_task:read')):
    result = PublishedTaskService.update_name(published_task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
