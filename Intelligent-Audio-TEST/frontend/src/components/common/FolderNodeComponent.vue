<template>
  <div class="folder-node">
    <div class="folder-header" @click="handleToggle">
      <input
        v-if="enableSelection && (folder.files?.length || folder.file_count || folderHasFiles)"
        type="checkbox"
        class="folder-checkbox"
        :checked="isFolderAllSelected"
        :indeterminate.prop="isFolderPartialSelected"
        @click.stop="handleFolderSelectionClick"
      >
      <i class="fas" :class="{ 'fa-folder-open': isOpen, 'fa-folder': !isOpen }"></i>
      <span class="folder-name">{{ folder.name }}</span>
      <span class="folder-stats">
        ({{ folder.count || folder.files?.length || 0 }} 个文件<template v-if="folder.folders?.length">, {{ folder.folders.length }} 个文件夹</template>)
      </span>
      <span v-if="isLoading" class="folder-loading">
        <i class="fas fa-spinner fa-spin"></i>
      </span>
    </div>
    <div class="folder-content" v-if="isOpen">
      <template v-for="subfolder in folder.folders" :key="subfolder.path || subfolder.name">
        <div class="folder-children">
          <FolderNodeComponent
            :folder="subfolder"
            :enable-selection="enableSelection"
            :is-selected-fn="isSelectedFn"
            :expanded-paths="expandedPaths"
            :is-folder-all-selected-fn="isFolderAllSelectedFn"
            :is-folder-partial-selected-fn="isFolderPartialSelectedFn"
            @toggle-folder="(f: any) => $emit('toggleFolder', f)"
            @expand-folder="(path: string) => $emit('expandFolder', path)"
            @toggle-audio-selection="(id: string | number) => $emit('toggleAudioSelection', id)"
            @toggle-folder-selection="(f: any) => $emit('toggleFolderSelection', f)"
            @preview="(id: string | number) => $emit('preview', id)"
            @edit="(id: string | number) => $emit('edit', id)"
            @delete="(id: string | number) => $emit('delete', id)"
          />
        </div>
      </template>
      <!-- Virtual scrolled file list -->
      <div
        v-if="folder.files && folder.files.length > 0"
        class="file-list"
        :class="{ 'virtual-list': folder.files.length > VIRTUAL_THRESHOLD }"
        @scroll="folder.files.length > VIRTUAL_THRESHOLD ? onScroll($event) : undefined"
        :style="folder.files.length > VIRTUAL_THRESHOLD ? containerStyle : {}"
      >
        <!-- Spacer for virtual scroll -->
        <div
          v-if="folder.files.length > VIRTUAL_THRESHOLD"
          :style="{ height: totalHeight + 'px', position: 'relative' }"
        >
          <div :style="{ position: 'absolute', top: offsetY + 'px', left: '0', right: '0' }">
            <div
              v-for="file in visibleFiles"
              :key="file.id"
              class="file-item"
              :class="{ highlighted: isSelectedFn(file.id) }"
              @click="$emit('toggleAudioSelection', file.id)"
            >
              <input
                v-if="enableSelection"
                type="checkbox"
                class="audio-checkbox"
                :value="file.id"
                :checked="isSelectedFn(file.id)"
                @change="$emit('toggleAudioSelection', file.id)"
                @click.stop
              >
              <i class="fas fa-file-audio file-icon"></i>
              <div class="file-info">
                <div class="file-name">{{ file.filename || file.name }}</div>
                <div class="file-meta">
                  <span class="format-badge" :class="file.format">{{ (file.format || '').toUpperCase() }}</span>
                  <span class="file-size">{{ formatSize(file.size) }}</span>
                  <span class="file-duration">{{ formatDuration(file.duration) }}</span>
                  <span class="audio-type-badge" :class="file.audio_type || file.type">
                    {{ getTypeLabel(file.audio_type || file.type) }}
                  </span>
                </div>
              </div>
              <div class="file-actions">
                <button class="btn btn-secondary" @click.stop="$emit('preview', file.id)">
                  <i class="fas fa-play btn-icon"></i>
                  预览
                </button>
                <button class="btn btn-secondary" @click.stop="$emit('edit', file.id)">
                  <i class="fas fa-edit btn-icon"></i>
                  详情
                </button>
                <button class="btn btn-danger" @click.stop="$emit('delete', file.id)">
                  <i class="fas fa-trash-alt btn-icon"></i>
                  删除
                </button>
              </div>
            </div>
          </div>
        </div>
        <!-- Normal (non-virtual) file list -->
        <template v-else>
          <div
            v-for="file in folder.files"
            :key="file.id"
            class="file-item"
            :class="{ highlighted: isSelectedFn(file.id) }"
            @click="$emit('toggleAudioSelection', file.id)"
          >
            <input
              v-if="enableSelection"
              type="checkbox"
              class="audio-checkbox"
              :value="file.id"
              :checked="isSelectedFn(file.id)"
              @change="$emit('toggleAudioSelection', file.id)"
              @click.stop
            >
            <i class="fas fa-file-audio file-icon"></i>
            <div class="file-info">
              <div class="file-name">{{ file.filename || file.name }}</div>
              <div class="file-meta">
                <span class="format-badge" :class="file.format">{{ (file.format || '').toUpperCase() }}</span>
                <span class="file-size">{{ formatSize(file.size) }}</span>
                <span class="file-duration">{{ formatDuration(file.duration) }}</span>
                <span class="audio-type-badge" :class="file.audio_type || file.type">
                  {{ getTypeLabel(file.audio_type || file.type) }}
                </span>
              </div>
            </div>
            <div class="file-actions">
              <button class="btn btn-secondary" @click.stop="$emit('preview', file.id)">
                <i class="fas fa-play btn-icon"></i>
                预览
              </button>
              <button class="btn btn-secondary" @click.stop="$emit('edit', file.id)">
                <i class="fas fa-edit btn-icon"></i>
                详情
              </button>
              <button class="btn btn-danger" @click.stop="$emit('delete', file.id)">
                <i class="fas fa-trash-alt btn-icon"></i>
                删除
              </button>
            </div>
          </div>
        </template>
      </div>
      <!-- Lazy loading indicator -->
      <div v-if="isOpen && (!folder.files || folder.files.length === 0) && (folder.file_count ?? 0) > 0 && folder.folders?.length === 0" class="lazy-load-hint">
        <i class="fas fa-spinner fa-spin" v-if="isLoading"></i>
        <span v-else>点击文件夹加载文件...</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

interface FolderNode {
  name: string;
  path?: string;
  count?: number;
  file_count?: number;
  has_children?: boolean;
  files: any[];
  folders: FolderNode[];
}

const VIRTUAL_THRESHOLD = 40;
const ITEM_HEIGHT = 48;
const BUFFER = 10;
const VISIBLE_HEIGHT = 500;

const props = defineProps<{
  folder: FolderNode;
  enableSelection: boolean;
  isSelectedFn: (id: string | number) => boolean;
  expandedPaths?: Set<string>;
  isFolderAllSelectedFn?: (folder: any) => boolean;
  isFolderPartialSelectedFn?: (folder: any) => boolean;
}>();

const emit = defineEmits<{
  (e: 'toggleFolder', folder: FolderNode): void;
  (e: 'expandFolder', path: string): void;
  (e: 'toggleAudioSelection', id: string | number): void;
  (e: 'toggleFolderSelection', folder: any): void;
  (e: 'preview', id: string | number): void;
  (e: 'edit', id: string | number): void;
  (e: 'delete', id: string | number): void;
}>();

const localOpen = ref(true);
const scrollTop = ref(0);
const isLoading = ref(false);

const isOpen = computed(() => {
  if (props.expandedPaths && props.folder.path !== undefined) {
    return props.expandedPaths.has(props.folder.path);
  }
  return localOpen.value;
});

// 递归判断该文件夹（含子文件夹）是否含有文件
const folderHasFiles = computed(() => {
  function hasFiles(node: any): boolean {
    if (Array.isArray(node?.files) && node.files.length > 0) return true;
    if (Array.isArray(node?.folders)) {
      return node.folders.some((c: any) => hasFiles(c));
    }
    return false;
  }
  return hasFiles(props.folder) || (props.folder.file_count ?? 0) > 0;
});

const isFolderAllSelected = computed(() => {
  if (props.isFolderAllSelectedFn) {
    try { return props.isFolderAllSelectedFn(props.folder); } catch { return false; }
  }
  return false;
});

const isFolderPartialSelected = computed(() => {
  if (props.isFolderPartialSelectedFn) {
    try { return props.isFolderPartialSelectedFn(props.folder); } catch { return false; }
  }
  return false;
});

async function handleFolderSelectionClick(event: Event) {
  event.stopPropagation();
  // 如果文件夹未展开且文件未加载（file_count > 0 但 files 为空），先懒加载再勾选
  const fileCount = props.folder.file_count ?? 0;
  const loadedFiles = props.folder.files?.length ?? 0;
  if (!isOpen.value && fileCount > 0 && loadedFiles === 0) {
    emit('expandFolder', props.folder.path ?? '');
    // 轮询等待懒加载完成，最长等 3 秒
    const start = Date.now();
    await new Promise<void>((resolve) => {
      const check = () => {
        if ((props.folder.files?.length ?? 0) > 0 || Date.now() - start > 3000) resolve();
        else setTimeout(check, 50);
      };
      check();
    });
  }
  emit('toggleFolderSelection', props.folder);
}

const totalHeight = computed(() => {
  return (props.folder.files?.length || 0) * ITEM_HEIGHT;
});

const containerStyle = computed(() => ({
  maxHeight: VISIBLE_HEIGHT + 'px',
  overflowY: 'auto' as const,
}));

const visibleRange = computed(() => {
  const files = props.folder.files || [];
  if (files.length <= VIRTUAL_THRESHOLD) return { start: 0, end: files.length };
  const start = Math.max(0, Math.floor(scrollTop.value / ITEM_HEIGHT) - BUFFER);
  const end = Math.min(files.length, Math.ceil((scrollTop.value + VISIBLE_HEIGHT) / ITEM_HEIGHT) + BUFFER);
  return { start, end };
});

const offsetY = computed(() => visibleRange.value.start * ITEM_HEIGHT);

const visibleFiles = computed(() => {
  const files = props.folder.files || [];
  if (files.length <= VIRTUAL_THRESHOLD) return files;
  return files.slice(visibleRange.value.start, visibleRange.value.end);
});

function onScroll(event: Event) {
  const target = event.target as HTMLElement;
  scrollTop.value = target.scrollTop;
}

function handleToggle() {
  if (props.expandedPaths && props.folder.path !== undefined) {
    emit('expandFolder', props.folder.path);
  } else {
    emit('toggleFolder', props.folder);
    localOpen.value = !localOpen.value;
  }
}

function formatSize(size: number): string {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let s = size;
  while (s >= 1024 && i < units.length - 1) { s /= 1024; i++; }
  return s.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function formatDuration(seconds: number): string {
  if (!seconds) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

function getTypeLabel(type: string): string {
  const map: Record<string, string> = { dry: '干声', noise: '噪声', mixed: '混合', prompt: '提示词' };
  return map[type] || type || '未知';
}
</script>

<style scoped>
.folder-node {
  margin-left: 0;
}

.folder-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  cursor: pointer;
  border-radius: var(--border-radius-md, 6px);
  transition: background-color 0.15s;
}

.folder-header:hover {
  background-color: var(--background-secondary, #f5f5f5);
}

.folder-header i {
  color: var(--primary-color, #4a90d9);
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.folder-name {
  font-weight: 500;
  color: var(--text-primary, #333);
}

.folder-stats {
  font-size: 12px;
  color: var(--text-muted, #999);
}

.folder-content {
  margin-left: 20px;
}

.folder-children {
  margin-left: 4px;
}

.file-list {
  margin-top: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md, 12px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--border-radius-md, 6px);
  margin-bottom: var(--spacing-xs, 4px);
  transition: all 0.15s;
  cursor: pointer;
}

.file-item:hover {
  background-color: var(--background-secondary, #f5f5f5);
  border-color: var(--primary-color, #4a90d9);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.file-item.highlighted {
  background-color: var(--primary-light, #e8f0fe);
  border-color: var(--primary-color, #4a90d9);
}

.file-icon {
  color: var(--primary-color, #4a90d9);
  font-size: var(--font-size-lg, 18px);
  width: 24px;
  text-align: center;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary, #333);
  margin-bottom: var(--spacing-xs, 4px);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.file-meta {
  display: flex;
  gap: var(--spacing-sm, 8px);
  flex-wrap: wrap;
  align-items: center;
}

.file-meta span {
  font-size: var(--font-size-xs, 12px);
}

.file-size {
  color: var(--text-muted, #999);
}

.file-duration {
  color: var(--text-muted, #999);
}

.format-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  background-color: var(--background-tertiary, #eee);
  color: var(--text-secondary, #666);
}

.format-badge.wav { background-color: #e3f2fd; color: #1565c0; }
.format-badge.mp3 { background-color: #f3e5f5; color: #7b1fa2; }
.format-badge.flac { background-color: #e8f5e9; color: #2e7d32; }
.format-badge.aac { background-color: #fff3e0; color: #e65100; }

.audio-type-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.audio-type-badge.dry { background-color: #e8eaf6; color: #283593; }
.audio-type-badge.noise { background-color: #fff8e1; color: #f57f17; }
.audio-type-badge.mixed { background-color: #e0f2f1; color: #00695c; }
.audio-type-badge.prompt { background-color: #fce4ec; color: #c62828; }

.file-actions {
  display: flex;
  gap: var(--spacing-xs, 4px);
  opacity: 0.7;
  transition: opacity 0.15s;
}

.file-item:hover .file-actions {
  opacity: 1;
}

.file-actions .btn {
  padding: 2px 8px;
  font-size: 12px;
  min-width: auto;
  height: auto;
  border-radius: 4px;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-secondary {
  background-color: var(--background-secondary, #f5f5f5);
  border: 1px solid var(--border-color, #e0e0e0) !important;
  color: var(--text-primary, #333);
}

.btn-secondary:hover {
  background-color: var(--background-tertiary, #eee);
  border-color: var(--primary-color, #4a90d9) !important;
  color: var(--primary-color, #4a90d9);
}

.btn-danger {
  background-color: #ef5350;
  color: white;
}

.btn-danger:hover {
  background-color: #e53935;
}

.btn-icon {
  margin-right: 4px;
}

.audio-checkbox {
  accent-color: var(--primary-color, #4a90d9);
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.folder-checkbox {
  accent-color: var(--primary-color, #4a90d9);
  cursor: pointer;
  width: 16px;
  height: 16px;
  margin-right: 4px;
  flex-shrink: 0;
}

.folder-loading {
  margin-left: 8px;
  color: var(--primary-color, #4a90d9);
  font-size: 12px;
}

.lazy-load-hint {
  padding: 12px 20px;
  color: var(--text-muted, #999);
  font-size: 13px;
  text-align: center;
}

.lazy-load-hint i {
  margin-right: 6px;
}

.virtual-list {
  position: relative;
}

.virtual-list .file-item {
  height: 48px;
  box-sizing: border-box;
}
</style>