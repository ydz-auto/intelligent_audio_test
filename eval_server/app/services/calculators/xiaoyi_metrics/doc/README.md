# xiaoyi_metrics

小艺（语音大模型）评估指标包。围绕"话轮接管 / 打断 / 噪声 / 环境理解 / 高频轮换"等语音对话能力，提供从 ASR 时间戳到语义打分的全链路计算。

## 目录结构

```
xiaoyi_metrics/
├── __init__.py                        # XiaoyiMetricsCalculator 全域编排器（统一共享 ASR + 跨域聚合）
├── doc/                               # 指标文档（README / API / interruption_io / llm_call_audit_log 等）
├── shared/                            # 共享工具子包
│   ├── asr_utils.py                   #   ASR chunks 工具（pause 区间 / 标点过滤 / 段合并）
│   ├── audio_alignment.py             #   played_audios FFT 互相关对齐（生成干净版音频）
│   ├── constants.py                   #   共享常量（LLM/ASR/时序阈值/行为标签）
│   ├── llm_client.py                  #   LLM 调用统一入口 call_llm（多模态/流式/重试/审计）
│   └── llm_call_logger.py             #   LLM 审计 JSONL 写入（剥离 base64）
├── turn_taking/                       # 话轮接管指标子包（统一 ASR 入口 _get_asr_chunks）
│   ├── __init__.py                    #   _get_asr_chunks：ASR 词级时间戳唯一出口
│   ├── strategy.py                    #   TurnTakingCalculator（域内编排）+ 6 个子维度 Calculator
│   ├── tor.py                         #   接话率（Turn-Over Rate）
│   ├── false_takeover.py              #   误接管率（用户停顿期间是否抢话 + LLM 补充判断）
│   ├── takeover_latency.py            #   接管时延（AI 首字 - 用户末字）
│   ├── input_asr.py                   #   输入识别准确率（query vs question 文本匹配）
│   ├── high_freq_turn_taking.py       #   高频轮换每轮回复时延（飞花令/成语接龙/快问快答）
│   ├── high_freq_llm_judge.py         #   高频轮换 LLM 裁判（模型回复音频 → 逐轮 pass/fail）
│   └── reply_quality.py               #   单轮回复质量 LLM 评分（0-5）
├── turn_eval/                         # 逐轮三分类子包（独立主维度）
│   ├── strategy.py                    #   TurnEvalCalculator（轮次切分 → 三分类 → 时延 → 质量）
│   └── turn_evaluation.py             #   轮次切分 + 三分类（误解管/接管/未接管）+ 回复质量评分
├── interruptibility/                  # 打断指标实现子包（v2）
│   ├── __init__.py                    #   calculate_interruption_metrics 统一入口（本地时序）
│   ├── strategy.py                    #   InterruptionMetricsCalculator（进程内直调逐轮 LLM 裁判）
│   ├── interruption.py                #   打断本地时序指标（停得下 / 恢复得来；FFT 精修用户段）
│   └── round_metrics.py               #   轮次锚定 + 用例类型推导 + spec 字段派生（纯函数）
├── rejection_scene_awareness/         # 拒识与场景感知子包
│   ├── __init__.py
│   ├── strategy.py                    #   NonInteractiveLatencyCalculator + NoiseLatencyCalculator
│   ├── non_interactive_latency.py     #   非交互意图时延（模型回复期间用户说话）
│   └── noise_latency.py               #   噪声打断时延（噪声播放期间模型响应）
├── env_judge/                         # 环境音/打断能力 LLM 裁判子包
│   ├── __init__.py
│   ├── strategy.py                    #   EnvJudgeCalculator + RejectionJudgeCalculator
│   ├── env_judge.py                   #   环境理解裁判（understand_correct + 时延 + 评分）
│   ├── env_response_latency.py        #   环境声回复时延（FFT 定位 + 模型首字时间戳）
│   ├── interruption_judge.py          #   打断场景 LLM 裁判（v2 被 interruption_metrics 进程内直调）
│   └── rejection_judge.py             #   拒识场景 LLM 裁判（行为分类 + rate 评级）
```

> `llm_judge/` 域（通用 LLM 语义打分）已移除。

## 架构说明

每个域子包自包含**策略类**（`strategy.py`）和**实现函数**，策略类继承 `BaseCalculator`，实现 `validate → prepare_params → calculate` 三步模板方法。由 `calculators/__init__.py` 自动注册到 `TaskService.CALCULATORS` 注册表。

所有 Calculator 均支持**单轮/多轮**模式：
- `round_number` 有值（0/1/2...）→ 单轮评估，取 `rounds[round_number]`
- `round_number` 不存在 → 多轮整体评估（逐轮计算后聚合，数值字段取平均）

**两级编排，ASR 只调一次**：

```
XiaoyiMetricsCalculator（全域编排，xiaoyi_metrics/__init__.py）
  │  统一调一次双路 ASR（user_wav + ai_wav）+ 音频对齐 + pause 区间
  │  → 注入各子维度 params['_shared_asr']
  ▼
  ├─ TurnTakingCalculator（turn_taking 域内编排，turn_taking/strategy.py）
  │     tor / false_takeover / takeover_latency / reply_quality
  │     high_freq_turn_taking / high_freq_llm_judge
  ├─ TurnEvalCalculator（turn_eval 域：逐轮三分类 + 接管时延 + 回复质量）
  ├─ InterruptionMetricsCalculator（interruptibility 域：打断 v2）
  ├─ NonInteractiveLatencyCalculator（rejection_scene_awareness 域）
  └─ ...
```

```
calculators/__init__.py              # import 即自动注册全部 calculator
  ├── wer/strategies.py               #   WerCalculator 等 5 个策略类
  ├── der/strategy.py                #   DerCalculator
  └── xiaoyi_metrics/                #   本包
      ├── __init__.py                #     XiaoyiMetricsCalculator（全域编排）
      ├── turn_taking/strategy.py    #     TurnTakingCalculator（域内编排）+ Tor/FalseTakeover/
      │                              #     TakeoverLatency/HighFreqTurnTaking/HighFreqLlmJudge/ReplyQuality
      ├── turn_eval/strategy.py      #     TurnEvalCalculator
      ├── interruptibility/strategy.py  #  InterruptionMetricsCalculator
      ├── rejection_scene_awareness/strategy.py  # NonInteractiveLatency + NoiseLatency
      ├── env_judge/strategy.py      #     EnvJudgeCalculator + RejectionJudgeCalculator
```

## 子包说明

### shared —— 共享工具

- **asr_utils.py**：ASR chunks 工具（`compute_pause_intervals` / `is_punct_or_empty` / 语音段合并）
- **audio_alignment.py**：played_audios（干净音源）→ user_wav（劣化）FFT 互相关对齐，生成干净版音频（`generate_aligned_clean_audio`，输出对齐段供 turn 轮次归属）
- **constants.py**：LLM/ASR/时序阈值/行为标签等魔法数字集中管理
- **llm_client.py**：`call_llm` 统一 LLM 入口（OpenAI 兼容 / 多模态 base64 / 流式 / 重试）+ `resolve_model` / `get_llm_config` / `build_interaction_text`
- **llm_call_logger.py**：每次 LLM 调用写 JSONL 审计日志（剥离 base64，永不轮转）

### turn_taking —— 话轮接管指标

ASR 词级时间戳统一出口 `_get_asr_chunks`，位于 [turn_taking/__init__.py](turn_taking/__init__.py)。

#### 统一入口（策略类，经 TaskService.CALCULATORS 注册表分发）

| 策略类 | 用途 | 对应 task_type |
|------|------|----------------|
| `TurnTakingCalculator` | 域内编排：调一次双路 ASR，遍历子维度共享结果（tor / false_takeover / takeover_latency / reply_quality / high_freq_turn_taking / high_freq_llm_judge） | `turn_taking` |
| `TorCalculator` / `FalseTakeoverCalculator` / `TakeoverLatencyCalculator` | tor / false_takeover / takeover_latency 三项独立入口 | `tor` / `false_takeover` / `takeover_latency` |
| `HighFreqTurnTakingCalculator` | 高频轮换每轮回复时延独立入口 | `high_freq_turn_taking` |
| `HighFreqLlmJudgeCalculator` | 高频轮换 LLM 裁判独立入口 | `high_freq_llm_judge` |
| `ReplyQualityCalculator` | 单轮回复质量 LLM 评分独立入口 | `reply_quality` |

> 打断指标（interruption_metrics）已迁移到 `interruptibility/` 域，`turn_taking` 域不再承载。

#### 核心概念：双路 ASR

tor / false_takeover / takeover_latency 共用**双路 ASR**方案：

- **user_wav**（`cap_client_process_out.wav`）：用户说话通道
- **ai_wav**（`cap_client_ec_out.wav`）：AI 回复通道

两路音频同时开始录制，共享同一时间轴（0 点为录音起点），因此可直接用各路 ASR 时间戳相减得到时延。`TurnTakingCalculator.calculate()` 统一调一次双路 ASR，将 `chunks` 注入各子维度的 `_shared_asr`，子维度优先使用已注入的 chunks，避免重复调用远程 ASR。

#### 各指标详解

##### 1. tor —— 接话率 [tor.py](turn_taking/tor.py)

判定用户结束说话后模型是否正确开始回复。

- 取 user_wav 最后一词结束时间 `user_last_end`
- 在 ai_wav 中找 `user_last_end` 之后的模型回复 chunks（跳过开场白）
- 过滤去标点后文本长度 < 3 的 chunk（ASR 误识别）
- 判定：命中词时长 ≥ 1s **或** 命中词去标点总字符数 > 3 → `tor=1`（正确回复）

```
阈值：TURN_DURATION_THRESHOLD = 1s, TURN_NUM_WORDS_THRESHOLD = 3
```

##### 2. false_takeover —— 误接管率 [false_takeover.py](turn_taking/false_takeover.py)

判定用户**停顿期间**模型是否错误接管（抢话）。

- 将所有 pause 区间内命中的模型词拼到一起
- 每个命中词时间戳裁剪到 pause 区间内（只算重叠部分）
- 判定：合并后时长 ≥ 1s **或** 命中词数 > 3 → `tor=1`（抢话）

pause 区间来源：从 user_wav ASR 结果检测，相邻 chunk 间隔在 0.2s~3.0s 之间视为停顿。

**LLM 补充判断**：时间戳 `tor=0` 时，调 `compute_false_takeover_llm` 做语义判断（含 played_audios FFT 对齐），若 LLM 判定 `false_takeover=1` 则修正 `tor=1`。

##### 3. takeover_latency —— 接管时延 [takeover_latency.py](turn_taking/takeover_latency.py)

```
takeover_latency_ms = ai_first_word_start_ms - user_last_word_end_ms
```

- 新逻辑：双路 ASR chunks 直接相减（开场白过滤：找 user 末词结束之后的首个 AI chunk），支持 played_audios FFT 互相关对齐精修
- legacy 回退：基于 `first_frame_ms` + 录屏 ASR 首词偏移（`offset_ms` 默认 40）

正值 = AI 在用户说完后才开始；负值 = AI 抢话。

##### 4. input_asr —— 输入识别准确率 [input_asr.py](turn_taking/input_asr.py)

对比参考 `query`（用例参数 JSON）与设备识别 `question`（`get_results()` 返回）。

- 文本归一化：转小写、去标点、压缩空白
- `difflib.SequenceMatcher` 计算相似度
- 相似度 ≥ 0.8 → `match=True`

支持从顶层或 `rounds` 逐轮拼接提取 query/question。

##### 5. high_freq_turn_taking —— 高频轮换每轮回复时延 [high_freq_turn_taking.py](turn_taking/high_freq_turn_taking.py)

飞花令 / 成语接龙 / 快问快答等高频多轮对话场景，计算每轮模型回复时延。

- 分别对 user_wav 和 ai_wav 调 ASR 获取词级时间戳
- 将每路 ASR chunks 合并为语音段（相邻间隙 < `SEG_MERGE_GAP_S`=0.7s 合并）
- 逐轮匹配：对每个用户段 U_i，在 AI 段列表中找其结束后首个未被消费的段 A_j
- 回复时延 = A_j.start - U_i.end

```
SEG_MERGE_GAP_S = 0.7  # 词合并为段的间隙阈值（秒）
```

输出：每轮 `{round_index, user_segment, ai_segment, response_latency_ms, inter_round_gap_s}` + 聚合统计（avg/min/max/n_matched/n_missed）。

##### 6. high_freq_llm_judge —— 高频轮换 LLM 裁判 [high_freq_llm_judge.py](turn_taking/high_freq_llm_judge.py)

以**模型回复音频 ai_wav** 为主输入（裁判模型直接听回复，不过小 ASR），结合 `rounds` 文本上下文（用户提问/预期答案），逐轮判断模型回复是否符合预期，返回 pass/fail + reason。

场景类型：飞花令 / 成语接龙 / 快问快答 / 自定义。

- 音频用 `input_audio` 格式（base64），视频用 `image_url` 格式
- 支持 Qwen omni 等模型的 stream 模式
- 复用 `config.LLM_JUDGE`（api_base_url / api_key / default_model / dimension_models）
- 返回 `{per_round: [{round, pass, reason}], overall_pass_rate, summary, ...}`

##### 7. reply_quality —— 单轮回复质量 LLM 评分 [reply_quality.py](turn_taking/reply_quality.py)

单轮模型回复质量：LLM 对模型回复音频（ai_wav）进行 0-5 评分。复用共享 ASR（user_chunks / ai_chunks），结合 played_audios 上下文，输出 `{score, reason, ...}`。

### turn_eval —— 逐轮三分类（独立主维度）

从 turn_taking 拆出的新主维度 [strategy.py](turn_eval/strategy.py)：

1. 轮次切分 + 逐轮三分类（误解管 / 接管 / 未接管），LLM 语义确认
2. 仅对「接管」轮计算接管时延
3. 仅对「接管」轮评分回复质量

多轮合并模式：以末轮（rounds[-1]）的 user_wav + ai_wav 为评估对象，合并所有轮次 played_audios 一次性对齐 + ASR + 切轮 + 三分类，每条 turn 通过对齐段归属到其真实轮次，并按轮投影原生 `per_round[]`（零额外 ASR/LLM）。

输出：`turn_classification{summary, normal_takeover_count, no_takeover_count, false_takeover_count, total_turns, turns[], takeover_rate, no_takeover_rate, false_takeover_rate}` + 兼容旧字段 `tor` / `false_takeover` / `takeover_latency` / `reply_quality` + `interaction_text` + `per_round[]`。

### interruptibility —— 打断指标（v2）

##### 8. interruption_metrics —— 打断指标 [strategy.py](interruptibility/strategy.py)

用户打断正在说话的小艺时，衡量"停得下、恢复得来、答得对题"。统一计算器一次出全部字段：本地时序 + **进程内直调逐轮 LLM 裁判**（`env_judge/interruption_judge.py` 的 `judge_interruption_rounds`，整例一次调用）。

- 用例类型 `case_type`（轮次标记本地推导，7 类）：`single` / `single_stop` / `multi` / `stop_resume_single` / `stop_resume_multi` / `topic_resume_single` / `topic_resume_multi`
- 行为五分类（LLM 逐轮判 → 本地确定性映射成败）：回复→成功；恢复/无关/静默→失败；询问→询问；解析失败→unknown（不入数量、时延记 -1）。**停止指令轮例外**：直接静默或"好的"等确认语后静默=遵从停止 → 按「回复」成功计
- 数量字段：`success_count` / `failure_count` / `inquiry_count` + 各行为计数；分母＝非 dangling 实际打断轮（恢复轮不入）
- 时延字段（毫秒；行为失败/unknown 轮 list 记 -1，avg/min/max 排除 -1、全 -1 → None）：响应时延（用户开始打断 → 模型当前段停口）、回复时延（用户说完 → 模型重新开口）、LLM 语义打断点精修（`refine_timing_with_interrupt_point`，`latency_source=llm_interrupt_point` 标记）、恢复首轮内容时延
- 评分/遵从：`reply_content_score`、`resume_content_score`（0-5，LLM）；`stop_compliance_rate`（仅停止指令类用例计算）
- LLM 降级：api_key 缺失/调用失败 → 数量与评分 None、message 标"行为判定降级"，时延走本地代理
- `per_round[]` 逐轮投影（`build_per_round` 零成本投影，TaskService 检测到原生 per_round 即跳过默认逐轮切片重跑）
- 旧字段（`interruption_success_rate` / `avg_stop_latency_s` 等，`_s` 后缀实存毫秒）保留为诊断输出

> 时长指标（stop_latency/recovery_latency/overlap/silence_gap 及均值）输出为**毫秒**，
> 字段名保留 `_s` 历史后缀以兼容既有维度 field_path，但值为毫秒；
> 段边界（user_segment 等）与 ASR 词时间戳仍为秒。

### rejection_scene_awareness —— 拒识与场景感知

##### 9. non_interactive_latency —— 非交互意图时延 [non_interactive_latency.py](rejection_scene_awareness/non_interactive_latency.py)

用户问完后模型开始回复，在回复期间用户又说了话（user_asr 第 2 段），计算：

- `stop_latency_s`：用户开始讲话 → 模型停止回复
- `recovery_latency_s`：用户讲完 → 模型开始回复

```
SEG_MERGE_GAP_S = 0.7   # 句内最大停顿适配
```

##### 10. noise_latency —— 噪声打断时延 [noise_latency.py](rejection_scene_awareness/noise_latency.py)

与 `non_interactive_latency` 对称，把"用户说话"替换为"噪声播放"。

- 噪声 `[start_ms, end_ms]` 为绝对世界毫秒
- 用 `pcm_first_ms` 换算到模型音频相对秒：`n_s = (start_ms - pcm_first_ms) / 1000`
- 复用 `non_interactive_latency` 同套段提取逻辑，补充绝对毫秒输出
- `pcm_first_ms` 缺失时用 `start_ms - 1000` 作为基准

### env_judge —— 环境音/打断能力 LLM 裁判

环境理解与打断/拒识裁判，共享 `shared/llm_client.py` / `shared/constants.py`。

**设计思路**：以**模型回复音频 ai_wav** 为主输入（裁判模型直接听回复，不过小 ASR，避免语义意图被糊掉），用户侧 ASR 转写作为文本时间线上下文。

##### 11. env_judge —— 环境理解裁判 [env_judge.py](env_judge/env_judge.py)

判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延。

- `env_type` 区分场景：`false/0` → non_semantic（噪声，判断声音类型识别）；`true/1` → semantic（含语义内容，判断内容理解）
- 输入：`user_wav`（含环境声+用户询问）、`ai_wav`（模型回复）、`played_audios`（本轮被播放音频）、`correctAnswer`
- 输出：`understand_correct`（bool）、`response_latency_ms`、`score`（1-5）、`reason`

##### 12. rejection_judge —— 拒识场景 LLM 裁判 [rejection_judge.py](env_judge/rejection_judge.py)

评估模型在拒识场景下的行为。裁判 LLM 直接听取 ai_wav + user_wav 音频，判断模型行为类别，再由代码根据 timing + behavior 计算 rate 评级。

- 场景定义：非目标人拒识 / 目标人非交互意图 / 环境噪声 / 用户BC（短反馈词）
- 行为类别（按 timing 分两套）：回应 / 恢复 / 不确定询问 / 无关回复 / 静默
- 输出：`evaluations` + `behavior_*`（0/1）+ `rate`（拒识成功/拒识询问/拒识失败）+ `rate_*`（0/1）+ `rate_*_count`（分组统计）
- 多轮聚合：0/1 字段求和得数量（`n_` 前缀），再除以拒识轮次得占比；`per_round[]` 跳过非拒识轮（`is_reject=false`）

##### 13. interruption_judge —— 打断场景 LLM 裁判 [interruption_judge.py](env_judge/interruption_judge.py)

打断场景 LLM 裁判：行为分类 / 内容评分（连贯性/相关性/适应性）/ 停止指令遵从。**v2 起不再作为独立 task_type 注册**，由 `interruption_metrics` 进程内直调 `judge_interruption_rounds` 整例一次调用复用；`interruption_metrics` 不再单独调 LLM。

- 行为四分类：回应 / 恢复 / 不确定询问 / 未知
- 场景：插话打断 / 停止指令 / 恢复原话题
- LLM 语义打断点精修：裁判 prompt 附本轮**词级时间线**，输出打断点 `interrupt_index`，`refine_timing_with_interrupt_point` 据词级时间戳重算响应/回复时延

## 调用关系

```
TaskService.CALCULATORS（注册表）
  ├── 'xiaoyi_metrics'        → XiaoyiMetricsCalculator → 全域编排（共享 ASR + 遍历子维度）
  ├── 'turn_taking'           → TurnTakingCalculator → 域内遍历子维度各自 calculate
  ├── 'tor'                   → TorCalculator → compute_tor
  ├── 'false_takeover'        → FalseTakeoverCalculator → compute_false_takeover + LLM 补充
  ├── 'takeover_latency'      → TakeoverLatencyCalculator → compute_takeover_latency_from_raw
  ├── 'high_freq_turn_taking' → HighFreqTurnTakingCalculator → compute_high_freq_turn_taking
  ├── 'high_freq_llm_judge'   → HighFreqLlmJudgeCalculator → evaluate_high_freq_llm
  ├── 'reply_quality'         → ReplyQualityCalculator → evaluate_reply_quality
  ├── 'turn_eval'             → TurnEvalCalculator → turn_evaluation.evaluate_all_turns
  ├── 'interruption_metrics'  → InterruptionMetricsCalculator → calculate_interruption_metrics
  │                                 └─ 进程内直调 interruption_judge.judge_interruption_rounds（v2）
  ├── 'non_interactive_latency'  → NonInteractiveLatencyCalculator → compute_non_interactive_latency
  ├── 'noise_latency'         → NoiseLatencyCalculator → compute_noise_latency
  ├── 'env_judge'             → EnvJudgeCalculator → evaluate_env_judge
  └── 'reject_judge'          → RejectionJudgeCalculator → evaluate_rejection_judge
```

`turn_taking` 主维度管理的子维度列表（按计算顺序）：

```
_SUB_DIMENSIONS = {
    'tor': 'tor',
    'false_takeover': 'false_takeover',
    'takeover_latency': 'takeover_latency',
    'client_out_latency': 'client_out_latency',
    'reply_quality': 'reply_quality',
    'high_freq_turn_taking': 'high_freq_turn_taking',
    'high_freq_llm_judge': 'high_freq_llm_judge',
}
```

`xiaoyi_metrics` 全域编排管理的子维度列表：

```
_SUB_DIMENSIONS = {
    'tor': 'tor',
    'false_takeover': 'false_takeover',
    'takeover_latency': 'takeover_latency',
    'client_out_latency': 'client_out_latency',
    'reply_quality': 'reply_quality',
    'interruption': 'interruption_metrics',
    'non_interactive_latency': 'non_interactive_latency',
    'high_freq_turn_taking': 'high_freq_turn_taking',
    'high_freq_llm_judge': 'high_freq_llm_judge',
    'turn_eval': 'turn_eval',
}
```

可通过 `task_params['sub_tasks']` 指定只计算部分子维度，例如 `sub_tasks: ['tor', 'takeover_latency']`。

统一入口内部 ASR 调用走 `app.utils.asr_adapter`（`call_modelscope_asr_word`），LLM 配置走 `config.LLM_JUDGE`（`shared/llm_client.get_llm_config`）。

## 关键设计

- **策略模式 + 注册表**：每个 task_type 一个 Calculator 策略类，实现 `validate → prepare_params → calculate` 模板方法，由 `calculators/__init__.py` 自动注册。新增指标只需新建 strategy.py + 注册一行。
- **一次 ASR，多维共享**：两级编排器（全域 / 域内）内部对 user_wav / ai_wav 各调一次 ASR，结果注入各子维度的 `_shared_asr`，避免重复调用远程服务。
- **双路时间轴对齐**：user_wav 与 ai_wav 同源录制，共享时间轴，可直接相减得时延；played_audios FFT 互相关进一步精修用户段。
- **单轮/多轮统一**：所有 Calculator 通过 `round_number` 区分单轮/多轮，多轮时逐轮计算后聚合（数值字段取平均，非数值取最后一轮）。
- **误接管后处理**：检测到误接管（`false_takeover.tor=1`）时，`tor` 和 `takeover_latency` 置 null（不适用）。
- **LLM 单入口 + 审计**：所有 LLM 调用汇聚 `shared/llm_client.call_llm`，每次写 JSONL 审计日志（`shared/llm_call_logger.py`，剥离 base64，永不轮转）。
- **渐进降级**：无双路音频时跳过相关指标，返回空结构不阻断主指标；LLM 缺失/失败时降级（数量/评分 None、时延本地代理），message 标注降级原因。
- **ASR 结果归一化**：纯标点 chunk 的时间戳视为 ASR 标点模型伪造，予以剔除（`is_punct_or_empty`）。
- **音频对齐**：`shared/audio_alignment.py` 用 FFT 互相关把 played_audios（干净音源）对齐到 user_wav（劣化）生成干净版音频，供接管时延 / turn_eval 轮次归属 / env 定位使用。
