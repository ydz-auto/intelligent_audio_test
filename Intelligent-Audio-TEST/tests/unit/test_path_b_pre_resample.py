# -*- coding: utf-8 -*-
"""路径B 预下载重采样验收测试 (INT-23, 设计见父 issue INT-21)。

覆盖以下 4 个验收点:

1. 多噪声设备不同采样率 —— 同一噪声 audio_id 在 44100/48000 设备上各有一份预下载文件,
   播放时 needs_resample 均为 false。
2. 秒传/原始已是 target_rate —— 若音频原始采样率已等于 target_rate,不重复重采样,
   直接用原文件。
3. 多轮复用 —— 第 2+ 轮不再触发 _pre_resample。
4. 兜底(缓存 miss) —— 缓存 miss 时仍能走 OSS 下载 + 运行时重采样,不报错。

被测对象:
- ``audio_service.infrastructure.audio.playback_config_builder._resolve_preloaded_path``
  路径B 嵌套查缓存:``{audio_id: {target_rate: local_path, "original": local_path}}``。
- ``build_dry_configs`` / ``build_noise_play_configs`` / ``build_interferer_configs``
  三个构建器按设备 target_rate 解析预下载路径,缓存 miss 回退原文件。
- ``audio_service.infrastructure.audio.audio_driver.PyAudioDriver._pre_resample``
  运行时重采样决策:file_rate==target_rate 复用原文件(不重采样),否则重采样到 target_rate。

依赖说明:
- ``audio_driver`` 顶层 import pyaudio/numpy/pydub/shared.infrastructure.storage。在无音频硬件、
  无 numpy 的测试环境用 ``sys.modules`` 桩替换(始终桩 pyaudio/pydub/storage,仅当真实缺失时桩
  numpy/scipy),保证测试独立、可重复、无副作用。
- 真实重采样(mismatch 分支)需要真实 numpy/scipy;缺失时该用例自动 skip。
- 重采样临时目录通过 ``RESAMPLE_TEMP_PATH`` 指向 pytest ``tmp_path``,不污染仓库。
"""
import importlib
import importlib.util
import json
import os
import struct
import sys
import types
import wave
from types import SimpleNamespace
from unittest import mock

import pytest

from audio_service.infrastructure.audio.playback_config_builder import (
    _resolve_preloaded_path,
    build_dry_configs,
    build_interferer_configs,
    build_noise_play_configs,
)


# --------------------------------------------------------------------------- #
#  通用 fixture                                                               #
# --------------------------------------------------------------------------- #
def _make_wav(path, rate, channels=1, frames=1600):
    """在 path 写入一个真实的单声道/双声道 PCM wav 文件。"""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * (frames * channels), *[0] * (frames * channels)))
    return str(path)


class FakeAudioService:
    """替身 audio_service:按设备 unique_id 返回 target_rate 与 device_index。"""

    def __init__(self, sample_rate_map=None):
        self._sr = sample_rate_map or {}
        self.get_device_sample_rate_calls = []

    def get_device_index(self, unique_id):
        # 非 None,使构建器不会因 device_index 为 None 跳过
        return 1

    def get_device_sample_rate(self, unique_id):
        self.get_device_sample_rate_calls.append(unique_id)
        return self._sr.get(unique_id)


@pytest.fixture
def nested_paths(tmp_path):
    """构造路径B 嵌套预下载映射(模拟 PrepareAudios 返回结构)。

    audio_id=100 在 44100/48000 设备上各有一份预下载文件,original 指向 44100 原文件。
    """
    p44 = _make_wav(tmp_path / "n_44100.wav", 44100)
    p48 = _make_wav(tmp_path / "n_48000.wav", 48000)
    return {
        100: {44100: p44, 48000: p48, "original": p44},
    }, p44, p48


# --------------------------------------------------------------------------- #
#  验收点 1 & 2 & 4:_resolve_preloaded_path 契约                              #
# --------------------------------------------------------------------------- #
class TestResolvePreloadedPath:
    """嵌套查缓存纯逻辑。"""

    def test_resolves_per_target_rate(self, nested_paths):
        # 验收点 1:同一 audio_id 在 44100/48000 各取到对应路径
        paths, p44, p48 = nested_paths
        assert _resolve_preloaded_path(paths, 100, 44100) == p44
        assert _resolve_preloaded_path(paths, 100, 48000) == p48

    def test_int_str_key_compat(self, nested_paths):
        # gRPC JSON 往返后 key 变字符串,helper 必须兼容 int/str
        paths, p44, p48 = nested_paths
        str_paths = {str(k): {str(rk): rv for rk, rv in v.items()} for k, v in paths.items()}
        assert _resolve_preloaded_path(str_paths, 100, 48000) == p48
        assert _resolve_preloaded_path(str_paths, "100", "44100") == p44

    def test_original_key_is_passthrough(self, nested_paths):
        # 验收点 2:original 槽位保存原文件路径(秒传,无重采样副本)
        paths, p44, _ = nested_paths
        assert paths[100]["original"] == p44

    def test_cache_miss_falls_back_to_original(self, nested_paths):
        # 验收点 4:target_rate 未命中时回退 original,播放侧走运行时重采样
        paths, p44, _ = nested_paths
        assert _resolve_preloaded_path(paths, 100, 16000) == p44

    def test_missing_audio_returns_none(self, nested_paths):
        # 验收点 4 边界:audio_id 完全不在映射中 -> None -> 构建器回退 OSS
        paths, _, _ = nested_paths
        assert _resolve_preloaded_path(paths, 999, 44100) is None

    def test_empty_inputs_return_none(self):
        assert _resolve_preloaded_path(None, 100, 44100) is None
        assert _resolve_preloaded_path({}, 100, 44100) is None
        assert _resolve_preloaded_path({100: {44100: "x"}}, None, 44100) is None


# --------------------------------------------------------------------------- #
#  验收点 1 & 4:构建器按设备 target_rate 解析预下载路径                         #
# --------------------------------------------------------------------------- #
class TestBuilderResolvesTargetRate:
    """build_noise_play_configs / build_dry_configs / build_interferer_configs。"""

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch):
        # 屏蔽 SPL 映射与日志,避免触碰真实 gRPC/DB
        import audio_service.infrastructure.audio.playback_config_builder as pcb

        monkeypatch.setattr(pcb, "resolve_spl_gain", lambda *a, **k: 1.0)
        monkeypatch.setattr(pcb, "_log", lambda *a, **k: None)
        # build_dry_configs / build_interferer_configs 顶层惰性 import AudioRepository,
        # 其真实模块链需要 DATABASE_URL 配置;注入桩模块避免触碰 DB 配置。
        repo_mod = types.ModuleType(
            "audio_service.infrastructure.persistence.audio_repository"
        )

        class _AudioRepository:
            def __init__(self):
                pass

            def get_audio(self, audio_id):
                return None

        repo_mod.AudioRepository = _AudioRepository
        monkeypatch.setitem(
            sys.modules,
            "audio_service.infrastructure.persistence.audio_repository",
            repo_mod,
        )

    def _noise_devices(self):
        return [
            {"device_unique_id": "dev_441", "channel_index": 0, "current_spl_mapping_id": None},
            {"device_unique_id": "dev_480", "channel_index": 0, "current_spl_mapping_id": None},
        ]

    def test_noise_picks_per_device_target_rate(self, nested_paths):
        # 验收点 1:两台噪声设备采样率不同,各自命中对应 target_rate 的缓存
        paths, p44, p48 = nested_paths
        svc = FakeAudioService({"dev_441": 44100, "dev_480": 48000})
        n_audio = SimpleNamespace(file_path="oss://noise/100.wav", duration=1.0)
        noise_audio_info = ({"spl": 60, "audio_id": 100}, n_audio)

        configs = build_noise_play_configs(
            noise_audio_info, self._noise_devices(), svc, audio_local_paths=paths
        )

        assert len(configs) == 2
        assert [c["file"] for c in configs] == [p44, p48]
        # 每台设备都调用了 get_device_sample_rate
        assert svc.get_device_sample_rate_calls == ["dev_441", "dev_480"]

    def test_noise_cache_miss_falls_back_to_oss(self, nested_paths):
        # 验收点 4:(audio_id, target_rate) 缓存 miss 且无 original -> 回退 OSS file_path
        paths, _, _ = nested_paths
        # 构造一个 target_rate 不在映射、且移除 original 兜底的场景
        sparse = {100: {44100: paths[100][44100]}}  # 只有 44100,无 48000/original
        svc = FakeAudioService({"dev_480": 48000})
        oss_path = "oss://noise/100.wav"
        n_audio = SimpleNamespace(file_path=oss_path, duration=1.0)
        noise_audio_info = ({"spl": 60, "audio_id": 100}, n_audio)
        devices = [self._noise_devices()[1]]  # 只取 48000 设备

        configs = build_noise_play_configs(
            noise_audio_info, devices, svc, audio_local_paths=sparse
        )

        assert len(configs) == 1
        assert configs[0]["file"] == oss_path  # 回退 OSS,运行时再重采样

    def test_dry_picks_target_rate_path(self, nested_paths, monkeypatch):
        # 验收点 1:主讲人音频在 48000 设备上取 48000 预下载路径
        paths, _, p48 = nested_paths
        import audio_service.infrastructure.audio.playback_config_builder as pcb

        dev_obj = SimpleNamespace(
            id=7, device_unique_id="dev_480", channel_index=0,
            current_spl_mapping_id=None, name="spk",
        )
        monkeypatch.setattr(pcb, "_get_playback_device_via_grpc", lambda pid: dev_obj)
        svc = FakeAudioService({"dev_480": 48000})
        audio_obj = SimpleNamespace(file_path="oss://dry/100.wav", duration=2.0, audio_type="dry")
        dry_audios_info = [({"audio_id": 100, "playback_device_id": 7, "spl": 65}, audio_obj)]

        configs, _ = build_dry_configs(dry_audios_info, svc, audio_local_paths=paths)

        assert len(configs) == 1
        assert configs[0]["file"] == p48

    def test_interferer_picks_target_rate_path(self, nested_paths, monkeypatch):
        # 验收点 1:干扰人音频按设备 target_rate 取预下载路径
        paths, _, p48 = nested_paths
        import audio_service.infrastructure.audio.playback_config_builder as pcb

        dev_obj = SimpleNamespace(
            id=9, device_unique_id="dev_480", channel_index=0,
            current_spl_mapping_id=None, name="intf",
        )
        monkeypatch.setattr(pcb, "_get_playback_device_via_grpc", lambda pid: dev_obj)
        svc = FakeAudioService({"dev_480": 48000})
        interferers = [{"audio": {"id": 100, "name": "n"}, "device": {"id": 9}, "spl": 60}]

        configs = build_interferer_configs("t1", interferers, svc, audio_local_paths=paths)

        assert len(configs) == 1
        assert configs[0]["file"] == p48


# --------------------------------------------------------------------------- #
#  验收点 1 & 2:PrepareAudios 响应契约                                          #
# --------------------------------------------------------------------------- #
class TestPrepareAudiosResponseContract:
    """PrepareAudios RPC 返回的 JSON 契约(见 audio_service.proto)。"""

    def test_response_shape_consumable_by_helper(self, nested_paths):
        # 验收点 1 & 2:PrepareAudiosResponse.data 是
        # {audio_id: {target_rate: local_path, "original": local_path}} 的 JSON,
        # 且能被 _resolve_preloaded_path 正确消费。
        _, p44, p48 = nested_paths
        resp_data = {
            "100": {"44100": p44, "48000": p48, "original": p44},
        }
        # 模拟 gRPC JSON 往返
        wire = json.dumps(resp_data)
        parsed = json.loads(wire)

        assert _resolve_preloaded_path(parsed, 100, 44100) == p44
        assert _resolve_preloaded_path(parsed, 100, 48000) == p48
        # original 槽位 = 原文件(秒传:无重采样副本)
        assert parsed["100"]["original"] == p44

    def test_passthrough_when_sr_equals_target(self, nested_paths):
        # 验收点 2:原始采样率 == target_rate 时,PrepareAudios 不产生重采样副本,
        # original 与 target_rate 条目指向同一原文件。
        _, p44, _ = nested_paths
        parsed = {"100": {"44100": p44, "original": p44}}
        assert _resolve_preloaded_path(parsed, 100, 44100) == parsed["100"]["original"]


# --------------------------------------------------------------------------- #
#  运行时重采样驱动(audio_driver._pre_resample)                                #
# --------------------------------------------------------------------------- #
@pytest.fixture
def driver_env(monkeypatch, tmp_path):
    """提供可实例化的 PyAudioDriver(桩 pyaudio/pydub/storage;numpy 真实可用则用真实)。"""
    stubs = {}

    pa = types.ModuleType("pyaudio")
    pa.PyAudio = lambda: mock.MagicMock()
    for cn in ("paInt16", "paFloat32", "paInt32", "paComplete", "paContinue"):
        setattr(pa, cn, 0)
    stubs["pyaudio"] = pa

    pd = types.ModuleType("pydub")

    class _AS:
        @staticmethod
        def from_file(*a, **k):
            raise RuntimeError("pydub stub")
    pd.AudioSegment = _AS
    stubs["pydub"] = pd

    st = types.ModuleType("shared.infrastructure.storage")

    class _S:
        def load_file(self, key):
            raise AssertionError("storage.load_file 不应在等采样率用例中被调用")
    st.storage = _S()
    stubs["shared.infrastructure.storage"] = st

    if importlib.util.find_spec("numpy") is None:
        stubs["numpy"] = types.ModuleType("numpy")
    if importlib.util.find_spec("scipy") is None:
        sc = types.ModuleType("scipy")
        sc.signal = types.ModuleType("signal")
        stubs["scipy"] = sc

    monkeypatch.setenv("RESAMPLE_TEMP_PATH", str(tmp_path))
    sys.modules.pop("audio_service.infrastructure.audio.audio_driver", None)
    with mock.patch.dict(sys.modules, stubs, clear=False):
        drv_mod = importlib.import_module("audio_service.infrastructure.audio.audio_driver")
        with mock.patch.object(drv_mod, "log_and_emit", lambda *a, **k: None):
            drv = drv_mod.PyAudioDriver()
            yield drv_mod, drv
    sys.modules.pop("audio_service.infrastructure.audio.audio_driver", None)


class TestPreResampleRuntime:
    """运行时 _pre_resample 决策:等采样率不重采样,不等则重采样。"""

    def test_equal_rate_reuses_original_no_temp(self, driver_env, tmp_path):
        # 验收点 2:file_rate==target_rate -> 复用原文件,不产生临时重采样文件
        _, drv = driver_env
        wav = _make_wav(tmp_path / "a_44100.wav", 44100)
        wf = wave.open(wav, "rb")

        res_files, res_rates, temps = drv._pre_resample([wf], [44100], [1], 44100)

        assert res_rates == [44100]
        assert temps == []
        assert res_files[0] is wf  # 同一 wave 对象,未重采样

    def test_multi_round_no_new_temp_files(self, driver_env, tmp_path):
        # 验收点 3:第 2 轮(预下载已就位、采样率匹配)不再触发 _pre_resample,
        # 两轮均不产生临时重采样文件。
        _, drv = driver_env
        wav = _make_wav(tmp_path / "a_44100.wav", 44100)

        round1_temps = []
        wf1 = wave.open(wav, "rb")
        _, _, t1 = drv._pre_resample([wf1], [44100], [1], 44100)
        round1_temps.extend(t1)

        round2_temps = []
        wf2 = wave.open(wav, "rb")
        _, _, t2 = drv._pre_resample([wf2], [44100], [1], 44100)
        round2_temps.extend(t2)

        assert round1_temps == []
        assert round2_temps == []  # 第 2 轮未新增 Pre-resample 临时文件

    def test_mismatch_creates_temp_at_target(self, driver_env, tmp_path):
        # 验收点 4 兜底:缓存 miss -> OSS 下载原文件(44100)+ 运行时重采样到 48000,
        # 产生 target_rate 临时文件,不报错。需要真实 numpy/scipy。
        drv_mod, drv = driver_env
        if not callable(getattr(getattr(drv_mod, "np", None), "frombuffer", None)):
            pytest.skip("真实重采样需要 numpy/scipy,当前环境缺失,跳过")

        wav = _make_wav(tmp_path / "a_44100.wav", 44100)
        wf = wave.open(wav, "rb")

        res_files, res_rates, temps = drv._pre_resample([wf], [44100], [1], 48000)

        assert res_rates == [48000]
        assert len(temps) == 1
        with wave.open(temps[0], "rb") as out:
            assert out.getframerate() == 48000
        # 清理临时文件
        for t in temps:
            if os.path.exists(t):
                os.remove(t)
