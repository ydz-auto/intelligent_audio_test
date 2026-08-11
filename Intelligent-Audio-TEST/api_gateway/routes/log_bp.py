from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.log.log_query_service import LogQueryService
from api_gateway.application.services.log.log_command_service import LogCommandService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()

@router.get('')
def get_logs(_: None = require_permission('log:read')):
    result = LogQueryService.get_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/stats')
def get_stats(_: None = require_permission('log:read')):
    result = LogQueryService.get_stats()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/mark')
def mark_logs(_: None = require_permission('log:manage')):
    result = LogCommandService.mark_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.api_route('/export', methods=['GET', 'POST'])
def export_logs(_: None = require_permission('log:read')):
    result = LogQueryService.export_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/refresh')
def refresh_logs(_: None = require_permission('log:manage')):
    result = LogQueryService.refresh_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/clear')
def clear_logs(_: None = require_permission('log:manage')):
    result = LogCommandService.clear_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/status')
def get_archive_status(_: None = require_permission('log:read')):
    result = LogQueryService.get_archive_status()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/archive')
def archive_logs(_: None = require_permission('log:manage')):
    result = LogCommandService.archive_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/logs')
def get_archived_logs(_: None = require_permission('log:read')):
    result = LogQueryService.get_archived_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/{filename}')
def download_archive(filename: str, _: None = require_permission('log:read')):
    result = LogQueryService.download_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/archive/{filename}')
def delete_archive(filename: str, _: None = require_permission('log:manage')):
    result = LogCommandService.delete_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


