# APITest - API测试页面适配方案

## 1. 页面概述

### 1.1 页面定位
APITest 是 API 测试的核心页面，用于执行 API 接口测试。算法配置化适配**已实施**：页面编排逻辑收敛于 `views/APITestLogic/apiTest.ts`（useApiTest，Application 层），视图（APITest.vue）只消费其暴露的状态与动作，与 E2ETest 保持一致的五步交互流程。

### 1.2 页面路由
- 路由路径：`/APITest`
- 菜单位置：测试执行 > API测试

### 1.3 核心改动（已实施）
- 步骤0：选择算法类型（AlgorithmSelectionPanel + AlgorithmConfigModal 配置入口）
- 根据算法类型筛选用例（TestCaseListContainer 的 algorithm-type-filter + test-type-filter='api'）
- 根据算法类型筛选 API（APIConfig.algorithmType 精确匹配）
- 算法参数随用例（algorithm_params 独立列）进入执行链路，页面不设参数配置步骤

### 1.4 分层与命名口径
后端响应经 `success_response` 统一转 camelCase；前端 DDD 分层——Presentation（APITest.vue + 公共组件）只消费 composables 与 camelCase Domain；`utils/api.ts`（Infrastructure）唯一感知 snake_case。用例执行的执行方式由被测设备 `device_type` 路由三执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor）；"api/e2e 为独立用例记录的 test_type 决定执行方式"属废弃口径，本页任务的 `type: 'api'` 仅是任务分类标识，任务关联的被测 API 通过 `apiIds` 字段传递。

---

## 2. 页面流程改造

### 2.1 流程对比

```
原有流程:
  选择用例 → 选择API → 执行测试 → 查看结果

改造后流程:
  [选择算法类型] → 选择测试用例 → 选择被测API → 执行测试 → 查看结果
```

### 2.2 步骤说明（已实施，currentStep 0-4）

| 步骤 | 名称 | 说明 |
|-----|------|------|
| 步骤0 | 选择算法 | AlgorithmSelectionPanel 卡片选择，可新增/配置算法 |
| 步骤1 | 选择测试用例 | 按算法类型过滤（algorithm-type-filter + test-type-filter='api'），复用 TestCaseListContainer |
| 步骤2 | 选择被测API | 按 APIConfig.algorithmType 过滤（allFilteredAPIs），复用 ResourceSelectionGrid |
| 步骤3 | 执行测试 | tasksApi.create + tasksApi.start（apiIds 关联被测 API），复用 TestExecutionComponent |
| 步骤4 | 查看结果 | 复用 TaskReportPanel |

### 2.3 与 E2ETest 的差异

| 项目 | E2ETest | APITest |
|-----|---------|---------|
| 步骤顺序 | 算法→用例→设备→执行→结果 | 算法→用例→API→执行→结果 |
| 资源选择 | 设备（supportedAlgorithms 过滤，未配置视为兼容） | API（algorithmType 精确匹配，未配置则不显示） |
| 任务关联字段 | deviceIds | apiIds |
| 编排位置 | composables/useE2eView.ts | views/APITestLogic/apiTest.ts |

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  API测试                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  步骤指示器: [1.选择算法] → [2.选择测试用例] → [3.选择被测API] → [4.执行测试] → [5.查看结果] │
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
│  │  │ 类型: asr        │  │ 类型: tts        │                     │   │
│  │  │ ☐ 选择           │  │ ☐ 选择           │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 👤 说话人识别     │  │ 📊 ASR评估       │                     │   │
│  │  │ 类型: speaker    │  │ 类型: asr_eval   │                     │   │
│  │  │ ☐ 选择           │  │ ☐ 选择           │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │                                                                   │   │
│  │  当前选择: 语音识别(ASR)                                           │   │
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
│  第三步: 选择被测API (已实现 - 复用ResourceSelectionGrid组件)             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 新增API] [搜索框] [状态筛选▼]                                  │   │
│  │                                                                   │   │
│  │  API卡片列表:                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐│   │
│  │  │ ☐ API名称  端点: http://...  状态: 在线  [编辑][删除]        ││   │
│  │  │ ☐ API名称  端点: http://...  状态: 在线  [编辑][删除]        ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  │                                                                   │   │
│  │  分页控件                                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [开始任务]                                  │
│                                                                          │
│  第四步: 执行测试 (已实现 - 复用TestExecutionComponent组件)               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务信息 | 执行进度 | API资源 | 日志                              │   │
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
| 步骤0: 选择算法 | ✅ 已实现 | 复用 AlgorithmSelectionPanel（卡片网格 + 搜索 + open-config 配置入口） |
| 步骤1: 选择测试用例 | ✅ 已实现 | 复用 TestCaseListContainer（algorithm-type-filter + test-type-filter='api'） |
| 步骤2: 选择被测API | ✅ 已实现 | 复用 ResourceSelectionGrid（allFilteredAPIs 按 algorithmType/状态/搜索过滤 + 分页） |
| 步骤3: 执行测试 | ✅ 已实现 | 复用 TestExecutionComponent，tasksApi.create + tasksApi.start（apiIds） |
| 步骤4: 查看结果 | ✅ 已实现 | 复用 TaskReportPanel |
| 进度导航 | ✅ 已实现 | ProgressNav（step-labels 5 步，go-to-step 跳转） |
| 算法配置入口 | ✅ 已实现 | AlgorithmConfigModal（useModal/MODAL_TYPES 注册） |
| 用例按算法过滤 | ✅ 已实现 | fetchTagView/fetchCaseIdsByFilter 携带 algorithmType |
| API按算法过滤 | ✅ 已实现 | allFilteredAPIs：api.algorithmType === selectedAlgorithmType |

### 4.2 设计取舍说明 📋

| 功能 | 说明 |
|------|------|
| 页面级算法参数配置步骤 | 不设独立参数步骤——算法参数已按轮固化在用例的 algorithm_params 独立列中，执行时随用例下发；如需调整参数回到用例管理编辑 |
| API 编辑入口绑定算法类型 | 后端 API 模型 algorithm_type 字段已落地、页面过滤逻辑已实现，但 APIEditModal 尚未提供算法类型编辑控件（见 09_API管理适配方案），当前 API 的 algorithmType 依赖后端数据维护 |

---

## 5. 数据结构

### 5.1 页面状态（已实施，useApiTest 摘要）

```typescript
// 状态由 views/APITestLogic/apiTest.ts 的 useApiTest 统一编排（Application 层），非 Pinia store
const currentStep = ref(0);                       // 0-4
const selectedAlgorithmType = ref<string | null>(null);
const algorithmList = ref<AlgorithmOption[]>([]); // camelCase Domain（useAlgorithmSelection）
const selectedTestCaseIds = ref<(string|number)[]>([]);
const selectedAPIIds = ref<(string|number)[]>([]);
const apiSearchQuery = ref('');
const apiFilter = ref('all');                     // all | online | offline
const concurrentTasks = ref(4);
const taskName = ref('');
// 派生值：allFilteredAPIs / filteredAPIs（分页切片）/ isVoiceLLM / stepHints
```

### 5.2 API 数据结构（camelCase，shared/types/businessTypes.ts）

```typescript
interface APIConfig {
  id: string | number;
  name: string;
  vendor?: string;
  apiUrl?: string;                     // 主端点（卡片展示字段）
  apiEndpoints?: any[];                // 端点列表（搜索匹配 url/endpoint）
  status: 'online' | 'offline' | 'busy' | 'error';
  algorithmType?: string;              // 关联算法类型（页面过滤依据）
  maxConcurrent?: number;              // 汇总并发上限用
  currentConcurrent?: number;
  avgResponseTime?: number;
  ...
}
```

### 5.3 任务创建参数（已实施，tasksApi.create payload）

```typescript
// 前端 → POST /api/v1/tasks（camelCase，后端 TaskCreateRequest 两种命名均接受）
{
  name: 'API测试任务_2026-09-11 12:00:00',
  description: '通过API测试任务',
  type: 'api',                         // 任务分类标识（非执行路由依据）
  caseIds: (string|number)[],          // 关联用例；算法参数随用例 algorithm_params 独立列下发
  apiIds: number[],                    // 关联被测 API；执行方式由设备/API 的 device_type 路由
  tags: []
}
// 随后 POST /api/v1/tasks/:id/start 启动，返回 { startTime, expectedTotalTime, expectedCompleteTime }
// 并发数默认取所选 API 的 maxConcurrent（缺省 currentConcurrent，兜底 5）求和
```

---

## 5. 组件设计

### 5.1 组件结构（已实施）

```
views/APITest.vue                          # 视图壳：组合 useApiTest 与公共组件
├── views/APITestLogic/apiTest.ts          # 页面编排（Application 层）：步骤/选择/任务创建启动/进度
├── ProgressNav.vue                        # 进度导航（5 步标签 + go-to-step）
├── TestStepContainer.vue                  # 步骤容器（上一步/下一步）
├── AlgorithmSelectionPanel.vue            # 算法卡片选择面板（步骤0，components/algorithm/）
├── TestCaseListContainer.vue              # 用例分组列表（步骤1，algorithm-type-filter）
├── ResourceSelectionGrid.vue              # API 资源网格（步骤2，allFilteredAPIs + apiDisplayFields）
├── TestExecutionComponent                 # 执行面板（步骤3：任务信息/进度/API资源/日志）
├── TaskReportPanel.vue                    # 结果报告（步骤4，含对比表组件）
├── PaginationComponent.vue                # API 列表分页
└── AlgorithmConfigModal.vue               # 算法配置弹窗（components/algorithm/）
```

### 5.2 核心模板（实际结构摘要）

```vue
<template>
  <div class="test-view-common">
    <ProgressNav
      :current-step="currentStep"
      :step-labels="['选择算法', '选择测试用例', '选择被测API', '执行测试', '查看结果']"
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
      :test-type-filter="'api'"
      ...
    />

    <!-- 步骤2：选择被测API（多选，下一步即"开始任务"→任务名弹窗） -->
    <ResourceSelectionGrid
      :items="filteredAPIs"
      :selected-ids="selectedAPIIds"
      :display-fields="[{ key: 'apiUrl', label: '端点' }, { key: 'description', label: '描述' }]"
      @toggle-selection="toggleAPISelection"
      @action-click="handleResourceAction"
    />
  </div>
</template>
```

---

## 6. 核心交互逻辑

### 6.1 步骤定义（已实施）

```typescript
// ProgressNav step-labels（currentStep 0-4）
['选择算法', '选择测试用例', '选择被测API', '执行测试', '查看结果']
```

### 6.2 算法选择处理（已实施）

```typescript
// useAlgorithmSelection（Application 层）驱动：选择后按算法刷新用例数据
const { algorithmList, selectedAlgorithmType, selectAlgorithm, openAlgorithmConfigModal, ... } =
  useAlgorithmSelection({ onSelectCallback: (type) => initializeApiTests() });

// 步骤1 用例列表按算法过滤（视图绑定）
// :algorithm-type-filter="selectedAlgorithmType || 'all'"
// :test-type-filter="'api'"

// 特殊算法提示：isVoiceLLM（voice_llm）时 stepHints.caseSelection
// 'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频'
```

> 与旧设计差异：不加载页面级 formSchema/默认参数（algorithmService.getFormSchema/getDefaultParams 属废弃口径），算法参数随用例 algorithm_params 独立列下发。

### 6.3 API 选择处理（已实施）

```typescript
// apiTest.ts：API 过滤 = 算法精确匹配 ∩ 状态 ∩ 关键词（名称/端点）
const allFilteredAPIs = computed(() => {
  return apis.value.filter(api => {
    let matchesAlgorithm = true;
    if (selectedAlgorithmType.value) {
      matchesAlgorithm = api.algorithmType === selectedAlgorithmType.value;  // 未配置算法类型的 API 不显示
    }
    let matchesStatus = true;
    if (apiFilter.value !== 'all') {
      matchesStatus = (api.status === 'online' ? 'online' : 'offline') === apiFilter.value;
    }
    let matchesSearch = /* 名称 或 apiEndpoints[].url|endpoint 包含关键词 */;
    return matchesAlgorithm && matchesStatus && matchesSearch;
  });
});
// filteredAPIs = allFilteredAPIs 的分页切片（apiCurrentPage/apiPageSize）
```

### 6.4 开始任务（已实施）

```typescript
// APITest.vue：步骤2 点击"开始任务" → 任务名弹窗确认 → nextStep()
const handleStartTask = () => {
  localTaskName.value = `API测试任务_${new Date().toLocaleString()}`;
  showTaskNameModal.value = true;
};
const confirmTaskName = () => { taskName.value = localTaskName.value; nextStep(); };

// apiTest.ts：nextStep 在 currentStep === 2 时创建并启动任务
const nextStep = async () => {
  if (currentStep.value === 2) {
    // 1. 校验：已选用例（未勾选则 fetchCaseIdsByFilter({ testType: 'api', algorithmType }) 拉全量）
    // 2. 校验：已选 API 全部存在且在线
    // 3. 创建任务（camelCase payload，apiIds 关联被测 API）
    const taskData = {
      name: taskName.value || 'API测试任务',
      description: '通过API测试任务',
      type: 'api',
      caseIds: caseIds,
      apiIds: selectedAPIIds.value,
      tags: []
    };
    const taskResponse = await tasksApi.create(taskData);
    currentTaskId.value = taskResponse.id;
    // 4. 并发数 = 所选 API 的 maxConcurrent（缺省 currentConcurrent，兜底 5）求和
    // 5. 启动任务
    const startResponse = await tasksApi.start(taskResponse.id);
    // startResponse: { startTime, expectedTotalTime, expectedCompleteTime }
  }
};
```

---

## 7. API 选择器组件（已实施，复用 ResourceSelectionGrid）

### 7.1 组件定位

未新建独立的 APISelector.vue；步骤2 复用公共 `ResourceSelectionGrid` 多选网格，APITest.vue 通过 `apiDisplayFields` 配置展示字段（端点 apiUrl / 描述 description），工具栏提供新增 API（openApiEditModal）/ 搜索（apiSearchQuery）/ 状态筛选（apiFilter）与分页（PaginationComponent）。数据过滤收敛于 useApiTest 的 `allFilteredAPIs`（见 §6.3），不再让展示组件自行拉取/过滤数据。

### 7.2 交互行为

- 多选：`@toggle-selection="toggleAPISelection"` 维护 selectedAPIIds，开始任务前校验全部在线
- 行内操作：`@action-click="handleResourceAction"`（test 连接测试 / edit 编辑 / delete 删除）
- 离线 API 可见但不可执行（开始任务时提示"以下API处于离线状态，无法执行测试"）

---

## 8. 算法类型快速筛选（未实施，已由现有过滤入口覆盖）

### 8.1 设计稿方案（未实施）

设计稿曾规划按算法类型统计数量的快速筛选栏（全部/翻译/ASR/声纹识别 + 计数徽标）。当前未落地，步骤0 的 AlgorithmSelectionPanel 选择 + 步骤2 的搜索/状态筛选已覆盖核心过滤诉求；如后续需要，可在 allFilteredAPIs 基础上按 algorithmType 分组计数实现，属增量优化项。

---

## 9. 执行参数传递（已实施）

### 9.1 前端到后端（tasksApi.create + tasksApi.start）

```typescript
// utils/api.ts（Infrastructure 层）：POST /api/v1/tasks + POST /api/v1/tasks/:id/start
const taskData = {
  name: 'API测试任务_2026-09-11 12:00:00',
  description: '通过API测试任务',
  type: 'api',                        // 任务分类标识，非执行路由依据
  caseIds: ['case_001', 'case_002'],  // 算法参数随用例 algorithm_params 独立列下发，任务级不传
  apiIds: [1, 2],                     // 关联被测 API
  tags: []
};
const taskResponse = await tasksApi.create(taskData);   // → { id, ... }
const startResponse = await tasksApi.start(taskResponse.id);
// startResponse: { startTime, expectedTotalTime, expectedCompleteTime }（camelCase）
```

> 与旧设计差异：不再走 `executionService.executeAPITest` 传任务级 `algorithm_params`；算法参数已按轮固化在用例 `test_cases.algorithm_params` 独立列，执行时由后端随用例读取。

### 9.2 后端处理（TaskCreateRequest → ExecutionEngine）

```python
# backend/schemas/task.py（请求 schema，经 AliasChoices 兼容 snake_case/camelCase）
class TaskCreateRequest(APIModel):
    name: str
    type: str
    case_ids: Optional[List[str]] = Field(None, alias='caseIds', validation_alias='caseIds')
    api_ids: Optional[List[int]] = Field(None, alias='apiIds', validation_alias='apiIds')
    device_ids: Optional[List[int]] = Field(None, alias='deviceIds', validation_alias='deviceIds')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
```

链路：`POST /api/v1/tasks` 创建任务（blueprints/task_bp.py，写入用例/API 关联）→ `POST /api/v1/tasks/:id/start` 启动 → ExecutionEngine 按被测对象 `device_type` 路由执行器（HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor；物理设备→E2EExecutor 属 E2E 页面场景），执行时从用例 `algorithm_params` 独立列取参数注入 API 请求，参考值取 `reference_params`（scope=api）。响应经 `success_response` 统一转 camelCase。

---

## 10. 状态管理（已实施，useApiTest composable）

### 10.1 编排模式

未采用设计稿中的 Pinia `useAPITestStore`；页面状态由 Application 层 composable `useApiTest()`（views/APITestLogic/apiTest.ts）统一编排，视图（APITest.vue）只消费其返回的状态与动作，符合 DDD 分层约定（Application 只见 Domain，Infrastructure 的 snake_case 不上浮）。

### 10.2 组合结构（useApiTest 内部复用的领域 composables）

| Composable / Store | 职责 |
|-------------------|------|
| `useTestCaseStore`（Pinia，共享状态层） | 用例/分组/标签数据与 CRUD（fetchTestCases/fetchTagView/fetchCaseIdsByFilter） |
| `useTestCaseCard` + `useModalControl` | 用例/分组 CRUD 弹窗（MODAL_TYPES 注册） |
| `useDeviceManagement`（复用于 API 列表管理） | API 列表/搜索/分页/CRUD/连接测试（'api' 模式） |
| `useAlgorithmSelection` | 算法列表/选择/搜索/AlgorithmConfigModal 开关 |
| `useTaskProgress` + `useTestControl` | 任务进度、暂停/恢复/停止 |
| `useTestReport` | 报告查看/结论编辑/导出/发布 |

### 10.3 关键状态与派生值（摘要）

```typescript
const currentStep = ref(0);                        // 0-4
const selectedTestCaseIds / selectedAPIIds ...
const apiSearchQuery / apiFilter ...
const concurrentTasks = ref(4);                    // 启动时按所选 API maxConcurrent 求和覆盖

// 派生值
const allFilteredAPIs = computed(...);             // §6.3 API 过滤
const isVoiceLLM = computed(...);                  // voice_llm 特化提示开关
const stepHints = computed(...);                   // 步骤提示文案
```

---

## 11. 实施清单（已实施）

> 与设计稿差异落地记录：algorithmService→`algorithmApi`（Infrastructure api 层）；`useAPITestStore`（Pinia）→`useApiTest`（views/APITestLogic/apiTest.ts composable）；`AlgorithmSelectList.vue`→`AlgorithmSelectionPanel.vue`；API/用例选择复用 `ResourceSelectionGrid`/`TestCaseListContainer`（未新建 APISelector/TestCaseSelector）；任务级算法参数配置步骤取消（参数随用例 algorithm_params 独立列）。

### 11.1 后端实施

- [x] API 模型增加 algorithm_type 字段（响应 camelCase algorithmType；编辑入口见 09 文档）
- [x] 任务创建/启动接口（POST /api/v1/tasks + POST /api/v1/tasks/:id/start，TaskCreateRequest 支持 apiIds/caseIds 等，兼容两种命名）
- [x] API 按算法类型筛选（前端 allFilteredAPIs 过滤已实现）
- [x] 用例按算法类型筛选（testcases 查询参数 algorithmType）
- [x] API执行时从用例 algorithm_params 独立列取参数、reference_params（scope=api）取参考值

### 11.2 前端实施

- [x] 改造 APITest.vue：编排收敛于 useApiTest（currentStep 0-4）
- [x] AlgorithmSelectionPanel 算法卡片选择（select/open-config/searchQuery）
- [x] 用例按算法过滤（TestCaseListContainer algorithm-type-filter + test-type-filter='api'）
- [x] API按算法过滤（allFilteredAPIs：algorithmType/状态/关键词）
- [x] 步骤控制（ProgressNav step-labels + TestStepContainer + 任务名弹窗）
- [x] 任务创建/启动（tasksApi.create + tasksApi.start，apiIds 关联）

### 11.3 测试验证

- [x] 算法选择流程测试
- [x] API 筛选测试（算法/状态/关键词组合）
- [x] 用例筛选测试
- [x] 执行测试流程（创建+启动+进度+报告）
- [x] 步骤回退/重置流程测试
- [x] 与 E2ETest 流程一致性测试（五步结构对齐，差异见 §2.3）
