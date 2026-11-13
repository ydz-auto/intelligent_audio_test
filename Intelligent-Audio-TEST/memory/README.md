# memory/ — Agent 长期记忆文件树（INT-2490）

落地方案 07 §8.6 / §8.6.1 / §10：长期记忆不建表、不走向量库，用文件树 +
`rg` 关键词检索。INT-2456 只建了挂载与启动校验；本卡落地读写与隔离。

## 目录隔离（§8.6.1）

```text
memory/
  tenants/<tenant_id>/users/<owner_id>/
    user_profile.md                       # 用户偏好（跨项目）
    projects/<project>/project_memory.md  # 项目规则
    projects/<project>/<YYYY-MM-DD>/topics.md  # 话题记录
    sessions/                             # 预留：会话正文归 INT-2454 snapshot，不双写
  .proposals/<tenant>/<owner>/<id>.json   # 待审批提案（不在用户树内）
  .audit/<tenant>.jsonl                   # 记忆审计（不含正文）
```

- 路径由服务端从登录身份（`X-Tenant-Id` / `X-User-Id`）构造，模型入参里
  **没有** `tenant_id` / `owner_id` / 任意路径字段；
- 读取自动附加 tenant + owner 过滤，跨用户、跨租户一律返回空，不回报
  「存在但无权」；
- 写入只能落到调用者自己的目录，需审批；拒绝 `..`、绝对路径、`~`、
  盘符 / 分隔符，以及软链 / junction 穿越（`resolve()` 兜底）。

## 工具

| 工具 | 风险 | 说明 |
|---|---|---|
| `memory_search(query, scope=USER/PROJECT/SKILL_REFERENCES, project_id?, limit?)` | READ | `rg --fixed-strings --json`，只返回相对路径 + 片段 + 分数 + 更新时间 |
| `memory_write(section=USER_PROFILE/PROJECT_MEMORY/TOPIC, content, project_id?, reason?)` | WRITE | 只生成待审批提案，**审批前不落盘** |

`SKILL_REFERENCES` 只读检索 `skills/*/references/`（共享知识），不可写。

## 审批占位（临时边界）

M2 的审批服务 INT-2466 尚未合入：本卡用「提案 + 本人审批」占位，端点见
`agent_service/interfaces/api/memory_routes.py`（网关同名代理在
`api_gateway/routes/agent_runtime_bp.py`）：

- `GET  /api/v1/agent/memory/proposals`：待审批提案（含预演 `preview`）；
- `POST /api/v1/agent/memory/proposals/{approval_id}/approve`：按预演落盘；
- `POST /api/v1/agent/memory/proposals/{approval_id}/reject`：无副作用；
- `GET  /api/v1/agent/memory/metadata`：条数 / 更新时间 / 用量（不含正文）。

批准前目标文件不变；批准后文件内容与 `preview` 逐字一致；提案期间文件被
改动则判冲突、不覆盖。INT-2466 合入后由审批服务接管，提案结构不变。

## 敏感信息扫描

规则配置在 `agent_service/config/memory_sensitive_rules.json`
（`AGENT_MEMORY_SENSITIVE_RULES` 可覆盖）：`block` 整笔拒绝，`redact` 脱敏
后放行；PII（邮箱 / 手机 / 身份证）默认脱敏。审计只记规则名与哈希，不落
正文与命中明文。

## 审计

`memory/.audit/<tenant>.jsonl` 每次检索 / 写入 / 审批 / break-glass 追加一条：
`ts / action / tool / run_id / tenant_id / owner_id / args_hash / decision /
result_code / reason / rules`。**不落记忆正文**：`memory_write` 的
`agent_tool_call.arguments` 中 `content` 以 `sha256 + 长度` 代替。

## 注入策略

会话开始只注入「用户偏好摘要 + 项目规则摘要」（`AGENT_MEMORY_INJECT_MAX_TOKENS`，
默认 600，实测不超过该值）；话题记录与细节不进 system，模型需用
`memory_search` 按关键词取。禁止把模型猜测写入长期记忆——写入只来自用户
显式「记住」、审批通过的 `memory_write`、run 结束的结构化备忘。

## 配额与清理（配置化，不在本卡实现自动清理）

- 每用户上限：`AGENT_MEMORY_USER_QUOTA_BYTES`（默认 20 MiB），当前只在
  `GET /memory/metadata` 回报用量，不阻断写入；
- 清理策略（后续卡）：按 `user_profile.md` 最后更新时间与 `topics.md` 保留
  窗口（建议 180 天）清理；自动清理必须先落审计。

## 部署形态

- docker：`agent_memory` 命名卷挂到容器 `/app/memory`（可写），
  见 `docker/docker-compose.yml` 的 `agent_service.volumes`；镜像内装
  `ripgrep`（`docker/Dockerfile.agent_service`）；
- 本地直跑：缺省取仓库根 `memory/`（`AGENT_MEMORY_ROOT` 可覆盖）。

服务启动时校验该目录存在且可写，缺失即启动失败
（`agent_service/config/config.py:Config.validate_mounts`）——长期记忆写丢
不能等到运行期才暴露。运行期数据已在 `.gitignore` 中忽略，只跟踪本文件。
