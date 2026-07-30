import { ref } from 'vue';
import { algorithmApi } from '../../utils/api';
import { extractParamsFromAnnotations } from '../../utils/audioUtils';
import { stripAlgorithmParamSchema } from '../../utils/utils';
import type { TestCaseConfig } from '../../utils/folderParser';
import type { AudioUploadFile } from '../../shared/types';

/**
 * 算法参数处理组合式函数
 *
 * 职责：
 * - 获取算法选项列表
 * - 按 algorithmType 缓存 CaseAlgorithmParam 配置
 * - 从标注 JSON 解析参数并合并到 normalizedAlgorithmParams
 * - 多轮模式下将参数分发到 tcConfig.algorithm_params 对应 round
 */
export function useAlgorithmParams() {
  const algorithmOptions = ref<{ value: string; name: string }[]>([]);
  const selectedAlgorithmType = ref<string>('');
  const algorithmParams = ref<any[]>([]);

  // CaseAlgorithmParam 配置缓存（按 algorithmType 缓存，避免每次上传都请求）
  const caseParamConfigCache = ref<Record<string, any[]>>({});

  /**
   * 获取所有可用算法选项
   */
  async function fetchAlgorithmOptions() {
    try {
      const response = await fetch('/api/v1/algorithm/options');
      const result = await response.json();
      if (result.success && result.data && result.data.algorithms) {
        algorithmOptions.value = result.data.algorithms.map((a: any) => ({
          value: a.value,
          name: a.name
        }));
      } else {
        algorithmOptions.value = [];
      }
    } catch (e) {
      console.error('Fetch algorithm options failed:', e);
      algorithmOptions.value = [];
    }
  }

  /**
   * 获取 CaseAlgorithmParam 配置（带缓存）
   */
  async function getCaseParams(algorithmType: string): Promise<any[]> {
    if (!algorithmType) return [];

    // 检查缓存
    if (caseParamConfigCache.value[algorithmType]) {
      return caseParamConfigCache.value[algorithmType];
    }

    try {
      const res = await algorithmApi.getCaseParams(algorithmType);
      const caseParams = res?.parameters || [];
      caseParamConfigCache.value[algorithmType] = caseParams;
      return caseParams;
    } catch (e) {
      console.warn('[getCaseParams] 获取用例参数配置失败:', e);
      return [];
    }
  }

  /**
   * 从标注 JSON 按用例参数配置提取参数，合并到 normalizedAlgorithmParams
   * 前端解析，用户可预览/修改解析结果。后端不再做解析。
   */
  async function resolveAlgorithmParamsFromAnnotations(
    algorithmType: string | undefined,
    annotations: any[] | undefined,
    existingParams: any[] | undefined
  ): Promise<any[]> {
    // 基础参数：把现有 params 归一化为 [{field_code, field_value}]，剔除 schema 定义
    let result: any[] = stripAlgorithmParamSchema(existingParams);

    if (!algorithmType || !annotations || annotations.length === 0) return result;

    const caseParams = await getCaseParams(algorithmType);
    if (!caseParams || caseParams.length === 0) return result;

    // 从标注 JSON 提取参数
    const extracted = extractParamsFromAnnotations(annotations, caseParams, algorithmType);

    // 合并：提取到的非 null 值覆盖已有的 null/undefined 值；已有的真实值保留；没有的追加
    for (const p of extracted) {
      if (!p.field_code) continue;
      const idx = result.findIndex(r => r.field_code === p.field_code);
      if (idx === -1) {
        // 没有该参数，追加
        result.push(p);
      } else if (result[idx].field_value === null || result[idx].field_value === undefined) {
        // 已有但是 null/undefined，用提取到的值覆盖（提取到的非空值才有意义）
        if (p.field_value !== null && p.field_value !== undefined) {
          result[idx].field_value = p.field_value;
        }
      }
      // 已有非空值则保留，不覆盖
    }

    return result;
  }

  /**
   * 多轮模式：把当前文件的标注解析参数分发到 tcConfig.algorithm_params（按轮分组）里匹配的 round
   * - 每个 round 按 audio_name 匹配当前 fileTask
   * - 匹配到的 round：从 fileTask.annotations 解析参数，合并到 tcConfig.algorithm_params 中对应 round_number 的 entry.params
   * - 新设计：algorithmParams 不再存于 config.rounds[]，而是作为 test_cases.algorithm_params 独立列，按轮分组
   * - 单轮多音频模式：多个音频可能匹配同一个 round，参数合并到同一 entry
   */
  async function dispatchParamsToRounds(
    tcConfig: TestCaseConfig | undefined,
    algorithmType: string | undefined,
    fileTask: AudioUploadFile,
    _options: any
  ): Promise<void> {
    if (!tcConfig?.rounds || !algorithmType) return;
    const annotations = fileTask.annotations || [];
    if (annotations.length === 0) return;

    const caseParams = await getCaseParams(algorithmType);
    if (!caseParams || caseParams.length === 0) return;

    // 从当前文件标注解析参数
    const extracted = extractParamsFromAnnotations(annotations, caseParams, algorithmType);

    // 初始化按轮分组的 algorithm_params（独立列，不再写 round.algorithmParams）
    if (!Array.isArray(tcConfig.algorithm_params)) {
      tcConfig.algorithm_params = [];
    }

    // 遍历 rounds，按 audio_name 判断归属，把解析结果分发到匹配 round_number 的 entry.params
    for (const round of tcConfig.rounds) {
      if (!round.audios) continue;
      // 当前 fileTask 是否属于这个 round（按 audio_name 匹配）
      const belongsToRound = round.audios.some((a: any) => a.audio_name === fileTask.name);
      if (!belongsToRound) continue;

      const roundNumber = round.roundNumber ?? 1;
      // 找到匹配 round_number 的 entry
      let entry = tcConfig.algorithm_params.find((e: any) => e.round_number === roundNumber);
      if (!entry) {
        // 没有匹配的 entry，创建一条并追加
        entry = { round_number: roundNumber, params: [] };
        tcConfig.algorithm_params.push(entry);
      }
      if (!Array.isArray(entry.params)) {
        entry.params = [];
      }
      const existingCodes = new Set(entry.params.map((p: any) => p.field_code ?? p.fieldCode));
      for (const p of extracted) {
        if (p.field_code && !existingCodes.has(p.field_code)) {
          entry.params.push(p);
          existingCodes.add(p.field_code);
        }
      }
    }
  }

  return {
    // 状态
    algorithmOptions,
    selectedAlgorithmType,
    algorithmParams,
    // 方法
    fetchAlgorithmOptions,
    getCaseParams,
    resolveAlgorithmParamsFromAnnotations,
    dispatchParamsToRounds,
  };
}
