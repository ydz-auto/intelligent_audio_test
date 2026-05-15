import { ref, reactive, computed, watch, nextTick } from 'vue';
import { getModalManager } from '../../composables/useModal';
import { splApi, playbackApi } from '../../utils/api';
import Chart from 'chart.js/auto';
import type { 
  SPLMapping, 
  SPLQueryParams, 
  Device
} from '../../shared/types';
import { MODAL_TYPES } from '../../shared/types';
import { useModalStore } from '../../store/modalStore';

export function useSplMapping() {
  const mappingData = ref<SPLMapping[]>([]);
  const searchTerm = ref<string>('');
  const calibrationFilter = ref<'all' | 'calibrated' | 'uncalibrated'>('all');
  const deviceFilter = ref<string>('all');
  const playbackDevices = ref<Device[]>([]);

  const stats = reactive({
    total: 0,
    calibrated: 0,
    uncalibrated: 0,
    associated_devices: 0
  });

  const formData = reactive({
    name: '',
    description: '',
    device_id: '',
    distance: 1,
    test_frequency: 1000,
    is_current: false,
    calibration_points: [] as Array<{ gain: number | null; spl: number | null }>
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
        (m.calibration_status === calibrationFilter.value)
      );
    }
    
    if (deviceFilter.value !== 'all') {
      result = result.filter(m => 
        m.device_id?.toString() === deviceFilter.value
      );
    }
    
    return result.map(m => {
      const points = m.calibration_data?.points || [];
      const gain1 = points.find((p: any) => p.gain === 1)?.spl;
      const gain50 = points.find((p: any) => p.gain === 50)?.spl;
      const gain100 = points.find((p: any) => p.gain === 100)?.spl;
      
      const findClosest = (targetGain: number) => {
        if (points.length === 0) return undefined;
        return points.reduce((prev: any, curr: any) => {
          const prevGain = prev.gain || 0;
          const currGain = curr.gain || 0;
          return Math.abs(currGain - targetGain) < Math.abs(prevGain - targetGain) ? curr : prev;
        }).spl;
      };

      return {
        ...m, 
        gain1Spl: gain1 ?? findClosest(1), 
        gain50Spl: gain50 ?? findClosest(50), 
        gain100Spl: gain100 ?? findClosest(100), 
        measurementDate: m.last_calibrated_at ? new Date(m.last_calibrated_at).toLocaleDateString() : undefined
      };
    });
  });

  async function searchMappings() {
    try {
      const params : SPLQueryParams = {keyword: searchTerm.value, calibration_status: calibrationFilter.value === 'all' ? undefined : calibrationFilter.value};
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
        stats.associated_devices = response.associated_devices || 0;
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
      formData: formData,
      fields: [
        { key: 'name', label: '映射名称', type: 'text', required: true, placeholder: '请输入映射名称' },
        { key: 'description', label: '描述', type: 'textarea', placeholder: '请输入描述信息' },
        { 
          key: 'device_id', 
          label: '关联设备', 
          type: 'select', 
          required: true, 
          options: deviceOptions,
          placeholder: '请选择关联播放设备'
        },
        {
          key: 'is_current',
          label: '设为当前映射',
          type: 'switch',
          hint: '选中后，该映射将立即应用于所选设备'
        },
        { key: 'distance', label: '测量距离 (米)', type: 'number', required: true, min: 0.1, defaultValue: 1 },
        { key: 'test_frequency', label: '测试频率 (Hz)', type: 'number', required: true, min: 20, max: 20000, defaultValue: 1000 },
        { 
          key: 'calibration_points', 
          label: '增益点配置', 
          type: 'array', 
          arrayItemType: 'gain_spl',
          required: false,
          arrayItemTemplate: {gain: null, spl: null},
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
          const submitData = {...result.data};
          
          if (submitData.calibration_points !== undefined) {
            submitData.calibration_data = {points: submitData.calibration_points};
            delete submitData.calibration_points;
          }
          
          await splApi.create(submitData);
          await searchMappings();
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
    const modalStore = useModalStore();
    
    editingMapping.value = true;
    selectedMappingId.value = typeof mapping.id === 'string' ? parseInt(mapping.id) : mapping.id;
    
    modalStore.clearDraft('声压级映射_edit');
    Object.assign(formData, {
      name: mapping.name,
      description: mapping.description || '',
      device_id: String(mapping.device_id || ''),
      distance: mapping.distance || 1,
      test_frequency: mapping.test_frequency || 1000,
      is_current: !!mapping.is_current,
      calibration_points: mapping.calibration_data?.points || [{ gain: null, spl: null }]
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
      formData: formData,
      fields: [
        { key: 'name', label: '映射名称', type: 'text', required: true, placeholder: '请输入映射名称' },
        { key: 'description', label: '描述', type: 'textarea', placeholder: '请输入描述信息' },
        { 
          key: 'device_id', 
          label: '关联设备', 
          type: 'select', 
          required: true, 
          options: deviceOptions,
          placeholder: '请选择关联播放设备'
        },
        {
          key: 'is_current',
          label: '设为当前映射',
          type: 'switch',
          hint: '选中后，该映射将立即应用于所选设备'
        },
        { key: 'distance', label: '测量距离 (米)', type: 'number', required: true, min: 0.1 },
        { key: 'test_frequency', label: '测试频率 (Hz)', type: 'number', required: true, min: 20, max: 20000 },
        { 
          key: 'calibration_points', 
          label: '增益点配置', 
          type: 'array', 
          arrayItemType: 'gain_spl',
          required: false,
          arrayItemTemplate: {gain: null, spl: null},
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
            const submitData = {...result.data};
            
            if (submitData.calibration_points !== undefined) {
              submitData.calibration_data = {points: submitData.calibration_points};
              delete submitData.calibration_points;
            }
            
            await splApi.update(selectedMappingId.value, submitData);
            await searchMappings();
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
        await searchMappings();
      }
    });
  }

  function resetForm() {
    Object.assign(formData, {
      name: '',
      description: '',
      device_id: '',
      distance: 1,
      test_frequency: 1000,
      is_current: false,
      calibration_points: [{ gain: null, spl: null }]
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
    const calibration_status = mapping.calibration_status;
    const calibration_data = mapping.calibration_data;
    
    if (calibration_status === 'uncalibrated' || !calibration_data || !calibration_data.points || calibration_data.points.length === 0) {
      return {labels: ['1', '20', '40', '60', '80', '100'], data: [0, 0, 0, 0, 0, 0], isCalibrated: false};
    }
    
    const points = calibration_data.points;
    const sortedPoints = [...points].sort((a: any, b: any) => (a.gain || 0) - (b.gain || 0));
    
    const labels = sortedPoints.map((p: any) => (p.gain || 0).toString());
    const data = sortedPoints.map((p: any) => p.spl || p.measured_spl || p.target_spl || 0);
    
    return {labels, data, isCalibrated: true};
  }

  async function initCharts() {
    await nextTick();
    
    const container = document.querySelector('.spl-mapping-view');
    if (!container) return;
    
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
      
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      
      const chartData = generateChartData(mapping);
      
      try {
        charts.value[chartId] = new Chart(ctx, {
          type: 'line',
          data: {labels: chartData.labels, datasets: [{
              label: '增益-SPL关系', data: chartData.data, borderColor: chartData.isCalibrated ? '#FF6A00' : '#CCCCCC', backgroundColor: chartData.isCalibrated ? 'rgba(255, 106, 0, 0.1)' : 'rgba(204, 204, 204, 0.1)', tension: 0.4, fill: true}]
          },
          options: {responsive: true, maintainAspectRatio: false, plugins: {
              legend: { display: false},
              tooltip: {mode: 'index', intersect: false}
            },
            scales: {x: { title: { display: true, text: '数字增益 (1-100)'} },
              y: {title: { display: true, text: '声压级 (dB)'}, min: 40, max: 100 }
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
      
      try {
        charts.value['detailsChart'] = new Chart(ctx, {
          type: 'line',
          data: {labels: chartData.labels, datasets: [{
              label: '增益-SPL关系', data: chartData.data, borderColor: chartData.isCalibrated ? '#FF6A00' : '#CCCCCC', backgroundColor: chartData.isCalibrated ? 'rgba(255, 106, 0, 0.1)' : 'rgba(204, 204, 204, 0.1)', tension: 0.4, fill: true}]
          },
          options: {responsive: true, maintainAspectRatio: true, plugins: {
              legend: { display: true},
              tooltip: {mode: 'index', intersect: false}
            },
            scales: {x: { title: { display: true, text: '数字增益 (1-100)'} },
              y: {title: { display: true, text: '声压级 (dB)'}, min: 40, max: 100 }
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
      const response = await playbackApi.getAll({ per_page: 1000 });
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
    initData
  };
}
