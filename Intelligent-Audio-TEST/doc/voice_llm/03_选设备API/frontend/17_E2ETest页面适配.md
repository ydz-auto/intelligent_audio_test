# 17_E2ETest 页面适配

> 文件：`frontend/src/views/E2ETest.vue` + `frontend/src/composables/useE2eView.ts`

## 现状分析

E2ETest.vue 是 E2E 测试的 5 步向导页面：

```
选算法 → 选用例 → 选被测设备 → 执行测试 → 查看结果
```

### 现有用例筛选逻辑

`useE2eTest.ts` 中的过滤逻辑：

```ts
function isE2eTestCase(caseItem: TestCase): boolean {
  // 简单判断：所有非删除的用例都视为 E2E 用例
  return !caseItem.deleted
}
```

当前没有按 `test_type` 过滤，而是将所有非删除用例视为 E2E 用例。

### 现有设备选择逻辑

```ts
// useE2eView.ts 中的设备筛选
const algorithmFilteredDevices = computed(() =>
  filteredDevices.value.filter(device =>
    !device.supportedAlgorithms ||
    device.supportedAlgorithms.includes(selectedAlgorithmType.value)
  )
)
```

### 关键状态

| 状态 | 类型 | 说明 |
|------|------|------|
| `selectedDeviceIdsList` | `string[]` | 已选设备 ID 列表 |
| `concurrentTasks` | `number` | 并发任务数（默认 4） |
| `selectedTestCaseIds` | `(string\|number)[]` | 已选用例 ID 列表 |

## 改造方案

### 1. 用例筛选改为使用 test_type 字段

```ts
// useE2eTest.ts 改造
function isE2eTestCase(caseItem: TestCase): boolean {
  // 优先使用用例级别的 test_type
  if (caseItem.test_type) {
    return caseItem.test_type === 'e2e' && !caseItem.deleted
  }
  // 降级到现有逻辑（向后兼容）
  return !caseItem.deleted
}
```

### 2. 设备选择适配

当选择 voice_llm 算法时，设备列表增加能力标签显示：

```vue
<!-- E2ETest.vue 设备选择步骤 -->
<template v-if="isVoiceLLM">
  <el-alert type="info" :closable="false">
    voice_llm 测试可能需要设备支持：音量控制、导轨控制。
    请确认设备能力后再选择。
  </el-alert>
</template>

<!-- ResourceSelectionGrid 设备卡片扩展 -->
<template #extra="{ item }">
  <div v-if="isVoiceLLM" class="device-capabilities">
    <el-tag v-if="item.supportsVolumeControl" size="small" type="success">
      音量控制
    </el-tag>
    <el-tag v-if="item.supportsRailControl" size="small" type="success">
      导轨控制
    </el-tag>
  </div>
</template>
```

### 3. 任务创建适配

```ts
// useE2eView.ts 任务创建
async function startTest() {
  // 验证设备选择
  if (selectedDeviceIdsList.value.length === 0) {
    alert('请至少选择一个设备')
    return
  }
  
  // 验证所有设备在线
  const offlineDevices = associatedDevices.value.filter(
    d => d.selected && d.status !== 'online'
  )
  if (offlineDevices.length > 0) {
    alert(`有 ${offlineDevices.length} 个设备离线`)
    return
  }

  const payload = {
    name: taskName.value,
    type: 'e2e',
    algorithmType: selectedAlgorithmType.value,
    deviceIds: selectedDeviceIdsList.value,
    caseIds: selectedTestCaseIds.value,
    config: {
      parallel: true,
      concurrentTasks: concurrentTasks.value
    }
  }
  // voice_llm 和其他算法使用相同的任务创建 API
  const task = await tasksApi.create(payload)
  await tasksApi.start(task.id)
}
```

### 4. 并发配置提示

voice_llm 的 E2E 测试由于多轮循环、声纹注册等操作，每轮耗时较长，建议降低并发数：

```ts
// useE2eView.ts
const recommendedConcurrency = computed(() => {
  if (selectedAlgorithmType.value === 'voice_llm') {
    return 2  // voice_llm 建议并发数较低
  }
  return 4  // 默认并发数
})

// 在 UI 中显示建议
const concurrencyHint = computed(() =>
  isVoiceLLM.value
    ? 'voice_llm 多轮测试耗时较长，建议并发数不超过 2'
    : ''
)
```

### 5. 确认：5 步流程不需要改动

E2ETest.vue 的 5 步向导结构完全不变：

| 步骤 | 组件 | 改动 |
|------|------|------|
| 0 | AlgorithmSelectionPanel | 不变 |
| 1 | TestCaseListContainer | 不变（筛选逻辑在 composable 中） |
| 2 | ResourceSelectionGrid | 不变（可选增加能力标签） |
| 3 | TestExecutionComponent | 不变（多轮进度在执行器文档中） |
| 4 | TaskReportPanel | 不变 |

## 不变部分

- E2ETest.vue 的 5 步向导结构
- useE2eView.ts 的步骤导航逻辑
- ResourceSelectionGrid 组件基础功能
- 设备扫描、添加设备功能
- 任务创建/启动/停止控制
- useDeviceManagement composable

## 引用关系

- ← `02_选用例/backend/01_TestCase模型新增字段` — TestCase.test_type
- ← `02_选用例/frontend/07_testCaseStore_test_type处理` — Store 提供含 test_type 的用例
- → `04_执行测试/backend/17_e2e_executor多轮循环` — 后端执行 voice_llm E2E 测试
- → `03_选设备API/backend/18_被测设备音量控制` — 设备音量控制能力
- → `03_选设备API/backend/29_设备驱动导轨控制集成` — 设备导轨控制能力
