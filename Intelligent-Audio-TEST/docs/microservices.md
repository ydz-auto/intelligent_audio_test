# 微服务架构

## 概览

系统由 5 个微服务 + 3 个基础设施组件组成，通过 gRPC 通信，Redis 做服务注册与发现。

```
                    ┌─────────────┐
                    │ api_gateway │ :5000
                    └──────┬──────┘
              gRPC          │          gRPC
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌────────────────┐
│ task_service │  │e2e_test_svc  │  │api_test_service│
│   :5001     │  │   :5002      │  │    :5003       │
│  :50061 grpc│  │  :50051 grpc │  │   :50071 grpc  │
└──────┬───────┘  └──────────────┘  └───────┬────────┘
       │ gRPC                              │ gRPC
       ▼                                   ▼
┌──────────────────┐              ┌────────────────────┐
│api_adapter_service│              │   基础设施          │
│      :8000       │              │ PostgreSQL :5432    │
└──────────────────┘              │ Redis      :6379   │
                                  │ MinIO      :9000   │
                                  └────────────────────┘
```

## 服务列表

| 服务 | HTTP 端口 | gRPC 端口 | 说明 |
|---|---|---|---|
| **api_gateway** | 5000 | — | 前端入口，REST API，转发请求到后端服务 |
| **task_service** | 5001 | 50061 | 任务调度引擎，创建/启动/停止/暂停任务，评估 |
| **e2e_test_service** | 5002 | 50051 | 端到端测试，设备驱动/音频播放/结果采集 |
| **api_test_service** | 5003 | 50071 | API 接口测试，并发控制 |
| **api_adapter_service** | 8000 | — | 语音 LLM 适配层 |

## 基础设施

| 组件 | 端口 | 用途 |
|---|---|---|
| PostgreSQL 15 | 5432 | 业务数据库（任务、用例、设备、结果） |
| Redis 7 | 6379 | 服务注册/发现、日志 pubsub、分布式协调 |
| MinIO | 9000/9001 | 对象存储（音频、结果、报告、归档） |

## 服务间通信

所有跨服务调用走 gRPC，proto 定义在 [shared/proto/](../shared/proto/)：

| 调用方 → 被调方 | RPC | 用途 |
|---|---|---|
| api_gateway → task_service | StartTask / StopTask / PauseTask / ResumeTask | 任务控制 |
| task_service → e2e_test_service | AudioService / DeviceService / PlaybackService | E2E 测试编排 |
| task_service → api_test_service | APITestService | API 测试调度 |
| api_test_service → api_adapter_service | HTTP | 调用语音 LLM |

gRPC 客户端工厂：[shared/clients/grpc_clients.py](../shared/clients/grpc_clients.py)，`lru_cache` 复用 channel。

## 服务注册与发现

[shared/utils/service_registry.py](../shared/utils/service_registry.py)

- 启动时注册到 Redis Set `service:set:{service_name}`
- 心跳 15s TTL，超时自动剔除
- 调用方从 Redis 获取可用实例列表

## 多实例部署

同一服务起多个实例，用不同端口：

### 本地多实例

```powershell
# task_service 实例 A
$env:PORT="5001"; $env:GRPC_PORT="50061"; $env:DISTRIBUTED_COORDINATOR_ENABLED="true"
python -m uvicorn task_service.app:app --port 5001

# task_service 实例 B
$env:PORT="50011"; $env:GRPC_PORT="500611"
python -m uvicorn task_service.app:app --port 50011
```

### Docker 多实例

[docker/docker-compose.yml](../docker/docker-compose.yml) 中 `deploy.replicas` 控制：

```yaml
api_test_service:
  deploy:
    replicas: 2
```

多实例需开启分布式协调：`DISTRIBUTED_COORDINATOR_ENABLED=true`

## 配置

所有配置通过环境变量，参考 [.env.example](../.env.example)。

关键配置项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL 连接串（必填） |
| `REDIS_URL` | redis://localhost:6379 | Redis 连接串 |
| `OSS_ENDPOINT` | http://localhost:9000 | MinIO 地址 |
| `PORT` | 服务各自默认 | HTTP 端口 |
| `GRPC_PORT` | 服务各自默认 | gRPC 端口 |
| `DISTRIBUTED_COORDINATOR_ENABLED` | false | 多实例开关 |
| `E2E_TEST_SERVICE_HOST` | localhost | 服务发现地址 |
| `TASK_SERVICE_HOST` | localhost | 服务发现地址 |
| `API_TEST_SERVICE_HOST` | localhost | 服务发现地址 |

## Docker 部署

```bash
cd Intelligent-Audio-TEST/docker
docker compose up -d
```

Dockerfile 按服务分离：[docker/](../docker/) 目录下每个服务一个 `Dockerfile.{service_name}`。

## 目录结构

```
Intelligent-Audio-TEST/
├── api_gateway/          # 前端 API 网关
├── task_service/         # 任务调度引擎
├── e2e_test_service/     # 端到端测试服务
├── api_test_service/     # API 接口测试服务
├── api_adapter_service/  # 语音 LLM 适配层
├── shared/               # 共享层
│   ├── infrastructure/   #   基类、配置、gRPC 拦截器
│   ├── clients/           #   gRPC 客户端工厂
│   ├── models/            #   数据模型
│   ├── proto/             #   protobuf 定义
│   └── utils/             #   工具（日志、Redis、分布式协调器）
├── docker/                # Docker 配置
└── .env.example           # 配置模板
```
