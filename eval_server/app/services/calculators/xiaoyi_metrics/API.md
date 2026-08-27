# xiaoyi_metrics API 入参出参文档

## 公共约定

### task_params 通用字段

以下字段在多数指标中共享，各指标的额外字段见各自章节。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_wav` | str | 指标依赖 | 用户通道音频路径（`cap_client_process_out.wav`） |
| `ai_wav` | str | 指标依赖 | 模型回复音频路径（`cap_client_ec_out.wav`） |
| `rounds` | list[dict] | 否 | 多轮文本数据，每轮可含 `query`/`answer`/`question`/`correct_answer`/`ai_wav`/`user_wav` 等 |
| `round_number` | int | 否 | 轮次索引（0-based）。有值→单轮评估；无值→多轮整体评估 |
| `sub_tasks` | list[str] | 否 | 仅 `turn_taking` 主维度：指定只计算部分子维度 |
| `enable_llm_eval` | bool/str | 否 | 是否启用 LLM 语义评估，默认 True |

### ASR chunks 格式

```json
[
  {"text": "你好", "timestamp": [0.50, 0.80]},
  {"text": "世界", "timestamp": [0.90, 1.20]}
]
```

`timestamp` 为 `[start_s, end_s]`，秒级，双路音频共享同一时间轴（0 点为录音起点）。

---

## 1. turn_taking（话轮接管主维度）

### 入参

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_wav` | str | 是 | 用户通道音频路径 |
| `ai_wav` | str | 是 | 模型回复音频路径 |
| `rounds` | list[dict] | 否 | 多轮文本上下文，传给 `high_freq_llm_judge` |
| `round_number` | int | 否 | 单轮/多轮模式切换 |
| `sub_tasks` | list[str] | 否 | 指定子维度子集，如 `['tor', 'takeover_latency']` |
| `seg_merge_gap_s` | float | 否 | 词合并为段的间隙阈值（秒），默认 0.7 |
| `scenario_type` | str | 否 | 高频轮换场景类型（飞花令/成语接龙/快问快答/自定义） |
| `scenario_rules` | str | 否 | 自定义场景规则 |
| `enable_llm_eval` | bool | 否 | 是否启用 LLM 评估，默认 True |

### 出参

```json
{
  "tor": { /* 见 §2 */ },
  "false_takeover": { /* 见 §3 */ },
  "takeover_latency": { /* 见 §4 */ },
  "interruption": { /* 见 §7 */ },
  "non_interactive_latency": { /* 见 §9 */ },
  "high_freq_turn_taking": { /* 见 §5 */ },
  "high_freq_llm_judge": { /* 见 §6 */ }
}
```

**后处理**：若 `false_takeover.tor == 1`（检测到抢话），则 `tor` 和 `takeover_latency` 置 null。

---

## 2. tor —— 接话率

### 入参（compute_tor）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_chunks` | list | 是 | 用户通道 ASR chunks |
| `ai_chunks` | list | 是 | 模型回复 ASR chunks |
| `duration_threshold` | float | 否 | 时长阈值（秒），默认 1 |
| `num_words_threshold` | int | 否 | 词数阈值（严格大于），默认 3 |
| `min_text_len` | int | 否 | 去标点后最短文本长度，默认 1 |

### 出参

```json
{
  "tor": 1,                        // 0=未正确回复, 1=正确回复
  "n_words": 5,                    // 命中词总数
  "duration": 2.3,                // 命中词总跨度（秒）
  "hit_words": [                  // 命中词列表
    {"text": "你好", "timestamp": [1.2, 1.5]},
    ...
  ],
  "user_last_word_end_s": 0.80,   // 用户最后一词结束时间（秒）
  "message": "OK"
}
```

---

## 3. false_takeover —— 误接管率

### 入参（compute_false_takeover）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `chunks` | list | 是 | 模型词级 ASR chunks |
| `pause_intervals` | list | 是 | 停顿区间列表，每项 `{"text", "timestamp": [start, end]}` |
| `duration_threshold` | float | 否 | 时长阈值（秒），默认 1 |
| `num_words_threshold` | int | 否 | 词数阈值（严格大于），默认 3 |

### 出参

```json
{
  "tor": 0,                        // 0=未抢话, 1=抢话
  "n_words": 2,                   // 所有 pause 区间内命中词总数
  "duration": 0.5,                // 命中词总跨度（秒）
  "total_pauses": 3,              // pause 区间总数
  "hit_words": [                  // 所有命中词
    {"text": "好的", "timestamp": [1.5, 1.8]},
    ...
  ],
  "details": [                    // 每个 pause 的命中情况
    {
      "pause_interval": [1.0, 2.0],
      "hit_n_words": 2,
      "hit_words": [...]
    },
    ...
  ],
  "llm_eval": {                   // LLM 补充判断（时间戳 tor=0 时触发）
    "false_takeover": 0,          // LLM 判定结果
    "reason": "模型等待用户说完才回复",
    "evidence": {...}             // 证据信息
  }
}
```

---

## 4. takeover_latency —— 接管时延

### 入参（compute_takeover_latency_from_raw）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_chunks` | list | 是 | 用户通道 ASR chunks（kwargs 传入） |
| `ai_chunks` | list | 是 | 模型回复 ASR chunks（kwargs 传入） |
| `first_frame_ms` | int | 否 | 录屏首帧时刻（legacy 回退用） |
| `start_ms` | int | 否 | 音频开始播放时刻（legacy 回退用） |
| `input_words` | list | 否 | 主服务下发的词级时间戳（legacy 回退用） |
| `offset_ms` | int | 否 | 时延补偿（毫秒），默认 40 |

### 出参

```json
{
  "takeover_latency_ms": 450.0,     // 接管时延（毫秒），正值=AI在用户说完后开始，负值=AI抢话
  "user_last_word_end_ms": 800.0,   // 用户最后一字结束时间（毫秒）
  "ai_first_word_start_ms": 1250.0, // 模型首字开始时间（毫秒）
  "ai_skipped_opening_chunks": 2,   // 跳过的开场白 chunk 数
  "ai_total_chunks": 15,            // AI chunks 总数
  "message": "OK"
}
```

---

## 5. high_freq_turn_taking —— 高频轮换每轮回复时延

### 入参（compute_high_freq_turn_taking）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_chunks` | list | 是 | 用户通道 ASR chunks |
| `ai_chunks` | list | 是 | 模型回复 ASR chunks |
| `seg_merge_gap_s` | float | 否 | 词合并为段的间隙阈值（秒），默认 0.7 |

### 出参

```json
{
  "n_rounds": 5,                       // 轮数（用户段总数）
  "per_round": [                       // 每轮结果
    {
      "round_index": 1,               // 轮次（1-based）
      "user_segment": [0.5, 2.1, "飞花令月"],  // [start, end, text]
      "ai_segment": [2.3, 4.5, "月落乌啼霜满天"], // AI回复段，未匹配时为 null
      "response_latency_s": 0.2,     // 回复时延（秒）
      "response_latency_ms": 200.0,  // 回复时延（毫秒）
      "inter_round_gap_s": 0.1,      // 本轮AI结束→下轮用户开始的间隔（秒）
      "message": "OK"
    },
    ...
  ],
  "avg_response_latency_s": 0.25,      // 平均回复时延（秒）
  "min_response_latency_s": 0.1,      // 最小回复时延（秒）
  "max_response_latency_s": 0.5,      // 最大回复时延（秒）
  "avg_response_latency_ms": 250.0,   // 平均回复时延（毫秒）
  "n_user_segments": 5,               // 用户段总数
  "n_ai_segments": 6,                 // AI段总数
  "n_matched_rounds": 5,              // 成功匹配到AI回复的轮数
  "n_missed_rounds": 0,              // 未匹配到AI回复的轮数
  "n_unmatched_ai_segments": 1,       // 未被消费的AI段数（开场白/结束语等）
  "message": "OK"
}
```

---

## 6. high_freq_llm_judge —— 高频轮换 LLM 裁判

### 入参（evaluate_high_freq_llm）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ai_wav` | str | 是 | 模型回复音频路径（主输入，被判定对象） |
| `rounds` | list[dict] | 是 | 多轮文本数据，每轮 `{query, answer, expected_answer}` |
| `scenario_type` | str | 否 | 场景类型（飞花令/成语接龙/快问快答/自定义） |
| `scenario_rules` | str | 否 | 自定义场景规则 |
| `model` | str | 否 | LLM 模型名，缺省读 `config.LLM_JUDGE.default_model` |
| `max_tokens` | int | 否 | 最大输出 token，默认 4096 |
| `temperature` | float | 否 | 采样温度，默认 0.1 |

### 出参

```json
{
  "enabled": true,
  "model": "gpt-4o",
  "scenario_type": "飞花令",
  "ai_wav": "/path/to/ai.wav",
  "n_rounds": 5,
  "per_round": [
    {
      "round": 1,                    // 轮次
      "pass": true,                  // 是否符合预期
      "reason": "回复包含指定字且为有效诗句"
    },
    ...
  ],
  "overall_pass_rate": 0.8,          // 通过率（0.0~1.0）
  "n_passed": 4,                     // 通过轮数
  "n_failed": 1,                     // 未通过轮数
  "summary": "第1轮、第2轮符合预期；第3轮不符合预期（回复非有效诗句）",
  "tokens_used": 1500,
  "input_token": 800,
  "output_token": 700,
  "message": "OK"
}
```

---

## 7. interruption —— 打断指标

### 入参（compute_interruption_metrics）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_asr` | list/dict | 是 | 用户打断 ASR 结果（chunks 列表 或 `{text, chunks}`） |
| `model_asr` | list/dict | 是 | 模型恢复 ASR 结果（同上）。两路需同一时间轴 |
| `seg_merge_gap_s` | float | 否 | 词合并为段的间隙阈值（秒），默认 3.0 |

**calculate_interruption_metrics 入参**（封装层）：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_wav` | str | 二选一 | 用户打断 wav 路径（内部调 ASR） |
| `ai_wav` | str | 二选一 | 模型恢复 wav 路径（内部调 ASR） |
| `user_asr` | list/dict | 二选一 | 已对齐的用户 ASR 结果 |
| `model_asr` | list/dict | 二选一 | 已对齐的模型 ASR 结果 |
| `seg_merge_gap_s` | float | 否 | 同上，但强制最小 0.5 |
| `enable_llm_eval` | bool | 否 | 是否启用 LLM 评估，默认 True |
| `rounds` | list[dict] | 否 | 多轮文本数据（LLM 评估用） |

### 出参

```json
{
  "interruption_success_rate": 0.75,   // 打断成功率（让出且恢复 / 有效打断事件）
  "stop_rate": 0.80,                  // 让出率（没说穿）
  "resume_rate": 0.90,               // 恢复率
  "avg_stop_latency_s": 0.3,          // 平均打断检查时延（秒）
  "avg_recovery_latency_s": 0.5,      // 平均打断恢复时延（秒）
  "avg_overlap_s": 0.2,              // 平均双方同时说话时长（秒）
  "avg_silence_gap_s": 0.15,         // 平均静默时长（秒）
  "n_events": 4,                     // 有效打断事件数（event_type=interruption）
  "n_user_segments": 5,              // 用户语音段总数
  "n_recovery_only": 1,              // 退化事件数（只算到恢复时延）
  "n_no_model_speech": 0,            // 模型全程未说话的用户段数
  "per_event": [                     // 每个用户段的结果
    {
      "user_segment": [1.0, 3.0],   // 用户段 [start, end]
      "event_type": "interruption", // interruption / recovery_only / no_model_speech
      "stop_latency_s": 0.3,        // 用户开始打断→模型当前段结束
      "recovery_latency_s": 0.5,   // 用户说完→模型重新开口
      "silence_gap_s": 0.15,        // 模型停止→恢复的静默
      "overlap_s": 0.2,            // 重叠时长
      "stopped": true,             // 是否停下
      "resumed": true,             // 是否恢复
      "success": true              // 是否成功（容差内停下且恢复）
    },
    ...
  ],
  "message": "OK",
  "llm_eval": { /* 见 §8 */ },
  "behavior_respond": 0,            // 0/1 行为字段（LLM评估填充）
  "behavior_recover": 1,
  "behavior_ask": 0,
  "behavior_irrelevant": 0,
  "behavior_silence": 0,
  "interaction_respond": 0,
  "interaction_recover": 1,
  "interaction_ask": 0,
  "interaction_irrelevant": 0,
  "interaction_silence": 0
}
```

---

## 8. interruption_llm —— 打断 LLM 评估

### 入参（evaluate_interruption_llm）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rounds` | list[dict] | 是 | 多轮文本数据，每轮 `{query, answer, is_return_to_topic}` |
| `original_topic` | str | 否 | 原始话题文本（顶层参数） |
| `llm_model` | str | 否 | LLM 模型名，缺省读 `config.LLM_JUDGE` |
| `enable_llm_eval` | bool | 否 | 是否启用，默认 True |

### 出参

```json
{
  "enabled": true,
  "model": "gpt-4o",
  "llm_recovery_per_round": [        // 1) 打断后回复打分
    {
      "coherence": 4,               // 连贯性 0-5
      "relevance": 5,              // 相关性 0-5
      "adaptability": 4,           // 适应性 0-5
      "overall": 4.3,             // 三维平均
      "reason": "回复与打断内容衔接自然",
      "error": null
    },
    ...
  ],
  "llm_recovery_avg_coherence": 4.0,
  "llm_recovery_avg_relevance": 4.5,
  "llm_recovery_avg_adaptability": 4.2,
  "llm_return_behavior_summary": {  // 2) 回到原话题行为判断
    "respond": 1, "recover": 0, "ask": 0, "irrelevant": 0, "silence": 0
  },
  "llm_return_per_round": [          // 每轮行为判断
    {"behavior": "回应", "reason": "..."},
    ...
  ],
  "llm_return_scores_per_round": [   // 3) 回到原话题回复打分
    {"coherence": 4, "relevance": 5, "adaptability": 4, "overall": 4.3, "reason": "..."},
    ...
  ],
  "llm_return_avg_coherence": 4.0,
  "llm_return_avg_relevance": 5.0,
  "llm_return_avg_adaptability": 4.0,
  "llm_interaction_per_round": [     // 4) 交互过程行为判断
    {"behavior": "回应", "reason": "..."},
    ...
  ],
  "llm_interaction_behavior_summary": {
    "respond": 2, "recover": 1, "ask": 0, "irrelevant": 0, "silence": 0
  },
  "behavior_respond": 1,             // 0/1 行为字段（回到原话题）
  "behavior_recover": 0,
  "behavior_ask": 0,
  "behavior_irrelevant": 0,
  "behavior_silence": 0,
  "interaction_respond": 1,        // 0/1 行为字段（交互过程）
  "interaction_recover": 0,
  "interaction_ask": 0,
  "interaction_irrelevant": 0,
  "interaction_silence": 0,
  "tokens_used": 3000
}
```

---

## 9. non_interactive_latency —— 非交互意图时延

### 入参（compute_non_interactive_latency）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_wav` | str | 是 | 用户语音 wav 路径 |
| `ai_wav` | str | 是 | 模型语音 wav 路径 |
| `seg_merge_gap_s` | float | 否 | 词合并为段的间隙阈值（秒），默认 0.7 |
| `target_segment_index` | int | 否 | 目标用户段索引（0-based，默认 1=第 2 段） |

### 出参

```json
{
  "stop_latency_s": 0.3,              // 用户开始讲话→模型停止回复（秒）
  "recovery_latency_s": 0.5,         // 用户讲完→模型开始回复（秒）
  "user_segment": [2.1, 4.5, "你好世界"], // 目标用户段 [start, end, text]
  "model_active_segment": [1.0, 3.5, "正在回复"], // 被插话的模型段
  "model_recovery_segment": [5.0, 7.0, "恢复回复"], // 恢复回复段
  "silence_gap_s": 1.5,             // 模型停止→恢复的静默（秒）
  "overlap_s": 0.2,                 // 用户与模型同时说话的时长（秒）
  "n_user_segments": 2,             // 用户段总数
  "n_model_segments": 3,             // 模型段总数
  "message": "OK"
}
```

---

## 10. noise_latency —— 噪声打断时延

### 入参（compute_noise_latency）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ai_wav` | str | 是 | 模型语音 wav 路径 |
| `start_ms` | float | 是 | 噪声播放开始时间（绝对毫秒） |
| `end_ms` | float | 是 | 噪声结束播放时间（绝对毫秒） |
| `pcm_first_ms` | float | 否 | 模型 PCM 文件创建时间（绝对毫秒）。缺失时用 `start_ms - 1000` |
| `seg_merge_gap_s` | float | 否 | 词合并为段的间隙阈值（秒），默认 0.7 |

### 出参

继承 `non_interactive_latency` 全部字段，额外补充：

```json
{
  // ── 继承字段 ──
  "stop_latency_s": 0.3,
  "recovery_latency_s": 0.5,
  "user_segment": [3.0, 5.0, "noise"],
  "model_active_segment": [2.0, 4.5, "正在回复"],
  "model_recovery_segment": [5.5, 7.0, "恢复"],
  "silence_gap_s": 1.0,
  "overlap_s": 0.5,
  "n_model_segments": 3,
  "message": "OK",
  // ── 噪声特有字段 ──
  "stop_latency_ms": 300.0,          // 噪声开始→模型停止（毫秒）
  "recovery_latency_ms": 500.0,     // 噪声结束→模型恢复（毫秒）
  "noise_start_ms": 5000,           // 噪声开始绝对毫秒（回传）
  "noise_end_ms": 8000,             // 噪声结束绝对毫秒（回传）
  "pcm_first_ms": 2000,            // PCM 创建时刻（回传）
  "has_model_reply": true,         // 模型是否产生有效回复
  "model_active_segment_abs": [3000.0, 5500.0, "正在回复"], // 绝对毫秒
  "model_recovery_segment_abs": [6500.0, 8000.0, "恢复"],   // 绝对毫秒
  "model_recovery_abs_ms": 6500.0  // 恢复回复绝对世界时刻
}
```

---

## 11. rejection_judge —— 拒识场景 LLM 裁判

### 入参（evaluate_rejection_judge）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ai_wav` | str | 是 | 模型回复音频路径（主输入） |
| `user_wav` | str | 否 | 用户通道音频路径（生成 ASR 时间线上下文） |
| `model` | str | 否 | LLM 模型名，缺省读 `config.LLM_JUDGE.default_model` |
| `max_tokens` | int | 否 | 最大输出 token，默认 4096 |
| `temperature` | float | 否 | 采样温度，默认 0.1 |

### 出参

```json
{
  "enabled": true,
  "model": "gpt-4o",
  "ai_wav": "/path/to/ai.wav",
  "evaluations": [
    {
      "behavior": "沉默",          // 回应/恢复/不确定询问/未知
      "reason": "模型未对旁人交谈做出回应，保持静默"
    }
  ],
  "behavior_respond": 0,          // 回应 → 1, 否则 0
  "behavior_recover": 0,          // 恢复 → 1, 否则 0
  "behavior_uncertain": 0,        // 不确定询问 → 1, 否则 0
  "behavior_unknown": 1,          // 未知 → 1, 否则 0
  "tokens_used": 1500,
  "input_token": 800,
  "output_token": 700,
  "message": "OK"
}
```

**场景定义**：旁人交谈 / 环境噪声 / 反馈词 / 生理声 / 环境回溯。

---

## 12. interruption_judge —— 打断场景 LLM 裁判

### 入参（evaluate_interruption_judge）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ai_wav` | str | 是 | 模型回复音频路径（主输入） |
| `user_wav` | str | 否 | 用户通道音频路径（生成 ASR 时间线上下文） |
| `model` | str | 否 | LLM 模型名，缺省读 `config.LLM_JUDGE.default_model` |
| `max_tokens` | int | 否 | 最大输出 token，默认 4096 |
| `temperature` | float | 否 | 采样温度，默认 0.1 |

### 出参

```json
{
  "enabled": true,
  "model": "gpt-4o",
  "ai_wav": "/path/to/ai.wav",
  "evaluations": [
    {
      "behavior": "回应",          // 回应/恢复/不确定询问/未知
      "reason": "模型停止当前输出并对用户插话内容给出了直接回复"
    }
  ],
  "behavior_respond": 1,
  "behavior_recover": 0,
  "behavior_uncertain": 0,
  "behavior_unknown": 0,
  "tokens_used": 1500,
  "input_token": 800,
  "output_token": 700,
  "message": "OK"
}
```

**场景定义**：插话打断 / 停止指令 / 恢复原话题。

---

## 13. llm_judge —— 通用 LLM 语义打分

### 入参（evaluate_with_llm）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `answer` | str | 是 | 设备回答 |
| `correct_answer` | str | 否 | 参考答案 |
| `question` | str | 否 | 设备识别的问题 |
| `query` | str | 否 | 参考问题 |
| `record_file` | str | 否 | 音频文件路径（多模态评估） |
| `rounds` | list[dict] | 否 | 多轮数据，有则逐轮列出 |
| `model` | str | 否 | LLM 模型名，默认 `deepseek-r1` |
| `prompt` | str | 否 | 自定义 prompt 模板 |
| `max_tokens` | int | 否 | 最大输出 token，默认 1024 |
| `temperature` | float | 否 | 采样温度，默认 0.7 |
| `scoring_criteria` | list | 否 | 自定义评分维度 |

### 出参

```json
{
  "enabled": true,
  "llm_judge_score": 4,              // LLM 评分
  "criteria_scores": null,           // 分维度评分（可选）
  "reasoning": "回答准确，与参考答案一致", // 评分理由
  "model": "deepseek-r1",
  "query": "什么是人工智能",
  "answer": "人工智能是...",
  "correct_answer": "人工智能是..."
}
```

**多轮模式**额外字段：

```json
{
  "n_rounds": 3,                      // 轮数
  "per_round": [                      // 每轮结果
    {
      "enabled": true,
      "llm_judge_score": 4,
      "reasoning": "...",
      "model": "deepseek-r1",
      "query": "...",
      "answer": "...",
      "correct_answer": "..."
    },
    ...
  ]
}
```

---

## task_type → 注册表映射

| task_type | Calculator 类 | 入口函数 |
|-----------|---------------|---------|
| `turn_taking` | `TurnTakingCalculator` | 遍历子维度各自 calculate |
| `tor` | `TorCalculator` | `compute_tor` |
| `false_takeover` | `FalseTakeoverCalculator` | `compute_false_takeover` + `compute_false_takeover_llm` |
| `takeover_latency` | `TakeoverLatencyCalculator` | `compute_takeover_latency_from_raw` |
| `high_freq_turn_taking` | `HighFreqTurnTakingCalculator` | `compute_high_freq_turn_taking` |
| `high_freq_llm_judge` | `HighFreqLlmJudgeCalculator` | `evaluate_high_freq_llm` |
| `interruption_metrics` | `InterruptionMetricsCalculator` | `calculate_interruption_metrics` |
| `non_interactive_latency` | `NonInteractiveLatencyCalculator` | `compute_non_interactive_latency` |
| `noise_latency` | `NoiseLatencyCalculator` | `compute_noise_latency` |
| `rejection_judge` | `RejectionJudgeCalculator` | `evaluate_rejection_judge` |
| `interruption_judge` | `InterruptionJudgeCalculator` | `evaluate_interruption_judge` |
| `llm_judge` | `LlmJudgeCalculator` | `evaluate_with_llm` |
