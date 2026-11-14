# 外部 Agent 能力清单

> 本文件是「外部 Agent 能用什么」的**唯一归属文件**：可用工具、Skill、鉴权方式、
> 限额与内部对照。INT-2478 只在本文件末尾的「发布说明」追加，不建第二份。
>
> 数据源（改代码必须同步本文件，`tests/agent_mcp` 逐项比对名称集合）：
> `shared/agent_tools/mcp_registry.py`（对外 MCP 工具，单一事实源）、
> `shared/agent_tools/intent_tools.py`（内部意图工具）、
> `shared/agent_tools/coverage.py` / `COVERAGE.md`（MCP → 意图工具归属）、
> `skills/`（平台内置 Skill，平台 Agent 与外部宿主共用）。

## 1. 接入方式（一套 Skill，两种宿主）

| 宿主 | Skill | 工具通道 |
|---|---|---|
| 平台内置 Agent | 直接装载 `skills/`（L1 列表 + L2 正文 + L3 references） | 31 个意图工具（延迟加载 + `tool_search`） |
| 外部 Claude Code / Codex 等 | `GET /api/v1/agent/skill` 下载平台包（根级 `SKILL.md` + `references/` + `assets/mcp.json`），解压即用 | `POST /api/v1/mcp`（JSON-RPC 2.0，207 个工具，1:1 映射既有 REST） |

平台下载包与用户自定义 Skill 的导入 / 导出包**同一结构**（成员集合一致、根级
`SKILL.md`、不套外层目录、资源只放 `references/ scripts/ assets/`），但**不承诺
回导**（INT-2612）：平台包预填下载时的服务地址，导入侧按自定义包规则校验，
**内网 / 回环地址会被 `INTERNAL_ADDRESS` 拒绝**（正文与 `assets/mcp.json` 各一条）。
平台包 frontmatter 面向外部宿主（`allowed-tools` / `permissions` 为空），导入后只是
文档型 Skill、不参与内部工具收敛；内部复用平台 Skill 请走「从内置 fork」
（`POST /api/v1/agent/skills/{skill_id}/fork`）。
`assets/mcp.json` 已预填下载时的服务地址，鉴权头是占位符。`skills/` 目录不可读时
下载回退静态模板包，**兜底包不保证可导入**（模板 Bearer 占位命中 `EMBEDDED_SECRET`、
正文超过 500 行上限）；兜底只保证下载可用、结构合法。

**来源层级与「自定义包 → 平台层」的 N/A 依据（INT-2610 P3-7）**：Skill 只有三层来源——
`PLATFORM`（平台内置，只读 fs 扫描 `skills/` 目录得到）、`TENANT`（租户共享，走审核流）、
`USER`（用户自建 / 导入）。`PLATFORM` 层**没有写入口**（无导入、无保存、无发布接口），
所以「把自定义包提升为平台层」这个方向不存在攻击面，也不是本期能力缺口；要复用平台
Skill 只能「从内置 fork」生成 `USER` 副本。此依据同时写在 `tests/agent_mcp` 的注册表
一致性注释里，改注册表时不得新增 PLATFORM 写入口。

## 2. 鉴权与权限

- 外部调用使用 **Access Token**（明文 `at_` 开头，仅创建时显示一次，库中只存哈希）；
  同一 token 在 Skill 里的 curl 指令与 MCP 两种方式下通用。
- 请求头：`Authorization: Bearer <ACCESS_TOKEN>`。
- **生效权限 = 用户当前权限 ∩ token scopes**：空 scopes = 继承用户全部权限；
  `*` 为管理员通配。scope 未覆盖某工具所需权限时，MCP `tools/call` 直接返回越权
  错误（403 语义），目标 REST 端点还会二次校验权限码。
- 权限码格式固定 `资源:操作`，**可多级**（如 `report:studio:create`、`benchmark:baseline:read`）；多权限判定是 OR。
- 401 = token 无效 / 过期；403 = 越权；422 = 参数校验失败。MCP 层错误以
  `isError=true` + 文本内容返回，不抛协议异常。

## 3. 限额

| 项 | 值 | 来源 |
|---|---|---|
| 对外 MCP 工具数 | 207 | `shared/agent_tools/mcp_registry.py` |
| 内部意图工具数 | 31 | `shared/agent_tools/intent_tools.py` |
| MCP 单次工具转发超时 | 60 秒 | `api_gateway/application/services/mcp/mcp_handler.py` |
| Skill `SKILL.md` 上限 | 64 KB | `shared/skill_package.SkillPackageLimits` |
| 单资源上限 | 512 KB | 同上 |
| 整包上限 | 5 MB | 同上 |
| 包内条目上限 / 压缩比 | 200 条 / 100:1 | 同上 |
| 导入上传（压缩前）上限 | 10 MB（`AGENT_SKILL_MAX_UPLOAD_BYTES`） | 同上 |
| 平台内置 Skill 预算 | 见各 `skills/*/SKILL.md` 的 `budgets`（如 `maxToolCalls` / `maxTokens`） | `skills/` |

MCP 端点未单独设按用户配额，沿用网关通用鉴权与系统选项 `security.rate_limit`（若开启）。

## 4. 对外 MCP 工具（207 个）

### 4.1 按域汇总

| 域 | 工具数 | 只读 | 权限码 |
|---|---|---|---|
| task | 25 | 8 | `task:batch`, `task:create`, `task:delete`, `task:execute`, `task:merge`, `task:read`, `task:reextract`, `task:share`, `task:update` |
| published_task | 3 | 2 | `published_task:execute`, `published_task:read` |
| testcase | 10 | 2 | `testcase:copy`, `testcase:create`, `testcase:delete`, `testcase:import_export`, `testcase:read`, `testcase:share`, `testcase:update` |
| audio | 25 | 8 | `audio:convert`, `audio:delete`, `audio:folder`, `audio:read`, `audio:update`, `audio:upload` |
| device | 37 | 12 | `device:control`, `device:create`, `device:delete`, `device:read`, `device:update` |
| evaluation | 9 | 3 | `evaluation:category_manage`, `evaluation:dim_manage`, `evaluation:execute`, `evaluation:read`, `evaluation:share` |
| report | 31 | 12 | `report:compare`, `report:create`, `report:delete`, `report:publish`, `report:read`, `report:share`, `report:studio:create`, `report:studio:edit`, `report:studio:export`, `report:update` |
| algorithm | 44 | 16 | `algorithm:case_param_manage`, `algorithm:definition_manage`, `algorithm:group_manage`, `algorithm:param_manage`, `algorithm:read` |
| tag | 6 | 2 | `tag:create`, `tag:delete`, `tag:read`, `tag:share`, `tag:update` |
| group | 5 | 1 | `group:create`, `group:delete`, `group:read`, `group:share`, `group:update` |
| data | 3 | 0 | `task:export`, `task:import` |
| favorites | 1 | 1 | — |
| benchmark | 4 | 3 | `benchmark:baseline:read`, `benchmark:ranking:compute`, `benchmark:ranking:read`, `benchmark:report:read` |
| log | 2 | 2 | `log:read` |
| home | 2 | 2 | `home:read` |
| **合计** | **207** | **74** | — |

「只读」只按 HTTP 方法判定（74 个 GET 工具）——`task_favorite` 这类
写动作声明的是读权限，按权限码判会误标，故不采用。

### 4.2 逐项清单

| 工具 | 方法 | 风险 | 权限 | 说明 |
|---|---|---|---|---|
| `task_list` | GET | 只读 | `task:read` | 列出任务（支持 search/status 等过滤参数） |
| `task_get` | GET | 只读 | `task:read` | 获取任务详情 |
| `task_create` | POST | 写 | `task:create` | 创建任务（body 按任务字段，如 name/type/case_ids 等） |
| `task_update` | PUT | 写 | `task:update` | 修改任务 |
| `task_delete` | DELETE | 写 | `task:delete` | 删除任务 |
| `task_start` | POST | 写 | `task:execute` | 启动任务执行 |
| `task_stop` | POST | 写 | `task:execute` | 停止任务执行 |
| `task_control` | POST | 写 | `task:execute` | 控制任务（暂停/继续等控制指令） |
| `task_retry` | POST | 写 | `task:execute` | 重试任务 |
| `task_reextract` | POST | 写 | `task:reextract` | 重新提取任务结果 |
| `task_merge` | POST | 写 | `task:merge` | 合并任务（挑选合并） |
| `task_stats` | GET | 只读 | `task:read` | 任务域全量聚合统计 |
| `task_get_progress` | GET | 只读 | `task:read` | 获取任务执行进度 |
| `task_batch_action` | POST | 写 | `task:batch` | 任务批量操作 |
| `task_validate` | POST | 写 | `task:create` | 任务资源归属预检（创建前校验实验室归属） |
| `task_get_labs` | GET | 只读 | `task:read` | 获取任务关联实验室 |
| `task_get_case_detail` | GET | 只读 | `task:read` | 获取任务内用例执行详情 |
| `task_get_case_results` | GET | 只读 | `task:read` | 获取任务内用例结果 |
| `task_remove_case` | DELETE | 写 | `task:execute` | 从任务移除用例 |
| `task_update_cases` | PATCH | 写 | `task:update` | 更新任务用例集合 |
| `task_get_stats` | GET | 只读 | `task:read` | 获取任务内统计 |
| `published_task_list` | GET | 只读 | `published_task:read` | 列出已发布任务 |
| `published_task_get` | GET | 只读 | `published_task:read` | 获取已发布任务详情 |
| `published_task_execute` | POST | 写 | `published_task:execute` | 执行已发布任务 |
| `testcase_list` | GET | 只读 | `testcase:read` | 列出测试用例（支持 keyword/status 等过滤参数） |
| `testcase_get` | GET | 只读 | `testcase:read` | 获取测试用例详情 |
| `testcase_create` | POST | 写 | `testcase:create` | 创建测试用例 |
| `testcase_update` | PUT | 写 | `testcase:update` | 修改测试用例 |
| `testcase_delete` | DELETE | 写 | `testcase:delete` | 删除测试用例 |
| `testcase_copy` | POST | 写 | `testcase:copy` | 复制测试用例 |
| `testcase_export` | POST | 写 | `testcase:import_export` | 导出测试用例 |
| `testcase_import` | POST | 写 | `testcase:import_export` | 导入测试用例（multipart file，MCP 场景建议直接调接口） |
| `audio_list` | GET | 只读 | `audio:read` | 列出音频（支持关键词 / 格式 / 类型 / 采样率 / 标签等过滤参数） |
| `audio_get` | GET | 只读 | `audio:read` | 获取音频详情 |
| `audio_get_by_ids` | POST | 写 | `audio:read` | 按 ID 列表批量获取音频 |
| `audio_update_metadata` | PUT | 写 | `audio:update` | 更新音频元数据 |
| `audio_convert` | POST | 写 | `audio:convert` | 音频转码 |
| `audio_delete` | DELETE | 写 | `audio:delete` | 删除音频 |
| `audio_get_by_md5` | POST | 写 | `audio:read` | 按 MD5 批量查音频（请求体字段 md5_list） |
| `audio_list_tags` | GET | 只读 | `audio:read` | 列出音频标签 |
| `audio_upload_progress` | GET | 只读 | `audio:read` | 获取分片上传进度 |
| `audio_url_import` | POST | 写 | `audio:upload` | URL 导入音频 |
| `audio_batch_annotations` | POST | 写 | `audio:update` | 批量更新音频标注 |
| `audio_batch_action` | POST | 写 | `audio:update` | 音频批量操作 |
| `audio_features` | GET | 只读 | `audio:read` | 获取音频特征分析 |
| `audio_quality` | GET | 只读 | `audio:read` | 获取音频质量评估 |
| `audio_process` | POST | 写 | `audio:update` | 处理音频（降噪/增益/剪辑） |
| `audio_get_algorithms` | GET | 只读 | `audio:read` | 获取音频已配算法 |
| `audio_update_algorithms` | PUT | 写 | `audio:update` | 更新音频算法配置 |
| `audio_playback_history` | GET | 只读 | `audio:read` | 获取音频播放历史（按播放时间倒序分页） |
| `audio_folder_tree` | POST | 写 | `audio:folder` | 获取音频目录树 |
| `audio_upload_init` | POST | 写 | `audio:upload` | 分片上传初始化 |
| `audio_upload_register` | POST | 写 | `audio:upload` | 分片上传注册文件 |
| `audio_upload_merge` | POST | 写 | `audio:upload` | 分片上传合并 |
| `audio_upload_presign` | POST | 写 | `audio:upload` | OSS 直传预签名（整文件） |
| `audio_upload_presign_part` | POST | 写 | `audio:upload` | OSS 直传预签名（分片） |
| `audio_upload_complete_direct` | POST | 写 | `audio:upload` | OSS 直传完成确认 |
| `device_list` | GET | 只读 | `device:read` | 列出被测设备 |
| `device_get` | GET | 只读 | `device:read` | 获取被测设备详情 |
| `device_create` | POST | 写 | `device:create` | 创建被测设备 |
| `device_update` | PUT | 写 | `device:update` | 修改被测设备 |
| `device_delete` | DELETE | 写 | `device:delete` | 删除被测设备 |
| `device_connect` | POST | 写 | `device:control` | 连接被测设备 |
| `device_disconnect` | POST | 写 | `device:control` | 断开被测设备 |
| `device_reboot` | POST | 写 | `device:control` | 重启被测设备 |
| `device_health_check` | POST | 写 | `device:control` | 被测设备健康检查 |
| `device_status_list` | GET | 只读 | `device:read` | 获取设备状态汇总 |
| `device_driver_keywords` | GET | 只读 | `device:read` | 获取设备驱动关键词 |
| `device_serials` | GET | 只读 | `device:read` | 获取可用设备序列号 |
| `device_status_history` | GET | 只读 | `device:read` | 获取设备状态历史（全局） |
| `device_group_list` | GET | 只读 | `device:read` | 列出设备分组 |
| `device_group_create` | POST | 写 | `device:create` | 创建设备分组 |
| `device_group_get` | GET | 只读 | `device:read` | 获取设备分组详情 |
| `device_group_update` | PUT | 写 | `device:update` | 修改设备分组 |
| `device_group_move` | PUT | 写 | `device:update` | 移动设备分组 |
| `device_group_delete` | DELETE | 写 | `device:delete` | 删除设备分组 |
| `device_group_add_devices` | POST | 写 | `device:update` | 向分组添加设备 |
| `device_group_remove_devices` | POST | 写 | `device:update` | 从分组移除设备 |
| `device_alarm_rule_list` | GET | 只读 | `device:read` | 列出告警规则 |
| `device_alarm_rule_create` | POST | 写 | `device:update` | 创建告警规则 |
| `device_alarm_rule_update` | PUT | 写 | `device:update` | 修改告警规则 |
| `device_alarm_rule_delete` | DELETE | 写 | `device:update` | 删除告警规则 |
| `device_alarm_list` | GET | 只读 | `device:read` | 列出设备告警 |
| `device_alarm_acknowledge` | POST | 写 | `device:control` | 确认告警 |
| `device_batch_action` | POST | 写 | `device:control` | 设备批量操作 |
| `device_scan` | POST | 写 | `device:control` | 扫描设备 |
| `device_shutdown` | POST | 写 | `device:control` | 关闭被测设备 |
| `device_install_app` | POST | 写 | `device:control` | 安装应用到被测设备 |
| `device_uninstall_app` | POST | 写 | `device:control` | 卸载应用 |
| `device_get_status_history` | GET | 只读 | `device:read` | 获取设备状态历史（单设备） |
| `device_export` | GET | 只读 | `device:read` | 导出设备 |
| `device_import` | POST | 写 | `device:create` | 导入设备 |
| `device_test` | POST | 写 | `device:control` | 被测设备测试 |
| `device_stop_test` | POST | 写 | `device:control` | 停止被测设备测试 |
| `evaluation_dimension_list` | GET | 只读 | `evaluation:read` | 列出评估维度（可按分类 / 关键词过滤） |
| `evaluation_dimension_get` | GET | 只读 | `evaluation:read` | 获取评估维度详情 |
| `evaluation_dimension_create` | POST | 写 | `evaluation:dim_manage` | 创建评估维度 |
| `evaluation_dimension_update` | PUT | 写 | `evaluation:dim_manage` | 修改评估维度 |
| `evaluation_dimension_delete` | DELETE | 写 | `evaluation:dim_manage` | 删除评估维度 |
| `evaluation_category_list` | GET | 只读 | `evaluation:read` | 列出评估分类 |
| `evaluation_category_create` | POST | 写 | `evaluation:category_manage` | 创建评估分类 |
| `evaluation_task_reevaluate` | POST | 写 | `evaluation:execute` | 触发任务重新评估 |
| `report_list` | GET | 只读 | `report:read` | 列出报告（支持类型 / 状态 / 任务 / 算法 / 时间 / 收藏 / 回收站过滤） |
| `report_get` | GET | 只读 | `report:read` | 获取报告详情 |
| `report_by_task` | GET | 只读 | `report:read` | 按任务获取报告 |
| `report_generate_task` | POST | 写 | `report:create` | 按任务生成报告 |
| `report_update` | PUT | 写 | `report:update` | 修改报告 |
| `report_delete` | DELETE | 写 | `report:delete` | 删除报告 |
| `report_publish` | POST | 写 | `report:publish` | 发布报告 |
| `report_compare` | POST | 写 | `report:compare` | 报告对比 |
| `report_tab_counts` | GET | 只读 | `report:read` | 获取报告页签计数（与列表同口径，随关键词收缩） |
| `report_export_get` | GET | 只读 | `report:read` | 导出报告（GET） |
| `report_statistics` | GET | 只读 | `report:read` | 获取报告统计（按维度聚合） |
| `report_statistics_trend` | GET | 只读 | `report:read` | 获取报告统计趋势 |
| `report_statistics_report` | POST | 写 | `report:read` | 生成统计报告 |
| `report_batch_delete` | POST | 写 | `report:delete` | 批量删除报告 |
| `report_progress` | GET | 只读 | `report:read` | 获取报告生成进度 |
| `report_share_create` | POST | 写 | `report:update` | 创建报告分享链接 |
| `report_share_list` | GET | 只读 | `report:update` | 列出报告分享链接 |
| `report_share_revoke` | DELETE | 写 | `report:update` | 撤销报告分享链接 |
| `report_secondary_compare` | POST | 写 | `report:compare` | 报告二次对比 |
| `report_regenerate` | POST | 写 | `report:create` | 重新生成报告 |
| `report_export` | POST | 写 | `report:read` | 导出报告（POST） |
| `report_case_averages` | POST | 写 | `report:read` | 按过滤条件获取用例平均值 |
| `report_cases` | GET | 只读 | `report:read` | 获取报告内用例 |
| `report_cases_search` | POST | 写 | `report:read` | 搜索报告内用例 |
| `report_case_logs` | GET | 只读 | `report:read` | 获取报告内用例日志 |
| `algorithm_definition_list` | GET | 只读 | `algorithm:read` | 列出算法定义 |
| `algorithm_definition_get` | GET | 只读 | `algorithm:read` | 获取算法定义详情 |
| `algorithm_definition_create` | POST | 写 | `algorithm:definition_manage` | 创建算法定义 |
| `algorithm_definition_update` | PUT | 写 | `algorithm:definition_manage` | 修改算法定义 |
| `algorithm_definition_delete` | DELETE | 写 | `algorithm:definition_manage` | 删除算法定义 |
| `algorithm_group_list` | GET | 只读 | `algorithm:read` | 列出算法分组 |
| `algorithm_group_create` | POST | 写 | `algorithm:group_manage` | 创建算法分组 |
| `algorithm_param_list` | GET | 只读 | `algorithm:read` | 列出算法参数 |
| `algorithm_param_create` | POST | 写 | `algorithm:param_manage` | 创建算法参数 |
| `algorithm_definition_save` | PUT | 写 | `algorithm:definition_manage` | 保存算法定义（整体保存） |
| `algorithm_definition_draft` | PUT | 写 | `algorithm:definition_manage` | 保存算法定义草稿 |
| `algorithm_definition_draft_get` | GET | 只读 | `algorithm:read` | 获取算法定义草稿 |
| `algorithm_group_get` | GET | 只读 | `algorithm:read` | 获取算法分组详情 |
| `algorithm_group_update` | PUT | 写 | `algorithm:group_manage` | 修改算法分组 |
| `algorithm_group_delete` | DELETE | 写 | `algorithm:group_manage` | 删除算法分组 |
| `algorithm_param_get` | GET | 只读 | `algorithm:read` | 获取算法参数详情 |
| `algorithm_param_update` | PUT | 写 | `algorithm:param_manage` | 修改算法参数 |
| `algorithm_param_delete` | DELETE | 写 | `algorithm:param_manage` | 删除算法参数 |
| `algorithm_case_param_list` | GET | 只读 | `algorithm:read` | 列出用例算法参数 |
| `algorithm_case_param_get` | GET | 只读 | `algorithm:read` | 获取用例算法参数详情 |
| `algorithm_case_param_create` | POST | 写 | `algorithm:case_param_manage` | 创建用例算法参数 |
| `algorithm_case_param_update` | PUT | 写 | `algorithm:case_param_manage` | 修改用例算法参数 |
| `algorithm_case_param_delete` | DELETE | 写 | `algorithm:case_param_manage` | 删除用例算法参数 |
| `algorithm_reference_param_list` | GET | 只读 | `algorithm:read` | 列出参考算法参数 |
| `algorithm_reference_param_get` | GET | 只读 | `algorithm:read` | 获取参考算法参数详情 |
| `algorithm_reference_param_create` | POST | 写 | `algorithm:param_manage` | 创建参考算法参数 |
| `algorithm_reference_param_update` | PUT | 写 | `algorithm:param_manage` | 修改参考算法参数 |
| `algorithm_reference_param_delete` | DELETE | 写 | `algorithm:param_manage` | 删除参考算法参数 |
| `algorithm_mapping_list` | GET | 只读 | `algorithm:read` | 列出算法映射 |
| `algorithm_mapping_create` | POST | 写 | `algorithm:definition_manage` | 创建算法映射 |
| `algorithm_mapping_update` | PUT | 写 | `algorithm:definition_manage` | 修改算法映射 |
| `algorithm_mapping_delete` | DELETE | 写 | `algorithm:definition_manage` | 删除算法映射 |
| `algorithm_options` | GET | 只读 | `algorithm:read` | 获取算法下拉选项 |
| `algorithm_form_schema` | GET | 只读 | `algorithm:read` | 获取算法表单 Schema |
| `algorithm_dimension_list` | GET | 只读 | `algorithm:read` | 获取算法维度 |
| `algorithm_dimension_create` | POST | 写 | `algorithm:definition_manage` | 创建算法维度 |
| `algorithm_dimension_relation_create` | POST | 写 | `algorithm:definition_manage` | 创建算法维度关系 |
| `algorithm_dimension_relation_update` | PUT | 写 | `algorithm:definition_manage` | 修改算法维度关系 |
| `algorithm_dimension_relation_delete` | DELETE | 写 | `algorithm:definition_manage` | 删除算法维度关系 |
| `algorithm_reload` | POST | 写 | `algorithm:definition_manage` | 重新加载算法配置 |
| `algorithm_import` | POST | 写 | `algorithm:definition_manage` | 导入算法定义 |
| `algorithm_bulk_delete` | POST | 写 | `algorithm:definition_manage` | 批量删除算法 |
| `algorithm_extract_params` | POST | 写 | `algorithm:param_manage` | 抽取算法参数 |
| `algorithm_dimension_params` | GET | 只读 | `algorithm:read` | 获取维度参数 |
| `tag_list` | GET | 只读 | `tag:read` | 列出标签 |
| `tag_get` | GET | 只读 | `tag:read` | 获取标签详情 |
| `tag_create` | POST | 写 | `tag:create` | 创建标签 |
| `tag_update` | PUT | 写 | `tag:update` | 修改标签 |
| `tag_delete` | DELETE | 写 | `tag:delete` | 删除标签 |
| `group_list` | GET | 只读 | `group:read` | 列出用例分组 |
| `group_create` | POST | 写 | `group:create` | 创建用例分组 |
| `group_update` | PUT | 写 | `group:update` | 修改用例分组 |
| `group_delete` | DELETE | 写 | `group:delete` | 删除用例分组 |
| `task_set_visibility` | PATCH | 写 | `task:share` | 设置任务可见性分享（shared/private） |
| `testcase_set_visibility` | PATCH | 写 | `testcase:share` | 设置测试用例可见性分享 |
| `report_set_visibility` | PATCH | 写 | `report:share` | 设置报告可见性分享 |
| `tag_set_visibility` | PATCH | 写 | `tag:share` | 设置标签可见性分享 |
| `group_set_visibility` | PATCH | 写 | `group:share` | 设置用例分组可见性分享 |
| `evaluation_dimension_set_visibility` | PATCH | 写 | `evaluation:share` | 设置评估维度可见性分享 |
| `data_transfer_export` | POST | 写 | `task:export` | 导出任务数据（ZIP） |
| `data_transfer_import_preview` | POST | 写 | `task:import` | 导入预检 |
| `data_transfer_import` | POST | 写 | `task:import` | 执行任务数据导入 |
| `favorites_list` | GET | 只读 | — | 列出当前用户收藏 ID 列表 |
| `task_favorite` | POST | 写 | `task:read` | 收藏任务 |
| `task_restore` | POST | 写 | `task:delete` | 从回收站恢复任务 |
| `task_purge` | DELETE | 写 | `task:delete` | 彻底删除任务（purge） |
| `testcase_favorite` | POST | 写 | `testcase:read` | 收藏测试用例 |
| `report_favorite` | POST | 写 | `report:read` | 收藏报告 |
| `benchmark_ranking` | GET | 只读 | `benchmark:ranking:read` | 查看 Benchmark 排行 |
| `benchmark_ranking_compute` | POST | 写 | `benchmark:ranking:compute` | 触发 Benchmark 排行计算 |
| `benchmark_baselines` | GET | 只读 | `benchmark:baseline:read` | 查看 Benchmark 基线 |
| `benchmark_reports` | GET | 只读 | `benchmark:report:read` | 查看 Benchmark 报告 |
| `report_studio_create_document` | POST | 写 | `report:studio:create` | 创建 Report Studio 文档草稿 |
| `report_studio_get_document` | GET | 只读 | `report:read` | 获取 Report Studio 文档 |
| `report_studio_update_document` | PUT | 写 | `report:studio:edit` | 编辑 Report Studio 文档 |
| `report_studio_export_document` | POST | 写 | `report:studio:export` | Report Studio 导出作业 |
| `log_list` | GET | 只读 | `log:read` | 查看测试执行日志（级别 / 模块 / 任务 / 用例 / 时间过滤） |
| `log_stats` | GET | 只读 | `log:read` | 日志级别统计（total / debug / info / warning / error / critical） |
| `home_stats_details` | GET | 只读 | `home:read` | 首页统计详情（用例 / 任务 / 设备 / 音频 / API / 报告 / 维度汇总） |
| `home_stats_summary` | GET | 只读 | `home:read` | 首页统计摘要（最近任务 / TOP 分组 / 设备在线状态） |

完整说明与下载包内 `references/mcp-tools.md` 同源（由注册表渲染），与
`POST /api/v1/mcp` 的 `tools/list` 逐项一致。

## 5. 仅外部 MCP（不内部暴露）

以下 9 个工具没有对应意图工具，只作为原始 MCP 工具存在
（内部 Agent 仍可经 `tool_search` 检索，执行受只读门禁 / 审批约束）：

| MCP 工具 | 理由 |
|---|---|
| `audio_get_by_ids` | 宿主语境批量读通道（不做归属校验），Agent 侧不暴露（INT-2530） |
| `data_transfer_export` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import_preview` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `favorites_list` | 跨域个人收藏 ID 列表，§6.1 无对应意图工具 |
| `benchmark_ranking` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_ranking_compute` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_baselines` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_reports` | Benchmark 域不在 §6.1 工具表内 |

## 6. 内部意图工具（31 个）与外部对照

| 意图工具 | 风险 | 启用 | 权限 | 对应外部 MCP 工具数 |
|---|---|---|---|---|
| `platform_contract` | READ | 是 | — | 本地能力（无外部 MCP 对应） |
| `tool_search` | READ | 是 | — | 本地能力（无外部 MCP 对应） |
| `task_query` | READ | 是 | `task:read` | 10 |
| `task_diagnose` | READ | 是 | `task:read`, `log:read` | 本地能力（无外部 MCP 对应） |
| `log_diagnose` | READ | 是 | `log:read` | 2 |
| `dashboard_query` | READ | 是 | `home:read` | 2 |
| `report_query` | READ | 是 | `report:read` | 14 |
| `audio_query` | READ | 是 | `audio:read` | 9 |
| `evaluation_query` | READ | 是 | `evaluation:read` | 3 |
| `testcase_query` | READ | 是 | `testcase:read` | 3 |
| `testcase_generate` | READ | 是 | `testcase:read` | 本地能力（无外部 MCP 对应） |
| `ui_tree` | READ | 是 | `device:read` | 本地能力（无外部 MCP 对应） |
| `ui_action` | WRITE | 是 | `device:control` | 本地能力（无外部 MCP 对应） |
| `api_spec` | READ | 是 | `api_config:read` | 本地能力（无外部 MCP 对应） |
| `memory_search` | READ | 是 | — | 本地能力（无外部 MCP 对应） |
| `memory_write` | WRITE | 是 | — | 本地能力（无外部 MCP 对应） |
| `audio_import` | WRITE | 是 | `audio:upload` | 7 |
| `audio_annotate` | WRITE | 是 | `audio:update` | 8 |
| `testcase_write` | WRITE | 是 | `testcase:create`, `testcase:update`, `testcase:copy`, `testcase:delete` | 7 |
| `tag_group_manage` | WRITE | 是 | `tag:create`, `tag:update`, `tag:delete`, `group:create`, `group:update`, `group:delete`, `testcase:update`, `testcase:delete` | 11 |
| `evaluation_manage` | WRITE | 是 | `evaluation:dim_manage`, `evaluation:category_manage`, `evaluation:execute`, `evaluation:share` | 6 |
| `algorithm_query` | READ | 是 | `algorithm:read` | 16 |
| `device_query` | READ | 是 | `device:read`, `spl:read`, `digital_spl:read` | 12 |
| `algorithm_manage` | WRITE | 是 | `algorithm:definition_manage`, `algorithm:param_manage` | 28 |
| `task_run` | WRITE | 是 | `task:create`, `task:execute`, `task:merge`, `task:reextract` | 18 |
| `spl_calibrate` | WRITE | 是 | `spl:create`, `spl:update`, `spl:delete`, `spl:test_tone`, `digital_spl:create`, `digital_spl:update`, `digital_spl:delete` | 本地能力（无外部 MCP 对应） |
| `device_control` | DESTRUCTIVE | 是 | `device:control` | 25 |
| `report_generate` | WRITE | 是 | `report:create`, `report:studio:create`, `report:studio:edit`, `report:studio:undo` | 12 |
| `report_compare` | READ | 是 | `report:compare` | 2 |
| `report_export` | WRITE | 是 | `report:studio:export` | 3 |
| `driver_propose` | WRITE | 是 | `device:update` | 本地能力（无外部 MCP 对应） |

归属关系的逐项理由见 `shared/agent_tools/COVERAGE.md`（由 `coverage.py` 生成，禁止手改）。

## 7. 平台内置 Skill（14 个）

| Skill | 版本 | 触发 / 用途（description） | allowed-tools |
|---|---|---|---|
| `algorithm-config` | 1.1.0 | 算法配置域的查询与写操作入口：算法定义（状态、分组、草稿）、设备与 API 参数 （含三层解析）、参考参数、参数映射、用例专属参数、表单 Schema 与下拉选项、 算法关联的评估维度，以及热重载的前置条件；新建 / 修改 / 删除算法定义、参数、 参考参数、映射、导入算法定义与热重载走提案 + 审批。 触发词：算法定义、算法参数、参考参数、参数映射、参数列表、表单 Schema、表单字段、 算法选项、算法下拉、算法分组、算法配置、算法维度、设备参数、API 参数、用例参数、 热重载前提、改算法参数、新增算法参数、删除算法参数、改设备参数、改 API 参数、 改参数映射、新增映射、删除映射、改参考参数、新增参考参数、删除参考参数、 改算法定义、新增算法定义、删除算法定义、导入算法定义、热重载、重载算法配置、 算法配置回滚、参数变更风险。 不适用：报告与指标取数 / 导出（report-studio、report-compare）、评估维度与分类的 配置（evaluation-config）、音频导入与标注（audio-import）、SPL 校准 （spl-calibration）；算法计算本身的数值结论（WER / MOS / 准确率）由报告与评估 服务给出，本 Skill 不计算、不估算。 | `algorithm_query`, `algorithm_manage`, `tool_search` |
| `app-api-onboarding` | 1.0.0 | App / API 接入全流程（onboarding）：用户说「我要测这个 App / 这个 API / 这个 厂商接口」时，先受理确认测试目标与测量路径，用 ui_tree / ui_action 探索 App 界面或用 api_spec 解析 OpenAPI / gRPC proto / WebSocket 契约，查同类驱动与设备 事实，输出接入计划与缺口；确认后调 driver_propose 生成 AppDriver / ApiVendorAdapter / 成对交付的固定接入包（代码 + config.yaml + capabilities.json + test_plan.md + ui_trace.json + tests/ + smoke_case.json + manifest.json + onboarding_report.md），T2 编译 / 单测 / mock 契约 / 注册表 resolve 后在 staging 目录用 task_run(mode=SMOKE) 跑冒烟，失败最多迭代 3 轮且 每轮必须带新证据。只产提案与 staging 包，不写生产目录、不自动注册、不发布。 触发词：接入 App、接入 API、App 接入、API 接入、接入包、onboarding、新 App 接入、新厂商接入、测这个 App、测这个 API、厂商适配器、接入流程、测量路径、 ASR 测量、TTS 测量、ui_trace、capabilities、冒烟用例、staging 冒烟、接入报告、 驱动提案、元素树探索、API 契约解析、OpenAPI、proto、WebSocket 帧、AppDriver、 ApiVendorAdapter、成对交付、接入计划、缺口清单、驱动生成、适配器生成。 不适用：只问平台接口 / 字段 / 枚举（platform-reference）；已有驱动的设备连接、 重启、告警（device-operations）；只做驱动代码评审不跑接入流程（driver-proposal）； SPL 校准（spl-calibration）；用例 / 任务 / 报告日常操作（testcase-authoring / task-operations / report-studio）。 | `ui_tree`, `ui_action`, `api_spec`, `driver_propose`, `device_query`, `testcase_generate`, `task_run`, `tool_search` |
| `audio-import` | 1.1.0 | 音频资源排查、导入与标注（写操作走审批）：查列表、看详情、按 MD5 查重、看目录树、 标签、特征 / 质量、已配算法、播放历史；URL 导入、分片上传初始化 / 合并、OSS 直传 完成确认、批量标注、改元数据、配算法。触发词：音频列表、查音频、音频详情、这个音频 有没有导入过、MD5 查重、重复音频、音频目录树、文件夹结构、音频标签、音频格式、 采样率、音频质量、信噪比、特征、已配算法、播放历史、导入前检查、导入音频、 上传音频、URL 导入、批量标注、修改音频元数据、配算法。 不适用：用例生成、任务执行、报告导出——那些各有专门 Skill。 | `audio_query`, `audio_import`, `audio_annotate`, `platform_contract`, `tool_search` |
| `device-operations` | 1.1.0 | 被测设备运维：设备列表与详情、设备分组、在线状态与状态历史（含健康检查事件）、 告警与告警规则、可用序列号、驱动关键词，以及连接 / 断开 / 重启 / 关机 / 扫描 / 安装 / 卸载 / 批量控制（写操作走审批 + 二次确认）。 触发词：设备列表、设备详情、设备分组、设备状态、状态历史、设备告警、告警规则、 可用序列号、序列号列表、驱动关键词、设备实验室、设备在线、设备离线、设备占用、 连接设备、重启设备、设备扫描、安装应用、卸载应用、健康检查状态。 不适用：SPL 映射 / 校准 / 测试音（spl-calibration 负责）；设备驱动代码生成提案 （driver-proposal 负责）；用例、任务、报告、音频等其它域。 | `device_query`, `device_control`, `tool_search` |
| `driver-proposal` | 1.1.0 | 设备驱动与厂商 API 适配器代码提案：从 UiAutoDev 元素树 / 操作轨迹和被测 API 契约出发，先查设备与算法事实、找同类驱动样例，产出 AppDriver / ApiVendorAdapter 提案并在 T2 沙箱验证（只提案，不执行、不注册、不发布）。 触发词：驱动提案、驱动代码、生成驱动、AppDriver、ApiVendorAdapter、适配器提案、 适配器代码、UiAutoDev、元素树、操作轨迹、能力画像、驱动覆盖率、驱动模板、 同类驱动样例、驱动生成前置条件、驱动发布。 不适用：设备连接 / 重启 / 告警（device-operations 负责）；SPL 映射 / 校准 （spl-calibration 负责）；用例生成与任务编排。 | `device_query`, `driver_propose`, `tool_search` |
| `evaluation-config` | 1.1.0 | 评估维度配置口径速查与写操作入口：维度列表与详情、评分口径字段（分值范围 / 单位 / 权重 / 统计方式 / 聚合分母 / 排除轮次 / 评分规则）、评估分类、可见性、 导入导出格式、健康检查与重评估前置条件；新增 / 修改 / 删除维度、新建 / 修改 / 删除分类、切换维度可见性、触发重评估走提案 + 审批。 触发词：评估维度、维度配置、评分口径、评分规则、分值范围、分数单位、权重、 统计方式、聚合分母、排除轮次、评估分类、维度可见性、导入导出维度、 维度健康检查、重评估条件、重评估前置条件、新增维度、修改维度、删除维度、 新建评估分类、改分类、切换维度可见性、触发重评估。 不适用：跑评估、查看评估结果 / 报告指标（report-studio、task-operations 负责）； 算法参数、SPL 校准、任务编排等其它配置域。 | `evaluation_query`, `evaluation_manage`, `tool_search` |
| `log-diagnostics` | 1.0.0 | 日志域只读查询与诊断：按级别 / 模块 / 分类 / 任务 / 用例 / 时间检索日志行， 取真实级别统计（total / debug / info / warning / error / critical），并把错误 日志按来源聚合成带日志 ID 的线索。不导出、不清除、不刷新、不归档日志，也不做 逐行实时推送。 触发词：日志查询、日志搜索、日志统计、错误日志、报错日志、异常日志、日志诊断、 失败日志、日志级别、日志来源、日志行、日志关键词、查日志、看日志。 不适用：任务进度 / 用例通过率 / 失败用例归因（task-operations）、报告与指标 取数（report-studio）、设备离线告警（device-operations）、Agent 自身的运行 事件流（Agent 页面）。 | `log_diagnose`, `tool_search` |
| `platform-reference` | 1.0.0 | 智能语音测试平台的接口、字段别名、枚举、权限码与工具检索口径速查。 触发词：平台有哪些接口、这个字段叫什么、状态枚举取值、权限码是什么、 某个工具的 Schema、tool_search 怎么用、接口返回的是什么类型。 不适用：具体业务操作（导入音频、创建任务、生成报告等）各自有专门 Skill； 本 Skill 只回答「平台怎么描述自己」，不代替业务 Skill 执行流程。 | `platform_contract`, `tool_search` |
| `report-compare` | 1.0.0 | 报告对比口径：多报告并排取数（指标矩阵 / 设备与 API 统计 / 用例分类统计）、 二次对比（对已有对比报告再做一次对比）、统计趋势序列，以及异常报告下钻。 触发词：报告对比、对比报告、二次对比、多报告对比、并排对比、报告差异、 指标差异、通过率对比、报告趋势、指标趋势、趋势序列、异常报告、通过率异常、 环比、同比。 不适用：单份报告的取数与指标解释、报告起草（report-studio 负责）；生成对比 报告 / 二次对比报告（写操作，M2 走提案 + 审批）；任务执行（task-operations 负责）。 | `report_compare`, `report_query`, `tool_search` |
| `report-studio` | 1.1.0 | 报告取数、指标解释与报告交付口径：三类报告（任务 / 对比 / 二次对比）列表与详情、 指标矩阵、设备与 API 统计、用例明细与用例搜索、维度统计、生成进度、页签计数、 报告文本（描述 / 分析 / 结论）的起草与版本口径，以及生成 / 重生成报告、 Studio 草稿与版本恢复、导出 PDF / PPTX / HTML / MD（写操作走提案 + 审批）。 触发词：报告详情、报告指标、报告列表、报告用例、报告统计、报告进度、页签计数、 通过率、平均分、指标单位、用例平均值、报告起草、报告版本、导出报告、报告结论、 生成报告、重生成报告、Studio 草稿、导出 PDF、导出 PPTX、导出 HTML。 不适用：多报告对比 / 二次对比 / 趋势（report-compare 负责）；任务执行本身 （task-operations 负责）；评估维度评分口径（evaluation-config 负责）。 | `report_query`, `report_generate`, `report_export`, `tool_search` |
| `spl-calibration` | 1.1.0 | SPL 声压级校准口径速查：物理域 SPL 映射（播放设备 / 距离 / 测试频率 / 目标 SPL / 校准状态 / 校准点集）与数字域 RMS→SPL 映射（被测 API / 参考 SPL / 增益限幅 / 校准点集），以及校准历史、最新校准数据，和映射增删改 / 校准 / 测试音写操作 （写操作走审批）。 触发词：SPL 映射、声压级、SPL 校准、校准状态、校准历史、校准点集、校准数据、 测试音、增益偏移、增益限幅、目标声压级、数字域映射、RMS 映射、播放设备校准、 已校准、未校准。 不适用：被测设备连接 / 重启 / 告警（device-operations 负责）；驱动代码提案 （driver-proposal 负责）；报告里的 SPL 指标解读（report-studio 负责）。 | `device_query`, `spl_calibrate`, `tool_search` |
| `tag-group` | 1.1.0 | 标签与用例分组口径速查：标签列表与分类归属、标签 / 分组可见性、用例分组列表 与用例数，以及经提案 + 审批执行的标签 / 分组写操作（新增、修改、删除、批量 打标与标签改名）。 触发词：标签、标签列表、标签分类、标签归属、标签可见性、批量打标、打标策略、 重命名标签、新建标签、删除标签、用例分组、分组、分组列表、分组下、分组里、 分组可见性、分组用例数、新建分组、修改分组、删除分组。 不适用：用例本身的编制与轮次配置（testcase-authoring）；音频标签的素材元数据 （audio-import）。 | `tool_search`, `platform_contract`, `tag_group_manage` |
| `task-operations` | 1.1.0 | 任务域的查询、失败诊断与写操作：任务列表与过滤、任务详情与用例清单、实时执行 进度、用例统计与通过率、用例执行详情 / 结果、关联实验室，失败用例 + 真实错误 日志的归因和重测建议；创建 / 启动 / 停止 / 重试 / 合并 / 重提取经提案 + 审批 后执行。 触发词：任务列表、任务详情、执行进度、任务进度、任务统计、通过率、失败用例、 失败原因、任务诊断、任务诊断报告、重测建议、用例结果、任务实验室、重试任务、 合并任务、创建任务、启动任务、停止任务、重新提取、重新执行。 不适用：日志全文检索 / 日志级别统计 / 日志来源归因（log-diagnostics）、 报告与指标取数（report-studio）、音频导入与标注（audio-import）、评估维度配置 （evaluation-config）、算法参数与表单（algorithm-config）。 | `task_query`, `task_diagnose`, `task_run`, `log_diagnose`, `tool_search` |
| `testcase-authoring` | 1.1.0 | 用例编制口径速查：用例列表与详情、轮次配置（config.rounds 的音频 / 声压 / 播放设备 / 逐轮评估维度）、评估维度挂载（逐轮与多轮整体）、用例算法参数、 轮次参考参数、导入导出状态与统计；并支持由音频标注推导用例草案（只读生成， 不落库）。用例写操作（新建、修改、复制、删除、加 / 去标签）经提案 + 审批后 执行。 触发词：用例、用例列表、用例详情、用例轮次、轮次配置、轮次参考参数、轮的参考参数、 参考参数、用例参考参数、参考参数刷新、刷新状态、用例导出、导出作业、评估维度挂载、 用例参数、用例统计、按分组、分组下的用例、分组里的用例、标注生成用例、 生成用例草案、复制用例、用例变体、新建用例、创建用例、修改用例、编辑用例、 删除用例、给用例加标签、给用例去标签。 不适用：标签字典与用例分组管理、跨用例批量打标（tag-group）；算法参数定义 （algorithm-config）；用例执行与结果（task-operations）。 | `testcase_query`, `testcase_generate`, `testcase_write`, `tool_search` |

平台下载包（`GET /api/v1/agent/skill`）以 `platform-reference` 的正文与 references 为
底，追加「外部 Agent 接入」「只读能力」与完整工具目录；包内 Skill 名为
`intelligent-audio-test`，不占用平台内置名，导入后可落库为本人自定义 Skill。

## 8. 对照结论（无暗能力）

- 对外 MCP 207 个工具逐项都有归属结论（内部归属 198 / 仅外部 9），
  见 `COVERAGE.md`；
- 内部 31 个意图工具全部在上面第 6 节列出，没有未登记的隐藏工具；
- 对外 `tools/list` 只暴露 name / description / inputSchema，权限声明留在注册表与
  第 4 节表中，两者同源（`shared/agent_tools/mcp_registry.py`）；
- `tests/agent_mcp` 逐项比对名称集合与 Schema / 权限，注册表新增工具而本文件未更新即失败。

## 9. 发布说明

> 本节由 INT-2478 追加。上方内容随代码同步更新，不在此处写发布过程。

### 9.1 M3 发布口径（2026-11-15）

- **能力面**：对外 MCP **207** 个工具（§4）、内部意图工具 **31** 个（§6）、平台内置
  Skill **14** 个（§7）——数字与前文逐项一致，本次发布未改动任何数字。
- **接入方式不变**：外部宿主仍用 `GET /api/v1/agent/skill` 下载平台包 + `POST /api/v1/mcp`；
  包结构为根级 `SKILL.md` + `references/` + `assets/mcp.json`（不再是根目录 `mcp.json`）。
- **权限口径**：权限码 `资源:操作`，可多级；生效权限 = 用户权限 ∩ token scopes，
  空 scopes = 继承用户全部权限。
- **文档型 Skill 边界**：平台包导入为 `USER` Skill 后是**文档型 Skill**
  （`allowed-tools` / `permissions` 为空），不参与内部工具收敛；需要内部复用请 fork。

### 9.2 灰度与开关（对外可见表现，2026-11-15）

- Agent 功能由平台侧总闸 `AGENT_ENABLED` 控制（**默认关闭**）。关闭时调用
  `/api/v1/agent/**` 返回 `503` + `code=AGENT_DISABLED`；任务 / 用例 / 报告 / 设备等
  业务接口**不受影响**。
- 平台可按租户 / 用户做灰度（`AGENT_GRAY_TENANTS` / `AGENT_GRAY_USERS`）：未命中灰度
  的账号表现与总闸关闭**完全相同**（同一错误码），不产生后台 run，也不会告诉外部
  「是否配置了灰度名单」。
- 外部 MCP（`/api/v1/mcp`）与 Skill 包下载属于既有接入面，不在 Agent 运行底座总闸
  的关闭范围内；但内部意图工具与写操作依赖的运行底座关闭后，MCP 工具调用仍按各自
  权限与上游状态返回。
- 灰度切换由平台运维按 `.env` 重启网关完成，外部接入方无需改配置；被移出灰度的账号
  不会追溯取消其已创建的 run。
