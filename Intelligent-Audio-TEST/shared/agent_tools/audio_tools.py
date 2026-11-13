# -*- coding: utf-8 -*-
"""音频域写意图工具分组（INT-2467，方案 §6.1 / §9.4）。

两个写工具：

- ``audio_import``（WRITE，``audio:upload``）：URL 导入、上传初始化 / 合并 /
  OSS 直传确认。动作直接映射共享 MCP 注册表里同名的 ``audio_*`` 写工具，
  REST 路径与请求体仍由 ``mcp_registry.build_path`` / ``build_body`` 决定，
  本模块只做「意图参数 → 目标 REST 参数」的归一与校验。
- ``audio_annotate``（WRITE，``audio:update``）：批量标注、元数据、算法配置。

为什么映射 MCP 条目而不是另写路由：外部 MCP 与内部 Agent 共用同一份 Schema
（§6.2 / 模块 ``mcp_registry`` 顶部约定），复制路径会产生第二份契约。

写执行口径（§5.2 / §9.4，INT-2466）：本模块只解析目标请求；真正的副作用由
Loop 先落 ``agent_approval``、经审批人批准后由 ToolGateway 带审批凭据执行。
本模块不做任何网络调用、不落库。

边界（与人工页面一致）：

- 分片上传的**二进制字节**不经 Agent 通道（HTTP chunk 上传是 multipart 文件流，
  非 JSON 文本通道），所以 Agent 能做的「上传」只有：初始化上传任务、合并已在
  服务端/OSS 上的分片、OSS 直传完成确认；字节由宿主页面或直传客户端放上去。
- ``PUT /audios/batch/algorithms`` 被网关的 ``/{audio_id}/algorithms`` 抢先匹配
  （URL 不可达，见 ``mcp_registry`` 顶部边界），因此算法配置只做**单音频**
  ``set_algorithms``，批量算法请逐个调用。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.agent_tools import mcp_registry

AUDIO_UPLOAD = ('audio:upload',)
AUDIO_UPDATE = ('audio:update',)

# 导入动作 → 共享 MCP 注册表的写工具名
AUDIO_IMPORT_ACTIONS: Dict[str, str] = {
    'url_import': 'audio_url_import',
    'upload_init': 'audio_upload_init',
    'upload_merge': 'audio_upload_merge',
    'confirm': 'audio_upload_complete_direct',
}

# 标注动作 → 共享 MCP 注册表的写工具名
AUDIO_ANNOTATE_ACTIONS: Dict[str, str] = {
    'batch_annotate': 'audio_batch_annotations',
    'update_meta': 'audio_update_metadata',
    'set_algorithms': 'audio_update_algorithms',
}

# 动作支持的可选参数白名单（动作独立口径）。网关写接口的 Schema 基类
# ``APIModel`` 是 ``extra='ignore'``：不认识的字段被静默丢弃，工具层先拒，
# 避免模型以为「传了就会生效」。
AUDIO_IMPORT_PARAMS: Dict[str, Tuple[str, ...]] = {
    'url_import': ('url', 'relative_path', 'audio_type'),
    'upload_init': (),
    # 合并请求体是宿主上传流程的完整载荷（file_id / task_id / 用例配置等），
    # 以整体 body 透传，避免在意图层复制 30+ 字段的第二份口径。
    'upload_merge': ('body',),
    'confirm': ('oss_key', 'upload_id', 'filename', 'md5', 'file_size',
                'duration', 'sample_rate', 'tags', 'audio_type', 'asr_text'),
}
AUDIO_ANNOTATE_PARAMS: Dict[str, Tuple[str, ...]] = {
    'batch_annotate': ('items', 'algorithm_type', 'refresh_test_cases'),
    'update_meta': ('metadata',),
    'set_algorithms': ('algorithms',),
}

# 动作的必填参数（含路径参数；Schema 无法表达的条件必填）
AUDIO_IMPORT_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'url_import': ('url',),
    'upload_init': (),
    'upload_merge': ('body',),
    'confirm': ('oss_key', 'filename'),
}
AUDIO_ANNOTATE_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'batch_annotate': ('items',),
    'update_meta': ('audio_id', 'metadata'),
    'set_algorithms': ('audio_id', 'algorithms'),
}

# ``PUT /audios/{audio_id}/metadata`` 的 UpdateMetadataRequest 只认这些字段
# （``tags`` 在该接口是**字符串**，不是数组）；其余字段服务端静默丢弃。
AUDIO_METADATA_FIELDS: Tuple[str, ...] = (
    'name', 'audio_type', 'asr_text', 'description', 'source_language',
    'tags', 'annotations')

# ``upload_merge`` 的 MergeChunksRequest 两个必填字段
UPLOAD_MERGE_REQUIRED_BODY: Tuple[str, ...] = ('file_id', 'task_id')

# 音频上传 / 标注动作的权限（工具级与动作级同域）
AUDIO_IMPORT_PERMISSIONS: Tuple[str, ...] = AUDIO_UPLOAD
AUDIO_ANNOTATE_PERMISSIONS: Tuple[str, ...] = AUDIO_UPDATE


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _normalize_batch_items(items: Any) -> Optional[str]:
    """``batch_annotate`` 的 items 逐项校验（对齐 BatchAnnotationItem）。"""
    if not isinstance(items, list) or not items:
        return '参数 items 必须是非空数组（每项 {audio_id, annotations?, tags?}）'
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return f'参数 items[{index}] 必须是对象'
        unknown = sorted(set(item) - {'audio_id', 'annotations', 'tags'})
        if unknown:
            return f'参数 items[{index}] 含不支持字段：{"、".join(unknown)}'
        if not _positive_int(item.get('audio_id')):
            return f'参数 items[{index}].audio_id 必须是正整数'
        annotations = item.get('annotations')
        if annotations is not None and not isinstance(annotations, list):
            return f'参数 items[{index}].annotations 必须是数组'
        tags = item.get('tags')
        if tags is not None and (
                not isinstance(tags, list)
                or any(not isinstance(tag, str) for tag in tags)):
            return f'参数 items[{index}].tags 必须是字符串数组'
    return None


def _normalize_metadata(metadata: Any) -> Optional[str]:
    """``update_meta`` 的字段白名单（服务端 ``extra='ignore'``，不静默透传）。"""
    if not isinstance(metadata, dict) or not metadata:
        return f'参数 metadata 必须是非空对象（可用字段：{"、".join(AUDIO_METADATA_FIELDS)}）'
    unknown = sorted(set(metadata) - set(AUDIO_METADATA_FIELDS))
    if unknown:
        return (f'参数 metadata 含不支持字段：{"、".join(unknown)}'
                f'（可用：{"、".join(AUDIO_METADATA_FIELDS)}）')
    tags = metadata.get('tags')
    if tags is not None and not isinstance(tags, str):
        return '参数 metadata.tags 必须是字符串（该接口的 tags 不是数组）'
    annotations = metadata.get('annotations')
    if annotations is not None and not isinstance(annotations, list):
        return '参数 metadata.annotations 必须是数组'
    return None


def _normalize_algorithms(algorithms: Any) -> Optional[str]:
    """``set_algorithms`` 逐项校验（AudioAlgorithmRelationItem）。"""
    if not isinstance(algorithms, list) or not algorithms:
        return '参数 algorithms 必须是非空数组（每项 {algorithm_type, is_primary?, weight?, params?}）'
    fields = {'algorithm_type', 'is_primary', 'weight', 'params'}
    for index, item in enumerate(algorithms):
        if not isinstance(item, dict):
            return f'参数 algorithms[{index}] 必须是对象'
        unknown = sorted(set(item) - fields)
        if unknown:
            return f'参数 algorithms[{index}] 含不支持字段：{"、".join(unknown)}'
        algorithm_type = str(item.get('algorithm_type') or '').strip()
        if not algorithm_type:
            return f'参数 algorithms[{index}].algorithm_type 不能为空'
        is_primary = item.get('is_primary')
        if is_primary is not None and not isinstance(is_primary, bool):
            return f'参数 algorithms[{index}].is_primary 必须是布尔值'
        weight = item.get('weight')
        if weight is not None and (
                isinstance(weight, bool) or not isinstance(weight, (int, float))):
            return f'参数 algorithms[{index}].weight 必须是数值'
        params = item.get('params')
        if params is not None and not isinstance(params, dict):
            return f'参数 algorithms[{index}].params 必须是对象'
    return None


def _build_body(action: str, merged: Dict[str, Any]) -> Tuple[Optional[dict],
                                                              Optional[str]]:
    """按动作把意图参数折成 REST 请求体；返回 ``(body, 错误文本)``。"""
    if action == 'upload_init':
        # InitUploadTaskRequest 是空对象：不传 body 即是合法请求。
        return None, None
    if action == 'upload_merge':
        body = merged.get('body')
        if not isinstance(body, dict):
            return None, '参数 body 必须是对象（MergeChunksRequest 请求体）'
        missing = [key for key in UPLOAD_MERGE_REQUIRED_BODY
                   if body.get(key) in (None, '')]
        if missing:
            return None, f'参数 body 缺少必填字段：{"、".join(missing)}'
        return dict(body), None
    if action == 'url_import':
        body = {key: merged[key] for key in AUDIO_IMPORT_PARAMS[action]
                if key in merged and merged[key] is not None}
        url = str(body.get('url') or '').strip()
        if not url:
            return None, '参数 url 不能为空'
        body['url'] = url
        return body, None
    if action == 'confirm':
        body = {key: merged[key] for key in AUDIO_IMPORT_PARAMS[action]
                if key in merged and merged[key] is not None}
        return body, None
    if action == 'batch_annotate':
        error = _normalize_batch_items(merged.get('items'))
        if error:
            return None, error
        body = {'items': merged['items']}
        for key in ('algorithm_type', 'refresh_test_cases'):
            if merged.get(key) is not None:
                body[key] = merged[key]
        return body, None
    if action == 'update_meta':
        error = _normalize_metadata(merged.get('metadata'))
        if error:
            return None, error
        return dict(merged['metadata']), None
    if action == 'set_algorithms':
        error = _normalize_algorithms(merged.get('algorithms'))
        if error:
            return None, error
        return {'algorithms': merged['algorithms']}, None
    return None, f'不支持的音频写动作：action={action}'


def resolve_call(tool: str, arguments: Dict[str, Any]
                 ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把 ``audio_import`` / ``audio_annotate`` 调用解析为
    ``(目标工具, 合并参数, 错误文本)``；错误文本非空时不得发出请求。
    """
    table = AUDIO_IMPORT_ACTIONS if tool == 'audio_import' else AUDIO_ANNOTATE_ACTIONS
    params_table = (AUDIO_IMPORT_PARAMS if tool == 'audio_import'
                    else AUDIO_ANNOTATE_PARAMS)
    required_table = (AUDIO_IMPORT_REQUIRED if tool == 'audio_import'
                      else AUDIO_ANNOTATE_REQUIRED)
    action = arguments.get('action')
    if action not in table:
        return None, None, (
            f'action 取值必须是 {"/".join(table)} 之一')
    missing = [name for name in required_table.get(action, ())
               if arguments.get(name) is None]
    if missing:
        return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'
    allowed = set(params_table.get(action, ())) | set(required_table.get(action, ()))
    merged = {key: value for key, value in arguments.items()
              if key != 'action' and value is not None}
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return None, None, (
            f'action={action} 不支持参数：{"、".join(unknown)}'
            '（服务端会静默忽略这些字段）')
    body, error = _build_body(action, merged)
    if error:
        return None, None, error

    target = mcp_registry.get_tool(table[action])
    if target is None:  # pragma: no cover - 注册表内部一致性防御
        return None, None, f'工具映射失效：{tool}.{action}'
    rest_args: Dict[str, Any] = {}
    if action in ('update_meta', 'set_algorithms'):
        # 两个动作都是 ``/{audio_id}/...``，audio_id 走路径参数
        rest_args['audio_id'] = merged['audio_id']
    if body is not None:
        rest_args['body'] = body
    return target, rest_args, None


__all__ = [
    'AUDIO_ANNOTATE_ACTIONS', 'AUDIO_ANNOTATE_PARAMS',
    'AUDIO_ANNOTATE_PERMISSIONS', 'AUDIO_ANNOTATE_REQUIRED',
    'AUDIO_IMPORT_ACTIONS', 'AUDIO_IMPORT_PARAMS',
    'AUDIO_IMPORT_PERMISSIONS', 'AUDIO_IMPORT_REQUIRED',
    'AUDIO_METADATA_FIELDS', 'AUDIO_UPDATE', 'AUDIO_UPLOAD',
    'UPLOAD_MERGE_REQUIRED_BODY', 'resolve_call',
]
