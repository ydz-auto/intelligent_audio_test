import type { Ref } from 'vue';
import { audiosApi } from '../../utils/api';
import { extractAudioFiles, buildTestCaseConfig, groupAudioFilesByLeafFolder, type TestCaseConfig } from '../../utils/folderParser';
import { groupAudiosByTestCase, computeGroupKeyForAudio, type TestCaseGroup } from '../../utils/testCaseStrategy';
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
  const totalSize = currentTask.value.total_size || 0;
  const uploadedSize = currentTask.value.files.reduce((sum, f) => sum + (f.uploadedSize || 0), 0);
  uploadProgress.value = totalSize > 0 ? Math.round((uploadedSize / totalSize) * 100) : 0;
  currentTask.value.uploaded_size = uploadedSize;
}

export async function startUploadProcess(
  ctx: UploadProcessContext,
  files: any[],
  folderGroupMappings?: Record<string, string>,
  unifiedRoundsByGroup?: Record<string, any>,
  testCaseGroupsData?: Record<string, any>,
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

  // 构建测试用例配置：按 JSON 用例分组，每个 JSON 各自一个独立用例
  // 未被 JSON 引用的音频回退到 folderParser 按文件名分组
  const allRawFiles: File[] = files.map((f: any) => f.file || f);
  const audioFileInfos = extractAudioFiles(allRawFiles);

  // 将 testCaseGroupsData 转为 Map
  const testCaseGroups = new Map<string, TestCaseGroup>()
  if (testCaseGroupsData) {
    for (const [key, val] of Object.entries(testCaseGroupsData)) {
      testCaseGroups.set(key, val as TestCaseGroup)
    }
  }

  // 按测试用例分组音频：被 JSON 引用的归入对应 JSON groupKey，未引用的回退文件名分组
  const audioGroups = testCaseGroups.size > 0
    ? groupAudiosByTestCase(audioFileInfos, testCaseGroups)
    : groupAudioFilesByLeafFolder(audioFileInfos)
  // 为每个分组构建独立的 testCaseConfig（分组键 = 最子级文件夹名）
  // 每个分组最后一个文件 mergeChunks 时才创建用例
  const groupTestCaseConfigs = new Map<string, TestCaseConfig | undefined>();
  if (audioFileInfos.length > 0 && uploadOptions.create_test_case) {
    audioGroups.forEach((groupFiles, groupKey) => {
      const groupConfig = buildTestCaseConfig(groupFiles, allRawFiles, {
        spl: (uploadOptions as any).spl,
        playbackDeviceId: (uploadOptions as any).playback_device_id,
        groupName: folderGroupMappings ? Object.values(folderGroupMappings)[0] : undefined,
        inheritTags: uploadOptions.inherit_tags,
        algorithmParams: uploadOptions.algorithm_params
      });
      // 用该分组的 JSON rounds 覆盖 folderParser 自动推断的 rounds
      if (unifiedRoundsByGroup && unifiedRoundsByGroup[groupKey] && (unifiedRoundsByGroup[groupKey] as any).length > 0) {
        const groupRounds = unifiedRoundsByGroup[groupKey];
        groupConfig.rounds = groupRounds;
        // case 级背景噪声（rounds 外层），优先级高于轮次级
        const caseBg = (groupRounds as any)?._caseBackgroundNoise;
        if (caseBg) {
          groupConfig.background_noise = caseBg;
        }
      }
      groupTestCaseConfigs.set(groupKey, groupConfig.rounds && groupConfig.rounds.length > 0 ? groupConfig : undefined);
    });
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

      // 计算该文件所属分组键
      // 有 JSON 用例时按 JSON 引用匹配，否则回退文件夹名/文件名
      const groupKeyRelativePath = (file as any).webkitRelativePath || ''
      const groupKey = testCaseGroups.size > 0
        ? computeGroupKeyForAudio(file.name, groupKeyRelativePath, testCaseGroups)
        : (() => {
            const pathParts = groupKeyRelativePath.split('/').filter(Boolean)
            return pathParts.length >= 2
              ? pathParts[pathParts.length - 2]
              : file.name.replace(/\.[^.]+$/, '')
          })()

      preparedFiles.push({
        id: fileId,
        file_id: fileId,
        file,
        name: file.name,
        size: file.size,
        md5,
        status: 'pending',
        progress: 0,
        uploadedSize: 0,
        folder_group_name: folderGroupName,
        group_key: groupKey,
        asr_text: asrText,
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
        file_id: reg.file_id ?? reg.fileId,
        totalChunks: reg.totalChunks,
        chunkSize: reg.chunkSize,
        uploadedChunks: [],
        status: reg.status || 'pending',
        progress: reg.status === 'completed' ? 100 : 0,
        uploadedSize: reg.status === 'completed' ? pf.size : 0,
        asr_text: pf.asr_text,
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
      total_files: audioFiles.length,
      completed_files: tasks.filter(f => f.status === 'completed').length,
      failed_files: tasks.filter(f => f.status === 'failed').length,
      total_size: tasks.reduce((sum, f) => sum + f.size, 0),
      uploaded_size: tasks.reduce((sum, f) => sum + (f.uploadedSize || 0), 0),
      files: tasks,
      options: { ...uploadOptions },
      start_time: new Date().toISOString()
    };

    currentTask.value = task;
    saveLocalTask(task, ctx.uploadTasks);
    uploadStatus.value = 'uploading';
    updateOverallProgress(ctx);

    // 按分组创建测试用例：每个分组（最子级文件夹）独立一个测试用例
    // 分组内最后一个待处理文件 mergeChunks 时才创建用例，之前的文件只入库
    // 后端在最后一个文件 mergeChunks 时从数据库按 audio_name 查到该分组所有 audio_id

    // 统计每个分组的待处理文件数和已处理数
    const groupPendingCounts = new Map<string, number>()
    const groupProcessedCounts = new Map<string, number>()
    for (const t of tasks) {
      if (t.status === 'failed') continue
      const gk = t.group_key || t.name.replace(/\.[^.]+$/, '')
      groupPendingCounts.set(gk, (groupPendingCounts.get(gk) || 0) + 1)
      groupProcessedCounts.set(gk, 0)
    }

    for (const fileTask of tasks) {
      if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;

      // 跳过已失败文件（不参与 pending 序列）
      if (fileTask.status === 'failed') {
        continue;
      }

      // 该文件所属分组键
      const gk = fileTask.group_key || fileTask.name.replace(/\.[^.]+$/, '')
      const groupConfig = groupTestCaseConfigs.get(gk)
      const hasGroupRounds = !!groupConfig?.rounds?.length
      const processedInGroup = groupProcessedCounts.get(gk) || 0
      const pendingInGroup = groupPendingCounts.get(gk) || 0
      // 分组内最后一个待处理文件才创建用例
      const isGroupFinalMerge = hasGroupRounds && (processedInGroup === pendingInGroup - 1)
      const effectiveOptions = (hasGroupRounds && !isGroupFinalMerge)
        ? { ...uploadOptions, create_test_case: false }
        : uploadOptions;

      if (fileTask.status === 'completed' && fileTask.totalChunks === 0) {
        fileTask.status = 'uploading';
        currentUploadingFile.value = fileTask.name;

        try {
          await processMergeForExistingFile(ctx, taskId, fileTask, effectiveOptions, groupConfig);
          fileTask.status = 'completed';
          saveLocalTask(task, ctx.uploadTasks);
        } catch (err) {
          console.error(`处理已存在文件失败 ${fileTask.name}:`, err);
          fileTask.status = 'failed';
          fileTask.error = err instanceof Error ? err.message : String(err);
          task.failed_files = (task.failed_files || 0) + 1;
          saveLocalTask(task, ctx.uploadTasks);
        }
        updateOverallProgress(ctx);
        groupProcessedCounts.set(gk, processedInGroup + 1)
        continue;
      }

      if (fileTask.status === 'completed') {
        continue;
      }

      fileTask.status = 'uploading';
      currentUploadingFile.value = fileTask.name;

      try {
        await uploadFileChunks(ctx, taskId, fileTask, effectiveOptions, groupConfig);
        fileTask.status = 'completed';
        fileTask.progress = 100;
        task.completed_files = (task.completed_files || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      } catch (err) {
        console.error(`Upload failed for ${fileTask.name}:`, err);
        fileTask.status = 'failed';
        fileTask.error = err instanceof Error ? err.message : String(err);
        task.failed_files = (task.failed_files || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      }
      updateOverallProgress(ctx);
      groupProcessedCounts.set(gk, processedInGroup + 1)
    }

    uploadStatus.value = (task.failed_files || 0) > 0 ? 'failed' : 'completed';
    task.status = uploadStatus.value;
    task.end_time = new Date().toISOString();
    saveLocalTask(task, ctx.uploadTasks);

    // 上传完成后回调（用于刷新列表等）
    if (onUploadComplete) onUploadComplete();

    if (uploadOptions.create_test_case && (task.failed_files || 0) === 0) {
      // 用例生成提示由主模块处理
      ctx.onTestCaseGenerated?.(generatedTestCaseTotal.value, task.completed_files || 0);
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

  await algorithmApi.dispatchParamsToRounds(tcConfig, options.algorithm_type, fileTask, options);
  const normalizedAlgorithmParams = await algorithmApi.resolveAlgorithmParamsFromAnnotations(
    options.algorithm_type,
    fileTask.annotations,
    options.algorithm_params
  );

  const mergeResponse = await audiosApi.mergeChunks(fileTask.file_id, taskId, {
    audioType: options.audio_type,
    createTestCase: options.create_test_case,
    tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
    description: options.description,
    testTypes: options.test_types,
    playbackDeviceId: options.playback_device_id,
    spl: options.spl,
    groupNameType: options.group_name_type,
    customGroupName: fileTask.folder_group_name || options.custom_group_name,
    inheritTags: options.inherit_tags,
    dimensions: options.create_test_case ? options.dimensions : undefined,
    noiseAudioId: options.noise_audio_id,
    noiseSpl: options.noise_spl,
    asrText: fileTask.asr_text || '',
    translations: fileTask.translations || [],
    annotations: fileTask.annotations || [],
    algorithmType: options.algorithm_type,
    algorithmRelations: options.algorithm_relations,
    algorithmParams: normalizedAlgorithmParams || [],
    testCaseConfig: tcConfig
  }, {
    signal: ctx.getAbortController()?.signal,
    unwrapResponse: false
  }) as APIResponse<{ audioId: string | number }>;

  if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
    throw new Error(mergeResponse.message || 'Failed to process existing file');
  }

  fileTask.audio_id = mergeResponse.data?.audio_id ?? mergeResponse.data?.audioId;
  const cnt = mergeResponse.data?.test_case_count;
  if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;

  if (tcConfig?.rounds && fileTask.audio_id) {
    const realName = mergeResponse.data?.name || fileTask.name;
    for (const r of tcConfig.rounds) {
      if (!r.audios) continue;
      for (const a of r.audios) {
        if (a.audio_name === fileTask.name || a.audio_name === realName) {
          a.audio_id = fileTask.audio_id;
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

  await algorithmApi.dispatchParamsToRounds(tcConfig, options.algorithm_type, fileTask, options);
  const normalizedAlgorithmParams = await algorithmApi.resolveAlgorithmParamsFromAnnotations(
    options.algorithm_type,
    fileTask.annotations,
    options.algorithm_params
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
    fileTask.audio_id = presignResponse.data.audio_id ?? presignResponse.data.audioId;
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
      audioType: options.audio_type,
      asrText: fileTask.asr_text || '',
    }, {
      signal: ctx.getAbortController()?.signal,
      unwrapResponse: false,
    }) as APIResponse<any>;

    if (completeResp.code !== undefined && completeResp.code !== 0 && completeResp.code !== 200) {
      throw new Error(completeResp.message || '直传完成失败');
    }
    fileTask.audio_id = completeResp.data?.audio_id ?? completeResp.data?.audioId;

    if (tcConfig?.rounds?.length || options.create_test_case) {
      await processMergeForExistingFile(ctx, taskId, fileTask, options, tcConfig);
    }
  } else {
    const mergeResponse = await audiosApi.mergeChunks(fileTask.file_id, taskId, {
      audioType: options.audio_type,
      createTestCase: options.create_test_case,
      tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
      description: options.description,
      testTypes: options.test_types,
      playbackDeviceId: options.playback_device_id,
      spl: options.spl,
      groupNameType: options.group_name_type,
      customGroupName: fileTask.folder_group_name || options.custom_group_name,
      inheritTags: options.inherit_tags,
      dimensions: options.create_test_case ? options.dimensions : undefined,
      noiseAudioId: options.noise_audio_id,
      noiseSpl: options.noise_spl,
      asrText: fileTask.asr_text || '',
      translations: fileTask.translations || [],
      annotations: fileTask.annotations || [],
      algorithmType: options.algorithm_type,
      algorithmRelations: options.algorithm_relations,
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

    fileTask.audio_id = mergeResponse.data?.audio_id ?? mergeResponse.data?.audioId;
    const cnt = mergeResponse.data?.test_case_count;
    if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;
    if (tcConfig?.rounds && fileTask.audio_id) {
      const realName = mergeResponse.data?.name || fileTask.name;
      for (const r of tcConfig.rounds) {
        if (!r.audios) continue;
        for (const a of r.audios) {
          if (a.audio_name === fileTask.name || a.audio_name === realName) {
            a.audio_id = fileTask.audio_id;
          }
        }
      }
    }
  }
}
