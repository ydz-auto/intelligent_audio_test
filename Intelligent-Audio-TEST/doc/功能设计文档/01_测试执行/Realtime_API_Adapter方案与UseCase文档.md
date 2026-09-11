# Realtime API Adapter 最终方案 — 文档索引

> 版本：v3.1 | 日期：2026-09-10 | 状态：最终方案
> 
> v3.1 变更：前端恢复 3 个独立测试页面（E2ETest / APITest / RealtimeAPITest），废弃 APIExecutor 编排层改由 ExecutionEngine 直接路由

---

本文档已拆分为 8 个子文档，各子文档独立、内容完整。

| 序号 | 子文档 | 内容说明 |
|:---:|------|------|
| 1 | [01_UseCase总览.md](01_UseCase总览.md) | 核心模型、调用模式、用例结构、被测 API 配置、多模态输出、SPL 处理逻辑、路由总流程图、执行模式对比、配置被测 API/Realtime 设备 UseCase、API Realtime Adaptor 模式 UseCase |
| 2 | [02_架构设计.md](02_架构设计.md) | 背景与问题、设计目标、总体架构（架构图/路由分发/对称关系/文件结构/路由分离） |
| 3 | [03_流程图.md](03_流程图.md) | HTTP API 测试流程、Realtime API 测试流程、轮次状态机 |
| 4 | [04_类设计.md](04_类设计.md) | BaseAPIAdapter（含 AdapterOutput）、HttpAPIAdapter、RealtimeAPIAdapter（含帧结果/最终结果）、OpenAIRealtimeAdapter、APIAdapterFactory、AudioStreamOrchestrator、ApiRmsSplMapping、混音流程图、RealtimeSessionExecutor |
| 5 | [05_路由与废弃.md](05_路由与废弃.md) | 路由分发改造、数据库改动、废弃清单、实施阶段 |
| 6 | [06_评估与前端.md](06_评估与前端.md) | 三种执行模式对比、评估维度、前端改动清单（3 页面对称） |
| 7 | [07_流式推送与结果获取.md](07_流式推送与结果获取.md) | 生产者-消费者机制、推送方向、接收方向、帧结果与最终结果、正常轮时序、打断轮时序、与 E2E 对比 |
| 8 | [08_混音与SPL映射.md](08_混音与SPL映射.md) | 混音 6 步流程、噪声合并优先级、RMS 补偿、SPL 增益、E2E vs Realtime 对称设计、SPL 未配置行为 |
