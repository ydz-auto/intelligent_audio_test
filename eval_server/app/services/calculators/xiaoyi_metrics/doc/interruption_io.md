# 打断逻辑入参/出参文档

> 范围：`xiaoyi_metrics` 下与"打断"相关的两个子维度
> - **`interruption_metrics`**（`interruptibility/`）—— **纯本地时序**指标（吃双路字词级 ASR，不调 LLM）
> - **`interruption_judge`**（`env_judge/interruption_judge.py`）—— 打断场景 LLM 裁判，**一次带音频的调用**
>   产出全部打断 LLM 维度（行为分类 / 询问率 / 回复内容评分 / 停止指令遵从率）
>
> 两者独立计算、互不依赖，可单独或同时由编排器 `XiaoyiMetricsCalculator` 调起。
> LLM 相关维度全部归裁判，避免同一用例重复请求 LLM（历史上 metrics 会按事件逐个调用文本 LLM 再额外调一次裁判）。

---

## 0. 调用链路概览

### interruption_metrics（无 LLM）
```
XiaoyiMetricsCalculator.calculate          # 编排器：统一共享 ASR，按 sub_tasks 遍历子维度
  └─ InterruptionMetricsCalculator.calculate        # interruptibility/strategy.py：取参 + 逐实际轮计算 + 轮级聚合
       └─ calculate_interruption_metrics(task_params)  # interruptibility/__init__.py：wav→ASR、轮次元数据、时延聚合
            └─ compute_interruption_metrics(user_asr, model_asr, ...)  # interruption.py：本地时序指标
```

### interruption_judge（一次 LLM 调用）
```
XiaoyiMetricsCalculator.calculate          # 同上编排器（sub_tasks 含 'interruption_judge' 或任一 LLM 子维度 code）
  └─ InterruptionJudgeCalculator.calculate           # env_judge/strategy.py：取参 + 透传 sub_tasks/轮次元数据
       └─ evaluate_interruption_judge(ai_wav, user_wav, sub_tasks, rounds, ...)  # interruption_judge.py
            ├─ get_asr_chunks(user_wav / ai_wav)                 # 两路 ASR（同时供 interaction_text 与本地时序复用）
            ├─ compute_interruption_metrics(user_chunks, model_chunks)  # 本地时序定位"最后一个有效实际打断轮"的恢复段
            └─ call_llm(prompt=按 sub_tasks 拼接的分块 prompt, file_paths=[ai_wav])  # 唯一一次 LLM 调用
```

---

## 1. interruption_metrics —— 打断时序指标（纯本地）

### 1.1 入参（`task_params`，由编排器透传）

入参支持两种形式：
- **A. 传 wav 路径**：`user_wav` / `ai_wav`，内部调远程 ASR 转字词级 chunks 再算；
- **B. 直接传已对齐 ASR 结果**：`user_asr` / `model_asr`，跳过内部 ASR。
- 编排器会在算之前统一调一次共享 ASR，按**来源 wav 路径匹配**注入 `_shared_asr`，避免重复识别且保证各子维度基于同一份时间戳。

| 字段 | 类型 | 必填 | 默认/来源 | 说明 |
| --- | --- | --- | --- | --- |
| `user_wav` | str | 二选一 | 顶层或 `rounds[idx].user_wav` | 用户打断语音 wav 路径（走 A 必填） |
| `ai_wav` / `model_wav` | str | 二选一 | 顶层或 `rounds[idx].ai_wav` | 模型恢复语音 wav 路径（走 A 必填，`model_wav` 为别名） |
| `user_asr` | list\|dict | 二选一 | 顶层或 `rounds[idx]`；别名 `user_chunks`/`input_asr` | 用户 ASR 结果（chunks 列表 或 `{text, chunks}`，走 B 必填） |
| `model_asr` | list\|dict | 二选一 | 顶层或 `rounds[idx]`；别名 `model_chunks`/`recovery_asr` | 模型 ASR 结果（走 B 必填） |
| `rounds` | list\[dict] | 否 | — | 多轮数据，每轮可含 `user_wav`/`ai_wav`/`user_asr`/`model_asr`、`is_interruption`、`is_actual_interruption`、`stop_intent` |
| `round_number` | int\|str | 否 | — | 逐轮评估时平台传入的当前轮索引；缺省时按"单轮请求取唯一有效实际轮"推断 |
| `is_actual_interruption` | bool\|str | 否 | — | 显式实际打断模式；缺省但存在有效实际轮时自动置真 |
| `interruption_rounds` | list\[int]\|str | 否 | 平台按轮次元数据生成 | 用例级**有效实际打断轮**索引；缺省时按 `is_actual_interruption` → `is_interruption` 的下一轮推导 |
| `dangling_interruption_rounds` | list\[int]\|str | 否 | 同上 | 末轮 `is_interruption=true` 但无后继轮的标记，不入任何分母 |
| `stop_intent` / `is_stop_instruction` | bool\|str | 否 | 顶层或 `rounds[idx]`（含 `algorithm_params` 嵌套） | 显式停止指令标记；**不从 `is_interruption` 推断**，遵从率由裁判判定 |
| `user_seg_merge_gap_s` | float | 否 | `1.5`（`ASR_USER_SEG_MERGE_GAP_S`） | 用户侧词合并为语音段的间隙阈值(秒)；下限强制提升到 `0.1` |
| `model_seg_merge_gap_s` | float | 否 | `0.7`（`ASR_MODEL_SEG_MERGE_GAP_S`） | 模型侧词合并为段的间隙阈值(秒)；下限 `0.1` |
| `stop_tolerance_s` | float | 否 | — | **已废弃**，传入会被忽略并打日志 |
| `_shared_asr` | dict | 内部注入 | 编排器 | 共享 ASR chunks + 来源 wav；子维度按来源匹配复用，防多轮错用 |

> 经 multipart 上传时标量会变成字符串，`interruption_rounds` 可以是 JSON 字符串、
> `is_actual_interruption`/`stop_intent` 可以是 `'true'/'1'/'是'`，内部统一归一化。

### 1.2 出参

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `interruption_success_rate` | int\|float | 主成功率。显式实际打断轮模式下**严格 0/1**：所有有效实际轮成功才为 1，任一轮失败为 0；兼容模式（无轮次元数据）按事件比例 |
| `interruption_failure_rate` | float\|None | 失败率，与主成功率**二值互补**（`1 - interruption_success_rate`）：多轮里任一有效实际轮失败即为 1；无任何可判定轮时为 null |
| `timing_success_rate` | int\|float\|None | 本地时序成功率（与主成功率同值，保留作诊断） |
| `stop_rate` | float | 让出率（没说穿，时序启发式） |
| `resume_rate` | float | 恢复率（时序启发式） |
| `avg_stop_latency_s` | float\|None | 平均打断检查时延（**毫秒**；字段名保留 `_s` 历史后缀，值为 ms） |
| `avg_recovery_latency_s` | float\|None | 平均打断恢复时延（毫秒），跨有效实际轮平均 |
| `avg_overlap_s` | float\|None | 平均双方同时说话时长（毫秒，越短越好） |
| `avg_silence_gap_s` | float\|None | 平均静默时长（毫秒） |
| `target_stop_latency_s` | float\|None | **本轮代表事件**（与模型语音重叠时长最大的打断事件）的检查时延（毫秒）；多轮整体评估取最后一个有效实际轮 |
| `target_recovery_latency_s` | float\|None | 同代表事件的恢复时延（毫秒）；多轮整体评估取最后一个有效实际轮 |
| `round_latencies` | list\[dict] | **逐轮时延明细**：每项 `{round, stop_latency_s, recovery_latency_s, target_stop_latency_s, target_recovery_latency_s, first_recovery_latency_s}`（毫秒），每个有效实际打断轮一项 |
| `first_recovery_latency_s` | float\|None | **最后一个有效实际打断轮**的首个恢复回复时延（毫秒）= 该轮 `target_recovery_latency_s`；非最后一轮为 null（前面轮次回复被后续打断截断） |
| `n_events` | int | 有效打断事件数（`event_type='interruption'`） |
| `n_user_segments` | int | 用户语音段总数 |
| `n_recovery_only` | int | 退化事件数（只算到恢复时延） |
| `n_no_model_speech` | int | 模型全程未说话的用户段数 |
| `per_event` | list\[dict] | 每个用户段的结果（见 §1.3），仅诊断用，不作为维度输出 |
| `round_results` | list\[dict] | **仅多轮整体评估**：每个有效实际打断轮的完整子结果（带 `round_number`），诊断用；单轮/逐轮评估无此字段 |
| `user_segments` | list\[dict] | 用户侧完整语音段时间线（过滤开场白后，含 `words`） |
| `model_segments` | list\[dict] | 模型侧完整语音段时间线（同上） |
| `is_actual_interruption` | bool | 本次计算采用的实际打断模式 |
| `interruption_rounds` | list\[int] | 参与聚合的有效实际打断轮索引 |
| `dangling_interruption_rounds` | list\[int] | 末轮未闭合标记（不入分母） |
| `stop_intent` | bool | 本轮是否显式停止指令轮（回显） |
| `message` | str | 状态消息（`OK` / 退化提示 / 空数据提示 / 未闭合提示） |

> 本维度**不再输出任何 LLM 或行为裁判字段**（`llm_*`、`behavior_*`、`interaction_text`、
> `interruption_inquiry_rate`、`first_recovery_*` 内容评分、`stop_instruction_compliance_rate` 均已移除），
> 这些全部由 `interruption_judge` 产出，见 §2。

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
| `stop_intent` | bool | 该事件所属轮是否为显式停止指令轮（回显） |

> 一轮内可能出现多个 ASR 打断事件，它们只是诊断明细；**轮次分母按有效实际打断轮计**，
> 不按事件数量计（历史上曾出现"一轮三个事件 → 成功率 0.667"的错误口径）。

---

## 2. interruption_judge —— 打断场景 LLM 裁判（一次调用产出全部 LLM 维度）

### 2.1 入参（`evaluate_interruption_judge`）

由 `InterruptionJudgeCalculator.prepare_params` 从 `task_params` 顶层或 `rounds[idx]` 提取：

| 字段 | 类型 | 必填 | 默认/来源 | 说明 |
| --- | --- | --- | --- | --- |
| `ai_wav` | str | 是 | 顶层或 `rounds[idx].ai_wav` | **主输入**：模型回复音频路径（被判定对象，文件须存在） |
| `user_wav` | str | 否 | 顶层或 `rounds[idx].user_wav` | 用户通道音频路径（生成用户侧 ASR 时间线，并供本地时序定位恢复段） |
| `sub_tasks` | list\[str]\|str | 否 | 平台按勾选的子维度注入 | **prompt 分块开关**：未勾选的评分/停止块不拼进 prompt，对应输出为 null |
| `rounds` | list\[dict] | 否 | — | 轮次列表，含 `is_interruption`/`is_actual_interruption`/`stop_intent` |
| `round_number` | int\|str | 否 | 平台逐轮评估时传入 | 当前轮索引；缺省时按"单轮请求取唯一有效实际轮"推断 |
| `interruption_rounds` | list\[int]\|str | 否 | 平台按轮次元数据生成 | 用例级有效实际打断轮索引，用于判断单/多轮与"是否最后一轮" |
| `stop_intent` / `is_stop_instruction` | bool\|str | 否 | 顶层或 `rounds[idx]` | 本轮是否显式停止指令轮，决定是否拼接停止遵从判定块 |
| `model` | str | 否 | 维度配置 `interruption_judge` → 全局默认 | LLM 模型名（需支持音频输入） |
| `max_tokens` | int | 否 | `4096`（`LLM_DEFAULT_MAX_TOKENS`） | LLM 最大输出 token |
| `temperature` | float | 否 | `0.1`（`LLM_DEFAULT_TEMPERATURE`） | LLM 采样温度 |
| `scene` / `env_type` | str | 否 | — | 场景类型（`env_type` 为旧字段名回退）；当前实现未强制使用 |
| `start_ms` / `end_ms` / `pcm_first_ms` / `env_events` | — | 否 | 顶层或 `rounds[idx]` | 时间线/环境事件参数（公共基类提取，本维度当前未直接使用） |

> 裁判模型**直接听 `ai_wav` 回复音频**（多模态调用，音频以 base64 内联），用户侧走小 ASR 生成文本时间线作上下文。
> 两路 ASR 结果同时被本地时序复用，因此**不会新增 ASR 调用**。

#### sub_tasks → prompt 分块对照

| sub_tasks 含 | 拼接的 prompt 块 | 产出字段 |
| --- | --- | --- |
| （任意，行为分类始终执行） | 行为类别判定 | `evaluations` / `behavior_*` / `interruption_inquiry_rate` |
| `interruption_reply_content`、`interruption_first_recovery_content`、`interruption_coherence`、`interruption_relevance`、`interruption_adaptability` | 回复内容评分块 | `recovery_coherence/relevance/adaptability`、`interruption_reply_overall` 或 `first_recovery_overall`、`recovery_score_reasons` |
| `interruption_stop_instruction_compliance` **且** 该轮 `stop_intent` 为真 | 停止指令遵从判定块 | `stop_complied`、`stop_compliance_reason`、`stop_instruction_compliance_rate` |

> `sub_tasks` 缺省（旧调用方）时只做行为分类，保持向后兼容。

#### 评分目标轮规则

内容评分只针对**最后一个有效实际打断轮的首个恢复回复**——前面轮次的回复会被后续打断截断，不完整：

- `valid = interruption_rounds`（缺省时按 `is_actual_interruption` → `is_interruption` 下一轮推导，dangling 末轮排除）
- `is_multi = len(valid) > 1`；`is_target = 当前轮 == valid[-1]`
- 非目标轮：不拼接评分块，内容评分字段全部为 null
- 目标轮：`interruption_reply_overall` 与 `first_recovery_overall` **同时**写入同一个评分
  （两个维度面向不同用例形态——单实际轮看"打断回复内容评分"、多实际轮看"恢复首轮内容评分"，
  同时填充可保证用例只勾选其中任一维度时也能看到结果）

### 2.2 出参（`evaluate_interruption_judge` 返回，扁平结构）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否成功调用（LLM 调用失败置 false） |
| `model` | str | 实际使用的 LLM 模型名 |
| `ai_wav` | str | 被判定的回复音频路径 |
| `interaction_text` | str | 完整交互文字（query/answer 按时间排序，含 `[m:ss; m:ss]` 时间戳） |
| `evaluations` | list\[dict] | 裁判结果列表，每项 `{behavior, reason}`（当前取首项） |
| `behavior_respond` | int (0/1) | 行为=「回应」→1，否则 0 |
| `behavior_recover` | int (0/1) | 行为=「恢复」→1，否则 0 |
| `behavior_uncertain` | int (0/1) | 行为=「不确定询问」→1，否则 0 |
| `behavior_unknown` | int (0/1) | 行为=「未知」→1，否则 0 |
| `interruption_inquiry_rate` | float\|None | 打断询问率：行为有效解析时 `不确定询问→1.0`，否则 `0.0`；解析失败为 null（**不当 0**） |
| `recovery_coherence` | float\|None | 目标轮首个恢复回复的连贯性(0-5) |
| `recovery_relevance` | float\|None | 相关性(0-5) |
| `recovery_adaptability` | float\|None | 适应性(0-5) |
| `interruption_reply_overall` | float\|None | 目标轮（最后一个有效实际打断轮）恢复回复的内容综合评分(0-5)；面向**单**实际打断轮用例，非目标轮为 null |
| `first_recovery_overall` | float\|None | 同上评分；面向**多**实际打断轮用例，两个字段同时写入，非目标轮为 null |
| `recovery_score_reasons` | dict\|None | 三维评分理由 `{coherence, relevance, adaptability}` |
| `stop_complied` | bool\|None | 停止指令是否被遵从（未勾选/非停止轮/解析失败为 null） |
| `stop_compliance_reason` | str\|None | 停止遵从判定理由 |
| `stop_instruction_compliance_rate` | float\|None | 停止指令遵从率：遵从 `1.0`，不遵从 `0.0`，无有效判定 null |
| `tokens_used` / `input_token` / `output_token` | int | token 统计 |
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

#### 停止指令遵从判定口径
| 模型行为 | 判定 |
| --- | --- |
| 停止原内容输出，之后无新语音 | 遵从（1.0） |
| 停止原内容输出，只回复"好的/我明白了/已为你停止"等确认语 | **遵从（1.0）**，并算打断成功 |
| 无视停止指令，继续输出原来的内容 | 不遵从（0.0） |

> 停止指令轮的主成功率由平台回填：裁判判定遵从时，即使本地时序认为"停止后仍有模型语音"，
> 也会把 `interruption_success_rate` 回填为 1
> （`Intelligent-Audio-TEST/backend/services/evaluation/evaluation_result_processor.py::reconcile_stop_instruction_success`）。

> LLM 输出严格 JSON（单个对象）：`{behavior, reason}`，勾选内容评分时追加
> `recovery_score{coherence, relevance, adaptability, overall, *_reason}`，
> 勾选停止判定时追加 `stop_complied` / `stop_compliance_reason`。未勾选的键不会出现在输出格式要求里。

---

## 3. 配置项（`.env` / `config.LLM_JUDGE`）

打断裁判从 `config.LLM_JUDGE` 读取 LLM 配置（`get_llm_config()`）；`interruption_metrics` 不使用 LLM 配置：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_JUDGE_API_BASE` | `https://az.gptplus5.com/v1` | LLM API base URL |
| `LLM_JUDGE_API_KEY` | `''` | LLM API Key（未配置则裁判返回 `enabled=false`） |
| `LLM_JUDGE_DEFAULT_MODEL` | `gpt-4o-mini` | 全局兜底模型名 |
| `LLM_JUDGE_MODEL_INTERRUPTION_JUDGE` | `''` | 打断裁判维度专用模型（覆盖全局，需支持音频输入） |
| `LLM_JUDGE_MAX_TOKENS` | `4096` | 全局默认 max_tokens |
| `LLM_JUDGE_TEMPERATURE` | `0.1` | 全局默认 temperature |
| `LLM_JUDGE_TIMEOUT` | `120` | LLM 请求超时(秒) |

模型解析优先级（`resolve_model`）：显式 `model` 参数 > 维度专用模型 > 全局默认。
- `interruption_judge` 缺 `ai_wav` 或文件不存在时抛 `FileNotFoundError`；LLM 调用/解析失败时返回 `enabled=false` 或 `message='LLM 输出解析失败'`，不抛异常。
- 每次 LLM 调用都会写一条审计 JSONL 到 `config.LLM_CALL_LOG_DIR`（见 `llm_call_audit_log.md`），
  可用于核对"每用例只调用一次"。
