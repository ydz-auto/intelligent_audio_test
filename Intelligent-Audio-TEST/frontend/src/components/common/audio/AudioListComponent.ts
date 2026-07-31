import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { buildFolderTree, extractAllTags, filterAudios as filterAudiosUtil } from '../../../utils/audioUtils';
import { useTagFilter, type TagFilterState } from '../../../composables/shared/useTagFilter';

export interface AudioProblem {
  type: string;
  description: string;
  severity: 'severe' | 'warning' | 'info';
}

export interface AudioItem {
  id: string | number;
  filename: string;
  path: string;
  format: string;
  size: string;
  duration: string;
  type: string;
  sourceLanguage?: string;
  tags: string[];
  status?: string;
  problems?: AudioProblem[];
  audioType?: string;
}

export interface FolderNode {
  name: string;
  files: AudioItem[];
  folders: FolderNode[];
}

export interface AudioListProps {
  audios: AudioItem[];
  loading?: boolean;
  viewMode?: 'list' | 'folder' | 'diagnostics';
  enableSelection: boolean;
  showStatus: boolean;
  audioType: string;
  selectedAudios: (string | number)[];
  totalAudios: number;
  currentPage: number;
  pageSize: number;
  allTags: string[];
  selectedTags: string[];
  tagModes?: Record<string, 'or' | 'and'>;
  serverFolderTree?: any;
  folderLoading?: boolean;
  expandedFolderPaths?: Set<string>;
  isFolderAllSelectedFn?: (folder: any) => boolean;
  isFolderPartialSelectedFn?: (folder: any) => boolean;
}

export function useAudioListComponent(props: AudioListProps, emit: any) {
  const viewMode = ref<'list' | 'folder' | 'diagnostics'>(props.viewMode ?? 'list');

  const searchQuery = ref('');
  const tagSearchQuery = ref('');
  const filters = ref({
    format: 'all',
    sampleRate: 'all',
    duration: 'all',
    audioType: props.audioType || 'all'
  });

  const {
    selectedTags: localSelectedTags,
    tagModes: localTagModes,
    tagModesObject,
    isTagSelected,
    getTagMode,
    handleTagClick: localHandleTagClick,
    setTagMode: localSetTagMode,
    removeTag: localRemoveTag,
    setTagsFromProps
  } = useTagFilter();

  const showTagModeMenu = ref(false);
  const menuPosition = ref({ x: 0, y: 0 });
  const currentMenuTag = ref('');

  const selectedTags = computed(() => {
    if (props.selectedTags && props.selectedTags.length > 0) {
      return props.selectedTags;
    }
    return localSelectedTags.value;
  });

  const tagModes = computed(() => {
    if (props.tagModes && Object.keys(props.tagModes).length > 0) {
      return new Map(Object.entries(props.tagModes));
    }
    return localTagModes.value;
  });

  const handleTagClick = (tagName: string) => {
    const result = localHandleTagClick(tagName);
    emit('filterChange', {
      tags: result.selectedTags,
      tagModes: result.tagModes
    });
  };

  const showTagMenu = (event: MouseEvent, tag: string) => {
    if (!selectedTags.value.includes(tag)) return;
    currentMenuTag.value = tag;
    menuPosition.value = { x: event.pageX, y: event.pageY };
    showTagModeMenu.value = true;

    const closeMenu = () => {
      showTagModeMenu.value = false;
      document.removeEventListener('click', closeMenu);
    };
    setTimeout(() => {
      document.addEventListener('click', closeMenu);
    }, 0);
  };

  const setTagMode = (mode: 'or' | 'and') => {
    if (currentMenuTag.value) {
      const result = localSetTagMode(currentMenuTag.value, mode);
      emit('filterChange', {
        ...filters.value,
        tags: result.selectedTags,
        tagModes: result.tagModes
      });
    }
    showTagModeMenu.value = false;
  };

  const removeTag = () => {
    if (currentMenuTag.value) {
      const result = localRemoveTag(currentMenuTag.value);
      emit('filterChange', {
        tags: result.selectedTags,
        tagModes: result.tagModes
      });
    }
    showTagModeMenu.value = false;
  };

  const toggleTag = (tagName: string) => {
    emit('toggleTag', tagName);
  };

  const localAllTags = ref<string[]>([]);

  const allTags = computed(() => {
    if (props.allTags && props.allTags.length > 0) {
      return props.allTags;
    }
    return localAllTags.value;
  });

  const filteredTags = computed(() => {
    let tags = [...allTags.value];

    if (tagSearchQuery.value.trim()) {
      const query = tagSearchQuery.value.toLowerCase();
      tags = tags.filter(tag => tag.toLowerCase().includes(query));
    }

    const selectedAudioIds = new Set(localSelectedAudios.value);
    const selectedAudioTagCounts = new Map<string, number>();

    props.audios.forEach(audio => {
      if (selectedAudioIds.has(audio.id) && audio.tags) {
        const audioTags = Array.isArray(audio.tags) ? audio.tags : String(audio.tags).split(',');
        audioTags.forEach((tag: string) => {
          const trimmedTag = tag.trim();
          if (trimmedTag) {
            selectedAudioTagCounts.set(trimmedTag, (selectedAudioTagCounts.get(trimmedTag) || 0) + 1);
          }
        });
      }
    });

    tags.sort((a, b) => {
      const countA = selectedAudioTagCounts.get(a) || 0;
      const countB = selectedAudioTagCounts.get(b) || 0;
      return countB - countA;
    });

    return tags;
  });

  const localSelectedAudios = ref<(string | number)[]>([...props.selectedAudios]);
  const headerCheckboxChecked = ref(false);

  const isAllSelected = computed({
    get() {
      const allSelected = localSelectedAudios.value.length === props.audios.length && props.audios.length > 0;
      headerCheckboxChecked.value = allSelected;
      return allSelected;
    },
    set() {
      toggleSelectAll();
    }
  });

  const folderTree = ref<FolderNode>({
    name: '音频文件',
    files: [],
    folders: []
  });

  const activeFolderTree = computed(() => {
    if (props.serverFolderTree && props.serverFolderTree.name) {
      return props.serverFolderTree as FolderNode;
    }
    return folderTree.value;
  });

  const MAX_VISIBLE_TAGS = 8;
  const expandedTags = ref<Record<string | number, boolean>>({});

  const toggleExpandTags = (audioId: string | number) => {
    expandedTags.value[audioId] = !expandedTags.value[audioId];
  };

  const getNormalizedTags = (tags: any): string[] => {
    if (!tags) return [];
    if (Array.isArray(tags)) return tags;
    if (typeof tags === 'string') {
      return tags.split(',').map((t: string) => t.trim()).filter((t: string) => t);
    }
    return [];
  };

  const problematicAudios = computed(() => {
    return props.audios.filter(audio => audio.problems && audio.problems.length > 0);
  });

  watch(() => props.audios, (newAudios) => {
    folderTree.value = buildFolderTree(newAudios);
  }, { deep: true });

  watch(() => props.audioType, (newType) => {
    filters.value.audioType = newType || 'all';
  }, { immediate: true });

  watch(() => props.selectedAudios, (newSelected) => {
    localSelectedAudios.value = [...newSelected];
  }, { deep: true });

  watch(() => props.allTags, (newAllTags) => {
    if (newAllTags && newAllTags.length > 0) {
      localAllTags.value = [...newAllTags];
    }
  }, { deep: true, immediate: true });

  watch(
    () => props.viewMode,
    (newMode) => {
      if (!newMode) return;
      if (newMode !== viewMode.value) viewMode.value = newMode;
    }
  );

  const switchView = (mode: 'list' | 'folder' | 'diagnostics') => {
    viewMode.value = mode;
    emit('view-change', mode);
  };

  const handleSearch = () => {
    emit('search', searchQuery.value);
  };

  const handleFilterChange = () => {
    emit('filterChange', filters.value);
  };

  const resetFilters = () => {
    filters.value = { format: 'all', sampleRate: 'all', duration: 'all', audioType: props.audioType || 'all' };
    searchQuery.value = '';
    emit('filterChange', { ...filters.value, tags: [], tagModes: {}, resetSearch: true });
  };

  const applyFilters = () => {
    emit('filterChange', { ...filters.value, tags: [...selectedTags.value], tagModes: Object.fromEntries(tagModes.value) });
  };

  // 直接使用props.audios，因为它已经是在父组件中过滤过的音频列表
  const filteredAudios = computed(() => props.audios);

  // 文件夹展开/折叠由父组件通过 expandedFolderPaths prop 控制
  const toggleFolder = (folder: FolderNode) => {
    emit('expand-folder', folder.path ?? '');
  };

  const handleAudioSelect = (audio: AudioItem) => {
    emit('select', audio);
  };

  const isSelected = (audioId: string | number) => {
    return localSelectedAudios.value.includes(audioId);
  };

  const toggleAudioSelection = (audioId: string | number) => {
    if (props.enableSelection) {
      const index = localSelectedAudios.value.indexOf(audioId);
      if (index > -1) {
        localSelectedAudios.value.splice(index, 1);
      } else {
        localSelectedAudios.value.push(audioId);
      }
      emit('selectionChange', audioId);
    }
  };

  const toggleSelectAll = () => {
    emit('toggleSelectAll');
  };

  const handleCheckboxClick = () => {
    if (isAllSelected.value) {
      emit('toggleSelectAll');
    } else {
      emit('selectCurrentPage');
    }
  };

  const handlePageChange = (page: number) => {
    emit('pageChange', page);
  };

  const handleSizeChange = (size: number) => {
    emit('sizeChange', size);
  };

  const previewAudio = (audioId: string | number) => {
    emit('preview', audioId);
  };

  const editMetadata = (audioId: string | number) => {
    if (!audioId) {
      alert('请先选择音频');
      return;
    }
    emit('edit', audioId);
  };

  const deleteAudio = (audioId: string | number) => {
    if (!audioId) {
      alert('请先选择音频');
      return;
    }
    emit('delete', audioId);
  };

  const convertAudio = (audioId: string | number) => {
    if (!audioId) {
      alert('请先选择音频');
      return;
    }
    emit('convert', audioId);
  };

  const downloadAudio = (audioId: string | number) => {
    if (!audioId) {
      alert('请先选择音频');
      return;
    }
    emit('download', audioId);
  };

  const getProblemIcon = (type: string) => {
    const icons: Record<string, string> = {
      metadata: 'fas fa-tags',
      format: 'fas fa-file-audio',
      duration: 'fas fa-clock',
      corrupted: 'fas fa-exclamation-triangle'
    };
    return icons[type] || 'fas fa-exclamation-circle';
  };

  const handleClickOutside = (event: MouseEvent) => {
  };

  onMounted(() => {
    localAllTags.value = [...props.allTags];
    folderTree.value = buildFolderTree(props.audios);
    document.addEventListener('click', handleClickOutside);
  });

  onUnmounted(() => {
    document.removeEventListener('click', handleClickOutside);
  });

  return {
    viewMode,
    searchQuery,
    tagSearchQuery,
    filters,
    showTagModeMenu,
    menuPosition,
    selectedTags,
    tagModes,
    handleTagClick,
    showTagMenu,
    setTagMode,
    removeTag,
    toggleTag,
    filteredTags,
    isTagSelected,
    getTagMode,
    isAllSelected,
    activeFolderTree,
    MAX_VISIBLE_TAGS,
    expandedTags,
    toggleExpandTags,
    getNormalizedTags,
    problematicAudios,
    switchView,
    handleSearch,
    handleFilterChange,
    resetFilters,
    applyFilters,
    filteredAudios,
    toggleFolder,
    handleAudioSelect,
    isSelected,
    toggleAudioSelection,
    handleCheckboxClick,
    handlePageChange,
    handleSizeChange,
    previewAudio,
    editMetadata,
    deleteAudio,
    convertAudio,
    downloadAudio,
    getProblemIcon,
  }
}
