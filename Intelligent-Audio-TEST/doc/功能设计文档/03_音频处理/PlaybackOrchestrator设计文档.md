# PlaybackOrchestrator 设计文档

## 概述

PlaybackOrchestrator 是音频播放的编排层，负责将高层配置（round_config / preview_config）转化为底层 `audio_to_play` 列表，最终调用 AudioEngine 执行播放。

**定位**：介于调用方（e2e_executor / testcase_controller）和驱动层（AudioEngine）之间，是三层架构的中间层。

```
调用方层              编排层                    驱动层
e2e_executor    ──→  PlaybackOrchestrator  ──→  AudioEngine
testcase_controller       ↓                         ↓
                     audio_to_play              pyaudio stream
```

## 职责边界

**Orchestrator 负责**：
- 解析音频配置（干声/噪声/干扰人分类）
- 设备绑定（device_unique_id → device_index）
- SPL 增益计算（target_spl → digital_gain）
- 时间轴调度（交叠/顺序/speaker 感知）
- 构建统一 `audio_to_play` 列表

**Orchestrator 不负责**：
- PyAudio 流操作（AudioDriver）
- 时间轴计算细节（audio_engine 模块函数）
- 单音频直接播放（B 类调用方直接用 AudioService）

## 高层 API

### play_round()

E2E 测试单轮播放，处理主讲人 + 噪声 + 干扰人。

```python
def play_round(self, round_config, device_info_list, task_id,
               case_config=None, test_case_id=None):
    """
    Args:
        round_config: 本轮配置 dict
            - audios: 主讲人列表 [{audio_id, playback_device_id, play_order}, ...]
            - backgroundNoise: 噪声配置 {audio_id, spl, device_ids}
            - interferers: 干扰人列表 [{audio, device, spl, startDelay, loop}, ...]
        device_info_list: 可用设备信息（含 device_sn, driver, current_spl_mapping_id）
        task_id: 任务ID
        case_config: 用例全局配置（fallback 噪声配置）
        test_case_id: 测试用例关联ID

    Returns:
        {'audio_timelines': [...], 'playback_result': True}
        失败返回 None
    """
```

**调用方**：`E2EExecutor._execute_e2e_with_rounds()`

### preview()

用例预览播放，支持 offset 偏移。

```python
def preview(self, audio_configs, case_config, task_id,
            offset=0, overlap_rate=0, overlap_time=0):
    """
    Args:
        audio_configs: 音频配置列表 [{audio_id, playback_device_id}, ...]
        case_config: 用例配置（含 background_noise）
        task_id: 预览任务ID
        offset: 播放起始偏移（秒）
        overlap_rate / overlap_time: 交叠参数

    Returns:
        {'audio_timelines': [...], 'total_duration': float}
    """
```

**调用方**：`TestCaseController.preview()`

### play_voiceprint()

声纹注册播放。

```python
def play_voiceprint(self, vp_config, device_info_list, task_id):
    """
    Args:
        vp_config: 声纹配置 {audio: {id, name}, device: {id, name}, spl, waitTime}
        device_info_list: 可用设备信息
        task_id: 任务ID

    Returns:
        True: 注册成功 / 不需要注册
        False: 注册失败
    """
```

**调用方**：`E2EExecutor._execute_e2e_with_rounds()` 循环前

## 内部方法

### 配置构建

| 方法 | 用途 | 输出 |
|------|------|------|
| `_resolve_dry_audios()` | 分类干声/噪声，加载 Audio 对象 | `[(audio_config, audio_obj), ...]` |
| `_build_noise_info()` | 解析噪声音频和设备 | `(noise_info, noise_devices)` |
| `_build_dry_configs()` | 主讲人 audio_to_play 配置 | `(configs, playback_devices_map)` |
| `_build_noise_play_configs()` | 噪声 audio_to_play 配置 | `[configs]` |
| `_build_interferer_configs()` | 干扰人 audio_to_play 配置 | `[configs]` |

### 工具方法

| 方法 | 用途 |
|------|------|
| `_find_device_obj()` | 兼容 dict/ORM 对象，按 ID 查找设备 |
| `_resolve_spl_gain()` | SPL mapping → digital_gain |
| `_extract_overlap_rate()` | 从 case_config 提取 overlap_rate |
| `_extract_overlap_time()` | 从 case_config 提取 overlap_time |
| `_prepare_preview_playback_info()` | preview 场景的音频/设备分类 |

## 语义拆分

Orchestrator 构建的 `audio_to_play` 列表包含三类音频，通过三个字段区分：

```python
# 主讲人
{
    'type': 'dry',           # 来源：dry / noise / interferer
    'is_noise': False,       # 音频类型：人声
    'loop': False,           # 播放行为：不循环
    'delay': 0,              # 无延迟
    ...
}

# 噪声
{
    'type': 'noise',
    'is_noise': True,        # 背景音
    'loop': True,            # 循环播放
    'delay': 0,              # 强制为 0
    ...
}

# 干扰人
{
    'type': 'interferer',
    'is_noise': False,       # 人声
    'loop': True/False,      # 可配置
    'delay': startDelay/1000, # 保留（ms → s）
    ...
}
```

**三字段语义**：

| 字段 | 含义 | 主讲人 | 噪声 | 干扰人 |
|------|------|--------|------|--------|
| `type` | 来源分类 | `dry` | `noise` | `interferer` |
| `is_noise` | 音频类型（人声/背景音） | `False` | `True` | `False` |
| `loop` | 播放行为（是否循环） | `False` | `True` | 可配置 |

## 延迟计算

Orchestrator 调用 `calculate_speaker_aware_audio_delays()` 计算延迟，按 `type` 分类处理：

| 类型 | 延迟计算 | 参与干声交叠 |
|------|----------|--------------|
| `dry` | speaker 感知（共同 speaker → 顺序，否则 → 交叠） | ✅ |
| `noise` | 强制 `delay=0` | ❌ |
| `interferer` | 保留 `startDelay`（ms → s） | ❌ |

## 调用链路

```
E2EExecutor._execute_e2e_with_rounds()
    ↓
PlaybackOrchestrator.play_round(round_config, ...)
    ↓
1. _resolve_dry_audios()         → 分类干声/噪声
2. _build_noise_info()           → 解析噪声配置
3. _build_dry_configs()          → 主讲人 audio_to_play
4. _build_noise_play_configs()   → 噪声 audio_to_play
5. _build_interferer_configs()   → 干扰人 audio_to_play
6. build_audio_timelines()       → 交叠时间轴（speaker 感知）
7. 合并三类音频为 audio_to_play
8. calculate_speaker_aware_audio_delays() → 延迟计算
    ↓
AudioService.play_overlap(audio_to_play, ...)
    ↓
按 device_index 分组 → play_multi()
    ↓
pyaudio stream + callback（use_loop = is_noise or loop）
```

## 与旧代码对比

**旧架构**（2026-06 之前）：
- `audio_engine.prepare_audio_playback_info()` — 配置准备
- `audio_engine.execute_audio_playback()` — 播放执行
- `e2e_executor._build_interferer_configs()` — 干扰人配置
- `e2e_executor._execute_audio_playback()` — E2E 播放
- `testcase_controller` 内嵌 `play_audio()` 函数 — 预览播放

**问题**：
- 配置构建和播放执行混杂在 audio_engine.py（700+ 行）
- 干扰人 `is_noise=bool(loop)` 语义错误，导致 loop 不生效
- 干声/噪声/干扰人三类音频未明确区分

**新架构**：
- `PlaybackOrchestrator` 统一编排（~500 行）
- 语义拆分：`type` / `is_noise` / `loop` 三字段独立
- 调用方只传高层配置，不关心底层细节

## 测试覆盖

纯计算逻辑测试（不依赖数据库）：

```bash
pytest backend/tests/test_audio_engine_pure.py -v
```

**测试范围**（48 个用例）：
- `calculate_audio_delays`: 三类音频延迟分离
- `calculate_speaker_aware_audio_delays`: speaker 感知版
- `use_loop = is_noise or loop`: 循环触发条件
- `all_empty` / `all_dry_finished`: 排除循环音频
- 语义拆分：`type` / `is_noise` / `loop` 字段独立性
- 回归测试：旧 bug（干扰人 loop 不生效）

## 关键文件

| 文件 | 用途 |
|------|------|
| `backend/services/audio/playback_orchestrator.py` | Orchestrator 实现 |
| `backend/services/audio/audio_engine.py` | 驱动层（AudioService、PyAudioDriver） |
| `backend/services/execution/e2e_executor.py` | E2E 测试调用方 |
| `backend/controllers/testcase_controller.py` | 预览调用方 |
| `backend/tests/test_audio_engine_pure.py` | 纯计算逻辑测试 |

## 扩展指南

**新增音频类型**：
1. 在 `_build_*_configs()` 中添加新类型的配置构建方法
2. 在 `calculate_audio_delays()` 中添加延迟计算逻辑
3. 在 `play_multi` 回调中添加行为处理（如需要）
4. 更新测试用例

**新增播放场景**：
1. 在 Orchestrator 中添加高层 API（如 `play_api_test()`）
2. 复用内部方法构建配置
3. 调用 `AudioService.play_overlap()` 执行
4. 在调用方（controller / executor）中调用新 API