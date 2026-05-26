# 服务拆分与API测试功能开发计划

## 文档信息

| 项目 | 内容 |
|------|------|
| 版本 | v2.0 |
| 创建日期 | 2026-05-25 |
| 状态 | 规划阶段 |
| 参考文档 | [服务拆分方案.md](../总架构/服务拆分方案.md) |

---

## 1. 项目概述

### 1.1 目标架构 (四层微服务)

根据现有服务拆分方案，目标架构如下：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端应用 (Vue3 + Electron)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        API Gateway (5000)                                    │
│   职责：HTTP 路由、认证、限流、WebSocket 代理、静态文件服务                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Task Service (5001)                                   │
│   职责：任务调度、分发、进度管理、结果汇总                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                              │
                    │ gRPC                         │ HTTP
                    ▼                              ▼
         ┌─────────────────────────┐    ┌─────────────────────────┐
         │   E2E Test Service      │    │    API Test Service     │
         │     (5002/50051)        │    │       (5003)            │
         │                         │    │                         │
         │  需要物理设备            │    │  不需要物理设备          │
         │  设备驱动、音频播放       │    │  API适配器、并发测试     │
         └─────────────────────────┘    └─────────────────────────┘
                                        │
                                        ▼
                            ┌─────────────────────────┐
                            │   Evaluation Service    │
                            │        (5004)           │
                            │   评估计算、报告生成     │
                            └─────────────────────────┘
```

### 1.2 当前状态

| 服务 | 状态 | 说明 |
|------|------|------|
| API Gateway | ✅ 已实现 | Flask单体应用，需拆分 |
| Task Service | 🔶 部分实现 | 需从主服务拆分 |
| E2E Test Service | 🔶 部分实现 | 需从主服务拆分 |
| **API Test Service** | 🔶 基础框架 | **api_adaper_service需整合** |
| Evaluation Service | ✅ 已实现 | 可独立部署或合并 |

### 1.3 开发周期

**总周期: 4周**

| 阶段 | 内容 | 时间 |
|------|------|------|
| 阶段一 | 服务拆分实施 | 第1周 |
| 阶段二 | API Test Service完善 | 第2周 |
| 阶段三 | API测试功能开发 | 第3周 |
| 阶段四 | 集成测试与优化 | 第4周 |

---

## 2. 阶段一: 服务拆分实施 (第1周)

### 2.1 Day 1-2: 服务注册与发现

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建服务注册表 | `models/models.py` | ServiceRegistry模型 |
| 实现服务发现 | `shared/utils/service_discovery.py` | 服务发现与负载均衡 |
| 实现服务管理API | `blueprints/service_bp.py` | 服务CRUD、心跳 |
| 实现健康检查 | 各服务 `/internal/health` | 健康检查接口 |

### 2.2 Day 3-4: 服务拆分

| 任务 | 源文件 | 目标位置 | 说明 |
|------|--------|----------|------|
| **拆分API Gateway** | `app.py` | `api_gateway/` | 保留路由、认证、限流 |
| **拆分Task Service** | `execution_engine.py` | `task_service/` | 任务调度、分发 |
| **拆分E2E Test Service** | `e2e_executor.py`, `device_driver/` | `e2e_test_service/` | 设备驱动、音频播放 |
| **整合API Test Service** | `api_executor.py`, `api_adaper_service/` | `api_test_service/` | API测试执行 |

### 2.3 Day 5: 服务间通信

| 任务 | 说明 |
|------|------|
| gRPC接口定义 | E2E Test Service gRPC接口 |
| HTTP客户端封装 | Task Service调用API Test Service |
| WebSocket聚合 | API Gateway聚合各服务推送 |
| Redis Pub/Sub | 进度推送、日志推送 |

---

## 3. 阶段二: API Test Service完善 (第2周)

### 3.1 API Test Service架构

```
api_test_service/
├── app/
│   ├── main.py                    # Flask入口
│   └── config.py                  # 配置
├── core/
│   ├── api_executor.py            # API执行器
│   ├── api_driver.py              # API驱动
│   ├── api_client.py              # API客户端
│   ├── concurrent_controller.py   # 并发控制器 (新增)
│   └── health_monitor.py          # 健康监控 (新增)
├── adapters/                       # 从api_adaper_service整合
│   ├── base/
│   │   ├── base_adapter.py
│   │   ├── asr_adapter.py
│   │   └── llm_adapter.py
│   ├── volcengine/
│   │   ├── volc_asr_adapter.py
│   │   └── volc_ast_adapter.py
│   ├── aliyun/
│   │   ├── bailian_asr_adapter.py
│   │   └── qwen_ast_adapter.py
│   └── openai/
│       ├── openai_adapter.py
│       └── whisper_adapter.py
├── models/
│   ├── execution_config.py
│   └── api_response.py
├── services/
│   ├── adapter_factory.py
│   └── task_manager.py
├── blueprints/
│   ├── execute_bp.py              # 执行接口
│   └── health_bp.py               # 健康检查
└── requirements.txt
```

### 3.2 Day 1-2: 适配器框架完善

| 任务 | 文件 | 优先级 |
|------|------|--------|
| ExecutionConfig模型 | `models/execution_config.py` | P0 |
| APIResponse模型 | `models/api_response.py` | P0 |
| 适配器基类 | `adapters/base/base_adapter.py` | P0 |
| ASR适配器基类 | `adapters/base/asr_adapter.py` | P0 |
| LLM适配器基类 | `adapters/base/llm_adapter.py` | P0 |
| 适配器工厂 | `services/adapter_factory.py` | P0 |

### 3.3 Day 3-4: 核心适配器实现

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 火山引擎ASR适配器 | `adapters/volcengine/volc_asr_adapter.py` | P0 |
| 阿里云百炼ASR适配器 | `adapters/aliyun/bailian_asr_adapter.py` | P0 |
| OpenAI适配器 | `adapters/openai/openai_adapter.py` | P0 |
| 火山引擎AST适配器 | `adapters/volcengine/volc_ast_adapter.py` | P1 |
| 通义千问AST适配器 | `adapters/aliyun/qwen_ast_adapter.py` | P1 |

### 3.4 Day 5: 服务接口实现

| 任务 | 文件 | 说明 |
|------|------|------|
| 执行接口 | `blueprints/execute_bp.py` | POST /execute |
| 健康检查 | `blueprints/health_bp.py` | GET /internal/health |
| 适配器列表 | `blueprints/execute_bp.py` | GET /adapters |
| 心跳上报 | `app/main.py` | 定时心跳到API Gateway |

---

## 4. 阶段三: API测试功能开发 (第3周)

### 4.1 Day 1-2: 后端API测试功能

| 任务 | 文件 | 说明 |
|------|------|------|
| API配置管理完善 | `api_gateway/controllers/api_controller.py` | CRUD完善 |
| API测试执行接口 | `api_gateway/controllers/api_test_controller.py` | 新增 |
| 测试任务管理 | `task_service/controllers/task_controller.py` | 任务状态管理 |
| 结果收集与存储 | `task_service/services/result_service.py` | 结果处理 |
| WebSocket进度推送 | `api_gateway/blueprints/ws_bp.py` | 实时推送 |

### 4.2 Day 3-4: 前端API测试页面

| 任务 | 文件 | 说明 |
|------|------|------|
| API管理页面 | `views/APITest/ApiManage.vue` | API配置管理 |
| 测试配置页面 | `views/APITest/TestConfig.vue` | 测试参数配置 |
| 测试执行页面 | `views/APITest/TestExecution.vue` | 执行监控 |
| 结果展示页面 | `views/APITest/TestResult.vue` | 结果分析 |
| 对比分析页面 | `views/APITest/Comparison.vue` | 多API对比 |

### 4.3 Day 5: 功能联调

| 任务 | 说明 |
|------|------|
| 前后端联调 | 接口对接 |
| WebSocket联调 | 实时通信 |
| 功能测试 | 端到端测试 |

---

## 5. 阶段四: 集成测试与优化 (第4周)

### 5.1 Day 1-2: 集成测试

| 任务 | 说明 |
|------|------|
| 服务间通信测试 | API Gateway ↔ Task Service ↔ API Test Service |
| gRPC通信测试 | Task Service ↔ E2E Test Service |
| 端到端测试 | 完整测试流程 |
| 性能测试 | 并发、压力测试 |

### 5.2 Day 3-4: 优化与修复

| 任务 | 说明 |
|------|------|
| 性能优化 | 响应时间、并发处理 |
| Bug修复 | 测试发现的问题 |
| 代码重构 | 优化代码结构 |
| 文档完善 | API文档、部署文档 |

### 5.3 Day 5: 部署与交付

| 任务 | 说明 |
|------|------|
| Docker配置 | 各服务Dockerfile |
| Docker Compose | 本地开发环境 |
| 部署文档 | 部署指南 |
| 功能验收 | 功能验收测试 |

---

## 6. 详细任务清单

### 6.1 服务拆分任务 (阶段一)

| ID | 任务 | 服务 | 优先级 | 状态 |
|----|------|------|--------|------|
| S1 | 创建ServiceRegistry模型 | 共享 | P0 | 待开发 |
| S2 | 实现服务发现模块 | 共享 | P0 | 待开发 |
| S3 | 实现服务管理API | API Gateway | P0 | 待开发 |
| S4 | 拆分API Gateway | API Gateway | P0 | 待开发 |
| S5 | 拆分Task Service | Task Service | P0 | 待开发 |
| S6 | 拆分E2E Test Service | E2E Test Service | P1 | 待开发 |
| S7 | 整合API Test Service | API Test Service | P0 | 待开发 |
| S8 | gRPC接口定义 | E2E Test Service | P1 | 待开发 |
| S9 | WebSocket聚合 | API Gateway | P1 | 待开发 |

### 6.2 API Test Service任务 (阶段二)

| ID | 任务 | 文件 | 优先级 | 状态 |
|----|------|------|--------|------|
| A1 | ExecutionConfig模型 | `models/execution_config.py` | P0 | 待开发 |
| A2 | APIResponse模型 | `models/api_response.py` | P0 | 待开发 |
| A3 | 适配器基类 | `adapters/base/base_adapter.py` | P0 | 待开发 |
| A4 | 适配器工厂 | `services/adapter_factory.py` | P0 | 待开发 |
| A5 | 火山引擎ASR适配器 | `adapters/volcengine/volc_asr_adapter.py` | P0 | 待开发 |
| A6 | 阿里云百炼ASR适配器 | `adapters/aliyun/bailian_asr_adapter.py` | P0 | 待开发 |
| A7 | OpenAI适配器 | `adapters/openai/openai_adapter.py` | P0 | 待开发 |
| A8 | 火山引擎AST适配器 | `adapters/volcengine/volc_ast_adapter.py` | P1 | 待开发 |
| A9 | 通义千问AST适配器 | `adapters/aliyun/qwen_ast_adapter.py` | P1 | 待开发 |
| A10 | 并发控制器 | `core/concurrent_controller.py` | P1 | 待开发 |
| A11 | 健康监控 | `core/health_monitor.py` | P2 | 待开发 |

### 6.3 API测试功能任务 (阶段三)

| ID | 任务 | 文件 | 优先级 | 状态 |
|----|------|------|--------|------|
| T1 | API测试执行接口 | `api_gateway/controllers/api_test_controller.py` | P0 | 待开发 |
| T2 | 测试结果存储 | `task_service/services/result_service.py` | P0 | 待开发 |
| T3 | WebSocket进度推送 | `api_gateway/blueprints/ws_bp.py` | P0 | 待开发 |
| T4 | API管理页面 | `views/APITest/ApiManage.vue` | P0 | 待开发 |
| T5 | 测试执行页面 | `views/APITest/TestExecution.vue` | P0 | 待开发 |
| T6 | 结果展示页面 | `views/APITest/TestResult.vue` | P0 | 待开发 |
| T7 | 测试配置页面 | `views/APITest/TestConfig.vue` | P1 | 待开发 |
| T8 | 对比分析页面 | `views/APITest/Comparison.vue` | P1 | 待开发 |

---

## 7. 服务端口规划

| 服务 | HTTP端口 | gRPC端口 | 说明 |
|------|----------|----------|------|
| API Gateway | 5000 | - | 统一入口 |
| Task Service | 5001 | - | 任务调度 |
| E2E Test Service | 5002 | 50051 | 设备测试 |
| **API Test Service** | **5003** | - | **API测试** |
| Evaluation Service | 5004 | - | 评估计算 |

---

## 8. 服务间通信

| 通信场景 | 方式 | 说明 |
|---------|------|------|
| 前端 → API Gateway | HTTP/WebSocket | 统一入口 |
| API Gateway → Task Service | HTTP REST | 任务启动/控制/查询 |
| Task Service → E2E Test Service | gRPC | 设备控制、音频播放 |
| **Task Service → API Test Service** | **HTTP REST** | **API测试执行** |
| Task Service → Evaluation Service | HTTP REST | 评估计算 |
| 各服务 → 前端 | WebSocket (via Redis Pub/Sub) | 进度推送 |

---

## 9. 验收标准

### 9.1 服务拆分验收

- [ ] 各服务可独立启动运行
- [ ] 服务注册与发现正常
- [ ] 服务间通信正常
- [ ] WebSocket推送正常
- [ ] 健康检查正常

### 9.2 API Test Service验收

- [ ] 火山引擎ASR适配器可正常调用
- [ ] 阿里云百炼ASR适配器可正常调用
- [ ] OpenAI适配器可正常调用（直连和中转站）
- [ ] 结果格式统一
- [ ] 时延统计准确

### 9.3 API测试功能验收

- [ ] API配置管理功能正常
- [ ] 测试执行功能正常
- [ ] WebSocket进度推送正常
- [ ] 结果展示正确
- [ ] 多API对比功能正常

---

## 10. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 服务拆分工作量大 | 高 | 优先拆分核心功能，非核心功能延后 |
| gRPC协议复杂 | 中 | 参考现有方案，逐步实现 |
| 适配器开发超预期 | 中 | 优先P0任务，P2任务可延后 |
| 服务间通信延迟 | 中 | 使用异步调用，优化接口设计 |

---

## 11. 附录

### 11.1 目录结构

```
Intelligent-Audio-TEST/
├── api_gateway/                     # API Gateway (5000)
│   ├── app.py
│   ├── blueprints/
│   ├── controllers/
│   ├── middleware/
│   └── services/
│
├── task_service/                    # Task Service (5001)
│   ├── app/
│   ├── core/
│   ├── clients/
│   └── evaluation/
│
├── e2e_test_service/                # E2E Test Service (5002/50051)
│   ├── app/
│   ├── core/
│   ├── drivers/
│   ├── audio/
│   └── grpc/
│
├── api_test_service/                # API Test Service (5003)
│   ├── app/
│   ├── core/
│   ├── adapters/                    # 从api_adaper_service整合
│   ├── models/
│   ├── services/
│   └── blueprints/
│
├── evaluation_service/              # Evaluation Service (5004)
│   ├── app/
│   └── core/
│
├── shared/                          # 共享模块
│   ├── models/
│   ├── utils/
│   └── schemas/
│
└── frontend/
    └── src/
        └── views/
            └── APITest/
```

### 11.2 API接口清单

#### API Test Service接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/execute` | POST | 执行API调用 |
| `/internal/health` | GET | 健康检查 |
| `/adapters` | GET | 获取适配器列表 |
| `/adapters/{vendor}/{type}` | GET | 获取适配器信息 |

#### Task Service调用API Test Service

```python
# task_service/clients/api_test_client.py

class APITestClient:
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"
    
    def execute(self, execution_config: dict) -> dict:
        """执行API测试"""
        response = requests.post(
            f"{self.base_url}/execute",
            json=execution_config,
            timeout=60
        )
        return response.json()
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            response = requests.get(
                f"{self.base_url}/internal/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
```
