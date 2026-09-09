import type { Ref } from 'vue';
import type { AudioUploadOptions, DimensionConfigData, SelectedEvaluationDimension } from '../../domain';
import type { UploadProcessContext } from './uploadProcess';
import { TestType, RoundMode } from '@/domain/enums';

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
 * 单个维度配置块展开：按 roundMode 三分支
 * - all：所有轮次统一维度，不携带 roundNumber（后端按全轮次生效）
 * - specific：指定轮次共享同一组维度，每个轮次各生成一条 round_number
 * - per_round：逐轮独立维度，roundDimensions 按 roundNumber → 维度列表展开
 * 多轮整体评估（multiDimensions）始终 roundScope=multi，与轮次无关
 * 输出 camelCase 域模型；上行 snake_case 化统一在 audiosApi 出口 toEvaluationDimensionDto
 */
function expandDimensionConfig(
  cfg: DimensionConfigData | undefined,
  testType: typeof TestType[keyof typeof TestType]
): SelectedEvaluationDimension[] {
  if (!cfg) return [];
  const result: SelectedEvaluationDimension[] = [];

  if (cfg.roundMode === RoundMode.PER_ROUND) {
    const roundDimensions = cfg.roundDimensions || {};
    for (const roundKey of Object.keys(roundDimensions)) {
      const roundNumber = Number(roundKey);
      for (const d of roundDimensions[roundNumber] || []) {
        result.push({ ...d, testType, roundScope: 'single', roundNumber });
      }
    }
  } else {
    const dimensions = cfg.dimensions || [];
    const roundNumbers = cfg.roundNumbers || [];
    for (const d of dimensions) {
      if (cfg.roundMode === RoundMode.SPECIFIC && roundNumbers.length > 0) {
        for (const roundNumber of roundNumbers) {
          result.push({ ...d, testType, roundScope: 'single', roundNumber });
        }
      } else {
        result.push({ ...d, testType, roundScope: 'single' });
      }
    }
  }

  for (const d of cfg.multiDimensions || []) {
    result.push({ ...d, testType, roundScope: 'multi' });
  }
  return result;
}

/**
 * 维度展开工具：将 API/E2E 维度配置（DimensionConfigData）展开为评估维度列表
 * 从 options 读取 apiDimensionConfig/e2eDimensionConfig，写入 uploadOptions.dimensions
 * 兼容旧结构 apiDimensions/e2eDimensions + apiScopes/e2eScopes（展开为 all 模式等价物）
 */
export function expandDimensions(uploadOptions: AudioUploadOptions, options: any): void {
  const expandLegacy = (dims: any[], testType: typeof TestType[keyof typeof TestType], scopes: ('single' | 'multi')[]) => {
    if (!dims || dims.length === 0) return [];
    const result: SelectedEvaluationDimension[] = [];
    for (const d of dims) {
      for (const scope of scopes) {
        result.push({ ...d, testType, roundScope: scope });
      }
    }
    return result;
  };
  (uploadOptions as any).dimensions = [
    ...expandDimensionConfig(options?.apiDimensionConfig, TestType.API),
    ...expandDimensionConfig(options?.e2eDimensionConfig, TestType.E2E),
    ...expandLegacy(options?.apiDimensions || [], TestType.API, options?.apiScopes || ['single']),
    ...expandLegacy(options?.e2eDimensions || [], TestType.E2E, options?.e2eScopes || ['single']),
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
