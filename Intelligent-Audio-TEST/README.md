# Intelligent Audio Test

智能语音算法自动化测试平台，面向语音交互大模型 / 算法的端到端（E2E）与 API 自动化测试，覆盖测试用例管理、音频播放与采集、设备自动化驱动、多维度评估、报告对比全流程。

## 核心特性

- **微服务架构（DDD + CQRS）**：11 个后端微服务（FastAPI + gRPC），按 `interfaces → application → domain → infrastructure` 分层
- **双测试模式**：端到端测试（E2E，真机自动化）与 API 测试（HTTP/SSE/流式接口，多路并发）
- **音频引擎**：多音频并行播放、交叠播放、时间戳对齐、声压级（SPL）校准与映射
- **多设备驱动**：Android（adbutils/uiautomator2）、HarmonyOS（hypium/wda）、环境设备（Modbus/串口）
- **多维度评估**：WER/SER/DER/LLM Judge/小艺/环境音/打断/时延等维度，动态可配置
- **实时通信**：Socket.IO 日志推送 + Redis Pub/Sub 进度广播 + SSE 事件流
- **算法配置化**：动态表单驱动算法接入，零代码新增被测算法
- **RBAC 权限**：基于 Redis 的认证/OAuth（本地与华为云模式）+ 角色权限模型
- **报告对比**：任务级/用例级/标签级多维度对比，时间轴说话人自动匹配，异步生成
- **桌面端**：Electron 封装，支持本地设备直连

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| RPC | gRPC + Protocol Buffers |
| 数据库 | PostgreSQL 16 + SQLAlchemy 2.0 |
| 对象存储 | MinIO（单桶模式 + 前端分片直传） |
| 缓存 / 消息 | Redis（Pub/Sub + 服务发现 + 分布式协调） |
| 认证 | OAuth2 + JWT + RBAC |
| 数据校验 | Pydantic 2.0 |
| 音频处理 | pydub / librosa / soundfile / scipy / pyaudio |
| 设备自动化 | adbutils / uiautomator2 / pymodbus / hypium / wda |

### 前端

| 类别 | 技术 |
|------|------|
| 框架 | Vue 3.4 + TypeScript 5.9 |
| 构建 | Vite 5 |
| 状态管理 | Pinia |
| 通信 | Axios + socket.io-client |
| 图表 | Chart.js + chartjs-plugin-zoom |
| 桌面端 | Electron 31 |
| 测试 | Vitest + @vue/test-utils |

## 架构总览

```
                      ┌───────────────────────────┐
                      │ frontend (Vue3 + Electron) │
                      └────────────┬──────────────┘
                           HTTP / Socket.IO / SSE（Vite proxy → 5000）
                                   ▼
                       ┌───────────────────────┐
                       │    api_gateway :5000   │
                       │ 路由 · WS · SSE · 鉴权 │
                       └───┬────┬────┬────┬────┘
                    gRPC/HTTP│    │    │    │
               ┌─────────────┘    │    │    └─────────────┐
               ▼                  ▼    ▼                  ▼
        ┌──────────────┐  ┌─────────────────┐   ┌──────────────────┐
        │ 业务服务 (HTTP) │  │ 认证/算法/适配服务 │   │ gRPC-only 服务    │
        │ task 5001     │  │ auth 5009       │   │ audio 50052       │
        │ e2e 5002      │  │ algorithm 5007  │   │ device 50053      │
        │ api_test 5003 │  │ adapter 5008    │   └──────────────────┘
        │ eval 5004     │  └─────────────────┘
        │ report 5006   │
        └──────┬───────┘
               │
        ┌──────┴─────────────────────────────────┐
        │ PostgreSQL 5432 · Redis 6379 · MinIO 9000 │
        └────────────────────────────────────────┘
```

### 微服务清单

端口统一注册在 [shared/config/service_ports.py](shared/config/service_ports.py)，禁止散落硬编码。

| 服务 | HTTP | gRPC | 职责 |
|------|------|------|------|
| api_gateway | 5000 | - | HTTP 路由、WebSocket 日志、SSE 事件、服务注册 |
| task_service | 5001 | 50061 | 任务执行引擎、评测调度、多轮聚合、分布式协调 |
| e2e_test_service | 5002 | 50051 | 端到端测试、音频引擎、设备驱动、结果采集 |
| api_test_service | 5003 | 50071 | API 测试、并发控制、会话执行 |
| evaluation_service | 5004 | 50091 | 评估维度管理、指标计算（WER/DER/LLM Judge 等） |
| report_service | 5006 | 50068 | 报告生成（异步）与查询、对比分析 |
| algorithm_service | 5007 | 50067 | 被测算法配置、参考参数生成器 |
| api_adapter_service | 5008 | 50081 | 被测算法适配（Qwen/火山 AST/SSE/HTTP） |
| auth_service | 5009 | 50069 | 认证 / OAuth / RBAC 角色权限 |
| audio_service | - | 50052 | 音频播放（gRPC-only） |
| device_service | - | 50053 | 播放 / 环境设备驱动（gRPC-only） |

基础设施：PostgreSQL `5432`、Redis `6379`、MinIO `9000`（控制台 `9001`）、前端 `5173`。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 16 / Redis 7+ / MinIO（也可由 `run_all.py` 自动拉起本地实例）
- FFmpeg（音频处理依赖，需加入 PATH）
- Android Platform Tools（`adb`，端到端测试用）

### 安装与启动

```bash
cd Intelligent-Audio-TEST

# 1. 后端依赖
pip install -r requirements.txt

# 2. 前端依赖
cd frontend && npm install && cd ..

# 3. 配置环境变量
cp .env.example .env   # 按需修改数据库/Redis/MinIO 地址、认证模式

# 4. 初始化数据库表（详见下方「数据库初始化与迁移」）
python scripts/create_all_tables.py

# 5. 一键启动：3 基础设施 + 11 后端微服务 + 前端
python run_all.py
```

启动后各服务地址：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| API Gateway | http://localhost:5000 |
| MinIO Console | http://localhost:9001 |
| 各微服务 | 见上方「微服务清单」 |

说明：

- `run_all.py` 启动前会自动清理被占用的服务端口，并探测端口就绪后再启动下一个；`Ctrl+C` 优雅停止全部。
- 前端请求经 Vite proxy 转发到 API Gateway（`run_all.py` 已注入 `VITE_API_TARGET=http://localhost:5000`）。
- 单独启动前端：`cd frontend && VITE_API_TARGET=http://localhost:5000 npm run dev -- --port 5173 --strictPort`。
- 本地 infra 已被占用（如已装 PG 服务）时会直接复用，不重复拉起。

## 数据库初始化与迁移

> ⚠️ 迁移脚本需要 `ALTER TABLE` 排他锁。**在服务运行期间执行可能被阻塞**（本次排查发现的 `created_by_user_id 不存在` 等报错，正是迁移未执行导致），建议在服务停止或低峰期执行。所有脚本均为幂等（`IF NOT EXISTS` / 已存在即跳过），可重复执行。

### 1. 建表

```bash
python scripts/create_all_tables.py
```

用 SQLAlchemy `Base.metadata.create_all()` 创建所有 ORM 表。**约定：模型变更后新增列，一律通过迁移脚本落地，禁止修改此脚本。**

### 2. 迁移脚本（按目录时间顺序执行）

| 目录 | 脚本 | 说明 |
|------|------|------|
| 202608 | [remove_foreign_keys_and_soft_delete.py](scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py) | 12 步：删除全库外键约束、补软删除列（deleted/deleted_at）、补审计列（created_by/updated_by_user_id）、建 RBAC/OAuth 表、建软删除索引 |
| 202608 | [add_laboratory_tables.py](scripts/migrations/202608/add_laboratory_tables.py) | 实验室 / 环境设备相关表 |
| 202608 | [add_audit_columns.py](scripts/migrations/202608/add_audit_columns.py) | 补齐剩余审计/软删除列并为主键列建索引（覆盖 TASK_TAGS、TEST_CASE_TAGS 等全量表，`--dry-run` 可预览缺失） |
| 202608 | [add_reevaluated_at.py](scripts/migrations/202608/add_reevaluated_at.py) | `test_tasks` 重新评估标记列（reevaluated_at / reevaluation_count） |
| 202608 | [fix_audio_tags_types.py](scripts/migrations/202608/fix_audio_tags_types.py) | 修复 audio_tags 类型不一致 |
| 202608 | [fix_partial_unique_indexes.py](scripts/migrations/202608/fix_partial_unique_indexes.py) | 修复局部唯一索引与软删除冲突 |
| 202608 | [seed_rbac.py](scripts/migrations/202608/seed_rbac.py) | RBAC 角色 / 权限种子数据 |
| 202609 | [add_pass_threshold_to_eval_params.py](scripts/migrations/202609/add_pass_threshold_to_eval_params.py) | 评估参数 pass_threshold 列 |
| 202609 | [seed_voice_llm.py](scripts/migrations/202609/seed_voice_llm.py) 等 `seed_*.py` | 评估维度种子数据（VoiceLLM / 打断 / 环境音 / 时延 / 小艺指标等） |

执行示例：

```bash
python scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py
python scripts/migrations/202608/add_audit_columns.py              # 可加 --dry-run 先预览
python scripts/migrations/202608/add_reevaluated_at.py
python scripts/migrations/202609/add_pass_threshold_to_eval_params.py
python scripts/migrations/202609/seed_voice_llm.py                  # 按需
```

新增迁移约定：复制现有脚本风格（psycopg2 直连 + savepoint 逐表回滚 + SKIP 跳过），放入 `scripts/migrations/YYYYMM/`，脚本内注明用途与幂等性。

## 测试流程

1. **用例管理**：创建测试用例，配置音频、参考参数、评估维度、干扰项（支持用例共用与分组）
2. **算法配置**：通过动态表单接入被测算法（HTTP/SSE/gRPC）
3. **设备管理**：扫描并注册被测设备（Android/HarmonyOS）与播放/环境设备
4. **任务执行**：
   - E2E：编排音频播放 → 设备自动化 → 录音采集 → 评估（支持重跑、重新评估、重新提取、任务合并）
   - API：多路并发调用被测接口 → 结果采集 → 评估
5. **报告对比**：任务级/用例级/标签级对比，时间轴说话人自动匹配

## 配置说明

主配置在 [.env](.env)（模板：[.env.example](.env.example)）。关键项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379` | Redis 地址 |
| `OSS_ENDPOINT` | `http://localhost:9000` | MinIO 地址 |
| `OSS_ACCESS_KEY` / `OSS_SECRET_KEY` | `minio` / `minio123` | MinIO 凭据 |
| `AUTH_MODE` | `off` | 认证模式：`dev`(本地OAuth) / `prod`(华为云OAuth) / `off`(无认证) |
| `DISTRIBUTED_COORDINATOR_ENABLED` | `true` | Redis 分布式锁/信号量，Redis 不可达自动降级 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 开发约定

- **后端 DDD 分层**：`interfaces/`（API/gRPC 路由）→ `application/`（用例编排）→ `domain/`（实体/事件/DTO）→ `infrastructure/`（持久化/适配器）
- **枚举化 / 配置化**：业务状态一律使用枚举（[shared/models/common_enums.py](shared/models/common_enums.py)），禁止魔法数字 / 魔法字符串
- **端口集中注册**：[shared/config/service_ports.py](shared/config/service_ports.py)，禁用散落硬编码
- **gRPC proto** 位于 [shared/proto/](shared/proto/)，修改后需重新生成 Python 桩代码（`grpc_tools.protoc`）
- **前端域分层**：`views/`（页面）+ `components/`（组件）→ `composables/` + `store/`（编排）→ `domain/model/` + `domain/enums.ts`（领域模型）→ `api/` + `dto/`（基础设施，唯一接触 snake_case 的层）
- **命名规范**：后端模型 `shared/models/`，DTO 命名采用 camelCase；前后端字段经 `keyTransform` 适配

## 目录导航

```
Intelligent-Audio-TEST/
├── api_gateway/            # API 网关（路由/WS/SSE/鉴权）
├── task_service/           # 任务执行引擎
├── e2e_test_service/       # 端到端测试
├── api_test_service/       # API 测试
├── evaluation_service/     # 评估维度
├── report_service/         # 报告生成
├── algorithm_service/      # 算法配置
├── api_adapter_service/    # 算法适配
├── auth_service/           # 认证 / RBAC
├── audio_service/          # 音频播放（gRPC-only）
├── device_service/         # 设备驱动（gRPC-only）
├── frontend/               # Vue3 + Electron
├── shared/                 # 跨服务共享：models / config / proto / clients
├── scripts/                # 建表、迁移、Seed 脚本
├── docker/                 # Docker 部署编排与镜像
├── docs/                   # 系统架构 / DDD / RBAC / OAuth 等设计文档
└── doc/                    # 功能设计文档（按模块分目录）
```

## 相关文档

- [系统架构](docs/系统架构.md) / [微服务](docs/微服务.md) / [DDD 重构](docs/DDD重构.md)
- [RBAC 权限划分](docs/RBAC权限划分.md) / [OAuth](docs/oauth.md) / [迁移验证报告](docs/迁移验证报告.md)
- [分布式协调器](docs/分布式协调器.md)
- [数据库设计](doc/数据库设计文档/数据库设计.md) / [数据库迁移文档](doc/数据库设计文档/数据库迁移文档.md)
- [后端设计文档](doc/总架构/后端设计文档.md) / [分布式部署文档](doc/总架构/分布式部署文档.md)
- [服务拆分方案](doc/总架构/服务拆分方案.md)
- [gRPC Proto 接口](shared/proto/README.md)
- [前端更新日志](frontend/docs/CHANGELOG.md)