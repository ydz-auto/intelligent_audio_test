<template>
  <div class="dt-dialog-overlay" @click.self="emit('close')">
    <div class="dt-dialog">
      <div class="dt-dialog-header">
        <h3>导入任务数据</h3>
        <button class="dt-close-btn" @click="emit('close')"><i class="fas fa-times"></i></button>
      </div>

      <div class="dt-dialog-body">
        <!-- 步骤 1：选择文件 + 预检 -->
        <section v-if="phase === 'select'" class="dt-section">
          <label class="dt-file-label">
            <input type="file" accept=".zip" @change="onFileChange" />
          </label>
          <div v-if="previewing" class="dt-info"><i class="fas fa-spinner fa-spin"></i> 正在解析导出包…</div>
          <div v-if="errorMessage" class="dt-error">{{ errorMessage }}</div>
        </section>

        <!-- 步骤 2：预检结果 -->
        <section v-if="preview" class="dt-section">
          <h4>预检结果</h4>
          <div class="dt-meta">
            <div>版本：{{ preview.version }}　导出时间：{{ preview.exportedAt || '未知' }}</div>
            <div>源服务器：{{ preview.source || '未知' }}</div>
          </div>
          <ul class="dt-task-list">
            <li v-for="task in preview.tasks" :key="task.id">
              <span class="dt-task-name">{{ task.name }}</span>
              <span class="dt-task-meta">{{ task.type }} · {{ task.status }} · {{ task.resultCount }} 条结果</span>
            </li>
          </ul>
          <div class="dt-stats">
            任务 {{ preview.stats.taskCount }} · 结果 {{ preview.stats.resultCount }} ·
            维度评分 {{ preview.stats.dimensionCount }} · 报告 {{ preview.stats.reportCount }} ·
            文件 {{ preview.stats.fileCount }}
          </div>
          <div v-if="preview.conflicts.length" class="dt-warn">
            <i class="fas fa-exclamation-triangle"></i>
            {{ preview.conflicts.length }} 条 ID 冲突，导入时将自动重映射
          </div>
          <ul v-if="preview.warnings.length" class="dt-warning-list">
            <li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li>
          </ul>
        </section>

        <!-- 步骤 3：导入进度 -->
        <section v-if="phase === 'importing' || phase === 'done' || phase === 'error'" class="dt-section">
          <h4>导入进度</h4>
          <div class="dt-progress-track">
            <div class="dt-progress-bar" :style="{ width: progressPercent + '%' }"
                 :class="{ 'dt-progress-error': progress.step === 'error' }"></div>
          </div>
          <div class="dt-progress-text">
            {{ progressText }}（{{ progress.percentage || 0 }}%）
          </div>
        </section>

        <!-- 步骤 4：导入结果 -->
        <section v-if="result" class="dt-section">
          <h4>导入完成</h4>
          <div class="dt-stats">
            任务 {{ result.importedTasks }} · 结果 {{ result.importedResults }} ·
            维度评分 {{ result.importedDimensions }} · 报告 {{ result.importedReports }} ·
            文件 {{ result.importedFiles }}
          </div>
          <div v-if="remapText" class="dt-warn"><i class="fas fa-random"></i> {{ remapText }}</div>
          <div v-if="errorMessage" class="dt-error">{{ errorMessage }}</div>
        </section>
      </div>

      <div class="dt-dialog-footer">
        <button v-if="phase !== 'importing'" class="dt-btn" @click="emit('close')">
          {{ result ? '关闭' : '取消' }}
        </button>
        <button v-if="preview && phase === 'select'" class="dt-btn dt-btn-primary" @click="startImport"
                :disabled="importing">
          <i class="fas fa-upload"></i> 开始导入
        </button>
        <button v-if="result" class="dt-btn dt-btn-primary" @click="emit('imported'); emit('close')">
          查看任务
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { dataTransferPort } from '../../composables/task/dataTransferPort';
import type { ImportPreview, ImportResult, ImportProgress } from '../../domain/model/dataTransfer';

const emit = defineEmits(['close', 'imported']);

type Phase = 'select' | 'importing' | 'done' | 'error';

const phase = ref<Phase>('select');
const selectedFile = ref<File | null>(null);
const preview = ref<ImportPreview | null>(null);
const previewing = ref(false);
const errorMessage = ref('');
const result = ref<ImportResult | null>(null);
const progress = ref<ImportProgress>({
  step: 'parsing', currentTable: '', processedRows: 0,
  totalRows: 0, percentage: 0, message: '', batchId: '',
});

let unsubscribe: (() => void) | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

const importing = computed(() => phase.value === 'importing');

const progressPercent = computed(() => {
  if (phase.value === 'done') return 100;
  return Math.min(Math.max(progress.value.percentage || 0, 0), 100);
});

const STEP_TEXT: Record<string, string> = {
  parsing: '解析导出包',
  writing_db: '写入数据库',
  extracting_files: '回写文件',
  updating_paths: '更新文件路径',
  done: '导入完成',
  error: '导入失败',
};

const progressText = computed(() => {
  const stepText = STEP_TEXT[progress.value.step] || progress.value.step;
  const table = progress.value.currentTable ? `（${progress.value.currentTable}）` : '';
  const rows = progress.value.totalRows > 0
    ? ` ${progress.value.processedRows}/${progress.value.totalRows}`
    : '';
  return `${stepText}${table}${rows} ${progress.value.message || ''}`;
});

const remapText = computed(() => {
  const remaps = result.value?.remappedIds || {};
  const parts: string[] = [];
  const TABLE_NAMES: Record<string, string> = {
    tasks: '任务', test_results: '结果',
    test_result_dimensions: '维度评分', test_reports: '报告',
  };
  for (const [table, mapping] of Object.entries(remaps)) {
    const count = Object.keys(mapping || {}).length;
    if (count > 0) parts.push(`${TABLE_NAMES[table] || table} ID ${count} 条`);
  }
  return parts.length ? `发生 ID 重映射：${parts.join('，')}` : '';
});

const onFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  selectedFile.value = file;
  preview.value = null;
  errorMessage.value = '';
  previewing.value = true;
  try {
    preview.value = await dataTransferPort.previewImport(file);
  } catch (e: any) {
    errorMessage.value = e?.message || '预检失败：无法解析该导出包';
    preview.value = null;
  } finally {
    previewing.value = false;
  }
};

const startImport = async () => {
  if (!selectedFile.value) return;
  errorMessage.value = '';
  result.value = null;
  phase.value = 'importing';
  // 实时进度：SocketIO 订阅 + 快照轮询双保险
  unsubscribe = dataTransferPort.onImportProgress(p => { progress.value = p; });
  pollTimer = setInterval(pollProgress, 3000);
  try {
    result.value = await dataTransferPort.executeImport(selectedFile.value);
    phase.value = 'done';
  } catch (e: any) {
    errorMessage.value = e?.message || '导入失败';
    phase.value = 'error';
  } finally {
    stopWatching();
  }
};

const pollProgress = async () => {
  try {
    const snapshot = await dataTransferPort.getImportProgress();
    if (snapshot && typeof snapshot === 'object' && 'step' in snapshot) {
      // 快照兜底：仅在 socket 尚未推送时更新（避免回退旧值）
      if (progress.value.percentage === 0 || progress.value.step === 'parsing') {
        progress.value = {
          step: (snapshot.step as ImportProgress['step']) || 'parsing',
          currentTable: String(snapshot.current_table ?? ''),
          processedRows: Number(snapshot.processed_rows ?? 0),
          totalRows: Number(snapshot.total_rows ?? 0),
          percentage: Number(snapshot.percentage ?? 0),
          message: String(snapshot.message ?? ''),
          batchId: String(snapshot.batch_id ?? ''),
        };
      }
    }
  } catch {
    // 快照兜底失败忽略（socket 为主通道）
  }
};

const stopWatching = () => {
  if (unsubscribe) { unsubscribe(); unsubscribe = null; }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
};

onUnmounted(stopWatching);
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
  width: 560px;
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
.dt-file-label input { font-size: 13px; }
.dt-meta { font-size: 12px; color: var(--text-secondary, #666); margin-bottom: 8px; }
.dt-task-list { list-style: none; margin: 0 0 8px; padding: 0; max-height: 140px; overflow-y: auto; }
.dt-task-list li { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.dt-task-meta { color: var(--text-secondary, #888); }
.dt-stats { font-size: 12px; color: var(--text-secondary, #666); margin-bottom: 6px; }
.dt-warn { font-size: 12px; color: var(--warning-color, #b8860b); margin: 6px 0; }
.dt-warning-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; color: var(--warning-color, #b8860b); }
.dt-error { color: var(--danger-color, #d9534f); font-size: 13px; margin-top: 8px; }
.dt-info { color: var(--text-secondary, #666); font-size: 13px; margin-top: 8px; }
.dt-progress-track {
  height: 10px;
  border-radius: 5px;
  background: var(--border-color, #e5e7eb);
  overflow: hidden;
  margin-bottom: 6px;
}
.dt-progress-bar {
  height: 100%;
  background: var(--primary-color, #3b82f6);
  transition: width 0.4s ease;
}
.dt-progress-error { background: var(--danger-color, #d9534f); }
.dt-progress-text { font-size: 12px; color: var(--text-secondary, #666); }
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
