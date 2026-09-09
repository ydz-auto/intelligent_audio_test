/**
 * useEvaluationDimensions —— 表单字段定义与校验
 *
 * 负责维度表单的字段动态定义（evaluationFields，含条件显示常量）与必填字段校验。
 */
import { computed } from 'vue';
import type { EvalDimensionState } from './useEvaluationDimensions.state';
import {
  NEW_CATEGORY_FLAG,
  DIMENSION_TYPE_MAIN,
  DIMENSION_TYPE_SUB,
  DEFAULT_LLM_MAX_TOKENS,
  DEFAULT_LLM_TEMPERATURE,
  DEFAULT_MAX_PROCESS,
  DEFAULT_MAX_TIMEOUT,
  DEFAULT_MAX_AUDIO_DURATION,
} from './useEvaluationDimensions.constants';

/** 创建维度表单字段定义与校验模块 */
export function createEvalDimensionForm(state: EvalDimensionState) {
  const { categories, dimensions, algorithms } = state;

  // 条件显示常量：仅主维度显示
  const CONDITION_MAIN = { field: 'dimensionType', value: DIMENSION_TYPE_MAIN };
  // 条件显示常量：仅子维度显示
  const CONDITION_SUB = { field: 'dimensionType', value: DIMENSION_TYPE_SUB };
  // 条件显示常量：新建分类时显示
  const CONDITION_NEW_CATEGORY = { field: 'categoryId', value: NEW_CATEGORY_FLAG };
  // 条件显示常量：LLM Judge 类型时显示
  const CONDITION_LLM_JUDGE = { field: 'resultType', value: 'llm_judge' };

  const evaluationFields = computed(() => [
    { key: 'id', type: 'hidden' },
    { key: 'name', label: '维度名称', type: 'text', required: true, placeholder: '请输入维度名称', group: '基本信息' },
    { key: 'description', label: '描述', type: 'textarea', rows: 3, placeholder: '请输入维度描述', group: '基本信息' },
    { key: 'type', label: '评估类型', type: 'select', required: true, options: [
      { value: 'auto', label: '自动评估' },
      { value: 'manual', label: '人工评估' }
    ], group: '基本信息' },
    { key: 'categoryId', label: '所属分类', type: 'select', required: false, options: [
      { value: '', label: '请选择分类' },
      { value: NEW_CATEGORY_FLAG, label: '+ 新建分类' },
      ...categories.value.map(c => ({ value: c.id, label: c.name }))
    ], group: '基本信息' },
    { key: 'newCategoryName', label: '新分类名称', type: 'text', required: false, placeholder: '输入新分类名称', conditional: CONDITION_NEW_CATEGORY, group: '基本信息' },
    { key: 'dimensionType', label: '维度类型', type: 'select', required: true, options: [
      { value: DIMENSION_TYPE_MAIN, label: '主维度' },
      { value: DIMENSION_TYPE_SUB, label: '子维度' }
    ], defaultValue: DIMENSION_TYPE_MAIN, group: '层级配置' },
    { key: 'parentDimensionId', label: '所属主维度', type: 'select', required: false, options: [
      { value: '', label: '请选择所属主维度' },
      ...dimensions.value.filter(d => d.dimensionType === DIMENSION_TYPE_MAIN || !d.dimensionType).map(d => ({
        value: d.id,
        label: d.name,
        taskTypeCode: d.taskTypeCode,
        apiSettings: d.apiSettings,
        requiredInputs: d.requiredInputs || [],
        outputFields: d.outputFields || []
      }))
    ], conditional: CONDITION_SUB, group: '层级配置' },
    { key: 'parentApiInfo', label: '继承API配置', type: 'info', conditional: CONDITION_SUB,
      helpText: '子维度将自动使用父维度的API配置，无需手动配置', group: '层级配置' },
    { key: 'taskTypeCode', label: '评估任务关键字', type: 'text', placeholder: '如: wer, asr, translation 等', helpText: '调用API时使用的任务关键字', group: '层级配置',
      conditional: CONDITION_MAIN },
    { key: 'apiUrl', label: 'Master入口URL', type: 'text', required: false, placeholder: '请输入Master调度节点URL (分布式架构必填)', group: 'API配置',
      conditional: CONDITION_MAIN },
    { key: 'scoreUnit', label: '分数单位', type: 'text', required: false, placeholder: '如: %, 分, 秒等', group: '结果配置' },
    { key: 'resultType', label: '结果类型', type: 'select', required: true, options: [
      { value: 1, label: '数值 (1)' },
      { value: 2, label: '布尔 (2)' },
      { value: 3, label: '文本 (3)' },
      { value: 'llm_judge', label: 'LLM Judge' }
    ], group: '结果配置' },
    { key: 'llmJudgeConfig', label: 'LLM Judge 配置', type: 'object', required: false, group: '结果配置',
      conditional: CONDITION_LLM_JUDGE,
      fields: [
        { key: 'model', label: '模型', type: 'text', required: true, placeholder: '如: gpt-4, qwen-max' },
        { key: 'promptTemplate', label: 'Prompt 模板', type: 'textarea', required: true, placeholder: '输入评估 prompt 模板，可使用 {{asr_result}} {{asr_ref}} 等变量' },
        { key: 'maxTokens', label: '最大 Token 数', type: 'number', required: false, min: 1, max: 8192, default: DEFAULT_LLM_MAX_TOKENS },
        { key: 'temperature', label: 'Temperature', type: 'number', required: false, min: 0, max: 2, step: 0.1, default: DEFAULT_LLM_TEMPERATURE }
      ]
    },
    { key: 'resultMin', label: '结果最小值', type: 'number', required: true, group: '结果配置' },
    { key: 'resultMax', label: '结果最大值', type: 'number', required: true, group: '结果配置' },
    { key: 'decimalPlaces', label: '小数位数', type: 'number', required: true, min: 0, max: 4, group: '结果配置' },
    { key: 'weight', label: '权重', type: 'number', required: true, min: 1, max: 10, group: '结果配置' },
    { key: 'estimatedExecTime', label: '预计执行时间(s)', type: 'number', required: true, min: 1, group: '结果配置' },
    { key: 'rule', label: '评分规则', type: 'ruleEditor', required: false, fullWidth: true, group: '结果配置' },
    { key: 'apiSettings', label: 'API设置', type: 'apiSettingsEditor', required: false, fullWidth: true, group: 'API配置',
      conditional: CONDITION_MAIN },
    { key: 'requiredInputs', label: '所需输入配置', type: 'requiredInputs', required: false, fullWidth: true, group: 'API配置',
      helpText: '配置当前维度所需的输入参数；子维度默认继承父维度配置，可按需调整。' },
    { key: 'outputFields', label: '输出字段配置', type: 'outputFields', required: false, fullWidth: true, group: 'API配置',
      helpText: '配置当前维度的结果提取字段及聚合角色。' },
    { key: 'statisticMethod', label: '统计方式', type: 'select', required: false, default: 'average', group: 'API配置',
      options: [
        { value: 'average', label: '简单平均' },
        { value: 'weighted_wer', label: '加权WER (Σ分子/Σ分母)' }
      ],
      conditional: CONDITION_MAIN },
    { key: 'apiEndpoints', label: 'API端点配置', type: 'array', arrayItemType: 'apiEndpoint', required: false, fullWidth: true, arrayItemTemplate: { url: '', name: '', priority: 1, maxProcess: DEFAULT_MAX_PROCESS, maxTimeout: DEFAULT_MAX_TIMEOUT, maxAudioDuration: DEFAULT_MAX_AUDIO_DURATION }, group: 'API配置',
      conditional: CONDITION_MAIN },
    { key: 'associatedAlgorithms', label: '关联算法', type: 'multi-select-tags', required: false, options: algorithms.value.length > 0 ? algorithms.value : [
      { value: 'asr', label: 'ASR语音识别' },
      { value: 'translation', label: '翻译' },
      { value: 'tts', label: 'TTS语音合成' },
      { value: 'speaker_recognition', label: '说话人识别' },
      { value: 'noise_reduction', label: '降噪' },
      { value: 'vad', label: '语音活动检测' }
    ], placeholder: '选择关联的算法类型', group: '关联算法', conditional: CONDITION_MAIN },
    { key: 'status', label: '状态', type: 'switch', default: true, group: '基础信息' }
  ]);

  // 校验必填字段，返回缺失字段标签列表
  function validateRequiredFields(dimensionData: any): string[] {
    const missingFields: string[] = [];
    evaluationFields.value.forEach(field => {
      if (!field.required) return;
      const value = dimensionData[field.key];
      if (field.type === 'textarea') {
        // 对于JSON格式的textarea字段，不在这里验证JSON格式，而是在后面专门处理
        if (value === undefined || value === null || value === '') {
          missingFields.push(field.label);
        }
      } else if (value === undefined || value === null || value === '') {
        missingFields.push(field.label);
      } else if (field.type === 'array') {
        if (Array.isArray(value) && value.length === 0) {
          missingFields.push(field.label);
        } else if (Array.isArray(value)) {
          value.forEach((item: any, index: number) => {
            if (field.arrayItemType === 'apiEndpoint') {
              // 只有当API端点字段是必填时，才验证URL是否为空
              const hasUrl = (item.url && item.url.trim() !== '') || (item.endpoint && item.endpoint.trim() !== '');
              if (field.required && !hasUrl) {
                missingFields.push(`${field.label}[${index + 1}]的URL`);
              }
            }
          });
        }
      }
    });
    return missingFields;
  }

  return {
    evaluationFields,
    validateRequiredFields,
  };
}

/** 表单字段定义与校验模块类型（由工厂推断） */
export type EvalDimensionFormModule = ReturnType<typeof createEvalDimensionForm>;
