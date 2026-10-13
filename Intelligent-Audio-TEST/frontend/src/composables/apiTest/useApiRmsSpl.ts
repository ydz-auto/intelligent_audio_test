// -*- coding: utf-8 -*-
/**
 * API RMS→SPL 映射（数字域灵敏度）composable —— INT-300
 * 与 useSplMapping（设备物理域 E2E）对称的 API/Realtime 口径：
 * - 列表按 API 过滤、映射 CRUD、校准（点集全量替换）、设默认
 * - 状态徽章/校准历史对齐设备侧展示口径
 * 依赖方向：views → 本 composable → apiRmsSplPort（Application）→ Infrastructure
 */
import { ref, computed } from 'vue';
import { apiRmsSplPort } from './apiRmsSplPort';
import { apisPort } from './apisPort';
import { getModalManager } from '../modal/useModal';
import { MODAL_TYPES } from '../modal/constants';
import { useNotification } from '../modal/useNotification';
import { CalibrationStatus } from '../../domain/enums';
import type { ApiRmsSplMapping, ApiRmsSplUpsertInput, ApiCalibrationPoint } from '../../domain';
import type { APIConfig } from '../../domain';

/** 校准状态徽章文案（enum 化，禁止魔法字符串散落） */
export const CALIBRATION_STATUS_LABELS: Record<string, string> = {
  [CalibrationStatus.CALIBRATED]: '已校准',
  [CalibrationStatus.UNCALIBRATED]: '未校准',
};

export function useApiRmsSpl() {
  const notification = useNotification();

  // ===== 响应式数据 =====
  const mappingData = ref<ApiRmsSplMapping[]>([]);
  const apiList = ref<APIConfig[]>([]);
  const apiFilter = ref<string>('all');
  const calibrationFilter = ref<'all' | 'calibrated' | 'uncalibrated'>('all');
  const searchTerm = ref<string>('');
  const loading = ref(false);

  const stats = computed(() => {
    const total = mappingData.value.length;
    const calibrated = mappingData.value.filter(m => m.calibrationStatus === CalibrationStatus.CALIBRATED).length;
    // 关联 API 数 = 被映射引用的去重 API 数
    const associatedApis = new Set(mappingData.value.map(m => String(m.apiId))).size;
    return { total, calibrated, uncalibrated: total - calibrated, associatedApis };
  });

  /** 拉取映射全量（后端 list 支持 api_id/calibration_status 过滤；关键词前端过滤） */
  async function searchMappings() {
    loading.value = true;
    try {
      const response = await apiRmsSplPort.getAll({
        apiId: apiFilter.value === 'all' ? undefined : apiFilter.value,
        calibrationStatus: calibrationFilter.value === 'all' ? undefined : calibrationFilter.value,
        page: 1,
        perPage: 100,
      });
      mappingData.value = response?.items ?? [];
    } catch (error) {
      console.error('[useApiRmsSpl] 获取映射数据失败:', error);
      notification.error('获取 RMS-SPL 映射数据失败');
    } finally {
      loading.value = false;
    }
  }

  /** 拉取被测 API 列表（下拉选项；apisPort 已展平为 camelCase Domain 数组） */
  async function fetchApis() {
    try {
      apiList.value = await apisPort.getAll({ perPage: 1000 });
    } catch (error) {
      console.error('[useApiRmsSpl] 获取 API 列表失败:', error);
    }
  }

  function apiName(apiId: string | number | undefined): string {
    if (apiId === undefined || apiId === null) return '-';
    const api = apiList.value.find(a => String(a.id) === String(apiId));
    return api?.name ?? `API #${apiId}`;
  }

  /** 映射是否为该 API 当前默认（apis.rmsSplMappingId 指针） */
  function isDefaultMapping(mapping: ApiRmsSplMapping): boolean {
    const api = apiList.value.find(a => String(a.id) === String(mapping.apiId));
    return api?.rmsSplMappingId != null && String(api.rmsSplMappingId) === String(mapping.id);
  }

  const filteredMappings = computed(() => {
    let result = mappingData.value;
    if (searchTerm.value) {
      const term = searchTerm.value.toLowerCase();
      result = result.filter(m =>
        (m.name || '').toLowerCase().includes(term) ||
        (m.vendor || '').toLowerCase().includes(term) ||
        (m.protocol || '').toLowerCase().includes(term) ||
        apiName(m.apiId).toLowerCase().includes(term)
      );
    }
    return result;
  });

  // ===== 弹窗：新增/编辑映射 =====
  let isSubmitting = false;

  function upsertFields(mapping?: ApiRmsSplMapping) {
    const apiOptions = apiList.value.map(a => ({
      value: String(a.id),
      label: `${a.name}${a.vendor ? ` (${a.vendor})` : ''}`,
    }));
    const isEdit = !!mapping;
    const fields = [
      ...(isEdit ? [] : [{
        key: 'apiId',
        label: '关联被测 API',
        type: 'select',
        required: true,
        options: apiOptions,
        placeholder: '请选择被测 API（API 1:N 映射）',
      }]),
      { key: 'name', label: '映射名称', type: 'text', required: true, placeholder: '请输入映射名称' },
      { key: 'vendor', label: '供应商 (vendor)', type: 'text', placeholder: '如 volc_ast / qwen_llm' },
      {
        key: 'protocol',
        label: '协议',
        type: 'select',
        options: [
          { value: 'websocket', label: 'WebSocket (Realtime)' },
          { value: 'http', label: 'HTTP (非实时/流式)' },
        ],
        defaultValue: 'websocket',
      },
      {
        key: 'referenceSpl',
        label: '参考声压级 (dB SPL)',
        type: 'number',
        min: 30,
        max: 120,
        step: 0.1,
        defaultValue: 65,
        hint: '未校准时的参考基准（30-120 dB）',
      },
      {
        key: 'referenceGainLinear',
        label: '参考线性增益',
        type: 'number',
        min: 0.001,
        step: 0.001,
        defaultValue: 1.0,
        hint: '未校准时的参考增益（正数）',
      },
      {
        key: 'minGainLinear',
        label: '增益下限',
        type: 'number',
        min: 0.001,
        step: 0.001,
        defaultValue: 0.001,
        hint: '防静音限幅',
      },
      {
        key: 'maxGainLinear',
        label: '增益上限',
        type: 'number',
        min: 0.001,
        step: 0.1,
        defaultValue: 10.0,
        hint: '防爆音限幅',
      },
    ] as any[];
    return fields;
  }

  function formDataFrom(mapping?: ApiRmsSplMapping) {
    return {
      apiId: mapping ? String(mapping.apiId) : '',
      name: mapping?.name ?? '',
      vendor: mapping?.vendor ?? '',
      protocol: mapping?.protocol ?? 'websocket',
      referenceSpl: mapping?.referenceSpl ?? 65,
      referenceGainLinear: mapping?.referenceGainLinear ?? 1.0,
      minGainLinear: mapping?.minGainLinear ?? 0.001,
      maxGainLinear: mapping?.maxGainLinear ?? 10.0,
    };
  }

  function openAddMappingModal() {
    const modalManager = getModalManager();
    const formData = formDataFrom();
    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '添加 RMS-SPL 映射',
      entityName: 'API RMS-SPL 映射',
      mode: 'create',
      width: '720px',
      formData,
      fields: upsertFields(),
      onConfirm: async (result: any) => {
        if (isSubmitting) return;
        isSubmitting = true;
        try {
          const input: ApiRmsSplUpsertInput = { ...result.data, apiId: result.data.apiId };
          await apiRmsSplPort.create(input);
          notification.success('RMS-SPL 映射创建成功');
          await searchMappings();
          await fetchApis();
          modalManager.close();
        } catch (error: any) {
          notification.error(`添加失败: ${error?.message || '未知错误'}`);
        } finally {
          isSubmitting = false;
        }
      },
    });
  }

  function openEditMappingModal(mapping: ApiRmsSplMapping) {
    const modalManager = getModalManager();
    const formData = formDataFrom(mapping);
    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '编辑 RMS-SPL 映射',
      entityName: 'API RMS-SPL 映射',
      mode: 'edit',
      width: '720px',
      formData,
      fields: upsertFields(mapping),
      onConfirm: async (result: any) => {
        if (isSubmitting) return;
        isSubmitting = true;
        try {
          const { apiId: _ignored, ...rest } = result.data;
          await apiRmsSplPort.update(mapping.id, rest);
          notification.success('RMS-SPL 映射更新成功');
          await searchMappings();
          await fetchApis();
          modalManager.close();
        } catch (error: any) {
          notification.error(`修改失败: ${error?.message || '未知错误'}`);
        } finally {
          isSubmitting = false;
        }
      },
    });
  }

  function viewMappingDetails(mapping: ApiRmsSplMapping) {
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
      title: 'RMS-SPL 映射详情',
      data: {
        ...mapping,
        apiName: apiName(mapping.apiId),
        isDefault: isDefaultMapping(mapping),
        calibrationPointsCount: mapping.calibrationPoints?.length ?? 0,
      },
    });
  }

  async function handleDeleteMapping(mapping: ApiRmsSplMapping) {
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '确认删除',
      content: `确定要删除映射「${mapping.name || mapping.id}」吗？此操作不可撤销。`,
      onConfirm: async () => {
        try {
          await apiRmsSplPort.remove(mapping.id);
          notification.success('RMS-SPL 映射已删除');
          await Promise.all([searchMappings(), fetchApis()]);
        } catch (error: any) {
          notification.error(`删除失败: ${error?.message || '未知错误'}`);
        }
      },
    });
  }

  // ===== 校准（数字域：点集 target_spl ↔ gain_linear ↔ rms_dbfs）=====
  function openCalibrationModal(mapping: ApiRmsSplMapping) {
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.API_RMS_SPL_CALIBRATION, {
      title: 'RMS-SPL 数字校准',
      mappingId: mapping.id,
      mappingName: mapping.name || `映射 #${mapping.id}`,
      apiId: mapping.apiId,
      data: {
        calibrationPoints: (mapping.calibrationPoints ?? []).map(p => ({ ...p })),
        referenceSpl: mapping.referenceSpl ?? 65,
        referenceGainLinear: mapping.referenceGainLinear ?? 1.0,
        minGainLinear: mapping.minGainLinear ?? 0.001,
        maxGainLinear: mapping.maxGainLinear ?? 10.0,
      },
      // 数字域校准：提交点集全量替换并置已校准（后端分布式锁互斥，409 冲突提示）
      onConfirm: async (payload: { points: ApiCalibrationPoint[] }) => {
        try {
          await apiRmsSplPort.calibrate(mapping.id, payload.points);
          notification.success('校准完成：校准点已落库并置为已校准');
          await searchMappings();
        } catch (error: any) {
          // 409：同 API 并发校准互斥（DistributedLock lock:spl:calibration:{api_id}）
          notification.error(`校准失败: ${error?.message || '未知错误'}`);
          throw error;
        }
      },
    });
  }

  /** 设为 API 当前默认映射（apis.rms_spl_mapping_id）；再次点击已默认的则清除 */
  async function toggleDefaultMapping(mapping: ApiRmsSplMapping) {
    const isDefault = isDefaultMapping(mapping);
    try {
      await apiRmsSplPort.setDefault(mapping.apiId, isDefault ? null : mapping.id);
      notification.success(isDefault ? '已清除默认映射' : '已设为该 API 的默认映射');
      await fetchApis();
    } catch (error: any) {
      notification.error(`设置默认映射失败: ${error?.message || '未知错误'}`);
    }
  }

  async function initData() {
    await Promise.all([searchMappings(), fetchApis()]);
  }

  function resetFilters() {
    searchTerm.value = '';
    apiFilter.value = 'all';
    calibrationFilter.value = 'all';
  }

  return {
    mappingData,
    filteredMappings,
    apiList,
    apiFilter,
    calibrationFilter,
    searchTerm,
    loading,
    stats,
    apiName,
    isDefaultMapping,
    searchMappings,
    fetchApis,
    filterMappings: searchMappings,
    filterByApi: searchMappings,
    openAddMappingModal,
    openEditMappingModal,
    viewMappingDetails,
    handleDeleteMapping,
    openCalibrationModal,
    toggleDefaultMapping,
    initData,
    resetFilters,
  };
}
