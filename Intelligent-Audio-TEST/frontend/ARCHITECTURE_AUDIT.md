# 前端架构诊断报告

> 生成时间:2026-07-29 | 最后更新:2026-07-29
> 范围:`frontend/src/`
> 
> ## 执行进度
> - [x] Step 1: CSS 归并 — 根 css 合入子目录,main.css 统一聚合,修大小写 bug,构建通过
> - [x] Step 2: components/common 平铺 — 12 个组件归入 audio/data/misc,4 个根组件归入 task/layout,50 处 import 更新,构建通过
> - [x] Step 3: views/ 改为 view+logic 子目录结构 — 12 个 view 子目录化,router + 跨文件引用更新,构建通过
> - [x] Step 4: composables/ 按域分组 — 49 个文件归入 11 个域子目录,删除 3 个死代码,91 处外部引用 + 48 处内部引用 + 100 处相对路径全部更新,构建通过

## 一、当前目录结构(简化)

```
src/
├── assets/
│   └── styles/                    ❌ 12 个根 css + 6 个子目录并存,语义重复
│       ├── api-test.css           47.5KB  ← 和 api-test/ 子目录并存
│       ├── APITest.css             9.8KB  ← 和上面 api-test.css 命名混淆
│       ├── TestCaseManager.css   23.4KB  ← 和 test-case-manager/ 子目录并存
│       ├── e2etest.css            10.4KB  ← 和 e2etest/ 子目录并存
│       ├── device.css / device-card.css / reports.css / SPLMapping.css
│       ├── main.css / reset.css / variables.css / test-common.css
│       ├── api-test/              6 个 css
│       ├── components/           14 个 css
│       ├── e2etest/              9 个 css
│       ├── tasks/                5 个 css
│       ├── test-case-manager/     4 个 css
│       ├── reports/               1 个 css
│       └── layouts/               1 个 css
├── chart/                        ✅ 自治模块,结构清晰
├── components/
│   ├── algorithm/                 ✅ 已分组
│   ├── common/
│   │   ├── form/                  ✅ 已分组
│   │   ├── modal/                 ✅ 已分组(30 个)
│   │   ├── test-case/             ✅ 已分组
│   │   ├── AlgorithmSelector.vue  ❌ 以下 12 个平铺在 common/ 根
│   │   ├── AudioListComponent.vue
│   │   ├── AudioPlayerModal.vue
│   │   ├── AudioSelectModal.vue
│   │   ├── AudioTimelineVisualization.vue
│   │   ├── DataTable.vue
│   │   ├── FolderNodeComponent.vue
│   │   ├── PaginationComponent.vue
│   │   ├── ResourceSelectionGrid.vue
│   │   ├── TestCaseReportDetail.vue
│   │   ├── TestStepContainer.vue
│   │   ├── UploadOptions.vue
│   │   └── UploadProgressCard.vue
│   ├── report/                    ✅ 已分组
│   ├── ProgressNav.vue           ❌ 4 个未分组,平铺在 components/ 根
│   ├── TaskCard.vue
│   ├── TaskListWithPagination.vue
│   └── TestExecutionComponent.vue
├── composables/                  ❌ 52 个 .ts 全平铺一层
│   ├── index.ts                   barrel,但只导出 7 个符号(覆盖率 13%)
│   ├── modalIndex.ts
│   ├── modalRegistration.ts
│   ├── useDeviceManagement.ts
│   ├── useDeviceScanning.ts
│   ├── useDeviceSelection.ts
│   ├── useAudioList.ts
│   ├── ... (共 52 个)
│   └── __tests__/
├── constants/
│   └── annotation.ts
├── preload/
│   └── apiadapter.ts
├── router/
│   └── index.ts
├── services/
│   └── reportService.ts
├── shared/
│   ├── constants/
│   └── types/
├── store/
│   ├── index.ts
│   ├── modalStore.ts
│   ├── testCaseGroupStore.ts
│   └── testCaseStore.ts
├── utils/
│   ├── api/                       ✅ 已拆分到子模块
│   ├── api.ts                     ❌ 旧版聚合文件,和 api/ 子目录并存
│   ├── audioUtils.ts
│   ├── ... (共 13 个)
│   └── utils.ts
└── views/                        ❌ 14 个 .vue + 9 个 Logic/ 混在一层
    ├── APITest.vue / APITestLogic/apiTest.ts
    ├── AudioImport.vue / AudioImportLogic/audioImport.ts
    ├── Device.vue / DeviceLogic/device.ts
    ├── Evaluation.vue / EvaluationLogic/evaluation.ts
    ├── E2ETest.vue / (无 Logic/)
    ├── Tasks.vue / TasksLogic/tasks.ts
    ├── TestCaseManager.vue / TestCaseManagerLogic/testCaseManager.ts
    ├── HistoryReports.vue / HistoryReportsLogic/historyReports.ts
    ├── LogView.vue / LogViewLogic/logView.ts
    ├── TestReports.vue / TestReportsLogic/testReports.ts
    ├── SPLMapping.vue / splMapping/SPLMapping.ts
    ├── AlgorithmConfigPage.vue / (无 Logic/)
    ├── Home.vue / ReportView.vue / TagManagement.vue
    └── TasksLogic/TaskDetailModal.vue / TaskTypeModal.vue  ← .vue 放进了 Logic/
```

## 二、核心问题诊断

### 问题 1:CSS 语义重复与路径混乱(影响:样式加载/维护)

| 问题 | 详情 |
|------|------|
| 根 css 与子目录并存 | `api-test.css` 与 `api-test/`、`e2etest.css` 与 `e2etest/`、`TestCaseManager.css` 与 `test-case-manager/` 同时存在,命名暗示同一域但内容不同 |
| 大小写命名混淆 | `APITest.css` vs `api-test.css` vs `apiTest.css`(APITest.vue:515 引用了不存在的 `apiTest.css`,实际文件是 `APITest.css`) |
| main.css 聚合不完整 | main.css 只 @import 了子目录文件和部分根 css,`api-test.css`/`APITest.css`/`TestCaseManager.css`/`e2etest.css`/`reports.css` 等大文件未被聚合,而是被各 .vue 单独 @import |
| 引用路径不统一 | 17 处引用中,大部分用相对路径 `../assets/styles/main.css`,少数用别名 `@/assets/styles/...` |

### 问题 2:composables/ 52 文件平铺(影响:可维护性)

- 全部 52 个 .ts 平铺一层,无功能域分组
- `index.ts` barrel 只导出 7 个符号(覆盖率 13%),消费方直接 `from './useXxx'` 相对引用
- 移动文件需同步改 200+ 处消费方 import 路径
- 跨域依赖集中:`useE2eView` 依赖 9 个其他 composable,`useModal` 被 6 个域依赖

### 问题 3:components/common/ 平铺(影响:组件查找)

- `common/` 下 12 个 .vue 平铺,与已有的 `form/`/`modal/`/`test-case/` 子目录混放
- `components/` 根下 4 个未分组(.ProgressNav/TaskCard/TaskListWithPagination/TestExecutionComponent)
- 命名后缀不统一:`AudioListComponent.vue` vs `AudioListStep.vue`(一个有 Component 后缀一个没有)

### 问题 4:views/ 与 Logic/ 结构不统一(影响:一致性)

- 9 个 `XxxLogic/` 子目录各自只含 1-2 个 .ts,有的 Logic 里还放 .vue(TasksLogic/TaskDetailModal.vue)
- 3 个 view 无对应 Logic(E2ETest/AlgorithmConfigPage/Home)
- view 与 logic 的 style 引用混在 .vue 的 `<style>` 块里用相对 @import

## 三、推荐的目标架构

```
src/
├── assets/
│   └── styles/                    按域聚合,根目录只留 main.css 入口
│       ├── main.css               唯一入口,@import 所有子文件
│       ├── reset.css
│       ├── variables.css
│       ├── test-common.css
│       ├── device/
│       │   ├── device.css
│       │   └── device-card.css
│       ├── audio-import/
│       │   └── audio-import.css
│       ├── api-test/
│       │   ├── api-test.css       合并根目录的 api-test.css + APITest.css
│       │   ├── api-card.css
│       │   ├── radio.css
│       │   ├── step-panel.css
│       │   ├── tag-stats.css
│       │   ├── toolbar.css
│       │   └── visualization.css
│       ├── e2etest/
│       │   ├── e2etest.css        合并根目录的 e2etest.css
│       │   ├── alert.css
│       │   ├── audio.css
│       │   ├── case.css
│       │   ├── checkbox.css
│       │   ├── dropdown.css
│       │   ├── layout.css
│       │   ├── progress.css
│       │   ├── tabs.css
│       │   └── visualization.css
│       ├── tasks/
│       │   └── (现有 5 个)
│       ├── test-case-manager/
│       │   ├── test-case-manager.css  合并根目录的 TestCaseManager.css
│       │   ├── base.css
│       │   ├── case.css
│       │   ├── category.css
│       │   └── toolbar.css
│       ├── reports/
│       │   ├── reports.css        合并根目录的 reports.css
│       │   └── base.css
│       ├── spl-mapping/
│       │   └── spl-mapping.css
│       ├── components/            通用组件样式(现有 14 个)
│       └── layouts/
│           └── main.css
│
├── chart/                         保持不变
│
├── components/
│   ├── algorithm/                 保持不变
│   ├── common/
│   │   ├── form/                  保持不变
│   │   ├── modal/                 保持不变
│   │   ├── test-case/             保持不变
│   │   ├── audio/                 ← 新建,归入 Audio* 组件
│   │   │   ├── AudioListComponent.vue
│   │   │   ├── AudioPlayerModal.vue
│   │   │   ├── AudioSelectModal.vue
│   │   │   └── AudioTimelineVisualization.vue
│   │   ├── data/                  ← 新建
│   │   │   ├── DataTable.vue
│   │   │   ├── PaginationComponent.vue
│   │   │   └── ResourceSelectionGrid.vue
│   │   └── misc/                  ← 新建,归入其余
│   │       ├── FolderNodeComponent.vue
│   │       ├── TestCaseReportDetail.vue
│   │       ├── TestStepContainer.vue
│   │       ├── UploadOptions.vue
│   │       └── UploadProgressCard.vue
│   ├── report/                    保持不变
│   ├── task/                      ← 新建
│   │   ├── TaskCard.vue
│   │   └── TaskListWithPagination.vue
│   └── layout/                   ← 新建
│       ├── ProgressNav.vue
│       └── TestExecutionComponent.vue
│
├── composables/                   按功能域分组
│   ├── index.ts                   补全 barrel,从各域 re-export
│   ├── device/
│   │   ├── useDeviceManagement.ts
│   │   ├── useDeviceScanning.ts
│   │   └── useDeviceSelection.ts
│   ├── audio/
│   │   ├── useAudioList.ts
│   │   ├── useAudioBatchOps.ts
│   │   └── useAudioUpload.ts
│   ├── evaluation/
│   │   ├── useEvaluationDimensions.ts   ← 域内核心
│   │   ├── useEvaluationCategories.ts
│   │   ├── useEvaluationBatchOps.ts
│   │   ├── useEvaluationImport.ts
│   │   └── useEvaluationModals.ts
│   ├── task/
│   │   ├── useTaskList.ts
│   │   ├── useTaskControl.ts
│   │   ├── useTaskBatchOps.ts
│   │   ├── useTaskLogs.ts
│   │   ├── useTaskCharts.ts
│   │   ├── useTaskReport.ts
│   │   └── useTaskProgress.ts
│   ├── testCase/
│   │   ├── useTestCaseCard.ts          ← 域内核心
│   │   ├── useTestCaseConfig.ts
│   │   ├── useTestCaseFilters.ts
│   │   ├── useTestCaseGroups.ts
│   │   ├── useTestCaseGroupExpand.ts
│   │   ├── useTestCaseImport.ts
│   │   ├── useTestCaseBatchActions.ts
│   │   ├── useTestCaseBatchOps.ts
│   │   ├── useTestCaseManagement.ts
│   │   └── useTestCaseAudioPreview.ts
│   ├── algorithm/
│   │   ├── useAlgorithmConfig.ts
│   │   ├── useAlgorithmLabels.ts
│   │   ├── useAlgorithmParams.ts
│   │   └── useAlgorithmSelection.ts
│   ├── modal/
│   │   ├── useModal.ts                 ← 全局枢纽,被 6 个域依赖
│   │   ├── useDeleteConfirm.ts
│   │   ├── useFormValidation.ts
│   │   ├── useNotification.ts
│   │   └── modalRegistration.ts
│   ├── e2e/
│   │   ├── useE2eTest.ts
│   │   └── useE2eView.ts               ← 跨域聚合点,依赖 9 个 composable
│   ├── apiTest/
│   │   └── useApiTest.ts
│   ├── upload/
│   │   ├── useUploadModal.ts
│   │   └── useUploadState.ts
│   └── shared/
│       ├── useDimensions.ts
│       ├── useFolderSelection.ts
│       ├── useFolderTree.ts
│       ├── useReportFilters.ts
│       ├── useTagFilter.ts
│       ├── useTestBase.ts
│       ├── useTestControl.ts
│       └── useTestReport.ts
│
├── shared/                        保持不变
├── store/                         保持不变
├── router/                        保持不变
├── services/                      保持不变
├── utils/                         保持不变(api.ts 确认是否旧聚合文件后删除)
│
└── views/                         每个 view 带 Logic + style
    ├── APITest/
    │   ├── APITest.vue
    │   └── apiTest.ts
    ├── AudioImport/
    │   ├── AudioImport.vue
    │   └── audioImport.ts
    ├── Device/
    │   ├── Device.vue
    │   └── device.ts
    ├── Evaluation/
    │   ├── Evaluation.vue
    │   └── evaluation.ts
    ├── E2ETest/
    │   ├── E2ETest.vue
    │   └── e2eTest.ts            ← 新建 Logic(如果需要)
    ├── Tasks/
    │   ├── Tasks.vue
    │   ├── tasks.ts
    │   ├── TaskDetailModal.vue   ← 从 TasksLogic/ 移入
    │   └── TaskTypeModal.vue
    ├── TestCaseManager/
    │   ├── TestCaseManager.vue
    │   └── testCaseManager.ts
    ├── HistoryReports/
    │   ├── HistoryReports.vue
    │   └── historyReports.ts
    ├── LogView/
    │   ├── LogView.vue
    │   └── logView.ts
    ├── TestReports/
    │   ├── TestReports.vue
    │   └── testReports.ts
    ├── SPLMapping/
    │   ├── SPLMapping.vue
    │   └── SPLMapping.ts
    ├── AlgorithmConfigPage.vue    简单页可不建子目录
    ├── Home.vue
    └── ReportView.vue
```

## 四、整理执行顺序(风险从低到高)

| 步骤 | 内容 | 风险 | 备注 |
|------|------|------|------|
| 1 | CSS 归并:根 css 合入对应子目录,统一 @/ 别名,修 apiTest.css 大小写 bug | 低 | 不影响 JS 逻辑,只动样式引用 |
| 2 | components/common 平铺归入 audio/data/misc 子目录 | 低 | 只动 import 路径 |
| 3 | views/ 改为 view+logic 子目录结构 | 中 | 路由配置需同步改 |
| 4 | composables/ 按域分组 + 补全 barrel | 高 | 200+ 处 import 路径需改,建议脚本批量处理 |

## 五、跨域依赖关键文件(迁移时最需小心)

| 文件 | 依赖数 | 被谁依赖 |
|------|--------|----------|
| `useModal.ts` | — | device/task/testCase/evaluation/e2e/apiTest 6 个域 |
| `useE2eView.ts` | 依赖 9 个 composable | E2ETest.vue |
| `useTestCaseCard.ts` | — | useTestCaseManagement/useApiTest/useE2eTest |
| `useUploadModal.ts` | 跨 device/algorithm/audio 3 域 | UploadFileModal |
