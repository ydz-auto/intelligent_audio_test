# -*- coding: utf-8 -*-
"""B→C 第三方评估适配器（ThirdPartyEvalPort 实现，设计文档 §4.3 三种形态）。

- MultipartThirdPartyEvalAdapter       multipart/form-data 流式上传 + 同步响应
- FeatureExtractThirdPartyEvalAdapter  B 预处理大文件→提取特征向量→只传特征
- PresignedUrlThirdPartyEvalAdapter    预签名 URL 上传→C 拉取→携带对象引用评估

适配形态由评估能力注册表配置选择（枚举化，运行时可切换）；网络错误指数退避重试
（4xx 语义错误不重试），EVAL_RESULT 经统一校验后返回。
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import wave
from abc import ABC, abstractmethod
from typing import Dict, Optional

import requests

from evaluation_service.domain.repositories.third_party_eval_port import (
    ThirdPartyEvalPort,
    ThirdPartyEvalRequest,
    ThirdPartyEvalResult,
)
from shared.models.common_enums import ThirdPartyAdapterKind

logger = logging.getLogger(__name__)


class ThirdPartyEvalAdapterError(Exception):
    """第三方评估调用层错误（协议/HTTP/校验）。"""


class FeatureExtractor(ABC):
    """特征提取端口（feature_extract 形态的 B 侧预处理）。"""

    @abstractmethod
    def extract(self, filename: str, content: bytes) -> dict:
        """从文件内容提取特征向量（小体积可序列化 dict）。"""


class AudioFeatureExtractor(FeatureExtractor):
    """默认特征提取器：WAV 头解析（声道/采样率/时长）+ 体积与内容摘要。"""

    def extract(self, filename: str, content: bytes) -> dict:
        features: Dict = {
            'filename': filename,
            'size_bytes': len(content),
            'sha256': hashlib.sha256(content).hexdigest(),
        }
        if filename.lower().endswith('.wav'):
            try:
                with wave.open(io.BytesIO(content), 'rb') as wav:
                    framerate = wav.getframerate() or 0
                    features.update({
                        'channels': wav.getnchannels(),
                        'sample_width': wav.getsampwidth(),
                        'framerate': framerate,
                        'n_frames': wav.getnframes(),
                        'duration_seconds': round(wav.getnframes() / framerate, 6) if framerate else None,
                    })
            except (wave.Error, EOFError) as e:
                logger.warning('WAV 特征解析失败（退化为基础特征）: %s (%s)', filename, e)
        return features


class _ThirdPartyHttpEvalAdapter(ThirdPartyEvalPort, ABC):
    """HTTP 适配器基类：指数退避重试 + EVAL_RESULT 解析与校验。"""

    def __init__(self, base_url: str, timeout_seconds: int = 120,
                 max_retries: int = 3, backoff_seconds: float = 1.0,
                 session: Optional[requests.Session] = None):
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._backoff_seconds = backoff_seconds
        self._session = session or requests.Session()

    # ---- 重试 HTTP ----
    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        attempt = 0
        while True:
            try:
                resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            except requests.RequestException as e:
                attempt += 1
                if attempt > self._max_retries:
                    raise ThirdPartyEvalAdapterError(f'第三方 API 不可达: {url} ({e})') from e
                self._backoff(attempt, f'网络异常 {e}')
                continue
            if resp.status_code >= 500:
                attempt += 1
                if attempt > self._max_retries:
                    raise ThirdPartyEvalAdapterError(
                        f'第三方 API 服务端错误: {url} -> HTTP {resp.status_code}')
                self._backoff(attempt, f'HTTP {resp.status_code}')
                continue
            return resp

    def _backoff(self, attempt: int, reason: str) -> None:
        sleep_s = self._backoff_seconds * (2 ** (attempt - 1))
        logger.warning('第三方评估请求将重试: attempt=%s/%s backoff=%.1fs reason=%s',
                       attempt, self._max_retries, sleep_s, reason)
        time.sleep(sleep_s)

    # ---- EVAL_RESULT 解析与校验（8 步流程之④结果回传 ⑤校验）----
    def _parse_result(self, resp: requests.Response, transfer_id: str) -> ThirdPartyEvalResult:
        if resp.status_code >= 400:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=transfer_id, status_code=resp.status_code,
                error=f'第三方 API 返回 HTTP {resp.status_code}: {resp.text[:200]}')
        try:
            data = resp.json()
        except ValueError:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=transfer_id, status_code=resp.status_code,
                error='第三方 API 响应不是合法 JSON')
        if not isinstance(data, dict) or not data:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=transfer_id, status_code=resp.status_code,
                error='第三方 API 响应为空或非对象')
        if 'code' in data and data.get('code') not in (0, '0'):
            return ThirdPartyEvalResult(
                ok=False, transfer_id=transfer_id, status_code=resp.status_code,
                error=f"第三方评估失败: {data.get('msg') or data.get('message') or '未知错误'}")
        return ThirdPartyEvalResult(ok=True, transfer_id=transfer_id,
                                    data=data, status_code=resp.status_code)

    @staticmethod
    def _validate_required_keys(data: dict, required_keys) -> None:
        for key in required_keys or []:
            if key not in data:
                raise ThirdPartyEvalAdapterError(f'EVAL_RESULT 缺少必填字段: {key}')


class MultipartThirdPartyEvalAdapter(_ThirdPartyHttpEvalAdapter):
    """形态一：multipart/form-data 流式上传 + 同步响应（C 支持 multipart 契约）。"""

    def evaluate(self, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        url = f'{self._base_url}/evaluate'
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in (request.form_fields or {}).items()}
        data['transfer_id'] = request.transfer_id
        files = {
            name: (f.filename, io.BytesIO(f.content), f.content_type)
            for name, f in (request.files or {}).items()
        }
        try:
            resp = self._request_with_retry('POST', url, data=data, files=files)
            result = self._parse_result(resp, request.transfer_id)
        except ThirdPartyEvalAdapterError as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id, error=str(e))
        if result.ok:
            try:
                self._validate_required_keys(result.data,
                                             request.eval_params.get('response_required_keys'))
            except ThirdPartyEvalAdapterError as e:
                return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id,
                                            status_code=result.status_code, error=str(e))
        return result


class FeatureExtractThirdPartyEvalAdapter(_ThirdPartyHttpEvalAdapter):
    """形态二：B 预处理大文件→特征向量→只传特征（C 仅接受小参数字段）。"""

    def __init__(self, base_url: str, feature_extractor: Optional[FeatureExtractor] = None,
                 **kwargs):
        super().__init__(base_url, **kwargs)
        self._feature_extractor = feature_extractor or AudioFeatureExtractor()

    def evaluate(self, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        url = f'{self._base_url}/evaluate'
        features = {}
        try:
            for name, f in (request.files or {}).items():
                features[name] = self._feature_extractor.extract(f.filename, f.content)
        except Exception as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id,
                                        error=f'特征提取失败: {e}')
        payload = {
            'transfer_id': request.transfer_id,
            'fields': request.form_fields or {},
            'features': features,
        }
        try:
            resp = self._request_with_retry('POST', url, json=payload)
            result = self._parse_result(resp, request.transfer_id)
        except ThirdPartyEvalAdapterError as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id, error=str(e))
        if result.ok:
            try:
                self._validate_required_keys(result.data,
                                             request.eval_params.get('response_required_keys'))
            except ThirdPartyEvalAdapterError as e:
                return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id,
                                            status_code=result.status_code, error=str(e))
        return result


class PresignedUrlThirdPartyEvalAdapter(_ThirdPartyHttpEvalAdapter):
    """形态三：预签名 URL 上传→C 主动拉取→携带对象引用评估。"""

    def evaluate(self, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        objects: Dict[str, str] = {}
        try:
            for name, f in (request.files or {}).items():
                presign_resp = self._request_with_retry(
                    'POST', f'{self._base_url}/upload-url',
                    json={
                        'name': name,
                        'filename': f.filename,
                        'size': len(f.content),
                        'sha256': hashlib.sha256(f.content).hexdigest(),
                        'content_type': f.content_type,
                        'transfer_id': request.transfer_id,
                    })
                if presign_resp.status_code >= 400:
                    return ThirdPartyEvalResult(
                        ok=False, transfer_id=request.transfer_id,
                        error=f'预签名申请失败 HTTP {presign_resp.status_code}')
                presign = presign_resp.json()
                upload_url = presign.get('upload_url')
                object_ref = presign.get('object_ref')
                if not upload_url or not object_ref:
                    return ThirdPartyEvalResult(
                        ok=False, transfer_id=request.transfer_id,
                        error='预签名响应缺少 upload_url/object_ref')
                put_resp = self._request_with_retry(
                    'PUT', upload_url, data=f.content,
                    headers={'Content-Type': f.content_type})
                if put_resp.status_code >= 400:
                    return ThirdPartyEvalResult(
                        ok=False, transfer_id=request.transfer_id,
                        error=f'预签名上传失败 HTTP {put_resp.status_code}')
                objects[name] = object_ref
        except ThirdPartyEvalAdapterError as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id, error=str(e))
        except ValueError as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id,
                                        error=f'预签名响应非 JSON: {e}')

        payload = {
            'transfer_id': request.transfer_id,
            'fields': request.form_fields or {},
            'objects': objects,
        }
        try:
            resp = self._request_with_retry('POST', f'{self._base_url}/evaluate', json=payload)
            result = self._parse_result(resp, request.transfer_id)
        except ThirdPartyEvalAdapterError as e:
            return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id, error=str(e))
        if result.ok:
            try:
                self._validate_required_keys(result.data,
                                             request.eval_params.get('response_required_keys'))
            except ThirdPartyEvalAdapterError as e:
                return ThirdPartyEvalResult(ok=False, transfer_id=request.transfer_id,
                                            status_code=result.status_code, error=str(e))
        return result


class ThirdPartyEvalAdapterFactory:
    """适配器工厂 — 按 ThirdPartyAdapterKind 枚举构建（未登记形态 fail-closed）。"""

    def __init__(self, feature_extractor: Optional[FeatureExtractor] = None):
        self._feature_extractor = feature_extractor

    def create(self, kind: str, settings: Optional[dict] = None) -> ThirdPartyEvalPort:
        settings = dict(settings or {})
        try:
            kind_enum = ThirdPartyAdapterKind(str(kind).lower())
        except ValueError:
            raise ValueError(
                f'非法第三方评估适配形态: {kind}'
                f'（允许 {", ".join(k.value for k in ThirdPartyAdapterKind)}）')
        common = {
            'timeout_seconds': int(settings.get('timeout_seconds', 120)),
            'max_retries': int(settings.get('max_retries', 3)),
            'backoff_seconds': float(settings.get('backoff_seconds', 1.0)),
        }
        base_url = settings.get('base_url') or ''
        if not base_url:
            raise ValueError('第三方评估 base_url 未配置（c_api_base_url）')
        if kind_enum == ThirdPartyAdapterKind.MULTIPART:
            return MultipartThirdPartyEvalAdapter(base_url, **common)
        if kind_enum == ThirdPartyAdapterKind.FEATURE_EXTRACT:
            return FeatureExtractThirdPartyEvalAdapter(
                base_url, feature_extractor=self._feature_extractor, **common)
        return PresignedUrlThirdPartyEvalAdapter(base_url, **common)
