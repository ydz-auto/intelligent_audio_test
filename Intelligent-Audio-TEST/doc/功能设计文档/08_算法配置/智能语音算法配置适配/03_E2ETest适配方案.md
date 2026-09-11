# E2ETest - E2E测试页面适配方案

## 1. 页面概述

### 1.1 页面定位
E2ETest 是端到端测试的核心页面，用于执行设备端的测试任务。算法配置化适配**已实施**：页面编排逻辑收敛于 `composables/useE2eView.ts`（Application 层），视图只消费其暴露的状态与动作。

### 1.2 页面路由
- 路由路径：`/E2ETest`
- 菜单位置：测试执行 > E2E测试

### 1.3 核心改动（已实施）
- 步骤0：选择算法类型（AlgorithmSelectionPanel + AlgorithmConfigModal 配置入口）
- 根据算法类型筛选用例（TestCaseListContainer 的 algorithm-type-filter）
- 根据算法类型筛选设备（Device.supportedAlgorithms 过滤）
- 算法参数随用例（algorithm_params 独立列）进入执行链路，任务级不重复传递

### 1.4 分层与命名口径
后端响应经 `success_response` 统一转 camelCase；前端 DDD 分层——Presentation（E2ETest.vue + 公共组件）只消费 composables（useE2eView/useAlgorithmConfig 等）与 camelCase Domain；`utils/api.ts`（Infrastructure）唯一感知 snake_case。用例执行的执行方式由被测设备 `device_type` 路由三执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor）；"api/e2e 为独立用例记录的 test_type 决定执行方式"属废弃口径，本页任务的 `type: 'e2e'` 仅是任务分类标识。

---

## 2. 页面流程改造

### 2.1 流程对比

```
原有流程:
  选择设备 → 选择用例 → 执行测试 → 查看结果

改造后流程:
  [选择算法类型] → 选择测试用例 → 选择测试设备 → 执行测试 → 查看结果
```

### 2.2 步骤说明（已实施，currentStep 0-4）

| 步骤 | 名称 | 说明 |
|-----|------|------|
| 步骤0 | 选择算法 | AlgorithmSelectionPanel 卡片选择，可新增/配置算法 |
| 步骤1 | 选择测试用例 | 按算法类型过滤（algorithm-type-filter），复用 TestCaseListContainer |
| 步骤2 | 选择测试设备 | 按设备支持算法过滤（supportedAlgorithms），复用 ResourceSelectionGrid |
| 步骤3 | 执行测试 | tasksApi.create + tasksApi.start，复用 TestExecutionComponent |
| 步骤4 | 查看结果 | 复用 TaskReportPanel |

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  E2E测试                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  步骤指示器: [1.选择算法] → [2.选择测试用例] → [3.选择测试设备] → [4.执行测试] → [5.查看结果] │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  第一步: 选择算法 (已实现)                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [⚙ 算法配置]                                                     │   │
│  │                                                                   │   │
│  │  算法卡片网格:                                                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 🎤 语音识别(ASR)  │  │ 🔊 语音合成(TTS)  │                     │   │
│  │  │ type: asr        │  │ type: tts        │                     │   │
│  │  │ ✓ 已选择         │  │                  │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 👤 说话人识别     │  │ 📊 ASR评估       │                     │   │
│  │  │ type: speaker    │  │ type: asr_eval   │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │                                                                   │   │
│  │  已选择: 语音识别(ASR)                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [下一步]                                    │
│                                                                          │
│  第二步: 选择测试用例 (已实现 - 复用TestCaseListContainer组件)            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  用例分组列表，支持:                                                │   │
│  │  - 新建分组/用例                                                    │   │
│  │  - 导入/导出用例                                                    │   │
│  │  - 批量选择用例                                                     │   │
│  │  - 标签筛选                                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [下一步]                                    │
│                                                                          │
│  第三步: 选择测试设备 (已实现 - 复用ResourceSelectionGrid组件)            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 新增设备] [扫描设备] [搜索框] [状态筛选▼]                       │   │
│  │                                                                   │   │
│  │  设备卡片列表:                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐│   │
│  │  │ ☐ 设备名称  型号: xxx  状态: 在线  [编辑][删除]              ││   │
│  │  │ ☐ 设备名称  型号: xxx  状态: 在线  [编辑][删除]              ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  │                                                                   │   │
│  │  分页控件                                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [开始任务]                                  │
│                                                                          │
│  第四步: 执行测试 (已实现 - 复用TestExecutionComponent组件)               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务信息 | 执行进度 | 设备资源 | 日志                             │   │
│  │                                                                   │   │
│  │  执行进度: ████████░░ 80%                                         │   │
│  │  已完成: 8  进行中: 1  待执行: 1                                   │   │
│  │                                                                   │   │
│  │  [暂停] [停止]                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  第五步: 查看结果 (已实现 - 复用TaskReportPanel组件)                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务报告                                                          │   │
│  │  - 测试结果统计                                                    │   │
│  │  - 详细报告表格                                                    │   │
│  │  - 结论分析                                                        │   │
│  │                                                                   │   │
│  │  [上一步] [导出报告] [发布] [开始新测试]                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 实现状态

### 4.1 已实现功能 ✅

| 功能 | 状态 | 说明 |
|------|------|------|
| 步骤0: 选择算法 | ✅ 已实现 | AlgorithmSelectionPanel 卡片网格 + 搜索 + 新增算法按钮 |
| 步骤1: 选择测试用例 | ✅ 已实现 | 复用 TestCaseListContainer（algorithm-type-filter + test-type-filter='e2e'） |
| 步骤2: 选择测试设备 | ✅ 已实现 | 复用 ResourceSelectionGrid（algorithmFilteredDevices） |
| 步骤3: 执行测试 | ✅ 已实现 | 复用 TestExecutionComponent，tasksApi.create + tasksApi.start |
| 步骤4: 查看结果 | ✅ 已实现 | 复用 TaskReportPanel |
| 进度导航 | ✅ 已实现 | ProgressNav（step-labels 5 步，go-to-step 跳转） |
| 算法配置入口 | ✅ 已实现 | AlgorithmConfigModal（useModal 注册） |
| 用例按算法过滤 | ✅ 已实现 | initializeE2eTests/fetchTagView 携带 algorithmType |
| 设备按算法过滤 | ✅ 已实现 | device.supportedAlgorithms.includes(selectedAlgorithmType) |

### 4.2 设计取舍说明 📋

| 功能 | 说明 |
|------|------|
| 页面级算法参数配置步骤 | 不设独立参数步骤——算法参数已按轮固化在用例的 algorithm_params 独立列中，执行时随用例下发；如需调整参数回到用例管理编辑 |

---

## 5. 数据结构

### 5.1 页面状态（已实施，useE2eView.ts 摘要）

```typescript
// 状态由 useE2eView composable 统一编排（Application 层），非 Pinia store
const currentStep = ref(0);                       // 0-4
const selectedAlgorithmType = ref<string | null>(null);
const algorithmList = ref([]);                    // camelCase Domain
const selectedTestCaseIds = ref([]);
const selectedDeviceIds = ref([]);
const deviceSearchQuery = ref('');
const selectedDeviceStatus = ref('all');
const isExecuting = ref(false);
const isPaused = ref(false);
const currentTaskId = ref<string | null>(null);
const taskName = ref('');
const logs / progress / associatedDevices / associatedCases ...
```

### 5.2 设备数据结构（camelCase）

```typescript
interface Device {
  id: string | number;
  name: string;
  deviceType: string;             // 被测设备类型：物理设备/HTTP API/WebSocket API，决定执行路由
  model?: string;
  status: 'online' | 'offline';
  connectionAddress?: string;
  supportedAlgorithms?: string[]; // 支持的算法类型（camelCase，见 08_Device适配方案）
}
```

### 5.3 任务创建参数（已实施，tasksApi.create payload）

```typescript
// 前端 → POST /api/v1/tasks（camelCase，后端 TaskCreateRequest 两种命名均接受）
{
  name: 'E2E测试任务_2026-09-11 12:00:00',
  type: 'e2e',                       // 任务分类标识（非执行路由依据）
  deviceIds: number[],               // 关联被测设备；执行方式由设备 device_type 路由
  caseIds: (string|number)[],        // 关联用例；算法参数随用例 algorithm_params 独立列下发
  config: { parallel: true, concurrentTasks: number }
}
// 随后 POST /api/v1/tasks/:id/start 启动
```

> TaskCreateRequest 亦支持可选 `algorithmType`/`algorithmParams` 字段，本页面流程不使用（参数以用例独立列为准）。

---

## 5. 组件设计

### 5.1 组件结构（已实施）

```
views/E2ETest.vue                     # 视图壳：组合 composable 与公共组件
├── composables/useE2eView.ts         # 页面编排（Application 层）：步骤/选择/任务创建启动/进度
├── ProgressNav.vue                   # 进度导航（5 步标签 + go-to-step）
├── TestStepContainer.vue             # 步骤容器（上一步/下一步）
├── AlgorithmSelectionPanel.vue       # 算法卡片选择面板（步骤0，含搜索/配置入口）
├── TestCaseListContainer.vue         # 用例分组列表（步骤1，algorithm-type-filter）
├── ResourceSelectionGrid.vue         # 设备资源网格（步骤2，algorithmFilteredDevices）
├── TestExecutionComponent            # 执行面板（步骤3：任务信息/进度/资源/日志）
├── TaskReportPanel.vue               # 结果报告（步骤4）
└── AlgorithmConfigModal.vue          # 算法配置弹窗（useModal/MODAL_TYPES 注册）
```

### 5.2 核心模板（实际结构摘要）

```vue
<template>
  <div class="test-view-common">
    <ProgressNav
      :current-step="currentStep"
      :step-labels="['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']"
      @go-to-step="goToStep"
    />

    <!-- 步骤0：选择算法 -->
    <TestStepContainer :is-active="currentStep === 0" title="选择算法" :show-prev="false" @next="nextStep">
      <AlgorithmSelectionPanel
        :algorithm-list="algorithmList"
        :selected-algorithm-type="selectedAlgorithmType"
        :search-query="algorithmSearchQuery"
        @select="selectAlgorithm"
        @open-config="openAlgorithmConfigModal"
      />
    </TestStepContainer>

    <!-- 步骤1：选择测试用例（按算法/测试类型过滤） -->
    <TestCaseListContainer
      :algorithm-type-filter="selectedAlgorithmType || 'all'"
      :test-type-filter="'e2e'"
      ...
    />

    <!-- 步骤2：选择测试设备（按支持算法过滤，下一步即"开始任务"） -->
    <ResourceSelectionGrid
      :items="algorithmFilteredDevices"
      :selected-ids="selectedDeviceIdsList"
      ...
    />
  </div>
</template>
```

---

## 6. 核心交互逻辑

### 6.1 步骤定义（已实施）

```typescript
// ProgressNav step-labels（currentStep 0-4）
['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']
```

### 6.2 算法选择与设备兼容性（已实施）

```typescript
// useE2eView.ts：设备是否支持当前算法（camelCase Domain）
const isDeviceCompatible = (device: Device) => {
  if (!selectedAlgorithmType.value) return true;
  const supportedAlgorithms = device.supportedAlgorithms;
  if (!supportedAlgorithms || !Array.isArray(supportedAlgorithms)) return true;
  return supportedAlgorithms.includes(selectedAlgorithmType.value);
};

// algorithmFilteredDevices：设备卡片网格只展示兼容设备
// 特殊算法提示：isVoiceLLM（voice_llm）时展示 voiceLlmHint
```

### 6.3 用例过滤（已实施）

```typescript
// 选择算法后，用例列表按算法类型 + 测试类型过滤
await initializeE2eTests(selectedAlgorithmType.value || undefined);
await fetchTagView({ testType: 'e2e', algorithmType: selectedAlgorithmType.value || undefined });
```

### 6.4 开始任务（已实施）

```typescript
const startTest = async () => {
  // 1. 校验：已选设备（至少一台，全部在线）、已选用例
  //    未勾选用例时按筛选条件拉取全量 ID：
  //    testCaseStore.fetchCaseIdsByFilter({ testType: 'e2e', algorithmType: selectedAlgorithmType })

  // 2. 创建任务（camelCase payload）
  const payload = {
    name: taskName.value || `E2E测试任务_${new Date().toLocaleString()}`,
    type: 'e2e',
    deviceIds: selectedDeviceIds,        // 关联被测设备，执行方式由 device_type 路由
    caseIds: selectedCaseIds,            // 算法参数随用例 algorithm_params 独立列下发
    config: { parallel: true, concurrentTasks: concurrentTasks.value }
  };
  const response = await tasksApi.create(payload);
  currentTaskId.value = response.id;

  // 3. 启动任务
  const startResponse = await tasksApi.start(response.id);
  // startResponse: { startTime, expectedTotalTime, expectedCompleteTime }（camelCase）
};
```

---

## 7. 设备算法兼容性（已实施）

### 7.1 设备过滤逻辑（useE2eView.ts 实际实现）

```typescript
// useE2eView.ts：兼容设备 = 基础过滤（搜索/状态）∩ 算法支持过滤
const algorithmFilteredDevices = computed(() => {
  if (!selectedAlgorithmType.value) {
    return filteredDevices.value;   // filteredDevices 来自 useDeviceManagement（搜索/状态筛选）
  }
  return filteredDevices.value.filter(device => {
    const supportedAlgorithms = device.supportedAlgorithms;   // camelCase，见 08_Device适配方案
    if (!supportedAlgorithms || !Array.isArray(supportedAlgorithms)) {
      return true;    // 未配置支持算法的设备视为兼容，不隐藏
    }
    return supportedAlgorithms.includes(selectedAlgorithmType.value);
  });
});
```

> 设计说明：只做"算法 → 设备"单向过滤，不做"设备 → 算法"反向收敛——步骤0 已先锁定算法，设备列表只需按支持算法收敛。

### 7.2 兼容性提示（voice_llm 特化提示）

```typescript
// useE2eView.ts：特殊算法提示（枚举化算法类型，非魔法字符串散落）
const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm');

const voiceLlmHint = computed(() => {
  if (!isVoiceLLM.value) return null;
  return 'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。';
});

const concurrencyHint = computed(() => {
  if (!isVoiceLLM.value) return null;
  return 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。';
});
```

设备卡片（ResourceSelectionGrid）本身不展示 supportedAlgorithms 标签；不兼容设备直接从网格中隐藏（经 algorithmFilteredDevices），选择动作仅允许在线设备（离线设备点击选择时记 warn 日志并拒绝）。

---

## 8. 算法选择列表组件（已实施，AlgorithmSelectionPanel.vue）

### 8.1 组件定位

实际落地组件为 `components/algorithm/AlgorithmSelectionPanel.vue`（设计稿中的 AlgorithmSelectList.vue 未采用），供 E2ETest/APITest 等测试页步骤0 复用；算法的编辑/删除入口收敛在 AlgorithmConfigPage 与 AlgorithmConfigModal，面板内只提供"选择 + 配置入口"。

### 8.2 Props / Emits（实际签名）

```typescript
// 数据源：AlgorithmOption（composables/useAlgorithmSelection.ts，camelCase Domain）
interface AlgorithmOption {
  value: string;        // 算法类型标识（如 voice_llm）
  name: string;         // 显示名
  group_id?: number;
  group_name?: string;  // 分组名（用于图标映射与搜索）
}

interface Props {
  algorithmList: AlgorithmOption[];
  selectedAlgorithmType: string | null;
  searchQuery: string;
}

// Emits
(e: 'select', type: string): void;              // 单选：点击卡片/勾选框即切换选择
(e: 'open-config', algo: AlgorithmOption): void; // 卡片右上 ⚙ 按钮 → 打开 AlgorithmConfigModal
(e: 'update:searchQuery', value: string): void;
```

### 8.3 核心模板（实际结构摘要）

```vue
<template>
  <div class="algorithm-selection">
    <div v-if="filteredAlgorithmList.length === 0" class="empty-state">
      暂无可用算法，请先配置算法
    </div>
    <div v-else class="algorithm-grid">
      <div
        v-for="algo in filteredAlgorithmList"
        :key="algo.value"
        class="algorithm-card"
        :class="{ selected: selectedAlgorithmType === algo.value }"
        @click="handleSelectAlgorithm(algo.value)"
      >
        <!-- 头部：图标（按 group_name 映射）+ 名称 + ⚙配置按钮(@click.stop open-config) -->
        <!-- 内容：分组元信息 -->
        <!-- 底部：选择checkbox + 选择/已选择按钮 -->
      </div>
    </div>
    <div v-if="selectedAlgorithmType" class="selected-info">
      当前选择：{{ getAlgorithmName(selectedAlgorithmType) }}
    </div>
  </div>
</template>
```

搜索过滤由组件内部完成：`filteredAlgorithmList` 按 `searchQuery` 对 `name / group_name / value` 做不区分大小写匹配；选中态以 `selectedAlgorithmType === algo.value` 判定。

---

## 9. 执行参数传递（已实施）

### 9.1 前端到后端（tasksApi.create + tasksApi.start）

```typescript
// utils/api.ts（Infrastructure 层）：POST /api/v1/tasks + POST /api/v1/tasks/:id/start
const payload = {
  name: 'E2E测试任务_2026-09-11 12:00:00',
  type: 'e2e',                        // 任务分类标识，非执行路由依据
  deviceIds: [1, 2],                  // 被测设备：执行方式由设备 device_type 路由三执行器
  caseIds: ['case_001', 'case_002'],  // 算法参数随用例 algorithm_params 独立列下发，任务级不传
  config: { parallel: true, concurrentTasks: 4 }
};
const response = await tasksApi.create(payload);   // → { id, ... }
const startResponse = await tasksApi.start(response.id);
// startResponse: { startTime, expectedTotalTime, expectedCompleteTime }（camelCase）
```

> 与旧设计差异：不再走 `executionService.executeE2ETest` 传任务级 `algorithm_params`；算法参数已按轮固化在用例 `test_cases.algorithm_params` 独立列，执行时由后端随用例读取。

### 9.2 后端处理（TaskCreateRequest → ExecutionEngine）

```python
# backend/schemas/task.py（请求 schema，经 AliasChoices 兼容 snake_case/camelCase）
class TaskCreateRequest(APIModel):
    name: str
    type: str
    case_ids: Optional[List[str]] = Field(None, alias='caseIds', validation_alias='caseIds')
    device_ids: Optional[List[int]] = Field(None, alias='deviceIds', validation_alias='deviceIds')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
```

链路：`POST /api/v1/tasks` 创建任务（blueprints/task_bp.py，写入用例/设备关联）→ `POST /api/v1/tasks/:id/start` 启动 → ExecutionEngine 按每台被测设备的 `device_type` 路由执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor），执行时从用例 `algorithm_params` 独立列取参数注入 E2E 指令。响应经 `success_response` 统一转 camelCase。

---

## 10. 状态管理（已实施，useE2eView composable）

### 10.1 编排模式

未采用设计稿中的 Pinia `useE2ETestStore`；页面状态由 Application 层 composable `useE2eView()` 统一编排，视图（E2ETest.vue）只消费其返回的状态与动作，符合 DDD 分层约定（Application 只见 Domain，Infrastructure 的 snake_case 不上浮）。

### 10.2 组合结构（useE2eView 内部复用的领域 composables）

| Composable | 职责 |
|-----------|------|
| `useDeviceManagement('test')` | 设备列表/搜索/状态筛选/分页/CRUD/连接测试 |
| `useE2eTest` | e2e 用例分组与标签视图数据（initializeE2eTests/fetchTagView） |
| `useAlgorithmSelection` | 算法列表/选择/搜索/AlgorithmConfigModal 开关，选择回调触发用例刷新 |
| `useTestCaseCard` + `useModalControl` | 用例/分组 CRUD 弹窗（MODAL_TYPES 注册） |
| `useTaskProgress` + `useTestControl` | 任务进度、暂停/恢复/停止 |
| `useTestReport` | 报告查看/结论编辑/导出/发布 |

### 10.3 关键状态与派生值（摘要）

```typescript
const currentStep = ref(0);                        // 0-4
const selectedTestCaseIds = ref<(string|number)[]>([]);
const selectedDeviceIds / associatedDevices / associatedCases ...
const concurrentTasks = ref(4);                    // 并发数（voice_llm 建议值见 concurrencyHint）

// 派生值
const algorithmFilteredDevices = computed(...);    // §7.1 设备按支持算法收敛
const canStartTest = computed(...);                // 开始任务前置校验
const isVoiceLLM = computed(...);                  // 特殊算法提示开关
```

---

## 11. 实施清单（已实施）

> 与设计稿差异落地记录：algorithmService→`algorithmApi`（Infrastructure api 层）；`useE2ETestStore`（Pinia）→`useE2eView`（composable）；`AlgorithmSelectList.vue`→`AlgorithmSelectionPanel.vue`；设备/用例选择器复用 `ResourceSelectionGrid`/`TestCaseListContainer`（未新建 DeviceSelector/TestCaseSelector）。

### 11.1 后端实施

- [x] 设备支持算法字段（devices.supported_algorithms 独立列，响应 camelCase supportedAlgorithms）
- [x] 用例按算法类型筛选（testcases 查询参数 algorithmType）
- [x] 任务创建/启动接口（POST /api/v1/tasks + POST /api/v1/tasks/:id/start，TaskCreateRequest 兼容两种命名）
- [x] 执行时从用例 algorithm_params 独立列取参考参数（reference_params）注入 E2E 指令
- [x] 执行路由：ExecutionEngine 按被测设备 device_type 分发三执行器

### 11.2 前端实施

- [x] 改造 E2ETest.vue：编排收敛于 useE2eView.ts（currentStep 0-4）
- [x] AlgorithmSelectionPanel.vue 算法卡片选择（select/open-config/searchQuery）
- [x] 用例按算法过滤（TestCaseListContainer algorithm-type-filter + test-type-filter='e2e'）
- [x] 设备按支持算法过滤（algorithmFilteredDevices + supportedAlgorithms）
- [x] 步骤控制（ProgressNav step-labels + TestStepContainer 上一步/下一步）
- [x] 算法参数不设页面级配置步骤（随用例独立列下发）
- [x] 任务创建/启动（tasksApi.create + tasksApi.start）

### 11.3 测试验证

- [x] 算法选择流程测试
- [x] 用例按算法筛选测试
- [x] 设备-算法兼容性测试（未配置支持算法的设备不隐藏）
- [x] 设备选择流程测试（仅在线设备可选）
- [x] 执行测试流程（创建+启动+进度+报告）
- [x] 步骤回退/重置流程测试
