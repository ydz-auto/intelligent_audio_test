# -*- coding: utf-8 -*-
"""C 第三方评估 API 出站客户端 — T-B 出站投递腿（设计文档 §4.2.2 步骤⑤ / §4.3 三契约）。

B→C 经 GW-2 出站：multipart / feature_extract / presigned PUT 三种第三方契约。
网络错误与 5xx 指数退避重试、4xx 不重试；响应透传给调用方 —— 评估结果语义校验
（EVAL_RESULT 解析、必填字段）由 evaluation_service 侧完成，本客户端只负责
投递与传输层错误语义（deliver 语义，不做评估语义判断）。
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from shared.models.common_enums import ThirdPartyAdapterKind

from transfer_agent.domain.errors import InvalidPackageFieldError
from transfer_agent.domain.services.feature_extraction import (
    AudioFeatureExtractor,
    FeatureExtractor,
)

logger = logging.getLogger(__name__)


@dataclass
class CADeliveryOutcome:
    """一次 C 端投递结果（投递语义：包是否送达并取得同步响应）。"""
    delivered: bool
    dst_status: Optional[int] = None
    body: Optional[dict] = None      # C 响应 JSON（可解析为对象时）
    text: str = ''                   # C 响应原始文本（JSON 解析失败时兜底）
    attempts: int = 0
    error: Optional[str] = None


class ThirdPartyCAPIClient:
    """C 第三方评估 API HTTP 客户端 — 按契约形态投递 EVAL_REQUEST 包内容。"""

    def __init__(self, base_url: str, timeout_seconds: int = 120,
                 max_retries: int = 3, backoff_seconds: float = 1.0,
                 feature_extractor: Optional[FeatureExtractor] = None,
                 session: Optional[requests.Session] = None):
        self._base_url = (base_url or '').rstrip('/')
        self._timeout = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._backoff_seconds = backoff_seconds
        self._feature_extractor = feature_extractor or AudioFeatureExtractor()
        self._session = session or requests.Session()

    def deliver(self, adapter_kind: str, bundle) -> CADeliveryOutcome:
        """按契约形态投递（bundle: eval_request_bundle.EvalRequestBundle）。

        未登记形态 fail-closed 拒绝（枚举化，禁魔法字符串）。
        """
        try:
            kind = ThirdPartyAdapterKind(str(adapter_kind or '').lower())
        except ValueError:
            raise InvalidPackageFieldError(
                f'非法第三方评估投递形态: {adapter_kind}'
                f'（允许 {", ".join(k.value for k in ThirdPartyAdapterKind)}）')
        if kind == ThirdPartyAdapterKind.MULTIPART:
            return self._deliver_multipart(bundle)
        if kind == ThirdPartyAdapterKind.FEATURE_EXTRACT:
            return self._deliver_feature_extract(bundle)
        return self._deliver_presigned(bundle)

    # ---- 三种契约形态 ----
    def _deliver_multipart(self, bundle) -> CADeliveryOutcome:
        """形态一：multipart/form-data 流式上传 + 同步响应。"""
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in (bundle.form_fields or {}).items()}
        data['transfer_id'] = bundle.transfer_id
        files = {
            name: (f.filename, io.BytesIO(f.content), f.content_type)
            for name, f in (bundle.files or {}).items()
        }
        return self._post_and_collect('POST', f'{self._base_url}/evaluate',
                                      data=data, files=files)

    def _deliver_feature_extract(self, bundle) -> CADeliveryOutcome:
        """形态二：B 侧预处理大文件→提取特征向量→只传特征（C 仅接受小参数字段）。"""
        features = {}
        try:
            for name, f in (bundle.files or {}).items():
                features[name] = self._feature_extractor.extract(f.filename, f.content)
        except Exception as e:
            return CADeliveryOutcome(delivered=False, error=f'特征提取失败: {e}')
        payload = {
            'transfer_id': bundle.transfer_id,
            'fields': bundle.form_fields or {},
            'features': features,
        }
        return self._post_and_collect('POST', f'{self._base_url}/evaluate', json=payload)

    def _deliver_presigned(self, bundle) -> CADeliveryOutcome:
        """形态三：预签名 URL 上传（B→C 可上传）→携带对象引用评估。"""
        objects = {}
        for name, f in (bundle.files or {}).items():
            presign = self._post_and_collect(
                'POST', f'{self._base_url}/upload-url',
                json={
                    'name': name,
                    'filename': f.filename,
                    'size': len(f.content),
                    'sha256': hashlib.sha256(f.content).hexdigest(),
                    'content_type': f.content_type,
                    'transfer_id': bundle.transfer_id,
                })
            if not presign.delivered:
                return presign
            presign_body = presign.body or {}
            upload_url = presign_body.get('upload_url')
            object_ref = presign_body.get('object_ref')
            if not upload_url or not object_ref:
                return CADeliveryOutcome(
                    delivered=False, dst_status=presign.dst_status,
                    error='预签名响应缺少 upload_url/object_ref')
            put = self._post_and_collect(
                'PUT', upload_url, data=f.content,
                headers={'Content-Type': f.content_type})
            if not put.delivered:
                return put
            objects[name] = object_ref
        payload = {
            'transfer_id': bundle.transfer_id,
            'fields': bundle.form_fields or {},
            'objects': objects,
        }
        return self._post_and_collect('POST', f'{self._base_url}/evaluate', json=payload)

    # ---- 投递与重试 ----
    def _post_and_collect(self, method: str, url: str, **kwargs) -> CADeliveryOutcome:
        """投递一次 HTTP 请求并收集响应（网络错误/5xx 指数退避重试，4xx 不重试）。"""
        attempts = 0
        while True:
            attempts += 1
            try:
                resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            except requests.RequestException as e:
                if attempts > self._max_retries:
                    return CADeliveryOutcome(
                        delivered=False, attempts=attempts,
                        error=f'C 第三方 API 不可达: {url} ({e})')
                self._backoff(attempts, f'网络异常 {e}')
                continue
            if resp.status_code >= 500:
                if attempts > self._max_retries:
                    return CADeliveryOutcome(
                        delivered=False, dst_status=resp.status_code, attempts=attempts,
                        error=f'C 第三方 API 服务端错误: HTTP {resp.status_code}')
                self._backoff(attempts, f'HTTP {resp.status_code}')
                continue
            break
        text = resp.text or ''
        body = None
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None
        delivered = resp.status_code < 400
        return CADeliveryOutcome(
            delivered=delivered,
            dst_status=resp.status_code,
            body=body,
            text='' if body is not None else text,
            attempts=attempts,
            error=None if delivered else f'C 第三方 API 拒绝: HTTP {resp.status_code}: {text[:200]}',
        )

    def _backoff(self, attempt: int, reason: str) -> None:
        sleep_s = self._backoff_seconds * (2 ** (attempt - 1))
        logger.warning('C 端投递将重试: attempt=%s/%s backoff=%.1fs reason=%s',
                       attempt, self._max_retries, sleep_s, reason)
        time.sleep(sleep_s)
