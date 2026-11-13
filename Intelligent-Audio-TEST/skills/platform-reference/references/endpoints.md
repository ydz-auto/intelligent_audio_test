# 网关接口前缀明细（L3，按需读取）

来源：`api_gateway/app.py` 的路由注册。路径都相对网关根，外部访问形如
`http://<gateway>/api/v1/tasks`。前缀变更新增时先改代码，再改这里。

| 前缀 | 路由模块 | 说明 |
|---|---|---|
| `/api/v1/auth` | `auth_bp` / `user_bp` / `role_bp` / `oauth_bp` | 登录、用户、角色、OAuth、权限点 |
| `/api/v1/testcases` | `testcase_bp` | 用例 CRUD、导入导出 |
| `/api/v1/groups` | `group_bp` | 用例分组 |
| `/api/v1/tags` | `tag_bp` | 标签、批量打标 |
| `/api/v1/tasks` | `task_bp` | 任务 CRUD、启动、停止、统计 |
| `/api/v1/tasks/cherry-picks` | `cherry_pick_bp` | 挑选合并 |
| `/api/v1/tasks/results` | `review_bp` | 人工复核提交 / 计数 / 历史 |
| `/api/v1/published-tasks` | `published_task_bp` | 发布任务 |
| `/api/v1/apis` | `api_bp` | 被测 API 定义 |
| `/api/v1/execution` | `execution_bp` | 执行编排 |
| `/api/v1/audios` | `audio_bp` | 音频列表 / 详情 / 导入 / 标注 |
| `/api/v1/test-devices` | `device_bp` | 测试设备 |
| `/api/v1/playback-devices` | `playback_bp` | 播放设备 |
| `/api/v1/laboratories` | `laboratory_bp` | 实验室 |
| `/api/v1/evaluation` | `evaluation_bp` | 评估维度 / 分类 |
| `/api/v1/evaluation-strategies` | `evaluation_strategy_bp` | 评估策略 |
| `/api/v1/reports` | `report_bp` | 报告生成、发布、导出、进度 |
| `/api/v1/report-studio` | `report_studio_bp` | Studio 文档 / 版本 / 图表 / 导出 |
| `/api/v1/algorithm` | `algorithm_bp` | 算法定义、参数、映射、热重载 |
| `/api/v1/spl` | `spl_bp` | SPL 映射与校准 |
| `/api/v1/digital-spl` | `digital_spl_bp` | 数字 SPL |
| `/api/v1/logs` | `log_bp` | 日志搜索 / 统计 / 导出 |
| `/api/v1/home` | `home_bp` | 首页统计 |
| `/api/v1/sse` | `sse_bp` | 业务进度推送（与 Agent 事件流不是同一条） |
| `/api/v1/data-transfer` | `data_transfer_bp` | 数据迁移 |
| `/api/v1/benchmarks` | `benchmark_bp` | 基准报告 |
| `/api/v1/system` | `system_bp` | 系统信息 |
| `/api/v1/favorites` | `favorite_trash_bp` | 收藏（回收站无独立前缀：恢复 `POST {tasks\|testcases\|reports}/{id}/restore`、彻底删除 `DELETE {tasks\|testcases\|reports}/{id}/purge`，批量走 `POST {实体}/restore\|purge`；回收站列表走各实体列表的 `deleted` / `only_deleted` 过滤） |
| `/api/v1/agent` | `agent_runtime_bp` | Agent sessions / runs / events / skills |
| `/api/v1/agent/skill` | `agent_bp` | 外部 Skill 包 zip 下载（单数，与上面区分） |
| `/api/v1/mcp` | `agent_bp` | 外部 MCP JSON-RPC |
| `/api` | `status_bp` / `option_bp` | 站点状态 / 系统选项 KV（根级，无 `/v1`） |

补充口径：

- SSE 有两条独立通道：业务进度 `/api/v1/sse`；Agent 运行事件
  `/api/v1/agent/runs/{id}/events`（支持 `Last-Event-ID` 续传）。
- 外部 MCP 与内部 Agent 共用工具 Schema（`shared/agent_tools`），不要复制两份。
