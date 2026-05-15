<template>
  <!-- 图表操作按钮（仅在有数据时显示） -->
  <div class="chart-actions-container">
    <div class="chart-actions">
      <button class="btn btn-secondary" @click="handleResetZoom">
        <i class="fas fa-search-plus"></i> 重置缩放
      </button>
      <button class="btn btn-primary" @click="handleExportChart">
        <i class="fas fa-download"></i> 导出
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  hasData?: boolean;
}

withDefaults(defineProps<Props>(), {
  hasData: false
});

const emit = defineEmits<{
  (e: 'resetZoom'): void;
  (e: 'exportChart'): void;
}>();

// 处理重置缩放
const handleResetZoom = () => {
  emit('resetZoom');
};

// 处理导出图表
const handleExportChart = () => {
  emit('exportChart');
};
</script>

<style scoped>
.chart-actions-container {
  margin-bottom: 20px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.chart-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: #f8fafc;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
}

.btn-primary {
  background: linear-gradient(90deg, #FF6A00, #1677FF);
  color: white;
}

.btn-primary:hover {
  opacity: 0.9;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.btn-secondary {
  background: white;
  color: #666;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover {
  background: #f5f5f5;
  border-color: #1677FF;
}
</style>
