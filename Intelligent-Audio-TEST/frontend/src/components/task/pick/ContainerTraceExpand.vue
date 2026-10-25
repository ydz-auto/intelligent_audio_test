<template>
  <div class="cte" data-testid="container-trace-expand">
    <!-- 组成区树：与容器详情组成区同一套组件 / 纯函数（§3 落点③，不另造树） -->
    <ContainerComposition
      :entries="entries"
      :loading="loading"
      :error="error"
      :source-task-count="sourceTaskCount"
      variant="expand"
      @retry="retry"
      @trace="onTrace"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * ContainerTraceExpand —— 挑选合并页签「行展开」（INT-1834 · 规范 18 §3 落点③ / §4.3）。
 *
 * `picked`（结果挑选）容器行展开即渲染**组成区树**（任务视图默认），与容器详情组成区
 * 共用 `ContainerComposition` + `compositionTree` 纯函数，不另写第二套树。
 *
 * 补拉策略（§4.3）：列表 DTO 只有任务名与计数、无 `cases[]` → 首次展开补 1 次
 * `GET /tasks/{id}`（+ 一次 source 溯源取结果 id 级数据），结果按 `taskId` 缓存在
 * `useContainerComposition` 的 `Map<number, CompositionModel>`；再次展开复用缓存、
 * 收起不释放、不重复请求。补拉失败 → 展开区 Empty + 「重试」，行本体与计数照常（§7）。
 */
import { computed } from 'vue';
import ContainerComposition from './ContainerComposition.vue';
import { useContainerTraceComposition } from '../../../composables/task/useContainerComposition';

const props = defineProps<{
  /** 容器任务 ID（picked 行） */
  taskId: number;
  /** 列表 DTO 的来源任务 / 结果计数（补拉未完成时兜底；缺省不占位） */
  summary?: { taskCount?: number | null; resultCount?: number | null } | null;
}>();

const emit = defineEmits<{
  /** 叶行「溯源」：宿主打开源任务详情并定位来源用例（INT-1838 §6） */
  (e: 'trace', payload: { resultId: number; sourceTaskId: number; sourceCaseId?: string | null }): void;
}>();

defineOptions({ name: 'ContainerTraceExpand' });

const taskIdRef = computed(() => props.taskId);
const { model, loading, error, retry } = useContainerTraceComposition(taskIdRef);

const entries = computed(() => model.value?.entries ?? []);

/** 来源任务数：组成模型到位用 source.groups.length，否则用列表 DTO 计数 */
const sourceTaskCount = computed(
  () => model.value?.taskCount ?? Number(props.summary?.taskCount ?? 0),
);

function onTrace(resultId: number) {
  const entry = model.value?.entries.find((e) => e.resultId === resultId);
  if (!entry) return;
  emit('trace', { resultId, sourceTaskId: entry.sourceTaskId, sourceCaseId: entry.sourceCaseId });
}
</script>

<style scoped>
.cte {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
