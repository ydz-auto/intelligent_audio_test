<template>
  <div class="test-case-list-container">
    <h3 class="step-title">
      <span>测试用例列表</span>
      <div class="view-switcher">
        <button
          class="btn btn-toggle"
          :class="{ active: innerViewMode === 'group' }"
          @click="() => updateViewMode('group')"
          title="分组视图"
        >
          <i class="fas fa-folder"></i>
          分组视图
        </button>
        <button
           class="btn btn-toggle"
          :class="{ active: innerViewMode === ViewMode.TAG }"
          @click="() => updateViewMode('tag')"
          title="标签视图"
        >
          <i class="fas fa-tags"></i>
          标签视图
        </button>
      </div>
    </h3>
    
    <div class="test-case-toolbar">
      <div class="toolbar-actions">
          <button class="btn btn-primary" @click="() => {
            const algoType = algorithmTypeFilter === 'all' ? '' : algorithmTypeFilter;
            emit('openAddModal', undefined, { algorithmType: algoType, testType: testTypeFilter === 'all' ? undefined : testTypeFilter as 'api' | 'e2e' });
          }">
            <i class="fas fa-plus"></i>
            新增用例
          </button>
          <button class="btn btn-secondary" @click="() => emit('openCreateGroupModal')" v-if="innerViewMode === 'group'">
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
          <BadgeFilter
            :options="TEST_TYPE_OPTIONS"
            :model-value="testTypeFilter"
            all-label="所有类型"
            title="测试类型"
            @update:model-value="setTestTypeFilter"
          />
          <BadgeFilter
            :options="algorithmOptions"
            :model-value="algorithmTypeFilter"
            all-label="所有算法"
            title="算法类型"
            @update:model-value="value => algorithmTypeFilter = String(value)"
          />
          <BadgeFilter
            :options="dimensionFilterOptions"
            :model-value="dimensionFilter"
            all-label="所有维度"
            title="评估维度"
            collapsible
            :collapsed-count="8"
            @update:model-value="setDimensionFilter"
          />
          <BadgeFilter
            :options="groupFilterOptions"
            :model-value="groupFilter"
            all-label="所有分组"
            title="用例分组"
            @update:model-value="setGroupFilter"
          />
          <BadgeFilter
            :options="tagFilterOptions"
            :model-value="tagFilter"
            all-label="所有标签"
            title="标签"
            collapsible
            :collapsed-count="8"
            @update:model-value="setTagFilter"
          />
          <BadgeFilter
            :options="SORT_BY_OPTIONS"
            :model-value="sortBy"
            :show-all="false"
            :deselectable="false"
            title="排序"
            @update:model-value="setSortBy"
          />
          <BadgeFilter
            :options="SORT_ORDER_OPTIONS"
            :model-value="sortOrder"
            :show-all="false"
            :deselectable="false"
            title="顺序"
            @update:model-value="setSortOrder"
          />
          <div class="filter-section">
            <button class="btn btn-secondary" @click="() => resetFilters()">重置筛选</button>
          </div>
        </div>
      </div>
    </div>
    
    <div class="single-column-layout" ref="listContainerRef" @scroll="handleScroll">
      <!-- ===== 分组视图 ===== -->
      <template v-if="innerViewMode === 'group'">
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
            <span class="category-count">{{ getGroupTotalCount(group) }}</span>
            <span v-if="getGroupDurationStats(group).totalDuration > 0" class="group-duration-tags">
              <span class="duration-tag">{{ formatGroupDuration(getGroupDurationStats(group).totalDuration) }}</span>
            </span>
          </div>
          <TestCaseGroupActions 
                @click.stop
                @edit="() => emit('openEditGroupModal', group)"
                @delete="() => handleGroupDelete(group)"
                @addCase="() => emit('openAddModal', group, { algorithmType: algorithmTypeFilter === 'all' ? '' : algorithmTypeFilter, testType: testTypeFilter === 'all' ? undefined : testTypeFilter as 'api' | 'e2e' })"
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

      <div v-if="hasMoreGroups && !isLoadingMore && paginatedGroups.length > 0" class="load-more-trigger" ref="loadMoreTriggerRef">
        <span class="load-more-hint">已显示 {{ paginatedGroups.length }} / {{ paginationInfo.totalItems }} 个分组</span>
        <button class="btn btn-secondary btn-sm" @click="loadMoreGroups">
          <i class="fas fa-chevron-down"></i> 加载更多
        </button>
      </div>

      <div v-if="!hasMoreGroups && paginatedGroups.length > 0" class="all-loaded">
        <span>已加载全部 {{ paginationInfo.totalItems }} 个分组</span>
      </div>
      </template>

      <!-- ===== 标签视图 ===== -->
      <template v-else>
        <div
          v-for="tagName in sortedTags"
          :key="tagName"
          class="category-card"
        >
          <div class="category-header" @click="() => toggleTagCategory(tagName)">
            <div class="category-info">
              <input type="checkbox" class="group-checkbox"
                     @change="() => toggleTagSelection(tagName)"
                     @click.stop
                     :checked="tagSelectionStates[tagName]">
              <i class="fas fa-chevron-down category-toggle" :class="{ expanded: expandedTagCategories[tagName] }"></i>
              <i class="fas fa-tag" style="color: var(--primary-color); margin-right: 6px;"></i>
              <h4 class="category-title">{{ tagName }}</h4>
              <span class="category-count">{{ filteredTagCases[tagName]?.length || 0 }}</span>
              <span v-if="getTagDurationStats(tagName).totalDuration > 0" class="group-duration-tags">
                <span class="duration-tag">{{ formatGroupDuration(getTagDurationStats(tagName).totalDuration) }}</span>
              </span>
            </div>
            <TestCaseGroupActions
              @click.stop
              @edit="() => handleTagEdit(tagName)"
              @delete="() => handleTagDelete(tagName)"
              @addCase="() => handleTagAddCase(tagName)"
              @copyGroup="() => handleTagCopyGroup(tagName)"
              @updateAlgorithmParams="() => handleTagUpdateAlgorithmParams(tagName)"
              @updatePlaybackDevice="() => handleTagUpdatePlaybackDevice(tagName)"
              @updateSPL="() => handleTagUpdateSPL(tagName)"
              @adjustGroup="() => handleTagAdjustGroup(tagName)"
              @updateDimensions="() => handleTagUpdateDimensions(tagName)"
              @updateNoise="() => handleTagUpdateNoise(tagName)"
              @autoGenerateName="() => handleTagAutoGenerateName(tagName)"
              @updateTags="() => handleTagUpdateTags(tagName)"
              @refreshReference="() => handleTagRefreshReference(tagName)"
              @toggleBatchMenu="() => toggleBatchMenu(tagName)"
              :showBatchMenu="openBatchMenuGroup === tagName"
            />
          </div>
          <div class="category-content" :class="{ expanded: expandedTagCategories[tagName] }">
            <TestCaseListWithPagination
              :test-cases="formattedTagCases[tagName]"
              :actions="getTestCaseActions()"
              :show-config="false"
              :search-query="searchQuery"
              :is-loading="isLoading"
              @toggle-selection="toggleTestCaseSelection"
              @action="(actionEvent) => handleAction(actionEvent, tagName)"
            />
          </div>
        </div>

        <div v-if="sortedTags.length === 0" class="empty-state">
          <i class="fas fa-tags"></i>
          <p>没有找到标签分组的测试用例</p>
          <p class="empty-state-hint">请为测试用例添加标签</p>
        </div>

        <div v-if="tagViewLoading" class="loading-more">
          <i class="fas fa-spinner fa-spin"></i>
          <span>加载更多标签...</span>
        </div>

        <div v-if="hasMoreTagsFromBackend && !tagViewLoading && sortedTags.length > 0" class="load-more-trigger" ref="loadMoreTriggerRef">
          <span class="load-more-hint">已加载 {{ sortedTags.length }} / {{ props.tagViewPagination?.total || sortedTags.length }} 个标签</span>
          <button class="btn btn-secondary btn-sm" @click="emit('loadMoreTags')">
            <i class="fas fa-chevron-down"></i> 加载更多
          </button>
        </div>

        <div v-if="!hasMoreTagsFromBackend && sortedTags.length > 0" class="all-loaded">
          <span>已加载全部 {{ props.tagViewPagination?.total || sortedTags.length }} 个标签</span>
        </div>
      </template>
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
            <div class="audio-type-option" v-if="currentHasAPIConfig" @click="selectAudioType(TestType.API)">
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
      :audio-id="currentTestCaseCaseId != null ? String(currentTestCaseCaseId) : undefined"
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
      :audio-type="selectedAudioType === TestType.API ? TestType.API : TestType.E2E"
      :is-test-case-preview="true"
      :playback-mode="previewPlaybackMode"
      @close="handleAudioPlayerClose"
    />
  </teleport>
</template>

<script setup lang="ts">
import TestCaseListWithPagination from './TestCaseListWithPagination.vue';
import TestCaseGroupActions from './TestCaseGroupActions.vue';
import BadgeFilter from '../BadgeFilter.vue';
import AudioPlayerModal from '../audio/AudioPlayerModal.vue';
import AudioPreviewModal from '../modal/AudioPreviewModal.vue';
import type { TestCase, PaginationInfo, PlaybackDevice } from '../../../domain';
import { TestType, ViewMode } from '@/domain/enums';
import { useTestCaseStore } from '../../../store/testCaseStore';
import { useModalControl, MODAL_TYPES } from '../../../composables/modal/useModal';
import { useNotification } from '../../../composables/modal/useNotification';
import { tagsPort } from '../../../composables/shared/tagsPort';
import { useTestCaseListContainer } from './TestCaseListContainer';

const props = defineProps<{
  testCaseGroups?: Record<string, TestCase[]>;
  tagViewData?: Record<string, TestCase[]>;
  tags?: string[];
  paginationInfo?: PaginationInfo;
  tagViewPagination?: { page: number; pages: number; perPage: number; total: number };
  tagViewLoading?: boolean;
  isLoading?: boolean;
  algorithmTypeFilter?: string;
  testTypeFilter?: string;
  viewMode?: 'group' | 'tag';
}>();

const emit = defineEmits<{
  (e: 'deleteGroup', groupName: string): void;
  (e: 'deleteTestCase', testCase: TestCase): void;
  (e: 'openAddModal', group?: string, options?: { algorithmType?: string; testType?: 'api' | 'e2e'; tags?: string[] }): void;
  (e: 'openEditModal', testCase: TestCase): void;
  (e: 'openCreateGroupModal'): void;
  (e: 'openEditGroupModal', groupName: string): void;
  (e: 'openImportModal'): void;
  (e: 'openExportModal'): void;
  (e: 'updateSelectedCases', selectedCases: (string | number)[]): void;
  (e: 'update:viewMode', mode: 'group' | 'tag'): void;
  (e: 'tagFilterChange', filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }): void;
  (e: 'groupFilterChange', filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }): void;
  (e: 'loadMoreTags'): void;
}>();

const {
  tags,
  isLoading,
  playbackDevices,
  algorithmOptions,
  innerViewMode,
  searchQuery,
  testTypeFilter,
  algorithmTypeFilter,
  groupFilter,
  tagFilter,
  sortBy,
  sortOrder,
  dimensionFilter,
  dimensionOptions,
  TEST_TYPE_OPTIONS,
  SORT_BY_OPTIONS,
  SORT_ORDER_OPTIONS,
  dimensionFilterOptions,
  groupFilterOptions,
  tagFilterOptions,
  setTestTypeFilter,
  setDimensionFilter,
  setGroupFilter,
  setTagFilter,
  setSortBy,
  setSortOrder,
  hasMoreGroups,
  expandedCategories,
  expandedTagCategories,
  currentPage,
  itemsPerPage,
  isLoadingMore,
  listContainerRef,
  loadMoreTriggerRef,
  toggleCategory,
  toggleTagCategory,
  isGroupLoading,
  hasMoreGroupCases,
  getGroupTotalCount,
  loadMoreCases,
  loadMoreGroups,
  handleScroll,
  resetFilters,
  handleCopyGroup,
  handleUpdateAlgorithmParams,
  handleUpdatePlaybackDevice,
  handleUpdateSPL,
  handleAdjustGroup,
  handleUpdateDimensions,
  handleUpdateNoise,
  handleAutoGenerateName,
  handleUpdateTags,
  handleRefreshReference,
  showAudioPlayer,
  handleTagDelete,
  handleTagCopyGroup,
  handleTagUpdateSPL,
  handleTagUpdatePlaybackDevice,
  handleTagUpdateNoise,
  handleTagUpdateAlgorithmParams,
  handleTagUpdateDimensions,
  handleTagAdjustGroup,
  handleTagAutoGenerateName,
  handleTagUpdateTags,
  handleTagRefreshReference,
  currentTestCaseCaseId,
  showAudioTypeModal,
  currentTestCase,
  currentHasAPIConfig,
  currentHasE2eConfig,
  selectedAudioType,
  showAudioPreviewModal,
  previewPlaybackMode,
  handleCloseAudioTypeModal,
  selectAudioType,
  handleAudioPreviewModalClose,
  handleAudioPreviewConfirm,
  handleAudioPlayerClose,
  handleAction,
  updateViewMode,
  availableGroups,
  filteredTestCases,
  formattedTestCases,
  groupSelectionStates,
  getGroupDurationStats,
  formatGroupDuration,
  sortedGroups,
  paginatedGroups,
  paginationInfo,
  availableTags,
  filteredTagCases,
  formattedTagCases,
  sortedTags,
  hasMoreTagsFromBackend,
  tagSelectionStates,
  toggleTagSelection,
  getTagDurationStats,
  getTestCaseActions,
  toggleTestCaseSelection,
  toggleGroupSelection,
  handleGroupDelete,
  openBatchMenuGroup,
  toggleBatchMenu
} = useTestCaseListContainer(props, emit)

const testCaseStore = useTestCaseStore()
const modalControl = useModalControl()
const notification = useNotification()

/** 编辑标签（重命名/颜色/分类）：对齐 V9.7.10，成功后按当前视图刷新 */
const handleTagEdit = async (tagName: string) => {
  try {
    // 先通过标签名查找标签对象（端口层 camelCase 契约：getTags({ keyword })）
    const res = await tagsPort.getTags({ keyword: tagName })
    const tagItem = (res as any)?.items?.find((t: any) => t.name === tagName)
    if (!tagItem) {
      notification.warning(`未找到标签"${tagName}"，可能已被删除`)
      return
    }
    const result = await modalControl.open(MODAL_TYPES.TAG_EDIT, {
      tag: tagItem,
      categoryId: (tagItem as any).categoryId || null,
      categories: []
    })
    if (result) {
      notification.success(`标签"${tagName}"已更新`)
      // 编辑后按当前视图刷新（标签视图下 tagViewData / tags 需重新拉取）
      await testCaseStore.refreshView(innerViewMode.value)
    }
  } catch (error) {
    console.error('编辑标签失败:', error)
    notification.error('编辑标签失败')
  }
}

/** 添加用例到标签：打开新增用例模态窗并预填当前标签 */
const handleTagAddCase = (tagName: string) => {
  emit('openAddModal', undefined, {
    algorithmType: algorithmTypeFilter.value === 'all' ? '' : algorithmTypeFilter.value,
    testType: testTypeFilter.value === 'all' ? undefined : testTypeFilter.value as 'api' | 'e2e',
    tags: [tagName]
  })
}
</script>

<style scoped>@import './TestCaseListContainer.css';

/* 以下为 TestCaseListContainer.css 未覆盖的补充规则（选中态/交互态） */

.category-card:has(.group-checkbox:checked){
    background-color: color-mix(in srgb, var(--primary) 5%, transparent);
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 20%, transparent);
}

.category-card:has(.group-checkbox:checked) .category-header{
    background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 10%, transparent) 0%, color-mix(in srgb, var(--primary) 5%, transparent) 100%);
    border-bottom: 1px solid color-mix(in srgb, var(--primary) 20%, transparent);
}

.group-checkbox{
    pointer-events: auto ;
    cursor: pointer ;
}

.category-header > button{
    margin-left: auto;
}

.group-checkbox:checked ~ .category-title{
    color: var(--primary-color);
    font-weight: 700;
}

</style>
