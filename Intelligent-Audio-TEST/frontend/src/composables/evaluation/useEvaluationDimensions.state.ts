/**
 * useEvaluationDimensions —— 共享状态与派生数据
 *
 * 集中声明维度管理模块的全部共享响应式状态（跨 loaders/form/selection/normalize/save 复用同一份引用）、
 * 维度模板与新建表单初值，以及列表过滤/全选/层级展示等派生计算属性和算法标签工具方法。
 */
import { ref, computed } from 'vue';
import {
  EvaluationDimension,
  EvaluationCategory,
} from '../../domain';
import type { DimensionHealthCheckResult } from '../../domain/model/evaluationTypes';
import { ViewMode, TestType } from '@/domain/enums';
import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_MAX_PROCESS,
  DEFAULT_MAX_TIMEOUT,
  DEFAULT_MAX_AUDIO_DURATION,
  DEFAULT_API_TIMEOUT,
  DEFAULT_EDITOR_API_TIMEOUT,
  DEFAULT_LLM_MAX_TOKENS,
  DEFAULT_LLM_TEMPERATURE,
  DIMENSION_TYPE_SUB,
} from './useEvaluationDimensions.constants';

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

/** 创建评估维度管理共享状态（状态 / 模板 / 派生计算属性 / 工具方法） */
export function createEvalDimensionState() {
  // ========== 基础状态 ==========
  const loading = ref(false);
  const error = ref<string | null>(null);

  const searchKeyword = ref('');
  const filterStatus = ref<'all' | 'active' | 'inactive'>('all');
  const filterCategory = ref(ViewMode.ALL);
  const filterAlgorithm = ref('all');

  const selectedDimensions = ref<(number | string)[]>([]);

  const currentPage = ref(1);
  const pageSize = ref(DEFAULT_PAGE_SIZE);
  const totalItems = ref(0);
  const totalPages = ref(0);

  const dimensions = ref<EvaluationDimension[]>([]);
  const categories = ref<EvaluationCategory[]>([]);
  const algorithms = ref<{ value: string; label: string }[]>([]);
  const apiHealthResult = ref<DimensionHealthCheckResult | null>(null);

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
      { key: 'asr_result', label: 'ASR识别结果', source: TestType.API, required: true, description: 'ASR算法识别出的文本' },
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
      { key: 'asr_result', label: 'ASR识别结果', source: TestType.API, required: true, description: 'ASR算法识别出的文本' },
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

  // ========== 视图模式（列表/分组） ==========
  // 'list' 列表视图（平铺表格） | 'group' 分组视图（按分类聚合）
  const viewMode = ref<'list' | 'group'>('list');
  // 分组折叠状态：key 为分类 id（'uncategorized' 表示未分类组），缺省默认展开
  const collapsedGroups = ref<Record<string, boolean>>({});

  function isGroupExpanded(key: string): boolean {
    return !collapsedGroups.value[key];
  }

  function toggleGroupExpanded(key: string) {
    collapsedGroups.value = { ...collapsedGroups.value, [key]: isGroupExpanded(key) };
  }

  // ========== 计算属性 ==========
  const filteredDimensions = computed(() => {
    const all = dimensions.value;
    const keyword = (searchKeyword.value || '').trim().toLowerCase();

    // 单个维度的筛选匹配（搜索 / 状态 / 分类 / 关联算法）
    const matches = (dim: EvaluationDimension): boolean => {
      const matchesSearch = !keyword ||
        dim.name.toLowerCase().includes(keyword) ||
        (dim.description && dim.description.toLowerCase().includes(keyword)) ||
        ((dim as any).keywords || '').toLowerCase().includes(keyword);
      const matchesStatus = filterStatus.value === 'all' ||
        (filterStatus.value === 'active' && dim.status) ||
        (filterStatus.value === 'inactive' && !dim.status);
      const matchesCategory = filterCategory.value === 'all' ||
        dim.categoryId === Number(filterCategory.value) ||
        dim.type === filterCategory.value;
      const matchesAlgorithm = filterAlgorithm.value === 'all' ||
        (dim.associatedAlgorithms || []).some((algo: any) =>
          typeof algo === 'string'
            ? algo === filterAlgorithm.value
            : algo?.algorithmType === filterAlgorithm.value
        );
      return matchesSearch && matchesStatus && matchesCategory && matchesAlgorithm;
    };

    const matchedIds = new Set<number | string>();
    for (const dim of all) {
      if (matches(dim)) matchedIds.add(dim.id);
    }

    // 主/子联动：子维度命中时带上父维度作为上下文；搜索/算法筛选命中主维度时整组展示，
    // 避免出现「孤儿子维度」被甩到列表底部、父子显示不在一块的问题
    const byParentId = new Map<number | string, EvaluationDimension[]>();
    for (const dim of all) {
      const pid = dim.parentDimensionId ?? '';
      if (!byParentId.has(pid)) byParentId.set(pid, []);
      byParentId.get(pid)!.push(dim);
    }

    const groupIds = new Set<number | string>();
    for (const dim of all) {
      if (!dim.parentDimensionId) {
        if (matchedIds.has(dim.id)) {
          groupIds.add(dim.id);
          for (const child of byParentId.get(dim.id) || []) {
            // 搜索/算法筛选时主维度命中则整组展示（子维度作为该维度的完整上下文）
            if (keyword || filterAlgorithm.value !== 'all' || matchedIds.has(child.id)) groupIds.add(child.id);
          }
        }
      } else if (matchedIds.has(dim.id)) {
        groupIds.add(dim.id);
        groupIds.add(dim.parentDimensionId);
      }
    }

    return all.filter(dim => groupIds.has(dim.id));
  });

  const isAllSelected = computed(() => {
    return filteredDimensions.value.length > 0 &&
      selectedDimensions.value.length === filteredDimensions.value.length;
  });

  // 层级维度：主维度在前，子维度紧跟其父维度
  const hierarchicalDimensions = computed(() => {
    const filtered = filteredDimensions.value;
    const mainDims = filtered.filter(d => !d.parentDimensionId && d.dimensionType !== DIMENSION_TYPE_SUB);
    const subDims = filtered.filter(d => d.parentDimensionId || d.dimensionType === DIMENSION_TYPE_SUB);

    const result: any[] = [];
    const placedIds = new Set<number | string>();

    for (const main of mainDims) {
      result.push({ ...main, _level: 0, _isMain: true, _parentName: '' });
      placedIds.add(main.id);

      const children = subDims.filter(s => s.parentDimensionId === main.id);
      for (const child of children) {
        result.push({ ...child, _level: 1, _isMain: false, _parentName: main.name });
        placedIds.add(child.id);
      }
    }

    // 孤儿子维度：父维度不在当前筛选结果中
    for (const sub of subDims) {
      if (!placedIds.has(sub.id)) {
        const parent = dimensions.value.find(d => d.id === sub.parentDimensionId);
        result.push({ ...sub, _level: 1, _isMain: false, _parentName: parent?.name || '' });
        placedIds.add(sub.id);
      }
    }

    return result;
  });

  // 分组视图数据：基于 hierarchicalDimensions（已含主/子层级）按分类聚合，
  // 未设置分类的维度归入「未分类」组，保证每个维度都有归属
  const groupedDimensions = computed(() => {
    const list = hierarchicalDimensions.value;
    const byCategory = new Map<string, any[]>();
    const uncategorized: any[] = [];

    for (const dim of list) {
      const catId = dim.categoryId;
      if (catId === null || catId === undefined || catId === '') {
        uncategorized.push(dim);
      } else {
        const key = String(catId);
        if (!byCategory.has(key)) byCategory.set(key, []);
        byCategory.get(key)!.push(dim);
      }
    }

    const groups: { key: string; category: EvaluationCategory | null; items: any[] }[] = [];

    // 分类按接口返回顺序展示（无维度数据的空分类不展示）
    for (const cat of categories.value) {
      const items = byCategory.get(String(cat.id));
      if (items && items.length > 0) {
        groups.push({ key: String(cat.id), category: cat, items });
      }
    }

    // 兜底：存在分类id但分类信息未加载到的维度，作为独立组展示
    for (const [key, items] of byCategory.entries()) {
      if (!groups.some(g => g.key === key)) {
        groups.push({ key, category: null, items });
      }
    }

    if (uncategorized.length > 0) {
      groups.push({ key: 'uncategorized', category: null, items: uncategorized });
    }

    return groups;
  });

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
    filterAlgorithm,
    selectedDimensions,
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    // 视图模式（列表/分组）
    viewMode,
    collapsedGroups,
    isGroupExpanded,
    toggleGroupExpanded,
    // 模板与表单数据
    dimensionTemplate,
    newDimension,
    apiSettings,
    // 计算属性
    filteredDimensions,
    isAllSelected,
    hierarchicalDimensions,
    groupedDimensions,
    // 工具方法
    getAlgorithmLabel,
  };
}

/** 评估维度共享状态类型（由工厂推断） */
export type EvalDimensionState = ReturnType<typeof createEvalDimensionState>;
