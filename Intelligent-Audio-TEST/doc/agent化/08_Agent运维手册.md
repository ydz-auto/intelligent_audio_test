# 08 Agent 运维手册

> 适用版本：V10.11.2（M3 收口，2026-11-15）。
> 上位文档：[07_单Agent_Skills落地方案.md](07_单Agent_Skills落地方案.md)（实现口径以 07 为准）、
> [09_外部Agent能力清单.md](09_外部Agent能力清单.md)（对外能力）。
> 部署操作细节以 `docker/README.md` 为准（§8.1 Agent 运行底座、§8.2 评测门禁）。

本手册面向运维 / 值班同学，覆盖：开关与灰度、配置全集、限额与预算、故障处置、部署与回滚。

---

## 1. 总开关与灰度

### 1.1 唯一总闸

| 项 | 值 |
|---|---|
| 环境变量 | `AGENT_ENABLED` |
| 缺省 | `false`（关闭） |
| 执行点 | **只在网关** `api_gateway/routes/agent_guard.py`（agent_service 不发布宿主端口） |
| 关闭表现 | `/api/v1/agent/**`（sessions / runs / events / approvals / skills / providers）返回 `503` + `code=AGENT_DISABLED`；不转发 agent_service、不产生后台 run |
| 人工流程 | 任务 / 用例 / 报告 / 设备等不走这些路由，**完全不受影响** |

判定逻辑：`shared/agent_access.py` 的 `evaluate_agent_access()`，结果枚举
`AgentAccessDecision`（`ENABLED` / `DISABLED` / `NOT_IN_GRAY`）。网关与
agent_service 都按需引用同一模块，不各写一套字符串比较。

### 1.2 灰度白名单（INT-2478）

在 `AGENT_ENABLED=true` 之上，可选配置两级白名单：

| 环境变量 | 含义 | 示例 |
|---|---|---|
| `AGENT_GRAY_TENANTS` | 放行的租户 ID | `default` |
| `AGENT_GRAY_USERS` | 放行的用户 ID | `1,42` |

- 分隔符：逗号 / 分号 / 空白；空项忽略。
- 判定：总闸关闭 → 拒绝；两白名单都为空 → **全员放行**（默认，向后兼容）；
  任一非空 → 租户命中 **或** 用户命中才放行。
- 未命中与总闸关闭**表现完全相同**：同一 `503 AGENT_DISABLED`、不转发、不产生
  run、响应里不区分原因（避免探测灰度名单）。
- 匿名空态（`AUTH_MODE=off` 且无 token，`user_id=0`）不命中用户白名单；整租户
  放行需用 `AGENT_GRAY_TENANTS`。
- 网关按调用时读环境变量；**容器 env 是启动时快照**，改完要重启目标容器。

### 1.3 开启 / 关闭步骤

只在 `D:\00_code\V10.11.2\Intelligent-Audio-TEST\docker` 操作（部署基线 = `V10.11.2`）：

1. 改 `docker/.env`（该文件不入库，示例见 `.env.compose.example`）：
   ```ini
   AGENT_ENABLED=true
   # 灰度（不需要灰度就留空/删掉这两行 = 全员放行）
   AGENT_GRAY_TENANTS=
   AGENT_GRAY_USERS=
   ```
2. 重启**目标容器**（不重复全栈部署）：
   ```powershell
   docker compose -p intelligent-audio-test --env-file .env up -d --no-deps --force-recreate api_gateway
   ```
   只改了 agent_service 的开关语义（启动期恢复投递）时，另重启 `agent_service`。
3. 验证（见 §1.4）。

关闭：把 `AGENT_ENABLED=false` 按同样步骤重启 `api_gateway`；agent_service 的
启动恢复投递随之停止（它复用同一变量，缺省关闭）。

### 1.4 验证清单

```powershell
# 关闭态：任一 Agent 路由应 503 + AGENT_DISABLED（带登录 token 时）
curl -s -o - -w "`nHTTP %{http_code}`n" -H "Authorization: Bearer <token>" `
  http://localhost:15000/api/v1/agent/sessions/any
# 人工流程不受影响
curl -s -o - -w "`nHTTP %{http_code}`n" -H "Authorization: Bearer <token>" `
  http://localhost:15000/api/v1/tasks?page=1&per_page=1
```

- 关闭态：Agent 路由 `503` 且 `detail.code=AGENT_DISABLED`；任务接口正常 200；
  `agent_service` 日志没有新 run 产生。
- 灰度：非灰名单账号同一请求 503 `AGENT_DISABLED`；灰名单账号可正常建会话 / 发 run。
- 灰度用户可用但刷新后仍可用：说明配置已生效（不是前端缓存）。

### 1.5 关闭与恢复投递

- agent_service 的启动期恢复投递只在 `AGENT_ENABLED=true` 时执行
  （`agent_service/config/config.py` 的 `AGENT_ENABLED`，缺省 false）。
- 关闭总闸**不会**删除既有 run；重新开启后按恢复策略继续（`AGENT_RECOVERY_ON_STARTUP`，
  默认 true）。
- 把用户移出灰名单**不会**追溯取消已被他创建的 run；要停止需显式取消
  （`POST /api/v1/agent/runs/{id}/cancel` 或前端中断按钮）。

---

## 2. 配置项全集（agent_service）

来源优先级：显式环境变量 → `agent_service/config/agent_defaults.json` → 代码兜底。
模型目录另有 `agent_service/config/model_catalog.json`。

### 2.1 凭据与供应商

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_CREDENTIAL_MASTER_KEY` | 空 | **生产必填**，缺失拒绝启动；单个 base64 32 字节或 JSON `{"版本": "密钥"}` 支持轮换 |
| `AGENT_CREDENTIAL_KEY_VERSION` | `1` | 当前主密钥版本 |
| `AGENT_ALLOW_PLATFORM_KEY` | `false` | 平台 Key 分支不实现，置 `true` 直接拒绝启动 |
| `AGENT_MODEL_CATALOG_PATH` | 空 | 空 = 用内置 `model_catalog.json` |
| `AGENT_PROVIDER_VERIFY_TIMEOUT_SECONDS` | `10` | 供应商连通性验证超时 |
| `AGENT_TOKEN_BUDGET_MULTIPLIER_DEFAULT` | `2` | 普通对话 token 预算 = 2 × 有效窗口 W |
| `AGENT_TOKEN_BUDGET_MULTIPLIER_AUTO` | `4` | Auto token 预算 = 4 × W |
| `AGENT_OUTPUT_TOKEN_RATIO` / `AGENT_OUTPUT_TOKEN_CAP` | `0.10` / `8192` | 单轮输出预留与上限 |
| `AGENT_COMPACTION_SOFT_RATIO` / `AGENT_COMPACTION_HARD_RATIO` | `0.60` / `0.80` | 压缩软 / 硬触发 |

### 2.2 网关侧

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_ENABLED` | `false` | 唯一总闸（网关 + agent_service 启动恢复） |
| `AGENT_GRAY_TENANTS` / `AGENT_GRAY_USERS` | 空 | 灰度白名单；都空 = 全员放行 |
| `AGENT_SERVICE_URL` | `http://127.0.0.1:5011`（按 `shared/config/service_ports.py`） | 网关 → agent_service |
| `AGENT_SERVICE_TIMEOUT_SECONDS` | `30` | 普通代理超时 |
| `AGENT_SERVICE_SSE_READ_TIMEOUT_SECONDS` | `0` | SSE 读超时，0 = 长连接不设读超时 |
| `AGENT_DEFAULT_TENANT_ID` | `default` | 网关下发的 `X-Tenant-Id`（恒覆盖客户端伪造值） |
| `AGENT_SKILLS_ROOT` | 仓内 `skills/` | 网关与 agent_service 同一物理目录（只读挂载） |

### 2.3 技能与记忆

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_SKILLS_ROOT` | 仓内 `skills/` | 平台 Skill 只读目录 |
| `AGENT_MEMORY_ROOT` | 仓内 `memory/` | 长期记忆写卷，按 `tenants/<t>/users/<u>/` 隔离 |
| `AGENT_MEMORY_RG_BIN` | `rg` | 检索后端；缺失返回 `MEMORY_BACKEND_UNAVAILABLE` |
| `AGENT_MEMORY_RG_TIMEOUT_SECONDS` | `5` | 单次检索超时 |
| `AGENT_MEMORY_SEARCH_DEFAULT_LIMIT` / `MAX_LIMIT` | `10` / `20` | 检索条数 |
| `AGENT_MEMORY_INJECT_MAX_TOKENS` | `600` | 会话开始注入摘要 token 上限 |
| `AGENT_MEMORY_USER_QUOTA_BYTES` | 20 MiB | 每用户磁盘上限（只回报、不阻断） |
| `AGENT_MEMORY_SENSITIVE_RULES` | `config/memory_sensitive_rules.json` | 敏感信息规则（凭证 block / PII redact） |

### 2.4 沙箱 T1 / T2

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_SANDBOX_EXECUTOR_MODE` | `runner_http` | `runner_http`（生产）/ `host_cli`（开发机） |
| `AGENT_SANDBOX_RUNNER_URL` / `AGENT_SANDBOX_RUNNER_TOKEN` | 空 | runner HTTP 入口与令牌 |
| `AGENT_SANDBOX_WORK_ROOT` | 空（系统临时目录） | `/work` 临时目录根，容器内需挂载同路径 |
| `AGENT_SANDBOX_OUTPUT_SUMMARY_CHARS` | `2000` | 回灌模型 stdout/stderr 摘要上限（原始输出 1 MB 截断） |
| `AGENT_SANDBOX_MAX_ARTIFACTS` / `_MAX_ARTIFACT_BYTES` / `_MAX_TOTAL_ARTIFACT_BYTES` | `32` / 8 MB / 32 MB | T1 产物上限 |
| `AGENT_SANDBOX_T2_MAX_*` | 同上 | T2 独立产物上限（未配置回落到 T1 口径） |
| `AGENT_T2_RUNTIME` | `runsc` | T2 运行时；宿主需注册同名 `runsc` 运行时（与 `AGENT_SANDBOX_T2_RUNTIME_NAME` 一致） |
| `AGENT_SANDBOX_T2_RUNTIME_NAME` | 见 `docker/README.md` §8.1 | Docker 运行时名；与 `AGENT_T2_RUNTIME` 不一致会按 `T2_RUNTIME_UNAVAILABLE` 失败 |

T2 运行时不可用时**绝不回落 T1**：返回 `T2_RUNTIME_UNAVAILABLE` 并按 `FAILED` 收口。

T2 启用步骤（宿主级，一次性）：

1. 在宿主 Docker 注册 gVisor 运行时（`/etc/docker/daemon.json` 增加
   `"runtimes": {"runsc": {"path": "/usr/local/bin/runsc"}}` 后重启 Docker）；
2. 令 `AGENT_T2_RUNTIME` 与 compose / runner 的 `AGENT_SANDBOX_T2_RUNTIME_NAME`
   **取同一个运行时名**（缺省 `runsc`），两者不一致会按 `T2_RUNTIME_UNAVAILABLE` 失败；
3. 用 `docker info` 确认运行时已注册，再跑 `tests/agent_sandbox/test_t2_*.py` 冒烟；
4. 本机若没有 `runsc`，T2 用例只能 skip，门禁 `--tier t2` 预期 exit 2（不是用例失败）。

### 2.5 总开关与恢复

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_ENABLED` | `false` | 见 §1 |
| `AGENT_RECOVERY_ON_STARTUP` | `true` | 启动期恢复投递（仅总开关开启时生效） |

---

## 3. 限额与预算

预算按有效上下文窗口 **W = 用户覆盖 → 模型目录默认 → 128k 兜底** 派生；请求可随
run 下发 `budget` 但**只收紧**（`min(服务端, 请求值)`，`0` / 负数视为不覆盖，未知键
400 `INVALID_BUDGET`）。

| 项 | 默认（chat） | Auto |
|---|---|---|
| 最大轮次 | 40 | 60 |
| 最大工具调用 | 80 | 120 |
| 总 token（输入+输出） | 2 × W | 4 × W |
| 单轮输出 | 8k | 8k |
| 时长 | 15 min（900 s） | 30 min（1800 s） |
| 输出字节 | 10 MB | 20 MB |
| 压缩触发 | 60% / 80% | 60% / 80% |

- 超限统一 `BUDGET_EXCEEDED`，保留已完成产物与事件。
- Auto 暂停：预算到 **80%**（`AGENT_AUTO_PAUSE_BUDGET_RATIO`）或连续 **2** 次工具失败
  （`AGENT_AUTO_PAUSE_CONSECUTIVE_FAILURES`，必须小于熔断阈值）→ `WAITING_APPROVAL`，
  用户「继续」后同一暂停点不再触发。
- 熔断：连续工具失败 **3** 次（`AGENT_MAX_CONSECUTIVE_TOOL_FAILURES`）→ `FAILED` +
  `CONSECUTIVE_TOOL_FAILURES`，不再自动重试。
- **`DESTRUCTIVE` 永不预授权**（Auto 也不预授权）；单次影响 > 20 个对象拆单审批
  （`split_threshold=20` / `split_chunk_size=1` / `max_objects=100`）。
- 审批单 TTL 默认 900 s（`approval.ttl_seconds`），过期扫描 30 s。
- 并发：worker 4（`worker_concurrency`）、单批工具并行 8（`tool_max_concurrency`）。

覆盖方式：环境变量优先，其余见 `agent_service/config/agent_defaults.json` 的
`budget` / `auto_budget` / `auto` / `approval` 段。

---

## 4. 故障处置

| 现象 | 机器码 / 位置 | 处置 |
|---|---|---|
| 所有 Agent 接口 503，人工流程正常 | `AGENT_DISABLED` | 看 `AGENT_ENABLED` 是否为 true；灰度部署再核对 `AGENT_GRAY_*` 是否命中（见 §1） |
| Agent 接口 503，上一条返回 `agent service unavailable` | `UPSTREAM_UNAVAILABLE` | `docker compose ps agent_service`；看 agent_service 日志与 `/health` |
| 服务返回 503 | `AGENT_SERVICE_UNAVAILABLE` | agent_service 未起或内部依赖（DB/Redis）不可用；按 compose 日志排查，不要只判 HTTP 200 |
| 401 | — | token 无效 / 过期；网关 Bearer 单分支（JWT 优先，其次 access token） |
| 凭据库不可用 | `CREDENTIAL_STORE_UNAVAILABLE` | 检查 `AGENT_CREDENTIAL_MASTER_KEY` 是否缺失 / 版本不匹配（生产缺失应拒绝启动） |
| 用户未配置模型 Key | 明确失败，不回退平台 Key | 让用户到「个人配置 → 模型供应商」配置；`AGENT_ALLOW_PLATFORM_KEY` 恒 false |
| 审批单过期 | `APPROVAL_EXPIRED` | 重新发起写操作生成新提案；同一批拆单按整批过期收口 |
| 沙箱失败 | `TIMEOUT` / `OUTPUT_LIMIT_EXCEEDED` / `MEMORY_LIMIT_EXCEEDED` / `RESOURCE_LIMIT_EXCEEDED` → `BUDGET_EXCEEDED`；其余原因码 → `FAILED` | 看 run 事件 `reason_code`；T2 报 `T2_RUNTIME_UNAVAILABLE` 先查宿主 `runsc` 注册与 `AGENT_T2_RUNTIME` / `AGENT_SANDBOX_T2_RUNTIME_NAME` 是否一致 |
| 评测门禁失败 | 退出码 `1` = 有层未通过；`2` = 基础设施不可用（Docker / 镜像 / runsc / 评测集缺失） | 先区分类别；`--allow-skip` / `AGENT_EVAL_ALLOW_SKIP=1` 允许层子集时，缺层记 `layers_missing`、选中不跑记 `layers_skipped`，**都不算通过**；容器内产物在 `/out/report.json` |
| SSE 中断 | 网关合成 error 帧 `UPSTREAM_ERROR` / `UPSTREAM_UNAVAILABLE` | 可恢复中断（前端重连 / 快照轮询）；run 级终态错误看 `reason_code` |
| run 卡在 `WAITING_APPROVAL` | — | 有待审批提案先处理（决策接口）；若是 Auto 暂停点，点「继续」(`POST /runs/{id}/resume`)；有提案时 resume 返回 409 |

排查顺序：① 总闸与灰度 → ② 网关到 agent_service 的可达性与 503 → ③ agent_service
日志的 `reason_code` → ④ 依赖（DB / Redis / OSS / runner）→ ⑤ 重试 / 恢复。

---

## 5. 部署与回滚

### 5.1 部署纪律

- **只从** `D:\00_code\V10.11.2\Intelligent-Audio-TEST\docker` 操作；部署后端 =
  `V10.11.2` 分支；不在其他目录 / 本地栈（`run_all.py`、uvicorn 5000-5010 / 5700-5710 /
  6000）替代。
- **一次只做一次部署**，不重复全栈重建；只改单个服务用
  `docker compose ... up -d --no-deps <service>`。
- `device_service` / `audio_service` 固定跑宿主（gRPC 50053 / 50052），docker 服务经
  `host.docker.internal` 访问；不要另起这两个进程。
- 前端：15173（React）/ 16173（新 Vue）。

### 5.2 一次性部署步骤（要点）

1. 在校验基线与 `github/V10.11.2` 一致后，主 clone 处于 `V10.11.2` 且工作区干净。
2. `docker compose -p intelligent-audio-test --env-file .env build <改动服务>`
   （构建失败先看 `docker/README.md` §3–§5 的 apt / 引擎崩溃恢复清单）。
3. `docker compose ... up -d --no-deps <改动服务>`。
4. 验证：网关 `/health`、OpenAPI 指纹、目标接口；前端入口可用。
5. 记录部署时间、服务、镜像 tag / 构建提交。

### 5.3 回滚

- 回滚口径 = **回到上一个已验证镜像 / 提交**：保留上次部署的镜像 tag 与
  `github/V10.11.2` 提交号，回滚时用同一 tag 重建目标服务（不 `git reset` 生产分支）。
- 配置回滚：`.env` 改动先备份；灰度 / 总闸回滚只改 `AGENT_ENABLED` / `AGENT_GRAY_*`
  并重启 `api_gateway`，**不需要重建镜像**。
- 数据库 / 记忆卷不做自动回滚：回滚前先备份 `memory/` 与代理库；schema 变更按
  `db_bootstrap` 的幂等迁移评估，禁止手工 drop / truncate 主库。
- 回滚后按 §1.4 复验总闸与人工流程，并在部署卡记录回滚原因与提交号。

---

## 6. 相关文档

- 方案与实现口径：[07_单Agent_Skills落地方案.md](07_单Agent_Skills落地方案.md)（§13.1 开关与灰度、§14 评测、§18 差异台账）
- 对外能力与发布说明：[09_外部Agent能力清单.md](09_外部Agent能力清单.md)（§2 权限、§9 发布说明）
- 部署细节：[`docker/README.md`](../../docker/README.md) §8.1 / §8.2
- 历史文档（仅演进记录，不作为实施依据）：00 / 03 / 04 / 05
