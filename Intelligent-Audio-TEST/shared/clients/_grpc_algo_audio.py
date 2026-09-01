# -*- coding: utf-8 -*-
"""algorithm_service / audio_service gRPC 便捷封装（从 grpc_clients.py 拆分，P4-4）。

封装 algorithm_service.AlgorithmQueryService / AlgorithmDefinitionService 与
audio_service 的通用 RPC 调用，替代原 shared/algorithm 包。
"""
from shared.clients._grpc_stubs import (
    get_algorithm_config_service_stub,
    get_algorithm_definition_service_stub,
    get_audio_config_service_stub,
    get_audio_service_stub,
)


def call_algo_config_rpc(method_name: str, **kwargs):
    """通用调用 task_service.AlgorithmConfigService RPC，返回解析后的 data（dict/list）

    Args:
        method_name: RPC 方法名（如 'ListAlgorithms'）
        **kwargs: 请求字段

    Returns:
        解析后的 data 字段（dict 或 list），失败返回 None
    """
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_config_service_stub()
        req_cls = getattr(task_pb, f'{method_name}Request')
        req = req_cls(**kwargs)
        resp = getattr(stub, method_name)(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'gRPC {method_name} failed: {resp.message}', category='algorithm')
            return None
        return _loads(resp.data, {})
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'gRPC {method_name} exception: {e}', category='algorithm')
        return None


def list_reference_params(algorithm_type: str):
    """通过 gRPC 获取参考参数列表（algorithm_service.ListReferenceParams）

    Returns:
        参考参数 dict 列表，失败返回空列表
    """
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.proto import algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_definition_service_stub()
        req = _algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')
        resp = stub.ListReferenceParams(req)
        if resp.success:
            return (_loads(resp.data, {}) or {}).get('parameters', []) or []
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'list_reference_params failed: {e}', category='algorithm')
    return []


def get_audios_by_ids(audio_ids):
    """通过 gRPC 批量获取音频数据（audio_service.GetAudiosByIds）

    Returns:
        {audio_id: {...}, ...} 或空 dict
    """
    from shared.utils.log_handler import log_not_emit
    if not audio_ids:
        return {}
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        import json as _json
        req = e2e_pb.GetAudiosByIdsRequest(data=_json.dumps({"ids": list(audio_ids)}))
        resp = stub.GetAudiosByIds(req)
        data = _loads(resp.data, {})
        audio_map = {}
        for item in data.get('items', []):
            aid = item.get('id')
            audio_map[aid] = item
        return audio_map
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'get_audios_by_ids failed: {e}', category='algorithm')
        return {}


def get_audio_by_id(audio_id):
    """通过 gRPC 获取单个音频（audio_service.GetAudio）

    Returns:
        音频 dict 或 None
    """
    from shared.utils.log_handler import log_not_emit
    if not audio_id:
        return None
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        resp = stub.GetAudio(e2e_pb.GetAudioRequest(audio_id=int(audio_id)))
        if not resp.success:
            return None
        return _loads(resp.data, {}) or {}
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'get_audio_by_id failed: {e}', category='algorithm')
        return None


def audio_prepare_audios(audio_ids, playback_device_ids):
    """通过 gRPC 预下载并按设备目标采样率重采样音频（audio_service.PrepareAudios）

    Args:
        audio_ids: 音频 ID 列表 [int, ...]
        playback_device_ids: 播放设备 ID 列表 [int|str, ...]

    Returns:
        嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}} 或空 dict
    """
    from shared.utils.log_handler import log_not_emit
    if not audio_ids:
        return {}
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps
        stub = get_audio_service_stub()
        req = e2e_pb.PrepareAudiosRequest(
            data=_dumps({
                'audio_ids': list(audio_ids),
                'playback_device_ids': list(playback_device_ids or []),
            }),
        )
        resp = stub.PrepareAudios(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'PrepareAudios failed: {resp.message}', category='algorithm')
            return {}
        return _loads(resp.data, {}) or {}
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'audio_prepare_audios failed: {e}', category='algorithm')
        return {}


# ==================== algorithm query 便捷封装（迁移自 shared/algorithm）====================

def _call_algo_query_rpc(method_name: str, **kwargs):
    """通用调用 algorithm_service.AlgorithmQueryService RPC，返回解析后的 data

    Args:
        method_name: RPC 方法名
        **kwargs: 请求字段

    Returns:
        解析后的 data 字段（dict/list），失败返回 None
    """
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.utils.grpc_json import loads as _loads
        from shared.clients._grpc_stubs import get_algorithm_query_service_stub
        stub = get_algorithm_query_service_stub()
        from shared.proto import algorithm_service_pb2 as _algo_pb2
        req_cls = getattr(_algo_pb2, f'{method_name}Request')
        req = req_cls(**kwargs)
        resp = getattr(stub, method_name)(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'AlgorithmQuery {method_name} failed: {resp.message}', category='algorithm')
            return None
        return _loads(resp.data, {})
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'AlgorithmQuery {method_name} exception: {e}', category='algorithm')
        return None


def algo_get_algorithm_config(algorithm_type: str):
    """获取算法定义配置（含 device/api/case params + mappings）"""
    return _call_algo_query_rpc('GetAlgorithmConfig', algorithm_type=algorithm_type or '')


def algo_get_all_algorithms():
    """获取所有在线算法列表"""
    return _call_algo_query_rpc('GetAllAlgorithmsList') or []


def algo_get_device_params(algorithm_type: str):
    """获取设备参数列表"""
    return _call_algo_query_rpc('GetDeviceParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_api_params(algorithm_type: str):
    """获取 API 参数列表"""
    return _call_algo_query_rpc('GetApiParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_case_params(algorithm_type: str):
    """获取用例参数列表"""
    return _call_algo_query_rpc('GetCaseParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_reference_params_list(algorithm_type: str):
    """获取参考参数列表"""
    return _call_algo_query_rpc('GetReferenceParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_param_mapping(algorithm_type: str, component_type: str):
    """获取参数映射"""
    return _call_algo_query_rpc('GetParamMappingForComponent',
                               algorithm_type=algorithm_type or '',
                               component_type=component_type or '') or []


def algo_get_evaluation_dimension_params(dimension_id: int):
    """获取评估维度参数"""
    return _call_algo_query_rpc('GetEvaluationDimensionParams', dimension_id=int(dimension_id)) or []


def algo_get_algorithm_definition(algorithm_type: str):
    """获取算法定义信息"""
    return _call_algo_query_rpc('GetAlgorithmDefinitionInfo', algorithm_type=algorithm_type or '')


def algo_reload_config():
    """重新加载算法配置缓存"""
    return _call_algo_query_rpc('ReloadConfig')


def algo_get_field_mappings(algorithm_type: str):
    """获取字段定义（original + mapped），返回 FieldMapperWrapper"""
    from shared.utils.field_mapper_wrapper import FieldMapperWrapper
    data = _call_algo_query_rpc('GetFieldMappings', algorithm_type=algorithm_type or '') or {}
    return FieldMapperWrapper(data)


def algo_get_evaluation_field_mappings(algorithm_type: str):
    """获取评估字段映射"""
    return _call_algo_query_rpc('GetEvaluationFieldMappings', algorithm_type=algorithm_type or '') or {}


def algo_build_api_request_data(algorithm_type: str, device_params=None, api_params=None, case_config=None, **kwargs):
    """构建 API 请求参数"""
    import json as _json
    data = _json.dumps({
        'device_params': device_params or {},
        'api_params': api_params or {},
        'case_config': case_config or {},
        'kwargs': kwargs,
    }, ensure_ascii=False)
    return _call_algo_query_rpc('BuildApiRequestData', algorithm_type=algorithm_type or '', data=data) or {}


def algo_convert_field_value(transform_type: str, value):
    """转换字段值"""
    import json as _json
    return _call_algo_query_rpc('ConvertFieldValue',
                               transform_type=transform_type or 'none',
                               data=_json.dumps({'value': value}, ensure_ascii=False))


def algo_get_output_fields(algorithm_type: str, test_type: str = None):
    """获取结果输出字段"""
    return _call_algo_query_rpc('GetOutputFields',
                               algorithm_type=algorithm_type or '',
                               test_type=test_type or '') or []


def algo_get_reference_output_fields(algorithm_type: str):
    """获取参考输出字段"""
    return _call_algo_query_rpc('GetReferenceOutputFields', algorithm_type=algorithm_type or '') or []


def algo_extract_result_fields(algorithm_type: str, algorithm_result=None, result_data=None):
    """从算法结果中提取字段"""
    import json as _json
    return _call_algo_query_rpc('ExtractResultFields',
                               algorithm_type=algorithm_type or '',
                               algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False),
                               result_data=_json.dumps(result_data or {}, ensure_ascii=False)) or {}


def algo_get_timeline_fields(algorithm_type: str):
    """获取时间线字段"""
    return _call_algo_query_rpc('GetTimelineFields', algorithm_type=algorithm_type or '') or []


def algo_get_full_field_mapping(algorithm_type: str):
    """获取完整字段映射"""
    return _call_algo_query_rpc('GetFullFieldMapping', algorithm_type=algorithm_type or '') or {}


def algo_map_api_results(algorithm_type: str, raw_results=None, test_type: str = None):
    """映射 API 结果"""
    import json as _json
    return _call_algo_query_rpc('MapApiResults',
                               algorithm_type=algorithm_type or '',
                               raw_results=_json.dumps(raw_results or {}, ensure_ascii=False),
                               test_type=test_type or '') or {}


def algo_extract_round_results(algorithm_result=None, test_type: str = None):
    """提取轮次结果"""
    import json as _json
    return _call_algo_query_rpc('ExtractRoundResults',
                               algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False),
                               test_type=test_type or '') or []


def algo_extract_case_all_params(case_config=None):
    """提取用例全部参数"""
    import json as _json
    return _call_algo_query_rpc('ExtractCaseAllParams',
                               case_config=_json.dumps(case_config or {}, ensure_ascii=False)) or {}


def algo_normalize_algorithm_params(algorithm_params=None):
    """规范化算法参数为 dict"""
    import json as _json
    return _call_algo_query_rpc('NormalizeAlgorithmParams',
                               algorithm_params=_json.dumps(algorithm_params or {}, ensure_ascii=False)) or {}


def algo_normalize_algorithm_params_to_list(algorithm_params=None):
    """规范化算法参数为 list"""
    import json as _json
    return _call_algo_query_rpc('NormalizeAlgorithmParamsToList',
                               algorithm_params=_json.dumps(algorithm_params or [], ensure_ascii=False)) or []


def algo_get_round_algo_params(algorithm_params_col=None, round_number: int = 0):
    """获取指定轮次算法参数"""
    import json as _json
    return _call_algo_query_rpc('GetRoundAlgoParams',
                               algorithm_params_col=_json.dumps(algorithm_params_col or [], ensure_ascii=False),
                               round_number=int(round_number)) or {}


def algo_get_algo_param(algorithm_params=None, field_code: str = ''):
    """从参数列表获取指定字段值"""
    import json as _json
    result = _call_algo_query_rpc('GetAlgoParam',
                                  algorithm_params=_json.dumps(algorithm_params or [], ensure_ascii=False),
                                  field_code=field_code)
    return result.get('value') if result else None


def algo_build_case_form_schema(algorithm_type: str):
    """构建用例表单 schema"""
    return _call_algo_query_rpc('BuildCaseFormSchema', algorithm_type=algorithm_type or '') or {}


def algo_generate_reference_params(test_case_config=None, round_data=None):
    """生成参考参数"""
    import json as _json
    data = _json.dumps({
        'test_case_config': test_case_config or {},
        'round_data': round_data or {},
    }, ensure_ascii=False)
    return _call_algo_query_rpc('GenerateReferenceParams', data=data) or []


def algo_load_reference_params_file(filepath: str = ''):
    """从 OSS 加载参考参数"""
    return _call_algo_query_rpc('LoadReferenceParamsFile', filepath=filepath or '') or []


def algo_get_reference_text(reference_params_col=None, code: str = ''):
    """获取参考文本"""
    import json as _json
    result = _call_algo_query_rpc('GetReferenceTextValue',
                                  reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False),
                                  code=code or '')
    return result.get('text', '') if result else ''


def algo_get_all_reference_params(reference_params_col=None):
    """获取所有参考参数"""
    import json as _json
    return _call_algo_query_rpc('GetAllReferenceParams',
                               reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False)) or []


def algo_get_reference_params_for_report(reference_params_col=None):
    """获取报告用参考参数"""
    import json as _json
    return _call_algo_query_rpc('GetReferenceParamsForReport',
                               reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False)) or {}
