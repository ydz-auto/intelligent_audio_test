# Intelligent Audio Test

智能语音算法自动化测试平台，面向语音交互大模型/算法的端到端（E2E）与 API 自动化测试，覆盖测试用例管理、音频播放与采集、设备自动化驱动、多维度评估、报告对比全流程。

## 仓库结构

```
.
├── Intelligent-Audio-TEST/   # 主平台（FastAPI + Vue3 + Electron）
├── eval_server/              # 评估维度计算服务（WER/SER/DER/LLM Judge/小艺指标）
├── asr_server/                # 独立 ASR 推理服务（ModelScope Paraformer）
└── 第三方/                    # 第三方 SDK / proto（如火山 AST）
```

## 核心特性

- **多服务微服务架构**：5 个 FastAPI 后端 + 2 个 gRPC 服务，DDD 风格分层（application/domain/infrastructure/interfaces）
- **双测试模式**：端到端测试（E2E，真机自动化）与 API 测试（HTTP/SSE/流式接口）
- **音频引擎**：多音频并行播放、交叠播放、时间戳对齐、声压级（SPL）校准
- **多设备驱动**：Android（adbutils/uiautomator2）、HarmonyOS（hypium/wda）、环境设备（Modbus/串口）
- **多维度评估**：WER/SER/CPWER/TCPWER/STM_WER/DER/LLM Judge/小艺指标（tor/false_takeover/takeover_latency）
- **实时通信**：Socket.IO 日志推送 + Redis Pub/Sub 进度广播 + SSE 事件流
- **算法配置化**：动态表单驱动算法接入，零代码新增被测算法
- **报告对比**：任务级/用例级/标签级多维度对比，时间轴说话人自动匹配
- **桌面端**：Electron 封装，支持本地设备直连

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| RPC | gRPC + Protocol Buffers |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| 对象存储 | MinIO + boto3 |
| 缓存/消息 | Redis（Pub/Sub + 服务注册） |
| 数据校验 | Pydantic 2.0 |
| 音频处理 | pydub / librosa / soundfile / scipy / pyaudio |
| 设备自动化 | adbutils / uiautomator2 / playwright / pymodbus / hypium / wda |

### 前端

| 类别 | 技术 |
|------|------|
| 框架 | Vue 3.4 + TypeScript 5.9 |
| 构建 | Vite 5 |
| 状态管理 | Pinia |
| 路由 | Vue Router 4 |
| 通信 | Axios + socket.io-client |
| 图表 | Chart.js + chartjs-plugin-zoom |
| 桌面端 | Electron 31 |
| 测试 | Vitest + jsdom + @vue/test-utils |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 16
- Redis 7+
- MinIO
- FFmpeg（音频处理依赖，需加入 PATH）
- Android Platform Tools（adb，端到端测试）
- Hypium（HarmonyOS 测试，可选）

### 一键启动

```bash
cd Intelligent-Audio-TEST

# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install && cd ..

# 配置环境变量（按需修改数据库/Redis/MinIO/ASR 地址）
cp .env.example .env

# 一键启动全部服务（Redis + PG + MinIO + 5 后端 + 前端）
python run_all.py
```

启动完成后：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| API Gateway | http://localhost:5000 |
| Task Service | http://localhost:5001 |
| E2E Test Service | http://localhost:5002 |
| API Test Service | http://localhost:5003 |
| Adapter Service | http://localhost:5008 |
| MinIO Console | http://localhost:9001 |

### Docker 部署

所有 Docker 配置集中在仓库根 [docker/](docker/) 目录：

```bash
# 一键启动全部服务（PG + Redis + MinIO + 5 后端微服务）
docker compose -f docker/docker-compose.yml up -d --build
```

| 文件 | 说明 |
|------|------|
| [docker/docker-compose.yml](docker/docker-compose.yml) | 编排文件（含 PG/Redis/MinIO + 5 服务 + minio-init） |
| [docker/Dockerfile.api_gateway](docker/Dockerfile.api_gateway) | API 网关镜像 |
| [docker/Dockerfile.task_service](docker/Dockerfile.task_service) | 任务服务镜像 |
| [docker/Dockerfile.e2e_test_service](docker/Dockerfile.e2e_test_service) | E2E 测试服务镜像 |
| [docker/Dockerfile.api_test_service](docker/Dockerfile.api_test_service) | API 测试服务镜像 |
| [docker/Dockerfile.api_adapter_service](docker/Dockerfile.api_adapter_service) | 算法适配服务镜像 |
| [docker/.dockerignore](docker/.dockerignore) | 构建上下文排除规则 |

> 注：build context 为仓库根（`..`），Dockerfile 内通过 `COPY Intelligent-Audio-TEST/ .` 拷贝主平台代码。E2E 服务挂载 `/dev/bus/usb` 以直连 Android 设备。

### 单独启动评估/ASR 服务

```bash
# 评估服务（端口 5001，需与主平台 task_service 区分端口）
cd eval_server && python app.py

# ASR 服务（端口 10095，需独立主机部署以保证时延测量准确性）
cd asr_server && python asr_server.py
```

## 服务架构

```
                      ┌───────────────────┐
                      │   frontend (Vue3)  │
                      │  + Electron 桌面端 │
                      └─────────┬─────────┘
                            │  HTTP / Socket.IO / SSE
                            ▼
┌───────────────────────────────────────────────────────┐
│                  api_gateway (FastAPI)                 │
│  HTTP 路由 · WebSocket 日志 · SSE 事件 · Redis PubSub  │
└───┬───────────┬──────────────┬───────────────┬───────┘
    │ gRPC      │ gRPC         │ gRPC          │ HTTP
    ▼           ▼              ▼               ▼
┌────────┐ ┌────────┐   ┌────────────┐   ┌──────────────┐
│ task_  │ │ e2e_   │   │ api_test_  │   │ api_adapter_ │
│ service│ │ test_  │   │ service    │   │ service      │
│        │ │ service│   │            │   │ (Qwen/火山)  │
└───┬────┘ └───┬────┘   └────────────┘   └──────────────┘
    │ HTTP      │ 设备自动化
    ▼           ▼
┌────────┐  ┌─────────────────┐
│eval_   │  │ Android / Harmony│
│server  │  │ 环境设备 / 串口   │
└───┬────┘  └─────────────────┘
    │ HTTP
    ▼
┌────────┐
│asr_    │
│server  │
│(独立机) │
└────────┘
```

### 主平台微服务（Intelligent-Audio-TEST）

| 服务 | 端口 | gRPC | 职责 |
|------|------|------|------|
| api_gateway | 5000 | - | HTTP 路由、WebSocket 日志、SSE、服务注册 |
| task_service | 5001 | 50061 | 任务执行引擎、评测调度、多轮聚合 |
| e2e_test_service | 5002 | 50051 | 端到端测试、音频引擎、设备驱动、结果采集 |
| api_test_service | 5003 | 50071 | API 测试、并发控制、会话执行 |
| api_adapter_service | 5008 | 50081 | 被测算法适配（Qwen/火山 AST/SSE/HTTP） |

### 评估/识别服务（独立部署）

| 服务 | 端口 | 职责 |
|------|------|------|
| eval_server | 5001 | WER/SER/DER/LLM Judge/小艺指标计算 |
| asr_server | 10095 | ModelScope Paraformer ASR 推理（独立主机） |

## 测试流程

1. **用例管理**：创建测试用例，配置音频、参考参数、评估维度、干扰项
2. **算法配置**：通过动态表单接入被测算法（HTTP/SSE/gRPC）
3. **设备管理**：扫描并注册被测设备（Android/HarmonyOS）与播放/环境设备
4. **任务执行**：
   - E2E：编排音频播放 → 设备自动化 → 录音采集 → ASR → 评估
   - API：并发调用被测接口 → 结果采集 → 评估
5. **报告对比**：任务级/用例级/标签级对比，时间轴可视化

## 关键配置

主配置在 `Intelligent-Audio-TEST/.env`，关键项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 地址 |
| `OSS_ENDPOINT` | `localhost:9000` | MinIO 地址 |
| `OSS_ACCESS_KEY` / `OSS_SECRET_KEY` | - | MinIO 凭据 |
| `ASR_SERVER_URL` | `http://127.0.0.1:10095` | ASR 服务地址 |
| `EVAL_SERVER_URL` | `http://127.0.0.1:5001` | 评估服务地址 |

## 开发约定

- 后端遵循 DDD 分层：`application/`（命令/查询）→ `domain/`（实体/事件）→ `infrastructure/`（持久化/适配器）→ `interfaces/`（API/gRPC）
- 前端组件按域分组：`components/{algorithm,common,layout,report,task}`，composables 按域拆分
- gRPC proto 定义位于 `shared/proto/`，修改后需重新生成 Python 桩代码
- 前端样式按页面域归并至 `assets/styles/<domain>/`，组件级样式与组件同名

## 相关文档

- [eval_server 评估服务](eval_server/doc/README.md) — 评估维度计算服务文档
- [eval_server 架构](eval_server/doc/ARCHITECTURE.md) — 评估服务架构设计
- [eval_server API](eval_server/doc/API_DOC.md) — 评估服务接口规范
- [asr_server ASR 服务](asr_server/README.md) — ASR 推理服务文档
- [gRPC Proto 接口](Intelligent-Audio-TEST/shared/proto/README.md) — 跨服务 gRPC 接口定义
- [前端更新日志](Intelligent-Audio-TEST/frontend/docs/CHANGELOG.md) — 前端变更记录
