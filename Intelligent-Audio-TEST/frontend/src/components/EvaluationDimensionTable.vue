<template>
  <div class="table-container">
    <table class="data-table">
      <thead>
        <tr>
          <th class="checkbox-column" style="width: 50px;">
            <input
              v-if="showHeaderCheckbox"
              type="checkbox"
              id="selectAll"
              :checked="isAllSelected"
              @change="emit('toggle-select-all')"
            >
          </th>
          <th class="dimension-name-col sortable" style="width: 200px;">维度名称</th>
          <th class="dimension-description-col" style="width: 250px;">描述</th>
          <th class="dimension-category-col sortable" style="width: 120px;">分类</th>
          <th class="dimension-algorithms-col" style="width: 260px;">关联算法</th>
          <th class="dimension-weight-col sortable" style="width: 150px;">权重</th>
          <th class="dimension-api-status-col sortable" style="width: 120px;">API状态</th>
          <th class="dimension-status-col sortable" style="width: 100px;">状态</th>
          <th class="dimension-sort-col" style="width: 90px;">排序</th>
          <th class="dimension-actions-col" style="width: 340px;">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="dimension in items"
          :key="dimension.id"
          :class="{ 'sub-dimension-row': dimension._level === 1 }"
          @click="emit('toggle-selection', dimension.id)"
        >
          <td class="checkbox-column">
            <input
              type="checkbox"
              class="dimension-checkbox"
              :checked="isSelected(dimension.id)"
              @click.stop
              @change="emit('toggle-selection', dimension.id)"
            >
          </td>
          <td class="dimension-name-col" @click.stop="emit('edit', dimension.id)">
            <div class="dimension-name-cell" :style="{ paddingLeft: dimension._level === 1 ? '28px' : '0' }">
              <span v-if="dimension._level === 1" class="tree-branch">└</span>
              <span class="dimension-type-badge" :class="dimension._isMain ? 'main-dim-badge' : 'sub-dim-badge'">
                {{ dimension._isMain ? '主' : '子' }}
              </span>
              <span class="dimension-name-text">{{ dimension.name }}</span>
              <span v-if="dimension._level === 1 && dimension._parentName" class="parent-name-hint">（{{ dimension._parentName }}）</span>
            </div>
          </td>
          <td class="dimension-description-col text-truncate" :title="dimension.description">{{ dimension.description || '-' }}</td>
          <td class="dimension-category-col">{{ dimension.category || dimension.type }}</td>
          <td class="dimension-algorithms-col">
            <div class="algorithm-tags" v-if="dimension.associatedAlgorithms && dimension.associatedAlgorithms.length > 0">
              <span class="algo-tag" v-for="algo in dimension.associatedAlgorithms" :key="algo.algorithmType" :class="{ 'is-default': algo.isDefault }">
                {{ getAlgorithmLabel(algo.algorithmType) }}
              </span>
            </div>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="dimension-weight-col">
            <div class="weight-control">
              <input type="range" class="weight-slider" min="1" max="10" :value="dimension.weight" @input="emit('weight-change', { id: dimension.id, weight: Number($event.target.value) })" @click.stop>
              <span class="weight-value">{{ dimension.weight }}</span>
            </div>
          </td>
          <td class="dimension-api-status-col">
            <span v-if="isLlmJudge(dimension)" class="api-status llm-judge">
              <i class="fas fa-robot"></i> LLM Judge
            </span>
            <span v-else class="api-status" :class="dimension.apiStatus">
              <i class="fas fa-circle" :class="dimension.apiStatus === 'online' ? 'online-indicator' : 'offline-indicator'"></i> {{ dimension.apiStatus === 'online' ? '在线' : '离线' }}
            </span>
          </td>
          <td class="dimension-status-col"><span class="status-badge" :class="dimension.status ? 'active' : 'inactive'">{{ dimension.status ? '启用' : '禁用' }}</span></td>
          <td class="dimension-sort-col">
            <div class="sort-control" @click.stop>
              <button class="sort-btn" :disabled="!canMoveUp(dimension)" @click="emit('move', { id: dimension.id, direction: -1 })" title="上移">
                <i class="fas fa-chevron-up"></i>
              </button>
              <button class="sort-btn" :disabled="!canMoveDown(dimension)" @click="emit('move', { id: dimension.id, direction: 1 })" title="下移">
                <i class="fas fa-chevron-down"></i>
              </button>
            </div>
          </td>
          <td class="dimension-actions-col">
            <div class="action-buttons">
              <button class="btn btn-text btn-primary" @click.stop="emit('edit', dimension.id)">
                <i class="fas fa-edit btn-icon"></i>
                编辑
              </button>
              <button class="btn btn-text btn-info" @click.stop="emit('test-api', dimension.id)">
                <i class="fas fa-heartbeat btn-icon"></i>
                测试API
              </button>
              <button class="btn btn-text btn-danger" @click.stop="emit('delete', dimension.id)">
                <i class="fas fa-trash btn-icon"></i>
                删除
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
// 评估维度表格公共组件：列表视图与分组视图共用，避免表格模板重复
const props = defineProps({
  items: { type: Array, default: () => [] },
  selectedDimensions: { type: Array, default: () => [] },
  isAllSelected: { type: Boolean, default: false },
  showHeaderCheckbox: { type: Boolean, default: true },
  canMoveUp: { type: Function, default: () => () => false },
  canMoveDown: { type: Function, default: () => () => false },
  getAlgorithmLabel: { type: Function, required: true },
  isLlmJudge: { type: Function, required: true }
});

const emit = defineEmits([
  'toggle-select-all',
  'toggle-selection',
  'edit',
  'test-api',
  'delete',
  'weight-change',
  'move'
]);

const isSelected = (id) => props.selectedDimensions.includes(id);
</script>

<style scoped>
/* 全局 .data-table 为 table-layout: fixed + width:100%，窄窗口下列会按比例压扁。
   设 min-width = 列宽总和，窄屏改为横向滚动、列保持设计宽度不挤压 */
.table-container {
  overflow-x: auto;
}

.table-container .data-table {
  width: 100% !important;
  min-width: 1680px !important;
}

/* 操作列按钮不换行、不压缩 */
.table-container .dimension-actions-col .action-buttons {
  white-space: nowrap;
}

/* === 层级展示样式（主/子维度徽章等，原在父组件 scoped，子组件需自带） === */

/* 子维度行背景微调 */
.sub-dimension-row {
  background-color: var(--background-secondary, #fafafa);
}

.sub-dimension-row:hover {
  background-color: var(--background-tertiary, #f5f5f5);
}

/* 维度名称单元格容器 */
.dimension-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
}

/* 树形分支符号 */
.tree-branch {
  color: var(--text-light, #999);
  font-size: 16px;
  font-family: monospace;
  margin-right: 2px;
  flex-shrink: 0;
}

/* 主维度/子维度类型标签 */
.dimension-type-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
  flex-shrink: 0;
}

.main-dim-badge {
  background-color: var(--primary-light, #fff3e0);
  color: var(--primary-color, #ff6a00);
  border: 1px solid var(--primary-color, #ff6a00);
}

.sub-dim-badge {
  background-color: #e8f5e9;
  color: #2e7d32;
  border: 1px solid #2e7d32;
}

/* 维度名称文字 */
.dimension-name-text {
  font-weight: var(--font-weight-medium, 500);
  color: var(--text-primary);
}

/* 父维度提示文字 */
.parent-name-hint {
  font-size: 12px;
  color: var(--text-light, #999);
  white-space: nowrap;
}

/* 排序按钮样式 */
.sort-control {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--background-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
}

.sort-btn:hover:not(:disabled) {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: var(--primary-color-light, rgba(22, 119, 255, 0.06));
}

.sort-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* 关联算法标签样式 */
.algorithm-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.algo-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  border-radius: 4px;
  background-color: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.algo-tag.is-default {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-color: var(--primary-color);
}

.text-muted {
  color: var(--text-light);
}

/* LLM Judge 维度标签样式 */
.api-status.llm-judge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 16px;
  border: none;
}

.api-status.llm-judge i {
  font-size: 11px;
}
</style>
