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
│   │   ├── xiaoyi_metrics/     # 小艺指标（tor / false_takeover / takeover_latency）
│   │   │   ├── __init__.py     # 统一入口：调一次 ASR，三个子指标共享结果
│   │   │   ├── tor.py          # 接话率（Take-Off Rate）
│   │   │   ├── false_takeover.py   # 误接管率
│   │   │   └── takeover_latency.py # 接管时延
│   │   ├── wer_calculator.py   # WER/SER/CPWER/TCPWER/STM_WER
│   │   ├── der_calculator.py   # DER
│   │   ├── llm_judge_calculator.py # LLM 语义评分
│   │   ├── remote_service.py   # 远程端点调用
│   │   └── task_service.py     # 任务调度入口（根据 task_type 分发）
│   └── utils/
│       ├── asr_adapator.py     # ASR 适配层（HTTP 调用远程 asr_server.py）
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

| task_type | 说明 | 计算模块 |
|-----------|------|---------|
| wer | 词错误率 | wer_calculator.py |
| ser | 句错误率 | wer_calculator.py |
| cpwer | 连接词错误率 | wer_calculator.py |
| tcpwer | 时间约束词错误率 | wer_calculator.py |
| stm_wer | 基于 STM 的 WER | wer_calculator.py |
| der | 说话人分离错误率 | der_calculator.py |
| llm_judge | LLM 语义评分 | llm_judge_calculator.py |
| xiaoyi_metrics | 小艺指标（tor + false_takeover + takeover_latency） | xiaoyi_metrics/ |

## 4. 核心调用流程

### 4.1 通用流程

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
    │  保存上传文件 → 替换占位符 → task_service.calculate(task_type, task_params)
    │
    ▼
计算模块 → 返回结果 → 存入 tasks/{date}/task_{id}.json
    │
    ▼
主服务轮询 GET /api/get_final_result/{task_id} → 获取结果
```

### 4.2 xiaoyi_metrics 流程

```
task_service.py → calculate('xiaoyi_metrics', task_params)
    │  task_params: record_path, pause, first_frame_ms, end_ms, offset_ms
    │
    ▼
xiaoyi_metrics/__init__.py → calculate_xiaoyi_metrics(task_params)
    │
    │  1. 调一次 ASR（通过返回值，不读写中间文件）
    │     asr_adapator.call_modelscope_asr(record_path)
    │         └── HTTP POST → asr_server.py /asr (port 10095)
    │             └── 上传 wav → ModelScope Paraformer 推理
    │             └── 返回 {text, chunks}
    │     asr_adapator.parse_result(raw)
    │         └── 透传，得到 asr_result 对象
    │
    │  2. 三个子指标共享 asr_result（纯内存计算）
    │
    ├── tor.compute_tor_during_pauses(chunks, pause)
    ├── false_takeover.compute_false_takeover(chunks, pause)
    └── takeover_latency.compute_takeover_latency_from_raw(first_frame_ms, asr_result, end_ms)
    │
    ▼
返回 {tor: {...}, false_takeover: {...}, takeover_latency: {...}}
```

### 4.3 ASR 服务调用链

```
eval_server (port 5001)
    │
    │  asr_adapator.py
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

## 5. xiaoyi_metrics 三个子指标

### 5.1 tor（接话率）

判定模型在用户停顿期间是否错误接管（开口）。

- 输入：chunks（ASR 词级时间戳），pause_intervals（停顿区间）
- 判定：若模型某个词的 [start, end] 与 pause 区间相交 → 该 pause 记为错误接管(1)
- 输出：`{tor, takeover_count, total_pauses, per_pause}`
- 主流程函数：`compute_tor_during_pauses(chunks, pause_intervals)`
- CLI 函数：`compute_tor_during_pauses_from_files(asr_json_path, pause_json_path)`

### 5.2 false_takeover（误接管率）

将所有 pause 区间内命中的模型词拼到一起，统一判定是否抢话。

- 输入：chunks，pause_intervals
- 判定：duration >= 1秒 或 n_words > 3 → 抢话(1)
- 输出：`{tor, n_words, duration, total_pauses, hit_words, details}`
- 主流程函数：`compute_false_takeover(chunks, pause_intervals)`
- CLI 函数：`compute_false_takeover_from_files(asr_json_path, pause_json_path)`

### 5.3 takeover_latency（接管时延）

模型回复第一个词时刻 - (音响结束播放时刻 + offset)。

- 公式：`takeover_latency_ms = (first_frame_ms + first_word_begin_ms) - (end_ms + offset_ms)`
- 输入：first_frame_ms, asr_result, end_ms, offset_ms(默认40)
- 输出：`{takeover_latency_ms, first_word_begin_ms, model_first_word_ms, ...}`
- 主流程函数：`compute_takeover_latency_from_raw(first_frame_ms, asr_result, end_ms)`
- CLI 函数：`compute_takeover_latency(first_frame_ms, asr_json_path, end_ms)`

## 5.5 interruption_metrics（打断指标）

用户打断正在说话的小艺时，衡量"停得下、恢复得来"。与 `xiaoyi_metrics` 不同：**不内部调 ASR**，由调用方直接传两路已对齐的 ASR 词级时间戳。

- 输入：`user_asr`（用户提问/打断 ASR）、`model_asr`（模型恢复 ASR，与 user_asr 等长、同一时间轴）
  - 两路均可为 chunks 列表或 `{text, chunks}`
  - 可选：`seg_merge_gap_s`（默认 0.3）
- 三个子指标（对每个用户打断段 u=[u_s, u_e]）：
  - **打断检查时延** `avg_stop_latency_s`：用户开始打断 → 模型当前语音段结束（停下）。对应 FDB v1.5 `latency_stop_list`
  - **打断恢复时延** `avg_recovery_latency_s`：用户说完 → 模型重新开口。对应 FDB v1.5 `latency_resp_list`
  - **打断成功率** `interruption_success_rate`：模型让出（没说穿整个打断区间）且之后恢复。仅 `event_type='interruption'` 计入分母。对应 FDB v1.0 user_interruption 的 TOR↑
  - 辅助：`stop_rate`（让出率）、`resume_rate`（恢复率）、`avg_overlap_s`（双方同时说话时长，越短越好）、`avg_silence_gap_s`（静默时长）
- 退化情形：若 `model_asr` 只含恢复段（用户打断时模型未在说话），停止时延/成功率记为 None，仅给出恢复时延，事件标为 `recovery_only`
- 输出：`{interruption_success_rate, stop_rate, resume_rate, avg_stop_latency_s, avg_recovery_latency_s, avg_overlap_s, avg_silence_gap_s, n_events, per_event, ...}`
- 主流程函数：`compute_interruption_metrics(user_asr, model_asr)`
- 统一入口：`calculate_interruption_metrics(task_params)`（`xiaoyi_metrics/__init__.py`）
- 路由：`task_service.calculate(task_type='interruption_metrics', ...)`
- 维度注册：`Intelligent-Audio-TEST/backend/scripts/migrations/202606/seed_interruption_dimensions.py`

## 6. 关键设计决策

1. **ASR 只调一次**：三个子指标共享同一次 ASR 推理结果，通过返回值传递
2. **不读写中间 JSON 文件**：ASR 结果直接通过内存对象传递，不再写 .json 再读
3. **multipart 文件上传**：主服务上传 wav 文件到 eval_server，eval_server 再上传到 asr_server
4. **CLI 与主流程分离**：子模块保留 `*_from_files` 函数供命令行独立测试，主流程用 `compute_*` / `*_from_raw` 函数
5. **三机部署**：测试机（主服务+eval_server）→ ASR 主机（asr_server），网线直连

## 7. 配置

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

## 8. 网络部署

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
