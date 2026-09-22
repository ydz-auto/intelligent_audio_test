# eval_server 架构文档

## 1. 概述

eval_server 是音频评估维度计算服务，接收主服务（Intelligent-Audio-TEST）提交的评估任务，计算 WER/SER/DER/LLM Judge/小艺指标等维度，返回评估结果。

## 2. 项目结构

```
eval_server/
├── app/
│   ├── app.py                  # 应用创建和初始化
│   ├── config.py               # 配置信息
│   ├── controllers/
│   │   ├── api.py              # 任务管理 API（create_task / create_task_upload / get_status / get_final_result）
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
│   │   │   ├── base.py         #   BaseCalculator 基类（模板方法）
│   │   │   ├── wer/            #   WER 系列域
│   │   │   │   ├── strategies.py       #     wer/ser/cpwer/tcpwer/stm_wer 策略类
│   │   │   │   └── wer_calculator.py  #     WER/SER/CPWER/TCPWER/STM_WER 实现函数
│   │   │   ├── der/            #   DER 域
│   │   │   │   ├── strategy.py         #     der 策略类
│   │   │   │   └── der_calculator.py   #     DER 实现函数
│   │   │   └── xiaoyi_metrics/ #   小艺指标域（含 llm_judge）
│   │   │       ├── turn_taking/                # 话轮接管与打断指标
│   │   │       │   ├── strategy.py              #   TurnTaking + InterruptionMetrics 策略类
│   │   │       │   ├── tor.py                  #   接话率
│   │   │       │   ├── false_takeover.py       #   误接管率
│   │   │       │   ├── takeover_latency.py     #   接管时延
│   │   │       │   └── input_asr.py            #   输入识别准确率
│   │   │       ├── interruptibility/            # 打断指标 v2（本地时序 + 逐轮 LLM 五分类）
│   │   │       │   ├── strategy.py              #   统一计算器 InterruptionMetricsCalculator（进程内直调裁判）
│   │   │       │   ├── interruption.py          #   本地时序（停得下 / 恢复得来；played_audios FFT 精修用户段）
│   │   │       │   └── round_metrics.py         #   轮次锚定 + 用例类型推导 + spec 字段派生（纯函数）
│   │   │       ├── rejection_scene_awareness/  # 拒识与场景感知
│   │   │       │   ├── strategy.py              #   NonInteractiveLatency + NoiseLatency 策略类
│   │   │       │   ├── non_interactive_latency.py
│   │   │       │   └── noise_latency.py
│   │   │       ├── env_judge/                  # 环境音/打断能力录屏裁判
│   │   │       │   ├── strategy.py              #   EnvJudge 策略类
│   │   │       │   └── env_judge.py
│   │   │       └── llm_judge/                  # LLM 语义打分
│   │   │           ├── strategy.py              #   LlmJudge 策略类
│   │   │           └── llm_judge_calculator.py
│   │   ├── remote_service.py   # 远程端点调用
│   │   └── task_service.py     # 任务调度入口（注册表查找 + worker 线程）
│   └── utils/
│       ├── asr_adapter.py      # ASR 适配层（HTTP 调用远程 asr_server.py）
│       ├── concurrency.py      # 并发控制
│       ├── decorators.py       # 装饰器
│       ├── log_rotation.py     # 日志轮转
│       ├── normalizer.py       # 文本正则化
│       └── responses.py        # 响应格式化
├── app.py                      # 主应用入口
├── start_multiple_servers.py   # 多实例启动
├── doc/                        # 文档目录
│   ├── ARCHITECTURE.md         # 本文件
│   ├── API_DOC.md              # API 接口文档
│   └── README.md               # 项目说明
├── tests/                      # 测试文件
└── requirements.txt
```

## 3. 支持的任务类型

| task_type | 说明 | 策略类 | 实现函数 |
|-----------|------|--------|---------|
| wer | 词错误率 | WerCalculator | wer_calculator.py |
| ser | 句错误率 | SerCalculator | wer_calculator.py |
| cpwer | 连接词错误率 | CpwerCalculator | wer_calculator.py |
| tcpwer | 时间约束词错误率 | TcpwerCalculator | wer_calculator.py |
| stm_wer | 基于 STM 的 WER | StmWerCalculator | wer_calculator.py |
| der | 说话人分离错误率 | DerCalculator | der_calculator.py |
| llm_judge | LLM 语义评分 | LlmJudgeCalculator | llm_judge_calculator.py |
| turn_taking | 话轮接管（tor + false_takeover + takeover_latency + input_asr） | TurnTakingCalculator | turn_taking/ |
| interruption_metrics | 打断指标 v2（用例类型 + 行为数量 + 时延 + LLM 评分/停止遵从） | InterruptionMetricsCalculator | interruptibility/ |
| non_interactive_latency | 非交互意图时延 | NonInteractiveLatencyCalculator | rejection_scene_awareness/ |
| noise_latency | 噪声打断时延 | NoiseLatencyCalculator | rejection_scene_awareness/ |
| env_judge | 环境音/打断能力录屏裁判 | EnvJudgeCalculator | env_judge/ |

## 4. 核心架构：策略模式 + 注册表

### 4.1 设计模式

采用 **策略模式 + 注册表** 组合，辅以 **模板方法** 处理参数提取：

- **策略模式**：每种 task_type 封装成独立的 Calculator 类，实现同一接口（`BaseCalculator`）
- **注册表**：`TaskService.CALCULATORS` dict，`calculators/__init__.py` import 时自动注册全部策略类
- **模板方法**：`BaseCalculator.run()` 调 `prepare_params → calculate`，子类可覆写 `prepare_params`

### 4.2 BaseCalculator 基类

```python
class BaseCalculator:
    task_type: str = ''

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
    │  3. 提交到线程池 → calculate_in_process()
    │
    ▼
task_service.py calculate()
    │  calculator = TaskService.CALCULATORS.get(task_type)
    │  return calculator.run(task_params)
    │
    ▼
BaseCalculator.run()
    │  params = self.prepare_params(task_params)  → 提取/转换参数
    │  return self.calculate(params)              → 执行计算
    │
    ▼
具体 Calculator.calculate() → 调用实现函数 → 返回结果
```

### 4.4 新增任务类型

只需两步，无需改 `calculate()` 或 `api.py`：

1. 在对应域子包新建 `strategy.py`，实现 `validate` + `prepare_params` + `calculate`
2. 在 `calculators/__init__.py` 加一行注册

## 5. 通用流程

```
主服务 (Intelligent-Audio-TEST, port 5000)
    │
    │  方式一：JSON POST → /api/create_task（无文件）
    │  方式二：multipart/form-data POST → /api/create_task_upload（带文件）
    │
    │  文件上传时：
    │    - wav 文件提取为 multipart 字段
    │    - payload 中路径替换为 __MULTIPART__:field_name 占位符
    │    - eval_server 收到后保存文件，替换占位符为实际路径
    │
    ▼
eval_server (port 5001)
    │
    │  保存上传文件 → 替换占位符 → TaskService.calculate(task_type, task_params)
    │
    ▼
计算模块 → 返回结果 → 存入 tasks/{date}/task_{id}.json
    │
    ▼
主服务轮询 GET /api/get_final_result/{task_id} → 获取结果
```

## 6. xiaoyi_metrics 指标

### 6.1 turn_taking —— 话轮接管

统一入口位于 [turn_taking/__init__.py](../app/services/calculators/xiaoyi_metrics/turn_taking/__init__.py)。

#### 核心概念：双路 ASR

tor / false_takeover / takeover_latency 共用**双路 ASR**方案：

- **user_wav**（`cap_client_process_out.wav`）：用户说话通道
- **ai_wav**（`cap_client_ec_out.wav`）：AI 回复通道

两路音频同时开始录制，共享同一时间轴（0 点为录音起点），因此可直接用各路 ASR 时间戳相减得到时延。统一入口在 `__init__.py` 内部对两路 wav 各调一次 ASR，将 `chunks` 传给各子指标，避免重复调用。

#### 子指标

| 指标 | 说明 | 主函数 |
|------|------|--------|
| tor | 接话率：判定用户结束说话后模型是否正确开始回复 | `compute_tor_during_pauses(chunks, pause_intervals)` |
| false_takeover | 误接管率：判定用户停顿期间模型是否错误接管（抢话） | `compute_false_takeover(chunks, pause_intervals)` |
| takeover_latency | 接管时延：AI 首字时刻 - 用户末字时刻 | `compute_takeover_latency_from_raw(first_frame_ms, asr_result, end_ms)` |
| input_asr | 输入识别准确率：query vs question 文本匹配 | `compare_query_question(query, question)` |

### 6.2 interruption_metrics —— 打断指标（v2）

用户打断正在说话的小艺时，衡量"停得下、恢复得来、答得对题"。统一计算器一次出全部字段：本地时序 + **进程内直调逐轮 LLM 裁判**（`env_judge/interruption_judge.py` 的 `judge_interruption_rounds`，整例一次调用），不依赖平台跨维度回填。

- 输入：`rounds[]`（逐轮 `user_asr`/`model_asr`/`query`/`is_interruption`/`stop_intent`/`is_return_to_topic`/`played_audios`）+ 用例级 `interruption_rounds`/`dangling_interruption_rounds`；兼容单轮平铺 `user_asr`/`model_asr`（平台逐轮切片路径）
- 用例类型 `case_type`（轮次标记本地推导，7 类）：`single` / `single_stop` / `multi` / `stop_resume_single` / `stop_resume_multi` / `topic_resume_single` / `topic_resume_multi`
- 行为五分类（LLM 逐轮判 → 本地确定性映射成败）：回复→成功；恢复/无关/静默→失败；询问→询问；解析失败→unknown（不入数量、时延记 -1）。**停止指令轮例外**：直接静默或"好的"等确认语后静默=遵从停止 → 按「回复」成功计（prompt 指引 + 派生层兜底重映射，score 不入内容均分）
- 数量字段：`success_count` / `failure_count` / `inquiry_count` + 各行为计数（`reply/recover/irrelevant/silence/ask_behavior_count`）；分母＝非 dangling 实际打断轮（恢复轮不入）
- 时延字段（毫秒；行为失败/unknown 轮 list 记 -1，avg/min/max 排除 -1、全 -1 → None）：
  - **响应时延** `response_latency_avg/min/max_ms` + `round_response_latencies`：用户开始打断 → 模型当前段停口
  - **回复时延** `reply_latency_avg/min/max_ms` + `round_reply_latencies`：用户说完 → 模型重新开口
  - **恢复首轮内容时延** `resume_first_reply_latency_ms`：最后一个恢复轮的回复时延；无恢复轮（普通用例）→ null 显示 -（与恢复内容评分口径一致，不回退打断轮时延）
  - **恢复原话题判定** `topic_resumed`：恢复轮（输入标记 `is_return_to_topic`）由 LLM 判模型**实际**是否回到原话题（true/false；降级 null），配套 `resume_content_score`（未回到原话题时三维 ≤2）
  - 用户段锚定：优先 `played_audios` FFT 对齐精修 → 回退驱动轮窗口（start_ms/end_ms）→ 再回退重叠启发式（message 标降级）
- 评分/遵从：`reply_content_score`、`resume_content_score`（0-5，LLM）；`stop_compliance_rate`（仅停止指令类用例计算，其余 None）
- LLM 降级：api_key 缺失/调用失败 → 数量与评分 None、message 标"行为判定降级"，时延走本地代理
- `per_round[]` 逐轮投影（整体评估返回逐轮结果方案）：`build_per_round` 把 round_details 零成本投影为每轮 `{'round_number', 'interruption': {轮级字段}}`（成功/失败/询问 0/1、响应/回复时延、评分、停止遵从、恢复首轮回覆时延）；无时序/降级的轮为跳过项。run() 把投影提升到响应 result 顶层（与 `interruption` 包同级），TaskService 检测到原生 per_round 即跳过默认逐轮切片重跑（省 N 次 LLM）。平台据此覆盖逐轮 TestResultDimension，字段名与整体 spec 同名，按维度 field_path 直接提取
- 旧字段（`interruption_success_rate` / `avg_stop_latency_s` 等，`_s` 后缀实存毫秒）保留为诊断输出

### 6.3 non_interactive_latency —— 非交互意图时延

用户问完后模型开始回复，在回复期间用户又说了话（user_asr 第 2 段），计算：

- `stop_latency_s`：用户开始讲话 → 模型停止回复
- `recovery_latency_s`：用户讲完 → 模型开始回复

```
SEG_MERGE_GAP_S = 0.7   # 句内最大停顿适配
```

### 6.4 noise_latency —— 噪声打断时延

与 `non_interactive_latency` 对称，把"用户说话"替换为"噪声播放"。

- 噪声 `[start_ms, end_ms]` 为绝对世界毫秒
- 用 `pcm_first_ms` 换算到模型音频相对秒：`n_s = (start_ms - pcm_first_ms) / 1000`
- 复用 `non_interactive_latency` 同套段提取逻辑，补充绝对毫秒输出

### 6.5 env_judge —— 环境音/打断能力录屏裁判

传入录屏/音频文件，由裁判 LLM 对语音大模型行为评判。

支持两类 task_type：
- **env_judge**（拒识与环境理解）：旁人交谈静默 / 环境噪声 / 反馈词 / 生理声 / 环境事件回溯
- **interruption_judge**（打断能力）：插话打断与重新响应 / 停止指令响应 / 多轮打断后恢复原话题

行为五分类（v2 逐轮裁判 `judge_interruption_rounds`，interruption_metrics 进程内复用）：回复 / 恢复 / 无关 / 静默 / 询问。

### 6.6 llm_judge —— 通用 LLM 语义打分

用大模型（默认 `deepseek-r1`）对设备回答与参考答案做语义打分。

- 支持单轮 / 多轮（`rounds` 逐轮列出）
- 支持多模态：音频文件编码为 base64 data URI 发送
- 默认评价维度：准确率 / 流畅度 / 相关性（可通过 `scoring_criteria` 自定义）

## 7. ASR 服务调用链

```
eval_server (port 5001)
    │
    │  asr_adapter.py
    │    call_modelscope_asr(wav_path)
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
2. **按域分子包**：策略类和实现函数放同一域子包，如 `wer/` 内含 `strategies.py` + `wer_calculator.py`，`xiaoyi_metrics/` 下按 turn_taking / interruptibility / rejection_scene_awareness / env_judge / llm_judge 分子包
3. **ASR 只调一次**：turn_taking 的三个子指标共享同一次 ASR 推理结果，通过返回值传递
4. **不读写中间 JSON 文件**：ASR 结果直接通过内存对象传递
5. **multipart 文件上传**：主服务上传 wav 文件到 eval_server，eval_server 再上传到 asr_server
6. **CLI 与主流程分离**：子模块保留 `*_from_files` 函数供命令行独立测试，主流程用 `compute_*` / `*_from_raw` 函数
7. **三机部署**：测试机（主服务+eval_server）→ ASR 主机（asr_server），网线直连

## 9. 配置

### eval_server .env

```
ASR_SERVER_URL=http://100.70.20.135:10095
ASR_TIMEOUT=120
```

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
│ eval_server (port 5001)│ ←── 网线直连 ──→ │ (port 10095)      │
│ Intelligent-Audio-TEST │                  │ ModelScope ASR    │
└──────────────────────┘                  └──────────────────┘
```

- 两台机配同网段静态 IP，默认网关留空
- ASR 主机关闭防火墙或放行 10095 端口
- ASR 服务监听 0.0.0.0:10095
