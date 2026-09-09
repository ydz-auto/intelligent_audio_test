/**
 * useEvaluationDimensions —— 保存前字段规范化处理链
 *
 * 负责维度数据在保存前的逐字段规范化与回填：rule / requiredInputs / outputFields / apiSettings /
 * categoryId（含新建分类回填）/ 子维度继承父维度 / apiEndpoints / associatedAlgorithms / llmJudgeConfig。
 */
import { evaluationPort } from './evaluationPort';
import type { EvalDimensionState } from './useEvaluationDimensions.state';
import {
  NEW_CATEGORY_FLAG,
  DIMENSION_TYPE_SUB,
  DEFAULT_CATEGORY_ICON,
  DEFAULT_LLM_MAX_TOKENS,
  DEFAULT_LLM_TEMPERATURE,
  DEFAULT_MAX_PROCESS,
  DEFAULT_MAX_TIMEOUT,
  DEFAULT_MAX_AUDIO_DURATION,
} from './useEvaluationDimensions.constants';

/** 创建保存前字段规范化处理链模块 */
export function createEvalDimensionNormalizers(state: EvalDimensionState) {
  const { categories, dimensions } = state;

  // 处理 rule 字段：对象转 JSON 字符串，字符串解析后再序列化，空字符串删除
  function normalizeRule(dimensionData: any) {
    if (typeof dimensionData.rule === 'object' && dimensionData.rule !== null) {
      dimensionData.rule = JSON.stringify(dimensionData.rule);
    } else if (typeof dimensionData.rule === 'string' && dimensionData.rule.trim()) {
      try {
        dimensionData.rule = JSON.stringify(JSON.parse(dimensionData.rule));
      } catch (e) {
        throw new Error('评分规则格式不正确，请检查 JSON 格式');
      }
    } else if (typeof dimensionData.rule === 'string') {
      delete dimensionData.rule;
    }
  }

  // 将 requiredInputs 同步到 apiSettings.bodyTemplate.rounds[0]
  function syncRequiredInputsToBodyTemplate(dimensionData: any) {
    if (!Array.isArray(dimensionData.requiredInputs) || dimensionData.requiredInputs.length === 0) return;
    if (!dimensionData.apiSettings) dimensionData.apiSettings = {};
    if (!dimensionData.apiSettings.bodyTemplate) dimensionData.apiSettings.bodyTemplate = {};
    // 确保 bodyTemplate 有 rounds 结构
    if (!dimensionData.apiSettings.bodyTemplate.rounds) {
      dimensionData.apiSettings.bodyTemplate.rounds = [{}];
    }
    const roundTpl = dimensionData.apiSettings.bodyTemplate.rounds[0];

    // 添加 requiredInputs 中缺失的 key
    dimensionData.requiredInputs.forEach((input: any) => {
      // TODO: param_code 为后端原字段名，apiSettings bodyTemplate 透传结构
      const inputKey = input.param_code || input.key;
      if (inputKey && !roundTpl[inputKey]) {
        roundTpl[inputKey] = `{{${inputKey}}}`;
      }
    });
    // 清理 rounds 内不在 requiredInputs 中的 key
    Object.keys(roundTpl).forEach(key => {
      const exists = dimensionData.requiredInputs.some((input: any) => {
        // TODO: param_code 为后端原字段名，apiSettings bodyTemplate 透传结构
        const inputKey = input.param_code || input.key;
        return inputKey === key;
      });
      if (!exists) delete roundTpl[key];
    });
  }

  // 处理 requiredInputs：字符串解析为数组、数组同步 bodyTemplate、其他删除
  function normalizeRequiredInputs(dimensionData: any) {
    if (dimensionData.requiredInputs === undefined) return;
    if (typeof dimensionData.requiredInputs === 'string' && dimensionData.requiredInputs.trim()) {
      try {
        dimensionData.requiredInputs = JSON.parse(dimensionData.requiredInputs);
      } catch (e) {
        throw new Error('所需输入配置格式不正确，请检查 JSON 格式');
      }
    } else if (Array.isArray(dimensionData.requiredInputs)) {
      syncRequiredInputsToBodyTemplate(dimensionData);
    } else {
      delete dimensionData.requiredInputs;
    }
  }

  // 处理 outputFields：字符串解析为数组、非数组删除
  function normalizeOutputFields(dimensionData: any) {
    if (dimensionData.outputFields === undefined) return;
    if (typeof dimensionData.outputFields === 'string' && dimensionData.outputFields.trim()) {
      try {
        dimensionData.outputFields = JSON.parse(dimensionData.outputFields);
      } catch (e) {
        throw new Error('输出字段配置格式不正确，请检查 JSON 格式');
      }
    } else if (!Array.isArray(dimensionData.outputFields)) {
      delete dimensionData.outputFields;
    }
  }

  // 处理 apiSettings：字符串解析为对象、对象保留、其他删除
  function normalizeApiSettings(dimensionData: any) {
    if (dimensionData.apiSettings === undefined) return;
    if (typeof dimensionData.apiSettings === 'string' && dimensionData.apiSettings.trim()) {
      try {
        dimensionData.apiSettings = JSON.parse(dimensionData.apiSettings);
      } catch (e) {
        throw new Error('API设置格式不正确，请检查 JSON 格式');
      }
    } else if (typeof dimensionData.apiSettings === 'object' && dimensionData.apiSettings !== null) {
      // 对象类型直接保留
    } else {
      delete dimensionData.apiSettings;
    }
  }

  // 处理 categoryId：空值转 null、新建分类则创建并回填
  async function resolveCategory(dimensionData: any) {
    if (dimensionData.categoryId === '' || dimensionData.categoryId === undefined) {
      dimensionData.categoryId = null;
    }
    if (dimensionData.categoryId === NEW_CATEGORY_FLAG) {
      if (dimensionData.newCategoryName && dimensionData.newCategoryName.trim()) {
        const newCatName = dimensionData.newCategoryName.trim();
        const existingCat = categories.value.find(c => c.name === newCatName);
        if (existingCat) {
          dimensionData.categoryId = existingCat.id;
        } else {
          const newCat = await evaluationPort.createCategory({
            name: newCatName, description: '', icon: DEFAULT_CATEGORY_ICON
          });
          dimensionData.categoryId = newCat.id;
          categories.value.push({ id: newCat.id, name: newCat.name, description: '', icon: DEFAULT_CATEGORY_ICON });
        }
      } else {
        dimensionData.categoryId = null;
      }
      delete dimensionData.newCategoryName;
    }
  }

  const hasConfiguredList = (value: unknown): boolean =>
    Array.isArray(value) && value.length > 0

  // 子维度继承父维度配置：任务类型、输入输出参数、关联算法、parentDimensionId 空值处理
  function inheritFromParentDimension(dimensionData: any) {
    if (dimensionData.dimensionType !== DIMENSION_TYPE_SUB) {
      // 非 sub 类型，parentDimensionId 空值转 null
      if (dimensionData.parentDimensionId === '' || dimensionData.parentDimensionId === undefined) {
        dimensionData.parentDimensionId = null;
      }
      return;
    }
    const parentDim = dimensions.value.find(d => d.id === dimensionData.parentDimensionId);
    // 自动填充主维度的 taskTypeCode
    if (dimensionData.parentDimensionId && !dimensionData.taskTypeCode && parentDim?.taskTypeCode) {
      dimensionData.taskTypeCode = parentDim.taskTypeCode;
    }
    if (parentDim && !hasConfiguredList(dimensionData.requiredInputs) && hasConfiguredList(parentDim.requiredInputs)) {
      dimensionData.requiredInputs = structuredClone(parentDim.requiredInputs);
    }
    if (parentDim && !hasConfiguredList(dimensionData.outputFields) && hasConfiguredList(parentDim.outputFields)) {
      dimensionData.outputFields = structuredClone(parentDim.outputFields);
    }
    // 继承父维度的关联算法
    if (!dimensionData.associatedAlgorithms || dimensionData.associatedAlgorithms.length === 0) {
      if (parentDim?.associatedAlgorithms && parentDim.associatedAlgorithms.length > 0) {
        dimensionData.associatedAlgorithms = parentDim.associatedAlgorithms.map((item: any) =>
          typeof item === 'string' ? item : item.algorithmType
        );
      }
    }
    // parentDimensionId 空值转 null
    if (dimensionData.parentDimensionId === '' || dimensionData.parentDimensionId === undefined) {
      dimensionData.parentDimensionId = null;
    }
  }

  // 规范化 apiEndpoints：补全默认字段
  function normalizeApiEndpoints(dimensionData: any) {
    if (!Array.isArray(dimensionData.apiEndpoints)) return;
    dimensionData.apiEndpoints = dimensionData.apiEndpoints.map((ep: any) => ({
      ...ep,
      url: ep.url || ep.endpoint || '',
      maxProcess: ep.maxProcess || DEFAULT_MAX_PROCESS,
      maxTimeout: ep.maxTimeout || DEFAULT_MAX_TIMEOUT,
      maxAudioDuration: ep.maxAudioDuration || DEFAULT_MAX_AUDIO_DURATION
    }));
  }

  // 将 associatedAlgorithms 字符串数组转换为 AlgorithmAssociation 格式
  function normalizeAssociatedAlgorithms(dimensionData: any) {
    if (dimensionData.associatedAlgorithms === undefined) {
      dimensionData.associatedAlgorithms = [];
      return;
    }
    if (Array.isArray(dimensionData.associatedAlgorithms)) {
      // 如果是字符串数组，转换为 AlgorithmAssociation 格式
      if (dimensionData.associatedAlgorithms.length > 0 && typeof dimensionData.associatedAlgorithms[0] === 'string') {
        dimensionData.associatedAlgorithms = dimensionData.associatedAlgorithms.map((algoType: string) => ({
          algorithmType: algoType, isDefault: false, weight: 1.0
        }));
      }
    } else {
      dimensionData.associatedAlgorithms = [];
    }
  }

  // 处理 llmJudgeConfig：对象规范化、非对象删除
  function normalizeLlmJudgeConfig(dimensionData: any) {
    if (dimensionData.llmJudgeConfig === undefined) return;
    if (typeof dimensionData.llmJudgeConfig === 'object' && dimensionData.llmJudgeConfig !== null) {
      dimensionData.llmJudgeConfig = {
        model: dimensionData.llmJudgeConfig.model || '',
        promptTemplate: dimensionData.llmJudgeConfig.promptTemplate || '',
        maxTokens: dimensionData.llmJudgeConfig.maxTokens || DEFAULT_LLM_MAX_TOKENS,
        temperature: dimensionData.llmJudgeConfig.temperature ?? DEFAULT_LLM_TEMPERATURE
      };
    } else {
      delete dimensionData.llmJudgeConfig;
    }
  }

  return {
    normalizeRule,
    normalizeRequiredInputs,
    normalizeOutputFields,
    normalizeApiSettings,
    resolveCategory,
    inheritFromParentDimension,
    normalizeApiEndpoints,
    normalizeAssociatedAlgorithms,
    normalizeLlmJudgeConfig,
  };
}

/** 保存前字段规范化处理链模块类型（由工厂推断） */
export type EvalDimensionNormalizers = ReturnType<typeof createEvalDimensionNormalizers>;
