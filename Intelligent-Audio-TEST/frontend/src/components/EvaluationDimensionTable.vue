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
          <th class="dimension-algorithms-col" style="width: 180px;">关联算法</th>
          <th class="dimension-weight-col sortable" style="width: 150px;">权重</th>
          <th class="dimension-api-status-col sortable" style="width: 120px;">API状态</th>
          <th class="dimension-status-col sortable" style="width: 100px;">状态</th>
          <th class="dimension-sort-col" style="width: 90px;">排序</th>
          <th class="dimension-actions-col" style="width: 1%; white-space: nowrap;">操作</th>
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
