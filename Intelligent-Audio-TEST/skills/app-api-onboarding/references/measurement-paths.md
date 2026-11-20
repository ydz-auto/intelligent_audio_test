# 测量路径参考（§6.5.1）

接入前先定「怎么喂、怎么收、怎么对齐、算哪个指标」。本页是
`app-api-onboarding` 的 L3 参考：五类可复用模板 + 测试目标映射 + 拒绝 / 降级
话术。

## 1. 五类模板

| 模板 | 参考驱动 | 输入 | 采集 | 时序点 | 适用 |
|---|---|---|---|---|---|
| UI 文本 | `DouBaoAndroidAsrDriver`、`HarmonyXiaoyiInputMethodDriver` | 声学播放 / 手动说话 | 消息列表 / 编辑器文本 | `PLAYBACK_START`、`FINAL_TEXT` | ASR 文本、对话回复 |
| 录屏音频 | `HarmonyDriver` + `HarmonyCollectionMixin` | 声学播放 | 每轮 mp4 → wav → OSS，首帧时间 | `PLAYBACK_START`、`FIRST_FRAME`、`REPLY_END` | TTS 播放、对话回复音频 |
| PCM 抓取 | `HarmonyDoubaoChat`、`XiaoyiLiveChat` | 声学播放 | `client_out.pcm`（用户）/ `client_in.pcm`（AI），RMS 判结束 | `PLAYBACK_START`、`PLAYBACK_END`、`FIRST_AUDIO_PACKET` | 低延迟、打断、TTS 音频 |
| App 导出 | `PlaudDriver` | 声学播放 | App 内转写 / 导出 / 分享 | `PLAYBACK_START`、`FINAL_TEXT` | 长录音转写、离线结果 |
| API 响应 | `OpenAIRealtimeAdapter`、`WebSocketAdapter` | 文件上传 / 流式音频 / 文本 | JSON 文本 + 音频流 / 文件 | `FIRST_PARTIAL`、`FIRST_AUDIO_PACKET`、`REPLY_END` | API ASR / TTS |

选型顺序（同分时选更稳定的）：

1. 有结构化文本通道（UI 文本 / API 文本）→ 优先，定位与复现最稳；
2. 要评音质 / 时延 → PCM 抓取（数据最全）> 含音轨录屏 > App 导出；
3. 长录音 / 离线 → App 导出；
4. 只有录屏且**无音轨** → 只能评文本 / 延迟，不能评 TTS 音质。

## 2. 测试目标 → 指标 → 采集 → 时序

| 测试目标 | 至少一个指标 | 可接受采集 | 额外时序 |
|---|---|---|---|
| ASR | `WER` / `CER` / `SENTENCE_ACC` | `UI_TEXT` / `APP_EXPORT` / `API_RESPONSE`，或录屏 / PCM **+ 识别步骤** | — |
| TTS | `TTS_QUALITY` | `SCREEN_RECORD`（含音轨）/ `PCM_CAPTURE` / `API_RESPONSE` | — |
| 对话 | `SENTENCE_ACC` / `REPLY_LATENCY` | `UI_TEXT` / `APP_EXPORT` / `API_RESPONSE` | `FINAL_TEXT` / `REPLY_END` |
| 翻译 | `SENTENCE_ACC` | `UI_TEXT` / `APP_EXPORT` / `API_RESPONSE` | — |
| 降噪 | `TTS_QUALITY` / `WER` / `CER` | `PCM_CAPTURE` / `API_RESPONSE` | — |
| 打断 | `BARGE_IN` | `PCM_CAPTURE` / `API_RESPONSE` | `PLAYBACK_START` / `PLAYBACK_END` |

指标由 algorithm_service / evaluation_service 计算；驱动只负责采集
`result_fields`，不写 WER / MOS。

## 3. `measurement_profile` 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `test_goals` | 是 | `ASR` / `TTS` / `DIALOG` / `TRANSLATION` / `NOISE_REDUCTION` / `BARGE_IN` 的非空子集 |
| `stimulus_modes` | 否 | 本次怎么喂；必须是 `capabilities.stimulus_modes` 的子集 |
| `capture_modes` | 否 | 本次怎么收；必须是 `capabilities.capture_modes` 的子集 |
| `timing_points` | 否 | 本次对齐的时序点；必须是 `capabilities.timing_points` 的子集 |
| `capture_details` | 否 | 采集细节；`SCREEN_RECORD.audio`（默认 `true`）、`SCREEN_RECORD.asr` / `PCM_CAPTURE.asr` |
| `completion` | 否 | 完成判定（例如「AI 回复文本出现且播放结束」） |
| `assets` | 否 | 测试音 / 文本 / 标注资产列表 |
| `extra_recognition` | 否 | 录屏 / PCM 出 ASR 文本时补的识别步骤 |

## 4. 拒绝 / 降级例子（原样转述给用户）

### 4.1 只有 UI 文本，却要 TTS 音质

> 测量路径不可测：测试目标 TTS 需要音频采集（录屏含音轨 / PCM / API 音频），
> 当前只有 `UI_TEXT`。降级：只评 ASR 文本与延迟类指标；要评音质需补
> `PCM_CAPTURE` 或含音轨录屏。

### 4.2 只能录屏且无音轨

`capture_details.SCREEN_RECORD.audio=false` + `TTS_QUALITY`：

> 测量路径不可测：只有画面没有音轨，无法评 TTS 音质。降级为文本 / 延迟指标，
> 或补充 PCM / 含音轨录屏后重新接入。

### 4.3 只能录屏 / PCM，却要 ASR 文本且没补识别步骤

> 测量路径不可测：ASR 只能拿到音频，缺少 ASR 识别步骤。补
> `extra_recognition=true` 或 `capture_details.<mode>.asr=true`；否则降级为
> 只评延迟 / 音频质量，不产出 ASR 文本指标。

### 4.4 时序点缺失

`DIALOG` 没有 `FINAL_TEXT` / `REPLY_END`，或 `BARGE_IN` 没有
`PLAYBACK_START` / `PLAYBACK_END`：

> 测量路径不可测：该目标需要时序点 X 之一；请补时序采集后再生成。

### 4.5 指标未声明

`capabilities.supported_metrics` 没有目标所需指标：先改能力画像（真的能算再
声明），或把该目标移出本次接入范围；不要为了过校验硬塞指标。

## 5. capabilities.json 最小示例

```json
{
  "stimulus_modes": ["ACOUSTIC_PLAYBACK"],
  "capture_modes": ["UI_TEXT", "PCM_CAPTURE"],
  "timing_points": ["PLAYBACK_START", "PLAYBACK_END", "FINAL_TEXT"],
  "result_fields": ["success", "message", "asr", "text", "user_wav",
                    "ai_wav", "start_ms", "end_ms", "latency_ms"],
  "supported_metrics": ["WER", "CER", "SENTENCE_ACC", "REPLY_LATENCY",
                        "TTS_QUALITY", "BARGE_IN"],
  "limitations": ["无录屏：只能取 UI 文本 + PCM 抓取"]
}
```
