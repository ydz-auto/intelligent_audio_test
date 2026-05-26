# 服务拆分与API测试功能开发计划

## 文档信息

| 项目 | 内容 |
|------|------|
| 版本 | v1.0 |
| 创建日期 | 2026-05-25 |
| 状态 | 规划阶段 |

---

## 1. 项目概述

### 1.1 目标

1. **服务拆分**: 将现有的单体后端服务拆分为微服务架构，提高可维护性和可扩展性
2. **API测试功能开发**: 完善API测试功能，支持多厂商API测试、中转站调用、结果对比分析

### 1.2 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 主服务后端 | ✅ 已实现 | Flask单体应用，功能完整 |
| 前端 | ✅ 已实现 | Vue3 + Electron |
| 适配器服务 | 🔶 基础框架 | 需要完善适配器实现 |
| API测试功能 | 🔶 部分实现 | 需要完善和调通 |

### 1.3 开发周期

**总周期: 4周**

| 阶段 | 内容 | 时间 |
|------|------|------|
| 阶段一 | 服务拆分设计与基础框架 | 第1周 |
| 阶段二 | 适配器服务完善 | 第2周 |
| 阶段三 | API测试功能开发 | 第3周 |
| 阶段四 | 集成测试与优化 | 第4周 |

---

## 2. 服务拆分方案

### 2.1 目标架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端应用 (Vue3 + Electron)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API网关 (Nginx / Kong)                          │
│                         统一入口、路由、限流、认证                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   主服务          │     │   适配器服务       │     │   评估服务        │
│   (core-service)  │     │   (adapter-service)│    │   (eval-service)  │
├───────────────────┤     ├───────────────────┤     ├───────────────────┤
│ - 用户管理        │     │ - API适配器        │     │ - 评估计算        │
│ - 任务管理        │     │ - 协议处理         │     │ - 结果分析        │
│ - 用例管理        │     │ - 厂商调用         │     │ - 报告生成        │
│ - 设备管理        │     │ - 结果标准化       │     │ - 数据统计        │
│ - 音频管理        │     │ - 健康监控         │     │                   │
│ - 报告管理        │     │                   │     │                   │
└───────────────────┘     └───────────────────┘     └───────────────────┘
        │                               │                               │
        └───────────────────────────────┼───────────────────────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │       PostgreSQL 数据库        │
                        │       Redis 缓存               │
                        └───────────────────────────────┘
```

### 2.2 服务拆分详情

#### 2.2.1 主服务

**职责**: 核心业务逻辑，数据管理

| 模块 | 功能 | 保留/迁移 |
|------|------|-----------|
| 用户管理 | 用户认证、权限管理 | 保留 |
| 任务管理 | 测试任务CRUD、状态管理 | 保留 |
| 用例管理 | 测试用例CRUD、分组管理 | 保留 |
| 设备管理 | 设备配置、驱动管理 | 保留 |
| 音频管理 | 音频上传、处理、存储 | 保留 |
| 报告管理 | 报告生成、查询、导出 | 保留 |
| API管理 | API配置CRUD | 保留 |
| **API调用** | API执行、结果收集 | **迁移到适配器服务** |
| **评估计算** | 评估指标计算 | **迁移到评估服务** |

**端口**: 5000

#### 2.2.2 适配器服务

**职责**: API调用、协议适配、厂商对接

| 模块 | 功能 | 说明 |
|------|------|------|
| 适配器工厂 | 创建适配器实例 | 根据vendor和api_type |
| ASR适配器 | 语音识别API调用 | 火山、阿里、OpenAI等 |
| AST适配器 | 语音翻译API调用 | 火山AST、通义千问等 |
| LLM适配器 | 大语言模型API调用 | GPT、Claude、Gemini等 |
| 协议处理 | HTTP/WebSocket/Protobuf | 协议转换 |
| 结果标准化 | 统一响应格式 | APIResponse |
| 健康监控 | API可用性检测 | 心跳检测 |

**端口**: 5001

#### 2.2.3 评估服务 - 可选

**职责**: 评估计算、结果分析

| 模块 | 功能 | 说明 |
|------|------|------|
| 评估计算 | ASR/翻译评估指标 | WER、BLEU等 |
| 结果分析 | 多API对比分析 | 性能对比 |
| 报告生成 | 测试报告生成 | PDF/HTML |

**端口**: 5002

### 2.3 服务间通信

| 通信方式 | 场景 | 说明 |
|----------|------|------|
| HTTP REST | 同步调用 | 主服务调用适配器服务 |
| WebSocket | 实时推送 | 测试进度、状态更新 |
| Redis Pub/Sub | 异步消息 | 任务状态变更通知 |
| 共享数据库 | 数据共享 | PostgreSQL |

---

## 3. 详细开发计划

### 3.1 阶段一: 服务拆分设计与基础框架 (第1周)

#### Day 1-2: 服务拆分设计

| 任务 | 说明 | 产出 |
|------|------|------|
| 确定拆分边界 | 明确各服务职责 | 服务拆分文档 |
| 设计API接口 | 服务间调用接口 | 接口文档 |
| 设计数据模型 | 共享数据结构 | 数据模型文档 |
| 配置管理方案 | 环境变量、配置文件 | 配置方案 |

#### Day 3-4: 适配器服务框架完善

| 任务 | 文件 | 说明 |
|------|------|------|
| 完善ExecutionConfig模型 | `models/execution_config.py` | 执行配置 |
| 完善APIResponse模型 | `models/api_response.py` | 响应模型 |
| 实现适配器基类 | `adapters/base/base_adapter.py` | 基础框架 |
| 实现ASR适配器基类 | `adapters/base/asr_adapter.py` | ASR基类 |
| 实现LLM适配器基类 | `adapters/base/llm_adapter.py` | LLM基类 |
| 实现适配器工厂 | `services/adapter_factory.py` | 工厂模式 |

#### Day 5: 主服务集成适配器服务

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建配置构建器 | `utils/execution_config_builder.py` | 构建配置 |
| 修改API Driver | `utils/api_driver.py` | 集成适配器 |
| 添加服务调用 | `utils/adapter_client.py` | HTTP调用适配器服务 |

---

### 3.2 阶段二: 适配器服务完善 (第2周)

#### Day 1-2: 国内厂商适配器

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 火山引擎ASR适配器 | `adapters/volcengine/volc_asr_adapter.py` | P0 |
| 火山引擎AST适配器 | `adapters/volcengine/volc_ast_adapter.py` | P0 |
| 阿里云百炼ASR适配器 | `adapters/aliyun/bailian_asr_adapter.py` | P0 |
| 通义千问AST适配器 | `adapters/aliyun/qwen_ast_adapter.py` | P1 |

#### Day 3-4: 海外厂商适配器

| 任务 | 文件 | 优先级 |
|------|------|--------|
| OpenAI适配器 | `adapters/openai/openai_adapter.py` | P1 |
| OpenAI Whisper适配器 | `adapters/openai/whisper_adapter.py` | P1 |
| Google Gemini适配器 | `adapters/google/gemini_adapter.py` | P2 |
| Azure Speech适配器 | `adapters/azure/azure_speech_adapter.py` | P2 |

#### Day 5: 适配器测试

| 任务 | 文件 | 说明 |
|------|------|------|
| 单元测试 | `tests/test_adapters.py` | 测试各适配器 |
| 集成测试 | `tests/test_adapter_service.py` | 端到端测试 |
| Mock测试 | `adapters/mock_adapter.py` | 完善Mock适配器 |

---

### 3.3 阶段三: API测试功能开发 (第3周)

#### Day 1-2: 后端API测试功能

| 任务 | 文件 | 说明 |
|------|------|------|
| API配置管理完善 | `controllers/api_controller.py` | CRUD完善 |
| API测试执行接口 | `controllers/api_test_controller.py` | 新增执行接口 |
| 测试任务管理 | `controllers/api_task_controller.py` | 任务状态管理 |
| 结果收集与存储 | `services/api_result_service.py` | 结果处理 |
| WebSocket进度推送 | `blueprints/api_ws_bp.py` | 实时推送 |

#### Day 3-4: 前端API测试页面

| 任务 | 文件 | 说明 |
|------|------|------|
| API管理页面 | `views/APITest/ApiManage.vue` | API配置管理 |
| 测试配置页面 | `views/APITest/TestConfig.vue` | 测试参数配置 |
| 测试执行页面 | `views/APITest/TestExecution.vue` | 执行监控 |
| 结果展示页面 | `views/APITest/TestResult.vue` | 结果分析 |
| 对比分析页面 | `views/APITest/Comparison.vue` | 多API对比 |

#### Day 5: API测试功能联调

| 任务 | 说明 |
|------|------|
| 前后端联调 | 接口对接 |
| WebSocket联调 | 实时通信 |
| 功能测试 | 端到端测试 |

---

### 3.4 阶段四: 集成测试与优化 (第4周)

#### Day 1-2: 集成测试

| 任务 | 说明 |
|------|------|
| 服务间通信测试 | 主服务↔适配器服务 |
| 端到端测试 | 完整测试流程 |
| 性能测试 | 并发、压力测试 |
| 异常场景测试 | 错误处理 |

#### Day 3-4: 优化与修复

| 任务 | 说明 |
|------|------|
| 性能优化 | 响应时间、并发处理 |
| Bug修复 | 测试发现的问题 |
| 代码重构 | 优化代码结构 |
| 文档完善 | API文档、部署文档 |

#### Day 5: 部署与交付

| 任务 | 说明 |
|------|------|
| 部署配置 | Docker、Nginx配置 |
| 环境配置 | 生产环境配置 |
| 功能验收 | 功能验收测试 |
| 文档交付 | 使用文档、开发文档 |

---

## 4. 任务清单

### 4.1 服务拆分任务

#### P0 - 必须完成

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| S1 | 完善ExecutionConfig模型 | `api_adaper_service/models/execution_config.py` | 待开发 |
| S2 | 完善APIResponse模型 | `api_adaper_service/models/api_response.py` | 待开发 |
| S3 | 实现适配器基类 | `api_adaper_service/adapters/base/base_adapter.py` | 待开发 |
| S4 | 实现适配器工厂 | `api_adaper_service/services/adapter_factory.py` | 待开发 |
| S5 | 创建配置构建器 | `backend/utils/execution_config_builder.py` | 待开发 |
| S6 | 修改API Driver集成适配器 | `backend/utils/api_driver.py` | 待开发 |

#### P1 - 重要

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| S7 | 服务健康检查接口 | `api_adaper_service/app/main.py` | 待开发 |
| S8 | 服务配置管理 | `api_adaper_service/config/` | 待开发 |
| S9 | 日志与监控 | `api_adaper_service/utils/logger.py` | 待开发 |
| S10 | 错误处理统一 | `api_adaper_service/utils/errors.py` | 待开发 |

### 4.2 适配器开发任务

#### P0 - 必须完成

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| A1 | 火山引擎ASR适配器 | `adapters/volcengine/volc_asr_adapter.py` | 待开发 |
| A2 | 阿里云百炼ASR适配器 | `adapters/aliyun/bailian_asr_adapter.py` | 待开发 |
| A3 | OpenAI适配器 | `adapters/openai/openai_adapter.py` | 待开发 |

#### P1 - 重要

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| A4 | 火山引擎AST适配器 | `adapters/volcengine/volc_ast_adapter.py` | 待开发 |
| A5 | 通义千问AST适配器 | `adapters/aliyun/qwen_ast_adapter.py` | 待开发 |
| A6 | OpenAI Whisper适配器 | `adapters/openai/whisper_adapter.py` | 待开发 |

#### P2 - 可选

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| A7 | Google Gemini适配器 | `adapters/google/gemini_adapter.py` | 待开发 |
| A8 | Azure Speech适配器 | `adapters/azure/azure_speech_adapter.py` | 待开发 |
| A9 | 腾讯云ASR适配器 | `adapters/tencent/tencent_asr_adapter.py` | 待开发 |
| A10 | 百度ASR适配器 | `adapters/baidu/baidu_asr_adapter.py` | 待开发 |

### 4.3 API测试功能任务

#### P0 - 必须完成

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| T1 | API测试执行接口 | `backend/controllers/api_test_controller.py` | 待开发 |
| T2 | 测试结果存储 | `backend/services/api_result_service.py` | 待开发 |
| T3 | WebSocket进度推送 | `backend/blueprints/api_ws_bp.py` | 待开发 |
| T4 | API管理页面 | `frontend/src/views/APITest/ApiManage.vue` | 待开发 |
| T5 | 测试执行页面 | `frontend/src/views/APITest/TestExecution.vue` | 待开发 |
| T6 | 结果展示页面 | `frontend/src/views/APITest/TestResult.vue` | 待开发 |

#### P1 - 重要

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| T7 | 测试配置页面 | `frontend/src/views/APITest/TestConfig.vue` | 待开发 |
| T8 | 对比分析页面 | `frontend/src/views/APITest/Comparison.vue` | 待开发 |
| T9 | API健康监控 | `backend/services/api_health_service.py` | 待开发 |
| T10 | 测试报告生成 | `backend/services/api_report_service.py` | 待开发 |

---

## 5. 技术要点

### 5.1 服务拆分关键技术

| 技术点 | 说明 | 实现方式 |
|--------|------|----------|
| 配置传递 | 主服务构建配置传递给适配器 | ExecutionConfig |
| 服务发现 | 服务间调用地址管理 | 环境变量/配置中心 |
| 错误处理 | 统一错误码和错误信息 | 自定义异常类 |
| 日志追踪 | 跨服务请求追踪 | request_id |
| 超时控制 | 服务调用超时管理 | requests timeout |

### 5.2 适配器关键技术

| 技术点 | 说明 | 实现方式 |
|--------|------|----------|
| 协议处理 | HTTP/WebSocket/Protobuf | 协议处理器 |
| 认证管理 | 多种认证方式 | 凭据管理 |
| 代理支持 | 海外API代理 | requests proxies |
| 结果解析 | 响应字段映射 | JSONPath |
| 时延统计 | 首字/尾字时延 | 时间戳记录 |

### 5.3 API测试关键技术

| 技术点 | 说明 | 实现方式 |
|--------|------|----------|
| 并发控制 | 并发请求管理 | asyncio.Semaphore |
| 实时推送 | 测试进度推送 | WebSocket |
| 结果存储 | 测试结果持久化 | PostgreSQL |
| 评估计算 | 准确率计算 | 评估算法 |
| 报告生成 | 测试报告 | PDF/HTML |

---

## 6. 风险与应对

### 6.1 技术风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 火山引擎Protobuf协议复杂 | 高 | 参考现有demo代码，逐步实现 |
| 服务间通信延迟 | 中 | 使用异步调用，优化接口设计 |
| 海外API代理不稳定 | 中 | 实现重试机制，支持多代理切换 |
| 并发性能瓶颈 | 中 | 使用连接池，优化数据库查询 |

### 6.2 进度风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 适配器开发工作量超预期 | 高 | 优先实现P0任务，P2任务可延后 |
| 前端页面开发延迟 | 中 | 使用现有组件，快速搭建 |
| 集成测试问题多 | 中 | 预留缓冲时间，提前测试 |

---

## 7. 验收标准

### 7.1 服务拆分验收

- [ ] 适配器服务可独立启动运行
- [ ] 主服务可调用适配器服务
- [ ] 配置正确传递给适配器
- [ ] 错误处理正确返回
- [ ] 日志完整记录

### 7.2 适配器验收

- [ ] 火山引擎ASR适配器可正常调用
- [ ] 阿里云百炼ASR适配器可正常调用
- [ ] OpenAI适配器可正常调用（直连和中转站）
- [ ] 结果格式统一
- [ ] 时延统计准确

### 7.3 API测试功能验收

- [ ] API配置管理功能正常
- [ ] 测试执行功能正常
- [ ] WebSocket进度推送正常
- [ ] 结果展示正确
- [ ] 多API对比功能正常

---

## 8. 附录

### 8.1 文件结构

```
Intelligent-Audio-TEST/
├── backend/                          # 主服务
│   ├── controllers/
│   │   ├── api_controller.py         # API配置管理
│   │   └── api_test_controller.py    # API测试执行 (新增)
│   ├── utils/
│   │   ├── api_driver.py             # API驱动 (修改)
│   │   ├── execution_config_builder.py # 配置构建器 (新增)
│   │   └── adapter_client.py         # 适配器客户端 (新增)
│   └── ...
│
├── api_adaper_service/               # 适配器服务
│   ├── adapters/
│   │   ├── base/                     # 基类
│   │   ├── volcengine/               # 火山引擎
│   │   ├── aliyun/                   # 阿里云
│   │   └── openai/                   # OpenAI
│   ├── models/
│   │   ├── execution_config.py       # 执行配置
│   │   └── api_response.py           # 响应模型
│   ├── services/
│   │   └── adapter_factory.py        # 适配器工厂
│   └── app/
│       └── main.py                   # 服务入口
│
└── frontend/
    └── src/
        └── views/
            └── APITest/              # API测试页面
                ├── ApiManage.vue
                ├── TestConfig.vue
                ├── TestExecution.vue
                ├── TestResult.vue
                └── Comparison.vue
```

### 8.2 接口清单

#### 适配器服务接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/execute` | POST | 执行API调用 |
| `/api/health` | GET | 健康检查 |
| `/api/adapters` | GET | 获取适配器列表 |
| `/api/adapters/{vendor}/{type}` | GET | 获取适配器信息 |

#### 主服务API测试接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/apis` | GET/POST | API配置管理 |
| `/api/apis/{id}` | GET/PUT/DELETE | 单个API管理 |
| `/api/apis/{id}/test` | POST | 测试API连接 |
| `/api/test/execute` | POST | 执行API测试 |
| `/api/test/tasks` | GET | 获取测试任务列表 |
| `/api/test/results/{task_id}` | GET | 获取测试结果 |
