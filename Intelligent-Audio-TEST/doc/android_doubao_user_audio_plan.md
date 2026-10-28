# 豆包 Android 驱动：用户通道（user_wav）方案评审稿

> 状态：**方案已实现，离线 + 真机播放落点验证通过；AI 回复链路/平台 RME E2E 待验**
> 范围：`Intelligent-Audio-TEST` 的 E2E 执行引擎 + `android_doubaochat.py` 驱动
> 关联代码：`backend/services/execution/e2e_executor.py`、`e2e_collector.py`、`backend/utils/device_driver/android_doubaochat.py`、`android_scrcpy_audio.py`
> 编写时间：2026-10-22；实现/离线测试：2026-10-27

---

## 1. 背景与问题

豆包 Android 语音通话驱动（`android_doubaochat.py`）已实现，AI 通道（`playback`）已验证可抓到模型语音；**用户通道拿不到**。

实测结论（nubia P0110 / Android 16 / 豆包 15.3.0.1，未 root）：

| 采集方式 | 通话中结果 |
|---|---|
| `mic` / `mic-voice-communication` | 全 0（把豆包自己静音后仍为 0） |
| `mic-voice-recognition` / `mic-unprocessed` / `mic-camcorder` / `voice-performance` / `voice-call` | 全 0 |
| `voice-call-uplink` | 全 0（用户说话时也是 0） |
| `voice-call-downlink` | 只有低电平底噪，与 AI 音频相关性 0.01 |
| 先启动 mic 采集、再进通话 | 进通话瞬间被置 0 |
| 豆包 App 自身 | 正常识别用户（气泡“你好，豆包。0618 是什么？”），但音频在 App 私有链路，未 root 读不到 |

这是 Android 通话态音频策略对非特权采集的限制，不是驱动或 scrcpy 的 bug。评估侧 `user_wav` 却必须有，否则话轮/打断/拒识等维度缺输入。

---

## 2. 目标与非目标

### 目标

1. 每个用例/轮次都产出**非空、可用**的 `user_wav`；
2. `user_wav` 与 `ai_wav` 共享同一绝对时间轴，**误差目标 ≤100ms**（话轮/打断指标的常规分辨率），可验证；
3. 不改变现有结果字段契约（仍是文件路径），不影响鸿蒙驱动；
4. 无 root、无额外硬件的前提下可落地（方案 A）；同时为有硬件/root 的场景保留升级路径；
5. 对“合成”语义做显式标记与日志，避免被误当成设备麦克风实录。

### 非目标

- 不解决“设备麦克风真实声学通道”的采集（那需要 root 或外部录音，见 §3 备选）；
- 不改评估算法/维度定义；
- 不改 Android 端豆包 App。

---

## 3. 方案对比与选型

| 方案 | 用户通道来源 | 时间对齐 | 电平/环境 | 依赖 | 评价 |
|---|---|---|---|---|---|
| **A. 播放源合成（推荐评审）** | 平台本轮播放的用户/干扰人音频文件 | 播放时间戳（PC epoch），精确 | 原始文件电平，无房间/麦克风染色 | 无 | 合成输入场景下是“真值”，最稳 |
| A'. RME 回环录制 | RME TotalMix Loopback 录“实际送到音箱的信号” | 录制起点 + epoch，精确 | **含增益/SPL/混音**，无房间 | 需 RME Loopback 可用 | 若可用，比 A 更接近真实、实现更简单 |
| B. Root + ALSA 麦克风 | `tinycap` 直接读 `/dev/snd` | 设备侧时钟，需与 PC 校准 | 真实麦克风+房间 | 解锁/root | 最真实的设备通道，成本最高 |
| C. 外部麦克风 | 手机旁/音箱处放麦，PC 录制 | 录制起点 + epoch | 真实声学 | 需麦+RME 输入 | 无需 root，但要硬件和摆位 |
| D. 系统特权录音 | 系统录音/录屏 App 的麦克风 | 录制起点 | 混合轨 | 系统权限 | 本机 tile 启停不稳定，且混合轨难分离 |
| E. 豆包转写文本 | 无音频 | — | — | — | 不能满足音频评估 |

**推荐：A 作为默认实现**；如果实验室 RME 支持 Loopback，**A' 优先于 A**（工作量更小、电平正确、含噪声）。本评审稿按 A 设计，A' 作为可替换的“用户通道提供者”。

---

## 4. 总体设计

```
[E2E 执行引擎]
  play_round() ──► playback_orchestrator
                     │  audio_timelines: file / start / end / playback_start_time_ms / end_ms / audio_type
                     ▼
  _collect_playback_timestamps()  ← 新增：current_round_played_audios（含 file_path/start/end/type）
                     ▼
  e2e_collector.collect_results() ← 新增：extra_params['played_audios'] = [...]
                     ▼
  driver.get_results(**kwargs)    ← 读取 played_audios
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  _synth_user_wav()           _remux_ai_wav()
  按 epoch 放用户/干扰轨        按 wav 创建时刻裁/补到 T0
        └────────────┬─────────────┘
                     ▼
        user_wav / ai_wav（同一 T0、同一目标时长）
                     ▼
        _validate_alignment()（地标校验 + 日志）
```

### 4.1 驱动输入（新增 kwargs）

```python
played_audios = [
    {
        "audio_id": 123,
        "audio_type": "dry" | "noise" | "interferer",
        "play_order": 0,
        "file_path": "D:/.../user.wav",
        "start_ms": 1792657300000,   # epoch ms，实际播放开始
        "end_ms":   1792657305000,   # epoch ms，实际播放结束
    },
    ...
]
```

- 由 `e2e_collector` 透传；无该参数时自动退回现有行为（mic/uplink 或静音）。
- `start_ms`/`end_ms` 来自 `playback_orchestrator` 的 `playback_start_time_ms` / `playback_end_time_ms`（`_stamp` 已写入，噪声/干扰人也有）。
- 时间轴对象里已有 `file` 字段；`_collect_playback_timestamps` 直接取 `timeline.get('file')`，无需查库。

### 4.2 新增驱动参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `user_audio_source` | `synth_played` | `synth_played`：合成；`mic`/`mic-voice-communication`/`voice-call-uplink`：保留现有硬件尝试（未来 root 设备） |
| `user_wav_include_types` | `dry,interferer` | 合成时纳入的音频类型；默认不含 `noise`（噪声会掩蔽用户语音，环境声可通过 `played_audios` 单独给评估） |
| `user_wav_synth_fallback` | `silent` | 合成失败（无 played_audios/文件缺失）时：`silent` 保留空轨并告警；`mic` 退回硬件采集 |
| `ai_wav_timebase` | `wav_ctime` | `wav_ctime`：用文件创建时刻；`calibrated`：用一次性标定常量（预留） |
| `alignment_tolerance_ms` | `100` | 地标校验告警阈值 |

配置经 `round_algo_params`/`case_algorithm_params` 传入，沿用现有 E2E 参数透传链路，无需新增 DB 字段。

---

## 5. 时间轴模型与对齐算法

### 5.1 时钟域

- 所有 epoch 毫秒均来自**同一台 PC 的时钟**：`playback_start_time_ms` 由 `playback_orchestrator` 在播放开始时 `time.time()*1000` 写入；scrcpy 在 PC 上创建 wav，文件创建时刻也在同一时钟域。
- 不使用手机时钟，避免设备/PC 时钟漂移。

### 5.2 锚点 T0

```
T0 = min( played_audios.start_ms 的最小值, ai_wav_create_epoch_ms )
```

- `ai_wav_create_epoch_ms` 取 `os.stat(ai_wav).st_birthtime / st_ctime`（Windows 为创建时间；实测与 `start()` 返回只差 **84ms**，与另一路只差 **77ms**）。
- 若 `played_audios` 为空 → 不合成，走 fallback。
- 若 ai wav 不存在 → `T0 = min(played start_ms)`，ai 通道标记缺失。

### 5.3 目标时长

```
target_end_ms = max(
    max(played_audios.end_ms),
    ai_create_epoch_ms + ai_duration_ms,
    current_round_end_ms (若提供)
) + ALIGN_TAIL_MS (默认 500ms)
target_duration = target_end_ms - T0
```

### 5.4 用户通道合成

1. 对每个 `played_audios`（按 `user_wav_include_types` 过滤）：
   - `ffmpeg -i file -f s16le -ar 48000 -ac 2 -` 解码为 PCM（缓存到内存，单轮通常 <100MB；可流式写入）；
   - `offset_samples = round((start_ms - T0) / 1000 * 48000)`；
   - 长度按 `end_ms - start_ms`（噪声轨若 end 覆盖整轮，循环文件直到结束）。
2. 建 int32 累加缓冲（长度 `target_duration * 48000` 帧 × 2 声道）：
   - 逐样本相加；结束做 int16 截断（`clip(-32768, 32767)`），并记录削波样本数；
   - 可选：按 `audio_config` 的 gain/SPL 做电平补偿（见 §10 开放问题）；
3. 写 `user_wav`：48k / 双声道 / pcm_s16le，t=0 对应 T0；
4. 若某文件缺失/解码失败：跳过并告警；全部失败按 `user_wav_synth_fallback` 处理。

**为什么这样能对齐**：用户音频的起始位置来自播放调度器（不是声学检测），放在 epoch 轴上的位置是确定的；唯一误差是文件本身的采样边界（<1 帧）。

### 5.5 AI 通道对齐

1. `ai_birth_ms = int(os.stat(ai_wav).st_ctime * 1000)`；
2. `lead_ms = ai_birth_ms - T0`：
   - `lead_ms > 0` → 在 ai wav 前补 `lead_ms` 静音；
   - `lead_ms < 0` → 裁掉 `-lead_ms`（用 `atrim`）；
3. 尾部用静音补到 `target_duration`（`apad`），或在 Python 混音器里与用户通道同一缓冲长度输出；
4. 输出覆盖原 `..._r{n}_ai.wav`（或写 `..._aligned.wav` 并更新返回值）。

### 5.6 case 模式

- 每轮独立抓 AI 音频（现状），T0 取该轮 `played_audios` 最小 start 与 ai birth 的较小者；每轮单独对齐；
- 录屏仍是整用例一段，音画对齐只对 round 模式生效；case 模式下在日志记录 `video_offset = recorder_start - T0`。

### 5.7 中断轮

- 中断轮的用户音频（打断语）同样按 `played_audios` 放在时间轴上；AI 音频只抓到打断前的一段；
- 合成不依赖“AI 是否说完”，不会引入额外等待。

---

## 6. 引擎改造点（逐文件）

| 文件 | 改动 | 影响面 |
|---|---|---|
| `backend/services/execution/e2e_executor.py` | `_collect_playback_timestamps()`：每轮把 `timeline['file']`、`playback_start_time_ms`、`playback_end_time_ms`、`audio_type`、`is_noise` 存入 `current_round_played_audios`；每轮开始清空 | 仅 E2E |
| `backend/services/execution/e2e_collector.py` | `collect_results()`：把 `current_round_played_audios` 放进 `extra_params['played_audios']`；保留现有时间戳字段 | 仅 E2E |
| `backend/utils/device_driver/android_doubaochat.py` | 新增 `_synth_user_wav()`、`_remux_ai_wav()`、`_validate_alignment()`；`_start_audio_capture()` 在 `synth_played` 下只启动 AI 路；`get_results()` 优先合成 | 仅该驱动 |
| `android_scrcpy_audio.py` | 可选：暴露 `birth_ts` 属性（或驱动直接 `os.stat`），无需大改 | 低 |
| 测试 `backend/tests/test_android_doubaochat_driver.py` | 新增合成/对齐/回退/削波用例 | 测试 |
| 文档 `CLAUDE.md` | 补充“用户通道合成”语义与开关 | 文档 |

不改：数据库、API schema、评估服务、鸿蒙驱动、前端。

---

## 7. 校验与测试

### 7.1 运行时自检（每次 get_results）

- `T0`、`lead_ms`、`target_duration`、各 track 的 offset、削波样本数 → INFO/DEBUG 日志；
- `ai_wav` 起声点（`_wav_first_speech_offset`）→ 绝对时刻；
- 地标校验：
  1. `user_wav` 末尾 ≤ `ai_wav` 起声 + 容差（普通轮）；打断轮允许交叠，跳过该告警；
  2. `abs(user_wav_duration - ai_wav_duration) ≤ 50ms`（同 T0/同目标时长）；
  3. AI 起声必须落在 `[T0, T0+target_duration]`；
  4. 用户轨/干扰轨 offset ≥ 0 且 ≤ 目标时长；
- 失败仅告警，不阻断用例（与现有风格一致），但日志明确 `aligned=false` 原因。

### 7.2 单元测试（新增）

- 两段 wav 按 1.0s/2.5s 偏移合成，校验对应采样位置和总时长；
- T0 选择：played start 早于/晚于 ai birth 两种情况（补静音 / 裁剪）；
- 多轨重叠：int32 累加不溢出、削波保护；
- 文件缺失、空 played_audios、非法 wav 的回退路径；
- 对齐校验函数的地标判断（可注入假值）；
- ai wav 起声点修正 first_frame_ms（已有部分）。

### 7.3 真机验收

1. 一轮真实说话：`user_wav` 非静音、ASR 可识别出用户句子；`ai_wav` 非静音；
2. `user_wav`/`ai_wav` 时长差 ≤50ms；AI 起声与通话页字幕/状态差 ≤1s；
3. 用户说话结束到 AI 起声的间隔符合实际（用录屏/字幕对照）；
4. 打断轮：用户打断语位置正确，AI 音频在打断后停止；
5. case 模式两轮：每轮 user/ai 独立、可评估；
6. 无 played_audios 的旧路径：回退正常、有告警。

---

## 8. 兼容与回滚

- **开关**：`user_audio_source=synth_played` 为 Android 豆包驱动默认；设为 `mic`/`voice-call-uplink` 即回退现有行为；
- 合成失败回退 `silent`（默认）或 `mic`；
- 鸿蒙驱动不读取该参数，行为不变；
- 引擎新增 `played_audios` 是**附加字段**，旧驱动忽略即可；
- Git 回滚：仅 4 个文件 + 测试，无 DB 变更。

---

## 9. 工作量与排期

| 阶段 | 内容 | 预估 |
|---|---|---|
| P0 评审 | 确认 §10 开放问题（语义/噪声/电平/精度） | 0.5d（含评审会） |
| P1 引擎透传 | executor + collector 透传 `played_audios`，日志 | 0.3d |
| P2 驱动合成 | 混音器、AI 对齐、T0/校验、配置与回退 | 1.0d |
| P3 测试 | 单测 15+、真机一轮/两轮/case/打断 | 0.7d |
| P4 文档/联调 | CLAUDE.md、使用说明、评估侧确认 | 0.3d |
| 合计 | | **约 2.5 人日** |

---

## 10. 风险与开放问题（评审重点）

### 10.1 语义风险（最重要）

- 合成 `user_wav` 是“平台送进设备的信号”，不是“设备麦克风实际拾到的声音”（缺房间混响、设备麦克风频响、AGC/降噪、实际增益）。
- 如果评估维度（尤其 `env_judge`、环境理解）要求 `user_wav` 必须包含房间/设备染色，方案 A 不满足；需要 A'（RME loopback）或 B/C。
- **请确认**：平台对 `user_wav` 的语义要求是“用户输入真值”还是“设备输入实录”？

### 10.2 电平/增益

- 播放链路有 SPL/增益补偿（`playback_orchestrator` 按 `gain`/SPL 播放）；合成若直接相加原始文件，电平可能和实际听到的不一致。
- 选项：
  a. 按 `audio_config` 的 gain/SPL 施加与播放一致的增益（需要把这些参数透传）；
  b. 忽略电平差异（评估多为内容/时序指标）；
  c. 用 RME Loopback 录实际输出（最准）。
- **请确认**是否要求电平一致；若要求，选 a 或 A'。

### 10.3 噪声/干扰人

- 噪声轨是**循环播放到轮次结束**；默认 `user_wav_include_types=dry,interferer`，不含 noise，避免掩蔽用户语音；
- 若 env 维度需要 user_wav 带环境声，可设 `dry,interferer,noise`（需实现循环拼接）。
- **请确认**默认策略。

### 10.4 精度目标

- 当前 `wav_ctime` 方案误差约 50~100ms（文件创建→首帧的常量 + 播放调度时间戳精度）；
- 若要求 ≤20ms，需要增加“手机侧同步标记”：在每轮开始让手机播放一个极短已知音，被 playback 抓到来反推首帧时刻。当前系统通知音/音量音未被 playback 捕获，需要额外找一个稳定的发声通道（小 helper/豆包提示音），成本另计。
- **请确认**目标精度。

### 10.5 跨平台

- `st_birthtime` 在 Windows 可用；Linux 上 `st_ctime` 是 inode 变更时间，不是创建时间。若后端将来跑 Linux，需要改为一轮一次性标定（或从 scrcpy 日志/扩展 server 取精确起点）。
- 当前部署为 Windows，可接受；文档标注。

### 10.6 其它

- `playback_start_time_ms` 是 sounddevice 开始播放的时刻，声卡实际出声有毫秒级延迟；通常可忽略。
- AI wav 若在 T0 之后才开始（采集启动慢），会补前导静音；评估侧需能处理前导静音（现有 ASR 一般可以）。
- 合成会多一次全文件解码/混音，CPU/内存开销：单轮 ~几十 MB、<1s；case 模式每轮一次，可接受。

---

## 11. 验收标准（Definition of Done）

1. 真实一轮：`user_wav` 非静音，ASR 内容与说话一致；`ai_wav` 非静音；
2. `user_wav`/`ai_wav` 同一 T0，时长差 ≤50ms；AI 起声与通话页地标差 ≤1s；
3. 地标自检通过并写日志；失败有明确原因；
4. 无 `played_audios` 时回退正常，不影响旧用例；
5. 单测全绿（含新增 15+），真机 round/case/打断各一轮通过；
6. 鸿蒙驱动与现有 API/DB 无变化；
7. 评审确认 §10 的语义/电平/噪声/精度四项。

---

## 12. 附录：本次实测数据（支撑对齐设计）

| 项 | 数值 |
|---|---|
| AI 音频起声（playback wav） | 16:22:38.79 |
| 通话页字幕出现回答 | 16:22:39.2 |
| AI 音频结束 | 16:22:53.8 |
| 通话页回到“正在听…” | 16:22:54.1 |
| 驱动检测到回复开始/结束 | 16:22:40 / 16:23:03 |
| ai wav 文件创建时刻 | 16:21:53.785 |
| `start()` 返回时刻 | 16:21:53.869（差 84ms） |
| user wav 文件创建时刻 | 16:21:54.254（与 ai 差 469ms） |
| 录屏起点 | 16:21:54.426 |
| 各 scrcpy 源在通话中的表现 | mic/mvc/mic-voice-recognition/mic-unprocessed/mic-camcorder/voice-performance/voice-call/uplink = 全 0；downlink = 底噪 |
| playback 音频质量 | 69.6s，峰值 28226，RMS 3370，44.9–60.0s 为语音 |

---

## 13. 待评审问题清单（请逐条确认）

1. `user_wav` 允许是“平台播放源合成”的吗？还是必须设备麦克风实录？
2. 是否接受合成通道**不含房间/麦克风染色**？若必须含，是否可上 RME Loopback / 外接麦？
3. 合成时是否包含噪声/干扰人？默认 `dry+interferer` 可以吗？
4. 是否要求与播放增益/SPL 一致的电平？
5. 对齐精度要求：≤100ms 够用，还是要 ≤20ms（需同步标记）？
6. 是否保留 `mic` 路径作为未来 root 设备的开关？
7. 如果 RME Loopback 可用，是否优先做 A'（实现更简单且电平正确）？

---

---

## 14. 实现与离线验证（2026-10-27）

### 14.1 已实现

- 引擎：`e2e_executor._collect_playback_timestamps` 记录 `file_path`，并输出
  `current_round_played_audios`；`e2e_collector` 将其作为 `played_audios` 透传给驱动
  （不依赖 `audio_offsets` 是否存在）。
- 驱动：`android_doubaochat.py` 新增
  `_synthesize_user_wav` / `_align_ai_wav_to_timeline` / `_synthesize_from_played`。
  case 配置 `user_audio_source=synth_played` 时跳过用户麦克风抓取，`get_results`
  按播放文件+时间戳合成 `*_user_synth.wav`，并把 AI wav 重采样/裁补到同一 T0 的
  `*_ai_aligned.wav`；默认只拼 `dry+interferer`，不含 `noise`。
- 兼容：未配置 `synth_*` 的旧用例走原路径，行为不变。

### 14.2 离线验证结果

用真实豆包 AI 录音（`local-voice2_r0_ai.wav`，69.6s）+ 真实中文语音文件，模拟
`played_audios` 时间戳，验证结果：

| 项 | 结果 |
|---|---|
| 用户音频落点误差 | 0 样本（5.000s / 8.080s 均精确命中） |
| AI 起声对齐误差 | 20ms（44.920s → 44.940s，一个 20ms 扫描窗） |
| user/ai 时长 | 70.132s / 70.132s，差 0 |
| 峰值 | 10000 / 21373，无削波 |
| 幂等性 | 第二次调用不生成 `_ai_aligned_ai_aligned.wav`，时长不漂移 |
| 单测 | 合成测试 10/10；驱动原有 23/23；合计 33/33 通过 |
| 真机 user 落点 | 源起声 0.993s + 播放偏移 4.589s → 期望 5.582s，实测 5.583s，误差 ≈1ms |
| 时延字段 | `get_results.latency_ms` 直接给出 `question_end_to_ai_ms`（问题播完→AI 起声） |

真机这一轮 `user_wav` 落点正确，但 PC 外放的“今天周几”没有被豆包识别（UI 字幕
是环境里另一段说话），AI 通道 `peak=0`，所以“豆包听到并回复”仍未打通。

测试文件：`backend/tests/test_audio_synthesis.py`；详细报告见
`doc/android_doubao_audio_synthesis_test_report.md`。

### 14.3 尚未验证

- 未跑“平台真实播放 → RME 出声 → 手机拾音 → 豆包回复”的完整 E2E：当前 Windows
  主机只有 Realtek/Jabra 输出，数据库里的 RME 播放设备均 `Unknown`，无法复现舞台
  播放链路；已用 Realtek 直接播放做了一次真机近似，user 落点精确但手机没识别到
  播放内容，AI 未回复；
- 未验证平台 `sounddevice` 的实际出声延迟（毫秒级）对 T0 的影响；
- 未验证真实用例中 `played_audios` 与 `user_audio_source` 的配置下发。

下一步：在接有 RME 的测试机上建一条 `user_audio_source=synth_played` 的豆包用例，
跑一轮后检查 `*_user_synth.wav` 非静音、与 `*_ai_aligned.wav` 同时长，并对照录屏
字幕/通话页地标复核。

*（完）*
