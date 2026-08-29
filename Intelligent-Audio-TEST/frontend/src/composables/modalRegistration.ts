import { getModalManager } from './useModal';
import { MODAL_TYPES } from '../shared/types';
import TestCaseModal from '../components/common/test-case/TestCaseModal/index.vue';
import AddTestCaseModal from '../components/common/test-case/AddTestCaseModal.vue';
import ModalConfirm from '../components/common/modal/ModalConfirm.vue';
import APIEditModal from '../components/common/modal/APIEditModal.vue';
import DetailViewModal from '../components/common/modal/DetailViewModal.vue';
import ImportExportModal from '../components/common/modal/ImportExportModal.vue';
import CRUDFormModal from '../components/common/modal/CRUDFormModal.vue';
import UploadFileModal from '../components/common/modal/UploadFileModal.vue';
import URLImportModal from '../components/common/modal/URLImportModal.vue';
import FolderImportModal from '../components/common/modal/FolderImportModal.vue';
import ScanDevicesModal from '../components/common/modal/ScanDevicesModal.vue';
import SPLCalibrationModal from '../components/common/modal/SPLCalibrationModal.vue';
import GlobalPlaybackDeviceModal from '../components/common/modal/GlobalPlaybackDeviceModal.vue';
import BatchAlgorithmParamsModal from '../components/common/modal/BatchAlgorithmParamsModal.vue';
import BatchSPLModal from '../components/common/modal/BatchSPLModal.vue';
import BatchPlaybackDeviceModal from '../components/common/modal/BatchPlaybackDeviceModal.vue';
import BatchAdjustGroupModal from '../components/common/modal/BatchAdjustGroupModal.vue';
import BatchDimensionModal from '../components/common/modal/BatchDimensionModal.vue';
import BatchNoiseModal from '../components/common/modal/BatchNoiseModal.vue';
import BatchTagsModal from '../components/common/modal/BatchTagsModal.vue';
import BatchRefreshReferenceModal from '../components/common/modal/BatchRefreshReferenceModal.vue';
import TagCategoryModal from '../components/common/modal/TagCategoryModal.vue';
import TagEditModal from '../components/common/modal/TagEditModal.vue';
import TestCaseDetailModal from '../components/common/modal/TestCaseDetailModal.vue';
import AudioPlayerModal from '../components/common/AudioPlayerModal.vue';
import AudioSelectModal from '../components/common/AudioSelectModal.vue';
import TaskTypeModal from '../views/TasksLogic/TaskTypeModal.vue';
import TaskDetailModal from '../views/TasksLogic/TaskDetailModal.vue';
import ReevaluateSelectModal from '../components/common/modal/ReevaluateSelectModal.vue';

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
    defaultConfig: { title: '测试用例详情', width: '1200px', maxWidth: '95vw', maxHeight: '90vh' }
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
