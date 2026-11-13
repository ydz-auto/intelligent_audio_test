---
name: platform-reference
description: >-
  智能语音测试平台的接口、字段别名、枚举、权限码与工具检索口径速查。
  触发词：平台有哪些接口、这个字段叫什么、状态枚举取值、权限码是什么、
  某个工具的 Schema、tool_search 怎么用、接口返回的是什么类型。
  不适用：具体业务操作（导入音频、创建任务、生成报告等）各自有专门 Skill；
  本 Skill 只回答「平台怎么描述自己」，不代替业务 Skill 执行流程。
version: 1.0.0
owner: agent-platform
allowed-tools:
  - platform_contract
  - tool_search
permissions: []
budgets:
  maxToolCalls: 20
  maxTokens: 30000
---

# platform-reference

回答「平台长什么样」的唯一入口：服务拓扑、接口前缀、字段与枚举口径、权限码、
工具检索方式。本 Skill 只做**事实查询与口径澄清**，不执行任何业务写操作。

## 何时用

- 不确定某个字段 / 枚举 / 状态值的准确拼写与取值；
- 需要知道某个能力由哪个服务、哪个接口前缀提供；
- 需要确认权限码，或判断当前用户能不能做某件事；
- 不确定该调哪个工具，需要按关键词检索长尾工具 Schema。

## 何时不用

- 用户要的是「做事」（导入音频、建用例、跑任务、出报告）：转到对应业务 Skill；
- 需要平台没有的能力：明确告诉用户「平台未提供」，不要臆造接口或字段。

## 平台拓扑

所有外部访问只走 **api_gateway**（`/api/v1` 前缀，容器内 5000 / 本机 docker 栈
15000），网关负责鉴权、租户、限流、审计；业务服务之间才用 gRPC。

| 服务 | HTTP | gRPC | 职责 |
|---|---|---|---|
| api_gateway | 5000 | — | 对外唯一入口、鉴权、转发 |
| task_service | 5001 | 51061 | 任务、任务用例、结果 |
| e2e_test_service | 5002 | 50051 | 端到端执行 |
| api_test_service | 5003 | 51071 | API 测试执行 |
| evaluation_service | 5004 | 51091 | 评估维度、评分 |
| report_service | 5006 | 51068 | 报告生成、发布、导出 |
| algorithm_service | 5007 | 51067 | 算法定义与参数 |
| auth_service | 5009 | 51069 | 用户、角色、权限、令牌 |
| transfer_agent | 5010 | 51101 | 数据迁移 |
| agent_service | 5011 | — | 本 Agent 的 Loop / Run / SSE |

音频（audio_service, gRPC 50052）与设备（device_service, gRPC 50053）不直接对外
开 HTTP 端口，经网关对应前缀访问。端口以 `shared/config/service_ports.py` 为唯一
事实源；不要凭记忆写端口。

常见接口前缀（网关路由注册处 `api_gateway/app.py`，明细见
`references/endpoints.md`）：

| 前缀 | 域 |
|---|---|
| `/api/v1/tasks`、`/api/v1/tasks/cherry-picks`、`/api/v1/tasks/results` | 任务 / 挑选合并 / 人工复核 |
| `/api/v1/testcases`、`/api/v1/groups`、`/api/v1/tags` | 用例 / 分组 / 标签 |
| `/api/v1/audios` | 音频 |
| `/api/v1/test-devices`、`/api/v1/playback-devices`、`/api/v1/laboratories` | 设备 / 播放设备 / 实验室 |
| `/api/v1/evaluation`、`/api/v1/evaluation-strategies` | 评估维度 / 策略 |
| `/api/v1/reports`、`/api/v1/report-studio` | 报告 / 报告 Studio |
| `/api/v1/algorithm` | 算法 |
| `/api/v1/spl`、`/api/v1/digital-spl` | SPL 校准 / 数字 SPL |
| `/api/v1/logs`、`/api/v1/home`、`/api/v1/benchmarks` | 日志 / 首页 / 基准 |
| `/api/v1/auth` | 登录、用户、角色、权限 |
| `/api/v1/agent` | 本 Agent：sessions / runs / events / skills |

## 鉴权与权限码

- 外部调用带 `Authorization: Bearer <JWT>` 或 Access Token；网关解析后把
  `X-User-Id` / `X-Tenant-Id` / `X-User-Permissions` 注入下游服务。
- 权限码格式固定为 **`资源:操作`**（如 `task:read`、`task:create`、`task:share`）；
  权限点全集在 auth_service 的 `permissions` 表，不要自己拼不存在的码。
- `*` 是管理员通配，命中即放行所有权限校验。
- 多权限判定是 **OR**（`require_permission('task:read', 'task:execute')` 任一满足
  即可）；Skill / 工具声明的 `permissions` 同样按 OR 与用户权限取交集判定可见性。

## 字段与命名口径

- **服务端一律 snake_case**；前端 camelCase 只在 `frontend-react/src/infrastructure`
  的 dto / adapters 层转换。模型侧拿到的是服务端口径，直接用 snake_case。
- ID：除 `agent_*` 表用 UUID 字符串外，业务实体主键一般是整数（`task_id: 123`）；
  `user_id` 是整数，`tenant_id` 是字符串。
- 时间：接口返回 ISO 8601 字符串；数据库按 UTC naive 写入。
- 序列化：网关统一用 `CustomJSONResponse` —— `datetime` → isoformat、`Decimal`
  → float、`Enum` → 其 `value`；因此枚举在 JSON 里永远是**值**而不是名字。
- 列表响应形态各域不完全一致（有的 `{items, total}`，有的裸数组），不要假设
  统一 envelope；以接口实际返回为准，必要时先调一次只读接口确认。
- 金额 / 指标 / 评分一律以接口返回数值为准；缺失就是缺失，不要用 0 或估算值填补。

## 枚举速查

**任务状态**（`task_service/domain/entities/task.py` `TaskStatus`）：
`pending` / `queued` / `running` / `evaluating` / `reevaluate_queued` /
`reevaluating` / `completed` / `failed` / `stopped` / `paused` / `skipped`。
终态 = `completed` / `failed` / `stopped` / `skipped`；运行中 =
`running` / `evaluating` / `reevaluating`。

**报告状态**（`shared/models/common_enums.py` `ReportStatus`）只有两个值：
`draft`（未发布）/ `published`（已发布）。生成进度不落这一列，进度看
`GET /api/v1/reports/{id}/progress` 的响应态。

**可见性**（`Visibility`）：`shared` / `private`。`private` 仅 owner 与 admin 可见。

**可收藏实体**（`EntityType`）：`task` / `report` / `testcase`。

**评估维度是否 LLM 判分**：用 `shared/constants/evaluation_dimension.py` 的
`is_llm_judge_dimension(task_type_code=..., dimension_type=...)`，不要自己写
`'llm_judge' in ...` 的子串判断（历史上三处口径漂移过）。

## tool_search 用法

`tool_search` 是长尾工具的检索入口，不是业务工具本身：

1. 先想清楚意图关键词（如「校准 SPL」「导出 PPT」「对比报告」）；
2. 调 `tool_search(query="...")`，返回匹配工具的 name / description / 参数
   Schema；
3. 只调**返回结果里出现过的**工具，参数按返回 Schema 填；未返回 = 平台没有该
   能力，直接告诉用户，不要猜工具名硬调；
4. 调不通时回来看 Schema 的必填字段与枚举，不要连续重试同一个错误参数。

意图工具（`platform_contract` / `tool_search` / `task_query` 等）的权威清单在
`shared/agent_tools`（工具 Schema 单一事实源）。工具名以注册表为准，不以文档
里的示例为准。

## Gotchas

1. **`/agent/skill` 与 `/agent/skills` 不是一回事**：前者是外部 Skill 包 zip
   下载（单数），后者是当前用户可见的内部 Skill 列表（复数）。
2. **报告类型有两套枚举，别混用**：`report_service` 的 `ReportType` 是
   `standard` / `comparison` / `detailed`；`shared.models.common_enums.ReportType`
   是 `task` / `comparison` / `secondary_comparison` / `benchmark`。判断某接口
   能用哪些值，看它导入的是哪一个，不要跨域套用。
3. **报告状态不是生成进度**：`status` 只有 `draft` / `published`；想回答「生成到
   哪一步」必须查 progress 接口，不能把 `generating` / `completed` 当成 status 值。
4. **枚举值大小写**：数据库与接口里是**小写值**（`completed`），Python 枚举名是
   大写（`COMPLETED`）；回答用户时用中文名，调接口时用小写值。
5. **权限码是「资源:操作」**：`task_read`、`task.read`、`read:task` 都是错的；
   不存在的权限码不会报错，只会让校验恒失败——宁可先查 auth 域的权限列表。
6. **多权限是 OR 不是 AND**：`require_permission('a', 'b')` 表示任一即可；需要
   「都必须有」时要显式分别校验。
7. **`AUTH_MODE=off` 时 permissions 注入为 `['*']`**：本地/联调环境看似什么权限
   都有，不代表线上角色也有；按线上权限模型回答用户。
8. **跨服务只走 gRPC + ACL**：任何「直连别的服务的数据库 / 内部模块」的方案都是
   错的；对外只能走网关 `/api/v1`。
9. **离线数据不要现算**：等级、评分、指标由领域服务计算并落库；模型不得用对话
   里的数字做二次计算冒充平台结论。
10. **端口与路径以代码为准**：`shared/config/service_ports.py` 与
    `api_gateway/app.py` 是唯一事实源；文档、注释、记忆里的端口都可能过期。
11. **事件与日志脱敏**：音频、完整日志、Prompt 全文不落事件表；不要把这类内容
    回灌进上下文或贴给用户。
12. **写操作一律提案 + 审批**：写工具调用返回 `APPROVAL_REQUIRED`（M2 落地通用
    审批链）；`memory_write` 只生成待审批提案、审批前不落盘。不要把它当成
    「平台不支持写操作」。
13. **长期记忆**：用户偏好与项目规则用 `memory_search` 按关键词检索（只能看到
    当前登录用户自己的记忆；精简为主，细节现查）；确实需要长期记住时用
    `memory_write`（需审批），只写用户明确要求记住的事实，禁止把猜测写入记忆。

## 验收

回答平台口径类问题时，逐项自检：

- [ ] 接口路径、端口、服务名能在代码事实源里找到（`service_ports.py` / `app.py`）；
- [ ] 枚举回答的是**接口里的值**（小写）且来自正确模块，没有混用两套报告类型；
- [ ] 权限码形如 `资源:操作`，并说明是 OR 判定 / `*` 通配；
- [ ] 字段名用服务端 snake_case，涉及前端转换时明确说在 infrastructure 层；
- [ ] 调工具前先 `tool_search`，只调返回结果中出现的工具；
- [ ] 没有编造数值、ID、接口或权限码；平台没有的能力明确说「不支持」；
- [ ] 涉及写操作时说明当前 M0 口径（提案 + 审批）。
