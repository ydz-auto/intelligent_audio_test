# 豆包 Android 合成 user_wav：离线验证报告

- 日期：2026-10-27
- 目标：验证“按平台播放文件+时间戳合成 `user_wav`，并与 AI 通道对齐到同一 T0”是否可行
- 结论：**离线逻辑、真实录音回放、真机播放落点均验证通过**；真机这一轮 AI 通道静音（手机没识别到 PC 播的问题），平台 RME 整体 E2E 仍待跑

---

## 1. 测试环境

| 项 | 值 |
|---|---|
| 系统 | Windows |
| Python | 3.14 |
| 音频工具 | `D:\work\ffmpeg\bin\ffmpeg.exe` |
| 手机 | nubia NX888J / Android 16（`324462534283`，adb 在线） |
| 真实 AI 录音 | `static/case_result/900003/local-voice2/EP0110MZ0BC050906W/local-voice2_r0_ai.wav`（69.63s） |
| 真实用户语音 | `static/audios/2026144010.wav`（0.8s 中文） |

说明：本机只有 Realtek/Jabra 输出，数据库中的 RME 播放设备均为 `Unknown`，
因此本轮不驱动平台 `playback_orchestrator`，而是用“真实 AI 文件 + 人工播放时间戳”
验证合成/对齐算法；平台完整 E2E 留待 RME 机器。

---

## 2. 验证内容

1. 按 `start_ms` 把播放文件放到 `user_wav` 的精确偏移；
2. 默认只拼 `dry+interferer`，`noise` 不拼入；
3. 把 AI wav 放到同一 T0（裁头/补前导静音）；
4. `user_wav` 与 `ai_wav` 同时长；
5. `get_results` 在 `user_audio_source=synth_played` 时走合成分支；
6. 重复调用 `get_results` 幂等，不产生嵌套 `*_ai_aligned_ai_aligned.wav`。

---

## 3. 关键结果

### 3.1 方波落点测试

`played_audios`：一个 2s 方波，`start_ms = T0+5s`，`end_ms = T0+7s`。

| 项 | 期望 | 实测 | 误差 |
|---|---|---|---|
| user 起声 | 5.000s | 5.000s | 0 样本 |
| AI 起声 | 44.920s | 44.940s | +20ms（一个扫描窗） |
| user 时长 | 70.132s | 70.132s | 0 |
| ai 时长 | 70.132s | 70.132s | 0 |
| user 峰值 | ≤32767 | 10000 | 无削波 |

### 3.2 真实中文语音落点测试

`played_audios`：真实 0.8s 中文语音，播放起点 `T0+8s`。

| 项 | 期望 | 实测 | 误差 |
|---|---|---|---|
| user 起声 | 8.080s | 8.080s | 0 样本 |
| 源文件自身起声 | 0.080s | 0.080s | 0 |
| user 峰值 | — | 21373 | 无削波 |
| user/ai 时长 | — | 70.632s / 70.632s | 0 |

### 3.3 `get_results` 集成

在 `user_audio_source=synth_played` 下调用 `get_results`，返回：

- `success=True`
- `user_wav=..._user_synth.wav`
- `ai_wav=..._ai_aligned.wav`
- `first_frame_ms` 由对齐后的 AI 起声点修正（`1792657358725`）

### 3.4 真机播放落点（NX888J，真实豆包通话）

用驱动真实走完 `initialize → pre_process`（进语音通话页，只抓 AI playback），
从 PC Realtek 扬声器播放 `B-IS-005_..._今天周几.wav`（5s，源文件起声 0.993s），
记录 `sounddevice` 播放起止后调 `_synthesize_from_played`：

| 项 | 值 |
|---|---|
| 播放起点相对 T0 | 4.589s |
| 源文件自身起声 | 0.993s |
| 期望 user 起声 | 5.582s |
| 实测 user 起声 | 5.583s |
| 落点误差 | ≈1ms |
| user_wav 时长 | 20.980s（与 ai_aligned 相同） |
| user 峰值 | 12014（无削波） |

第二轮把播放幅度拉到 1.0、通话后再等 6s、手机音量加 8 档，手机 UI 字幕里
出现的是环境里另一段说话（“网线/弱电箱……”），**没有出现“今天周几”**；
AI 通道 wav 全程 `peak=0`。说明这一轮不是合成落点问题，而是 PC 外放的声音
没有被豆包麦克风当成用户输入（音量/距离/环境声掩蔽），AI 因此没有回复。

### 3.5 单元测试

```text
backend/tests/test_audio_synthesis.py   10 passed
backend/tests/test_android_doubaochat_driver.py  23 passed
合计 33 passed
```

覆盖：偏移落点、noise 跳过、interferer 拼入、AI 裁补对齐、端到端同时长、
幂等、引擎 `file_path/current_round_played_audios` 透传、时延字段计算。

### 3.6 结果里的时延字段

`get_results` 现在直接返回 `latency_ms`，服务器跑完不用再手算：

```json
"latency_ms": {
  "question_start_ms": 1793063997614,
  "question_end_ms": 1793064002710,
  "ai_start_ms": 1793064009000,
  "question_to_ai_ms": 11386,
  "question_end_to_ai_ms": 6290,
  "played_count": 1
}
```

- `question_start_ms` / `question_end_ms`：本轮 `dry+interferer` 的最早开始/最晚结束（`noise` 不计入）；
- `ai_start_ms`：对齐后 AI 真实起声点（`first_frame_ms`）；
- `question_to_ai_ms`：从问题开始到 AI 起声；
- `question_end_to_ai_ms`：从问题播完到 AI 起声，即通常说的“回复时延”。


---

## 4. 已知限制 / 未验证

1. **平台真实出声延迟**：`playback_start_time_ms` 是 sounddevice 开始播放时刻，
   声卡实际出声有毫秒级延迟；本轮未测。
2. **T0 精度**：AI 通道用文件创建时刻（`st_birthtime`）做锚点，实测与 `start()`
   返回相差约 84ms；合成侧按此对齐，误差预计 50~100ms 量级。
3. **声学链路**：合成 `user_wav` 不含房间/麦克风染色，也不施加播放 SPL/gain；
   若评估需要“设备实际听到的输入”，应改用 RME Loopback。
4. **噪声轨**：默认不拼入，仅 `dry+interferer`；需要环境声时另行开启。
5. **真机 AI 回复未打通**：本轮 user 落点已对，但 PC 外放没被手机识别成有效输入，
   AI 通道静音；需提高 PC 输出音量/拉近距离，或改用 RME/定向扬声器后再验一次
   “豆包听到问题并回复”的完整链路。平台完整 E2E（真实 `played_audios` 下发）
   仍需在 RME 测试机建 `user_audio_source=synth_played` 用例。

---

## 5. 复现方式

```powershell
cd D:\work\20260630\Intelligent-Audio-TEST
python -m pytest backend/tests/test_audio_synthesis.py -q
python -m pytest backend/tests/test_android_doubaochat_driver.py -q
```

平台侧启用：用例配置里设置 `user_audio_source=synth_played`（旧用例不设则保持原行为）。
一轮结束后检查：

- `*_user_synth.wav` 非静音；
- `*_ai_aligned.wav` 与 `*_user_synth.wav` 时长差 ≤50ms；
- 日志出现 `合成 user_wav` 与 `AI wav 对齐到 T0`。

---

## 6. 相关文件

- 驱动：`backend/utils/device_driver/android_doubaochat.py`
- 引擎：`backend/services/execution/e2e_executor.py`、`e2e_collector.py`
- 测试：`backend/tests/test_audio_synthesis.py`
- 方案：`doc/android_doubao_user_audio_plan.md`
