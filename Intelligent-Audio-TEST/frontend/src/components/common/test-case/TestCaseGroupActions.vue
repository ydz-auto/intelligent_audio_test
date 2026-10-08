<template>
  <div class="category-actions-container">
    <button 
      class="btn btn-secondary" 
      @click="() => { console.log('[TestCaseGroupActions] Button click: 编辑分组'); $emit('edit'); }"
      :disabled="disabledActions?.includes('edit')"
    >
      <i class="fas fa-edit"></i> 编辑
    </button>
    
    <button 
      class="btn btn-danger" 
      @click="() => { console.log('[TestCaseGroupActions] Button click: 删除分组'); $emit('delete'); }"
      :disabled="disabledActions?.includes('delete')"
    >
      <i class="fas fa-trash"></i> 删除
    </button>
    
    <button 
      class="btn btn-primary" 
      @click="() => { console.log('[TestCaseGroupActions] Button click: 新增用例到分组'); $emit('addCase'); }"
      :disabled="disabledActions?.includes('addCase')"
    >
      <i class="fas fa-plus"></i> 新增用例
    </button>

    <button 
      class="btn btn-info" 
      @click="() => { console.log('[TestCaseGroupActions] Button click: 复制分组'); $emit('copyGroup'); }"
      :disabled="disabledActions?.includes('copyGroup')"
    >
      <i class="fas fa-copy"></i> 复制
    </button>

    <div class="dropdown-container">
      <button 
        class="btn btn-warning dropdown-toggle" 
        @click.stop="$emit('toggleBatchMenu')"
        :disabled="disabledActions?.includes('batchUpdate')"
      >
        <i class="fas fa-cog"></i> 批量修改
      </button>
      <div class="dropdown-menu" v-if="showBatchMenu" @click.stop>
        <button class="dropdown-item" @click="() => { $emit('updateAlgorithmParams'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-sliders-h"></i> 用例专属参数
        </button>
        <button class="dropdown-item" @click="() => { $emit('updatePlaybackDevice'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-volume-up"></i> 播放设备
        </button>
        <button class="dropdown-item" @click="() => { $emit('updateSPL'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-wave-square"></i> 声压
        </button>
        <button class="dropdown-item" @click="() => { $emit('adjustGroup'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-folder"></i> 调整分组
        </button>
        <button class="dropdown-item" @click="() => { $emit('updateDimensions'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-chart-pie"></i> 评价维度
        </button>
        <button class="dropdown-item" @click="() => { $emit('updateNoise'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-volume-up"></i> 噪声
        </button>
        <button class="dropdown-item" @click="() => { $emit('autoGenerateName'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-magic"></i> 标签生成名称
        </button>
        <button class="dropdown-item" @click="() => { $emit('updateTags'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-tags"></i> 管理标签
        </button>
        <button class="dropdown-item" @click="() => { $emit('refreshReference'); $emit('toggleBatchMenu'); }">
          <i class="fas fa-sync-alt"></i> 用例参考更新
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  disabledActions: { type: Array, default: () => [] },
  showBatchMenu: { type: Boolean, default: false }
});

const emit = defineEmits(['edit', 'delete', 'addCase', 'copyGroup', 'updateAlgorithmParams', 'updatePlaybackDevice', 'updateSPL', 'adjustGroup', 'updateDimensions', 'updateNoise', 'autoGenerateName', 'updateTags', 'refreshReference', 'toggleBatchMenu']);
</script>

<style scoped>
.category-actions-container {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dropdown-container {
  position: relative;
}

.dropdown-toggle::after {
  display: inline-block;
  margin-left: 0.255em;
  vertical-align: 0.255em;
  content: "";
  border-top: 0.3em solid;
  border-right: 0.3em solid transparent;
  border-left: 0.3em solid transparent;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  min-width: 160px;
  padding: 0.5rem 0;
  margin: 0.125rem 0 0;
  background-color: var(--background);
  background-clip: padding-box;
  border: 1px solid color-mix(in srgb, var(--color-black) 15%, transparent);
  border-radius: 0.25rem;
  box-shadow: 0 0.5rem 1rem color-mix(in srgb, var(--color-black) 17.5%, transparent);
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 0.5rem 1rem;
  clear: both;
  font-weight: 400;
  color: var(--color-gray-800);
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
}

.dropdown-item:hover {
  background-color: var(--muted);
  color: var(--color-gray-900);
}

.btn-warning {
  color: var(--color-gray-800);
  background-color: var(--color-amber-500);
  border-color: var(--color-amber-500);
}

.btn-warning:hover {
  background-color: var(--color-amber-500);
  border-color: var(--color-amber-600);
}

.btn-info {
  color: var(--background);
  background-color: var(--color-cyan-500);
  border-color: var(--color-cyan-500);
}

.btn-info:hover {
  background-color: var(--color-cyan-600);
  border-color: var(--color-cyan-700);
}
</style>
