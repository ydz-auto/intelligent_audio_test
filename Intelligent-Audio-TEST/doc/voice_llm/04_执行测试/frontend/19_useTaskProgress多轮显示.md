# 19 — useTaskProgress 多轮显示

> **所属步骤**：04_执行测试 → frontend  
> **改造类型**：修改  
> **涉及文件**：`frontend/src/composables/useTaskProgress.ts`

---

## 背景

`useTaskProgress` 通过 Socket.IO 监听 `task_progress` 事件，更新执行进度状态。voice_llm 多轮对话的进度数据中包含 `roundProgress` 字段，需要在处理进度事件时将其映射到 `AssociatedCase` 接口。

---

## 改造内容

### 1. AssociatedCase 接口扩展

```typescript
interface AssociatedCase {
  id: number;
  name?: string;
  status: string;
  executionStatus: string;
  evaluationStatus: string;
  duration: number | null;
  errorMessage?: string;
  roundProgress?: {           // 新增
    current: number;
    total: number;
  };
}
```

### 2. handleTaskProgress 适配

在 `handleTaskProgress()` 中，处理 `testCases` 数组时提取 `roundProgress`：

```typescript
function handleTaskProgress(progressData: any) {
  // ... 现有 taskId 匹配和状态更新逻辑 ...

  if (progressData.testCases && Array.isArray(progressData.testCases)) {
    // 重新计算所有用例状态
    const cases: AssociatedCase[] = progressData.testCases.map((tc: any) => ({
      id: tc.id,
      name: tc.name,
      status: tc.status,
      executionStatus: tc.executionStatus || tc.status,
      evaluationStatus: tc.evaluationStatus || '',
      duration: tc.duration || null,
      errorMessage: tc.errorMessage,
      // 新增：轮次进度
      roundProgress: tc.roundProgress
        ? {
            current: tc.roundProgress.current,
            total: tc.roundProgress.total,
          }
        : undefined,
    }));

    associatedCases.value = cases;

    // 重新计算统计数据
    completedTests.value = cases.filter(c => c.executionStatus === 'completed').length;
    inProgressTests.value = cases.filter(c => c.executionStatus === 'running').length;
    pendingTests.value = cases.filter(c => c.executionStatus === 'pending').length;
    executionFailedTests.value = cases.filter(c => c.executionStatus === 'failed').length;
    // ...
  }
}
```

### 3. 日志中的轮次信息

```typescript
function addLog(log: LogEntry) {
  // 如果日志内容包含轮次标记，增加视觉区分
  const roundMatch = log.content?.match(/\[第 (\d+)\/(\d+) 轮\]/);
  if (roundMatch) {
    log.roundInfo = {
      current: parseInt(roundMatch[1]),
      total: parseInt(roundMatch[2]),
    };
  }

  // ... 现有去重和格式化逻辑 ...
}
```

### 4. LogEntry 接口扩展

```typescript
interface LogEntry {
  id: string;
  timestamp: string;
  level: string;
  content: string;
  roundInfo?: {          // 新增
    current: number;
    total: number;
  };
}
```

### 5. WebSocket 数据结构

```json
{
  "taskId": "task-001",
  "testCases": [
    {
      "id": 101,
      "name": "多轮对话_场景A",
      "status": "running",
      "executionStatus": "running",
      "roundProgress": {
        "current": 5,
        "total": 10
      }
    }
  ],
  "logs": [
    {
      "id": "log-001",
      "content": "[第 5/10 轮] 开始播放音频 round5.wav",
      "level": "info",
      "timestamp": "2026-06-05T16:30:00"
    }
  ]
}
```

---

## 不变部分

- Socket.IO 事件监听不变
- `resetProgress()` 不变
- `taskLogHandler` 不变
- 回调函数（`onCompleted`、`onFailed`）不变
- 时间预估显示不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `31_event_manager多轮进度推送` | 后端推送 roundProgress 数据 |
| `18_TestExecutionComponent多轮进度` | 前端组件展示 |
