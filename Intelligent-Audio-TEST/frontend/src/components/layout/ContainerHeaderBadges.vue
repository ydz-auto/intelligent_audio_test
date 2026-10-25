<template>
  <div v-if="source" ref="rootEl" class="container-header-badges">
    <!-- 名称右侧：合并方式徽章 + 混合态徽章（规范 18 §2.2） -->
    <div class="chb-badges">
      <span class="chb-badge chb-badge--merge-type">{{ mergeTypeText }}</span>
      <span
        v-if="mixedState"
        class="chb-badge"
        :class="mixedState.className"
        :title="mixedState.title"
      >{{ mixedState.text }}</span>
    </div>

    <!-- 结构化摘要：来源 / 结果 / 用例 + 创建时间（替代描述字段里的「挑选合并自 n 个来源任务」堆叠） -->
    <div class="chb-stats">
      <div class="chb-source">
        <button
          type="button"
          class="chb-stat chb-stat--action"
          :class="{ 'is-open': popoverOpen }"
          :aria-expanded="popoverOpen ? 'true' : 'false'"
          :title="`查看 ${sourceTaskCount} 个来源任务`"
          @click.stop="togglePopover"
        >
          <i class="fas fa-code-branch"></i>
          来源 {{ sourceTaskCount }} 个任务
          <i class="fas fa-chevron-down chb-caret" :class="{ 'is-open': popoverOpen }"></i>
        </button>

        <!-- 就地浮层（不 teleport，避免模态窗内被遮罩盖住——INT-1106 教训） -->
        <div v-if="popoverOpen" class="chb-popover" role="dialog" aria-label="来源任务" @click.stop>
          <div class="chb-popover-title">来源任务</div>
          <div v-if="source.groups.length === 0" class="chb-popover-empty">无来源任务记录</div>
          <div
            v-for="group in source.groups"
            :key="group.sourceTaskId"
            class="chb-popover-row"
          >
            <span class="chb-popover-name" :title="group.sourceTaskName">{{ group.sourceTaskName }}</span>
            <span class="chb-popover-count">{{ group.results.length }} 条</span>
          </div>
        </div>
      </div>
      <span class="chb-stat">结果 {{ sourceResultCount }} 条</span>
      <span class="chb-stat">用例 {{ caseCount }} 个</span>
      <span v-if="createdAtText" class="chb-created">创建时间 {{ createdAtText }}</span>
    </div>
  </div>
</template>

<script setup>
/**
 * ContainerHeaderBadges —— 挑选合并容器详情信息头（INT-1832 · 规范 18 §2.2）。
 *
 * 只读展示：合并方式徽章、来源任务 Popover、结果 / 用例计数、创建时间、混合态徽章。
 * 源任务状态位在 §11-8 `source_task_status` 落地前不渲染、不占位、不显示「—」。
 * 纯 props，不直连 API（数据由宿主经 useContainerComposition 注入）。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue';

const props = defineProps({
  /** 容器溯源数据（useContainerComposition 归一后的 PickSource；null 时不渲染） */
  source: { type: Object, default: null },
  /** 详情 failedCases（混合态徽章判定） */
  failedCases: { type: Number, default: 0 },
  /** 详情 caseCount（用例数 + 混合态分母） */
  caseCount: { type: Number, default: 0 },
  /** 详情 createdAt（ISO / 后端时间串） */
  createdAt: { type: String, default: '' },
});

const rootEl = ref(null);
const popoverOpen = ref(false);

const isCherryPick = computed(() => props.source?.isCherryPick !== false);
const mergeTypeText = computed(() => (isCherryPick.value ? '结果挑选' : '整任务合并'));
const sourceTaskCount = computed(() => props.source?.groups?.length ?? 0);
const sourceResultCount = computed(() => props.source?.total ?? 0);

/** 混合态：0 < failedCases < caseCount → 部分失败 f/c；failedCases === caseCount → 全部失败；= 0 不显示 */
const mixedState = computed(() => {
  const total = Number(props.caseCount ?? 0);
  const failed = Number(props.failedCases ?? 0);
  if (!Number.isFinite(total) || !Number.isFinite(failed) || total <= 0 || failed <= 0) return null;
  if (failed === total) {
    return { text: '全部失败', className: 'chb-badge--destructive', title: `${total} 条用例全部失败` };
  }
  if (failed < total) {
    return {
      text: `部分失败 ${failed}/${total}`,
      className: 'chb-badge--warning',
      title: `${total} 条用例中 ${failed} 条执行失败`,
    };
  }
  return null;
});

/** 创建时间 mono `YYYY-MM-DD HH:mm`（本地时区；无法解析时不渲染该位） */
const createdAtText = computed(() => {
  if (!props.createdAt) return '';
  const date = new Date(props.createdAt);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
});

function togglePopover() {
  popoverOpen.value = !popoverOpen.value;
}

function onDocumentClick(event) {
  if (!popoverOpen.value) return;
  if (rootEl.value && !rootEl.value.contains(event.target)) popoverOpen.value = false;
}

function onKeydown(event) {
  if (event.key === 'Escape') popoverOpen.value = false;
}

watch(popoverOpen, (open) => {
  if (open) {
    document.addEventListener('click', onDocumentClick);
    document.addEventListener('keydown', onKeydown);
  } else {
    document.removeEventListener('click', onDocumentClick);
    document.removeEventListener('keydown', onKeydown);
  }
});

watch(() => props.source, () => { popoverOpen.value = false; });

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick);
  document.removeEventListener('keydown', onKeydown);
});
</script>

<style scoped>
/* 全部取语义令牌（规范 18 §9.2），深浅色同一套成立；不硬编码颜色 / 圆角 / 阴影 */
.container-header-badges {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 12px;
}

.chb-badges {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.chb-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

/* 合并方式徽章：结果挑选 — secondary 系 outline */
.chb-badge--merge-type {
  background: var(--secondary-light);
  color: var(--secondary);
  border: 1px solid var(--secondary);
}

.chb-badge--warning {
  background: var(--warning-light);
  color: var(--warning);
  border: 1px solid var(--warning);
}

.chb-badge--destructive {
  background: var(--destructive-light);
  color: var(--destructive);
  border: 1px solid var(--destructive);
}

.chb-stats {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.chb-stat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--muted);
  border: 1px solid var(--border);
  color: var(--foreground);
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.chb-stat--action {
  cursor: pointer;
  font-family: inherit;
  transition: color 0.2s, border-color 0.2s;
}

.chb-stat--action:hover,
.chb-stat--action.is-open {
  color: var(--primary);
  border-color: var(--primary);
}

.chb-caret {
  font-size: 10px;
  transition: transform 0.2s;
}

.chb-caret.is-open {
  transform: rotate(180deg);
}

.chb-source {
  position: relative;
  display: inline-flex;
}

.chb-popover {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: var(--z-index-dropdown);
  min-width: 240px;
  max-width: 360px;
  padding: 8px 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-md);
}

.chb-popover-title {
  padding: 4px 12px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-foreground);
}

.chb-popover-empty {
  padding: 4px 12px 8px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.chb-popover-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  font-size: 12px;
}

.chb-popover-row:hover {
  background: var(--muted);
}

.chb-popover-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--foreground);
}

.chb-popover-count {
  flex-shrink: 0;
  color: var(--muted-foreground);
  font-variant-numeric: tabular-nums;
}

.chb-created {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted-foreground);
  font-variant-numeric: tabular-nums;
}
</style>
