import { useModalControl } from '../modal/useModal';
import { MODAL_TYPES } from '../modal/constants';
import { evaluationPort } from './evaluationPort';
import { getVisibilityPref } from '../visibility/useVisibility';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';
import type { UseEvaluationCategoriesReturn } from './useEvaluationCategories';

/**
 * 评估模态框管理组合式函数
 *
 * 职责：
 * - 打开新增维度模态框（openAddModal）
 * - 打开编辑维度模态框（openEditModal）
 * - 打开新增分类模态框（openAddCategoryModal）
 *
 * 依赖维度模块：dimensions、categories、evaluationFields、dimensionTemplate、saveDimension、loading
 * 依赖分类模块：saveCategory
 */

export function useEvaluationModals(dimensionsModule: UseEvaluationDimensionsReturn, categoriesModule: UseEvaluationCategoriesReturn) {
  const modalManager = useModalControl();

  const {
    loading,
    dimensions,
    categories,
    dimensionTemplate,
    evaluationFields,
    saveDimension,
  } = dimensionsModule;

  const { saveCategory } = categoriesModule;

  // ========== 编辑维度模态框 ==========
  async function openEditModal(id: number | string) {
    try {
      // 列表接口只返回轻量字段，编辑时按需加载完整参数配置。
      const dimension = await evaluationPort.getOne(id);
      if (!dimension) return;
      // Domain 侧为 camelCase：apiEndpoints / maxProcess / maxTimeout / maxAudioDuration
      const rawEndpoints = dimension.apiEndpoints || [];
      const apiEndpoints = Array.isArray(rawEndpoints) ? rawEndpoints.map(ep => ({
        url: ep.url || (ep as any).endpoint || '',
        name: ep.name || '',
        priority: ep.priority || 1,
        maxProcess: ep.maxProcess || 5,
        maxTimeout: ep.maxTimeout || 30,
        maxAudioDuration: ep.maxAudioDuration || 60
      })) : [];

      if (apiEndpoints.length === 0) {
        apiEndpoints.push({ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 });
      }

      // Domain 侧为 camelCase（adapter 已完成 snake_case → camelCase 转换）
      const apiUrl = dimension.apiUrl || '';
      const rawApiSettings = dimension.apiSettings;
      // 使用 any 类型以兼容动态 bodyTemplate.rounds 结构
      let apiSettingsObj: any = { method: 'POST', headers: {}, bodyTemplate: {}, timeout: 30000 };
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

      const rawRequiredInputs = dimension.requiredInputs || [];
      const requiredInputsArray = Array.isArray(rawRequiredInputs) ? rawRequiredInputs : [];
      const requiredInputsObj = requiredInputsArray;

      if (apiSettingsObj.bodyTemplate) {
        // 对齐 rounds 内的字段
        if (apiSettingsObj.bodyTemplate.rounds && Array.isArray(apiSettingsObj.bodyTemplate.rounds)) {
          const roundTpl = apiSettingsObj.bodyTemplate.rounds[0] || {};
          const requiredInputKeys = new Set(
            // TODO: param_code 为后端原字段名，apiSettings bodyTemplate 透传结构
            requiredInputsArray.map((input: any) => input.param_code || input.key).filter(Boolean)
          );
          Object.keys(roundTpl).forEach(key => {
            if (!requiredInputKeys.has(key)) {
              delete roundTpl[key];
            }
          });
          requiredInputsArray.forEach((input: any) => {
            // TODO: param_code 为后端原字段名，apiSettings bodyTemplate 透传结构
            const inputKey = input.param_code || input.key;
            if (inputKey && !roundTpl[inputKey]) {
              roundTpl[inputKey] = `{{${inputKey}}}`;
            }
          });
          apiSettingsObj.bodyTemplate.rounds[0] = roundTpl;
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
      const rawAssociatedAlgorithms = dimension.associatedAlgorithms || [];
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
      const parentDimensionId = dimension.parentDimensionId || '';

      // INT-1868 裁定 A：LLM Judge 是维度属性（后端派生 llm_judge，由 task_type_code 判定），
      // 不是结果类型选项；编辑时只读展示结果类型，不再提供模型 / Prompt / Token / Temperature。
      const isLlmJudgeDimension = dimension.llmJudge === true;
      const formFields = isLlmJudgeDimension
        ? evaluationFields.value.map((field: any) =>
            field.key === 'resultType'
              ? {
                  ...field,
                  // 禁用下拉即只读：选项固定为派生口径，提交值仍取维度自身的 result_type(int)
                  disabled: true,
                  options: [{ value: dimension.resultType ?? 1, label: 'LLM Judge' }],
                  hint: '由维度任务类型（task_type_code=llm_judge）决定，不支持在此修改'
                }
              : field
          )
        : evaluationFields.value;

      const rawOutputFields = dimension.outputFields || [];
      const outputFieldsArray = Array.isArray(rawOutputFields) ? rawOutputFields : [];
      const statisticMethod = dimension.statisticMethod || 'average';
      const aggDenominator = dimension.aggDenominator || 'case';
      // adapter 已把 exclude_rounds 归一为 number[]，此处仅做数组兜底
      const excludeRounds = Array.isArray(dimension.excludeRounds) ? dimension.excludeRounds : [];

      const editingData = {
        ...dimension,
        categoryId: dimension.categoryId,
        apiEndpoints,
        apiUrl,
        apiSettings: apiSettingsObj,
        rule: ruleObj,
        requiredInputs: requiredInputsObj,
        outputFields: outputFieldsArray,
        statisticMethod: statisticMethod,
        aggDenominator: aggDenominator,
        excludeRounds: excludeRounds,
        associatedAlgorithms: associatedAlgorithmsArray,
        status: String(dimension.status).toLowerCase() === 'true',
        dimensionType: dimensionType,
        parentDimensionId: parentDimensionId,
        taskTypeCode: dimension.taskTypeCode || '',
        // 结果类型按后端 int 提交（LLM Judge 维度也保留原值，不写 llm_judge 字符串）
        resultType: dimension.resultType ?? 1
      };

      modalManager.open(MODAL_TYPES.CRUD_FORM, {
        mode: 'edit',
        entityName: '评估维度',
        width: '1400px',
        fields: formFields,
        formData: editingData,
        onSave: async (result: any) => {
          console.log('[Evaluation] openEditModal onSave result:', JSON.stringify(result, null, 2));
          const payload = result.data || result;
          console.log('[Evaluation] Extracted payload:', JSON.stringify(payload, null, 2));
          await saveDimension(payload, result.mode || 'edit');
        }
      });
    } catch (error) {
      console.error('[Evaluation] 加载评估维度详情失败:', error);
    }
  }

  // ========== 新增维度模态框 ==========
  function openAddModal(categoryId?: number | string, parentDimensionId?: number | string) {
    const formData = {
      name: '',
      description: '',
      type: 'auto',
      // INT-536（D5）：新建默认取 localStorage 可见性偏好（visibility_pref，缺省 shared），
      // 与任务/用例新建口径一致；不再回落到表单字段的 defaultValue:'shared'
      visibility: getVisibilityPref(),
      // 预填参数：分组视图「添加维度」带入分类，主维度行「添加子维度」带入父维度；未预填时默认选中第一个分类
      categoryId: categoryId ?? (categories.value[0]?.id ?? undefined),
      dimensionType: parentDimensionId ? 'sub' : 'main',
      parentDimensionId: parentDimensionId || '',
      apiUrl: '',
      scoreUnit: '',
      apiSettings: {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        bodyTemplate: {
          rounds: [
            {
              asrRef: "{{asr_ref}}",
              outputText: "{{output_text}}"
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
      aggDenominator: 'case',
      excludeRounds: [],
      apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 }],
      associatedAlgorithms: []
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

  // ========== 新增分类模态框 ==========
  const categoryFields = [
    { key: 'name', label: '分类名称', type: 'text', required: true, placeholder: '请输入分类名称', group: '基本信息' },
    { key: 'description', label: '描述', type: 'textarea', rows: 2, placeholder: '请输入分类描述', group: '基本信息' },
    { key: 'icon', label: '图标', type: 'text', placeholder: '如 fas fa-folder', defaultValue: 'fas fa-folder', group: '基本信息' }
  ];

  function openAddCategoryModal() {
    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      mode: 'add',
      entityName: '评估分类',
      width: '600px',
      fields: categoryFields,
      formData: { name: '', description: '', icon: 'fas fa-folder' },
      onSave: async (result: any) => {
        const payload = result.data || result;
        await saveCategory(payload, 'add');
      }
    });
  }

  // ========== API 设置 / 规则编辑器（已随 CRUD_FORM 模态框统一化移除：API 配置编辑由维度表单页承载） ==========

  return {
    openEditModal,
    openAddModal,
    openAddCategoryModal,
  };
}

export type UseEvaluationModalsReturn = ReturnType<typeof useEvaluationModals>;
