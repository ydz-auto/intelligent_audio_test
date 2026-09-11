# 混音与 SPL 映射

> 版本：v1.1 | 日期：2026-09-10 | 状态：最终方案
>
> **v1.1 变更**：
> 1. 修正：HTTP API（非实时 + 流式）**均支持混音**——非实时混音后整文件上传，流式混音后切片 SSE 推送，Realtime 混音后切片 WS 推送。三者共用同一套 `AudioStreamOrchestrator` 编排，仅消费方式不同。
> 2. 新增：**格式适配层**（`AudioFormatAdapter`）——不同被测 API 的采样率/位深/通道数不同，混音前统一适配到 `api.audio_config` 声明的目标格式（重采样 / 位深转换 / 上混下混）。

---

## 一、概述

API 类测试（HTTP 非实时、HTTP 流式 SSE、Realtime WebSocket）需要将主讲人音频、干扰人音频、背景噪声**离线混音**后，按被测 API 要求的格式输出：

| 被测设备 | 混音 | 混音产物 | 推送方式 |
|---------|------|---------|---------|
| HTTP API（非实时） | `AudioStreamOrchestrator` 离线混音 | 完整 PCM（包装为请求要求的格式） | 一次性 HTTP POST |
| HTTP API（流式） | `AudioStreamOrchestrator` 离线混音 | base64 PCM chunk | SSE 逐 chunk 推送 |
| WebSocket API（Realtime） | `AudioStreamOrchestrator` 离线混音 | base64 PCM chunk | WS 逐 chunk 推送 |
| E2E 物理设备（对照） | `audio_driver` callback 实时混音 | int16 帧 → 声卡 | PyAudio 物理播放 |

> **结论**：三种 API 模式的混音编排完全一致（同一 orchestrator、同一 6 步流程），差别只在**消费方式**——非实时拼接整文件，流式/Realtime 逐 chunk 推送。且混音前都要经过**格式适配**，统一到被测 API 要求的采样率/位深/通道数。

### 与 E2E 混音的区别

| 维度 | E2E (audio_driver + spl_service) | API 类 (AudioStreamOrchestrator + ApiRmsSplService) |
|------|----------------------------------|-----------------------------------------------------|
| 混音时机 | 实时（PyAudio callback 内逐帧混音） | 离线整段混音（执行中一次性混好整段） |
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

### 3.1 AudioStreamOrchestrator

> 文件：`backend/services/audio/audio_stream_orchestrator.py`

负责多源音频的混音编排和切片输出，复用 `audio_timeline.calculate_speaker_aware_audio_delays()` 的时间轴算法。**HTTP 非实时 / HTTP 流式 / Realtime 三种 executor 共用**。

```python
class AudioStreamOrchestrator:
    DEFAULT_SAMPLE_RATE = 24000   # api.audio_config 未配置时的回退值（OpenAI 兼容）
    DEFAULT_SAMPLE_WIDTH = 2      # 16bit
    TARGET_RMS_DBFS = -30.0       # 与 audio_driver.calculate_gain_compensation 一致
    chunk_duration_ms = 100       # 默认切片时长

    @staticmethod
    def chunk_audio(
        audios_config: list,          # [{audio_id, type, delay, play_order, spl, ...}]
        audio_loader,                 # 回调 (audio_id) -> bytes PCM
        chunk_duration_ms=100,        # 切片时长
        api_id=None,                 # 被测 API ID（查 RMS→SPL 映射）
        rms_spl_mapping=None,        # 预加载的映射对象（可选）
        background_noise=None,       # 噪声配置（已按优先级合并）
        target_format=None,          # api.audio_config（目标格式，None → 默认 24k/s16/mono）
    ) -> list[str]:                  # base64 PCM chunk 列表（统一输出，消费方式由 executor 决定）
```

> **输出统一为 base64 PCM chunk 列表**：
> - Realtime executor：逐 chunk `adapter.send()` + sleep 模拟实时速率
> - HTTP 流式 executor：逐 chunk SSE 推送
> - HTTP 非实时 executor：拼接全部 chunk → 按 `container` 包装（wav/pcm）→ 一次性 POST

### 3.2 ApiRmsSplService

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
│  → 传入 AudioStreamOrchestrator.chunk_audio()                │
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

## 五、混音 6 步流程

```
┌──────────────────────────────────────────────────────────────┐
│                 AudioStreamOrchestrator.chunk_audio()         │
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
│  ┌─ Step 5: 混音叠加 — 按时间轴混入 float32 缓冲 ───────┐    │
│  │  对每个 source:                                          │    │
│  │    samples = int16 → float32（已在 Step 2 统一格式）    │    │
│  │    samples *= gain_linear                               │    │
│  │                                                          │    │
│  │    if type == 'noise' and loop:                         │    │
│  │      # 铺满整个混音缓冲                                  │    │
│  │      for i in range(0, buf_len, len(noise_samples)):    │    │
│  │        mix_buffer[i:end] += noise_samples[:chunk_len]   │    │
│  │    else:                                                 │    │
│  │      # 主讲人/干扰人/非循环噪声 → 按 start_time 混入    │    │
│  │      start_sample = 16000 * start_ms / 1000              │    │
│  │      mix_buffer[start:end] += samples                   │    │
│  │                                                          │    │
│  │  最终: mix_buffer = Σ (各源 × gain)                    │    │
│  │  (立体声目标时按 interleaved 帧对齐混入)                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌─ Step 6: 切片输出 — 按目标位深度化 → base64 chunk ───┐     │
│  │  mix_buffer → np.clip(±满量程) → int16 量化             │     │
│  │  chunk_samples = 16000 * 100ms / 1000 = 1600 samples   │     │
│  │  chunk_bytes = 1600 * 2 = 3200 bytes                   │     │
│  │                                                          │     │
│  │  mix_buffer[0:1600]     → base64 → chunk_0              │     │
│  │  mix_buffer[1600:3200]  → base64 → chunk_1             │     │
│  │  ...                                                    │     │
│  │  mix_buffer[-1600:]     → base64 → chunk_N             │     │
│  │  (不足补零到 1600 samples)                              │     │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  输出: [chunk_0, chunk_1, ..., chunk_N] (base64 PCM)          │
│  → 消费方式由 executor 决定:                                   │
│    - Realtime:  for chunk: adapter.send(chunk) + sleep         │
│    - HTTP 流式: for chunk: SSE 推送                            │
│    - HTTP 非实时: b''.join(decode(chunks)) → wav → POST        │
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

    # 2. 混音 + 切片（含格式适配）
    chunks = AudioStreamOrchestrator.chunk_audio(
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

    # 3. 混音 + 切片（打断音频 + 噪声，含格式适配）
    background_noise = self._resolve_noise(round_config, global_bg)
    chunks = AudioStreamOrchestrator.chunk_audio(
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

    # 2. 混音 + 切片（与 Realtime 完全同一套编排）
    chunks = AudioStreamOrchestrator.chunk_audio(
        audios_config=round_config.get('audios', []),
        audio_loader=self._load_audio_fn(case_config),
        background_noise=background_noise,
        api_id=data['api_configs'][0].id,
        target_format=adapter.target_format,   # api.audio_config
    )

    # 3. 整文件打包：chunks 拼接 → 按容器格式包装（wav/pcm）
    pcm_bytes = b''.join(base64.b64decode(c) for c in chunks)
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

    # 2. 混音 + 切片（同一套编排）
    chunks = AudioStreamOrchestrator.chunk_audio(
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

> **三种 executor 的差异只在消费方式**：`chunk_audio()` 之前的编排（噪声合并、格式适配、RMS/SPL、时间轴、混音）完全一致，无重复代码。

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
    AudioStreamOrchestrator.chunk_audio(target_format=api.audio_config)
          │
          ├── Step 1: 加载 PCM（speaker + interferer + noise，源格式各异）
          ├── Step 2: 格式适配（AudioFormatAdapter: 位深→重采样→上下混
          │            统一到 16k/s16/mono）
          ├── Step 3: RMS 补偿 + SPL 增益（查 api_id 的映射）
          ├── Step 4: 时间轴编排（speaker 感知交叠）
          ├── Step 5: 混音叠加（float32 buffer，目标采样率）
          └── Step 6: 切片输出（按目标位深度化 → base64 PCM chunk）
                    │
                    ▼
              [chunk_0, chunk_1, ..., chunk_N]
                    │
        ┌───────────┼───────────────┐
        ▼           ▼               ▼
  Realtime WS   HTTP SSE 流式   HTTP 非实时
        │           │               │
  for chunk:    for chunk:      b''.join(chunks)
    adapter.send  SSE 推送        → wav 包装
    sleep(100ms)                  → 一次性 POST
        │           │               │
        ▼           ▼               ▼
  ws.send({type:      event:       multipart/form-data
  "input_audio_       audio_chunk    (audio 文件字段)
   buffer.append",    (base64)
   audio: chunk})
```

---
