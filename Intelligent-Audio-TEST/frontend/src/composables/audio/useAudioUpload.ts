import { ref, reactive } from 'vue';
import { useUploadState } from '../upload/useUploadState';
import type {
  AudioUploadFile,
  AudioUploadTask,
  AudioUploadOptions,
} from '../../shared/types';
import type { useAlgorithmParams } from '../algorithm/useAlgorithmParams';
import { calculateMd5 } from './md5Utils';
import { getLocalTasks, saveLocalTask, pathBasename } from './taskPersistence';
import {
  updateOverallProgress,
  startUploadProcess as startUploadProcessImpl,
  processMergeForExistingFile as processMergeForExistingFileImpl,
  uploadFileChunks as uploadFileChunksImpl,
  type UploadProcessContext,
} from './uploadProcess';
import {
  pauseUploadTask as pauseUploadTaskImpl,
  resumeUploadTask as resumeUploadTaskImpl,
  retryFailedFiles as retryFailedFilesImpl,
  removeLocalTask as removeLocalTaskImpl,
  dismissTask as dismissTaskImpl,
  checkAndResumeTasks as checkAndResumeTasksImpl,
} from './taskControl';
import {
  handleDrop as handleDropImpl,
  pickFiles as pickFilesImpl,
  expandDimensions as expandDimensionsImpl,
  updateUploadOptionsFromModal as updateUploadOptionsFromModalImpl,
} from './uploadHelpers';

/**
 * 文件上传处理组合式函数
 *
 * 职责：
 * - 上传任务初始化、文件注册
 * - 分片上传（WAV 直传 / 非 WAV 转码）
 * - 上传进度管理
 * - 暂停/恢复/重试
 * - 本地任务持久化（localStorage）
 *
 * 注意：本模块为薄封装层，具体实现拆分至同目录下：
 * - md5Utils.ts            MD5 计算
 * - taskPersistence.ts     本地任务持久化
 * - uploadProcess.ts       上传流程（进度/初始化/分片/秒传）
 * - taskControl.ts         任务控制（暂停/恢复/重试/移除）
 * - uploadHelpers.ts       文件拖拽与选项工具
 */

interface AlgorithmParamsApi {
  resolveAlgorithmParamsFromAnnotations: ReturnType<typeof useAlgorithmParams>['resolveAlgorithmParamsFromAnnotations'];
  dispatchParamsToRounds: ReturnType<typeof useAlgorithmParams>['dispatchParamsToRounds'];
}

export function useAudioUpload(algorithmApi: AlgorithmParamsApi) {
  const { uploadProgress, currentTask, currentUploadingFile, isRetryingFailed, uploadStatus } = useUploadState();

  // 上传完成后的用例生成提示
  const testCaseGeneratedCount = ref(0);
  const showTestCaseGeneratedTip = ref(false);
  const generatedTestCaseTotal = { value: 0 };

  const uploadTasks = ref<AudioUploadTask[]>([]);
  const selectedFilesForUpload = ref<File[]>([]);
  const fileList = ref<AudioUploadFile[]>([]);

  let abortController: AbortController | null = null;
  let isOpeningUploadModal = false;

  const uploadOptions = reactive<AudioUploadOptions>({
    audioType: 'dry',
    createTestCase: false,
    tags: [],
    description: '',
    testTypes: ['api'],
    inheritTags: true,
    dimensions: [],
    algorithmType: '',
    algorithmRelations: [],
    algorithmParams: [],
    promptDeviceId: null,
    promptSourceLanguage: '',
    promptTargetLanguage: '',
    promptTranslationDirection: '',
    promptAlgorithmType: ''
  });

  const folderImportOptions = reactive({
    recursive: true,
    keepStructure: true,
    allowedExtensions: ['.wav', '.mp3', '.m4a', '.flac'],
    createTestCase: false,
    testTypes: ['api'] as ('api' | 'e2e')[],
    playbackDeviceId: null as string | number | null,
    spl: 65.0,
    groupNameType: 'root' as 'root' | 'folder' | 'custom',
    customGroupName: ''
  });

  // 构建上下文，供提取的模块共享状态与副作用
  const ctx: UploadProcessContext = {
    uploadProgress,
    currentTask,
    currentUploadingFile,
    uploadStatus,
    uploadTasks,
    uploadOptions,
    generatedTestCaseTotal,
    getAbortController: () => abortController,
    setAbortController: (c) => { abortController = c; },
    algorithmApi,
    onTestCaseGenerated: (total, completed) => {
      testCaseGeneratedCount.value = total > 0 ? total : completed;
      showTestCaseGeneratedTip.value = true;
    },
  };

  // ========== 进度管理 ==========
  const updateOverallProgressFn = () => updateOverallProgress(ctx);

  // ========== 上传流程 ==========
  const startUploadProcess = (
    files: any[],
    folderGroupMappings?: Record<string, string>,
    unifiedRounds?: any[],
    onUploadComplete?: () => void
  ) => startUploadProcessImpl(ctx, files, folderGroupMappings, unifiedRounds, onUploadComplete);

  const processMergeForExistingFile = (
    taskId: string,
    fileTask: AudioUploadFile,
    options: any = uploadOptions,
    tcConfig?: any
  ) => processMergeForExistingFileImpl(ctx, taskId, fileTask, options, tcConfig);

  const uploadFileChunks = (
    taskId: string,
    fileTask: AudioUploadFile,
    options: any = uploadOptions,
    tcConfig?: any
  ) => uploadFileChunksImpl(ctx, taskId, fileTask, options, tcConfig);

  // ========== 任务控制 ==========
  const taskControlCtx = {
    ...ctx,
    isRetryingFailed,
    uploadFileChunks: (ctxParam: any, taskId: string, fileTask: AudioUploadFile, options: any, tcConfig?: any) =>
      uploadFileChunksImpl(ctxParam, taskId, fileTask, options, tcConfig),
  };

  const pauseUploadTask = (taskId: string) => pauseUploadTaskImpl(taskControlCtx, taskId);
  const resumeUploadTask = (taskId: string, isRetry = false, onUploadComplete?: () => void) =>
    resumeUploadTaskImpl(taskControlCtx, taskId, isRetry, onUploadComplete);
  const retryFailedFiles = (taskId: string, autoSelectFiles = false, onUploadComplete?: () => void) =>
    retryFailedFilesImpl(taskControlCtx, taskId, autoSelectFiles, onUploadComplete);
  const removeLocalTask = (taskId: string) => removeLocalTaskImpl(taskControlCtx, taskId);
  const dismissTask = (taskId: string, onUploadComplete?: () => void) =>
    dismissTaskImpl(taskControlCtx, taskId, onUploadComplete);
  const checkAndResumeTasks = (onUploadComplete?: () => void) =>
    checkAndResumeTasksImpl(taskControlCtx, onUploadComplete);

  // ========== 拖拽上传 ==========
  const filePickCtx = {
    ...ctx,
    selectedFilesForUpload,
    startUploadProcess: (ctxParam: any, files: any[], folderGroupMappings?: Record<string, string>, unifiedRounds?: any[], onUploadComplete?: () => void) =>
      startUploadProcessImpl(ctxParam, files, folderGroupMappings, unifiedRounds, onUploadComplete),
  };

  const handleDrop = (e: DragEvent) => handleDropImpl(filePickCtx, e);
  const pickFiles = (onUploadComplete?: () => void) => pickFilesImpl(filePickCtx, onUploadComplete);

  // ========== 维度展开工具 ==========
  const expandDimensions = (options: any) => expandDimensionsImpl(uploadOptions, options);
  const updateUploadOptionsFromModal = (data: any) => updateUploadOptionsFromModalImpl(uploadOptions, data);

  return {
    // 状态
    uploadTasks,
    selectedFilesForUpload,
    fileList,
    uploadProgress,
    currentTask,
    currentUploadingFile,
    isRetryingFailed,
    uploadStatus,
    uploadOptions,
    folderImportOptions,
    testCaseGeneratedCount,
    showTestCaseGeneratedTip,
    isOpeningUploadModal,
    // 方法
    calculateMd5,
    getLocalTasks,
    saveLocalTask: (task: AudioUploadTask) => saveLocalTask(task, uploadTasks),
    pathBasename,
    updateOverallProgress: updateOverallProgressFn,
    startUploadProcess,
    processMergeForExistingFile,
    uploadFileChunks,
    pauseUploadTask,
    resumeUploadTask,
    retryFailedFiles,
    removeLocalTask,
    dismissTask,
    checkAndResumeTasks,
    handleDrop,
    pickFiles,
    expandDimensions,
    updateUploadOptionsFromModal,
  };
}
