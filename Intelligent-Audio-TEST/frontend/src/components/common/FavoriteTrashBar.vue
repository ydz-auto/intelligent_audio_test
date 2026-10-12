<template>
  <div class="favorite-trash-bar">
    <label
      class="bar-toggle"
      :class="{ active: favoriteOnly, disabled: favoriteDisabled }"
      title="仅显示我收藏的项目"
    >
      <input
        type="checkbox"
        :checked="favoriteOnly"
        :disabled="favoriteDisabled"
        @change="onFavoriteChange"
      >
      <i class="fas fa-star"></i> 仅看收藏
    </label>
    <button
      class="bar-toggle"
      :class="{ active: trashMode }"
      :title="trashTitle"
      @click="$emit('update:trashMode', !trashMode)"
    >
      <i class="fas fa-trash-restore"></i> 回收站
    </button>
    <button v-if="showRestoreAll && trashMode" class="bar-toggle" :title="restoreAllTitle" @click="$emit('restore-all')">
      <i class="fas fa-undo"></i> 全部恢复
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * FavoriteTrashBar —— 收藏 / 回收站工具栏（INT-215：三视图统一交互口径）
 *
 * 收藏筛选（bar-toggle）+ 回收站开关（+ 可选「全部恢复」），
 * 收敛 Tasks / HistoryReports / TestCaseManager 三处复制的样式块与任务侧裸 checkbox 口径。
 */
withDefaults(defineProps<{
  favoriteOnly?: boolean;
  trashMode?: boolean;
  /** 回收站模式下收藏筛选不可用（favoriteOnly 与 trashMode 互斥） */
  favoriteDisabled?: boolean;
  showRestoreAll?: boolean;
  trashTitle?: string;
  restoreAllTitle?: string;
}>(), {
  favoriteOnly: false,
  trashMode: false,
  favoriteDisabled: false,
  showRestoreAll: false,
  trashTitle: '回收站：已删除项目，可恢复或彻底删除',
  restoreAllTitle: '恢复回收站中的全部项目',
});

const emit = defineEmits<{
  (e: 'update:favoriteOnly', value: boolean): void;
  (e: 'update:trashMode', value: boolean): void;
  (e: 'restore-all'): void;
}>();

const onFavoriteChange = (event: Event) => {
  emit('update:favoriteOnly', (event.target as HTMLInputElement).checked);
};
</script>

<style scoped>
.favorite-trash-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.bar-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--background-primary);
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: inherit;
}
.bar-toggle.active {
  border-color: var(--primary);
  color: var(--primary);
}
.bar-toggle.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.bar-toggle i { color: var(--favorite-star); }
.bar-toggle i.fa-trash-restore,
.bar-toggle i.fa-undo { color: inherit; }
</style>
