import { useModalControl } from './useModal';
import { MODAL_TYPES } from '../shared/types';
import { evaluationApi } from '../utils/api';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估模态框管理组合式函数
 *
 * 职责：
 * - 打开新增维度模态框（openAddModal）
 * - 打开编辑维度模态框（openEditModal）
 * - 打开 API 设置 / 规则编辑器模态框（openAPISettingsModal / openRuleEditorModal）
 * - 保存 API 设置（saveAPISettings）
 * - 关闭模态框（closeModal）
 *
 * 依赖维度模块：dimensions、evaluationFields、dimensionTemplate、saveDimension、apiSettings、loading
 */

export function useEvaluationModals(dimensionsModule: UseEvaluationDimensionsReturn) {
  const modalManager = useModalControl();

  const {
    loading,
    dimensions,
    dimensionTemplate,
    evaluationFields,
    saveDimension,
    apiSettings,
  } = dimensionsModule;

  // ========== 编辑维度模态框 ==========
  function openEditModal(id: number | string) {
    const dimension = dimensions.value.find(dim => dim.id === id);
    if (dimension) {
      const rawEndpoints = dimension.apiEndpoints || (dimension as any).api_endpoints || [];
      const apiEndpoints = Array.isArray(rawEndpoints) ? rawEndpoints.map(ep => ({
        url: ep.url || ep.endpoint || '',
        name: ep.name || '',
        priority: ep.priority || 1,
        maxProcess: ep.maxProcess || ep.max_process || 5,
        maxTimeout: ep.maxTimeout || ep.max_timeout || 30,
        maxAudioDuration: ep.maxAudioDuration || ep.max_audio_duration || 60
      })) : [];

      if (apiEndpoints.length === 0) {
        apiEndpoints.push({ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 });
      }

      const apiUrl = dimension.apiUrl || (dimension as any).api_url || '';
      const rawApiSettings = dimension.apiSettings || (dimension as any).api_settings;
      // 使用 any 类型以兼容动态 body_template.rounds 结构
      let apiSettingsObj: any = { method: 'POST', headers: {}, body_template: {}, timeout: 30000 };
      if (rawApiSettings) {
        if (typeof rawApiSettings === 'object') {
          apiSettingsObj = { ...apiSettingsObj, ...rawApiSettings };
        } else {
          try {
            const parsed = JSON.parse(rawApiSettings);
            apiSettingsObj = { ...apiSettingsObj, ...parsed };
          } catch (e) {
            console.error('Parse apiSettings failed:', e);
          }
        }
      }

      const rawRequiredInputs = dimension.requiredInputs || (dimension as any).required_inputs || [];
      const requiredInputsArray = Array.isArray(rawRequiredInputs) ? rawRequiredInputs : [];
      const requiredInputsObj = requiredInputsArray;

      if (apiSettingsObj.body_template) {
        // 对齐 rounds 内的字段
        if (apiSettingsObj.body_template.rounds && Array.isArray(apiSettingsObj.body_template.rounds)) {
          const roundTpl = apiSettingsObj.body_template.rounds[0] || {};
          const requiredInputKeys = new Set(
            requiredInputsArray.map((input: any) => input.param_code || input.key).filter(Boolean)
          );
          Object.keys(roundTpl).forEach(key => {
            if (!requiredInputKeys.has(key)) {
              delete roundTpl[key];
            }
          });
          requiredInputsArray.forEach((input: any) => {
            const inputKey = input.param_code || input.key;
            if (inputKey && !roundTpl[inputKey]) {
              roundTpl[inputKey] = `{{${inputKey}}}`;
            }
          });
          apiSettingsObj.body_template.rounds[0] = roundTpl;
        }
      }

      const rawRule = dimension.rule;
      let ruleObj = { rules: [], defaultScore: 0 };
      if (rawRule) {
        if (typeof rawRule === 'object') {
          ruleObj = { ...ruleObj, ...rawRule };
        } else if (typeof rawRule === 'string' && rawRule.trim()) {
          try {
            ruleObj = { ...ruleObj, ...JSON.parse(rawRule) };
          } catch (e) {
            console.error('Parse rule failed:', e);
          }
        }
      }

      // 处理 associatedAlgorithms - 将对象数组转换为字符串数组
      const rawAssociatedAlgorithms = dimension.associatedAlgorithms || (dimension as any).associated_algorithms || [];
      let associatedAlgorithmsArray = [];
      if (Array.isArray(rawAssociatedAlgorithms)) {
        if (rawAssociatedAlgorithms.length > 0 && typeof rawAssociatedAlgorithms[0] === 'object') {
          // 如果是对象数组，提取 algorithmType (驼峰格式，由后端 schema 转换)
          associatedAlgorithmsArray = rawAssociatedAlgorithms.map((item: any) => item.algorithmType);
        } else {
          // 如果已经是字符串数组，直接使用
          associatedAlgorithmsArray = rawAssociatedAlgorithms;
        }
      }

      const rawDimensionType = dimension.dimensionType || 'main';
      const dimensionType = (rawDimensionType === 'main' || rawDimensionType === 'sub') ? rawDimensionType : 'main';
      const parentDimensionId = dimension.parentDimensionId || (dimension as any).parent_dimension_id || '';

      // 处理 llmJudgeConfig
      const rawLlmJudgeConfig = dimension.llmJudgeConfig || (dimension as any).llm_judge_config;
      const llmJudgeConfig = rawLlmJudgeConfig
        ? {
            model: rawLlmJudgeConfig.model || '',
            promptTemplate: rawLlmJudgeConfig.promptTemplate || rawLlmJudgeConfig.prompt_template || '',
            maxTokens: rawLlmJudgeConfig.maxTokens || rawLlmJudgeConfig.max_tokens || 1024,
            temperature: rawLlmJudgeConfig.temperature ?? 0.7
          }
        : {
            model: '',
            promptTemplate: '',
            maxTokens: 1024,
            temperature: 0.7
          };

      const rawOutputFields = (dimension as any).outputFields || (dimension as any).output_fields || [];
      const outputFieldsArray = Array.isArray(rawOutputFields) ? rawOutputFields : [];
      const statisticMethod = (dimension as any).statisticMethod || (dimension as any).statistic_method || 'average';

      const editingData = {
        ...dimension,
        categoryId: dimension.categoryId || (dimension as any).category_id,
        apiEndpoints,
        apiUrl,
        apiSettings: apiSettingsObj,
        rule: ruleObj,
        requiredInputs: requiredInputsObj,
        outputFields: outputFieldsArray,
        statisticMethod: statisticMethod,
        associatedAlgorithms: associatedAlgorithmsArray,
        status: String(dimension.status).toLowerCase() === 'true',
        dimensionType: dimensionType,
        parentDimensionId: parentDimensionId,
        taskTypeCode: dimension.taskTypeCode || (dimension as any).task_type_code || '',
        llmJudgeConfig: llmJudgeConfig
      };

      modalManager.open(MODAL_TYPES.CRUD_FORM, {
        mode: 'edit',
        entityName: '评估维度',
        width: '1400px',
        fields: evaluationFields.value,
        formData: editingData,
        onSave: async (result: any) => {
          console.log('[Evaluation] openEditModal onSave result:', JSON.stringify(result, null, 2));
          const payload = result.data || result;
          console.log('[Evaluation] Extracted payload:', JSON.stringify(payload, null, 2));
          await saveDimension(payload, result.mode || 'edit');
        }
      });
    }
  }

  // ========== 新增维度模态框 ==========
  function openAddModal() {
    const formData = {
      name: '',
      description: '',
      type: 'auto',
      categoryId: undefined,
      apiUrl: '',
      scoreUnit: '',
      apiSettings: {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body_template: {
          rounds: [
            {
              asr_ref: "{{asr_ref}}",
              output_text: "{{output_text}}"
            }
          ]
        },
        timeout: 30000
      },
      resultType: 1,
      resultMin: 0,
      resultMax: 100,
      decimalPlaces: 2,
      weight: 5,
      estimatedExecTime: 5,
      status: true,
      rule: { ...dimensionTemplate.rule },
      requiredInputs: [...dimensionTemplate.requiredInputs],
      outputFields: [],
      statisticMethod: 'average',
      apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 }],
      associatedAlgorithms: [],
      llmJudgeConfig: {
        model: '',
        promptTemplate: '',
        maxTokens: 1024,
        temperature: 0.7
      }
    };

    console.log('[Evaluation] openAddModal formData:', JSON.stringify(formData, null, 2));

    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      mode: 'add',
      entityName: '评估维度',
      width: '1400px',
      fields: evaluationFields.value,
      formData,
      onSave: async (result: any) => {
        console.log('[Evaluation] openAddModal onSave result:', JSON.stringify(result, null, 2));
        const payload = result.data || result;
        console.log('[Evaluation] Extracted payload:', JSON.stringify(payload, null, 2));
        const saveType = result.mode === 'create' ? 'add' : result.mode;
        await saveDimension(payload, saveType);
      }
    });
  }

  // ========== API 设置模态框 ==========
  function openAPISettingsModal(id: number | string) {
    modalManager.open(MODAL_TYPES.API_OTHER_CONFIG, {
      title: 'API设置',
      dimensionId: id,
      onSave: (settings: any) => {
        saveAPISettings(settings);
      }
    });
  }

  // ========== 规则编辑器模态框 ==========
  function openRuleEditorModal(fieldId: string) {
    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '规则编辑器',
      fieldId: fieldId,
      onSave: (rule: any) => {
        console.log('保存规则:', rule);
      }
    });
  }

  // ========== 保存 API 设置 ==========
  async function saveAPISettings(settings: any) {
    loading.value = true;
    try {
      const apiSettingsData = { ...apiSettings.value, ...settings };

      await evaluationApi.update(apiSettingsData.id, {
        apiSettings: apiSettingsData
      });

      Object.assign(apiSettings.value, apiSettingsData);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: 'API设置已保存',
        onConfirm: () => {
        }
      });
    } catch (err: any) {
      console.error('Failed to save API settings:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `保存API设置失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  // ========== 关闭模态框 ==========
  function closeModal(id: string) {
    modalManager.close(id);
  }

  return {
    openEditModal,
    openAddModal,
    openAPISettingsModal,
    openRuleEditorModal,
    saveAPISettings,
    closeModal,
  };
}

export type UseEvaluationModalsReturn = ReturnType<typeof useEvaluationModals>;
