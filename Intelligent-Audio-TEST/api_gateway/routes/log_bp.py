from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.log_query_service import LogQueryService
from api_gateway.application.services.log_command_service import LogCommandService
from api_gateway.routes._response import to_response

router = APIRouter()

@router.get('')
def get_logs():
    result = LogQueryService.get_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/stats')
def get_stats():
    result = LogQueryService.get_stats()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/mark')
def mark_logs():
    result = LogCommandService.mark_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.api_route('/export', methods=['GET', 'POST'])
def export_logs():
    result = LogQueryService.export_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/refresh')
def refresh_logs():
    result = LogQueryService.refresh_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/clear')
def clear_logs():
    result = LogCommandService.clear_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/status')
def get_archive_status():
    result = LogQueryService.get_archive_status()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/archive')
def archive_logs():
    result = LogCommandService.archive_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/logs')
def get_archived_logs():
    result = LogQueryService.get_archived_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/{filename}')
def download_archive(filename: str):
    result = LogQueryService.download_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/archive/{filename}')
def delete_archive(filename: str):
    result = LogCommandService.delete_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

from api_gateway.websocket.connection_manager import ws_router
