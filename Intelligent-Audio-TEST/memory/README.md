# memory/ — Agent 长期记忆文件树（INT-2456）

落地方案 07 §8.6：长期记忆不建表、不走向量库，用文件树 + 关键词检索。

## 目录隔离（§8.6.1）

```text
memory/tenants/<tenant_id>/users/<owner_id>/...
```

- 路径由服务端从登录身份构造，模型输入不得传 `tenant_id` / `owner_id` / 任意路径；
- 读取自动附加 tenant + owner 过滤，跨用户、跨租户一律返回空；
- 写入需审批（`memory_write`），拒绝 `..`、绝对路径与软链穿越。

## 部署形态

- docker：`agent_memory` 命名卷挂到容器 `/app/memory`（可写），
  见 `docker/docker-compose.yml` 的 `agent_service.volumes`；
- 本地直跑：缺省取仓库根 `memory/`（`AGENT_MEMORY_ROOT` 可覆盖）。

服务启动时校验该目录存在且可写，缺失即启动失败
（`agent_service/config/config.py:Config.validate_mounts`）——长期记忆写丢
不能等到运行期才暴露。
