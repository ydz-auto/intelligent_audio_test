# Speaker 感知交叠播放功能设计文档

## 1. 功能概述

### 1.1 问题背景

在多音频重叠播放场景中，存在以下问题：

1. **连续同说话人交叠**：多个连续的同一说话人音频会按 overlap_rate 发生交叠播放，但实际场景中同一说话人的连续语音不应该发生时间重叠
2. **跨音频同一说话人交叠**：不同音频中包含相同说话人时，会发生交叠播放，但该说话人的语音片段实际上不应该重叠

**示例场景**：

```
音频1: [spk9: 0-2s] [spk8: 2-5s]
音频2: [spk9: 0-3s] [spk4: 3-6s]
音频3: [spk7: 0-2s] [spk8: 2-5s]

问题：
- 音频1和音频2都有spk9，不应该交叠
- 音频2和音频3都有spk8，不应该交叠
- 当前逻辑会让它们按overlap_rate交叠
```

### 1.2 解决方案

引入 **Speaker 感知交叠播放** 逻辑：
- 从音频的 diarization 标注中提取 speaker 标签集合
- 比较相邻音频的 speakers 集合
- 有共同 speaker → 顺序播放（不交叠）
- 无共同 speaker → 按 overlap_rate 或 overlap_time 交叠

---

## 2. 技术设计

### 2.1 核心规则

```
相邻音频 speakers 集合有交集 → 顺序播放（start_time = prev_end_time）
相邻音频 speakers 集合无交集 → 按 overlap_rate 或 overlap_time 交叠（start_time = prev_end_time - overlap_time 或 start_time = prev_end_time * (1 - overlap_rate)）
```

**关键实现要点**：
- 使用 `prev_end_time`（上一个音频的实际结束时间）作为计算基准
- **不是** `cumulative_duration`（累计总时长，包含当前音频）

### 2.2 数据来源

从 `audio_annotations` 表查询每个音频的 diarization 标注，提取 `segments` 中的 `speaker` 字段构建 speakers 集合。

**音频标注格式**：
```json
{
  "segments": [
    {"speaker": "spk9", "start": 0, "end": 0.75, "text": "..."},
    {"speaker": "spk8", "start": 0.75, "end": 3.75, "text": "..."},
    {"speaker": "spk9", "start": 3.75, "end": 7.5, "text": "..."}
  ]
}
```

### 2.3 数据结构

```python
# speakers_map: 从 diarization 标注提取
speakers_map = {
    audio_id_1: {'spk9', 'spk8'},  # 音频1同时包含spk9和spk8
    audio_id_2: {'spk9', 'spk4'},  # 音频2同时包含spk9和spk4
    audio_id_3: {'spk7', 'spk8'},  # 音频3同时包含spk7和spk8
}

# 交叠判断
audio1 ∩ audio2 = {'spk9'} → 有交集 → 顺序播放
audio2 ∩ audio3 = {'spk8'} → 有交集 → 顺序播放
```

### 2.4 同声道混合机制

**Speaker 感知逻辑负责判断时序关系（顺序/交叠），实际的同声道混合由 `play_multi` 的 callback 函数处理**。

| 场景 | 时序关系 | 物理层处理 |
|------|---------|-----------|
| 同 speaker + 同声道 | 顺序播放 | 不涉及混合 |
| 不同 speaker + 同声道 | 交叠 | `out_buffer[ch] += audio1 + audio2` 混合 |
| 同 speaker + 不同声道 | 顺序播放 | 不涉及混合 |
| 不同 speaker + 不同声道 | 交叠 | 不同声道输出，无混合 |

**同声道混合原理**（`audio_engine.py` 的 `play_multi` callback）：

```python
# 同一声道上可能有多个音频同时播放
# 使用 += 混合到同一缓冲区位置
out_buffer[ch_idx:limit*stream_channels:stream_channels] += audio_data[:limit]
```

**效果示例**：

```
音频1 (spk0):        [AAAAAAA        ]────────────────────────►  channel=0
音频2 (spk1):             [BBBBB]────────────────────────►  channel=0

时间轴：0 ─────────────────────────────────────────────────►
         0-7s: 只有 spk0 播放
         7-12s: spk0 + spk1 同时播放，信号叠加
         12s+: 只有 spk1 播放
```

---

## 3. 代码实现

### 3.1 标注生成器修改 (reference_params_generator.py)

**新增函数**：`_extract_speakers_from_audio()`

```python
def _extract_speakers_from_audio(audio_id: int) -> set:
    """
    从音频的diarization标注中提取所有speaker集合

    Args:
        audio_id: 音频ID

    Returns:
        set: speaker标签集合，如 {'spk9', 'spk8'}
    """
    if not audio_id:
        return set()

    speakers = set()
    annotations = AudioAnnotation.query.filter_by(
        audio_id=audio_id,
        deleted=False
    ).all()

    for ann in annotations:
        if not ann.data:
            continue

        if isinstance(ann.data, dict):
            segments = ann.data.get('segments', [])
            for seg in segments:
                if 'speaker' in seg:
                    speakers.add(seg['speaker'])
        elif isinstance(ann.data, list):
            for seg in ann.data:
                if isinstance(seg, dict) and 'speaker' in seg:
                    speakers.add(seg['speaker'])

    return speakers
```

**新增函数**：`_calculate_speaker_aware_offsets()`

```python
def _calculate_speaker_aware_offsets(audios_config: List[Dict], overlap_rate: float, overlap_time: float = 0) -> Dict[int, float]:
    """
    计算每个音频播放项的开始时间偏移（speaker感知版本）

    规则：
    - 相邻音频有共同speaker → 顺序播放（start_time = prev_end_time）
    - 相邻音频无共同speaker → 按overlap_time或overlap_rate交叠

    Args:
        audios_config: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate

    Returns:
        {play_order: offset_seconds}
    """
    offsets = {}
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    # 提取每个音频的speaker集合
    audio_speakers = {}
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if audio_id:
            audio_speakers[audio_id] = _extract_speakers_from_audio(audio_id)

    cumulative_duration = 0.0
    prev_end_time = 0.0

    for i, audio_item in enumerate(sorted_audios):
        play_order = audio_item.get('play_order', 0)
        audio_id = audio_item.get('audio_id')

        audio_duration = 1.0
        if audio_id:
            audio = db.session.get(Audio, audio_id)
            if audio and audio.duration:
                audio_duration = audio.duration

        if i == 0:
            offsets[play_order] = 0
        else:
            prev_audio_id = sorted_audios[i-1].get('audio_id')
            curr_speakers = audio_speakers.get(audio_id, set())
            prev_speakers = audio_speakers.get(prev_audio_id, set())

            has_common_speaker = len(curr_speakers & prev_speakers) > 0

            if has_common_speaker:
                # 有共同speaker，顺序播放
                offsets[play_order] = prev_end_time
            else:
                # 无共同speaker，按overlap交叠
                if overlap_time and overlap_time > 0:
                    offset_val = prev_end_time - overlap_time
                    if offset_val < 0:
                        offset_val = 0
                    offsets[play_order] = offset_val
                elif overlap_rate is not None and overlap_rate > 0:
                    offsets[play_order] = prev_end_time * (1 - overlap_rate)
                else:
                    offsets[play_order] = prev_end_time

        prev_end_time = offsets[play_order] + audio_duration
        cumulative_duration += audio_duration

    return offsets
```

**修改**：`generate()` 方法 - 合并 algorithm_params

```python
@classmethod
def generate(cls, test_case) -> list:
    if not test_case:
        return []

    algorithm_type = test_case.algorithm_type
    config = test_case.config or {}

    # 重要：algorithm_params 存储在 test_case.algorithm_params 字段，不是 config 中
    if hasattr(test_case, 'algorithm_params') and test_case.algorithm_params:
        config['algorithm_params'] = test_case.algorithm_params

    # ... 后续逻辑
```

**修改**：`_extract_annotation_with_overlap()`

```python
# 将原来的 _calculate_audio_offsets 调用改为
audio_offsets = _calculate_speaker_aware_offsets(audios_config, overlap_rate, overlap_time)
```

### 3.2 音频引擎修改 (audio_engine.py)

**新增函数**：`extract_speakers_from_annotations()`

```python
def extract_speakers_from_annotations(audio_id, app=None):
    """
    从音频的diarization标注中提取所有speaker集合

    Args:
        audio_id: 音频ID
        app: Flask应用实例

    Returns:
        set: speaker标签集合
    """
    if not audio_id:
        return set()

    speakers = set()

    def _query_annotations():
        from backend.models.models import AudioAnnotation
        return AudioAnnotation.query.filter_by(
            audio_id=audio_id,
            deleted=False
        ).all()

    if app:
        with app.app_context():
            annotations = _query_annotations()
    else:
        annotations = _query_annotations()

    for ann in annotations:
        if not ann.data:
            continue

        if isinstance(ann.data, dict):
            segments = ann.data.get('segments', [])
            for seg in segments:
                if 'speaker' in seg:
                    speakers.add(seg['speaker'])
        elif isinstance(ann.data, list):
            for seg in ann.data:
                if isinstance(seg, dict) and 'speaker' in seg:
                    speakers.add(seg['speaker'])

    return speakers
```

**新增函数**：`build_speakers_map_from_dry_audios()`

```python
def build_speakers_map_from_dry_audios(dry_audios_info, app=None):
    """
    从干声信息列表构建speakers_map

    Args:
        dry_audios_info: 干声列表 [(audio_config, audio_obj), ...]
        app: Flask应用实例

    Returns:
        dict: {audio_id: set(speakers)}
    """
    speakers_map = {}

    for audio_config, audio_obj in dry_audios_info:
        audio_id = audio_config.get('audio_id') if isinstance(audio_config, dict) else getattr(audio_config, 'id', None)
        if audio_id:
            speakers_map[audio_id] = extract_speakers_from_annotations(audio_id, app=app)

    return speakers_map
```

**新增函数**：`calculate_speaker_aware_audio_delays()`

```python
def calculate_speaker_aware_audio_delays(audio_configs, overlap_rate, is_overlap, global_offset=0, overlap_time=0, speakers_map=None):
    """
    计算每个音频的开始时间（speaker感知版本）

    规则：
    - 相邻音频有共同speaker → 顺序播放（start_time = prev_end_time）
    - 相邻音频无共同speaker → 按overlap_rate或overlap_time交叠

    Args:
        audio_configs: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        is_overlap: 是否为重叠播放模式
        global_offset: 全局偏移量
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        speakers_map: {audio_id: set(speakers)}

    Returns:
        list: [(config, start_time), ...] 按 play_order 排序
    """
    dry_configs = [c.copy() for c in audio_configs if not c.get('is_noise', False)]
    sorted_dry = sorted(dry_configs, key=lambda x: x.get('play_order', 0))

    audio_delays_with_config = []
    prev_end_time = 0

    for i, config in enumerate(sorted_dry):
        audio_offset = config.get('offset', 0)
        total_duration = config.get('duration', 0) or get_audio_duration(config['file'])
        effective_duration = max(0, total_duration - audio_offset)

        audio_id = config.get('audio_id')
        curr_speakers = speakers_map.get(audio_id, set()) if speakers_map else set()

        if i == 0:
            start_time = 0
        else:
            prev_audio_id = sorted_dry[i-1].get('audio_id')
            prev_speakers = speakers_map.get(prev_audio_id, set()) if speakers_map else set()

            has_common_speaker = len(curr_speakers & prev_speakers) > 0

            if has_common_speaker:
                start_time = prev_end_time
            else:
                if overlap_time and overlap_time > 0:
                    start_time = prev_end_time - overlap_time
                    if start_time < 0:
                        start_time = 0
                elif overlap_rate is not None and overlap_rate > 0:
                    start_time = prev_end_time * (1 - overlap_rate)
                else:
                    start_time = prev_end_time

        audio_delays_with_config.append((config, start_time))
        prev_end_time = start_time + effective_duration

    # 处理噪声配置
    noise_configs = [c.copy() for c in audio_configs if c.get('is_noise', False)]
    for config in noise_configs:
        audio_delays_with_config.append((config, 0))

    return audio_delays_with_config
```

**修改**：`execute_audio_playback()`

```python
# 构建 speakers_map 并使用 speaker 感知延迟计算
speakers_map = build_speakers_map_from_dry_audios(dry_audios_info, app=app)

audio_delays = calculate_speaker_aware_audio_delays(
    audio_to_play,
    overlap_rate,
    overlap_time > 0,
    global_offset,
    overlap_time,
    speakers_map=speakers_map
)
```

---

## 4. 数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Speaker 感知交叠播放流程                                │
└─────────────────────────────────────────────────────────────────────────────┘

1. 获取用例配置 (config.audios)
   └─ 音频列表: [{audio_id: 101, play_order: 0}, {audio_id: 102, play_order: 1}, ...]

2. 构建 speakers_map
   ├─ 音频101 → 查询 audio_annotations → 提取 speakers → {'spk9', 'spk8'}
   ├─ 音频102 → 查询 audio_annotations → 提取 speakers → {'spk9', 'spk4'}
   └─ 音频103 → 查询 audio_annotations → 提取 speakers → {'spk7', 'spk8'}

3. 计算播放 offset（使用 prev_end_time 而非 cumulative_duration）
   ├─ 音频101: i=0 → offset=0, prev_end_time=2.88
   ├─ 音频102: i=1 → 音频101∩音频102={'spk9'}≠∅ → 顺序播放 → offset=prev_end_time=2.88
   └─ 音频103: i=2 → 音频102∩音频103=∅ → 交叠播放 → offset=prev_end_time(9.37) - overlap_time(2.0) = 7.37

4. 执行播放
   └─ 按计算出的 offset 顺序/交叠播放音频

5. 生成标注
   └─ 使用 speaker-aware offset 调整每个音频的时间戳
   └─ 合并所有音频的 segments
```

---

## 5. 时间轴效果对比

### 5.1 修改前（链式交叠）

```
overlap_rate = 0.3

音频1 (spk9, spk8):        [AAAAAAAAAA            ]────────────────────────►
音频2 (spk9, spk4):             [BBBBB        ]────────────────────────►
音频3 (spk7, spk8):                  [CCCCCC]────────────────────────►

总时长 ≈ 音频1.duration * 0.7 + 音频2.duration * 0.7 + 音频3.duration
```

### 5.2 修改后（Speaker 感知交叠）

```
overlap_rate = 0.3

音频1 (spk9, spk8):        [AAAAAAAAAA            ]────────────────────────►
音频2 (spk9, spk4):                         [BBBBBBBBBB]────────────────────────►
音频3 (spk7, spk8):                                        [CCCCCCCCCC]────────────────────────►

总时长 = 音频1.duration + 音频2.duration + 音频3.duration
```

---

## 6. 适用场景

### 6.1 适用场景

- **声纹识别测试**：多说话人场景下，避免同一说话人的连续语音发生交叠
- **语音转写测试**：参考标注基于 diarization，需要精确还原播放时间轴
- **多轮对话测试**：同一说话人的多轮回复不应交叠

### 6.2 不适用场景

- **纯噪声叠加测试**：只需要噪声和干声叠加，不需要考虑说话人
- **音乐混合测试**：音乐片段的交叠逻辑与语音不同

---

## 7. 修改文件清单

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/algorithm/reference_params_generator.py` | 新增 `_extract_speakers_from_audio()`, `_calculate_speaker_aware_offsets()`；修改 `generate()` 合并 `algorithm_params`；修改 `_extract_annotation_with_overlap()` 使用新函数 |
| `backend/utils/audio_engine.py` | 新增 `extract_speakers_from_annotations()`, `build_speakers_map_from_dry_audios()`, `calculate_speaker_aware_audio_delays()`；修改 `execute_audio_playback()` 使用新函数 |

---

## 8. 测试验证

### 8.1 测试用例设计

**测试场景1**：连续同说话人不交叠

```
音频1: segments=[{spk9, 0-2s}]
音频2: segments=[{spk9, 0-3s}]
音频3: segments=[{spk9, 0-4s}]

预期：三个音频完全顺序播放，总时长=2+3+4=9秒
```

**测试场景2**：不同说话人正常交叠

```
音频1: segments=[{spk9, 0-2s}]
音频2: segments=[{spk8, 0-3s}]  # 无交集

预期：音频2在音频1播放到 (2 * (1 - overlap_rate)) 时开始
```

**测试场景3**：部分交集

```
音频1: segments=[{spk9, 0-2s}, {spk8, 2-5s}]
音频2: segments=[{spk9, 0-3s}, {spk4, 3-6s}]
音频3: segments=[{spk7, 0-2s}, {spk8, 2-5s}]

预期：
- 音频1 ∩ 音频2 = {spk9} → 顺序播放
- 音频2 ∩ 音频3 = {spk8} → 顺序播放
```

### 8.2 日志验证

开启 DEBUG 日志后，可观察到：

```
[_calculate_speaker_aware_offsets] audio_speakers={'61': {'spk0', 'spk1'}, '60': {'spk0', 'spk2', 'spk1'}, '59': {'', 'spk4', 'spk5'}}
[_calculate_speaker_aware_offsets] i=1, prev_audio_id=61, prev_speakers={'spk0', 'spk1'}, curr_speakers={'spk0', 'spk2', 'spk1'}, has_common_speaker=True
[_calculate_speaker_aware_offsets] Has common speaker, sequential playback: offset=prev_end_time=2.88
[_calculate_speaker_aware_offsets] i=2, prev_audio_id=60, prev_speakers={'spk0', 'spk2', 'spk1'}, curr_speakers={'', 'spk4', 'spk5'}, has_common_speaker=False
[_calculate_speaker_aware_offsets] Using overlap_time: offset=prev_end_time(9.37) - 2.0 = 7.37
```

---

## 9. 注意事项

1. **性能影响**：每次播放都需要查询 `audio_annotations` 表提取 speakers，对于大量音频可能影响性能。可以考虑在音频入库时缓存 speakers 集合。

2. **回退机制**：如果音频没有 diarization 标注（speakers 为空集合），则按原有链式交叠逻辑处理。

3. **数据库上下文**：`audio_engine.py` 中的 `extract_speakers_from_annotations()` 需要在 Flask app context 中执行数据库查询，已通过 `app` 参数传递。

4. **向后兼容**：此修改不影响没有 speaker 交集的场景，交叠行为保持不变。

5. **algorithm_params 存储位置**：`TestCase` 模型中 `algorithm_params` 存储在独立的 `_algorithm_params` 字段（通过 `algorithm_params` 属性访问），**不是** `config` 中的一部分。`reference_params_generator.generate()` 需要显式合并后才能正确读取。

---

## 10. Bug 修复记录

### 10.1 offset 计算基准错误（2026-04-20）

**问题描述**：
`reference_params_generator.py` 中的 `_calculate_speaker_aware_offsets()` 函数错误地使用 `cumulative_duration`（累计总时长）作为 offset 计算基准，导致生成的标注时间戳与 `audio_engine` 实际播放时间轴不一致。

**错误代码**：
```python
if has_common_speaker:
    offsets[play_order] = cumulative_duration  # ❌ 错误：包含了当前音频时长
else:
    offset_val = cumulative_duration - overlap_time  # ❌ 错误
```

**正确代码**：
```python
if has_common_speaker:
    offsets[play_order] = prev_end_time  # ✓ 使用上一个音频的结束时间
else:
    offset_val = prev_end_time - overlap_time  # ✓ 使用上一个音频的结束时间
```

**计算示例**：
```
音频0: duration=2.88, start=0, end=2.88
音频1: duration=6.49, start=2.88, end=9.37 (sequential, 因为有共同speaker)
音频2: duration=2.81

错误计算 (cumulative_duration):
  i=2时: cumulative_duration=9.37, offset=9.37-2.0=7.37
  但标注生成时 start = 原始start + offset = 1.0 + 7.37 = 8.37 ❌

正确计算 (prev_end_time):
  i=2时: prev_end_time=9.37, offset=9.37-2.0=7.37
  标注时间戳正确: start = offset = 7.37 ✓
```

### 10.2 algorithm_params 读取失败（2026-04-20）

**问题描述**：
`reference_params_generator.generate()` 方法从 `config` 中读取 `algorithm_params`，但实际上 `algorithm_params` 存储在 `TestCase.algorithm_params` 字段中，导致 `overlap_time` 和 `overlap_rate` 始终为默认值 0。

**修复方案**：
```python
@classmethod
def generate(cls, test_case) -> list:
    algorithm_type = test_case.algorithm_type
    config = test_case.config or {}

    # 重要：algorithm_params 存储在 test_case.algorithm_params 字段
    if hasattr(test_case, 'algorithm_params') and test_case.algorithm_params:
        config['algorithm_params'] = test_case.algorithm_params

    # ... 后续逻辑
```
