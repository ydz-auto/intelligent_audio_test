import type { Ref } from 'vue';
import type { AudioUploadOptions } from '../../shared/types';
import type { UploadProcessContext } from './uploadProcess';

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
  (uploadOptions as any).dimensions = [
    ...expandDims(options?.apiDimensions || [], 'api', apiScopes),
    ...expandDims(options?.e2eDimensions || [], 'e2e', e2eScopes),
    ...(Array.isArray(options?.dimensions) ? options.dimensions : [])
  ];
}

/**
 * 从模态框数据更新上传选项
 */
export function updateUploadOptionsFromModal(
  uploadOptions: AudioUploadOptions,
  data: any
): void {
  const options = (data && typeof data === 'object' && data.options && typeof data.options === 'object')
    ? data.options
    : ((data && typeof data === 'object' && data.config && typeof data.config === 'object') ? data.config : data);

  if (options?.audioType !== undefined) uploadOptions.audio_type = options.audioType;
  if (options?.createTestCase !== undefined) uploadOptions.create_test_case = options.createTestCase;
  if (data?.tags !== undefined) uploadOptions.tags = data.tags;
  if (options?.testTypes !== undefined) uploadOptions.test_types = options.testTypes;
  if (options?.playbackDeviceId !== undefined) (uploadOptions as any).playback_device_id = options.playbackDeviceId;
  if (options?.defaultSpl !== undefined) (uploadOptions as any).spl = options.defaultSpl;
  if (options?.groupNameType !== undefined) (uploadOptions as any).group_name_type = options.groupNameType;
  if (options?.customGroupName !== undefined) (uploadOptions as any).custom_group_name = options.customGroupName;
  if (options?.inheritTags !== undefined) uploadOptions.inherit_tags = options.inheritTags;
  expandDimensions(uploadOptions, options);
  if (options?.noiseAudioId !== undefined) (uploadOptions as any).noise_audio_id = options.noiseAudioId;
  if (options?.noiseSpl !== undefined) (uploadOptions as any).noise_spl = options.noiseSpl;
  if (options?.algorithmType !== undefined) uploadOptions.algorithm_type = options.algorithmType;
  if (options?.algorithmRelations !== undefined) uploadOptions.algorithm_relations = options.algorithmRelations;
  if (options?.algorithmParams !== undefined) uploadOptions.algorithm_params = options.algorithmParams;
  if (data?.algorithmRelations !== undefined) uploadOptions.algorithm_relations = data.algorithmRelations;
}
