<template>
  <div class="case-card" :class="{ 'card-selected': isSelected }" @click="() => { if (testCase) { console.log('[TestCaseManager] 点击测试用例卡片: 选择/取消选择测试用例 ' + testCase.name + ' (ID: ' + testCase.id + '), 时间:', new Date().toISOString()); toggleSelection(); } }">
    <!-- 只有当testCase为有效对象时才渲染内容 -->
    <template v-if="testCase">
      <div class="case-header">
        <div class="case-info-wrapper">
          <input 
            v-if="showCheckbox"
            type="checkbox" 
            id="checkbox-{{ testCase.id }}" 
            class="test-case-checkbox"
            @change="() => { console.log('[TestCaseManager] 点击测试用例复选框: 选择/取消选择测试用例 ' + testCase.name + ' (ID: ' + testCase.id + '), 时间:', new Date().toISOString()); toggleSelection(); }"
            @click.stop
            :checked="isSelected"
            tabindex="0"
          >
          <div class="case-info">
            <div class="case-name-status">
            <div class="case-name-wrapper">
              <div class="case-name" >
              {{ truncatedName }}
              <div class="case-name-tooltip">{{ testCase.name }}</div>
              <!-- 根据type数组显示对应的标签 -->
              <div class="test-type-tags">
                <span 
                  v-for="(type, index) in (testCase.type ? (Array.isArray(testCase.type) ? testCase.type : [testCase.type]) : [])" 
                  :key="index"
                  class="test-type-tag"
                  :class="{
                    'tag-api': type === 'api',
                    'tag-e2e': type === 'e2e'
                  }"
                >
                  {{ type === 'api' ? 'API测试' : (type === 'e2e' ? 'E2E测试' : type) }}
                </span>
                <!-- 算法类型标签 -->
                <span 
                  v-if="testCase.algorithmType"
                  class="test-type-tag tag-algorithm"
                  :class="getAlgorithmTagClass(testCase.algorithmType)"
                >
                  {{ getAlgorithmTypeText(testCase.algorithmType) }}
                </span>
              </div>
            </div>
            </div>
          </div>
            <div class="case-id-row">
              <span
                class="case-id-badge"
                :title="idCopied ? '已复制' : '点击复制ID'"
                @click.stop="copyCaseId"
                @keydown.enter.prevent.stop="copyCaseId"
                tabindex="0"
                role="button"
                :aria-label="`用例ID: ${testCase.id}, 点击复制`"
              >
                <i class="fas fa-copy"></i> 用例ID: {{ testCase.id }}
                <span class="case-id-copied" v-if="idCopied">已复制</span>
              </span>
            </div>
            <div class="case-description">{{ testCase.description || '' }}</div>
            <div v-if="testCase.lastEditTime || testCase.createdAt || testCase.updatedAt" style="margin-bottom: 8px; font-size: 12px; color: var(--text-secondary);">
              <span class="meta-label">最后编辑时间:</span> {{ testCase.lastEditTime || testCase.updatedAt || testCase.createdAt || '未知' }}
            </div>
            <div v-if="testCase.totalDuration" class="case-duration-info">
              <span class="duration-tag">{{ formatDuration(testCase.totalDuration) }}</span>
            </div>
            <div v-if="roundCount > 0" class="case-duration-info">
              <span class="round-count-tag" title="用例轮次数量">
                <i class="fas fa-layer-group"></i> {{ roundCount }} 轮
              </span>
            </div>
            <div class="case-tags-container" v-if="testCase.tags && testCase.tags.length > 0">
              <template v-if="!isTagsExpanded">
                <span v-for="(tag, index) in visibleTags" :key="index" class="tag">{{ tag }}</span>
                <span 
                  v-if="hasMoreTags" 
                  class="tag-more"
                  @click.stop="toggleTagsExpansion"
                  @keydown.enter="toggleTagsExpansion"
                  @keydown.space.prevent="toggleTagsExpansion"
                  tabindex="0"
                  role="button"
                  :aria-expanded="isTagsExpanded"
                >+{{ testCase.tags.length - maxVisibleTags }}</span>
              </template>
              <template v-else>
                <span v-for="(tag, index) in testCase.tags" :key="index" class="tag">{{ tag }}</span>
                <span 
                  class="tag-collapse"
                  @click.stop="toggleTagsExpansion"
                  @keydown.enter="toggleTagsExpansion"
                  @keydown.space.prevent="toggleTagsExpansion"
                  tabindex="0"
                  role="button"
                  :aria-expanded="isTagsExpanded"
                >收起</span>
              </template>
            </div>
          </div>
        </div>
          <div class="case-actions" v-if="actions && actions.length > 0">
            <button 
              v-for="action in actions" 
              :key="action.id"
              class="btn-icon-only"
              @click.stop="() => { console.log('[TestCaseManager] 点击测试用例操作按钮: ' + (action.title || action.label) + ' - 测试用例 ' + testCase.name + ' (ID: ' + testCase.id + '), 时间:', new Date().toISOString()); handleAction(action); }"
              :disabled="action.disabled"
              :title="action.title || action.label"
            >
              <i v-if="action.icon" :class="`fas ${action.icon}`"></i>
            </button>
          </div>
      </div>
      
      <div v-if="showConfig && testCase.config" class="case-config-container">
        <div class="config-header" @click.stop="toggleConfigExpansion" @keydown.enter="toggleConfigExpansion" @keydown.space.prevent="toggleConfigExpansion" tabindex="0" role="button" :aria-expanded="isConfigExpanded">
          <h5 class="config-toggle-title">
            <i :class="`fas ${isConfigExpanded ? 'fa-chevron-down' : 'fa-chevron-right'} config-arrow`"></i>
            测试配置
          </h5>
        </div>
        <div class="case-config" v-if="isConfigExpanded">
          <div class="config-section">
            <h5 class="config-title">{{ testCase.testType === 'e2e' || testCase.type === 'e2e' ? 'E2E测试配置' : 'API测试配置' }}</h5>
            <div class="config-details">
              <div class="config-row">
                <span class="config-label">轮次:</span>
                <span>{{ testCase.config?.rounds?.length || 0 }} 个</span>
              </div>
              <div class="config-row">
                <span class="config-label">音频:</span>
                <span>{{ getAudioCount(testCase.config) }} 个</span>
              </div>
              <div class="config-row">
                <span class="config-label">评测维度:</span>
                <span>{{ testCase.config?.dimensions?.length || 0 }} 个</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useAlgorithmLabels } from '../../../composables/algorithm/useAlgorithmLabels';
import { copyToClipboard } from '../../../utils/utils';

const { loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels();

onMounted(() => {
  loadAlgorithms();
});

const props = defineProps({
  testCase: { type: Object, required: true },
  isSelected: { type: Boolean, default: false },
  showCheckbox: { type: Boolean, default: true },
  showConfig: { type: Boolean, default: true },
  actions: { type: Array, default: () => [] }
});

const emit = defineEmits(['toggle-selection', 'action']);

const isTagsExpanded = ref(false);
const isConfigExpanded = ref(true);
const idCopied = ref(false);
let idCopiedTimer = null;

const roundCount = computed(() => {
  const tc = props.testCase;
  if (!tc) return 0;
  if (tc.config?.rounds && Array.isArray(tc.config.rounds)) return tc.config.rounds.length;
  if (tc.rounds && Array.isArray(tc.rounds)) return tc.rounds.length;
  if (tc.algorithm_params && Array.isArray(tc.algorithm_params)) return tc.algorithm_params.length;
  if (tc.reference_params && Array.isArray(tc.reference_params)) return tc.reference_params.length;
  return 0;
});

const truncatedName = computed(() => {
  const name = props.testCase.name;
  if (!name || name.length <= 80) return name;
  const start = name.substring(0, 40);
  const end = name.substring(name.length - 40);
  return `${start}...${end}`;
});

const toggleSelection = () => {
  emit('toggle-selection', props.testCase.id);
};

const copyCaseId = async () => {
  const id = props.testCase?.id;
  if (id === undefined || id === null) return;
  const ok = await copyToClipboard(String(id));
  if (ok) {
    idCopied.value = true;
    if (idCopiedTimer) clearTimeout(idCopiedTimer);
    idCopiedTimer = setTimeout(() => {
      idCopied.value = false;
    }, 1500);
  }
};

const handleAction = (action) => {
  emit('action', { action, testCase: props.testCase });
};

const getStatusText = (status) => {
  const statusMap = { pending: '待处理', 'in-progress': '进行中', completed: '已完成', failed: '执行失败', deleted: '已删除' };
  return statusMap[status] || status;
};

const formatDuration = (seconds) => {
  if (seconds === undefined || seconds === null || seconds === 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds.toFixed(1)}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
};

const getAudioCount = (config) => {
  if (!config) return 0;
  // Rounds format
  if (config.rounds && Array.isArray(config.rounds)) {
    return config.rounds.reduce((total, round) => {
      return total + (Array.isArray(round.audios) ? round.audios.length : 0);
    }, 0);
  }
  // Legacy flat format
  return config.audios?.length || 0;
};

const getAlgorithmTypeText = (type) => {
  return getAlgorithmLabel(type);
};

const getAlgorithmTagClass = (type) => {
  const classMap = {
    'translation': 'tag-translation',
    'asr': 'tag-asr',
    'speaker_recognition': 'tag-speaker-recognition',
    'tts': 'tag-tts',
    'vad': 'tag-vad',
    'diarization': 'tag-diarization'
  };
  return classMap[type] || '';
};

const toggleTagsExpansion = () => {
  isTagsExpanded.value = !isTagsExpanded.value;
};

const toggleConfigExpansion = () => {
  isConfigExpanded.value = !isConfigExpanded.value;
};

const getMaxVisibleTags = () => {
  return 8;
};

const maxVisibleTags = ref(getMaxVisibleTags());
const visibleTags = computed(() => {
  if (!props.testCase.tags) return [];
  return props.testCase.tags.slice(0, maxVisibleTags.value);
});
const hasMoreTags = computed(() => {
  if (!props.testCase.tags) return false;
  return props.testCase.tags.length > maxVisibleTags.value;
});

onMounted(() => {
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  if (idCopiedTimer) clearTimeout(idCopiedTimer);
});

watch(() => props.testCase?.tags, () => {
  isTagsExpanded.value = false;
});

const handleResize = () => {
  maxVisibleTags.value = getMaxVisibleTags();
  isTagsExpanded.value = false;
};
</script>

<style scoped>
.case-name-wrapper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  max-width: 100%;
  min-width: 0;
  gap: 8px;
}

.case-name {
  white-space: normal;
  word-break: break-word;
  position: relative;
  flex: 1;
  min-width: 0;
}

.case-name-tooltip {
  position: absolute;
  left: 0;
  bottom: 100%;
  background-color: var(--text-primary);
  color: white;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  white-space: normal;
  word-break: break-all;
  max-width: 400px;
  z-index: 10000;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
  margin-bottom: 4px;
  box-shadow: var(--shadow-lg);
}

.case-name-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 16px;
  border-width: 6px;
  border-style: solid;
  border-color: var(--text-primary) transparent transparent transparent;
}

.case-name:hover .case-name-tooltip {
  opacity: 1;
}

/* 测试类型标签样式 */
.test-type-tags {
  display: inline-flex;
  gap: 6px;
  margin-left: 8px;
  vertical-align: middle;
}

.test-type-tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  color: white;
}

.tag-api {
  background-color: #1677FF;
}

.tag-e2e {
  background-color: #FF6A00;
}

/* 算法类型标签样式 */
.tag-algorithm {
  background-color: #8b5cf6;
}

.tag-translation {
  background-color: #8b5cf6;
}

.tag-asr {
  background-color: #06b6d4;
}

.tag-speaker-recognition {
  background-color: #f59e0b;
}

.tag-tts {
  background-color: #10b981;
}

.tag-vad {
  background-color: #6366f1;
}

.tag-diarization {
  background-color: #ec4899;
}

/* 用例卡片音频时长信息 */
.case-duration-info {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.duration-tag {
  display: inline-block;
  background-color: #FF6A00;
  color: white;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 12px;
  min-width: 20px;
  text-align: center;
}

.round-count-tag {
  display: inline-block;
  background-color: #6366f1;
  color: white;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 用例ID徽章 - 点击可复制 */
.case-id-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.case-id-badge {
  padding: 2px 10px;
  background: white;
  color: #1677ff;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.case-id-badge:hover,
.case-id-badge:focus-visible {
  background: #f8fafc;
  color: #1677ff;
  outline: none;
}

.case-id-badge:active {
  transform: translateY(1px);
}

.case-id-badge .fa-copy {
  font-size: 10px;
}

.case-id-copied {
  color: #16a34a;
  font-weight: 600;
  margin-left: 2px;
}
</style>

