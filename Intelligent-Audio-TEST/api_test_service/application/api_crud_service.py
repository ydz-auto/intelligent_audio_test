# -*- coding: utf-8 -*-
"""API 配置 CRUD 应用服务

把原 api_gateway 的 ApiCommandService / ApiQueryService 业务逻辑下沉到微服务。
- 不再依赖 request 对象，改为接收 dict 参数
- 返回 dict（{success, message, data, code}），由 servicer 层包装为 gRPC 响应
- 校验逻辑（_validate_api_data 等）一并下沉
"""
import time
import logging
import requests
import websocket
from urllib.parse import urlparse

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from shared.models.common_enums import (
    OutputType, AudioBitDepth, AudioContainer, APIProtocol,
    normalize_protocol, is_protocol_streaming_available,
)
from api_test_service.domain.entities.api import (
    normalize_output_types,
    normalize_audio_config,
    redact_endpoint_keys,
)
from api_test_service.infrastructure.adapters.proxy_utils import (
    build_proxy_url,
    validate_proxy,
    websocket_proxy_kwargs,
)
from api_gateway.application.services.stats_cache import refresh_stats_cache
from api_test_service.infrastructure.persistence.api_test_repository import api_test_repository
from api_test_service.infrastructure.persistence.api_rms_spl_repository import ApiRmsSplRepositoryImpl

logger = logging.getLogger(__name__)

# audio_config 目标采样率合法取值（01_UseCase总览.md §0.4）
_AUDIO_SAMPLE_RATES = (8000, 16000, 24000, 48000)
# 位深数字与枚举别名对应（UC-0901 用数字 16，08_混音与SPL映射.md §2.2 用 s16）
_BIT_DEPTH_ALIASES = {16: AudioBitDepth.S16, 24: AudioBitDepth.S24, 32: AudioBitDepth.S32}
# 密钥池上限（INT-1177 审计 D1/D2，endpoint 级沿用 INT-1230 审计 D1'）
_MAX_API_KEYS = 20


class APICrudService:
    """API 配置 CRUD 应用服务（写侧 + 读侧）"""

    # ========== 校验辅助 ==========

    @staticmethod
    def _validate_api_data(data):
        """验证 API 配置数据"""
        meta = data.get('meta')
        if meta is not None and not isinstance(meta, dict):
            return "元数据 (meta) 必须是一个 JSON 对象"

        if data.get('default_max_process') is not None:
            val = data['default_max_process']
            if not isinstance(val, int) or val < 1 or val > 100:
                return "默认最大并发数 (default_max_process) 必须在 1-100 之间"

        if data.get('default_max_timeout') is not None:
            val = data['default_max_timeout']
            if not isinstance(val, int) or val < 1 or val > 3000:
                return "默认最大超时时间 (default_max_timeout) 必须在 1-3000 之间"

        if data.get('default_max_audio_duration') is not None:
            val = data['default_max_audio_duration']
            if not isinstance(val, int) or val < 1 or val > 36000:
                return "默认最大音频时长 (default_max_audio_duration) 必须在 1-36000 之间"

        if data.get('output_types') is not None:
            if not isinstance(data['output_types'], list):
                return "输出类型列表 (output_types) 必须是一个数组"
            valid_values = {item.value for item in OutputType}
            invalid = [v for v in data['output_types'] if v not in valid_values]
            if invalid:
                return (f"非法的输出类型 (output_types): {', '.join(map(str, invalid))}，"
                        f"仅支持: {', '.join(valid_values)}")

        # INT-1799（B0 裁定）：device_type 已废弃——写请求携带非空值一律 400，
        # 不再做值域校验（协议与流式性由 protocol / streaming 两列承载）
        device_type = data.get('device_type')
        if device_type not in (None, ''):
            return "device_type 已废弃，请改用 protocol + streaming"

        protocol = data.get('protocol')
        if protocol is not None:
            try:
                normalize_protocol(protocol)
            except ValueError as e:
                return str(e)

        streaming = data.get('streaming')
        if streaming is not None and not isinstance(streaming, bool):
            return "流式性 (streaming) 必须为布尔值"

        adapter_class = data.get('adapter_class')
        if adapter_class is not None:
            if not isinstance(adapter_class, str) or len(adapter_class) > 100:
                return "适配器类名 (adapter_class) 必须为不超过 100 字符的字符串"

        audio_config = data.get('audio_config')
        if audio_config is not None:
            if not isinstance(audio_config, dict):
                return "音频配置 (audio_config) 必须是一个 JSON 对象"
            error = APICrudService._validate_audio_config(audio_config)
            if error:
                return error

        proxy_error = validate_proxy(data.get('proxy_type'), data.get('proxy_url'))
        if proxy_error:
            return proxy_error

        return None

    @staticmethod
    def _validate_lane_combo(protocol, streaming):
        """协议 × 流式性可用矩阵校验（INT-1799 / B0 裁定 §3.2.3）。

        只放行已实现执行器的组合（http+非流式、websocket+流式）；其余组合
        显式拒绝，文案固定，不静默降级。protocol 需已归一为规范值。
        """
        try:
            normalized = normalize_protocol(protocol)
        except ValueError as e:
            return str(e)
        if not isinstance(streaming, bool):
            return "流式性 (streaming) 必须为布尔值"
        if not is_protocol_streaming_available(normalized, streaming):
            return (f"协议 {normalized} 与流式性 streaming={str(bool(streaming)).lower()} "
                    f"的组合实现未上线")
        return None

    @staticmethod
    def _validate_api_keys(api_keys, label='api_keys') -> str:
        """校验端点级密钥池 api_keys（INT-1177 审计 D1/D2，INT-1230 审计 D1'）：
        必须为字符串数组、元素非空、去重、上限 ≤20。返回错误信息或 None。
        label 用于错误提示（端点级默认 api_keys）。"""
        if not isinstance(api_keys, list):
            return f"密钥池 ({label}) 必须是字符串数组"
        if len(api_keys) > _MAX_API_KEYS:
            return f"密钥池 ({label}) 最多支持 {_MAX_API_KEYS} 个密钥"
        seen = set()
        for key in api_keys:
            if not isinstance(key, str) or not str(key).strip():
                return f"密钥池 ({label}) 元素必须为非空字符串"
            stripped = str(key).strip()
            if stripped in seen:
                return f"密钥池 ({label}) 元素不能重复"
            seen.add(stripped)
        return None

    @staticmethod
    def _validate_audio_config(audio_config: dict) -> str:
        """校验 audio_config 目标格式声明（08_混音与SPL映射.md §2.2 / §0.4）"""
        sample_rate = audio_config.get('sample_rate')
        if sample_rate is not None and sample_rate not in _AUDIO_SAMPLE_RATES:
            return (f"非法采样率 (audio_config.sample_rate): {sample_rate}，"
                    f"仅支持: {', '.join(map(str, _AUDIO_SAMPLE_RATES))}")

        bit_depth = audio_config.get('bit_depth')
        if bit_depth is not None:
            normalized = _BIT_DEPTH_ALIASES.get(bit_depth, bit_depth)
            if normalized not in {item.value for item in AudioBitDepth}:
                return (f"非法位深 (audio_config.bit_depth): {bit_depth}，"
                        f"仅支持: s16/s24/s32（或 16/24/32）")

        channels = audio_config.get('channels')
        if channels is not None and channels not in (1, 2):
            return f"非法通道数 (audio_config.channels): {channels}，仅支持: 1/2"

        for key in ('container', 'format'):
            container = audio_config.get(key)
            if container is not None and container not in {item.value for item in AudioContainer}:
                return (f"非法音频容器 (audio_config.{key}): {container}，"
                        f"仅支持: {', '.join(item.value for item in AudioContainer)}")

        return None

    @staticmethod
    def _validate_endpoint_data(data):
        """验证 API 链接数据"""
        endpoint = data.get('endpoint')
        if endpoint:
            try:
                result = urlparse(endpoint)
                if not all([result.scheme, result.netloc]):
                    return "无效的接口地址 (endpoint)，必须包含协议 (http/https/ws/wss)"
                allowed_schemes = ['http', 'https', 'ws', 'wss']
                if result.scheme not in allowed_schemes:
                    return f"无效的协议 {result.scheme}，仅支持 http, https, ws, wss"
            except Exception:
                return "无效的接口地址 (endpoint)"

        if 'max_process' in data:
            val = data['max_process']
            if not isinstance(val, int) or val < 1 or val > 100:
                return "最大并发数 (max_process) 必须在 1-100 之间"

        if 'max_timeout' in data:
            val = data['max_timeout']
            if not isinstance(val, int) or val < 1 or val > 300:
                return "最大超时时间 (max_timeout) 必须在 1-300 之间"

        if 'max_audio_duration' in data:
            val = data['max_audio_duration']
            if not isinstance(val, int) or val < 1 or val > 3600:
                return "最大音频时长 (max_audio_duration) 必须在 1-3600 之间"

        if 'priority' in data:
            val = data['priority']
            if not isinstance(val, int) or val < 0:
                return "优先级 (priority) 必须为非负整数"

        return None

    @staticmethod
    def _build_endpoints_list(endpoints_data, default_max_process, default_max_timeout, default_max_audio_duration):
        """构建 api_endpoints JSON 数组

        Args:
            endpoints_data: 端点字典列表，每个元素含 endpoint/name/max_process/...
                （INT-1177 endpoint 级：每端点可含 api_keys 字符串数组作为该端点
                密钥池；写侧拒收 api_keys_summary 摘要字段，防回传污染存储）
        """
        api_endpoints = []
        for ep in endpoints_data:
            # INT-1230 审计 D6'：写侧拒收端点级摘要字段（防前端回传污染存储；
            # 完整密钥池以 api_keys 明文入库，摘要为读侧派生）
            if isinstance(ep, dict):
                ep = {k: v for k, v in ep.items() if k != 'api_keys_summary'}
            api_endpoints.append({
                'endpoint': ep.get('endpoint') or '',
                'name': ep.get('name') or '',
                'max_process': ep.get('max_process') if ep.get('max_process') is not None else default_max_process,
                'max_timeout': ep.get('max_timeout') if ep.get('max_timeout') is not None else default_max_timeout,
                'max_audio_duration': ep.get('max_audio_duration') if ep.get('max_audio_duration') is not None else default_max_audio_duration,
                'status': ep.get('status') or 'online',
                'health_score': 100,
                'priority': ep.get('priority') if ep.get('priority') is not None else 0,
                'description': ep.get('description') or '',
                'api_keys': ep.get('api_keys') or [],
            })
        return api_endpoints

    @staticmethod
    def _validate_endpoint_obj(ep):
        """验证单个端点对象（dict）

        Args:
            ep: 端点字典
        """
        data = {
            'endpoint': ep.get('endpoint'),
            'max_process': ep.get('max_process'),
            'max_timeout': ep.get('max_timeout'),
            'max_audio_duration': ep.get('max_audio_duration'),
            'priority': ep.get('priority')
        }
        error = APICrudService._validate_endpoint_data(data)
        if error:
            return error
        # INT-1177 endpoint 级密钥池校验（INT-1230 审计 D1'/D2'）：每端点
        # api_keys 必须为字符串数组、非空元素、去重、≤20
        if ep.get('api_keys') is not None:
            error = APICrudService._validate_api_keys(ep.get('api_keys'), label='api_keys')
            if error:
                return error
        return None

    # ========== 序列化辅助 ==========

    @staticmethod
    def _api_to_dict(api):
        """将 API 对象序列化为 dict（兼容 APIAggregate 和 ORM PO 两种类型）"""
        endpoints = []
        # INT-1230 审计 D6'：逐端点内嵌 api_keys_summary（完整密钥零响应）。
        # 优先聚合根派生态（endpoint_keys_summary：完整 api_keys 已剥离），
        # 回退 PO 原始 api_endpoints（读侧防御：派生摘要 + 剥离完整密钥）
        raw_eps = getattr(api, 'endpoint_keys_summary', None)
        if not raw_eps:
            raw_eps = getattr(api, 'api_endpoints', None) or []
        for i, ep in enumerate(raw_eps):
            if not isinstance(ep, dict):
                continue
            redacted = redact_endpoint_keys(ep)
            endpoints.append({
                'id': f"{api.id}_{i}",
                'endpoint': redacted.get('endpoint', ''),
                'name': redacted.get('name', ''),
                'max_process': redacted.get('max_process', 5),
                'max_timeout': redacted.get('max_timeout', 30),
                'max_audio_duration': redacted.get('max_audio_duration', 60),
                'status': redacted.get('status', 'online'),
                'health_score': redacted.get('health_score', 100),
                'priority': redacted.get('priority', 0),
                'description': redacted.get('description', ''),
                'api_keys_summary': redacted.get('api_keys_summary'),
            })

        created_at = getattr(api, 'created_at', None)
        updated_at = getattr(api, 'updated_at', None)

        # 防御：meta 中完整 api_keys 一律不输出（PO/聚合根双兼容——防未来
        # PO 误入序列化层导致完整密钥回显）。endpoint 级密钥池摘要已逐端点
        # 内嵌（api_keys_summary），meta 不再承载池。
        raw_meta = getattr(api, 'meta', None)
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        if 'api_keys' in meta:
            meta = {k: v for k, v in meta.items() if k != 'api_keys'}

        return {
            'id': api.id,
            'name': api.name,
            'vendor': getattr(api, 'vendor', None),
            'description': getattr(api, 'description', None),
            'status': api.status,
            'meta': meta,
            'algorithm_type': getattr(api, 'algorithm_type', None),
            'default_max_process': getattr(api, 'default_max_process', None),
            'default_max_timeout': getattr(api, 'default_max_timeout', None),
            'default_max_audio_duration': getattr(api, 'default_max_audio_duration', None),
            'health_score': getattr(api, 'health_score', None),
            'output_types': normalize_output_types(getattr(api, 'output_types', None)),
            # INT-1799：读侧只出 protocol / streaming，不再返回已废弃的 device_type
            'protocol': getattr(api, 'protocol', None) or APIProtocol.HTTP.value,
            'streaming': bool(getattr(api, 'streaming', False)),
            'adapter_class': getattr(api, 'adapter_class', None),
            'audio_config': getattr(api, 'audio_config', None),
            'rms_spl_mapping_id': getattr(api, 'rms_spl_mapping_id', None),
            'proxy_type': getattr(api, 'proxy_type', None),
            'proxy_url': getattr(api, 'proxy_url', None),
            'endpoints': endpoints,
            'created_at': created_at.isoformat() if created_at and hasattr(created_at, 'isoformat') else (created_at if isinstance(created_at, str) else None),
            'updated_at': updated_at.isoformat() if updated_at and hasattr(updated_at, 'isoformat') else (updated_at if isinstance(updated_at, str) else None),
        }

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None,
             category='execution', module='API', **kwargs):
        """统一日志记录方法"""
        # INT-148：允许调用方覆盖 source（test_connection 传 source='System'），
        # 修复 kwargs 重复传参导致 log_not_emit TypeError、TestAPIConnection 恒失败
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source=kwargs.pop('source', 'backend'),
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    @staticmethod
    def _publish_config_changed(action: str, api_id=None) -> None:
        """API 配置变更后发布事件（CQRS 命令侧，Redis 不可用时降级只打日志）"""
        try:
            payload = {'action': action}
            if api_id is not None:
                payload['api_id'] = api_id
            EventBus().publish(
                EventChannel.CONFIG_EVENTS,
                EventType.API_CONFIG_CHANGED,
                payload,
            )
        except Exception as e:
            logger.warning(f"发布 API 配置变更事件失败，降级忽略: {e}")

    # ========== 写操作 ==========

    @classmethod
    def create(cls, data: dict) -> dict:
        """创建 API 配置

        Args:
            data: API 配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        if not data.get('name') or data.get('meta') is None:
            return {'success': False, 'message': '缺少必要字段: name, meta', 'data': None, 'code': 400}

        # INT-1177：写侧拒收摘要字段（防前端回传 api_keys_summary 污染存储；
        # 完整密钥池以 meta.api_keys 明文入库，摘要为读侧派生）
        data = {k: v for k, v in data.items() if k != 'api_keys_summary'}

        error = cls._validate_api_data({
            'meta': data.get('meta'),
            'default_max_process': data.get('default_max_process'),
            'default_max_timeout': data.get('default_max_timeout'),
            'default_max_audio_duration': data.get('default_max_audio_duration'),
            'output_types': data.get('output_types'),
            'device_type': data.get('device_type'),
            'protocol': data.get('protocol'),
            'streaming': data.get('streaming'),
            'adapter_class': data.get('adapter_class'),
            'audio_config': data.get('audio_config'),
            'proxy_type': data.get('proxy_type'),
            'proxy_url': data.get('proxy_url'),
        })
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        # INT-1799：新建缺省 protocol='http' / streaming=false（前端预选同值），
        # 再按可用矩阵校验组合（未上线组合显式 400，不静默降级）
        protocol = normalize_protocol(data.get('protocol') or APIProtocol.HTTP.value)
        streaming = data.get('streaming')
        streaming = False if streaming is None else bool(streaming)
        error = cls._validate_lane_combo(protocol, streaming)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        endpoints = data.get('endpoints') or []
        for ep in endpoints:
            error = cls._validate_endpoint_obj(ep)
            if error:
                return {'success': False, 'message': error, 'data': None, 'code': 400}

        try:
            default_max_process = data.get('default_max_process') if data.get('default_max_process') is not None else 5
            default_max_timeout = data.get('default_max_timeout') if data.get('default_max_timeout') is not None else 30
            default_max_audio_duration = data.get('default_max_audio_duration') if data.get('default_max_audio_duration') is not None else 60

            api_endpoints = cls._build_endpoints_list(
                endpoints,
                default_max_process,
                default_max_timeout,
                default_max_audio_duration
            )

            create_data = {
                'name': data['name'],
                'vendor': data.get('vendor'),
                'description': data.get('description'),
                'meta': data.get('meta', {}),
                'algorithm_type': data.get('algorithm_type'),
                'default_max_process': default_max_process,
                'default_max_timeout': default_max_timeout,
                'default_max_audio_duration': default_max_audio_duration,
                'max_process': default_max_process,
                'max_timeout': default_max_timeout,
                'max_audio_duration': default_max_audio_duration,
                'status': data.get('status') or 'online',
                'api_endpoints': api_endpoints,
                'output_types': normalize_output_types(data.get('output_types')),
                'protocol': protocol,
                'streaming': streaming,
                'adapter_class': data.get('adapter_class'),
                'audio_config': normalize_audio_config(data.get('audio_config')),
                'proxy_type': (data.get('proxy_type') or '').strip() or None,
                'proxy_url': (data.get('proxy_url') or '').strip() or None,
            }

            new_api = api_test_repository.create_api(create_data)

            cls._publish_config_changed('created', api_id=new_api.id)

            try:
                refresh_stats_cache()
            except Exception:
                logger.debug("创建API配置后刷新统计缓存失败", exc_info=True)

            return {
                'success': True,
                'message': 'API配置创建成功',
                'data': {'id': new_api.id},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def update(cls, api_id: int, data: dict) -> dict:
        """更新 API 配置

        Args:
            api_id: API ID
            data: 需要更新的字段字典

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        # INT-1177：写侧拒收摘要字段（防前端回传 api_keys_summary 污染存储）
        data = {k: v for k, v in data.items() if k != 'api_keys_summary'}

        # 校验 API 数据（代理字段剔除：update 为局部更新，代理对走下方
        # 合并口径校验，避免「只改 proxy_type 无 proxy_url」在此误判）
        data_dict = {k: v for k, v in data.items()
                     if v is not None and k not in ('proxy_type', 'proxy_url')}
        error = cls._validate_api_data(data_dict)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        # INT-1799：可用矩阵按「提交值 + 当前值」合并口径校验——只改其中一维
        # 时也要保证最终状态是已上线的组合（例：http+false 任务改 streaming=true → 400）
        merged_protocol = (data.get('protocol') if data.get('protocol') is not None
                           else (getattr(api, 'protocol', None) or APIProtocol.HTTP.value))
        merged_streaming = (data['streaming'] if isinstance(data.get('streaming'), bool)
                            else bool(getattr(api, 'streaming', False)))
        error = cls._validate_lane_combo(merged_protocol, merged_streaming)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        # 代理校验（INT-839）：按「更新字段 + 当前 DB 值」合并口径校验，
        # 单字段更新（只改 proxy_type 或只改 proxy_url）也保证最终状态合法；
        # 显式传 None 表示清空代理
        merged_proxy_type = data.get('proxy_type', getattr(api, 'proxy_type', None))
        merged_proxy_url = data.get('proxy_url', getattr(api, 'proxy_url', None))
        proxy_error = validate_proxy(merged_proxy_type, merged_proxy_url)
        if proxy_error:
            return {'success': False, 'message': proxy_error, 'data': None, 'code': 400}

        try:
            update_fields = {}

            if data.get('name') is not None:
                update_fields['name'] = data['name']
            if data.get('vendor') is not None:
                update_fields['vendor'] = data['vendor']
            if data.get('description') is not None:
                update_fields['description'] = data['description']
            if data.get('meta') is not None:
                incoming_meta = data['meta']
                # INT-1177 返工(2)：编辑无关字段保存时保留既有密钥池。
                # 读侧防御（_api_to_dict）剥离 meta.api_keys，前端编辑表单
                # 拿不到池、回传 meta 必无 api_keys——整块覆盖会静默清空池。
                # 合并语义：入参 meta 未含 api_keys 时保留既有；显式传完整
                # 数组才覆盖（空数组/清空语义另行明确，D2 口径）。
                if 'api_keys' not in incoming_meta:
                    current_meta = api_test_repository.get_api_meta(api_id)
                    if isinstance(current_meta, dict) and current_meta.get('api_keys') is not None:
                        incoming_meta = dict(incoming_meta)
                        incoming_meta['api_keys'] = current_meta['api_keys']
                update_fields['meta'] = incoming_meta
            if data.get('algorithm_type') is not None:
                update_fields['algorithm_type'] = data['algorithm_type']
            if data.get('default_max_process') is not None:
                update_fields['default_max_process'] = data['default_max_process']
            if data.get('default_max_timeout') is not None:
                update_fields['default_max_timeout'] = data['default_max_timeout']
            if data.get('default_max_audio_duration') is not None:
                update_fields['default_max_audio_duration'] = data['default_max_audio_duration']
            if data.get('status') is not None:
                update_fields['status'] = data['status']
            if data.get('output_types') is not None:
                update_fields['output_types'] = normalize_output_types(data['output_types'])
            if isinstance(data.get('streaming'), bool):
                update_fields['streaming'] = data['streaming']
            if data.get('protocol') is not None:
                update_fields['protocol'] = normalize_protocol(data['protocol'])
            if data.get('adapter_class') is not None:
                update_fields['adapter_class'] = data['adapter_class']
            if data.get('audio_config') is not None:
                update_fields['audio_config'] = normalize_audio_config(data['audio_config'])
            # 代理字段（INT-839）：键存在即更新（含显式 None 清空），
            # 空串归一化为 None；合并口径已由上方 validate_proxy 把关
            if 'proxy_type' in data:
                update_fields['proxy_type'] = (data['proxy_type'] or '').strip() or None
            if 'proxy_url' in data:
                update_fields['proxy_url'] = (data['proxy_url'] or '').strip() or None
            if 'rms_spl_mapping_id' in data:
                # 与 set-default 命令同口径双校验：映射必须存在且归属本 API，
                # 防止把默认灵敏度映射指向其他 API 的校准曲线（越权配置写入）
                spl_mapping_id = data['rms_spl_mapping_id']
                if spl_mapping_id:
                    spl_mapping = ApiRmsSplRepositoryImpl().get_mapping(int(spl_mapping_id))
                    if spl_mapping is None:
                        return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
                    if spl_mapping.api_id != int(api_id):
                        return {'success': False, 'message': '映射不属于该 API', 'data': None, 'code': 400}
                update_fields['rms_spl_mapping_id'] = int(spl_mapping_id) if spl_mapping_id else None

            if data.get('endpoints') is not None:
                for ep in data['endpoints']:
                    error = cls._validate_endpoint_obj(ep)
                    if error:
                        return {'success': False, 'message': error, 'data': None, 'code': 400}

                default_max_process = getattr(api, 'default_max_process', None) or 5
                default_max_timeout = getattr(api, 'default_max_timeout', None) or 30
                default_max_audio_duration = getattr(api, 'default_max_audio_duration', None) or 60

                # INT-1230 审计 D2'/D6'（endpoint 级返工）：读侧剥离完整
                # api_keys，编辑表单拿不到池、回传端点必无 api_keys——整块覆盖
                # 会静默清空既有池。合并语义：入参端点未含 api_keys 时按
                # endpoint URL 匹配保留既有池；显式传完整数组才覆盖。
                existing_endpoints = []
                if data['endpoints']:
                    existing_endpoints = api_test_repository.get_api_endpoints(api_id) or []
                existing_pool_by_url = {}
                for exist_ep in existing_endpoints:
                    if isinstance(exist_ep, dict) and exist_ep.get('endpoint'):
                        pool = exist_ep.get('api_keys') or []
                        if pool:
                            existing_pool_by_url[str(exist_ep['endpoint']).rstrip('/')] = list(pool)

                merged_endpoints = []
                for ep in data['endpoints']:
                    if 'api_keys' not in ep:
                        base = str(ep.get('endpoint') or '').rstrip('/')
                        pool = existing_pool_by_url.get(base)
                        if pool:
                            ep = {**ep, 'api_keys': list(pool)}
                    merged_endpoints.append(ep)

                new_api_endpoints = cls._build_endpoints_list(
                    merged_endpoints,
                    default_max_process,
                    default_max_timeout,
                    default_max_audio_duration
                )
                update_fields['api_endpoints'] = new_api_endpoints

            update_fields['updated_at'] = now_cst()

            updated_api = api_test_repository.update_api(api_id, update_fields)
            if not updated_api:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

            cls._publish_config_changed('updated', api_id=api_id)

            return {
                'success': True,
                'message': 'API配置更新成功',
                'data': cls._api_to_dict(updated_api),
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def delete(cls, api_id: int) -> dict:
        """软删除 API 配置

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        try:
            # 影响面检查：检查是否有正在运行的任务引用此 API
            running_tasks = api_test_repository.check_api_in_running_tasks(api_id)

            if running_tasks:
                task_names = [t.get('name') if isinstance(t, dict) else t.name for t in running_tasks]
                return {
                    'success': False,
                    'message': f"无法删除：以下正在运行的任务正在使用此 API: {', '.join(task_names)}。请先停止任务。",
                    'data': None,
                    'code': 202,
                }

            success = api_test_repository.delete_api(api_id)
            if not success:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

            cls._publish_config_changed('deleted', api_id=api_id)

            try:
                refresh_stats_cache()
            except Exception:
                logger.debug("删除API配置后刷新统计缓存失败: api_id=%s", api_id, exc_info=True)

            return {
                'success': True,
                'message': 'API配置已删除',
                'data': None,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    # ========== 读操作 ==========

    @classmethod
    def get_all(cls, page: int = 1, per_page: int = 10, keyword: str = None,
                status: str = None, algorithm_type: str = None,
                protocol: str = None, streaming: bool = None) -> dict:
        """分页查询 API 列表

        Args:
            page: 页码
            per_page: 每页条数
            keyword: 搜索关键字
            status: 状态过滤
            algorithm_type: 算法类型过滤
            protocol: 协议等值过滤（INT-1799，规范值）
            streaming: 流式性等值过滤（INT-1799，None = 不过滤）

        Returns:
            dict: {success, message, data, code}
        """
        try:
            # 协议筛选入参同样只接受规范值（别名归一后过滤，非法值 400 而非静默空集）
            if protocol:
                try:
                    protocol = normalize_protocol(protocol)
                except ValueError as e:
                    return {'success': False, 'message': str(e), 'data': None, 'code': 400}

            result = api_test_repository.list_apis(
                page=page, per_page=per_page,
                keyword=keyword, status=status, algorithm_type=algorithm_type,
                protocol=protocol, streaming=streaming,
            )

            data = {
                'items': [cls._api_to_dict(api) for api in result['items']],
                'total': result['total'],
                'page': result['page'],
                'per_page': result['per_page'],
                'pages': result['pages'],
            }

            return {
                'success': True,
                'message': 'Success',
                'data': data,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def get_one(cls, api_id: int) -> dict:
        """查询单个 API 详情

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        return {
            'success': True,
            'message': 'Success',
            'data': cls._api_to_dict(api),
            'code': 200,
        }

    @classmethod
    def test_connection(cls, api_id: int) -> dict:
        """测试 API 连接（含 WebSocket/HTTP 健康检查）

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        # INT-148：仓储返回 APIAggregate（无 health_score/api_endpoints 属性），
        # 统一经 _api_to_dict（PO/聚合根双兼容）取字段，修复健康检查恒 AttributeError
        info = cls._api_to_dict(api)

        # INT-839：代理参数（健康检查双分支共用）——http/https 走 requests.proxies，
        # ws/wss 走 websocket-client 代理参数（http_proxy_host/port/auth + proxy_type）
        ws_proxy_kwargs = websocket_proxy_kwargs(info.get('proxy_type'), info.get('proxy_url'))
        requests_proxies = None
        _full_proxy_url = build_proxy_url(info.get('proxy_type'), info.get('proxy_url'))
        if _full_proxy_url:
            requests_proxies = {'http': _full_proxy_url, 'https': _full_proxy_url}

        start_time = time.time()
        try:
            # 健康检查：仅测试 endpoints（INT-1361 api_url 移除后唯一端点来源）
            endpoints_status = False
            endpoint_error = None
            endpoint_response = None
            endpoint_duration = 0

            if not info.get('endpoints'):
                endpoint_error = "没有配置任何端点"
                endpoints_status = True
            else:
                endpoint = info['endpoints'][0]
                test_url = endpoint.get('endpoint', '')

                if not test_url:
                    endpoint_error = "第一个端点URL为空"
                    endpoints_status = True
                else:
                    parsed_url = urlparse(test_url)
                    scheme = parsed_url.scheme.lower()

                    try:
                        if scheme in ['ws', 'wss']:
                            ws = websocket.WebSocket()
                            ws.settimeout(endpoint.get('max_timeout', 30))
                            ws.connect(test_url, **ws_proxy_kwargs)
                            endpoint_duration = (time.time() - start_time) * 1000
                            ws.close()
                            endpoints_status = True

                        elif scheme in ['http', 'https']:
                            if test_url and not test_url.endswith('/'):
                                test_url += '/health'
                            elif test_url and test_url.endswith('/'):
                                test_url += 'health'

                            endpoint_response = requests.get(
                                test_url,
                                timeout=endpoint.get('max_timeout', 30),
                                headers={"User-Agent": "Task-Manager-Health-Checker/1.0"},
                                proxies=requests_proxies,
                            )
                            endpoint_duration = (time.time() - start_time) * 1000

                            if 200 <= endpoint_response.status_code < 400:
                                endpoints_status = True
                            else:
                                endpoint_error = f"端点连接失败: {endpoint_response.status_code}"
                        else:
                            endpoint_error = f"不支持的协议: {scheme}"

                    except Exception as e:
                        endpoint_error = f"端点连接异常: {str(e)}"

            # 综合判断 API 状态
            overall_status = endpoints_status

            # 记录日志
            if overall_status:
                log_content = f"API [{info['name']}] 连接测试成功: 端点在线"
                if not endpoints_status:
                    log_content += f" (端点测试状态: {endpoint_error})"
                elif endpoint_duration > 0:
                    log_content += f", 端点响应耗时: {endpoint_duration:.2f}ms"
                log_level = 'INFO'
            else:
                log_content = f"API [{info['name']}] 连接测试失败: {endpoint_error}"
                log_level = 'ERROR'

            cls._log(
                level=log_level,
                category='HealthCheck',
                source='System',
                content=log_content,
                api_id=info['id']
            )

            # 5. 更新 API 状态
            new_status = 'online' if overall_status else 'offline'
            if info.get('status') != new_status:
                api_test_repository.update_api(info['id'], {
                    'status': new_status,
                    'updated_at': now_cst(),
                })

            # 6. 构建响应
            return {
                'success': True,
                'message': '连接测试完成' if overall_status else '连接测试失败',
                'data': {
                    'id': info['id'],
                    'status': new_status,
                    'health_score': info.get('health_score'),
                    'endpoints_status': str(endpoints_status),
                    'error': endpoint_error if not overall_status else None,
                    'warning': endpoint_error if overall_status and not endpoints_status else None,
                    'status_code': endpoint_response.status_code if endpoint_response else None,
                    'response_time': f"{endpoint_duration:.2f}ms" if endpoint_duration > 0 else None,
                },
                'code': 200,
            }

        except Exception as e:
            cls._log(
                level='ERROR',
                category='HealthCheck',
                source='System',
                content=f"API [{info.get('name')}] 连接测试异常: {str(e)}",
                api_id=info.get('id')
            )

            if info.get('status') != 'offline':
                api_test_repository.update_api(info['id'], {
                    'status': 'offline',
                    'updated_at': now_cst(),
                })

            return {
                'success': True,
                'message': '连接测试失败',
                'data': {
                    'id': info['id'],
                    'status': 'offline',
                    'error': str(e),
                    'health_score': info.get('health_score'),
                    'endpoints_status': str(False),
                },
                'code': 200,
            }

    @classmethod
    def health_check(cls, api_id: int) -> dict:
        """兼容别名，等同 test_connection"""
        return cls.test_connection(api_id)

    @classmethod
    def stop_test(cls, api_id: int) -> dict:
        """停止测试 API

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        try:
            return {
                'success': True,
                'message': '测试已停止',
                'data': {
                    'id': api.id,
                    'status': api.status,
                    'health_score': api.health_score,
                    'endpoints_status': str(False),
                },
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 模块级实例
api_crud_service = APICrudService()
