# 报告标签显示ID问题修复与异步生成

## 问题概述

### 问题1: 标签对比卡片显示标签ID而非名称

**现象**: 用例标签对比卡片中的表格，部分标签显示的是数字ID，而不是标签名称。

**影响**: 用户无法直观识别标签含义，影响报告可读性。

### 问题2: 报告生成耗时较长

**现象**: 点击"查看报告"后，需要等待较长时间才能看到报告，用户体验不佳。

**影响**: 用户等待时间长，无法及时获取报告结果。

---

## 问题分析

### 问题1 根因分析

**定位过程**:

1. 检查前端 `CaseTagComparisonComponent.vue` 的 `getTags` 函数
2. 发现前端期望标签名称作为键
3. 检查后端 `report_utils.py` 的 `calculate_core_metrics` 函数
4. 发现后端使用 `tag.id` 作为 `tag_metric_data` 的键

**根本原因**:

后端在 `calculate_core_metrics` 函数中（`report_utils.py:207`）：
```python
tags = [tag.id for tag in tc_tags] or ["default_tag"]
```

使用标签ID作为 `tag_metric_data` 字典的键，而前端期望使用标签名称。

**数据流**:
```
后端: tag_metric_data = {tag_id: {resource: {metric: value}}}
前端期望: tagMetricData = {tag_name: {resource: {metric: value}}}
```

### 问题2 根因分析

**定位过程**:

1. 检查 `report_controller_task.py` 的 `generate_task_report` 函数
2. 发现报告生成是同步执行，阻塞HTTP请求

**根本原因**:

报告生成涉及大量数据查询和计算：
- 查询测试结果
- 计算维度得分
- 构建统计数据
- 写入数据库

整个过程在HTTP请求处理中同步执行，导致响应延迟。

---

## 解决方案

### 问题1 解决方案

**修改文件**: `backend/utils/report_utils.py`

**修改内容**:

```python
# 修改前
tags = [tag.id for tag in tc_tags] or ["default_tag"]

# 修改后
tags = [tag.name for tag in tc_tags if tag.name] or ["default_tag"]
```

同时更新 `_calculate_tag_category_averages` 函数，适配新的键格式：

```python
# 修改前
for tag_id in tag_accumulator.keys():
    tag = db.session.get(Tag, tag_id) if isinstance(tag_id, int) else None
    tag_name = tag.name if tag else str(tag_id)

# 修改后
for tag_name in tag_accumulator.keys():
    tag_data = tag_accumulator.get(tag_name, {})
```

### 问题2 解决方案

**修改文件**: `backend/controllers/report_controller_task.py`

**实现方案**:

1. 添加线程池用于异步执行：
```python
from concurrent.futures import ThreadPoolExecutor
import threading

_report_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='report_gen')
_generating_tasks = set()
_generating_lock = threading.Lock()
```

2. 修改 `generate_task_report` 为异步入口（含并发控制）：
```python
def generate_task_report():
    # 验证参数和任务状态
    ...
    
    # 并发控制：检查是否已在生成中
    with _generating_lock:
        if task_id in _generating_tasks:
            return success_response({"taskId": task_id, "status": "generating"}, "报告正在生成中")
        _generating_tasks.add(task_id)
    
    # 提交异步任务
    _report_executor.submit(
        ReportControllerTask._generate_task_report_async,
        task_id, name, description
    )
    
    # 立即返回
    return success_response({"taskId": task_id, "status": "generating"}, "报告生成中，请稍后刷新")
```

3. 新增 `_generate_task_report_async` 异步执行函数：
```python
@staticmethod
def _generate_task_report_async(task_id, name, description):
    # 关键：在函数内部导入 flask_app，而非模块加载时
    from backend.app import app as flask_app
    
    if flask_app is None:
        log_and_emit('ERROR', 'report', 'Flask app is None', task_id=task_id)
        with _generating_lock:
            _generating_tasks.discard(task_id)
        socketio.emit('report_generated', {
            'taskId': task_id,
            'success': False,
            'error': '服务器内部错误'
        })
        return
    
    with flask_app.app_context():
        try:
            # 执行报告生成逻辑
            ...
            
            # 完成后推送SocketIO事件
            socketio.emit('report_generated', {
                'taskId': task_id,
                'reportId': report_id,
                'success': True,
                'status': 'completed'
            })
        except Exception as e:
            socketio.emit('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '报告生成失败'
            })
        finally:
            # 并发控制：移除任务ID
            with _generating_lock:
                _generating_tasks.discard(task_id)
```

**前端适配**:

修改 `frontend/src/services/reportService.ts`：

```typescript
async function viewTaskReport(task: Task): Promise<Report> {
  let result = await reportsApi.generateTaskReport(task.id, name);
  
  // 如果返回 generating 状态，监听 SocketIO 事件
  if (result.status === 'generating') {
    // 确保 Socket 连接已建立
    socketService.connect();
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        socketService.off('report_generated', handleReportGenerated);
        reject(new Error('报告生成超时'));
      }, 120000);
      
      const handleReportGenerated = async (data: any) => {
        console.log('[reportService] Received report_generated event:', data);
        if (data.taskId === task.id) {
          clearTimeout(timeout);
          socketService.off('report_generated', handleReportGenerated);
          
          if (!data.success) {
            reject(new Error(data.error));
            return;
          }
          
          // 获取报告详情
          let report = await reportsApi.getOne(data.reportId);
          resolve(report);
        }
      };
      
      socketService.on('report_generated', handleReportGenerated);
    });
  }
  
  // 已存在报告，直接获取
  ...
}
```

添加用户提示（`frontend/src/views/TasksLogic/tasks.ts`）：

```typescript
const viewTaskReport = async (task: Task) => {
  notification.info('正在生成报告，请稍候...');
  try {
    const result = await reportService.viewTaskReport(task);
    if (result && result.id) {
      notification.success('报告生成成功');
      router.push({ name: 'reportView', params: { id: result.id } });
    }
  } catch (error) {
    notification.error('报告生成失败');
  }
};
```

---

## 技术细节

### 并发控制

**问题场景**:
- 用户快速点击两次"查看报告"按钮
- 多个用户同时请求生成同一任务的报告
- 网络延迟导致重复请求

**解决方案**:

使用 `set` + `threading.Lock` 实现并发控制：

```python
_generating_tasks = set()       # 正在生成的任务ID集合
_generating_lock = threading.Lock()  # 线程锁保护共享状态
```

**控制流程**:

1. **入口检查**: 请求到达时，检查任务ID是否已在 `_generating_tasks` 中
2. **添加标记**: 如果不在，添加到集合并提交异步任务
3. **移除标记**: 任务完成（成功或失败）后，在 `finally` 块中移除

**关键代码**:

```python
# 入口处
with _generating_lock:
    if task_id in _generating_tasks:
        return success_response({"taskId": task_id, "status": "generating"}, "报告正在生成中")
    _generating_tasks.add(task_id)

# 完成后
finally:
    with _generating_lock:
        _generating_tasks.discard(task_id)
```

**为什么使用 `discard` 而不是 `remove`**:
- `discard` 不会抛出异常，即使元素不存在也能正常执行
- 防止极端情况下（如任务ID被意外移除）导致程序崩溃

### 线程池配置

新增的报告生成线程池与现有线程池互不冲突：

| 线程池 | 前缀 | 用途 | workers |
|--------|------|------|---------|
| `_report_executor` | `report_gen` | 报告生成 | 3 |
| `device_control_pool` | `device_ctrl_` | 设备驱动操作 | 5 |
| `audio_playback_pool` | `audio_play_` | 音频播放 | 3 |

**不冲突原因**:
- 独立实例，各自管理线程队列
- 不同 `thread_name_prefix`，便于调试区分
- 不同用途，互不干扰

### Flask 上下文处理（关键）

**问题**: 在后台线程中执行数据库操作需要 Flask 应用上下文。

**错误做法**:
```python
# 模块加载时导入，此时 app 为 None
from backend.app import app as flask_app

def _generate_task_report_async():
    with flask_app.app_context():  # flask_app 是 None！
        ...
```

**正确做法**:
```python
def _generate_task_report_async():
    # 在函数内部导入，运行时获取已初始化的 app
    from backend.app import app as flask_app
    
    if flask_app is None:
        # 处理异常情况
        return
    
    with flask_app.app_context():
        ...
```

**原因**: 
- `backend/app.py` 中 `app = None` 是全局变量
- `create_app()` 函数调用后才赋值 `app = Flask(__name__)`
- 模块导入顺序导致导入时 `app` 尚未初始化

### Socket 连接初始化

**问题**: 前端监听事件前需要确保 Socket 连接已建立。

**解决方案**:
```typescript
if (result.status === 'generating') {
  socketService.connect();  // 确保连接已建立
  socketService.on('report_generated', handleReportGenerated);
}
```

### SocketIO 事件格式

**成功事件**:
```json
{
  "taskId": 123,
  "reportId": 456,
  "success": true,
  "status": "completed"
}
```

**失败事件**:
```json
{
  "taskId": 123,
  "success": false,
  "error": "错误信息"
}
```

---

## 测试验证

### 问题1 验证

1. 生成新报告
2. 查看用例标签对比卡片
3. 确认表格中标签显示名称而非ID

### 问题2 验证

1. 点击"查看报告"
2. 确认立即显示"正在生成报告，请稍候..."提示
3. 等待报告生成完成
4. 确认显示"报告生成成功"并跳转到报告页面

---

## 相关文件

### 后端
- `backend/utils/report_utils.py` - 标签数据处理逻辑
- `backend/controllers/report_controller_task.py` - 报告生成控制器

### 前端
- `frontend/src/services/reportService.ts` - 报告服务
- `frontend/src/views/TasksLogic/tasks.ts` - 任务页面逻辑
- `frontend/src/components/report/CaseTagComparisonComponent.vue` - 标签对比组件
- `frontend/src/utils/socket.ts` - SocketIO 服务

---

## 修复日期

2026-05-21