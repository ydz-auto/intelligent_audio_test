# -*- coding: utf-8 -*-
"""任务数据导入导出代理（api_gateway → task_service DataTransferService，INT-25）

JSON 信封编解码 + 通用异常包装。ZIP 不走 gRPC：
- 导出：task_service 落盘共享目录，网关按返回的 zip_path FileResponse 下发
- 导入：网关把上传 ZIP 落盘共享目录，仅传 zip_path 给 task_service
"""
import json
import logging

from shared.clients.grpc_clients import get_data_transfer_service_stub
from shared.proto import task_service_pb2 as task_pb
from api_gateway.infrastructure.grpc_proxies._common import _grpc_call, _logger

# ExecuteImport 为长耗时调用（含跨服务分段导入 + 文件回写），
# 网关同步等待回包，超时放宽到 1 小时；进度经 Redis → SocketIO 通道可见。
_EXECUTE_TIMEOUT_SECONDS = 3600
_DEFAULT_TIMEOUT_SECONDS = 120


class _DataTransferProxy:
    """DataTransferService gRPC 代理"""

    @staticmethod
    def _resp(resp) -> dict:
        try:
            data = json.loads(resp.data) if resp.data else None
        except (ValueError, TypeError):
            _logger.warning("DataTransfer 响应 data 非法 JSON: %r", resp.data[:200])
            data = None
        return {'success': resp.success, 'message': resp.message, 'data': data}

    def export_tasks(self, data: dict) -> dict:
        """导出任务数据。data: {task_ids, options:{include_ref_params, include_audios}}"""
        def _call():
            stub = get_data_transfer_service_stub()
            resp = stub.ExportTasks(task_pb.ExportTasksRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str)),
                timeout=_DEFAULT_TIMEOUT_SECONDS)
            return self._resp(resp)
        return _grpc_call(_call, default_return=lambda e: {
            'success': False, 'message': f'导出任务数据失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='导出任务数据失败')

    def preview_import(self, zip_path: str) -> dict:
        """导入预检（zip 在共享盘 DATA_TRANSFER_TMP_DIR/import/ 下）"""
        def _call():
            stub = get_data_transfer_service_stub()
            resp = stub.PreviewImport(task_pb.PreviewImportRequest(zip_path=zip_path),
                                      timeout=_DEFAULT_TIMEOUT_SECONDS)
            return self._resp(resp)
        return _grpc_call(_call, default_return=lambda e: {
            'success': False, 'message': f'导入预检失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='导入预检失败')

    def execute_import(self, zip_path: str) -> dict:
        """执行导入（长耗时，timeout=3600s；进度走 Redis → SocketIO）"""
        def _call():
            stub = get_data_transfer_service_stub()
            resp = stub.ExecuteImport(task_pb.ExecuteImportRequest(zip_path=zip_path),
                                      timeout=_EXECUTE_TIMEOUT_SECONDS)
            return self._resp(resp)
        return _grpc_call(_call, default_return=lambda e: {
            'success': False, 'message': f'执行导入失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='执行导入失败')

    def get_progress_snapshot(self) -> dict:
        """最近一次导入进度快照（GET /import/progress 兜底）

        直读 Redis HASH（task_service 写入），不经 gRPC。
        快照为兜底只读通道：Redis 不可用时按仓库读路径约定降级为
        success=True + data=None，不以 500 阻断前端。
        """
        def _call():
            from shared.utils.redis_pubsub import RedisStore
            from shared.constants.data_transfer import REDIS_PROGRESS_KEY
            try:
                snapshot = RedisStore().load_task(REDIS_PROGRESS_KEY)
            except Exception as e:
                _logger.warning("读取导入进度快照失败（降级为空）: %s", e)
                snapshot = {}
            return {'success': True, 'message': '', 'data': snapshot or None}
        return _grpc_call(_call, default_return=lambda e: {
            'success': True, 'message': '', 'data': None},
            error_msg_prefix='读取导入进度失败')


data_transfer_service = _DataTransferProxy()
