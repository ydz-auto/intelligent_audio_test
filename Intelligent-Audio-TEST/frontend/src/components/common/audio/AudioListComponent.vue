<template>
  <div class="audio-list-component">
    <!-- 卡片头部 -->
    <div class="card-header">
      <h3 class="card-title">音频文件列表</h3>
      <div class="card-actions">
        <slot name="header-actions"></slot>
        <div class="view-toggle" role="group" aria-label="视图切换">
          <button type="button"
            class="btn btn-secondary"
            :class="{ active: viewMode === 'list' }"
            @click="switchView('list')"
            :aria-pressed="viewMode === 'list'"
            title="列表视图"
          >
            <i class="fas fa-list"></i>
          </button>
          <button type="button"
            class="btn btn-secondary"
            :class="{ active: viewMode === 'folder' }"
            @click="switchView('folder')"
            :aria-pressed="viewMode === 'folder'"
            title="文件夹视图"
          >
            <i class="fas fa-folder"></i>
          </button>
          <button type="button"
            class="btn btn-secondary"
            :class="{ active: viewMode === 'diagnostics' }"
            @click="switchView('diagnostics')"
            :aria-pressed="viewMode === 'diagnostics'"
            title="诊断视图"
          >
            <i class="fas fa-exclamation-triangle"></i>
          </button>
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
          <FolderNodeComponent
            :folder="activeFolderTree"
            :enable-selection="enableSelection"
            :is-selected-fn="isSelected"
            :is-folder-all-selected-fn="props.isFolderAllSelectedFn"
            :is-folder-partial-selected-fn="props.isFolderPartialSelectedFn"
            @toggle-folder="toggleFolder"
            @expand-folder="(path: string) => emit('expand-folder', path)"
            :expanded-paths="expandedFolderPaths"
            @toggle-audio-selection="toggleAudioSelection"
            @toggle-folder-selection="(folder: any) => emit('toggle-folder-selection', folder)"
            @preview="previewAudio"
            @edit="editMetadata"
            @delete="deleteAudio"
          />
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
    <div class="pagination-container" v-if="props.totalAudios > 0 && viewMode === 'list'">
      <PaginationComponent
        :total-items="props.totalAudios"
        :page-size="props.pageSize"
        :current-page="props.currentPage"
        @go-to-page="handlePageChange"
        @page-size-change="handleSizeChange"
      />
    </div>
    
  </div>
</template>

<script setup lang="ts">
import FolderNodeComponent from '../misc/FolderNodeComponent.vue';
import PaginationComponent from '../data/PaginationComponent.vue';
import { useAudioListComponent } from './AudioListComponent';
import type { AudioItem, AudioListProps } from './AudioListComponent';

const props = defineProps<AudioListProps>();

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
  (e: 'expand-folder', folderPath: string): void;
  (e: 'toggle-folder-selection', folder: any): void;
}>();

const {
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
} = useAudioListComponent(props, emit)
</script>

<style scoped>
@import './AudioListComponent.css';
</style>
