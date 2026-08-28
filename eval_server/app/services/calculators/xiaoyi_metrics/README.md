# xiaoyi_metrics

小艺（语音大模型）评估指标包。围绕"话轮接管 / 打断 / 噪声 / 环境理解 / 高频轮换"等语音对话能力，提供从 ASR 时间戳到语义打分的全链路计算。

## 目录结构

```
xiaoyi_metrics/
├── __init__.py
├── README.md                        # 本文档
├── turn_taking/                     # 话轮接管与打断指标子包（统一 ASR 入口）
│   ├── __init__.py                  #   统一入口：calculate_xiaoyi_metrics 等
│   ├── strategy.py                  #   TurnTakingCalculator + 6 个子维度 Calculator
│   ├── tor.py                       #   接话率（Turn-Over Rate）
│   ├── false_takeover.py            #   误接管率（用户停顿期间是否抢话）
│   ├── takeover_latency.py          #   接管时延（AI 首字 - 用户末字）
│   ├── input_asr.py                 #   输入识别准确率（query vs question 文本匹配）
│   ├── high_freq_turn_taking.py     #   高频轮换每轮回复时延（飞花令/成语接龙/快问快答）
│   ├── high_freq_llm_judge.py      #   高频轮换 LLM 裁判（模型回复音频 → 逐轮 pass/fail）
│   └── _show_segments.py            #   调试脚本：可视化 ASR 分段
├── interruptbility/                  # 打断指标实现子包
│   ├── __init__.py
│   ├── interruption.py              #   打断指标（停得下 / 恢复得来）
│   └── interruption_llm.py         #   打断 LLM 评估（回复连贯性/相关性/适应性）
├── rejection_scene_awareness/        # 拒识与场景感知子包
│   ├── __init__.py
│   ├── strategy.py                  #   NonInteractiveLatencyCalculator + NoiseLatencyCalculator 策略类
│   ├── non_interactive_latency.py   #   非交互意图时延（模型回复期间用户说话）
│   └── noise_latency.py             #   噪声打断时延（噪声播放期间模型响应）
├── env_judge/                       # 环境音/打断能力 LLM 裁判子包
│   ├── __init__.py
│   ├── _common.py                   #   共享工具：文件编码 / LLM 调用 / 时间线构建 / JSON 解析
│   ├── strategy.py                  #   RejectionJudgeCalculator + InterruptionJudgeCalculator 策略类
│   ├── rejection_judge.py           #   拒识场景 LLM 裁判（四分类：回应/恢复/不确定询问/未知）
│   ├── interruption_judge.py        #   打断场景 LLM 裁判（四分类：回应/恢复/不确定询问/未知）
│   └── env_judge.py                 #   [legacy] 全场景 LLM 裁判（五分类，保留回退）
└── llm_judge/                       # LLM 语义打分子包
    ├── strategy.py                  #   LlmJudgeCalculator 策略类
    └── llm_judge_calculator.py      #   通用 LLM Judge（准确率/流畅度/相关性）
```

## 架构说明

每个域子包自包含**策略类**（`strategy.py`）和**实现函数**，策略类继承 `BaseCalculator`，实现 `validate → prepare_params → calculate` 三步模板方法。由 `calculators/__init__.py` 自动注册到 `TaskService.CALCULATORS` 注册表。

所有 Calculator 均支持**单轮/多轮**模式：
- `round_number` 有值（0/1/2...）→ 单轮评估，取 `rounds[round_number]`
- `round_number` 不存在 → 多轮整体评估（逐轮计算后聚合，数值字段取平均）

```
calculators/__init__.py              # import 即自动注册全部 calculator
  ├── wer/strategies.py               #   WerCalculator 等 5 个策略类
  ├── der/strategy.py                #   DerCalculator
  └── xiaoyi_metrics/                #   本包
      ├── turn_taking/strategy.py     #     TurnTaking(主) + Tor + FalseTakeover +
      │                               #     TakeoverLatency + HighFreqTurnTaking + HighFreqLlmJudge +
      │                               #     InterruptionMetrics
      ├── rejection_scene_awareness/strategy.py  # NonInteractiveLatency + NoiseLatency
      ├── env_judge/strategy.py       #     RejectionJudge + InterruptionJudge
      └── llm_judge/strategy.py       #     LlmJudge
```

## 子包说明

### turn_taking —— 话轮接管与打断指标

所有时序类指标的统一入口，位于 [turn_taking/__init__.py](turn_taking/__init__.py)。

#### 统一入口

| 函数 | 用途 | 对应 task_type |
|------|------|----------------|
| `calculate_xiaoyi_metrics(task_params)` | 调一次 ASR，多维共享结果（tor / false_takeover / takeover_latency / interruption / non_interactive_latency / high_freq_turn_taking / high_freq_llm_judge） | `turn_taking` |
| `calculate_interruption_metrics(task_params)` | 打断指标独立入口，由调用方直接传两路已对齐 ASR 结果（不内部调 ASR） | `interruption_metrics` |
| `calculate_takeover_metrics(task_params)` | 只算 tor / false_takeover / takeover_latency 三项 | — |
| `calculate_high_freq_turn_taking_metrics(task_params)` | 高频轮换每轮回复时延独立入口 | `high_freq_turn_taking` |
| `calculate_high_freq_llm_judge(task_params)` | 高频轮换 LLM 裁判独立入口 | `high_freq_llm_judge` |

#### 核心概念：双路 ASR

tor / false_takeover / takeover_latency 共用**双路 ASR**方案：

- **user_wav**（`cap_client_process_out.wav`）：用户说话通道
- **ai_wav**（`cap_client_ec_out.wav`）：AI 回复通道

两路音频同时开始录制，共享同一时间轴（0 点为录音起点），因此可直接用各路 ASR 时间戳相减得到时延。统一入口在 `__init__.py` 内部对两路 wav 各调一次 ASR，将 `chunks` 传给各子指标，避免重复调用。

**策略类共享 ASR**：`TurnTakingCalculator.calculate()` 统一调一次双路 ASR（user_chunks / ai_chunks / ai_word_chunks / pause_intervals），注入各子维度的 `_shared_asr`，子维度优先使用已注入的 chunks，避免重复调用远程 ASR。

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

**LLM 补充判断**：时间戳 `tor=0` 时，调 `compute_false_takeover_llm` 做语义判断，若 LLM 判定 `false_takeover=1` 则修正 `tor=1`。

##### 3. takeover_latency —— 接管时延 [takeover_latency.py](turn_taking/takeover_latency.py)

```
takeover_latency_ms = ai_first_word_start_ms - user_last_word_end_ms
```

- 新逻辑：双路 ASR chunks 直接相减（开场白过滤：找 user 末词结束之后的首个 AI chunk）
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
- 复用 `config.LLM_JUDGE`（api_base_url / api_key / default_model）
- 返回 `{per_round: [{round, pass, reason}], overall_pass_rate, summary, ...}`

### interruptbility —— 打断指标实现

##### 7. interruption —— 打断指标 [interruption.py](interruptbility/interruption.py)

用户打断正在说话的小艺时，衡量"停得下、恢复得来"。对每个用户打断段 `u=[u_s, u_e]`：

| 指标 | 含义 |
|------|------|
| stop_latency | 用户开始打断 → 模型当前语音段结束（停下） |
| recovery_latency | 用户说完 → 模型重新开口（恢复段起点） |
| success | 容差内停下 且 之后恢复 |

模型是否"说穿"：语音段结尾比用户打断结尾晚 `YIELD_GRACE_S`（0.5s）以上 → 无视打断继续说。

```
SEG_MERGE_GAP_S = 0.3   # 词合并为段的间隙阈值
YIELD_GRACE_S   = 0.5   # 让出宽限
```

事件类型：`interruption`（完整打断）/ `recovery_only`（只算到恢复）/ `no_model_speech`（模型全程未说话）。

**success 全本地**：`interruption_success_rate` 始终由本地时序算出（让出且恢复 / 有效打断事件）。
`n_events=0` 时 success_rate=0.0，不再走 LLM 兜底（旧 `evaluate_interruption_success_llm` 已移除）。

##### 8. interruption_llm —— 打断 LLM 评估 [interruption_llm.py](interruptbility/interruption_llm.py)

打断指标的**可选**大模型语义评估。仅在 `enable_llm_eval=True` 且配置 `LLM_JUDGE_API_KEY` 时触发。
LLM 直接吃 `compute_interruption_metrics` 富集后的 `per_event`（用户与模型的**字词级 ASR**），
对每个 `event_type=='interruption'` 事件做：

1. **是否真的打断（语义复核）**：基于两侧字词级 ASR（词+时间戳）判断是否为真实打断，
   给出 `is_real_interruption` 布尔结论与简短原因 `interruption_reason`。
   **不回写覆盖**本地 `interruption_success_rate`——本地数值始终是唯一权威。
2. **AI 回复内容打分**：对模型恢复回复按 连贯性/相关性/适应性 打 0-5 分
   （对标 Full-Duplex-Bench GPT-4o Score）。

数值指标（时延/成功率/让出率/恢复率等）全部本地算，本模块不产出任何数值指标。
复用 `config.LLM_JUDGE`（api_base_url / api_key / timeout）。单事件失败不阻断其他事件。
旧 `rounds` 文本链路与"回到原话题"独立打分已移除（`llm_return_*` 字段保留为空以兼容既有维度）。

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

从原 `env_judge.py` 拆分为两个独立子维度，共享 [_common.py](env_judge/_common.py) 工具模块。

**设计思路**：以**模型回复音频 ai_wav** 为主输入（裁判模型直接听回复，不过小 ASR，避免语义意图被糊掉），用户侧 ASR 转写作为文本时间线上下文。

#### 共享工具 [_common.py](env_judge/_common.py)

- 文件编码：音频 → 纯 base64（`input_audio`），视频 → data URI（`image_url`）
- LLM API 调用：支持 omni stream / audio 模型 / 普通文本模型，含重试
- 时间线构建：`build_timeline_text()` 将用户 ASR chunks + 环境声事件窗拼为文本
- JSON 解析与 evaluations 归一化

#### 行为四分类

| 行为 | 含义 |
|------|------|
| 回应 | 模型对重叠内容进行了有意义的回应（回答/澄清/反应） |
| 恢复 | 模型忽略重叠，继续或完成重叠前的任务 |
| 不确定询问 | 模型表示不确定/没听清/缺少信息，未给出明确回答 |
| 未知 | 模型输出语义偏离或信息量低，包括完全没有语音输出 |

##### 11. rejection_judge —— 拒识场景 LLM 裁判 [rejection_judge.py](env_judge/rejection_judge.py)

评估模型在拒识场景下的行为。用户输入音频包含两部分：第一段为用户交互内容，第二段为拒识干扰内容。

场景定义：旁人交谈 / 环境噪声 / 反馈词 / 生理声 / 环境回溯。

输出：严格 JSON `{behavior, reason}` + 四个 0/1 字段（`behavior_respond` / `behavior_recover` / `behavior_uncertain` / `behavior_unknown`）。

##### 12. interruption_judge —— 打断场景 LLM 裁判 [interruption_judge.py](env_judge/interruption_judge.py)

评估模型在打断场景下的行为。用户输入音频包含两部分：第一段为用户交互内容，第二段为打断干扰内容。

场景定义：插话打断 / 停止指令 / 恢复原话题。

输出同 rejection_judge 格式。

##### [legacy] env_judge —— 全场景 LLM 裁判 [env_judge.py](env_judge/env_judge.py)

原全场景裁判（五分类：回应/恢复/询问/无关回复/沉默），保留为 legacy 回退。支持 `env_type` 参数自动推断场景集。

### llm_judge —— 通用 LLM 语义打分 [llm_judge/llm_judge_calculator.py](llm_judge/llm_judge_calculator.py)

用大模型（默认 `deepseek-r1`）对设备回答与参考答案做语义打分。

```python
evaluate_with_llm(
    answer, correct_answer, question, query,
    record_file='', rounds=None,
    model='deepseek-r1', prompt='', max_tokens=1024,
    temperature=0.7, scoring_criteria=None, **kwargs
)
```

- 支持单轮 / 多轮（`rounds` 逐轮列出）
- 支持多模态：音频文件编码为 base64 data URI 发送
- 默认评价维度：准确率 / 流畅度 / 相关性（可通过 `scoring_criteria` 自定义）
- 返回 `{llm_judge_score, reasoning, tokens_used, ...}`

## 调用关系

```
TaskService.CALCULATORS（注册表）
  ├── 'turn_taking'              → TurnTakingCalculator → 遍历子维度各自 calculate
  ├── 'tor'                      → TorCalculator → compute_tor
  ├── 'false_takeover'           → FalseTakeoverCalculator → compute_false_takeover + LLM 补充
  ├── 'takeover_latency'         → TakeoverLatencyCalculator → compute_takeover_latency_from_raw
  ├── 'high_freq_turn_taking'    → HighFreqTurnTakingCalculator → compute_high_freq_turn_taking
  ├── 'high_freq_llm_judge'      → HighFreqLlmJudgeCalculator → evaluate_high_freq_llm
  ├── 'interruption_metrics'     → InterruptionMetricsCalculator → calculate_interruption_metrics
  ├── 'non_interactive_latency'  → NonInteractiveLatencyCalculator → compute_non_interactive_latency
  ├── 'noise_latency'            → NoiseLatencyCalculator → compute_noise_latency
  ├── 'rejection_judge'          → RejectionJudgeCalculator → evaluate_rejection_judge
  ├── 'interruption_judge'      → InterruptionJudgeCalculator → evaluate_interruption_judge
  └── 'llm_judge'                → LlmJudgeCalculator → evaluate_with_llm
```

`turn_taking` 主维度管理的子维度列表（按计算顺序）：

```
_SUB_DIMENSIONS = {
    'tor': 'tor',
    'false_takeover': 'false_takeover',
    'takeover_latency': 'takeover_latency',
    'interruption': 'interruption_metrics',
    'non_interactive_latency': 'non_interactive_latency',
    'high_freq_turn_taking': 'high_freq_turn_taking',
    'high_freq_llm_judge': 'high_freq_llm_judge',
}
```

可通过 `task_params['sub_tasks']` 指定只计算部分子维度，例如 `sub_tasks: ['tor', 'takeover_latency']`。

统一入口内部 ASR 调用走 `app.utils.asr_adapator`（`call_modelscope_asr_word`），LLM 配置走 `app.config.config.LLM_JUDGE`。

## 关键设计

- **策略模式 + 注册表**：每个 task_type 一个 Calculator 策略类，实现 `validate → prepare_params → calculate` 模板方法，由 `calculators/__init__.py` 自动注册。新增指标只需新建 strategy.py + 注册一行。
- **一次 ASR，多维共享**：`TurnTakingCalculator.calculate()` 内部对 user_wav / ai_wav 各调一次 ASR，结果注入各子维度的 `_shared_asr`，避免重复调用远程服务。
- **双路时间轴对齐**：user_wav 与 ai_wav 同源录制，共享时间轴，可直接相减得时延。
- **单轮/多轮统一**：所有 Calculator 通过 `round_number` 区分单轮/多轮，多轮时逐轮计算后聚合（数值字段取平均，非数值取最后一轮）。
- **误接管后处理**：检测到误接管（`false_takeover.tor=1`）时，`tor` 和 `takeover_latency` 置 null（不适用）。
- **渐进降级**：无双路音频时跳过打断指标，返回空结构不阻断主指标；legacy 逻辑回退兼容旧入参。
- **ASR 结果归一化**：`_to_chunks` 接受 chunks 列表 / `{text, chunks}` / 直接列表；纯标点 chunk 的时间戳视为 ASR 标点模型伪造，予以剔除。
- **env_judge 共享工具**：`_common.py` 抽取文件编码、LLM 调用、时间线构建、JSON 解析等共享逻辑，`rejection_judge` 和 `interruption_judge` 复用。
- **LLM 兜底**：时序指标算不出结果时（如 `n_events=0`），用 LLM 按对话语义做兜底判定。
