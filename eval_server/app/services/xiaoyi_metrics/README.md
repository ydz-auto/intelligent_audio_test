# xiaoyi_metrics

小艺（语音大模型）评估指标包。围绕"话轮接管 / 打断 / 噪声 / 环境理解"等语音对话能力，提供从 ASR 时间戳到语义打分的全链路计算。

## 目录结构

```
xiaoyi_metrics/
├── __init__.py                  # 包说明（指标已迁移至子包）
├── README.md                    # 本文档
├── llm_judge/                   # LLM 语义打分子包
│   └── llm_judge_calculator.py  #   通用 LLM Judge（准确率/流畅度/相关性）
├── env_judge/                   # 环境音/打断能力录屏 LLM 裁判子包
│   ├── __init__.py
│   └── env_judge.py             #   录屏文件 LLM 裁判（env_judge / interruption_judge）
└── turn_taking/                 # 话轮接管与打断指标子包（统一 ASR 入口）
    ├── __init__.py              #   统一入口：calculate_xiaoyi_metrics 等
    ├── tor.py                   #   接话率（Turn-Over Rate）
    ├── false_takeover.py        #   误接管率（用户停顿期间是否抢话）
    ├── takeover_latency.py      #   接管时延（AI 首字 - 用户末字）
    ├── input_asr.py             #   输入识别准确率（query vs question 文本匹配）
    ├── interruption.py           #   打断指标（停得下 / 恢复得来）
    ├── non_interactive_latency.py # 非交互意图时延（模型回复期间用户说话）
    ├── interruption_llm.py      #   打断 LLM 评估（回复连贯性/相关性/适应性）
    ├── noise_latency.py         #   噪声打断时延（噪声播放期间模型响应）
    └── _show_segments.py        #   调试脚本：可视化 ASR 分段
```

## 子包说明

### turn_taking —— 话轮接管与打断指标

所有时序类指标的统一入口，位于 [turn_taking/__init__.py](turn_taking/__init__.py)。

#### 统一入口

| 函数 | 用途 | 对应 task_type |
|------|------|----------------|
| `calculate_xiaoyi_metrics(task_params)` | 调一次 ASR，六维度共享结果（tor / false_takeover / takeover_latency / input_asr / interruption / non_interactive_latency） | `turn_taking` / `xiaoyi_metrics` |
| `calculate_takeover_metrics(task_params)` | 只算话轮接管三项（tor / false_takeover / takeover_latency），不执行主录音 ASR | `takeover` |
| `calculate_interruption_metrics(task_params)` | 打断指标独立入口，由调用方直接传两路已对齐 ASR 结果（不内部调 ASR） | `interruption_metrics` |
| `print_objective_summary(results_list)` | 跨多用例汇总 tor=1 比例 / 平均接管时延 / false_takeover=0 比例 | — |

#### 核心概念：双路 ASR

tor / false_takeover / takeover_latency 共用**双路 ASR**方案：

- **user_wav**（`cap_client_process_out.wav`）：用户说话通道
- **ai_wav**（`cap_client_ec_out.wav`）：AI 回复通道

两路音频同时开始录制，共享同一时间轴（0 点为录音起点），因此可直接用各路 ASR 时间戳相减得到时延。统一入口在 `__init__.py` 内部对两路 wav 各调一次 ASR，将 `chunks` 传给各子指标，避免重复调用。

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

##### 5. interruption —— 打断指标 [interruption.py](turn_taking/interruption.py)

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

##### 6. non_interactive_latency —— 非交互意图时延 [non_interactive_latency.py](turn_taking/non_interactive_latency.py)

用户问完后模型开始回复，在回复期间用户又说了话（user_asr 第 2 段），计算：

- `stop_latency_s`：用户开始讲话 → 模型停止回复
- `recovery_latency_s`：用户讲完 → 模型开始回复

```
SEG_MERGE_GAP_S = 0.7   # 句内最大停顿适配
```

##### 7. interruption_llm —— 打断 LLM 评估 [interruption_llm.py](turn_taking/interruption_llm.py)

打断指标的**可选**大模型语义评估。仅在 `enable_llm_eval=True` 且配置 `LLM_JUDGE_API_KEY` 时触发。

三类评估：
1. **打断后回复打分**：每轮按 连贯性/相关性/适应性 打 1-5 分
2. **回到原话题行为判断**：分类为 回应/恢复/询问/无关恢复/沉默
3. **回到原话题回复打分**：同三维打分

复用 `config.LLM_JUDGE`（api_base_url / api_key / timeout）。单轮失败不阻断其他轮。

##### 8. noise_latency —— 噪声打断时延 [noise_latency.py](turn_taking/noise_latency.py)

与 `non_interactive_latency` 对称，把"用户说话"替换为"噪声播放"。

- 噪声 `[start_ms, end_ms]` 为绝对世界毫秒
- 用 `pcm_first_ms` 换算到模型音频相对秒：`n_s = (start_ms - pcm_first_ms) / 1000`
- 复用 `non_interactive_latency` 同套段提取逻辑，补充绝对毫秒输出

##### 9. env_judge —— 环境音/打断能力录屏裁判 [env_judge/env_judge.py](env_judge/env_judge.py)

传入录屏/音频文件，由裁判 LLM 对语音大模型行为评判。

支持两类 task_type：
- **env_judge**（拒识与环境理解）：旁人交谈静默 / 环境噪声 / 反馈词 / 生理声 / 环境事件回溯
- **interruption_judge**（打断能力）：插话打断与重新响应 / 停止指令响应 / 多轮打断后恢复原话题

行为五分类：回应 / 恢复 / 询问 / 无关回复 / 沉默。音频用 `input_audio` 格式（base64），视频用 `image_url` 格式。支持 Qwen omni 等模型的 stream 模式。

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
task_service.py
  ├── task_type='turn_taking'/'xiaoyi_metrics' → calculate_xiaoyi_metrics
  ├── task_type='takeover'                    → calculate_takeover_metrics
  ├── task_type='interruption_metrics'        → calculate_interruption_metrics
  ├── task_type='llm_judge'                   → evaluate_with_llm
  └── 汇总打印                                → print_objective_summary
```

统一入口内部 ASR 调用走 `app.utils.asr_adapator`（`call_modelscope_asr` / `call_modelscope_asr_word`），LLM 配置走 `app.config.config.LLM_JUDGE`。

## 关键设计

- **一次 ASR，多维共享**：`calculate_xiaoyi_metrics` 内部对 user_wav / ai_wav 各调一次 ASR，结果传给所有子指标，避免重复调用远程服务。
- **双路时间轴对齐**：user_wav 与 ai_wav 同源录制，共享时间轴，可直接相减得时延。
- **渐进降级**：无双路音频时跳过打断指标，返回空结构不阻断主指标；legacy 逻辑回退兼容旧入参。
- **ASR 结果归一化**：`_to_chunks` 接受 chunks 列表 / `{text, chunks}` / 直接列表；纯标点 chunk 的时间戳视为 ASR 标点模型伪造，予以剔除。
