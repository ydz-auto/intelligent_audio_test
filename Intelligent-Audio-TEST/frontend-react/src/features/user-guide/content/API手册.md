# 平台 API 手册

本手册介绍智能语音测试平台 REST API 的接入方式、认证、响应格式与核心接口示例。所有接口前缀为 `/api/v1`，统一 JSON 响应；接口事实取自 `doc/接口文档/*.md` 实测端点。

## 目录

- [准备接入信息](#准备接入信息)
- [认证](#认证)
- [响应格式与错误码](#响应格式与错误码)
- [任务接口](#任务接口)
- [用例、音频、设备与报告接口](#用例音频设备与报告接口)
- [实时推送](#实时推送)
- [错误处理与重试](#错误处理与重试)
- [常见问题](#常见问题)
- [Windows 与调用环境](#windows-与调用环境)
- [联系支持](#联系支持)

## 准备接入信息

接入前请准备以下信息：

| 信息 | 说明 |
| --- | --- |
| Base URL | `{{API_BASE_URL}}`（= 站点根 + `/api/v1`） |
| API 根地址 | `{{API_ROOT}}`（= 站点根 + `/api`，`/v1` 的前缀） |
| 访问令牌 | 登录接口返回的 JWT `access_token` |
| 请求头 | `Authorization: Bearer {token}` |

AUTH_MODE=off 部署时接口免令牌即可访问。

## 认证

### 登录

```bash
curl -X POST "{{API_BASE_URL}}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "你的用户名", "password_encrypted": "加密后的密码", "encryption_key_id": "公钥ID"}'
```

响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer",
    "user": { "user_id": 1, "username": "tester", "role_id": 2 }
  }
}
```

> 说明：登录密码按 RSA 公钥加密传输——先调 `GET {{API_BASE_URL}}/auth/login/encryption-key` 获取公钥与公钥 ID；加密开关开启时仅接受 `password_encrypted` / `encryption_key_id`。凭证错误统一回 401，以错误码区分：加密载荷无效回 105（AUTH_ENCRYPTION_INVALID），凭证错误回 106（AUTH_CREDENTIALS_INVALID）。

### 刷新与登出

```bash
curl -X POST "{{API_BASE_URL}}/auth/refresh" \
  -H "Authorization: Bearer {token}"
```

```bash
curl -X POST "{{API_BASE_URL}}/auth/logout" \
  -H "Authorization: Bearer {token}"
```

刷新接口返回新的 `access_token` 与 `token_type`；登出后令牌失效，需重新登录。

## 响应格式与错误码

### 统一响应结构

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | INTEGER | 业务错误码（0 表示成功） |
| message | STRING | 状态描述消息 |
| data | OBJECT/ARRAY | 响应数据载体（可选） |
| detail | STRING/OBJECT | 详细错误或参数校验详情（仅非 0 时提供） |

### HTTP 状态码

| 状态码 | 描述 |
| --- | --- |
| 200 | 请求成功 |
| 201 | 资源创建成功 |
| 400 | 请求参数错误或业务逻辑冲突 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 全局业务错误码

| 错误码 | 枚举值 | 描述 |
| --- | --- | --- |
| 0 | SUCCESS | 操作成功 |
| 100 | INVALID_PARAMS | 参数校验失败（格式、类型或必填项缺失） |
| 101 | MISSING_PARAMS | 缺少必填参数 |
| 102 | INVALID_TYPE | 参数类型错误 |
| 103 | UNAUTHORIZED | 未认证或凭证无效 |
| 104 | FORBIDDEN | 权限不足 |
| 105 | AUTH_ENCRYPTION_INVALID | 登录加密载荷无效 |
| 106 | AUTH_CREDENTIALS_INVALID | 登录凭证错误 |
| 200 | BUSINESS_ERROR | 通用业务错误 |
| 201 | NOT_FOUND | 目标对象不存在 |
| 202 | ALREADY_EXISTS | 对象已存在（重复创建） |
| 203 | OPERATION_FAILED | 操作执行失败 |
| 204 | CONFLICT | 状态冲突（当前状态不允许该操作） |
| 205 | TASK_ALREADY_RUNNING | 任务已在运行中 |
| 206 | TASK_NOT_FOUND | 任务不存在 |
| 210 | CALIBRATION_FAILED | 校准失败 |
| 220 | TASK_EXECUTION_ERROR | 任务执行异常 |
| 300 | SYSTEM_ERROR | 通用系统错误 |
| 301 | DATABASE_ERROR | 数据库操作异常 |
| 302 | FILE_IO_ERROR | 文件读写错误 |
| 303 | NETWORK_ERROR | 网络错误 |
| 304 | INTERNAL_SERVER_ERROR | 服务器内部错误 |
| 305 | INTERNAL_ERROR | 内部错误 |
| 306 | EXTERNAL_SERVICE_ERROR | 外部服务调用失败 |

## 任务接口

### 获取任务列表

```bash
curl -X GET "{{API_BASE_URL}}/tasks?page=1&per_page=10" \
  -H "Authorization: Bearer {token}"
```

| 参数 | 类型 | 位置 | 必需 | 描述 |
| --- | --- | --- | --- | --- |
| page | INTEGER | query | 否 | 页码，默认 1 |
| per_page | INTEGER | query | 否 | 每页记录数，默认 10 |
| status | STRING | query | 否 | `pending`/`running`/`completed`/`failed`/`stopped` |
| start_date / end_date | DATE | query | 否 | ISO 格式 `YYYY-MM-DDTHH:MM:SS` |

### 创建任务

```bash
curl -X POST "{{API_BASE_URL}}/tasks" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "回归测试任务", "case_ids": ["case_001"], "device_ids": [1], "tags": ["回归"]}'
```

### 启动、停止与控制

```bash
curl -X POST "{{API_BASE_URL}}/tasks/1/start" -H "Authorization: Bearer {token}"
curl -X POST "{{API_BASE_URL}}/tasks/1/stop" -H "Authorization: Bearer {token}"
curl -X POST "{{API_BASE_URL}}/tasks/1/control" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"action": "pause"}'
```

`control` 支持 `pause` / `resume` / `stop` / `skip` / `retry`；`skip`/`retry` 时传 `case_id` 指定目标用例。

### 查询执行进度

```bash
curl -X GET "{{API_BASE_URL}}/tasks/1/progress" -H "Authorization: Bearer {token}"
```

响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 100,
    "completed": 50,
    "failed": 5,
    "progress": 50,
    "current_case": "case_001",
    "status": "running"
  }
}
```

## 用例、音频、设备与报告接口

| 类别 | 端点 | 说明 |
| --- | --- | --- |
| 用例 | `GET /api/v1/testcases` | 用例列表（分页/搜索/分组/标签筛选） |
| 用例 | `POST /api/v1/testcases` | 创建用例 |
| 音频 | `GET /api/v1/audios` | 音频列表 |
| 音频 | `POST /api/v1/audios/upload` | 上传测试音频 |
| 测试设备 | `GET /api/v1/test-devices` | 测试设备列表 |
| 测试设备 | `POST /api/v1/test-devices/scan` | 扫描可用设备 |
| 播放设备 | `GET /api/v1/playback-devices` | 播放设备列表 |
| 评估维度 | `GET /api/v1/evaluation` | 评估维度列表 |
| SPL 映射 | `GET /api/v1/spl` | SPL 映射配置列表 |
| 报告 | `GET /api/v1/reports` | 报告列表 |
| 报告 | `POST /api/v1/reports/compare` | 报告对比 |

代表性创建用例示例：

```bash
curl -X POST "{{API_BASE_URL}}/testcases" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "唤醒词检测", "audio_id": 1, "evaluation_dimension_ids": [1, 2], "reference_params": {"唤醒词": "小智小智"}}'
```

## 实时推送

- **SSE 事件流**：`GET /api/v1/sse/events`（需 `sse:read` 权限），订阅 EventBus 通道实时推送日志/进度/报告事件。
- **WebSocket 日志**：`/ws/logs`（socket.io），实时推送日志；亦支持轮询 `POST /api/v1/logs/refresh` 兜底。

## 错误处理与重试

- **429/5xx**：使用指数退避重试（如 1s、2s、4s…，最多 5 次），避免打满服务端。
- **幂等与重复提交**：创建类请求重复提交可能生成重复资源；以响应 `code` 判断是否成功，提交前确认任务/资源状态。
- **流式断开**：SSE/WebSocket 连接断开后应自动重连，并注意消息去重。
- **业务错误码**：201 确认目标存在；202 重复创建时确认对象是否已存在；204 确认状态允许该操作；303 检查网络连通性后重试。

## 常见问题

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 401 | 令牌缺失或过期 | 重新登录或刷新令牌 |
| 403 | 权限不足 | 确认角色权限（`docs/RBAC权限划分.md`） |
| 201 | 目标不存在 | 检查用例/设备/任务 ID |
| 204 | 状态冲突 | 确认任务当前状态允许该操作 |
| 302 | 文件读写错误 | 检查文件路径、磁盘空间与访问权限 |
| 303 | 网络错误 | 检查网络连通性后重试 |

## Windows 与调用环境

Windows 下 curl 使用 `curl.exe`（避免 PowerShell 别名指向 `Invoke-WebRequest`）：

```powershell
$env:API_BASE_URL = "{{API_BASE_URL}}"
$env:TOKEN = "你的访问令牌"
curl.exe -X GET "$env:API_BASE_URL/tasks" -H "Authorization: Bearer $env:TOKEN"
```

或直接使用 Invoke-RestMethod：

```powershell
$token = "你的访问令牌"
Invoke-RestMethod -Uri "{{API_BASE_URL}}/tasks" -Headers @{ Authorization = "Bearer $token" }
```

## 联系支持

使用或接入中遇到问题请联系平台管理员，反馈时请附上接口、请求参数、状态码与错误信息，并隐藏令牌等敏感信息。

## 返回文档目录

返回[文档目录](#目录) ｜ 关于本平台见[关于](/about)
