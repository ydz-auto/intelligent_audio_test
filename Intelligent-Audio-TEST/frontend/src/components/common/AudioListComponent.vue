<template>
  <div class="audio-list-component">
    <!-- 卡片头部 -->
    <div class="card-header">
      <h3 class="card-title">音频文件列表</h3>
      <div class="card-actions">
        <slot name="header-actions"></slot>
        <div class="view-toggle">
          <div 
            class="btn btn-secondary" 
            :class="{ active: viewMode === 'list' }" 
            @click="switchView('list')"
          >
            <i class="fas fa-list"></i>
          </div>
          <div 
            class="btn btn-secondary" 
            :class="{ active: viewMode === 'folder' }" 
            @click="switchView('folder')"
          >
            <i class="fas fa-folder"></i>
          </div>
          <div 
            class="btn btn-secondary" 
            :class="{ active: viewMode === 'diagnostics' }" 
            @click="switchView('diagnostics')"
          >
            <i class="fas fa-exclamation-triangle"></i>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 筛选区域 -->
    <div class="card-filter-section">
      <!-- 搜索区域 -->
      <div class="search-section">
        <div class="search-box">
          <i class="fas fa-search search-icon"></i>
          <input 
            type="text" 
            class="search-input" 
            placeholder="搜索音频文件名、标签、ASR文本..." 
            v-model="searchQuery"
            @input="handleSearch"
          >
        </div>
      </div>
      
      <!-- 筛选面板 -->
      <div class="filter-panel">
        <div class="filter-content">
          <div class="filter-grid">
            <!-- 格式筛选 -->
            <div class="filter-item">
              <label class="filter-label">音频格式</label>
              <select 
                class="filter-select" 
                v-model="filters.format"
                @change="handleFilterChange"
              >
                <option value="all">所有格式</option>
                <option value="mp3">MP3</option>
                <option value="wav">WAV</option>
                <option value="flac">FLAC</option>
                <option value="aac">AAC</option>
                <option value="m4a">M4A</option>
              </select>
            </div>
            
            <!-- 采样率筛选 -->
            <div class="filter-item">
              <label class="filter-label">采样率</label>
              <select 
                class="filter-select" 
                v-model="filters.sampleRate"
                @change="handleFilterChange"
              >
                <option value="all">所有采样率</option>
                <option value="8000">8 kHz</option>
                <option value="16000">16 kHz</option>
                <option value="24000">24 kHz</option>
                <option value="44100">44.1 kHz</option>
                <option value="48000">48 kHz</option>
                <option value="96000">96 kHz</option>
              </select>
            </div>
            
            <!-- 标签云筛选 -->
            <div class="filter-item">
              <label class="filter-label">标签云</label>
              <div class="tag-search-wrapper">
                <input 
                  type="text" 
                  v-model="tagSearchQuery"
                  placeholder="搜索标签..."
                  class="tag-search-input"
                />
              </div>
              <div class="tag-filter">
                <div 
                  v-for="tag in filteredTags" 
                  :key="tag"
                  :class="['tag-filter-item', { active: isTagSelected(tag), 'tag-or': getTagMode(tag) === 'or', 'tag-and': getTagMode(tag) === 'and' }]"
                  @click="handleTagClick(tag)"
                  @contextmenu.prevent="showTagMenu($event, tag)"
                >
                  {{ tag }}
                  <span v-if="getTagMode(tag)" class="tag-mode-badge">{{ getTagMode(tag) === 'or' ? 'OR' : 'AND' }}</span>
                </div>
                <div v-if="filteredTags.length === 0" class="no-data-tip">
                  暂无可用的用例标签或用例分组
                </div>
              </div>
              <!-- 标签模式选择菜单 -->
              <div 
                v-if="showTagModeMenu" 
                class="tag-mode-menu"
                :style="{ top: menuPosition.y + 'px', left: menuPosition.x + 'px' }"
              >
                <div class="tag-mode-menu-item" @click="setTagMode('or')">
                  <span class="tag-mode-icon or">OR</span>
                  满足任一标签
                </div>
                <div class="tag-mode-menu-item" @click="setTagMode('and')">
                  <span class="tag-mode-icon and">AND</span>
                  满足所有标签
                </div>
                <div class="tag-mode-menu-divider"></div>
                <div class="tag-mode-menu-item remove" @click="removeTag">
                  <i class="fas fa-times"></i> 移除标签
                </div>
              </div>
            </div>
            
            <!-- 时长筛选 -->
            <div class="filter-item">
              <label class="filter-label">音频时长</label>
              <select 
                class="filter-select" 
                v-model="filters.duration"
                @change="handleFilterChange"
              >
                <option value="all">所有时长</option>
                <option value="short">短 (<= 30秒)</option>
                <option value="medium">中 (30秒 - 5分钟)</option>
                <option value="long">长 (> 5分钟)</option>
              </select>
            </div>
            
            <!-- 类型筛选 -->
            <div class="filter-item">
              <label class="filter-label">音频类型</label>
              <select 
                class="filter-select" 
                v-model="filters.audioType"
                @change="handleFilterChange"
              >
                <option value="all">所有类型</option>
                <option value="dry">干声</option>
                <option value="noise">噪声</option>
                <option value="prompt">提示词音频</option>
                <option value="mixed">混合音频</option>
              </select>
            </div>
            
            <!-- 筛选操作按钮 -->
            <div class="filter-item filter-actions-item">
              <div class="filter-actions">
                <button class="btn btn-secondary" @click="resetFilters">重置筛选</button>
                <button class="btn btn-primary" @click="applyFilters">应用筛选</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 列表视图 -->
    <div v-if="viewMode === 'list'" class="card-body">
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th v-if="enableSelection" style="width: 40px;" class="checkbox-col core-col">
                <input 
                  type="checkbox"
                  class="audio-checkbox"
                  :checked="isAllSelected"
                  @click.stop="handleCheckboxClick"
                >
              </th>
              <th class="sortable file-name-col core-col">文件名</th>
              <th class="sortable core-col">格式</th>
              <th class="sortable secondary-col">大小</th>
              <th class="sortable core-col">时长</th>
              <th class="sortable secondary-col">音频类型</th>
              <th class="sortable tertiary-col">源语言</th>
              <th class="tertiary-col">标签</th>
              <th v-if="showStatus" class="secondary-col">状态</th>
              <th class="action-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="audio in filteredAudios" 
              :key="audio.id" 
              :class="{ 'highlighted': isSelected(audio.id) }"
              @click="toggleAudioSelection(audio.id)"
              style="cursor: pointer;"
            >
              <td v-if="enableSelection" class="checkbox-col core-col">
                <input 
                  type="checkbox" 
                  class="audio-checkbox" 
                  :value="audio.id" 
                  :checked="isSelected(audio.id)"
                  @change="toggleAudioSelection(audio.id)"
                  @click.stop
                >
              </td>
              <td class="core-col">
                <div class="audio-info">
                  <div class="audio-icon">
                    <i class="fas fa-file-audio"></i>
                  </div>
                  <div class="audio-details">
                <div class="audio-name">{{ audio.filename }}</div>
              </div>
                </div>
              </td>
              <td class="core-col"><span class="format-badge" :class="audio.format">{{ audio.format.toUpperCase() }}</span></td>
              <td class="secondary-col">{{ audio.size }}</td>
              <td class="core-col">{{ audio.duration }}</td>
              <td class="secondary-col"><span class="audio-type-badge" :class="audio.type">
                {{ audio.type === 'dry' ? '干声' : (audio.type === 'noise' ? '噪声' : (audio.type === 'mixed' ? '混合' : '提示词')) }}
              </span></td>
              <td class="tertiary-col">
                {{ audio.sourceLanguage || '-' }}
              </td>
              <td class="tertiary-col">
                <div class="tags-container">
                  <template v-if="getNormalizedTags(audio.tags).length > 0">
                    <template v-if="!expandedTags[audio.id]">
                      <span 
                        v-for="(tag, index) in getNormalizedTags(audio.tags).slice(0, MAX_VISIBLE_TAGS)" 
                        :key="index" 
                        class="tag-item"
                      >{{ tag }}</span>
                      <span 
                        v-if="getNormalizedTags(audio.tags).length > MAX_VISIBLE_TAGS" 
                        class="tag-more"
                        @click.stop="toggleExpandTags(audio.id)"
                      >+{{ getNormalizedTags(audio.tags).length - MAX_VISIBLE_TAGS }} 更多</span>
                    </template>
                    <template v-else>
                      <span v-for="(tag, index) in getNormalizedTags(audio.tags)" :key="index" class="tag-item">{{ tag }}</span>
                      <span 
                        class="tag-collapse"
                        @click.stop="toggleExpandTags(audio.id)"
                      >收起</span>
                    </template>
                  </template>
                  <span v-else class="no-tags">-</span>
                </div>
              </td>
              <td v-if="showStatus" class="secondary-col"><span class="status-badge active">{{ audio.status }}</span></td>
              <td class="action-col">
                <div class="action-buttons">
                  <button class="btn btn-secondary" @click.stop="previewAudio(audio.id)">
                    <i class="fas fa-play btn-icon"></i>
                    预览
                  </button>
                  <button class="btn btn-secondary" @click.stop="editMetadata(audio.id)">
                    <i class="fas fa-edit btn-icon"></i>
                    详情
                  </button>
                  <button class="btn btn-secondary" @click.stop="downloadAudio(audio.id)">
                    <i class="fas fa-download btn-icon"></i>
                    下载
                  </button>
                  <button class="btn btn-danger" @click.stop="deleteAudio(audio.id)">
                    <i class="fas fa-trash-alt btn-icon"></i>
                    删除
                  </button>
                  <slot 
                    name="actions" 
                    :audio="audio"
                  >
                    <div 
                      v-if="$slots.actions === undefined"
                      class="btn btn-secondary" 
                      @click.stop="handleAudioSelect(audio)"
                    >
                      <i class="fas fa-check btn-icon"></i>
                      选择
                    </div>
                  </slot>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div v-if="filteredAudios.length === 0" class="empty-state">
        <i class="fas fa-music"></i>
        <p>没有找到匹配的音频文件</p>
      </div>
    </div>
    
    <!-- 文件夹视图 -->
    <div v-if="viewMode === 'folder'" class="card-body">
      <div class="folder-view">
        <div class="folder-tree">
          <div class="folder-node" :key="folderTree.name">
            <div 
              class="folder-header" 
              @click="toggleFolder(folderTree)"
            >
              <i class="fas" :class="{ 'fa-folder-open': isFolderOpen(folderTree), 'fa-folder': !isFolderOpen(folderTree) }"></i>
              <span class="folder-name">{{ folderTree.name }}</span>
              <span class="folder-stats">
                ({{ folderTree.files.length }} 个文件, {{ folderTree.folders.length }} 个文件夹)
              </span>
            </div>
            <div class="folder-content" v-if="isFolderOpen(folderTree)">
              <!-- 递归渲染子文件夹 -->
              <template v-for="subfolder in folderTree.folders" :key="subfolder.name">
                <div class="folder-children">
                  <div class="folder-node">
                    <div 
                      class="folder-header" 
                      @click="toggleFolder(subfolder)"
                    >
                      <i class="fas" :class="{ 'fa-folder-open': isFolderOpen(subfolder), 'fa-folder': !isFolderOpen(subfolder) }"></i>
                      <span class="folder-name">{{ subfolder.name }}</span>
                      <span class="folder-stats">
                        ({{ subfolder.files.length }} 个文件, {{ subfolder.folders.length }} 个文件夹)
                      </span>
                    </div>
                    <div class="folder-content" v-if="isFolderOpen(subfolder)">
                      <!-- 递归渲染更深层的子文件夹 -->
                      <template v-for="deeperFolder in subfolder.folders" :key="deeperFolder.name">
                        <div class="folder-children">
                          <div class="folder-node">
                            <div
                              class="folder-header"
                              @click="toggleFolder(deeperFolder)"
                            >
                              <i class="fas" :class="{ 'fa-folder-open': isFolderOpen(deeperFolder), 'fa-folder': !isFolderOpen(deeperFolder) }"></i>
                              <span class="folder-name">{{ deeperFolder.name }}</span>
                              <span class="folder-stats">
                                ({{ deeperFolder.files.length }} 个文件, {{ deeperFolder.folders.length }} 个文件夹)
                              </span>
                            </div>
                            <div class="folder-content" v-if="isFolderOpen(deeperFolder)">
                              <!-- 当前文件夹的文件列表 -->
                              <div class="file-list">
                                <div
                                  v-for="file in deeperFolder.files"
                                  :key="file.id"
                                  class="file-item"
                                  :class="{ 'highlighted': isSelected(file.id) }"
                                  @click="toggleAudioSelection(file.id)"
                                >
                                  <input
                                    v-if="enableSelection"
                                    type="checkbox"
                                    class="audio-checkbox"
                                    :value="file.id"
                                    :checked="isSelected(file.id)"
                                    @change="toggleAudioSelection(file.id)"
                                    @click.stop
                                  >
                                  <i class="fas fa-file-audio file-icon"></i>
                                  <div class="file-info">
                                    <div class="file-name">{{ file.filename }}</div>
                                    <div class="file-meta">
                                      <span class="format-badge" :class="file.format">{{ file.format.toUpperCase() }}</span>
                                      <span class="file-size">{{ file.size }}</span>
                                      <span class="file-duration">{{ file.duration }}</span>
                                      <span class="audio-type-badge" :class="file.type">
                                        {{ file.type === 'dry' ? '干声' : (file.type === 'noise' ? '噪声' : (file.type === 'mixed' ? '混合' : '提示词')) }}
                                      </span>
                                    </div>
                                  </div>
                                  <div class="file-actions">
                                    <button class="btn btn-secondary" @click.stop="previewAudio(file.id)">
                                      <i class="fas fa-play btn-icon"></i>
                                      预览
                                    </button>
                                    <button class="btn btn-secondary" @click.stop="editMetadata(file.id)">
                                      <i class="fas fa-edit btn-icon"></i>
                                      详情
                                    </button>
                                    <button class="btn btn-danger" @click.stop="deleteAudio(file.id)">
                                      <i class="fas fa-trash-alt btn-icon"></i>
                                      删除
                                    </button>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </template>
                      <!-- 当前文件夹的文件列表 -->
                      <div class="file-list">
                        <div
                          v-for="file in subfolder.files"
                          :key="file.id"
                          class="file-item"
                          :class="{ 'highlighted': isSelected(file.id) }"
                          @click="toggleAudioSelection(file.id)"
                        >
                          <input
                            v-if="enableSelection"
                            type="checkbox"
                            class="audio-checkbox"
                            :value="file.id"
                            :checked="isSelected(file.id)"
                            @change="toggleAudioSelection(file.id)"
                            @click.stop
                          >
                          <i class="fas fa-file-audio file-icon"></i>
                          <div class="file-info">
                            <div class="file-name">{{ file.filename }}</div>
                            <div class="file-meta">
                              <span class="format-badge" :class="file.format">{{ file.format.toUpperCase() }}</span>
                              <span class="file-size">{{ file.size }}</span>
                              <span class="file-duration">{{ file.duration }}</span>
                              <span class="audio-type-badge" :class="file.type">
                                {{ file.type === 'dry' ? '干声' : (file.type === 'noise' ? '噪声' : (file.type === 'mixed' ? '混合' : '提示词')) }}
                              </span>
                            </div>
                          </div>
                          <div class="file-actions">
                            <button class="btn btn-secondary" @click.stop="previewAudio(file.id)">
                              <i class="fas fa-play btn-icon"></i>
                              预览
                            </button>
                            <button class="btn btn-secondary" @click.stop="editMetadata(file.id)">
                              <i class="fas fa-edit btn-icon"></i>
                              详情
                            </button>
                            <button class="btn btn-danger" @click.stop="deleteAudio(file.id)">
                              <i class="fas fa-trash-alt btn-icon"></i>
                              删除
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
              <!-- 根文件夹的文件列表 -->
              <div class="file-list">
                <div 
                  v-for="file in folderTree.files" 
                  :key="file.id" 
                  class="file-item"
                  :class="{ 'highlighted': isSelected(file.id) }"
                  @click="toggleAudioSelection(file.id)"
                >
                  <input 
                    v-if="enableSelection"
                    type="checkbox" 
                    class="audio-checkbox" 
                    :value="file.id" 
                    :checked="isSelected(file.id)"
                    @change="toggleAudioSelection(file.id)"
                    @click.stop
                  >
                  <i class="fas fa-file-audio file-icon"></i>
                  <div class="file-info">
                    <div class="file-name">{{ file.filename }}</div>
                    <div class="file-meta">
                      <span class="format-badge" :class="file.format">{{ file.format.toUpperCase() }}</span>
                      <span class="file-size">{{ file.size }}</span>
                      <span class="file-duration">{{ file.duration }}</span>
                      <span class="audio-type-badge" :class="file.type">
                        {{ file.type === 'dry' ? '干声' : (file.type === 'noise' ? '噪声' : (file.type === 'mixed' ? '混合' : '提示词')) }}
                      </span>
                    </div>
                  </div>
                  <div class="file-actions">
                    <button class="btn btn-secondary" @click.stop="previewAudio(file.id)">
                      <i class="fas fa-play btn-icon"></i>
                      预览
                    </button>
                    <button class="btn btn-secondary" @click.stop="editMetadata(file.id)">
                      <i class="fas fa-edit btn-icon"></i>
                      详情
                    </button>
                    <button class="btn btn-danger" @click.stop="deleteAudio(file.id)">
                      <i class="fas fa-trash-alt btn-icon"></i>
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 诊断视图 -->
    <div v-if="viewMode === 'diagnostics'" class="card-body diagnostics-view">
      <div class="diagnostics-header">
        <h4>音频文件问题诊断</h4>
        <div class="diagnostics-stats">
          <div class="stat-item">
            <span class="stat-number">{{ problematicAudios.length }}</span>
            <span class="stat-label">个问题文件</span>
          </div>
        </div>
      </div>
      
      <div class="diagnostics-list">
        <div v-if="problematicAudios.length === 0" class="no-problems">
          <i class="fas fa-check-circle success-icon"></i>
          <p>所有音频文件正常</p>
        </div>
        
        <div 
          v-for="audio in problematicAudios" 
          :key="audio.id" 
          class="diagnostics-item"
        >
          <div class="audio-basic-info">
            <i class="fas fa-file-audio audio-icon"></i>
            <div class="audio-details">
              <div class="audio-name">{{ audio.filename }}</div>
              <div class="audio-meta">
                <span class="format-badge" :class="audio.format">{{ audio.format.toUpperCase() }}</span>
                <span class="file-size">{{ audio.size }}</span>
                <span class="file-duration">{{ audio.duration }}</span>
              </div>
            </div>
          </div>
          
          <div class="audio-problems">
            <div 
              v-for="(problem, index) in audio.problems" 
              :key="index" 
              class="problem-item"
              :class="problem.severity"
            >
              <i :class="getProblemIcon(problem.type)"></i>
              <span class="problem-description">{{ problem.description }}</span>
            </div>
          </div>
          
          <div class="diagnostics-actions">
            <button class="btn btn-secondary" @click.stop="editMetadata(audio.id)">
              <i class="fas fa-edit btn-icon"></i>
              修复
            </button>
            <button class="btn btn-danger" @click.stop="deleteAudio(audio.id)">
              <i class="fas fa-trash-alt btn-icon"></i>
              删除
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 分页组件 -->
    <div class="pagination-container" v-if="props.totalAudios > 0">
      <PaginationComponent
        :total-items="props.totalAudios"
        :page-size="props.pageSize"
        :current-page="props.currentPage"
        @go-to-page="handlePageChange"
        @page-size-change="handleSizeChange"
      />
    </div>
    
    <!-- 音频播放模态框 -->
    <AudioPlayerModal
      :visible="showAudioPlayerModal"
      :audio-id="currentAudioId"
      :audio-title="currentAudioTitle"
      :audio-type="props.audioType"
      :selected-devices="[]"
      @close="showAudioPlayerModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { buildFolderTree, isFolderOpen as checkFolderOpen, toggleFolder as toggleFolderState, extractAllTags, filterAudios as filterAudiosUtil } from '../../utils/audioUtils';
import { useTagFilter, type TagFilterState } from '../../composables/useTagFilter';
import AudioPlayerModal from './AudioPlayerModal.vue';
import PaginationComponent from './PaginationComponent.vue';

interface AudioProblem {
  type: string;
  description: string;
  severity: 'severe' | 'warning' | 'info';
}

interface AudioItem {
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

interface FolderNode {
  name: string;
  files: AudioItem[];
  folders: FolderNode[];
}

const props = defineProps<{
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
}>();

const emit = defineEmits<{
  (e: 'select', audio: AudioItem): void;
  (e: 'selectionChange', audioId: string | number): void;
  (e: 'bulkSelectionChange', audioIds: (string | number)[]): void;
  (e: 'search', query: string): void;
  (e: 'filterChange', filters: any): void;
  (e: 'preview', audioId: string | number): void;
  (e: 'edit', audioId: string | number): void;
  (e: 'delete', audioId: string | number): void;
  (e: 'convert', audioId: string | number): void;
  (e: 'download', audioId: string | number): void;
  (e: 'pageChange', page: number): void;
  (e: 'sizeChange', size: number): void;
  (e: 'toggleSelectAll'): void;
  (e: 'selectCurrentPage'): void;
  (e: 'deselectCurrentPage'): void;
  (e: 'deselectAll'): void;
  (e: 'view-change', mode: string): void;
  (e: 'toggleTag', tag: string, mode?: 'or' | 'and'): void;
}>();

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

const allTags = ref(props.allTags);

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

const expandedFolders = ref<Set<string>>(new Set(['音频文件']));

const showAudioPlayerModal = ref(false);
const currentAudioId = ref<string | number | null>(null);
const currentAudioTitle = ref('');
const currentAudioType = ref('dry');
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
  emit('filterChange', { ...filters.value });
}, { immediate: true });

watch(() => props.selectedAudios, (newSelected) => {
  localSelectedAudios.value = [...newSelected];
}, { deep: true });

watch(() => props.allTags, (newAllTags) => {
  allTags.value = [...newAllTags];
}, { deep: true });

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

const isFolderOpen = (folder: FolderNode) => {
  return checkFolderOpen(folder, expandedFolders.value);
};

const toggleFolder = (folder: FolderNode) => {
  toggleFolderState(folder, expandedFolders.value);
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
  if (!audioId) {
    alert('请先选择音频');
    return;
  }
  
  const audio = props.audios.find(a => a.id === audioId);
  if (audio) {
    currentAudioId.value = audioId;
    currentAudioTitle.value = audio.filename || '未知音频';
    currentAudioType.value = audio?.audioType || audio?.type || 'dry';
    showAudioPlayerModal.value = true;
  }
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
  // 使用父组件传递的完整标签列表，而不是从当前音频中提取
  allTags.value = [...props.allTags];
  folderTree.value = buildFolderTree(props.audios);
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg);
  background-color: var(--background-primary);
  border-bottom: var(--card-border);
}

.card-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.card-actions {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.view-toggle {
  display: flex;
  gap: var(--spacing-xs);
  background-color: var(--background-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-full);
  padding: var(--spacing-xs);
  box-shadow: var(--shadow-sm);
}

.view-toggle .btn {
  background: transparent;
  border: none;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--border-radius-full);
  cursor: pointer;
  transition: all var(--transition-normal);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.view-toggle .btn:hover {
  background-color: var(--background-primary);
  color: var(--primary-color);
}

.view-toggle .btn.active {
  background-color: var(--primary-color);
  color: var(--white-color);
  box-shadow: var(--shadow-sm);
}

.card-filter-section {
  padding: var(--spacing-lg);
  background-color: var(--background-primary);
  border-bottom: var(--card-border);
}

.search-section {
  margin-bottom: var(--spacing-lg);
}

.search-box {
  max-width: 600px;
}

.search-input::placeholder {
  color: var(--text-light);
}

.filter-panel {
  background-color: var(--background-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-normal);
}

.filter-panel:hover {
  box-shadow: var(--shadow-md);
}

.filter-content {
  transition: all var(--transition-normal);
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-lg);
  align-items: start;
}

.filter-item:nth-child(3) {
  grid-column: 3 / 4;
  grid-row: 1 / 3;
}

.filter-item.filter-actions-item {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--border-color);
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  min-width: 0;
}

.filter-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: color var(--transition-normal);
}

.filter-item:hover .filter-label {
  color: var(--primary-color);
}

.filter-select {
  border-radius: var(--border-radius-md);
  border: 1px solid var(--border-color);
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  background-color: var(--background-primary);
  color: var(--text-secondary);
  transition: all var(--transition-normal);
  min-height: auto;
  height: auto;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none'%3E%3Cpath d='M3.293 6.293a1 1 0 0 1 1.414 0L8 10.586l3.293-3.293a1 1 0 0 1 1.414 1.414l-4 4a1 1 0 0 1-1.414 0l-4-4a1 1 0 0 1 0-1.414z' fill='%236B7280'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right var(--spacing-sm) center;
  background-size: 16px 16px;
  position: relative;
  z-index: 1;
}

.tag-search-wrapper {
  margin-bottom: 8px;
  width: 100%;
  box-sizing: border-box;
}

.tag-search-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: all 0.2s ease;
  box-sizing: border-box;
  background: white;
}

.tag-search-input:focus {
  border-color: #1677FF;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.tag-search-input::placeholder {
  color: #94a3b8;
}

.tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  min-height: 80px;
  max-height: 180px;
  overflow-y: auto;
  width: 100%;
  box-sizing: border-box;
}

.tag-filter-item {
  padding: 6px 12px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.tag-filter-item:hover {
  background: #e2e8f0;
  color: #334155;
}

.tag-filter-item.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
}

.tag-filter-item.active.tag-or {
  background: #f97316;
  border-color: #f97316;
  box-shadow: 0 2px 8px rgba(249, 115, 22, 0.3);
}

.tag-filter-item.active.tag-and {
  background: #22c55e;
  border-color: #22c55e;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
}

.tag-mode-badge {
  margin-left: 4px;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.3);
  font-weight: 600;
}

.tag-mode-menu {
  position: fixed;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  min-width: 160px;
  overflow: hidden;
}

.tag-mode-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  color: #334155;
  transition: background 0.2s;
}

.tag-mode-menu-item:hover {
  background: #f1f5f9;
}

.tag-mode-menu-divider {
  height: 1px;
  background: #e2e8f0;
  margin: 4px 0;
}

.tag-mode-menu-item.remove {
  color: #ef4444;
}

.tag-mode-menu-item.remove:hover {
  background: #fef2f2;
}

.tag-mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 22px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}

.tag-mode-icon.or {
  background: #fff7ed;
  color: #f97316;
  border: 1px solid #fed7aa;
}

.tag-mode-icon.and {
  background: #f0fdf4;
  color: #22c55e;
  border: 1px solid #bbf7d0;
}

/* No Data Tip */
.no-data-tip {
  color: #94a3b8;
  font-size: 13px;
  font-style: italic;
  padding: 12px;
  text-align: center;
  width: 100%;
}

.filter-actions {
  display: flex;
  gap: var(--spacing-md);
}

.filter-actions .btn {
  min-width: 120px;
  padding: var(--spacing-sm) var(--spacing-xl);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  border-radius: var(--border-radius-full);
  transition: all var(--transition-normal);
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
}

.filter-actions .btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.filter-actions .btn-primary {
  background: var(--primary-gradient);
  border: none;
  color: var(--white-color);
}

.filter-actions .btn-secondary {
  background-color: var(--background-secondary);
  border: 2px solid var(--border-color);
  color: var(--text-primary);
}

.filter-actions .btn-secondary:hover {
  background-color: var(--background-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.card-body {
  padding: var(--spacing-lg);
  background-color: var(--background-primary);
}

.table-container {
  position: relative;
  overflow-x: auto;
  border-radius: var(--border-radius-md);
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--spacing-lg);
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  background-color: var(--background-primary);
}

.data-table {
  width: 100%;
  min-width: 800px;
  border-collapse: collapse;
  table-layout: auto;
  border-spacing: 0;
  transition: all var(--transition-normal);
}

.data-table th {
  background-color: var(--background-secondary);
  font-weight: var(--font-weight-semibold);
  text-align: left;
  padding: var(--spacing-sm) var(--spacing-md);
  position: sticky;
  top: 0;
  z-index: 10;
  white-space: normal;
  word-wrap: break-word;
  overflow: visible;
  text-overflow: clip;
  vertical-align: middle;
}

.data-table tbody tr {
  transition: background-color var(--transition-fast);
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
}

.data-table tbody tr:hover {
  background-color: var(--background-secondary);
}

.data-table tbody tr.highlighted {
  background-color: var(--primary-light);
}

.data-table td {
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-all;
  overflow: visible;
  text-overflow: clip;
  vertical-align: middle;
  padding: var(--spacing-sm) var(--spacing-md);
  min-height: 24px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 200px;
  overflow: visible;
  align-items: center;
}

.tags-container .tag-item {
  padding: 3px 8px;
  font-size: 11px;
  cursor: default;
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  border-radius: var(--border-radius-full);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-all;
  max-width: 100%;
}

.tags-container .tag-item:hover {
  background-color: var(--primary-light);
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: none;
  box-shadow: none;
}

.tags-container .tag-more {
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  background-color: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
  transition: all 0.2s ease;
}

.tags-container .tag-more:hover {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-color: var(--primary-color);
  border-style: solid;
}

.tags-container .tag-collapse {
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  background-color: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
  transition: all 0.2s ease;
}

.tags-container .tag-collapse:hover {
  background-color: var(--warning-light);
  color: var(--warning-color);
  border-color: var(--warning-color);
  border-style: solid;
}

.tags-container .no-tags {
  color: var(--text-light);
  font-size: 11px;
}

.audio-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.audio-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-radius: var(--border-radius-md);
  font-size: var(--font-size-xl);
}

.audio-details {
  flex: 1;
}

.audio-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-all;
}

.audio-path {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.format-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--border-radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
}

.format-badge.wav {
  background-color: var(--primary-light);
  color: var(--primary-color);
}

.format-badge.mp3 {
  background-color: var(--secondary-light);
  color: var(--secondary-color);
}

.format-badge.flac {
  background-color: var(--success-light);
  color: var(--success-color);
}

.format-badge.aac {
  background-color: var(--warning-light);
  color: var(--warning-color);
}

.audio-type-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--border-radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
}

.audio-type-badge.dry {
  background-color: var(--secondary-light);
  color: var(--secondary-color);
}

.audio-type-badge.noise {
  background-color: var(--warning-light);
  color: var(--warning-color);
}

.audio-type-badge.mixed {
  background-color: var(--info-light);
  color: var(--info-color);
}

.status-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--border-radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
}

.status-badge.active {
  background-color: var(--success-light);
  color: var(--success-color);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
  width: 100%;
  align-items: center;
  justify-content: center;
}

.action-buttons .btn {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-xs);
  width: auto;
  min-width: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
}

.btn-primary {
  background: var(--primary-gradient);
  border: none;
  color: var(--white-color);
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
  box-shadow: var(--shadow-sm);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-secondary {
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
  box-shadow: var(--shadow-sm);
}

.btn-secondary:hover {
  background-color: var(--background-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-danger {
  background-color: var(--danger-color);
  border: none;
  color: var(--white-color);
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
  box-shadow: var(--shadow-sm);
}

.btn-danger:hover {
  background-color: var(--danger-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-icon {
  margin-right: 4px;
}

.folder-view {
  background-color: var(--background-primary);
  border-radius: var(--border-radius-md);
  overflow: hidden;
  padding: var(--spacing-md);
  max-height: 600px;
  overflow-y: auto;
}

.folder-tree {
  padding: 0;
}

.folder-node {
  margin-bottom: var(--spacing-xs);
}

.folder-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.folder-header:hover {
  background-color: var(--background-tertiary);
  border-color: var(--primary-color);
}

.folder-header i {
  color: var(--primary-color);
  font-size: var(--font-size-md);
  transition: transform var(--transition-normal);
}

.folder-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  flex: 1;
}

.folder-stats {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  font-weight: var(--font-weight-normal);
}

.folder-children {
  margin-left: var(--spacing-lg);
  padding-left: var(--spacing-md);
  border-left: 2px solid var(--border-color);
}

.folder-content {
  margin-top: var(--spacing-xs);
}

.file-list {
  margin-top: var(--spacing-sm);
  background-color: var(--background-primary);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  margin-bottom: var(--spacing-xs);
  transition: all var(--transition-normal);
  cursor: pointer;
}

.file-item:hover {
  background-color: var(--background-secondary);
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.file-item.highlighted {
  background-color: var(--primary-light);
  border-color: var(--primary-color);
}

.file-icon {
  color: var(--primary-color);
  font-size: var(--font-size-lg);
  width: 24px;
  text-align: center;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.file-meta {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.file-meta span {
  font-size: var(--font-size-xs);
}

.file-actions {
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0.7;
  transition: opacity var(--transition-normal);
}

.file-item:hover .file-actions {
  opacity: 1;
}

.file-actions .btn {
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-xs);
  min-width: auto;
  height: auto;
}

.audio-checkbox {
  accent-color: var(--primary-color);
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.diagnostics-view {
  padding: var(--spacing-lg);
  background-color: var(--background-primary);
}

.diagnostics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: var(--card-border);
}

.diagnostics-stats {
  display: flex;
  gap: var(--spacing-lg);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.stat-number {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--warning-color);
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.diagnostics-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.no-problems {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  text-align: center;
}

.success-icon {
  font-size: var(--font-size-3xl);
  color: var(--success-color);
  margin-bottom: var(--spacing-md);
}

.diagnostics-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  transition: all var(--transition-normal);
}

.diagnostics-item:hover {
  border-color: var(--warning-color);
  box-shadow: var(--shadow-md);
}

.audio-basic-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.audio-problems {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-left: 54px;
}

.problem-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--border-radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.problem-item.severe {
  background-color: var(--danger-light);
  color: var(--danger-color);
  border: 1px solid var(--danger-color);
}

.problem-item.warning {
  background-color: var(--warning-light);
  color: var(--warning-color);
  border: 1px solid var(--warning-color);
}

.problem-item.info {
  background-color: var(--info-light);
  color: var(--info-color);
  border: 1px solid var(--info-color);
}

.diagnostics-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-left: 54px;
}

.diagnostics-actions .btn {
  font-size: var(--font-size-sm);
  padding: var(--spacing-sm) var(--spacing-md);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-md);
  color: var(--text-light);
}
</style>
