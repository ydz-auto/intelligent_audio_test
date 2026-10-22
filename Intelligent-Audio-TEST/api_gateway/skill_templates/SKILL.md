# 智能音频测试（Intelligent Audio Test）平台能力

通过本 skill / MCP，外部 agent（Claude Code / Codex 等）可以调用智能音频测试平台的业务能力：任务、测试用例、音频、被测设备、评估维度、报告、算法、标签、用例分组、数据分享、Benchmark 排行、Report Studio 等。

## 1. 前置条件

1. **创建 Access Token**：登录平台，在「个人配置页 → Access Token」创建访问令牌。明文格式 `at_` 开头（如 `at_9f2c…`），**仅创建时明文显示一次**，库中只存哈希；创建时可配置权限 scopes 与有效时间。
2. **确认服务地址可达**：本包 mcp.json 已按下载时的配置预填服务地址 `{{BASE_URL}}`。多网络环境下可改为你实际可访问的地址（IP 或 http(s) 链接）。
3. **权限范围**：token 生效权限 = 用户当前权限 ∩ token scopes；不勾选 scopes = 继承用户全部权限。token 不含某接口所需权限时调用返回 403。

## 2. 配置与认证

两个环境变量（或在你使用工具时按需提供）：

- `INTELLIGENT_AUDIO_TEST_BASE_URL`：平台服务地址，默认 `{{BASE_URL}}`。
- `INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN`：你的 Access Token（`at_` 开头，明文仅创建时显示一次）。

所有请求通过 `Authorization: Bearer <ACCESS_TOKEN>` 头鉴权：

```bash
curl -H "Authorization: Bearer $INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN" \
  "$INTELLIGENT_AUDIO_TEST_BASE_URL/api/v1/tasks?page=1&per_page=10"
```

同一 Access Token 在 skill（curl 指令）与 MCP 两种方式下通用。

## 3. 通用约定（REST）

- **URL 前缀**：所有接口挂 `/api/v1`，如 `${BASE_URL}/api/v1/tasks`。
- **字段命名**：请求与响应字段一律 **snake_case**（如 `task_id`、`per_page`、`execution_status`）。
- **分页**：列表接口统一使用 `page`（页码，默认 1）+ `per_page`（每页条数，默认 10~20 视接口而定）；响应数据信封 `{items, total, page, pages, per_page}`。
- **响应信封**：统一为 `{success: bool, code: int, message: str, data: ...}`；`success=false` 时为错误，附带 `detail`（可能缺省）。
- **错误语义**：4xx/5xx HTTP 状态 + 错误信封；**403 = 越权**（token scopes 不足）；422 = 参数校验失败；401 = token 无效/过期。
- **时间字段**：ISO 8601 字符串（`YYYY-MM-DD HH:MM:SS`）。

## 4. 能力总览（覆盖 / 除外）

| 域 | 覆盖 | 除外 / 说明 |
| --- | --- | --- |
| 任务 task | CRUD、执行控制（启动/停止/控制/重试）、结果提取、合并、批量、统计、进度、用例子接口 | 二进制通道（见下） |
| 已发布任务 | 列表 / 详情 / 执行 | — |
| 测试用例 testcase | CRUD、复制、导入导出 | multipart 导入建议直接调接口 |
| 音频 audio | 列表 / 详情 / 元数据 / 转码 / 删除 / 特征 / 质量 / 处理 / 算法配置 / 上传 / 目录树 | **排除**：音频二进制流 / 下载、分片 chunk 字节上传（非 JSON 通道不承载） |
| 被测设备 device | CRUD、连接控制、分组、告警、扫描、应用安装、导入导出 | — |
| 评估 evaluation | 维度 / 分类管理、触发重新评估 | — |
| 报告 report | CRUD、发布、对比、统计、导出、分享、用例日志 | 用例日志文件下载为二进制，不承载 |
| 算法 algorithm | 定义 / 分组 / 参数 / 映射 / 维度 / 表单 Schema / 导入导出 | — |
| 标签 tag / 用例分组 group | CRUD | — |
| 跨域 | 数据可见性分享（`*:share`）、数据转移（task 导入导出）、收藏 / 回收站、Benchmark 排行、Report Studio、日志只读（`log:read`） | — |
| **除外（不暴露）** | 系统设置（用户 / 角色 / 权限 / OAuth 提供方 / 系统选项 / 系统健康状态）、个人信息（auth me/self/改密/OAuth 绑定）、日志管理（log:manage / log:websocket）、SSE 长连接推送 | MCP 工具清单中不提供 |

## 5. 分域接口参考

> 下表「MCP 工具名」为 MCP `tools/call` 的 `name`；「端点」即 REST 路径。MCP 与 REST 一一对应，入参 Schema 以 MCP `tools/list` 返回为准。参数说明：`body` 表示将整个 JSON 对象作为请求体（复杂嵌套结构）。

### 5.1 任务 task（`task_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| task_list | `GET /api/v1/tasks` | 列出任务（search/status/page/per_page 过滤） | task:read |
| task_get | `GET /api/v1/tasks/{task_id}` | 任务详情 | task:read |
| task_create | `POST /api/v1/tasks` | 创建任务（name 必填、case_ids 等） | task:create |
| task_update | `PUT /api/v1/tasks/{task_id}` | 修改任务 | task:update |
| task_delete | `DELETE /api/v1/tasks/{task_id}` | 删除任务 | task:delete |
| task_start | `POST /api/v1/tasks/{task_id}/start` | 启动执行 | task:execute |
| task_stop | `POST /api/v1/tasks/{task_id}/stop` | 停止执行 | task:execute |
| task_control | `POST /api/v1/tasks/{task_id}/control` | 控制（暂停/继续等） | task:execute |
| task_retry | `POST /api/v1/tasks/{task_id}/retry` | 重试 | task:execute |
| task_reextract | `POST /api/v1/tasks/{task_id}/reextract` | 重新提取任务结果 | task:reextract |
| task_merge | `POST /api/v1/tasks/merge` | 合并任务（挑选合并） | task:merge |
| task_stats | `GET /api/v1/tasks/stats` | 任务域全量聚合统计 | task:read |
| task_get_progress | `GET /api/v1/tasks/{task_id}/progress` | 任务执行进度 | task:read |
| task_batch_action | `POST /api/v1/tasks/batch-action` | 批量操作（ids/action） | task:batch |
| task_validate | `POST /api/v1/tasks/validate` | 创建前资源归属预检 | task:create |
| task_get_labs | `GET /api/v1/tasks/{task_id}/labs` | 任务关联实验室 | task:read |
| task_get_case_detail | `GET /api/v1/tasks/{task_id}/cases/{case_id}/detail` | 任务内用例执行详情 | task:read |
| task_get_case_results | `GET /api/v1/tasks/{task_id}/cases/{case_id}/results` | 任务内用例结果 | task:read |
| task_remove_case | `DELETE /api/v1/tasks/{task_id}/cases/{case_id}` | 从任务移除用例 | task:execute |
| task_update_cases | `PATCH /api/v1/tasks/{task_id}/cases` | 更新任务用例集合（case_ids） | task:update |
| task_get_stats | `GET /api/v1/tasks/{task_id}/stats` | 任务内统计 | task:read |

```bash
# 列出任务（搜索 + 分页）
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/tasks?search=唤醒&page=1&per_page=10"

# 创建任务
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"唤醒率回归-20261022","case_ids":["tc_1001","tc_1002"]}' \
  "$BASE_URL/api/v1/tasks"

# 启动任务
curl -X POST -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks/42/start"

# 任务进度
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks/42/progress"
```

### 5.2 已发布任务 published_task（`published_task_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| published_task_list | `GET /api/v1/published-tasks` | 列出已发布任务 | published_task:read |
| published_task_get | `GET /api/v1/published-tasks/{published_task_id}` | 详情 | published_task:read |
| published_task_execute | `POST /api/v1/published-tasks/{published_task_id}/execute` | 执行已发布任务 | published_task:execute |

### 5.3 测试用例 testcase（`testcase_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| testcase_list | `GET /api/v1/testcases` | 列出用例（keyword/status/page/per_page） | testcase:read |
| testcase_get | `GET /api/v1/testcases/{tc_id}` | 用例详情 | testcase:read |
| testcase_create | `POST /api/v1/testcases` | 创建用例 | testcase:create |
| testcase_update | `PUT /api/v1/testcases/{tc_id}` | 修改用例 | testcase:update |
| testcase_delete | `DELETE /api/v1/testcases/{tc_id}` | 删除用例 | testcase:delete |
| testcase_copy | `POST /api/v1/testcases/{tc_id}/copy` | 复制用例 | testcase:copy |
| testcase_export | `POST /api/v1/testcases/export` | 导出用例（ids） | testcase:import_export |
| testcase_import | `POST /api/v1/testcases/import` | 导入用例（multipart，建议直接调接口） | testcase:import_export |

```bash
# 按关键词搜索用例
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/testcases?keyword=唤醒&page=1&per_page=10"
```

### 5.4 音频 audio（`audio_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| audio_list | `GET /api/v1/audios` | 列出音频（keyword/page/per_page） | audio:read |
| audio_get | `GET /api/v1/audios/{audio_id}` | 音频详情 | audio:read |
| audio_get_by_ids | `POST /api/v1/audios/by-ids` | 按 ID 列表批量获取 | audio:read |
| audio_get_by_md5 | `POST /api/v1/audios/by-md5` | 按 MD5 查音频 | audio:read |
| audio_list_tags | `GET /api/v1/audios/tags` | 音频标签 | audio:read |
| audio_update_metadata | `PUT /api/v1/audios/{audio_id}/metadata` | 更新元数据（name 等） | audio:update |
| audio_convert | `POST /api/v1/audios/{audio_id}/convert` | 音频转码 | audio:convert |
| audio_delete | `DELETE /api/v1/audios/{audio_id}` | 删除音频 | audio:delete |
| audio_url_import | `POST /api/v1/audios/url-import` | URL 导入音频 | audio:upload |
| audio_upload_init | `POST /api/v1/audios/upload/init` | 分片上传初始化 | audio:upload |
| audio_upload_register | `POST /api/v1/audios/upload/register` | 分片上传注册 | audio:upload |
| audio_upload_merge | `POST /api/v1/audios/upload/merge` | 分片上传合并 | audio:upload |
| audio_upload_progress | `GET /api/v1/audios/upload/progress` | 上传进度 | audio:read |
| audio_upload_presign | `POST /api/v1/audios/upload/presign` | OSS 直传预签名（整文件） | audio:upload |
| audio_upload_presign_part | `POST /api/v1/audios/upload/presign-part` | OSS 直传预签名（分片） | audio:upload |
| audio_upload_complete_direct | `POST /api/v1/audios/upload/complete-direct` | OSS 直传完成确认 | audio:upload |
| audio_batch_annotations | `POST /api/v1/audios/batch/annotations` | 批量更新标注 | audio:update |
| audio_batch_action | `POST /api/v1/audios/batch-action` | 批量操作（ids/action） | audio:update |
| audio_features | `GET /api/v1/audios/{audio_id}/features` | 音频特征分析 | audio:read |
| audio_quality | `GET /api/v1/audios/{audio_id}/quality` | 音频质量评估 | audio:read |
| audio_process | `POST /api/v1/audios/{audio_id}/process` | 处理（降噪/增益/剪辑） | audio:update |
| audio_get_algorithms | `GET /api/v1/audios/{audio_id}/algorithms` | 音频已配算法 | audio:read |
| audio_update_algorithms | `PUT /api/v1/audios/{audio_id}/algorithms` | 更新算法配置 | audio:update |
| audio_playback_history | `GET /api/v1/audios/{audio_id}/playback-history` | 播放历史 | audio:read |
| audio_folder_tree | `POST /api/v1/audios/folder-tree` | 音频目录树 | audio:folder |

> 音频二进制流 / 下载（`stream-by-path`、`download`、`/{audio_id}/stream`）与分片 chunk 字节上传不经 MCP / skill 暴露，请走平台前端或直接 HTTP。

```bash
# 音频列表
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/audios?page=1&per_page=10"

# 按 MD5 定位音频
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"md5":"d41d8cd98f00b204e9800998ecf8427e"}' "$BASE_URL/api/v1/audios/by-md5"
```

### 5.5 被测设备 device（`device_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| device_list | `GET /api/v1/test-devices` | 列出设备（page/per_page/status） | device:read |
| device_get | `GET /api/v1/test-devices/{device_id}` | 设备详情 | device:read |
| device_create | `POST /api/v1/test-devices` | 创建设备 | device:create |
| device_update | `PUT /api/v1/test-devices/{device_id}` | 修改设备 | device:update |
| device_delete | `DELETE /api/v1/test-devices/{device_id}` | 删除设备 | device:delete |
| device_connect | `POST /api/v1/test-devices/{device_id}/connect` | 连接设备 | device:control |
| device_disconnect | `POST /api/v1/test-devices/{device_id}/disconnect` | 断开设备 | device:control |
| device_reboot | `POST /api/v1/test-devices/{device_id}/reboot` | 重启设备 | device:control |
| device_shutdown | `POST /api/v1/test-devices/{device_id}/shutdown` | 关闭设备 | device:control |
| device_health_check | `POST /api/v1/test-devices/health-check` | 健康检查 | device:control |
| device_scan | `POST /api/v1/test-devices/scan` | 扫描设备 | device:control |
| device_batch_action | `POST /api/v1/test-devices/batch` | 设备批量操作 | device:control |
| device_test | `POST /api/v1/test-devices/{device_id}/test` | 设备测试 | device:control |
| device_stop_test | `POST /api/v1/test-devices/{device_id}/stop-test` | 停止设备测试 | device:control |
| device_install_app | `POST /api/v1/test-devices/{device_id}/install-app` | 安装应用 | device:control |
| device_uninstall_app | `POST /api/v1/test-devices/{device_id}/uninstall-app` | 卸载应用 | device:control |
| device_export | `GET /api/v1/test-devices/export` | 导出设备 | device:read |
| device_import | `POST /api/v1/test-devices/import` | 导入设备 | device:create |
| device_status_list | `GET /api/v1/test-devices/status` | 设备状态汇总 | device:read |
| device_driver_keywords | `GET /api/v1/test-devices/driver-keywords` | 驱动关键词 | device:read |
| device_serials | `GET /api/v1/test-devices/serials` | 可用序列号 | device:read |
| device_status_history | `GET /api/v1/test-devices/status-history` | 状态历史（全局） | device:read |
| device_get_status_history | `GET /api/v1/test-devices/{device_id}/status-history` | 状态历史（单设备） | device:read |
| device_group_list | `GET /api/v1/test-devices/device-groups` | 设备分组列表 | device:read |
| device_group_get | `GET /api/v1/test-devices/device-groups/{group_id}` | 分组详情 | device:read |
| device_group_create | `POST /api/v1/test-devices/device-groups` | 创建设备分组 | device:create |
| device_group_update | `PUT /api/v1/test-devices/device-groups/{group_id}` | 修改分组 | device:update |
| device_group_move | `PUT /api/v1/test-devices/device-groups/{group_id}/move` | 移动分组 | device:update |
| device_group_delete | `DELETE /api/v1/test-devices/device-groups/{group_id}` | 删除分组 | device:delete |
| device_group_add_devices | `POST /api/v1/test-devices/device-groups/{group_id}/devices` | 向分组添加设备 | device:update |
| device_group_remove_devices | `POST /api/v1/test-devices/device-groups/{group_id}/remove-devices` | 从分组移除设备 | device:update |
| device_alarm_rule_list | `GET /api/v1/test-devices/alarm-rules` | 告警规则列表 | device:read |
| device_alarm_rule_create | `POST /api/v1/test-devices/alarm-rules` | 创建告警规则 | device:update |
| device_alarm_rule_update | `PUT /api/v1/test-devices/alarm-rules/{rule_id}` | 修改告警规则 | device:update |
| device_alarm_rule_delete | `DELETE /api/v1/test-devices/alarm-rules/{rule_id}` | 删除告警规则 | device:update |
| device_alarm_list | `GET /api/v1/test-devices/alarms` | 设备告警列表（page/per_page） | device:read |
| device_alarm_acknowledge | `POST /api/v1/test-devices/alarms/{alarm_id}/acknowledge` | 确认告警 | device:control |

### 5.6 评估 evaluation（`evaluation_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| evaluation_dimension_list | `GET /api/v1/evaluation/dimensions` | 评估维度列表（keyword/page/per_page） | evaluation:read |
| evaluation_dimension_get | `GET /api/v1/evaluation/dimensions/{dim_id}` | 维度详情 | evaluation:read |
| evaluation_dimension_create | `POST /api/v1/evaluation/dimensions` | 创建维度 | evaluation:dim_manage |
| evaluation_dimension_update | `PUT /api/v1/evaluation/dimensions/{dim_id}` | 修改维度 | evaluation:dim_manage |
| evaluation_dimension_delete | `DELETE /api/v1/evaluation/dimensions/{dim_id}` | 删除维度 | evaluation:dim_manage |
| evaluation_category_list | `GET /api/v1/evaluation/categories` | 评估分类列表 | evaluation:read |
| evaluation_category_create | `POST /api/v1/evaluation/categories` | 创建分类 | evaluation:category_manage |
| evaluation_task_reevaluate | `POST /api/v1/evaluation/task/reevaluate` | 触发任务重新评估（task_id 等） | evaluation:execute |

### 5.7 报告 report（`report_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| report_list | `GET /api/v1/reports` | 列出报告（keyword/page/per_page） | report:read |
| report_get | `GET /api/v1/reports/{report_id}` | 报告详情 | report:read |
| report_by_task | `GET /api/v1/reports/by_task/{task_id}` | 按任务获取报告 | report:read |
| report_generate_task | `POST /api/v1/reports/generate-task` | 按任务生成报告（task_id 等） | report:create |
| report_regenerate | `POST /api/v1/reports/{report_id}/regenerate` | 重新生成报告 | report:create |
| report_update | `PUT /api/v1/reports/{report_id}` | 修改报告 | report:update |
| report_delete | `DELETE /api/v1/reports/{report_id}` | 删除报告 | report:delete |
| report_batch_delete | `POST /api/v1/reports/batch-delete` | 批量删除（ids） | report:delete |
| report_publish | `POST /api/v1/reports/{report_id}/publish` | 发布报告 | report:publish |
| report_compare | `POST /api/v1/reports/compare` | 报告对比 | report:compare |
| report_secondary_compare | `POST /api/v1/reports/secondary-compare` | 报告二次对比 | report:compare |
| report_progress | `GET /api/v1/reports/{report_id}/progress` | 报告生成进度 | report:read |
| report_cases | `GET /api/v1/reports/{report_id}/cases` | 报告内用例 | report:read |
| report_cases_search | `POST /api/v1/reports/{report_id}/cases/search` | 搜索报告内用例 | report:read |
| report_case_logs | `GET /api/v1/reports/{report_id}/cases/{case_id}/logs` | 报告内用例日志 | report:read |
| report_case_averages | `POST /api/v1/reports/case-averages` | 用例平均值 | report:read |
| report_statistics | `GET /api/v1/reports/statistics` | 报告统计 | report:read |
| report_statistics_trend | `GET /api/v1/reports/statistics/trend` | 报告统计趋势 | report:read |
| report_statistics_report | `POST /api/v1/reports/statistics/report` | 生成统计报告 | report:read |
| report_tab_counts | `GET /api/v1/reports/tab-counts` | 报告页签计数 | report:read |
| report_export_get | `GET /api/v1/reports/export` | 导出报告（GET） | report:read |
| report_export | `POST /api/v1/reports/export` | 导出报告（POST，report_ids/格式） | report:read |
| report_share_create | `POST /api/v1/reports/{report_id}/share` | 创建分享链接 | report:update |
| report_share_list | `GET /api/v1/reports/{report_id}/share` | 分享链接列表 | report:update |
| report_share_revoke | `DELETE /api/v1/reports/{report_id}/share/{token}` | 撤销分享 | report:update |

```bash
# 报告列表
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/reports?page=1&per_page=10"

# 按任务生成报告
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"task_id":42}' "$BASE_URL/api/v1/reports/generate-task"
```

### 5.8 算法 algorithm（`algorithm_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| algorithm_definition_list | `GET /api/v1/algorithm/definitions` | 算法定义列表 | algorithm:read |
| algorithm_definition_get | `GET /api/v1/algorithm/definitions/{algo_type}` | 定义详情 | algorithm:read |
| algorithm_definition_create | `POST /api/v1/algorithm/definitions` | 创建定义 | algorithm:definition_manage |
| algorithm_definition_update | `PUT /api/v1/algorithm/definitions/{algo_type}` | 修改定义 | algorithm:definition_manage |
| algorithm_definition_delete | `DELETE /api/v1/algorithm/definitions/{algo_type}` | 删除定义 | algorithm:definition_manage |
| algorithm_definition_save | `PUT /api/v1/algorithm/definitions/save` | 整体保存定义 | algorithm:definition_manage |
| algorithm_definition_draft | `PUT /api/v1/algorithm/definitions/draft` | 保存定义草稿 | algorithm:definition_manage |
| algorithm_definition_draft_get | `GET /api/v1/algorithm/definitions/draft/{algo_type}` | 获取定义草稿 | algorithm:read |
| algorithm_group_list | `GET /api/v1/algorithm/groups` | 算法分组列表 | algorithm:read |
| algorithm_group_get | `GET /api/v1/algorithm/groups/{group_id}` | 分组详情 | algorithm:read |
| algorithm_group_create | `POST /api/v1/algorithm/groups` | 创建分组 | algorithm:group_manage |
| algorithm_group_update | `PUT /api/v1/algorithm/groups/{group_id}` | 修改分组 | algorithm:group_manage |
| algorithm_group_delete | `DELETE /api/v1/algorithm/groups/{group_id}` | 删除分组 | algorithm:group_manage |
| algorithm_param_list | `GET /api/v1/algorithm/params` | 算法参数列表 | algorithm:read |
| algorithm_param_get | `GET /api/v1/algorithm/params/{param_id}` | 参数详情 | algorithm:read |
| algorithm_param_create | `POST /api/v1/algorithm/params` | 创建参数 | algorithm:param_manage |
| algorithm_param_update | `PUT /api/v1/algorithm/params/{param_id}` | 修改参数 | algorithm:param_manage |
| algorithm_param_delete | `DELETE /api/v1/algorithm/params/{param_id}` | 删除参数 | algorithm:param_manage |
| algorithm_case_param_list | `GET /api/v1/algorithm/case-params` | 用例算法参数列表 | algorithm:read |
| algorithm_case_param_get | `GET /api/v1/algorithm/case-params/{param_id}` | 用例参数详情 | algorithm:read |
| algorithm_case_param_create | `POST /api/v1/algorithm/case-params` | 创建用例参数 | algorithm:case_param_manage |
| algorithm_case_param_update | `PUT /api/v1/algorithm/case-params/{param_id}` | 修改用例参数 | algorithm:case_param_manage |
| algorithm_case_param_delete | `DELETE /api/v1/algorithm/case-params/{param_id}` | 删除用例参数 | algorithm:case_param_manage |
| algorithm_reference_param_list | `GET /api/v1/algorithm/reference-params` | 参考算法参数列表 | algorithm:read |
| algorithm_reference_param_get | `GET /api/v1/algorithm/reference-params/{param_id}` | 详情 | algorithm:read |
| algorithm_reference_param_create | `POST /api/v1/algorithm/reference-params` | 创建参考参数 | algorithm:param_manage |
| algorithm_reference_param_update | `PUT /api/v1/algorithm/reference-params/{param_id}` | 修改参考参数 | algorithm:param_manage |
| algorithm_reference_param_delete | `DELETE /api/v1/algorithm/reference-params/{param_id}` | 删除参考参数 | algorithm:param_manage |
| algorithm_mapping_list | `GET /api/v1/algorithm/mappings` | 算法映射列表 | algorithm:read |
| algorithm_mapping_create | `POST /api/v1/algorithm/mappings` | 创建映射 | algorithm:definition_manage |
| algorithm_mapping_update | `PUT /api/v1/algorithm/mappings/{mapping_id}` | 修改映射 | algorithm:definition_manage |
| algorithm_mapping_delete | `DELETE /api/v1/algorithm/mappings/{mapping_id}` | 删除映射 | algorithm:definition_manage |
| algorithm_options | `GET /api/v1/algorithm/options` | 下拉选项 | algorithm:read |
| algorithm_form_schema | `GET /api/v1/algorithm/form-schema/{algo_type}` | 表单 Schema | algorithm:read |
| algorithm_dimension_list | `GET /api/v1/algorithm/dimensions/{algo_type}` | 算法维度 | algorithm:read |
| algorithm_dimension_create | `POST /api/v1/algorithm/dimensions/{algo_type}` | 创建算法维度 | algorithm:definition_manage |
| algorithm_dimension_relation_create | `POST /api/v1/algorithm/dimension-relations` | 创建维度关系 | algorithm:definition_manage |
| algorithm_dimension_relation_update | `PUT /api/v1/algorithm/dimension-relations/{relation_id}` | 修改维度关系 | algorithm:definition_manage |
| algorithm_dimension_relation_delete | `DELETE /api/v1/algorithm/dimension-relations/{relation_id}` | 删除维度关系 | algorithm:definition_manage |
| algorithm_dimension_params | `GET /api/v1/algorithm/dimension-params/{dimension_id}` | 维度参数 | algorithm:read |
| algorithm_extract_params | `POST /api/v1/algorithm/extract-params` | 抽取算法参数 | algorithm:param_manage |
| algorithm_reload | `POST /api/v1/algorithm/reload` | 重新加载算法配置 | algorithm:definition_manage |
| algorithm_import | `POST /api/v1/algorithm/import` | 导入算法定义 | algorithm:definition_manage |
| algorithm_bulk_delete | `POST /api/v1/algorithm/bulk-delete` | 批量删除 | algorithm:definition_manage |

### 5.9 标签 tag（`tag_*`）与用例分组 group（`group_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| tag_list | `GET /api/v1/tags` | 列出标签 | tag:read |
| tag_get | `GET /api/v1/tags/{tag_id}` | 标签详情 | tag:read |
| tag_create | `POST /api/v1/tags` | 创建标签（name/category 等） | tag:create |
| tag_update | `PUT /api/v1/tags/{tag_id}` | 修改标签 | tag:update |
| tag_delete | `DELETE /api/v1/tags/{tag_id}` | 删除标签 | tag:delete |
| group_list | `GET /api/v1/groups` | 用例分组列表 | group:read |
| group_create | `POST /api/v1/groups` | 创建分组（name 等） | group:create |
| group_update | `PUT /api/v1/groups/{group_id}` | 修改分组 | group:update |
| group_delete | `DELETE /api/v1/groups/{group_id}` | 删除分组 | group:delete |

```bash
# 创建标签
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"唤醒率回归","category":"回归"}' "$BASE_URL/api/v1/tags"
```

### 5.10 数据可见性分享 `*:share`（`*_set_visibility`）

可见性取值仅 **`shared` / `private`**。

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| task_set_visibility | `PATCH /api/v1/tasks/{task_id}/visibility` | 任务可见性 | task:share |
| testcase_set_visibility | `PATCH /api/v1/testcases/{tc_id}/visibility` | 用例可见性 | testcase:share |
| report_set_visibility | `PATCH /api/v1/reports/{report_id}/visibility` | 报告可见性 | report:share |
| tag_set_visibility | `PATCH /api/v1/tags/{tag_id}/visibility` | 标签可见性 | tag:share |
| group_set_visibility | `PATCH /api/v1/groups/{group_id}/visibility` | 分组可见性 | group:share |
| evaluation_dimension_set_visibility | `PATCH /api/v1/evaluation/dimensions/{dim_id}/visibility` | 评估维度可见性 | evaluation:share |

### 5.11 数据转移 data-transfer（`data_transfer_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| data_transfer_export | `POST /api/v1/data-transfer/export` | 导出任务数据（ZIP，task_id 等） | task:export |
| data_transfer_import_preview | `POST /api/v1/data-transfer/import/preview` | 导入预检 | task:import |
| data_transfer_import | `POST /api/v1/data-transfer/import` | 执行任务数据导入 | task:import |

### 5.12 收藏 / 回收站（INT-141）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| favorites_list | `GET /api/v1/favorites` | 当前用户收藏 ID 列表（entity_type=task/testcase/report，空=全部） | 仅需登录 |
| task_favorite | `POST /api/v1/tasks/{task_id}/favorite` | 收藏任务 | task:read |
| task_restore | `POST /api/v1/tasks/{task_id}/restore` | 从回收站恢复任务 | task:delete |
| task_purge | `DELETE /api/v1/tasks/{task_id}/purge` | 彻底删除任务 | task:delete |
| testcase_favorite | `POST /api/v1/testcases/{tc_id}/favorite` | 收藏用例 | testcase:read |
| report_favorite | `POST /api/v1/reports/{report_id}/favorite` | 收藏报告 | report:read |

### 5.13 Benchmark 排行（`benchmark_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| benchmark_ranking | `GET /api/v1/benchmarks/ranking` | Benchmark 排行（page/per_page） | benchmark:ranking:read |
| benchmark_ranking_compute | `POST /api/v1/benchmarks/ranking/compute` | 触发排行计算 | benchmark:ranking:compute |
| benchmark_baselines | `GET /api/v1/benchmarks/baselines` | Benchmark 基线 | benchmark:baseline:read |
| benchmark_reports | `GET /api/v1/benchmarks/reports` | Benchmark 报告 | benchmark:report:read |

### 5.14 Report Studio（`report_studio_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| report_studio_create_document | `POST /api/v1/report-studio/documents` | 创建文档草稿 | report:studio:create |
| report_studio_get_document | `GET /api/v1/report-studio/documents/{doc_id}` | 获取文档 | report:read |
| report_studio_update_document | `PUT /api/v1/report-studio/documents/{doc_id}` | 编辑文档 | report:studio:edit |
| report_studio_export_document | `POST /api/v1/report-studio/documents/{doc_id}/exports` | 导出作业 | report:studio:export |

### 5.15 日志只读 `log:read`（`log_*`）

| MCP 工具 | 端点（方法） | 说明 | 权限 |
| --- | --- | --- | --- |
| log_list | `GET /api/v1/logs` | 测试执行日志（page/per_page/keyword/level） | log:read |
| log_stats | `GET /api/v1/logs/stats` | 日志统计 | log:read |

## 6. MCP 接入

### 6.1 配置模板

`mcp.json`（同目录）为 MCP 配置模板，URL 指向本平台 MCP 端点。在支持 MCP 的客户端（如 Claude Code / Claude Desktop）中添加远程 MCP：

```json
{
  "name": "intelligent-audio-test",
  "description": "智能音频测试平台 MCP（联接你的 agent）：任务/用例/音频/设备/评估/报告/算法/标签/分组等业务能力",
  "type": "http",
  "url": "{{BASE_URL}}/api/v1/mcp",
  "headers": {
    "Authorization": "Bearer 在此填入你的 Access Token"
  }
}
```

### 6.2 协议（JSON-RPC 2.0）

端点实现 JSON-RPC 2.0：`initialize` / `notifications/initialized` / `ping` / `tools/list` / `tools/call`（`resources/list` 返回空）。Accept 含 `text/event-stream` 时按 streamable HTTP（SSE 帧）响应；无 `id` 的通知返回 202 空响应。

- `tools/list`：返回全部工具及入参 Schema（工具名 = 5.x 各表「MCP 工具」列；入参均为 snake_case）。
- `tools/call`：携带 `name` + `arguments`；越权（token scopes 不足）返回 `isError=true` + 403 语义；目标 REST 4xx/5xx 透传为调用失败。

`tools/call` 示例：

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"task_list","arguments":{"search":"唤醒","page":1,"per_page":10}}}' \
  "$BASE_URL/api/v1/mcp"
```

响应（`result.content[0].text` 为 JSON 字符串，即目标 REST 的响应信封）：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "isError": false,
    "content": [
      {"type": "text", "text": "{\"success\":true,\"code\":0,\"message\":\"Success\",\"data\":{\"items\":[...],\"total\":2,\"page\":1,\"pages\":1,\"per_page\":10}}"}
    ]
  }
}
```

## 7. 端到端示例（任务执行 → 报告）

```bash
BASE_URL="${INTELLIGENT_AUDIO_TEST_BASE_URL:-{{BASE_URL}}}"
TOKEN="${INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN}"

# 1) 搜索用例
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/testcases?keyword=唤醒&page=1&per_page=10"

# 2) 创建任务（name 必填）
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"唤醒率回归-20261022","case_ids":["tc_1001"]}' "$BASE_URL/api/v1/tasks"

# 3) 启动任务（替换为返回的任务 id）
curl -X POST -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks/42/start"

# 4) 轮询执行进度
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks/42/progress"

# 5) 执行完成后按任务生成报告
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"task_id":42}' "$BASE_URL/api/v1/reports/generate-task"
```

## 8. 注意事项

- **越权语义**：token scopes 不含某接口所需权限时调用被拒绝（403）。所需权限码见 5.x 各表「权限」列。
- **除外边界**：个人信息（个人资料 / 改密 / 登录态 / token 管理本身）与系统设置（用户 / 权限 / 系统参数 / 集成配置）不在覆盖范围，MCP 工具清单中不提供。
- **非 JSON 通道不承载**：音频二进制流 / 下载、分片 chunk 字节上传、报告用例日志文件下载，不经 skill / MCP 暴露。
- **token 生命周期**：默认有效期 30 天，可配置永不过期；停用立即失效；删除（软删）后不可恢复；每用户上限默认 20 个。
- **服务地址**：`{{BASE_URL}}` 默认取你下载时的站点地址；如网络环境不同，请修改为实际可访问的地址。
- **安全**：Access Token 只存哈希、明文仅一次显示，请妥善保存，勿写入公共仓库 / 日志 / 聊天记录。
