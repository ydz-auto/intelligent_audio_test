# 后端任务进度实时推送配置文档

## 1. 概述
本文档详细介绍了后端任务进度实时推送的配置和实现，包括 SocketIO 服务配置、命名空间设置、进度推送逻辑以及前端集成方法。

## 2. 技术栈
- **后端框架**: Flask 2.x
- **SocketIO 库**: Flask-SocketIO 5.5.1
- **WebSocket 客户端**: socket.io-client 2.5.0 (前端)
- **异步模式**: threading (与 Flask 开发服务器兼容)

## 3. 配置步骤

### 3.1 SocketIO 服务初始化
在 `backend/app.py` 中配置 SocketIO 服务：

```python
from flask_socketio import SocketIO

# 初始化 SocketIO 实例
socketio = SocketIO(
    cors_allowed_origins="*",  # 允许跨域请求
    async_mode='threading',     # 使用线程模式，与 Flask 开发服务器兼容
    ping_timeout=10,            # 连接超时时间（秒）
    ping_interval=5,            # 心跳间隔（秒）
    logger=True,               # 启用 SocketIO 日志
    engineio_logger=True,       # 启用 EngineIO 日志
    path='/ws/tasks'           # Socket.io 路径
)
```

### 3.2 应用上下文配置
在 `backend/run.py` 中启动 SocketIO 服务器：

```python
from backend.app import app, socketio

socketio.run(app, host='0.0.0.0', port=5000, debug=True)
```

### 3.3 命名空间设置
后端使用 `/ws/tasks` 命名空间专门用于任务进度推送：

```python
# 在 app.py 中可以配置命名空间事件处理
# socketio.on_event('connect', lambda: print('Task client connected'), namespace='/ws/tasks')
# socketio.on_event('disconnect', lambda: print('Task client disconnected'), namespace='/ws/tasks')
```

## 4. 代码实现

### 4.1 进度推送核心方法

在 `backend/utils/execution_engine.py` 中实现了进度推送逻辑，并引入了节流（Throttle）和强制推送机制：

```python
from backend.app import socketio

class ExecutionEngine:
    # ... 其他方法 ...
    
    def _emit_progress(self, task, force=False):
        """
        推送任务进度到前端（带节流保护）
        :param task: Task 对象
        :param force: 是否强制推送，忽略节流限制
        """
```

#### 4.1.1 性能优化策略 (New)

为了平衡实时性与系统负载，推送机制采用了以下优化：

1. **高频节流 (Throttling)**：
   - 默认推送间隔为 **0.1s**（原为 0.5s），兼顾流畅度与后端压力。
   - 连续的高频更新会被合并，减少无效的网络开销。

2. **强制推送 (Force Push)**：
   - 当任务状态发生关键切换（如 `pending` -> `running`, `running` -> `completed`, `stop`, `pause`）时，调用 `_emit_progress(task, force=True)`。
   - 强制推送会绕过节流计时器，确保前端第一时间获取到最新的任务状态，避免状态更新“跳变”或丢失。

3. **并发统计准确性**：
   - 进度数据现在包含更细致的用例计数：`running`、`queued`、`evaluation` 等。
   - 前端进度条基于 `completed_cases / total_cases` 计算，而子状态统计则由后端实时汇总并推送。
        try:
            # 获取当前运行的测试用例
            current_tc = TaskCase.query.filter_by(task_id=task.id, status='running').first()
            current_case_data = None
            if current_tc:
                case_info = TestCase.query.get(current_tc.test_case_id)
                current_case_data = {
                    "caseId": str(current_tc.test_case_id),
                    "name": case_info.name if case_info else "未知用例",
                    "step": "playing" if task.type == 'e2e' else "evaluating",
                    "startTime": int(current_tc.started_at.timestamp() * 1000) if current_tc.started_at else int(time.time() * 1000)
                }

            # 获取最近日志
            from backend.models.models import Log
            recent_logs = Log.query.filter_by(task_id=task.id).order_by(Log.time.desc()).limit(5).all()
            logs_data = [{
                "level": l.level.lower() if l.level else 'info',
                "message": l.content,
                "timestamp": int(l.time.timestamp() * 1000) if l.time else int(time.time() * 1000)
            } for l in reversed(recent_logs)]

            # 构建进度数据
            progress_data = {
                "taskId": str(task.id),
                "totalProgress": round(task.completed_cases / task.total_cases * 100, 2) if task.total_cases > 0 else 0,
                "status": task.status,
                "completedCount": task.completed_cases,
                "totalCount": task.total_cases,
                "currentCase": current_case_data,
                "logs": logs_data
            }
            
            # 发送进度更新到 /ws/tasks 命名空间
            socketio.emit('task_progress', progress_data, namespace='/ws/tasks')
            
        except Exception as e:
            print(f"推送进度失败: {str(e)}")
```

### 4.2 进度推送触发时机

#### 4.2.1 任务启动时
```python
def start_task(self, app, task_id):
    # ... 任务启动逻辑 ...
    # 发送初始进度
    self._emit_progress(task)
    # ...
```

#### 4.2.2 任务状态变化时
```python
def control_task(self, app, task_id, action):
    # ... 任务控制逻辑 ...
    # 发送状态变化后的进度
    self._emit_progress(task)
    # ...
```

#### 4.2.3 任务执行过程中
```python
def _run_task(self, app, task_id, stop_event, pause_event):
    # ... 任务执行逻辑 ...
    # 定期发送进度更新
    self._emit_progress(task)
    # ...
```

## 5. 工作流程

1. **任务启动**: 当任务启动时，后端创建执行线程，并发送初始进度
2. **进度计算**: 执行引擎实时计算任务进度（已完成用例数/总用例数）
3. **数据构建**: 构建包含任务ID、进度百分比、状态、当前用例等信息的进度数据
4. **WebSocket推送**: 通过 SocketIO 发送 `task_progress` 事件到 `/ws/tasks` 命名空间
5. **前端接收**: 前端监听该事件并更新测试执行页面
6. **实时更新**: 任务执行过程中定期推送进度更新

## 6. 调试和监控

### 6.1 日志配置
已启用详细的日志记录，包括：
- SocketIO 连接和断开日志
- WebSocket 消息发送和接收日志
- 进度推送日志
- 错误处理日志

### 6.2 日志查看
可以通过以下方式查看日志：
1. **终端输出**: 后端服务终端会实时显示进度和 WebSocket 日志
2. **日志文件**: 如果配置了日志文件，可以通过查看日志文件监控

### 6.3 日志格式
```
[实时进度] 任务ID: {task.id}, 进度: {progress_data['totalProgress']}%, 状态: {progress_data['status']}
[实时进度] 已完成: {progress_data['completedCount']}/{progress_data['totalCount']} 个用例
[实时进度] 当前执行: {current_case_data['name']}, 步骤: {current_case_data['step']}
[WebSocket] 发送 task_progress 事件到命名空间 /ws/tasks
[WebSocket] 消息发送成功
```

## 7. 前端集成

### 7.1 连接配置
前端需要使用 socket.io-client 2.5.0 连接到后端：

```javascript
import io from 'socket.io-client'

// 创建 Socket 连接
const socket = io.connect('http://localhost:5000/ws/tasks', {
  path: '/ws/tasks',
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
  upgrade: false,
  timeout: 20000
})
```

### 7.2 事件监听
```javascript
// 监听任务进度事件
socket.on('task_progress', (progressData) => {
  console.log('Received task progress:', progressData)
  // 更新测试执行页面
  updateProgress(progressData)
})
```

### 7.3 连接管理
```javascript
// 监听连接事件
socket.on('connect', () => {
  console.log('Socket connected to tasks namespace')
})

// 监听断开连接事件
socket.on('disconnect', () => {
  console.log('Socket disconnected from tasks namespace')
})
```

## 8. 常见问题和解决方案

### 8.1 连接失败
- 检查后端服务是否运行
- 确认端口号是否正确（默认5000）
- 检查跨域配置是否正确
- 查看浏览器控制台和后端日志

### 8.2 进度不更新
- 检查任务是否正在运行
- 确认 `_emit_progress` 方法是否被调用
- 查看后端日志中的进度推送记录
- 检查前端事件监听器是否正确配置

### 8.3 性能问题
- 调整心跳间隔和超时时间
- 优化进度计算逻辑
- 减少推送频率
- 考虑使用更高效的异步模式

## 9. 安全考虑

1. **跨域配置**: 生产环境中应限制允许的源，避免使用 `*`
2. **认证和授权**: 考虑添加身份验证和授权机制
3. **数据加密**: 建议在生产环境中使用 HTTPS/WSS
4. **速率限制**: 添加速率限制，防止滥用

## 10. 生产环境部署

### 10.1 配置调整
```python
socketio = SocketIO(
    cors_allowed_origins=["https://yourdomain.com"],  # 限制允许的源
    async_mode='gevent',  # 生产环境建议使用 gevent 或 eventlet
    logger=False,  # 生产环境关闭日志
    engineio_logger=False,
    path='/ws/tasks'
)
```

### 10.2 部署方式
- 使用 Gunicorn + Gevent 部署
- 配置 Nginx 作为反向代理
- 启用 HTTPS/WSS
- 配置负载均衡（如果需要）

## 11. 总结

后端任务进度实时推送通过 SocketIO 实现，使用 `/ws/tasks` 命名空间专门用于任务进度推送。执行引擎在任务启动、状态变化和执行过程中定期推送进度数据，前端通过监听 `task_progress` 事件接收并更新测试执行页面。

该实现具有以下特点：
- 实时性高：任务进度实时推送
- 可靠性强：支持自动重连和心跳机制
- 可扩展性好：支持命名空间和多任务
- 易于集成：前端通过简单的 API 即可接收进度
- 便于调试：详细的日志记录

通过本配置，可以实现测试任务进度的实时监控，提高测试过程的可视化程度和用户体验。
