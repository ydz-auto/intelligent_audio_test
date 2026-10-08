# 前端模态窗使用情况总结

## 模态窗类型列表

### 全局注册模态窗

| 模态窗类型 | 组件文件 | 功能描述 |
| --- | --- | --- |
| TEST_CASE_RELATED | TestCaseModal.vue | 测试用例编辑/新增 |
| TEST_GROUP | TestCaseModal.vue | 测试用例组编辑/创建 |
| TEST_CASE_IMPORT | TestCaseModal.vue | 批量导入测试用例 |
| TEST_CASE_EXPORT | TestCaseModal.vue | 批量导出测试用例 |
| TEST_CASE_DETAIL | TestCaseDetailModal.vue | 测试用例详情查看 |
| ADD_TEST_CASE | AddTestCaseModal.vue | 添加测试用例 |
| BASIC_CONFIRM | ModalConfirm.vue | 基本确认操作对话框 |
| DELETE_CONFIRM | ModalConfirm.vue | 删除操作确认对话框 |
| DETAIL_VIEW | DetailViewModal.vue | 查看详情信息 |
| IMPORT_EXPORT | ImportExportModal.vue | 导入导出数据 |
| CRUD_FORM | CRUDFormModal.vue | 通用添加/编辑表单 |
| API_OTHER_CONFIG | APIEditModal.vue | API配置编辑 |
| UPLOAD_AUDIO_IMPORT | UploadFileModal.vue | 文件上传 |
| URL_IMPORT | URLImportModal.vue | URL导入 |
| FOLDER_IMPORT | FolderImportModal.vue | 文件夹导入 |
| AUDIO_IMPORT | UploadFileModal.vue | 音频上传 |
| AUDIO_PLAYER | AudioPlayerModal.vue | 音频播放器 |
| EDIT_METADATA | CRUDFormModal.vue | 元数据编辑 |
| SCAN_DEVICES | ScanDevicesModal.vue | 扫描设备 |
| SPL_CALIBRATION | SPLCalibrationModal.vue | 声压级校准 |
| GLOBAL_PLAYBACK_DEVICE | GlobalPlaybackDeviceModal.vue | 全局播放设备选择 |
| ADD_DEVICE | CRUDFormModal.vue | 添加设备 |
| EDIT_DEVICE | CRUDFormModal.vue | 编辑设备 |
| ADD_MAPPING | CRUDFormModal.vue | 添加映射 |
| EDIT_MAPPING | CRUDFormModal.vue | 编辑映射 |
| MAPPING_DETAILS | DetailViewModal.vue | 映射详情 |
| TASK_RELATED | TaskTypeModal.vue | 任务相关 |
| TASK_DETAIL | TaskDetailModal.vue | 任务详情 |
| TASK_COMPLETE | ModalConfirm.vue | 任务完成确认 |

### 可共用模态窗（已全局注册）

| 模态窗类型 | 组件文件 | 功能描述 | 适用页面 |
| --- | --- | --- | --- |
| API_OTHER_CONFIG | APIEditModal.vue | 新增和编辑API配置 | APITest、Device、Evaluation |
| DETAIL_VIEW | DetailViewModal.vue | 查看详情信息 | LogView、SPLMapping、Evaluation |
| IMPORT_EXPORT | ImportExportModal.vue | 导入导出数据 | LogView、Device、TestCase |
| CRUD_FORM | CRUDFormModal.vue | 通用添加/编辑表单 | SPLMapping、Device、Evaluation |
| UPLOAD_AUDIO_IMPORT | UploadFileModal.vue | 文件上传 | AudioImport、Device |
| URL_IMPORT | URLImportModal.vue | 通过URL导入数据 | AudioImport |
| FOLDER_IMPORT | FolderImportModal.vue | 通过文件夹导入数据 | AudioImport |
| SCAN_DEVICES | ScanDevicesModal.vue | 扫描系统中可用的设备 | Device |
| SPL_CALIBRATION | SPLCalibrationModal.vue | 声压级校准 | SPLMapping |

### 页面本地定义模态窗（页面特定，无需共用）

| 页面名称 | 模态窗名称 | 功能描述 | 备注 |
| --- | --- | --- | --- |
| LogView | 日志详情展开 | 查看日志详细信息 | 使用表格行内展开，无需模态窗 |
| AudioImport | 音频转换模态框 | 转换音频格式和参数 | 音频处理特定功能 |
| Evaluation | API健康测试结果模态框 | 显示API健康测试结果 | 评估特定功能 |

## 模态窗使用详情

### 1. 全局注册模态窗详情

#### 1.1 测试用例相关模态窗

**组件文件**：`src/components/common/test-case/TestCaseModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：
- 通过 `useModalControl()` 中的 `open()` 函数调用
- 使用对应的模态窗类型：`TEST_CASE_RELATED`、`TEST_GROUP`、`TEST_CASE_IMPORT`、`TEST_CASE_EXPORT`

**使用页面**：
- E2ETest.vue
- APITest.vue
- TestCaseManager.vue

#### 1.2 ADD_TEST_CASE 模态窗

**组件文件**：`src/components/AddTestCaseModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `ADD_TEST_CASE` 类型

**功能描述**：在测试执行过程中中途新增测试用例

**使用页面**：
- E2ETest.vue (第3步执行测试阶段)
- APITest.vue (第3步执行测试阶段)

#### 1.3 确认模态窗

**组件文件**：`src/composables/ModalConfirm.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `BASIC_CONFIRM` 或 `DELETE_CONFIRM` 类型

**使用页面**：
- 所有需要确认操作的页面

#### 1.4 详情查看模态窗

**组件文件**：`src/components/common/modal/DetailViewModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `DETAIL_VIEW` 类型

**功能描述**：查看各类数据的详细信息

**适用页面**：
- LogView（日志详情）
- SPLMapping（映射详情）
- Evaluation（维度详情）

#### 1.5 导入导出模态窗

**组件文件**：`src/components/common/modal/ImportExportModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `IMPORT_EXPORT` 类型

**功能描述**：导入或导出数据

**适用页面**：
- LogView（导出日志）
- Device（导入导出设备信息）
- TestCase（导入导出测试用例）
- Evaluation（导入维度）

#### 1.6 CRUD表单模态窗

**组件文件**：`src/components/common/modal/CRUDFormModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `CRUD_FORM` 类型

**功能描述**：通用添加/编辑表单

**适用页面**：
- SPLMapping（添加/编辑映射）
- Device（添加/编辑设备）
- Evaluation（添加/编辑维度、添加/编辑分类）

#### 1.7 API编辑模态窗

**组件文件**：`src/components/common/modal/APIEditModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `API_OTHER_CONFIG` 类型

**功能描述**：API配置编辑

**适用页面**：
- APITest（API配置）
- Device（测试设备管理）
- Evaluation（API设置）

#### 1.8 文件上传模态窗

**组件文件**：`src/components/common/modal/UploadFileModal.vue`

**注册位置**：`src/composables/modalRegistration.ts`

**调用方式**：通过 `useModalControl()` 中的 `open()` 函数调用，使用 `UPLOAD_AUDIO_IMPORT` 或 `AUDIO_IMPORT` 类型

**功能描述**：文件上传

**适用页面**：
- AudioImport（上传音频）
- Device（上传设备相关文件）

## 模态窗注册与管理

### 全局注册模态窗管理

全局注册的模态窗通过以下方式管理：
1. 在 `src/composables/modalRegistration.ts` 中通过 `registerGlobalModals()` 函数统一注册
2. 由 `useModal.ts` 中的模态窗管理器统一管理
3. 调用流程：
   - 各页面组件通过 `useModalControl()` 获取模态窗操作函数
   - 调用 `open()` 函数打开模态窗，传入模态窗类型和配置参数
   - 模态窗管理器处理模态窗的显示、隐藏和回调

### 模态窗注册代码示例

```typescript
// 在 src/composables/modalRegistration.ts 中
import { getModalManager } from './useModal';
import { MODAL_TYPES } from '../shared/types';
import TestCaseModal from '../components/common/test-case/TestCaseModal.vue';
// 导入其他模态窗组件...

export function registerGlobalModals() {
  const manager = getModalManager();
  
  const testCaseConfig = {
    component: TestCaseModal,
    defaultConfig: {
      isEditMode: false
    }
  };
  
  manager.registerModal(MODAL_TYPES.TEST_CASE_RELATED, testCaseConfig);
  manager.registerModal(MODAL_TYPES.TEST_GROUP, testCaseConfig);
  // 注册其他模态窗...
}
```

### 模态窗调用代码示例

```typescript
// 在页面组件中
import { useModalControl } from '../../composables/useModal';
import { MODAL_TYPES } from '../../shared/types';

const modalManager = useModalControl();

// 打开确认模态窗
modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
  title: '确认操作',
  message: '确定要执行此操作吗？',
  confirmText: '确定',
  cancelText: '取消',
  onConfirm: async () => {
    // 确认操作逻辑
  }
});

// 打开导入导出模态窗
modalManager.open(MODAL_TYPES.IMPORT_EXPORT, {
  mode: 'export',
  title: '导出日志',
  // 其他配置...
});
```

## 模态窗配置

### 全局注册模态窗配置

| 模态窗类型 | 默认配置 |
| --- | --- |
| TEST_CASE_RELATED | `{ isEditMode: false }` |
| TEST_GROUP | `{ isEditMode: false }` |
| TEST_CASE_IMPORT | `{ isEditMode: false }` |
| TEST_CASE_EXPORT | `{ isEditMode: false }` |
| TEST_CASE_DETAIL | `{ title: '测试用例详情' }` |
| ADD_TEST_CASE | `{}` |
| BASIC_CONFIRM | `{ title: '确认操作', content: '确定要执行此操作吗？', confirmText: '确定', cancelText: '取消', danger: false }` |
| DELETE_CONFIRM | `{ title: '删除确认', content: '确定要执行此操作吗？', confirmText: '确定', cancelText: '取消', danger: true }` |
| DETAIL_VIEW | `{}` |
| IMPORT_EXPORT | `{ mode: 'import' }` |
| CRUD_FORM | `{ mode: 'create', entityName: '数据' }` |
| API_OTHER_CONFIG | `{ mode: 'create' }` |
| UPLOAD_AUDIO_IMPORT | `{ multiple: false }` |
| URL_IMPORT | `{}` |
| FOLDER_IMPORT | `{}` |
| AUDIO_IMPORT | `{ title: '上传音频', multiple: true, acceptedFileTypes: 'audio/*', supportedFormats: ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg'] }` |
| AUDIO_PLAYER | `{ title: '音频播放' }` |
| EDIT_METADATA | `{ mode: 'edit', entityName: '元数据' }` |
| SCAN_DEVICES | `{ deviceType: 'test' }` |
| SPL_CALIBRATION | `{ title: '声压级(SPL)校准' }` |
| GLOBAL_PLAYBACK_DEVICE | `{ title: '选择播放设备' }` |
| ADD_DEVICE | `{ mode: 'create', entityName: '设备' }` |
| EDIT_DEVICE | `{ mode: 'edit', entityName: '设备' }` |
| ADD_MAPPING | `{ mode: 'create', entityName: '声压级映射' }` |
| EDIT_MAPPING | `{ mode: 'edit', entityName: '声压级映射' }` |
| MAPPING_DETAILS | `{ title: '声压级映射详情' }` |
| TASK_RELATED | `{}` |
| TASK_DETAIL | `{ title: '任务详情', width: '1200px', maxWidth: '90vw' }` |
| TASK_COMPLETE | `{ title: '测试完成', content: '测试任务已完成', confirmText: '确定', cancelText: '取消', danger: false }` |

## 模态窗优化建议

1. **统一模态窗样式**：所有模态窗已使用统一的样式规范，包括颜色、字体、间距、阴影效果等，提升用户体验一致性。

2. **优化模态窗性能**：
   - 所有常用模态窗已全局注册并预加载
   - 模态窗管理器使用单例模式，确保性能优化
   - 关闭模态窗时及时清理资源，避免内存泄漏

3. **增强模态窗可访问性**：
   - 支持键盘操作
   - 提供清晰的视觉反馈
   - 支持屏幕阅读器

4. **改进模态窗交互体验**：
   - 添加加载状态指示
   - 提供明确的操作反馈
   - 支持自定义配置选项

5. **完善模态窗文档**：
   - 本文档已详细记录所有模态窗的使用方式
   - 提供了模态窗注册和调用的代码示例
   - 说明了各模态窗的适用场景和配置选项

6. **建立模态窗设计系统**：
   - 定义了统一的模态窗设计规范
   - 提供了可视化的配置选项
   - 支持主题定制

通过以上优化，模态窗的复用性、可维护性和用户体验得到了显著提升，减少了重复开发工作，提高了开发效率。