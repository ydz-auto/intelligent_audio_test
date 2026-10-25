<template>
  <!-- §7「无报告」态 / §8.2 线框：容器详情报告区（容器无执行过程 → 引导手动生成） -->
  <section class="crc" aria-labelledby="container-report-title">
    <header class="crc-header">
      <h4 id="container-report-title" class="crc-title">报告</h4>
      <button
        v-if="report && canRead"
        type="button"
        class="btn btn-secondary btn-sm crc-view"
        @click="openReport"
      >
        查看报告
      </button>
    </header>

    <!-- 加载中：骨架（不闪「暂无报告」） -->
    <div v-if="loading" class="crc-skeleton" data-testid="container-report-skeleton" aria-hidden="true"></div>

    <!-- 列表加载失败：空态 + 重试（不阻断详情其余区域） -->
    <div v-else-if="error" class="crc-empty">
      <i class="fas fa-arrows-rotate"></i>
      <p class="crc-empty-title">报告加载失败</p>
      <p class="crc-empty-desc">该任务的报告列表没能加载出来</p>
      <button type="button" class="btn btn-secondary btn-sm" data-layout-btn @click="retry">重试</button>
    </div>

    <!-- 已有报告：名称 + 状态 + ID -->
    <div v-else-if="report" class="crc-row">
      <span class="crc-name" :title="report.name">{{ report.name }}</span>
      <span class="crc-status" :class="{ 'crc-status--published': report.status === 'published' }">
        {{ report.status === 'published' ? '已发布' : '草稿' }}
      </span>
      <span class="crc-id">ID {{ report.id }}</span>
    </div>

    <!-- 生成中：后端异步落库，轮询期间不谎报「暂无报告」 -->
    <div v-else-if="generating" class="crc-empty">
      <i class="fas fa-arrows-rotate fa-spin"></i>
      <p class="crc-empty-title">报告生成中…</p>
      <p class="crc-empty-desc">生成完成后自动显示报告入口</p>
    </div>

    <!-- 无报告：引导手动生成（§7 / §11） -->
    <div v-else class="crc-empty">
      <i class="fas fa-file-lines"></i>
      <p class="crc-empty-title">该合并任务暂无报告</p>
      <p class="crc-empty-desc">合并任务无执行过程，报告需手动生成</p>
      <button
        v-if="canCreate"
        type="button"
        class="btn btn-primary btn-sm"
        data-layout-btn
        :disabled="generating"
        @click="generate"
      >生成报告</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/layouts/main.css'

/**
 * ContainerReportCard —— 挑选合并容器详情「报告」区（INT-1837 · 规范 18 §7 / §8.2 / §11）。
 *
 * 容器无执行过程、不自动生成报告 → 空态直接引导手动生成；已有报告给「查看报告」入口。
 * 数据 / 生成 / 轮询在 `useContainerReport`（既有 `/reports?task_id=` 与
 * `/reports/generate-task`，不新增端点）；权限按 `report:read` / `report:create` 门控。
 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../../store/authStore';
import { useContainerReport } from '../../composables/task/useContainerReport';

const props = defineProps<{
  /** 容器任务 ID（模态窗 taskId 为 string | number） */
  taskId: number | string;
}>();

defineOptions({ name: 'ContainerReportCard' });

const router = useRouter();
const { hasPermission } = useAuthStore();
const canRead = computed(() => hasPermission('report:read'));
const canCreate = computed(() => hasPermission('report:create'));

const taskIdRef = computed(() => Number(props.taskId));
const { report, loading, error, generating, retry, generate } = useContainerReport(taskIdRef);

function openReport() {
  if (!report.value) return;
  router.push({ name: 'reportView', params: { id: String(report.value.id) } });
}
</script>

<style scoped>
/* 语义令牌（规范 18 §9.2）；圆角/阴影/颜色不硬编码 */
.crc {
  margin-top: 24px;
  padding: 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-sm);
}

.crc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.crc-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.crc-view {
  margin-left: auto;
}

.crc-skeleton {
  height: 64px;
  border-radius: var(--radius-card);
  background: var(--muted);
}

.crc-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
}

.crc-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.crc-status {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 11px;
}

.crc-status--published {
  border-color: var(--success);
  background: var(--success-light);
  color: var(--success);
}

.crc-id {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: var(--muted-foreground);
}

.crc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-card);
  color: var(--muted-foreground);
  text-align: center;
}

.crc-empty i {
  font-size: 24px;
  color: var(--muted-foreground);
}

.crc-empty-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.crc-empty-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
