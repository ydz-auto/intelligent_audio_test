# DeepSeek Harness 统一迁移设计（V9.7.31）

> 状态：目标设计，非已实现功能。基线：`V9.7.31`；DeepSeek Harness 来源： https://github.com/deepseek-ai/deepseek-harness （2026-10-08 查询，开发者预览版）。本文件是 agent化 目录的 Agent Runtime 技术选型依据；业务功能以 01、02 为准，03 中与本文冲突的“自研 Harness”设计不再适用。

## 1. 决策与范围

- **统一 Agent Runtime 为 DeepSeek Harness（DSH）**：运行循环、模型适配、工具执行入口、会话/事件和插件生命周期使用上游能力，不平行研发自有通用 Runtime。
- **业务插件化而非重写业务**：音频导入、标注、用例、SPL、任务控制、评估、报告、UiAutoDev/设备驱动生成通过 DSH 插件或适配桥接现有 FastAPI/HTTP/gRPC 服务；后端领域逻辑、现有持久化和设备驱动保留。
- **前端渐进集成**：保留原 Vue 业务 UI，新增/改造 Agent 交互层，通过经认证的桥接 API 连接 DSH 会话/事件；不直接将 DSH 本地 Web UI 当生产业务前端。
- **不默认引入 LangChain、LangGraph、向量数据库**：源码定位可由受限检索工具使用 rg；业务数据从授权 API 获取；历史故障与文档知识依评测决定是否引入语义检索。
- **多模型可配置**：DSH 模型适配层接入经验证的 DeepSeek 或其他模型，不把“DeepSeek Harness”误当作模型名称。

## 2. DSH 已核实的集成边界

上游技术栈为 TypeScript / Node.js，基于 Cordis 的 Everything-is-a-Plugin 机制；模型适配、Tool Registry、Agent Loop 和 Session Log 可作为插件组合。官方文档提供 `web`、`headless`、`sdk`、`sdk-minimal`、`acp` Profile；通过 Profile/Bundle 和 patch 装配能力。Python SDK 通过运行对应版本的 DSH CLI 与 SDK Profile 交互。**正式编码前须根据固定版本复核插件 API、SDK 接口、会话事件、鉴权、取消及部署行为，不得猜测接口。**

建议边界：

```text
Vue Agent UI
    ↓ 已认证 HTTPS（由 FastAPI 发起/代理受控调用）
FastAPI Gateway ── 业务身份/租户/授权/审批/审计
    ↓ Agent Bridge（接口契约与版本适配）
DSH 独立受限 Node 进程（Profile + 定制业务 Plugins）
    ↓ 受控服务端 API / gRPC Adapter（短期凭证、细粒度权限）
现有 audio / test-case / task / device / evaluation / report 服务
    ↓
现有 PostgreSQL / Redis / 文件及音频存储
```

### 职责归属（避免双 Runtime）

| 能力 | 责任方 |
|---|---|
| 模型调用、Agent Loop、工具分派、插件生命周期、会话主日志 | DSH |
| 身份认证、资源授权、风险分级、审批决策、幂等性、业务审计 | FastAPI / 业务服务（强制校验） |
| 用户会话映射、Agent Run 到业务任务映射、可恢复审批和业务步骤 | 我方 Agent Bridge + PostgreSQL |
| 音频导入/标注/评估/报告/设备操作 | 现有领域服务 |
| UI 消息、审批展示、业务任务进度 | Vue + Agent Bridge 的受控事件契约 |
| 代码提案、沙盒验证、人工签核后发布 | 独立受控工作流；DSH 只发起提案 |

上游 Session Log 并不自动等于我方业务任务的幂等事务记录。Agent 恢复、事件断线重放、取消、审批状态、用户隔离在 Bridge 层有独立契约，须经端到端测试验证。禁止同时维护第二套模型/工具执行主循环。

## 3. 插件划分

首期仅启用少量只读插件；61 个业务工具是候选能力目录，不是全部默认注册。

| 插件领域 | 典型能力 | 安全策略 |
|---|---|---|
| audio | 查询音频、标注、目录；导入提案 | 创建/更新由服务端审批 |
| testcase | 用例查询、生成建议、写入提案 | 写操作幂等/归属校验 |
| task | 任务状态、结果、重试提案 | 启停/重试走服务端策略 |
| evaluation-report | 维度读取、分析、报告比较 | 发布/修改需批准 |
| diagnostics | 任务日志、归因、受限代码搜索 | 脱敏、分页、范围/输出约束 |
| device | 设备扫描、状态与受控调试请求 | 租用状态与动作白名单 |
| driver-proposal | UiAutoDev 元素→代码提案 | 不授予任意 Shell/生产目录写权限 |

优先复用 DSH 插件、工具、LLM、事件和权限扩展点。仅在必须与外部服务互操作时使用 MCP；不为域内业务调用强制引入 MCP。

## 4. 安全约束（上线前阻断项）

DSH 的 `SAFETY.md` 明示开发者预览、**未经安全审计、不应作为安全或生产就绪软件使用**，且可能执行模型生成命令/代码、访问进程/网络/凭证/文件。因而：

1. 在隔离 Node 容器/VM 中运行 DSH，非 root、只读基础层、最小资源配额；禁止加载任意第三方插件。
2. DSH 进程无生产数据库凭证、设备直连凭证或宿主机 Shell/任意文件权限；出站网络仅允许必要端点。
3. 每个业务工具在服务端重新校验用户、租户、对象权限、实时状态及参数；模型建议或前端按钮不是授权。
4. 有副作用工具采用提案→不可变审批→原子状态验证→幂等执行；拒绝/过期不可执行。
5. 生成设备驱动只写提案存储，经隔离测试、代码审查和审批后由专用发布服务落地；不得把静态检查当沙盒。
6. 前端和桥接日志去敏，禁止透传内部 DSH Token、密钥、全量 Prompt、未经脱敏音频数据。
7. 未通过安全审查、故障演练与能力评测前，生产开关保持关闭；若无法实现隔离，则不开放自动代码/命令执行。

## 5. 迁移阶段与验收

- **M0 版本锁定与可运行性验证**：锁定 DSH commit/发行版及 Node/pnpm 版本；验证 Web、SDK、Profile、插件示例和 MIT/三方许可。保存完整依赖清单。
- **M1 Agent Bridge**：建立 DSH 独立运行进程、FastAPI 鉴权代理、Run/Session 映射、取消和事件续传；验证断线、并发、用户隔离。
- **M2 首批只读业务 Plugins**：完成任务查询、报告读取、日志诊断；工具参数 Schema、限流、超时、输出截断、审计均有测试。
- **M3 审批写流程**：测试用例创建/任务重试走审批/幂等事务；测试并发确认、过期、重放、拒绝和权限变更。
- **M4 设备与驱动提案**：UiAutoDev 元素输入、驱动生成提案、隔离检查、人工发布，设备操作限定白名单。
- **M5 场景扩展**：按真实用户任务集逐步扩展其余工具，评估引入 LSP、语义检索、独立子 Agent 的必要性。

关键验收：正确完成率、工具调用正确率、越权拦截率、审批/幂等正确率、长任务恢复率、事件续传正确率、延迟与成本；新旧业务 API 行为对比不得回归。

## 6. 旧文档迁移说明

- `01_功能介绍.md` 的用户功能目标、交互/Auto 模式与工具目录仍有效；把“Agent”实现统一理解为 DSH 插件 + 我方 Bridge/服务端审批。
- `02_用户场景.md` 的场景与结果目标继续有效；实现角色不是“自研 Agent Loop”。
- `03_技术设计文档.md` 里的自研 Agent Loop、Registry、ModelClient、通用 Session 实现、目录落地建议、配置项和 P0-P5 计划属于**被替换的旧方案**；与本文件冲突时以本设计为准，下一实施阶段再按锁定的 DSH 插件 SDK 转换具体代码/配置。业务权限、审批、隔离、任务幂等原则保留。

## 7. 前后端实施细化

前端 Vue 3 的页面、Store、SSE/DTO 分层，以及 FastAPI Gateway 的路由、业务工具、审批、Run/Event 持久化、DSH Worker 部署及验收计划，统一参考 [04_前后端改造方案.md](04_前后端改造方案.md)。

## 8. 官方参考

- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/deepseek-ai/deepseek-harness/blob/master/README.zh.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md
