# eval_server 架构文档

## 1. 概述

eval_server 是音频评估维度计算服务，接收主服务（Intelligent-Audio-TEST）提交的评估任务，计算 WER/SER/DER/LLM Judge/小艺指标等维度，返回评估结果。

## 2. 项目结构

```
eval_server/
├── app/
│   ├── app.py                  # 应用创建和初始化
│   ├── config.py               # 配置加载（config.yaml 默认值 + .env 覆盖）
│   ├── controllers/
│   │   ├── api.py              # 任务管理 API（create_task / create_task_upload / get_status / get_final_result / delete_task / cancel_task / endpoints / status）
│   │   └── health.py           # 健康检查 API
│   ├── database/
│   │   ├── tasks/              # 任务结果 JSON 存储（按日期分目录）
│   │   ├── schema.sql          # 数据库表结构
│   │   ├── modify_schema.sql   # 增量修改
│   │   └── endpoints.json      # 远程端点配置
│   ├── models/
│   │   └── task.py             # 任务数据模型
│   ├── services/
│   │   ├── calculators/        # 计算器包（策略模式 + 注册表）
│   │   │   ├── __init__.py     #   自动注册全部 calculator
│   │   │   ├── base.py         #   BaseCalculator 基类（模板方法 + 单轮/多轮公共方法）
│   │   │   ├── wer/            #   WER 系列域
│   │   │   │   ├── strategies.py       #     wer/ser/cpwer/tcpwer/stm_wer 策略类
│   │   │   │   └── wer_calculator.py  #     WER/SER/CPWER/TCPWER/STM_WER 实现函数
│   │   │   ├── der/            #   DER 域
│   │   │   │   ├── strategy.py         #     der 策略类
│   │   │   │   └── der_calculator.py   #     DER 实现函数
│   │   │   └── xiaoyi_metrics/ #   小艺指标域（含 llm_judge）
│   │   │       ├── __init__.py         #     XiaoyiMetricsCalculator 全域编排器
│   │   │       ├── doc/                #     指标文档（README / API / interruption_io / llm_call_audit_log 等）
│   │   │       ├── shared/             #     共享工具
│   │   │       │   ├── asr_utils.py          #       ASR chunks 工具（pause 区间 / 标点过滤 / 段合并）
│   │   │       │   ├── audio_alignment.py    #       played_audios FFT 互相关对齐（生成干净版音频）
│   │   │       │   ├── constants.py          #       共享常量（LLM/ASR/时序阈值集中管理）
│   │   │       │   ├── llm_client.py         #       LLM 调用统一入口 call_llm（含审计日志）
│   │   │       │   └── llm_call_logger.py    #       LLM 审计 JSONL 写入
│   │   │       ├── turn_taking/              #     话轮接管域（域内编排 + 子维度）
│   │   │       │   ├── __init__.py          #       _get_asr_chunks：ASR 词级时间戳唯一出口
│   │   │       │   ├── strategy.py          #       TurnTakingCalculator（域内编排）+ 6 个子维度策略
│   │   │       │   ├── tor.py               #       接话率
│   │   │       │   ├── false_takeover.py    #       误接管率（含 LLM 补充判断）
│   │   │       │   ├── takeover_latency.py  #       接管时延
│   │   │       │   ├── input_asr.py         #       输入识别准确率
│   │   │       │   ├── high_freq_turn_taking.py  #   高频轮换每轮回复时延
│   │   │       │   ├── high_freq_llm_judge.py    #   高频轮换 LLM 裁判
│   │   │       │   └── reply_quality.py         #   单轮回复质量 LLM 评分
│   │   │       ├── turn_eval/                  #     逐轮三分类域
│   │   │       │   ├── strategy.py             #       TurnEvalCalculator
│   │   │       │   └── turn_evaluation.py      #       轮次切分 + 三分类（误解管/接管/未接管）+ 接管时延 + 回复质量
│   │   │       ├── interruptibility/            #     打断指标 v2
│   │   │       │   ├── strategy.py              #       InterruptionMetricsCalculator（进程内直调 LLM 裁判）
│   │   │       │   ├── interruption.py          #       本地时序（停得下 / 恢复得来；FFT 精修用户段）
│   │   │       │   └── round_metrics.py         #       轮次锚定 + 用例类型推导 + spec 字段派生（纯函数）
│   │   │       ├── rejection_scene_awareness/  #     拒识与场景感知
│   │   │       │   ├── strategy.py              #       NonInteractiveLatency + NoiseLatency 策略类
│   │   │       │   ├── non_interactive_latency.py
│   │   │       │   └── noise_latency.py
│   │   │       ├── env_judge/                  #     环境音/打断能力裁判
│   │   │       │   ├── strategy.py              #       EnvJudgeCalculator + RejectionJudgeCalculator
│   │   │       │   ├── env_judge.py             #       环境理解裁判（understand_correct + 时延 + 评分）
│   │   │       │   ├── env_response_latency.py  #       环境声回复时延（FFT 定位 + 模型首字）
│   │   │       │   ├── interruption_judge.py    #       打断场景 LLM 裁判（v2 被 interruption_metrics 进程内直调）
│   │   │       │   └── rejection_judge.py       #       拒识场景 LLM 裁判（行为分类 + rate 评级）
│   │   │       └── llm_judge/                  #     通用 LLM 语义打分
│   │   │           ├── strategy.py              #       LlmJudgeCalculator
│   │   │           └── llm_judge_calculator.py
│   │   ├── remote_service.py   # 远程端点调用
│   │   └── task_service.py     # 任务调度入口（注册表查找 + worker 线程 + 逐轮回填 + 事件化回调）
│   └── utils/
│       ├── asr_adapter.py      # ASR 适配层（HTTP 调用远程 asr_server.py）
│       ├── concurrency.py      # 维度并发控制
│       ├── decorators.py       # 装饰器
│       ├── log_rotation.py     # 日志轮转
│       ├── normalizer.py       # 文本正则化
│       ├── oss_client.py       # OSS/MinIO 客户端（可选，oss:// 路径下载）
│       ├── pause_json.py       # 停顿区间 JSON 生成（CLI 工具）
│       └── responses.py        # 响应格式化
├── app.py                      # 主应用入口（waitress 启动）
├── start_multiple_servers.py   # 多实例启动
├── config.yaml                 # 结构配置（端口/并发/LLM 默认模型/品牌识别规则）
├── .env.example                # 环境变量示例（密钥与部署级覆盖）
├── scripts/                    # 脚本（如 summarize_tasks.py）
├── doc/                        # 文档目录
│   ├── ARCHITECTURE.md         # 本文件
│   ├── API_DOC.md              # API 接口文档
│   └── README.md               # 项目说明
├── tests/                      # 测试文件
└── requirements.txt
```

## 3. 支持的任务类型

| task_type | 说明 | 策略类 | 实现位置 |
|-----------|------|--------|---------|
| wer | 词错误率 | WerCalculator | wer/wer_calculator.py |
| ser | 句错误率 | SerCalculator | wer/wer_calculator.py |
| cpwer | 连接词错误率 | CpwerCalculator | wer/wer_calculator.py |
| tcpwer | 时间约束词错误率 | TcpwerCalculator | wer/wer_calculator.py |
| stm_wer | 基于 STM 的 WER | StmWerCalculator | wer/wer_calculator.py |
| der | 说话人分离错误率 | DerCalculator | der/der_calculator.py |
| xiaoyi_metrics | 小艺全域编排（统一共享 ASR + 跨域聚合） | XiaoyiMetricsCalculator | xiaoyi_metrics/__init__.py |
| turn_taking | 话轮接管主维度（域内编排） | TurnTakingCalculator | turn_taking/strategy.py |
| tor | 接话率 | TorCalculator | turn_taking/tor.py |
| false_takeover | 误接管率 | FalseTakeoverCalculator | turn_taking/false_takeover.py |
| takeover_latency | 接管时延 | TakeoverLatencyCalculator | turn_taking/takeover_latency.py |
| high_freq_turn_taking | 高频轮换每轮回复时延 | HighFreqTurnTakingCalculator | turn_taking/high_freq_turn_taking.py |
| high_freq_llm_judge | 高频轮换 LLM 裁判 | HighFreqLlmJudgeCalculator | turn_taking/high_freq_llm_judge.py |
| reply_quality | 单轮回复质量 LLM 评分 | ReplyQualityCalculator | turn_taking/reply_quality.py |
| turn_eval | 逐轮三分类（误解管/接管/未接管）+ 接管时延 + 回复质量 | TurnEvalCalculator | turn_eval/ |
| interruption_metrics | 打断指标 v2 | InterruptionMetricsCalculator | interruptibility/ |
| non_interactive_latency | 非交互意图时延 | NonInteractiveLatencyCalculator | rejection_scene_awareness/ |
| noise_latency | 噪声打断时延 | NoiseLatencyCalculator | rejection_scene_awareness/ |
| env_judge | 环境理解裁判 | EnvJudgeCalculator | env_judge/ |
| reject_judge | 拒识裁判（行为分类 + rate 评级） | RejectionJudgeCalculator | env_judge/rejection_judge.py |
| llm_judge | LLM 语义评分 | LlmJudgeCalculator | llm_judge/ |

## 4. 核心架构：策略模式 + 注册表

### 4.1 设计模式

采用 **策略模式 + 注册表** 组合，辅以 **模板方法** 处理参数提取：

- **策略模式**：每种 task_type 封装成独立的 Calculator 类，实现同一接口（`BaseCalculator`）
- **注册表**：`TaskService.CALCULATORS` dict，`calculators/__init__.py` import 时自动注册全部策略类
- **模板方法**：`BaseCalculator.run()` 调 `prepare_params → calculate`，子类可覆写 `prepare_params`
- **单轮/多轮统一**：`round_number` 有值（0/1/2...）→ 单轮评估取 `rounds[round_number]`；缺省 → 多轮整体评估（数值字段聚合）。公共方法（`_is_multi_round` / `_get_target_round_index` / `_get_round_safe` / `_get_audio_from_round` / `_iter_rounds` / `_aggregate_results`）由 `BaseCalculator` 统一提供
- **逐轮回填**：`supports_per_round=True` 的 Calculator 在整体评估模式下自动产出 `per_round[]`；Calculator 若已返回**原生 per_round[]**（turn_eval / interruption_metrics 整体合并评估一次产出），`TaskService` 直接复用并跳过默认逐轮切片重跑（省 N 次 ASR/LLM）

### 4.2 BaseCalculator 基类

```python
class BaseCalculator:
    task_type: str = ''
    supports_per_round = False

    def run(self, task_params):          # 模板方法
        params = self.prepare_params(task_params)
        return self.calculate(params)

    def validate(self, task_params):     # 参数校验，子类可覆写
        return True, None

    def prepare_params(self, task_params):  # 参数提取，子类可覆写
        return TaskService._prepare_params(task_params, self.task_type)

    def calculate(self, params):        # 子类必须实现
        raise NotImplementedError
```

### 4.3 调用流程

```
api.py _validate_and_dispatch_task()
    │
    │  1. calculator = TaskService.CALCULATORS.get(task_type)
    │  2. calculator.validate(task_params)        → 拦截参数缺失
    │  3. 并发位检查（全局 + 维度，满则入队由后台 worker 消费）
    │  4. 提交到线程池 → calculate_in_process()
    │
    ▼
task_service.py calculate()
    │  calculator = TaskService.CALCULATORS.get(task_type)
    │  result = calculator.run(task_params)
    │  整体评估 + supports_per_round → 附加 per_round[]
    │
    ▼
BaseCalculator.run()
    │  params = self.prepare_params(task_params)  → 提取/转换参数
    │  return self.calculate(params)              → 执行计算
    │
    ▼
具体 Calculator.calculate() → 调用实现函数 → 返回结果
```

小艺指标的两级编排（ASR 只调一次）：

```
XiaoyiMetricsCalculator.calculate        # 全域编排
  │  统一调一次双路 ASR（user_wav + ai_wav）+ 音频对齐 + pause 区间
  │  → 注入各子维度 params['_shared_asr']
  ▼
  ├─ TurnTakingCalculator（turn_taking 域内编排，域内子维度）
  │     tor / false_takeover / takeover_latency / reply_quality
  │     high_freq_turn_taking / high_freq_llm_judge
  ├─ TurnEvalCalculator（turn_eval 域：逐轮三分类 + 接管时延 + 回复质量）
  ├─ InterruptionMetricsCalculator（interruptibility 域：打断 v2）
  ├─ NonInteractiveLatencyCalculator（rejection_scene_awareness 域）
  └─ ...
```

### 4.4 新增任务类型

只需两步，无需改 `calculate()` 或 `api.py`：

1. 在对应域子包新建 `strategy.py`，实现 `validate` + `prepare_params` + `calculate`
2. 在 `calculators/__init__.py` 加一行注册

`api.py` 的 `SUPPORTED_TASK_TYPES` 与 `update_endpoint_concurrency` 均动态读取注册表，新注册的 Calculator 自动可用。

## 5. 通用流程

```
主服务 (Intelligent-Audio-TEST, port 5000)
    │
    │  方式一：JSON POST → /api/create_task（无文件）
    │  方式二：multipart/form-data POST → /api/create_task_upload（带文件）
    │
    │  文件上传时：
    │    - 文本文件 (.txt/.stm/.rttm/.json/.csv/.srt/.vtt)：读取内容为字符串
    │    - 二进制文件 (wav/mp4 等)：保存到上传目录，使用文件路径
    │    - rounds / played_audios 等 JSON 字符串中的 __MULTIPART__:field_name
    │      占位符递归还原为落盘路径
    │  可选 oss:// 路径：计算前由 oss_client 下载为本地文件
    │
    ▼
eval_server (port 8888)
    │
    │  保存上传文件 → 替换占位符 → TaskService.calculate(task_type, task_params)
    │
    ▼
计算模块 → 返回结果 → 存入 tasks/{date}/task_{id}.json
    │
    ▼
主服务轮询 GET /api/get_final_result/{task_id} 获取结果；
或创建任务时传 callback_url，eval_server 完成后主动 POST 回调（事件化，指数退避重试 3 次）
```

## 6. xiaoyi_metrics 指标

### 6.0 全域编排（XiaoyiMetricsCalculator）

小艺评估所有域的唯一编排入口，位于 [xiaoyi_metrics/__init__.py](../app/services/calculators/xiaoyi_metrics/__init__.py)：

- 统一调一次双路 ASR（user_wav / ai_wav）+ 音频对齐（played_audios FFT 生成干净版音频）+ pause 区间，结果注入 `_shared_asr` 供所有子维度复用
- 按 `sub_tasks` 遍历注册表子维度：tor / false_takeover / takeover_latency / client_out_latency / reply_quality / interruption / non_interactive_latency / high_freq_turn_taking / high_freq_llm_judge / turn_eval
- 后处理：检测到误接管（`false_takeover.tor=1`）时，`tor` 与 `takeover_latency` 置 null（不适用）

### 6.1 turn_taking —— 话轮接管

统一入口位于 [turn_taking/__init__.py](../app/services/calculators/xiaoyi_metrics/turn_taking/__init__.py)（`_get_asr_chunks` 为 ASR 词级时间戳唯一出口）。

#### 核心概念：双路 ASR

tor / false_takeover / takeover_latency 共用**双路 ASR**方案：

- **user_wav**（`cap_client_process_out.wav`）：用户说话通道
- **ai_wav**（`cap_client_ec_out.wav`）：AI 回复通道

两路音频同时开始录制，共享同一时间轴（0 点为录音起点），因此可直接用各路 ASR 时间戳相减得到时延。`TurnTakingCalculator.calculate()` 统一调一次双路 ASR，将 `chunks` 注入各子维度的 `_shared_asr`，避免重复调用。

#### 子指标

| 指标 | 说明 | 主函数 |
|------|------|--------|
| tor | 接话率：判定用户结束说话后模型是否正确开始回复 | `compute_tor(user_chunks, ai_chunks)` |
| false_takeover | 误接管率：判定用户停顿期间模型是否错误接管（抢话），时间戳 tor=0 时用 LLM 语义补充判断 | `compute_false_takeover` + `compute_false_takeover_llm` |
| takeover_latency | 接管时延：AI 首字时刻 - 用户末字时刻（双路 ASR 直接相减，legacy 回退） | `compute_takeover_latency_from_raw` |
| input_asr | 输入识别准确率：query vs question 文本匹配（相似度 ≥ 0.8） | `compute_input_asr_match` |
| high_freq_turn_taking | 高频轮换每轮回复时延（飞花令/成语接龙/快问快答） | `compute_high_freq_turn_taking` |
| high_freq_llm_judge | 高频轮换 LLM 裁判（模型回复音频 ai_wav 直接给多模态 LLM，逐轮 pass/fail） | `evaluate_high_freq_llm` |
| reply_quality | 单轮模型回复质量 LLM 评分（0-5） | `evaluate_reply_quality` |

### 6.2 turn_eval —— 逐轮三分类（新域）

从 turn_taking 拆出的独立主维度（[turn_eval/strategy.py](../app/services/calculators/xiaoyi_metrics/turn_eval/strategy.py)）：

1. 轮次切分 + 逐轮三分类（误解管 / 接管 / 未接管），LLM 语义确认
2. 仅对「接管」轮计算接管时延
3. 仅对「接管」轮评分回复质量

多轮合并模式：以末轮（rounds[-1]）的 user_wav + ai_wav 为评估对象，合并所有轮次 played_audios 一次性对齐 + ASR + 切轮 + 三分类，每条 turn 通过对齐段归属到其真实轮次，并按轮投影原生 `per_round[]`（零额外 ASR/LLM）。

输出结构：`turn_classification{summary, normal_takeover_count, no_takeover_count, false_takeover_count, total_turns, turns[], takeover_rate, no_takeover_rate, false_takeover_rate}` + 兼容旧字段 `tor` / `false_takeover` / `takeover_latency` / `reply_quality` + `interaction_text` + `per_round[]`。

### 6.3 interruption_metrics —— 打断指标（v2）

用户打断正在说话的小艺时，衡量"停得下、恢复得来、答得对题"。统一计算器一次出全部字段：本地时序 + **进程内直调逐轮 LLM 裁判**（`env_judge/interruption_judge.py` 的 `judge_interruption_rounds`，整例一次调用），不依赖平台跨维度回填。

- 输入：`rounds[]`（逐轮 `user_asr`/`model_asr`/`query`/`is_interruption`/`stop_intent`/`is_return_to_topic`/`played_audios`）+ 用例级 `interruption_rounds`/`dangling_interruption_rounds`；兼容单轮平铺 `user_asr`/`model_asr`（平台逐轮切片路径）
- 用例类型 `case_type`（轮次标记本地推导，7 类）：`single` / `single_stop` / `multi` / `stop_resume_single` / `stop_resume_multi` / `topic_resume_single` / `topic_resume_multi`
- 行为五分类（LLM 逐轮判 → 本地确定性映射成败）：回复→成功；恢复/无关/静默→失败；询问→询问；解析失败→unknown（不入数量、时延记 -1）。**停止指令轮例外**：直接静默或"好的"等确认语后静默=遵从停止 → 按「回复」成功计
- 数量字段：`success_count` / `failure_count` / `inquiry_count` + 各行为计数；分母＝非 dangling 实际打断轮（恢复轮不入）
- 时延字段（毫秒；行为失败/unknown 轮 list 记 -1，avg/min/max 排除 -1、全 -1 → None）：响应时延（用户开始打断 → 模型当前段停口）、回复时延（用户说完 → 模型重新开口）、LLM 语义打断点精修（`refine_timing_with_interrupt_point`，`latency_source=llm_interrupt_point` 标记）、恢复首轮内容时延
- 评分/遵从：`reply_content_score`、`resume_content_score`（0-5，LLM）；`stop_compliance_rate`（仅停止指令类用例计算）
- LLM 降级：api_key 缺失/调用失败 → 数量与评分 None、message 标"行为判定降级"，时延走本地代理
- `per_round[]` 逐轮投影（`build_per_round` 零成本投影，TaskService 检测到原生 per_round 即跳过默认逐轮切片重跑）
- 旧字段（`interruption_success_rate` / `avg_stop_latency_s` 等，`_s` 后缀实存毫秒）保留为诊断输出

### 6.4 non_interactive_latency —— 非交互意图时延

用户问完后模型开始回复，在回复期间用户又说了话（user_asr 第 2 段），计算：

- `stop_latency_s`：用户开始讲话 → 模型停止回复
- `recovery_latency_s`：用户讲完 → 模型开始回复

```
SEG_MERGE_GAP_S = 0.7   # 句内最大停顿适配
```

### 6.5 noise_latency —— 噪声打断时延

与 `non_interactive_latency` 对称，把"用户说话"替换为"噪声播放"。

- 噪声 `[start_ms, end_ms]` 为绝对世界毫秒
- 用 `pcm_first_ms` 换算到模型音频相对秒：`n_s = (start_ms - pcm_first_ms) / 1000`
- 复用 `non_interactive_latency` 同套段提取逻辑，补充绝对毫秒输出

### 6.6 env_judge —— 环境音/打断能力裁判

#### env_judge（环境理解）

传入双路音频 + played_audios + correctAnswer，判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延。

- `env_type` 区分场景：`false/0` → non_semantic（噪声，判断声音类型识别）；`true/1` → semantic（含语义内容，判断内容理解）
- 输出：`understand_correct`（bool）、`response_latency_ms`、`score`（1-5）、`reason`

#### reject_judge（拒识裁判）

评估模型在拒识场景（非意图交互内容出现时）下的行为表现。裁判 LLM 直接听取 ai_wav + user_wav 音频，判断模型行为类别（回应/恢复/不确定询问/无关回复/静默），再由代码根据 timing + behavior 计算 rate 评级（拒识成功/拒识询问/拒识失败）。

- 场景：非目标人拒识 / 目标人非交互意图 / 环境噪声 / 用户BC（短反馈词）
- 多轮聚合：0/1 字段求和得数量（`n_` 前缀），再除以拒识轮次得占比；`per_round[]` 跳过非拒识轮（`is_reject=false`）

#### interruption_judge（打断裁判，v2 进程内直调）

打断场景 LLM 裁判（行为分类 / 内容评分 / 停止指令遵从），由 `interruption_metrics` 进程内直调 `judge_interruption_rounds` 复用，不再作为独立 task_type 注册。

### 6.7 llm_judge —— 通用 LLM 语义打分

用大模型（默认 `config.LLM_JUDGE.default_model`，如 gemini-3.7-flash）对设备回答与参考答案做语义打分。

- 支持单轮 / 多轮（`rounds` 逐轮列出，逐轮评分后取平均）
- 支持多模态：音频文件编码为 base64 data URI 发送
- 默认评价维度：准确率 / 流畅度 / 相关性（可通过 `scoring_criteria` 自定义）
- 每次调用写 LLM 审计日志（`shared/llm_call_logger.py`）

### 6.8 shared —— 共享工具

- `asr_utils.py`：ASR chunks 工具（`compute_pause_intervals` / `is_punct_or_empty` / 段合并）
- `audio_alignment.py`：played_audios（干净音源）→ user_wav（劣化）FFT 互相关对齐，生成干净版音频（`generate_aligned_clean_audio`）
- `constants.py`：LLM/ASR/时序阈值/行为标签等魔法数字集中管理
- `llm_client.py`：`call_llm` 统一 LLM 入口（OpenAI 兼容 / 多模态 base64 / 流式 / 重试）+ `resolve_model` / `get_llm_config` / `build_interaction_text`
- `llm_call_logger.py`：每次 LLM 调用写 JSONL 审计日志（剥离 base64，永不轮转）

## 7. ASR 服务调用链

```
eval_server (port 8888)
    │
    │  asr_adapter.py
    │    call_modelscope_asr_word(wav_path)
    │       → HTTP POST → asr_server.py /asr (port 10095)
    │       → 上传 wav 文件
    │       → 返回 {text, chunks}
    │    parse_result(raw)
    │       → 透传，返回 asr_result 对象
    │
    ▼
asr_server (port 10095, 独立主机 100.70.20.135)
    │
    │  FastAPI + ModelScope Paraformer-large-vad-punc
    │  POST /asr        → 接收 wav → 推理 → 返回 {text, chunks}
    │  POST /asr_file   → 本机路径调用（CLI 测试用）
    │  GET  /health     → 健康检查
    │  GET  /           → 服务信息
```

## 8. 关键设计决策

1. **策略模式 + 注册表**：每种 task_type 一个 Calculator 策略类，实现 `validate → prepare_params → calculate` 模板方法，由 `calculators/__init__.py` 自动注册。新增指标只需新建 strategy.py + 注册一行，无需改 `calculate()` 或 `api.py`
2. **按域分子包**：策略类和实现函数放同一域子包，如 `wer/` 内含 `strategies.py` + `wer_calculator.py`；`xiaoyi_metrics/` 下按 turn_taking / turn_eval / interruptibility / rejection_scene_awareness / env_judge / llm_judge 分子包，公共逻辑收敛到 `shared/`
3. **ASR 只调一次**：两级编排器统一调双路 ASR，`_shared_asr` 注入所有子维度复用
4. **不读写中间 JSON 文件**：ASR 结果直接通过内存对象传递
5. **multipart 文件上传**：主服务上传 wav 文件到 eval_server，eval_server 再上传到 asr_server；`__MULTIPART__` 占位符递归还原
6. **CLI 与主流程分离**：子模块保留 `*_from_files` 函数供命令行独立测试，主流程用 `compute_*` / `*_from_raw` 函数
7. **并发满不拒绝**：全局并发位 + 维度并发位双重限制，满则创建 pending 任务由后台 worker 排队消费，`callback_url` 事件化回调通知结果
8. **LLM 统一入口 + 审计**：`shared/llm_client.py:call_llm` 单入口（含多模态、流式、重试），每次调用写 JSONL 审计日志（剥离 base64）
9. **OSS 双模式**：`oss://` 路径计算前自动下载；未配置 OSS 时原样返回，不影响 multipart/本地路径传参
10. **三机部署**：测试机（主服务+eval_server）→ ASR 主机（asr_server），网线直连

## 9. 配置

配置加载顺序：`config.yaml`（默认值）→ `.env`（密钥与部署级覆盖）→ `config.LLM_JUDGE` 等单例暴露。修改后需重启 eval_server 生效。

### eval_server .env（密钥与部署覆盖）

```
ASR_SERVER_URL=http://100.70.20.135:10095
ASR_TIMEOUT=120
LLM_JUDGE_API_KEY=<LLM中转站API Key>
LOG_DIR=D:\00_static\logs\eval_server      # 可选覆盖
STATIC_BASE_PATH=D:\00_static\static       # 可选覆盖
LLM_CALL_LOG_ENABLED=1                     # LLM 审计开关
OSS_ENDPOINT=...                           # 可选 OSS
```

### eval_server config.yaml（结构配置）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `port` | 8888 | 服务端口 |
| `local_max_concurrency` | 100 | 全局并发上限 |
| `concurrency_limits` | 各维度 100 | 维度并发上限（env_judge / reject_judge 传音频给 LLM，限 5） |
| `llm_text_max_concurrency` / `llm_audio_max_concurrency` | 100 / 5 | LLM 文本/音频调用并发池 |
| `llm_brand_keywords` | — | 模型品牌识别规则（模型名小写 substring 匹配） |
| `llm_judge` | api_base_url / default_model / dimension_models / max_tokens / temperature / timeout / prompt_template | LLM Judge 默认配置 |
| `static_base_path` | D:\00_static\static | 静态资源根目录 |

### asr_server 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| ASR_HOST | 0.0.0.0 | 监听地址 |
| ASR_PORT | 10095 | 监听端口 |
| ASR_MODELSCOPE_MODEL | iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch | ASR 模型 |
| ASR_VAD_MODEL | iic/speech_fsmn_vad_zh-cn-16k-common-pytorch | VAD 模型 |
| ASR_PUNC_MODEL | iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch | 标点模型 |

## 10. 网络部署

```
测试机 (100.70.20.136)                    ASR 主机 (100.70.20.135)
┌──────────────────────┐                  ┌──────────────────┐
│ 主服务 (port 5000)    │                  │ asr_server        │
│ eval_server (port 8888)│ ←── 网线直连 ──→ │ (port 10095)      │
│ Intelligent-Audio-TEST │                  │ ModelScope ASR    │
└──────────────────────┘                  └──────────────────┘
```

- 两台机配同网段静态 IP，默认网关留空
- ASR 主机关闭防火墙或放行 10095 端口
- ASR 服务监听 0.0.0.0:10095
