import { ref, reactive, computed, watch, nextTick } from 'vue';
import { getModalManager } from '../../composables/modal/useModal';
import { splApi, playbackApi } from '../../utils/api';
import Chart, { ChartDataset } from 'chart.js/auto';
import type {
  SPLMapping,
  SPLQueryParams,
  Device
} from '../../shared/types';
import { MODAL_TYPES } from '../../shared/types';
import { volumeToDb, DB_MIN, DB_MAX } from '../../utils/audioUtils';

export function useSplMapping() {
  // 响应式数据
  const mappingData = ref<SPLMapping[]>([]);
  const searchTerm = ref<string>('');
  const calibrationFilter = ref<'all' | 'calibrated' | 'uncalibrated'>('all');
  const deviceFilter = ref<string>('all');
  const playbackDevices = ref<Device[]>([]);

  const stats = reactive({
    total: 0,
    calibrated: 0,
    uncalibrated: 0,
    associatedDevices: 0
  });

  const formData = reactive({
    name: '',
    description: '',
    deviceId: '',
    deviceUniqueId: '',
    distance: 1,
    testFrequency: 1000,
    calibrationPoints: [{ digital_gain: null, spl: null }]
  });

  let isSubmitting = false;

  const showModal = ref(false);
  const showDetailsModal = ref(false);
  const editingMapping = ref(false);
  const selectedMappingId = ref<string | number | null>(null);
  const selectedMapping = ref<SPLMapping | null>(null);

  const charts = ref<Record<string, any>>({});

  const filteredMappings = computed(() => {
    let result = mappingData.value;
    
    if (searchTerm.value) {
      const term = searchTerm.value.toLowerCase();
      result = result.filter(m => 
        m.name.toLowerCase().includes(term) || 
        (m.description && m.description.toLowerCase().includes(term)) ||
        ((m.device?.name && m.device.name.toLowerCase().includes(term)) || (m.device_name && m.device_name.toLowerCase().includes(term)))
      );
    }
    
    if (calibrationFilter.value !== 'all') {
      result = result.filter(m =>
        m.calibration_status === calibrationFilter.value
      );
    }

    if (deviceFilter.value !== 'all') {
      result = result.filter(m =>
        m.device_id?.toString() === deviceFilter.value
      );
    }
    
    return result.map(m => {
      const points = m.calibration_data?.points || [];
      
      const validPoints = points.filter((p: any) => p && typeof p === 'object' && p.gainOffset !== undefined && p.spl !== undefined);
      
      let minOffset = null;
      let maxOffset = null;
      let minOffsetSpl = null;
      let maxOffsetSpl = null;
      
      if (validPoints.length > 0) {
        const sortedByOffset = [...validPoints].sort((a: any, b: any) => a.gainOffset - b.gainOffset);
        minOffset = sortedByOffset[0].gainOffset;
        maxOffset = sortedByOffset[sortedByOffset.length - 1].gainOffset;
        minOffsetSpl = sortedByOffset[0].spl;
        maxOffsetSpl = sortedByOffset[sortedByOffset.length - 1].spl;
      }

      const BASE_LEVEL_DBFS = -30;
      const baseLevel = BASE_LEVEL_DBFS;
      const finalLevelMin = minOffset !== null ? BASE_LEVEL_DBFS + minOffset : null;
      const finalLevelMax = maxOffset !== null ? BASE_LEVEL_DBFS + maxOffset : null;

      return {
        ...m,
        gainOffsetMin: minOffset,
        gainOffsetMax: maxOffset,
        minOffsetSpl: minOffsetSpl,
        maxOffsetSpl: maxOffsetSpl,
        calibrationPointsCount: validPoints.length,
        baseLevel: baseLevel,
        finalLevelMin: finalLevelMin,
        finalLevelMax: finalLevelMax,
        measurementDate: m.updated_at ? new Date(m.updated_at).toLocaleDateString() : undefined
      };
    });
  });

  // 分页状态
  const currentPage = ref(1);
  const pageSize = ref(6);
  const totalItems = ref(0);
  const totalPages = computed(() => Math.ceil(totalItems.value / pageSize.value));

  // 分页后的映射列表
  const paginatedMappings = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return filteredMappings.value.slice(start, end);
  });

  // 更新总数
  watch(filteredMappings, (newVal) => {
    totalItems.value = newVal.length;
    if (currentPage.value > totalPages.value && totalPages.value > 0) {
      currentPage.value = 1;
    }
  }, { immediate: true });

  // 分页方法
  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page;
    }
  };

  const handlePageSizeChange = (size: number) => {
    pageSize.value = size;
    currentPage.value = 1;
  };

  const handlePrevPage = () => {
    if (currentPage.value > 1) {
      currentPage.value--;
    }
  };

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
    }
  };

  async function searchMappings() {
    try {
      const params : SPLQueryParams = {
        keyword: searchTerm.value,
        calibration_status: calibrationFilter.value === 'all' ? undefined : calibrationFilter.value,
        device_id: deviceFilter.value === 'all' ? undefined : deviceFilter.value,
        page: 1,
        per_page: 100
      };
      const response = await splApi.getAll(params);
      if (response && response.items) {
        mappingData.value = response.items;
      }
    } catch (error) {
      console.error('获取映射数据失败:', error);
    }
  }

  async function fetchStats() {
    try {
      const response = await splApi.getStats();
      if (response) {
        stats.total = response.total || 0;
        stats.calibrated = response.calibrated || 0;
        stats.uncalibrated = response.uncalibrated || 0;
        stats.associatedDevices = response.associatedDevices || 0;
      }
    } catch (error) {
      console.error('获取统计数据失败:', error);
    }
  }

  function filterMappings() {
    searchMappings();
  }

  function filterByDevice() {
    console.log('Filtering by device:', deviceFilter.value);
    searchMappings();
  }

  async function initData() {
    await Promise.all([
      searchMappings(),
      fetchStats()
    ]);
  }

  function openAddMappingModal() {
    resetForm();
    editingMapping.value = false;
    showModal.value = true;
    const modalManager = getModalManager();
    
    const deviceOptions = playbackDevices.value.map(d => ({
      value: String(d.id),
      label: `${d.name}${d.model ? ` (${d.model})` : ''}`
    }));

    console.log('[openAddMappingModal] playbackDevices:', playbackDevices.value.length);
    console.log('[openAddMappingModal] deviceOptions:', deviceOptions);

    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '添加增益映射',
      entityName: '声压级映射',
      mode: 'create',
      width: '1000px',
      formData: formData,
      fields: [
        { key: 'name', label: '映射名称', type: 'text', required: true, placeholder: '请输入映射名称' },
        { key: 'description', label: '描述', type: 'textarea', placeholder: '请输入描述信息' },
        { 
          key: 'deviceId', 
          label: '关联设备', 
          type: 'select', 
          required: true, 
          options: deviceOptions,
          placeholder: '请选择关联播放设备'
        },
        { key: 'distance', label: '测量距离 (米)', type: 'number', required: true, min: 0.1, defaultValue: 1 },
        { key: 'testFrequency', label: '测试频率 (Hz)', type: 'number', required: true, min: 20, max: 20000, defaultValue: 1000 },
        { 
          key: 'calibrationPoints', 
          label: '增益点配置', 
          type: 'array', 
          arrayItemType: 'gainSpl',
          required: false,
          arrayItemTemplate: { gainOffset: null, digital_gain: null, spl: null },
          hint: '添加多个增益点，每个点包含数字增益和对应的SPL值'
        }
      ],
      onConfirm: async (result: any) => {
        if (isSubmitting) {
          console.log('[SPLMapping] 提交中，跳过重复提交');
          return;
        }
        
        isSubmitting = true;
        try {
          const submitData = { ...result.data };
          
          if (submitData.calibrationPoints !== undefined) {
            submitData.calibrationData = {
              points: submitData.calibrationPoints
            };
            delete submitData.calibrationPoints;
          }
          
          await splApi.create(submitData);
          await Promise.all([
            searchMappings(),
            fetchStats()
          ]);
          modalManager.close();
        } catch (error: any) {
          alert(`添加失败: ${error.message || '未知错误'}`);
        } finally {
          isSubmitting = false;
        }
      }
    });
  }

  async function editMapping(mapping: SPLMapping) {
    const modalManager = getModalManager();
    
    editingMapping.value = true;
    selectedMappingId.value = typeof mapping.id === 'string' ? parseInt(mapping.id) : mapping.id;
    
    Object.assign(formData, {
      name: mapping.name,
      description: mapping.description || '',
      deviceId: String(mapping.device_id || ''),
      deviceUniqueId: mapping.device?.device_unique_id || '',
      distance: mapping.distance || 1,
      testFrequency: mapping.test_frequency || 1000,
      calibrationPoints: mapping.calibration_data?.points || [{ digital_gain: null, spl: null }]
    });
    showModal.value = true;

    const deviceOptions = playbackDevices.value.map(d => ({
      value: String(d.id),
      label: `${d.name}${d.model ? ` (${d.model})` : ''}`
    }));

    console.log('[editMapping] formData:', formData);
    console.log('[editMapping] deviceOptions:', deviceOptions);

    modalManager.open(MODAL_TYPES.CRUD_FORM, {
      title: '编辑增益映射',
      entityName: '声压级映射',
      mode: 'edit',
      width: '1000px',
      formData: formData,
      fields: [
        { key: 'name', label: '映射名称', type: 'text', required: true, placeholder: '请输入映射名称' },
        { key: 'description', label: '描述', type: 'textarea', placeholder: '请输入描述信息' },
        { 
          key: 'deviceId', 
          label: '关联设备', 
          type: 'select', 
          required: true, 
          options: deviceOptions,
          placeholder: '请选择关联播放设备'
        },
        { key: 'distance', label: '测量距离 (米)', type: 'number', required: true, min: 0.1 },
        { key: 'testFrequency', label: '测试频率 (Hz)', type: 'number', required: true, min: 20, max: 20000 },
        { 
          key: 'calibrationPoints', 
          label: '增益点配置', 
          type: 'array', 
          arrayItemType: 'gainSpl',
          required: false,
          arrayItemTemplate: { gainOffset: null, digital_gain: null, spl: null },
          hint: '添加多个增益点，每个点包含数字增益和对应的SPL值'
        }
      ],
      onConfirm: async (result: any) => {
        if (isSubmitting) {
          console.log('[SPLMapping] 编辑提交中，跳过重复提交');
          return;
        }
        
        if (selectedMappingId.value) {
          isSubmitting = true;
          try {
            const submitData = { ...result.data };
            
            if (submitData.calibrationPoints !== undefined) {
              submitData.calibrationData = {
                points: submitData.calibrationPoints
              };
              delete submitData.calibrationPoints;
            }
            
            await splApi.update(selectedMappingId.value, submitData);
            await Promise.all([
              searchMappings(),
              fetchStats()
            ]);
            modalManager.close();
          } catch (error: any) {
            alert(`修改失败: ${error.message || '未知错误'}`);
          } finally {
            isSubmitting = false;
          }
        }
      }
    });
  }

  function viewMappingDetails(mapping: SPLMapping) {
    const modalManager = getModalManager();
    selectedMapping.value = mapping;
    showDetailsModal.value = true;
    modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
      title: '增益映射详情',
      data: mapping
    });
  }

  async function handleDeleteMapping(id: string | number) {
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '确认删除',
      content: '确定要删除此映射吗？此操作不可撤销。',
      onConfirm: async () => {
        await splApi.delete(id);
        await Promise.all([
          searchMappings(),
          fetchStats()
        ]);
      }
    });
  }

  function resetForm() {
    Object.assign(formData, {
      name: '',
      description: '',
      deviceId: '',
      distance: 1,
      testFrequency: 1000,
      calibrationPoints: [{ digital_gain: null, spl: null }]
    });
    selectedMappingId.value = null;
  }

  async function importMappingData() {
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.IMPORT_EXPORT, {
      title: '导入增益映射',
      type: 'import',
      onSuccess: searchMappings
    });
  }

  function generateChartData(mapping: SPLMapping) {
    const calibrationStatus = mapping.calibration_status;
    const calibrationData = mapping.calibration_data;

    const hasCalibrationData = calibrationData && calibrationData.points && calibrationData.points.length > 0;

    if (!hasCalibrationData) {
      const defaultLabels = ['-50', '-25', '0', '25', '50'];
      const defaultData = [0, 0, 0, 0, 0];
      return {
        labels: defaultLabels,
        measuredData: defaultData,
        isCalibrated: false,
        minDb: DB_MIN,
        maxDb: DB_MAX
      };
    }

    const points = calibrationData.points;
    const sortedPoints = [...points].sort((a: any, b: any) => {
      const aGainOffset = a.gainOffset ?? a.gain ?? 0;
      const bGainOffset = b.gainOffset ?? b.gain ?? 0;
      return aGainOffset - bGainOffset;
    });

    const labels = sortedPoints.map((p: any) => String(p.gainOffset ?? p.gain ?? 0));
    const measuredData = sortedPoints.map((p: any) => {
      const spl = p.spl ?? p.measuredSpl ?? p.targetSpl ?? 0;
      return typeof spl === 'number' ? spl : 0;
    });

    return {
      labels,
      measuredData,
      isCalibrated: true
    };
  }

  async function initCharts() {
    await nextTick();
    
    const container = document.querySelector('.spl-mapping-view');
    if (!container) return;
    
    // 安全销毁现有图表
    Object.keys(charts.value).forEach(key => {
      const chart = charts.value[key];
      if (chart && typeof chart.destroy === 'function') {
        try {
          chart.destroy();
        } catch (e) {
          console.warn('[initCharts] Failed to destroy chart:', e);
        }
      }
    });
    charts.value = {};
    
    filteredMappings.value.forEach((mapping) => {
      const chartId = `chart-${mapping.id}`;
      const canvas = document.getElementById(chartId) as HTMLCanvasElement;
      if (!canvas || !canvas.parentElement) return;
      
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      
      // 检查 canvas 是否可见
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      
      const chartData = generateChartData(mapping);

      const datasets: ChartDataset<'line'>[] = [{
        label: '实测 SPL',
        data: chartData.measuredData,
        borderColor: chartData.isCalibrated ? '#FF6A00' : '#CCCCCC',
        backgroundColor: chartData.isCalibrated ? 'rgba(255, 106, 0, 0.1)' : 'rgba(204, 204, 204, 0.1)',
        tension: 0.4,
        fill: true
      }];

      const measuredValidData = chartData.measuredData.filter(v => typeof v === 'number' && v > 0);
      const measuredMin = measuredValidData.length > 0 ? Math.min(...measuredValidData) : 50;
      const measuredMax = measuredValidData.length > 0 ? Math.max(...measuredValidData) : 80;

      try {
        charts.value[chartId] = new Chart(ctx, {
          type: 'line',
          data: {
            labels: chartData.labels,
            datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
              mode: 'index',
              intersect: false
            },
            plugins: {
              legend: { display: true, position: 'top' }
            },
            scales: {
              x: { title: { display: true, text: '增益偏移' } },
              y: {
                type: 'linear',
                display: true,
                position: 'left',
                title: { display: true, text: '实测 SPL (dB)', color: '#FF6A00' },
                min: Math.max(30, measuredMin - 10),
                max: Math.min(100, measuredMax + 10),
                grid: { color: 'rgba(255, 106, 0, 0.1)' }
              }
            },
            animation: false
          }
        });
      } catch (e) {
        console.warn('[initCharts] Failed to create chart:', e);
      }
    });
    
    if (showDetailsModal.value && selectedMapping.value) {
      const canvas = document.getElementById('detailsChart') as HTMLCanvasElement;
      if (!canvas || !canvas.parentElement) return;
      
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      
      const mapping = selectedMapping.value;
      const chartData = generateChartData(mapping);

      const datasets: ChartDataset<'line'>[] = [{
        label: '实测 SPL',
        data: chartData.measuredData,
        borderColor: chartData.isCalibrated ? '#FF6A00' : '#CCCCCC',
        backgroundColor: chartData.isCalibrated ? 'rgba(255, 106, 0, 0.1)' : 'rgba(204, 204, 204, 0.1)',
        tension: 0.4,
        fill: true
      }];

      const measuredValidData = chartData.measuredData.filter(v => typeof v === 'number' && v > 0);
      const measuredMin = measuredValidData.length > 0 ? Math.min(...measuredValidData) : 50;
      const measuredMax = measuredValidData.length > 0 ? Math.max(...measuredValidData) : 80;

      try {
        charts.value['detailsChart'] = new Chart(ctx, {
          type: 'line',
          data: {
            labels: chartData.labels,
            datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
              mode: 'index',
              intersect: false
            },
            plugins: {
              legend: { display: true, position: 'top' }
            },
            scales: {
              x: { title: { display: true, text: '增益偏移' } },
              y: {
                type: 'linear',
                display: true,
                position: 'left',
                title: { display: true, text: '实测 SPL (dB)', color: '#FF6A00' },
                min: Math.max(30, measuredMin - 10),
                max: Math.min(100, measuredMax + 10),
                grid: { color: 'rgba(255, 106, 0, 0.1)' }
              }
            },
            animation: false
          }
        });
      } catch (e) {
        console.warn('[initCharts] Failed to create details chart:', e);
      }
    }
  }

  function initModalWatchers() {
    watch(filteredMappings, () => {
      nextTick(() => {
        initCharts();
      });
    }, { deep: true });

    watch(showDetailsModal, (newVal) => {
      if (newVal) {
        nextTick(() => {
          initCharts();
        });
      }
    });
  }

  function resetAllStates() {
    const modalManager = getModalManager();
    searchTerm.value = '';
    calibrationFilter.value = 'all';
    resetForm();
    modalManager.closeAll();
    editingMapping.value = false;
    selectedMappingId.value = null;
    selectedMapping.value = null;
  }

  async function fetchDevices() {
    try {
      const response = await playbackApi.getAll({ perPage: 1000 });
      if (response) {
        if (Array.isArray(response)) {
          playbackDevices.value = response;
        } else if (response.items) {
          playbackDevices.value = response.items;
        }
      }
    } catch (error) {
      console.error('获取设备列表失败:', error);
    }
  }

  return {
    mappingData,
    searchTerm,
    calibrationFilter,
    deviceFilter,
    playbackDevices,
    stats,
    formData,
    showModal,
    showDetailsModal,
    editingMapping,
    selectedMappingId,
    selectedMapping,
    filteredMappings,
    paginatedMappings,
    // 分页相关
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    handlePageChange,
    handlePageSizeChange,
    handlePrevPage,
    handleNextPage,
    searchMappings,
    fetchStats,
    fetchDevices,
    filterMappings,
    filterByDevice,
    openAddMappingModal,
    editMapping,
    viewMappingDetails,
    handleDeleteMapping,
    importMappingData,
    initModalWatchers,
    initData,
    initCharts
  };
}