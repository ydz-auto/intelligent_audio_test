import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue';
import { audiosApi, devicesApi } from '../../utils/api';
import SparkMD5 from 'spark-md5';
import { getModalManager } from '../../utils/modalManager';
import { useModalStore } from '../../store/modalStore';
import { useUploadState } from '../../composables/useUploadState';
import { useTagFilter } from '../../composables/useTagFilter';
import type { 
  AudioInfo, 
  AudioUploadFile, 
  AudioUploadTask, 
  AudioUploadOptions, 
  APIResponse, 
  AudioStats, 
  PlaybackDevice, 
  AudioQueryParams
 } from '../../shared/types/index';
import { MODAL_TYPES } from '../../shared/types/index';

export function useAudioImport() {
  const modalManager = getModalManager();
  const modalStore = useModalStore();
  
  const { uploadProgress, currentTask, currentUploadingFile, isRetryingFailed, uploadStatus } = useUploadState();
  
  const audioList = ref<AudioInfo[]>([]);
  const totalAudios = ref(0);
  const loading = ref(false);
  const currentPage = ref(1);
  const pageSize = ref(20);
  const searchTerm = ref('');
  const searchQuery = ref('');
  const audioTypeFilter = ref<'all' | 'dry' | 'noise' | 'prompt' | 'mixed'>('all');
  const viewMode = ref<'list' | 'folder'>('list');
  const showConvertModal = ref(false);
  const selectedAudios = ref<(string | number)[]>([]);
  
  const filters = ref({
    format: 'all',
    sampleRate: 'all',
    duration: 'all',
    audioType: 'all',
    direction: 'all',
    dateRange: null as [Date, Date] | null,
    tagMatchMode: 'and' as 'or' | 'and'
  });

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

  function isAllTagsSelected(): boolean {
    if (!tagsLoaded.value) return false;
    if (allTags.value.length === 0) return false;
    if (selectedTags.value.length < allTags.value.length) return false;
    const selectedSet = new Set(selectedTags.value);
    return allTags.value.every(t => selectedSet.has(t));
  }

  function normalizeSampleRate(value: unknown): string | null {
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

  const urlImportData = reactive({
    url: '',
    type: 'dry' as 'dry' | 'noise' | 'prompt' | 'mixed',
    tags: [] as string[]
  });

  const convertAudioInfo = reactive({
    id: '' as string | number,
    name: '',
    originalFileName: '',
    originalFormat: '',
    originalSampleRate: '',
    originalChannels: '',
    originalBitDepth: '',
    targetFormat: 'wav',
    targetSampleRate: '44100',
    targetChannels: '1',
    targetBitDepth: '16'
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

  const expandedFolders = ref<Set<string>>(new Set());
  const showSelectAllOptions = ref(false);
  
  const folderImportOptions = reactive({
    recursive: true,
    keepStructure: true,
    allowedExtensions: ['.wav', '.mp3', '.m4a', '.flac'],
    createTestCase: false,
    testTypes: ['api'] as ('api' | 'e2e')[],
    playbackDeviceId: null as string | number | null,
    spl: 65.0,
    groupNameType: 'root' as 'root' | 'folder' | 'custom',
    customGroupName: '',
    translationDirectionId: '' as string | number | null
  });

  const showDeleteResultModal = computed({
    get: () => modalStore.showDeleteResultModal,
    set: (val) => modalStore.showDeleteResultModal = val
  });

  const deleteResult = computed({
    get: () => modalStore.deleteResult,
    set: (val) => modalStore.deleteResult = {...modalStore.deleteResult, ...val}
  });

  const showAudioPlayerModal = ref(false);
  const audioTitle = ref('');
  const currentPreviewAudioId = ref<string | number | null>(null);
  const currentPreviewAudioType = ref<'dry' | 'noise' | 'prompt' | 'mixed'>('dry');

  const playbackDevices = ref<PlaybackDevice[]>([]);
  const playbackDevicePage = ref(1);
  const playbackDevicePages = ref(1);
  const playbackDeviceLoading = ref(false);
  const playbackDeviceHasMore = ref(true);
  const translationDirections = ref<any[]>([]);
  const uploadOptions = reactive<AudioUploadOptions>({
    audioType: 'dry',
    createTestCase: false,
    tags: [],
    description: '',
    testTypes: ['api'],
    playbackDeviceId: null,
    spl: 65.0,
    groupNameType: 'root',
    customGroupName: '',
    translationDirectionId: '',
    inheritTags: true,
    dimensions: { api: [], e2e: [] },
    noiseAudioId: null,
    noiseSpl: 60.0,
    algorithmType: '',
    algorithmRelations: [],
    algorithmParams: [],
    promptDeviceId: null,
    promptSourceLanguage: '',
    promptTargetLanguage: '',
    promptTranslationDirection: '',
    promptAlgorithmType: ''
  });

  const algorithmOptions = ref<{ value: string; name: string }[]>([]);
  const selectedAlgorithmType = ref<string>('');
  const algorithmParams = ref<any[]>([]);

  const uploadTasks = ref<AudioUploadTask[]>([]);
  const selectedFilesForUpload = ref<File[]>([]);
  const fileList = ref<AudioUploadFile[]>([]);
  
  let abortController : AbortController | null = null;
  let isOpeningUploadModal = false;
  let isOpeningFolderImport = false;

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
      
      // 标签过滤 - 如果 selectedTags 为空，则匹配所有音频
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

  const flattenedFolderTree = computed(() => {
    const folders: any[] = [];
    const folderMap = new Map<string, any>();

    audioList.value.forEach(audio => {
      const filePath = audio.filepath || '';
      if (!filePath) return;

      const normalizedPath = filePath.replace(/\\/g, '/');
      const lastSlashIndex = normalizedPath.lastIndexOf('/');
      
      let dir: string;
      if (lastSlashIndex === -1) {
        dir = '/';
      } else {
        dir = normalizedPath.substring(0, lastSlashIndex);
      }
      
      if (!folderMap.has(dir)) {
        const folderName = dir === '/' ? '根目录' : dir.split('/').pop() || '未知目录';
        folderMap.set(dir, { path: dir, name: folderName, files: [] });
        folders.push(folderMap.get(dir));
      }
      folderMap.get(dir).files.push(audio);
    });

    return folders;
  });

  const serverFolderTree = ref<any>({
    name: '音频文件',
    path: '',
    count: 0,
    file_count: 0,
    has_children: false,
    files: [],
    folders: []
  });
  const folderLoading = ref(false);
  const expandedFolderPaths = ref<Set<string>>(new Set(['']));

  async function fetchFolderTree(params: any = {}) {
    folderLoading.value = true;
    try {
      const response = await audiosApi.getFolderTree({
        keyword: searchQuery.value || undefined,
        audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
        format: filters.value.format === 'all' ? undefined : filters.value.format,
        sampleRate: filters.value.sampleRate === 'all' ? undefined : normalizeSampleRate(filters.value.sampleRate),
        duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
        tags: selectedTags.value.length > 0 ? selectedTags.value.map(tag => {
          const mode = tagModes.value?.get(tag);
          return { name: tag, mode: mode || 'and' };
        }) : undefined,
        algorithmType: uploadOptions.algorithmType || undefined,
        depth: 2,
        ...params
      });
      
      if (response.success && response.data) {
        serverFolderTree.value = response.data.tree;
        totalAudios.value = response.data.total;
      }
    } catch (error) {
      console.error('获取文件夹树失败:', error);
    } finally {
      folderLoading.value = false;
    }
  }

  function toggleFolderExpand(folderPath: string) {
    if (expandedFolderPaths.value.has(folderPath)) {
      expandedFolderPaths.value.delete(folderPath);
    } else {
      expandedFolderPaths.value.add(folderPath);
    }
  }

  function isFolderExpanded(folderPath: string): boolean {
    return expandedFolderPaths.value.has(folderPath);
  }

  async function calculateMd5(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const chunkSize = 10 * 1024 * 1024;
      const chunks = Math.ceil(file.size / chunkSize);
      const spark = new SparkMD5.ArrayBuffer();
      const reader = new FileReader();
      let currentChunk = 0;

      reader.onload = (e) => {
        if (e.target?.result) {
          spark.append(e.target.result as ArrayBuffer);
          currentChunk++;
          if (currentChunk < chunks) {
            loadNext();
          } else {
            resolve(spark.end());
          }
        }
      };

      reader.onerror = () => reject('MD5 calculation failed');

      function loadNext() {
        const start = currentChunk * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        reader.readAsArrayBuffer(file.slice(start, end));
      }

      loadNext();
    });
  }

  function getLocalTasks(): AudioUploadTask[] {
    try {
      const stored = localStorage.getItem('audioUploadTasks');
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error('Failed to get local tasks:', e);
      return [];
    }
  }

  function saveLocalTask(task: AudioUploadTask): void {
    if (!task.id) return;
    try {
      const tasks = getLocalTasks();
      const index = tasks.findIndex(t => t.id === task.id);
      if (index !== -1) {
        tasks[index] = task;
      } else {
        tasks.push(task);
      }
      localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
      uploadTasks.value = tasks;
    } catch (e) {
      console.error('Failed to save local task:', e);
    }
  }

  function pathBasename(filePath: string): string {
    if (!filePath) return '';
    const parts = filePath.split(/[\\/]/);
    return parts[parts.length - 1];
  }

  // 获取所有可用标签
  async function fetchAllTags() {
    try {
      const response = await audiosApi.getAllTags({ unwrapResponse: false }) as APIResponse<any>;
      if (response.success && response.data) {
        allTags.value = normalizeTagList(response.data.items ?? response.data.data ?? response.data ?? []);
        tagsLoaded.value = true;
        const tagSet = new Set(allTags.value);
        selectedTags.value = selectedTags.value.filter(tag => tagSet.has(tag));
        console.log('[fetchAllTags] 获取到的所有标签:', allTags.value);
      }
    } catch (e) {
      console.error('Fetch all tags failed:', e);
    }
  }

  async function fetchAudios() {
    loading.value = true;
    try {
      const normalizedSampleRate =
        filters.value.sampleRate === 'all' ? undefined : (normalizeSampleRate(filters.value.sampleRate) ?? filters.value.sampleRate);
      const params : AudioQueryParams = {
        page: currentPage.value,
        perPage: pageSize.value,
        keyword: searchQuery.value || undefined,
        audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
        format: filters.value.format === 'all' ? undefined : filters.value.format,
        sampleRate: normalizedSampleRate,
        duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
        direction: filters.value.direction === 'all' ? undefined : filters.value.direction
      };
      
      const shouldFilterByTags = selectedTags.value.length > 0 && !isAllTagsSelected();
      if (shouldFilterByTags) {
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
      
      const response = await audiosApi.getAll(params, { unwrapResponse: false }) as APIResponse<any>;
      
      if (response.success && response.data) {
          let items : any[] = [];
          let total : number = 0;
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
          
          console.log('[fetchAudios] API响应数据:', response.data);
          console.log('[fetchAudios] 解析后的items:', items);
          console.log('[fetchAudios] total:', total);
          
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
        } else {
          console.log('[fetchAudios] 响应失败或无数据:', response);
        }
    } catch (e) {
      console.error('Fetch audios failed:', e);
    } finally {
      loading.value = false;
    }
  }

  async function fetchPlaybackDevices(reset = true) {
    if (reset) {
      playbackDevicePage.value = 1;
      playbackDevices.value = [];
      playbackDeviceHasMore.value = true;
    }
    if (playbackDeviceLoading.value || (!playbackDeviceHasMore.value && !reset)) return;
    playbackDeviceLoading.value = true;
    try {
      const response = await devicesApi.getPlaybackDevices({
        params: { page: playbackDevicePage.value, per_page: 50 },
        unwrapResponse: false
      }) as APIResponse<{ items: PlaybackDevice[]; pages: number }>;
      if (response.success && response.data && Array.isArray(response.data.items)) {
        if (reset) {
          playbackDevices.value = response.data.items;
        } else {
          playbackDevices.value = [...playbackDevices.value, ...response.data.items];
        }
        playbackDevicePages.value = response.data.pages || 1;
        playbackDeviceHasMore.value = playbackDevicePage.value < playbackDevicePages.value;
        if (playbackDeviceHasMore.value) {
          playbackDevicePage.value += 1;
        }
      } else {
        if (reset) playbackDevices.value = [];
      }
    } catch (e) {
      console.error('Fetch playback devices failed:', e);
      if (reset) playbackDevices.value = [];
    } finally {
      playbackDeviceLoading.value = false;
    }
  }

  async function loadMorePlaybackDevices() {
    if (!playbackDeviceLoading.value && playbackDeviceHasMore.value) {
      await fetchPlaybackDevices(false);
    }
  }

  async function fetchTranslationDirections() {
    try {
      const response = await audiosApi.getDirections() as any;
      const directions = response.items || response.data?.items || response.data || [];
      if (Array.isArray(directions)) {
        translationDirections.value = directions.map(dir => ({
          id: dir.id,
          name: dir.name || `${dir.sourceLanguage} -> ${dir.targetLanguage}`,
          sourceLanguage: dir.sourceLanguage,
          targetLanguage: dir.targetLanguage,
          description: dir.description
        }));
      } else {
        translationDirections.value = [];
      }
    } catch (e) {
      console.error('Fetch translation directions failed:', e);
      translationDirections.value = [];
    }
  }

  async function fetchAlgorithmOptions() {
    try {
      const response = await fetch('/api/v1/algorithm/options');
      const result = await response.json();
      if (result.success && result.data && result.data.algorithms) {
        algorithmOptions.value = result.data.algorithms.map((a: any) => ({
          value: a.value,
          name: a.name
        }));
      } else {
        algorithmOptions.value = [];
      }
    } catch (e) {
      console.error('Fetch algorithm options failed:', e);
      algorithmOptions.value = [];
    }
  }

  const deviceList = ref<{ value: string | number; name: string }[]>([]);
  
  async function fetchDevices() {
    try {
      const response = await devicesApi.getAll({ per_page: 100 });
      if (response && response.items) {
        deviceList.value = response.items.map((d: any) => ({
          value: d.id,
          name: d.name
        }));
      }
    } catch (e) {
      console.error('Fetch devices failed:', e);
      deviceList.value = [];
    }
  }

  function switchView(mode: 'list' | 'folder') {
    viewMode.value = mode;
    if (mode === 'folder') {
      fetchFolderTree();
    }
  }

  function applyFilters() {
    currentPage.value = 1;
    fetchAudios();
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
    fetchAudios();
  }

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

  const selectAllAcrossPages = ref(false);

  function selectCurrentPage() {
    selectedAudios.value = audioList.value.map(a => a.id);
    showSelectAllOptions.value = false;
    selectAllAcrossPages.value = false;
  }

  async function selectAllPages() {
    selectAllAcrossPages.value = true;
    showSelectAllOptions.value = false;
    loading.value = true;
    
    // 保存当前状态
    const originalPage = currentPage.value;
    const originalSelected = [...selectedAudios.value];
    
    try {
      const normalizedSampleRate =
        filters.value.sampleRate === 'all' ? undefined : (normalizeSampleRate(filters.value.sampleRate) ?? filters.value.sampleRate);
      // 构建与fetchAudios相同的过滤参数
      const params : AudioQueryParams = {
        page: 1,
        perPage: 10000,
        keyword: searchQuery.value || undefined,
        audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
        format: filters.value.format === 'all' ? undefined : filters.value.format,
        sampleRate: normalizedSampleRate,
        duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
        direction: filters.value.direction === 'all' ? undefined : filters.value.direction,
        tags: (selectedTags.value.length > 0 && !isAllTagsSelected()) ? selectedTags.value : undefined
      };
      
      try {
        // 方案1：调用后端新增的获取所有音频ID接口（推荐）
      // 后端需要新增GET /audios/ids接口，支持与getAll相同的过滤参数
      const idsParams = { ...params, page: 1, perPage: 10000 };
      const response = await audiosApi.getAllIds(idsParams, { unwrapResponse: false }) as APIResponse<any>;
      
      if (response.success && response.data) {
        selectedAudios.value = response.data.ids || response.data || [];
      } else {
        throw new Error('Failed to get all audio IDs');
      }
      } catch (error) {
        console.error('Failed to call getAllIds, falling back to pagination:', error);
        
        // 方案2：优化的分页获取方式
        const allSelectedIds = new Set<string | number>();
        let currentPageNum = 1;
        let hasMorePages = true;
        
        // 使用较大的pageSize减少请求次数
        const originalPageSize = pageSize.value;
        pageSize.value = 100; // 一次请求100条记录
        
        while (hasMorePages) {
          // 直接调用API获取数据，避免触发fetchAudios的副作用
          const response = await audiosApi.getAll({ ...params, page: currentPageNum, perPage: pageSize.value }, { unwrapResponse: false }) as APIResponse<any>;
          
          if (response.success && response.data) {
            let items : AudioInfo[] = [];
            if (Array.isArray(response.data)) {
              items = response.data;
            } else if (response.data.items) {
              items = response.data.items as AudioInfo[];
            } else if (response.data.data) {
              items = response.data.data as AudioInfo[];
            }
            
            // 添加当前页所有音频ID
            items.forEach(audio => {
              allSelectedIds.add(audio.id);
            });
            
            // 检查是否还有下一页
            if (items.length < pageSize.value) {
              hasMorePages = false;
            } else {
              currentPageNum++;
            }
          } else {
            hasMorePages = false;
          }
        }
        
        // 恢复原始pageSize
        pageSize.value = originalPageSize;
        
        // 更新选中的音频ID
        selectedAudios.value = Array.from(allSelectedIds);
      }
    } catch (error) {
      console.error('Failed to select all pages:', error);
      // 恢复原始状态
      selectedAudios.value = originalSelected;
      selectAllAcrossPages.value = false;
    } finally {
      // 恢复到原始页面
      currentPage.value = originalPage;
      await fetchAudios();
      loading.value = false;
    }
  }

  watch(() => currentPage.value, () => {
    if (selectAllAcrossPages.value) {
      const currentPageIds = audioList.value.map(a => a.id);
      currentPageIds.forEach(id => {
        if (!selectedAudios.value.includes(id)) {
          selectedAudios.value.push(id);
        }
      });
    }
  });

  async function openUploadModal() {
    if (isOpeningUploadModal) return;
    isOpeningUploadModal = true;
    try {
    await fetchPlaybackDevices();
    await fetchTranslationDirections();
    await fetchAlgorithmOptions();
    await fetchDevices();
    
    modalManager.open(MODAL_TYPES.AUDIO_IMPORT, {
      title: '上传音频',
      deviceOptions: deviceList.value,
      algorithmOptions: algorithmOptions.value,
      uploadOptions: [
        { 
          key: 'audioType', 
          label: '音频类型', 
          type: 'radio', 
          options: [
            { label: '干声', value: 'dry' },
            { label: '噪声', value: 'noise' },
            { label: '提示词', value: 'prompt' },
            { label: '混合', value: 'mixed' }
          ], 
          defaultValue: uploadOptions.audioType 
        },
        { 
          key: 'createTestCase', 
          label: '生成测试用例', 
          type: 'boolean', 
          defaultValue: uploadOptions.createTestCase 
        },
        { 
          key: 'algorithmType', 
          label: '算法类型', 
          type: 'select', 
          options: [
            { label: '请选择算法', value: '' },
            ...(Array.isArray(algorithmOptions.value) ? algorithmOptions.value : []).map(a => ({ label: a.name, value: a.value }))
          ],
          defaultValue: uploadOptions.algorithmType 
        },
        { 
          key: 'translationDirectionId', 
          label: '翻译方向', 
          type: 'select', 
          options: (Array.isArray(translationDirections.value) ? translationDirections.value : []).map(d => ({ label: d.name, value: d.id })),
          defaultValue: uploadOptions.translationDirectionId 
        },
        { 
          key: 'testTypes', 
          label: '测试类型', 
          type: 'checkbox', 
          options: [
            { label: 'API测试', value: 'api' },
            { label: 'E2E测试', value: 'e2e' }
          ], 
          defaultValue: uploadOptions.testTypes 
        },
        {
          key: 'dimensions',
          label: '评估维度',
          type: 'dimensions',
          defaultValue: uploadOptions.dimensions
        },
        { 
          key: 'playbackDeviceId', 
          label: '播放设备', 
          type: 'select', 
          options: (Array.isArray(playbackDevices.value) ? playbackDevices.value : []).map(d => ({ label: d.name, value: d.id })),
          defaultValue: uploadOptions.playbackDeviceId 
        },
        { 
          key: 'defaultSpl', 
          label: '默认声压级(SPL)', 
          type: 'number', 
          min: 30, 
          max: 120, 
          step: 0.1, 
          defaultValue: uploadOptions.spl 
        },
        { 
          key: 'groupNameType', 
          label: '用例分组', 
          type: 'radio', 
          options: [
            { label: '根目录', value: 'root' },
            { label: '文件夹名', value: 'folder' },
            { label: '自定义', value: 'custom' }
          ], 
          defaultValue: uploadOptions.groupNameType 
        },
        { 
          key: 'customGroupName', 
          label: '自定义分组名称', 
          type: 'text', 
          placeholder: '请输入分组名称', 
          defaultValue: uploadOptions.customGroupName 
        },
        { 
          key: 'inheritTags',
          label: '继承音频标签',
          type: 'boolean',
          defaultValue: uploadOptions.inheritTags
        }
      ],
      supportedFormats: ['wav', 'mp3', 'm4a', 'flac'],
      acceptedFileTypes: '.wav,.mp3,.m4a,.flac',
      maxFileSize: 100 * 1024 * 1024,
      multiple: true,
      onConfirm: async (data: any) => {
        if (data.files && data.files.length > 0) {
          const options = (data && typeof data === 'object' && data.options && typeof data.options === 'object')
            ? data.options
            : data;

          if (options?.audioType !== undefined) uploadOptions.audioType = options.audioType;
          if (options?.createTestCase !== undefined) uploadOptions.createTestCase = options.createTestCase;
          if (data?.tags !== undefined) uploadOptions.tags = data.tags;
          if (options?.testTypes !== undefined) uploadOptions.testTypes = options.testTypes;
          if (options?.playbackDeviceId !== undefined) uploadOptions.playbackDeviceId = options.playbackDeviceId;
          if (options?.defaultSpl !== undefined) uploadOptions.spl = options.defaultSpl;
          if (options?.groupNameType !== undefined) uploadOptions.groupNameType = options.groupNameType;
          if (options?.customGroupName !== undefined) uploadOptions.customGroupName = options.customGroupName;
          if (options?.translationDirectionId !== undefined) uploadOptions.translationDirectionId = options.translationDirectionId;
          if (options?.inheritTags !== undefined) uploadOptions.inheritTags = options.inheritTags;
          if (options?.dimensions !== undefined) uploadOptions.dimensions = options.dimensions;
          if (options?.noiseAudioId !== undefined) uploadOptions.noiseAudioId = options.noiseAudioId;
          if (options?.noiseSpl !== undefined) uploadOptions.noiseSpl = options.noiseSpl;
          if (options?.algorithmType !== undefined) uploadOptions.algorithmType = options.algorithmType;
          if (options?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = options.algorithmRelations;
          if (options?.algorithmParams !== undefined) uploadOptions.algorithmParams = options.algorithmParams;
          if (data?.algorithmParams !== undefined) uploadOptions.algorithmParams = data.algorithmParams;
          if (data?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = data.algorithmRelations;
          
          selectedFilesForUpload.value = data.files;
          await startUploadProcess(data.files);
        }
      }
    });
    } finally {
      isOpeningUploadModal = false;
    }
  }

  function closeModal(modalId?: string) {
    if (modalId === 'convertAudioModal') {
      showConvertModal.value = false;
    } else {
      modalManager.closeAll();
    }
  }

  async function pickFiles() {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = 'audio/*';
    input.onchange = async (e: any) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        selectedFilesForUpload.value = Array.from(files);
        await startUploadProcess(selectedFilesForUpload.value);
      }
    };
    input.click();
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      selectedFilesForUpload.value = Array.from(files);
      await startUploadProcess(selectedFilesForUpload.value);
    }
  }

  async function startUploadProcess(files: any[], folderGroupMappings?: Record<string, string>) {
    if (files.length === 0) return;

    uploadStatus.value = 'preparing';
    uploadProgress.value = 1;
    abortController = new AbortController();

    if (typeof window !== 'undefined') {
      await new Promise(resolve => requestAnimationFrame(resolve));
    }

    try {
      const initResponse = await audiosApi.initUpload({ 
        signal: abortController.signal,
        unwrapResponse: false 
      }) as APIResponse<{ taskId: string }>;
      
      let taskId = '';
      if (initResponse.data?.taskId) {
        taskId = initResponse.data.taskId;
      }
      
      if (!taskId) {
        throw new Error(initResponse.message || 'Failed to initialize upload task');
      }

      const fileData = [];
      const preparedFiles : AudioUploadFile[] = [];

      for (const item of files) {
        const file = item.file || item;
        const asrText = item.asrText || '';
        const translations = item.translations || [];

        const md5 = await calculateMd5(file);
        const fileId = `f_${Math.random().toString(36).substring(2, 11)}`;
        
        let folderGroupName = '';
        if (folderGroupMappings) {
          const relativePath = (file as any).webkitRelativePath || '';
          if (relativePath) {
            const rootFolder = relativePath.split('/')[0];
            folderGroupName = folderGroupMappings[rootFolder] || '';
          }
        }

        preparedFiles.push({
          id: fileId,
          fileId,
          file,
          name: file.name,
          size: file.size,
          md5,
          status: 'pending',
          progress: 0,
          uploadedSize: 0,
          folderGroupName,
          asrText: asrText,
          translations,
          annotations: item.annotations || [],
          tags: item.tags || []
        });
        fileData.push({
          name: file.name,
          size: file.size,
          md5,
          relativePath: (file as any).webkitRelativePath || ''
        });
      }

      const regResponse = await audiosApi.registerUploadFiles(taskId, fileData, { 
        signal: abortController.signal,
        unwrapResponse: false
      }) as APIResponse<{ files: any[] }>;
      
      let registeredFiles : any[] = [];
      if (regResponse.data?.files) {
        registeredFiles = regResponse.data.files;
      } else {
        throw new Error(regResponse.message || 'Failed to register files');
      }

      const tasks : AudioUploadFile[] = preparedFiles.map((pf, idx) => {
        const reg = registeredFiles[idx];
        if (!reg) {
          console.warn(`No registration found for file at index ${idx}: ${pf.name}`);
          return {...pf, status: 'failed', error: 'Registration failed'} as AudioUploadFile;
        }
        return {...pf, fileId: reg.fileId, totalChunks: reg.totalChunks, chunkSize: reg.chunkSize, uploadedChunks: [], status: reg.status || 'pending', progress: reg.status === 'completed' ? 100 : 0, uploadedSize: reg.status === 'completed' ? pf.size : 0, asrText: pf.asrText, translations: pf.translations};
      });

      const supportedAudioExts = ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg'];
      const audioFiles = files.filter(item => {
        const file = item.file || item;
        const ext = file.name?.split('.').pop()?.toLowerCase() || '';
        return supportedAudioExts.includes(ext);
      });

      const task : AudioUploadTask = {id: taskId, status: 'uploading', progress: 0, totalFiles: audioFiles.length, completedFiles: tasks.filter(f => f.status === 'completed').length, failedFiles: tasks.filter(f => f.status === 'failed').length, totalSize: tasks.reduce((sum, f) => sum + f.size, 0), uploadedSize: tasks.reduce((sum, f) => sum + (f.uploadedSize || 0), 0), files: tasks, options: { ...uploadOptions},
        startTime: new Date().toISOString()
      };

      currentTask.value = task;
      saveLocalTask(task);
      uploadStatus.value = 'uploading';
      updateOverallProgress();

      for (const fileTask of tasks) {
        if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;
        
        // 秒传的文件 total_chunks = 0，仍然需要处理测试用例创建
        if (fileTask.status === 'completed' && fileTask.totalChunks === 0) {
          fileTask.status = 'uploading';
          currentUploadingFile.value = fileTask.name;
          
          try {
            // 秒传时也需要调用 merge 来处理测试用例创建
            await processMergeForExistingFile(taskId, fileTask, uploadOptions);
            fileTask.status = 'completed';
            task.completedFiles = (task.completedFiles || 0) + 1;
            saveLocalTask(task);
          } catch (err) {
            console.error(`处理已存在文件失败 ${fileTask.name}:`, err);
            fileTask.status = 'failed';
            fileTask.error = err instanceof Error ? err.message : String(err);
            task.failedFiles = (task.failedFiles || 0) + 1;
            saveLocalTask(task);
          }
          updateOverallProgress();
          continue;
        }
        
        if (fileTask.status === 'completed' || fileTask.status === 'failed') {
          continue;
        }

        fileTask.status = 'uploading';
        currentUploadingFile.value = fileTask.name;
        
        try {
          await uploadFileChunks(taskId, fileTask, uploadOptions);
          fileTask.status = 'completed';
          fileTask.progress = 100;
          task.completedFiles = (task.completedFiles || 0) + 1;
          saveLocalTask(task);
        } catch (err) {
          console.error(`Upload failed for ${fileTask.name}:`, err);
          fileTask.status = 'failed';
          fileTask.error = err instanceof Error ? err.message : String(err);
          task.failedFiles = (task.failedFiles || 0) + 1;
          saveLocalTask(task);
        }
        updateOverallProgress();
      }

      uploadStatus.value = (task.failedFiles || 0) > 0 ? 'failed' : 'completed';
      task.status = uploadStatus.value;
      task.endTime = new Date().toISOString();
      saveLocalTask(task);
      
      fetchAudios();

    } catch (err: any) {
      if (err.name === 'AbortError') {
        uploadStatus.value = 'stopped';
      } else {
        console.error('Upload process failed:', err);
        uploadStatus.value = 'failed';
      }
    } finally {
      abortController = null;
      currentUploadingFile.value = null;
    }
  }

  async function processMergeForExistingFile(taskId: string, fileTask: AudioUploadFile, options: any = uploadOptions) {
    let normalizedAlgorithmParams = options.algorithmParams;
    if (normalizedAlgorithmParams && typeof normalizedAlgorithmParams === 'object' && !Array.isArray(normalizedAlgorithmParams)) {
      normalizedAlgorithmParams = Object.entries(normalizedAlgorithmParams).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }
    const mergeResponse = await audiosApi.mergeChunks(fileTask.fileId, taskId, {
      audioType: options.audioType,
      createTestCase: options.createTestCase,
      tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
      description: options.description,
      testTypes: options.testTypes,
      playbackDeviceId: options.playbackDeviceId,
      spl: options.spl,
      groupNameType: options.groupNameType,
      customGroupName: fileTask.folderGroupName || options.customGroupName,
      translationDirectionId: options.translationDirectionId,
      inheritTags: options.inheritTags,
      dimensions: options.createTestCase ? options.dimensions : undefined,
      noiseAudioId: options.noiseAudioId,
      noiseSpl: options.noiseSpl,
      asrText: fileTask.asrText || '',
      translations: fileTask.translations || [],
      annotations: fileTask.annotations || [],
      algorithmType: options.algorithmType,
      algorithmRelations: options.algorithmRelations,
      algorithmParams: normalizedAlgorithmParams || []
    }, { 
      signal: abortController?.signal,
      unwrapResponse: false
    }) as APIResponse<{ audioId: string | number }>;

    if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
      throw new Error(mergeResponse.message || 'Failed to process existing file');
    }
    
    fileTask.audioId = mergeResponse.data?.audioId;
  }

  async function uploadFileChunks(taskId: string, fileTask: AudioUploadFile, options: any = uploadOptions) {
    let normalizedAlgorithmParams = options.algorithmParams;
    if (normalizedAlgorithmParams && typeof normalizedAlgorithmParams === 'object' && !Array.isArray(normalizedAlgorithmParams)) {
      normalizedAlgorithmParams = Object.entries(normalizedAlgorithmParams).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }
    const chunkSize = fileTask.chunkSize || 10 * 1024 * 1024;
    const totalChunks = fileTask.totalChunks || Math.ceil(fileTask.size / chunkSize);
    
    for (let i = 0; i < totalChunks; i++) {
      if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') {
        fileTask.status = (uploadStatus.value as string) === 'paused' ? 'paused' : 'stopped';
        throw new Error(`Upload ${fileTask.status}`);
      }

      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, fileTask.size);
      const chunk = fileTask.file.slice(start, end);
      
      const formData = new FormData();
      formData.append('chunk', chunk);
      formData.append('task_id', taskId);
      formData.append('file_id', fileTask.fileId);
      formData.append('chunk_index', i.toString());
      formData.append('total_chunks', totalChunks.toString());
      formData.append('md5', fileTask.md5 || '');

      await audiosApi.uploadChunk(formData, { signal: abortController?.signal });
      
      fileTask.uploadedSize = end;
      fileTask.progress = Math.round((end / fileTask.size) * 100);
      updateOverallProgress();
    }

    const mergeResponse = await audiosApi.mergeChunks(fileTask.fileId, taskId, {
      audioType: options.audioType,
      createTestCase: options.createTestCase,
      tags: fileTask.tags && fileTask.tags.length > 0 ? fileTask.tags : options.tags,
      description: options.description,
      testTypes: options.testTypes,
      playbackDeviceId: options.playbackDeviceId,
      spl: options.spl,
      groupNameType: options.groupNameType,
      customGroupName: fileTask.folderGroupName || options.customGroupName,
      translationDirectionId: options.translationDirectionId,
      inheritTags: options.inheritTags,
      dimensions: options.createTestCase ? options.dimensions : undefined,
      noiseAudioId: options.noiseAudioId,
      noiseSpl: options.noiseSpl,
      asrText: fileTask.asrText || '',
      translations: fileTask.translations || [],
      annotations: fileTask.annotations || [],
      algorithmType: options.algorithmType,
      algorithmRelations: options.algorithmRelations,
      algorithmParams: normalizedAlgorithmParams || []
    }, { 
      signal: abortController?.signal,
      unwrapResponse: false
    }) as APIResponse<{ audioId: string | number }>;

    if (mergeResponse.code !== undefined && mergeResponse.code !== null && mergeResponse.code !== 0 && mergeResponse.code !== 200 && mergeResponse.code !== 201) {
      throw new Error(mergeResponse.message || 'Failed to merge chunks');
    }
    
    fileTask.audioId = mergeResponse.data?.audioId;
  }

  function updateOverallProgress() {
    if (!currentTask.value) return;
    const totalSize = currentTask.value.totalSize || 0;
    const uploadedSize = currentTask.value.files.reduce((sum, f) => sum + (f.uploadedSize || 0), 0);
    uploadProgress.value = totalSize > 0 ? Math.round((uploadedSize / totalSize) * 100) : 0;
    currentTask.value.uploadedSize = uploadedSize;
  }

  async function batchDelete() {
    if (selectedAudios.value.length === 0) return;
    
    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '批量删除',
        content: `确定要删除选中的 ${selectedAudios.value.length} 个音频吗？此操作不可撤销。`,
        danger: true
      });

      if (confirmed) {
        try {
          const response = await audiosApi.batchAction('delete', selectedAudios.value, {}, { unwrapResponse: false }) as APIResponse<any>;
          const hasError = response.message && (response.message.includes('失败') || response.message.includes('没有可删除') || response.message.includes('被其他资源引用') || response.message.includes('禁止删除'));
          if (response.success && !hasError) {
            selectedAudios.value = [];
            fetchAudios();
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '删除成功',
              content: response.message || `成功删除音频`,
              danger: false
            });
          } else {
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '删除失败',
              content: response.message || '部分文件删除失败',
              danger: true
            });
          }
        } catch (e: any) {
          console.error('Batch delete failed:', e);
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除失败',
            content: e.message || '批量删除失败，请重试',
            danger: true
          });
        }
      }
  }

  async function batchExport() {
    if (selectedAudios.value.length === 0) return;
    try {
      const response = await audiosApi.batchAction('export', selectedAudios.value, {}, { responseType: 'blob' }) as any;
      const url = window.URL.createObjectURL(new Blob([response]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audios_export_${new Date().getTime()}.zip`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Batch export failed:', e);
    }
  }

  function previewAudio(audioOrId: AudioInfo | string | number) {
    let audio : AudioInfo | undefined;
    if (typeof audioOrId === 'object') {
      audio = audioOrId;
    } else {
      audio = audioList.value.find(a => a.id === audioOrId);
    }

    if (audio) {
      audioTitle.value = audio.name;
      currentPreviewAudioId.value = audio.id;
      currentPreviewAudioType.value = audio.audioType || 'dry';
      showAudioPlayerModal.value = true;
    }
  }

  function editMetadata(audioOrId: AudioInfo | string | number) {
    let audio : AudioInfo | undefined;
    if (typeof audioOrId === 'object') {
      audio = audioOrId;
    } else {
      audio = audioList.value.find(a => a.id === audioOrId);
    }
    
    if (audio) {
      let tagsArray: string[] = [];
      if (Array.isArray(audio.tags)) {
        tagsArray = audio.tags;
      } else if (audio.tags) {
        const tagsString = String(audio.tags);
        if (tagsString) {
          tagsArray = tagsString.split(',').map((tag: string) => tag.trim());
        }
      }
      
      const metadata = {
        id: audio.id,
        fileName: audio.name || '',
        category: audio.filepath || audio.filePath || audio.file_path || '',
        audioType: audio.audioType || 'dry',
        asrText: audio.asrText || '',
        tags: tagsArray.join(','),
        format: audio.format || '',
        duration: audio.duration || 0,
        sourceLanguage: audio.sourceLanguage || '',
        size: audio.size || 0,
        translations: audio.translations || [],
        annotations: audio.annotations || []
      };
      
      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: '编辑元数据',
        width: '1200px',
        data: metadata,
        fields: [
          { key: 'fileName', label: '文件名' },
          { key: 'audioType', label: '音频类型' },
          { key: 'tags', label: '标签' },
          { key: 'format', label: '音频格式' },
          { key: 'duration', label: '时长(秒)' },
          { key: 'size', label: '文件大小' },
          { key: 'sourceLanguage', label: '源语言' },
          { key: 'asrText', label: 'ASR文本' },
          { key: 'translations', label: '翻译语向' },
          { key: 'annotations', label: '标注' }
        ]
      }).then(async (payload: any) => {
        if (payload && payload.action === 'save') {
          const editedData = payload.data;
          try {
            const response = await audiosApi.updateMetadata(editedData.id, editedData, { unwrapResponse: false }) as any;
            if (response.success) {
              fetchAudios();
              await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
                title: '保存成功',
                content: '元数据保存成功',
                danger: false
              });
            } else {
              await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
                title: '保存失败',
                content: response.message || '保存失败',
                danger: true
              });
            }
          } catch (err: any) {
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '保存失败',
              content: err.message || String(err),
              danger: true
            });
          }
        }
      });
    }
  }

  async function downloadAudio(audioOrId: AudioInfo | string | number) {
    let id : string | number;
    let name : string;
    
    if (typeof audioOrId === 'object') {
      id = audioOrId.id;
      name = audioOrId.name;
    } else {
      id = audioOrId;
      const audio = audioList.value.find(a => a.id === id);
      name = audio ? audio.name : `audio_${id}.wav`;
    }

    try {
      const response = await audiosApi.stream(id, { responseType: 'blob' }) as any;
      const url = window.URL.createObjectURL(new Blob([response]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', name);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Download audio failed:', e);
    }
  }

  async function deleteAudio(id: string | number) {
    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '删除音频',
        content: '确定要删除这个音频吗？',
        danger: true
      });

      if (confirmed) {
        try {
          const response = await audiosApi.delete(id, { unwrapResponse: false }) as APIResponse;
          const hasError = response.message && (response.message.includes('失败') || response.message.includes('没有可删除') || response.message.includes('被其他资源引用') || response.message.includes('禁止删除'));
          if (response.success && !hasError) {
            fetchAudios();
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '删除成功',
              content: '音频删除成功',
              danger: false
            });
          } else {
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '删除失败',
              content: response.message || '音频删除失败',
              danger: true
            });
          }
        } catch (e: any) {
          console.error('Delete audio failed:', e);
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除失败',
            content: e.message || '音频删除失败，请重试',
            danger: true
          });
        }
      }
  }

  function shareAudio(audioOrId: AudioInfo | string | number) {
    let id : string | number;
    if (typeof audioOrId === 'object') {
      id = audioOrId.id;
    } else {
      id = audioOrId;
    }
    console.log('Share audio:', id);
  }

  function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--;
      fetchAudios();
    }
  }

  function nextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
      fetchAudios();
    }
  }

  function handleGoToPage(page: number) {
    currentPage.value = page;
    fetchAudios();
  }

  function handlePageSizeChange(size: number) {
    pageSize.value = size;
    currentPage.value = 1;
    fetchAudios();
  }

  function convertAudio(audioOrEvent?: AudioInfo | any) {
    if (audioOrEvent && (audioOrEvent as AudioInfo).id) {
      const audio = audioOrEvent as AudioInfo;
       convertAudioInfo.id = audio.id;
       convertAudioInfo.name = audio.name;
       convertAudioInfo.originalFileName = audio.filename || '';
       convertAudioInfo.originalFormat = audio.format || '';
       convertAudioInfo.originalSampleRate = (audio.sampleRate || '').toString();
       convertAudioInfo.originalChannels = (audio.channels || '').toString();
       convertAudioInfo.originalBitDepth = '';
       
       showConvertModal.value = true;
    } else {
      console.log('Starting conversion for:', convertAudioInfo.id);
      showConvertModal.value = false;
    }
  }

  function resetAllStates() {
    selectedAudios.value = [];
    resetFilters();
  }

  function initModalWatchers() {
  }

  function toggleFolder(path: string) {
    if (expandedFolders.value.has(path)) {
      expandedFolders.value.delete(path);
    } else {
      expandedFolders.value.add(path);
    }
  }

  function closeDeleteResultModal() {
    showDeleteResultModal.value = false;
  }

  const closeActiveModal = () => {
    showConvertModal.value = false;
    showAudioPlayerModal.value = false;
    showDeleteResultModal.value = false;
    modalManager.closeAll?.();
  };

  const pauseUploadTask = (taskId: string) => {
    if (currentTask.value?.id === taskId) {
      uploadStatus.value = 'paused';
      currentTask.value.status = 'paused';
      saveLocalTask(currentTask.value);
      abortController?.abort();
    }
  };

  const resumeUploadTask = async (taskId: string, isRetry = false) => {
    const task = uploadTasks.value.find(t => t.id === taskId);
    if (task) {
      currentTask.value = task;
      uploadStatus.value = 'uploading';
      task.status = 'uploading';
      const taskOptions = task.options || uploadOptions;
      
      for (const fileTask of task.files) {
        if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;
        if (fileTask.status !== 'completed') {
          try {
            fileTask.status = 'uploading';
            currentUploadingFile.value = fileTask.name;
            await uploadFileChunks(taskId, fileTask, taskOptions);
            fileTask.status = 'completed';
            fileTask.progress = 100;
            saveLocalTask(task);
          } catch (err) {
            fileTask.status = 'failed';
            fileTask.error = err instanceof Error ? err.message : String(err);
            saveLocalTask(task);
          }
          updateOverallProgress();
        }
      }
      
      task.completedFiles = task.files.filter(f => f.status === 'completed').length;
      task.failedFiles = task.files.filter(f => f.status === 'failed').length;
      
      uploadStatus.value = task.failedFiles > 0 ? 'failed' : 'completed';
      task.status = uploadStatus.value;
      task.endTime = new Date().toISOString();
      saveLocalTask(task);
      
      isRetryingFailed.value = false;
      fetchAudios();
    }
  };

  const retryFailedFiles = async (taskId: string, autoSelectFiles = false) => {
    const task = uploadTasks.value.find(t => t.id === taskId);
    if (task) {
      isRetryingFailed.value = true;
      const previousFailedFiles = task.files.filter(f => f.status === 'failed');
      const fileData = [];
      let canReRegister = true;
      let needReSelectFiles = false;
      let failedFileNames: string[] = [];
      
      for (const fileTask of previousFailedFiles) {
        failedFileNames.push(fileTask.name);
        if (fileTask.file && typeof fileTask.file.slice === 'function') {
          try {
            const md5 = await calculateMd5(fileTask.file);
            fileData.push({
              name: fileTask.name,
              size: fileTask.size,
              md5
            });
          } catch (md5Err) {
            console.error('计算MD5失败:', fileTask.name, md5Err);
            canReRegister = false;
            needReSelectFiles = true;
          }
        } else {
          canReRegister = false;
          needReSelectFiles = true;
        }
      }
      
      if (needReSelectFiles || autoSelectFiles) {
        setTimeout(async () => {
          const input = document.createElement('input');
          input.type = 'file';
          input.multiple = true;
          input.accept = 'audio/*,.wav,.mp3,.m4a,.flac';
          input.onchange = async (e: any) => {
            const files = e.target.files;
            if (files && files.length > 0) {
              const selectedFiles = Array.from(files);
              
              const newFileTasks: typeof task.files = [];
              
              for (const file of selectedFiles) {
                if (failedFileNames.includes(file.name)) {
                  const md5 = await calculateMd5(file);
                  const fileId = `f_${Math.random().toString(36).substring(2, 11)}`;
                  
                  newFileTasks.push({
                    id: fileId,
                    fileId,
                    file,
                    name: file.name,
                    size: file.size,
                    md5,
                    status: 'pending',
                    progress: 0,
                    uploadedSize: 0,
                    uploadedChunks: []
                  });
                }
              }
              
              if (newFileTasks.length > 0) {
                task.files = task.files.filter(f => f.status !== 'failed');
                task.files.push(...newFileTasks);
                task.failedFiles = 0;
                task.completedFiles = task.files.filter(f => f.status === 'completed').length;
                task.totalFiles = task.files.length;
                saveLocalTask(task);
                
                const newFileData = newFileTasks.map(ft => ({
                  name: ft.name,
                  size: ft.size,
                  md5: ft.md5
                }));
                
                try {
                  const regResponse = await audiosApi.registerUploadFiles(taskId, newFileData, { 
                    signal: abortController?.signal,
                    unwrapResponse: false 
                  }) as APIResponse<{ files: any[] }>;
                  
                  if (regResponse.data?.files) {
                    newFileTasks.forEach((ft, idx) => {
                      const reg = regResponse.data.files[idx];
                      if (reg) {
                        ft.fileId = reg.fileId;
                        ft.totalChunks = reg.totalChunks;
                        ft.chunkSize = reg.chunkSize;
                      }
                    });
                  }
                } catch (regErr) {
                  console.error('重新注册文件失败:', regErr);
                }
                
                await resumeUploadTask(taskId);
              } else {
                await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
                  title: '无法重试',
                  content: '未找到与失败文件匹配的文件，请确保选择相同的文件进行重试。',
                  danger: true
                });
                isRetryingFailed.value = false;
              }
            } else {
              isRetryingFailed.value = false;
            }
          };
          input.click();
        }, 100);
        return;
      }
      
      if (canReRegister && fileData.length > 0) {
        try {
          const regResponse = await audiosApi.registerUploadFiles(taskId, fileData, { 
            signal: abortController?.signal,
            unwrapResponse: false 
          }) as APIResponse<{ files: any[] }>;
          
          if (regResponse.data?.files) {
            previousFailedFiles.forEach((fileTask, idx) => {
              const reg = regResponse.data.files[idx];
              if (reg) {
                fileTask.fileId = reg.fileId;
                fileTask.totalChunks = reg.totalChunks;
                fileTask.chunkSize = reg.chunkSize;
                fileTask.uploadedChunks = [];
                fileTask.progress = 0;
                fileTask.uploadedSize = 0;
                fileTask.status = 'pending';
                fileTask.error = undefined;
              }
            });
          }
        } catch (regErr) {
          console.error('重新注册文件失败:', regErr);
        }
      }
      
      task.files.forEach(f => {
        if (f.status === 'failed') f.status = 'pending';
      });
      
      task.failedFiles = 0;
      task.completedFiles = 0;
      saveLocalTask(task);
      
      await resumeUploadTask(taskId);
    }
  };

  const removeLocalTask = (taskId: string) => {
    const tasks = getLocalTasks().filter(t => t.id !== taskId);
    localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
    uploadTasks.value = tasks;
    if (currentTask.value?.id === taskId) {
      currentTask.value = null;
      uploadStatus.value = 'idle';
      uploadProgress.value = 0;
    }
  };

  const dismissTask = (taskId: string) => {
    removeLocalTask(taskId);
    fetchAudios();
  };

  const checkAndResumeTasks = () => {
    const tasks = getLocalTasks();
    const unfinished = tasks.find(t => t.status === 'uploading' || t.status === 'paused');
    if (unfinished && unfinished.id) {
      resumeUploadTask(unfinished.id);
    }
  };

  async function batchImportFromFolder() {
    if (isOpeningFolderImport) return;
    isOpeningFolderImport = true;
    try {
    await fetchPlaybackDevices();
    await fetchTranslationDirections();
    await fetchAlgorithmOptions();
    
    modalManager.open(MODAL_TYPES.FOLDER_IMPORT, {
      title: '批量从文件夹导入',
      uploadOptions: [
        { 
          key: 'audioType', 
          label: '音频类型', 
          type: 'radio', 
          options: [
            { label: '干声', value: 'dry' },
            { label: '噪声', value: 'noise' },
            { label: '混合', value: 'mixed' }
          ], 
          defaultValue: uploadOptions.audioType 
        },
        { 
          key: 'createTestCase', 
          label: '生成测试用例', 
          type: 'boolean', 
          defaultValue: uploadOptions.createTestCase 
        },
        { 
          key: 'algorithmType', 
          label: '算法类型', 
          type: 'select', 
          options: [
            { label: '请选择算法', value: '' },
            ...(Array.isArray(algorithmOptions.value) ? algorithmOptions.value : []).map(a => ({ label: a.name, value: a.value }))
          ],
          defaultValue: uploadOptions.algorithmType 
        },
        { 
          key: 'translationDirectionId', 
          label: '翻译方向', 
          type: 'select', 
          options: (Array.isArray(translationDirections.value) ? translationDirections.value : []).map(d => ({ label: d.name, value: d.id })),
          defaultValue: uploadOptions.translationDirectionId 
        },
        { 
          key: 'testTypes', 
          label: '测试类型', 
          type: 'checkbox', 
          options: [
            { label: 'API测试', value: 'api' },
            { label: 'E2E测试', value: 'e2e' }
          ], 
          defaultValue: uploadOptions.testTypes 
        },
        {
          key: 'dimensions',
          label: '评估维度',
          type: 'dimensions',
          defaultValue: uploadOptions.dimensions
        },
        { 
          key: 'playbackDeviceId', 
          label: '播放设备', 
          type: 'select', 
          options: (Array.isArray(playbackDevices.value) ? playbackDevices.value : []).map(d => ({ label: d.name, value: d.id })),
          defaultValue: uploadOptions.playbackDeviceId 
        },
        { 
          key: 'defaultSpl', 
          label: '默认声压级(SPL)', 
          type: 'number', 
          min: 30, 
          max: 120, 
          step: 0.1, 
          defaultValue: uploadOptions.spl 
        },
        { 
          key: 'groupNameType', 
          label: '用例分组', 
          type: 'radio', 
          options: [
            { label: '根目录', value: 'root' },
            { label: '文件夹名', value: 'folder' },
            { label: '自定义', value: 'custom' }
          ], 
          defaultValue: uploadOptions.groupNameType 
        },
        { 
          key: 'customGroupName', 
          label: '自定义分组名称', 
          type: 'text', 
          placeholder: '请输入分组名称', 
          defaultValue: uploadOptions.customGroupName 
        },
        { 
          key: 'inheritTags',
          label: '继承音频标签',
          type: 'boolean',
          defaultValue: uploadOptions.inheritTags
        }
      ],
      supportedFormats: ['wav', 'mp3', 'm4a', 'flac'],
      onConfirm: async (data: any) => {
        if (data.files && data.files.length > 0) {
          const options = (data && typeof data === 'object' && data.config && typeof data.config === 'object')
            ? data.config
            : ((data && typeof data === 'object' && data.options && typeof data.options === 'object') ? data.options : data);

          if (options?.audioType !== undefined) uploadOptions.audioType = options.audioType;
          if (options?.createTestCase !== undefined) uploadOptions.createTestCase = options.createTestCase;
          if (data?.tags !== undefined) uploadOptions.tags = data.tags;
          if (options?.testTypes !== undefined) uploadOptions.testTypes = options.testTypes;
          if (options?.playbackDeviceId !== undefined) uploadOptions.playbackDeviceId = options.playbackDeviceId;
          if (options?.defaultSpl !== undefined) uploadOptions.spl = options.defaultSpl;
          if (options?.groupNameType !== undefined) uploadOptions.groupNameType = options.groupNameType;
          if (options?.customGroupName !== undefined) uploadOptions.customGroupName = options.customGroupName;
          if (options?.translationDirectionId !== undefined) uploadOptions.translationDirectionId = options.translationDirectionId;
          if (options?.inheritTags !== undefined) uploadOptions.inheritTags = options.inheritTags;
          if (options?.dimensions !== undefined) uploadOptions.dimensions = options.dimensions;
          if (options?.noiseAudioId !== undefined) uploadOptions.noiseAudioId = options.noiseAudioId;
          if (options?.noiseSpl !== undefined) uploadOptions.noiseSpl = options.noiseSpl;
          if (options?.algorithmType !== undefined) uploadOptions.algorithmType = options.algorithmType;
          if (options?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = options.algorithmRelations;
          if (options?.algorithmParams !== undefined) uploadOptions.algorithmParams = options.algorithmParams;
          if (data?.algorithmRelations !== undefined) uploadOptions.algorithmRelations = data.algorithmRelations;
          
          selectedFilesForUpload.value = data.files;
          await startUploadProcess(data.files, data.folderGroupMappings);
        }
      }
    });
    } finally {
      isOpeningFolderImport = false;
    }
  }

  onMounted(() => {
    // 先获取所有标签，再获取音频列表
    fetchAllTags().then(() => {
      fetchAudios();
    });
    fetchPlaybackDevices();
    fetchTranslationDirections();
    uploadTasks.value = getLocalTasks();
    checkAndResumeTasks();
    
    // 初始化currentTask，如果有未完成的任务
    const tasks = getLocalTasks();
    const unfinished = tasks.find(t => t.status === 'uploading' || t.status === 'paused' || t.status === 'failed');
    if (unfinished) {
      currentTask.value = unfinished;
      updateOverallProgress();
      if (uploadProgress.value === 0) {
        uploadProgress.value = 1;
      }
    }
    
    initModalWatchers();
  });

  onUnmounted(() => {
    if (uploadStatus.value === 'uploading') {
      abortController?.abort();
    }
  });

  const searchAudios = () => fetchAudios();
  const filterAudios = (newFilters?: any) => {
    if (newFilters) {
      // 更新筛选条件
      if (newFilters.format) filters.value.format = newFilters.format;
      if (newFilters.sampleRate) filters.value.sampleRate = normalizeSampleRate(newFilters.sampleRate) ?? newFilters.sampleRate;
      if (newFilters.duration) filters.value.duration = newFilters.duration;
      if (newFilters.audioType) filters.value.audioType = newFilters.audioType;
      if (newFilters.tags) {
        // 更新选中的标签
        selectedTags.value = newFilters.tags || [];
      }
    }
    fetchAudios();
  };

  return {
    audioList,
    totalAudios,
    loading,
    currentPage,
    pageSize,
    searchTerm,
    searchQuery,
    audioTypeFilter,
    viewMode,
    showConvertModal,
    selectedAudios,
    filters,
    selectedTags,
    tagModes,
    tagModesObject,
    allTags,
    urlImportData,
    convertAudioInfo,
    stats,
    expandedFolders,
    showSelectAllOptions,
    folderImportOptions,
    showDeleteResultModal,
    deleteResult,
    showAudioPlayerModal,
    audioTitle,
    currentPreviewAudioId,
    currentPreviewAudioType,
    playbackDevices,
    playbackDevicePage,
    playbackDevicePages,
    playbackDeviceLoading,
    playbackDeviceHasMore,
    uploadOptions,
    uploadTasks,
    selectedFilesForUpload,
    fileList,
    uploadStatus,
    uploadProgress,
    currentTask,
    currentUploadingFile,
    isRetryingFailed,
    filteredAudios,
    totalPages,
    flattenedFolderTree,
    serverFolderTree,
    folderLoading,
    expandedFolderPaths,
    fetchFolderTree,
    toggleFolderExpand,
    isFolderExpanded,
    fetchAudios,
    searchAudios,
    filterAudios,
    fetchPlaybackDevices,
    loadMorePlaybackDevices,
    switchView,
    applyFilters,
    resetFilters,
    toggleTag,
    toggleSelectAll,
    toggleAudioSelection,
    selectCurrentPage,
    selectAllPages,
    openUploadModal,
    closeModal,
    closeActiveModal,
    pickFiles,
    handleDrop,
    batchDelete,
    batchExport,
    previewAudio,
    editMetadata,
    downloadAudio,
    deleteAudio,
    shareAudio,
    prevPage,
    nextPage,
    handleGoToPage,
    handlePageSizeChange,
    convertAudio,
    resetAllStates,
    initModalWatchers,
    toggleFolder,
    closeDeleteResultModal,
    pathBasename,
    pauseUploadTask,
    resumeUploadTask,
    retryFailedFiles,
    removeLocalTask,
    dismissTask,
    batchImportFromFolder,
    checkAndResumeTasks,
    algorithmOptions,
    fetchAlgorithmOptions,
    deviceList,
    fetchDevices
  };
}
