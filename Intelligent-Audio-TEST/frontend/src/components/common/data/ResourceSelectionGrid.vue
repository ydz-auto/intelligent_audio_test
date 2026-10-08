<template>
  <div class="resource-grid-container">
    <div class="resource-grid" :class="gridClass">
      <div 
        v-for="item in items" 
        :key="item?.id" 
        class="resource-card" 
        :class="{ 'selected': item && isSelected(item.id) }"
        @click="item && isItemOnline(item) && $emit('toggle-selection', item.id)"
      >
        <div class="card-header">
          <div class="card-info">
            <div class="card-name">{{ item?.name || '未命名资源' }}</div>
            <div class="card-status" :class="`status-${item?.status || DeviceStatus.OFFLINE}`">
              <i class="fas fa-circle" :class="item?.status === DeviceStatus.ONLINE ? 'online-indicator' : 'offline-indicator'"></i>
              {{ item?.status === DeviceStatus.ONLINE ? '在线' : '离线' }}
            </div>
          </div>
          <div class="card-actions">
            <button 
              v-for="action in actions" 
              :key="action.id"
              class="btn-icon-only" 
              :title="action.title"
              :disabled="action.requireOnline && item?.status !== DeviceStatus.ONLINE"
              @click.stop="item && $emit('action-click', { actionId: action.id, itemId: item.id })"
            >
              <i :class="action.icon"></i>
            </button>
          </div>
        </div>

        <div class="card-content">
          <slot name="item-content" :item="item">
            <div class="specs-list">
              <div v-for="(value, label) in getDisplaySpecs(item)" :key="label" class="spec-item">
                <span class="spec-label">{{ label }}:</span>
                <span class="spec-value">{{ value }}</span>
              </div>
            </div>
          </slot>
        </div>

        <div class="card-footer">
          <input 
            type="checkbox" 
            :id="`check-${item?.id || ''}`" 
            class="resource-checkbox" 
            :disabled="item?.status !== DeviceStatus.ONLINE" 
            :checked="item && isSelected(item.id)"
            @click.stop
            @change="item && $emit('toggle-selection', item.id)"
          >
          <label 
            :for="`check-${item?.id || ''}`" 
            class="resource-select-btn" 
            :class="{ disabled: item?.status !== DeviceStatus.ONLINE }" 
            @click.stop
          >
            {{ item?.status === DeviceStatus.ONLINE ? '选择' : '离线' }}
          </label>
        </div>
      </div>
    </div>
    
    <div v-if="items.length === 0" class="empty-resource">
      <i class="fas fa-box-open"></i>
      <p>{{ emptyText }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { DeviceStatus } from '../../../domain/enums';

const props = defineProps({
  items: { type: Array, required: true, default: () => [] },
  selectedIds: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [
      { id: 'test', title: '连接测试', icon: 'fas fa-plug', requireOnline: false },
      { id: 'edit', title: '编辑', icon: 'fas fa-edit', requireOnline: false },
      { id: 'delete', title: '删除', icon: 'fas fa-trash', requireOnline: false }
    ]
  },
  gridClass: { type: String, default: 'standard-grid' },
  emptyText: { type: String, default: '未找到相关资源' },
  displayFields: { type: Array, default: () => [] }
});

const emit = defineEmits(['toggle-selection', 'action-click']);

const isSelected = (id) => props.selectedIds.includes(id);

const isItemOnline = (item) => item?.status === DeviceStatus.ONLINE;

const getDisplaySpecs = (item) => {
  if (!item) return {};
  if (props.displayFields.length > 0) {
    const specs = {};
    props.displayFields.forEach(field => {
      if (item[field.key] !== undefined) {
        specs[field.label] = item[field.key];
      }
    });
    return specs;
  }
  return item.meta || {};
};
</script>

<style scoped>

.spec-label{
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 500;
    min-width: 80px;
}

.spec-value{
    font-size: 14px;
    color: var(--text-primary);
    font-weight: 500;
}






.resource-grid{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.resource-card{
  background: white;
  border-radius: 12px;
  border: 1px solid var(--color-slate-200);
  padding: 16px;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  cursor: pointer;
  height: 100%;
}

.resource-card:hover{
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 15%, transparent);
}

.resource-card.selected{
  border: 2px solid var(--primary-color);
  background-color: color-mix(in srgb, var(--primary) 15%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 20%, transparent), 0 4px 16px color-mix(in srgb, var(--primary) 10%, transparent);
}

.card-header{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  gap: 8px;
}

.card-info{
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.card-name{
  font-weight: 600;
  font-size: 16px;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-status{
  font-size: 12px;
  margin-top: 4px;
}

.online-indicator{ color: var(--success); }
.offline-indicator{ color: var(--color-gray-300); }

.card-actions{
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.btn-icon-only{
  background: transparent;
  border: none;
  color: var(--color-slate-500);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-icon-only:hover:not(:disabled){
  background: var(--muted);
  color: var(--secondary);
}

.card-content{
  flex: 1;
  margin-bottom: 16px;
}

.specs-list{
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.spec-item{
  display: flex;
  font-size: 13px;
}





.card-footer{
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--muted);
  display: flex;
  align-items: center;
  gap: 12px;
}

.resource-checkbox{
  width: 18px;
  height: 18px;
}

.resource-select-btn{
  flex: 1;
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  background: var(--color-slate-50);
  border: 1px solid var(--color-slate-200);
  font-size: 14px;
  cursor: pointer;
}

.resource-card.selected .resource-select-btn{
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.resource-select-btn.disabled{
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-resource{
  text-align: center;
  padding: 60px 0;
  color: var(--color-slate-400);
}

.empty-resource i{
  font-size: 48px;
  margin-bottom: 16px;
}
</style>
