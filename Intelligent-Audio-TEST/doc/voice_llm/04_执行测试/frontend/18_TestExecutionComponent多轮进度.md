# 18 — TestExecutionComponent 多轮进度

> **所属步骤**：04_执行测试 → frontend  
> **改造类型**：修改  
> **涉及文件**：`frontend/src/components/TestExecutionComponent.vue`

---

## 背景

`TestExecutionComponent` 展示测试执行的实时进度，包括进度条、用例状态列表、日志等。voice_llm 多轮对话需要在用例状态中显示"第 N/M 轮"的进度信息。

---

## 改造内容

### 1. 用例列表项增加轮次进度

在用例状态列表中，当用例包含 `roundProgress` 时，显示轮次信息：

```vue
<!-- 现有用例列表项 -->
<div class="case-item" v-for="case in visibleCases" :key="case.id">
  <div class="case-info">
    <span class="case-name">{{ case.name }}</span>
    <span class="case-status" :class="case.executionStatus">
      {{ statusLabel(case) }}
    </span>
  </div>

  <!-- 新增：轮次进度 -->
  <div v-if="case.roundProgress" class="round-progress">
    <span class="round-text">
      第 {{ case.roundProgress.current }}/{{ case.roundProgress.total }} 轮
    </span>
    <div class="round-bar">
      <div
        class="round-bar-fill"
        :style="{
          width: (case.roundProgress.current / case.roundProgress.total * 100) + '%'
        }"
      ></div>
    </div>
  </div>
</div>
```

### 2. 样式定义

```css
.round-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.round-text {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.round-bar {
  flex: 1;
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
  overflow: hidden;
}

.round-bar-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 2px;
  transition: width 0.3s ease;
}
```

### 3. 状态标签适配

```typescript
function statusLabel(caseItem: AssociatedCase): string {
  const status = caseItem.executionStatus;

  // voice_llm 多轮：运行中 + 有轮次进度
  if (status === 'running' && caseItem.roundProgress) {
    const { current, total } = caseItem.roundProgress;
    return `执行中 (${current}/${total})`;
  }

  // 现有状态映射
  const labels: Record<string, string> = {
    completed: '已完成',
    running: '执行中',
    pending: '等待中',
    failed: '执行失败',
    eval_failed: '评估失败',
  };
  return labels[status] || status;
}
```

### 4. AssociatedCase 接口扩展

```typescript
// useTaskProgress.ts 中的接口
interface AssociatedCase {
  id: number;
  status: string;
  executionStatus: string;
  evaluationStatus: string;
  duration: number | null;
  errorMessage?: string;
  // 新增
  roundProgress?: {
    current: number;
    total: number;
  };
}
```

### 5. 视觉效果

```
┌────────────────────────────────────────────┐
│ 多轮对话_场景A              执行中 (5/10) │
│ ██████████░░░░░░░░░░░░░░░░░░             │
│ 第 5/10 轮  ████████████████░░░░░░░░     │
├────────────────────────────────────────────┤
│ 单轮翻译_场景B              已完成        │
├────────────────────────────────────────────┤
│ 多轮对话_场景C              等待中        │
└────────────────────────────────────────────┘
```

---

## 不变部分

- 进度条整体逻辑不变
- 暂停/恢复/停止按钮不变
- 日志显示不变
- 非 voice_llm 用例的显示不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `31_event_manager多轮进度推送` | WebSocket 推送 roundProgress |
| `19_useTaskProgress多轮显示` | 数据接收和处理 |
