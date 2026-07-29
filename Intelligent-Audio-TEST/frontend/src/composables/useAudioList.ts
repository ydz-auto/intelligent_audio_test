import { ref, computed, type Ref } from 'vue';
import { audiosApi } from '../utils/api';
import { useTagFilter } from './useTagFilter';
import { useFolderSelection } from './useFolderSelection';
import { normalizeSampleRate } from './useFolderTree';
import type { AudioInfo, AudioQueryParams, AudioStats, APIResponse } from '../shared/types';

/**
 * 音频列表管理组合式函数
 *
 * 职责：
 * - 音频列表的获取、搜索、过滤、分页
 * - 标签管理（获取所有标签、标签过滤）
 * - 选择管理（单选、全选、跨页全选）
 * - 客户端过滤计算（filteredAudios）
 */

// 兼容类型导出（供 AudioSelectModal / UploadOptions 等组件使用）
export type AudioItem = AudioInfo;

export interface AudioListFilters {
  format: string;
  sampleRate: string;
  duration: string;
  audioType: string;
  direction: string;
  dateRange: [Date, Date] | null;
  tagMatchMode: 'or' | 'and';
}

export function useAudioList() {
  const audioList = ref<AudioInfo[]>([]);
  const totalAudios = ref(0);
  const loading = ref(false);
  const currentPage = ref(1);
  const pageSize = ref(20);
  const searchTerm = ref('');
  const searchQuery = ref('');
  const audioTypeFilter = ref<'all' | 'dry' | 'noise' | 'prompt' | 'mixed'>('all');
  const viewMode = ref<'list' | 'folder'>('list');

  const filters = ref<AudioListFilters>({
    format: 'all',
    sampleRate: 'all',
    duration: 'all',
    audioType: 'all',
    direction: 'all',
    dateRange: null as [Date, Date] | null,
    tagMatchMode: 'and' as 'or' | 'and'
  });

  const stats = ref<AudioStats>({
    total: 0,
    dry: 0,
    noise: 0,
    prompt: 0,
    mixed: 0,
    totalFiles: 0,
    totalSize: '0 B',
    totalDuration: '0s',
    todayUploads: 0
  });

  // 标签管理
  const allTags = ref<string[]>([]);
  const tagsLoaded = ref(false);

  const {
    selectedTags,
    tagModes,
    tagModesObject,
    handleTagClick: tagFilterHandleTagClick,
    toggleTag: tagFilterToggleTag,
    clearTags
  } = useTagFilter();

  // 选择管理
  const selectedAudios = ref<(string | number)[]>([]);
  const showSelectAllOptions = ref(false);
  const selectAllAcrossPages = ref(false);

  // 文件夹批量勾选逻辑（复用 composable）
  const {
    toggleFolderSelection,
    isFolderAllSelected,
    isFolderPartialSelected,
  } = useFolderSelection(selectedAudios);

  // ========== 标签相关辅助 ==========

  function isAllTagsSelected(): boolean {
    if (!tagsLoaded.value) return false;
    if (allTags.value.length === 0) return false;
    if (selectedTags.value.length < allTags.value.length) return false;
    const selectedSet = new Set(selectedTags.value);
    return allTags.value.every(t => selectedSet.has(t));
  }

  function normalizeTagList(raw: unknown): string[] {
    if (!Array.isArray(raw)) return [];
    const result: string[] = [];
    for (const item of raw) {
      if (typeof item === 'string') {
        const t = item.trim();
        if (t) result.push(t);
        continue;
      }
      if (item && typeof item === 'object') {
        const obj = item as any;
        const candidate = obj.tag ?? obj.name ?? obj.value ?? obj.label;
        if (typeof candidate === 'string') {
          const t = candidate.trim();
          if (t) result.push(t);
        }
      }
    }
    return Array.from(new Set(result));
  }

  /**
   * 获取所有可用标签
   */
  async function fetchAllTags() {
    try {
      const response = await audiosApi.getAllTags({ unwrapResponse: false }) as APIResponse<any>;
      if (response.success && response.data) {
        allTags.value = normalizeTagList(response.data.items ?? response.data.data ?? response.data ?? []);
        tagsLoaded.value = true;
        const tagSet = new Set(allTags.value);
        selectedTags.value = selectedTags.value.filter(tag => tagSet.has(tag));
      }
    } catch (e) {
      console.error('Fetch all tags failed:', e);
    }
  }

  // ========== 查询参数构建 ==========

  /**
   * 统一的查询参数构建逻辑（避免客户端/服务端过滤逻辑重复）
   */
  function buildQueryParams(overrides: Partial<AudioQueryParams> = {}): AudioQueryParams {
    const normalizedSampleRate =
      filters.value.sampleRate === 'all' ? undefined : (normalizeSampleRate(filters.value.sampleRate) ?? filters.value.sampleRate);
    return {
      page: currentPage.value,
      perPage: pageSize.value,
      keyword: searchQuery.value || undefined,
      audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
      format: filters.value.format === 'all' ? undefined : filters.value.format,
      sampleRate: normalizedSampleRate,
      duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
      direction: filters.value.direction === 'all' ? undefined : filters.value.direction,
      ...overrides
    };
  }

  /**
   * 构建带模式的标签参数
   */
  function buildTagParams(): (string | { name: string; mode: string })[] | undefined {
    const shouldFilterByTags = selectedTags.value.length > 0 && !isAllTagsSelected();
    if (!shouldFilterByTags) return undefined;
    return selectedTags.value.map(tag => {
      const mode = tagModes.value?.get(tag);
      if (mode === 'or') {
        return { name: tag, mode: 'or' };
      }
      return tag;
    });
  }

  // ========== 音频列表获取 ==========

  async function fetchAudios() {
    loading.value = true;
    try {
      const params: AudioQueryParams = buildQueryParams({
        tags: buildTagParams()
      });

      const response = await audiosApi.getAll(params, { unwrapResponse: false }) as APIResponse<any>;

      if (response.success && response.data) {
        let items: any[] = [];
        let total: number = 0;
        let statsData: any;

        if (Array.isArray(response.data)) {
          items = response.data;
          total = response.data.length;
        } else if (response.data.items) {
          items = response.data.items;
          total = response.data.total;
          statsData = response.data.stats;
        } else if (response.data.data) {
          items = response.data.data;
          total = response.data.total;
          statsData = response.data.stats;
        }

        audioList.value = items.map((audio: any) => ({
          id: audio.id,
          name: audio.name,
          filename: audio.original_filename || audio.filename || '',
          filepath: audio.filePath || audio.file_path || audio.filepath || '',
          size: audio.size || 0,
          duration: audio.duration || 0,
          format: audio.format || '',
          sampleRate: audio.sample_rate || audio.sampleRate || 0,
          channels: audio.channels || 0,
          type: audio.audioType || audio.type || 'dry',
          audioType: audio.audioType || audio.type || 'dry',
          tags: audio.tags || [],
          createdAt: audio.created_at || audio.createdAt || new Date().toISOString(),
          updatedAt: audio.updated_at || audio.updatedAt || new Date().toISOString(),
          asrText: audio.asr_text || audio.asrText || '',
          translations: audio.translations || [],
          annotations: audio.annotations || [],
          description: audio.description || '',
          sourceLanguage: audio.source_language || audio.sourceLanguage || ''
        }));
        totalAudios.value = total;
        if (statsData) {
          stats.value = statsData;
        }

        // 确保 selectedTags 只包含真实标签
        if (tagsLoaded.value && allTags.value.length > 0) {
          const tagSet = new Set(allTags.value);
          selectedTags.value = selectedTags.value.filter(tag => tagSet.has(tag));
        }
      }
    } catch (e) {
      console.error('Fetch audios failed:', e);
    } finally {
      loading.value = false;
    }
  }

  // ========== 客户端过滤 ==========

  const filteredAudios = computed(() => {
    return audioList.value.filter(audio => {
      // 搜索词过滤
      const matchesSearch = !searchQuery.value ||
        audio.name?.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
        audio.asrText?.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
        audio.filename?.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
        audio.filepath?.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
        audio.filePath?.toLowerCase().includes(searchQuery.value.toLowerCase());

      // 音频类型过滤
      const matchesType = filters.value.audioType === 'all' || audio.type?.toLowerCase() === filters.value.audioType.toLowerCase();

      // 格式过滤
      const matchesFormat = filters.value.format === 'all' || audio.format?.toLowerCase() === filters.value.format.toLowerCase();

      // 采样率过滤
      const filterSampleRate = normalizeSampleRate(filters.value.sampleRate);
      const audioSampleRate = normalizeSampleRate(audio.sampleRate);
      const matchesSampleRate =
        filters.value.sampleRate === 'all' ||
        (filterSampleRate !== null && audioSampleRate !== null && audioSampleRate === filterSampleRate);

      // 时长过滤
      const matchesDuration = filters.value.duration === 'all' || {
        short: (audio.duration || 0) <= 30,
        medium: (audio.duration || 0) > 30 && (audio.duration || 0) <= 300,
        long: (audio.duration || 0) > 300
      }[filters.value.duration] || false;

      // 标签过滤
      let matchesTags = true;
      if (selectedTags.value.length > 0 && !isAllTagsSelected()) {
        const audioTags = audio.tags;
        let hasMatchingTag = false;

        if (Array.isArray(audioTags)) {
          hasMatchingTag = audioTags.some(tag => selectedTags.value.includes(tag));
        } else if (typeof audioTags === 'string') {
          const tagsString = audioTags as string;
          const audioTagArray = tagsString.split(',').map(tag => tag.trim()).filter(Boolean);
          hasMatchingTag = audioTagArray.some(tag => selectedTags.value.includes(tag));
        }

        matchesTags = hasMatchingTag;
      }

      return matchesSearch && matchesType && matchesFormat && matchesSampleRate && matchesDuration && matchesTags;
    });
  });

  const totalPages = computed(() => {
    return Math.ceil(totalAudios.value / pageSize.value);
  });

  // ========== 过滤控制 ==========

  function applyFilters() {
    currentPage.value = 1;
  }

  function resetFilters() {
    filters.value.audioType = 'all';
    filters.value.format = 'all';
    filters.value.duration = 'all';
    filters.value.sampleRate = 'all';
    filters.value.direction = 'all';
    filters.value.dateRange = null;
    searchQuery.value = '';
    selectedTags.value = tagsLoaded.value && allTags.value.length > 0 ? [...allTags.value] : [];
    applyFilters();
  }

  function toggleTag(tag: string, mode?: 'or' | 'and') {
    tagFilterToggleTag(tag, mode);
  }

  function filterAudios(newFilters?: any) {
    if (newFilters) {
      if (newFilters.format) filters.value.format = newFilters.format;
      if (newFilters.sampleRate) filters.value.sampleRate = normalizeSampleRate(newFilters.sampleRate) ?? newFilters.sampleRate;
      if (newFilters.duration) filters.value.duration = newFilters.duration;
      if (newFilters.audioType) filters.value.audioType = newFilters.audioType;
      if (newFilters.tags) {
        selectedTags.value = newFilters.tags || [];
      }
    }
  }

  // ========== 选择管理 ==========

  function toggleSelectAll() {
    if (selectedAudios.value.length === audioList.value.length) {
      selectedAudios.value = [];
    } else {
      selectedAudios.value = audioList.value.map(a => a.id);
    }
  }

  function toggleAudioSelection(id: string | number) {
    const index = selectedAudios.value.indexOf(id);
    if (index === -1) {
      selectedAudios.value.push(id);
    } else {
      selectedAudios.value.splice(index, 1);
    }
  }

  function selectCurrentPage() {
    selectedAudios.value = audioList.value.map(a => a.id);
    showSelectAllOptions.value = false;
    selectAllAcrossPages.value = false;
  }

  async function selectAllPages() {
    selectAllAcrossPages.value = true;
    showSelectAllOptions.value = false;
    loading.value = true;

    const originalPage = currentPage.value;
    const originalSelected = [...selectedAudios.value];

    try {
      const params: AudioQueryParams = buildQueryParams({
        page: 1,
        perPage: 10000,
        tags: (selectedTags.value.length > 0 && !isAllTagsSelected()) ? selectedTags.value : undefined
      });

      try {
        const idsParams = { ...params, page: 1, perPage: 10000 };
        const response = await audiosApi.getAllIds(idsParams, { unwrapResponse: false }) as APIResponse<any>;

        if (response.success && response.data) {
          selectedAudios.value = response.data.ids || response.data || [];
        } else {
          throw new Error('Failed to get all audio IDs');
        }
      } catch (error) {
        console.error('Failed to call getAllIds, falling back to pagination:', error);

        const allSelectedIds = new Set<string | number>();
        let currentPageNum = 1;
        let hasMorePages = true;

        const originalPageSize = pageSize.value;
        pageSize.value = 100;

        while (hasMorePages) {
          const response = await audiosApi.getAll({ ...params, page: currentPageNum, perPage: pageSize.value }, { unwrapResponse: false }) as APIResponse<any>;

          if (response.success && response.data) {
            let items: AudioInfo[] = [];
            if (Array.isArray(response.data)) {
              items = response.data;
            } else if (response.data.items) {
              items = response.data.items as AudioInfo[];
            } else if (response.data.data) {
              items = response.data.data as AudioInfo[];
            }

            items.forEach(audio => {
              allSelectedIds.add(audio.id);
            });

            if (items.length < pageSize.value) {
              hasMorePages = false;
            } else {
              currentPageNum++;
            }
          } else {
            hasMorePages = false;
          }
        }

        pageSize.value = originalPageSize;
        selectedAudios.value = Array.from(allSelectedIds);
      }
    } catch (error) {
      console.error('Failed to select all pages:', error);
      selectedAudios.value = originalSelected;
      selectAllAcrossPages.value = false;
    } finally {
      currentPage.value = originalPage;
      loading.value = false;
    }
  }

  // ========== 分页控制 ==========

  function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--;
    }
  }

  function nextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
    }
  }

  function handleGoToPage(page: number) {
    currentPage.value = page;
  }

  function handlePageSizeChange(size: number) {
    pageSize.value = size;
    currentPage.value = 1;
  }

  function switchView(mode: 'list' | 'folder') {
    viewMode.value = mode;
  }

  function resetAllStates() {
    selectedAudios.value = [];
    resetFilters();
  }

  return {
    // 状态
    audioList,
    totalAudios,
    loading,
    currentPage,
    pageSize,
    searchTerm,
    searchQuery,
    audioTypeFilter,
    viewMode,
    filters,
    stats,
    allTags,
    tagsLoaded,
    selectedTags,
    tagModes,
    tagModesObject,
    selectedAudios,
    showSelectAllOptions,
    selectAllAcrossPages,
    // 计算属性
    filteredAudios,
    totalPages,
    // 标签方法
    fetchAllTags,
    isAllTagsSelected,
    toggleTag,
    clearTags,
    // 列表方法
    fetchAudios,
    buildQueryParams,
    buildTagParams,
    // 过滤方法
    applyFilters,
    resetFilters,
    filterAudios,
    // 选择方法
    toggleSelectAll,
    toggleAudioSelection,
    toggleFolderSelection,
    isFolderAllSelected,
    isFolderPartialSelected,
    selectCurrentPage,
    selectAllPages,
    // 分页方法
    prevPage,
    nextPage,
    handleGoToPage,
    handlePageSizeChange,
    switchView,
    resetAllStates,
    // 工具
    normalizeSampleRate,
  };
}
