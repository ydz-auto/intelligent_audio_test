# APITest与E2ETest测试功能开发计划（合并版）

## 一、项目概述

| 项目名称 | APITest/E2ETest 测试功能合并开发计划 |
|---------|-------------------------------------|
| 目标页面 | APITest.vue 及 E2ETest.vue |
| 后端模块 | API管理、任务执行、评估服务、设备驱动、报告服务 |
| 技术栈 | Electron + Vue 3 + Flask + SQLite |
| 代码规模 | 前端 ~10,000 行，后端 ~15,000 行 |

> **说明**：本文档将 APITest开发计划 和 E2ETest开发计划 合并为一个统一文档，避免重复工作量估算。

---

## 二、现有功能分析

### 2.1 前端页面结构

#### APITest.vue (API接口测试)

| 步骤 | 组件 | 功能 | 状态 |
|------|------|------|------|
| 步骤0 | 算法选择 | 选择测试算法（翻译/ASR等），支持算法配置弹窗 | ✅ 已完成 |
| 步骤1 | 测试用例选择 | TestCaseListContainer，支持用例分组管理 | ✅ 已完成 |
| 步骤2 | API选择 | ResourceSelectionGrid，支持API CRUD、分页、搜索 | ✅ 已完成 |
| 步骤3 | 执行监控 | TestExecutionComponent，实时进度、日志、API状态 | ⚠️ 部分异常 |
| 步骤4 | 结果报告 | TaskReportPanel，支持图表对比、结论编辑 | ⚠️ 部分异常 |

#### E2ETest.vue (端到端设备测试)

| 步骤 | 组件 | 功能 | 状态 |
|------|------|------|------|
| 步骤0 | 算法选择 | TestStepContainer + algorithm-grid | ✅ 已完成 |
| 步骤1 | 测试用例 | TestCaseListContainer - 内部管理模态窗 | ✅ 已完成 |
| 步骤2 | 测试设备 | ResourceSelectionGrid + pagination | ✅ 已完成 |
| 步骤3 | 执行测试 | TestExecutionComponent | ⚠️ 部分异常 |
| 步骤4 | 查看结果 | TaskReportPanel | ⚠️ 部分异常 |

### 2.2 共用组件分析

| 组件 | 文件路径 | APITest问题 | E2ETest问题 | 合并策略 |
|------|----------|-------------|-------------|----------|
| TaskReportPanel | components/report/TaskReportPanel.vue | P3: 报告数据适配 | F23: 数据格式适配 | 合并为1项 |
| OverviewCardComponent | components/report/OverviewCardComponent.vue | P3: 数据格式不匹配 | F24: 组件适配 | 合并为1项 |
| ComparisonTableComponent | components/report/ComparisonTableComponent.vue | P4: 表格渲染异常 | F24: 组件适配 | 合并为1项 |
| TestCaseDetailModal | components/common/modal/TestCaseDetailModal.vue | P1: 数据绑定异常 | F25: 详情展示修复 | 合并为1项 |
| TestCaseReportDetail | components/common/TestCaseReportDetail.vue | P1b: 时间轴适配 | F25: 详情展示修复 | 合并为1项 |

---

## 三、已完成后端功能

### 3.1 APITest后端 (API测试)

| 功能 | 说明 | 代码位置 | 状态 |
|------|------|----------|------|
| API CRUD | API的创建、查询、更新、删除 | api_controller.py | ✅ 已完成 |
| API健康检查 | 第三方API健康状态检测 | api_executor.py/_health_check | ✅ 已完成 |
| API调用适配 | HTTP/WebSocket协议支持、参数渲染 | api_driver.py | ✅ 已完成 |
| 异步执行机制 | 队列控制、并发管理、动态超时 | api_executor.py | ✅ 已完成 |
| 任务生命周期 | 任务创建、执行、等待完成、结果获取 | api_executor.py | ✅ 已完成 |
| 评估服务集成 | 调用评估API、解析响应 | evaluation_service.py | ✅ 已完成 |
| 字段映射 | 动态字段映射、多算法类型支持 | field_mapper.py | ✅ 已完成 |
| 任务用例详情 | 获取单个用例执行详情 | task_controller.py/get_case_detail | ✅ 已完成 |
| 用例增删改 | 任务执行过程中用例管理 | task_controller.py/update_cases | ✅ 已完成 |

### 3.2 E2ETest后端 (端到端测试)

#### Blueprint API (32 人天)

| 序号 | 模块 | 路由数 | 状态 |
|------|------|--------|------|
| B1 | 任务管理API | 15 | ✅ 已完成 |
| B2 | 执行控制API | 2 | ✅ 已完成 |
| B3 | 报告管理API | 16 | ✅ 已完成 |
| B4 | 设备管理API | 12 | ✅ 已完成 |
| B5 | SSE事件推送 | - | ✅ 已完成 |
| B6 | 任务Controller | - | ✅ 已完成 |
| B7 | 报告Controller | - | ✅ 已完成 |
| B8 | 设备Controller | - | ✅ 已完成 |

#### 执行引擎 (10 人天)

| 序号 | 组件 | 状态 |
|------|------|------|
| B9 | E2EExecutor | ✅ 已完成 |
| B10 | BaseExecutor | ✅ 已完成 |
| B11 | DeviceResultCollector | ✅ 已完成 |
| B12 | AudioEngine | ✅ 已完成 |

#### 设备驱动 (8 人天)

| 序号 | 驱动类型 | 状态 |
|------|----------|------|
| B13 | AndroidDriver | ✅ 已完成 |
| B14 | HarmonyDriver | ✅ 已完成 |
| B15 | PlaudDriver | ✅ 已完成 |
| B16 | XiaoyiFace2FaceDriver | ✅ 已完成 |
| B17 | XiaoyiSimultaneousInterpretationDriver | ✅ 已完成 |
| B18 | HarmonyHardenXiaoyiHuiJiDriver | ✅ 已完成 |

---

## 四、工作量总览（合并后）

| 分类 | 原APITest | 原E2ETest | 合并后 | 节省 |
|------|-----------|-----------|--------|------|
| 前端已完成 | - | 45人天 | 45人天 | - |
| 后端已完成 | 9人天 | 50人天 | 59人天 | - |
| 前端步骤3+4修复 | 7人天 | 15人天 | 13人天 | 9人天 |
| 后端步骤3+4适配 | 2人天 | 8人天 | 6人天 | 4人天 |
| 音频播放问题修复(E4) | - | 6人天 | 6人天 | - |
| 音频功能优化(AF1-AF5) | - | - | **10人天** | 新增 |
| API测试执行器适配(AD1-AD3) | - | - | **7人天** | 新增 |
| 独立服务化(SVC1-SVC9) | - | - | **21人天** | 新增 |
| PostgreSQL迁移(PG1-PG8) | - | - | **4人天** | 新增 |
| APITest异步并发API(A1) | - | - | **4人天** | 新增 |
| **待开发合计** | 9人天 | 29人天 | **71人天** | - |
| **总计** | - | - | **175人天** | - |

---

## 五、待开发工作（合并版）

### 5.1 共用组件修复（按组件合并）

| 序号 | 组件 | 原APITest问题 | 原E2ETest问题 | 合并后工作量 | 代码位置 | 状态 |
|------|------|--------------|--------------|-------------|----------|------|
| S1 | TestCaseDetailModal + TestCaseReportDetail | P1+P1b (3人天) | F25 (3人天) | **3人天** | TestCaseDetailModal.vue, TestCaseReportDetail.vue | 待修复 |
| S2 | TaskReportPanel + 报告组件 | P3+P4 (3人天) | F23+F24 (9人天) | **4人天** | reportService.ts, OverviewCardComponent.vue, ComparisonTableComponent.vue | 待适配 |

### 5.2 共用功能

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| C1 | 用例增删功能 | 任务执行过程中无法动态添加/移除测试用例，skipTestCase和removeTestCase为空实现（APITest和E2ETest共用） | 3人天 | apiTest.ts, useE2eView.ts, TestExecutionComponent.vue | 待开发 |

### 5.3 APITest特有工作

| 序号 | 问题 | 说明 | 工作量 | 代码位置 | 状态 |
|------|------|------|--------|----------|------|
| A1 | 异步和并发调用算法API | 当前API调用为同步方式，需要实现异步并发调用机制，支持多API同时调用和结果汇总 | 4人天 | api_executor.py, api_driver.py | 待开发 |

### 5.4 E2ETest特有工作

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| E1 | 设备并发状态显示 | TestExecutionComponent中设备并发数/队列长度显示适配 | 2人天 | TestExecutionComponent.vue | 待开发 |
| E2 | 用例跳过UI集成 | 执行中跳过按钮与后端API集成 | 1人天 | useE2eView.ts | 待开发 |
| E3 | 设备状态API适配 | 执行监控中设备状态数据结构适配 | 3人天 | task_bp.py, task_controller.py | 待开发 |
| E4 | 音频播放问题 | 噪声循环处理bug、混合播放loop参数错误、进度显示不准确 | 6人天 | audio_engine.py | 待修复 |

### 5.4 音频播放功能优化（新增）

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| AF1 | 噪声循环播放bug修复 | 当前第1363行将干声和噪声混合传入play_multi导致干声被错误循环，应分别处理干声和噪声的播放 | 2人天 | audio_engine.py (第1289-1405行) | 待修复 |
| AF2 | 设备资源锁机制优化 | 当前_device_locks锁的获取和释放时机不明确，可能导致死锁或资源泄露 | 2人天 | audio_engine.py (_get_device_lock) | 待优化 |
| AF3 | 多任务设备抢占处理 | 当多个任务同时需要使用同一设备时，当前实现会阻塞或失败，需要实现设备预约和排队机制 | 3人天 | audio_engine.py (stop_task_audio) | 待开发 |
| AF4 | 预览与执行offset同步 | 预览时的offset计算与实际执行时的offset计算可能不一致，需要统一逻辑 | 1人天 | audio_engine.py, testcase_controller.py | 待验证 |
| AF5 | 播放设备资源抢占优化 | 解决多个测试任务同时使用同一物理设备时的冲突问题，实现设备资源的动态分配 | 2人天 | audio_engine.py, audio_service.py | 待开发 |

### 5.5 后端适配工作

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| B1 | 报告数据聚合适配 | 统一报告数据结构，复用组件同时支持APITest和E2ETest | 3人天 | report_controller.py, report_bp.py | 待开发 |

---

## 六、工作量明细表

| 分类 | 工作项 | 工作量 | 优先级 |
|------|--------|--------|--------|
| **前端** | | | |
| | S1: TestCaseDetailModal + TestCaseReportDetail 修复 | 3人天 | 高 |
| | S2: TaskReportPanel + 报告组件适配 | 4人天 | 高 |
| | C1: 共用用例增删功能 | 3人天 | 高 |
| | E1: E2ETest 设备并发状态显示 | 2人天 | 高 |
| | E2: E2ETest 用例跳过UI集成 | 1人天 | 高 |
| | **前端小计** | **13人天** | |
| **后端** | | | |
| | B1: 报告数据聚合适配 | 3人天 | 高 |
| | E3: E2ETest 设备状态API适配 | 3人天 | 高 |
| | E4: 音频播放问题修复 | 6人天 | 高 |
| | AF1: 噪声循环播放bug修复 | 2人天 | 高 |
| | AF2: 设备资源锁机制优化 | 2人天 | 中 |
| | AF3: 多任务设备抢占处理 | 3人天 | 高 |
| | AF4: 预览与执行offset同步 | 1人天 | 中 |
| | AF5: 播放设备资源抢占优化 | 2人天 | 高 |
| | AD1: 执行器职责边界模糊优化 | 2人天 | 高 |
| | AD2: API结果与评估服务解耦 | 3人天 | 高 |
| | AD3: 并发控制与API队列适配 | 2人天 | 高 |
| | A1: APITest异步和并发调用算法API | 4人天 | 高 |
| | SVC1: 服务拆分框架 | 5人天 | 高 |
| | SVC2: 进程管理 | 2人天 | 中 |
| | SVC3: API Service健康检查 | 1人天 | 中 |
| | SVC4: E2E Service设备管理 | 2人天 | 中 |
| | SVC5: 共用数据库适配 | 3人天 | 高 |
| | SVC6: 跨服务通信 | 3人天 | 高 |
| | SVC7: 配置分离 | 2人天 | 低 |
| | SVC8: 日志分离 | 1人天 | 低 |
| | SVC9: 部署脚本更新 | 2人天 | 低 |
| | PG1-PG8: PostgreSQL迁移 | 4人天 | 高 |
| | **后端小计** | **63人天** | |
| **总计** | | **71人天** | |

---

## 七、里程碑计划

| 里程碑 | 内容 | 前端 | 后端 | 交付时间 | 状态 |
|--------|------|------|------|----------|------|
| M0 | 基础功能上线 | 45人天 | 59人天 | 已完成 | ✅ 已完成 |
| M1 | 共用组件修复 (S1+S2) + 共用功能 (C1) | 10人天 | 3人天 | 第1周 | 待开发 |
| M2 | APITest异步并发API (A1) | - | 4人天 | 第1周 | 待开发 |
| M3 | E2ETest特有功能 (E1+E2+E3) | 3人天 | 3人天 | 第2周 | 待开发 |
| M4 | 音频播放问题修复 (E4) | - | 6人天 | 第2周 | 待开发 |
| M5 | 音频功能优化 (AF1-AF5) | - | 10人天 | 第3周 | 待开发 |
| M6 | API测试执行器适配 (AD1-AD3) | - | 7人天 | 第3周 | 待开发 |
| M7 | 独立服务化 (SVC1-SVC9) | - | 21人天 | 第4-5周 | 待开发 |
| M8 | PostgreSQL迁移 (PG1) | 1人天 | 3人天 | 第5-6周 | 待开发 |

---

## 八、技术架构

### 8.1 前端架构

```
APITest.vue / E2ETest.vue
├── TestExecutionComponent.vue (共用)
│   ├── 进度监控
│   ├── 实时日志
│   ├── API/设备资源状态
│   └── 用例增删控制
├── TaskReportPanel.vue (共用)
│   ├── OverviewCardComponent.vue
│   ├── ComparisonTableComponent.vue
│   ├── CaseTagComparisonComponent.vue
│   └── TimelineComparison.vue
└── TestCaseDetailModal.vue (共用)
    └── TestCaseReportDetail.vue
```

### 8.2 后端架构

```
backend/
├── blueprints/
│   ├── api_bp.py (APITest)
│   ├── task_bp.py (共用)
│   ├── execution_bp.py (共用)
│   ├── report_bp.py (共用)
│   ├── device_bp.py (E2ETest)
│   └── sse_bp.py (共用)
├── controllers/
│   ├── api_controller.py
│   ├── task_controller.py
│   ├── report_controller.py
│   └── device_controller.py
└── utils/
    ├── api_driver.py (APITest)
    ├── api_executor.py (APITest)
    ├── e2e_executor.py (E2ETest)
    └── audio_engine.py (E2ETest)
```

---

## 九、关键文件索引

### 共用组件

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| TestExecutionComponent | frontend/src/components/TestExecutionComponent.vue | 执行监控组件 |
| TaskReportPanel | frontend/src/components/report/TaskReportPanel.vue | 报告面板 |
| TestCaseDetailModal | frontend/src/components/common/modal/TestCaseDetailModal.vue | 用例详情模态窗 |
| TestCaseReportDetail | frontend/src/components/common/TestCaseReportDetail.vue | 用例结果详情 |
| GlobalModalContainer | frontend/src/components/common/modal/GlobalModalContainer.vue | 模态窗容器 |

### APITest特有

| 组件 | 文件路径 |
|------|----------|
| APITest.vue | frontend/src/views/APITest.vue |
| apiTest.ts | frontend/src/views/APITestLogic/apiTest.ts |
| AlgorithmConfigModal | frontend/src/components/algorithm/AlgorithmConfigModal.vue |

### E2ETest特有

| 组件 | 文件路径 |
|------|----------|
| E2ETest.vue | frontend/src/views/E2ETest.vue |
| useE2eView.ts | frontend/src/composables/useE2eView.ts |
| TestCaseListContainer | frontend/src/components/common/test-case/TestCaseListContainer.vue |
| DeviceSelector | frontend/src/components/common/modal/DeviceSelector.vue |

### 后端

| 模块 | 文件路径 |
|------|----------|
| API Blueprint | backend/blueprints/api_bp.py |
| 任务 Blueprint | backend/blueprints/task_bp.py |
| 报告 Blueprint | backend/blueprints/report_bp.py |
| 设备 Blueprint | backend/blueprints/device_bp.py |
| API执行器 | backend/utils/api_executor.py |
| E2E执行器 | backend/utils/e2e_executor.py |
| 音频引擎 | backend/utils/audio_engine.py |

---

## 十、问题详解

### S1: TestCaseDetailModal 数据绑定异常

**问题描述**：
- 步骤3执行过程中点击用例查看详情时，TestCaseReportDetail组件无法正确显示数据
- 后端 `get_case_detail` 返回的数据格式与前端期望的prop格式不匹配

**后端返回数据格式** (task_controller.py:get_case_detail):
```json
{
  "task_id": 1,
  "case_id": 123,
  "case_name": "测试用例",
  "execution_status": "completed",
  "evaluation_status": "completed",
  "results": [{
    "id": 1,
    "device_name": "设备1",
    "api_name": "API1",
    "dimensions": [
      {"id": 1, "name": "WER", "value": 85.5, "score": 5}
    ],
    "algorithm_result": {...}
  }],
  "logs": [...]
}
```

**前端期望prop格式** (TestCaseReportDetail.vue):
```typescript
props: {
  dimensions: Array,        // result.dimensions
  audioPath: String,        // result.resultData?.audioPath
  asrResult: String,        // result.asrResult
  transResult: String,      // result.translationResult
}
```

**修复方向**：
1. 统一后端返回字段名与前端期望的prop名
2. 或在前端添加数据转换逻辑适配后端返回格式

---

### S1b: RTTM/STM时间轴适配

**问题描述**：
- TestCaseReportDetail 组件的 `hasTimelineData` 计算属性仅检查 `props.algorithmResults`
- 但 RTTM/STM 时间轴数据可能存储在 `result.resultData` 字段中

**修复方向**：
1. 修改 `hasTimelineData` 计算属性，同时检查 `results[].resultData` 中的 RTTM/STM 数据

---

### S2: 报告数据适配异常

**问题描述**：
- OverviewCardComponent等报告组件无法正确渲染报告数据
- reportService.viewTaskReport返回的数据结构与报告组件期望的格式不匹配
- 影响APITest和E2ETest两个页面

**修复方向**：
1. 检查 reportService.ts 中 viewTaskReport 的数据转换逻辑
2. 确保 summary 字段包含 allMetrics、resources、deviceStats 等报告组件需要的字段

---

### A1: 异步和并发调用算法API (APITest特有)

**问题描述**：
- 当前API调用为同步方式，无法充分利用API并发能力
- 多API同时调用时无法有效汇总结果
- 执行效率低下

**修复方向**：
1. 实现异步API调用机制，使用 asyncio 或线程池
2. 支持多API同时调用和结果汇总
3. 实现API调用超时和重试机制

---

### C1: 用例增删功能缺失 (共用)

**问题描述**：
- 任务执行过程中无法动态添加新测试用例
- 任务执行过程中无法移除待执行的测试用例
- TestExecutionComponent中skipTestCase和removeTestCase为空实现

**修复方向**：
1. 后端：实现 task_bp.py 的 `/tasks/<task_id>/cases` PATCH 方法
2. 前端：实现 skipTestCase 和 removeTestCase 的API调用逻辑

---

### E1-E2: 设备并发状态与用例跳过 (E2ETest)

**问题描述**：
- TestExecutionComponent中设备并发数/队列长度显示不正确
- 用例跳过按钮未与后端API集成

**修复方向**：
1. 适配设备状态数据结构
2. 实现skipTestCase与后端API的集成

---

### E4: 音频播放问题

**问题描述**：
- 噪声循环处理bug：noise_multi在循环内被重复创建
- 混合播放loop参数错误：干声+噪声混合播放时loop参数错误
- 音频播放进度显示不准确

**修复方向**：
1. 将noise_multi创建移至循环外
2. 修正混合播放的loop参数
3. 修复音频播放进度计算逻辑

---

### AF1: 噪声循环播放bug修复

**问题描述**：
当前 `audio_engine.py` 第1363行存在bug：
```python
all_configs = dry_multi + noise_multi
self.driver.play_multi(all_configs, device_index, stop_event, loop=True)
```
干声和噪声混合传入 `play_multi`，导致干声也被错误地循环播放。

**代码位置**：
- `backend/utils/audio_engine.py` 第1289-1405行

**修复方向**：
1. 将干声和噪声分开处理
2. 干声使用 `loop=False`
3. 噪声单独使用 `loop=True` 循环播放
4. 确保干声播放完毕后噪声才停止（或按原设计）

---

### AF2: 设备资源锁机制优化

**问题描述**：
当前 `_device_locks` 锁的获取和释放时机不明确：
```python
def _get_device_lock(self, device_index):
    with self._device_locks_lock:
        if device_index not in self._device_locks:
            self._device_locks[device_index] = threading.Lock()
        return self._device_locks[device_index]
```
锁在整个播放过程中被持有，可能导致死锁或资源泄露。

**代码位置**：
- `backend/utils/audio_engine.py` 第612-616行

**修复方向**：
1. 实现上下文管理器（Context Manager）来自动管理锁
2. 确保锁在异常情况下也能正确释放
3. 添加锁超时机制避免死锁
4. 增加锁使用日志便于调试

---

### AF3: 多任务设备抢占处理

**问题描述**：
当多个任务同时需要使用同一设备时，当前实现会阻塞或失败。例如：
- Task A 正在设备34上播放
- Task B 也想使用设备34
- 当前实现没有任何排队或预约机制

**代码位置**：
- `backend/utils/audio_engine.py` 第1465-1500行

**修复方向**：
1. 实现设备资源预约机制
2. 为每个设备维护一个播放队列
3. 实现任务的优先级调度
4. 支持设备占用超时自动释放

---

### AF4: 预览与执行offset同步

**问题描述**：
预览时的offset计算与实际执行时的offset计算可能不一致：
- 预览调用：`audio_controller.py` 的 `preview` 方法
- 执行调用：`e2e_executor.py` 的播放逻辑

两个路径使用不同的offset计算方式。

**代码位置**：
- `backend/utils/audio_engine.py` 第87-138行（calculate_audio_delays）
- `backend/controllers/testcase_controller.py` 第XXX行

**修复方向**：
1. 统一offset计算逻辑到 `calculate_audio_delays` 函数
2. 确保预览和执行使用相同的入口
3. 添加单元测试验证offset计算正确性

---

### AF5: 播放设备资源抢占优化

**问题描述**：
多个测试任务同时使用同一物理设备时存在冲突问题：
- PyAudio限制同一设备只能打开一个流
- 当前 `active_players` 字典管理不完善
- 停止播放时可能出现竞争条件

**代码位置**：
- `backend/utils/audio_engine.py` 第875行（active_players字典）
- `backend/utils/audio_engine.py` 第1465-1546行

**修复方向**：
1. 优化 `active_players` 字典的并发访问
2. 实现更细粒度的设备锁定
3. 支持设备强制释放（即使任务异常退出）
4. 增加资源监控和告警机制

---

## 十、API测试执行器适配层

### 10.1 适配层概述

当前 `api_executor.py` 和 `audio_engine.py` 存在功能重叠和职责边界不清晰的问题，需要明确适配层职责：

| 模块 | 职责 | 代码位置 |
|------|------|----------|
| api_executor.py | API测试任务执行（调用第三方API） | `backend/utils/api_executor.py` |
| e2e_executor.py | E2E测试任务执行（设备控制+音频播放） | `backend/utils/e2e_executor.py` |
| audio_engine.py | 底层音频播放控制 | `backend/utils/audio_engine.py` |

### 10.2 API测试执行器适配问题

| 序号 | 问题 | 说明 | 工作量 | 代码位置 | 状态 |
|------|------|------|--------|----------|------|
| AD1 | 执行器职责边界模糊 | api_executor同时处理API调用和结果存储，职责过重 | 2人天 | api_executor.py | 待优化 |
| AD2 | API结果与评估服务解耦 | 当前API测试结果直接写入DB后再异步评估，存在状态同步问题 | 3人天 | api_executor.py, evaluation_service.py | 待开发 |
| AD3 | 并发控制与API队列适配 | APIExecutor的队列机制与ExecutionEngine的并发控制存在冲突 | 2人天 | api_executor.py, execution_engine.py | 待修复 |

### 10.3 适配层设计

**统一执行引擎接口**：
```python
class BaseExecutor(ABC):
    """执行器基类 - 统一定义API/E2E执行器接口"""
    def execute_case(self, task_id, case_id): pass
    def acquire_execution_right(self, resource_id, task_id): pass
    def release_execution_right(self, resource_id, task_id): pass
```

**API执行器适配要点**：
1. 移除APIExecutor中直接操作DB的逻辑，统一通过ExecutionEngine处理
2. 评估服务结果回调统一通过事件机制通知
3. API并发控制移至统一的资源管理器

---

## 十一、API/E2E测试独立服务化

### 11.1 服务化背景

当前API测试和E2E测试共用同一Flask进程，存在以下问题：
- API测试的长时间HTTP轮询占用资源
- E2E测试的设备驱动加载影响API响应速度
- 两侧的配置文件和日志系统混合

### 11.2 服务化架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    Electron 主进程                       │
└─────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              API Test Service (独立Flask)               │
│  - api_bp.py (API CRUD)                                │
│  - api_executor.py (API调用)                           │
│  - evaluation_service.py (评估计算)                     │
│  - 健康检查定时任务                                      │
└─────────────────────────────────────────────────────────┘
                    │                    │
┌─────────────────────────────────────────────────────────┐
│              E2E Test Service (独立Flask)                │
│  - device_bp.py (设备管理)                              │
│  - e2e_executor.py (设备控制)                           │
│  - audio_engine.py (音频播放)                           │
│  - 设备驱动 (Android/Harmony/Plaud等)                   │
└─────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              Shared SQLite Database                     │
│  - 任务表、报告表、设备表 (共用)                          │
│  - API配置表 (API Service专用)                          │
│  - 播放设备表 (E2E Service专用)                         │
└─────────────────────────────────────────────────────────┘
```

### 11.3 服务化工作量

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| SVC1 | 服务拆分框架 | 创建独立Flask应用，提取共用代码到shared模块 | 5人天 | backend/services/api_service/, backend/services/e2e_service/ | 待开发 |
| SVC2 | 进程管理 | 使用supervisor或systemd管理双服务进程 | 2人天 | backend/ | 待开发 |
| SVC3 | API Service健康检查 | API服务独立健康检查和监控 | 1人天 | api_service/ | 待开发 |
| SVC4 | E2E Service设备管理 | 设备服务独立启动和驱动加载 | 2人天 | e2e_service/ | 待开发 |
| SVC5 | 共用数据库适配 | 统一数据库连接池和Session管理 | 3人天 | backend/models/ | 待开发 |
| SVC6 | 跨服务通信 | SSE事件统一推送（通过主进程代理） | 3人天 | backend/sse/ | 待开发 |
| SVC7 | 配置分离 | 分离API和E2E的独立配置 | 2人天 | backend/config/ | 待开发 |
| SVC8 | 日志分离 | 分离两服务的日志输出 | 1人天 | backend/logs/ | 待开发 |
| SVC9 | 部署脚本更新 | 更新部署脚本支持双服务 | 2人天 | scripts/deploy/ | 待开发 |

### 11.4 服务化后工作量汇总

| 分类 | 原工作量 | 新增工作量 | 合并后工作量 | 节省 |
|------|---------|-----------|-------------|------|
| API测试执行器适配 | 0人天 | 7人天 | 7人天 | - |
| 独立服务化 | 0人天 | 21人天 | 21人天 | - |
| **新增小计** | **0人天** | **28人天** | **28人天** | - |

---

## 十二、PostgreSQL数据库迁移

### 12.1 迁移背景

当前系统使用SQLite数据库，存在以下局限性：
- 并发写入能力有限，不适合多用户场景
- 无法高效支持远程访问和集群部署
- 备份和恢复机制相对简单

### 12.2 PostgreSQL迁移工作量

| 序号 | 功能点 | 说明 | 工作量 | 代码位置 | 状态 |
|------|--------|------|--------|----------|------|
| PG1 | 数据库迁移与时区配置 | SQLite迁移到PostgreSQL + UTC8时区配置 + 数据验证 | 4人天 | backend/models/ | 待开发 |

---

## 十三、更新记录

| 日期 | 更新内容 | 更新人 |
|------|----------|--------|
| 2026-04-02 | 首次创建APITest.vue页面和后端开发计划 | - |
| 2026-04-02 | 首次创建E2ETest.vue页面与模态窗开发计划 | - |
| 2026-04-07 | 合并APITest和E2ETest开发计划，识别重复工作量，合并后总工时从38人天降至25人天 | - |
| 2026-04-07 | 新增音频播放功能优化项(AF1-AF5)：噪声循环播放bug修复、设备资源锁机制优化、多任务设备抢占处理、预览与执行offset同步、播放设备资源抢占优化，共增加10人天工作量，总工时从129人天增至139人天 | - |
| 2026-04-07 | 新增API测试执行器适配层(AD1-AD3)：执行器职责边界模糊、API结果与评估服务解耦、并发控制与API队列适配，共7人天工作量；新增API/E2E测试独立服务化(SVC1-SVC9)：服务拆分框架、进程管理、跨服务通信等，共21人天工作量，新增合计28人天 | - |
| 2026-04-07 | 新增PostgreSQL迁移工作量(PG1-PG8)：数据库迁移(9人天)+时区配置(6人天)，共15人天；修正A1用例增删功能为共用功能(C1)；新增APITest特有工作A1(异步和并发调用算法API,4人天)；总工时从167人天增至186人天 | - |
| 2026-04-07 | PostgreSQL迁移工作量从15人天调整为4人天；总工时从186人天降至175人天 | - |
