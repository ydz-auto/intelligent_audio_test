"""测试用例写操作 Service（CQRS Command Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
保留 Pydantic schema 校验。
"""
import json
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import testcase_config_service
from api_gateway.schemas.common import StringIdData
from api_gateway.schemas.testcase import (
    TestCaseStopPreviewData,
    TestCaseCreateSchema,
    TestCaseUpdateSchema,
    TestCaseBatchActionRequest,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

# reference_params 文件存储到 OSS（ref_params bucket）
_REF_PARAMS_BUCKET = 'ref_params'


def _build_ref_params_key(case_id, round_number, filename=None):
    """构建参考参数 OSS key：{case_id}/{filename} 或 {case_id}/round_{round_number}.json"""
    if filename is None:
        filename = f"round_{round_number}.json"
    return f"{case_id}/{filename}"


def _apply_reference_params_to_config(test_case) -> None:
    """为 test_case 逐轮生成参考参数并写入 OSS，路径存入 reference_params 独立列。

    替代 ReferenceParamsGenerator.apply_to_config，改为通过 gRPC 调用
    algorithm_service 生成每轮参考参数，存储逻辑仍在本地完成。
    """
    if not test_case:
        return

    config = test_case.config or {}
    rounds = config.get('rounds', [])

    if not rounds:
        return

    from shared.clients.grpc_clients import (
        algo_generate_reference_params,
        algo_get_all_reference_params,
    )

    case_id = getattr(test_case, 'id', '') or str(id(test_case))

    # 构建传入 gRPC 的 test_case_config（algorithm_type / config / test_type）
    test_case_config = {
        'algorithm_type': getattr(test_case, 'algorithm_type', None),
        'config': config,
        'test_type': getattr(test_case, 'test_type', 'api') or 'api',
    }

    ref_params_list = []
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue

        round_number = round_item.get('round_number') or round_item.get('roundNumber') or 1

        round_params = algo_generate_reference_params(test_case_config, round_item)
        if not round_params:
            continue

        round_params = algo_get_all_reference_params(round_params)

        oss_key = _build_ref_params_key(case_id, round_number)

        try:
            from shared.infrastructure.storage import storage_save_bytes
            data = json.dumps(round_params, ensure_ascii=False, indent=2).encode('utf-8')
            stored_path = storage_save_bytes(data, _REF_PARAMS_BUCKET, oss_key,
                                             content_type='application/json')
            ref_params_list.append({
                'round_number': round_number,
                'reference_params_path': stored_path
            })
        except Exception as e:
            logger.warning(f"round {round_number}: failed to upload {_REF_PARAMS_BUCKET}/{oss_key}: {e}")

    test_case.reference_params = ref_params_list


class TestCaseCommandService:
    """测试用例写操作 Service（CQRS Command Side）。

    网关侧只做 Pydantic 校验 + gRPC 调用，不直接操作 DB。
    """

    # 公共方法：刷新测试用例的ASR和翻译参考文本
    # 保留在网关侧：import_export_service 仍直接调用此方法（操作 ORM 对象）
    @staticmethod
    def refresh_reference_texts(test_case):
        """
        刷新测试用例的参考参数
        根据算法类型和测试用例配置，自动生成并更新config中的参考参数
        通过 gRPC 调用 algorithm_service 生成参考字段
        """
        _apply_reference_params_to_config(test_case)

    # 创建测试用例
    @staticmethod
    def create():
        try:
            data = TestCaseCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = testcase_config_service.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建测试用例失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(StringIdData(id=new_id), result.get('message', '测试用例创建成功'), http_code=201)

    # 更新测试用例信息
    @staticmethod
    def update(tc_id):
        try:
            data = TestCaseUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        if data.id and data.id != tc_id:
            return error_response("请求URL中的id与请求体中的id不一致")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = testcase_config_service.update(tc_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到测试用例", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(None, result.get('message', '测试用例更新成功'))

    # 删除测试用例（逻辑删除）
    @staticmethod
    def delete(tc_id):
        result = testcase_config_service.delete(tc_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到测试用例", 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '测试用例已删除'))

    # 复制测试用例
    @staticmethod
    def copy(tc_id):
        result = testcase_config_service.copy(tc_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到原始测试用例", 404)
            return error_response(result.get('message', '复制失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(StringIdData(id=new_id), result.get('message', '测试用例复制成功'), http_code=201)

    # 停止预览测试用例
    # 保留在网关侧：涉及跨服务编排（audio_service），非纯 DB 操作
    @staticmethod
    def stop_preview(tc_id):
        """停止预览测试用例：向音频引擎发送停止信号"""
        from api_gateway.infrastructure.grpc_proxies import audio_service
        preview_task_id = f"PREVIEW_{tc_id}"

        # 设置停止标志，通知播放线程停止（共享于 common 模块）
        common.preview_stop_flags[tc_id] = True

        # 停止音频播放 - 停止所有 PREVIEW_ 开头的任务
        try:
            audio_service.stop_task_audio_by_pattern("PREVIEW_")
        except AttributeError:
            # gRPC 服务不可用时忽略，本地预览已通过 preview_stop_flags 停止
            pass

        return success_response(TestCaseStopPreviewData(test_case_id=tc_id, status="preview_stopped", message="预览已停止"))

    # 批量操作
    @staticmethod
    def batch_action():
        """批量操作入口：验证请求并转发到 gRPC"""
        try:
            req_data = TestCaseBatchActionRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = testcase_config_service.batch_action(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            return error_response(result.get('message', '批量操作失败'), code=code)

        data = result.get('data')

        # 异步任务提交时返回 task_id
        if isinstance(data, dict) and data.get('task_id'):
            return success_response(data, result.get('message', '已提交异步任务'))

        return success_response(None, result.get('message', '批量操作执行成功'))

    # 更新参考参数
    @staticmethod
    def update_ref_params(tc_id, round_number):
        """更新指定用例指定轮的参考参数文件"""
        body = request.get_json()
        if not body:
            return error_response("请求体不能为空")

        result = testcase_config_service.update_ref_params(tc_id, round_number, body)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到测试用例'), 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(result.get('data'), result.get('message', '参考参数更新成功'))
