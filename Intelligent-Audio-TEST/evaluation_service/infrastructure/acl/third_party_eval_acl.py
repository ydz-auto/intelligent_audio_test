# -*- coding: utf-8 -*-
"""第三方评估 ACL — A→B→C 评估请求 8 步完整流程编排（设计文档 §4.1.2/§4.2.2）。

8 步流程：
  ① 请求打包（algorithm_result 载荷 + 所需文件 → EVAL_REQUEST zip 包）
  ② 传输（经 transfer_agent 分片上传登记：幂等 transfer_id + 审计流水 + transit 暂存）
  ③ C 执行（ThirdPartyEvalPort 适配器：multipart / feature_extract / presigned_url）
  ④ 结果回传（C 同步响应 = EVAL_RESULT）
  ⑤ 校验（响应结构 + 必填字段）
  ⑥ 落库（调用方持 resp_data 走 result_processor，本 ACL 不落库 — CQRS）
  ⑦ 审计（领域事件 ThirdPartyEvalDispatched/Completed/Failed + transfer_agent 流水）
  ⑧ 回调（EVAL_RESULT 经 transfer_agent 回同步源区，pkg_type=EVAL_RESULT）

区角色（配置化）：self_zone == hub_zone 即评估中枢（B，主线方案），全流程内联执行；
self_zone != hub_zone 为边缘区（A），仅做①②打包传输（dispatch_eval_request），
C 执行在中枢（execute_incoming），结果经 fetch_incoming_result 取回。
"""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import time
import uuid
import zipfile
from typing import Callable, Dict, List, Optional

from evaluation_service.domain.events.evaluation_events import (
    ThirdPartyEvalCompleted,
    ThirdPartyEvalDispatched,
    ThirdPartyEvalFailed,
)
from evaluation_service.domain.repositories.third_party_eval_port import (
    ThirdPartyEvalFile,
    ThirdPartyEvalRequest,
)
from evaluation_service.infrastructure.acl.third_party_adapters import (
    ThirdPartyEvalAdapterFactory,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import (
    TransferEvalClient,
    load_transfer_tokens,
)
from shared.models.common_enums import EvalCapabilityTarget

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_DEFAULT_CONFIG_PATH = os.path.join(
    _REPO_ROOT, 'shared', 'config', 'evaluation_capability_config.json')

# 跨服务传输协议常量（与 transfer_agent TransferCategory 对齐）
EVAL_CATEGORY = 'case-result'
PKG_EVAL_REQUEST = 'EVAL_REQUEST'
PKG_EVAL_RESULT = 'EVAL_RESULT'


class ThirdPartyEvalSettings:
    """第三方评估链路配置（评估能力配置文件 third_party 段 + 环境变量覆盖）。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.environ.get(
            'EVALUATION_CAPABILITY_CONFIG_FILE', _DEFAULT_CONFIG_PATH)
        section = {}
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    section = (json.load(f) or {}).get('third_party') or {}
        except Exception:
            logger.warning('第三方评估配置读取失败，使用默认值: %s', self.config_path, exc_info=True)

        def _get(key, default):
            return os.environ.get(f'THIRD_PARTY_EVAL_{key.upper()}', section.get(key, default))

        self.self_zone = str(_get('self_zone', 'B')).upper()
        self.hub_zone = str(_get('hub_zone', 'B')).upper()
        self.transfer_agent_base_url = str(_get('transfer_agent_base_url', 'http://127.0.0.1:5010'))
        self.hub_transfer_agent_base_url = str(_get('hub_transfer_agent_base_url',
                                                    self.transfer_agent_base_url))
        self.c_api_base_url = str(_get('c_api_base_url', 'http://127.0.0.1:5101'))
        self.adapter = str(_get('adapter', 'multipart'))
        self.timeout_seconds = int(_get('timeout_seconds', 120))
        self.max_retries = int(_get('max_retries', 3))
        self.backoff_seconds = float(_get('backoff_seconds', 1.0))
        self.staging_enabled = str(_get('staging_enabled', 'true')).lower() not in ('0', 'false', 'no')
        self.staging_ttl_seconds = int(_get('staging_ttl_seconds', 3600))
        self.sync_back_enabled = str(_get('sync_back_enabled', 'true')).lower() not in ('0', 'false', 'no')
        self.sync_back_zone = str(_get('sync_back_zone', 'A')).upper()
        self.response_required_keys = list(_get('response_required_keys', []) or [])

    @property
    def is_hub(self) -> bool:
        return self.self_zone == self.hub_zone

    def adapter_settings(self) -> dict:
        return {
            'base_url': self.c_api_base_url,
            'timeout_seconds': self.timeout_seconds,
            'max_retries': self.max_retries,
            'backoff_seconds': self.backoff_seconds,
        }


def _deterministic_zinfo(name: str) -> zipfile.ZipInfo:
    """固定时间戳的 ZipInfo — 保证同输入打包出字节一致的 zip（幂等重发判重前提）。"""
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _default_bundle_reader(path: str) -> bytes:
    """默认 bundle 读取器（本地文件；MinIO 部署形态由区部署绑定存储读取器）。"""
    with open(path, 'rb') as f:
        return f.read()


def _default_event_sink(event) -> None:
    logger.info('third_party_eval_event=%s %s', type(event).__name__, event)


class ThirdPartyEvalACL:
    """第三方评估 ACL（8 步流程编排，事件/传输/适配器均可注入）。"""

    def __init__(self, settings: Optional[ThirdPartyEvalSettings] = None,
                 registry=None, adapter_factory: Optional[ThirdPartyEvalAdapterFactory] = None,
                 client: Optional[TransferEvalClient] = None,
                 bundle_reader: Optional[Callable[[str], bytes]] = None,
                 event_sink: Optional[Callable] = None):
        self._settings = settings
        self._registry = registry
        self._adapter_factory = adapter_factory
        self._client = client
        self._tokens: Optional[Dict[str, str]] = None
        self._bundle_reader = bundle_reader or _default_bundle_reader
        self._event_sink = event_sink or _default_event_sink

    # ---- 依赖延迟装配 ----
    @property
    def settings(self) -> ThirdPartyEvalSettings:
        if self._settings is None:
            self._settings = ThirdPartyEvalSettings()
        return self._settings

    @property
    def registry(self):
        if self._registry is None:
            from evaluation_service.domain.services.evaluation_capability_registry import (
                evaluation_capability_registry,
            )
            self._registry = evaluation_capability_registry
        return self._registry

    @property
    def adapter_factory(self) -> ThirdPartyEvalAdapterFactory:
        if self._adapter_factory is None:
            self._adapter_factory = ThirdPartyEvalAdapterFactory()
        return self._adapter_factory

    @property
    def client(self) -> TransferEvalClient:
        if self._client is None:
            self._client = self._client_for(self.settings.transfer_agent_base_url)
        return self._client

    @property
    def tokens(self) -> Dict[str, str]:
        if self._tokens is None:
            # 注入客户端时优先复用其 token 表（测试/部署注入一致性），否则从环境/密钥文件装载
            if self._client is not None:
                self._tokens = self._client.tokens
            else:
                self._tokens = load_transfer_tokens()
        return self._tokens

    def _client_for(self, base_url: str) -> TransferEvalClient:
        return TransferEvalClient(
            base_url=base_url,
            tokens=self.tokens,
            timeout_seconds=self.settings.timeout_seconds,
        )

    def _emit(self, event) -> None:
        try:
            self._event_sink(event)
        except Exception:
            logger.warning('第三方评估事件发布失败（不阻塞主流程）: %s', event, exc_info=True)

    # ================ 主入口：中枢侧维度组评估（8 步全流程） ================
    def evaluate_dimension_group(self, *, payload: Dict, form_fields: Dict,
                                 files: Dict[str, tuple], representative_dim_data: Dict,
                                 dim_names: List[str], dim_info: Dict,
                                 task_id=None, test_case_id=None,
                                 adapter_kind: Optional[str] = None,
                                 transfer_id: Optional[str] = None) -> Dict:
        """执行第三方评估，返回 resp_data（成功）或 {'__error__': ...}（失败）。

        resp_data 形态与本地评估端点响应一致，由调用方经 result_processor 落库。
        """
        started = time.monotonic()
        adapter_kind = adapter_kind or self._resolve_adapter_kind(representative_dim_data)
        transfer_id = transfer_id or uuid.uuid4().hex
        eval_params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'dimensions': list(dim_names or []),
            'dim_info': dict(dim_info or {}),
            'adapter': adapter_kind,
            'response_required_keys': self.settings.response_required_keys,
        }
        request = self._build_request(transfer_id, form_fields, files, eval_params)
        try:
            if not self.settings.is_hub:
                raise RuntimeError(
                    f'第三方评估须在评估中枢（{self.settings.hub_zone}）执行，'
                    f'当前区 {self.settings.self_zone} 请经 dispatch_eval_request 中转')

            # ①② 打包 + 传输登记（幂等 transfer_id，审计流水）
            bundle_path = self._pack_bundle(request)
            try:
                self._stage_eval_request(bundle_path, request)
            finally:
                try:
                    os.remove(bundle_path)
                except OSError:
                    pass
            self._emit(ThirdPartyEvalDispatched(
                transfer_id=transfer_id, task_id=task_id, test_case_id=str(test_case_id) if test_case_id else None,
                dimensions=list(dim_names or []), adapter=adapter_kind,
                src_zone=self.settings.self_zone, dst_zone='C'))

            # ③④⑤ C 执行 → 结果回传 → 校验
            result = self._run_adapter_call(request, adapter_kind)

            # ⑥ 落库由调用方完成（CQRS：本 ACL 只回传 resp_data）
            # ⑦ 审计事件；⑧ 回调：结果回同步源区（仅中转请求带源区，中枢自有评估不回传）
            synced_back = False
            try:
                synced_back = self._sync_result_back(
                    request, result.data, origin_zone=request.eval_params.get('origin_zone'))
            except Exception as e:
                self._emit(ThirdPartyEvalFailed(
                    transfer_id=transfer_id, task_id=task_id,
                    test_case_id=str(test_case_id) if test_case_id else None,
                    stage='result_sync_back', error=str(e)))
            self._emit(ThirdPartyEvalCompleted(
                transfer_id=transfer_id, task_id=task_id,
                test_case_id=str(test_case_id) if test_case_id else None,
                duration_ms=int((time.monotonic() - started) * 1000),
                synced_back=synced_back))
            return result.data
        except Exception as e:
            self._emit(ThirdPartyEvalFailed(
                transfer_id=transfer_id, task_id=task_id,
                test_case_id=str(test_case_id) if test_case_id else None,
                stage=_error_stage(e), error=str(e)))
            return {'__error__': f'第三方评估失败: {e}'}

    # ================ 边缘区：发起中转（8 步之①②） ================
    def dispatch_eval_request(self, *, form_fields: Dict, files: Dict[str, tuple],
                              eval_params: Dict, transfer_id: Optional[str] = None) -> Dict:
        """边缘区（A）打包 EVAL_REQUEST 并传输到评估中枢（B），返回传输登记视图。"""
        transfer_id = transfer_id or uuid.uuid4().hex
        request = self._build_request(transfer_id, form_fields, files, dict(eval_params or {}))
        bundle_path = self._pack_bundle(request)
        try:
            transfer_view = self._stage_eval_request(bundle_path, request, to_hub=True)
        finally:
            try:
                os.remove(bundle_path)
            except OSError:
                pass
        self._emit(ThirdPartyEvalDispatched(
            transfer_id=transfer_id,
            task_id=(eval_params or {}).get('task_id'),
            test_case_id=(eval_params or {}).get('test_case_id'),
            dimensions=list((eval_params or {}).get('dimensions') or []),
            adapter=str((eval_params or {}).get('adapter') or self.settings.adapter),
            src_zone=self.settings.self_zone, dst_zone=self.settings.hub_zone))
        return {'transfer_id': transfer_id, 'transfer': transfer_view,
                'hub_zone': self.settings.hub_zone}

    # ================ 中枢区：执行中转进来的 EVAL_REQUEST（③~⑧） ================
    def execute_incoming(self, transfer_id: str, token: Optional[str] = None) -> Dict:
        """中枢执行边缘区中转来的 EVAL_REQUEST：解包→C 执行→校验→结果回同步源区。"""
        info = self.client.get_transfer(transfer_id, token=token or self._route_token_for_incoming())
        if str(info.get('pkg_type') or '').upper() != PKG_EVAL_REQUEST:
            raise RuntimeError(f'transfer {transfer_id} 包类型非 EVAL_REQUEST: {info.get("pkg_type")}')
        final_path = info.get('final_path')
        if not final_path:
            raise RuntimeError(f'transfer {transfer_id} 尚未完成传输（无 final_path）')
        started = time.monotonic()
        try:
            request = self._unpack_bundle(self._bundle_reader(final_path))
            result = self._run_adapter_call(request, request.eval_params.get('adapter'))
            synced_back = False
            try:
                synced_back = self._sync_result_back(request, result.data,
                                                     origin_zone=info.get('src_zone'))
            except Exception as e:
                self._emit(ThirdPartyEvalFailed(
                    transfer_id=transfer_id,
                    task_id=request.eval_params.get('task_id'),
                    test_case_id=request.eval_params.get('test_case_id'),
                    stage='result_sync_back', error=str(e)))
            self._emit(ThirdPartyEvalCompleted(
                transfer_id=transfer_id,
                task_id=request.eval_params.get('task_id'),
                test_case_id=request.eval_params.get('test_case_id'),
                duration_ms=int((time.monotonic() - started) * 1000),
                synced_back=synced_back))
            return result.data
        except Exception as e:
            self._emit(ThirdPartyEvalFailed(
                transfer_id=transfer_id,
                task_id=request.eval_params.get('task_id'),
                test_case_id=request.eval_params.get('test_case_id'),
                stage=_error_stage(e), error=str(e)))
            raise

    # ================ 边缘区：取回回同步的 EVAL_RESULT（⑧接收侧） ================
    def fetch_incoming_result(self, transfer_id: str, token: Optional[str] = None) -> Dict:
        """按 transfer_id 读取回同步的 EVAL_RESULT 包，返回结果载荷 dict。"""
        token = token or self.client.get_token(self.settings.hub_zone, self.settings.self_zone)
        info = self.client.get_transfer(transfer_id, token=token)
        if str(info.get('pkg_type') or '').upper() != PKG_EVAL_RESULT:
            raise RuntimeError(f'transfer {transfer_id} 包类型非 EVAL_RESULT: {info.get("pkg_type")}')
        final_path = info.get('final_path')
        if not final_path:
            raise RuntimeError(f'transfer {transfer_id} 尚未完成传输（无 final_path）')
        with zipfile.ZipFile(io.BytesIO(self._bundle_reader(final_path))) as zf:
            return json.loads(zf.read('result.json').decode('utf-8'))

    # ================ 内部：各步骤实现 ================
    def _build_request(self, transfer_id: str, form_fields: Dict, files: Dict[str, tuple],
                       eval_params: Dict) -> ThirdPartyEvalRequest:
        eval_files: Dict[str, ThirdPartyEvalFile] = {}
        for name, item in (files or {}).items():
            filename, content, content_type = item
            eval_files[name] = ThirdPartyEvalFile(
                name=str(name), filename=str(filename or name),
                content=content if isinstance(content, bytes) else str(content).encode('utf-8'),
                content_type=str(content_type or 'application/octet-stream'))
        return ThirdPartyEvalRequest(
            transfer_id=transfer_id,
            form_fields=dict(form_fields or {}),
            files=eval_files,
            eval_params=eval_params,
            src_zone=self.settings.self_zone,
            dst_zone='C',
        )

    def _resolve_adapter_kind(self, representative_dim_data: Dict) -> str:
        try:
            entry = self.registry.resolve(representative_dim_data or {})
        except Exception:
            entry = None
        if entry is not None and entry.target == EvalCapabilityTarget.THIRD_PARTY_C and entry.adapter:
            return entry.adapter.value
        return self.settings.adapter

    def _pack_bundle(self, request: ThirdPartyEvalRequest) -> str:
        """① 请求打包：EVAL_REQUEST zip（request.json + files/*）。"""
        manifest = {
            'transfer_id': request.transfer_id,
            'form_fields': request.form_fields,
            'eval_params': request.eval_params,
            'src_zone': request.src_zone,
            'dst_zone': request.dst_zone,
            'files': {
                f.name: {'filename': f.filename, 'content_type': f.content_type,
                         'size': len(f.content)}
                for f in request.files.values()
            },
        }
        fd, path = tempfile.mkstemp(prefix=f'eval_request_{request.transfer_id}_', suffix='.zip')
        with os.fdopen(fd, 'wb') as raw:
            with zipfile.ZipFile(raw, 'w') as zf:
                zf.writestr(_deterministic_zinfo('request.json'),
                            json.dumps(manifest, ensure_ascii=False))
                for f in request.files.values():
                    zf.writestr(_deterministic_zinfo(f'files/{f.name}'), f.content)
        return path

    def _unpack_bundle(self, bundle_bytes: bytes) -> ThirdPartyEvalRequest:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as zf:
            manifest = json.loads(zf.read('request.json').decode('utf-8'))
            files = {}
            for name, meta in (manifest.get('files') or {}).items():
                files[name] = ThirdPartyEvalFile(
                    name=name, filename=meta.get('filename') or name,
                    content=zf.read(f'files/{name}'),
                    content_type=meta.get('content_type') or 'application/octet-stream')
        return ThirdPartyEvalRequest(
            transfer_id=manifest['transfer_id'],
            form_fields=manifest.get('form_fields') or {},
            files=files,
            eval_params=manifest.get('eval_params') or {},
            src_zone=manifest.get('src_zone') or 'A',
            dst_zone=manifest.get('dst_zone') or 'C',
        )

    def _stage_eval_request(self, bundle_path: str, request: ThirdPartyEvalRequest,
                            to_hub: bool = False) -> Dict:
        """② 传输：EVAL_REQUEST 包分片上传到本区/中枢 transfer_agent（幂等 + 审计 + transit 暂存）。"""
        if to_hub:
            dst_zone = self.settings.hub_zone
            base_url = self.settings.hub_transfer_agent_base_url
        else:
            dst_zone = 'C'
            base_url = self.settings.transfer_agent_base_url
        client = self.client if base_url == self.settings.transfer_agent_base_url \
            else self._client_for(base_url)
        task_id = (request.eval_params or {}).get('task_id')
        test_case_id = (request.eval_params or {}).get('test_case_id')
        key = f'eval_request/{task_id or "unknown"}/{test_case_id or "unknown"}/{request.transfer_id}.zip'
        return client.send_file(
            transfer_id=request.transfer_id,
            pkg_type=PKG_EVAL_REQUEST,
            src_zone=self.settings.self_zone,
            dst_zone=dst_zone,
            category=EVAL_CATEGORY,
            key=key,
            local_path=bundle_path,
            ephemeral=True,
            ttl_seconds=self.settings.staging_ttl_seconds,
            meta={'adapter': request.eval_params.get('adapter'),
                  'dimensions': request.eval_params.get('dimensions')},
        )

    def _run_adapter_call(self, request: ThirdPartyEvalRequest, adapter_kind: str):
        """③④⑤ C 执行 → EVAL_RESULT 回传 → 校验（统一错误语义）。"""
        from evaluation_service.infrastructure.acl.third_party_adapters import (
            ThirdPartyEvalAdapterError,
        )
        adapter = self.adapter_factory.create(
            adapter_kind or self.settings.adapter, self.settings.adapter_settings())
        result = adapter.evaluate(request)
        if not result.ok:
            raise ThirdPartyEvalAdapterError(result.error or '第三方评估返回失败')
        return result

    def _sync_result_back(self, request: ThirdPartyEvalRequest, result_data: Dict,
                          origin_zone: Optional[str] = None) -> bool:
        """⑧ 回调：EVAL_RESULT 打包回同步源区（仅中转请求；未启用或源区==本区时跳过）。"""
        origin = (origin_zone or request.eval_params.get('origin_zone') or '').upper()
        if not self.settings.sync_back_enabled or not origin or origin == self.settings.self_zone:
            return False
        result_payload = {'transfer_id': request.transfer_id, 'result': result_data}
        fd, path = tempfile.mkstemp(prefix=f'eval_result_{request.transfer_id}_', suffix='.zip')
        try:
            with os.fdopen(fd, 'wb') as raw:
                with zipfile.ZipFile(raw, 'w') as zf:
                    zf.writestr(_deterministic_zinfo('result.json'),
                                json.dumps(result_payload, ensure_ascii=False))
            self.client.send_file(
                transfer_id=f'{request.transfer_id}-result',
                pkg_type=PKG_EVAL_RESULT,
                src_zone=self.settings.self_zone,
                dst_zone=origin,
                category=EVAL_CATEGORY,
                key=f'eval_result/{request.transfer_id}.zip',
                local_path=path,
                ephemeral=False,
                ttl_seconds=self.settings.staging_ttl_seconds,
                meta={'origin_transfer_id': request.transfer_id},
            )
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return True

    def _route_token_for_incoming(self) -> str:
        origin = self.settings.sync_back_zone or ''
        token = self.client.get_token(origin, self.settings.self_zone) if origin else None
        if not token:
            raise RuntimeError(
                f'未配置边缘区 {origin}->{self.settings.self_zone} 预共享 token，无法读取中转包')
        return token


def _error_stage(e: Exception) -> str:
    """按异常类型标注失败环节（⑦审计事件的 stage 字段）。"""
    from evaluation_service.infrastructure.acl.third_party_adapters import (
        ThirdPartyEvalAdapterError,
    )
    if isinstance(e, ThirdPartyEvalAdapterError):
        return 'third_party_call'
    from evaluation_service.infrastructure.acl.transfer_eval_client import ThirdPartyEvalError
    if isinstance(e, ThirdPartyEvalError):
        return 'transfer'
    if isinstance(e, RuntimeError) and '评估中枢' in str(e):
        return 'zone_role'
    return 'unknown'


# 模块级单例（评估宿主/端点 Worker 共用）
third_party_eval_acl = ThirdPartyEvalACL()
