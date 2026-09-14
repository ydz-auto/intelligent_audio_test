# 混音与 SPL 映射

> 版本：v1.1 | 日期：2026-09-10 | 状态：最终方案
>
> **v1.1 变更**：
> 1. **重构：`AudioStreamOrchestrator` 作为编排路由层**——接收执行设备类型（device_type），路由到具体混音路径：
>    - HTTP 非实时 → `RenderAudioFile`（unary）：整段混音 → 整文件 POST
>    - HTTP 流式 / WebSocket Realtime → `RenderAudioStream`（server-streaming）：逐帧流式混音 → chunk SSE/WS 推送
>    - E2E 物理设备 → `device_driver`：PyAudio callback 实时混音 → 物理播放
> 2. 新增：**格式适配层**（`AudioFormatAdapter`）——不同被测 API 的采样率/位深/通道数不同，混音前统一适配到 `api.audio_config` 声明的目标格式（重采样 / 位深转换 / 上混下混）。

---

## 一、概述

API 类测试需要将主讲人音频、干扰人音频、背景噪声混音后，按被测 API 要求的格式输出。**由 `AudioStreamOrchestrator` 根据执行模式路由到三条混音路径**：

| 被测设备 | 混音路径 | 混音方式 | 混音产物 | 推送方式 |
|---------|---------|---------|---------|---------|
| HTTP API（非实时） | `RenderAudioFile`（unary RPC） | 整段混音 | 完整 PCM（包装为请求要求的格式） | 一次性 HTTP POST |
| HTTP API（流式） | `RenderAudioStream`（server-streaming RPC） | 逐帧流式混音 | base64 PCM chunk | SSE 逐 chunk 推送 |
| WebSocket API（Realtime） | `RenderAudioStream`（server-streaming RPC） | 逐帧流式混音 | base64 PCM chunk | WS 逐 chunk 推送 |
| E2E 物理设备（对照） | `device_driver` | callback 实时混音 | int16 帧 → 声卡 | PyAudio 物理播放 |

> **结论**：三种 API 模式的混音**不是同一套流程**——非实时走 `RenderAudioFile`（等所有音频齐了一次性混整段），流式/Realtime 走 `RenderAudioStream`（一边收 chunk 一边逐帧混）。`AudioStreamOrchestrator` 只负责**路由编排**，把请求分发到正确的路径；混音前都要经过**格式适配**，统一到被测 API 要求的采样率/位深/通道数。

### 与 E2E 混音的区别

| 维度 | E2E (audio_driver + spl_service) | API 类 (Orchestrator + ApiRmsSplService) |
|------|----------------------------------|-----------------------------------------------------|
| 混音时机 | 实时（PyAudio callback 内逐帧混音） | 非实时：整段混音（等所有音频齐了一次性混整段）；流式/Realtime：逐帧流式混音（一边收 chunk 一边混） |
| 混音实现 | `_create_multi_callback` 内 `+=` 叠加 | `np.zeros` + `+=` 叠加（float32 缓冲） |
| 格式适配 | 声卡格式（PyAudio 自动处理） | `AudioFormatAdapter` → `api.audio_config`（重采样/位深/通道） |
| RMS 补偿 | `calculate_gain_compensation` (file→dBFS→gain) | `_rms_compensate` (bytes→numpy→dBFS→gain) |
| SPL 映射 | `SPLMappingService.spl_to_gain` (device→DB) | `ApiRmsSplService.spl_to_gain` (api_id→DB) |
| SPL 关联 | `PlaybackDevice` 1:N `SPLMapping` | `API` 1:N `ApiRmsSplMapping` |
| SPL 校准 | 物理校准（播放测试音 + 实测 SPL） | 数字校准（发送已知 RMS + 评估识别效果） |
| 增益链路 | `effective = audio_gain × GLOBAL_SAFE × gain_comp` | `effective = spl_gain × rms_compensate` |
| 输出 | int16 → PyAudio stream | 目标格式 PCM → 整文件 / base64 chunk |
| 防削波 | `np.clip(-32768, 32767)` | `np.clip` 按目标位深满量程 |
| 背景 | 物理设备同时播放 | 混入轮次混音缓冲（不单独推送） |

---

## 二、格式适配层（v1.1 新增）

### 2.1 为什么需要

不同被测 API 对输入音频的格式要求不同：

| 被测 API | 采样率 | 位深 | 通道 |
|---------|--------|------|------|
| OpenAI Realtime | 24000 Hz | 16bit (pcm16) | mono |
| 某厂商 A | 16000 Hz | 16bit | mono |
| 某厂商 B | 8000 Hz | 16bit（电话线路） | mono |
| 某厂商 C | 44100 Hz | 24bit | stereo |

而音频库里的素材采样率/位深/通道五花八门（16k/44.1k/48k，16/24/32bit，mono/stereo）。**不同采样率的样本无法直接叠加**，必须先把所有源统一适配到目标格式，再进入 RMS 补偿和混音。

### 2.2 目标格式声明：`api.audio_config`

目标格式挂在被测 API 上（`apis` 表 JSON 字段），配置化、无硬编码：

```json
{
  "sample_rate": 24000,
  "bit_depth": "s16",
  "channels": 1,
  "container": "pcm"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sample_rate` | int | 目标采样率（Hz） |
| `bit_depth` | enum | `s16` / `s24` / `s32` |
| `channels` | int | 1=mono，2=stereo |
| `container` | enum | `pcm`（裸流）/ `wav`（非实时整文件常用） |

> `audio_config` 未配置时回退默认值 `24000/s16/mono`（OpenAI Realtime 兼容格式）。

### 2.3 AudioFormatAdapter

> 文件：`backend/services/audio/audio_format_adapter.py`

```python
class BitDepth(Enum):
    S16 = ('s16', 2, 32768)   # (名称, 字节数, 满量程)
    S24 = ('s24', 3, 8388608)
    S32 = ('s32', 4, 2147483648)


class AudioFormatAdapter:
    """音频格式适配器：位深转换 → 重采样 → 通道上下混

    适配时机：混音之前（Step 2）——不同采样率的样本无法直接叠加，
    所有源必须先统一到 api.audio_config 声明的目标格式。
    """

    DEFAULT_FORMAT = {'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1}

    @staticmethod
    def resolve_target_format(api) -> dict:
        """读取 api.audio_config，未配置回退 DEFAULT_FORMAT"""

    @staticmethod
    def detect_source_format(pcm: bytes, audio_file) -> AudioFormat:
        """源格式优先级：
        1. audio_file 表元数据（sample_rate/bit_depth/channels 字段）
        2. WAV 头解析（wave/soundfile）
        3. 库内默认（24kHz/16bit/mono）
        """

    @staticmethod
    def adapt(pcm: bytes, src: AudioFormat, dst: AudioFormat) -> bytes:
        """src → dst 转换（固定顺序）：
        1. 位深归一化 → float32 [-1.0, 1.0]
        2. 重采样 src_rate → dst_rate
        3. 通道转换 src_ch → dst_ch
        4. 按目标位深度化
        """

    @staticmethod
    def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        """重采样：scipy.signal.resample_poly（有理分数重采样，抗混叠）
        上下取整 gcd 化简；采样率相同直接返回"""

    @staticmethod
    def convert_bit_depth(samples: np.ndarray, src: BitDepth, dst: BitDepth) -> np.ndarray:
        """位深转换：先归一化 float32，再量化到目标位深（避免 16→24 直接移位溢出）"""

    @staticmethod
    def convert_channels(samples: np.ndarray, src_ch: int, dst_ch: int) -> np.ndarray:
        """通道转换：
        - 下混 stereo→mono：L/R 均值
        - 上混 mono→stereo：复制（interleaved 排列）
        - N→M 其他组合：抛配置错误（不静默兜底）
        """
```

> **设计原则**：转换顺序固定为「位深 → 采样率 → 通道」。下混发生在重采样之后（对 mono 重采样再扩展，比先重采样双声道再下混节省一半算力）；位深先归一化 float32 再量化，避免截断误差累积。

---

## 三、核心组件

### 3.1 AudioStreamOrchestrator（编排路由层）

> 文件：`backend/services/audio/audio_stream_orchestrator.py`

负责**混音路径的编排路由**：接收执行设备类型（device_type），分发到具体混音路径。自身不直接实现混音，而是持有公共前置逻辑（噪声合并、格式适配、RMS/SPL 增益）并路由：

```python
class AudioStreamOrchestrator:
    DEFAULT_SAMPLE_RATE = 24000   # api.audio_config 未配置时的回退值（OpenAI 兼容）
    DEFAULT_SAMPLE_WIDTH = 2      # 16bit
    TARGET_RMS_DBFS = -30.0       # 与 audio_driver.calculate_gain_compensation 一致
    chunk_duration_ms = 100       # 流式切片时长（RenderAudioStream 用）

    @staticmethod
    def route(device_type: str, request) -> Response:
        """编排路由：根据执行模式分发到具体混音路径
        - device_type == 'http_api' 且 stream=False  → RenderAudioFile (unary)
        - device_type == 'http_api' 且 stream=True   → RenderAudioStream (server-streaming)
        - device_type == 'websocket_api'             → RenderAudioStream (server-streaming)
        - device_type == 'physical'                  → device_driver（E2E，不经此处）
        """

    @staticmethod
    def _resolve_noise(round_config, global_bg):
        """公共前置：合并噪声配置（轮次级 > 全局级）"""

    @staticmethod
    def _apply_format_and_gain(sources, api, target_format):
        """公共前置：格式适配 + RMS 补偿 + SPL 增益（两条 API 路径共用）"""
```

### 3.2 RenderAudioFile（unary RPC — HTTP 非实时）

> 文件：`backend/services/audio/render_audio_file.py`

**整段混音**：等所有音频齐了 → 一次性混整段 → 输出完整文件 → HTTP POST。

```python
class RenderAudioFile:
    """HTTP 非实时混音 RPC（unary：请求 → 完整音频文件响应）

    混音时机：执行中，等所有音频齐了 → 一次性混整段
    混音产物：完整 PCM（包装为 api.audio_config.container 要求格式）
    结果交付：一次性 HTTP POST，等完整 JSON 响应
    """

    def render(self, audios_config, audio_loader, background_noise,
               api, target_format) -> bytes:
        """整段混音流程：
        Step 1  加载各源 PCM（主讲人 + 干扰人 + 噪声）
        Step 2  格式适配（AudioFormatAdapter → api.audio_config）
        Step 3  RMS 补偿 + SPL 增益（ApiRmsSplService）
        Step 4  时间轴编排（speaker 感知交叠）
        Step 5  整段混音叠加（float32 缓冲，一次性混完）
        Step 6  整段量化输出（wav/pcm 包装，无切片）
        """
```

### 3.3 RenderAudioStream（server-streaming RPC — HTTP 流式 / Realtime）

> 文件：`backend/services/audio/render_audio_stream.py`

**逐帧流式混音**：一边收 chunk 一边混 → 100ms chunk → SSE/WS 推送。

```python
class RenderAudioStream:
    """流式混音 RPC（server-streaming：请求 → chunk 流式响应）

    混音时机：执行中，一边收 chunk 一边逐帧混
    混音产物：100ms base64 PCM chunk
    结果交付：HTTP 流式 → SSE 逐 chunk 推送；Realtime → WS 逐 chunk 推送 + sleep 模拟实时速率
    """

    def render(self, audios_config, audio_loader, background_noise,
               api, target_format) -> Iterator[str]:
        """逐帧流式混音流程：
        Step 1  加载各源 PCM
        Step 2  格式适配（AudioFormatAdapter → api.audio_config）
        Step 3  RMS 补偿 + SPL 增益（ApiRmsSplService）
        Step 4  时间轴编排（计算 100ms 窗口边界）
        Step 5  按 100ms 窗口逐帧混音（滑动窗口内叠加）
        Step 6  逐窗口量化 → base64 PCM chunk → yield
        """
```

### 3.4 ApiRmsSplService

> 文件：`backend/services/audio/api_rms_spl_service.py`

负责被测 API 的 RMS→SPL 映射，与 E2E 的 `SPLMappingService` 对称。**三种 API 模式通用**。

```python
class ApiRmsSplService:
    @staticmethod
    def spl_to_gain(api_id: int, target_spl: float) -> float:
        """查 api_id 关联的映射 → 计算 gain"""

    @staticmethod
    def spl_to_gain_by_mapping(mapping, target_spl: float) -> float:
        """用预加载的映射对象计算 gain（避免重复查 DB）"""

    @staticmethod
    def _linear_approx(target_spl: float) -> float:
        """无映射时的线性近似：gain = 10^((target_spl - 65) / 20)"""
```

---

## 四、噪声合并优先级

```
┌──────────────────────────────────────────────────────────────┐
│                    噪声合并规则                                │
│                                                              │
│  数据源:                                                      │
│    轮次级: round_config.background_noise                      │
│    全局级: case_config.background_noise                       │
│                                                              │
│  优先级:                                                      │
│    1. 轮次级有噪声 → 用轮次级                                │
│    2. 轮次级无噪声 → 用全局级                                │
│    3. 两者都无 → 不混噪声                                    │
│                                                              │
│  合并后: background_noise = {audio_id, spl, loop, ...}       │
│  → AudioStreamOrchestrator 公共前置（噪声合并 + 格式适配 + 增益） │
└──────────────────────────────────────────────────────────────┘
```

```python
# RealtimeSessionExecutor / APISessionExecutor 共用
def _resolve_noise(self, round_config, global_bg):
    """合并噪声配置：轮次级 > case 级"""
    round_bg = round_config.get('background_noise')
    if round_bg:
        return round_bg      # 轮次级优先
    return global_bg          # 回退到全局级
```

### 噪声配置结构

```json
{
  "audio_id": 42,
  "audio_name": "咖啡厅噪声",
  "spl": 55.0,
  "loop": true,
  "delay": 0
}
```

| 字段 | 说明 |
|------|------|
| `audio_id` | 噪声音频文件 ID |
| `spl` | 噪声目标声压级（dB SPL） |
| `loop` | 是否循环铺满整个轮次时长 |
| `delay` | 噪声开始时间偏移（ms），默认 0 = 从轮次开始就混入 |

---

## 五、混音流程

> **Step 1-4（加载 / 格式适配 / RMS+SPL / 时间轴）为 `RenderAudioFile` 与 `RenderAudioStream` 共用**；Step 5/6 按路径分叉：
> - `RenderAudioFile`（HTTP 非实时）：整段混音 → 整段量化输出（wav/pcm 包装，无切片）
> - `RenderAudioStream`（HTTP 流式 / Realtime）：100ms 窗口逐帧混音 → 逐窗口量化输出（base64 chunk）

```
┌──────────────────────────────────────────────────────────────┐
│          RenderAudioFile / RenderAudioStream 混音流程         │
│                                                                │
│  输入: audios_config = [                                       │
│    {audio_id:1, type:'speaker',   spl:65, delay:0},           │
│    {audio_id:2, type:'interferer', spl:55, delay:2000},      │
│  ]                                                              │
│  background_noise = {audio_id:3, spl:45, loop:true}           │
│  target_format = api.audio_config                              │
│    = {sample_rate:16000, bit_depth:'s16', channels:1}          │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─ Step 1: 加载各源 PCM（主讲人 + 干扰人 + 噪声）────────┐   │
│  │  audio_loader(1) → speaker_pcm    (源格式 44.1k/24bit) │   │
│  │  audio_loader(2) → interferer_pcm (源格式 48k/16bit)   │   │
│  │  audio_loader(3) → noise_pcm      (源格式 44.1k/16bit) │   │
│  │                                                         │   │
│  │  sources = [                                            │   │
│  │    {config, pcm, type:'speaker',   target_spl:65},     │   │
│  │    {config, pcm, type:'interferer', target_spl:55},    │   │
│  │    {config, pcm, type:'noise',      target_spl:45,     │   │
│  │     loop:True},                                        │   │
│  │  ]                                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 2: 格式适配 — 统一到 api.audio_config ──────────┐   │
│  │  对每个 source:                                          │   │
│  │    src_fmt = AudioFormatAdapter.detect_source_format(   │   │
│  │                  pcm, audio_file)                       │   │
│  │    dst_fmt = AudioFormatAdapter.resolve_target_format(  │   │
│  │                  api)  # 16k/s16/mono                   │   │
│  │    src['pcm'] = AudioFormatAdapter.adapt(               │   │
│  │                    pcm, src_fmt, dst_fmt)               │   │
│  │                                                         │   │
│  │  转换顺序（固定）:                                       │   │
│  │    位深: 24bit → float32 → 16bit                        │   │
│  │    采样率: 44100 → resample_poly → 16000                │   │
│  │    通道: stereo → 下混均值 → mono                       │   │
│  │                                                         │   │
│  │  ★ 混音前必须适配：不同采样率样本无法直接叠加          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 3: RMS 补偿 + SPL 增益 ────────────────────────┐    │
│  │  对每个 source（已统一格式）:                            │    │
│  │                                                          │    │
│  │  3a. RMS 补偿（归一化到 -30 dBFS）:                      │    │
│  │      rms = sqrt(mean(samples²))                         │    │
│  │      current_db = 20 * log10(rms / 32768)               │    │
│  │      gain_db = -30 - current_db                          │    │
│  │      gain_comp = 10 ^ (gain_db / 20)                    │    │
│  │      samples *= gain_comp                                │    │
│  │                                                          │    │
│  │  3b. SPL 增益（按被测 API 映射调整）:                    │    │
│  │      if rms_spl_mapping:                                 │    │
│  │        gain = ApiRmsSplService.spl_to_gain_by_mapping(  │    │
│  │                    mapping, target_spl)                 │    │
│  │      elif api_id:                                        │    │
│  │        gain = ApiRmsSplService.spl_to_gain(             │    │
│  │                    api_id, target_spl)                  │    │
│  │      else:                                               │    │
│  │        gain = _linear_approx(target_spl)                │    │
│  │                                                          │    │
│  │      src['gain_linear'] = gain                           │    │
│  │                                                          │    │
│  │  示例结果:                                               │    │
│  │    speaker(65dB):   gain=10^((65-65)/20)=1.0            │    │
│  │    interferer(55dB): gain=10^((55-65)/20)=0.316         │    │
│  │    noise(45dB):     gain=10^((45-65)/20)=0.1             │    │
│  │    → 相对能量比 = speaker:interferer:noise = 1:0.3:0.1   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 4: 时间轴编排 — speaker 感知交叠 ───────────────┐    │
│  │  calculate_speaker_aware_audio_delays(audios_config)    │    │
│  │  → timeline = [                                         │    │
│  │    {audio_id:1, start_time_ms:0,    end_time_ms:3000},  │    │
│  │    {audio_id:2, start_time_ms:2000, end_time_ms:4500},  │    │
│  │  ]                                                      │    │
│  │  (噪声不参与时间轴计算，单独按 loop/delay 混入)         │    │
│  │                                                          │    │
│  │  计算总时长（按目标采样率）:                             │    │
│  │    max_end_ms = max(end_time_ms)                        │    │
│  │    total_samples = 16000 * max_end_ms / 1000            │    │
│  │    mix_buffer = np.zeros(total_samples, dtype=float32)  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 5A: 整段混音（RenderAudioFile 路径）────────────────┐  │
│  │  mix_buffer = np.zeros(total_samples, dtype=float32)      │  │
│  │  对每个 source:                                           │  │
│  │    samples *= gain_linear                                │  │
│  │    if type == 'noise' and loop:   # 铺满整个混音缓冲      │  │
│  │      for i in range(0, buf_len, len(noise)):             │  │
│  │        mix_buffer[i:end] += noise[:chunk_len]            │  │
│  │    else:                   # 按 start_time 混入          │  │
│  │      mix_buffer[start:end] += samples                    │  │
│  │  mix_buffer = Σ (各源 × gain)  ← 一次性混完整段          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 5B: 逐帧流式混音（RenderAudioStream 路径）───────────┐ │
│  │  按 100ms 滑动窗口推进:                                    │  │
│  │  for w in range(0, total_samples, window_samples):        │  │
│  │    window_buffer = np.zeros(window_samples, float32)      │  │
│  │    for source:  # 窗口内取与 [w, w+window) 相交的片段叠加  │  │
│  │      seg = source_samples[w : w+window] × gain            │  │
│  │      window_buffer += seg                                 │  │
│  │    yield Step 6 产物                                       │  │
│  │  (一边收 chunk 一边混 — 窗口边界由 Step 4 时间轴决定)      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 6A: 整段量化输出（RenderAudioFile）──────────────────┐ │
│  │  mix_buffer → np.clip(±满量程) → int16 量化                │  │
│  │  → AudioFormatAdapter.wrap_container(wav/pcm)             │  │
│  │  → 一次性 HTTP POST（无切片）                              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 6B: 逐窗口量化输出（RenderAudioStream）──────────────┐ │
│  │  各 100ms 窗口: np.clip → 量化 → base64 PCM chunk          │  │
│  │  chunk_samples = 16000 * 100ms / 1000 = 1600 samples      │  │
│  │  chunk_bytes    = 1600 * 2 = 3200 bytes                   │  │
│  │  → yield [chunk_0, chunk_1, ..., chunk_N]                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                     │
│                          ▼                                     │
│  输出交付（由 executor 决定）:                                  │
│    - Realtime(HTTP 流式):  for chunk: SSE/WS 推送 + sleep      │
│    - HTTP 非实时:          b''.join(decode(chunks)) → wav POST │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、SPL 映射对称设计

### 6.1 为什么要两套 SPL 映射

| 场景 | E2E 物理设备 | API 类（非实时/流式/Realtime 通用） |
|------|-------------|-------------------------------------|
| 用户配的声压 | 65 dB SPL | 65 dB SPL |
| 实际含义 | 物理音箱在 1m 处产生 65 dB | 数字音频的 RMS 对应 65 dB |
| 需要校准的对象 | **物理音箱**（不同音箱增益不同） | **被测 API**（不同 API 对输入 RMS 处理不同） |
| 映射关联实体 | `PlaybackDevice`（音箱） | `API`（被测 API） |
| 映射关系 | device 1:N SPLMapping | api 1:N ApiRmsSplMapping |

> 用户在用例里配的是声压（SPL），不是 RMS，也不是在音频文件里配。声压映射在执行时根据被测设备类型查不同的映射表。

### 6.2 SPL 映射模型

```python
# E2E 物理设备映射（现有）
class SPLMapping(db.Model):
    __tablename__ = 'spl_mappings'
    id = Column(Integer, primary_key=True)
    playback_device_id = Column(Integer, ForeignKey('playback_devices.id'))
    # device 1:N SPLMapping

# API 类映射（新增，非实时/流式/Realtime 通用）
class ApiRmsSplMapping(db.Model):
    __tablename__ = 'api_rms_spl_mappings'
    id = Column(Integer, primary_key=True)
    api_id = Column(Integer, ForeignKey('apis.id'))
    name = Column(String(100))
    description = Column(Text)
    target_spl = Column(Float)           # 目标声压级
    digital_gain = Column(Float)         # 数字增益
    calibration_status = Column(String(20), default='uncalibrated')
    calibration_data = Column(JSON)       # 校准数据
    # api 1:N ApiRmsSplMapping
```

### 6.3 增益计算链路

```
E2E 链路:
  用户配 SPL=65dB
    → SPLMappingService.spl_to_gain(device, 65) → gain_db (查设备映射表)
    → effective = audio_gain × GLOBAL_SAFE × gain_comp (RMS补偿)
    → PyAudio 播放

API 链路（非实时/流式/Realtime 通用）:
  用户配 SPL=65dB
    → ApiRmsSplService.spl_to_gain(api_id, 65) → gain_linear (查 API 映射表)
    → samples *= gain_linear × rms_compensate (RMS补偿)
    → 非实时: 整文件 POST | 流式: SSE chunk | Realtime: WS chunk
```

### 6.4 SPL 未配置时的行为

> 用户在用例导入时，不一定会设定声压级等数据。如果没设定，就将原始音频不变动 RMS 传递给被测 API。

```python
# 无 SPL 配置时 → gain=1.0，原始 RMS 不变（格式适配仍然执行）
if target_spl is None:
    gain_linear = 1.0   # 原始音频不动
else:
    # 有 SPL → 查映射 → 调整增益
    gain_linear = ApiRmsSplService.spl_to_gain(api_id, target_spl)
```

| 场景 | SPL 配置 | RMS 补偿 | SPL 增益 | 最终 gain |
|------|---------|---------|---------|-----------|
| 未配 SPL | 无 | 不补偿 | 1.0 | 1.0（原始不动） |
| 配了 SPL，无映射 | 65 dB | 归一化到 -30 dBFS | `_linear_approx(65)` | `rms_comp × linear` |
| 配了 SPL，有映射 | 65 dB | 归一化到 -30 dBFS | 查映射表 | `rms_comp × mapped_gain` |

---

## 七、executor 中的混音调用

### 7.1 RealtimeSessionExecutor（WebSocket，chunk 流式推送）

```python
def _execute_normal_round(self, adapter, round_config, ...):
    # 1. 合并噪声配置（轮次级 > 全局级）
    background_noise = self._resolve_noise(round_config, global_bg)

    # 2. 逐帧流式混音（RenderAudioStream：一边收 chunk 一边混）
    chunks = RenderAudioStream.render(
        audios_config=round_config.get('audios', []),
        audio_loader=self._load_audio_fn(case_config),
        background_noise=background_noise,
        api_id=data['api_configs'][0].id,
        target_format=adapter.target_format,   # api.audio_config
    )

    # 3. 流式推送
    for chunk_b64 in chunks:
        adapter.send(chunk_b64, is_audio=True)
        time.sleep(adapter._chunk_duration_ms / 1000)  # 模拟实时速率

    # 4. 标记输入结束
    adapter.commit_input()

    # 5. 等 AI 完整回复
    adapter.post_process(is_interruption=False)
```

```python
def _execute_interruption_round(self, adapter, round_config, ...):
    # 1. 等 AI 开始说话
    adapter.post_process(start_timeout=25, is_interruption=True)

    # 2. 延迟（等 AI 说一会儿）
    time.sleep(round_config.get('interruption_delay_ms', 1000) / 1000)

    # 3. 逐帧流式混音（RenderAudioStream：一边收 chunk 一边混，打断音频 + 噪声）
    background_noise = self._resolve_noise(round_config, global_bg)
    chunks = RenderAudioStream.render(
        audios_config=round_config.get('audios', []),
        audio_loader=self._load_audio_fn(case_config),
        background_noise=background_noise,
        api_id=data['api_configs'][0].id,
        target_format=adapter.target_format,
    )

    # 4. 流式推送打断音频
    for chunk_b64 in chunks:
        adapter.send(chunk_b64, is_audio=True)
        time.sleep(adapter._chunk_duration_ms / 1000)

    adapter.commit_input()

    # 5. 检测 barge-in（5s 窗口）
    while time.time() - check_start < 5:
        event = adapter.recv(timeout=2)
        if event.get('type') in ('user_speech_started', 'response_cancelled'):
            barge_in_detected = True
            break

    # 6. barge-in 成功则等 AI 重新回复
    if barge_in_detected:
        adapter.post_process(is_interruption=False)
```

### 7.2 APISessionExecutor — HTTP 非实时（整文件上传）

```python
def _execute_non_stream_round(self, adapter, round_config, ...):
    # 1. 合并噪声配置
    background_noise = self._resolve_noise(round_config, global_bg)

    # 2. 整段混音（RenderAudioFile：等所有音频齐了一次性混整段）
    pcm_bytes = RenderAudioFile.render(
        audios_config=round_config.get('audios', []),
        audio_loader=self._load_audio_fn(case_config),
        background_noise=background_noise,
        api_id=data['api_configs'][0].id,
        target_format=adapter.target_format,   # api.audio_config
    )

    # 3. 整文件打包：完整 PCM → 按容器格式包装（wav/pcm）
    audio_payload = AudioFormatAdapter.wrap_container(
        pcm_bytes, adapter.target_format, container='wav')

    # 4. 一次性 HTTP POST，等完整 JSON 响应
    adapter.send(audio_payload, is_audio=True)   # HttpAPIAdapter 内部组装 multipart/base64
    adapter.post_process(is_interruption=False)  # 解析完整响应 → text/image
```

### 7.3 APISessionExecutor — HTTP 流式（SSE chunk 推送）

```python
def _execute_stream_round(self, adapter, round_config, ...):
    # 1. 合并噪声配置
    background_noise = self._resolve_noise(round_config, global_bg)

    # 2. 逐帧流式混音（RenderAudioStream：一边收 chunk 一边混）
    chunks = RenderAudioStream.render(
        audios_config=round_config.get('audios', []),
        audio_loader=self._load_audio_fn(case_config),
        background_noise=background_noise,
        api_id=data['api_configs'][0].id,
        target_format=adapter.target_format,
    )

    # 3. SSE 流式推送
    for chunk_b64 in chunks:
        adapter.send(chunk_b64, is_audio=True)
        time.sleep(adapter._chunk_duration_ms / 1000)

    adapter.commit_input()

    # 4. 边推边收 SSE 事件（audio/text/video/image chunk）
    adapter.post_process(is_interruption=False)
```

> **两条 API 路径的差异在混音方式与交付**：非实时走 `RenderAudioFile`（unary RPC——等所有音频齐了一次性混整段 → 完整 PCM → 整文件 POST）；流式/Realtime 走 `RenderAudioStream`（server-streaming RPC——一边收 chunk 一边逐帧混 → 100ms chunk → SSE/WS 推送）。公共前置（噪声合并、格式适配、RMS/SPL、时间轴）由 `AudioStreamOrchestrator` 统一持有，无重复代码。

---

## 八、数据流总结

```
用例配置
  │
  ├── round_config.audios = [{audio_id:1, type:'speaker', spl:65},
  │                          {audio_id:2, type:'interferer', spl:55}]
  ├── round_config.background_noise = {audio_id:3, spl:45, loop:true}  ← 轮次级噪声
  ├── case_config.background_noise = {audio_id:99, spl:50, loop:true}  ← 全局噪声
  ├── api.rms_spl_mapping_id = 5       (被测 API 关联的 SPL 映射)
  └── api.audio_config = {sample_rate:16000, bit_depth:'s16',
                          channels:1, container:'pcm'}  (目标格式)
          │
          ▼
    _resolve_noise()  →  background_noise = 轮次级（优先）
          │
          ▼
    AudioStreamOrchestrator.route(device_type)
    （编排路由：接收执行设备类型 → 分发到具体混音路径）
          │
  ┌───────┼───────────────────────────────┐
  ▼       ▼                               ▼
http_api http_api stream=True          physical
stream=False / websocket_api       (device_driver，E2E)
  │       │                               │
  ▼       ▼                               ▼
RenderAudioFile.render           E2EExecutor（不经 Orchestrator）
（unary RPC，整段混音）   RenderAudioStream.render   PyAudio callback
  │       （server-streaming，逐帧流式混音）    实时混音 → 物理播放
  │       │
  │ 共用 Step 1-4: 加载 PCM / 格式适配 / RMS+SPL 增益 / 时间轴编排
  │       │
  ▼       ▼
Step 5A: 整段混音      Step 5B: 逐帧流式混音
（一次性混完整段）      （100ms 滑动窗口，一边收 chunk 一边混）
  │       │
  ▼       ▼
Step 6A: 整段量化输出   Step 6B: 逐窗口量化输出
（wav/pcm 包装）        （base64 PCM chunk）
  │       │
  ▼       ▼
完整 PCM            [chunk_0, chunk_1, ..., chunk_N]
  │                    │
  ▼        ┌───────────┼───────────────┐
wav 包装    ▼           ▼               ▼
  │    Realtime WS   HTTP SSE 流式   HTTP 非实时
  ▼        │           │               │
一次性    for chunk:  for chunk:	  完整 PCM
HTTP POST  adapter.send  SSE 推送      → wav 包装
           sleep(100ms)  sleep(100ms)  → 一次性 POST
                    │           │
                    ▼           ▼
              ws.send({type:   event:
              "input_audio_    audio_chunk
               buffer.append", (base64)
               audio: chunk})
```

---
