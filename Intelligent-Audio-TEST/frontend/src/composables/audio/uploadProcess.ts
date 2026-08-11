import type { Ref } from 'vue';
import { audiosApi } from '../../utils/api';
import { extractAudioFiles, buildTestCaseConfig, groupAudioFilesByLeafFolder, type TestCaseConfig } from '../../utils/folderParser';
import { stripAlgorithmParamSchema } from '../../utils/utils';
import type {
  AudioUploadFile,
  AudioUploadTask,
  AudioUploadOptions,
  APIResponse,
} from '../../shared/types';
import type { UploadStatus } from '../upload/useUploadState';
import { calculateMd5 } from './md5Utils';
import { saveLocalTask } from './taskPersistence';

/**
 * 上传流程相关逻辑：进度管理、上传初始化、分片上传、秒传/已存在文件处理
 */

export interface UploadProcessContext {
  uploadProgress: Ref<number>;
  currentTask: Ref<AudioUploadTask | null>;
  currentUploadingFile: Ref<string | null>;
  uploadStatus: Ref<UploadStatus>;
  uploadTasks: Ref<AudioUploadTask[]>;
  uploadOptions: AudioUploadOptions;
  generatedTestCaseTotal: { value: number };
  getAbortController: () => AbortController | null;
  setAbortController: (controller: AbortController | null) => void;
  algorithmApi: {
    resolveAlgorithmParamsFromAnnotations: ReturnType<any>['resolveAlgorithmParamsFromAnnotations'];
    dispatchParamsToRounds: ReturnType<any>['dispatchParamsToRounds'];
  };
  onTestCaseGenerated?: (total: number, completed: number) => void;
}

export function updateOverallProgress(ctx: UploadProcessContext): void {
  const { uploadProgress, currentTask } = ctx;
  if (!currentTask.value) return;
  const totalSize = currentTask.value.totalSize || 0;
  const uploadedSize = currentTask.value.files.reduce((sum, f) => sum + (f.uploadedSize || 0), 0);
  uploadProgress.value = totalSize > 0 ? Math.round((uploadedSize / totalSize) * 100) : 0;
  currentTask.value.uploadedSize = uploadedSize;
}

export async function startUploadProcess(
  ctx: UploadProcessContext,
  files: any[],
  folderGroupMappings?: Record<string, string>,
  unifiedRounds?: any[],
  onUploadComplete?: () => void
) {
  const {
    uploadProgress,
    currentTask,
    currentUploadingFile,
    uploadStatus,
    uploadOptions,
    generatedTestCaseTotal,
    setAbortController,
    algorithmApi,
  } = ctx;

  if (files.length === 0) return;

  uploadStatus.value = 'preparing';
  uploadProgress.value = 1;
  setAbortController(new AbortController());
  generatedTestCaseTotal.value = 0;

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
        spl: (uploadOptions as any).spl,
        playbackDeviceId: (uploadOptions as any).playbackDeviceId,
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
      signal: ctx.getAbortController()?.signal,
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
      signal: ctx.getAbortController()?.signal,
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
    saveLocalTask(task, ctx.uploadTasks);
    uploadStatus.value = 'uploading';
    updateOverallProgress(ctx);

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
          await processMergeForExistingFile(ctx, taskId, fileTask, effectiveOptions, testCaseConfig);
          fileTask.status = 'completed';
          saveLocalTask(task, ctx.uploadTasks);
        } catch (err) {
          console.error(`处理已存在文件失败 ${fileTask.name}:`, err);
          fileTask.status = 'failed';
          fileTask.error = err instanceof Error ? err.message : String(err);
          task.failedFiles = (task.failedFiles || 0) + 1;
          saveLocalTask(task, ctx.uploadTasks);
        }
        updateOverallProgress(ctx);
        processedPending++;
        continue;
      }

      if (fileTask.status === 'completed') {
        continue;
      }

      fileTask.status = 'uploading';
      currentUploadingFile.value = fileTask.name;

      try {
        await uploadFileChunks(ctx, taskId, fileTask, effectiveOptions, testCaseConfig);
        fileTask.status = 'completed';
        fileTask.progress = 100;
        task.completedFiles = (task.completedFiles || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      } catch (err) {
        console.error(`Upload failed for ${fileTask.name}:`, err);
        fileTask.status = 'failed';
        fileTask.error = err instanceof Error ? err.message : String(err);
        task.failedFiles = (task.failedFiles || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      }
      updateOverallProgress(ctx);
      processedPending++;
    }

    uploadStatus.value = (task.failedFiles || 0) > 0 ? 'failed' : 'completed';
    task.status = uploadStatus.value;
    task.endTime = new Date().toISOString();
    saveLocalTask(task, ctx.uploadTasks);

    // 上传完成后回调（用于刷新列表等）
    if (onUploadComplete) onUploadComplete();

    if (uploadOptions.createTestCase && (task.failedFiles || 0) === 0) {
      // 用例生成提示由主模块处理
      ctx.onTestCaseGenerated?.(generatedTestCaseTotal.value, task.completedFiles || 0);
    }
  } catch (err: any) {
    if (err.name === 'AbortError') {
      uploadStatus.value = 'stopped';
    } else {
      console.error('Upload process failed:', err);
      uploadStatus.value = 'failed';
    }
  } finally {
    setAbortController(null);
    currentUploadingFile.value = null;
  }
}

export async function processMergeForExistingFile(
  ctx: UploadProcessContext,
  taskId: string,
  fileTask: AudioUploadFile,
  options: any,
  tcConfig?: TestCaseConfig
) {
  const { uploadOptions, generatedTestCaseTotal, algorithmApi } = ctx;

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
    signal: ctx.getAbortController()?.signal,
    unwrapResponse: false
  }) as APIResponse<{ audioId: string | number }>;

  if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
    throw new Error(mergeResponse.message || 'Failed to process existing file');
  }

  fileTask.audioId = mergeResponse.data?.audioId;
  const cnt = mergeResponse.data?.testCaseCount ?? mergeResponse.data?.test_case_count;
  if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;

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

export async function uploadFileChunks(
  ctx: UploadProcessContext,
  taskId: string,
  fileTask: AudioUploadFile,
  options: any,
  tcConfig?: TestCaseConfig
) {
  const { uploadStatus, generatedTestCaseTotal, algorithmApi } = ctx;

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
    signal: ctx.getAbortController()?.signal,
    unwrapResponse: false,
  }) as APIResponse<any>;

  // 秒传命中
  if (presignResponse.data?.instantUpload) {
    fileTask.audioId = presignResponse.data.audioId;
    fileTask.status = 'completed';
    fileTask.progress = 100;
    fileTask.uploadedSize = fileTask.size;
    await processMergeForExistingFile(ctx, taskId, fileTask, options, tcConfig);
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
      }, ossKey, category, { signal: ctx.getAbortController()?.signal, unwrapResponse: false }) as APIResponse<any>;
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
      signal: ctx.getAbortController()?.signal,
    });
    if (!putResp.ok) {
      throw new Error(`分片 ${i + 1} 上传失败: ${putResp.status} ${putResp.statusText}`);
    }
    const etag = putResp.headers.get('ETag') || '';
    uploadedParts.push({ PartNumber: i + 1, ETag: etag });

    fileTask.uploadedSize = end;
    fileTask.progress = Math.round((end / fileTask.size) * 100);
    updateOverallProgress(ctx);
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
      signal: ctx.getAbortController()?.signal,
      unwrapResponse: false,
    }) as APIResponse<any>;

    if (completeResp.code !== undefined && completeResp.code !== 0 && completeResp.code !== 200) {
      throw new Error(completeResp.message || '直传完成失败');
    }
    fileTask.audioId = completeResp.data?.audio_id || completeResp.data?.audioId;

    if (tcConfig?.rounds?.length || options.createTestCase) {
      await processMergeForExistingFile(ctx, taskId, fileTask, options, tcConfig);
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
      signal: ctx.getAbortController()?.signal,
      unwrapResponse: false,
    }) as APIResponse<{ audioId: string | number }>;

    if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
      throw new Error(mergeResponse.message || 'Failed to merge chunks');
    }

    fileTask.audioId = mergeResponse.data?.audioId;
    const cnt = mergeResponse.data?.testCaseCount ?? mergeResponse.data?.test_case_count;
    if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;
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
