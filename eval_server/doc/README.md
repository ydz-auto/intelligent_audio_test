# eval_server 评估维度计算服务

音频评估维度计算服务，接收主服务（Intelligent-Audio-TEST）提交的评估任务，支持 WER/SER/DER/小艺指标等维度计算。

## 功能特性

- **多维度评估**：WER、SER、CPWER、TCPWER、STM_WER、DER、小艺指标（xiaoyi_metrics 全域 / turn_taking / turn_eval / interruption_metrics / non_interactive_latency / noise_latency / env_judge / reject_judge）
- **策略模式架构**：每种任务类型一个 Calculator 策略类，`validate → prepare_params → calculate` 模板方法，注册表自动注册
- **两级编排**：`XiaoyiMetricsCalculator` 全域编排（统一共享 ASR + 跨域聚合）→ `TurnTakingCalculator` 域内编排（tor / false_takeover / takeover_latency / reply_quality / high_freq_*）
- **异步任务模式**：创建任务 → 轮询状态 → 获取结果，另支持事件化回调（`callback_url`）
- **文件上传**：支持 multipart/form-data 上传音频/视频文件，`__MULTIPART__:field_name` 占位符递归还原
- **本地/远程处理**：支持本地处理和分发到远程 Worker 节点
- **两层并发控制**：全局并发位 + 维度并发位，并发满自动排队（后台 worker 消费），支持动态调整
- **ASR 远程调用**：小艺指标通过 HTTP 调用独立 ASR 主机推理，不占用本机 CPU
- **LLM 统一调用与审计**：`shared/llm_client.py:call_llm` 单入口，按「中转站 × 品牌」两级并发分池，每次调用写 JSONL 审计日志
- **OSS/MinIO 可选支持**：`oss://` 路径在计算前自动下载为本地文件

## 技术栈

- Python 3.10+
- Flask 3.0+ / waitress（生产 WSGI 服务器）
- NumPy / SciPy（音频对齐、FFT 互相关、时延计算）
- requests / httpx（HTTP 调用 ASR / LLM 服务）
- PyYAML（config.yaml 结构配置）

## 项目结构

```
eval_server/
├── app/
│   ├── app.py                  # 应用创建和初始化
│   ├── config.py               # 配置加载（config.yaml 默认值 + .env 覆盖）
│   ├── controllers/
│   │   ├── api.py              # 任务管理 API（create_task / create_task_upload / get_status / get_final_result / delete_task / cancel_task / endpoints）
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
│   │   │   ├── wer/            #   WER 系列域（strategies.py + wer_calculator.py）
│   │   │   ├── der/            #   DER 域（strategy.py + der_calculator.py）
│   │   │   └── xiaoyi_metrics/ #   小艺指标域（全域编排 + 按域分子包，见下）
│   │   ├── remote_service.py   # 远程端点调用
│   │   └── task_service.py     # 任务调度入口（注册表查找 + worker 线程 + 逐轮回填）
│   └── utils/
│       ├── asr_adapter.py      # ASR 适配层（HTTP 调用远程 asr_server）
│       ├── concurrency.py      # 维度并发控制
│       ├── decorators.py       # 装饰器
│       ├── log_rotation.py     # 日志轮转
│       ├── normalizer.py       # 文本正则化
│       ├── oss_client.py       # OSS/MinIO 客户端（可选，oss:// 路径下载）
│       ├── pause_json.py       # 停顿区间 JSON 生成（CLI 工具）
│       └── responses.py        # 响应格式化
│   └── services/calculators/xiaoyi_metrics/
│       ├── __init__.py         #   XiaoyiMetricsCalculator 全域编排器
│       ├── doc/                #   指标文档（README / API / interruption_io 等）
│       ├── shared/             #   共享工具（asr_utils / audio_alignment / constants / llm_client / llm_call_logger）
│       ├── turn_taking/        #   域内编排 + 子维度（tor / false_takeover / takeover_latency / high_freq_turn_taking / high_freq_llm_judge / reply_quality）
│       ├── turn_eval/          #   逐轮三分类（误解管 / 接管 / 未接管）+ 接管时延 + 回复质量
│       ├── interruptibility/   #   打断指标 v2（本地时序 + 进程内直调逐轮 LLM 裁判）
│       ├── rejection_scene_awareness/  # 非交互意图时延 / 噪声打断时延
│       └── env_judge/          #   环境理解裁判（env_judge / env_response_latency / interruption_judge / rejection_judge）
├── app.py                      # 主应用入口（waitress 启动）
├── start_multiple_servers.py   # 多实例启动
├── config.yaml                 # 结构配置（并发 / 品牌 / LLM 默认等）
├── .env.example                # 环境变量示例（密钥与部署级覆盖）
├── scripts/                    # 脚本（如 summarize_tasks.py）
├── doc/                        # 文档
│   ├── ARCHITECTURE.md         # 架构文档
│   ├── API_DOC.md              # API 接口文档
│   └── README.md               # 本文件
├── tests/                      # 测试文件
└── requirements.txt
```

## 安装与运行

```bash
# 安装依赖
pip install -r requirements.txt

# 配置（eval_server/.env，从 .env.example 复制）
# ASR_SERVER_URL=http://<ASR主机IP>:10095
# ASR_TIMEOUT=120
# LLM_JUDGE_API_KEY=<LLM中转站API Key>
# 结构配置在 config.yaml（端口 / 并发 / LLM 默认模型 / 品牌识别规则等）

# 启动服务
python app.py            # 默认端口见 config.yaml（8888），可用 --port/--host 覆盖
```

## 支持的任务类型

| task_type | 说明 | 必填字段 | Calculator 类 |
|-----------|------|---------|---------------|
| wer | 词错误率 | asr_ref, asr_hyp | WerCalculator |
| ser | 句错误率 | asr_ref, asr_hyp | SerCalculator |
| cpwer | 连接词错误率 | stm_ref, stm_hyp | CpwerCalculator |
| tcpwer | 时间约束词错误率 | stm_ref, stm_hyp | TcpwerCalculator |
| stm_wer | 基于 STM 的 WER | stm_ref, stm_hyp | StmWerCalculator |
| der | 说话人分离错误率 | rttm_ref, stm_ref, rttm_hyp, stm_hyp（旧名 rttm_res/stm_res 兼容） | DerCalculator |
| xiaoyi_metrics | 小艺全域编排（统一共享 ASR + 跨域聚合） | user_wav / ai_wav 至少一个 | XiaoyiMetricsCalculator |
| turn_taking | 话轮接管（tor + false_takeover + takeover_latency + reply_quality + high_freq_*） | user_wav / ai_wav | TurnTakingCalculator |
| tor | 接话率 | user_wav, ai_wav | TorCalculator |
| false_takeover | 误接管率 | ai_wav | FalseTakeoverCalculator |
| takeover_latency | 接管时延 | user_wav, ai_wav | TakeoverLatencyCalculator |
| high_freq_turn_taking | 高频轮换每轮回复时延 | user_wav, ai_wav | HighFreqTurnTakingCalculator |
| high_freq_llm_judge | 高频轮换 LLM 裁判 | ai_wav + rounds | HighFreqLlmJudgeCalculator |
| reply_quality | 单轮模型回复质量 LLM 评分 | ai_wav | ReplyQualityCalculator |
| turn_eval | 逐轮三分类（误解管/接管/未接管）+ 接管时延 + 回复质量 | user_wav / ai_wav | TurnEvalCalculator |
| interruption_metrics | 打断指标 v2（用例类型 + 行为数量 + 响应/回复时延 + LLM 评分/停止遵从） | rounds[]（逐轮 user_asr/model_asr 或双路 wav） | InterruptionMetricsCalculator |
| non_interactive_latency | 非交互意图时延 | user_wav, ai_wav | NonInteractiveLatencyCalculator |
| noise_latency | 噪声打断时延 | ai_wav, start_ms, end_ms, pcm_first_ms | NoiseLatencyCalculator |
| env_judge | 环境理解裁判 | user_wav, ai_wav, played_audios, correctAnswer | EnvJudgeCalculator |
| reject_judge | 拒识裁判（行为分类 + rate 评级） | ai_wav | RejectionJudgeCalculator |

> 完整注册列表以 `app/services/calculators/__init__.py` 为准（`/health` 的 `supported_task_types` 动态读取）。

## 快速开始

### 1. 健康检查

```bash
curl http://localhost:8888/health
```

### 2. 创建 WER 任务

```bash
curl -X POST http://localhost:8888/api/create_task \
  -H "Content-Type: application/json" \
  -d '{"task_type":"wer","asr_ref":"今天天气不错","asr_hyp":"今天天气不措"}'
```

### 3. 上传文件创建任务（multipart）

```bash
curl -X POST http://localhost:8888/api/create_task_upload \
  -F "task_type=turn_taking" \
  -F "user_wav=@cap_client_process_out.wav" \
  -F "ai_wav=@cap_client_ec_out.wav"
```

### 4. 查询任务

```bash
# 状态
curl http://localhost:8888/api/get_status/{task_id}

# 结果
curl http://localhost:8888/api/get_final_result/{task_id}
```

## 架构设计

采用 **策略模式 + 注册表** 组合，辅以 **模板方法** 处理参数提取：

- **策略模式**：每种 task_type 封装成独立的 Calculator 类，实现同一接口（`BaseCalculator`）
- **注册表**：`TaskService.CALCULATORS` dict，`calculators/__init__.py` import 时自动注册全部策略类
- **模板方法**：`BaseCalculator.run()` 调 `prepare_params → calculate`，子类可覆写 `prepare_params`
- **单轮/多轮统一**：`round_number` 有值 → 单轮评估；缺省 → 多轮整体评估；`supports_per_round=True` 的 Calculator 在整体评估下自动产出 `per_round[]` 逐轮结果
- **两级编排**：`XiaoyiMetricsCalculator` 调一次双路 ASR 注入 `_shared_asr` 供所有子维度复用（避免重复 ASR），再按 `sub_tasks` 遍历注册表子维度；`TurnTakingCalculator` 同域内编排
- **played_audios 音频对齐**：干净音源经 FFT 互相关对齐到劣化录制的 user_wav，精修用户段 / 归属 turn 轮次 / 定位环境声
- **并发满自动排队**：全局并发位 + 维度并发位双重限制，满则创建 pending 任务由后台 worker 消费（不再 429 拒绝），完成走 `callback_url` 事件化回调
- **LLM 两级并发池**：所有 LLM 调用汇聚 `call_llm`，按「中转站 × 模型品牌」分池（文本池 100 / 音频池 5），每次调用写 JSONL 审计日志

新增任务类型只需两步，无需改 `calculate()` 或 `api.py`：

1. 在对应域子包新建 `strategy.py`，实现 `validate` + `prepare_params` + `calculate`
2. 在 `calculators/__init__.py` 加一行注册

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 文档

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 项目简介、安装、快速开始 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构设计、策略模式、调用流程、xiaoyi_metrics 设计 |
| [API_DOC.md](API_DOC.md) | 完整 API 接口规范、请求/响应示例、错误码 |

小艺指标详细文档见 `app/services/calculators/xiaoyi_metrics/doc/`（README / API / interruption_io / llm_call_audit_log）。
