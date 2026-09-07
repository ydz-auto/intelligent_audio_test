/**
 * 全局弹窗注册表 —— Presentation 层（组合根）
 *
 * 注册属于「组件装配」职责：将 Presentation 组件接入 Application 层的
 * ModalManager 注册表。依赖方向为 Presentation → Application，合法。
 * Application（composables/）禁止反向依赖组件，故本文件不得迁回 composables/。
 */
import { getModalManager } from '../../../composables/modal/useModal'
import { MODAL_TYPES } from '../../../composables/modal/constants'
import TestCaseModal from '../test-case/TestCaseModal/index.vue'
import AddTestCaseModal from '../test-case/AddTestCaseModal.vue'
import ModalConfirm from './ModalConfirm.vue'
import APIEditModal from './APIEditModal.vue'
import DetailViewModal from './DetailViewModal.vue'
import ImportExportModal from './ImportExportModal.vue'
import CRUDFormModal from './CRUDFormModal.vue'
import UploadFileModal from './UploadFileModal.vue'
import URLImportModal from './URLImportModal.vue'
import FolderImportModal from './FolderImportModal.vue'
import ScanDevicesModal from './ScanDevicesModal.vue'
import SPLCalibrationModal from './SPLCalibrationModal.vue'
import GlobalPlaybackDeviceModal from './GlobalPlaybackDeviceModal.vue'
import BatchAlgorithmParamsModal from './BatchAlgorithmParamsModal.vue'
import BatchSPLModal from './BatchSPLModal.vue'
import BatchPlaybackDeviceModal from './BatchPlaybackDeviceModal.vue'
import BatchAdjustGroupModal from './BatchAdjustGroupModal.vue'
import BatchDimensionModal from './BatchDimensionModal.vue'
import BatchNoiseModal from './BatchNoiseModal.vue'
import BatchTagsModal from './BatchTagsModal.vue'
import BatchRefreshReferenceModal from './BatchRefreshReferenceModal.vue'
import TagCategoryModal from './TagCategoryModal.vue'
import TagEditModal from './TagEditModal.vue'
import TestCaseDetailModal from './TestCaseDetailModal.vue'
import AudioPlayerModal from '../audio/AudioPlayerModal.vue'
import AudioSelectModal from '../audio/AudioSelectModal.vue'
import TaskTypeModal from './TaskTypeModal.vue'
import TaskDetailModal from './TaskDetailModal.vue'
import ReevaluateSelectModal from './ReevaluateSelectModal.vue'

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
  manager.registerModal(MODAL_TYPES.TEST_CASE_IMPORT, testCaseConfig);
  manager.registerModal(MODAL_TYPES.TEST_CASE_EXPORT, testCaseConfig);

  manager.registerModal(MODAL_TYPES.TEST_CASE_DETAIL, {
    component: TestCaseDetailModal,
    defaultConfig: { title: '测试用例详情' }
  });

  manager.registerModal(MODAL_TYPES.ADD_TEST_CASE, {
    component: AddTestCaseModal,
    defaultConfig: {}
  });

  const confirmConfig = {
    component: ModalConfirm,
    defaultConfig: {
      title: '确认操作',
      content: '确定要执行此操作吗？',
      confirmText: '确定',
      cancelText: '取消',
      danger: false
    }
  };

  manager.registerModal(MODAL_TYPES.BASIC_CONFIRM, confirmConfig);
  manager.registerModal(MODAL_TYPES.DELETE_CONFIRM, {
    ...confirmConfig,
    defaultConfig: { ...confirmConfig.defaultConfig, title: '删除确认', danger: true }
  });

  manager.registerModal(MODAL_TYPES.API_OTHER_CONFIG, {
    component: APIEditModal,
    defaultConfig: { mode: 'create' }
  });

  manager.registerModal(MODAL_TYPES.DETAIL_VIEW, {
    component: DetailViewModal,
    defaultConfig: {}
  });

  manager.registerModal(MODAL_TYPES.IMPORT_EXPORT, {
    component: ImportExportModal,
    defaultConfig: { mode: 'import' }
  });

  manager.registerModal(MODAL_TYPES.CRUD_FORM, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'create', entityName: '数据' }
  });

  manager.registerModal(MODAL_TYPES.UPLOAD_AUDIO_IMPORT, {
    component: UploadFileModal,
    defaultConfig: { multiple: false }
  });

  manager.registerModal(MODAL_TYPES.URL_IMPORT, {
    component: URLImportModal,
    defaultConfig: {}
  });

  manager.registerModal(MODAL_TYPES.FOLDER_IMPORT, {
    component: FolderImportModal,
    defaultConfig: {}
  });

  manager.registerModal(MODAL_TYPES.SCAN_DEVICES, {
    component: ScanDevicesModal,
    defaultConfig: { deviceType: 'test' }
  });

  manager.registerModal(MODAL_TYPES.TASK_RELATED, {
    component: TaskTypeModal,
    defaultConfig: {}
  });

  manager.registerModal(MODAL_TYPES.TASK_DETAIL, {
    component: TaskDetailModal,
    defaultConfig: {
      title: '任务详情',
      width: '1200px',
      maxWidth: '90vw'
    }
  });

  manager.registerModal(MODAL_TYPES.AUDIO_IMPORT, {
    component: UploadFileModal,
    defaultConfig: { title: '上传音频', multiple: true, acceptedFileTypes: 'audio/*', supportedFormats: ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg'] }
  });

  manager.registerModal(MODAL_TYPES.EDIT_METADATA, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'edit', entityName: '元数据' }
  });

  manager.registerModal(MODAL_TYPES.SPL_CALIBRATION, {
    component: SPLCalibrationModal,
    defaultConfig: { title: '声压级(SPL)校准' }
  });

  manager.registerModal(MODAL_TYPES.ADD_MAPPING, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'create', entityName: '声压级映射' }
  });

  manager.registerModal(MODAL_TYPES.EDIT_MAPPING, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'edit', entityName: '声压级映射' }
  });

  manager.registerModal(MODAL_TYPES.MAPPING_DETAILS, {
    component: DetailViewModal,
    defaultConfig: { title: '声压级映射详情' }
  });

  manager.registerModal(MODAL_TYPES.ADD_DEVICE, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'create', entityName: '设备' }
  });

  manager.registerModal(MODAL_TYPES.EDIT_DEVICE, {
    component: CRUDFormModal,
    defaultConfig: { mode: 'edit', entityName: '设备' }
  });

  manager.registerModal(MODAL_TYPES.GLOBAL_PLAYBACK_DEVICE, {
    component: GlobalPlaybackDeviceModal,
    defaultConfig: { title: '选择播放设备' }
  });

  manager.registerModal(MODAL_TYPES.AUDIO_PLAYER, {
    component: AudioPlayerModal,
    defaultConfig: { title: '音频播放' }
  });

  manager.registerModal(MODAL_TYPES.AUDIO_SELECT, {
    component: AudioSelectModal,
    defaultConfig: { title: '选择音频' }
  });

  manager.registerModal(MODAL_TYPES.TASK_COMPLETE, {
    component: ModalConfirm,
    defaultConfig: {
      title: '测试完成',
      content: '测试任务已完成',
      confirmText: '确定',
      cancelText: '取消',
      danger: false
    }
  });

  manager.registerModal(MODAL_TYPES.REEVALUATE, {
    component: ReevaluateSelectModal,
    defaultConfig: {
      content: '请选择重新评估类型'
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_ALGORITHM_PARAMS, {
    component: BatchAlgorithmParamsModal,
    defaultConfig: {
      title: '批量设置用例专属参数',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_SPL, {
    component: BatchSPLModal,
    defaultConfig: {
      title: '批量设置声压级',
      caseCount: 0,
      initialValue: 65
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_PLAYBACK_DEVICE, {
    component: BatchPlaybackDeviceModal,
    defaultConfig: {
      title: '批量设置播放设备',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_ADJUST_GROUP, {
    component: BatchAdjustGroupModal,
    defaultConfig: {
      title: '批量调整分组',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_DIMENSION, {
    component: BatchDimensionModal,
    defaultConfig: {
      title: '批量设置评价维度',
      caseCount: 0,
      width: '90%',
      maxWidth: '800px'
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_NOISE, {
    component: BatchNoiseModal,
    defaultConfig: {
      title: '批量设置噪声',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_TAGS, {
    component: BatchTagsModal,
    defaultConfig: {
      title: '批量管理标签',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.BATCH_REFRESH_REFERENCE, {
    component: BatchRefreshReferenceModal,
    defaultConfig: {
      title: '用例参考更新',
      caseCount: 0
    }
  });

  manager.registerModal(MODAL_TYPES.TAG_CATEGORY, {
    component: TagCategoryModal,
    defaultConfig: {
      title: '标签分类'
    }
  });

  manager.registerModal(MODAL_TYPES.TAG_EDIT, {
    component: TagEditModal,
    defaultConfig: {
      title: '标签'
    }
  });
}
