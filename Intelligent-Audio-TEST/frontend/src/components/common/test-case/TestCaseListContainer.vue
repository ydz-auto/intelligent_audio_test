<template>
  <div class="test-case-list-container">
    <h3 class="step-title">测试用例列表</h3>
    
    <div class="test-case-toolbar">
      <div class="toolbar-actions">
          <button class="btn btn-primary" @click="() => {
            const algoType = algorithmTypeFilter === 'all' ? '' : algorithmTypeFilter;
            emit('openAddModal', undefined, { algorithmType: algoType });
          }">
            <i class="fas fa-plus"></i>
            新增用例
          </button>
          <button class="btn btn-secondary" @click="() => emit('openCreateGroupModal')">
            <i class="fas fa-folder-plus"></i>
            创建分组
          </button>
          <button class="btn btn-secondary" @click="() => emit('openExportModal')">
            <i class="fas fa-download"></i>
            导出用例
          </button>
          <button class="btn btn-secondary" @click="() => emit('openImportModal')">
            <i class="fas fa-upload"></i>
            导入用例
          </button>
        </div>
      <div class="toolbar-filters">
        <div class="search-box-container">
          <div class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input type="text" class="search-input" placeholder="搜索测试用例..." v-model="searchQuery">
          </div>
        </div>
        <div class="filters-container">
          <div class="filter-section">
            <label for="testTypeFilter">测试类型:</label>
            <div class="filter-select">
              <select id="testTypeFilter" class="form-input" v-model="testTypeFilter">
                <option value="all">所有类型</option>
                <option value="api">API测试</option>
                <option value="e2e">端到端测试</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <label for="algorithmTypeFilter">算法类型:</label>
            <div class="filter-select">
              <select id="algorithmTypeFilter" class="form-input" v-model="algorithmTypeFilter">
                <option v-for="option in algorithmOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <label for="groupFilter">用例分组:</label>
            <div class="filter-select">
              <select id="groupFilter" class="form-input" v-model="groupFilter">
                <option value="all">所有分组</option>
                <option v-for="group in availableGroups" :key="group" :value="group">{{ group }}</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <label for="tagFilter">标签:</label>
            <div class="filter-select">
              <select id="tagFilter" class="form-input" v-model="tagFilter">
                <option value="all">所有标签</option>
                <option v-for="tag in tags" :key="tag" :value="tag">{{ tag }}</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <label for="sortBy">排序:</label>
            <div class="filter-select">
              <select id="sortBy" class="form-input" v-model="sortBy">
                <option value="count">按用例数量</option>
                <option value="name">按分组名称</option>
                <option value="createTime">按创建时间</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <label for="sortOrder">顺序:</label>
            <div class="filter-select">
              <select id="sortOrder" class="form-input" v-model="sortOrder">
                <option value="desc">降序</option>
                <option value="asc">升序</option>
              </select>
            </div>
          </div>
          <div class="filter-section">
            <button class="btn btn-secondary" @click="() => resetFilters()">重置筛选</button>
          </div>
        </div>
      </div>
    </div>
    
    <div class="single-column-layout" ref="listContainerRef">
      <div 
        v-for="group in paginatedGroups" 
        :key="group" 
        class="category-card"
      >
        <div class="category-header" @click="() => toggleCategory(group)">
          <div class="category-info">
            <input type="checkbox" class="group-checkbox" 
                   @change="() => toggleGroupSelection(group)" 
                   @click.stop
                   :checked="groupSelectionStates[group]">
            <i class="fas fa-chevron-down category-toggle" :class="{ expanded: expandedCategories[group] }"></i>
            <h4 class="category-title">{{ group }}</h4>
            <span class="category-count">{{ filteredTestCases[group]?.length || 0 }}</span>
            <span v-if="getGroupDurationStats(group).totalDuration > 0" class="group-duration-tags">
              <span class="duration-tag">{{ formatGroupDuration(getGroupDurationStats(group).totalDuration) }}</span>
            </span>
          </div>
          <TestCaseGroupActions 
                @click.stop
                @edit="() => emit('openEditGroupModal', group)"
                @delete="() => handleGroupDelete(group)"
                @addCase="() => emit('openAddModal', group, { algorithmType: algorithmTypeFilter === 'all' ? '' : algorithmTypeFilter })"
                @copyGroup="() => handleCopyGroup(group)"
                @updateAlgorithmParams="() => handleUpdateAlgorithmParams(group)"
                @updatePlaybackDevice="() => handleUpdatePlaybackDevice(group)"
                @updateSPL="() => handleUpdateSPL(group)"
                @adjustGroup="() => handleAdjustGroup(group)"
                @updateDimensions="() => handleUpdateDimensions(group)"
                @updateNoise="() => handleUpdateNoise(group)"
                @autoGenerateName="() => handleAutoGenerateName(group)"
                @updateTags="() => handleUpdateTags(group)"
                @refreshReference="() => handleRefreshReference(group)"
                @toggleBatchMenu="() => toggleBatchMenu(group)"
                :showBatchMenu="openBatchMenuGroup === group"
              />
        </div>
        <div class="category-content" :class="{ expanded: expandedCategories[group] }">
          <div v-if="isGroupLoading(group)" class="group-loading">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>
          <TestCaseListWithPagination 
            v-else
            :test-cases="formattedTestCases[group]"
            :actions="getTestCaseActions()"
            :show-config="false"
            :search-query="searchQuery"
            :is-loading="isLoading"
            @toggle-selection="toggleTestCaseSelection"
            @action="(actionEvent) => handleAction(actionEvent, group)"
          />
          <div v-if="hasMoreGroupCases(group) && expandedCategories[group]" class="load-more-container">
            <button class="btn btn-secondary btn-sm" @click="loadMoreCases(group)" :disabled="isGroupLoading(group)">
              <i class="fas fa-chevron-down"></i>
              加载更多
            </button>
            <span class="load-more-info">
              已加载 {{ filteredTestCases[group]?.length || 0 }} / {{ getGroupTotalCount(group) }} 条
            </span>
          </div>
        </div>
      </div>
      
      <div v-if="paginatedGroups.length === 0" class="empty-state">
        <i class="fas fa-inbox"></i>
        <p>没有找到测试用例分组</p>
        <p class="empty-state-hint">请尝试添加新的测试用例或创建分组</p>
      </div>
      
      <div v-if="isLoadingMore" class="loading-more">
        <i class="fas fa-spinner fa-spin"></i>
        <span>加载更多分组...</span>
      </div>
      
      <div v-if="hasMoreGroups && !isLoadingMore && paginatedGroups.length > 0" class="load-more-trigger">
        <span class="load-more-hint">已显示 {{ paginatedGroups.length }} / {{ paginationInfo.totalItems }} 个分组</span>
        <button class="btn btn-secondary btn-sm" @click="loadMoreGroups">
          <i class="fas fa-chevron-down"></i> 加载更多
        </button>
      </div>
      
      <div v-if="!hasMoreGroups && paginatedGroups.length > 0" class="all-loaded">
        <span>已加载全部 {{ paginationInfo.totalItems }} 个分组</span>
      </div>
    </div>
    
  </div>
  
  <!-- 调试信息 -->
  <!-- <div style="position: fixed; top: 60px; left: 10px; z-index: 99999; background: rgba(0,0,0,0.8); color: white; padding: 10px; font-size: 12px; border-radius: 4px;">
    <div>showTestCaseModal: {{ props.showTestCaseModal }}</div>
    <div>showGroupModal: {{ props.showGroupModal }}</div>
    <div>showImportModal: {{ props.showImportModal }}</div>
    <div>showExportModal: {{ props.showExportModal }}</div>
  </div> -->
  
  <!-- 模态窗现在使用全局模态窗系统，不再需要内联组件 -->
  
  <teleport to="body">
    <div class="modal-overlay" v-if="showAudioTypeModal" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; z-index: 9999 !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">选择测试音频类型</h3>
          <button type="button" class="modal-close" @click="handleCloseAudioTypeModal">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="audio-type-options">
            <div class="audio-type-option" v-if="currentHasAPIConfig" @click="selectAudioType('api')">
              <i class="fas fa-microchip"></i>
              <span>API测试音频</span>
            </div>
            <div class="audio-type-option" v-if="currentHasE2eConfig" @click="selectAudioType('e2e')">
              <i class="fas fa-project-diagram"></i>
              <span>端到端测试音频</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <AudioPreviewModal
      :visible="showAudioPreviewModal"
      :audio-id="currentTestCaseId"
      :audio-type="'dry'"
      :playback-devices="playbackDevices.filter((d: PlaybackDevice) => d.deviceType === 'dry')"
      @close="handleAudioPreviewModalClose"
      @preview="handleAudioPreviewConfirm"
    />
    
    <AudioPlayerModal
      v-if="showAudioPlayer && currentTestCase"
      :visible="showAudioPlayer"
      :title="'测试用例预览'"
      :audio-id="currentTestCaseCaseId"
      :audio-title="'测试用例音频'"
      :audio-type="selectedAudioType === 'api' ? 'api' : 'e2e'"
      :is-test-case-preview="true"
      :playback-mode="previewPlaybackMode"
      @close="handleAudioPlayerClose"
    />
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount, shallowRef, triggerRef } from 'vue';
import TestCaseCard from './TestCaseCard.vue'
import TestCaseListWithPagination from './TestCaseListWithPagination.vue';
import TestCaseGroupActions from './TestCaseGroupActions.vue';
import AudioPlayerModal from '../AudioPlayerModal.vue';
import AudioPreviewModal from '../modal/AudioPreviewModal.vue';
import CRUDFormModal from '../modal/CRUDFormModal.vue';
import { playbackApi, algorithmApi } from '../../../utils/api';
import { useTestCaseStore } from '../../../store/testCaseStore';
import { normalizeTestCaseConfig } from '../../../utils/utils';
import { useModalControl, MODAL_TYPES } from '../../../composables/useModal';
import type { TestCase, PaginationInfo, PlaybackDevice } from '../../../shared/types';

function useDebounce<T>(value: Ref<T>, delay: number = 300): Ref<T> {
  const debouncedValue = ref(value.value) as Ref<T>;
  let timeout: ReturnType<typeof setTimeout> | null = null;
  
  watch(value, (newValue) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => {
      debouncedValue.value = newValue;
    }, delay);
  });
  
  return debouncedValue;
}

import type { Ref } from 'vue';

const props = defineProps<{
  testCaseGroups?: Record<string, TestCase[]>;
  tags?: string[];
  paginationInfo?: PaginationInfo;
  isLoading?: boolean;
  algorithmTypeFilter?: string;
}>();

const emit = defineEmits<{
  (e: 'deleteGroup', groupName: string): void;
  (e: 'deleteTestCase', testCase: TestCase): void;
  (e: 'openAddModal', group?: string, options?: { algorithmType?: string }): void;
  (e: 'openEditModal', testCase: TestCase): void;
  (e: 'openCreateGroupModal'): void;
  (e: 'openEditGroupModal', groupName: string): void;
  (e: 'openImportModal'): void;
  (e: 'openExportModal'): void;
  (e: 'updateSelectedCases', selectedCases: (string | number)[]): void;
  (e: 'updateSelectedGroups', groupIds: (string | number)[]): void;
}>();

const expandedCategories = ref<Record<string, boolean>>({});
const selectedCases = ref<(string | number)[]>([]);
const selectedGroupIds = ref<(string | number)[]>([]);
const searchQuery = ref('');
const debouncedSearchQuery = useDebounce(searchQuery, 300);
const testTypeFilter = ref('all');
const algorithmTypeFilter = ref('all');
const groupFilter = ref('all');
const tagFilter = ref('all');
const sortBy = ref('count');
const sortOrder = ref('desc');

// Pagination state
const currentPage = ref(1);
const itemsPerPage = ref(5);
const isLoadingMore = ref(false);
const hasMoreGroups = ref(true);
const listContainerRef = ref<HTMLElement | null>(null);

const showAudioPlayer = ref(false);
const currentTestCaseCaseId = ref<string | number | null>(null);
const showAudioTypeModal = ref(false);
const currentTestCase = ref<TestCase | null>(null);
const currentHasAPIConfig = ref(false);
const currentHasE2eConfig = ref(false);
const selectedAudioType = ref('');
const playbackDevices = ref<PlaybackDevice[]>([]);
const algorithmOptions = ref<{ value: string; label: string }[]>([]);
const showAudioPreviewModal = ref(false);
const previewPlaybackMode = ref<'frontend' | 'backend'>('frontend');
const showPlaybackDeviceModal = ref(false);

async function loadAlgorithmOptions() {
  try {
    const data = await algorithmApi.getOptions();
    algorithmOptions.value = [
      { value: 'all', label: '所有算法' },
      ...(data?.algorithms || []).map((algo: any) => ({
        value: algo.value,
        label: algo.name || algo.value
      }))
    ];
  } catch (error) {
    console.error('加载算法选项失败:', error);
    algorithmOptions.value = [
      { value: 'all', label: '所有算法' },
      { value: 'translation', label: '翻译' },
      { value: 'asr', label: 'ASR识别' },
      { value: 'speaker_recognition', label: '说话人识别' },
      { value: 'tts', label: '语音合成' }
    ];
  }
}

watch(selectedCases, (newValue) => {
  emit('updateSelectedCases', newValue);
}, { deep: true });

watch(selectedGroupIds, (newValue) => {
  emit('updateSelectedGroups', newValue);
}, { deep: true });

watch(() => props.algorithmTypeFilter, (newValue, oldValue) => {
  if (newValue !== undefined) {
    algorithmTypeFilter.value = newValue;
  }
}, { immediate: true });

watch([searchQuery, testTypeFilter, algorithmTypeFilter, groupFilter, tagFilter, sortBy, sortOrder], () => {
  currentPage.value = 1;
});

const loadPlaybackDevices = async () => {
  try {
    const result = await playbackApi.getAll();
    playbackDevices.value = (result as any).items || [];
  } catch (error) {
    console.error('加载播放设备列表失败:', error);
    playbackDevices.value = [];
  }
};

const modalControl = useModalControl();

let currentBatchGroup = '';
let currentBatchCaseIds: (string | number)[] = [];
const openBatchMenuGroup = ref<string | null>(null);

const toggleBatchMenu = (group: string) => {
  if (openBatchMenuGroup.value === group) {
    openBatchMenuGroup.value = null;
  } else {
    openBatchMenuGroup.value = group;
  }
};

const closeAllBatchMenus = () => {
  openBatchMenuGroup.value = null;
};

onMounted(() => {
  document.addEventListener('click', closeAllBatchMenus);
});

onUnmounted(() => {
  document.removeEventListener('click', closeAllBatchMenus);
});

const checkTestCaseConfig = (testCase: TestCase) => {
  const normalizedConfig = normalizeTestCaseConfig(testCase.config || {});
  const audios = normalizedConfig.audios || [];
  const apiAudios = audios.filter((a: any) => a.testType === 'api');
  const e2eAudios = audios.filter((a: any) => a.testType === 'e2e');
  
  const hasAPIConfig = apiAudios.length > 0;
  const hasE2eConfig = e2eAudios.length > 0;
  
  const apiAudioId = hasAPIConfig ? apiAudios[0].audioId : null;
  const e2eAudioIds = hasE2eConfig ? e2eAudios.map((a: any) => a.audioId) : [];
  
  console.log('检查测试用例配置:', { hasAPIConfig, hasE2eConfig, apiAudioId, e2eAudioIds });
  return { hasAPIConfig, hasE2eConfig, apiAudioId, e2eAudioIds };
};

const handleGlobalKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (showAudioTypeModal.value) {
      handleCloseAudioTypeModal();
    }
    if (showAudioPreviewModal.value) {
      handleAudioPreviewModalClose();
    }
    if (showPlaybackDeviceModal.value) {
      showPlaybackDeviceModal.value = false;
    }
    if (showAudioPlayer.value) {
      handleAudioPlayerClose();
    }
  }
};

onMounted(async () => {
  window.addEventListener('keydown', handleGlobalKeyDown);
  setupScrollListener();
  await Promise.all([
    loadPlaybackDevices(),
    loadAlgorithmOptions()
  ]);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeyDown);
  teardownScrollListener();
});

const availableGroups = computed(() => {
  console.log('[availableGroups] props.testCaseGroups:', props.testCaseGroups);
  console.log('[availableGroups] props.testCaseGroups keys:', Object.keys(props.testCaseGroups || {}));
  return Object.keys(props.testCaseGroups || {});
});

const filteredTestCases = computed(() => {
  const result: Record<string, TestCase[]> = {};
  const testCasesData = props.testCaseGroups || {};
  
  const query = debouncedSearchQuery.value?.toLowerCase() || '';
  const testType = testTypeFilter.value;
  const algorithmType = algorithmTypeFilter.value;
  const selectedGroup = groupFilter.value;
  const selectedTag = tagFilter.value;
  
  Object.keys(testCasesData).forEach((group: string) => {
    if (selectedGroup !== 'all' && group !== selectedGroup) {
      return;
    }
    
    const groupCases = testCasesData[group] || [];
    if (groupCases.length === 0) {
      result[group] = [];
      return;
    }
    
    let filtered = groupCases;
    
    if (query) {
      filtered = filtered.filter((testCase: TestCase) => {
        if (!testCase) return false;
        const idStr = String(testCase.id || '').toLowerCase();
        const name = (testCase.name || '').toLowerCase();
        const desc = (testCase.description || '').toLowerCase();
        
        if (idStr.includes(query) || name.includes(query) || desc.includes(query)) {
          return true;
        }
        
        if (testCase.tags && testCase.tags.length > 0) {
          return testCase.tags.some((tag: any) => {
            const tagName = typeof tag === 'string' ? tag : (tag.name || '');
            return tagName.toLowerCase().includes(query);
          });
        }
        return false;
      });
    }
    
    if (testType !== 'all') {
      filtered = filtered.filter((testCase: TestCase) => {
        if (!testCase) return false;
        const config = testCase.config || {};
        const types = testCase.type || config.type;
        
        if (types) {
          const typeArray = Array.isArray(types) ? types : [types];
          const normalizedTypes = typeArray.map(t => String(t).toLowerCase());
          
          if (testType === 'api') {
            return normalizedTypes.includes('api') || normalizedTypes.includes('apitest');
          } else if (testType === 'e2e') {
            return normalizedTypes.includes('e2e') || normalizedTypes.includes('e2etest');
          }
          return normalizedTypes.includes(testType.toLowerCase());
        }
        
        const normalizedConfig = normalizeTestCaseConfig(config);
        const audios = normalizedConfig.audios || [];
        if (testType === 'api') return audios.some((a: any) => a.testType === 'api');
        if (testType === 'e2e') return audios.some((a: any) => a.testType === 'e2e');
        return false;
      });
    }
    
    if (algorithmType !== 'all') {
      filtered = filtered.filter((testCase: TestCase) => {
        return testCase && testCase.algorithmType === algorithmType;
      });
    }
    
    if (selectedTag !== 'all') {
      filtered = filtered.filter((testCase: TestCase) => {
        if (!testCase || !testCase.tags) return false;
        return testCase.tags.some((tag: any) => {
          const tagName = typeof tag === 'string' ? tag : tag.name;
          return tagName === selectedTag;
        });
      });
    }
    
    result[group] = filtered;
  });
  
  return result;
});

const formattedTestCases = computed(() => {
  const result: Record<string, (TestCase & { lastEditTime?: string; selected: boolean })[]> = {};
  const filteredValue = filteredTestCases.value;
  
  Object.keys(filteredValue).forEach((group: string) => {
    result[group] = filteredValue[group]
      .filter((testCase: TestCase) => testCase && testCase.id)
      .map((testCase: TestCase) => ({
        ...testCase,
        lastEditTime: testCase.updatedAt || testCase.createdAt,
        selected: selectedCases.value.includes(testCase.id)
      }));
  });
  return result;
});

const groupSelectionStates = computed(() => {
  const result: Record<string, boolean> = {};
  const filteredValue = filteredTestCases.value;
  
  Object.keys(filteredValue).forEach((group: string) => {
    const groupCases = filteredValue[group];
    if (groupCases.length === 0) {
      result[group] = false;
    } else {
      result[group] = groupCases
        .filter((caseItem: TestCase) => caseItem && caseItem.id)
        .every((caseItem: TestCase) => 
          selectedCases.value.includes(caseItem.id)
        );
    }
  });
  
  return result;
});

const getGroupDurationStats = (group: string) => {
  const cases = filteredTestCases.value[group] || [];
  let totalDuration = 0;

  cases.forEach((tc: TestCase) => {
    if (tc.totalDuration) totalDuration += tc.totalDuration;
  });

  return { totalDuration };
};

const formatGroupDuration = (seconds: number): string => {
  if (!seconds || seconds === 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m${remainingSeconds > 0 ? ` ${remainingSeconds.toFixed(0)}s` : ''}`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
};

const sortedGroups = computed(() => {
  const filteredValue = filteredTestCases.value;
  const groups = Object.keys(filteredValue);
  const currentSortBy = sortBy.value;
  const currentSortOrder = sortOrder.value;
  
  return groups.sort((a, b) => {
    let result = 0;
    
    switch (currentSortBy) {
      case 'count':
        result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
        return currentSortOrder === 'asc' ? result * -1 : result;
      case 'name':
        result = a.localeCompare(b, 'zh-CN');
        return currentSortOrder === 'desc' ? result * -1 : result;
      case 'createTime':
        const aCases = filteredValue[a] || [];
        const bCases = filteredValue[b] || [];
        
        if (aCases.length === 0 && bCases.length === 0) {
          result = a.localeCompare(b, 'zh-CN');
          return currentSortOrder === 'desc' ? result * -1 : result;
        } else if (aCases.length === 0) {
          return currentSortOrder === 'asc' ? 1 : -1;
        } else if (bCases.length === 0) {
          return currentSortOrder === 'asc' ? -1 : 1;
        }
        
        const aTime = aCases[0]?.createdAt ? new Date(aCases[0].createdAt).getTime() : 0;
        const bTime = bCases[0]?.createdAt ? new Date(bCases[0].createdAt).getTime() : 0;
        result = bTime - aTime;
        return currentSortOrder === 'asc' ? result * -1 : result;
      default:
        result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
        return currentSortOrder === 'asc' ? result * -1 : result;
    }
  });
});

// Paginated groups computed property
const paginatedGroups = computed(() => {
  const allGroups = sortedGroups.value;
  const endIndex = currentPage.value * itemsPerPage.value;
  return allGroups.slice(0, endIndex);
});

// Pagination info computed property
const paginationInfo = computed(() => {
  const totalItems = sortedGroups.value.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage.value);
  hasMoreGroups.value = paginatedGroups.value.length < totalItems;
  
  return {
    totalItems,
    totalPages,
    currentPage: currentPage.value,
    itemsPerPage: itemsPerPage.value,
    hasPrev: currentPage.value > 1,
    hasNext: currentPage.value < totalPages
  };
});

const getTestCaseActions = () => {
  return [
    { id: 'preview', icon: 'fa-play', title: '预览音频' },
    { id: 'copy', icon: 'fa-copy', title: '复制用例' },
    { id: 'edit', icon: 'fa-edit', title: '编辑用例' },
    { id: 'delete', icon: 'fa-trash', title: '删除用例' }
  ];
};

const toggleCategory = async (group: string) => {
  const wasExpanded = expandedCategories.value[group];
  expandedCategories.value[group] = !wasExpanded;
  
  if (!wasExpanded) {
    const store = useTestCaseStore();
    const groupInfo = Object.values(store.fullGroupsMap).find(g => g.name === group);
    if (groupInfo && (!store.loadedGroupCases[groupInfo.id] || store.loadedGroupCases[groupInfo.id].length === 0)) {
      await store.fetchCasesByGroup(groupInfo.id);
    }
  }
};

const findGroupInfo = (groupName: string) => {
  const store = useTestCaseStore();
  return Object.values(store.fullGroupsMap).find(g => g.name === groupName);
};

const isGroupLoading = (groupName: string) => {
  const store = useTestCaseStore();
  const groupInfo = findGroupInfo(groupName);
  if (!groupInfo) return false;
  return store.isGroupLoading(groupInfo.id);
};

const hasMoreGroupCases = (groupName: string) => {
  const store = useTestCaseStore();
  const groupInfo = findGroupInfo(groupName);
  if (!groupInfo) return false;
  return store.hasMoreGroupCases(groupInfo.id);
};

const getGroupTotalCount = (groupName: string) => {
  const groupInfo = findGroupInfo(groupName) as any;
  return groupInfo?.testCaseCount || groupInfo?.test_case_count || 0;
};

const loadMoreCases = async (groupName: string) => {
  const store = useTestCaseStore();
  const groupInfo = findGroupInfo(groupName);
  if (groupInfo) {
    await store.loadMoreGroupCases(groupInfo.id);
  }
};

const toggleTestCaseSelection = (caseId: string | number) => {
  const index = selectedCases.value.indexOf(caseId);
  if (index > -1) {
    selectedCases.value.splice(index, 1);
    const allCases = Object.values(filteredTestCases.value).flat();
    const deselectedCase = allCases.find((tc: TestCase) => tc.id === caseId);
    if (deselectedCase) {
      const groupId = deselectedCase.groupId;
      if (groupId) {
        const gIdx = selectedGroupIds.value.indexOf(groupId);
        if (gIdx > -1) {
          selectedGroupIds.value.splice(gIdx, 1);
        }
      }
    }
  } else {
    selectedCases.value.push(caseId);
  }
};

const toggleGroupSelection = async (group: string) => {
  const allSelected = groupSelectionStates.value[group];
  const groupInfo = findGroupInfo(group);
  
  if (!allSelected) {
    const store = useTestCaseStore();
    if (groupInfo) {
      while (store.hasMoreGroupCases(groupInfo.id)) {
        await store.loadMoreGroupCases(groupInfo.id);
      }
    }
  }
  
  const groupCases = filteredTestCases.value[group] || [];
  
  groupCases.forEach((testCase: TestCase) => {
    const index = selectedCases.value.indexOf(testCase.id);
    if (allSelected) {
      if (index > -1) selectedCases.value.splice(index, 1);
    } else {
      if (index === -1) selectedCases.value.push(testCase.id);
    }
  });

  if (groupInfo) {
    const gIdx = selectedGroupIds.value.indexOf(groupInfo.id);
    if (allSelected) {
      if (gIdx > -1) selectedGroupIds.value.splice(gIdx, 1);
    } else {
      if (gIdx === -1) selectedGroupIds.value.push(groupInfo.id);
    }
  }
};

const resetFilters = () => {
  searchQuery.value = '';
  testTypeFilter.value = 'all';
  algorithmTypeFilter.value = 'all';
  groupFilter.value = 'all';
  tagFilter.value = 'all';
  sortBy.value = 'count';
  sortOrder.value = 'desc';
  currentPage.value = 1; // Reset to first page
};

const loadMoreGroups = () => {
  if (isLoadingMore.value || !hasMoreGroups.value) return;
  isLoadingMore.value = true;
  setTimeout(() => {
    currentPage.value++;
    isLoadingMore.value = false;
  }, 300);
};

let scrollAncestor: HTMLElement | null = null;

const handleScroll = () => {
  if (!listContainerRef.value || !hasMoreGroups.value || isLoadingMore.value) return;
  const rect = listContainerRef.value.getBoundingClientRect();
  const viewportHeight = window.innerHeight;
  if (rect.bottom - viewportHeight < 150) {
    loadMoreGroups();
  }
};

const setupScrollListener = () => {
  let el: HTMLElement | null = listContainerRef.value;
  while (el) {
    const style = getComputedStyle(el);
    const overflowY = style.overflowY;
    if (overflowY === 'auto' || overflowY === 'scroll') {
      scrollAncestor = el;
      break;
    }
    el = el.parentElement;
  }
  if (scrollAncestor) {
    scrollAncestor.addEventListener('scroll', handleScroll, { passive: true });
  }
};

const teardownScrollListener = () => {
  if (scrollAncestor) {
    scrollAncestor.removeEventListener('scroll', handleScroll);
    scrollAncestor = null;
  }
};

const deleteGroup = (groupName: string) => {
  emit('deleteGroup', groupName);
};

const exportTestCases = () => {
  console.log('导出测试用例');
  alert('导出用例功能开发中...');
};

const openBatchImportModal = () => {
  console.log('打开批量导入模态框');
  alert('导入用例功能开发中...');
};

const handleCloseAudioTypeModal = () => {
  showAudioTypeModal.value = false;
  currentTestCase.value = null;
};

const selectAudioType = (audioType: string) => {
  selectedAudioType.value = audioType;
  showAudioTypeModal.value = false;
  
  if (audioType === 'api') {
    showAudioPlayer.value = true;
  } else if (audioType === 'e2e') {
    showAudioPreviewModal.value = true;
  }
};

const handleAudioPreviewModalClose = () => {
  showAudioPreviewModal.value = false;
};

const handleAudioPreviewConfirm = (previewData: any) => {
  showAudioPreviewModal.value = false;
  previewPlaybackMode.value = previewData.playbackMode || 'frontend';
  showAudioPlayer.value = true;
};

const handleAudioPlayerClose = () => {
  showAudioPlayer.value = false;
  currentTestCaseCaseId.value = null;
  selectedAudioType.value = '';
  previewPlaybackMode.value = 'frontend';
};

const handleGroupDelete = (group: string) => {
  emit('deleteGroup', group);
};

const handleCopyGroup = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }
  
  currentBatchGroup = group;
  currentBatchCaseIds = groupCases.map((tc: TestCase) => tc.id);
  
  try {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '复制分组',
      content: `确定要复制分组 "${group}" 下的 ${groupCases.length} 个用例吗？\n\n复制后将成为新分组：${group}_copy`,
      confirmText: '复制',
      cancelText: '取消',
      danger: false
    });
    
    if (confirmed?.confirmed) {
      const store = useTestCaseStore();
      const result = await store.copyGroupCases(group);
      if (result) {
        alert(`分组复制成功！\n\n原分组：${group}\n新分组：${group}_copy`);
      }
    }
  } catch (error) {
    console.error('复制分组失败:', error);
  }
};

const handleUpdateAlgorithmParams = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_ALGORITHM_PARAMS, {
      title: '批量设置用例专属参数',
      caseCount: currentBatchCaseIds.length,
      algorithmType: groupCases[0]?.algorithmType || ''
    });

    if (result?.algorithmType && result?.params) {
      const store = useTestCaseStore();
      const updateResult = await store.batchUpdateAlgorithmParams(currentBatchCaseIds, result.params);
      if (updateResult) {
        alert(`已成功更新 ${currentBatchCaseIds.length} 个用例的专属参数`);
      }
    }
  } catch (error) {
    console.error('更新用例专属参数失败:', error);
  }
};

const handleUpdatePlaybackDevice = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_PLAYBACK_DEVICE, {
      title: '批量设置播放设备',
      caseCount: currentBatchCaseIds.length
    });

    if (result?.deviceId) {
      const store = useTestCaseStore();
      const updateResult = await store.batchUpdatePlaybackDevices(currentBatchCaseIds, { deviceId: result.deviceId });
      if (updateResult) {
        alert(`已成功更新 ${currentBatchCaseIds.length} 个用例的播放设备`);
      }
    }
  } catch (error) {
    console.error('更新播放设备失败:', error);
  }
};

const handleUpdateSPL = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_SPL, {
      title: '批量设置声压级',
      caseCount: currentBatchCaseIds.length,
      initialValue: 65
    });

    if (result?.value !== undefined) {
      const store = useTestCaseStore();
      const updateResult = await store.batchUpdateSPL(currentBatchCaseIds, { value: result.value });
      if (updateResult) {
        alert(`已成功更新 ${currentBatchCaseIds.length} 个用例的声压`);
      }
    }
  } catch (error) {
    console.error('更新声压失败:', error);
  }
};

const handleAdjustGroup = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_ADJUST_GROUP, {
      title: '批量调整分组',
      caseCount: currentBatchCaseIds.length,
      currentGroupId: ''
    });

    if (result?.groupId) {
      const store = useTestCaseStore();
      let updateResult = false;
      if (result.isCopy) {
        updateResult = await store.batchCopyCases(currentBatchCaseIds, result.groupId);
      } else {
        updateResult = await store.batchMoveCases(currentBatchCaseIds, result.groupId);
      }
      if (updateResult) {
        alert(`已成功将 ${currentBatchCaseIds.length} 个用例${result.isCopy ? '复制' : '移动'}到目标分组`);
      }
    }
  } catch (error) {
    console.error('调整分组失败:', error);
  }
};

const handleUpdateDimensions = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有勾选用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_DIMENSION, {
      title: '批量设置评价维度',
      caseCount: currentBatchCaseIds.length,
      algorithmType: algorithmTypeFilter.value !== 'all' ? algorithmTypeFilter.value : ''
    });

    if (result?.dimensions) {
      const store = useTestCaseStore();
      const updateResult = await store.batchUpdateDimensions(currentBatchCaseIds, result.dimensions, result.testType);
      if (updateResult) {
        alert(`已成功更新 ${currentBatchCaseIds.length} 个用例的评价维度`);
      }
    }
  } catch (error) {
    console.error('更新评价维度失败:', error);
  }
};

const handleUpdateNoise = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有勾选用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_NOISE, {
      title: '批量设置噪声',
      caseCount: currentBatchCaseIds.length
    });

    if (result) {
      const store = useTestCaseStore();
      const updateResult = await store.batchUpdateNoise(
        currentBatchCaseIds,
        result.audioId || '',
        result.spl || 0,
        result.deviceIds || []
      );
      if (updateResult) {
        alert(`已成功更新 ${currentBatchCaseIds.length} 个用例的噪声配置`);
      }
    }
  } catch (error) {
    console.error('更新噪声配置失败:', error);
  }
};

const handleAutoGenerateName = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有勾选用例');
    return;
  }

  try {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '批量通过标签自动生成用例名',
      content: `将为 ${currentBatchCaseIds.length} 个用例自动生成名称（按标签长度排序，用"-"连接）\n\n是否继续？`,
      confirmText: '确定',
      cancelText: '取消',
      danger: false
    });

    if (confirmed?.confirmed) {
      const store = useTestCaseStore();
      const updateResult = await store.batchAutoGenerateName(currentBatchCaseIds);
      if (updateResult) {
        alert(`已成功为 ${currentBatchCaseIds.length} 个用例自动生成名称`);
      }
    }
  } catch (error) {
    console.error('自动生成用例名失败:', error);
  }
};

const handleUpdateTags = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有勾选用例');
    return;
  }

  try {
    const result = await modalControl.open(MODAL_TYPES.BATCH_TAGS, {
      title: '批量管理用例标签',
      caseCount: currentBatchCaseIds.length
    });

    if (result) {
      const store = useTestCaseStore();
      let updateResult = false;
      if (result.action === 'add' && result.tags) {
        updateResult = await store.batchAddTags(currentBatchCaseIds, result.tags);
      } else if (result.action === 'remove' && result.tags) {
        updateResult = await store.batchRemoveTags(currentBatchCaseIds, result.tags);
      } else if (result.action === 'rename' && result.oldTagName && result.newTagName) {
        updateResult = await store.batchRenameTag(result.oldTagName, result.newTagName);
      }
      if (updateResult) {
        const actionText = result.action === 'add' ? '添加' : result.action === 'remove' ? '移除' : '重命名';
        alert(`已成功${actionText}标签`);
      }
    }
  } catch (error) {
    console.error('更新标签失败:', error);
  }
};

const handleRefreshReference = async (group: string) => {
  const groupCases = filteredTestCases.value[group] || [];
  if (groupCases.length === 0) {
    alert('该分组下没有用例');
    return;
  }

  const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
  const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

  currentBatchGroup = group;
  currentBatchCaseIds = selectedInGroup.length > 0 ? selectedInGroup : groupCaseIds.size > 0 ? Array.from(groupCaseIds) : [];

  if (currentBatchCaseIds.length === 0) {
    alert('该分组下没有勾选用例');
    return;
  }

  try {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '用例参考更新',
      content: `确定要刷新 ${currentBatchCaseIds.length} 个用例的参考参数吗？\n\n这将从关联音频的标注数据重新生成参考参数。`,
      confirmText: '确定刷新',
      cancelText: '取消',
      danger: false
    });

    if (confirmed?.confirmed) {
      const store = useTestCaseStore();
      const result = await store.batchRefreshReference(currentBatchCaseIds);

      if (result && typeof result === 'object' && 'taskId' in result) {
        console.log(`[handleRefreshReference] 异步任务已提交: ${result.taskId}，开始轮询进度...`);

        const pollAndNotify = async () => {
          const status = await store.pollRefreshTaskStatus(result.taskId);

          if (status.success) {
            console.log(`[handleRefreshReference] 任务完成: 成功 ${status.updated} 个，失败 ${status.failed} 个`);
            await store.fetchTestCases();
            alert(`用例参考更新完成！\n\n成功刷新: ${status.updated} 个\n失败: ${status.failed} 个`);
          } else {
            console.error('[handleRefreshReference] 任务查询失败或任务不存在');
            alert('用例参考更新任务执行失败，请稍后重试');
          }
        };

        pollAndNotify();
      } else if (result === true) {
        alert(`已成功刷新 ${currentBatchCaseIds.length} 个用例的参考参数`);
      }
    }
  } catch (error) {
    console.error('刷新用例参考失败:', error);
  }
};

const handleAction = async (actionEvent: { action: { id: string }; testCase: TestCase }, group: string) => {
  const testCase = actionEvent.testCase;
  console.log('[TestCaseListContainer] 处理测试用例操作:', { action: actionEvent.action.id, testCase: testCase.name });
  
  switch (actionEvent.action.id) {
    case 'preview': {
      const config = testCase.config || {};
      const hasAudioConfig = config.audios && config.audios.length > 0;
      
      if (hasAudioConfig) {
        try {
          const { hasAPIConfig, hasE2eConfig } = checkTestCaseConfig(testCase);
          currentTestCase.value = testCase;
          currentTestCaseCaseId.value = testCase.id;
          currentHasAPIConfig.value = hasAPIConfig;
          currentHasE2eConfig.value = hasE2eConfig;
          
          if (hasAPIConfig && hasE2eConfig) {
            showAudioTypeModal.value = true;
          } else if (hasAPIConfig) {
            selectedAudioType.value = 'api';
            showAudioPlayer.value = true;
          } else if (hasE2eConfig) {
            selectedAudioType.value = 'e2e';
            showAudioPreviewModal.value = true;
          }
        } catch (error: any) {
          console.error('音频试听失败:', error);
        }
      }
      break;
    }
    case 'copy':
      try {
        const store = useTestCaseStore();
        await store.copyTestCase(testCase.id);
        selectedCases.value = [];
      } catch (error: any) {
        console.error('复制测试用例失败:', error);
      }
      break;
    case 'edit':
      emit('openEditModal', testCase);
      break;
    case 'delete':
      emit('deleteTestCase', testCase);
      break;
  }
};
</script>

<style scoped>
/* 测试用例列表容器样式 */
.test-case-list-container {
  padding: 24px;
  background-color: #fff;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
}

/* 分组加载状态 */
.group-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--text-secondary);
  gap: 8px;
}

.group-loading i {
  font-size: 20px;
  color: var(--primary-color);
}

/* 加载更多容器 */
.load-more-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px;
  border-top: 1px solid var(--gray-light-color);
  background: var(--gray-lightest-color);
}

.load-more-info {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 步骤标题 */
.step-title {
  margin-top: 0;
  margin-bottom: 24px;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 测试用例工具栏样式 */
.test-case-toolbar {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg);
  background: #FFFFFF;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--gray-light-color);
  overflow: visible;
  box-sizing: border-box;
  min-height: 120px;
}

.toolbar-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  align-items: center;
  width: 100%;
  justify-content: center;
  margin-bottom: var(--spacing-md);
}

/* 响应式设计：在中等屏幕及以上，工具栏操作居左，过滤居右 */
@media (min-width: 768px) {
  .test-case-toolbar {
    align-items: center;
  }
  
  .toolbar-actions {
    width: auto;
    justify-content: flex-start;
    margin-bottom: 0;
  }
}

.toolbar-filters {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  align-items: stretch;
  flex-wrap: nowrap;
  background-color: white;
  padding: var(--spacing-md);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  width: 100%;
  box-sizing: border-box;
  overflow: visible;
  min-height: 80px;
}

/* 搜索框样式 */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  height: 40px;
  margin: 0;
  padding: 0;
  flex-shrink: 1;
  width: 100%;
  min-width: 200px;
  margin-bottom: 0;
}

/* 搜索框容器样式 */
.search-box-container {
  width: 100%;
  display: flex;
  justify-content: flex-start;
  min-height: 40px;
}

/* 筛选器容器样式 */
.filters-container {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  width: 100%;
  overflow-x: auto;
  padding-bottom: var(--spacing-xs);
  min-height: 40px;
  box-sizing: border-box;
}

/* 确保筛选器在所有屏幕尺寸下都在同一行 */
.filter-section {
  flex-shrink: 0;
  min-width: auto;
}

/* 针对小屏幕的优化，确保筛选器在空间不足时能够换行 */
@media (max-width: 767px) {
  .filters-container {
    flex-wrap: wrap;
    justify-content: center;
    overflow-x: visible;
  }
  
  .filter-section {
    min-width: 120px;
  }
}

.filter-section {
  display: flex;
  align-items: center;
  gap: 8px;
  height: auto;
  min-height: 40px;
  box-sizing: border-box;
  margin: 0;
  padding: 4px 0;
  flex-shrink: 1;
  flex-wrap: nowrap;
  min-width: 150px;
  justify-content: flex-start;
}

.filter-section label {
  margin: 0;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  flex-shrink: 0;
}

.filter-select {
  display: flex;
  align-items: center;
  flex-shrink: 1;
  min-width: 100px;
}

.filter-select .form-input {
  height: 40px;
  box-sizing: border-box;
  flex-shrink: 1;
  width: 100%;
  min-width: 100px;
}

.filter-section .form-input {
  width: 150px;
  min-width: 100px;
  flex-shrink: 1;
}

/* 确保重置筛选按钮高度与其他元素一致 */
.filter-section .btn-secondary {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-md);
  height: 40px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  white-space: nowrap;
  min-height: 40px;
}

/* 搜索框样式 */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  height: 40px;
  margin: 0;
  padding: 0;
  flex-shrink: 1;
  width: 100%;
  min-width: 200px;
  margin-bottom: 0;
}

/* 响应式设计：在中等屏幕及以上，搜索框不独占一行 */
@media (min-width: 768px) {
  .search-box {
    width: 300px;
  }
}

.search-icon {
  position: absolute;
  left: 12px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.search-input {
  padding-left: 36px;
  width: 100%;
  height: 40px;
  box-sizing: border-box;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  background-color: var(--background-primary);
  font-size: var(--font-size-md);
  margin: 0;
  flex-shrink: 0;
}

/* 针对1/2 1k屏幕(512px-1023px)的优化 */
@media (max-width: 1023px) {
  .test-case-toolbar {
    padding: var(--spacing-md);
    gap: var(--spacing-md);
  }
  
  .toolbar-actions {
    width: 100%;
    justify-content: center;
    margin-bottom: var(--spacing-md);
  }
  
  .toolbar-filters {
    gap: var(--spacing-md);
    padding: var(--spacing-sm);
    justify-content: center;
  }
  
  .filter-section {
    gap: 8px;
    min-width: 150px;
    justify-content: center;
  }
  
  .filter-section .form-input {
    width: 130px;
  }
  
  .search-box {
    width: 100%;
    min-width: 250px;
    justify-content: center;
  }
}

/* 针对小屏幕和半1k屏幕(512px以下)的优化 */
@media (max-width: 576px) {
  .test-case-toolbar {
    padding: var(--spacing-sm);
    gap: var(--spacing-sm);
  }
  
  .toolbar-actions {
    gap: var(--spacing-xs);
  }
  
  .toolbar-filters {
    gap: var(--spacing-sm);
    padding: var(--spacing-xs);
  }
  
  .filter-section {
    gap: 4px;
    min-width: 120px;
  }
  
  .filter-section .form-input {
    width: 100px;
    font-size: 13px;
  }
  
  .search-box {
    min-width: 150px;
  }
  
  .search-input {
    font-size: 13px;
  }
}

/* 针对1k屏幕(1024px-1279px)的优化 */
@media (min-width: 1024px) and (max-width: 1279px) {
  .test-case-toolbar {
    padding: var(--spacing-lg);
    gap: var(--spacing-lg);
  }
  
  .toolbar-filters {
    gap: var(--spacing-md);
  }
  
  .filter-section {
    min-width: 160px;
  }
  
  .filter-section .form-input {
    width: 140px;
  }
  
  .search-box {
    width: 250px;
  }
}

/* 单栏布局样式 */
.single-column-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  overflow-y: visible;
  padding-right: 8px;
  scroll-behavior: smooth;
}

.single-column-layout::-webkit-scrollbar {
  width: 6px;
}

.single-column-layout::-webkit-scrollbar-track {
  background: var(--background-tertiary);
  border-radius: 3px;
}

.single-column-layout::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.single-column-layout::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 加载更多提示 */
.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.load-more-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px;
  border-top: 1px dashed var(--border-color);
  margin-top: 8px;
}

.load-more-hint {
  color: var(--text-tertiary);
  font-size: 13px;
}

.all-loaded {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: var(--text-tertiary);
  font-size: 13px;
  border-top: 1px dashed var(--border-color);
  margin-top: 8px;
}

/* 类别卡片样式 */
.category-card {
  background-color: #fff;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: visible;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.category-card:hover {
  box-shadow: var(--shadow-md);
}

/* 类别卡片头部 */
.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  cursor: pointer;
  transition: all 0.3s ease;
}

.category-header:hover {
  background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%);
}

.category-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

/* 类别标题 */
.category-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* 类别计数 */
.category-count {
  background-color: var(--primary-color);
  color: white;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 12px;
  min-width: 20px;
  text-align: center;
}

/* 分组音频时长统计标签 */
.group-duration-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: 8px;
}

.group-duration-tags .duration-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  color: white;
}

.group-duration-tags .duration-api {
  background-color: #1677FF;
}

.group-duration-tags .duration-e2e {
  background-color: #FF6A00;
}

/* 类别内容 */
.category-content {
  display: none;
  padding: 16px;
  min-height: 200px;
}

.category-content.expanded {
  display: block;
}

/* 类别操作按钮容器 */
.category-actions-container {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  text-align: center;
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
  margin-top: 16px;
  margin-bottom: 16px;
}

.empty-state i {
  font-size: 48px;
  color: var(--text-tertiary);
  margin-bottom: 16px;
}

.empty-state p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 16px;
}

.empty-state-hint {
  margin-top: 8px !important;
  font-size: 14px !important;
  color: var(--text-tertiary);
}

/* 模态窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1001;
  animation: fadeIn 0.3s ease;
}

.modal-container {
  background-color: white;
  border-radius: var(--border-radius-xl);
  box-shadow: var(--shadow-lg);
  width: 90%;
  max-width: 400px;
  animation: slideIn 0.3s ease;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-top-left-radius: var(--border-radius-xl);
  border-top-right-radius: var(--border-radius-xl);
}

.modal-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
  transform: rotate(90deg);
}

.modal-body {
  padding: 24px;
  border-bottom-left-radius: var(--border-radius-xl);
  border-bottom-right-radius: var(--border-radius-xl);
}

/* 音频类型选择样式 */
.audio-type-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.audio-type-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e9ecef;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background-color: #f8f9fa;
}

.audio-type-option:hover {
  border-color: #007bff;
  background-color: #e3f2fd;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.15);
}

.audio-type-option i {
  font-size: 24px;
  color: #007bff;
}

.audio-type-option span {
  font-size: 16px;
  font-weight: 500;
  color: #343a40;
}

/* 动画效果 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideIn {
  from { transform: translateY(-20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
</style>
