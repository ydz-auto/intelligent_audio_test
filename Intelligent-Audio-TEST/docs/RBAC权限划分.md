# RBAC 权限划分文档

> 本文档定义智能语音测试平台的 RBAC（Role-Based Access Control）角色与权限划分方案，作为认证鉴权落地的依据。
>
> 关联文档：[oauth.md](./oauth.md)（认证方案设计）、[系统架构.md](./系统架构.md)、数据模型 [shared/models/models/user_models.py](../shared/models/models/user_models.py)

## 一、现状与目标

### 1.1 当前状态

| 维度 | 状态 |
|---|---|
| RBAC 数据模型 | **已定义** — `Role` / `Permission` / `RolePermission` / `UserPermission` / `User` 表已建，User 内置 `has_permission()` |
| 权限命名约定 | `资源:操作`（如 `task:create`），支持 `*` 通配 |
| 认证中间件 | **未实现** — `middleware.py` 仅含 `RequestAdapterMiddleware`，无鉴权 |
| 路由权限校验 | **未接入** — 16 个蓝图 ~170 个端点完全开放，无 `require_permission` 调用 |
| 用户/角色/权限管理 API | **未实现** — 无 `auth_bp` / `user_bp` / `role_bp` 路由 |

### 1.2 目标

- 为系统所有 REST 端点定义清晰的权限点
- 划分 4 个系统内置角色：`admin` / `tester` / `algo_engineer` / `device_admin`，覆盖 [Agent 化用户场景](../doc/agent化/02_用户场景.md) 中的 5 个业务角色
- 提供权限点 → 角色 → 端点的完整映射表，供落地实现参考

## 二、角色定义

角色划分对齐 [Agent 化用户场景](../doc/agent化/02_用户场景.md) 中的 5 个业务角色，合并职责相近的为 4 个系统内置角色：

| 角色 | name | 对应业务角色 | 说明 | is_system |
|---|---|---|---|---|
| 超级管理员 | `admin` | — | 拥有所有权限，可管理用户/角色/权限 | `true` |
| 测试工程师 | `tester` | 测试工程师 + 测试主管 | 可执行测试、管理用例/音频/任务/报告等业务资源，支持 Solo 模式批量操作，不含设备管理和用户角色管理 | `true` |
| 算法工程师 | `algo_engineer` | 算法工程师 + 质量负责人 | 可查看报告、结果对比、趋势分析、报告发布、算法配置管理，不可执行测试和设备操作 | `true` |
| 设备管理员 | `device_admin` | 设备管理员 | 可管理被测设备/播放设备/SPL 校准/驱动生成，不可管理用例/任务/报告 | `true` |
| 游客 | `guest` | — | 只读访问报告和首页统计，不可看日志、不可执行任何写操作 | `true` |

> 系统内置角色 `is_system=true`，不可删除，但可按需调整权限。未来可新增自定义角色，由 `admin` 分配权限点。

### 2.1 业务角色与系统角色映射

| 业务角色（Agent 场景） | 系统角色 | 典型需求 |
|---|---|---|
| 测试工程师 | `tester` | 快速建用例、跑测试、出报告 |
| 测试主管 | `tester` | 批量任务、无人值守（Solo 模式）、结果对比 |
| 算法工程师 | `algo_engineer` | 查看报告、结果对比、找优化方向、算法配置 |
| 质量负责人 | `algo_engineer` | 报告审阅、趋势分析、跨任务对比、报告发布 |
| 设备管理员 | `device_admin` | 新设备接入、驱动生成、设备健康、SPL 校准 |

## 三、权限点定义

权限点命名遵循 `资源:操作` 约定，与 `Permission.name` 字段对应。

### 3.1 任务管理（task）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `task:read` | 查看任务列表/详情/进度/统计 | `GET /api/v1/tasks`、`GET /tasks/{id}`、`GET /tasks/{id}/progress`、`GET /tasks/{id}/stats`、`GET /tasks/{id}/cases/{cid}/detail`、`GET /tasks/{id}/cases/{cid}/results` |
| `task:create` | 创建任务 | `POST /api/v1/tasks` |
| `task:update` | 修改任务 | `PUT /api/v1/tasks/{id}` |
| `task:delete` | 删除任务 | `DELETE /api/v1/tasks/{id}` |
| `task:execute` | 启动/停止/重试/控制任务 | `POST /tasks/{id}/start`、`POST /tasks/{id}/stop`、`POST /tasks/{id}/retry`、`POST /tasks/{id}/control`、`POST /execution/{id}/start`、`POST /execution/{id}/control` |
| `task:merge` | 合并任务 | `POST /api/v1/tasks/merge` |
| `task:batch` | 批量操作任务 | `POST /api/v1/tasks/batch-action`、`PATCH /tasks/{id}/cases` |
| `task:reextract` | 重新提取设备结果 | `POST /api/v1/tasks/{id}/reextract` |

### 3.2 测试用例（testcase）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `testcase:read` | 查看用例列表/详情/统计/标签 | `GET /api/v1/testcases`、`GET /testcases/{id}`、`GET /testcases/stats`、`GET /testcases/tags`、`GET /testcases/refresh_task/{tid}`、`GET /testcases/{id}/rounds/{r}/ref-params` |
| `testcase:create` | 创建用例 | `POST /api/v1/testcases`、`POST /testcases/batch` |
| `testcase:update` | 修改用例/参考参数 | `PUT /api/v1/testcases/{id}`、`PUT /testcases/{id}/rounds/{r}/ref-params` |
| `testcase:delete` | 删除用例 | `DELETE /api/v1/testcases/{id}` |
| `testcase:copy` | 复制用例 | `POST /api/v1/testcases/{id}/copy` |
| `testcase:preview` | 预览执行/停止预览 | `POST /testcases/{id}/preview`、`POST /testcases/{id}/stop_preview`、`POST /testcases/{id}/stop-preview` |
| `testcase:import_export` | 导入/导出/模板下载 | `POST /testcases/export`、`POST /testcases/import`、`GET /testcases/template/download`、`POST /testcases/import/preview` |

### 3.3 音频管理（audio）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `audio:read` | 查看音频详情/标签/算法/流播放 | `GET /audios/{id}`、`GET /audios/tags`、`GET /audios/{id}/algorithms`、`GET /audios/{id}/stream`、`GET /audios/stream-by-path`、`GET /audios/upload/progress` |
| `audio:upload` | 上传/导入/录制音频 | `POST /audios/by-ids`、`POST /audios/by-md5`、`POST /audios/url-import`、`POST /audios/record`、`POST /audios/upload/*`（init/register/chunk/merge/presign/presign-part/complete-direct） |
| `audio:update` | 修改音频元数据/算法/标注 | `PUT /audios/{id}/metadata`、`PUT /audios/{id}/algorithms`、`PUT /audios/batch/algorithms`、`POST /audios/batch/annotations`、`POST /audios/batch-action` |
| `audio:delete` | 删除音频 | `DELETE /api/v1/audios/{id}` |
| `audio:convert` | 音频转码/预览 | `POST /audios/{id}/convert`、`POST /audios/{id}/preview`、`POST /audios/{id}/stop-preview` |
| `audio:folder` | 文件夹树管理 | `POST /api/v1/audios/folder-tree` |

### 3.4 被测设备（device）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `device:read` | 查看设备列表/详情/状态/驱动关键字/序列号 | `GET /api/v1/test-devices`、`GET /test-devices/status`、`GET /test-devices/{id}`、`GET /test-devices/driver-keywords`、`GET /test-devices/serials` |
| `device:create` | 新增设备 | `POST /api/v1/test-devices` |
| `device:update` | 修改设备 | `PUT /api/v1/test-devices/{id}` |
| `device:delete` | 删除设备 | `DELETE /api/v1/test-devices/{id}` |
| `device:control` | 健康检查/扫描/测试/停止测试 | `POST /test-devices/health-check`、`POST /test-devices/scan`、`POST /test-devices/{id}/test`、`POST /test-devices/{id}/stop-test` |

### 3.5 播放设备（playback）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `playback:read` | 查看播放设备列表/详情/状态 | `GET /api/v1/playback-devices`、`GET /playback-devices/{id}`、`GET /playback-devices/check-status` |
| `playback:create` | 新增播放设备 | `POST /api/v1/playback-devices` |
| `playback:update` | 修改播放设备/关联 SPL | `PUT /api/v1/playback-devices/{id}`、`POST /playback-devices/{id}/associate-spl` |
| `playback:delete` | 删除播放设备 | `DELETE /api/v1/playback-devices/{id}` |
| `playback:control` | 扫描/测试/停止测试 | `POST /playback-devices/scan`、`POST /playback-devices/{id}/test`、`POST /playback-devices/{id}/stop-test` |

### 3.6 声压级映射（spl）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `spl:read` | 查看 SPL 映射/历史/统计/按设备查询 | `GET /api/v1/spl`、`GET /spl/{id}`、`GET /spl/{id}/history`、`GET /spl/{id}/calibration-data`、`GET /spl/stats`、`GET /spl/by-device/{did}` |
| `spl:create` | 创建 SPL 映射 | `POST /api/v1/spl` |
| `spl:update` | 修改 SPL 映射/校准 | `PUT /api/v1/spl/{id}`、`POST /spl/{id}/calibrate` |
| `spl:delete` | 删除 SPL 映射 | `DELETE /api/v1/spl/{id}` |
| `spl:test_tone` | 测试音播放/停止 | `POST /api/v1/spl/test-tone`、`POST /spl/test-tone/stop` |

### 3.7 API 配置（api_config）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `api_config:read` | 查看 API 列表/详情 | `GET /api/v1/apis`、`GET /apis/{id}` |
| `api_config:create` | 新增 API 配置 | `POST /api/v1/apis` |
| `api_config:update` | 修改 API 配置 | `PUT /api/v1/apis/{id}` |
| `api_config:delete` | 删除 API 配置 | `DELETE /api/v1/apis/{id}` |
| `api_config:test` | 测试/停止测试 API 连接 | `POST /apis/{id}/health`、`POST /apis/{id}/stop-test` |

### 3.8 报告（report）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `report:read` | 查看报告列表/详情/进度/用例 | `GET /api/v1/reports`、`GET /reports/{id}`、`GET /reports/{id}/progress`、`GET /reports/{id}/cases`、`POST /reports/{id}/cases/search` |
| `report:create` | 生成任务报告 | `POST /api/v1/reports/generate-task` |
| `report:update` | 修改报告 | `PUT /api/v1/reports/{id}` |
| `report:delete` | 删除报告/批量删除 | `DELETE /api/v1/reports/{id}`、`POST /reports/batch-delete` |
| `report:publish` | 发布报告 | `POST /api/v1/reports/{id}/publish` |
| `report:compare` | 报告对比/二次对比/均值/导出 | `POST /reports/compare`、`POST /reports/secondary-compare`、`POST /reports/case-averages`、`POST /reports/export` |
| `report:download_log` | 下载用例日志 | `GET /api/v1/reports/{id}/cases/{cid}/logs/download` |

### 3.9 评估维度（evaluation）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `evaluation:read` | 查看维度/选项/分类 | `GET /evaluation/dimensions`、`GET /evaluation/dimensions/options`、`GET /evaluation/categories`、`GET /evaluation/dimensions/export` |
| `evaluation:execute` | 触发重新评估 | `POST /api/v1/evaluation/task/reevaluate` |
| `evaluation:dim_manage` | 维度 CRUD / 批量 / 计算 | `POST /evaluation/dimensions`、`PUT /evaluation/dimensions/{id}`、`DELETE /evaluation/dimensions/{id}`、`POST /evaluation/dimensions/{id}/calculate`、`POST /evaluation/dimensions/batch` |
| `evaluation:category_manage` | 评估分类 CRUD | `POST /evaluation/categories`、`PUT /evaluation/categories/{id}`、`DELETE /evaluation/categories/{id}` |
| `evaluation:import_export` | 维度导入/导出 | `POST /evaluation/dimensions/import`、`GET /evaluation/dimensions/export` |

### 3.10 算法配置（algorithm）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `algorithm:read` | 查看算法定义/分组/参数/用例参数 | `GET /algorithm/definitions`、`GET /algorithm/definitions/{type}`、`GET /algorithm/groups`、`GET /algorithm/groups/{id}`、`GET /algorithm/params`、`GET /algorithm/params/{id}`、`GET /algorithm/case-params`、`GET /algorithm/case-params/{id}` |
| `algorithm:definition_manage` | 算法定义 CRUD | `POST /algorithm/definitions`、`PUT /algorithm/definitions/{type}`、`DELETE /algorithm/definitions/{type}` |
| `algorithm:group_manage` | 算法分组 CRUD | `POST /algorithm/groups`、`PUT /algorithm/groups/{id}`、`DELETE /algorithm/groups/{id}` |
| `algorithm:param_manage` | 算法参数 CRUD | `POST /algorithm/params`、`PUT /algorithm/params/{id}`、`DELETE /algorithm/params/{id}` |
| `algorithm:case_param_manage` | 用例算法参数 CRUD | `POST /algorithm/case-params`、`PUT /algorithm/case-params/{id}`、`DELETE /algorithm/case-params/{id}` |

### 3.11 用例分组（group）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `group:read` | 查看用例分组列表 | `GET /api/v1/groups` |
| `group:create` | 创建分组 | `POST /api/v1/groups` |
| `group:update` | 修改分组/移动用例 | `PUT /api/v1/groups/{id}`、`POST /groups/move-cases` |
| `group:delete` | 删除分组 | `DELETE /api/v1/groups/{id}` |

### 3.12 标签管理（tag）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `tag:read` | 查看标签/分类/按分类查/名称列表 | `GET /api/v1/tags`、`GET /tags/names`、`GET /tags/by-category`、`GET /tags/{id}`、`GET /tags/categories`、`GET /tags/categories/{id}` |
| `tag:create` | 创建标签/分类 | `POST /api/v1/tags`、`POST /tags/categories` |
| `tag:update` | 修改标签/分类/批量分类 | `PUT /api/v1/tags/{id}`、`PUT /tags/categories/{id}`、`PUT /tags/batch-category` |
| `tag:delete` | 删除标签/分类 | `DELETE /api/v1/tags/{id}`、`DELETE /tags/categories/{id}` |

### 3.13 日志（log）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `log:read` | 查看日志/统计/归档状态/归档列表/归档文件 | `GET /api/v1/logs`、`GET /logs/stats`、`GET /logs/archive/status`、`GET /logs/archive/logs`、`GET /logs/archive/{filename}` |
| `log:manage` | 标记/刷新/清空/归档/删除归档 | `PUT /logs/mark`、`POST /logs/refresh`、`POST /logs/clear`、`POST /logs/archive`、`DELETE /logs/archive/{filename}` |

### 3.14 首页（home）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `home:read` | 查看首页统计汇总/详情 | `GET /api/v1/home/stats/summary`、`GET /home/stats/details` |
| `home:refresh` | 刷新首页统计 | `POST /api/v1/home/stats/refresh` |

### 3.15 实时事件（sse）

| 权限点 | 说明 | 对应端点 |
|---|---|---|
| `sse:read` | 订阅 SSE 事件流 | `GET /api/v1/sse/events` |
| `log:websocket` | 订阅 WebSocket 日志推送 | `WS /api/v1/logs`（websocket 路由） |

### 3.16 用户与权限管理（user/role/permission）

> 以下权限点对应尚未实现的 `auth_bp` / `user_bp` / `role_bp` 路由，作为后续开发的设计依据。

| 权限点 | 说明 | 计划端点 |
|---|---|---|
| `user:read` | 查看用户列表/详情 | `GET /api/v1/auth/users`、`GET /auth/users/{id}` |
| `user:create` | 创建用户（dev 模式注册） | `POST /api/v1/auth/register` |
| `user:update` | 修改用户信息/状态/密码 | `PUT /api/v1/auth/users/{id}` |
| `user:delete` | 禁用/删除用户 | `DELETE /api/v1/auth/users/{id}` |
| `user:assign_role` | 给用户分配角色 | `POST /api/v1/auth/users/{id}/role` |
| `user:grant_permission` | 授予/撤销用户额外权限 | `POST /api/v1/auth/users/{id}/permissions`、`DELETE /auth/users/{id}/permissions/{pid}` |
| `role:read` | 查看角色列表/详情/权限 | `GET /api/v1/auth/roles`、`GET /auth/roles/{id}` |
| `role:create` | 创建自定义角色 | `POST /api/v1/auth/roles` |
| `role:update` | 修改角色信息/权限分配 | `PUT /api/v1/auth/roles/{id}`、`POST /auth/roles/{id}/permissions` |
| `role:delete` | 删除自定义角色（不可删系统角色） | `DELETE /api/v1/auth/roles/{id}` |
| `permission:read` | 查看所有权限点 | `GET /api/v1/auth/permissions` |
| `auth:login` | 登录 | `GET/POST /api/v1/auth/login` |
| `auth:callback` | OAuth 回调 | `GET /api/v1/auth/callback` |
| `auth:refresh` | 刷新令牌 | `POST /api/v1/auth/refresh` |
| `auth:logout` | 登出 | `POST /api/v1/auth/logout` |
| `auth:me` | 获取当前用户信息 | `GET /api/v1/auth/me` |

## 四、角色-权限映射矩阵

### 4.1 完整矩阵

> `✓` = 拥有，`✗` = 无，`R` = 只读。`admin` 持有全部权限（下表统一标 `✓`），不再单列。

| 权限点 | admin | tester | algo_engineer | device_admin | guest |
|---|---|---|---|---|---|
| **任务** | | | | | |
| task:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| task:create | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:execute | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:merge | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:batch | ✓ | ✓ | ✗ | ✗ | ✗ |
| task:reextract | ✓ | ✓ | ✗ | ✗ | ✗ |
| **测试用例** | | | | | |
| testcase:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| testcase:create | ✓ | ✓ | ✗ | ✗ | ✗ |
| testcase:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| testcase:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| testcase:copy | ✓ | ✓ | ✗ | ✗ | ✗ |
| testcase:preview | ✓ | ✓ | ✗ | ✗ | ✗ |
| testcase:import_export | ✓ | ✓ | ✗ | ✗ | ✗ |
| **音频** | | | | | |
| audio:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| audio:upload | ✓ | ✓ | ✗ | ✗ | ✗ |
| audio:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| audio:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| audio:convert | ✓ | ✓ | ✗ | ✗ | ✗ |
| audio:folder | ✓ | ✓ | ✗ | ✗ | ✗ |
| **被测设备** | | | | | |
| device:read | ✓ | ✓ | ✗ | ✓ | ✗ |
| device:create | ✓ | ✗ | ✗ | ✓ | ✗ |
| device:update | ✓ | ✗ | ✗ | ✓ | ✗ |
| device:delete | ✓ | ✗ | ✗ | ✓ | ✗ |
| device:control | ✓ | ✗ | ✗ | ✓ | ✗ |
| **播放设备** | | | | | |
| playback:read | ✓ | ✗ | ✗ | ✓ | ✗ |
| playback:create | ✓ | ✗ | ✗ | ✓ | ✗ |
| playback:update | ✓ | ✗ | ✗ | ✓ | ✗ |
| playback:delete | ✓ | ✗ | ✗ | ✓ | ✗ |
| playback:control | ✓ | ✗ | ✗ | ✓ | ✗ |
| **声压级** | | | | | |
| spl:read | ✓ | ✗ | ✗ | ✓ | ✗ |
| spl:create | ✓ | ✗ | ✗ | ✓ | ✗ |
| spl:update | ✓ | ✗ | ✗ | ✓ | ✗ |
| spl:delete | ✓ | ✗ | ✗ | ✓ | ✗ |
| spl:test_tone | ✓ | ✗ | ✗ | ✓ | ✗ |
| **API 配置** | | | | | |
| api_config:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| api_config:create | ✓ | ✓ | ✗ | ✗ | ✗ |
| api_config:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| api_config:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| api_config:test | ✓ | ✓ | ✗ | ✗ | ✗ |
| **报告** | | | | | |
| report:read | ✓ | ✓ | ✓ | ✗ | ✓ |
| report:create | ✓ | ✓ | ✓ | ✗ | ✗ |
| report:update | ✓ | ✓ | ✓ | ✗ | ✗ |
| report:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| report:publish | ✓ | ✗ | ✓ | ✗ | ✗ |
| report:compare | ✓ | ✓ | ✓ | ✗ | ✓ |
| report:download_log | ✓ | ✓ | ✓ | ✗ | ✗ |
| **评估** | | | | | |
| evaluation:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| evaluation:execute | ✓ | ✓ | ✗ | ✗ | ✗ |
| evaluation:dim_manage | ✓ | ✓ | ✓ | ✗ | ✗ |
| evaluation:category_manage | ✓ | ✓ | ✓ | ✗ | ✗ |
| evaluation:import_export | ✓ | ✓ | ✓ | ✗ | ✗ |
| **算法配置** | | | | | |
| algorithm:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| algorithm:definition_manage | ✓ | ✗ | ✓ | ✗ | ✗ |
| algorithm:group_manage | ✓ | ✗ | ✓ | ✗ | ✗ |
| algorithm:param_manage | ✓ | ✗ | ✓ | ✗ | ✗ |
| algorithm:case_param_manage | ✓ | ✓ | ✓ | ✗ | ✗ |
| **用例分组** | | | | | |
| group:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| group:create | ✓ | ✓ | ✗ | ✗ | ✗ |
| group:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| group:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| **标签** | | | | | |
| tag:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| tag:create | ✓ | ✓ | ✗ | ✗ | ✗ |
| tag:update | ✓ | ✓ | ✗ | ✗ | ✗ |
| tag:delete | ✓ | ✓ | ✗ | ✗ | ✗ |
| **日志** | | | | | |
| log:read | ✓ | ✓ | ✓ | ✗ | ✗ |
| log:manage | ✓ | ✓ | ✗ | ✗ | ✗ |
| log:websocket | ✓ | ✓ | ✓ | ✗ | ✗ |
| **首页** | | | | | |
| home:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| home:refresh | ✓ | ✓ | ✗ | ✗ | ✗ |
| **SSE** | | | | | |
| sse:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| **用户/角色/权限管理** | | | | | |
| user:read | ✓ | ✗ | ✗ | ✗ | ✗ |
| user:create | ✓ | ✗ | ✗ | ✗ | ✗ |
| user:update | ✓ | ✗ | ✗ | ✗ | ✗ |
| user:delete | ✓ | ✗ | ✗ | ✗ | ✗ |
| user:assign_role | ✓ | ✗ | ✗ | ✗ | ✗ |
| user:grant_permission | ✓ | ✗ | ✗ | ✗ | ✗ |
| role:read | ✓ | ✗ | ✗ | ✗ | ✗ |
| role:create | ✓ | ✗ | ✗ | ✗ | ✗ |
| role:update | ✓ | ✗ | ✗ | ✗ | ✗ |
| role:delete | ✓ | ✗ | ✗ | ✗ | ✗ |
| permission:read | ✓ | ✗ | ✗ | ✗ | ✗ |
| **认证** | | | | | |
| auth:login | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth:callback | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth:refresh | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth:logout | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth:me | ✓ | ✓ | ✓ | ✓ | ✓ |

### 4.2 角色权限汇总（精简）

| 角色 | 权限范围 | 权限点数 |
|---|---|---|
| `admin` | 全部权限 | 全部（含用户/角色/权限管理） |
| `tester` | 用例/音频/任务/报告/评估/算法参数的读写 + 执行，不含设备/SPL 管理、算法定义管理、报告发布、用户角色管理 | ~55 个 |
| `algo_engineer` | 报告/评估/算法配置的读写 + 报告发布/对比，不含测试执行、设备管理、用户角色管理 | ~40 个 |
| `device_admin` | 被测设备/播放设备/SPL/首页/SSE 的全权管理，不含用例/任务/报告/算法/用户角色管理 | ~25 个 |
| `guest` | 报告只读 + 报告对比 + 首页统计 + SSE + 认证，不可看日志、不可执行任何写操作 | ~8 个 |

## 五、数据模型映射

### 5.1 表结构对应

RBAC 数据模型定义在 [user_models.py](../shared/models/models/user_models.py)：

```
users ──role_id──> roles ──< role_permissions >── permissions
  │                                                        ▲
  └──< user_permissions >──────────────────────────────────┘
        (granted=true: 授予 / granted=false: 撤销)
```

| 表 | 模型 | 用途 |
|---|---|---|
| `roles` | `Role` | 角色定义，`name` 唯一，`is_system` 标记内置角色 |
| `permissions` | `Permission` | 权限点定义，`name` 格式为 `资源:操作` |
| `role_permissions` | `RolePermission` | 角色-权限多对多映射 |
| `users` | `User` | 用户，`role_id` 关联角色 |
| `user_permissions` | `UserPermission` | 用户附加/撤销权限（`granted` 字段控制方向） |

### 5.2 权限校验逻辑

`User.has_permission(perm_name)` 已实现：

1. 先查角色权限：遍历 `self.role.permissions`，匹配 `name == perm_name` 或 `name == '*'`
2. 再查用户附加权限：`granted=true` 的授予，`granted=false` 的撤销
3. `*` 为超级通配权限，仅授予 `admin`

### 5.3 种子数据初始化

系统首次部署时应插入以下种子数据（建议在 `auth_service` 初始化脚本或 migration 中执行）：

**权限表（节选示例）**：

```sql
INSERT INTO permissions (name, description) VALUES
('task:read', '查看任务'),
('task:create', '创建任务'),
('task:execute', '执行/控制任务'),
-- ... 全部权限点见第三节
('user:assign_role', '分配用户角色'),
('role:delete', '删除角色');
```

**角色表**：

```sql
INSERT INTO roles (name, description, is_system) VALUES
('admin', '超级管理员', true),
('tester', '测试工程师（含测试主管）', true),
('algo_engineer', '算法工程师（含质量负责人）', true),
('device_admin', '设备管理员', true),
('guest', '游客', true);
```

**角色-权限映射**：

- `admin` → 关联 `name='*'` 的超级权限（或关联全部权限点）
- `tester` → 关联第四节中 `tester = ✓` 的所有权限点
- `algo_engineer` → 关联第四节中 `algo_engineer = ✓` 的所有权限点
- `device_admin` → 关联第四节中 `device_admin = ✓` 的所有权限点
- `guest` → 关联第四节中 `guest = ✓` 的所有权限点

## 六、落地实现要点

### 6.1 认证中间件

在 [api_gateway/middleware.py](../api_gateway/middleware.py) 新增 `AuthMiddleware`，从 JWT 中解析 `user_id` / `role_id` / `permissions` 注入 `request.state`，详见 [oauth.md](./oauth.md) 2.5 节。

### 6.2 路由层权限校验

```python
# 辅助函数
def require_permission(request: Request, perm: str):
    permissions = request.state.permissions or []
    if perm not in permissions and '*' not in permissions:
        raise HTTPException(403, f'缺少权限: {perm}')

# 路由示例
@router.post('')
def create_task(request: Request):
    require_permission(request, 'task:create')
    ...
```

### 6.3 白名单路由（无需鉴权）

| 路由前缀 | 说明 |
|---|---|
| `/api/v1/auth/login` | 登录入口 |
| `/api/v1/auth/callback` | OAuth 回调 |
| `/api/v1/auth/register` | 注册（仅 dev 模式） |
| `/docs`、`/openapi.json`、`/redoc` | API 文档 |
| `/api/v1/home/stats/summary` | 首页公开统计（可选） |

### 6.4 实施优先级

| 阶段 | 内容 |
|---|---|
| P1 | `AuthMiddleware` + `TokenService` + `auth_bp` 路由（登录/回调/刷新/登出/me） |
| P2 | 开发模式 `LocalOAuthProvider` + 种子数据初始化 |
| P3 | 路由层接入 `require_permission`（按业务模块逐步铺开） |
| P4 | 用户/角色/权限管理 API（`user_bp` / `role_bp`） |
| P5 | 华为云 OAuth Provider（生产模式） |
