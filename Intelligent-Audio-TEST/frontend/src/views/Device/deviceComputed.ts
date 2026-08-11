import { computed, watch } from 'vue';
import {
  activeTab,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmFilter,
  algorithmTypeFilter,
  testDevices,
  playbackDevices,
  apiDevices,
  playbackCurrentPage,
  playbackPageSize,
  playbackTotalItems,
  playbackTotalPages,
  testCurrentPage,
  testPageSize,
  testTotalItems,
  testTotalPages,
  apiCurrentPage,
  apiPageSize,
  apiTotalItems,
  apiTotalPages
} from './deviceState';

export const addButtonText = computed(() => {
  switch (activeTab.value) {
    case 'playback':
      return '添加播放设备';
    case 'api':
      return '添加测试API';
    default:
      return '添加测试设备';
  }
});

export const stats = computed(() => {
  if (activeTab.value === 'playback') {
    return [
      { value: playbackDevices.value.filter(d => d && d.name).length, label: '总设备数', icon: 'fas fa-headphones', iconClass: 'device-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '在线设备', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '离线设备', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中设备', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  } else if (activeTab.value === 'api') {
    return [
      { value: apiDevices.value.filter(d => d && d.name).length, label: '总测试API数', icon: 'fas fa-exchange-alt', iconClass: 'device-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '可用API', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '不可用API', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中API', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  } else {
    return [
      { value: testDevices.value.filter(d => d && d.name).length, label: '总测试设备数', icon: 'fas fa-microphone', iconClass: 'device-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '在线测试设备', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '离线测试设备', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中设备', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  }
});

export const allFilteredPlaybackDevices = computed(() => {
  return playbackDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value ||
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase()));

    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;

    const typeMapping: Record<string, string> = { '干声': 'dry', '噪声': 'noise' };
    const actualFilterType = playbackTypeFilter.value === 'all' ? 'all' : typeMapping[playbackTypeFilter.value] || playbackTypeFilter.value;
    const matchesPlaybackType = actualFilterType === 'all' || device.type === actualFilterType;

    return matchesSearch && matchesStatus && matchesPlaybackType;
  });
});

export const filteredPlaybackDevices = computed(() => {
  const start = (playbackCurrentPage.value - 1) * playbackPageSize.value;
  const end = start + playbackPageSize.value;
  return allFilteredPlaybackDevices.value.slice(start, end);
});

watch(allFilteredPlaybackDevices, (newVal) => {
  playbackTotalItems.value = newVal.length;
  if (playbackCurrentPage.value > playbackTotalPages.value && playbackTotalPages.value > 0) {
    playbackCurrentPage.value = 1;
  }
}, { immediate: true });

export const allFilteredTestDevices = computed(() => {
  return testDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value ||
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.category && device.category.toLowerCase().includes(searchQuery.value.toLowerCase()));
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    const matchesAlgorithm = algorithmFilter.value === 'all' ||
      (device.supportedAlgorithms && device.supportedAlgorithms.includes(algorithmFilter.value));
    return matchesSearch && matchesStatus && matchesAlgorithm;
  });
});

export const filteredTestDevices = computed(() => {
  const start = (testCurrentPage.value - 1) * testPageSize.value;
  const end = start + testPageSize.value;
  return allFilteredTestDevices.value.slice(start, end);
});

watch(allFilteredTestDevices, (newVal) => {
  testTotalItems.value = newVal.length;
  if (testCurrentPage.value > testTotalPages.value && testTotalPages.value > 0) {
    testCurrentPage.value = 1;
  }
}, { immediate: true });

export const allFilteredAPIDevices = computed(() => {
  return apiDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value ||
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.category && device.category.toLowerCase().includes(searchQuery.value.toLowerCase()));
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    const matchesAlgorithmType = algorithmTypeFilter.value === 'all' ||
      (device as any).algorithm_type === algorithmTypeFilter.value ||
      (device as any).algorithmType === algorithmTypeFilter.value;
    return matchesSearch && matchesStatus && matchesAlgorithmType;
  });
});

export const filteredAPIDevices = computed(() => {
  const start = (apiCurrentPage.value - 1) * apiPageSize.value;
  const end = start + apiPageSize.value;
  return allFilteredAPIDevices.value.slice(start, end);
});

watch(allFilteredAPIDevices, (newVal) => {
  apiTotalItems.value = newVal.length;
  if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
    apiCurrentPage.value = 1;
  }
}, { immediate: true });
