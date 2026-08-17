import { ref, computed } from 'vue';
import { evaluationApi, algorithmApi } from '../../utils/api';
import { useModalControl } from '../../composables/useModal';
import { EvaluationDimension, EvaluationCategory, MODAL_TYPES, APIHealthResult, APIHealthResultModalData } from '../../shared/types';

export interface ExtendedAPISettings {
  id: string;
  url: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  timeout: number;
  headers: string;
  body: string;
  responseMapping: string;
}

function toSnakeCaseKey(key: string): string {
  return key
    .replace(/([A-Z]+)([A-Z][a-z0-9])/g, '$1_$2')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase();
}

function toSnakeCaseDict(data: any): any {
  if (data === null || data === undefined) return data;
  if (Array.isArray(data)) return data.map(item => toSnakeCaseDict(item));
  if (typeof data === 'object') {
    const result: Record<string, any> = {};
    for (const [key, value] of Object.entries(data)) {
      result[toSnakeCaseKey(key)] = toSnakeCaseDict(value);
    }
    return result;
  }
  return data;
}

export function useEvaluation() {
  const loading = ref(false);
  const error = ref<string | null>(null);
  const modalManager = useModalControl();

  function getAlgorithmLabel(algorithmType: string): string {
    if (algorithms.value && algorithms.value.length > 0) {
      const algo = algorithms.value.find(a => a.value === algorithmType);
      if (algo) return algo.label;
    }
    return algorithmType;
  }

  const batchMenuRef = ref<HTMLElement | null>(null);
  const importExportMenuRef = ref<HTMLElement | null>(null);

  const searchKeyword = ref('');
  const filterStatus = ref<'all' | 'active' | 'inactive'>('all');
  const filterCategory = ref('all');

  const selectedDimensions = ref<(number | string)[]>([]);

  const currentPage = ref(1);
  const pageSize = ref(10);
  const totalItems = ref(0);
  const totalPages = ref(0);

  const dimensions = ref<EvaluationDimension[]>([]);
  const categories = ref<EvaluationCategory[]>([]);
  const algorithms = ref<{ value: string; label: string }[]>([]);
  const apiHealthResult = ref<APIHealthResult | null>(null);

  const editingCategory = ref(false);
  const editingDimension = ref(false);

  function handleClickOutside(event: MouseEvent) {
    if (batchMenuRef.value && !batchMenuRef.value.contains(event.target as Node)) {
      const batchMenu = document.getElementById('batchMenu');
      if (batchMenu) {
        batchMenu.classList.remove('active');
      }
    }
    
    if (importExportMenuRef.value && !importExportMenuRef.value.contains(event.target as Node)) {
      const importExportMenu = document.getElementById('importExportMenu');
      if (importExportMenu) {
        importExportMenu.classList.remove('active');
      }
    }
  }

  function initEvaluation() {
    fetchData();
    window.addEventListener('click', handleClickOutside);
  }

  function cleanupEvaluation() {
    window.removeEventListener('click', handleClickOutside);
  }

  async function fetchData() {
    loading.value = true;
    error.value = null;
    try {
      const params : Record<string, any> = {page: currentPage.value, perPage: pageSize.value, search: searchKeyword.value};
      
      if (filterStatus.value !== 'all') {
        params.status = filterStatus.value === 'active';
      }
      
      if (filterCategory.value !== 'all') {
        params.categoryId = filterCategory.value;
      }
      
      const [dimsData, catsData, algosData] = await Promise.all([
        evaluationApi.getAll(params),
        evaluationApi.getCategories(),
        algorithmApi.getOptions()
      ]);
      
      dimensions.value = dimsData?.items || [];
      totalItems.value = dimsData?.total || 0;
      totalPages.value = dimsData?.pages || 0;
      categories.value = catsData?.items || [];
      algorithms.value = (algosData?.algorithms || []).map((algo: any) => ({
        value: algo.value,
        label: algo.name || algo.value
      }));
    } catch (err) {
      console.error('Failed to fetch evaluation data:', err);
      error.value = '获取评估维度失败';
    } finally {
      loading.value = false;
    }
  }

  const dimensionTemplate = {
    name: '',
    description: '', 
    apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60}],
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
            answer: "{{answer}}",
            correctAnswer: "{{correct_answer}}"
          }
        ]
      },
      timeout: 30000
    },
    type: 'auto',
    categoryId: undefined,
    resultType: 1,
    resultMin: 0,
    resultMax: 100,
    decimalPlaces: 2,
    weight: 5,
    estimatedExecTime: 5,
    rule: {
      rules: [
        { condition: '>=', value: 95, score: 10},
        { condition: '>=', value: 90, score: 9 },
        { condition: '>=', value: 80, score: 8 },
        { condition: '>=', value: 70, score: 7 },
        { condition: '>=', value: 60, score: 6 },
        { condition: '<', value: 60, score: 0 }
      ]
    },
    status: true,
    requiredInputs: [
      { key: 'asr_result', label: 'ASR识别结果', source: 'api', required: true, description: 'ASR算法识别出的文本' },
      { key: 'asr_ref', label: '参考文本', source: 'device', required: true, description: '标准参考文本' }
    ],
    associatedAlgorithms: [],
    llmJudgeConfig: {
      model: '',
      promptTemplate: '',
      maxTokens: 1024,
      temperature: 0.7
    }
  };

  const newDimension = ref<Partial<EvaluationDimension>>({ 
    name: '',
    description: '',
    apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60}],
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
            answer: "{{answer}}",
            correctAnswer: "{{correct_answer}}"
          }
        ]
      },
      timeout: 30000
    },
    type: 'auto',
    categoryId: undefined,
    resultType: 1,
    resultMin: 0,
    resultMax: 100,
    decimalPlaces: 2,
    weight: 5,
    estimatedExecTime: 5,
    rule: { ...dimensionTemplate.rule },
    status: true,
    requiredInputs: [
      { key: 'asr_result', label: 'ASR识别结果', source: 'api', required: true, description: 'ASR算法识别出的文本' },
      { key: 'asr_ref', label: '参考文本', source: 'device', required: true, description: '标准参考文本' }
    ],
    associatedAlgorithms: [],
    llmJudgeConfig: {
      model: '',
      promptTemplate: '',
      maxTokens: 1024,
      temperature: 0.7
    }
  } as any);

  const apiSettings = ref<ExtendedAPISettings>({
    id: '',
    url: '',
    method: 'POST',
    timeout: 5000,
    headers: '',
    body: '',
    responseMapping: ''
  });

  const importSettings = ref({
    updateExisting: true,
    skipErrors: false
  });

  const showImportPreview = ref(false);
  const importPreview = ref({
    fileName: '',
    format: '',
    totalCount: 0
  });

  const newCategory = ref<Partial<EvaluationCategory>>({
    name: '',
    description: '',
    icon: 'fas fa-tachometer-alt'
  });

  const filteredDimensions = computed(() => {
    return dimensions.value.filter(dim => {
      const matchesSearch = !searchKeyword.value || 
        dim.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
        (dim.description && dim.description.toLowerCase().includes(searchKeyword.value.toLowerCase()));
      
      const matchesStatus = filterStatus.value === 'all' || 
        (filterStatus.value === 'active' && dim.status) ||
        (filterStatus.value === 'inactive' && !dim.status);
      
      const matchesCategory = filterCategory.value === 'all' || 
        dim.categoryId === Number(filterCategory.value) ||
        dim.type === filterCategory.value;
        
      return matchesSearch && matchesStatus && matchesCategory;
    });
  });

  const isAllSelected = computed(() => {
    return filteredDimensions.value.length > 0 && 
           selectedDimensions.value.length === filteredDimensions.value.length;
  });

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
      { value: '__new__', label: '+ 新建分类' },
      ...categories.value.map(c => ({ value: c.id, label: c.name }))
    ], group: '基本信息' },
    { key: 'newCategoryName', label: '新分类名称', type: 'text', required: false, placeholder: '输入新分类名称', conditional: { field: 'categoryId', value: '__new__' }, group: '基本信息' },
    { key: 'dimensionType', label: '维度类型', type: 'select', required: true, options: [
      { value: 'main', label: '主维度' },
      { value: 'sub', label: '子维度' }
    ], defaultValue: 'main', group: '层级配置' },
    { key: 'parentDimensionId', label: '所属主维度', type: 'select', required: false, options: [
      { value: '', label: '请选择所属主维度' },
      ...dimensions.value.filter(d => d.dimensionType === 'main' || !d.dimensionType).map(d => ({ 
        value: d.id, 
        label: d.name, 
        taskTypeCode: d.taskTypeCode,
        apiSettings: d.apiSettings,
        requiredInputs: (d as any).required_inputs || []
      }))
    ], conditional: { field: 'dimensionType', value: 'sub' }, group: '层级配置' },
    { key: 'parentApiInfo', label: '继承API配置', type: 'info', conditional: { field: 'dimensionType', value: 'sub' }, 
      helpText: '子维度将自动使用父维度的API配置，无需手动配置', group: '层级配置' },
    { key: 'taskTypeCode', label: '评估任务关键字', type: 'text', placeholder: '如: wer, asr, translation 等', helpText: '调用API时使用的任务关键字', group: '层级配置', 
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'apiUrl', label: 'Master入口URL', type: 'text', required: false, placeholder: '请输入Master调度节点URL (分布式架构必填)', group: 'API配置', 
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'scoreUnit', label: '分数单位', type: 'text', required: false, placeholder: '如: %, 分, 秒等', group: '结果配置' },
    { key: 'resultType', label: '结果类型', type: 'select', required: true, options: [
      { value: 1, label: '数值 (1)' },
      { value: 2, label: '布尔 (2)' },
      { value: 3, label: '文本 (3)' },
      { value: 'llm_judge', label: 'LLM Judge' }
    ], group: '结果配置' },
    { key: 'llmJudgeConfig', label: 'LLM Judge 配置', type: 'object', required: false, group: '结果配置',
      conditional: { field: 'resultType', value: 'llm_judge' },
      fields: [
        { key: 'model', label: '模型', type: 'text', required: true, placeholder: '如: gpt-4, qwen-max' },
        { key: 'promptTemplate', label: 'Prompt 模板', type: 'textarea', required: true, placeholder: '输入评估 prompt 模板，可使用 {{asr_result}} {{asr_ref}} 等变量' },
        { key: 'maxTokens', label: '最大 Token 数', type: 'number', required: false, min: 1, max: 8192, default: 1024 },
        { key: 'temperature', label: 'Temperature', type: 'number', required: false, min: 0, max: 2, step: 0.1, default: 0.7 }
      ]
    },
    { key: 'resultMin', label: '结果最小值', type: 'number', required: true, group: '结果配置' },
    { key: 'resultMax', label: '结果最大值', type: 'number', required: true, group: '结果配置' },
    { key: 'decimalPlaces', label: '小数位数', type: 'number', required: true, min: 0, max: 4, group: '结果配置' },
    { key: 'weight', label: '权重', type: 'number', required: true, min: 1, max: 10, group: '结果配置' },
    { key: 'estimatedExecTime', label: '预计执行时间(s)', type: 'number', required: true, min: 1, group: '结果配置' },
    { key: 'rule', label: '评分规则', type: 'ruleEditor', required: false, fullWidth: true, group: '结果配置' },
    { key: 'apiSettings', label: 'API设置', type: 'apiSettingsEditor', required: false, fullWidth: true, group: 'API配置', 
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'requiredInputs', label: '所需输入配置', type: 'requiredInputs', required: false, fullWidth: true, group: 'API配置',
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'outputFields', label: '输出字段配置', type: 'outputFields', required: false, fullWidth: true, group: 'API配置' },
    { key: 'statisticMethod', label: '统计方式', type: 'select', required: false, default: 'average', group: 'API配置',
      options: [
        { value: 'average', label: '简单平均' },
        { value: 'weighted_wer', label: '加权WER (Σ分子/Σ分母)' }
      ],
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'apiEndpoints', label: 'API端点配置', type: 'array', arrayItemType: 'apiEndpoint', required: false, fullWidth: true, arrayItemTemplate: {url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60}, group: 'API配置', 
      conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'associatedAlgorithms', label: '关联算法', type: 'multi-select-tags', required: false, options: algorithms.value.length > 0 ? algorithms.value : [
      { value: 'asr', label: 'ASR语音识别' },
      { value: 'translation', label: '翻译' },
      { value: 'tts', label: 'TTS语音合成' },
      { value: 'speaker_recognition', label: '说话人识别' },
      { value: 'noise_reduction', label: '降噪' },
      { value: 'vad', label: '语音活动检测' }
    ], placeholder: '选择关联的算法类型', group: '关联算法', conditional: { field: 'dimensionType', value: 'main' } },
    { key: 'status', label: '状态', type: 'switch', default: true, group: '基础信息' }
  ]);

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
      let apiSettingsObj = { method: 'POST', headers: {}, bodyTemplate: {}, timeout: 30000 };
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

      if (apiSettingsObj.bodyTemplate) {
        // 对齐 rounds 内的字段
        if (apiSettingsObj.bodyTemplate.rounds && Array.isArray(apiSettingsObj.bodyTemplate.rounds)) {
          const roundTpl = apiSettingsObj.bodyTemplate.rounds[0] || {};
          const requiredInputKeys = new Set(
            requiredInputsArray.map((input: any) => input.paramCode || input.param_code || input.key).filter(Boolean)
          );
          Object.keys(roundTpl).forEach(key => {
            if (!requiredInputKeys.has(key)) {
              delete roundTpl[key];
            }
          });
          requiredInputsArray.forEach((input: any) => {
            const inputKey = input.paramCode || input.param_code || input.key;
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

      const rawOutputFields = dimension.outputFields || (dimension as any).output_fields || [];
      const outputFieldsArray = Array.isArray(rawOutputFields) ? rawOutputFields : [];
      const statisticMethod = dimension.statisticMethod || (dimension as any).statistic_method || 'average';

      const editingData = {...dimension, categoryId: dimension.categoryId || (dimension as any).category_id, apiEndpoints, apiUrl,
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
        llmJudgeConfig: llmJudgeConfig};
        
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

  function goToPage(page: number) {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page;
      fetchData();
    }
  }

  function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--;
      fetchData();
    }
  }

  function nextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
      fetchData();
    }
  }

  function onPageSizeChange(size: number) {
    pageSize.value = size;
    currentPage.value = 1;
    fetchData();
  }

  function searchDimensions() {
    currentPage.value = 1;
    fetchData();
  }

  function filterDimensions() {
    currentPage.value = 1;
    fetchData();
  }

  function resetFilters() {
    searchKeyword.value = '';
    filterStatus.value = 'all';
    filterCategory.value = 'all';
    currentPage.value = 1;
    fetchData();
  }

  async function saveDimension(payload: any, type: 'add' | 'edit' = 'add') {
    console.log(`[Evaluation] saveDimension called, type: ${type}`);
    console.log('[Evaluation] Received payload keys:', Object.keys(payload));
    console.log('[Evaluation] Received payload:', JSON.stringify(payload, null, 2));
    
    const data = payload.data !== undefined ? payload.data : payload;
    
    console.log('[Evaluation] Extracted data keys:', Object.keys(data));
    console.log('[Evaluation] Extracted data:', JSON.stringify(data, null, 2));
    
    loading.value = true;
    error.value = null;
    try {
      const dimensionData = {...data};
      console.log('[Evaluation] dimensionData after spread:', JSON.stringify(dimensionData, null, 2));
      
      if (typeof dimensionData.rule === 'object' && dimensionData.rule !== null) {
        console.log('[Evaluation] Converting rule object to JSON string');
        dimensionData.rule = JSON.stringify(dimensionData.rule);
      } else if (typeof dimensionData.rule === 'string' && dimensionData.rule.trim()) {
        try {
          console.log('[Evaluation] Parsing rule JSON');
          dimensionData.rule = JSON.parse(dimensionData.rule);
          dimensionData.rule = JSON.stringify(dimensionData.rule);
        } catch (e) {
          console.error('[Evaluation] Rule JSON parse failed:', e);
          throw new Error('评分规则格式不正确，请检查 JSON 格式');
        }
      } else if (typeof dimensionData.rule === 'string') {
        delete dimensionData.rule;
      }

      if (dimensionData.requiredInputs !== undefined) {
        if (typeof dimensionData.requiredInputs === 'string' && dimensionData.requiredInputs.trim()) {
          try {
            console.log('[Evaluation] Parsing required_inputs JSON');
            const parsed = JSON.parse(dimensionData.requiredInputs);
            dimensionData.requiredInputs = parsed;
          } catch (e) {
            console.error('[Evaluation] requiredInputs JSON parse failed:', e);
            throw new Error('所需输入配置格式不正确，请检查 JSON 格式');
          }
        } else if (Array.isArray(dimensionData.requiredInputs)) {
          dimensionData.requiredInputs = dimensionData.requiredInputs;

          if (Array.isArray(dimensionData.requiredInputs) && dimensionData.requiredInputs.length > 0) {
            if (!dimensionData.apiSettings) {
              dimensionData.apiSettings = {};
            }
            if (!dimensionData.apiSettings.bodyTemplate) {
              dimensionData.apiSettings.bodyTemplate = {};
            }
            // 确保 bodyTemplate 有 rounds 结构
            if (!dimensionData.apiSettings.bodyTemplate.rounds) {
              dimensionData.apiSettings.bodyTemplate.rounds = [{}];
            }
            const roundTpl = dimensionData.apiSettings.bodyTemplate.rounds[0];

            dimensionData.requiredInputs.forEach((input: any) => {
              const inputKey = input.paramCode || input.param_code || input.key;
              if (inputKey && !roundTpl[inputKey]) {
                roundTpl[inputKey] = `{{${inputKey}}}`;
              }
            });

            // 清理 rounds 内不在 requiredInputs 中的 key
            Object.keys(roundTpl).forEach(key => {
              const exists = dimensionData.requiredInputs.some((input: any) => {
                const inputKey = input.paramCode || input.param_code || input.key;
                return inputKey === key;
              });
              if (!exists) {
                delete roundTpl[key];
              }
            });
          }
        } else {
          delete dimensionData.requiredInputs;
        }
      }

      // 处理 outputFields
      if (dimensionData.outputFields !== undefined) {
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

      if (dimensionData.apiSettings !== undefined) {
        if (typeof dimensionData.apiSettings === 'string' && dimensionData.apiSettings.trim()) {
          try {
            console.log('[Evaluation] Parsing apiSettings JSON');
            const parsed = JSON.parse(dimensionData.apiSettings);
            dimensionData.apiSettings = parsed;
          } catch (e) {
            console.error('[Evaluation] apiSettings JSON parse failed:', e);
            throw new Error('API设置格式不正确，请检查 JSON 格式');
          }
        } else if (typeof dimensionData.apiSettings === 'object' && dimensionData.apiSettings !== null) {
          dimensionData.apiSettings = dimensionData.apiSettings;
        } else {
          delete dimensionData.apiSettings;
        }
      }

      // apiUrl 现在是字符串类型，不需要 JSON 解析
      if (dimensionData.apiUrl !== undefined && typeof dimensionData.apiUrl === 'string') {
        // 只需要修剪空格
        dimensionData.apiUrl = dimensionData.apiUrl.trim();
      }

      // 处理categoryId空字符串，转换为null
      if (dimensionData.categoryId === '' || dimensionData.categoryId === undefined) {
        dimensionData.categoryId = null;
      }

      // 处理选择新建分类
      if (dimensionData.categoryId === '__new__') {
        if (dimensionData.newCategoryName && dimensionData.newCategoryName.trim()) {
          const newCatName = dimensionData.newCategoryName.trim();
          const existingCat = categories.value.find(c => c.name === newCatName);
          if (existingCat) {
            dimensionData.categoryId = existingCat.id;
          } else {
            const newCat = await evaluationApi.createCategory({
              name: newCatName,
              description: '',
              icon: 'fas fa-tachometer-alt'
            });
            dimensionData.categoryId = newCat.id;
            categories.value.push({ id: newCat.id, name: newCat.name, description: '', icon: 'fas fa-tachometer-alt' });
          }
        } else {
          dimensionData.categoryId = null;
        }
        delete dimensionData.newCategoryName;
      }

      // 处理子维度自动填充主维度的解析类型
      if (dimensionData.dimensionType === 'sub' && dimensionData.parentDimensionId && !dimensionData.taskTypeCode) {
        const parentDim = dimensions.value.find(d => d.id === dimensionData.parentDimensionId);
        if (parentDim && parentDim.taskTypeCode) {
          dimensionData.taskTypeCode = parentDim.taskTypeCode;
        }
      }

      // 处理子维度继承父维度的关联算法
      if (dimensionData.dimensionType === 'sub' && dimensionData.parentDimensionId) {
        if (!dimensionData.associatedAlgorithms || dimensionData.associatedAlgorithms.length === 0) {
          const parentDim = dimensions.value.find(d => d.id === dimensionData.parentDimensionId);
          if (parentDim && parentDim.associatedAlgorithms && parentDim.associatedAlgorithms.length > 0) {
            const parentAlgorithms = parentDim.associatedAlgorithms.map((item: any) =>
              typeof item === 'string' ? item : item.algorithmType
            );
            dimensionData.associatedAlgorithms = parentAlgorithms;
          }
        }
      }

      // 处理 parentDimensionId 空字符串，转换为 null
      if (dimensionData.parentDimensionId === '' || dimensionData.parentDimensionId === undefined) {
        dimensionData.parentDimensionId = null;
      }

      if (Array.isArray(dimensionData.apiEndpoints)) {
        console.log('[Evaluation] Normalizing apiEndpoints');
        dimensionData.apiEndpoints = dimensionData.apiEndpoints.map((ep: any) => ({
          ...ep,
          url: ep.url || ep.endpoint || '',
          maxProcess: ep.maxProcess || 5,
          maxTimeout: ep.maxTimeout || 30,
          maxAudioDuration: ep.maxAudioDuration || 60
        }));
      }

      // 处理 associatedAlgorithms - 将字符串数组转换为 AlgorithmAssociation 数组
      if (dimensionData.associatedAlgorithms !== undefined) {
        if (Array.isArray(dimensionData.associatedAlgorithms)) {
          // 如果是字符串数组，转换为 AlgorithmAssociation 格式
          if (dimensionData.associatedAlgorithms.length > 0 && typeof dimensionData.associatedAlgorithms[0] === 'string') {
            dimensionData.associatedAlgorithms = dimensionData.associatedAlgorithms.map((algoType: string) => ({
              algorithmType: algoType,
              isDefault: false,
              weight: 1.0
            }));
          }
        } else {
          dimensionData.associatedAlgorithms = [];
        }
      } else {
        dimensionData.associatedAlgorithms = [];
      }

      // 处理 llmJudgeConfig
      if (dimensionData.llmJudgeConfig !== undefined) {
        if (typeof dimensionData.llmJudgeConfig === 'object' && dimensionData.llmJudgeConfig !== null) {
          // 确保包含必要的字段
          dimensionData.llmJudgeConfig = {
            model: dimensionData.llmJudgeConfig.model || '',
            promptTemplate: dimensionData.llmJudgeConfig.promptTemplate || '',
            maxTokens: dimensionData.llmJudgeConfig.maxTokens || 1024,
            temperature: dimensionData.llmJudgeConfig.temperature ?? 0.7
          };
        } else {
          delete dimensionData.llmJudgeConfig;
        }
      }

      console.log('[Evaluation] Validating required fields');
      const missingFields : string[] = [];
      
      evaluationFields.value.forEach(field => {
      if (field.required) {
        const value = dimensionData[field.key];
        
        if (field.type === 'textarea') {
          // 对于JSON格式的textarea字段，不在这里验证JSON格式，而是在后面专门处理
          if (value === undefined || value === null || value === '') {
            missingFields.push(field.label);
          }
        } else if (value === undefined || value === null || value === '') {
          missingFields.push(field.label);
        } else if (field.type === 'array') {
              if (field.required) {
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
          }
      }
    });

      if (missingFields.length > 0) {
        console.warn('[Evaluation] Validation failed:', missingFields);
        throw new Error(`以下必填字段缺失：${missingFields.join('、')}`);
      }

      console.log('[Evaluation] Validation passed, calling API');
      if (type === 'add') {
        console.log('[Evaluation] Creating new dimension');
        await evaluationApi.create(dimensionData);
        console.log('[Evaluation] Dimension created successfully');
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '评估维度添加成功',
          onConfirm: () => {
          }
        });
      } else {
        if (!dimensionData.id) throw new Error('维度 ID 缺失');
        await evaluationApi.update(dimensionData.id, dimensionData);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '评估维度更新成功',
          onConfirm: () => {
          }
        });
      }
      await fetchData();
    } catch (err: any) {
      console.error('Failed to save dimension:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '保存失败',
        onConfirm: () => {
        }
      });
      error.value = err.message || '保存评估维度失败';
    } finally {
      loading.value = false;
    }
  }

  async function deleteDimension(id: number | string) {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除维度',
      content: `确定要删除维度 ${id} 吗？`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationApi.delete(id);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '成功',
            content: '维度已删除',
            onConfirm: () => {
            }
          });
          await fetchData();
        } catch (err: any) {
          console.error('Failed to delete dimension:', err);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '错误',
            content: err.message || '删除维度失败',
            onConfirm: () => {
            }
          });
        } finally {
          loading.value = false;
        }
      }
    });
  }

  async function batchEnable() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要启用的维度',
        onConfirm: () => {
        }
      });
      return;
    }
    loading.value = true;
    try {
      await evaluationApi.batchAction('enable', selectedDimensions.value);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '批量启用成功',
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to batch enable dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '批量启用失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function batchDisable() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要禁用的维度',
        onConfirm: () => {
        }
      });
      return;
    }
    loading.value = true;
    try {
      await evaluationApi.batchAction('disable', selectedDimensions.value);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '批量禁用成功',
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to batch disable dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '批量禁用失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function batchDelete() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要删除的维度',
        onConfirm: () => {
        }
      });
      return;
    }
    
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '批量删除维度',
      content: `确定要删除选中的 ${selectedDimensions.value.length} 个维度吗？`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationApi.batchAction('delete', selectedDimensions.value);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '成功',
            content: '批量删除成功',
            onConfirm: () => {
            }
          });
          selectedDimensions.value = [];
          await fetchData();
        } catch (err: any) {
          console.error('Failed to batch delete dimensions:', err);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '错误',
            content: err.message || '批量删除失败',
            onConfirm: () => {
            }
          });
        } finally {
          loading.value = false;
        }
      }
    });
  }

  function toggleSelectAll() {
    if (isAllSelected.value) {
      selectedDimensions.value = [];
    } else {
      selectedDimensions.value = filteredDimensions.value.map(dim => dim.id);
    }
  }

  function toggleDimensionSelection(id: number | string) {
    const index = selectedDimensions.value.indexOf(id);
    if (index > -1) {
      selectedDimensions.value.splice(index, 1);
    } else {
      selectedDimensions.value.push(id);
    }
  }

  function toggleBatchMenu() {
    const batchMenu = document.getElementById('batchMenu');
    if (batchMenu) batchMenu.classList.toggle('active');
  }

  function toggleImportExportMenu() {
    const importExportMenu = document.getElementById('importExportMenu');
    if (importExportMenu) importExportMenu.classList.toggle('active');
  }

  async function testAPIHealth(id: number | string) {
    loading.value = true;
    try {
      const result : APIHealthResult = await evaluationApi.healthCheck(id);
      const dimension = dimensions.value.find(dim => dim.id === id) || {} as EvaluationDimension;
      
      const modalData : APIHealthResultModalData = {dimension, results: result};
      
      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: 'API健康测试结果',
        data: modalData
      });
    } catch (err: any) {
      console.error('Failed to test API health:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `API测试失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function updateWeight(id: number | string, weight: number) {
    loading.value = true;
    try {
      await evaluationApi.update(id, {
        weight: weight
      });
      
      const dimension = dimensions.value.find(dim => dim.id === id);
      if (dimension) {
        dimension.weight = weight;
      }
      
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '权重更新成功',
        onConfirm: () => {
        }
      });
    } catch (err: any) {
      console.error('Failed to update weight:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `权重更新失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  function importDimensions() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls,.json';
    input.style.display = 'none';
    
    input.addEventListener('change', async (event: any) => {
      const file = event.target.files[0];
      if (file) {
        await handleImport(file);
      }
      input.remove();
    });
    
    document.body.appendChild(input);
    input.click();
  }

  async function exportData(format: 'json' | 'excel' = 'json') {
    loading.value = true;
    try {
      const blob = await evaluationApi.export(format);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const extension = format === 'excel' ? 'xlsx' : 'json';
      link.download = `evaluation-dimensions-${new Date().toISOString().slice(0, 10)}.${extension}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '维度导出成功',
        onConfirm: () => {
        }
      });
    } catch (err: any) {
      console.error('Failed to export dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `导出维度失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function exportDimensions(format: 'json' | 'excel' = 'json') {
    return exportData(format);
  }

  function closeModal(id: string) {
    modalManager.close(id);
  }

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
      apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60}],
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

  function openAPISettingsModal(id: number | string) {
    modalManager.open(MODAL_TYPES.API_OTHER_CONFIG, {
      title: 'API设置',
      dimensionId: id,
      onSave: (settings: any) => {
        saveAPISettings(settings);
      }
    });
  }

  function openRuleEditorModal(fieldId: string) {
    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '规则编辑器',
      fieldId: fieldId,
      onSave: (rule: any) => {
        console.log('保存规则:', rule);
      }
    });
  }

  function previewImportData(event: any) {
      const file = event.target.files[0];
      if (file) {
          showImportPreview.value = true;
          importPreview.value = {fileName: file.name, format: file.name.split('.').pop().toUpperCase(), totalCount: 0};
      }
  }

  async function handleImport(file: File) {
    loading.value = true;
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('updateExisting', importSettings.value.updateExisting ? 'true' : 'false');
      formData.append('skipErrors', importSettings.value.skipErrors ? 'true' : 'false');
      
      const result = await evaluationApi.import(formData); 
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: `导入成功: ${result.message || '已完成'}`,
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to import dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `导入维度失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function saveAPISettings(settings: any) {
    loading.value = true;
    try {
      const apiSettingsData = {...apiSettings.value, ...settings};
      
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

  function toggleCategory(categoryHeader: HTMLElement, event: MouseEvent) {
    event.stopPropagation();
    const categoryContent = categoryHeader.querySelector('.category-content');
    const toggleIcon = categoryHeader.querySelector('.category-toggle');
    if (categoryContent) {
      categoryContent.classList.toggle('collapsed');
      if (toggleIcon) toggleIcon.classList.toggle('rotate');
    }
  }

  function toggleGroupSelection(groupCheckbox: HTMLInputElement, category: string) {
    const isChecked = groupCheckbox.checked;
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);
    
    if (isChecked) {
      dimensionsInCategory.forEach(dim => {
        if (!selectedDimensions.value.includes(dim.id)) {
          selectedDimensions.value.push(dim.id);
        }
      });
    } else {
      selectedDimensions.value = selectedDimensions.value.filter(id => {
        return !dimensionsInCategory.some(dim => dim.id === id);
      });
    }
  }

  function selectAllInGroup(category: string) {
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);
    dimensionsInCategory.forEach(dim => {
      if (!selectedDimensions.value.includes(dim.id)) {
        selectedDimensions.value.push(dim.id);
      }
    });
  }

  function toggleSelectAllInCategory(category: string) {
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);
    const allSelected = dimensionsInCategory.every(dim => selectedDimensions.value.includes(dim.id));
    
    if (allSelected) {
      selectedDimensions.value = selectedDimensions.value.filter(id => {
        return !dimensionsInCategory.some(dim => dim.id === id);
      });
    } else {
      dimensionsInCategory.forEach(dim => {
        if (!selectedDimensions.value.includes(dim.id)) {
          selectedDimensions.value.push(dim.id);
        }
      });
    }
  }

  async function deleteGroup(id: number) {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除分类',
      content: `确定要删除该分类吗？此操作将同时删除该分类下的所有维度。`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationApi.deleteCategory(id);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '成功',
            content: '分类已删除',
            onConfirm: () => {
            }
          });
          await fetchData();
        } catch (err: any) {
          console.error('Failed to delete category:', err);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '错误',
            content: err.message || '删除分类失败',
            onConfirm: () => {
            }
          });
        } finally {
          loading.value = false;
        }
      }
    });
  }

  async function saveCategory(data: any, type: 'add' | 'edit' = 'add') {
    loading.value = true;
    try {
      const missingFields: string[] = [];
      
      if (!data.name) {
        missingFields.push('分类名称');
      }
      
      if (missingFields.length > 0) {
        throw new Error(`以下必填字段缺失：${missingFields.join('、')}`);
      }
      
      if (type === 'add') {
        await evaluationApi.createCategory(data);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '分类添加成功',
          onConfirm: () => {
          }
        });
        newCategory.value = {name: '', description: '', icon: 'fas fa-tachometer-alt'};
      } else {
        if (!data.id) throw new Error('分类 ID 缺失');
        await evaluationApi.updateCategory(data.id, data);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '分类更新成功',
          onConfirm: () => {
          }
        });
      }
      await fetchData();
    } catch (err: any) {
      console.error('Failed to save category:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '保存分类失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  function resetAllStates() {
    resetFilters();
    currentPage.value = 1;
    pageSize.value = 10;
    selectedDimensions.value = [];
    newDimension.value = {...dimensionTemplate} as any;
    importSettings.value = {updateExisting: true, skipErrors: false};
    showImportPreview.value = false;
    newCategory.value = {name: '', description: '', icon: 'fas fa-tachometer-alt'};
  }

  return {
    loading, 
    error, 
    batchMenuRef, 
    importExportMenuRef, 
    searchKeyword, 
    filterStatus, 
    filterCategory, 
    selectedDimensions, 
    currentPage, 
    pageSize, 
    totalItems, 
    totalPages, 
    dimensions, 
    categories, 
    algorithms, 
    newDimension, 
    apiSettings, 
    importSettings, 
    showImportPreview, 
    importPreview, 
    newCategory, 
    filteredDimensions, 
    isAllSelected, 
    fetchData, 
    initEvaluation, 
    cleanupEvaluation, 
    openEditModal, 
    goToPage, 
    prevPage, 
    nextPage, 
    onPageSizeChange, 
    searchDimensions, 
    filterDimensions, 
    resetFilters, 
    saveDimension, 
    deleteDimension, 
    batchEnable, 
    batchDisable, 
    batchDelete, 
    toggleSelectAll, 
    toggleDimensionSelection, 
    toggleBatchMenu, 
    toggleImportExportMenu, 
    testAPIHealth, 
    updateWeight, 
    importDimensions, 
    exportData, 
    exportDimensions, 
    openAddModal, 
    openAPISettingsModal, 
    openRuleEditorModal, 
    previewImportData, 
    handleImport, 
    saveAPISettings, 
    toggleCategory, 
    toggleGroupSelection, 
    selectAllInGroup, 
    toggleSelectAllInCategory, 
    getAlgorithmLabel, 
    deleteGroup, 
    saveCategory, 
    resetAllStates, 
    closeModal
  };
}
