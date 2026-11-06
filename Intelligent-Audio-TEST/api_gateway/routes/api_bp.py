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


# INT-1772 响应解析预览：贴样例响应 → 看 meta 解析器（result_parser /
# *_mapping）能提取出什么。纯函数实现，不读库、不发外部请求、无副作用
# （静态段，同样先于 /{api_id} 注册）
@router.post('/parse-preview')
def parse_preview(_: None = require_permission('api_config:read')):
    """解析预览（只读）：路径语义与执行期共用 shared/utils/path_extractor"""
    return to_response(ApiQueryService.parse_preview())


# INT-1952 proto 上传与符号解析（A3 / INT-1791 硬前置）：multipart file →
# 编译 + 内容寻址落存储 + 回吐 service / method / 字段符号表。
# 静态段，同样先于 /{api_id} 注册；权限与 /import 同为 api_config:create
@router.post('/proto')
def parse_proto(_: None = require_permission('api_config:create')):
    """上传 .proto（multipart 字段 file），返回符号表与存储元信息"""
    return to_response(ApiCommandService.parse_proto())


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
