<template>
  <div class="case-card" :class="{ 'card-selected': isSelected, 'card-disabled': isDeleted }" @click="handleCardClick">
    <template v-if="testCase">
      <div class="case-card__body">
        <!-- 名称行前导（报告状态指示点等） -->
        <slot name="leading" />
        <div class="case-card__main">
          <!-- 名称行 + 行内操作区 -->
          <div class="case-card__head">
            <div class="case-name-status">
              <input
                v-if="showCheckbox"
                type="checkbox"
                class="test-case-checkbox"
                :checked="isSelected"
                @change="toggleSelection"
                @click.stop
                tabindex="0"
                :aria-label="`选择 ${testCase.name}`"
              />
              <span
                v-if="nameClickable"
                class="case-name case-name--clickable"
                role="button"
                tabindex="0"
                :title="'查看用例详情'"
                @click.stop="emit('name-click', testCase)"
                @keydown.enter.prevent.stop="emit('name-click', testCase)"
              >{{ truncatedName }}</span>
              <span v-else class="case-name" :title="testCase.name">{{ truncatedName }}</span>
              <span class="case-name-tooltip">{{ testCase.name }}</span>
              <!-- INT-423/467：可见性徽标（列表行私有标识） -->
              <VisibilityBadge :visibility="testCase.visibility" />
              <!-- 名称旁附加（报告分类 Badge / 复核 Badge 等） -->
              <slot name="titleExtra" />
              <CaseIdBadge
                v-if="testCase.id"
                :case-id="testCase.id"
                class="case-id-row"
              />
            </div>
            <div class="case-actions" v-if="hasActions || $slots.actions">
              <!-- 右操作区自定义（报告下载日志/固定/展开、任务移除等）；缺省=actions 行内按钮 -->
              <slot name="actions">
                <button
                  v-for="action in cardActions"
                  :key="action.id"
                  class="btn-icon-only"
                  @click.stop="handleAction(action)"
                  :disabled="action.disabled"
                  :title="action.title || action.label"
                >
                  <i v-if="action.iconClass || action.icon" :class="action.iconClass || `fas ${action.icon}`" :style="action.iconStyle"></i>
                </button>
              </slot>
            </div>
          </div>

          <!-- 次行：描述/最后编辑时间（meta 插槽可整体替代；回收站态换 删除时间/删除人） -->
          <div v-if="!hideMeta" class="case-card__meta">
            <slot name="meta">
              <div class="case-description">{{ testCase.description || '—' }}</div>
              <div class="case-meta-line"><span class="meta-label">最后编辑时间:</span> {{ lastEditTime }}</div>
              <div v-if="isDeleted" class="case-deleted-meta">
                <span><span class="meta-label">删除时间:</span> {{ testCase.deletedAt ? formatDate(testCase.deletedAt) : '—' }}</span>
                <span><span class="meta-label">删除人:</span> {{ deletedByLabel }}</span>
              </div>
            </slot>
          </div>

          <!-- 徽章行：算法 / 时长 / 轮次（数据缺省不落空徽章）+ 徽章行前导 -->
          <div v-if="!hideBadges && hasBadges" class="case-card__badges case-duration-info">
            <slot name="badgeLeading" />
            <span v-if="testCase.algorithmType" class="test-type-tag tag-algorithm" :class="getAlgorithmTagClass(testCase.algorithmType)">
              {{ getAlgorithmTypeText(testCase.algorithmType) }}
            </span>
            <span v-if="totalDuration > 0" class="duration-tag" title="用例总时长">
              <i class="fas fa-clock"></i> {{ formatDurationLong(totalDuration) }}
            </span>
            <span v-if="roundCount > 0" class="round-count-tag" title="用例轮次数量">
              <i class="fas fa-layer-group"></i> {{ roundCount }} 轮
            </span>
          </div>

          <!-- 标签行（≤6 折叠 +N 展开/收起；有登记色走数据驱动色） -->
          <div v-if="tagList.length > 0" class="case-tags-container">
            <div class="case-tags">
              <span
                v-for="tag in shownTags"
                :key="tag"
                class="tag"
                :class="{ 'tag--colored': tagStyle(tag).background }"
                :style="tagStyle(tag)"
              >
                <span v-if="tagCategory(tag)" class="tag-category">{{ tagCategory(tag) }}</span>
                {{ tag }}
              </span>
              <span
                v-if="hiddenCount > 0 && !isTagsExpanded"
                class="tag-more"
                role="button"
                tabindex="0"
                :aria-expanded="isTagsExpanded"
                @click.stop="toggleTagsExpansion"
                @keydown.enter="toggleTagsExpansion"
                @keydown.space.prevent="toggleTagsExpansion"
              >+{{ hiddenCount }}</span>
              <span
                v-if="isTagsExpanded && hiddenCount > 0"
                class="tag-collapse"
                role="button"
                tabindex="0"
                :aria-expanded="isTagsExpanded"
                @click.stop="toggleTagsExpansion"
                @keydown.enter="toggleTagsExpansion"
                @keydown.space.prevent="toggleTagsExpansion"
              >收起</span>
            </div>
          </div>

          <!-- 底栏（任务人工/AI 复核入口等） -->
          <slot name="footer" />
        </div>
      </div>
      <!-- 展开详情（报告 CaseReportDetail 等） -->
      <slot name="expandedContent" />
    </template>
  </div>
</template>

<script setup>
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'
import "../../../assets/styles/components/test-case-card.css"
import { ref, computed, watch, useSlots } from 'vue';
import { useAlgorithmLabels } from '../../../composables/algorithm/useAlgorithmLabels';
import CaseIdBadge from '../CaseIdBadge.vue';
// INT-423/467：可见性徽标（列表行私有标识）
import VisibilityBadge from '../visibility/VisibilityBadge.vue';
import { formatDate } from '../../../utils/utils';

/**
 * 全站统一用例展示组件（11_用例域.md §3.3 全站用例显示统一口径，INT-1103）。
 * 用例管理（分组视图/标签视图）、开始测试用例选择、报告具体用例、任务详情关联用例、
 * 挑选/购物车 compact 变体（PickCaseCard.vue）一律照本卡字段口径呈现用例信息，不另造平铺文本行。
 *
 * 公共字段（§3.3，React CaseCard 等价移植）：
 * - 卡头：勾选框 + 名称（超长 tooltip 截断，可点击开详情）+ ID 徽章（点击复制）+
 *   titleExtra 插槽（上下文附加，如报告分类/复核 Badge）；
 * - 次行：描述/最后编辑时间（回收站态换 删除时间/删除人元信息；meta 插槽可整体替代）；
 * - 徽章行：算法（getAlgorithmLabel）+ 时长/轮次（数据缺省不落空徽章）+ badgeLeading 上下文前导；
 * - 标签行：≤6 折叠 +N 展开/收起（有登记表色走数据驱动色 + 分类角标）；
 * - 行内操作区：actions 插槽/属性由消费方提供（用例管理=行内五钮，报告=下载/复核，任务=移除…），
 *   缺省为空——本卡不内建操作按钮（去行内五钮口径，INT-1103）；
 * - footer 底栏（任务人工/AI 复核入口）、expandedContent 展开详情（报告 TestCaseReportDetail）。
 * INT-486 用例不分类型口径：不落「类型徽章」（V9.7.10 基准含类型徽章，口径定稿移除）。
 */

const props = defineProps({
  testCase: { type: Object, required: true },
  isSelected: { type: Boolean, default: false },
  showCheckbox: { type: Boolean, default: true },
  /** 标签登记表（name → {color, categoryName}；缺省空表走灰色兜底） */
  tagRegistry: { type: Array, default: () => [] },
  /** 行内操作（静态数组或 (testCase) => actions 工厂函数；缺省空 = 不渲染操作区） */
  actions: { type: [Array, Function], default: () => [] },
  /** 名称可点击（任务域开用例详情弹窗） */
  nameClickable: { type: Boolean, default: false },
  /** 隐藏次行（描述/最后编辑时间；报告侧无此数据不落空行） */
  hideMeta: { type: Boolean, default: false },
  /** 隐藏徽章行（算法/时长/轮次） */
  hideBadges: { type: Boolean, default: false },
  /** 兼容旧调用方（V9.7.10 配置折叠已按 React 口径移除，本 prop 仅吞参不渲染） */
  showConfig: { type: Boolean, default: false },
});

const emit = defineEmits(['toggle-selection', 'action', 'name-click', 'copy-id']);

const { loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels();
loadAlgorithms();

/** actions 为工厂函数时按当前卡片用例求值（收藏星标按 isFavorite 动态生成），静态数组原样透传。 */
const cardActions = computed(() => {
  if (typeof props.actions === 'function') return props.actions(props.testCase);
  return props.actions;
});

const hasActions = computed(() => {
  const a = cardActions.value;
  return Array.isArray(a) && a.length > 0;
});

/** 删除人展示：后端返回 deletedByUserId；AUTH_MODE=off 时为 NULL 显示「—」 */
const deletedByLabel = computed(() => {
  const uid = props.testCase?.deletedByUserId;
  return uid !== undefined && uid !== null ? `用户 #${uid}` : '—';
});

const isDeleted = computed(() => props.testCase?.deleted === true);

const isTagsExpanded = ref(false);

const roundCount = computed(() => {
  const tc = props.testCase;
  if (!tc) return 0;
  if (tc.config?.rounds && Array.isArray(tc.config.rounds)) return tc.config.rounds.length;
  if (tc.rounds && Array.isArray(tc.rounds)) return tc.rounds.length;
  const algoParams = tc.algorithmParams;
  if (algoParams && Array.isArray(algoParams)) return algoParams.length;
  const refParams = tc.referenceParams;
  if (refParams && Array.isArray(refParams)) return refParams.length;
  return 0;
});

const totalDuration = computed(() => props.testCase?.totalDuration ?? 0);

const truncatedName = computed(() => {
  const name = props.testCase.name;
  if (!name || name.length <= 80) return name;
  const start = name.substring(0, 40);
  const end = name.substring(name.length - 40);
  return `${start}...${end}`;
});

/** INT-1103 返工 P3-2：最后编辑时间按 React CaseCard 口径展示——ISO 截取至分钟（2026-10-21T07:48:51 → 2026-10-21 07:48）；无值回退 '—' */
const lastEditTime = computed(() => {
  const tc = props.testCase;
  const raw = tc.lastEditTime || tc.updatedAt || tc.createdAt;
  if (!raw) return '—';
  const s = String(raw);
  // 对齐 React：slice(0,16) + T→空格；非 ISO 字符串原样透传
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) ? s.slice(0, 16).replace('T', ' ') : s;
});

const toggleSelection = () => {
  emit('toggle-selection', props.testCase.id);
};

const handleCardClick = () => {
  // 仅勾选态可交互：showCheckbox=false（报告/挑选 compact 等只读上下文）点击不触发选择
  if (props.testCase && props.showCheckbox) {
    toggleSelection();
  }
};

const handleAction = (action) => {
  emit('action', { action, testCase: props.testCase });
};

const formatDurationLong = (seconds) => {
  if (seconds === undefined || seconds === null || seconds === 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds.toFixed(1)}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
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

/** 卡内标签展示上限（对齐 React CaseCard MAX_VISIBLE_TAGS 语义：超限折叠 +N 展开/收起） */
const MAX_VISIBLE_TAGS = 6;

const tagList = computed(() => {
  const t = props.testCase?.tags;
  if (!Array.isArray(t)) return [];
  return t.map((x) => (typeof x === 'object' && x && x.name) ? x.name : String(x)).filter(Boolean);
});

const registry = computed(() => {
  const m = new Map();
  for (const item of props.tagRegistry || []) {
    if (item && item.name) m.set(String(item.name), item);
  }
  return m;
});

/** 标签分类名角标（数据驱动；未登记为 null） */
const tagCategory = (name) => {
  const item = registry.value.get(String(name));
  return item?.categoryName ?? null;
};

/** 标签数据驱动色（内联 style；未登记/无色走灰色兜底类） */
const tagStyle = (name) => {
  const item = registry.value.get(String(name));
  if (item?.color) return { backgroundColor: item.color };
  return {};
};

const shownTags = computed(() => {
  if (isTagsExpanded.value) return tagList.value;
  return tagList.value.slice(0, MAX_VISIBLE_TAGS);
});

const hiddenCount = computed(() => Math.max(0, tagList.value.length - MAX_VISIBLE_TAGS));

const slots = useSlots();

/** 徽章行是否有可渲染内容（数据缺省不落空徽章；badgeLeading 插槽存在即渲染，对齐 React hasBadges 口径） */
const hasBadges = computed(() => {
  const tc = props.testCase;
  return Boolean(slots.badgeLeading) || Boolean(tc?.algorithmType) || (totalDuration.value > 0) || (roundCount.value > 0);
});

const toggleTagsExpansion = () => {
  isTagsExpanded.value = !isTagsExpanded.value;
};

watch(() => props.testCase?.tags, () => {
  isTagsExpanded.value = false;
});
</script>

<style scoped>
.case-name {
  white-space: normal;
  word-break: break-word;
  position: relative;
  flex: 1;
  min-width: 0;
  font-weight: 500;
}

.case-name--clickable {
  cursor: pointer;
}
.case-name--clickable:hover {
  color: var(--primary);
}

.case-name-tooltip {
  position: absolute;
  left: 0;
  bottom: 100%;
  background-color: var(--foreground);
  color: white;
  padding: 8px 12px;
  border-radius: var(--radius-control);
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
  border-color: var(--foreground) transparent transparent transparent;
}

.case-name:hover .case-name-tooltip {
  opacity: 1;
}

/* 卡主体布局（对齐 React CaseCard：flex items-start + 主列 + 操作列） */
.case-card__body {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.case-card__main {
  flex: 1;
  min-width: 0;
}

.case-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

/* 行内操作区（消费方经 actions 插槽/属性注入；flex 布局收口于本卡，不再依赖消费方全局样式） */
.case-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: flex-end;
  flex-shrink: 0;
}

@media (max-width: 1024px) {
  .case-actions {
    align-self: flex-end;
  }
}

/* 次行元信息（描述/最后编辑时间/删除元信息） */
.case-card__meta {
  margin-top: 6px;
}

.case-meta-line {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted-foreground);
}

/* 徽章行（算法/时长/轮次；前导 slot 由消费方注入） */
.case-card__badges {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.case-card__badges .test-type-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 算法徽章（复用既有 token 色） */
.tag-algorithm {
  background-color: var(--color-violet-500);
}

.tag-translation { background-color: var(--color-violet-500); }
.tag-asr { background-color: var(--color-cyan-500); }
.tag-speaker-recognition { background-color: var(--color-amber-500); }
.tag-tts { background-color: var(--color-emerald-500); }
.tag-vad { background-color: var(--color-indigo-500); }
.tag-diarization { background-color: var(--color-pink-500); }

/* 标签数据驱动色 + 分类角标（无登记色走 .case-tags .tag 灰色兜底） */
.tag--colored {
  color: white;
  border: none;
}

.tag-category {
  font-size: 10px;
  opacity: 0.85;
  margin-right: 2px;
}

/* meta-label - 自全局样式就近迁移 */
.meta-label {
  font-size: var(--font-size-xs);
  color: var(--foreground);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-right: 4px;
  white-space: nowrap;
}

.case-deleted-meta {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted-foreground);
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  min-width: 0;
}

.case-deleted-meta .meta-label {
  margin-right: 4px;
}

.case-duration-info .duration-tag,
.case-duration-info .round-count-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 回收站态整卡 muted 底（对齐 React disabled 口径） */
.case-card.card-disabled {
  background-color: var(--muted);
  color: var(--muted-foreground);
}
</style>
