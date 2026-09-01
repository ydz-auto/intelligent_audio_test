# -*- coding: utf-8 -*-
"""音频引擎 - 音频预准备 Mixin

从 audio_engine.py 拆分出的职责：
- prepare_audios：预下载音频并按各播放设备目标采样率重采样
- _resample_to_file：单文件重采样到目标采样率并写入临时文件
"""
import os

from shared.utils.log_handler import log_and_emit


class EngineAudioPrepareMixin:
    """音频预下载与按设备采样率重采样职责"""

    def prepare_audios(self, audio_ids, playback_device_ids):
        """预下载并按各播放设备目标采样率重采样音频。

        流程：
        1. 解析 playback_device_ids → device_unique_id → defaultSampleRate，去重得到 target_rate 集合
        2. 对每个 audio_id：从仓储取 file_path → OSS 下载到本地 → 读原始采样率
        3. 对每个 (audio_id, target_rate)：sr==target_rate 直接用原文件；sr!=target_rate 重采样
        4. 返回嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}}

        Args:
            audio_ids: 待预下载的音频 ID 列表
            playback_device_ids: 播放设备 ID 列表（DB 主键或 device_unique_id）

        Returns:
            dict: {audio_id: {target_rate(int): local_path, "original": local_path}}
        """
        import wave
        from audio_service.infrastructure.persistence.audio_repository import AudioRepository
        from shared.infrastructure.storage import storage
        from audio_service.infrastructure.audio.playback_config_builder import (
            _get_playback_device_via_grpc, _find_playback_device_by_unique_id,
        )

        _repo = AudioRepository()

        # 1. 收集 target_rate 集合
        target_rates = set()
        for dev_id in playback_device_ids or []:
            dev_unique_id = self._resolve_device_unique_id(
                dev_id, _get_playback_device_via_grpc, _find_playback_device_by_unique_id
            )

            if not dev_unique_id:
                # 兜底：dev_id 本身可能就是 device_unique_id
                dev_unique_id = str(dev_id)

            sr = self.get_device_sample_rate(dev_unique_id)
            if sr:
                target_rates.add(sr)
                log_and_emit('DEBUG', 'audio_engine',
                             f"[prepare_audios] device_id={dev_id}, unique_id={dev_unique_id}, target_rate={sr}",
                             category='audio')

        if not target_rates:
            log_and_emit('WARNING', 'audio_engine',
                         f"[prepare_audios] no target_rate resolved from devices={playback_device_ids}",
                         category='audio')
            return {}

        log_and_emit('INFO', 'audio_engine',
                     f"[prepare_audios] start: audio_count={len(audio_ids)}, target_rates={sorted(target_rates)}",
                     category='audio')

        result = {}
        for audio_id in audio_ids or []:
            try:
                audio_obj = _repo.get_audio(audio_id)
                if not audio_obj or not getattr(audio_obj, 'file_path', None):
                    log_and_emit('WARNING', 'audio_engine',
                                 f"[prepare_audios] audio_id={audio_id} 不存在或无 file_path，跳过",
                                 category='audio')
                    continue
                # 2. 下载到本地
                local_path = storage.load_file(audio_obj.file_path)
                if not local_path or not os.path.exists(local_path):
                    log_and_emit('WARNING', 'audio_engine',
                                 f"[prepare_audios] audio_id={audio_id} 下载失败 path={local_path}，跳过",
                                 category='audio')
                    continue

                # 读取原始采样率与声道数
                orig_sr = None
                nchannels = 1
                try:
                    with wave.open(local_path, 'rb') as wf:
                        orig_sr = wf.getframerate()
                        nchannels = wf.getnchannels()
                except Exception as e:
                    log_and_emit('WARNING', 'audio_engine',
                                 f"[prepare_audios] audio_id={audio_id} 读取采样率失败: {e}",
                                 category='audio')

                inner = {}
                # 原始文件作为兜底（JSON 反序列化后为字符串 key）
                inner['original'] = local_path
                if orig_sr:
                    for tr in target_rates:
                        if tr == orig_sr:
                            # 原始已是目标采样率，不重复重采样
                            inner[tr] = local_path
                        else:
                            resampled = self._resample_to_file(local_path, tr, nchannels, audio_id)
                            if resampled:
                                inner[tr] = resampled
                result[audio_id] = inner
                log_and_emit('DEBUG', 'audio_engine',
                             f"[prepare_audios] prepared audio_id={audio_id}, orig_sr={orig_sr}, "
                             f"rates={sorted(k for k in inner if k != 'original')}",
                             category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine',
                             f"[prepare_audios] audio_id={audio_id} failed: {e}",
                             category='audio')

        log_and_emit('INFO', 'audio_engine',
                     f"[prepare_audios] done: prepared {len(result)}/{len(audio_ids or [])} audios",
                     category='audio')
        return result

    @staticmethod
    def _resolve_device_unique_id(dev_id, get_playback_device_via_grpc, find_playback_device_by_unique_id):
        """把播放设备 ID（DB 主键或 device_unique_id）解析为 device_unique_id。"""
        try:
            dev_obj = None
            # 先尝试按 DB 主键查询
            try_num = int(dev_id) if not isinstance(dev_id, int) else dev_id
            dev_obj = get_playback_device_via_grpc(try_num)
            if not dev_obj:
                dev_obj = find_playback_device_by_unique_id(str(dev_id))
            if dev_obj:
                return (
                    dev_obj.get('device_unique_id')
                    if isinstance(dev_obj, dict)
                    else getattr(dev_obj, 'device_unique_id', None)
                )
        except (ValueError, TypeError):
            dev_obj = find_playback_device_by_unique_id(str(dev_id))
            if dev_obj:
                return (
                    dev_obj.get('device_unique_id')
                    if isinstance(dev_obj, dict)
                    else getattr(dev_obj, 'device_unique_id', None)
                )
        except Exception:
            return None
        return None

    def _resample_to_file(self, src_path, target_rate, nchannels, audio_id):
        """将单个音频文件重采样到 target_rate，写入临时文件并返回路径。"""
        import wave
        import numpy as np
        import threading
        try:
            resample_temp_dir = os.environ.get(
                'RESAMPLE_TEMP_PATH',
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample'))
            os.makedirs(resample_temp_dir, exist_ok=True)

            with wave.open(src_path, 'rb') as wf:
                orig_sr = wf.getframerate()
                frames = wf.readframes(wf.getnframes())

            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            resampled_np = self._get_driver().resample_audio_data(audio_np, orig_sr, target_rate)
            resampled_np = np.clip(resampled_np, -32768, 32767).astype(np.int16)

            temp_file = os.path.join(
                resample_temp_dir,
                f'prepare_{audio_id}_{target_rate}_{os.getpid()}_{threading.get_ident()}.wav')
            with wave.open(temp_file, 'wb') as out_wf:
                out_wf.setnchannels(nchannels)
                out_wf.setsampwidth(2)
                out_wf.setframerate(target_rate)
                out_wf.writeframes(resampled_np.tobytes())

            log_and_emit('DEBUG', 'audio_engine',
                         f"[prepare_audios] resampled audio_id={audio_id}: {orig_sr} -> {target_rate}, "
                         f"temp={temp_file}",
                         category='audio')
            return temp_file
        except Exception as e:
            log_and_emit('WARNING', 'audio_engine',
                         f"[prepare_audios] resample failed audio_id={audio_id} {orig_sr}->{target_rate}: {e}",
                         category='audio')
            return None
