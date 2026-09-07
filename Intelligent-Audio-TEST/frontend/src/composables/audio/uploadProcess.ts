import type { Ref } from 'vue';
import { audiosPort } from './audiosPort';
import { extractAudioFiles, buildTestCaseConfig, groupAudioFilesByLeafFolder, type TestCaseConfig } from '../../utils/folderParser';
import { groupAudiosByTestCase, computeGroupKeyForAudio, type TestCaseGroupStrategy } from '../../utils/testCaseStrategy';
import type {
  AudioUploadFile,
  AudioUploadTask,
  AudioUploadOptions,
  APIResponse,
} from '../../domain';
import type { UploadStatus } from '../upload/useUploadState';
import { calculateMd5 } from './md5Utils';
import { saveLocalTask } from './taskPersistence';
// 引入上传状态与 HTTP 状态码枚举，消除魔法字符串与魔法数字
import { UploadStatus as UploadStatusEnum, HttpStatus } from '../../domain/enums';

/**
 * mergeChunks 响应 data 局部契约（Infrastructure 已归一为 camelCase 出口）
 */
interface MergeChunksData {
  audioId?: string | number;
  testCaseCount?: number;
  name?: string;
}

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

  uploadStatus.value = UploadStatusEnum.PREPARING;
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
  const testCaseGroups = new Map<string, TestCaseGroupStrategy>()
  if (testCaseGroupsData) {
    for (const [key, val] of Object.entries(testCaseGroupsData)) {
      testCaseGroups.set(key, val as TestCaseGroupStrategy)
    }
  }

  // 按测试用例分组音频：被 JSON 引用的归入对应 JSON groupKey，未引用的回退文件名分组
  const audioGroups = testCaseGroups.size > 0
    ? groupAudiosByTestCase(audioFileInfos, testCaseGroups)
    : groupAudioFilesByLeafFolder(audioFileInfos)
  // 为每个分组构建独立的 testCaseConfig（分组键 = 最子级文件夹名）
  // 每个分组最后一个文件 mergeChunks 时才创建用例
  const groupTestCaseConfigs = new Map<string, TestCaseConfig | undefined>();
  if (audioFileInfos.length > 0 && uploadOptions.createTestCase) {
    audioGroups.forEach((groupFiles, groupKey) => {
      const groupConfig = buildTestCaseConfig(groupFiles, allRawFiles, {
        spl: uploadOptions.spl,
        playbackDeviceId: uploadOptions.playbackDeviceId != null ? String(uploadOptions.playbackDeviceId) : undefined,
        groupName: folderGroupMappings ? Object.values(folderGroupMappings)[0] : undefined,
        inheritTags: uploadOptions.inheritTags,
        algorithmParams: uploadOptions.algorithmParams
      });
      // 用该分组的 JSON rounds 覆盖 folderParser 自动推断的 rounds
      if (unifiedRoundsByGroup && unifiedRoundsByGroup[groupKey] && (unifiedRoundsByGroup[groupKey] as any).length > 0) {
        const groupRounds = unifiedRoundsByGroup[groupKey];
        groupConfig.rounds = groupRounds;
        // case 级背景噪声（rounds 外层），优先级高于轮次级
        // background_noise 为后端用例配置协议原文（round_config_service 仅读 snake_case，无 camelCase 兜底）
        const caseBg = (groupRounds as any)?._caseBackgroundNoise;
        if (caseBg) {
          groupConfig.background_noise = caseBg;
        }
      }
      groupTestCaseConfigs.set(groupKey, groupConfig.rounds && groupConfig.rounds.length > 0 ? groupConfig : undefined);
    });
  }

  try {
    const initResponse = await audiosPort.initUpload({
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
        fileId: fileId,
        file,
        name: file.name,
        size: file.size,
        md5,
        status: UploadStatusEnum.PENDING,
        progress: 0,
        uploadedSize: 0,
        folderGroupName: folderGroupName,
        groupKey: groupKey,
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

    const regResponse = await audiosPort.registerUploadFiles(taskId, fileData, {
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
        return { ...pf, status: UploadStatusEnum.FAILED, error: 'Registration failed' } as AudioUploadFile;
      }
      return {
        ...pf,
        fileId: reg.fileId,
        totalChunks: reg.totalChunks,
        chunkSize: reg.chunkSize,
        uploadedChunks: [],
        status: reg.status || UploadStatusEnum.PENDING,
        progress: reg.status === UploadStatusEnum.COMPLETED ? 100 : 0,
        uploadedSize: reg.status === UploadStatusEnum.COMPLETED ? pf.size : 0,
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
      status: UploadStatusEnum.UPLOADING,
      progress: 0,
      totalFiles: audioFiles.length,
      completedFiles: tasks.filter(f => f.status === UploadStatusEnum.COMPLETED).length,
      failedFiles: tasks.filter(f => f.status === UploadStatusEnum.FAILED).length,
      totalSize: tasks.reduce((sum, f) => sum + f.size, 0),
      uploadedSize: tasks.reduce((sum, f) => sum + (f.uploadedSize || 0), 0),
      files: tasks,
      options: { ...uploadOptions },
      startTime: new Date().toISOString()
    };

    currentTask.value = task;
    saveLocalTask(task, ctx.uploadTasks);
    uploadStatus.value = UploadStatusEnum.UPLOADING;
    updateOverallProgress(ctx);

    // 按分组创建测试用例：每个分组（最子级文件夹）独立一个测试用例
    // 分组内最后一个待处理文件 mergeChunks 时才创建用例，之前的文件只入库
    // 后端在最后一个文件 mergeChunks 时从数据库按 audio_name 查到该分组所有 audio_id

    // 统计每个分组的待处理文件数和已处理数
    const groupPendingCounts = new Map<string, number>()
    const groupProcessedCounts = new Map<string, number>()
    for (const t of tasks) {
      if (t.status === UploadStatusEnum.FAILED) continue
      const gk = t.groupKey || t.name.replace(/\.[^.]+$/, '')
      groupPendingCounts.set(gk, (groupPendingCounts.get(gk) || 0) + 1)
      groupProcessedCounts.set(gk, 0)
    }

    for (const fileTask of tasks) {
      // as string 规避 TS 对 .value 赋值后的字面量窄化
    if ((uploadStatus.value as string) === UploadStatusEnum.PAUSED || (uploadStatus.value as string) === UploadStatusEnum.STOPPED) break;

      // 跳过已失败文件（不参与 pending 序列）
      if (fileTask.status === UploadStatusEnum.FAILED) {
        continue;
      }

      // 该文件所属分组键（camelCase 字段，Domain 类型已转换）
      const gk = fileTask.groupKey || fileTask.name.replace(/\.[^.]+$/, '')
      const groupConfig = groupTestCaseConfigs.get(gk)
      const hasGroupRounds = !!groupConfig?.rounds?.length
      const processedInGroup = groupProcessedCounts.get(gk) || 0
      const pendingInGroup = groupPendingCounts.get(gk) || 0
      // 分组内最后一个待处理文件才创建用例
      const isGroupFinalMerge = hasGroupRounds && (processedInGroup === pendingInGroup - 1)
      const effectiveOptions = (hasGroupRounds && !isGroupFinalMerge)
        ? { ...uploadOptions, createTestCase: false }
        : uploadOptions;

      if (fileTask.status === UploadStatusEnum.COMPLETED && fileTask.totalChunks === 0) {
        fileTask.status = UploadStatusEnum.UPLOADING;
        currentUploadingFile.value = fileTask.name;

        try {
          await processMergeForExistingFile(ctx, taskId, fileTask, effectiveOptions, groupConfig);
          fileTask.status = UploadStatusEnum.COMPLETED;
          saveLocalTask(task, ctx.uploadTasks);
        } catch (err) {
          console.error(`处理已存在文件失败 ${fileTask.name}:`, err);
          fileTask.status = UploadStatusEnum.FAILED;
          fileTask.error = err instanceof Error ? err.message : String(err);
          task.failedFiles = (task.failedFiles || 0) + 1;
          saveLocalTask(task, ctx.uploadTasks);
        }
        updateOverallProgress(ctx);
        groupProcessedCounts.set(gk, processedInGroup + 1)
        continue;
      }

      if (fileTask.status === UploadStatusEnum.COMPLETED) {
        continue;
      }

      fileTask.status = UploadStatusEnum.UPLOADING;
      currentUploadingFile.value = fileTask.name;

      try {
        await uploadFileChunks(ctx, taskId, fileTask, effectiveOptions, groupConfig);
        fileTask.status = UploadStatusEnum.COMPLETED;
        fileTask.progress = 100;
        task.completedFiles = (task.completedFiles || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      } catch (err) {
        console.error(`Upload failed for ${fileTask.name}:`, err);
        fileTask.status = UploadStatusEnum.FAILED;
        fileTask.error = err instanceof Error ? err.message : String(err);
        task.failedFiles = (task.failedFiles || 0) + 1;
        saveLocalTask(task, ctx.uploadTasks);
      }
      updateOverallProgress(ctx);
      groupProcessedCounts.set(gk, processedInGroup + 1)
    }

    uploadStatus.value = (task.failedFiles || 0) > 0 ? UploadStatusEnum.FAILED : UploadStatusEnum.COMPLETED;
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
      uploadStatus.value = UploadStatusEnum.STOPPED;
    } else {
      console.error('Upload process failed:', err);
      uploadStatus.value = UploadStatusEnum.FAILED;
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

  const mergeResponse = await audiosPort.mergeChunks(fileTask.fileId, taskId, {
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

  if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== HttpStatus.OK && mergeResponse.code !== HttpStatus.CREATED) {
    throw new Error(mergeResponse.message || 'Failed to process existing file');
  }

  // 响应 data 局部映射（Infrastructure 已归一为 camelCase 出口）
  const mergeData: MergeChunksData = mergeResponse.data || {};

  fileTask.audioId = mergeData.audioId;
  const cnt = mergeData.testCaseCount;
  if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;

  if (tcConfig?.rounds && fileTask.audioId) {
    const realName = mergeData.name || fileTask.name;
    for (const r of tcConfig.rounds) {
      if (!r.audios) continue;
      for (const a of r.audios) {
        // 回填音频 ID（camelCase，与消费方 useTestCaseAudioPreview 读取一致）
        if (a.audioName === fileTask.name || a.audioName === realName) {
          a.audioId = fileTask.audioId;
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
  const presignResponse = await audiosPort.presignUpload({
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

  // 秒传命中：响应 data 已由 Infrastructure 归一为 camelCase
  if (presignResponse.data?.instantUpload) {
    fileTask.audioId = presignResponse.data.audioId;
    fileTask.status = UploadStatusEnum.COMPLETED;
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
    if ((uploadStatus.value as string) === UploadStatusEnum.PAUSED || (uploadStatus.value as string) === UploadStatusEnum.STOPPED) {
      fileTask.status = uploadStatus.value === UploadStatusEnum.PAUSED ? UploadStatusEnum.PAUSED : UploadStatusEnum.STOPPED;
      throw new Error(`Upload ${fileTask.status}`);
    }

    let partUrl: string;
    if (i < presignedParts.length) {
      partUrl = presignedParts[i].url;
    } else {
      const partResp = await audiosPort.presignPart({
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
    // 预签名 URL 直传 OSS，非业务 API，无需 JWT
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
    const completeResp = await audiosPort.completeDirectUpload({
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

    if (completeResp.code !== undefined && completeResp.code !== 0 && completeResp.code !== HttpStatus.OK) {
      throw new Error(completeResp.message || '直传完成失败');
    }
    fileTask.audioId = completeResp.data?.audioId;

    if (tcConfig?.rounds?.length || options.createTestCase) {
      await processMergeForExistingFile(ctx, taskId, fileTask, options, tcConfig);
    }
  } else {
    const mergeResponse = await audiosPort.mergeChunks(fileTask.fileId, taskId, {
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

    if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== HttpStatus.OK && mergeResponse.code !== HttpStatus.CREATED) {
      throw new Error(mergeResponse.message || 'Failed to merge chunks');
    }

    // 响应 data 局部映射（Infrastructure 已归一为 camelCase 出口）
    const mergeData: MergeChunksData = mergeResponse.data || {};

    fileTask.audioId = mergeData.audioId;
    const cnt = mergeData.testCaseCount;
    if (typeof cnt === 'number' && cnt > 0) generatedTestCaseTotal.value += cnt;
    if (tcConfig?.rounds && fileTask.audioId) {
      const realName = mergeData.name || fileTask.name;
      for (const r of tcConfig.rounds) {
        if (!r.audios) continue;
        for (const a of r.audios) {
          // 回填音频 ID（camelCase，与消费方 useTestCaseAudioPreview 读取一致）
          if (a.audioName === fileTask.name || a.audioName === realName) {
            a.audioId = fileTask.audioId;
          }
        }
      }
    }
  }
}
