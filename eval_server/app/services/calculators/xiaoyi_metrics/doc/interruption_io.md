# 打断逻辑入参/出参文档

> 范围：`xiaoyi_metrics` 下与"打断"相关的两个子维度
> - **`interruption_metrics`**（`interruptibility/`）—— 时序指标 + LLM 语义复核/回复打分（吃双路字词级 ASR）
> - **`interruption_judge`**（`env_judge/interruption_judge.py`）—— 打断场景行为裁判（吃模型回复音频）
>
> 两者独立计算、互不依赖，可单独或同时由编排器 `XiaoyiMetricsCalculator` 调起。

---

## 0. 调用链路概览

### interruption_metrics
```
XiaoyiMetricsCalculator.calculate          # 编排器：统一共享 ASR，按 sub_tasks 遍历子维度
  └─ InterruptionMetricsCalculator.calculate        # interruptibility/strategy.py：取参 + 注入共享 ASR
       └─ calculate_interruption_metrics(task_params)  # interruptibility/__init__.py：wav→ASR、调度
            ├─ compute_interruption_metrics(user_asr, model_asr, ...)  # interruption.py：本地时序指标
            └─ evaluate_interruption_llm(per_event, task_params, ...)  # interruption_llm.py：LLM 语义复核+打分
```

### interruption_judge
```
XiaoyiMetricsCalculator.calculate          # 同上编排器（sub_tasks 含 'interruption_judge'）
  └─ InterruptionJudgeCalculator.calculate           # env_judge/strategy.py：取参（单轮/多轮）
       └─ evaluate_interruption_judge(ai_wav, user_wav, model, ...)  # interruption_judge.py：多模态 LLM 裁判
```

---

## 1. interruption_metrics —— 打断时序指标 + LLM 语义复核

### 1.1 入参（`task_params`，由编排器透传）

入参支持两种形式：
- **A. 传 wav 路径**：`user_wav` / `ai_wav`，内部调远程 ASR 转字词级 chunks 再算；
- **B. 直接传已对齐 ASR 结果**：`user_asr` / `model_asr`，跳过内部 ASR。
- 编排器会在算之前统一调一次共享 ASR，按**来源 wav 路径匹配**注入 `_shared_asr`，避免重复识别且保证各子维度基于同一份时间戳。

| 字段 | 类型 | 必填 | 默认/来源 | 说明 |
| --- | --- | --- | --- | --- |
| `user_wav` | str | 二选一 | 顶层或 `rounds[0].user_wav` | 用户打断语音 wav 路径（走 A 必填） |
| `ai_wav` / `model_wav` | str | 二选一 | 顶层或 `rounds[0].ai_wav` | 模型恢复语音 wav 路径（走 A 必填，`model_wav` 为别名） |
| `user_asr` | list\|dict | 二选一 | 顶层或 `rounds[0]`；别名 `user_chunks`/`input_asr` | 用户 ASR 结果（chunks 列表 或 `{text, chunks}`，走 B 必填） |
| `model_asr` | list\|dict | 二选一 | 顶层或 `rounds[0]`；别名 `model_chunks`/`recovery_asr` | 模型 ASR 结果（走 B 必填） |
| `rounds` | list\[dict] | 否 | — | 多轮数据，每轮可含 `user_wav`/`ai_wav`/`user_asr`/`model_asr` 等；缺 `round_number` 时取 `rounds[0]` |
| `user_seg_merge_gap_s` | float | 否 | `1.5`（`ASR_USER_SEG_MERGE_GAP_S`） | 用户侧词合并为语音段的间隙阈值(秒)；下限强制提升到 `0.1` |
| `model_seg_merge_gap_s` | float | 否 | `0.7`（`ASR_MODEL_SEG_MERGE_GAP_S`） | 模型侧词合并为段的间隙阈值(秒)；下限 `0.1` |
| `stop_tolerance_s` | float | 否 | — | **已废弃**，传入会被忽略并打日志 |
| `enable_llm_eval` | bool\|str | 否 | `True` | 是否启用 LLM 语义复核+回复打分；`'true'/'1'/'yes'` 视为启用 |
| `_shared_asr` | dict | 内部注入 | 编排器 | 共享 ASR chunks + 来源 wav；子维度按来源匹配复用，防多轮错用 |

#### 透传给 LLM 评估的字段（`enable_llm_eval=True` 时）
| 字段 | 类型 | 必填 | 默认/来源 | 说明 |
| --- | --- | --- | --- | --- |
| `original_topic` | str | 否 | `''` | 原始话题/上下文，喂给 LLM 做 relevance 判定 |
| `llm_model` | str | 否 | 维度配置 `interruption_llm` → 全局默认 | LLM 模型名 |
| `max_tokens` | int | 否 | `4096` | LLM 最大输出 token |
| `temperature` | float | 否 | `0.1` | LLM 采样温度 |

> LLM 入参还隐式包含 `compute_interruption_metrics` 产出的 `per_event` / `user_segments` / `model_segments`（含字词级 ASR 文本与 `words`），由 `evaluate_interruption_llm` 自动从结果中读取，**不再依赖 `rounds` 文本**。

### 1.2 出参（`compute_interruption_metrics` 返回，LLM 启用时由其覆盖部分字段）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `interruption_success_rate` | float | 打断成功率。LLM 启用 = `llm_success_rate`（语义判定，成功事件/已评估事件）；未启用 = 本地时序启发式（让出且恢复 / 有效打断事件） |
| `timing_success_rate` | float\|None | 本地时序启发式成功率**备份**（始终等于覆盖前的 `interruption_success_rate`） |
| `stop_rate` | float | 让出率（没说穿，时序启发式） |
| `resume_rate` | float | 恢复率（时序启发式） |
| `avg_stop_latency_s` | float\|None | 平均打断检查时延（**毫秒**；字段名保留 `_s` 历史后缀，值为 ms） |
| `avg_recovery_latency_s` | float\|None | 平均打断恢复时延（毫秒） |
| `avg_overlap_s` | float\|None | 平均双方同时说话时长（毫秒，越短越好） |
| `avg_silence_gap_s` | float\|None | 平均静默时长（毫秒） |
| `n_events` | int | 有效打断事件数（`event_type='interruption'`） |
| `n_user_segments` | int | 用户语音段总数 |
| `n_recovery_only` | int | 退化事件数（只算到恢复时延） |
| `n_no_model_speech` | int | 模型全程未说话的用户段数 |
| `per_event` | list\[dict] | 每个用户段的结果（见 §1.3） |
| `user_segments` | list\[dict] | 用户侧完整语音段时间线（过滤开场白后，含 `words`），供 LLM 全局上下文 |
| `model_segments` | list\[dict] | 模型侧完整语音段时间线（同上） |
| `llm_eval` | dict | LLM 评估汇总（见 §1.4）；未启用时 `{enabled:false, message:...}` |
| `llm_success_rate` | float\|None | LLM 语义判定的成功率，覆盖 `interruption_success_rate` |
| `interruption_real_rate` | float\|None | LLM 判定"真正打断"的事件占比 |
| `llm_recovery_avg_coherence` | float\|None | 回复连贯性均分(0-5) |
| `llm_recovery_avg_relevance` | float\|None | 回复相关性均分(0-5) |
| `llm_recovery_avg_adaptability` | float\|None | 回复适应性均分(0-5) |
| `llm_recovery_coherence_reason` | str\|None | 连贯性分项理由（各事件用 `；`拼接） |
| `llm_recovery_relevance_reason` | str\|None | 相关性分项理由 |
| `llm_recovery_adaptability_reason` | str\|None | 适应性分项理由 |
| `llm_recovery_per_round` | list\[dict] | 每事件复核+打分明细（见 §1.4） |
| `llm_return_avg_coherence` | float\|None | 保留字段（回到原话题链路已移除，恒为 null） |
| `llm_return_avg_relevance` | float\|None | 保留字段（恒为 null） |
| `llm_return_avg_adaptability` | float\|None | 保留字段（恒为 null） |
| `llm_return_scores_per_round` | list | 保留字段（恒为 `[]`） |
| `message` | str | 状态消息（`OK` / 退化提示 / 空数据提示） |

### 1.3 `per_event` 单事件结构

对每个用户打断段 `u=[u_s, u_e]` 产出一项。`event_type` 决定该段属于哪种情形：

| `event_type` | 情形 | 说明 |
| --- | --- | --- |
| `interruption` | A：模型当时在说话（完整打断） | 可算时延 + 成功率，计入分母 |
| `recovery_only` | B：模型当时不在说话（只含恢复段或模型提前停了） | 仅算恢复时延，`success=None`，不计成功率 |
| `no_model_speech` | C：模型全程没说话 | `success=None`，无任何时延 |

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_segment` | [float, float] | 用户打断段 `[start_s, end_s]`（秒） |
| `user_text` | str | 用户打断段字词级 ASR 拼接文本 |
| `user_words` | list\[dict] | 用户段内原始 word chunks（`{text, timestamp}`） |
| `model_interrupted_text` | str | 被打断时模型正在说的尾巴文本（情形 A） |
| `model_interrupted_words` | list\[dict] | 被打断段字词级 chunks |
| `model_recovery_text` | str | 模型恢复回复文本 |
| `model_recovery_words` | list\[dict] | 恢复段字词级 chunks |
| `event_type` | str | `interruption` / `recovery_only` / `no_model_speech` |
| `stop_latency_s` | float\|None | 用户开始打断 → 模型当前段结束（毫秒） |
| `recovery_latency_s` | float\|None | 用户说完 → 模型重新开口（毫秒） |
| `silence_gap_s` | float\|None | 模型尾巴结束 → 恢复段起点（毫秒） |
| `overlap_s` | float\|None | 双方同时说话时长（毫秒） |
| `stopped` | bool\|None | 模型是否停下（有后续恢复段即视为停下） |
| `resumed` | bool\|None | 模型是否恢复 |
| `success` | bool\|None | 本地时序启发式：`stopped and resumed`（情形 B/C 为 None） |

### 1.4 `llm_eval` / `llm_recovery_per_round` 结构（LLM 启用时）

`llm_eval` 顶层即 `evaluate_interruption_llm` 返回值：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否成功调用 |
| `model` | str | 实际使用的 LLM 模型名 |
| `original_topic` | str | 传入的原始话题 |
| `llm_recovery_per_round` | list\[dict] | 每事件复核+打分明细（见下表） |
| `llm_recovery_avg_coherence/relevance/adaptability` | float\|None | 三维均分(0-5) |
| `llm_recovery_coherence_reason/relevance_reason/adaptability_reason` | str | 三维分项理由拼接 |
| `llm_return_scores_per_round` | list | 保留字段（`[]`） |
| `llm_return_avg_*` | float\|None | 保留字段（null） |
| `interruption_real_rate` | float\|None | LLM 判定真正打断的事件占比 |
| `llm_success_rate` | float\|None | LLM 语义判定的成功率（成功事件/已评估事件） |
| `n_events_evaluated` | int | 已评估事件数（仅对 `event_type='interruption'` 的事件调用 LLM） |
| `message` | str | `OK` / 错误信息 |

#### `llm_recovery_per_round` 单项结构
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | int | 事件序号（1-based，仅计 interruption 事件） |
| `user_text` | str | 用户打断文本 |
| `model_interrupted_text` | str | 模型被打断尾巴文本 |
| `model_recovery_text` | str | 模型恢复回复文本 |
| `is_real_interruption` | bool\|None | (A) 是否真的打断（语义复核） |
| `interruption_reason` | str | (A) 真打断/否的简短原因 |
| `success` | bool\|None | (B) 是否成功处理打断（语义判定，成功率口径；只要 AI 停下即 true） |
| `success_reason` | str | (B) 停下/说穿的原因 |
| `coherence` | float\|None | (C) 连贯性 0-5 |
| `relevance` | float\|None | (C) 相关性 0-5 |
| `adaptability` | float\|None | (C) 适应性 0-5 |
| `overall` | float\|None | 三维平均（保留一位小数）；LLM 未给时本地补算 |
| `coherence_reason`/`relevance_reason`/`adaptability_reason` | str | 三维分项理由 |
| `error` | str | 单事件调用失败时的错误信息（失败不计入均值聚合） |

> LLM 输出严格 JSON：`{is_real_interruption, interruption_reason, success, success_reason, coherence, relevance, adaptability, overall, coherence_reason, relevance_reason, adaptability_reason}`。单事件失败不阻断其他事件（记 `error`，不计入均值）。

---

## 2. interruption_judge —— 打断场景行为裁判

### 2.1 入参（`evaluate_interruption_judge`）

由 `InterruptionJudgeCalculator.prepare_params` 从 `task_params` 顶层或 `rounds[idx]` 提取（单轮/多轮统一取目标轮，`rounds` 整体保留作上下文）：

| 字段 | 类型 | 必填 | 默认/来源 | 说明 |
| --- | --- | --- | --- | --- |
| `ai_wav` | str | 是 | 顶层或 `rounds[idx].ai_wav` | **主输入**：模型回复音频路径（被判定对象，文件须存在） |
| `user_wav` | str | 否 | 顶层或 `rounds[idx].user_wav` | 用户通道音频路径（用于生成用户侧 ASR 时间线上下文） |
| `model` | str | 否 | 维度配置 `interruption_judge` → 全局默认 | LLM 模型名 |
| `max_tokens` | int | 否 | `4096`（`LLM_DEFAULT_MAX_TOKENS`） | LLM 最大输出 token |
| `temperature` | float | 否 | `0.1`（`LLM_DEFAULT_TEMPERATURE`） | LLM 采样温度 |
| `scene` / `env_type` | str | 否 | — | 场景类型（`env_type` 为旧字段名回退）；当前实现未强制使用 |
| `rounds` | list\[dict] | 否 | — | 整体保留作上下文 |
| `start_ms` / `end_ms` / `pcm_first_ms` / `env_events` | — | 否 | 顶层或 `rounds[idx]` | 时间线/环境事件参数（公共基类提取，本维度当前未直接使用） |

> 裁判模型**直接听 `ai_wav` 回复音频**（多模态调用，音频以 base64 内联），用户侧走小 ASR 生成文本时间线作上下文；模型回复本身不在时间线里。

### 2.2 出参（`evaluate_interruption_judge` 返回）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否成功调用（LLM 调用失败置 false） |
| `model` | str | 实际使用的 LLM 模型名 |
| `ai_wav` | str | 被判定的回复音频路径 |
| `evaluations` | list\[dict] | 裁判结果列表，每项 `{behavior, reason}`（当前取首项） |
| `behavior_respond` | int (0/1) | 行为=「回应」→1，否则 0 |
| `behavior_recover` | int (0/1) | 行为=「恢复」→1，否则 0 |
| `behavior_uncertain` | int (0/1) | 行为=「不确定询问」→1，否则 0 |
| `behavior_unknown` | int (0/1) | 行为=「未知」→1，否则 0 |
| `tokens_used` | int | 总 token |
| `input_token` | int | 输入 token |
| `output_token` | int | 输出 token |
| `message` | str | `OK` / 失败原因（`LLM 调用失败` / `LLM 输出解析失败`） |

#### 行为类别（四选一）
| 类别 | 说明 |
| --- | --- |
| **回应** | 模型对重叠内容进行了有意义的回应（回答/澄清/对重叠中提到的内容做出反应） |
| **恢复** | 模型忽略重叠，继续或完成重叠之前正在进行中的任务或回答 |
| **不确定询问** | 模型表示不确定/难听清/缺信息（如"我没听清…"），未给出明确针对内容的回答；泛化重复/澄清归入此类 |
| **未知** | 模型输出语义偏离目标或信息量低，未明确恢复/回应/表达不确定；含重叠后模型完全无语音输出的情况 |

#### 场景定义（打断干扰内容类型参考）
| 场景 | 定义 |
| --- | --- |
| 插话打断 | 模型正在输出回复时，用户插话打断，发起新的提问或请求 |
| 停止指令 | 用户对模型发出明确停止指令（"停""闭嘴""不用了""停下来""好了好了"等） |
| 恢复原话题 | 用户打断切换话题后，要求回到原始话题（"我们继续聊刚才说的""回到之前的话题"） |

> LLM 输出严格 JSON：`{behavior, reason}`。`behavior` 须为四类之一；`reason` 说明从回复音频中听到了什么、结合时间线观察到什么、为何归类。

---

## 3. 配置项（`.env` / `config.LLM_JUDGE`）

两个打断维度均从 `config.LLM_JUDGE` 读取 LLM 配置（`get_llm_config()`）：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_JUDGE_API_BASE` | `https://az.gptplus5.com/v1` | LLM API base URL |
| `LLM_JUDGE_API_KEY` | `''` | LLM API Key（未配置则 `interruption_llm` 抛错跳过） |
| `LLM_JUDGE_DEFAULT_MODEL` | `gpt-4o-mini` | 全局兜底模型名 |
| `LLM_JUDGE_MODEL_INTERRUPTION_JUDGE` | `''` | 打断裁判维度专用模型（覆盖全局） |
| `LLM_JUDGE_MODEL_INTERRUPTION_LLM` | `''` | 打断语义复核维度专用模型（覆盖全局） |
| `LLM_JUDGE_MAX_TOKENS` | `4096` | 全局默认 max_tokens |
| `LLM_JUDGE_TEMPERATURE` | `0.1` | 全局默认 temperature |
| `LLM_JUDGE_TIMEOUT` | `120` | LLM 请求超时(秒) |

模型解析优先级（`resolve_model`）：显式 `model` 参数 > 维度专用模型 > 全局默认。
- `interruption_llm` 未配置 API base/key 时整体跳过（预检抛 `ValueError`，由编排器 catch 记 `llm_eval.enabled=false`）。
- `interruption_judge` 缺 `ai_wav` 或文件不存在时抛 `FileNotFoundError`。
