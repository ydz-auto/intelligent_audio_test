import { ref, computed } from 'vue';
import { audiosApi } from '../utils/api';
import { formatFileSize, formatDuration } from '../utils/audioUtils';
import { useTagFilter } from './useTagFilter';

export interface AudioItem {
  id: string | number;
  filename: string;
  path: string;
  format: string;
  size: string;
  duration: string;
  type: string;
  tags: string[];
  status?: string;
  asrText?: string;
  annotations?: any[];
}

export interface AudioQueryParams {
  page?: number;
  perPage?: number;
  keyword?: string;
  audioType?: string;
  format?: string;
  sampleRate?: string;
  duration?: string;
  direction?: string;
  tags?: string[];
  tagMatchMode?: 'or' | 'and';
}

export interface RawAudioData {
  id: string | number;
  name?: string;
  filename?: string;
  originalFilename?: string;
  filePath?: string;
  path?: string;
  format?: string;
  size?: number;
  duration?: number;
  audioType?: string;
  type?: string;
  tags?: string[] | string;
  tag?: string[] | string;
  status?: string;
  asrText?: string;
  annotations?: any[];
}

export function useAudioList() {
  const audios = ref<AudioItem[]>([]);
  const totalAudios = ref(0);
  const currentPage = ref(1);
  const pageSize = ref(20);
  const searchQuery = ref('');
  const allTags = ref<string[]>([]);
  const tagMatchMode = ref<'or' | 'and'>('and');
  
  const {
    selectedTags,
    tagModes,
    tagModesObject,
    handleTagClick: tagFilterHandleTagClick,
    setTagMode: tagFilterSetTagMode,
    removeTag: tagFilterRemoveTag,
    clearTags
  } = useTagFilter();
  
  const filters = ref({
    format: 'all',
    sampleRate: 'all',
    duration: 'all',
    audioType: 'all',
    direction: 'all'
  });

  const totalPages = computed(() => {
    return Math.ceil(totalAudios.value / pageSize.value);
  });

  const formatFilePath = (path: string): string => {
    if (!path) return '';
    
    const normalizedPath = path.replace(/\\/g, '/');
    
    const audioPathPattern = /\/static\/audios\/(.*)/i;
    const match = normalizedPath.match(audioPathPattern);
    if (match && match[1]) {
      return `/audios/${match[1]}`;
    }
    
    const altAudioPathPattern = /\/audios\/(.*)/i;
    const altMatch = normalizedPath.match(altAudioPathPattern);
    if (altMatch && altMatch[1]) {
      return `/audios/${altMatch[1]}`;
    }
    
    const pathParts = normalizedPath.split('/');
    const fileNameIndex = pathParts.lastIndexOf('audios');
    if (fileNameIndex !== -1 && fileNameIndex < pathParts.length - 1) {
      return pathParts.slice(fileNameIndex).join('/');
    }
    
    return pathParts[pathParts.length - 1];
  };

  const formatAudioData = (audio: RawAudioData): AudioItem => {
    let audioTags: string[] = [];
    if (Array.isArray(audio.tags)) {
      audioTags = audio.tags;
    } else if (Array.isArray(audio.tag)) {
      audioTags = audio.tag;
    } else if (typeof audio.tags === 'string' && audio.tags) {
      audioTags = audio.tags.split(',').map(tag => tag.trim());
    } else if (typeof audio.tag === 'string' && audio.tag) {
      audioTags = audio.tag.split(',').map(tag => tag.trim());
    }
    
    return {
      id: audio.id, 
      filename: audio?.name || audio?.filename || audio?.originalFilename || '', 
      path: formatFilePath(audio?.filePath || audio?.path || ''), 
      format: audio.format || 'unknown', 
      size: formatFileSize(audio.size || 0), 
      duration: formatDuration(audio.duration || 0), 
      type: audio?.audioType || audio?.type || 'dry', 
      tags: audioTags, 
      status: audio?.status || 'active', 
      asrText: audio?.asrText || '',
      annotations: audio?.annotations || []
    };
  };

  const normalizeSampleRate = (value: unknown): string | null => {
    if (value === undefined || value === null) return null;
    const str = String(value).trim();
    if (!str || str === 'all') return null;
    const lower = str.toLowerCase();
    if (lower.includes('khz') || lower.includes('k hz') || lower.includes('k')) {
      const num = parseFloat(lower.replace(/[^0-9.]+/g, ''));
      if (!Number.isFinite(num)) return null;
      return String(Math.round(num * 1000));
    }
    const int = parseInt(lower.replace(/[^0-9]+/g, ''), 10);
    if (!Number.isFinite(int)) return null;
    return String(int);
  };

  const loadAudios = async () => {
    try {
      const normalizedSampleRate = filters.value.sampleRate === 'all' 
        ? undefined 
        : (normalizeSampleRate(filters.value.sampleRate) ?? filters.value.sampleRate);
      
      const params: AudioQueryParams = {
        page: currentPage.value,
        perPage: pageSize.value,
        keyword: searchQuery.value || undefined,
        audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
        format: filters.value.format === 'all' ? undefined : filters.value.format,
        sampleRate: normalizedSampleRate,
        duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
        direction: filters.value.direction === 'all' ? undefined : filters.value.direction
      };
      
      if (selectedTags.value.length > 0) {
        // 转换标签为带模式的格式：[{name: 'xxx', mode: 'or'}, 'yyy']
        const tagsWithMode: (string | { name: string; mode: string })[] = selectedTags.value.map(tag => {
          const mode = tagModes.value?.get(tag);
          if (mode === 'or') {
            return { name: tag, mode: 'or' };
          }
          return tag;
        });
        params.tags = tagsWithMode;
      }
      
      const response = await audiosApi.getAll(params, { unwrapResponse: false }) as any;
      
      if (response.success && response.data) {
        let items: any[] = [];
        let total = 0;
        
        if (Array.isArray(response.data)) {
          items = response.data;
          total = response.data.length;
        } else if (response.data.items) {
          items = response.data.items;
          total = response.data.total;
        } else if (response.data.data) {
          items = response.data.data;
          total = response.data.total;
        }
        
        audios.value = items.map(formatAudioData);
        totalAudios.value = total;
        
        console.log('[useAudioList] 加载音频成功:', { itemsCount: items.length, total });
      } else {
        console.warn('[useAudioList] 加载音频失败:', response);
      }
    } catch (error) {
      console.error('[useAudioList] 加载音频失败:', error);
    }
  };

  const loadAllTags = async () => {
    try {
      const response = await audiosApi.getAllTags({ unwrapResponse: false }) as any;
      if (response.success && response.data) {
        let tags: string[] = [];
        if (Array.isArray(response.data)) {
          tags = response.data;
        } else if (response.data.items) {
          tags = response.data.items;
        } else if (response.data.tags) {
          tags = response.data.tags;
        }
        allTags.value = tags;
      }
    } catch (error) {
      console.error('[useAudioList] 加载标签失败:', error);
    }
  };

  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  const handleSearch = (query: string) => {
    searchQuery.value = query;
    currentPage.value = 1;
    if (searchDebounceTimer) {
      clearTimeout(searchDebounceTimer);
    }
    searchDebounceTimer = setTimeout(() => {
      loadAudios();
      searchDebounceTimer = null;
    }, 300);
  };

  const handleFilterChange = (newFilters: any) => {
    if (newFilters) {
      if (newFilters.format) filters.value.format = newFilters.format;
      if (newFilters.sampleRate) filters.value.sampleRate = newFilters.sampleRate;
      if (newFilters.duration) filters.value.duration = newFilters.duration;
      if (newFilters.audioType) filters.value.audioType = newFilters.audioType;
      if (newFilters.direction) filters.value.direction = newFilters.direction;
      if (newFilters.tags) {
        selectedTags.value = newFilters.tags;
      }
      if (newFilters.tagModes) {
        tagModes.value = new Map(Object.entries(newFilters.tagModes));
      }
      if (newFilters.tagMatchMode) {
        tagMatchMode.value = newFilters.tagMatchMode;
      }
      if (newFilters.resetSearch) {
        searchQuery.value = '';
      }
      if (newFilters.resetPage !== false) {
        currentPage.value = 1;
      }
    }
    loadAudios();
  };

  const handleToggleTag = (tag: string, mode?: 'or' | 'and') => {
    const index = selectedTags.value.indexOf(tag);
    if (index === -1) {
      selectedTags.value.push(tag);
      if (mode) {
        tagModes.value.set(tag, mode);
      } else {
        tagModes.value.set(tag, 'and');
      }
    } else {
      selectedTags.value.splice(index, 1);
      tagModes.value.delete(tag);
    }
    currentPage.value = 1;
    loadAudios();
  };

  const handleTagClick = (tag: string, mode?: 'or' | 'and') => {
    tagFilterHandleTagClick(tag);
    currentPage.value = 1;
    loadAudios();
  };

  const handlePageChange = (page: number) => {
    currentPage.value = page;
    loadAudios();
  };

  const handleSizeChange = (size: number) => {
    pageSize.value = size;
    currentPage.value = 1;
    loadAudios();
  };

  const resetFilters = (options?: { resetSearch?: boolean; resetPage?: boolean; preserveAudioType?: boolean; audioType?: string }) => {
    searchQuery.value = options?.resetSearch ? '' : searchQuery.value;
    const preservedAudioType = options?.preserveAudioType ? filters.value.audioType : (options?.audioType || 'all');
    filters.value = {
      format: 'all',
      sampleRate: 'all',
      duration: 'all',
      audioType: preservedAudioType,
      direction: 'all'
    };
    clearTags();
    tagMatchMode.value = 'and';
    if (options?.resetPage !== false) {
      currentPage.value = 1;
    }
    loadAudios();
  };

  const resetSearch = () => {
    searchQuery.value = '';
    currentPage.value = 1;
    loadAudios();
  };

  return {
    audios,
    totalAudios,
    currentPage,
    pageSize,
    searchQuery,
    allTags,
    selectedTags,
    tagMatchMode,
    tagModes,
    tagModesObject,
    filters,
    totalPages,
    formatFilePath,
    formatAudioData,
    normalizeSampleRate,
    loadAudios,
    loadAllTags,
    handleSearch,
    handleFilterChange,
    handleToggleTag,
    handleTagClick,
    handlePageChange,
    handleSizeChange,
    resetFilters,
    resetSearch
  };
}
