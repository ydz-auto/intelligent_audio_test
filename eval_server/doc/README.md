# eval_server 评估维度计算服务

音频评估维度计算服务，接收主服务（Intelligent-Audio-TEST）提交的评估任务，支持 WER/SER/DER/LLM Judge/小艺指标等维度计算。

## 功能特性

- **多维度评估**：WER、SER、CPWER、TCPWER、STM_WER、DER、LLM Judge、小艺指标(tor/false_takeover/takeover_latency)
- **异步任务模式**：创建任务 → 轮询状态 → 获取结果
- **文件上传**：支持 multipart/form-data 上传音频文件
- **本地/远程处理**：支持本地处理和分发到远程 Worker 节点
- **两层并发控制**：本地并发 + 远程端点并发，支持动态调整
- **ASR 远程调用**：小艺指标通过 HTTP 调用独立 ASR 主机推理，不占用本机 CPU

## 技术栈

- Python 3.10+
- Flask 3.0+
- NumPy 1.26+
- requests（HTTP 调用 ASR 服务）

## 项目结构

```
eval_server/
├── app/
│   ├── app.py                  # 应用创建和初始化
│   ├── config.py               # 配置信息
│   ├── controllers/
│   │   ├── api.py              # 任务管理 API
│   │   └── health.py           # 健康检查 API
│   ├── database/
│   │   ├── tasks/              # 任务结果 JSON 存储（按日期分目录）
│   │   ├── schema.sql          # 数据库表结构
│   │   └── endpoints.json      # 远程端点配置
│   ├── models/
│   │   └── task.py             # 任务数据模型
│   ├── services/
│   │   ├── xiaoyi_metrics/     # 小艺指标
│   │   │   ├── __init__.py     # 统一入口：调一次 ASR，三个子指标共享
│   │   │   ├── tor.py          # 接话率
│   │   │   ├── false_takeover.py   # 误接管率
│   │   │   └── takeover_latency.py # 接管时延
│   │   ├── wer_calculator.py   # WER/SER/CPWER/TCPWER/STM_WER
│   │   ├── der_calculator.py   # DER
│   │   ├── llm_judge_calculator.py # LLM 语义评分
│   │   ├── remote_service.py   # 远程端点调用
│   │   └── task_service.py     # 任务调度入口
│   └── utils/
│       ├── asr_adapator.py     # ASR 适配层（HTTP 调用远程 asr_server）
│       ├── concurrency.py      # 并发控制
│       ├── decorators.py       # 装饰器
│       ├── log_rotation.py     # 日志轮转
│       ├── normalizer.py       # 文本正则化
│       └── responses.py        # 响应格式化
├── app.py                      # 主应用入口
├── start_multiple_servers.py   # 多实例启动
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

# 配置 ASR 服务地址（eval_server/.env）
# ASR_SERVER_URL=http://<ASR主机IP>:10095
# ASR_TIMEOUT=120

# 启动服务
python app.py
```

## 支持的任务类型

| task_type | 说明 | 必填字段 |
|-----------|------|---------|
| wer | 词错误率 | asr_ref, asr_result |
| ser | 句错误率 | asr_ref, asr_result |
| cpwer | 连接词错误率 | ref_stm, hyp_stm |
| tcpwer | 时间约束词错误率 | ref_stm, hyp_stm |
| stm_wer | 基于 STM 的 WER | ref_stm, hyp_stm |
| der | 说话人分离错误率 | rttm_ref, stm_ref, rttm_res, stm_res |
| llm_judge | LLM 语义评分 | answer, correct_answer |
| xiaoyi_metrics | 小艺指标(tor+false_takeover+takeover_latency) | record_path, pause, first_frame_ms, end_ms |

## 快速开始

### 1. 健康检查

```bash
curl http://localhost:5001/health
```

### 2. 创建 WER 任务

```bash
curl -X POST http://localhost:5001/api/create_task \
  -H "Content-Type: application/json" \
  -d '{"task_type":"wer","asr_ref":"今天天气不错","asr_result":"今天天气不措"}'
```

### 3. 上传文件创建任务（multipart）

```bash
curl -X POST http://localhost:5001/api/create_task_upload \
  -F "task_type=xiaoyi_metrics" \
  -F "record_file=@audio.wav" \
  -F "first_frame_ms=1700000000000" \
  -F "end_ms=1700000005000" \
  -F 'pause=[{"text":"","timestamp":[1.0,2.0]}]'
```

### 4. 查询任务

```bash
# 状态
curl http://localhost:5001/api/get_status/{task_id}

# 结果
curl http://localhost:5001/api/get_final_result/{task_id}
```

## 文档

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 项目简介、安装、快速开始 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构设计、调用流程、xiaoyi_metrics 设计 |
| [API_DOC.md](API_DOC.md) | 完整 API 接口规范、请求/响应示例、错误码 |
