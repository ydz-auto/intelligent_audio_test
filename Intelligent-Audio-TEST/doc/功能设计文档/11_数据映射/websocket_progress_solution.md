# 后端任务进度实时推送配置文档

> 本文描述任务进度实时推送（WebSocket/SocketIO）的配置与实现。状态枚举以 [02_任务管理/status_fields_relationship.md](../02_任务管理/status_fields_relationship.md) 为权威；实时链路与执行引擎的关系参见 [01_测试执行/07_流式推送与结果获取.md](../01_测试执行/07_流式推送与结果获取.md)。

## 1. 概述
本文档详细介绍了后端任务进度实时推送的配置和实现，包括 SocketIO 服务配置、命名空间设置、消息类型与报文结构、进度推送逻辑（节流与强制推送）以及前端集成方法。

**核心要点**：任务进度推送使用 SocketIO **默认命名空间（`/`）**，由 `EventManager.emit_progress` 统一构建 `task_progress` 报文并广播；`/ws/logs` 命名空间仅用于全局日志流，不承担进度推送。

## 2. 技术栈
- **后端框架**: Flask >= 3.0.0
- **SocketIO 库**: Flask-SocketIO >= 5.3.0（当前环境安装版本为 5.6.1），底层 python-socketio >= 5.8.0
- **WebSocket 客户端**: socket.io-client ^4.7.5（前端，Vue 3 + TypeScript）
- **异步模式**: threading（与 Flask 开发服务器兼容）

## 3. 配置步骤

### 3.1 SocketIO 服务初始化
在 `backend/app.py` 中配置 SocketIO 服务（实际代码）：

```python
from flask_socketio import SocketIO

# 初始化 SocketIO 实例
socketio = SocketIO(
    cors_allowed_origins=_allowed_origins,   # 由环境变量配置；开发环境默认 "*"，生产环境为白名单
    allow_credentials=True if _allowed_origins != '*' else False,
    async_mode='threading',     # 使用线程模式，与 Flask 开发服务器兼容
    ping_timeout=10,            # 连接超时时间（秒）
    ping_interval=5,            # 心跳间隔（秒）
    logger=False,               # SocketIO 日志（生产保持关闭）
    engineio_logger=False,      # EngineIO 日志（生产保持关闭）
)
```

说明：
- **未自定义 `path` 参数**，Engine.IO 使用默认路径 `/socket.io/`；
- 跨域来源通过环境变量配置化（拒绝硬编码），生产环境必须配置白名单；
- 允许的来源为 `*` 时自动关闭 `allow_credentials`，避免不安全组合。

### 3.2 应用启动配置
在 `run.py` 中启动 SocketIO 服务器（实际代码）：

```python
from backend.app import create_app, socketio

app = create_app(config_name)

socketio.run(
    app,
    host='0.0.0.0',
    port=int(os.environ.get('FLASK_PORT', '5000')),  # 端口由环境变量配置，默认 5000
    debug=app.config.get('DEBUG', False),
    allow_unsafe_werkzeug=True,
    use_reloader=False
)
```

启动脚本同时注册了 `SIGINT/SIGTERM`（Windows 下含 `SIGBREAK`）信号处理：停止所有运行中任务与线程池 → 清空任务队列 → `socketio.stop()` → 关闭 Flask 服务，保证优雅停机。

### 3.3 命名空间设置
| 命名空间 | 用途 |
|----------|------|
| `/`（默认） | **任务进度推送**（`task_progress`）、任务告警（`error_alert`）、任务级日志（`task_log`） |
| `/ws/logs` | 全局日志流（`logs` 事件，`LOG_BATCH` 批量推送），并通过 `set_filter` 事件接收日志过滤设置 |

> 历史版本曾使用 `/ws/tasks` 专用命名空间推送进度，现已废弃：当前进度推送全部走默认命名空间，前端仅日志视图连接 `/ws/logs`。

## 4. 消息类型与报文结构

### 4.1 消息类型一览
| 事件 | 命名空间 | 方向 | 说明 |
|------|----------|------|------|
| `task_progress` | `/` | 服务端 → 前端 | 任务进度全量快照（含用例、日志、API 资源状态） |
| `error_alert` | `/` | 服务端 → 前端 | 任务执行异常告警 |
| `task_log` | `/` | 服务端 → 前端 | 任务级单条实时日志 |
| `logs` | `/ws/logs` | 服务端 → 前端 | 全局日志批量推送（`{type: 'LOG_BATCH', data: [...]}`） |
| `set_filter` | `/ws/logs` | 前端 → 服务端 | 设置日志过滤条件（`{levels: [...], modules: [...]}`） |

### 4.2 task_progress 报文（核心）
由 `backend/utils/common/event_manager.py` 的 `EventManager.emit_progress` 构建，字段为 **camelCase**（前端 Application/Domain 层只消费 camelCase Domain）：

```jsonc
{
  "taskId": "123",                       // 任务 ID（字符串化）
  "totalProgress": 42.5,                 // 进度百分比，口径见 4.3
  "status": "running",                   // Task.status 枚举值
  "completedCount": 17,                  // 已处理用例数（含 失败/跳过，与执行引擎口径一致）
  "inProgressCount": 2,                  // 执行中/排队中/评估中 用例数
  "executionFailedCount": 1,             // 执行失败用例数
  "evaluationFailedCount": 0,            // 评估失败用例数
  "totalCount": 40,                      // 总用例数（以 TaskCase 实际关联数校准）
  "currentCase": {                       // 当前执行用例（无则为 null）
    "caseId": "456",
    "name": "用例名称",
    "step": "playing",                   // e2e 任务为 "playing"，api 任务为 "evaluating"
    "startTime": 1725000000000           // 毫秒时间戳
  },
  "testCases": [                         // 全量用例进度快照
    {
      "id": "456",                       // 用例 ID（字符串化）
      "status": "completed",             // TaskCase.status：pending/completed/failed/skipped/running
      "executionStatus": "completed",    // execution_status 枚举
      "evaluationStatus": "completed",   // evaluation_status 枚举
      "duration": 12,                    // 用例耗时（秒，int）
      "errorMessage": null,              // 失败原因
      "roundProgress": { "current": 1, "total": 3 }  // 多轮进度（仅多轮任务，取自执行引擎内存缓存）
    }
  ],
  "logs": [                              // 最近 20 条任务日志（按时间正序）
    { "id": 789, "level": "info", "message": "日志内容", "timestamp": 1725000000000 }
  ],
  "apiResources": [                      // API 任务专属：API 资源负载状态
    {
      "id": "1",
      "name": "API 名称",
      "currentConcurrent": 2,            // 当前并发
      "queueLength": 5,                  // 待执行用例数（队列长度）
      "avgResponseTime": 320,            // 平均响应时间（ms）
      "maxConcurrent": 5                 // 最大并发（API 配置）
    }
  ],
  "expectedCompleteTime": "2025-01-01 12:30:00",  // 预计完成时间（未开始时为 null/''）
  "expectedTotalTime": "5分钟30秒",      // 预计总时长（_format_duration 格式化）
  "usedTime": "2分钟10秒"                // 已用时长（任务结束后以完成时间封顶，不再增长）
}
```

报文中状态枚举（枚举化定义，禁止魔法字符串散落使用，权威定义见 `status_fields_relationship.md`）：
- `status`（Task.status）：`pending / queued / running / evaluating / reevaluate_queued / reevaluating / completed / failed / stopped / paused / skipped`
- `executionStatus`（TaskCase.execution_status）：`pending / queued / running / completed / stopped / failed`
- `evaluationStatus`（TaskCase.evaluation_status）：`queued / pending / running / calculating / completed / stopped / failed`
- `testCases[].status`（TaskCase.status）：`pending / completed / failed / skipped / running`

### 4.3 进度百分比口径
- `totalProgress = processed_cases / actual_total_cases × 100`（保留 2 位小数）；
- `processed_cases` 统计 `TaskCase.status ∈ {completed, failed, skipped}` 的用例（含失败/跳过，与 `execution_engine` 状态口径一致）；
- `actual_total_cases` 以 `TaskCase` 实际关联数为准，若与 `Task.total_cases` 不一致会回写校准；
- 任务进入 `completed` / `failed` 终态时**强制 100%**，避免边界状态未更新导致进度卡住；
- 当前执行用例按 `TaskCase.execution_status = 'running'` 查询（注意不是 `TaskCase.status`）。

### 4.4 error_alert 报文
```json
{
  "task_id": "123",
  "message": "任务执行异常: ...",
  "level": "error",
  "time": "2025-01-01T12:30:00+08:00"
}
```
> 注意：`error_alert` 为历史遗留报文，字段为 **snake_case**（`task_id`），与其余消息的 camelCase 不一致；前端如需消费应自行做字段映射，后续演进应统一为 camelCase（`taskId`）。

### 4.5 task_log 报文
由 `backend/utils/web/log_handler.py` 的日志链路发出（默认命名空间）：
```json
{
  "taskId": "123",
  "log": {
    "id": 789,
    "time": "2025-01-01 12:30:00",
    "level": "INFO",
    "module": "EventManager",
    "content": "日志内容",
    "mark": ""
  }
}
```

## 5. 代码实现

### 5.1 进度推送核心方法
推送逻辑位于 `backend/utils/common/event_manager.py`（**不再是** `backend/utils/execution_engine.py`）：

```python
class EventManager:
    def emit_progress(self, task, force=False):
        """
        推送任务进度到前端（带节流保护）
        :param task: Task 对象 / 任务 ID
        :param force: 是否强制推送，绕过节流限制
        """

    def emit_alert(self, task_id, message, level='error'):
        """发送 error_alert 告警"""
```

`ExecutionEngine`（`backend/services/execution/execution_engine.py`）提供同名薄封装 `ExecutionEngine._emit_progress(task, force=False)`，内部委托 `event_manager.emit_progress`，执行流程内统一调用该封装。

### 5.2 性能优化策略

1. **两级节流（Throttling）**：
   - 第一级（入口节流）：`_progress_throttle_interval = 0.05s`，非 `force` 调用在 0.05 秒内的重复请求直接丢弃；
   - 第二级（推送节流）：最小推送间隔 `min_interval = min(WEBSOCKET_MIN_UPDATE_INTERVAL, 0.1)`，其中 `WEBSOCKET_MIN_UPDATE_INTERVAL` 为配置项（默认 0.1s，配置化、拒绝硬编码）；
   - 0.1 秒内命中进度缓存时直接重发缓存报文，减少数据库查询。

2. **强制推送（Force Push）**：
   - 任务启动、用例完成、状态关键切换（`running`/`completed`/`failed` 首次达成）等场景调用 `emit_progress(task, force=True)`；
   - 强制推送绕过节流计时器，确保前端第一时间获取最新状态，避免状态"跳变"或丢失。

3. **智能触发条件**（非 force 且未达最小间隔时，满足任一条件仍会推送）：
   - 任务状态首次切换到 `running` / `completed` / `failed`；
   - `completed_cases` 完成数变化；
   - 当前执行用例发生变化。

4. **时间预估防闪烁**：预计总时长变化小于 **10%** 时沿用上一次缓存值，避免前端 UI 数值抖动。

5. **并发统计准确性**：
   - 进度数据包含细粒度用例计数：`completedCount`、`inProgressCount`、`executionFailedCount`、`evaluationFailedCount`；
   - 前端进度条优先基于 `testCases` 快照按状态重算，后端计数作为兜底。

## 6. 工作流程

1. **任务启动**: `ExecutionEngine` 创建执行流程，`force=True` 推送初始进度；
2. **执行过程**: 用例执行/评估/状态变化等关键节点调用 `_emit_progress`，经两级节流决定是否实际推送；
3. **数据构建**: `EventManager.emit_progress` 从数据库构建进度快照（当前用例、用例列表、日志、API 资源、时间预估），复用进度缓存；
4. **WebSocket 推送**: `socketio.emit('task_progress', progress_data)` 广播到**默认命名空间**；
5. **前端接收**: `SocketService`（默认命名空间）收到事件 → `useTaskProgress` 按 `taskId` 过滤 → 状态映射 → 响应式更新视图；
6. **实时更新**: 任务执行过程中周期推送，直到任务进入终态（终态强制 100%）。

## 7. 前端集成

### 7.1 连接配置
前端通过 `frontend/src/utils/socket.ts` 的 `SocketService` 单例连接（socket.io-client ^4.7.5），基础设施层统一管理连接：

```typescript
// utils/config.ts
export const API_CONFIG = {
  baseUrl: 'http://127.0.0.1:5000/api/v1',
  wsBaseUrl: 'http://127.0.0.1:5000'   // SocketIO 连接地址（默认命名空间）
} as const;

// utils/socket.ts（节选）
import { io, Socket } from 'socket.io-client';

this.sockets['/'] = io(API_CONFIG.wsBaseUrl, {
  transports: ['polling', 'websocket'],   // 先轮询升级为 WebSocket
  reconnection: true,
  reconnectionAttempts: Infinity,          // 无限重连
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  timeout: 20000,
  autoConnect: true
});
```

`SocketService` 支持多命名空间管理（`getNamespaceSocket`）、事件订阅/退订（`on/off`，返回退订函数）与统一日志。**进度订阅不传命名空间参数（即默认命名空间）**；仅日志视图显式连接 `/ws/logs`。

### 7.2 事件监听（Application 层编排）
进度订阅封装在组合式函数 `frontend/src/composables/useTaskProgress.ts`（Application 层，编排用例、缓存 ReadModel），视图层（views/ + components/）只消费其暴露的 camelCase Domain 状态：

```typescript
import socketService from '../utils/socket'

onMounted(() => {
  socketService.on('task_progress', handleTaskProgress)  // 任务进度
  socketService.on('task_log', taskLogHandler)           // 任务级实时日志
})

onUnmounted(() => {
  socketService.off('task_progress', handleTaskProgress)
  socketService.off('task_log', taskLogHandler)
})
```

处理逻辑要点：
- **taskId 过滤**：仅处理与当前任务匹配的进度消息，避免多任务串扰；
- **终态回调**：`status === 'completed'` / `'failed'` 时各触发一次 `onCompleted` / `onFailed`；
- **状态映射**：后端状态经 `frontend/src/utils/statusUtils.ts` 的 `transformTestCaseStatus` 转换为前端展示状态：
  - `executionStatus`: `running → in_progress`（其余原样）；
  - `evaluationStatus`: `running → calculating`（其余原样）；
  - 复合展示状态优先级：执行失败 > 执行中 > 排队中 > 执行完成时按评估状态组合（`completed + pending → evaluating`、`completed + calculating → calculating`、`completed + completed → 取结果状态`）；
- **计数重算**：存在 `testCases` 快照时，前端按映射后状态重算完成/进行中/失败/待执行计数与总进度（`completed / totalCount`）；无快照时才使用报文计数字段兜底；
- **多轮进度**：消费 `roundProgress {current, total}` 更新用例轮次显示。

### 7.3 连接管理
`SocketService` 已内置 `connect / disconnect / connect_error / reconnect_attempt / reconnect` 等连接生命周期事件处理与日志输出，业务组件无需重复处理。

## 8. 常见问题和解决方案

### 8.1 连接失败
- 检查后端服务是否运行、端口是否正确（环境变量 `FLASK_PORT`，默认 5000）；
- 确认前端连接的是 `API_CONFIG.wsBaseUrl` 且**未附加** `/ws/tasks` 之类的命名空间（进度走默认命名空间）；
- 检查跨域配置（环境变量配置的允许来源）；
- 查看浏览器控制台（`SocketService` 日志）与后端日志。

### 8.2 进度不更新
- 检查任务是否处于运行态；
- 确认 `EventManager.emit_progress` 是否被调用（后端 DEBUG 日志中有关键字 `task_progress`）；
- 注意两级节流窗口（0.05s / 0.1s）内的更新会被合并，属预期行为；
- 检查前端 `taskId` 过滤逻辑与事件监听是否正确配置。

### 8.3 性能问题
- 调整配置项 `WEBSOCKET_MIN_UPDATE_INTERVAL` 平滑推送频率；
- 心跳参数（`ping_timeout=10 / ping_interval=5`）一般无需调整；
- 大量用例场景下 `testCases` 为全量快照，若出现带宽压力应考虑增量推送演进（当前实现为快照全量）。

## 9. 安全考虑

1. **跨域配置**: 允许来源由环境变量配置化注入；生产环境必须配置白名单，避免使用 `*`；
2. **认证和授权**: `/ws/logs` 命名空间预留了连接时 JWT 校验扩展点，进度命名空间暂未启用鉴权；
3. **数据加密**: 生产环境应通过 Nginx 启用 HTTPS/WSS；
4. **速率限制**: 服务端已内置两级节流；如面向公网，建议在反向代理层再加连接频率限制。

## 10. 生产环境部署

### 10.1 配置调整
跨域来源、端口、数据库等均通过环境变量配置（`FLASK_PORT`、`DATABASE_URI`/`DB_*` 等），生产部署无需修改代码。当前实现 `async_mode='threading'`，配合 `allow_unsafe_werkzeug=True` 仅适用于开发/内网环境；生产环境建议：

- 使用 Gunicorn + Gevent/Eventlet worker 部署（需同步将 `async_mode` 调整为对应模式）；
- 配置 Nginx 作为反向代理，并开启 WebSocket 升级（`Upgrade`/`Connection` 头，代理默认 `/socket.io/` 路径）；
- 启用 HTTPS/WSS；
- 配置负载均衡时启用粘性会话（SocketIO 长连接要求）。

## 11. 相关测试与验证

- 后端单测：`backend/tests/test_task_progress_time_fields.py` 覆盖 `usedTime` / `expectedTotalTime` / `expectedCompleteTime` 字段的推送行为（捕获 `task_progress` 事件断言）；
- 手动验证：启动任务后在浏览器控制台观察 `SocketService` 日志中的 `task_progress` 报文，核对 4.2 节字段。

## 12. 总结

后端任务进度实时推送通过 Flask-SocketIO 实现，使用**默认命名空间**广播 `task_progress` / `error_alert` / `task_log` 事件；`/ws/logs` 命名空间独立承载全局日志流。`EventManager.emit_progress` 统一构建进度快照报文，配合两级节流、强制推送与时间预估防闪烁策略，在实时性与系统负载间取得平衡。前端通过 `SocketService`（Infrastructure 层）连接默认命名空间，`useTaskProgress`（Application 层）完成 taskId 过滤、状态映射与计数重算，视图层仅消费 camelCase Domain 数据。

该实现具有以下特点：
- 实时性高：进度实时推送，关键状态强制推送；
- 可靠性强：自动重连、心跳机制、终态强制 100% 防进度卡住；
- 可扩展性好：消息类型与状态枚举化，多任务并行互不串扰；
- 易于集成：前端 Application 层封装，视图层零 SocketIO 依赖；
- 便于调试：推送链路 DEBUG 日志 + 单测覆盖时间字段。
