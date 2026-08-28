export { ErrorCode } from './errorCode';
export type { APIResponse, PaginatedData } from './errorCode';

// Algorithm-related shared types
export type {
  AlgorithmDefinition,
  AlgorithmParam,
  AlgorithmGroup,
  ParamMapping,
  FormSchema,
  FormField,
  TagCategory,
  TagItem
} from './algorithmTypes';

// rounds-as-top-level 架构核心类型 re-export
export type {
  AlgorithmParamItem,
  AudioConfig,
  DimensionConfig,
  BackgroundNoiseConfig,
  RoundEvaluationConfig,
  VoiceprintConfig,
  InterfererConfigItem,
  InterruptionConfig,
  RoundConfigItem,
  RoundAlgorithmParams,
  RoundReferenceParams,
  TestCaseConfig,
} from '../../components/common/test-case/TestCaseModal/types';

export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    page: number;
    perPage: number;
    pages: number;
}

export type { 
  TaskType, TaskStatus, Task, AudioInfo, Audio, AudioUploadFile, AudioUploadTask, 
  AudioUploadOptions, Tag, TestCase, APIConfig, PlaybackDevice, Dimension, 
  EvaluationCategory, DimensionAPIEndpoint, EvaluationDimension, Report, 
  ComparisonDevice, DeviceAPIComparisonItem, CaseExecutionItem, Device, 
  ReportListParams, ReportSummary, DetailedResult, CompareResult, Log, 
  LogFilters, AdvancedLogFilters, LogStats, LogQueryParams, LogLevelOption, 
  APIHealthResult, APIEndpointHealthResult, APISettings, APIHealthResultModalData, 
  TestCaseGroup, CalibrationPoint, CalibrationData, SPLMapping, SPLQueryParams, 
  PaginationInfo, StatItem
} from './businessTypes';

export const MODAL_TYPES = {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
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
    REEVALUATE: 'reevaluate',
    BATCH_ALGORITHM_PARAMS: 'batchAlgorithmParams',
    BATCH_SPL: 'batchSPL',
    BATCH_PLAYBACK_DEVICE: 'batchPlaybackDevice',
    BATCH_ADJUST_GROUP: 'batchAdjustGroup',
    BATCH_DIMENSION: 'batchDimension',
    BATCH_NOISE: 'batchNoise',
    BATCH_TAGS: 'batchTags',
    BATCH_REFRESH_REFERENCE: 'batchRefreshReference',
    TAG_CATEGORY: 'tagCategory',
    TAG_EDIT: 'tagEdit'
} as const;

export type ModalType = typeof MODAL_TYPES[keyof typeof MODAL_TYPES];

export type ModalSaveMode = 'create' | 'edit' | 'import' | 'export' | 'case' | 'group';

export interface ModalSaveData<T = any> {
    mode: ModalSaveMode;
    entity: string;
    isEdit?: boolean;
    id?: string | number;
    data: T;
}

export interface ModalSaveResult<T = any> {
    success: boolean;
    data?: T;
    message?: string;
    needRefresh?: boolean;
}

export interface ModalConfig {
    component: any;
    title?: string;
    width?: string;
    props?: Record<string, any>;
    options?: Record<string, any>;
    defaultConfig?: Record<string, any>;
}

export interface ActiveModal extends ModalConfig {
    id: string;
    visible: boolean;
    type: string;
    confirmed?: boolean;
    processing?: boolean;
}

export interface APIRequestOptions {
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    url: string;
    data?: any;
    params?: any;
    headers?: Record<string, string>;
    isMultipart?: boolean;
    options?: {
        responseType?: 'json' | 'blob' | 'arraybuffer' | 'text';
        timeout?: number;
    };
}

export interface TestCaseFormData {
    id?: string | number;
    name: string;
    description?: string;
    type?: string;
    test_type?: 'api' | 'e2e';
    config?: import('../../components/common/test-case/TestCaseModal/types').TestCaseConfig;
    groupId?: string | number;
    group?: string;
    tags?: string[];
    tagsInput?: string;
    algorithmType?: string;
    /** 按轮分组的算法参数，独立于 config，对应 test_cases.algorithm_params 列 */
    algorithm_params?: import('../../components/common/test-case/TestCaseModal/types').RoundAlgorithmParams[];
    /** 按轮分组的参考参数路径，独立于 config，对应 test_cases.reference_params 列 */
    reference_params?: import('../../components/common/test-case/TestCaseModal/types').RoundReferenceParams[];
}

export interface GroupFormData {
    name: string;
    description?: string;
    parentId?: string | number;
    algorithmType?: string;
}

export type TestCaseAction = 'add' | 'edit' | 'delete' | 'run' | 'duplicate';

export interface AudioStats {
    total: number;
    dry: number;
    noise: number;
    prompt: number;
    mixed: number;
    totalFiles: number;
    totalSize: string;
    totalDuration: string;
    todayUploads: number;
}

export interface AudioQueryParams {
    page: number;
    perPage: number;
    search?: string;
    keyword?: string;
    type?: string;
    tags?: string[];
    sortBy?: string;
    order?: 'asc' | 'desc';
    audioType?: string;
    format?: string;
    sampleRate?: string;
    duration?: string;
    direction?: string;
}
