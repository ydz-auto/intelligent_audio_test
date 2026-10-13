/**
 * INT-275：AudioImport 跨页 autoOpen 上传弹窗断链修复——query 解析与两端契约单测。
 *
 * 缺陷：useTestCaseCard.openImportTestCaseModal（E2E/API 测试页「导入用例」入口）跳转
 *   /AudioImport 时推送 autoOpen/createTestCase/algorithmType 三个 query 参数，
 *   但 V9.7.31 AudioImport.vue / audioImport.ts 全文不读 route.query（零消费者）
 *   → 上传弹窗不自动打开，跨页主流程断链。
 *
 * 修复：onMounted 对齐 V9.7.10 基线（AudioImport.vue:441-450）——解析 query、
 *   预置 uploadOptions、nextTick 打开上传弹窗；参数名收敛到
 *   domain/constants/audioImportQuery.ts，生产者/消费者同源引用防漂移。
 *
 * 锁定口径：
 * - 消费者：autoOpen==='1' 触发；createTestCase==='true' 勾选生成用例；
 *   algorithmType（字符串）预置；autoOpen 缺失/非 '1' 一律不触发（基线严格语义）
 * - 生产者：推送 query 键与 AUDIO_IMPORT_QUERY 常量同源（本次断链根因的防回归锁）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { reactive, ref, computed } from 'vue';
import { TestType } from '@/domain/enums';
import type { AudioUploadOptions } from '@/domain';

// ─── 可变 route.query 与 router.push 捕获（生产者/消费者共用） ───
const routeState = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  pushes: [] as any[],
}));

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeState.query }),
  useRouter: () => ({ push: (loc: any) => routeState.pushes.push(loc) }),
}));

// ─── useAudioImport 协调层替身：uploadOptions 是被测预置目标，须为真 reactive ───
const audioImportState = vi.hoisted(() => ({
  api: null as any,
}));

vi.mock('@/views/AudioImport/audioImport', () => ({
  useAudioImport: () => audioImportState.api,
}));

// ─── 生产者依赖替身（openImportTestCaseModal 仅触 router.push，其余不被调用） ───
vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: { getGroups: vi.fn(async () => ({ items: [] })), getOne: vi.fn(async () => ({})) },
}));
vi.mock('@/composables/device/playbackPort', () => ({
  playbackPort: { getAll: vi.fn(async () => []) },
}));
vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: vi.fn() }),
  getModalManager: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  provideModal: vi.fn(),
}));
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ show: vi.fn(), error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }),
  provideNotification: vi.fn(),
}));

// ─── 子组件浅替身：页面级 query 契约测试不渲染其内部 ───
vi.mock('@/components/common/audio/AudioListComponent.vue', () => ({
  default: { template: '<div class="audio-list-stub" />' },
}));
vi.mock('@/components/common/misc/UploadProgressCard.vue', () => ({
  default: { template: '<div class="upload-progress-stub" />' },
}));
vi.mock('@/components/common/audio/AudioPlayerModal.vue', () => ({
  default: { template: '<div class="audio-player-stub" />' },
}));
vi.mock('@/components/common/modal/BatchAnnotationModal.vue', () => ({
  default: { template: '<div class="batch-annotation-stub" />' },
}));
vi.mock('@/views/AudioImport/ConvertModal.vue', () => ({
  default: { template: '<div class="convert-modal-stub" />' },
}));
vi.mock('@/components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));

import AudioImportView from '@/views/AudioImport/AudioImport.vue';
import { useTestCaseCard } from '@/composables/testCase/useTestCaseCard';
import { AUDIO_IMPORT_QUERY, AUDIO_IMPORT_AUTO_OPEN_VALUE } from '@/domain';

/** uploadOptions 真实默认值（对齐 useAudioUpload.ts 初始 reactive） */
const uploadOptions = reactive<AudioUploadOptions>({
  audioType: 'dry',
  createTestCase: false,
  tags: [],
  testTypes: [TestType.E2E],
  inheritTags: true,
  dimensions: [],
  algorithmType: ''
});

/** useAudioImport 返回形状：覆盖组件解构与模板绑定所需的最小集 */
audioImportState.api = {
  audioList: ref([]),
  viewMode: ref('card'),
  currentPage: ref(1),
  pageSize: ref(50),
  loading: ref(false),
  totalAudios: ref(0),
  searchQuery: ref(''),
  uploadProgress: ref(0),
  showConvertModal: ref(false),
  selectedAudios: ref([]),
  filters: ref({}),
  selectedTags: ref([]),
  tagModes: ref(new Map()),
  tagModesObject: computed(() => ({})),
  allTags: ref([]),
  urlImportData: ref(null),
  convertAudioInfo: ref(null),
  stats: ref({}),
  filteredAudios: ref([]),
  totalPages: ref(0),
  flattenedFolderTree: computed(() => []),
  serverFolderTree: ref(null),
  folderLoading: ref(false),
  expandedFolderPaths: ref([]),
  fetchFolderTree: vi.fn(),
  toggleFolderExpand: vi.fn(),
  isFolderExpanded: vi.fn(() => false),
  loadSubTree: vi.fn(),
  mergeSubTree: vi.fn(),
  expandedFolders: ref([]),
  switchView: vi.fn(),
  applyFilters: vi.fn(),
  resetFilters: vi.fn(),
  searchAudios: vi.fn(),
  filterAudios: vi.fn(),
  toggleTag: vi.fn(),
  toggleSelectAll: vi.fn(),
  toggleAudioSelection: vi.fn(),
  toggleFolderSelection: vi.fn(),
  isFolderAllSelected: vi.fn(() => false),
  isFolderPartialSelected: vi.fn(() => false),
  selectCurrentPage: vi.fn(),
  selectAllPages: vi.fn(),
  showSelectAllOptions: ref(false),
  openUploadModal: vi.fn(),
  closeModal: vi.fn(),
  pickFiles: vi.fn(),
  handleDrop: vi.fn(),
  selectedFilesForUpload: ref([]),
  batchImportFromFolder: vi.fn(),
  batchDelete: vi.fn(),
  batchExport: vi.fn(),
  previewAudio: vi.fn(),
  editMetadata: vi.fn(),
  downloadAudio: vi.fn(),
  deleteAudio: vi.fn(),
  shareAudio: vi.fn(),
  prevPage: vi.fn(),
  nextPage: vi.fn(),
  handleGoToPage: vi.fn(),
  handlePageSizeChange: vi.fn(),
  convertAudio: vi.fn(),
  resetAllStates: vi.fn(),
  fetchAudios: vi.fn(),
  uploadOptions,
  playbackDevices: ref([]),
  fetchPlaybackDevices: vi.fn(),
  folderImportOptions: reactive({}),
  initModalWatchers: vi.fn(),
  uploadTasks: ref([]),
  currentTask: ref(null),
  fileList: ref([]),
  uploadStatus: ref('idle'),
  currentUploadingFile: ref(null),
  isRetryingFailed: ref(false),
  resumeUploadTask: vi.fn(),
  checkAndResumeTasks: vi.fn(),
  removeLocalTask: vi.fn(),
  retryFailedFiles: vi.fn(),
  dismissTask: vi.fn(),
  toggleFolder: vi.fn(),
  pauseUploadTask: vi.fn(),
  showAudioPlayerModal: ref(false),
  audioTitle: ref(''),
  currentPreviewAudioId: ref(null),
  currentPreviewAudioType: ref(''),
  pathBasename: vi.fn((p: string) => p),
  testCaseGeneratedCount: ref(0),
  showTestCaseGeneratedTip: ref(false),
  goToTestCaseManager: vi.fn(),
  algorithmOptions: ref([]),
  fetchAlgorithmOptions: vi.fn(),
};

const openUploadModal = () => audioImportState.api.openUploadModal as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  routeState.query = {};
  routeState.pushes.length = 0;
  // uploadOptions 还原为 useAudioUpload 初始默认
  Object.assign(uploadOptions, {
    audioType: 'dry',
    createTestCase: false,
    algorithmType: ''
  });
});

/** 挂载页面并等待 nextTick 打开弹窗的回调执行 */
const mountView = async () => {
  const wrapper = mount(AudioImportView);
  await flushPromises();
  return wrapper;
};

describe('消费者：AudioImport onMounted 解析 route.query（对齐 V9.7.10 基线）', () => {
  it('autoOpen=1 + createTestCase=true + algorithmType → 预置 uploadOptions 并自动打开上传弹窗', async () => {
    routeState.query = {
      [AUDIO_IMPORT_QUERY.autoOpen]: AUDIO_IMPORT_AUTO_OPEN_VALUE,
      [AUDIO_IMPORT_QUERY.createTestCase]: 'true',
      [AUDIO_IMPORT_QUERY.algorithmType]: 'voice_llm'
    };

    await mountView();

    expect(uploadOptions.createTestCase).toBe(true);
    expect(uploadOptions.algorithmType).toBe('voice_llm');
    expect(openUploadModal()).toHaveBeenCalledTimes(1);
  });

  it('仅 autoOpen=1：打开弹窗，createTestCase/algorithmType 维持默认', async () => {
    routeState.query = { [AUDIO_IMPORT_QUERY.autoOpen]: AUDIO_IMPORT_AUTO_OPEN_VALUE };

    await mountView();

    expect(openUploadModal()).toHaveBeenCalledTimes(1);
    expect(uploadOptions.createTestCase).toBe(false);
    expect(uploadOptions.algorithmType).toBe('');
  });

  it('autoOpen 缺失：其余参数存在也不打开弹窗、不改写 uploadOptions', async () => {
    routeState.query = {
      [AUDIO_IMPORT_QUERY.createTestCase]: 'true',
      [AUDIO_IMPORT_QUERY.algorithmType]: 'voice_llm'
    };

    await mountView();

    expect(openUploadModal()).not.toHaveBeenCalled();
    expect(uploadOptions.createTestCase).toBe(false);
    expect(uploadOptions.algorithmType).toBe('');
  });

  it('autoOpen 非 "1"（如 "0"）不触发（基线严格等于语义）', async () => {
    routeState.query = { [AUDIO_IMPORT_QUERY.autoOpen]: '0' };

    await mountView();

    expect(openUploadModal()).not.toHaveBeenCalled();
    expect(uploadOptions.createTestCase).toBe(false);
  });

  it('algorithmType 为数组（vue-router 重复参数形态）时忽略，不预置', async () => {
    routeState.query = {
      [AUDIO_IMPORT_QUERY.autoOpen]: AUDIO_IMPORT_AUTO_OPEN_VALUE,
      [AUDIO_IMPORT_QUERY.algorithmType]: ['voice_llm', 'tts']
    };

    await mountView();

    expect(openUploadModal()).toHaveBeenCalledTimes(1);
    expect(uploadOptions.algorithmType).toBe('');
  });
});

describe('生产者↔消费者 query 契约（本次断链根因的防漂移锁）', () => {
  it('openImportTestCaseModal 推送 /AudioImport，query 键与 AUDIO_IMPORT_QUERY 常量同源', async () => {
    const { openImportTestCaseModal } = useTestCaseCard();

    await openImportTestCaseModal();

    expect(routeState.pushes).toHaveLength(1);
    const loc = routeState.pushes[0];
    expect(loc.path).toBe('/AudioImport');
    expect(loc.query[AUDIO_IMPORT_QUERY.autoOpen]).toBe(AUDIO_IMPORT_AUTO_OPEN_VALUE);
    expect(loc.query[AUDIO_IMPORT_QUERY.createTestCase]).toBe('true');
    expect(loc.query[AUDIO_IMPORT_QUERY.algorithmType]).toBeUndefined();
  });

  it('带 algorithmType 时按同名常量键透传', async () => {
    const { openImportTestCaseModal } = useTestCaseCard();

    await openImportTestCaseModal('voice_llm');

    const loc = routeState.pushes[0];
    expect(loc.query[AUDIO_IMPORT_QUERY.algorithmType]).toBe('voice_llm');
  });
});
