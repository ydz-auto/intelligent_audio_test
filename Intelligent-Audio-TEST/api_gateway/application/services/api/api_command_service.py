# -*- coding: utf-8 -*-
"""API 配置命令 Service（写侧 / CRUD）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 api_test_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.api import ApiCreateInput, ApiUpdateInput
from api_gateway.schemas.common import IdData
from api_gateway.application.services.api.proto_upload import (
    ProtoUploadError,
    check_content_length,
    normalize_filename,
    read_upload,
)
from api_gateway.infrastructure.acl import ApiConfigAclRepositoryImpl

_api_acl = ApiConfigAclRepositoryImpl()


class ApiCommandService:
    """API 配置写操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 写操作 ==========

    @staticmethod
    def parse_proto():
        """上传 .proto → 编译 + 落存储 + 回吐符号表（INT-1952 / A3 硬前置）。

        网关只做「预检 + 错误码映射」：编译与符号表在 api_test_service 的
        `ParseProto` RPC；HTTP 状态由业务码决定（400 内容类 / 503 存储不可用），
        不是一律 400。
        """
        if 'file' not in request.files:
            return error_response('未收到 proto 文件', http_code=400)

        upload = request.files['file']
        filename = normalize_filename(getattr(upload, 'filename', None))
        if not filename:
            return error_response('未收到 proto 文件', http_code=400)

        try:
            # 巨型 body 预检必须在调 RPC 之前（卡面 §6 第 1 条）
            check_content_length(request.headers.get('content-length'))
            content = read_upload(upload)
        except ProtoUploadError as exc:
            return error_response(str(exc), http_code=400)

        result = _api_acl.parse_proto(filename, content)
        if result.get('success'):
            return success_response(
                result.get('data'), result.get('message') or 'proto 解析成功')

        code = int(result.get('code') or 0)
        http_code = code if 400 <= code <= 599 else 400
        return error_response(result.get('message') or 'proto 解析失败',
                              http_code=http_code)

    @staticmethod
    def create():
        try:
            data = ApiCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        # 将 Pydantic 模型转为 dict，传给微服务
        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = _api_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 202:
                return error_response(result.get('message', '操作失败'), code=202)
            return error_response(result.get('message', '操作失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', 'API配置创建成功'), http_code=201)

    @staticmethod
    def update(api_id):
        try:
            data = ApiUpdateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = _api_acl.update(api_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(result.get('data'), result.get('message', 'API配置更新成功'))

    @staticmethod
    def delete(api_id):
        result = _api_acl.delete(api_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            if code == 202:
                return error_response(result.get('message', '操作失败'), code=202)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', 'API配置已删除'))
