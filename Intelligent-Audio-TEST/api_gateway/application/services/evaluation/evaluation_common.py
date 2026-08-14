"""评估维度共享私有辅助函数。

这些函数从 EvaluationController 中抽取，供多个 service 共用。
原为 evaluation_controller.py 模块级函数，现改为集中放置以简化跨 service 引用。
"""
import json
import re


def _sync_body_template(api_settings, param_codes):
    """
    根据 param_codes 同步 api_settings 中的 body_template。
    - 新增参数：添加 "{{param_code}}" 占位符
    - 删除参数：移除对应的占位符
    - 静态字段（非 {{xxx}} 格式的值）保持不变
    """
    if not param_codes:
        return api_settings

    if api_settings is None:
        api_settings = {}
    if not isinstance(api_settings, dict):
        return api_settings

    body_template = api_settings.get('body_template')

    # 解析 body_template 为 dict
    if body_template is None:
        bt_dict = {}
    elif isinstance(body_template, str):
        try:
            bt_dict = json.loads(body_template) if body_template.strip() else {}
        except json.JSONDecodeError:
            bt_dict = {}
    elif isinstance(body_template, dict):
        bt_dict = dict(body_template)
    else:
        bt_dict = {}

    param_set = set(param_codes)

    # 移除已删除参数对应的占位符（值为 {{xxx}} 且 xxx 不在 param_set 中）
    placeholder_re = re.compile(r'^\{\{(\w+)\}\}$')
    keys_to_remove = []
    for key, value in bt_dict.items():
        if isinstance(value, str):
            match = placeholder_re.match(value)
            if match and match.group(1) not in param_set:
                keys_to_remove.append(key)
    for key in keys_to_remove:
        del bt_dict[key]

    # 添加新参数的占位符
    for code in param_codes:
        if code not in bt_dict:
            bt_dict[code] = f"{{{{{code}}}}}"

    # 写回 body_template（保持与原始类型一致）
    if isinstance(body_template, str):
        api_settings['body_template'] = json.dumps(bt_dict, ensure_ascii=False)
    else:
        api_settings['body_template'] = bt_dict

    return api_settings


def _get_default_algorithm_type(associated_algorithms):
    """从关联算法列表取默认（或第一个）算法的 type，回落到 voice_llm"""
    if not associated_algorithms:
        return 'voice_llm'
    for algo in associated_algorithms:
        if isinstance(algo, dict):
            if algo.get('isDefault'):
                return algo.get('algorithmType') or algo.get('algorithm_type') or 'voice_llm'
    # 没有标记默认的，取第一个
    for algo in associated_algorithms:
        if isinstance(algo, dict):
            return algo.get('algorithmType') or algo.get('algorithm_type') or 'voice_llm'
        return algo or 'voice_llm'
    return 'voice_llm'


def _sync_param_mappings(dimension_id, params, direction='output', algorithm_type='voice_llm'):
    """
    同步 ParamMapping：当评估维度的输入/输出字段变更时，
    自动为该维度创建/更新/删除对应的 ParamMapping 记录。

    映射规则：source='evaluation', source_param=param_code,
              dimension_id=dimension_id, target_param=param_code,
              source_direction=direction (input/output),
              algorithm_type=维度的关联算法类型（如 voice_llm）

    通过 gRPC 调用 algorithm_service.AlgorithmDefinitionService.SyncParamMappings，
    替代直连 algorithm_service PO（ParamMapping）。
    """
    if params is None:
        return

    from api_gateway.infrastructure.grpc_proxies import algorithm_query_service as _algo_svc
    from shared.proto import algorithm_service_pb2 as algo_pb

    data = {
        'params': params,
        'direction': direction,
        'algorithm_type': algorithm_type,
    }
    try:
        stub = _algo_svc.definition_stub
        resp = stub.SyncParamMappings(algo_pb.SyncParamMappingsRequest(
            dimension_id=int(dimension_id),
            data=json.dumps(data, ensure_ascii=False, default=str),
        ))
        if not resp.success:
            import logging
            logging.getLogger(__name__).warning(
                'SyncParamMappings gRPC 调用失败: %s', resp.message
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('SyncParamMappings failed: %s', e)
