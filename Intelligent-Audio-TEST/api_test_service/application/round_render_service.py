# -*- coding: utf-8 -*-
"""RoundRenderService — 执行器侧 RenderService 消费服务（INT-82，08 设计文档 §七）

混音 6 步全部发生在 audio_service 进程内；执行器仅「组装请求 + 消费产物」：
- Realtime / 流式（websocket_api）→ RenderAudioStream 逐 chunk（WS 推送 + 实时节奏）
- HTTP 非实时（http_api）→ RenderAudioFile 整文件（产物落存储后随请求模板引用）

两级噪声仅透传（round_noise / case_noise），合并优先级由 audio_service 复用
build_noise_info 统一裁决；SPL 映射由本服务预载（消费端查库随请求传入，
audio_service 不反向查库）；audios 未配 SPL 的条目回填轮次级 SPL 或参考基准，
保持 INT-61 单源 65 dB 目标语义。
"""
from __future__ import annotations

import logging
import time
from typing import Iterator, List, Optional

from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    AudioRenderAclRepository,
    RenderChunkDTO,
    RenderedAudioDTO,
)
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService

logger = logging.getLogger(__name__)


class RoundRenderService:
    """执行器混音渲染消费：组装 render_config → 经 ACL 出站 → 消费产物"""

    def __init__(self, render_acl: AudioRenderAclRepository, spl_repo=None,
                 storage_client=None):
        self._render_acl = render_acl
        self._spl_repo = spl_repo
        self._storage = storage_client

    # ── Realtime / 流式：逐 chunk 消费 ──

    def stream_round_chunks(self, api_config, round_config, case_config,
                            task_id) -> Iterator[RenderChunkDTO]:
        """流式混音（RenderAudioStream 经 ACL）：逐 chunk 迭代。

        失败经 ACL 收敛为 sequence=-1 终止帧，由执行器定轮次失败。
        """
        render_config = self.build_round_render_config(
            api_config, round_config, case_config, stream=True)
        return self._render_acl.render_audio_stream(render_config, task_id=str(task_id))

    # ── HTTP 非实时：整文件消费 ──

    def render_round_file_to_storage(self, api_config, round_config, case_config,
                                     task_id, name_hint: str = '') -> Optional[dict]:
        """整段混音（RenderAudioFile 经 ACL）→ 产物落存储，返回引用信息。

        返回 {path, duration_ms, sample_rate, bit_depth, channels, container}；
        渲染失败（gRPC 异常 / success=False）返回 None，由执行器定轮次失败，
        不静默回退原音频路径。
        """
        render_config = self.build_round_render_config(api_config, round_config, case_config)
        dto = self._render_acl.render_audio_file(render_config, task_id=str(task_id))
        if dto is None or not dto.audio_bytes:
            return None
        ext = 'wav' if dto.container == 'wav' else 'pcm'
        key = f"{task_id}/{getattr(api_config, 'id', 'api')}/rendered/" \
              f"{name_hint or 'round'}_{int(time.time() * 1000)}.{ext}"
        content_type = 'audio/wav' if ext == 'wav' else 'audio/pcm'
        path = self._store().save_bytes(dto.audio_bytes, 'audios', key,
                                        content_type=content_type)
        return {
            'path': path,
            'duration_ms': dto.duration_ms,
            'sample_rate': dto.sample_rate,
            'bit_depth': dto.bit_depth,
            'channels': dto.channels,
            'container': dto.container,
        }

    # ── 请求组装 ──

    def build_round_render_config(self, api_config, round_config, case_config,
                                  stream: bool = False) -> dict:
        """组装单轮渲染配置：audios 归一化 + 两级噪声透传 + 目标格式 + SPL 映射预载。

        stream=True（Realtime WS 推送）强制 s16/mono：WS 事件协议输入为
        pcm16 单声道（_build_session_config input_audio_format 默认 pcm16）。
        """
        round_cfg = round_config if isinstance(round_config, dict) else {}
        case_cfg = case_config if isinstance(case_config, dict) else {}
        audios = self._normalize_round_audios(round_cfg)
        api_id = getattr(api_config, 'id', None)
        return self._render_acl.build_render_config(
            {'audios': audios, 'background_noise': round_cfg.get('background_noise')},
            case_cfg,
            target_format=self._resolve_target_format(api_config, stream=stream),
            api_id=api_id,
            spl_mapping=self._load_spl_mapping_dict(api_id),
            overlap_rate=self._extract_param(round_cfg, case_cfg, 'overlap_rate',
                                             clamp_max=1.0),
            overlap_time=self._extract_param(round_cfg, case_cfg, 'overlap_time'),
        )

    # ── audios 归一化 ──

    @staticmethod
    def _normalize_round_audios(round_cfg: dict) -> List[dict]:
        """轮次 audios 归一化：仅保留带 audio_id 的条目；旧数据单 audio_id 字段
        合成为 speaker 源；未配 SPL 的条目回填轮次级 spl 或参考基准（65 dB）。"""
        audios = [dict(a) for a in (round_cfg.get('audios') or [])
                  if isinstance(a, dict) and a.get('audio_id')]
        if not audios and round_cfg.get('audio_id'):
            audios = [{'audio_id': round_cfg['audio_id'], 'type': 'speaker'}]
        if not audios:
            return []
        default_spl = round_cfg.get('spl')
        if default_spl is None:
            default_spl = ApiRmsSplService.REFERENCE_SPL
        for entry in audios:
            if entry.get('spl') is None:
                entry['spl'] = float(default_spl)
        return audios

    # ── 目标格式（api.audio_config；未配置回退 24kHz/s16/mono）──

    @staticmethod
    def _resolve_target_format(api_config, stream: bool = False) -> dict:
        audio_cfg = (getattr(api_config, 'meta', None) or {}).get('audio_config') or {}
        fmt = {
            'sample_rate': int(audio_cfg.get('sample_rate') or 24000),
            'bit_depth': str(audio_cfg.get('bit_depth') or 's16'),
            'channels': int(audio_cfg.get('channels') or 1),
        }
        if audio_cfg.get('container'):
            fmt['container'] = str(audio_cfg['container'])
        if stream:
            # Realtime WS 推送输入协议为 s16 单声道（INT-61 dst_fmt 语义）
            fmt['bit_depth'] = 's16'
            fmt['channels'] = 1
        return fmt

    # ── SPL 映射预载（实体 → dict，随 render_config 传给 audio_service）──

    def _load_spl_mapping_dict(self, api_id) -> Optional[dict]:
        if self._spl_repo is None or api_id is None:
            return None
        try:
            mapping = self._spl_repo.get_default_mapping(api_id)
        except Exception:
            logger.debug("查询 API %s 的 SPL 映射失败，按线性近似口径", api_id,
                         exc_info=True)
            return None
        if mapping is None:
            return None
        return {
            'calibration_status': mapping.calibration_status,
            'calibration_points': [
                {
                    'target_spl': p.target_spl,
                    'gain_linear': p.gain_linear,
                    'rms_dbfs': p.rms_dbfs,
                }
                for p in (mapping.calibration_points or [])
            ],
            'reference_spl': mapping.reference_spl,
            'reference_gain_linear': mapping.reference_gain_linear,
            'min_gain_linear': mapping.min_gain_linear,
            'max_gain_linear': mapping.max_gain_linear,
        }

    # ── 轮次参数提取（overlap_rate / overlap_time）──

    @staticmethod
    def _extract_param(round_cfg: dict, case_cfg: dict, key: str,
                       clamp_max: float = None) -> float:
        """轮次级优先，回退用例级；兼容 list[{field_code,field_value}] 与 dict 形态。

        与 E2E 同源语义（algorithm_params 携带 overlap 配置），
        rate 限幅 [0, 1]（rounds_loop_mixin 同规则）。
        """
        for source in (round_cfg, case_cfg):
            params = source.get('algorithm_params')
            value = None
            if isinstance(params, dict):
                value = params.get(key)
            elif isinstance(params, list):
                for p in params:
                    if isinstance(p, dict) and p.get('field_code') == key:
                        value = p.get('field_value')
                        break
            if value is None:
                continue
            try:
                parsed = max(0.0, float(value))
            except (TypeError, ValueError):
                break
            if clamp_max is not None:
                parsed = min(parsed, clamp_max)
            return parsed
        return 0.0

    # ── 存储 ──

    def _store(self):
        if self._storage is None:
            from shared.infrastructure.storage import storage
            self._storage = storage
        return self._storage
