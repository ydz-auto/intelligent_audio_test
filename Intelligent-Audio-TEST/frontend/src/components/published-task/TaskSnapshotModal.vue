<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal task-snapshot-modal">
        <div class="modal-header">
          <h3 class="modal-title">
            <i class="fas fa-file-invoice"></i> 任务详情（发布时冻结）
            <span class="modal-subtitle">（不可变 · 不随源任务/源用例改动变化）</span>
          </h3>
          <div class="header-actions">
            <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
          </div>
        </div>

        <div class="modal-scroll-container">
          <!-- 任务基本信息 -->
          <section class="ts-section">
            <h4 class="ts-section-title"><i class="fas fa-tasks"></i> 任务信息</h4>
            <div class="ts-kv-grid">
              <div class="ts-kv"><span class="ts-kv-label">名称</span><span class="ts-kv-value">{{ taskInfo.name || '-' }}</span></div>
              <div class="ts-kv" v-if="taskInfo.description"><span class="ts-kv-label">说明</span><span class="ts-kv-value">{{ taskInfo.description }}</span></div>
              <div class="ts-kv"><span class="ts-kv-label">算法类型</span><span class="ts-kv-value">{{ taskInfo.algorithmType || '-' }}</span></div>
              <div class="ts-kv" v-if="taskTags.length"><span class="ts-kv-label">标签</span><span class="ts-kv-value">{{ taskTags.join('、') }}</span></div>
            </div>
          </section>

          <!-- 关联设备 / API / 播放设备引用快照 -->
          <section class="ts-section" v-if="refsRows.length">
            <h4 class="ts-section-title"><i class="fas fa-plug"></i> 关联资源（发布时冻结）</h4>
            <div v-for="row in refsRows" :key="row.kind" class="ts-kv">
              <span class="ts-kv-label">{{ row.kind }}</span>
              <span class="ts-kv-value">{{ row.text }}</span>
            </div>
          </section>

          <!-- 用例完整配置深拷贝 -->
          <section class="ts-section">
            <h4 class="ts-section-title"><i class="fas fa-list-check"></i> 用例（{{ cases.length }}）</h4>
            <div v-if="cases.length === 0" class="ts-empty">冻结体无用例数据</div>
            <details v-for="c in cases" :key="c.caseId" class="ts-case">
              <summary class="ts-case-summary">
                <span class="ts-case-name">{{ c.name || c.caseId }}</span>
                <span class="ts-case-tag" v-if="c.algorithmType">{{ c.algorithmType }}</span>
                <span class="ts-case-tag" v-if="c.deviceType">{{ deviceTypeLabel(c.deviceType) }}</span>
                <span class="ts-case-meta" v-if="roundCount(c)">{{ roundCount(c) }} 轮</span>
                <span class="ts-case-meta" v-if="c.tags?.length">{{ c.tags.join('、') }}</span>
                <span class="ts-case-meta" v-if="c.group?.name">{{ c.group.name }}</span>
              </summary>
              <div class="ts-case-body">
                <div class="ts-kv" v-if="c.description"><span class="ts-kv-label">描述</span><span class="ts-kv-value">{{ c.description }}</span></div>
                <div class="ts-json-block"><pre>{{ prettyJson(c.config) }}</pre></div>
                <div class="ts-json-block" v-if="c.algorithmParams && Object.keys(c.algorithmParams).length">
                  <div class="ts-json-label">算法参数</div>
                  <pre>{{ prettyJson(c.algorithmParams) }}</pre>
                </div>
                <div class="ts-json-block" v-if="(c.referenceParams?.length ?? 0) > 0">
                  <div class="ts-json-label">参考参数（内容内联 · {{ c.referenceParams!.length }} 轮）</div>
                  <pre>{{ prettyJson(compactRefParams(c.referenceParams!)) }}</pre>
                </div>
              </div>
            </details>
          </section>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue';
import type { TaskSnapshot } from '../../domain/model/publishedTask';

const props = defineProps<{ snapshot: TaskSnapshot }>();
const emit = defineEmits<{ (e: 'close'): void }>();

const taskInfo = computed(() => props.snapshot?.task ?? {});
const taskTags = computed(() => props.snapshot?.task?.tags ?? []);
const cases = computed(() => props.snapshot?.cases ?? []);

const refsRows = computed(() => {
  const rows: { kind: string; text: string }[] = [];
  const fmt = (list: { id: number; name?: string | null }[] | undefined) =>
    (list ?? []).map((r) => (r.name ? `${r.name} (#${r.id})` : `#${r.id}`)).join('、');
  const devices = fmt(props.snapshot?.devices);
  const apis = fmt(props.snapshot?.apis);
  const playbacks = fmt(props.snapshot?.playbackDevices);
  if (devices) rows.push({ kind: '被测设备', text: devices });
  if (apis) rows.push({ kind: 'API', text: apis });
  if (playbacks) rows.push({ kind: '播放设备', text: playbacks });
  return rows;
});

function roundCount(c: { config?: Record<string, unknown> | null }): number {
  const rounds = (c.config as any)?.rounds;
  return Array.isArray(rounds) ? rounds.length : 0;
}

function deviceTypeLabel(dt: string): string {
  const map: Record<string, string> = {
    physical: 'E2E',
    http_api: 'API',
    websocket_api: 'API(WS)',
  };
  return map[dt] ?? dt;
}

function prettyJson(val: unknown): string {
  try {
    return JSON.stringify(val, null, 2) ?? '-';
  } catch {
    return String(val);
  }
}

/** 参考参数渲染压缩：逐轮只显示条数与前两条示例（全量数据大，弹窗内不整屏铺开） */
function compactRefParams(list: { roundNumber?: number | null; referenceParams: unknown[] }[]) {
  return list.map((r) => ({
    roundNumber: r.roundNumber,
    itemCount: r.referenceParams?.length ?? 0,
    sample: (r.referenceParams ?? []).slice(0, 2),
  }));
}

function handleClose() {
  emit('close');
}
</script>

<style scoped>
/* opacity/visibility 显式声明，规避全局 .modal-overlay{visibility:hidden;opacity:0}
   （test-case-manager.css，仅 .active 才可见）串扰；transform: none 对齐全局 .modal 位移 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 13000;
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: #fff;
  border-radius: var(--radius-xl);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transform: none;
}

.task-snapshot-modal {
  width: 960px;
  max-width: 96vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  flex-shrink: 0;
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
}

.modal-title i {
  color: #ff6a00;
}

.modal-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
}

.modal-scroll-container {
  max-height: calc(90vh - 58px);
  overflow-y: auto;
  flex: 1;
  padding: 16px 20px;
  background-color: #fff;
}

.ts-section {
  margin-bottom: 18px;
}

.ts-section-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ts-section-title i {
  color: #ff6a00;
}

.ts-kv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
}

.ts-kv {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 5px 8px;
  background: #f8fafc;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 4px;
}

.ts-kv-label {
  flex-shrink: 0;
  color: #9ca3af;
  min-width: 64px;
}

.ts-kv-value {
  color: #1f2937;
  word-break: break-all;
}

.ts-empty {
  padding: 20px;
  text-align: center;
  color: #94a3b8;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: var(--radius-md);
  font-size: 13px;
}

.ts-case {
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  overflow: hidden;
}

.ts-case-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  cursor: pointer;
  background: #fafafa;
  user-select: none;
  list-style: none;
}

.ts-case-summary::-webkit-details-marker {
  display: none;
}

.ts-case-summary::before {
  content: '▸';
  color: #9ca3af;
  transition: transform 0.15s;
}

.ts-case[open] .ts-case-summary::before {
  transform: rotate(90deg);
}

.ts-case-name {
  font-weight: 600;
  color: #1f2937;
  font-size: 13px;
}

.ts-case-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: #fff1e6;
  color: #ff6a00;
  white-space: nowrap;
}

.ts-case-meta {
  font-size: 12px;
  color: #9ca3af;
}

.ts-case-body {
  padding: 10px 12px;
  border-top: 1px solid #f0f0f0;
}

.ts-json-block {
  margin-top: 8px;
}

.ts-json-label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.ts-json-block pre {
  margin: 0;
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-md);
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 320px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
