/**
 * Modal 类型常量 —— Application 层
 *
 * 所有弹窗类型的唯一来源，禁止在组件中硬编码弹窗类型字符串。
 */

export const MODAL_TYPES = {
  BASIC_CONFIRM: 'basicConfirm',
  DELETE_CONFIRM: 'deleteConfirm',
  // INT-286：单字段表单输入确认模态（替代业务侧 window.prompt 收集输入）
  INPUT_CONFIRM: 'inputConfirm',
  DETAIL_VIEW: 'detailView',
  IMPORT_EXPORT: 'importExport',
  CRUD_FORM: 'crudForm',
  TEST_CASE_RELATED: 'testCase',
  TEST_GROUP: 'testGroup',
  TEST_CASE_IMPORT: 'testCaseImport',
  TEST_CASE_EXPORT: 'testCaseExport',
  ADD_TEST_CASE: 'addTestCase',
  TEST_CASE_DETAIL: 'testCaseDetail',
  UPLOAD_AUDIO_IMPORT: 'uploadFile',
  URL_IMPORT: 'urlImport',
  FOLDER_IMPORT: 'folderImport',
  AUDIO_IMPORT: 'audioImport',
  AUDIO_DETAIL: 'audioDetail',
  AUDIO_PLAYER: 'audioPlayer',
  AUDIO_SELECT: 'audioSelect',
  EDIT_METADATA: 'editMetadata',
  SCAN_DEVICES: 'scanDevices',
  SPL_CALIBRATION: 'splCalibration',
  API_RMS_SPL_CALIBRATION: 'apiRmsSplCalibration',
  GLOBAL_PLAYBACK_DEVICE: 'globalPlaybackDevice',
  ADD_DEVICE: 'addDevice',
  EDIT_DEVICE: 'editDevice',
  ADD_MAPPING: 'addMapping',
  EDIT_MAPPING: 'editMapping',
  MAPPING_DETAILS: 'mappingDetails',
  TASK_RELATED: 'taskTypeSelect',
  TASK_DETAIL: 'taskDetail',
  TASK_CONFIG: 'taskConfig',
  REPORT_DETAIL: 'reportDetail',
  API_OTHER_CONFIG: 'apiEdit',
  API_HEALTH: 'apiHealth',
  DIMENSION_EDIT: 'dimensionEdit',
  BATCH_EDIT: 'batchEdit',
  CASE_SELECT: 'caseSelect',
  GROUP_MANAGE: 'groupManage',
  TASK_COMPLETE: 'taskComplete',
  // INT-302/F4：REEVALUATE 类型选择模态窗由 REEXECUTE_OPTIONS 范围选择取代，常量一并移除
  REEXECUTE_OPTIONS: 'reexecuteOptions',
  BATCH_ALGORITHM_PARAMS: 'batchAlgorithmParams',
  BATCH_SPL: 'batchSPL',
  BATCH_PLAYBACK_DEVICE: 'batchPlaybackDevice',
  BATCH_ADJUST_GROUP: 'batchAdjustGroup',
  BATCH_DIMENSION: 'batchDimension',
  BATCH_NOISE: 'batchNoise',
  BATCH_TAGS: 'batchTags',
  BATCH_REFRESH_REFERENCE: 'batchRefreshReference',
  TAG_CATEGORY: 'tagCategory',
  TAG_EDIT: 'tagEdit',
  /** INT-340：测试结果人工复核（单条/批量改判 + 备注必填 + 复核历史展示） */
  RESULT_REVIEW: 'resultReview'
} as const

export type ModalTypeKey = keyof typeof MODAL_TYPES
