import { ref, computed } from 'vue';
import { evaluationApi, algorithmApi } from '../../utils/api';
import { useModalControl } from '../modal/useModal';
import {
  EvaluationDimension,
  EvaluationCategory,
  MODAL_TYPES,
  APIHealthResult,
  APIHealthResultModalData
} from '../../shared/types';

// === 常量定义 ===
/** 新建分类的特殊标识 */
const NEW_CATEGORY_FLAG = '__new__';
/** 维度类型：主维度 */
const DIMENSION_TYPE_MAIN = 'main';
/** 维度类型：子维度 */
const DIMENSION_TYPE_SUB = 'sub';
/** 默认分类图标 */
const DEFAULT_CATEGORY_ICON = 'fas fa-tachometer-alt';
/** 默认 LLM 最大 Token 数 */
const DEFAULT_LLM_MAX_TOKENS = 1024;
/** 默认 LLM 温度 */
const DEFAULT_LLM_TEMPERATURE = 0.7;
/** 默认 API 端点最大并发数 */
const DEFAULT_MAX_PROCESS = 5;
/** 默认 API 端点超时（秒） */
const DEFAULT_MAX_TIMEOUT = 30;
/** 默认 API 端点最大音频时长（秒） */
const DEFAULT_MAX_AUDIO_DURATION = 60;
/** 默认 API 超时（毫秒） */
const DEFAULT_API_TIMEOUT = 30000;
/** 编辑模态框默认 API 超时（毫秒） */
const DEFAULT_EDITOR_API_TIMEOUT = 5000;
/** 默认分页大小 */
const DEFAULT_PAGE_SIZE = 10;
/** 保存操作类型：新增 */
const SAVE_TYPE_ADD = 'add';
/** 保存操作类型：编辑 */
const SAVE_TYPE_EDIT = 'edit';

/**
 * 扩展的 API 设置（编辑模态框使用）
 *
 * 注：原 evaluation.ts 中定义的同名接口，此处为避免循环依赖在本地定义并导出，
 * evaluation.ts 会重新导出该类型以保持对外接口兼容。
 */
export interface ExtendedAPISettings {
  id: string;
  url: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  timeout: number;
  headers: string;
  body: string;
  responseMapping: string;
}

/**
 * 评估维度管理组合式函数
 *
 * 职责：
 * - 维度列表数据获取（含分类、算法）
 * - 维度 CRUD（saveDimension / deleteDimension）
 * - 维度选择（toggleSelectAll / toggleDimensionSelection / 分组选择）
 * - 分页与过滤（goToPage / searchDimensions / resetFilters 等）
 * - 维度表单字段定义（evaluationFields）
 * - API 健康检查、权重更新、算法标签
 *
 * 该模块为基础模块，其他子模块通过参数注入其返回值。
 */

export function useEvaluationDimensions() {
  const modalManager = useModalControl();

  // ========== 基础状态 ==========
  const loading = ref(false);
  const error = ref<string | null>(null);

  const searchKeyword = ref('');
  const filterStatus = ref<'all' | 'active' | 'inactive'>('all');
  const filterCategory = ref('all');

  const selectedDimensions = ref<(number | string)[]>([]);

  const currentPage = ref(1);
  const pageSize = ref(DEFAULT_PAGE_SIZE);
  const totalItems = ref(0);
  const totalPages = ref(0);

  const dimensions = ref<EvaluationDimension[]>([]);
  const categories = ref<EvaluationCategory[]>([]);
  const algorithms = ref<{ value: string; label: string }[]>([]);
  const apiHealthResult = ref<APIHealthResult | null>(null);

  const editingCategory = ref(false);
  const editingDimension = ref(false);

  // ========== 维度模板 ==========
  const dimensionTemplate = {
    name: '',
    description: '',
    apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: DEFAULT_MAX_PROCESS, maxTimeout: DEFAULT_MAX_TIMEOUT, maxAudioDuration: DEFAULT_MAX_AUDIO_DURATION }],
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
      timeout: DEFAULT_API_TIMEOUT
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
        { condition: '>=', value: 95, score: 10 },
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
      maxTokens: DEFAULT_LLM_MAX_TOKENS,
      temperature: DEFAULT_LLM_TEMPERATURE
    }
  };

  const newDimension = ref<Partial<EvaluationDimension>>({
    name: '',
    description: '',
    apiEndpoints: [{ url: '', name: '', priority: 1, maxProcess: DEFAULT_MAX_PROCESS, maxTimeout: DEFAULT_MAX_TIMEOUT, maxAudioDuration: DEFAULT_MAX_AUDIO_DURATION }],
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
      timeout: DEFAULT_API_TIMEOUT
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
      maxTokens: DEFAULT_LLM_MAX_TOKENS,
      temperature: DEFAULT_LLM_TEMPERATURE
    }
  } as any);

  const apiSettings = ref<ExtendedAPISettings>({
    id: '',
    url: '',
    method: 'POST',
    timeout: DEFAULT_EDITOR_API_TIMEOUT,
    headers: '',
    body: '',
    responseMapping: ''
  });

  // ========== 计算属性 ==========
  const filteredDimensions = computed(() => {
    return dimensions.value.filter(dim => {
      const matchesSearch = !searchKeyword.value ||
        dim.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
        (dim.description && dim.description.toLowerCase().includes(searchKeyword.value.toLowerCase()));

      const matchesStatus = filterStatus.value === 'all' ||
        (filterStatus.value === 'active' && dim.status) ||
        (filterStatus.value === 'inactive' && !dim.status);

      const matchesCategory = filterCategory.value === 'all' ||
        dim.category_id === Number(filterCategory.value) ||
        dim.type === filterCategory.value;

      return matchesSearch && matchesStatus && matchesCategory;
    });
  });

  const isAllSelected = computed(() => {
    return filteredDimensions.value.length > 0 &&
      selectedDimensions.value.length === filteredDimensions.value.length;
  });

  // 层级维度：主维度在前，子维度紧跟其父维度
  const hierarchicalDimensions = computed(() => {
    const filtered = filteredDimensions.value;
    const mainDims = filtered.filter(d => !d.parent_dimension_id && d.dimension_type !== DIMENSION_TYPE_SUB);
    const subDims = filtered.filter(d => d.parent_dimension_id || d.dimension_type === DIMENSION_TYPE_SUB);

    const result: any[] = [];
    const placedIds = new Set<number | string>();

    for (const main of mainDims) {
      result.push({ ...main, _level: 0, _isMain: true, _parentName: '' });
      placedIds.add(main.id);

      const children = subDims.filter(s => s.parent_dimension_id === main.id);
      for (const child of children) {
        result.push({ ...child, _level: 1, _isMain: false, _parentName: main.name });
        placedIds.add(child.id);
      }
    }

    // 孤儿子维度：父维度不在当前筛选结果中
    for (const sub of subDims) {
      if (!placedIds.has(sub.id)) {
        const parent = dimensions.value.find(d => d.id === sub.parent_dimension_id);
        result.push({ ...sub, _level: 1, _isMain: false, _parentName: parent?.name || '' });
        placedIds.add(sub.id);
      }
    }

    return result;
  });

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
      ...dimensions.value.filter(d => d.dimension_type === DIMENSION_TYPE_MAIN || !d.dimension_type).map(d => ({
        value: d.id,
        label: d.name,
        taskTypeCode: d.task_type_code,
        apiSettings: d.api_settings,
        requiredInputs: (d as any).required_inputs || []
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
      conditional: CONDITION_MAIN },
    { key: 'outputFields', label: '输出字段配置', type: 'outputFields', required: false, fullWidth: true, group: 'API配置',
      conditional: CONDITION_MAIN },
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

  // ========== 数据获取 ==========
  async function fetchData() {
    loading.value = true;
    error.value = null;
    try {
      const params: Record<string, any> = { page: currentPage.value, perPage: pageSize.value, search: searchKeyword.value };

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

  // ========== 分页与过滤 ==========
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

  // ========== 维度选择 ==========
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

  // ========== 维度 CRUD ==========

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
      const inputKey = input.param_code || input.key;
      if (inputKey && !roundTpl[inputKey]) {
        roundTpl[inputKey] = `{{${inputKey}}}`;
      }
    });
    // 清理 rounds 内不在 requiredInputs 中的 key
    Object.keys(roundTpl).forEach(key => {
      const exists = dimensionData.requiredInputs.some((input: any) => {
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
          const newCat = await evaluationApi.createCategory({
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

  // 子维度继承父维度配置：taskTypeCode、associatedAlgorithms、parentDimensionId 空值处理
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
    if (dimensionData.parentDimensionId && !dimensionData.taskTypeCode && parentDim?.task_type_code) {
      dimensionData.taskTypeCode = parentDim.task_type_code;
    }
    // 继承父维度的关联算法
    if (!dimensionData.associatedAlgorithms || dimensionData.associatedAlgorithms.length === 0) {
      if (parentDim?.associated_algorithms && parentDim.associated_algorithms.length > 0) {
        dimensionData.associatedAlgorithms = parentDim.associated_algorithms.map((item: any) =>
          typeof item === 'string' ? item : item.algorithm_type
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

  // 打开结果提示模态框（提取公共逻辑，消除重复）
  function showResultModal(title: string, content: string) {
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, { title, content, onConfirm: () => {} });
  }

  async function saveDimension(payload: any, type: 'add' | 'edit' = SAVE_TYPE_ADD): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const data = payload.data !== undefined ? payload.data : payload;
      const dimensionData = { ...data };

      // 依次规范化各字段
      normalizeRule(dimensionData);
      normalizeRequiredInputs(dimensionData);
      normalizeOutputFields(dimensionData);
      normalizeApiSettings(dimensionData);
      // apiUrl 现在是字符串类型，只需修剪空格
      if (dimensionData.apiUrl !== undefined && typeof dimensionData.apiUrl === 'string') {
        dimensionData.apiUrl = dimensionData.apiUrl.trim();
      }
      await resolveCategory(dimensionData);
      inheritFromParentDimension(dimensionData);
      normalizeApiEndpoints(dimensionData);
      normalizeAssociatedAlgorithms(dimensionData);
      normalizeLlmJudgeConfig(dimensionData);

      // 校验必填字段
      const missingFields = validateRequiredFields(dimensionData);
      if (missingFields.length > 0) {
        throw new Error(`以下必填字段缺失：${missingFields.join('、')}`);
      }

      // 调用 API 创建/更新
      if (type === SAVE_TYPE_ADD) {
        await evaluationApi.create(dimensionData);
        showResultModal('成功', '评估维度添加成功');
      } else {
        if (!dimensionData.id) throw new Error('维度 ID 缺失');
        await evaluationApi.update(dimensionData.id, dimensionData);
        showResultModal('成功', '评估维度更新成功');
      }
      await fetchData();
    } catch (err: any) {
      console.error('Failed to save dimension:', err);
      showResultModal('错误', err.message || '保存失败');
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
          showResultModal('成功', '维度已删除');
          await fetchData();
        } catch (err: any) {
          console.error('Failed to delete dimension:', err);
          showResultModal('错误', err.message || '删除维度失败');
        } finally {
          loading.value = false;
        }
      }
    });
  }

  // ========== API 健康检查 / 权重 ==========
  async function testAPIHealth(id: number | string) {
    loading.value = true;
    try {
      const result: APIHealthResult = await evaluationApi.healthCheck(id);
      const dimension = dimensions.value.find(dim => dim.id === id) || {} as EvaluationDimension;

      const modalData: APIHealthResultModalData = { dimension, results: result };

      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: 'API健康测试结果',
        data: modalData
      });
    } catch (err: any) {
      console.error('Failed to test API health:', err);
      showResultModal('错误', `API测试失败: ${err.message || '未知错误'}`);
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

      showResultModal('成功', '权重更新成功');
    } catch (err: any) {
      console.error('Failed to update weight:', err);
      showResultModal('错误', `权重更新失败: ${err.message || '未知错误'}`);
    } finally {
      loading.value = false;
    }
  }

  // ========== 工具方法 ==========
  function getAlgorithmLabel(algorithmType: string): string {
    if (algorithms.value && algorithms.value.length > 0) {
      const algo = algorithms.value.find(a => a.value === algorithmType);
      if (algo) return algo.label;
    }
    return algorithmType;
  }

  return {
    // 基础状态
    loading,
    error,
    dimensions,
    categories,
    algorithms,
    apiHealthResult,
    editingCategory,
    editingDimension,
    // 过滤与分页状态
    searchKeyword,
    filterStatus,
    filterCategory,
    selectedDimensions,
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    // 模板与表单数据
    dimensionTemplate,
    newDimension,
    apiSettings,
    // 计算属性
    filteredDimensions,
    hierarchicalDimensions,
    isAllSelected,
    evaluationFields,
    // 数据获取
    fetchData,
    // 分页与过滤
    goToPage,
    prevPage,
    nextPage,
    onPageSizeChange,
    searchDimensions,
    filterDimensions,
    resetFilters,
    // 维度选择
    toggleSelectAll,
    toggleDimensionSelection,
    toggleGroupSelection,
    selectAllInGroup,
    toggleSelectAllInCategory,
    // 维度 CRUD
    saveDimension,
    deleteDimension,
    // API 健康检查 / 权重
    testAPIHealth,
    updateWeight,
    // 工具方法
    getAlgorithmLabel,
  };
}

export type UseEvaluationDimensionsReturn = ReturnType<typeof useEvaluationDimensions>;
