import type { Ref } from 'vue';
import type { AudioUploadOptions } from '../../domain';
import type { UploadProcessContext } from './uploadProcess';
import { TestType } from '@/domain/enums';

/**
 * 文件拖拽上传与上传选项工具
 */

export interface FilePickContext extends UploadProcessContext {
  selectedFilesForUpload: Ref<File[]>;
  startUploadProcess: (
    ctx: UploadProcessContext,
    files: any[],
    folderGroupMappings?: Record<string, string>,
    unifiedRoundsByGroup?: Record<string, any>,
    testCaseGroupsData?: Record<string, any>,
    onUploadComplete?: () => void
  ) => Promise<void>;
}

export async function handleDrop(
  ctx: FilePickContext,
  e: DragEvent
) {
  e.preventDefault();
  const files = e.dataTransfer?.files;
  if (files && files.length > 0) {
    ctx.selectedFilesForUpload.value = Array.from(files);
    await ctx.startUploadProcess(ctx, ctx.selectedFilesForUpload.value);
  }
}

export async function pickFiles(
  ctx: FilePickContext,
  onUploadComplete?: () => void
) {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.accept = 'audio/*';
  input.onchange = async (e: any) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      ctx.selectedFilesForUpload.value = Array.from(files);
      await ctx.startUploadProcess(ctx, ctx.selectedFilesForUpload.value, undefined, undefined, undefined, onUploadComplete);
    }
  };
  input.click();
}

/**
 * 维度展开工具：将 API/E2E 维度按 scope 展开
 * 从 options 读取 scopes/dimensions，写入 uploadOptions.dimensions
 */
export function expandDimensions(uploadOptions: AudioUploadOptions, options: any): void {
  const apiScopes: ('single' | 'multi')[] = (options as any)?.apiScopes || ['single'];
  const e2eScopes: ('single' | 'multi')[] = (options as any)?.e2eScopes || ['single'];
  // camelCase 域模型（testType/roundScope）；上行 snake_case 化在 audiosApi 出口 toEvaluationDimensionDto
  const expandDims = (dims: any[], tt: string, scopes: ('single' | 'multi')[]) => {
    if (!dims || dims.length === 0) return [];
    const result: any[] = [];
    for (const d of dims) {
      for (const scope of scopes) {
        result.push({ ...d, testType: tt, roundScope: scope });
      }
    }
    return result;
  };
  (uploadOptions as any).dimensions = [
    ...expandDims(options?.apiDimensions || [], TestType.API, apiScopes),
    ...expandDims(options?.e2eDimensions || [], TestType.E2E, e2eScopes),
    ...(Array.isArray(options?.dimensions) ? options.dimensions : [])
  ];
}

/**
 * 从模态框数据更新上传选项
 * 模态框输入为 camelCase，AudioUploadOptions 本地状态为 camelCase（W1-D 起）
 */
export function updateUploadOptionsFromModal(
  uploadOptions: AudioUploadOptions,
  data: any
): void {
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
  expandDimensions(uploadOptions, options);
  if (options?.noiseAudioId !== undefined) uploadOptions.noiseAudioId = options.noiseAudioId;
  if (options?.noiseSpl !== undefined) uploadOptions.noiseSpl = options.noiseSpl;
  if (options?.algorithmType !== undefined) uploadOptions.algorithmType = options.algorithmType;
  if (options?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = options.algorithmRelations;
  if (options?.algorithmParams !== undefined) uploadOptions.algorithmParams = options.algorithmParams;
  if (data?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = data.algorithmRelations;
}
