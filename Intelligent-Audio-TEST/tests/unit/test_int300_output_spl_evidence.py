# -*- coding: utf-8 -*-
"""INT-300 打回修复回归 — 输出侧 SPL 实测口径（http_api 链路对称补齐）。

打回缺陷 2（测试工程师实机核验）：ai_output_rms_dbfs / ai_output_spl_db 仅
realtime_session_executor 落库，http_api（APISessionExecutor 多轮会话 /
APIExecutor 线性单轮）全仓无产出 —— F3 三口径对称验证在 http_api 口径缺腿。

修复链路（本文件锁定，INT-1169/1176 迁移后保留 api_test_service 侧能力）：
1. 多轮会话聚合（APISessionExecutor._aggregate_round_results）：
   rounds[].output_audio_path 逐轮收集 → 拼接 → calculate_rms_dbfs →
   rms_dbfs_to_spl，实测值并入 algorithm_result 与顶层（与 Realtime 同构）
2. 线性单轮（APIExecutor._attach_output_spl_evidence）：
   final_result data.output_audio_path 读档实测，并入 algo_result_dict
3. 全缺引用 / 读档失败 → 字段 None 缺省，不阻塞结果落库
4. 多轮 wav 容器逐轮剥头拼接（缺陷：各轮完整 wav 直接 join，第 2 轮起被
   wave.readframes 静默丢弃，RMS 失真数十 dB）——ApiRmsSplService.unwrap_container_pcm

INT-1169/1176 迁移：原 api_adapter_service.adapters.audio_output / qwen /
volc_ast 归档分支随独立服务删除（内嵌 HTTP/mock 路径 raw_response 恒无
output_audio_path → None，缺证据不阻塞落库），对应单测同步移除。

纯单测：不触真实 DB / gRPC / OSS（存储层 monkeypatch 为内存桩）。
"""
import base64
import io
import json
import math
import os
import struct
import wave

# 导入链拉起 shared BaseConfig，无 .env 加载机制的裸 pytest 环境补齐必填环境变量
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

import pytest

from api_test_service.core import api_session_executor as session_executor_mod
from api_test_service.core.api_session_executor import APISessionExecutor
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.domain.entities.api_rms_spl_mapping import ApiRmsSplMapping


def _sine_pcm(dbfs: float, seconds: float = 0.1, rate: int = 24000) -> bytes:
    """RMS 恰为 10^(dbfs/20) 的 s16 正弦 PCM（幅值 ×√2 补偿正弦 RMS 系数 1/√2）"""
    amp = 10.0 ** (dbfs / 20.0) * math.sqrt(2.0)
    samples = []
    n = int(rate * seconds)
    for i in range(n):
        v = amp * math.sin(2 * math.pi * 440 * i / rate)
        samples.append(int(max(-1.0, min(1.0, v)) * 32767))
    return struct.pack(f'<{n}h', *samples)


def _pcm_as_wav_bytes(pcm: bytes, rate: int = 24000) -> bytes:
    """adapter 侧归档产物是 wav 容器；构造同形 wav 供读侧解包路径。"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class _FakeSplRepo:
    """SPL 映射仓储桩：可注入默认映射，验证换算走映射参考基准。"""

    def __init__(self, mapping=None):
        self._mapping = mapping

    def get_default_mapping(self, api_id):
        return self._mapping


class _FakeStorage:
    """统一存储层桩：引用 → 字节（内存表）。"""

    def __init__(self, blobs=None):
        self.blobs = blobs or {}
        self.saved = []

    def load_bytes(self, ref):
        if ref not in self.blobs:
            raise FileNotFoundError(ref)
        return self.blobs[ref]

    def save_bytes(self, data, category, key, content_type=None):
        ref = f'local://{category}/{key}'
        self.saved.append((category, key))
        self.blobs[ref] = data
        return ref


class _FakeSession:
    session_id = 's-int300'

    def get_summary(self):
        return {}


# ==================== 4. 域服务容器剥头（INT-300） ====================

class TestUnwrapContainerPcm:
    def test_wav_container_unwrapped_to_data_segment(self):
        pcm = _sine_pcm(-20.0)
        wav = _pcm_as_wav_bytes(pcm)
        assert ApiRmsSplService.unwrap_container_pcm(wav) == pcm

    def test_raw_pcm_passthrough(self):
        pcm = _sine_pcm(-20.0)
        assert ApiRmsSplService.unwrap_container_pcm(pcm) == pcm

    def test_short_bytes_passthrough(self):
        assert ApiRmsSplService.unwrap_container_pcm(b'') == b''
        assert ApiRmsSplService.unwrap_container_pcm(b'RIFF') == b'RIFF'

    def test_riff_magic_but_invalid_wave_passthrough(self):
        # RIFF 魔数 + 非 WAVE 形（损坏文件）不剥，原样交由样本解析
        broken = b'RIFF' + b'\x00' * 100
        assert ApiRmsSplService.unwrap_container_pcm(broken) == broken

    def test_calculate_rms_dbfs_accepts_both_containers(self):
        pcm = _sine_pcm(-20.0)
        assert ApiRmsSplService.calculate_rms_dbfs(pcm) == \
            ApiRmsSplService.calculate_rms_dbfs(_pcm_as_wav_bytes(pcm))


# ==================== 2. 多轮会话聚合输出侧实测口径 ====================

class TestAggregateOutputSplEvidence:
    def _make_executor(self, mapping=None, storage=None):
        ex = APISessionExecutor.__new__(APISessionExecutor)
        ex._spl_repo = _FakeSplRepo(mapping)
        ex._spl_service = ApiRmsSplService(ex._spl_repo)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
        if storage is not None:
            self._orig_storage = session_executor_mod
            import shared.infrastructure.storage as storage_mod
            self._storage_mod = storage_mod
        return ex

    def test_no_output_audio_refs_yields_none_fields(self):
        """全轮无 output_audio_path → 三字段 None（缺证据不阻塞落库）。"""
        ex = self._make_executor()
        aggregated = ex._aggregate_round_results(
            [{'round_number': 1, 'output': 'hi', 'latency': 1.0, 'success': True}],
            _FakeSession())
        assert aggregated['ai_output_rms_dbfs'] is None
        assert aggregated['ai_output_spl_db'] is None
        assert aggregated['ai_wav'] is None
        assert aggregated['algorithm_result']['ai_output_rms_dbfs'] is None

    def test_rounds_with_refs_produce_rms_and_spl(self, monkeypatch):
        """有引用（wav 归档）→ 容器剥头实测：-20dBFS 正弦精确还原。"""
        ex = self._make_executor()
        pcm = _sine_pcm(-20.0)
        fake = _FakeStorage({
            'local://audios/r1.wav': _pcm_as_wav_bytes(pcm),
        })
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes', fake.load_bytes)
        monkeypatch.setattr(storage_mod.storage, 'save_bytes',
                            lambda data, cat, key, content_type=None:
                            f'local://{cat}/{key}')

        aggregated = ex._aggregate_round_results(
            [{'round_number': 1, 'output': 'hi', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r1.wav'}],
            _FakeSession())
        # wav 容器剥头后 RMS 精确（-20dBFS 正弦），基准口径 spl = 65 + (rms + 30)
        assert aggregated['ai_output_rms_dbfs'] == pytest.approx(-20.0, abs=0.5)
        assert aggregated['ai_output_spl_db'] == pytest.approx(75.0, abs=0.5)
        assert aggregated['algorithm_result']['ai_output_rms_dbfs'] == \
            aggregated['ai_output_rms_dbfs']
        assert aggregated['ai_wav']  # 归档引用已产出

    def test_multi_round_wav_containers_concat_rms_exact(self, monkeypatch):
        """审计打回缺陷 2 回归：2 轮 wav 容器不同电平 → 逐轮剥头拼接。

        缺陷实现把各轮完整 wav（含 44B RIFF 头）直接 join —— 读侧
        wave.readframes 只停在第一个 data chunk，第 2 轮起被静默丢弃：
        两轮 -60/-10dBFS 实测 -63dBFS（仅第 1 轮）而非全轮合成 -13dBFS，
        偏差 47dB。修复后逐轮 unwrap 再拼接，RMS 为全轮合成值。
        """
        ex = self._make_executor()
        fake = _FakeStorage({
            'local://audios/r1.wav': _pcm_as_wav_bytes(
                _sine_pcm(-60.0, seconds=0.1)),
            'local://audios/r2.wav': _pcm_as_wav_bytes(
                _sine_pcm(-10.0, seconds=0.1)),
        })
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes', fake.load_bytes)
        monkeypatch.setattr(storage_mod.storage, 'save_bytes',
                            lambda data, cat, key, content_type=None:
                            f'local://{cat}/{key}')

        aggregated = ex._aggregate_round_results(
            [{'round_number': 2, 'output': 'b', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r2.wav'},
             {'round_number': 1, 'output': 'a', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r1.wav'}],
            _FakeSession())
        # 等长两段合成 RMS：sqrt((10^(-6)+10^(-1))/2) → -13.01 dBFS
        expected = 20.0 * math.log10(math.sqrt(
            (10.0 ** (-60.0 / 10.0) + 10.0 ** (-10.0 / 10.0)) / 2.0))
        assert aggregated['ai_output_rms_dbfs'] == pytest.approx(expected, abs=0.5)
        assert aggregated['ai_output_spl_db'] == pytest.approx(expected + 95.0, abs=0.5)
        assert aggregated['ai_wav']

    def test_mixed_wav_and_bare_pcm_rounds(self, monkeypatch):
        """混合形态轮次：wav 归档轮剥头、裸 PCM 轮原样 —— 剥头不误伤裸数据。"""
        ex = self._make_executor()
        fake = _FakeStorage({
            'local://audios/r1.wav': _pcm_as_wav_bytes(
                _sine_pcm(-20.0, seconds=0.1)),
            'local://audios/r2.raw': _sine_pcm(-20.0, seconds=0.1),
        })
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes', fake.load_bytes)
        monkeypatch.setattr(storage_mod.storage, 'save_bytes',
                            lambda data, cat, key, content_type=None:
                            f'local://{cat}/{key}')

        aggregated = ex._aggregate_round_results(
            [{'round_number': 1, 'output': 'a', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r1.wav'},
             {'round_number': 2, 'output': 'b', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r2.raw'}],
            _FakeSession())
        # 等长同电平两段合成 RMS 与单段一致
        assert aggregated['ai_output_rms_dbfs'] == pytest.approx(-20.0, abs=0.5)

    def test_mapping_reference_spl_shifts_conversion(self, monkeypatch):
        """映射参考基准参与换算：reference_spl=70 → spl = 70 + (rms + 30)。"""
        mapping = ApiRmsSplMapping(id=1, api_id=7, reference_spl=70.0,
                                   reference_gain_linear=1.0)
        ex = self._make_executor(mapping=mapping)
        fake = _FakeStorage({
            'local://audios/r1.wav': _sine_pcm(-30.0),  # 裸 PCM 直读
        })
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes', fake.load_bytes)
        monkeypatch.setattr(storage_mod.storage, 'save_bytes',
                            lambda data, cat, key, content_type=None:
                            f'local://{cat}/{key}')

        aggregated = ex._aggregate_round_results(
            [{'round_number': 1, 'output': 'hi', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/r1.wav'}],
            _FakeSession(), api_config=SimpleNamespace(id=7, audio_config=None),
            task_id=31)
        assert aggregated['ai_output_rms_dbfs'] == pytest.approx(-30.0, abs=0.5)
        # spl = reference_spl + (rms - BASE(-30)) = 70 + 0
        assert aggregated['ai_output_spl_db'] == pytest.approx(70.0, abs=0.5)

    def test_load_failure_skips_round_not_crash(self, monkeypatch):
        """读档失败轮跳过；全部失败 → None 三元组（与全缺同语义）。"""
        ex = self._make_executor()
        import shared.infrastructure.storage as storage_mod

        def _boom(ref):
            raise FileNotFoundError(ref)

        monkeypatch.setattr(storage_mod.storage, 'load_bytes', _boom)
        aggregated = ex._aggregate_round_results(
            [{'round_number': 1, 'output': 'hi', 'latency': 1.0, 'success': True,
              'output_audio_path': 'local://audios/gone.wav'}],
            _FakeSession())
        assert aggregated['ai_output_rms_dbfs'] is None
        assert aggregated['ai_wav'] is None

    def test_rounds_sorted_by_round_number_before_concat(self, monkeypatch):
        """乱序轮次按 round_number 升序拼接（str 轮次号兼容，gRPC 往返）。"""
        ex = self._make_executor()
        seen = []

        real_load = _FakeStorage().load_bytes

        def _spy_load(ref):
            seen.append(ref)
            return _sine_pcm(-30.0, seconds=0.01)

        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes', _spy_load)
        monkeypatch.setattr(storage_mod.storage, 'save_bytes',
                            lambda data, cat, key, content_type=None:
                            f'local://{cat}/{key}')

        ex._aggregate_round_results(
            [{'round_number': '2', 'output_audio_path': 'r2', 'output': '',
              'latency': 0, 'success': True},
             {'round_number': '1', 'output_audio_path': 'r1', 'output': '',
              'latency': 0, 'success': True}],
            _FakeSession())
        assert seen == ['r1', 'r2']

    def test_round_number_sort_key_tolerant(self):
        assert APISessionExecutor._round_sort_key('3') == 3
        assert APISessionExecutor._round_sort_key(2) == 2
        assert APISessionExecutor._round_sort_key(None) == 0
        assert APISessionExecutor._round_sort_key('x') == 0

    def test_output_sample_rate_from_audio_config(self):
        api = SimpleNamespace(audio_config={'sample_rate': 16000})
        assert APISessionExecutor._resolve_output_sample_rate(api) == 16000
        assert APISessionExecutor._resolve_output_sample_rate(None) == 24000
        assert APISessionExecutor._resolve_output_sample_rate(
            SimpleNamespace(audio_config={'sample_rate': 'bad'})) == 24000


# ==================== 3. 线性单轮输出侧实测口径 ====================

class TestLinearSingleRoundSplEvidence:
    def _make_executor(self, mapping=None):
        import api_test_service.core.api_executor as executor_mod
        ex = executor_mod.APIExecutor.__new__(executor_mod.APIExecutor)
        ex._spl_repo = _FakeSplRepo(mapping)
        ex._spl_service = ApiRmsSplService(ex._spl_repo)
        return ex

    def test_attach_evidence_with_ref(self, monkeypatch):
        ex = self._make_executor()
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda ref: _sine_pcm(-30.0))

        algo = {}
        ex._attach_output_spl_evidence(
            algo, SimpleNamespace(id=7), 31,
            {'json': {'data': {'output_audio_path': 'local://audios/x.wav'}}})
        assert algo['ai_output_rms_dbfs'] == pytest.approx(-30.0, abs=0.5)
        assert algo['ai_output_spl_db'] == pytest.approx(65.0, abs=0.5)

    def test_attach_evidence_with_wav_container_ref(self, monkeypatch):
        """单轮引用为 wav 归档 → 容器剥头精确实测。"""
        ex = self._make_executor()
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda ref: _pcm_as_wav_bytes(_sine_pcm(-25.0)))

        algo = {}
        ex._attach_output_spl_evidence(
            algo, SimpleNamespace(id=7), 31,
            {'json': {'data': {'output_audio_path': 'local://audios/x.wav'}}})
        assert algo['ai_output_rms_dbfs'] == pytest.approx(-25.0, abs=0.5)

    def test_attach_evidence_without_ref_is_noop(self, monkeypatch):
        ex = self._make_executor()
        algo = {}
        ex._attach_output_spl_evidence(algo, SimpleNamespace(id=7), 31,
                                       {'json': {'data': {}}})
        assert algo == {}

        # final_result_result 非 dict 也不崩
        algo2 = {}
        ex._attach_output_spl_evidence(algo2, SimpleNamespace(id=7), 31, None)
        assert algo2 == {}

    def test_attach_evidence_load_failure_is_noop(self, monkeypatch):
        ex = self._make_executor()
        import shared.infrastructure.storage as storage_mod

        def _boom(ref):
            raise FileNotFoundError(ref)

        monkeypatch.setattr(storage_mod.storage, 'load_bytes', _boom)
        algo = {}
        # 读档失败 → 异常被收敛，字段缺省不阻塞落库
        ex._attach_output_spl_evidence(
            algo, SimpleNamespace(id=7), 31,
            {'json': {'data': {'output_audio_path': 'local://audios/gone.wav'}}})
        assert 'ai_output_rms_dbfs' not in algo or \
            algo.get('ai_output_rms_dbfs') is None

    def test_attach_evidence_with_mapping_reference(self, monkeypatch):
        mapping = ApiRmsSplMapping(id=1, api_id=7, reference_spl=80.0,
                                   reference_gain_linear=1.0)
        ex = self._make_executor(mapping=mapping)
        import shared.infrastructure.storage as storage_mod
        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda ref: _sine_pcm(-30.0))

        algo = {}
        ex._attach_output_spl_evidence(
            algo, SimpleNamespace(id=7), 31,
            {'json': {'data': {'output_audio_path': 'local://audios/x.wav'}}})
        assert algo['ai_output_spl_db'] == pytest.approx(80.0, abs=0.5)
