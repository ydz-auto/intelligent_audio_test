import { ref, reactive, type Ref } from 'vue';
import { audiosApi } from '../utils/api';
import { useUploadState } from './useUploadState';
import { extractAudioFiles, buildTestCaseConfig, groupAudioFilesByLeafFolder, type TestCaseConfig } from '../utils/folderParser';
import { stripAlgorithmParamSchema } from '../utils/utils';
import SparkMD5 from 'spark-md5';
import type {
  AudioUploadFile,
  AudioUploadTask,
  AudioUploadOptions,
  APIResponse,
} from '../shared/types';
import type { useAlgorithmParams } from './useAlgorithmParams';

/**
 * 文件上传处理组合式函数
 *
 * 职责：
 * - 上传任务初始化、文件注册
 * - 分片上传（WAV 直传 / 非 WAV 转码）
 * - 上传进度管理
 * - 暂停/恢复/重试
 * - 本地任务持久化（localStorage）
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
  let generatedTestCaseTotal = 0;

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

  // ========== MD5 计算 ==========

  async function calculateMd5(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const chunkSize = 10 * 1024 * 1024;
      const chunks = Math.ceil(file.size / chunkSize);
      const spark = new SparkMD5.ArrayBuffer();
      const reader = new FileReader();
      let currentChunk = 0;

      reader.onload = (e) => {
        if (e.target?.result) {
          spark.append(e.target.result as ArrayBuffer);
          currentChunk++;
          if (currentChunk < chunks) {
            loadNext();
          } else {
            resolve(spark.end());
          }
        }
      };

      reader.onerror = () => reject('MD5 calculation failed');

      function loadNext() {
        const start = currentChunk * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        reader.readAsArrayBuffer(file.slice(start, end));
      }

      loadNext();
    });
  }

  // ========== 本地任务持久化 ==========

  function getLocalTasks(): AudioUploadTask[] {
    try {
      const stored = localStorage.getItem('audioUploadTasks');
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error('Failed to get local tasks:', e);
      return [];
    }
  }

  function saveLocalTask(task: AudioUploadTask): void {
    if (!task.id) return;
    try {
      const tasks = getLocalTasks();
      const index = tasks.findIndex(t => t.id === task.id);
      if (index !== -1) {
        tasks[index] = task;
      } else {
        tasks.push(task);
      }
      localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
      uploadTasks.value = tasks;
    } catch (e) {
      console.error('Failed to save local task:', e);
    }
  }

  function pathBasename(filePath: string): string {
    if (!filePath) return '';
    const parts = filePath.split(/[\\/]/);
    return parts[parts.length - 1];
  }

  // ========== 进度管理 ==========

  function updateOverallProgress() {
    if (!currentTask.value) return;
    const totalSize = currentTask.value.totalSize || 0;
    const uploadedSize = currentTask.value.files.reduce((sum, f) => sum + (f.uploadedSize || 0), 0);
    uploadProgress.value = totalSize > 0 ? Math.round((uploadedSize / totalSize) * 100) : 0;
    currentTask.value.uploadedSize = uploadedSize;
  }

  // ========== 上传流程 ==========

  async function startUploadProcess(
    files: any[],
    folderGroupMappings?: Record<string, string>,
    unifiedRounds?: any[],
    onUploadComplete?: () => void
  ) {
    if (files.length === 0) return;

    uploadStatus.value = 'preparing';
    uploadProgress.value = 1;
    abortController = new AbortController();
    generatedTestCaseTotal = 0;

    if (typeof window !== 'undefined') {
      await new Promise(resolve => requestAnimationFrame(resolve));
    }

    // 构建多轮测试用例配置（testCaseConfig）
    const allRawFiles: File[] = files.map((f: any) => f.file || f);
    const audioFileInfos = extractAudioFiles(allRawFiles);
    const audioGroups = groupAudioFilesByLeafFolder(audioFileInfos);
    let testCaseConfig: TestCaseConfig | undefined;

    if (audioFileInfos.length > 0 && uploadOptions.createTestCase) {
      const allRounds: any[] = [];
      let roundNumber = 1;
      audioGroups.forEach(groupFiles => {
        const groupConfig = buildTestCaseConfig(groupFiles, allRawFiles, {
          spl: uploadOptions.spl,
          playbackDeviceId: uploadOptions.playbackDeviceId,
          groupName: folderGroupMappings ? Object.values(folderGroupMappings)[0] : undefined,
          inheritTags: uploadOptions.inheritTags,
          algorithmParams: uploadOptions.algorithmParams
        });
        if (groupConfig.rounds) {
          groupConfig.rounds.forEach(r => {
            allRounds.push({ ...r, roundNumber: roundNumber++ });
          });
        }
      });
      if (allRounds.length > 0) {
        const flatParams = stripAlgorithmParamSchema(uploadOptions.algorithmParams);
        const groupedParams = Array.isArray(flatParams) && flatParams.length > 0
          ? [{ round_number: 1, params: flatParams }]
          : [];
        testCaseConfig = {
          rounds: allRounds,
          group_name: folderGroupMappings ? Object.values(folderGroupMappings)[0] : undefined,
          inherit_tags: uploadOptions.inheritTags,
          algorithm_params: groupedParams
        };
        if (unifiedRounds && unifiedRounds.length > 0) {
          testCaseConfig.rounds = unifiedRounds;
        }
      }
    }

    try {
      const initResponse = await audiosApi.initUpload({
        signal: abortController.signal,
        unwrapResponse: false
      }) as APIResponse<{ taskId: string }>;

      let taskId = '';
      if (initResponse.data?.taskId) {
        taskId = initResponse.data.taskId;
      }

      if (!taskId) {
        throw new Error(initResponse.message || 'Failed to initialize upload task');
      }

      const fileData = [];
      const preparedFiles: AudioUploadFile[] = [];

      for (const item of files) {
        const file = item.file || item;
        const asrText = item.asrText || '';
        const translations = item.translations || [];

        const md5 = await calculateMd5(file);
        const fileId = `f_${Math.random().toString(36).substring(2, 11)}`;

        let folderGroupName = '';
        if (folderGroupMappings) {
          const relativePath = (file as any).webkitRelativePath || '';
          if (relativePath) {
            const rootFolder = relativePath.split('/')[0];
            folderGroupName = folderGroupMappings[rootFolder] || '';
          }
        }

        preparedFiles.push({
          id: fileId,
          fileId,
          file,
          name: file.name,
          size: file.size,
          md5,
          status: 'pending',
          progress: 0,
          uploadedSize: 0,
          folderGroupName,
          asrText: asrText,
          translations,
          annotations: item.annotations || [],
          tags: item.tags || []
        });
        fileData.push({
          name: file.name,
          size: file.size,
          md5,
          relativePath: (file as any).webkitRelativePath || ''
        });
      }

      const regResponse = await audiosApi.registerUploadFiles(taskId, fileData, {
        signal: abortController.signal,
        unwrapResponse: false
      }) as APIResponse<{ files: any[] }>;

      let registeredFiles: any[] = [];
      if (regResponse.data?.files) {
        registeredFiles = regResponse.data.files;
      } else {
        throw new Error(regResponse.message || 'Failed to register files');
      }

      const tasks: AudioUploadFile[] = preparedFiles.map((pf, idx) => {
        const reg = registeredFiles[idx];
        if (!reg) {
          return { ...pf, status: 'failed', error: 'Registration failed' } as AudioUploadFile;
        }
        return {
          ...pf,
          fileId: reg.fileId,
          totalChunks: reg.totalChunks,
          chunkSize: reg.chunkSize,
          uploadedChunks: [],
          status: reg.status || 'pending',
          progress: reg.status === 'completed' ? 100 : 0,
          uploadedSize: reg.status === 'completed' ? pf.size : 0,
          asrText: pf.asrText,
          translations: pf.translations
        };
      });

      const supportedAudioExts = ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg'];
      const audioFiles = files.filter(item => {
        const file = item.file || item;
        const ext = file.name?.split('.').pop()?.toLowerCase() || '';
        return supportedAudioExts.includes(ext);
      });

      const task: AudioUploadTask = {
        id: taskId,
        status: 'uploading',
        progress: 0,
        totalFiles: audioFiles.length,
        completedFiles: tasks.filter(f => f.status === 'completed').length,
        failedFiles: tasks.filter(f => f.status === 'failed').length,
        totalSize: tasks.reduce((sum, f) => sum + f.size, 0),
        uploadedSize: tasks.reduce((sum, f) => sum + (f.uploadedSize || 0), 0),
        files: tasks,
        options: { ...uploadOptions },
        startTime: new Date().toISOString()
      };

      currentTask.value = task;
      saveLocalTask(task);
      uploadStatus.value = 'uploading';
      updateOverallProgress();

      const hasRoundsConfig = !!testCaseConfig?.rounds?.length;
      const pendingTasks = tasks.filter(t => t.status !== 'failed');
      const totalPending = pendingTasks.length;

      let processedPending = 0;
      for (const fileTask of tasks) {
        if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;

        if (fileTask.status === 'failed') {
          continue;
        }

        const isFinalMerge = hasRoundsConfig && (processedPending === totalPending - 1);
        const effectiveOptions = (hasRoundsConfig && !isFinalMerge)
          ? { ...uploadOptions, createTestCase: false }
          : uploadOptions;

        if (fileTask.status === 'completed' && fileTask.totalChunks === 0) {
          fileTask.status = 'uploading';
          currentUploadingFile.value = fileTask.name;

          try {
            await processMergeForExistingFile(taskId, fileTask, effectiveOptions, testCaseConfig);
            fileTask.status = 'completed';
            saveLocalTask(task);
          } catch (err) {
            console.error(`处理已存在文件失败 ${fileTask.name}:`, err);
            fileTask.status = 'failed';
            fileTask.error = err instanceof Error ? err.message : String(err);
            task.failedFiles = (task.failedFiles || 0) + 1;
            saveLocalTask(task);
          }
          updateOverallProgress();
          processedPending++;
          continue;
        }

        if (fileTask.status === 'completed') {
          continue;
        }

        fileTask.status = 'uploading';
        currentUploadingFile.value = fileTask.name;

        try {
          await uploadFileChunks(taskId, fileTask, effectiveOptions, testCaseConfig);
          fileTask.status = 'completed';
          fileTask.progress = 100;
          task.completedFiles = (task.completedFiles || 0) + 1;
          saveLocalTask(task);
        } catch (err) {
          console.error(`Upload failed for ${fileTask.name}:`, err);
          fileTask.status = 'failed';
          fileTask.error = err instanceof Error ? err.message : String(err);
          task.failedFiles = (task.failedFiles || 0) + 1;
          saveLocalTask(task);
        }
        updateOverallProgress();
        processedPending++;
      }

      uploadStatus.value = (task.failedFiles || 0) > 0 ? 'failed' : 'completed';
      task.status = uploadStatus.value;
      task.endTime = new Date().toISOString();
      saveLocalTask(task);

      // 上传完成后回调（用于刷新列表等）
      if (onUploadComplete) onUploadComplete();

      if (uploadOptions.createTestCase && (task.failedFiles || 0) === 0) {
        testCaseGeneratedCount.value = generatedTestCaseTotal > 0 ? generatedTestCaseTotal : (task.completedFiles || 0);
        showTestCaseGeneratedTip.value = true;
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        uploadStatus.value = 'stopped';
      } else {
        console.error('Upload process failed:', err);
        uploadStatus.value = 'failed';
      }
    } finally {
      abortController = null;
      currentUploadingFile.value = null;
    }
  }

  // ========== 秒传/已存在文件处理 ==========

  async function processMergeForExistingFile(
    taskId: string,
    fileTask: AudioUploadFile,
    options: any = uploadOptions,
    tcConfig?: TestCaseConfig
  ) {
    await algorithmApi.dispatchParamsToRounds(tcConfig, options.algorithmType, fileTask, options);
    const normalizedAlgorithmParams = await algorithmApi.resolveAlgorithmParamsFromAnnotations(
      options.algorithmType,
      fileTask.annotations,
      options.algorithmParams
    );

    const mergeResponse = await audiosApi.mergeChunks(fileTask.fileId, taskId, {
      audioType: options.audioType,
      createTestCase: options.createTestCase,
      tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
      description: options.description,
      testTypes: options.testTypes,
      playbackDeviceId: options.playbackDeviceId,
      spl: options.spl,
      groupNameType: options.groupNameType,
      customGroupName: fileTask.folderGroupName || options.customGroupName,
      inheritTags: options.inheritTags,
      dimensions: options.createTestCase ? options.dimensions : undefined,
      noiseAudioId: options.noiseAudioId,
      noiseSpl: options.noiseSpl,
      asrText: fileTask.asrText || '',
      translations: fileTask.translations || [],
      annotations: fileTask.annotations || [],
      algorithmType: options.algorithmType,
      algorithmRelations: options.algorithmRelations,
      algorithmParams: normalizedAlgorithmParams || [],
      testCaseConfig: tcConfig
    }, {
      signal: abortController?.signal,
      unwrapResponse: false
    }) as APIResponse<{ audioId: string | number }>;

    if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
      throw new Error(mergeResponse.message || 'Failed to process existing file');
    }

    fileTask.audioId = mergeResponse.data?.audioId;
    const cnt = mergeResponse.data?.testCaseCount ?? mergeResponse.data?.test_case_count;
    if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal += cnt;

    if (tcConfig?.rounds && fileTask.audioId) {
      const realName = mergeResponse.data?.name || fileTask.name;
      for (const r of tcConfig.rounds) {
        if (!r.audios) continue;
        for (const a of r.audios) {
          if (a.audio_name === fileTask.name || a.audio_name === realName) {
            a.audio_id = fileTask.audioId;
          }
        }
      }
    }
  }

  // ========== 分片上传 ==========

  async function uploadFileChunks(
    taskId: string,
    fileTask: AudioUploadFile,
    options: any = uploadOptions,
    tcConfig?: TestCaseConfig
  ) {
    await algorithmApi.dispatchParamsToRounds(tcConfig, options.algorithmType, fileTask, options);
    const normalizedAlgorithmParams = await algorithmApi.resolveAlgorithmParamsFromAnnotations(
      options.algorithmType,
      fileTask.annotations,
      options.algorithmParams
    );

    const ext = fileTask.name.split('.').pop()?.toLowerCase() || '';
    const isWav = ext === 'wav';
    const chunkSize = 5 * 1024 * 1024;
    const totalChunks = Math.max(1, Math.ceil(fileTask.size / chunkSize));

    // 1. 请求预签名 URL
    const presignResponse = await audiosApi.presignUpload({
      filename: fileTask.name,
      fileSize: fileTask.size,
      md5: fileTask.md5,
      chunkSize,
      isWav,
      relativePath: (fileTask.file as any).webkitRelativePath || '',
    }, {
      signal: abortController?.signal,
      unwrapResponse: false,
    }) as APIResponse<any>;

    // 秒传命中
    if (presignResponse.data?.instantUpload) {
      fileTask.audioId = presignResponse.data.audioId;
      fileTask.status = 'completed';
      fileTask.progress = 100;
      fileTask.uploadedSize = fileTask.size;
      await processMergeForExistingFile(taskId, fileTask, options, tcConfig);
      return;
    }

    const { uploadId, ossKey, category, parts: presignedParts, totalParts } = presignResponse.data || {};
    if (!uploadId || !ossKey) {
      throw new Error(presignResponse.message || '获取上传预签名 URL 失败');
    }

    // 2. 分片直传 OSS
    const uploadedParts: Array<{ PartNumber: number; ETag: string }> = [];
    for (let i = 0; i < totalParts; i++) {
      if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') {
        fileTask.status = (uploadStatus.value as string) === 'paused' ? 'paused' : 'stopped';
        throw new Error(`Upload ${fileTask.status}`);
      }

      let partUrl: string;
      if (i < presignedParts.length) {
        partUrl = presignedParts[i].url;
      } else {
        const partResp = await audiosApi.presignPart({
          uploadId,
          partNumber: i + 1,
        }, ossKey, category, { signal: abortController?.signal, unwrapResponse: false }) as APIResponse<any>;
        partUrl = partResp.data?.url;
      }
      if (!partUrl) throw new Error(`获取分片 ${i + 1} 预签名 URL 失败`);

      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, fileTask.size);
      const chunk = fileTask.file.slice(start, end);

      const chunkBuf = await chunk.arrayBuffer();
      const putResp = await fetch(partUrl, {
        method: 'PUT',
        body: chunkBuf,
        signal: abortController?.signal,
      });
      if (!putResp.ok) {
        throw new Error(`分片 ${i + 1} 上传失败: ${putResp.status} ${putResp.statusText}`);
      }
      const etag = putResp.headers.get('ETag') || '';
      uploadedParts.push({ PartNumber: i + 1, ETag: etag });

      fileTask.uploadedSize = end;
      fileTask.progress = Math.round((end / fileTask.size) * 100);
      updateOverallProgress();
    }

    // 3. 完成上传
    if (isWav) {
      const completeResp = await audiosApi.completeDirectUpload({
        ossKey,
        uploadId,
        parts: uploadedParts,
        filename: fileTask.name,
        md5: fileTask.md5,
        fileSize: fileTask.size,
        tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
        audioType: options.audioType,
        asrText: fileTask.asrText || '',
      }, {
        signal: abortController?.signal,
        unwrapResponse: false,
      }) as APIResponse<any>;

      if (completeResp.code !== undefined && completeResp.code !== 0 && completeResp.code !== 200) {
        throw new Error(completeResp.message || '直传完成失败');
      }
      fileTask.audioId = completeResp.data?.audio_id || completeResp.data?.audioId;

      if (tcConfig?.rounds?.length || options.createTestCase) {
        await processMergeForExistingFile(taskId, fileTask, options, tcConfig);
      }
    } else {
      const mergeResponse = await audiosApi.mergeChunks(fileTask.fileId, taskId, {
        audioType: options.audioType,
        createTestCase: options.createTestCase,
        tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
        description: options.description,
        testTypes: options.testTypes,
        playbackDeviceId: options.playbackDeviceId,
        spl: options.spl,
        groupNameType: options.groupNameType,
        customGroupName: fileTask.folderGroupName || options.customGroupName,
        inheritTags: options.inheritTags,
        dimensions: options.createTestCase ? options.dimensions : undefined,
        noiseAudioId: options.noiseAudioId,
        noiseSpl: options.noiseSpl,
        asrText: fileTask.asrText || '',
        translations: fileTask.translations || [],
        annotations: fileTask.annotations || [],
        algorithmType: options.algorithmType,
        algorithmRelations: options.algorithmRelations,
        algorithmParams: normalizedAlgorithmParams || [],
        testCaseConfig: tcConfig,
        isDirectOss: true,
        ossUploadId: uploadId,
        ossKey,
        ossParts: uploadedParts,
      }, {
        signal: abortController?.signal,
        unwrapResponse: false,
      }) as APIResponse<{ audioId: string | number }>;

      if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
        throw new Error(mergeResponse.message || 'Failed to merge chunks');
      }

      fileTask.audioId = mergeResponse.data?.audioId;
      const cnt = mergeResponse.data?.testCaseCount ?? mergeResponse.data?.test_case_count;
      if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal += cnt;
      if (tcConfig?.rounds && fileTask.audioId) {
        const realName = mergeResponse.data?.name || fileTask.name;
        for (const r of tcConfig.rounds) {
          if (!r.audios) continue;
          for (const a of r.audios) {
            if (a.audio_name === fileTask.name || a.audio_name === realName) {
              a.audio_id = fileTask.audioId;
            }
          }
        }
      }
    }
  }

  // ========== 任务控制 ==========

  const pauseUploadTask = (taskId: string) => {
    if (currentTask.value?.id === taskId) {
      uploadStatus.value = 'paused';
      currentTask.value.status = 'paused';
      saveLocalTask(currentTask.value);
      abortController?.abort();
    }
  };

  const resumeUploadTask = async (taskId: string, isRetry = false, onUploadComplete?: () => void) => {
    const task = uploadTasks.value.find(t => t.id === taskId);
    if (!task) return;

    currentTask.value = task;
    uploadStatus.value = 'uploading';
    task.status = 'uploading';
    abortController = new AbortController();
    const taskOptions = task.options || uploadOptions;

    for (const fileTask of task.files) {
      if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;
      if (fileTask.status !== 'completed') {
        try {
          fileTask.status = 'uploading';
          currentUploadingFile.value = fileTask.name;
          await uploadFileChunks(taskId, fileTask, taskOptions);
          fileTask.status = 'completed';
          fileTask.progress = 100;
          saveLocalTask(task);
        } catch (err) {
          fileTask.status = 'failed';
          fileTask.error = err instanceof Error ? err.message : String(err);
          saveLocalTask(task);
        }
        updateOverallProgress();
      }
    }

    task.completedFiles = task.files.filter(f => f.status === 'completed').length;
    task.failedFiles = task.files.filter(f => f.status === 'failed').length;

    uploadStatus.value = task.failedFiles > 0 ? 'failed' : 'completed';
    task.status = uploadStatus.value;
    task.endTime = new Date().toISOString();
    saveLocalTask(task);

    isRetryingFailed.value = false;
    if (onUploadComplete) onUploadComplete();
  };

  const retryFailedFiles = async (taskId: string, autoSelectFiles = false, onUploadComplete?: () => void) => {
    const task = uploadTasks.value.find(t => t.id === taskId);
    if (!task) return;

    isRetryingFailed.value = true;
    const previousFailedFiles = task.files.filter(f => f.status === 'failed');
    const fileData = [];
    let canReRegister = true;
    let needReSelectFiles = false;
    let failedFileNames: string[] = [];

    for (const fileTask of previousFailedFiles) {
      failedFileNames.push(fileTask.name);
      if (fileTask.file && typeof fileTask.file.slice === 'function') {
        try {
          const md5 = await calculateMd5(fileTask.file);
          fileData.push({
            name: fileTask.name,
            size: fileTask.size,
            md5
          });
        } catch (md5Err) {
          console.error('计算MD5失败:', fileTask.name, md5Err);
          canReRegister = false;
          needReSelectFiles = true;
        }
      } else {
        canReRegister = false;
        needReSelectFiles = true;
      }
    }

    if (needReSelectFiles || autoSelectFiles) {
      setTimeout(async () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = 'audio/*,.wav,.mp3,.m4a,.flac';
        input.onchange = async (e: any) => {
          const files = e.target.files;
          if (files && files.length > 0) {
            const selectedFiles = Array.from(files);
            const newFileTasks: typeof task.files = [];

            for (const file of selectedFiles) {
              if (failedFileNames.includes(file.name)) {
                const md5 = await calculateMd5(file);
                const fileId = `f_${Math.random().toString(36).substring(2, 11)}`;
                newFileTasks.push({
                  id: fileId,
                  fileId,
                  file,
                  name: file.name,
                  size: file.size,
                  md5,
                  status: 'pending' as const,
                  progress: 0,
                  uploadedSize: 0,
                  uploadedChunks: []
                });
              }
            }

            if (newFileTasks.length > 0) {
              task.files = task.files.filter(f => f.status !== 'failed');
              task.files.push(...newFileTasks);
              task.failedFiles = 0;
              task.completedFiles = task.files.filter(f => f.status === 'completed').length;
              task.totalFiles = task.files.length;
              saveLocalTask(task);

              const newFileData = newFileTasks.map(ft => ({
                name: ft.name,
                size: ft.size,
                md5: ft.md5
              }));

              try {
                const regResponse = await audiosApi.registerUploadFiles(taskId, newFileData, {
                  signal: abortController?.signal,
                  unwrapResponse: false
                }) as APIResponse<{ files: any[] }>;

                if (regResponse.data?.files) {
                  newFileTasks.forEach((ft, idx) => {
                    const reg = regResponse.data.files[idx];
                    if (reg) {
                      ft.fileId = reg.fileId;
                      ft.totalChunks = reg.totalChunks;
                      ft.chunkSize = reg.chunkSize;
                    }
                  });
                }
              } catch (regErr) {
                console.error('重新注册文件失败:', regErr);
              }

              await resumeUploadTask(taskId, false, onUploadComplete);
            }
          } else {
            isRetryingFailed.value = false;
          }
        };
        input.click();
      }, 100);
      return;
    }

    if (canReRegister && fileData.length > 0) {
      try {
        const regResponse = await audiosApi.registerUploadFiles(taskId, fileData, {
          signal: abortController?.signal,
          unwrapResponse: false
        }) as APIResponse<{ files: any[] }>;

        if (regResponse.data?.files) {
          previousFailedFiles.forEach((fileTask, idx) => {
            const reg = regResponse.data.files[idx];
            if (reg) {
              fileTask.fileId = reg.fileId;
              fileTask.totalChunks = reg.totalChunks;
              fileTask.chunkSize = reg.chunkSize;
              fileTask.uploadedChunks = [];
              fileTask.progress = 0;
              fileTask.uploadedSize = 0;
              fileTask.status = 'pending';
              fileTask.error = undefined;
            }
          });
        }
      } catch (regErr) {
        console.error('重新注册文件失败:', regErr);
      }
    }

    task.files.forEach(f => {
      if (f.status === 'failed') f.status = 'pending';
    });

    task.failedFiles = 0;
    task.completedFiles = 0;
    saveLocalTask(task);

    await resumeUploadTask(taskId, false, onUploadComplete);
  };

  const removeLocalTask = (taskId: string) => {
    const tasks = getLocalTasks().filter(t => t.id !== taskId);
    localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
    uploadTasks.value = tasks;
    if (currentTask.value?.id === taskId) {
      currentTask.value = null;
      uploadStatus.value = 'idle';
      uploadProgress.value = 0;
    }
  };

  const dismissTask = (taskId: string, onUploadComplete?: () => void) => {
    removeLocalTask(taskId);
    if (onUploadComplete) onUploadComplete();
  };

  const checkAndResumeTasks = (onUploadComplete?: () => void) => {
    const tasks = getLocalTasks();
    const unfinished = tasks.find(t => t.status === 'uploading' || t.status === 'paused');
    if (unfinished && unfinished.id) {
      resumeUploadTask(unfinished.id, false, onUploadComplete);
    }
  };

  // ========== 拖拽上传 ==========

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      selectedFilesForUpload.value = Array.from(files);
      await startUploadProcess(selectedFilesForUpload.value);
    }
  }

  async function pickFiles(onUploadComplete?: () => void) {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = 'audio/*';
    input.onchange = async (e: any) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        selectedFilesForUpload.value = Array.from(files);
        await startUploadProcess(selectedFilesForUpload.value, undefined, undefined, onUploadComplete);
      }
    };
    input.click();
  }

  // ========== 维度展开工具 ==========

  function expandDimensions(options: any): void {
    const apiScopes: ('single' | 'multi')[] = (options as any)?.apiScopes || ['single'];
    const e2eScopes: ('single' | 'multi')[] = (options as any)?.e2eScopes || ['single'];
    const expandDims = (dims: any[], tt: string, scopes: ('single' | 'multi')[]) => {
      if (!dims || dims.length === 0) return [];
      const result: any[] = [];
      for (const d of dims) {
        for (const scope of scopes) {
          result.push({ ...d, test_type: tt, round_scope: scope });
        }
      }
      return result;
    };
    uploadOptions.dimensions = [
      ...expandDims(options?.apiDimensions || [], 'api', apiScopes),
      ...expandDims(options?.e2eDimensions || [], 'e2e', e2eScopes),
      ...(Array.isArray(options?.dimensions) ? options.dimensions : [])
    ];
  }

  /**
   * 从模态框数据更新上传选项
   */
  function updateUploadOptionsFromModal(data: any): void {
    const options = (data && typeof data === 'object' && data.options && typeof data.options === 'object')
      ? data.options
      : ((data && typeof data === 'object' && data.config && typeof data.config === 'object') ? data.config : data);

    if (options?.audioType !== undefined) uploadOptions.audioType = options.audioType;
    if (options?.createTestCase !== undefined) uploadOptions.createTestCase = options.createTestCase;
    if (data?.tags !== undefined) uploadOptions.tags = data.tags;
    if (options?.testTypes !== undefined) uploadOptions.testTypes = options.testTypes;
    if (options?.playbackDeviceId !== undefined) uploadOptions.playbackDeviceId = options.playbackDeviceId;
    if (options?.defaultSpl !== undefined) uploadOptions.spl = options.defaultSpl;
    if (options?.groupNameType !== undefined) uploadOptions.groupNameType = options.groupNameType;
    if (options?.customGroupName !== undefined) uploadOptions.customGroupName = options.customGroupName;
    if (options?.inheritTags !== undefined) uploadOptions.inheritTags = options.inheritTags;
    expandDimensions(options);
    if (options?.noiseAudioId !== undefined) uploadOptions.noiseAudioId = options.noiseAudioId;
    if (options?.noiseSpl !== undefined) uploadOptions.noiseSpl = options.noiseSpl;
    if (options?.algorithmType !== undefined) uploadOptions.algorithmType = options.algorithmType;
    if (options?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = options.algorithmRelations;
    if (options?.algorithmParams !== undefined) uploadOptions.algorithmParams = options.algorithmParams;
    if (data?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = data.algorithmRelations;
  }

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
    saveLocalTask,
    pathBasename,
    updateOverallProgress,
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
