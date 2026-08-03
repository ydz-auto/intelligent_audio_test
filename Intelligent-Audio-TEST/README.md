# Intelligent-Audio-TEST 智能语音测试系统

专业的端到端语音测试与 API 测试解决方案，基于 **微服务 + Electron + Vue 3 + Flask + PostgreSQL** 技术栈构建，支持多维度语音评估，提供完整的测试任务管理、报告分析功能。

## 目录

- [系统架构](#系统架构)
- [核心功能](#核心功能)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [部署](#部署)
- [文档](#文档)

## 系统架构

系统采用 **微服务架构**，由网关层、调度层、执行层、评估层四层服务组成，服务间通过 gRPC/HTTP 通信。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Electron 桌面应用                                   │
│         Vue 3 + TypeScript + Pinia + Vue Router + Vite                        │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │ RESTful API / WebSocket
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       API Gateway  (:5000)                                    │
│   HTTP 路由 · WebSocket 代理 · 服务发现 · 静态资源                            │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │ HTTP / gRPC
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ Task Service │     │ E2E Service  │     │ API Test Service │
│  (:5001)     │     │  (:5002)     │     │    (:5003)       │
│  调度/分发    │────▶│  端到端测试   │     │  API 测试        │
└──────┬───────┘     └──────────────┘     └──────────────────┘
       │ gRPC (:50061/:50051)
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       外部协作服务                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ eval_server  │  │ asr_server   │  │api_adapter_  │  │  PostgreSQL  │   │
│  │ 评估计算      │  │ ASR 推理      │  │ service      │  │  Redis       │   │
│  │  (:5000)     │  │  (:10095)    │  │  (:8000)     │  │  MinIO/S3    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 服务组件

| 服务 | 端口 | 职责 |
|------|------|------|
| **API Gateway** | 5000 | HTTP 路由、WebSocket 代理、服务发现、静态文件 |
| **Task Service** | 5001 / 50061 (gRPC) | 任务调度、分发、进度管理、结果汇总、评估分发 |
| **E2E Test Service** | 5002 / 50051 (gRPC) | 端到端测试执行、设备驱动、音频播放、SPL 映射 |
| **API Test Service** | 5003 / 50071 (gRPC) | API 测试执行、并发控制、健康监控 |
| **API Adapter Service** | 8000 | 适配不同厂商的 API 协议（voice_llm HTTP/SSE） |
| **eval_server** | 5000 | 评估计算（WER/SER/DER/LLM Judge/小艺指标） |
| **asr_server** | 10095 | 独立 ASR 推理服务（ModelScope Paraformer） |

### 基础设施

| 组件 | 用途 |
|------|------|
| PostgreSQL 15+ | 主数据库（用例、任务、设备、算法配置等） |
| Redis 7+ | 消息队列、缓存、Pub/Sub 进度推送 |
| MinIO / S3 | 对象存储（音频、报告、参考参数、归档） |

## 核心功能

### 1. 端到端测试（E2E Test）

在真实 Android/鸿蒙设备上执行端到端语音测试，模拟真实用户场景。

- **多设备并行测试**：同时在多台设备运行相同用例
- **五步测试流程**：选算法 → 选用例 → 选设备 → 执行测试 → 查看结果
- **多场景模拟**：不同角度/距离/声压；抢话、干扰人等复杂多说话人场景
- **动态时间戳偏移**：自动调整标注时间轴，确保评估准确
- **Speaker 感知交叠播放**：智能判断说话人重叠，还原真实多说话人场景
- **设备级同步播放**：多设备同时开始播放，精确的播放时序控制

### 2. API 测试

测试语音识别和翻译等 API 的性能与准确率。

- 批量测试执行、并发控制、响应时间监控
- 多维度对比不同 API 服务商效果
- 健康状态实时监控

### 3. 音频管理

- 多途径导入：本地上传、URL 导入、文件夹批量导入
- 多格式支持：MP3、WAV、FLAC、AAC
- 音频标注：RTTM/STM 等 diarization 标注格式
- 参考参数生成：基于策略模式，支持 ASR、翻译、TTS、说话人识别等

### 4. 测试用例管理

- 分组管理（唤醒词、命令识别、语音识别、多轮对话）
- 标签系统、批量操作、快速搜索
- 参考参数配置、重叠播放配置

### 5. 任务管理

- 多维筛选（时间、状态、类型、算法）
- 任务控制（启动、暂停、停止、重试、重新评估）
- 任务合并对比分析

### 6. 评估系统

- ASR 准确率：字错率、词错率、句错误率
- 翻译质量：COMET 等评分
- 说话人分离：DER
- LLM 语义评分：LLM Judge
- 小艺指标：接话率、误接管率、接管时延
- 自定义规则与第三方 API 扩展

### 7. 设备管理

- Android（ADB）/ 鸿蒙（HDC）设备连接
- 播放设备：声卡通道选择，采样率配置
- 设备分组、状态监控

### 8. 声压级映射

- 增益曲线配置、多节点校准、实时声压计算

### 9. 报告管理

- 详细报告查看、跨任务对比
- 多格式导出、数据可视化（准确率曲线、正态分布、对比图表）

## 项目结构

```
Intelligent-Audio-TEST/
├── api_gateway/              # API 网关（HTTP 路由、WebSocket 代理）
│   ├── controllers/          # 控制器层
│   ├── routes/               # 蓝图路由
│   ├── schemas/              # Pydantic Schema
│   └── websocket/           # WebSocket 连接管理
├── task_service/             # 任务调度服务
│   ├── core/                 # 执行引擎、重新评估
│   ├── evaluation/           # 评估服务（分发、API 客户端、结果处理）
│   └── grpc/                 # gRPC 服务
├── e2e_test_service/         # E2E 测试服务
│   ├── audio/                # 音频引擎、播放编排
│   ├── core/                 # E2E 执行器、结果聚合
│   ├── device/               # 设备结果采集、时间戳对齐
│   ├── drivers/              # 设备驱动（Android/鸿蒙）
│   └── env_device/           # 环境设备（导轨、Modbus）
├── api_test_service/         # API 测试服务
│   ├── clients/              # API 客户端、负载均衡
│   ├── core/                 # API 执行器、并发管理、会话执行
│   └── grpc/                 # gRPC 服务
├── api_adapter_service/      # API 适配服务（厂商协议适配）
│   ├── adapters/             # HTTP/SSE/Mock/Qwen/Volc 适配器
│   ├── grpc/                 # gRPC 服务
│   └── services/             # 会话存储、任务管理
├── shared/                   # 跨服务共享层
│   ├── proto/                # gRPC proto 定义
│   └── ...
├── frontend/                 # 前端（Electron + Vue 3）
│   ├── src/                  # 源码
│   ├── electron-main.ts      # Electron 主进程
│   └── package.json
├── doc/                      # 设计文档、接口文档、开发计划
├── docs/                     # 补充文档
├── scripts/                  # 脚本
├── docker-compose.yml        # Docker Compose 编排
├── Dockerfile.*              # 各服务 Dockerfile
└── .env.example              # 环境变量示例
```

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 桌面框架 | Electron 31.x |
| 前端框架 | Vue 3 + TypeScript |
| 构建工具 | Vite 5.x |
| 状态管理 | Pinia 3.x |
| 后端框架 | Flask 3.x + SQLAlchemy 2.x |
| 数据库 | PostgreSQL 15+ |
| 实时通信 | Flask-SocketIO + WebSocket |
| 对象存储 | MinIO / S3 |
| 设备连接 | ADB (Android) / HDC (鸿蒙) |
| 服务间通信 | gRPC + HTTP REST |
| 容器化 | Docker + Docker Compose |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+
- ffmpeg（音频处理）
- Android SDK Platform Tools（ADB，E2E 测试）
- HDC（鸿蒙设备连接，E2E 测试）

### 1. 克隆仓库

```bash
git clone <repo-url>
cd Intelligent-Audio-TEST
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并按需修改：

```bash
cp .env.example .env
```

关键配置项：

```env
DATABASE_URL=postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test
OSS_ACCESS_KEY=minio
OSS_SECRET_KEY=minio123
REDIS_URL=redis://localhost:6379
OSS_ENDPOINT=http://localhost:9000
```

### 3. 启动基础设施

使用 Docker Compose 启动 PostgreSQL、Redis、MinIO：

```bash
docker-compose up -d postgres redis minio minio-init
```

### 4. 启动后端服务

每个服务在各自目录下启动（先在项目根目录安装依赖 `pip install -r requirements.txt`）：

```bash
# API Gateway (端口 5000)
cd api_gateway && python app.py

# Task Service (端口 5001, gRPC 50061)
cd task_service && python app.py

# E2E Test Service (端口 5002, gRPC 50051)
cd e2e_test_service && python app.py

# API Test Service (端口 5003, gRPC 50071)
cd api_test_service && python app.py

# API Adapter Service (端口 8000)
cd api_adapter_service && python run.py
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev          # 开发模式
# 或
npm run electron:dev  # Electron 桌面应用
```

### 6. Docker 一键部署

```bash
docker-compose up -d
```

## 部署

支持三种部署模式：

| 模式 | 适用场景 | 服务器数量 |
|------|---------|-----------|
| 单机部署 | 开发测试 | 1 |
| 标准分布式 | 多数生产环境 | 3 |
| 高性能分布式 | 大规模、高并发 | 4+ |

详细部署方案见 [分布式部署文档](doc/总架构/分布式部署文档.md) 和 [Ubuntu+Docker部署方案](doc/部署文档/Ubuntu+Docker+Nginx部署方案.md)。

## 文档

### 架构与设计

| 文档 | 内容 |
|------|------|
| [项目介绍](doc/总架构/项目介绍.md) | 产品概述、核心功能、系统架构 |
| [后端设计文档](doc/总架构/后端设计文档.md) | 后端架构、模块设计、数据流 |
| [服务拆分方案](doc/总架构/服务拆分方案.md) | 微服务拆分方案、服务边界、gRPC 设计 |
| [分布式部署文档](doc/总架构/分布式部署文档.md) | 部署模式、环境要求、运维 |
| [性能问题分析与解决方案](doc/总架构/性能问题分析与解决方案.md) | 性能优化、瓶颈分析 |

### 功能设计

完整功能设计文档位于 [doc/功能设计文档/](doc/功能设计文档/)，按模块组织：

- 01_测试执行：API 测试、E2E 测试、执行引擎、重新评估
- 02_任务管理：任务调度、状态管理、任务合并
- 03_音频处理：音频引擎、播放编排、标注、导入
- 04_评估：评估服务、维度管理
- 05_报告管理：报告生成、对比、可视化
- 06_设备管理：设备驱动、多厂商 API 适配
- 07_用例管理：用例 CRUD、共用机制
- 08_算法配置：算法配置化、参考参数
- 09_声压级映射：SPL 映射逻辑
- 13_用户管理：用户与角色管理

### 接口文档

- [接口文档](doc/接口文档/)：REST API 规范、请求/响应示例
- [接口实现文档](doc/接口实现文档/)：实现细节说明

### voice_llm 改造

[doc/voice_llm/](doc/voice_llm/) 目录包含 voice_llm（语音交互大模型）测试能力改造的完整技术设计文档，按 5 步测试流程组织。

## 测试流程

系统采用标准化的五步测试流程：

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  1      │    │  2      │    │  3      │    │  4      │    │  5      │
│ 选算法   │ → │ 选用例   │ → │ 选设备   │ → │ 执行测试 │ → │ 查看结果 │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
   │              │              │              │              │
 配置算法参数    创建或选择      配置设备参数     运行测试        分析报告
                测试用例
```

## 技术特性

| 特性 | 说明 |
|------|------|
| **微服务架构** | 网关/调度/执行/评估分层，独立扩展、故障隔离 |
| **gRPC 通信** | 服务间高效通信，proto 契约驱动 |
| **异步执行** | 基于异步 IO 的任务调度，多任务并行 |
| **负载均衡** | 智能负载分配，避免资源争用 |
| **实时推送** | WebSocket 实时推送测试进度，秒级更新 |
| **并发控制** | 可配置并发数和队列长度 |
| **断点续传** | 支持暂停、恢复和任务重试 |
| **配置驱动** | 算法/参数/字段均配置化，无硬编码 |
