from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.api.api_query_service import ApiQueryService
from api_gateway.application.services.api.api_command_service import ApiCommandService
from api_gateway.application.services.device.device_import_export_service import ResourceImportExportService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all():
    return to_response(ApiQueryService.get_all())


# INT-816 导入导出（静态段，须先于 /{api_id} 注册；现有端点缺权限门槛，
# 新增端点必须带 require_permission，见 UX 规范 §11-10 / FEAT INT-759 审计）
@router.get('/export')
def export_apis(_: None = require_permission('api_config:read')):
    """导出 API 配置（json/excel 文件流，ids/format 可选；CQRS 查询侧无副作用）"""
    return to_response(ResourceImportExportService.export('apis'))


@router.post('/import')
def import_apis(_: None = require_permission('api_config:create')):
    """导入 API 配置（multipart 文件），按 name 匹配更新/新建/跳过"""
    return to_response(ResourceImportExportService.import_resource('apis'))


@router.get('/{api_id}')
def get_one(api_id: int):
    return to_response(ApiQueryService.get_one(api_id))


@router.post('')
def create():
    return to_response(ApiCommandService.create())


@router.put('/{api_id}')
def update(api_id: int):
    return to_response(ApiCommandService.update(api_id))


@router.delete('/{api_id}')
def delete(api_id: int, _: None = require_permission('api_config:delete')):
    return to_response(ApiCommandService.delete(api_id))


@router.post('/{api_id}/health')
def health_check(api_id: int, _: None = require_permission('api_config:read')):
    return to_response(ApiQueryService.health_check(api_id))


@router.api_route('/{api_id}/test', methods=['POST', 'GET'])
def test_connection(api_id: int):
    return to_response(ApiQueryService.test_connection(api_id))


@router.post('/{api_id}/stop-test')
def stop_test(api_id: int, _: None = require_permission('api_config:test')):
    return to_response(ApiQueryService.stop_test(api_id))
