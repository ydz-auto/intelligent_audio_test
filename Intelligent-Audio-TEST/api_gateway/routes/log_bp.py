from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.log_controller import LogController
from api_gateway.routes._response import to_response

router = APIRouter()

@router.get('')
def get_logs():
    result = LogController.get_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/stats')
def get_stats():
    result = LogController.get_stats()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/mark')
def mark_logs():
    result = LogController.mark_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.api_route('/export', methods=['GET', 'POST'])
def export_logs():
    result = LogController.export_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/refresh')
def refresh_logs():
    result = LogController.refresh_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/clear')
def clear_logs():
    result = LogController.clear_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/status')
def get_archive_status():
    result = LogController.get_archive_status()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/archive')
def archive_logs():
    result = LogController.archive_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/logs')
def get_archived_logs():
    result = LogController.get_archived_logs()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/archive/{filename}')
def download_archive(filename: str):
    result = LogController.download_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/archive/{filename}')
def delete_archive(filename: str):
    result = LogController.delete_archive(filename)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

from api_gateway.websocket.connection_manager import ws_router
