<template>
  <div class="dt-dialog-overlay" @click.self="emit('close')">
    <div class="dt-dialog">
      <div class="dt-dialog-header">
        <h3>导出任务数据</h3>
        <button class="dt-close-btn" @click="emit('close')"><i class="fas fa-times"></i></button>
      </div>

      <div class="dt-dialog-body">
        <section class="dt-section">
          <h4>选中任务（{{ tasks.length }} 个）</h4>
          <ul class="dt-task-list">
            <li v-for="task in tasks" :key="task.id">
              <span class="dt-task-name">{{ task.name }}</span>
              <span class="dt-task-meta">{{ task.type }} · {{ task.status }}</span>
            </li>
          </ul>
        </section>

        <section class="dt-section">
          <h4>导出选项</h4>
          <label class="dt-check">
            <input type="checkbox" v-model="includeRefParams" />
            <span>包含参考参数文件</span>
          </label>
          <label class="dt-check">
            <input type="checkbox" v-model="includeAudios" />
            <span>包含音频文件（体积较大）</span>
          </label>
        </section>

        <div v-if="errorMessage" class="dt-error">{{ errorMessage }}</div>
        <div v-if="exporting" class="dt-info">
          <i class="fas fa-spinner fa-spin"></i> 正在打包导出，请稍候…
        </div>
      </div>

      <div class="dt-dialog-footer">
        <button class="dt-btn" @click="emit('close')" :disabled="exporting">取消</button>
        <button class="dt-btn dt-btn-primary" @click="startExport" :disabled="exporting || !tasks.length">
          <i class="fas fa-download"></i> 开始导出
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { dataTransferPort } from '../../composables/task/dataTransferPort';
import { downloadBlob } from '../../utils/utils';

const props = defineProps<{
  tasks: Array<{ id: number | string; name: string; type: string; status: string }>;
}>();

const emit = defineEmits(['close', 'exported']);

const includeRefParams = ref(true);
const includeAudios = ref(false);
const exporting = ref(false);
const errorMessage = ref('');

const startExport = async () => {
  errorMessage.value = '';
  exporting.value = true;
  try {
    const blob = await dataTransferPort.exportTasks(
      props.tasks.map(t => t.id),
      { includeRefParams: includeRefParams.value, includeAudios: includeAudios.value },
    );
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
    downloadBlob(blob, `task_export_${stamp}.zip`);
    emit('exported');
    emit('close');
  } catch (e: any) {
    errorMessage.value = e?.message || '导出失败，请稍后重试';
  } finally {
    exporting.value = false;
  }
};
</script>

<style scoped>
.dt-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.dt-dialog {
  width: 520px;
  max-width: 92vw;
  max-height: 84vh;
  overflow-y: auto;
  background: var(--bg-color, #fff);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
}
.dt-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color, #eee);
}
.dt-dialog-header h3 { margin: 0; font-size: 16px; }
.dt-close-btn { background: none; border: none; cursor: pointer; font-size: 15px; color: inherit; }
.dt-dialog-body { padding: 14px 18px; flex: 1; }
.dt-section { margin-bottom: 14px; }
.dt-section h4 { margin: 0 0 8px; font-size: 13px; color: var(--text-secondary, #666); }
.dt-task-list { list-style: none; margin: 0; padding: 0; max-height: 160px; overflow-y: auto; }
.dt-task-list li { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.dt-task-meta { color: var(--text-secondary, #888); }
.dt-check { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; cursor: pointer; }
.dt-error { color: var(--danger-color, #d9534f); font-size: 13px; margin-top: 8px; }
.dt-info { color: var(--text-secondary, #666); font-size: 13px; margin-top: 8px; }
.dt-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-color, #eee);
}
.dt-btn {
  padding: 7px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-color, #ddd);
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 13px;
}
.dt-btn-primary {
  background: var(--primary-color, #3b82f6);
  border-color: var(--primary-color, #3b82f6);
  color: #fff;
}
.dt-btn:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
